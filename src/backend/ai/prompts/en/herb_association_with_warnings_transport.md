# Combined classification and warnings

Return only compact JSON with two sections, `relations` and `warnings`, without Markdown, comments or surrounding text. In `relations` include every `candidates` ID exactly once with `local_condition` (the source's local condition wording), `recommendation` and `prohibition` (booleans). Keep all classification rules, including the application's recommendation priority.

In `warnings` include every `safety_targets` ID exactly once with `status` and `items`. Each item contains exactly `kind`, `focus_id`, `summary`, `passage_ids`, `partners`. Focus IDs come from the target's `warning_statement_ids`, summaries are short English wording, and passage IDs select the unit's catalog entries; never return quotation text.

Read the complete `units[].text` in its single field. Warnings concern a product independently of each relation's condition. Do not repeat them per condition or change relation classification just to return warnings.
