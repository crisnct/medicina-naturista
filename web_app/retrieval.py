"""Local-only retrieval over the existing hybrid index and session documents."""
from __future__ import annotations

import json
import re
import threading
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np

from search_medical_embeddings import create_model, rank
from web_app.sessions import SessionData


def _plain(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


def _split_query(value: str, limit: int = 900) -> list[str]:
    """Split long consultation text without dropping its tail."""
    remaining = " ".join(value.split())
    parts: list[str] = []
    while remaining:
        if len(remaining) <= limit:
            parts.append(remaining)
            break
        boundary = remaining.rfind(" ", 0, limit + 1)
        if boundary < limit // 2:
            boundary = limit
        parts.append(remaining[:boundary].strip())
        remaining = remaining[boundary:].strip()
    return [part for part in parts if part]


def consultation_queries(profile: Any, document_summaries: list[str] | None = None) -> list[str]:
    """Build bounded queries from every meaningful consultation exchange."""
    values: list[str] = []
    structured = " ".join(profile.health_conditions + profile.symptoms).strip()
    if structured:
        values.append(structured)
    if profile.health_problem:
        values.append(profile.health_problem)

    pending_question = ""
    for entry in profile.transcript:
        role = entry.get("role")
        content = str(entry.get("content") or "").strip()
        if not content:
            continue
        if role == "assistant":
            pending_question = content
        elif role == "user":
            values.append(
                f"Întrebare: {pending_question} Răspuns: {content}"
                if pending_question else f"Informație utilizator: {content}"
            )
            pending_question = ""

    values.extend(profile.health_context)
    values.extend(summary[:400] for summary in (document_summaries or []) if summary)
    queries: list[str] = []
    seen: set[str] = set()
    for value in values:
        for part in _split_query(value):
            key = part.casefold()
            if key not in seen:
                seen.add(key)
                queries.append(part)
    return queries


class Retriever:
    def __init__(self, index_dir: Path, documents_dir: Path) -> None:
        self.index_dir = index_dir.resolve()
        self.documents_dir = documents_dir.resolve()
        manifest = json.loads((self.index_dir / "manifest.json").read_text(encoding="utf-8"))
        self.dimension = int(manifest["embedding"]["dimension"])
        self.model = create_model(
            str(manifest["embedding"]["model"]), self.dimension, self.index_dir.parent / "model_cache"
        )
        self._model_lock = threading.Lock()
        if not (self.index_dir / "index.sqlite3").is_file():
            raise FileNotFoundError("Local retrieval index is missing.")

    def _embed(self, texts: list[str], query: bool = False) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        with self._model_lock:
            values = self.model.query_embed([f"query: {text}" for text in texts]) if query else self.model.embed(
                [f"passage: {text}" for text in texts]
            )
            vectors = np.asarray(list(values), dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1)
        return vectors / np.maximum(norms[:, None], 1e-12)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts)

    def _context(self, result: dict[str, Any]) -> str:
        """Read a few neighboring lines from documents/ when the indexed excerpt is short."""
        relative = Path(str(result["source_relative_path"]))
        path = (self.documents_dir / relative).resolve()
        if not path.is_relative_to(self.documents_dir) or not path.is_file():
            return str(result["text"])
        if len(str(result["text"])) >= 600:
            return str(result["text"])
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            start = max(0, int(result["line_start"]) - 5)
            end = min(len(lines), int(result["line_end"]) + 4)
            return "\n".join(lines[start:end])[:1800]
        except (OSError, ValueError):
            return str(result["text"])

    def collect(self, session: SessionData) -> dict[str, dict[str, str]]:
        profile = session.profile
        queries = consultation_queries(profile, [document.summary for document in session.documents])
        if not queries:
            return {}
        search_queries = queries + [f"{query} contraindicații interacțiuni atenționări" for query in queries]
        batches: list[list[dict[str, Any]]] = []
        for search_query in search_queries:
            word_set = {word for word in re.findall(r"\w+", _plain(search_query)) if len(word) >= 4}
            accepted: list[dict[str, Any]] = []
            for result in rank(self.index_dir, search_query, limit=18, candidates=120):
                source_text = " ".join([
                    str(result["source_relative_path"]), str(result["heading"]), str(result["text"])
                ])
                matching = any(word in _plain(source_text) for word in word_set)
                safety = "ATENTIONARI-SI-CONTRAINDICATII" in str(result["source_relative_path"])
                if (result.get("lexical_rank") is not None and matching) or safety:
                    accepted.append(result)
            if accepted:
                batches.append(accepted)

        evidence: dict[str, dict[str, str]] = {}
        positions = [0] * len(batches)
        while len(evidence) < 24:
            progressed = False
            for batch_number, results in enumerate(batches):
                while positions[batch_number] < len(results):
                    result = results[positions[batch_number]]
                    positions[batch_number] += 1
                    token = f"C{result['chunk_id']}"
                    if token in evidence:
                        continue
                    evidence[token] = {
                        "source": f"documents/{result['source_relative_path']}:{result['line_start']}-{result['line_end']}",
                        "text": self._context(result)[:1800],
                    }
                    progressed = True
                    break
                if len(evidence) >= 24:
                    break
            if not progressed:
                break

        query_vectors = self._embed(queries, query=True)
        user_candidates: list[tuple[float, str, dict[str, str]]] = []
        for doc_number, document in enumerate(session.documents, start=1):
            if not len(document.vectors) or not len(query_vectors):
                continue
            all_scores = np.asarray(document.vectors @ query_vectors.T)
            scores = np.max(all_scores, axis=1)
            for row in np.argsort(scores)[-min(5, len(scores)):][::-1]:
                chunk = document.chunks[int(row)]
                token = f"U{doc_number}-{int(row) + 1}"
                user_candidates.append((
                    float(scores[int(row)]), token,
                    {"source": f"fișier încărcat/{document.name}:{chunk['line_start']}-{chunk['line_end']}",
                     "text": str(chunk["text"])[:1800]},
                ))
        for _score, token, value in sorted(user_candidates, reverse=True)[:12]:
            evidence[token] = value
        return evidence
