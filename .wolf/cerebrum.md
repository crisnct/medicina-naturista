---
description: learned preferences, project conventions, and Do-Not-Repeat rules
budget_tokens: 2000
---
# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: —

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

## Key Learnings

<!-- Project-specific conventions discovered during development. -->

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->

<!-- openwolf:native-memory-index:begin -->
## Native memory index (Claude Code, this machine)

Topics Claude Code recorded in its own memory. The files live in the
machine-local auto-memory directory, not in this repo; ask the person who
owns this machine, or re-derive, if you need the detail.

- [Never start full reindex myself](feedback_no_autonomous_reindex.md) — always give the user the rebuild command, let them run it
- [Retrieval plan excludes symptoms](project_retrieval_no_symptoms.md) — scoring plan only; the AI condition fallback DOES allow symptoms
- [Reranker measured, not integrated](project_reranker_measured.md) — Jina v2: 4-11 s, no nDCG gain on eval set
- [R1/R2/D1 fragmentation status](project_fragmentation_r1_r2_d1.md) — implemented, eval regressed; user will restructure sources to Markdown later
- [Scoring P1–P4 plan](project_scoring_p1_p4_plan.md) — confirmed formula decisions: 8·P1+4·P2+2·L+V, no top-N, 1M-char tail cut
- [Qwen migration done](project_qwen_migration_done.md) — Qwen only, formula 4·P1+2·P2+L+V, deployed; SEARCH_SEMANTIC_ONLY switch exists
- [Search signals A/B/C plan](project_search_signals_plan.md) — selectable P/L/V checkboxes; L redefined as expressions found / N, literal phrases
- [Condition AI fallback plan](project_condition_ai_fallback_plan.md) — approved: AI names used as-is, symptoms allowed, gemma3:1b local + HF fallback, D2=V2
- [Condition AI implemented](project_condition_ai_implemented.md) — built 2026-10-04; gemma3:1b too weak (smoke test), HF-first/bigger model pending
- [Conditions JSONL + herbs plan](project_conditions_jsonl_herbs_plan.md) — 2026-10-05; FR X + corpus first, then EMA; ro not unique; no group; all questions closed
- [No commits](feedback_no_commits.md) — never commit; user commits at the end
- [ICD-10 per-letter plan](project_icd10_letters_plan.md) — letter = canonical-name initial; A done (79), 22 pending for other letters; next B
- [No diacritics](feedback_no_diacritics.md) — Romanian names without diacritics, in data and when quoting them in replies
<!-- openwolf:native-memory-index:end -->
