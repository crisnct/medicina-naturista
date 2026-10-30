# Senior architect — architecture documentation

This guide is shared by Claude and ChatGPT/Codex. Read repository-root `AGENTS.md` and
`.claude/README.md`; adapt tool names and shell syntax to the active host.

The architect's job in this repository: which diagrams exist, what they are allowed to
claim, how a claim is verified, and which format each kind of diagram belongs in.

## Format rules

**`architecture/` is XMind 8 only.** The six workbooks there are this project's canonical
architecture documentation; `architecture/README.md` states the format is maintained only
in XMind 8. Do not introduce Mermaid, draw.io, PlantUML or PNG substitutes there.

**To create or edit one of those workbooks, read [xmind.md](xmind.md) first.** It is the
format reference — ZIP anatomy, `content.xml` structures (sheets, detached topics with
explicit `svg:x/y`, `<relationship>` edges, `<notes>`), the named style palette in
`styles.xml`, `xmind:#` and `xap:attachments/` links with their manifest requirement, and
the unzip/edit/rezip workflow with its id-stability rules. XMind 8 cannot be run here, so
the XML is edited directly and the user confirms the rendering. Read that file alongside
this one whenever you actually touch an `.xmind`; this file tells you *what* to draw, that
one tells you *how* to write it.

**[draw-io.md](draw-io.md) is for diagrams requested outside that set** — an ad-hoc
visual for a PR or an explanation, or a `.drawio` file the user explicitly asks for. It
does not apply to anything in `architecture/`: converting one of these workbooks to
`.drawio`, or adding a `.drawio` copy alongside it, creates a second source of truth for
the same flow and is a structural change needing explicit approval. If a diagram belongs
in `architecture/`, it is XMind 8.

## The six diagrams

Five of the six follow the same shape: an overview sheet of numbered stages, an
implementation-detail sheet, and a contracts/boundary-cases sheet, with
`attachments/*-architecture.md` and `attachments/code-evidence.json` carrying the
evidence behind the claims. All were reviewed on **2026-10-14** (the background report
workbook on 2026-10-15).

**`hybrid-index-generation.xmind`** — how the index is built: eight ordered stages from
CLI start and `.env` through document discovery, R1/R2/D1 fragmentation, embedding and
publication. Two sheets (overview + detailed execution), 99 topics. Its central note
records that migrations commit separately in stage 2 while stages 6–8 publish one atomic
generation **in a single transaction**, that the exclusive session lock covers
preparation and embedding too, and it pins the SHA-256 of `build_hybrid_index.py` —
which is also attached in full.

**`fragment-search-and-scoring.xmind`** — how a message becomes ranked evidence: accept
query and capture A/B/C signals → validate index generation and source selection →
resolve conditions → compute `P1 / P2 · L · V` → rank and admit against the
whole-fragment budget → capture citations and relevance % → display with independent UI
filters → the separately-thresholded report request. Three sheets, 107 topics. Its note
states the two things easiest to misread: runtime retrieval is read-only, and **scores
measure retrieval relevance, not medical confidence.**

**`final-report-generation.xmind`** — the eight stages from reviewing local evidence
through owner authorization and search-snapshot reservation, evidence admission at the
report's `minScore`, the single selected Responses provider, citation validation and
partial-report rules, PDF rendering with cited bibliography, atomic publication, and
download or email. Three sheets, 122 topics. Documents the owner guard as signed token
plus DB revocation, and notes that configuration values shown are **code defaults, not a
claim about the live deployment**.

**`report-generation-background.xmind`** — the asynchronous execution model that
supersedes the synchronous request lifetime in the diagram above: the browser starts a
session-owned job and polls, while provider requests stay synchronous inside a bounded
executor. Three sheets (admission/polling, job lifecycle and guarantees,
provider-independent execution), 24 topics, no relationship arrows — it is prose-led.
Key claims: admission uses the same registry → session lock order while the work itself
runs outside those locks; stable request IDs and active-search checks prevent duplicate
provider calls; **logical completion and physical worker termination are separate.**

**`message-classification-plan.xmind`** — how one message is routed: accept and capture
the context revision → determine intent by deterministic shortcut or local Ollama →
validate against catalog guards and strict JSON → clarify or dispatch to exactly one of
`remedii`, `planta`, `top_plante`, `diverse`, `email_raport`, each with its own outcome
branch. Three sheets, 112 topics. Its note records that this workbook **replaced the
former implementation plan with the implemented flow** — the filename still says "plan".

**`chatbot-external-connections.xmind`** — every inbound and outbound connection:
browser SPA, reverse proxy and optional tunnel, local Ollama in its two AI roles, the
selected report provider, PostgreSQL, in-process session state, local PDF creation,
Gmail delivery, the local corpus and SQL seeds, the separate index-build command, and
build-time model acquisition into `model_cache`. Three sheets, 118 topics. Its note is
load-bearing: it shows **supported connections, not simultaneous calls to every AI
provider.**

`architecture/README.md` lists them for readers and must be updated when a diagram is
added or its scope changes. Note that it still describes `message-classification-plan`
by its planning-era name; prefer the workbook's own note when the two disagree.

## The verification convention — keep it

The central topic's notes in `hybrid-index-generation.xmind` read, in part:

> Reviewed against the complete `src/scripts/build_hybrid_index.py` on 2026-10-14. …
> Code snapshot SHA-256: 86470f47…

A diagram here is a claim about code that was checked against that code at a stated date.
`hybrid-index-generation` is the strongest form — a single named source file, pinned by
hash and attached in full. The other five state a review date and carry their evidence in
`attachments/code-evidence.json` plus an `*-architecture.md` write-up, because they span
many files and no single hash would mean anything. Match whichever form the workbook you
are editing already uses; do not downgrade the index workbook to a bare date.

When you update a diagram:

1. Read the source files end to end — not a summary of them.
2. Update the note: the file list, the review date, and the fresh snapshot hash where one
   is pinned. Refresh `code-evidence.json` where that is the evidence form.
3. If you did not re-verify every stage, say which ones you did, in the note and to the
   user. Never carry an old hash or an old date forward on changed code.

A stale diagram that looks authoritative is worse than no diagram. If the code has moved
and you are not re-verifying, say so rather than leaving the old date in place.

Several workbooks also carry a scope disclaimer in their central note — retrieval scores
are not medical confidence, configuration shown is code defaults rather than the live
deployment, the connection map shows supported paths rather than simultaneous calls.
Preserve these. They are the sentences that stop a diagram being read as a stronger claim
than it is.

## Content standards

- Model the flow as it **is**, including the unhappy paths this system cares about:
  `503` during sync, atomic publication, queue admission and `429`, `403 MODEL_FORBIDDEN`,
  classification failure degrading to the existing flow, partial reports.
- Mark the local/external boundary explicitly. It is the project's central privacy claim:
  only the consultation profile plus approved fragments leave the machine.
- One stage box per real execution stage, in order, numbered. Decisions get a `decision`
  style and labelled edges.
- Keep titles short (two lines); put the explanation in the topic's notes.
- An overview sheet should be readable without the detail sheet; the detail sheet links
  back rather than repeating.
- Follow the established three-sheet shape for a new flow diagram — overview,
  implementation details, contracts and boundary cases — with the evidence attachments
  beside it. A new workbook that invents its own structure makes the set harder to read.
- Workbook text is English, including for flows whose runtime prompts and UI copy are
  Romanian or English. Keep API identifiers and intent names (`remedii`, `top_plante`, …) exactly as
  the code spells them.
