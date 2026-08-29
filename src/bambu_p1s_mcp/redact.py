from __future__ import annotations

import re

_SECRET_KEYS = re.compile(
    r"(access[_-]?code|password|token|mqtt_password)",
    re.IGNORECASE,
)
_CODE_LIKE = re.compile(r"\b[0-9A-Za-z]{8}\b")


def redact(text: str, access_code: str | None = None) -> str:
    out = text
    if access_code:
        out = out.replace(access_code, "***")
    return out


def public_error(exc: BaseException, access_code: str | None = None) -> str:
    return redact(f"{type(exc).__name__}: {exc}", access_code)
