"""Compatibility exports for the public report/chat rendering API."""

from backend.reporting.chat import (
    append as _append,
)
from backend.reporting.chat import (
    ask as _ask,
)
from backend.reporting.chat import (
    condition_match as _condition_match,
)
from backend.reporting.chat import (
    download_message as _download_message,
)
from backend.reporting.chat import (
    fragments_message as _fragments_message,
)
from backend.reporting.chat import (
    generate_label,
)
from backend.reporting.chat import (
    generate_message as _generate_message,
)
from backend.reporting.chat import (
    match_type_label as _match_type_label,
)
from backend.reporting.chat import (
    normalize_text as _normalize_text,
)
from backend.reporting.chat import (
    recommendation_text as _recommendation_text,
)
from backend.reporting.chat import (
    replace_generate_message as _replace_generate_message,
)
from backend.reporting.chat import (
    report_filename as _report_filename,
)
from backend.reporting.chat import (
    text as _text,
)

__all__ = [
    "_text",
    "_generate_message",
    "_replace_generate_message",
    "_report_filename",
    "_download_message",
    "_normalize_text",
    "_match_type_label",
    "_condition_match",
    "_fragments_message",
    "_append",
    "_ask",
    "_recommendation_text",
    "generate_label",
]
