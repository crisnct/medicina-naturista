# Complete-fragment classification output

Return only `{"relations":{"r0":{"local_condition":"...","recommendation":false,"prohibition":false}}}`, including each ID from `candidates` exactly once.

`units[].text` is the complete indexed excerpt in one field. Read it from beginning to end; do not assume missing or separately partitioned content.

For every relation, `local_condition` is the condition's exact local wording in the product statement, or an empty string when unidentified; `recommendation` says whether the source recommends the candidate for that condition; `prohibition` says whether it explicitly requires avoiding it for that condition.

Use all text, headings and candidate context without transferring statements between products or conditions. Do not return quotations, citation IDs, final labels, explanations or extra fields.
