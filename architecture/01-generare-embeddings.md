# 01 · Generarea embeddings (indexul hibrid local)

**Proiect:** medicina-naturista  
**Componente implicate:** `scripts/rebuild_embeddings.ps1`, `scripts/build_medical_embeddings.py`, `src/medicina_naturista/ai/search.py`  
**Tip diagrame:** sequence diagram (Mermaid)

## Context

Indexul este construit offline, la cerere, din fișierele Markdown din `data/documents`. Rezultatul are două componente folosite împreună la căutare:

| Componentă | Fișier | Rol |
|---|---|---|
| Semantic | `data/embeddings/embeddings.npy` | matrice `float32` N × 384, vectori normalizați L2 |
| Lexical | `data/embeddings/index.sqlite3` | tabelele `metadata`, `files`, `chunks` + FTS5 `chunks_fts` |
| Trasabilitate | `chunks.jsonl`, `source_manifest.jsonl`, `manifest.json`, `SHA256SUMS.txt` | legătura fragment → fișier-sursă → linii, sume de control |

Parametri de chunking: `TARGET_CHARS=1200`, `MAX_CHARS=1600`, `OVERLAP_CHARS=240`.  
Model: `intfloat/multilingual-e5-small` (ONNX, via FastEmbed), dimensiune 384, prefix document `passage: `, prefix interogare `query: `.

## 1.1 Construirea indexului (build complet)

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Administrator
    participant PS as rebuild_embeddings.ps1
    participant B as build_medical_embeddings.py<br/>build()
    participant FS as data/documents<br/>(fișiere .md)
    participant CH as Chunker<br/>markdown_blocks / chunk_document
    participant FE as FastEmbed TextEmbedding<br/>(ONNX Runtime)
    participant HF as Hugging Face Hub
    participant MC as data/model_cache
    participant ST as Staging dir<br/>embeddings/index-build-*
    participant DB as SQLite + FTS5<br/>index.sqlite3
    participant IDX as data/embeddings

    Admin->>PS: rulează scriptul (BatchSize=64)
    PS->>PS: șterge HF_HUB_OFFLINE (permite descărcarea modelului)
    PS->>B: python build_medical_embeddings.py --source --output --batch-size
    B->>B: validează source ≠ output, creează embeddings/ și model_cache/

    B->>FS: rglob("*.md"), sortare case-insensitive
    FS-->>B: listă de căi
    alt nu există fișiere .md
        B-->>PS: RuntimeError "No Markdown files found"
    end

    loop pentru fiecare fișier .md
        B->>FS: stat() — memorează (size, mtime_ns)
        B->>FS: read_bytes()
        B->>B: decodare utf-8-sig / utf-8 / utf-16 / cp1250 / cp1252
        B->>B: normalize_text (NUL, CRLF → LF, Unicode NFC)
        B->>B: SHA-256 pe conținutul brut → SourceFile
        B->>CH: chunk_document(text)
        CH->>CH: markdown_blocks — blocuri pe titluri și paragrafe,<br/>titluri "Pagina N" = graniță soft
        CH->>CH: split_long_piece — tăiere la propoziție / rând / spațiu (max 1600)
        CH->>CH: combinare până la ~1200 caractere, overlap ≤ 240<br/>graniță hard la titlu, overlap de o propoziție la graniță soft
        CH-->>B: fragmente (text, line_start, line_end, heading)
        B->>B: creează Chunk (chunk_id, embedding_row, text_sha256)
    end

    B->>FE: create_embedding_model(model, cache_dir)
    alt modelul nu e în lista FastEmbed
        FE->>FE: add_custom_model (MEAN pooling, normalizare, dim 384, onnx/model.onnx)
    end
    alt modelul lipsește din cache
        FE->>HF: descarcă snapshot-ul modelului
        HF-->>FE: fișiere ONNX + tokenizer
        FE->>MC: salvează local
    else model deja în cache
        FE->>MC: încarcă local
    end
    FE-->>B: instanță TextEmbedding (threads = CPU - 1)

    B->>FE: embed(iter_embedding_inputs, batch_size=64)
    Note right of B: input = "passage: " + nume fișier + heading + text
    loop pe loturi de 64 fragmente
        FE-->>B: vectori 384-dim
        B->>B: raport progres la 10 s (rată, ETA)
    end
    B->>B: validează forma (N, 384), valori finite, fără vectori zero
    B->>B: re-normalizare L2

    B->>FS: re-stat() pentru toate fișierele
    alt un fișier s-a modificat în timpul build-ului
        B-->>PS: RuntimeError "Source files changed during build"
    end

    B->>ST: mkdtemp(prefix="index-build-")
    B->>ST: np.save embeddings.npy
    B->>ST: chunks.jsonl, source_manifest.jsonl
    B->>DB: create_sqlite — CREATE TABLE metadata / files / chunks,<br/>FTS5 chunks_fts (unicode61, remove_diacritics 2)
    B->>DB: INSERT metadata, files, chunks, chunks_fts
    B->>DB: PRAGMA integrity_check
    DB-->>B: ok
    B->>ST: manifest.json (chunking, model, prefixe, avertismente)
    B->>ST: SHA256SUMS.txt pentru cele 5 artefacte
    loop pentru fiecare artefact (6 fișiere)
        B->>IDX: os.replace(staging/artefact, embeddings/artefact)
    end
    B->>ST: rmdir staging
    B-->>PS: JSON {status: ok, source_files, chunks, embedding_shape}
    PS-->>Admin: exit code
