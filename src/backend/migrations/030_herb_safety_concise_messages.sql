-- Keep full historical quotations while separating the displayed message from its evidence.
ALTER TABLE herb_safety_evidence
    ADD COLUMN quote_text TEXT,
    ADD COLUMN focus_start INTEGER,
    ADD COLUMN focus_end INTEGER;

UPDATE herb_safety_evidence AS evidence
SET quote_text = warning.text,
    focus_start = evidence.quote_start,
    focus_end = evidence.quote_end
FROM herb_safety_warnings AS warning
WHERE warning.run_id = evidence.run_id AND warning.warning_id = evidence.warning_id;

ALTER TABLE herb_safety_evidence
    ALTER COLUMN quote_text SET NOT NULL,
    ALTER COLUMN focus_start SET NOT NULL,
    ALTER COLUMN focus_end SET NOT NULL,
    ADD CONSTRAINT herb_safety_evidence_quote_text_nonempty CHECK (length(btrim(quote_text)) > 0),
    ADD CONSTRAINT herb_safety_evidence_focus_valid CHECK (
        quote_start <= focus_start AND focus_start < focus_end AND focus_end <= quote_end
    );

COMMENT ON COLUMN herb_safety_warnings.text IS
    'Concise source-supported warning message for new generations; historical rows retain their original text.';
COMMENT ON COLUMN herb_safety_evidence.quote_text IS
    'Full unchanged source quotation, independent of the concise warning message.';
COMMENT ON COLUMN herb_safety_evidence.focus_start IS
    'Inclusive Unicode offset of the product-specific statement; legacy rows retain the full quote span.';
COMMENT ON COLUMN herb_safety_evidence.focus_end IS
    'Exclusive Unicode offset of the product-specific statement, within the full quotation.';
