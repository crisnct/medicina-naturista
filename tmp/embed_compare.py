"""Throwaway comparison: current e5-small vs granite-embedding-97m-multilingual-r2
(int8 and fp32) with this project's exact fastembed 0.8.1 usage pattern.

Writes only into data/model_cache (model download). No DB, no project state."""
from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType

CACHE = Path("data/model_cache")
GRANITE = "ibm-granite/granite-embedding-97m-multilingual-r2"
E5 = "intfloat/multilingual-e5-small"

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

LONG = (
    "Musetelul (Matricaria chamomilla) este una dintre cele mai folosite plante medicinale. "
    "Florile contin ulei volatil bogat in bisabolol si chamazulen, flavonoide (apigenina), "
    "mucilagii si compusi fenolici. Se prepara infuzie din 1-2 lingurite de flori la 200 ml "
    "apa fiarta, lasata acoperit 10 minute. Este indicat in inflamatii ale mucoasei gastrice, "
    "colite, spasme digestive, insomnie si anxietate usoara, precum si in gargara pentru "
    "afectiuni ale gurii si gatului. "
) * 8


def load(name: str, dim: int, pooling, model_file: str):
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
    list(model.embed(["warmup"]))
    return model, time.perf_counter() - started


def bench(label: str, model, prefix: str = "") -> np.ndarray:
    texts = [prefix + text for text in TEXTS]
    timings = []
    for _ in range(3):
        started = time.perf_counter()
        list(model.embed(texts))
        timings.append(time.perf_counter() - started)
    batch = min(timings)
    single = []
    for text in texts[:10]:
        started = time.perf_counter()
        list(model.embed([text]))
        single.append((time.perf_counter() - started) * 1000)
    long_ms = []
    for _ in range(3):
        started = time.perf_counter()
        list(model.embed([prefix + LONG]))
        long_ms.append((time.perf_counter() - started) * 1000)
    vectors = np.asarray(list(model.embed(texts)), dtype=np.float32)
    print(f"\n== {label} ==")
    print(f"    batch of 20: {batch * 1000:7.1f} ms  ({20 / batch:5.1f} texts/s)")
    print(f"    single query (median of 10): {statistics.median(single):6.1f} ms  (min {min(single):.1f})")
    print(f"    long text ({len(LONG)} chars): {statistics.median(long_ms):6.1f} ms")
    print(f"    dim {vectors.shape[1]}, unit norms: {np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-4)}")
    return vectors


def ort_manual(model_file: str, texts: list[str]) -> np.ndarray:
    """fp32 granite through raw onnxruntime: proves CLS pooling + normalization is all it takes."""
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    path = hf_hub_download(GRANITE, model_file, cache_dir=str(CACHE))
    tokenizer_path = hf_hub_download(GRANITE, "tokenizer.json", cache_dir=str(CACHE))
    tokenizer = Tokenizer.from_file(tokenizer_path)
    tokenizer.enable_truncation(max_length=32768)
    tokenizer.enable_padding()
    session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    encodings = tokenizer.encode_batch(texts)
    inputs = {
        "input_ids": np.asarray([item.ids for item in encodings], dtype=np.int64),
        "attention_mask": np.asarray([item.attention_mask for item in encodings], dtype=np.int64),
    }
    started = time.perf_counter()
    outputs = session.run(None, inputs)[0]
    elapsed = (time.perf_counter() - started) * 1000
    cls = outputs[:, 0]
    print(f"    raw ORT fp32, batch of {len(texts)}: {elapsed:.1f} ms")
    return cls / np.linalg.norm(cls, axis=1, keepdims=True)


def main() -> None:
    print(f"cpu_count={os.cpu_count()}  threads used={os.cpu_count() - 1}")

    e5, seconds = load(E5, 384, PoolingType.MEAN, "onnx/model.onnx")
    print(f"e5-small load: {seconds:.1f}s")
    e5_vectors = bench("intfloat/multilingual-e5-small (current: fp32, MEAN, 'passage: ' prefix)", e5, "passage: ")

    granite, seconds = load(GRANITE, 384, PoolingType.CLS, "onnx/model_quint8_avx2.onnx")
    print(f"granite int8 load: {seconds:.1f}s")
    gi_vectors = bench("granite-embedding-97m-multilingual-r2 (int8 quint8-avx2, CLS, no prefix)", granite)

    gf_vectors = ort_manual("onnx/model.onnx", TEXTS)

    print("\n== int8 vs fp32 (same model, same 20 texts) ==")
    cosines = np.sum(gi_vectors * gf_vectors, axis=1)
    print(f"    per-text cosine: min {cosines.min():.5f}  mean {cosines.mean():.5f}  max {cosines.max():.5f}")
    print(f"    top-1 agreement on 20x20 similarity matrix: "
          f"{np.mean(np.argmax(gi_vectors @ gi_vectors.T, axis=1) == np.argmax(gf_vectors @ gf_vectors.T, axis=1)):.2%}")

    print("\n== qualitative: top-3 neighbours of 'ceai pentru tuse si dureri in gat' ==")
    for name, vectors in (("e5-small", e5_vectors), ("granite", gi_vectors)):
        order = np.argsort(-(vectors[0] @ vectors.T))[:4]
        print(f"    {name}: " + " | ".join(f"{vectors[0] @ vectors[i]:.3f} {TEXTS[i]}" for i in order if i))

    print("\n== neighbour-overlap between e5-small and granite (top-10 per text, 20 texts) ==")
    overlaps = []
    for row in range(len(TEXTS)):
        a = set(np.argsort(-(e5_vectors[row] @ e5_vectors.T))[:10])
        b = set(np.argsort(-(gi_vectors[row] @ gi_vectors.T))[:10])
        overlaps.append(len(a & b) / 10)
    print(f"    mean overlap {statistics.fmean(overlaps):.2f}  (1.00 = identical rankings)")

    json.dump(
        {"texts": TEXTS, "e5": e5_vectors.tolist(), "granite_int8": gi_vectors.tolist()},
        (Path("tmp") / "embed_smoke_vectors.json").open("w", encoding="utf-8"),
    )


if __name__ == "__main__":
    main()
