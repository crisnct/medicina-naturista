"""Shared local embedding model loading and per-model text profiles, used both
when syncing the index (scripts/build_hybrid_index.py) and when embedding a
query (ai/search.py).

Two backends share one interface (`embed(texts, batch_size, parallel)`):
FastEmbed/ONNX fp32 on CPU (queries, and builds without a GPU) and a PyTorch
fp16 adaptor on CUDA (index builds only, imported lazily so the web app and its
Docker image never need torch)."""
from __future__ import annotations

import json
import os
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

# Texts per call of the GPU adaptor: bounds memory and lets the build report
# progress between slices (sentence-transformers sorts by length inside a call).
_GPU_SLICE = 512


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
        EmbeddingProfile("Qwen/Qwen3-Embedding-0.6B", 1024, QWEN_QUERY_TEMPLATE, "{text}", 1400, 240),
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


class CudaEmbedding:
    """GPU (PyTorch fp16, sentence-transformers) stand-in for the part of
    FastEmbed's TextEmbedding that the index build uses. Vectors agree with the
    CPU fp32 ones to a cosine of about 0.9998, so an index built on the GPU is
    queried correctly with CPU query vectors."""

    def __init__(self, model_name: str, cache_dir: Path) -> None:
        # Both must be set before huggingface_hub is imported (through torch /
        # sentence-transformers) to take effect.
        os.environ.setdefault("HF_HUB_CACHE", str(cache_dir))
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        try:
            import torch
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "EMBEDDING_DEVICE=cuda needs torch and sentence-transformers; "
                "run the build from the GPU environment (.venv-gpu)"
            ) from exc
        if not torch.cuda.is_available():
            raise RuntimeError(
                "EMBEDDING_DEVICE=cuda but CUDA is not available; refusing to fall back to the CPU "
                "(a full build would take hours). Fix the GPU setup or use EMBEDDING_DEVICE=cpu."
            )
        self._model = SentenceTransformer(
            model_name,
            device="cuda",
            cache_folder=str(cache_dir),
            model_kwargs={"torch_dtype": torch.float16},
            tokenizer_kwargs={"padding_side": "left"},
        )

    # Embed `documents` in order, yielding one unit-length vector at a time.
    # `parallel` exists only for FastEmbed compatibility and is ignored.
    def embed(self, documents: Iterable[str], batch_size: int = 8, parallel=None) -> Iterator[np.ndarray]:
        texts = list(documents)
        for start in range(0, len(texts), _GPU_SLICE):
            vectors = self._model.encode(
                texts[start:start + _GPU_SLICE],
                batch_size=batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
            yield from np.asarray(vectors, dtype=np.float32)


# Load the configured model: FastEmbed on the CPU, or the PyTorch fp16 adaptor
# when the device is "cuda" (default: settings.embedding_device).
def create_embedding_model(model_name: str, cache_dir: Path, device: str | None = None):
    get_profile(model_name)  # unknown models fail here, before anything is loaded
    device = device or settings.embedding_device
    if device == "cuda":
        return CudaEmbedding(model_name, cache_dir)

    from fastembed import TextEmbedding

    return TextEmbedding(model_name=model_name, cache_dir=str(cache_dir), threads=settings.embedding_threads)


@lru_cache(maxsize=4)
# Load the offline CPU model used for query-time embedding, memoized per process.
# Queries are always embedded on the CPU, whatever EMBEDDING_DEVICE says.
def cached_query_model(model_name: str, cache_dir: Path):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")
    _normalize_fastembed_metadata(cache_dir)
    return create_embedding_model(model_name, cache_dir, device="cpu")
