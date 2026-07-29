from __future__ import annotations

import logging
import re


class SecretRedactionFilter(logging.Filter):
    _patterns = (
        re.compile(r"(?i)(bearer\s+)[^\s,]+"),
        re.compile(r"(?i)(freelancer-oauth-v1\s*[:=]\s*)[^\s,]+"),
        re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,]+"),
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in self._patterns:
            message = pattern.sub(r"\1[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(SecretRedactionFilter())
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[handler],
        force=True,
    )

