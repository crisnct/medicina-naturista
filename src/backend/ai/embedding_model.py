"""Shared local embedding model loading and per-model text profiles, used both
when syncing the index (scripts/build_hybrid_index.py) and when embedding a
query (ai/search.py).

Two backends share one interface (`embed(texts, batch_size, parallel)`):
FastEmbed/ONNX fp32 on CPU (queries, and builds without a GPU) and an HTTP client
for the local vLLM embedding server (index builds only; the server runs in the
`vllm-embed` Compose service, so neither the web app nor its Docker image needs
torch)."""

from __future__ import annotations

import json
import os
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np

from backend.config import settings

# Instruction Qwen3-Embedding was trained to expect in front of a query (kept in
# English on purpose; the question itself stays Romanian). FastEmbed does not add
# it. Changing it needs no reindex, but the retrieval evaluation must be rerun.
QWEN_QUERY_TEMPLATE = (
    "Instruct: Given a question about natural medicine in Romanian, retrieve passages "
    "from herbal and naturopathic texts that answer it\nQuery:{text}"
)

# Seconds one embeddings request may take; a request holds at most a few dozen windows.
VLLM_REQUEST_TIMEOUT_SECONDS = 600


# Address of the vllm-embed server on this machine (Compose publishes it on the loopback only).
def vllm_embed_url() -> str:
    return f"http://127.0.0.1:{settings.vllm_embed_port}/v1"


@dataclass(frozen=True)
class EmbeddingProfile:
    """Everything that depends on the embedding model: its vector width, how a
    query and a passage are written for it, and the size of one embedding window."""

    name: str
    dimension: int
    query_template: str  # "{text}" is the user's question
    passage_template: str  # "{text}" is the fragment's context line plus window
    max_chars: int  # a longer fragment is embedded as overlapping windows
    overlap_chars: int

    # The text fed to the model for a user question.
    def query_text(self, query: str) -> str:
        return self.query_template.format(text=query)

    # The text fed to the model for one window of a fragment.
    def passage_text(self, text: str) -> str:
        return self.passage_template.format(text=text)


PROFILES: dict[str, EmbeddingProfile] = {
    profile.name: profile
    for profile in (
        EmbeddingProfile(
            "Qwen/Qwen3-Embedding-0.6B", 1024, QWEN_QUERY_TEMPLATE, "{text}", 1400, 240
        ),
    )
}

# The model the index is built with and queried with, unless --model says otherwise.
DEFAULT_MODEL = "Qwen/Qwen3-Embedding-0.6B"


# Profile of a known model; an unknown name is an error, never a silent guess.
def get_profile(model_name: str) -> EmbeddingProfile:
    try:
        return PROFILES[model_name]
    except KeyError:
        raise ValueError(
            f"Unknown embedding model {model_name!r}; known models: {', '.join(sorted(PROFILES))}"
        ) from None


# Normalize cached FastEmbed metadata paths so Windows caches work in Linux containers.
def _normalize_fastembed_metadata(cache_dir: Path) -> None:
    """Make FastEmbed metadata created on Windows portable to Linux containers."""
    for metadata_file in cache_dir.glob("models--*/files_metadata.json"):
        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            normalized = {str(path).replace("\\", "/"): value for path, value in metadata.items()}
            if normalized != metadata:
                metadata_file.write_text(
                    json.dumps(normalized, ensure_ascii=False),
                    encoding="utf-8",
                )
        except (OSError, ValueError, TypeError):
            continue


class VllmEmbedding:
    """Client of the local vLLM embedding server, a stand-in for the part of FastEmbed's
    TextEmbedding that the index build uses. The server's precision is set in `.env`
    (VLLM_EMBED_*); its vectors agree with the CPU fp32 ones to a cosine above 0.98 even
    with fp8, so an index built on the GPU is queried correctly with CPU query vectors.
    The server must already be running (see backend.ai.vllm_embed_server)."""

    def __init__(self, model_name: str) -> None:
        import httpx

        self._httpx = httpx
        self._model_name = model_name
        self._dimension = get_profile(model_name).dimension
        self._url = f"{vllm_embed_url()}/embeddings"
        self._threads = settings.embedding_threads

    # One request: the vectors of `texts`, in order. Any HTTP or shape error stops the build;
    # nothing is retried quietly, because a wrong vector would be written to the index.
    def _request(self, client, texts: list[str]) -> list[np.ndarray]:
        try:
            response = client.post(self._url, json={"model": self._model_name, "input": texts})
            response.raise_for_status()
            rows = sorted(response.json()["data"], key=lambda row: row["index"])
        except (self._httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError(f"VLLM_EMBED_REQUEST_FAILED: {type(exc).__name__}") from None
        vectors = [np.asarray(row["embedding"], dtype=np.float32) for row in rows]
        if len(vectors) != len(texts) or any(v.shape != (self._dimension,) for v in vectors):
            raise RuntimeError("VLLM_EMBED_BAD_RESPONSE")
        return vectors

    # Embed `documents` in order, yielding one unit-length vector at a time. Up to
    # `settings.embedding_threads` requests of `batch_size` windows are in flight; the server
    # regroups them into its own steps. `parallel` exists only for FastEmbed compatibility.
    def embed(
        self, documents: Iterable[str], batch_size: int = 16, parallel=None
    ) -> Iterator[np.ndarray]:
        texts = list(documents)
        batches = (texts[start : start + batch_size] for start in range(0, len(texts), batch_size))
        pending: deque[Future[list[np.ndarray]]] = deque()
        limit = 2 * self._threads  # bounded look-ahead keeps the memory and the progress honest
        timeout = self._httpx.Timeout(VLLM_REQUEST_TIMEOUT_SECONDS)
        pool = ThreadPoolExecutor(self._threads)
        try:
            with self._httpx.Client(
                timeout=timeout,
                limits=self._httpx.Limits(max_connections=self._threads),
            ) as client:
                for batch in batches:
                    pending.append(pool.submit(self._request, client, batch))
                    if len(pending) >= limit:
                        yield from self._take(pending)
                while pending:
                    yield from self._take(pending)
        finally:
            pool.shutdown(wait=True, cancel_futures=True)

    @staticmethod
    def _take(pending: deque[Future[list[np.ndarray]]]) -> Iterator[np.ndarray]:
        yield from pending.popleft().result()


# Load the configured model: FastEmbed on the CPU, or the client of the vLLM server
# when the device is "vllm" (default: settings.embedding_device).
def create_embedding_model(model_name: str, cache_dir: Path, device: str | None = None):
    get_profile(model_name)  # unknown models fail here, before anything is loaded
    device = device or settings.embedding_device
    if device == "vllm":
        return VllmEmbedding(model_name)

    from fastembed import TextEmbedding

    return TextEmbedding(
        model_name=model_name, cache_dir=str(cache_dir), threads=settings.embedding_threads
    )


@lru_cache(maxsize=4)
# Load the offline CPU model used for query-time embedding, memoized per process.
# Queries are always embedded on the CPU, whatever EMBEDDING_DEVICE says.
def cached_query_model(model_name: str, cache_dir: Path):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")
    _normalize_fastembed_metadata(cache_dir)
    return create_embedding_model(model_name, cache_dir, device="cpu")
