"""Build the multilevel knowledge from the index fragments (plan 2026-11-27); level 1 for now.

Runs on the host, never in the web process, with local models only (the corpus never leaves the
machine). Level 1 sends every distinct fragment of a language, in windows, to KNOWLEDGE_L1_MODEL,
keeps the claims whose quote is found in the fragment and the questions, caches every validated
answer, embeds the items on vllm-embed and publishes the language's run atomically. A stopped or
crashed run continues on the next start; --sample N writes an unpublished run and a review file.

  PYTHONPATH=src .venv/Scripts/python.exe -m scripts.build_knowledge --level 1 --sample 200
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import threading
import time
from collections.abc import Iterator, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import httpx

from backend.ai.embedding_model import create_embedding_model, get_profile
from backend.ai.index_state import IndexUnavailable
from backend.ai.knowledge_l1 import (
    CatalogLinker,
    Extraction,
    ModelText,
    Window,
    claim_keys,
    extraction_from_output,
    halve,
    input_sha256,
    merge,
    model_text,
    parse_response,
    prompt_sha256,
    response_schema,
    split_windows,
    system_prompt,
    user_message,
)
from backend.ai.knowledge_repository import Fragment, IndexSnapshot, KnowledgeRepository, NewItem
from backend.ai.vllm_embed_server import running_embedding_server
from backend.config import Settings, configure_settings
from backend.core.language import LANGUAGES, Language, language_scope
from backend.core.report_models import REPORT_MODELS, ReportModel

logger = logging.getLogger("naturist.knowledge")

LEVEL = 1
# Parallel requests to a vLLM server (E0: 467 tok/s aggregate at 16); Ollama serves one at a time.
VLLM_PARALLEL = 16
OLLAMA_CONTEXT = 16_384
MAX_OUTPUT_TOKENS = 4_096
REQUEST_TIMEOUT_SECONDS = 900.0
REQUEST_ATTEMPTS = 3
RETRY_SECONDS = 5.0
_ORCHESTRATOR_TIMEOUT = httpx.Timeout(240.0, connect=5.0)
_PROBE_TIMEOUT = httpx.Timeout(3.0, connect=2.0)
_RUNNING_STATES = frozenset({"running", "restarting"})
_POLL_SECONDS = 3.0
# Items embedded per database round trip.
EMBED_PAGE = 1_024
PROGRESS_SECONDS = 30.0
# The review sample: distinct fragments of ordinary length (up to two windows), chosen reproducibly.
SAMPLE_SEED = 20261128
SAMPLE_MIN_CHARS, SAMPLE_MAX_CHARS = 150, 8_000
REVIEW_DIR = Path(__file__).resolve().parents[2] / "aiWork" / "knowledge-l1-sample"


@dataclass(frozen=True)
class Answer:
    content: str
    truncated: bool


class KnowledgeModel:
    """The level's local model: requests with a strict JSON schema, thinking off, temperature 0, and
    the vLLM server's life cycle through the llm-orchestrator (Ollama loads on the first request)."""

    def __init__(self, settings: Settings, choice: ReportModel) -> None:
        self.choice = choice
        self.spec = REPORT_MODELS[choice]
        self.parallel = VLLM_PARALLEL if self.spec.provider == "vllm" else 1
        self._settings = settings
        self._client = httpx.Client(
            timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=10.0),
            limits=httpx.Limits(max_connections=self.parallel),
            trust_env=False,
        )
        self._lock = threading.Lock()
        self.usage = {"requests": 0, "prompt_tokens": 0, "output_tokens": 0, "truncated": 0}

    def close(self) -> None:
        self._client.close()

    # Transport errors are retried a few times; then the run stops (resumable), nothing is cached.
    def complete(self, system: str, message: str, schema: dict[str, Any]) -> Answer:
        for attempt in range(1, REQUEST_ATTEMPTS + 1):
            try:
                if self.spec.provider == "vllm":
                    return self._vllm(system, message, schema)
                return self._ollama(system, message, schema)
            except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
                if attempt == REQUEST_ATTEMPTS:
                    raise RuntimeError(
                        f"KNOWLEDGE_MODEL_REQUEST_FAILED: {type(exc).__name__} from {self.choice}"
                    ) from None
                time.sleep(RETRY_SECONDS * attempt)
        raise AssertionError("unreachable")

    def _count(self, prompt_tokens: int, output_tokens: int, truncated: bool) -> None:
        with self._lock:
            self.usage["requests"] += 1
            self.usage["prompt_tokens"] += prompt_tokens
            self.usage["output_tokens"] += output_tokens
            self.usage["truncated"] += int(truncated)

    def _vllm(self, system: str, message: str, schema: dict[str, Any]) -> Answer:
        payload: dict[str, Any] = {
            "model": self.spec.model,
            "temperature": 0,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "knowledge", "schema": schema, "strict": True},
            },
        }
        if self.spec.effort_control != "none":
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        response = self._client.post(
            f"{self._settings.vllm_api_base}/chat/completions", json=payload
        )
        response.raise_for_status()
        body = response.json()
        choice = body["choices"][0]
        truncated = choice.get("finish_reason") == "length"
        usage = body.get("usage") or {}
        self._count(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), truncated)
        return Answer(choice["message"].get("content") or "", truncated)

    def _ollama(self, system: str, message: str, schema: dict[str, Any]) -> Answer:
        payload: dict[str, Any] = {
            "model": self.spec.model,
            "stream": False,
            "format": schema,
            "keep_alive": self._settings.ollama_keep_alive_seconds,
            "options": {
                "temperature": 0,
                "num_ctx": OLLAMA_CONTEXT,
                "num_predict": MAX_OUTPUT_TOKENS,
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
        }
        if self.spec.effort_control == "ollama_think":
            payload["think"] = False
        base = self._settings.ollama_api_base.removesuffix("/v1")
        response = self._client.post(f"{base}/api/chat", json=payload)
        response.raise_for_status()
        body = response.json()
        truncated = body.get("done_reason") == "length"
        self._count(body.get("prompt_eval_count", 0), body.get("eval_count", 0), truncated)
        return Answer(body["message"].get("content") or "", truncated)

    def _orchestrator(self, method: str, path: str) -> dict[str, Any]:
        url = f"http://127.0.0.1:{self._settings.llm_orchestrator_host_port}{path}"
        try:
            response = httpx.request(method, url, timeout=_ORCHESTRATOR_TIMEOUT)
        except httpx.HTTPError:
            raise RuntimeError(
                f"KNOWLEDGE_ORCHESTRATOR_UNAVAILABLE: the llm-orchestrator does not answer on {url}"
            ) from None
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code != 200:
            code = body.get("error") if isinstance(body, dict) else None
            raise RuntimeError(f"KNOWLEDGE_ORCHESTRATOR_ERROR: {code or response.status_code}")
        return body if isinstance(body, dict) else {}

    def _service_state(self, service: str) -> str:
        status = self._orchestrator("GET", "/status")
        groups = [group for group in status.values() if isinstance(group, dict)]
        for group in groups:
            if isinstance(group.get(service), dict):
                return str(group[service].get("state"))
        return "missing"

    def _serves_model(self) -> bool:
        try:
            response = self._client.get(
                f"{self._settings.vllm_api_base}/models", timeout=_PROBE_TIMEOUT
            )
            response.raise_for_status()
            return any(
                item.get("id") == self.spec.model for item in response.json().get("data", [])
            )
        except (httpx.HTTPError, ValueError, AttributeError):
            return False

    def _wait_until_served(self, service: str) -> None:
        deadline = time.monotonic() + self._settings.vllm_warmup_timeout_seconds
        while time.monotonic() < deadline:
            if self._serves_model():
                return
            state = self._service_state(service)
            if state not in _RUNNING_STATES:
                raise RuntimeError(
                    f"KNOWLEDGE_VLLM_EXITED: {service} stopped while starting (state {state}); "
                    f"see `docker logs medicina-{service}`"
                )
            time.sleep(_POLL_SECONDS)
        raise RuntimeError(
            f"KNOWLEDGE_VLLM_TIMEOUT: {service} served no model after "
            f"{self._settings.vllm_warmup_timeout_seconds} s"
        )

    @contextmanager
    def serving(self) -> Iterator[None]:
        """A vLLM model's server is started for the extraction and stopped after it, so vllm-embed
        can take the GPU; a server that was already running is used and left running."""
        service = self.spec.vllm_service if self.spec.provider == "vllm" else None
        if service is None:
            yield
            return
        state = self._service_state(service)
        if state == "missing":
            raise RuntimeError(
                f"KNOWLEDGE_VLLM_CONTAINER_MISSING: create it once with "
                f"`docker compose --profile {service} create`"
            )
        if state in _RUNNING_STATES:
            self._wait_until_served(service)
            yield
            return
        logger.info("knowledge_model_server_start service=%s", service)
        self._orchestrator("POST", f"/start/{service}")
        try:
            self._wait_until_served(service)
            yield
        finally:
            logger.info("knowledge_model_server_stop service=%s", service)
            self._orchestrator("POST", f"/stop/{service}")


@dataclass
class _Slot:
    """A fragment in flight: its windows, their cache keys and messages, and the answers so far."""

    fragment: Fragment
    text: ModelText
    windows: list[Window]
    messages: list[str]
    keys: list[str]
    results: list[Extraction | None]

    @property
    def complete(self) -> bool:
        return all(result is not None for result in self.results)


@dataclass
class LevelOneBuild:
    repository: KnowledgeRepository
    model: KnowledgeModel
    language: Language
    run_id: int
    linker: CatalogLinker
    counters: dict[str, Any]
    units_done: int
    units_total: int
    review: list[dict[str, Any]] | None = None
    prompt: str = field(init=False)
    prompt_sha: str = field(init=False)
    schema: dict[str, Any] = field(init=False)

    def __post_init__(self) -> None:
        self.prompt = system_prompt(self.language)
        self.prompt_sha = prompt_sha256(self.language)
        self.schema = response_schema()

    def _add(self, name: str, value: int = 1) -> None:
        self.counters[name] = int(self.counters.get(name, 0)) + value

    def _prepare(self, fragment: Fragment) -> _Slot:
        text = model_text(fragment.text)
        windows = split_windows(text.text)
        messages = [
            user_message(fragment.heading, text.text[window.start : window.end], part, len(windows))
            for part, window in enumerate(windows, start=1)
        ]
        keys = [
            input_sha256(fragment.text_sha256, message, self.prompt_sha, self.model.choice)
            for message in messages
        ]
        cached = self.repository.cached_outputs(keys, self.prompt_sha, self.model.choice)
        results = [extraction_from_output(cached[key]) if key in cached else None for key in keys]
        self._add("windows", len(windows))
        self._add("cache_hits", len(cached))
        return _Slot(fragment, text, windows, messages, keys, results)

    # Runs in a worker thread. An answer that is truncated or not the promised JSON is asked again
    # on the two halves of the window; at the smallest size the window is given up (and cached so).
    def _extract(self, slot: _Slot, window: Window, message: str, part: int) -> Extraction:
        answer = self.model.complete(self.prompt, message, self.schema)
        parsed = (
            None
            if answer.truncated
            else parse_response(answer.content, slot.text, slot.fragment.text, window)
        )
        if parsed is not None:
            return parsed
        halves = halve(slot.text.text, window)
        if halves is None:
            return Extraction(failed=True)
        parts = [
            self._extract(
                slot,
                half,
                user_message(
                    slot.fragment.heading,
                    slot.text.text[half.start : half.end],
                    part,
                    len(slot.windows),
                ),
                part,
            )
            for half in halves
        ]
        merged = merge(parts)
        return replace(merged, splits=merged.splits + 1)

    def _items(self, slot: _Slot) -> list[NewItem]:
        items: list[NewItem] = []
        seen_questions: set[str] = set()
        for key, result in zip(slot.keys, slot.results, strict=True):
            assert result is not None
            for claim in result.claims:
                subject_key, object_key = claim_keys(claim, self.linker)
                items.append(
                    NewItem(
                        "claim",
                        claim["statement"],
                        subject_key or object_key,
                        {**claim, "subject_key": subject_key, "object_key": object_key},
                        key,
                    )
                )
                self._add(f"quote_{claim['quote_match']}")
                if subject_key or object_key:
                    self._add("claims_linked")
            for question in result.questions:
                folded = " ".join(question.casefold().split())
                if folded not in seen_questions:
                    seen_questions.add(folded)
                    items.append(NewItem("question", question, None, {}, key))
            for rejected in result.rejected:
                self._add(f"rejected_{rejected.get('reason', 'unknown')}")
            self._add("windows_failed", int(result.failed))
        return items

    def _finish(self, slot: _Slot) -> None:
        items = self._items(slot)
        self.units_done += 1
        self.counters["usage"] = dict(self.model.usage)
        if items:
            self.repository.write_fragment(
                self.run_id,
                self.language,
                slot.fragment,
                items,
                self.units_done,
                self.counters,
            )
        else:
            self.repository.progress(self.run_id, self.units_done, self.counters)
        if self.review is not None:
            self.review.append(_review_entry(slot, items))

    def _collect(self, future: Future[Extraction], slot: _Slot, index: int) -> None:
        result = future.result()
        self.repository.store_output(
            slot.keys[index], self.prompt_sha, self.model.choice, result.as_output()
        )
        self._add("windows_split", result.splits)
        slot.results[index] = replace(result, splits=0)
        if slot.complete:
            self._finish(slot)

    def extract(self, fragments: Sequence[Fragment]) -> None:
        started = time.monotonic()
        first_done = self.units_done
        reported = started
        pending: dict[Future[Extraction], tuple[_Slot, int]] = {}
        pool = ThreadPoolExecutor(self.model.parallel)

        def drain(block: bool) -> None:
            nonlocal reported
            done, _ = wait(list(pending), timeout=None if block else 0, return_when=FIRST_COMPLETED)
            for future in done:
                slot, index = pending.pop(future)
                self._collect(future, slot, index)
            if time.monotonic() - reported >= PROGRESS_SECONDS:
                reported = time.monotonic()
                self._log_progress(started, first_done)

        try:
            with self.model.serving():
                for fragment in fragments:
                    slot = self._prepare(fragment)
                    for index, result in enumerate(slot.results):
                        if result is None:
                            future = pool.submit(
                                self._extract,
                                slot,
                                slot.windows[index],
                                slot.messages[index],
                                index + 1,
                            )
                            pending[future] = (slot, index)
                    if slot.complete:
                        self._finish(slot)
                    while len(pending) >= 2 * self.model.parallel:
                        drain(block=True)
                    drain(block=False)
                while pending:
                    drain(block=True)
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        self.counters["extraction_seconds"] = round(
            float(self.counters.get("extraction_seconds", 0)) + time.monotonic() - started, 1
        )
        self._log_progress(started, first_done)

    def _log_progress(self, started: float, first_done: int) -> None:
        elapsed = time.monotonic() - started
        done_here = self.units_done - first_done
        remaining = self.units_total - self.units_done
        eta = f"{remaining * elapsed / done_here / 60:.0f} min" if done_here else "estimating"
        logger.info(
            "knowledge_progress language=%s level=%s run=%s fragments=%s/%s requests=%s "
            "output_tokens=%s eta=%s",
            self.language,
            LEVEL,
            self.run_id,
            self.units_done,
            self.units_total,
            self.model.usage["requests"],
            self.model.usage["output_tokens"],
            eta,
        )


def _review_entry(slot: _Slot, items: list[NewItem]) -> dict[str, Any]:
    results = [result for result in slot.results if result is not None]
    return {
        "fragment": slot.fragment,
        "windows": len(slot.windows),
        "claims": [item for item in items if item.kind == "claim"],
        "questions": [item.body for item in items if item.kind == "question"],
        "rejected": [rejected for result in results for rejected in result.rejected],
        "failed": sum(int(result.failed) for result in results),
    }


# Items of the run get the vectors of identical items of the active run, the rest are embedded with
# the index model on vllm-embed (same space as chunks.embedding), page by page so a stop keeps them.
def embed_items(
    repository: KnowledgeRepository,
    run_id: int,
    language: Language,
    snapshot: IndexSnapshot,
    counters: dict[str, Any],
) -> None:
    started = time.monotonic()
    reused = repository.reuse_embeddings(run_id, language, LEVEL, snapshot.model_dimension)
    counters["embeddings_reused"] = int(counters.get("embeddings_reused", 0)) + reused
    page = repository.items_without_embedding(run_id, EMBED_PAGE)
    if not page:
        return
    profile = get_profile(snapshot.model_name)
    embedder = create_embedding_model(snapshot.model_name)
    with running_embedding_server():
        while page:
            vectors = list(embedder.embed([profile.passage_text(body) for _, body in page]))
            repository.store_embeddings(
                [(item_id, vector) for (item_id, _), vector in zip(page, vectors, strict=True)]
            )
            counters["embedded"] = int(counters.get("embedded", 0)) + len(page)
            logger.info(
                "knowledge_embedding language=%s run=%s embedded=%s",
                language,
                run_id,
                counters["embedded"],
            )
            page = repository.items_without_embedding(run_id, EMBED_PAGE)
    counters["embedding_seconds"] = round(
        float(counters.get("embedding_seconds", 0)) + time.monotonic() - started, 1
    )


def sample_fragments(fragments: Sequence[Fragment], size: int) -> list[Fragment]:
    pool = [
        fragment
        for fragment in fragments
        if SAMPLE_MIN_CHARS <= len(fragment.text) <= SAMPLE_MAX_CHARS
    ]
    random.Random(SAMPLE_SEED).shuffle(pool)
    return pool[:size]


def _lines(location: Any) -> str:
    return f"{location.source_relative_path}:{location.line_start}-{location.line_end}"


# The review file of a sample run (git-ignored aiWork/): every fragment with its claims, questions
# and rejected claims, and the fragment text to check the quotes against.
def write_review(
    language: Language, run_id: int, counters: dict[str, Any], entries: list[dict[str, Any]]
) -> Path:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    path = REVIEW_DIR / f"{language}-run{run_id}.md"
    lines = [
        f"# L1 sample, {language}, run {run_id}",
        "",
        "```json",
        json.dumps(counters, ensure_ascii=False, indent=1, sort_keys=True),
        "```",
        "",
    ]
    for number, entry in enumerate(entries, start=1):
        fragment: Fragment = entry["fragment"]
        lines += [
            f"## {number}. {_lines(fragment.locations[0])}",
            "",
            f"Section: {fragment.heading or '-'} · {len(fragment.text)} chars · "
            f"{entry['windows']} window(s) · occurrences: "
            + ", ".join(_lines(location) for location in fragment.locations)
            + (f" · **failed windows: {entry['failed']}**" if entry["failed"] else ""),
            "",
            f"### Claims ({len(entry['claims'])})",
            "",
        ]
        for item in entry["claims"]:
            claim = item.attributes
            keys = " · ".join(
                key for key in (claim.get("subject_key"), claim.get("object_key")) if key
            )
            qualifiers = ", ".join(
                f"{name} {claim[name]}"
                for name in ("dose", "duration", "population")
                if claim.get(name)
            )
            lines.append(
                f"- **{claim['subject']}** `{claim['relation']}` **{claim['object']}**"
                + (f" ({qualifiers})" if qualifiers else "")
                + (f" [{keys}]" if keys else "")
                + f" — {item.body}"
            )
            lines.append(
                f"  - quote ({claim['quote_match']}, {claim['quote_start']}-{claim['quote_end']}): "
                + json.dumps(claim["quote"], ensure_ascii=False)
            )
        lines += ["", f"### Questions ({len(entry['questions'])})", ""]
        lines += [f"- {question}" for question in entry["questions"]]
        lines += ["", f"### Rejected ({len(entry['rejected'])})", ""]
        for rejected in entry["rejected"]:
            lines.append(
                f"- {rejected.get('reason')}: {rejected.get('statement', '')} — model quote "
                + json.dumps(rejected.get("quote", ""), ensure_ascii=False)
            )
        lines += [
            "",
            "<details><summary>Fragment text</summary>",
            "",
            "```text",
            fragment.text.replace("```", "'''"),
            "```",
            "",
            "</details>",
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build_level_one(
    repository: KnowledgeRepository,
    settings: Settings,
    language: Language,
    sample: int | None,
) -> dict[str, Any]:
    choice = settings.knowledge_l1_model
    prompt_sha = prompt_sha256(language)
    snapshot = repository.index_snapshot(language)
    herbs, conditions = repository.catalog_names()
    linker = CatalogLinker.build(herbs, conditions)
    fragments: Sequence[Fragment] = snapshot.fragments
    run = None
    if sample is not None:
        repository.delete_sample_runs(language, LEVEL)
        fragments = sample_fragments(fragments, sample)
    else:
        run = repository.resumable_run(language, LEVEL, choice, prompt_sha)
    if run is None:
        counters: dict[str, Any] = {} if sample is None else {"sample": sample}
        run_id = repository.create_run(language, LEVEL, choice, prompt_sha, counters)
    else:
        run_id, counters = run.run_id, run.counters
        counters["resumed"] = int(counters.get("resumed", 0)) + 1
        logger.info("knowledge_resume language=%s run=%s status=%s", language, run_id, run.status)
    counters.update(index_generation=snapshot.index_generation, embedding_model=snapshot.model_name)
    current = {fragment.text_sha256 for fragment in fragments}
    removed = repository.fragments_with_items(run_id) - current
    if removed:
        repository.delete_fragment_items(run_id, removed)
    done = repository.fragments_with_items(run_id)
    todo = [fragment for fragment in fragments if fragment.text_sha256 not in done]
    repository.start_run(run_id, len(fragments), len(fragments) - len(todo))
    logger.info(
        "knowledge_start language=%s level=%s run=%s model=%s fragments=%s todo=%s",
        language,
        LEVEL,
        run_id,
        choice,
        len(fragments),
        len(todo),
    )
    model = KnowledgeModel(settings, choice)
    build = LevelOneBuild(
        repository,
        model,
        language,
        run_id,
        linker,
        counters,
        len(fragments) - len(todo),
        len(fragments),
        [] if sample is not None else None,
    )
    try:
        build.extract(todo)
        embed_items(repository, run_id, language, snapshot, counters)
        counters["items"] = repository.item_counts(run_id)
        repository.set_status(run_id, "ready", counters)
        if sample is None:
            repository.publish(run_id, language, LEVEL)
    except KeyboardInterrupt:
        repository.set_status(run_id, "paused", counters)
        raise
    except BaseException:
        repository.set_status(run_id, "failed", counters)
        raise
    finally:
        model.close()
    summary: dict[str, Any] = {
        "language": language,
        "level": LEVEL,
        "run_id": run_id,
        "published": sample is None,
        **counters,
    }
    if build.review is not None:
        summary["review_file"] = str(write_review(language, run_id, counters, build.review))
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the multilevel knowledge (L1-L4).")
    parser.add_argument("--level", type=int, choices=(1, 2, 3, 4), required=True)
    parser.add_argument("--language", choices=(*LANGUAGES, "all"), default="all")
    parser.add_argument(
        "--sample",
        type=int,
        metavar="N",
        help="process N fragments into an unpublished run and write a review file",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    if arguments.level != LEVEL:
        print(
            f"KNOWLEDGE_LEVEL_NOT_IMPLEMENTED: level {arguments.level} comes in a later stage",
            file=sys.stderr,
        )
        return 2
    if arguments.sample is not None and arguments.sample < 1:
        print("KNOWLEDGE_INVALID_SAMPLE: --sample must be at least 1", file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # One line per model or embedding request would bury the progress lines (~60,000 per language).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = Settings.from_env(dotenv=True)
    configure_settings(settings)
    languages: tuple[Language, ...] = (
        LANGUAGES if arguments.language == "all" else (arguments.language,)
    )
    repository = KnowledgeRepository(settings.database_url)
    try:
        if not repository.try_lock():
            print("KNOWLEDGE_BUILD_RUNNING: another knowledge build is running", file=sys.stderr)
            return 1
        for language in languages:
            with language_scope(language):
                summary = build_level_one(repository, settings, language, arguments.sample)
            print(json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)
    except KeyboardInterrupt:
        print("Stopped; the next start continues the run.", file=sys.stderr)
        return 130
    except IndexUnavailable as exc:
        print(f"{exc.code}: the index is being rebuilt or needs a resync", file=sys.stderr)
        return 1
    finally:
        repository.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
