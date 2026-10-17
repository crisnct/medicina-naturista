# Senior architect — XMind 8 diagrams

`architecture/` holds the canonical architecture documentation for this project, and it is
maintained **only in XMind 8 format** (`.xmind`, XMind 8 R3.7.9, content schema 2.0). Do
not introduce Mermaid, draw.io, PlantUML or PNG substitutes.

## Existing diagrams

| File | Covers |
|---|---|
| `hybrid-index-generation.xmind` | Documents → incremental sync (SHA-256) → R1/R2/D1 fragments → embeddings → Postgres |
| `fragment-search-and-scoring.xmind` | Message → recognised conditions → `4·P1 + 2·P2 + L + V` → relevance % → context budget |
| `final-report-generation.xmind` | Message → retrieval → fragments shown → generate → provider → PDF → download/email |
| `report-generation-background.xmind` | Async flow: HTTP admission/polling, job lifecycle, provider config. Supersedes the synchronous lifetime in the older report diagram |
| `message-classification-plan.xmind` | Intent classification and routing (remedii / planta / top_plante / diverse / email_raport) |
| `chatbot-external-connections.xmind` | Every outbound connection the chatbot makes |

`architecture/README.md` lists them for readers and must be updated when a diagram is
added or its scope changes.

## File format (what you are actually editing)

An `.xmind` is a ZIP containing `content.xml`, `styles.xml`, `meta.xml`,
`META-INF/manifest.xml`, `Thumbnails/`, `Revisions/` and `attachments/`. The conventions
already established in these files:

- **Two sheets per workbook** where detail warrants it: an overview sheet
  (`01 — Execution overview`) and a drill-down sheet (`02 — Detailed execution`). The
  central topic carries a summary title plus a `<notes><plain>` block.
- **Detached topics positioned explicitly** (`<topic ... ><position svg:x=".." svg:y=".."/>`)
  for stage boxes, with `<relationship end1 end2 style-id="arrow">` edges between them.
  Relationship titles carry branch labels such as `YES` / `NO`.
- **Named styles in `styles.xml`, referenced by `style-id`**, never inline colours:
  `central`, `stage1`…`stage8`, `step`, `context`, `decision`, `output`, `bypass`,
  `muted`, `warning`, `annotation`, `arrow`. Segoe UI; rounded-rect shapes;
  rounded-elbow branch connections. Reuse this palette so diagrams read as one set.
- **Cross-sheet links** with `xlink:href="xmind:#<sheet-or-topic-id>"`; **attachment links**
  with `xlink:href="xap:attachments/<file>"`, and every attachment must also be declared
  in `META-INF/manifest.xml` with its media type.
- **Notes carry the prose.** Each stage topic has a `<notes><plain>` explaining it.

## The verification convention — keep it

The central topic's notes in `hybrid-index-generation.xmind` read, in part:

> Reviewed against the complete `src/scripts/build_hybrid_index.py` on 2026-10-14. …
> Code snapshot SHA-256: 86470f47…

A diagram here is a claim about code that was checked against that code at a stated date,
pinned by the SHA-256 of the file it describes. When you update a diagram:

1. Read the source files end to end — not a summary of them.
2. Update the note: the file list, the review date, and the fresh snapshot hash.
3. If you did not re-verify every stage, say which ones you did, in the note and to the
   user. Never carry an old hash forward on a changed file.

## Working on a diagram

XMind 8 is a desktop application; you cannot run it here. Edit by unzipping, changing
`content.xml`/`styles.xml`/manifest, and rezipping — then tell the user to open the result
in XMind 8 to confirm it renders, because that is the only real check.

```bash
cd /tmp && rm -rf xm && mkdir xm && cd xm
unzip -q "C:/Data/Workspace/medicina-naturista/architecture/<name>.xmind"
# edit content.xml / styles.xml / META-INF/manifest.xml
zip -q -r -X "C:/Data/Workspace/medicina-naturista/architecture/<name>.xmind" .
```

Preserve `Revisions/` and `Thumbnails/` entries, keep the XML declaration and namespaces
byte-identical in shape, and keep ids stable — a changed topic id breaks every
relationship and cross-sheet link pointing at it. Generate new ids as 32-char hex.

## Content standards

- Model the flow as it **is**, including the unhappy paths this system cares about:
  `503` during sync, atomic publication, queue admission and `429`, `403 MODEL_FORBIDDEN`,
  classification failure degrading to the existing flow, partial reports.
- Mark the local/external boundary explicitly. It is the project's central privacy claim:
  only the profile plus approved fragments leave the machine.
- One stage box per real execution stage, in order, numbered. Decisions get a `decision`
  style and labelled edges.
- Keep titles short (two lines, with `svg:width` set); put the explanation in notes.
