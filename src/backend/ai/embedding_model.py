"""Embedding model profiles and the two clients of the one local model, Qwen3-Embedding-4B,
used both when syncing the index (scripts/build_hybrid_index.py) and when embedding a
query (ai/search.py).

Index builds embed the windows through the local vLLM server (the `vllm-embed` Compose
service, on the GPU, so neither the web app nor its Docker image needs torch). Questions
are embedded through the host Ollama on the CPU, so the GPU stays free for reports."""

from __future__ import annotations

from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Iterator

import numpy as np

from backend.config import settings
from backend.core.errors import ApplicationError
from backend.core.texts import tr

# Instruction Qwen3-Embedding was trained to expect in front of a query (kept in
# English on purpose; the question itself stays Romanian). Neither vLLM nor Ollama adds
# it, so the code does. Changing it needs no reindex, but the retrieval evaluation must
# be rerun.
QWEN_QUERY_TEMPLATE = (
    "Instruct: Given a question about natural medicine in Romanian, retrieve passages "
    "from herbal and naturopathic texts that answer it\nQuery:{text}"
)

# Seconds one embeddings request may take; a request holds at most a few dozen windows.
VLLM_REQUEST_TIMEOUT_SECONDS = 600

# Ollama loads the model on the first question (about 3 s); one question takes under 2 s after.
OLLAMA_QUERY_TIMEOUT_SECONDS = 60
# Seconds the list of loaded models may take; it answers at once when Ollama is up.
OLLAMA_PS_TIMEOUT_SECONDS = 3
# The model stays in the host's RAM between questions instead of the 60 s of OLLAMA_KEEP_ALIVE_SECONDS.
OLLAMA_QUERY_KEEP_ALIVE = "24h"
# num_gpu 0 keeps the model on the CPU, so it never competes with reports or the index build for the
# GPU. A question is far shorter than 1024 tokens; the context only sizes the memory it takes
# (about 4.3 GB, against 8 GB with Ollama's default context).
OLLAMA_QUERY_OPTIONS = {"num_gpu": 0, "num_ctx": 1024}


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
    # The Ollama tag that answers questions (a Q8_0 build of the same model).
    query_model: str = ""

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
            "Qwen/Qwen3-Embedding-4B",
            2560,
            QWEN_QUERY_TEMPLATE,
            "{text}",
            1400,
            240,
            "qwen3-embedding:4b-q8_0",
        ),
    )
}

# The model the index is built with and queried with, unless --model says otherwise.
DEFAULT_MODEL = "Qwen/Qwen3-Embedding-4B"


# Profile of a known model; an unknown name is an error, never a silent guess.
def get_profile(model_name: str) -> EmbeddingProfile:
    try:
        return PROFILES[model_name]
    except KeyError:
        raise ValueError(
            f"Unknown embedding model {model_name!r}; known models: {', '.join(sorted(PROFILES))}"
        ) from None


# True for the Ollama tag that answers questions. It lives in the host's RAM (num_gpu 0), so it
# neither blocks the GPU for the index build nor needs unloading before a local report.
def is_query_model(ollama_name: str) -> bool:
    return any(profile.query_model == ollama_name for profile in PROFILES.values())


# The Ollama server of this machine (the one that serves reports, never a cloud address).
def ollama_base_url() -> str:
    return settings.ollama_api_base.removesuffix("/v1")


class VllmEmbedding:
    """Client of the local vLLM embedding server, used by the index build only. The server's
    precision is set in docker-compose.yaml; the server must already be running (see
    backend.ai.vllm_embed_server)."""

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
    # regroups them into its own steps. `parallel` is ignored, kept for the build's protocol.
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


class OllamaQueryEmbedding:
    """Client of the host Ollama that embeds questions on the CPU. Its Q8_0 vectors agree with
    the vLLM fp8 ones of the index to a cosine above 0.96 (mean 0.992) with the same ranking
    quality. An unreachable Ollama stops the semantic search with SEMANTIC_MODEL_UNAVAILABLE;
    it never falls back to another signal quietly."""

    def __init__(self, profile: EmbeddingProfile) -> None:
        import httpx

        self._httpx = httpx
        self._profile = profile
        self._base = ollama_base_url()
        self._url = f"{self._base}/api/embed"
        self._client = httpx.Client(timeout=httpx.Timeout(OLLAMA_QUERY_TIMEOUT_SECONDS))

    # True when Ollama holds the question model in memory, so a question needs no load first.
    def is_loaded(self) -> bool:
        try:
            response = self._client.get(f"{self._base}/api/ps", timeout=OLLAMA_PS_TIMEOUT_SECONDS)
            response.raise_for_status()
            return any(
                self._profile.query_model in (item.get("name"), item.get("model"))
                for item in response.json().get("models") or []
            )
        except (self._httpx.HTTPError, ValueError, AttributeError):
            raise _semantic_model_unavailable() from None

    # An embed without input loads the model with the options and keep-alive of query_embed
    # (measured: about 3.5 s). A model that is not pulled gets its own error, because starting
    # Ollama again would not help.
    def load(self) -> None:
        try:
            response = self._client.post(
                self._url,
                json={
                    "model": self._profile.query_model,
                    "input": [],
                    "keep_alive": OLLAMA_QUERY_KEEP_ALIVE,
                    "options": OLLAMA_QUERY_OPTIONS,
                },
            )
            if response.status_code == 404:
                raise ApplicationError(
                    "SEMANTIC_MODEL_NOT_PULLED", tr("errors.semantic_model_not_pulled"), 503
                )
            response.raise_for_status()
        except self._httpx.HTTPError:
            raise _semantic_model_unavailable() from None

    # The vectors of `texts`, in order (not normalized: the caller does that).
    def query_embed(self, texts: list[str]) -> Iterator[np.ndarray]:
        try:
            response = self._client.post(
                self._url,
                json={
                    "model": self._profile.query_model,
                    "input": texts,
                    "keep_alive": OLLAMA_QUERY_KEEP_ALIVE,
                    "options": OLLAMA_QUERY_OPTIONS,
                },
            )
            response.raise_for_status()
            vectors = [np.asarray(row, dtype=np.float32) for row in response.json()["embeddings"]]
        except (self._httpx.HTTPError, ValueError, KeyError, TypeError):
            raise _semantic_model_unavailable() from None
        if len(vectors) != len(texts) or any(
            v.shape != (self._profile.dimension,) for v in vectors
        ):
            raise _semantic_model_unavailable()
        yield from vectors


def _semantic_model_unavailable() -> ApplicationError:
    return ApplicationError(
        "SEMANTIC_MODEL_UNAVAILABLE", tr("errors.semantic_model_unavailable"), 503
    )


# The client of the vLLM server that embeds the index windows.
def create_embedding_model(model_name: str) -> VllmEmbedding:
    get_profile(model_name)  # unknown models fail here, before anything is loaded
    return VllmEmbedding(model_name)


@lru_cache(maxsize=4)
# The question embedder of the model the index was built with, memoized per process (it only
# holds an HTTP client; the model itself is loaded and kept by Ollama).
def cached_query_model(model_name: str) -> OllamaQueryEmbedding:
    return OllamaQueryEmbedding(get_profile(model_name))
