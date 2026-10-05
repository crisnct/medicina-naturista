"""Does GPU (torch fp16) embed Qwen3-Embedding-0.6B the same as FastEmbed fp32 on CPU,
and how fast is it? Run it from the separate GPU venv (see the plan).

  .venv-gpu\\Scripts\\python tmp/gpu_check.py

Writes only into data/model_cache (FastEmbed) and the Hugging Face cache (torch)."""
from __future__ import annotations

import os
import statistics
import time
from pathlib import Path

# Windows "Controlled folder access" blocks the venv's python from writing to
# ~/.cache, so keep the Hugging Face cache in the (git-ignored) project model cache,
# the same folder FastEmbed uses (both use the Hugging Face models--* layout).
os.environ.setdefault("HF_HUB_CACHE", str(Path("data/model_cache").resolve()))

import numpy as np
import torch
from fastembed import TextEmbedding
from sentence_transformers import SentenceTransformer

CACHE = Path("data/model_cache")
NAME = "Qwen/Qwen3-Embedding-0.6B"
INSTRUCT = "Instruct: Given a question about natural medicine in Romanian, retrieve passages that answer it\nQuery:"
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
WINDOWS = [(PASSAGE * 4 + f" varianta {index}")[:1400] for index in range(64)]
TEXTS = [INSTRUCT + query for query in QUERIES] + WINDOWS[:8]


def main() -> None:
    assert torch.cuda.is_available(), "CUDA nu e disponibil in acest mediu"
    print(f"GPU: {torch.cuda.get_device_name(0)}  torch {torch.__version__}")

    gpu = SentenceTransformer(
        NAME, device="cuda", model_kwargs={"torch_dtype": torch.float16},
        tokenizer_kwargs={"padding_side": "left"},
    )
    gpu.encode(WINDOWS[:8], batch_size=8)  # warmup
    for batch_size in (8, 16, 32):
        torch.cuda.synchronize()
        started = time.perf_counter()
        gpu.encode(WINDOWS, batch_size=batch_size, normalize_embeddings=True)
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        print(f"GPU fp16 batch {batch_size:>2}: {len(WINDOWS) / elapsed:6.1f} windows/s "
              f"(peak VRAM {torch.cuda.max_memory_allocated() / 2**30:.1f} GB)")
    gpu_vectors = gpu.encode(TEXTS, batch_size=8, normalize_embeddings=True)

    threads = int(os.getenv("EMBEDDING_THREADS", "8"))
    cpu = TextEmbedding(model_name=NAME, cache_dir=str(CACHE), threads=threads)
    list(cpu.embed(TEXTS[:2]))
    cpu_vectors = np.asarray(list(cpu.embed(TEXTS)), dtype=np.float32)

    cosines = np.sum(gpu_vectors * cpu_vectors, axis=1)
    print(f"\nGPU fp16 vs FastEmbed fp32 (CPU, {threads} fire): cosinus per text "
          f"min {cosines.min():.5f}  mean {cosines.mean():.5f}  (tinta: min >= 0.99)")

    times = []
    for _ in range(3):
        for query in QUERIES:
            started = time.perf_counter()
            list(cpu.embed([INSTRUCT + query]))
            times.append((time.perf_counter() - started) * 1000)
    print(f"Intrebare pe CPU, fp32, {threads} fire: p50 {statistics.median(times):.0f} ms  "
          f"p95 {sorted(times)[int(0.95 * len(times))]:.0f} ms")


if __name__ == "__main__":
    main()
