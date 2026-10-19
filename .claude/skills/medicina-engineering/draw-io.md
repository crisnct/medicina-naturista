# draw.io diagrams

This guide is shared by Claude and ChatGPT/Codex. Read repository-root `AGENTS.md` and
`.claude/README.md`; adapt tool names and shell syntax to the active host.

For a diagram requested **outside** `architecture/` — an ad-hoc visual for a PR or an
explanation, or a `.drawio` file the user explicitly asks for.

Not for the canonical architecture workbooks: those are XMind 8 only. See
[architecture.md](architecture.md) for the format rules and [xmind.md](xmind.md) for the
`.xmind` format itself. Adding a `.drawio` copy of an `architecture/*.xmind` flow creates
a second source of truth and needs explicit approval.

## When a diagram is the right answer

When the user asks for one, or when the thing being explained is a graph — components
with edges between them, a state machine, a flow with branches. Prose and tables remain
the normal way to answer a question in this repository; a diagram is an addition to an
explanation, not a replacement for one. Do not convert a three-paragraph answer into a
diagram because the subject happens to have several parts.

## Output format

Write the XML directly — a complete `mxfile` the user can open:

```xml
<mxfile host="app.diagrams.net">
  <diagram name="Page-1">
    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10" page="1"
                  pageWidth="1100" pageHeight="850">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <mxCell id="node1" value="Label" style="rounded=1;whiteSpace=wrap;html=1;"
                vertex="1" parent="1">
          <mxGeometry x="40" y="40" width="160" height="60" as="geometry"/>
        </mxCell>
        <mxCell id="edge1" style="edgeStyle=orthogonalEdgeStyle;html=1;"
                edge="1" parent="1" source="node1" target="node2">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

Rules that keep a generated file openable and readable:

- `<mxCell id="0"/>` and `<mxCell id="1" parent="0"/>` must both be present; every other
  cell has `parent="1"`.
- Every vertex needs an explicit `x`, `y`, `width`, `height`. There is no auto-layout —
  place nodes on a grid yourself and leave room for labels, or boxes overlap and text
  clips.
- Edges reference `source` and `target` by cell id, with `<mxGeometry relative="1"
  as="geometry"/>`.
- Ids are unique and stable; an edge pointing at a missing id makes the file unopenable.
- Escape `&`, `<`, `>` in labels (`&amp;`, `&lt;`, `&gt;`).
- One page per diagram unless the user asks for more.

## Tooling — read this before claiming anything is rendered

**There is no draw.io tooling in this checkout.** No bundled generator, no `drawio-cli`
on PATH, no drawio-desktop install. You cannot render, auto-layout, validate visually, or
export PNG/SVG from here.

So: write the `.drawio` file, say where it is, and ask the user to open it in
diagrams.net or the desktop app. Never report a layout check, a visual fix pass or an
image export you did not run. If the user wants an image rather than an editable file,
tell them it has to be exported on their side.

What you *can* check: the XML parses, cell ids are unique, and every edge's `source` and
`target` resolve to a cell that exists.

```bash
python -c "
import xml.etree.ElementTree as ET
t = ET.parse('diagram.drawio'); r = t.getroot()
ids = {c.get('id') for c in r.iter('mxCell')}
bad = [(c.get('id'), e) for c in r.iter('mxCell')
       for e in (c.get('source'), c.get('target')) if e and e not in ids]
print('cells:', len(ids), '| dangling refs:', bad or 'none')
"
```

## Placement

Ask where it should live, or put it next to what it documents. Do not add `.drawio` files
to `architecture/`. A throwaway diagram for a PR comment does not need committing at all
— the XML in the reply is enough.
