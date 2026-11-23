# Senior Python developer — embeddings specialist

This guide is shared by Claude and ChatGPT/Codex. Read repository-root `AGENTS.md` and
`.claude/README.md`; adapt tool names and shell syntax to the active host.

One model, one dimension, two backends. Everything that depends on the model is
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

`Qwen/Qwen3-Embedding-0.6B`, 1024 dimensions, unit-normalised vectors. It is the only
model the code understands: `get_profile()` raises on an unknown name rather than
guessing. An `EmbeddingProfile` carries everything model-dependent — `dimension`,
`query_template`, `passage_template`, `max_chars` (1400), `overlap_chars` (240).

**Asymmetric encoding.** Queries are wrapped in the Qwen instruct template
(`QWEN_QUERY_TEMPLATE`, deliberately English while the question stays Romanian or English);
passages get no prefix. FastEmbed does not add the instruction, so the code does.
Changing the template needs no reindex but **does** invalidate retrieval measurements —
rerun the evaluation.

## Two backends, one interface

`embed(texts, batch_size, parallel)`:

- **FastEmbed / ONNX, fp32, CPU** — queries always, and index builds without a GPU.
  `settings.embedding_threads` defaults to `min(8, cpu_count)`: few threads beat all cores
  on hybrid P/E-core CPUs.
- **`VllmEmbedding`, HTTP client of the `vllm-embed` Compose service** — index builds only
  (`EMBEDDING_DEVICE=vllm`). `EMBEDDING_THREADS` is then the number of simultaneous requests
  (32, also the server's `--max-num-seqs`) and `VLLM_EMBED_BATCH_SIZE` the windows per request (16). `ai/vllm_embed_server.py`
  asks the `vllm-supervisor` (loopback port `VLLM_SUPERVISOR_HOST_PORT`; only it has Docker access)
  to start the service when there is something to embed, waits for the model and stops it in a
  `finally`; a busy GPU (a running `medicina-vllm-*` container or an Ollama model) is the
  error `VLLM_GPU_BUSY`, and there is no CPU fallback (a silent fallback means an hours-long
  build). The server flags are fixed in `docker-compose.yaml` (`fp8_per_tensor` weights, fp8 KV cache, `--max-model-len 2048`, `--gpu-memory-utilization 0.9`).

Measured on 7037 windows (RTX 3500 Ada): the former PyTorch fp16 path 35.5 windows/s; vLLM fp16
75, bf16 82, fp8 97, fp8 with fp8 KV cache 103 (the setting in use). Cosine against CPU fp32:
fp16 0.999997, bf16 0.99986, fp8 0.9887, fp8 + fp8 KV cache 0.9818 minimum (0.992 mean), which the
project accepted. Requests (16-128) and window count per request (1-64)
do not change the speed; the GPU is the limit. That is why a GPU-built index is correctly queried
with CPU vectors. **Queries always embed on CPU regardless of `EMBEDDING_DEVICE`.**

`cached_query_model` is `lru_cache`d per process, sets `HF_HUB_OFFLINE=1` and
`ORT_DISABLE_TELEMETRY=1`, and normalises FastEmbed's cached metadata paths so a cache
written on Windows works inside a Linux container.

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

The full score is `4·P1 + 2·P2 + L + V` with all signals on; weights per signal
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
- `VllmEmbedding` and `running_embedding_server()` refuse to fall back to CPU when the server
  cannot start or the GPU is busy — a silent fallback turns a 20-minute build into an
  all-night one. A wrong response (count or width of vectors) stops the build; nothing is retried.
- `create_embedding_model()` validates the profile *before* loading anything.
- `ensure_schema()` raises `INDEX_DIMENSION_CHANGE_REQUIRES_SYNC` rather than altering a
  vector column behind the synchronizer's back.
- A reader whose index metadata does not match raises `IndexUnavailable`
  (`INDEX_RESYNC_REQUIRED`) instead of serving mismatched vectors.

Preserve this when extending the module: validate up front, raise a specific exception
with an actionable message, and never degrade silently into a configuration that produces
plausible-looking but wrong vectors. Catch specific exception types — the one broad
`except (OSError, ValueError, TypeError)` in the metadata normaliser is scoped on purpose,
because a cache-metadata quirk must not block startup.

## Keeping it testable

Tests are written by the **app-tester** role (`.claude/agents/app-tester.md`). What
this role owes it: the model-dependent parts stay behind `EmbeddingProfile` and the
`embed(texts, batch_size, parallel)` interface, so a test can substitute deterministic
vectors of the right width without loading anything. Window arithmetic, templating and
averaging stay pure functions, separable from the model that consumes their output.
Never make the real model, a GPU or network access a precondition for exercising that
logic.

Retrieval *quality* is measured, not asserted — see the section above. It is the
app-tester's "retrieval quality" perspective, and it reports deltas against a baseline
rather than passing or failing.

## Index builds

```bash
PYTHONPATH=src .venv/Scripts/python.exe src/scripts/build_hybrid_index.py   # EMBEDDING_DEVICE in .env: cpu or vllm
```

Incremental by SHA-256; deleted documents are removed. Publication is atomic under
`INDEX_LOCK` — a failure keeps the previous generation **and** its dimension. `pyahocorasick`
imports as `ahocorasick` (the builder checks before starting workers). The CPU model downloads
into `model_cache/` on first use, then everything is offline; `vllm-embed` reads its Hugging
Face weights from the same folder, offline.
