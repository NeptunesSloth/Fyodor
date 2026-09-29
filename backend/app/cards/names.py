"""Card-name normalization shared by the importer, search and the deck parser."""

from __future__ import annotations

import re
import unicodedata

_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "Æ": "Ae", "æ": "ae"})
_SPACES = re.compile(r"\s+")
_SPLIT_SEP = re.compile(r"\s*/{1,2}\s*")


def normalize_name(name: str) -> str:
    """Lowercase, strip accents, unify quotes/dashes/whitespace and split-card separators.

    ``"Fire/Ice"``, ``"Fire // Ice"`` and ``"fire  //  ice"`` all normalize to ``"fire // ice"``.
    """
    text = name.translate(_QUOTES)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _SPACES.sub(" ", text.strip().lower())
    if "/" in text:
        text = " // ".join(part for part in _SPLIT_SEP.split(text) if part)
    return text
