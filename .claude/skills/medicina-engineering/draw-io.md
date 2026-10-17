---
name: drawio-skill
title: Draw.io Professional Diagrams
category: ai-ml
description: Turns natural language, application codebase files, database schemas, and API specs into fully editable, visually optimized .drawio architecture diagrams.
author: Agents365-ai
version: 1.32.0
platforms: [openclaw, hermes, claude-code]
requirements:
  - drawio-desktop >= 24.0.0
permissions:
  - filesystem: read/write
  - shell: execute
---

# Draw.io Diagram Generation Skill

## Purpose
Use this skill whenever the user explicitly requests diagrams, flowcharts, architecture maps, ER diagrams, UML sequence charts, or network topologies. Also trigger it proactively when explaining backend systems or code containing 3+ components with complex data flows.

## Core Rules for the Agent
1. **Never write raw markdown tables or plain lists** when the user requests a structural system architecture visualization. Instead, output a structured `.drawio` XML graph payload.
2. **Always structure output** utilizing valid `mxGraphModel` configurations embedded within standard `<mxfile><diagram><mxGraphModel><root>...</root></mxGraphModel></diagram></mxfile>` blocks.
3. **Handle coordinates strictly.** Ensure every vertex layout element possesses distinct `x`, `y`, `width`, and `height` dimensions to prevent overlapping blocks or clipping.
4. **Leverage the local draw.io engine execution path** to validate generated diagrams, outputting local asset mirrors in PNG or SVG whenever requested.

## Execution Handlers
When a diagram generation execution triggers, invoke the bundled local engine utility script:
```bash
# Core generation and auto-layout pass
node ./dist/index.js --input=\$TEXT_PROMPT_OR_CODEBASE --output=./diagram.drawio --preset=corporate

# Validation and visual fix loop (checks for text clipping or overlapping nodes)
drawio-cli --export --format=png --output=./render_check.png ./diagram.drawio
```