```

## 1.2 Embedding-ul interogării la runtime (consumatorul indexului)

Același model este folosit la căutare, cu prefixul `query: `. Diagrama arată ce se întâmplă pentru **o singură** interogare în `search.rank()`; detaliile despre câte interogări se trimit per raport sunt în documentul 02.

```mermaid
sequenceDiagram
    autonumber
    participant R as Retriever / CLI
    participant S as search.rank()
    participant IDX as data/embeddings
    participant FE as FastEmbed<br/>(create_model, lru_cache)
    participant DB as index.sqlite3

    R->>S: rank(index_dir, query, limit, candidates)
    S->>IDX: citește manifest.json (model, dimensiune)
    S->>IDX: np.load(embeddings.npy, mmap_mode="r")
    S->>FE: create_model(model, dim, model_cache)
    Note over FE: HF_HUB_OFFLINE=1, metadatele cache-ului<br/>normalizate Windows → Linux, instanță reutilizată prin lru_cache
    S->>FE: query_embed("query: " + text)
    FE-->>S: vector 384-dim
    S->>S: normalizare L2, scoruri = embeddings · q
    S->>S: argpartition → top "candidates" semantic
    S->>DB: FTS5 MATCH (max 32 tokeni, OR) ORDER BY bm25 LIMIT candidates
    DB-->>S: rowid-uri în ordinea bm25
    S->>S: Reciprocal Rank Fusion, k = 60 → top "limit"
    S->>DB: SELECT * FROM chunks WHERE chunk_id IN (...)
    DB-->>S: rânduri fragmente
    S-->>R: rezultate (hybrid_score, semantic_similarity, lexical_rank, sursă, linii, text)
```

## Observații de arhitectură

1. **Înlocuirea artefactelor nu este atomică pe ansamblu.** `os.replace` este atomic per fișier, dar cele 6 fișiere sunt mutate unul câte unul. Dacă procesul se oprește la mijloc sau aplicația web citește în acel interval, `embeddings.npy` poate aparține build-ului nou, iar `index.sqlite3` celui vechi. Cum `embedding_row` leagă cele două, rezultatul ar fi fragmente greșite fără nicio eroare. Soluție: director versionat (`embeddings/v<timestamp>/`) plus un pointer (`current.json` sau symlink) schimbat la final într-un singur pas.
2. **Dimensiunea 384 este fixă în cod**, deși `--model` este configurabil. Cu alt model build-ul cade abia după embedding, la validarea formei. Dimensiunea trebuie citită din descrierea modelului sau trecută ca parametru.
3. **Build-ul este complet de fiecare dată** și ține tot corpusul în memorie (listă de `Chunk`, apoi lista de vectori). Pentru arhiva actuală e acceptabil. La creșterea corpusului merită reconstruire incrementală pe baza `source_manifest.jsonl`: SHA-256 per fișier există deja, deci se pot re-embedda doar fișierele modificate.
4. **Protecția la modificări concurente este bună** (compararea `size` + `mtime_ns` înainte și după), la fel `integrity_check` și `SHA256SUMS.txt`. Totuși, sumele de control nu sunt verificate la pornirea aplicației. O verificare la startup ar prinde un index corupt sau amestecat, inclusiv cazul de la punctul 1.
5. **La runtime, `rank()` recitește `manifest.json` și redeschide `embeddings.npy` la fiecare interogare.** Doar modelul este în cache. Detaliile și impactul sunt în documentul 02.
