"""Latency/throughput of one fastembed model at several ONNX thread counts, with
this project's usage pattern (single short query; batches of ~1400-char passage
windows, as build_hybrid_index.py embeds them). Writes only into data/model_cache.

Usage: python tmp/bench_threads.py <model_name> [threads ...]
  python tmp/bench_threads.py intfloat/multilingual-e5-small
  python tmp/bench_threads.py Qwen/Qwen3-Embedding-0.6B-Q 4 8 12 16
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType

CACHE = Path("data/model_cache")
DEFAULT_THREADS = [4, 6, 8, 12, 16, 24, 32]
QUERIES = [
    "ceai pentru tuse si dureri in gat",
    "plante pentru digestie grea si balonare",
    "musetelul are efect antiinflamator?",
    "ce ajuta la insomnia si somnul agitat",
    "tratament natural pentru dureri de cap",
    "scaderea tensiunii arteriale prin plante",
    "ceai de sunatoare pentru anxietate",
    "gargara cu salvie pentru amigdale",
]
PASSAGE = (
    "Musetelul (Matricaria chamomilla) este una dintre cele mai folosite plante medicinale. "
    "Florile contin ulei volatil bogat in bisabolol si chamazulen, flavonoide (apigenina), "
    "mucilagii si compusi fenolici. Se prepara infuzie din 1-2 lingurite de flori la 200 ml "
    "apa fiarta, lasata acoperit 10 minute. Este indicat in inflamatii ale mucoasei gastrice, "
    "colite, spasme digestive, insomnie si anxietate usoara, precum si in gargara pentru "
    "afectiuni ale gurii si gatului. "
)
WINDOWS = [(PASSAGE * 4 + f" varianta {index}")[:1400] for index in range(32)]
INSTRUCT = "Instruct: Given a question about natural medicine in Romanian, retrieve passages that answer it\nQuery:"


def load(name: str, threads: int) -> TextEmbedding:
    supported = {item["model"] for item in TextEmbedding.list_supported_models()}
    if name not in supported:
        TextEmbedding.add_custom_model(
            model=name, pooling=PoolingType.MEAN, normalization=True,
            sources=ModelSource(hf=name), dim=384, model_file="onnx/model.onnx",
        )
    return TextEmbedding(model_name=name, cache_dir=str(CACHE), threads=threads)


def main() -> None:
    name = sys.argv[1]
    counts = [int(value) for value in sys.argv[2:]] or DEFAULT_THREADS
    qwen = "qwen" in name.casefold()
    query_prefix = INSTRUCT if qwen else "query: "
    passage_prefix = "" if qwen else "passage: "
    queries = [query_prefix + text for text in QUERIES]
    windows = [passage_prefix + text for text in WINDOWS]

    print(f"{name}\n{'threads':>7} | {'query p50':>10} {'query p95':>10} | {'windows/s':>10}")
    for threads in counts:
        print(f"        [{threads} threads] loading model...", flush=True)
        model = load(name, threads)
        print(f"        [{threads} threads] warmup...", flush=True)
        list(model.embed(queries[:2]))
        list(model.embed(windows[:4]))  # graph warmup for both shapes

        print(f"        [{threads} threads] single queries...", flush=True)
        single = []
        for _ in range(2):
            for text in queries:
                started = time.perf_counter()
                list(model.embed([text]))
                single.append((time.perf_counter() - started) * 1000)
        single.sort()
        p50 = statistics.median(single)
        p95 = single[min(len(single) - 1, int(0.95 * len(single)))]

        print(f"        [{threads} threads] batch of {len(windows)} windows...", flush=True)
        batch = []
        for _ in range(2):
            started = time.perf_counter()
            list(model.embed(windows, batch_size=32))
            batch.append(time.perf_counter() - started)
        rate = len(windows) / min(batch)
        print(f"{threads:>7} | {p50:>8.1f}ms {p95:>8.1f}ms | {rate:>10.1f}", flush=True)
        del model


if __name__ == "__main__":
    main()
