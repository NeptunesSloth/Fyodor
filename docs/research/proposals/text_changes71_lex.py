"""Staged CR612 word transformer; no engine hook or production admission."""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Literal

from pydantic import BaseModel, model_validator

from app.rules.characteristics import BASIC_LAND_MANA, Characteristics, with_intrinsic_mana
from app.rules.creature_types import CREATURE_TYPES
from app.rules.oracle import AbilityText, parse_abilities

Category = Literal['color', 'basic_land', 'creature']
COLORS = frozenset({'white', 'blue', 'black', 'red', 'green'})
LANDS = frozenset(BASIC_LAND_MANA)


class TextChange71(BaseModel):
    category: Category
    old: str
    new: str

    @model_validator(mode='after')
    def distinct_words(self) -> TextChange71:
        words = COLORS if self.category == 'color' else LANDS if self.category == 'basic_land' else CREATURE_TYPES
        if self.old not in words or self.new not in words or self.old == self.new:
            raise ValueError('A text change requires two distinct words in its category')
        return self


# A reference to a specific card is not a type/color word (612.2). Explicit native
# source names must be supplied; named-card clauses protect their full noun phrase.
_NAMED = re.compile(r'\bnamed\s+([^.;\n]+)', re.IGNORECASE)
_SYMBOL = re.compile(r'\{[^}]*\}')


def protected_spans(text: str, names: tuple[str, ...]) -> list[tuple[int, int]]:
    out = [m.span() for m in _SYMBOL.finditer(text)]
    for name in names:
        if name:
            out.extend(m.span() for m in re.finditer(re.escape(name), text))
    out.extend(m.span(1) for m in _NAMED.finditer(text))
    return out


def word_text(text: str, change: TextChange71, *, names: tuple[str, ...]) -> str:
    """Replace category words, including noncolor and landwalk/typecycling forms."""
    old = change.old
    suffix = r'(?:s|walk|cycling)?' if change.category != 'color' else ''
    prefix = 'non' if change.category == 'color' else ''
    pattern = re.compile(r'(?<![A-Za-z])(?P<prefix>' + prefix + r')?(?P<word>' + re.escape(old) +
                         r')(?P<suffix>' + suffix + r')(?![A-Za-z])', re.IGNORECASE)
    spans = protected_spans(text, names)

    def changed(m: re.Match[str]) -> str:
        if any(a < m.end() and m.start() < b for a, b in spans):
            return m.group()
        new = change.new
        if m['word'].islower():
            new = new.lower()
        elif m['word'].isupper():
            new = new.upper()
        return (m['prefix'] or '') + new + (m['suffix'] or '')

    return pattern.sub(changed, text)


def ability_text(ability: AbilityText, change: TextChange71, names: tuple[str, ...]) -> AbilityText:
    text = word_text(ability.text, change, names=names)
    if text == ability.text:
        return ability
    parsed = parse_abilities(text)
    # Text changes replace words, not native ability slots or grant provenance.
    matching = next((a for a in parsed if a.kind == ability.kind), None)
    return replace(ability, text=text,
                   cost=word_text(ability.cost, change, names=names) if ability.cost else None,
                   keywords=matching.keywords if matching is not None else ability.keywords)


def apply(ch: Characteristics, change: TextChange71) -> Characteristics:
    """Layer3 own/copied abilities only; call before native layer6 grants."""
    names = tuple(ch.name.split(' // '))
    abilities = [ability_text(a, change, names) for a in ch.abilities if not a.intrinsic]
    subtypes = ch.subtypes
    if change.category != 'color' and change.old in subtypes:
        subtypes = (subtypes - {change.old}) | {change.new}
    if 'Land' in ch.types:
        abilities = list(with_intrinsic_mana(abilities, subtypes))
    return replace(ch, oracle_text=word_text(ch.oracle_text, change, names=names),
                   abilities=tuple(abilities), subtypes=frozenset(subtypes))
