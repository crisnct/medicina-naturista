"""Throwaway smoke test: can fastembed 0.8.1 load granite-embedding-97m-multilingual-r2
from this project's cache layout, and how fast is it vs the current e5-small?
Read-only w.r.t. the project: only writes into data/model_cache (model download)."""
from __future__ import annotations

import os
import statistics
import time
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType

CACHE = Path("data/model_cache")
GRANITE = "ibm-granite/granite-embedding-97m-multilingual-r2"
GRANITE_FILE = "onnx/model_quint8_avx2.onnx"

TEXTS = [
    "ceai pentru tuse si dureri in gat",
    "plante pentru digestie grea si balonare",
    "musetelul are efect antiinflamator?",
    "ce ajuta la insomnia si somnul agitat",
    "tratament natural pentru dureri de cap",
    "mujdei de usturoi pentru paraziti",
    "scaderea tensiunii arteriale prin plante",
    "ceai de sunatoare pentru anxietate",
    "unguent pentru arsuri si rani",
    "susanul negru in afectiuni respiratorii",
    "ceai diuretic pentru retentia de apa",
    "plante care curata ficatul",
    "dureri de articulatii reumatism",
    "tinctura de propolis antibacterian",
    "ceai pentru colici la bebelusi",
    "menstruatie neregulata tratament herbal",
    "glicemie marita ceaiuri recomandate",
    "vitamina C naturala din catina",
    "afine pentru vedere si retina",
    "gargara cu salvie pentru amigdale",
]


def load(name: str, dim: int, model_file: str | None = None, pooling=None):
    supported = {item["model"] for item in TextEmbedding.list_supported_models()}
    if name not in supported:
        TextEmbedding.add_custom_model(
            model=name,
            pooling=pooling,
            normalization=True,
            sources=ModelSource(hf=name),
            dim=dim,
            model_file=model_file,
        )
    started = time.perf_counter()
    model = TextEmbedding(
        model_name=name,
        cache_dir=str(CACHE),
        threads=max(1, (os.cpu_count() or 2) - 1),
    )
    return model, time.perf_counter() - started


def run(model, texts: list[str]) -> tuple[float, list[float], np.ndarray]:
    cold = time.perf_counter()
    first = np.asarray(list(model.embed(texts[:1])), dtype=np.float32)
    cold_s = time.perf_counter() - cold

    warm = []
    for _ in range(3):
        started = time.perf_counter()
        vectors = np.asarray(list(model.embed(texts)), dtype=np.float32)
        warm.append(time.perf_counter() - started)

    single = []
    for text in texts[:10]:
        started = time.perf_counter()
        list(model.embed([text]))
        single.append((time.perf_counter() - started) * 1000)

    print(f"    first call (includes load): {cold_s * 1000:7.0f} ms")
    print(f"    batch {len(texts)} texts: {min(warm) * 1000:7.1f} ms  ({len(texts) / min(warm):6.1f} texts/s)")
    print(f"    single query (median of 10): {statistics.median(single):7.1f} ms  (min {min(single):.1f})")
    print(f"    shape {vectors.shape}, norms {np.linalg.norm(vectors, axis=1).min():.4f}..{np.linalg.norm(vectors, axis=1).max():.4f}")
    del first
    return min(warm), single, vectors


def main() -> None:
    print(f"onnxruntime threads available, cpu_count={os.cpu_count()}")
    print("\n== granite-embedding-97m-multilingual-r2 (int8, CLS pooling, no prefixes) ==")
    granite, load_s = load(GRANITE, 384, GRANITE_FILE, PoolingType.CLS)
    print(f"    load+download: {load_s:.1f} s")
    _, _, gvecs = run(granite, TEXTS)
    granite_queries = gvecs[:10]

    print("\n== intfloat/multilingual-e5-small (current, fp32, MEAN pooling) ==")
    e5, load_s = load("intfloat/multilingual-e5-small", 384)
    print(f"    load: {load_s:.1f} s")
    _, _, evecs = run(e5, [f"passage: {t}" for t in TEXTS])
    e5_queries = evecs[:10]

    print("\n== cross-check: cosine of 10 Romanian queries, granite vs e5 (same query text) ==")
    print("    (diagonal of granite-query x e5-query is meaningless; this is a sanity print only)")
    print("    granite row0 top-3 among the 20 texts:")
    order = np.argsort(-(gvecs[:1] @ gvecs.T))[0][:3]
    for index in order:
        print(f"      {gvecs[0] @ gvecs[index]:.3f}  {TEXTS[index]}")
    print("    e5 row0 top-3 among the 20 texts:")
    order = np.argsort(-(evecs[:1] @ evecs.T))[0][:3]
    for index in order:
        print(f"      {evecs[0] @ evecs[index]:.3f}  {TEXTS[index]}")
    del granite_queries, e5_queries


if __name__ == "__main__":
    main()
