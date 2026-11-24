# Senior Python developer — embeddings specialist

This guide is shared by Claude and ChatGPT/Codex. Read repository-root `AGENTS.md` and
`.claude/README.md`; adapt tool names and shell syntax to the active host.

One model, one dimension, two clients. Everything that depends on the model is
concentrated in `backend/ai/embedding_model.py`; keep it that way.

## Two general rules that bite harder here

Read [python-development.md](python-development.md) for the project's stack and coding
standards. Two of them need a sharper reading in embedding code:

- **No placeholders, ever.** A partially implemented embedding path does not fail loudly
  — it produces vectors that are subtly wrong and silently poisons the whole index. There
  is no "finish it next commit" here; incomplete work gets reported, not committed.
- **No blocking calls inside async code.** Embedding is CPU-bound and blocking. It is
  never awaited directly: the web app reaches it through `asyncio.to_thread` (see the
  search warm-up in `web/main.py`), and index builds run in their own processes.

Also note that **torch is deliberately absent from the runtime image and its lock.** The
GPU path is a vLLM server in its own container (`vllm-embed`), reached over HTTP by
`VllmEmbedding`, so neither the web app nor any venv needs torch. Do not add torch to the
runtime dependencies to make a test or a type-check easier.

## The model

`Qwen/Qwen3-Embedding-4B`, 2560 dimensions, unit-normalised vectors. It is the only
model the code understands: `get_profile()` raises on an unknown name rather than
guessing. An `EmbeddingProfile` carries everything model-dependent — `dimension`,
`query_template`, `passage_template`, `max_chars` (1400), `overlap_chars` (240) and
`query_model` (the Ollama tag that embeds questions, `qwen3-embedding:4b-q8_0`).

**Asymmetric encoding.** Queries are wrapped in the Qwen instruct template
(`QWEN_QUERY_TEMPLATE`, deliberately English while the question stays Romanian or English);
passages get no prefix. Neither vLLM nor Ollama adds the instruction, so the code does.
Changing the template needs no reindex but **does** invalidate retrieval measurements —
rerun the evaluation.

## Two clients of one model

- **`VllmEmbedding`, HTTP client of the `vllm-embed` Compose service** — index builds only,
  `embed(texts, batch_size, parallel)` (`parallel` is ignored). `EMBEDDING_THREADS` (24) is the
  number of simultaneous requests and also the server's `--max-num-seqs`; a request holds
  `BATCH_SIZE` (16) windows. `ai/vllm_embed_server.py` asks the `vllm-supervisor` (loopback port
  `VLLM_SUPERVISOR_HOST_PORT`; only it has Docker access) to start the service when there is
  something to embed, waits for the model and stops it in a `finally`; a busy GPU (a running
  `medicina-vllm-*` container or an Ollama model that holds the GPU) is the error `VLLM_GPU_BUSY`,
  and there is no fallback. The server flags are fixed in `docker-compose.yaml`
  (`fp8_per_tensor` weights, bf16 for the rest, fp8 KV cache, `--max-model-len 2048`,
  `--gpu-memory-utilization 0.8`).
- **`OllamaQueryEmbedding`, client of the host Ollama** — every question of the app,
  `query_embed(texts)`, through `/api/embed` with `num_gpu: 0` and `num_ctx: 1024` (the model runs
  on the CPU, ~4.3 GB of RAM, so it never competes for the GPU) and `keep_alive` 24 h. It reaches
  Ollama at `OLLAMA_API_BASE`. If Ollama does not answer, the semantic signal fails with
  `SEMANTIC_MODEL_UNAVAILABLE` (503); it never degrades to the other signals quietly.
  `is_query_model()` keeps this model out of `gpu_holders()` and out of the unloading that
  precedes a local report. `cached_query_model` is `lru_cache`d per process and holds only the
  HTTP client.

Measured on the RTX 3500 Ada at 55 W: 21 windows/s at 24 requests (~42 min for the whole
corpus), the same at `--gpu-memory-utilization` 0.45, 0.6 and 0.8 (compute-bound). At 0.9 the VRAM
filled up, Windows moved part of it to RAM and the build ran 3–8x slower. Questions: p50 0.7 s on
the CPU through Ollama (Q8_0 GGUF), whose vectors agree with the vLLM fp8 ones of the index to a
cosine above 0.96 (mean 0.992) with the same nDCG. Another Ollama version or tag of the model
needs that check again. nDCG@10 (C only) 0.652 against 0.542 for the former 0.6B model.

## Chunking and windowing

`ai/fragmenter.py` splits documents into R1 (condition in the chapter title), R2
(condition in the chapter text) and D1 (everything else), using the PostgreSQL condition
catalog. A fragment longer than `max_chars` is cut into **overlapping windows**
(`step = max_chars - overlap_chars`) so the model cannot silently truncate the tail; the
window vectors are averaged back into one vector per chunk. Each window is prefixed with
the fragment's context line.

