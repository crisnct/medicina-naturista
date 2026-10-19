# XMind 8 — file format and editing

This guide is shared by Claude and ChatGPT/Codex. Read repository-root `AGENTS.md` and
`.claude/README.md`; adapt tool names and shell syntax to the active host.

How to read and write `.xmind` files in this repository. For *what* a diagram in
`architecture/` must say and how it is verified, see
[architecture.md](architecture.md).

Target: **XMind 8 R3.7.9**, content schema `2.0`. Not XMind Zen / XMind 2020+, whose
JSON-based `content.json` format this project does not use.

## Anatomy of a workbook

An `.xmind` is a ZIP archive:

| Entry | Role |
|---|---|
| `content.xml` | Sheets, topics, titles, notes, relationships, positions |
| `styles.xml` | Named styles referenced by `style-id` |
| `meta.xml` | Creator, version, thumbnail origin and background colour |
| `META-INF/manifest.xml` | Declares every entry, including attachments, with media types |
| `attachments/` | Files linked from topics (source snapshots, notes) |
| `Thumbnails/thumbnail.png` | Preview image |
| `Revisions/` | XMind's own revision history |

`content.xml` opens with the namespace set XMind 8 expects — `xmap:xmlns:content:2.0`
plus `fo`, `svg`, `xhtml`, `xlink`. Keep it byte-identical in shape; a dropped namespace
makes the file unopenable.

## Structures used here

- **Sheets.** `<sheet id="…">` with a central `<topic>` and a `<title>`. Workbooks use
  two sheets where detail warrants it: an overview (`01 — Execution overview`) and a
  drill-down (`02 — Detailed execution`).
- **Detached topics** for stage boxes, positioned explicitly:
  `<topic …><position svg:x="2340" svg:y="680"/></topic>` inside
  `<topics type="detached">`. Position them on a grid; XMind will not lay them out for
  you.
- **Relationships** as edges: `<relationship end1="<id>" end2="<id>" style-id="arrow">`
  with a `<title>` carrying a branch label (`YES`, `NO`) or empty for plain flow.
- **Notes** carry the prose: `<notes><plain>…</plain></notes>` on the central topic and
  on each stage.
- **Titles** are short, often two lines, with an explicit `<title svg:width="280">`.

## Styles

Never inline colours. `styles.xml` defines the palette and `content.xml` references it by
`style-id`:

`central`, `stage1`…`stage8`, `step`, `context`, `decision`, `output`, `bypass`, `muted`,
`warning`, `annotation`, `arrow`.

Segoe UI throughout; `shape-class="org.xmind.topicShape.roundedRect"`;
`line-class="org.xmind.branchConnection.roundedElbow"`. Reuse these so every diagram in
the set reads as one system. Adding a style means adding it to `styles.xml`, not
decorating a topic inline.

## Links

- **Cross-sheet / cross-topic:** `xlink:href="xmind:#<sheet-or-topic-id>"`
- **Attachment:** `xlink:href="xap:attachments/<file>"` — and the file **must** also be
  declared in `META-INF/manifest.xml` with its media type, or XMind 8 silently drops it.

## Editing workflow

XMind 8 is a desktop application and cannot run here. Edit the XML directly:

```bash
cd /tmp && rm -rf xm && mkdir xm && cd xm
unzip -q "C:/Data/Workspace/medicina-naturista/architecture/<name>.xmind"
# edit content.xml / styles.xml / META-INF/manifest.xml
zip -q -r -X "C:/Data/Workspace/medicina-naturista/architecture/<name>.xmind" .
```

To inspect structure before changing anything:

```bash
cd /tmp/xm && python -c "
import re
d = open('content.xml', encoding='utf-8').read()
print('sheets:', len(re.findall(r'<sheet ', d)))
print('topics:', len(re.findall(r'<topic ', d)))
print('relationships:', len(re.findall(r'<relationship ', d)))
print('style-ids:', sorted(set(re.findall(r'style-id=\"([^\"]+)\"', d))))
"
```

Rules when rezipping:

- **Keep ids stable.** A changed topic id breaks every relationship and cross-sheet link
  pointing at it. New ids are 32-character lowercase hex.
- **Preserve `Revisions/` and `Thumbnails/`** entries and their manifest declarations.
- **Keep the XML declaration and namespaces** as they were.
- `-X` strips extra file attributes; include every extracted entry, directories included.

## Verifying

You cannot confirm a rendering from here. Re-open the archive and check the XML parses,
that every `end1`/`end2` resolves to an existing topic id, and that every
`xap:attachments/` link has a manifest entry — then tell the user to open it in XMind 8,
because that is the only real check. Do not report a diagram as visually confirmed when
you have only validated the XML.
