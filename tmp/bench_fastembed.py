"""Steady-state latency of one fastembed model, using this project's loading pattern.

Usage: python tmp/bench_fastembed.py <label> <model_name> <dim> <MEAN|CLS> <model_file>
Prints min/p50/p95 of a warmed single-text embed(), plus batch throughput, and
saves the vectors of TEXTS to tmp/vectors_<label>.npy for offline comparison.
Writes only into data/model_cache (download) and tmp/."""
from __future__ import annotations

import os
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType

CACHE = Path("data/model_cache")
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
    "dureri de articulati reumatism",
    "tinctura de propolis antibacterian",
    "ceai pentru colici la bebelusi",
    "menstruatie neregulata tratament herbal",
    "glicemie marita ceaiuri recomandate",
    "vitamina C naturala din catina",
    "afine pentru vedere si retina",
    "gargara cu salvie pentru amigdale",
]


def main() -> None:
    label, name, dim, pooling, model_file = sys.argv[1:6]
    threads = int(sys.argv[6]) if len(sys.argv) > 6 else max(1, (os.cpu_count() or 2) - 1)
    supported = {item["model"] for item in TextEmbedding.list_supported_models()}
    if name not in supported:
        TextEmbedding.add_custom_model(
            model=name,
            pooling=PoolingType[pooling],
            normalization=True,
            sources=ModelSource(hf=name),
            dim=int(dim),
            model_file=model_file,
        )
    model = TextEmbedding(model_name=name, cache_dir=str(CACHE), threads=threads)

    list(model.embed(["warmup", "warmup two", "warmup three"]))  # load + ORT graph warmup

    # Steady-state single-text latency, one call at a time (what a chat message costs).
    runs = []
    for index in range(40):
        text = TEXTS[index % len(TEXTS)]
        started = time.perf_counter()
        list(model.embed([text]))
        runs.append((time.perf_counter() - started) * 1000)
    runs = sorted(runs[8:])  # drop the first 8 as residual warmup
    p50 = statistics.median(runs)
    p95 = runs[min(len(runs) - 1, int(0.95 * len(runs)))]

    batch = []
    for _ in range(5):
        started = time.perf_counter()
        list(model.embed(TEXTS))
        batch.append(time.perf_counter() - started)
    batch_s = min(batch)

    vectors = np.asarray(list(model.embed(TEXTS)), dtype=np.float32)
    np.save(Path("tmp") / f"vectors_{label}.npy", vectors)

    print(f"[{label}] threads={threads} single query: min {runs[0]:.1f} ms | p50 {p50:.1f} ms | p95 {p95:.1f} ms")
    print(f"[{label}] batch of 20: {batch_s * 1000:.1f} ms -> {20 / batch_s:.0f} texts/s | dim {vectors.shape[1]}")
    print(f"[{label}] norms ok: {np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-4)}")


if __name__ == "__main__":
    main()
