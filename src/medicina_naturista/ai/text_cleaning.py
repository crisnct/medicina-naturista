"""Strip external links and "see also" cross-references from indexed and
displayed text.

Every substitution here must never add or remove a newline character:
line_start/line_end are computed once, from this cleaned text, and are later
used to re-read the *original* file on disk by line number (see
Retriever._context/_group_context in ai/retrieval.py). If cleaning shifted
line boundaries, those re-reads would pull the wrong lines.
"""
from __future__ import annotations

import re

# [etichetă](url) -> etichetă. Restricted to a single line: a link split
# across lines is rare in this corpus and not worth risking a newline match.
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]\n]*)\]\(([^()\n]+)\)")

# <a href="...">etichetă</a> -> etichetă.
_HTML_ANCHOR_RE = re.compile(r"<a\b[^>\n]*>([^<\n]*)</a>", re.IGNORECASE)

# A line containing a "see also" reference is dropped in its entirety (the
# newline itself is kept). Restricted to lines that actually contain the
# trigger phrase: a reference wrapped across several lines (common in
# PDF-extracted books) only has the line with "Vezi și"/"vezi si" removed —
# the wrapped continuation on following lines is left behind as a residual
# fragment. Accepted as a known v1 limitation rather than risk merging or
# dropping unrelated lines.
_VEZI_SI_LINE_RE = re.compile(r"(?m)^.*\b[Vv]ezi\s+(?:și|si)\b.*$")

# Any remaining bare URL not part of a Markdown/HTML link.
_BARE_URL_RE = re.compile(r"https?://\S+")

# Collapse runs of spaces/tabs left behind by the removals above, and trim
# trailing whitespace before a newline. Neither touches "\n" itself.
_INLINE_GAPS_RE = re.compile(r"[ \t]{2,}")
_TRAILING_SPACE_RE = re.compile(r"[ \t]+(?=\n)")


def clean_text(text: str) -> str:
    """Remove external link destinations and "see also" cross-references
    from ``text`` while preserving every newline (and therefore every line
    number) it contains."""
    cleaned = _MARKDOWN_LINK_RE.sub(r"\1", text)
    cleaned = _HTML_ANCHOR_RE.sub(r"\1", cleaned)
    cleaned = _VEZI_SI_LINE_RE.sub("", cleaned)
    cleaned = _BARE_URL_RE.sub("", cleaned)
    cleaned = _INLINE_GAPS_RE.sub(" ", cleaned)
    cleaned = _TRAILING_SPACE_RE.sub("", cleaned)
    return cleaned