If you change windowing, averaging, the context line, or the passage template, you have
changed the meaning of every stored vector. That requires a full reindex — see
`TEXT_REPR_VERSION`.

## TEXT_REPR_VERSION

A single `Final[str]` in `ai/index_constants.py`, currently `"13"`. Not an environment
variable. Bumping it makes the next build reprocess every document, and makes a running
backend reject the existing index (`INDEX_RESYNC_REQUIRED`) until the sync completes.
Bump it whenever the text representation changes; never bump it casually, and never
change the representation without bumping it.

## How the vector contributes to ranking

`V` is **not** raw cosine. It is the cosine rescaled from `[median, max] of this search`
into `[0,1]`, computed in the same SQL statement as everything else. So `V` is relative to
the current candidate set: identical documents score differently under a different pool.
Keep this in mind before proposing an ANN index — there is no ivfflat/hnsw index on
`chunks.embedding` today, and adding one changes which rows reach the statistics, not just
how fast they are found. Treat it as a retrieval-quality change requiring measurement, not
a performance tweak.

The full score is `4·P1 + 2·P2 + (K+1)/(K+L) + 2·(K+1)/(K+V)` with all signals on; weights per signal
combination are fixed in `ai/search.py` and chosen so a condition in the title outranks
everything below it.

## Measuring, always

```bash
PYTHONPATH=src .venv/Scripts/python.exe -m scripts.evaluate_retrieval --content \
  --rankings src/tests/eval/synthetic_rankings.json \
  --baseline src/tests/eval/synthetic_baseline.json --output var/output/metrics.json
```

The synthetic corpus and rankings **validate the metric mechanism, not model quality** —
say so whenever you report those numbers. For a real measurement, build 30 labelled cases
from the actual corpus (fragments identified by relative path + SHA-256 of the text, so
they survive reindexing and PostgreSQL id changes), record a baseline before the change,
and compare after. The comparator refuses mismatched corpora/cases/configs and exits 2 on
regression. Metrics reported: Recall@50, nDCG@10 with grades 0–3, irrelevant-in-top-10,
unlabelled-in-top-10, warning coverage in top 50.

None of this is clinical validation. Do not describe it as such.

## Failing loudly

Embedding bugs are quiet by nature, so this layer is deliberately intolerant:

- `get_profile()` raises on an unknown model rather than guessing a dimension.
- `VllmEmbedding` and `running_embedding_server()` refuse to continue when the server cannot
  start or the GPU is busy. A wrong response (count or width of vectors) stops the build; nothing
  is retried. `OllamaQueryEmbedding` raises `SEMANTIC_MODEL_UNAVAILABLE` for a failed request or
  a wrong vector count or width.
- `create_embedding_model()` validates the profile *before* loading anything.
- `ensure_schema()` raises `INDEX_DIMENSION_CHANGE_REQUIRES_SYNC` rather than altering a
  vector column behind the synchronizer's back.
- A reader whose index metadata does not match raises `IndexUnavailable`
  (`INDEX_RESYNC_REQUIRED`) instead of serving mismatched vectors.

Preserve this when extending the module: validate up front, raise a specific exception
with an actionable message, and never degrade silently into a configuration that produces
plausible-looking but wrong vectors. Catch specific exception types.

## Keeping it testable

Tests are written by the **app-tester** role (`.claude/agents/app-tester.md`). What
this role owes it: the model-dependent parts stay behind `EmbeddingProfile`, the
`embed(texts, batch_size, parallel)` interface of the build and `query_embed(texts)` of the questions, so a test can substitute deterministic
vectors of the right width without loading anything. Window arithmetic, templating and
averaging stay pure functions, separable from the model that consumes their output.
Never make the real model, a GPU or network access a precondition for exercising that
logic.

Retrieval *quality* is measured, not asserted — see the section above. It is the
app-tester's "retrieval quality" perspective, and it reports deltas against a baseline
rather than passing or failing.

## Index builds

```bash
PYTHONPATH=src .venv/Scripts/python.exe src/scripts/build_hybrid_index.py   # starts and stops vllm-embed itself
```

Incremental by SHA-256; deleted documents are removed. Publication is atomic under
`INDEX_LOCK` — a failure keeps the previous generation **and** its dimension. `pyahocorasick`
imports as `ahocorasick` (the builder checks before starting workers). `vllm-embed` reads its
Hugging Face weights (`models--Qwen--Qwen3-Embedding-4B`) from `model_cache/`, offline; the
Ollama model is pulled once with `ollama pull qwen3-embedding:4b-q8_0`.
