"""Shared local FastEmbed model loading, used both when syncing the index
(scripts/build_hybrid_index.py) and when embedding a query (ai/search.py)."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from medicina_naturista.config import settings

# Default multilingual model used for Romanian and English medical retrieval.
DEFAULT_MODEL = "intfloat/multilingual-e5-small"
# Vector width produced by DEFAULT_MODEL and required by the generated index.
MODEL_DIMENSION = 384
# ONNX artifact loaded from the local Hugging Face model snapshot.
MODEL_FILE = "onnx/model.onnx"


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


# Load or register the configured FastEmbed model in the local cache.
def create_embedding_model(model_name: str, dimension: int, cache_dir: Path):
    from fastembed import TextEmbedding

    supported = {item["model"] for item in TextEmbedding.list_supported_models()}
    if model_name not in supported:
        from fastembed.common.model_description import ModelSource, PoolingType

        TextEmbedding.add_custom_model(
            model=model_name,
            pooling=PoolingType.MEAN,
            normalization=True,
            sources=ModelSource(hf=model_name),
            dim=dimension,
            model_file=MODEL_FILE,
        )
    return TextEmbedding(model_name=model_name, cache_dir=str(cache_dir), threads=settings.embedding_threads)


@lru_cache(maxsize=4)
# Load the offline FastEmbed model used for query-time embedding, memoized per process.
def cached_query_model(model_name: str, dimension: int, cache_dir: Path):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")
    _normalize_fastembed_metadata(cache_dir)
    return create_embedding_model(model_name, dimension, cache_dir)
