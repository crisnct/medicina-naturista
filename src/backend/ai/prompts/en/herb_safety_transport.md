# Warnings-only output

Return only `{"warnings":{"s0":{"status":"complete","items":[]}}}` as compact JSON without Markdown, comments or text outside the object. Include every `safety_targets` ID exactly once, without extra IDs or fields. Each item has exactly `kind`, `focus_id`, `summary`, `passage_ids`, `partners`. `focus_id` belongs to the target's `warning_statement_ids`; `summary` is the short displayed English wording; `passage_ids` selects IDs from the target unit's catalog. Do not return quotation text, relations, recommendation, prohibition, ranking or reclassify associations.
