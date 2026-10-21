"""Frozen provenance for mana-cost templates granted by actual abilities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class GrantedManaCost:
    keyword: Literal["foretell", "madness", "encore", "embalm", "plot"]
    source_object: str
    generic_reduction: int = 0

    def __post_init__(self) -> None:
        if not self.source_object or self.generic_reduction < 0:
            raise ValueError("A granted cost requires actual source provenance and a nonnegative reduction")


@dataclass(frozen=True)
class ForetellCostReceipt:
    object_id: str
    template: GrantedManaCost

    def __post_init__(self) -> None:
        if not self.object_id or self.template.keyword != "foretell":
            raise ValueError("A foretell receipt requires its actual foretold object and foretell template")
