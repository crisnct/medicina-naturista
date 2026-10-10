"""Redact obsolete owner query strings even if a saved browser link is revisited."""

import logging
import re


class OwnerAccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                re.sub(r"(/owner)\?[^ ]*", r"\1?[redacted]", value)
                if isinstance(value, str)
                else value
                for value in record.args
            )
        record.msg = re.sub(r"(/owner)\?[^ ]*", r"\1?[redacted]", str(record.msg))
        return True
