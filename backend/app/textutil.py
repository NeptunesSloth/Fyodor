"""Sanitizing helpers for user-entered text (names, notes, chat)."""

from __future__ import annotations

import re
import unicodedata

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩]")


def clean_text(value: str, max_length: int, *, multiline: bool = False) -> str:
    """Strip control / bidi-override characters, normalize, collapse whitespace, truncate.

    The frontend renders all user text as text (never HTML), so this is defence in depth
    and keeps logs and saves tidy.
    """
    text = unicodedata.normalize("NFC", value)
    text = _CONTROL.sub("", text)
    if multiline:
        text = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
    else:
        text = re.sub(r"\s+", " ", text).strip()
    return text[:max_length]
