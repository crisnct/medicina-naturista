# Hybrid Index Generation Flow

**Input:** Markdown files from `data/documents`.

**Output:** the semantic index, lexical index, and traceability files in `data/hybrid_index`.

## 1. Start the process — `rebuild_index.ps1`

-   **1.1.** Receive the `BatchSize` parameter; its default value is `64`.
-   **1.2.** Configure PowerShell to stop at the first error.
-   **1.3.** Determine the project root directory.
-   **1.4.** Remove `HF_HUB_OFFLINE` so the model can be downloaded when it is not already cached.
-   **1.5.** Start Python from `.venv`.
-   **1.6.** Execute `build_hybrid_index.py` with these arguments:
    -   **1.6.1.** `--source data/documents`.
    -   **1.6.2.** `--output data`.
    -   **1.6.3.** `--batch-size 64` or the value supplied by the user.
-   **1.7.** Return the exit code received from the Python script.

## 2. Prepare the directories — `build_hybrid_index.py`

-   **2.1.** Convert the source and output directories to absolute paths.
-   **2.2.** Verify that `data/documents` exists.
-   **2.3.** Verify that the output directory is not inside the source directory.
-   **2.4.** Create `data/hybrid_index` when it does not exist.
-   **2.5.** Create `data/model_cache` when it does not exist.
-   **2.6.** Recursively find every file with the `.md` extension.
-   **2.7.** Sort the files deterministically by relative path.
-   **2.8.** Stop the process when no Markdown files are found.

## 3. Read and split every document into fragments

-   **3.1.** Read the size and last-modified time of each `.md` file.
-   **3.2.** Read the raw file contents.
-   **3.3.** Try `UTF-8 BOM`, `UTF-8`, `UTF-16`, `CP1250`, and `CP1252` decoding in sequence.
-   **3.4.** Normalize line endings and remove NUL characters.
-   **3.5.** Normalize Unicode to NFC while preserving Romanian diacritics.
-   **3.6.** Calculate the SHA-256 checksum of the source file.
-   **3.7.** Create `SourceFile` metadata: path, size, encoding, line count, and checksum.
-   **3.8.** Split the document into Markdown blocks based on headings, paragraphs, lists, and tables.
-   **3.9.** Treat regular headings as strict section boundaries.
-   **3.10.** Treat `Pagina N` or `Page N` markers as soft boundaries without using them as semantic headings.
-   **3.11.** For blocks larger than `MAX_CHARS=1400`, find a split point in this order:
    -   **3.11.1.** Sentence ending.
    -   **3.11.2.** Line ending, especially for lists and tables.
    -   **3.11.3.** Whitespace between words.
    -   **3.11.4.** The strict 1,400-character limit when no safer split point exists.
-   **3.12.** Combine complete units until the fragment approaches `TARGET_CHARS=1200`.
-   **3.13.** Carry at most `OVERLAP_CHARS=240` characters made from complete units.
-   **3.14.** At a page boundary, optionally carry the last complete sentence into the next fragment.
-   **3.15.** Never combine content from different Markdown sections.
-   **3.16.** Create a `Chunk` object for every fragment with:
    -   **3.16.1.** A unique `chunk_id`.
    -   **3.16.2.** Its `embedding_row` position in the vector matrix.
    -   **3.16.3.** The source path and source checksum.
    -   **3.16.4.** The source line range.
    -   **3.16.5.** The semantic heading or section.
    -   **3.16.6.** The text, character count, and fragment checksum.
-   **3.17.** Report preparation progress after every 50 files and after the final file.
-   **3.18.** Stop the process when no fragments are produced.

## 4. Load the semantic model

-   **4.1.** Select the default model `intfloat/multilingual-e5-small`.
-   **4.2.** Check whether FastEmbed already knows the model.
-   **4.3.** Register the model description when it is not already available in FastEmbed.
-   **4.4.** Load the ONNX model from `data/model_cache`.
-   **4.5.** Download the model and tokenizer only when they are missing from the local cache.
-   **4.6.** Configure ONNX Runtime to use up to `CPU count - 1` threads.

## 5. Generate the embeddings

-   **5.1.** Build each E5 document input from:
    -   **5.1.1.** The `passage:` prefix.
    -   **5.1.2.** The source filename.
    -   **5.1.3.** The semantic heading or section when available.
    -   **5.1.4.** The fragment text.
-   **5.2.** Send fragments to the model in batches of 64 or the requested batch size.
-   **5.3.** Approximately every 10 seconds, report processed fragments, percentage, elapsed time, rate, and ETA.
-   **5.4.** Collect one 384-dimensional vector for every fragment.
-   **5.5.** Verify that the matrix shape is `(fragment_count, 384)`.
-   **5.6.** Verify that all vectors contain finite values and that none are zero vectors.
-   **5.7.** L2-normalize every vector.
-   **5.8.** Print the final embedding-stage summary.

## 6. Verify the source files after embedding

-   **6.1.** Read the size and last-modified time of every source file again.
-   **6.2.** Compare them with the values captured before embedding.
-   **6.3.** Stop the build when a source document changed during processing.

## 7. Build the artifacts in a staging directory

-   **7.1.** Create a temporary `data/hybrid_index/index-build-*` staging directory.
-   **7.2.** Write the normalized semantic matrix to `embeddings.npy`.
-   **7.3.** Write fragments and their metadata to `fragments.jsonl`.
-   **7.4.** Write source metadata and checksums to `source_manifest.jsonl`.
-   **7.5.** Create `index.sqlite3`.
-   **7.6.** Create the SQLite `metadata`, `files`, and `chunks` tables.
-   **7.7.** Create the `chunks_fts` lexical FTS5 index.
-   **7.8.** Insert metadata, source files, fragments, and FTS records into SQLite.
-   **7.9.** Run `PRAGMA integrity_check` and stop when the database is invalid.
-   **7.10.** Write `manifest.json` with the model, vector dimension, chunking strategy, and source and fragment counts.
-   **7.11.** Calculate checksums for the primary artifacts.
-   **7.12.** Write the checksums to `SHA256SUMS.txt`.

## 8. Publish the hybrid index

-   **8.1.** Move each validated artifact from staging to `data/hybrid_index` with `os.replace`.
-   **8.2.** Publish these six files:
    -   **8.2.1.** `embeddings.npy` — semantic vectors.
    -   **8.2.2.** `index.sqlite3` — metadata, fragments, and the lexical FTS5 index.
    -   **8.2.3.** `fragments.jsonl` — auditable fragment export.
    -   **8.2.4.** `source_manifest.jsonl` — source-document inventory.
    -   **8.2.5.** `manifest.json` — build configuration.
    -   **8.2.6.** `SHA256SUMS.txt` — artifact checksums.
-   **8.3.** Remove the temporary directory when it is empty.
-   **8.4.** Print the final JSON result: status, source count, fragment count, matrix shape, and output path.
-   **8.5.** Return exit code `0` to `rebuild_index.ps1` when the build succeeds.
-   **8.6.** On failure, print the exception type and message and return a non-zero exit code.

## Final result

```text
data/hybrid_index/
├── embeddings.npy
├── fragments.jsonl
├── index.sqlite3
├── manifest.json
├── source_manifest.jsonl
└── SHA256SUMS.txt
```

This document complements the detailed technical diagram in `01-generare-embeddings.md` and explains the flow without Mermaid syntax or sequence-diagram complexity.