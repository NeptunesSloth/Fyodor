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
_NAMED_START = re.compile(r'\bnamed\s+', re.IGNORECASE)
_SYMBOL = re.compile(r'\{[^}]*\}')


def protected_spans(text: str, names: tuple[str, ...], catalog_names: tuple[str, ...]) -> list[tuple[int, int]]:
    out = [m.span() for m in _SYMBOL.finditer(text)]
    for name in names:
        if name:
            out.extend(m.span() for m in re.finditer(re.escape(name), text))
    # The catalog bounds each specific reference: card names containing "and"
    # or commas remain whole. A token type phrase is never guessed to be a name.
    ordered = sorted(set(catalog_names), key=len, reverse=True)
    for match in _NAMED_START.finditer(text):
        start = match.end()
        while True:
            found = next((n for n in ordered if text[start:start + len(n)].casefold() == n.casefold()
                          and (start + len(n) == len(text) or not text[start + len(n)].isalnum())), None)
            if found is None:
                break
            end = start + len(found)
            out.append((start, end))
            separator = re.match(r'(?:,\s*(?:(?:and|or)\s+)?|\s+(?:and|or)\s+)', text[end:])
            if separator is None:
                break
            start = end + separator.end()
    return out


def plural(word: str) -> str:
    irregular = {'Plains': 'Plains', 'Elf': 'Elves', 'Dwarf': 'Dwarves', 'Wolf': 'Wolves',
                 'Mouse': 'Mice', 'Ox': 'Oxen', 'Child': 'Children', 'Fungus': 'Fungi',
                 'Cyclops': 'Cyclopes', 'Fish': 'Fish', 'Sheep': 'Sheep', 'Merfolk': 'Merfolk',
                 'Treefolk': 'Treefolk', 'Moonfolk': 'Moonfolk', 'Kithkin': 'Kithkin',
                 'Eldrazi': 'Eldrazi', 'Myr': 'Myr', 'Kor': 'Kor', 'Dauthi': 'Dauthi',
                 'Soltari': 'Soltari', 'Aurochs': 'Aurochs'}
    if word in irregular:
        return irregular[word]
    if word.endswith(('s', 'x', 'ch', 'sh')):
        return word + 'es'
    if word.endswith('y') and word[-2].lower() not in 'aeiou':
        return word[:-1] + 'ies'
    return word + 's'


def word_text(text: str, change: TextChange71, *, names: tuple[str, ...], catalog_names: tuple[str, ...] = ()) -> str:
    """Replace category words, including noncolor and landwalk/typecycling forms."""
    old = change.old
    words = {old: change.new}
    if change.category != 'color':
        # Invariant words retain the selected canonical type word. They must
        # not overwrite singular replacement with a destination plural.
        if plural(old) != old:
            words[plural(old)] = plural(change.new)
        words[old.lower() + 'walk'] = change.new.lower() + 'walk'
        words[old.lower() + 'cycling'] = change.new.lower() + 'cycling'
    else:
        words['non' + old] = 'non' + change.new
    replacements = {key.lower(): value for key, value in words.items()}
    pattern = re.compile(r'(?<![A-Za-z])(?:' + '|'.join(re.escape(w) for w in sorted(words, key=len, reverse=True)) +
                         r')(?![A-Za-z])', re.IGNORECASE)
    spans = protected_spans(text, names, catalog_names)

    def changed(m: re.Match[str]) -> str:
        if any(a < m.end() and m.start() < b for a, b in spans):
            return m.group()
        new = replacements[m.group().lower()]
        if m.group().islower():
            new = new.lower()
        elif m.group().isupper():
            new = new.upper()
        elif m.group()[0].isupper():
            new = new[0].upper() + new[1:]
        return new

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
    if change.category != 'color' and change.old in subtypes and 'changeling' not in ch.keywords:
        subtypes = (subtypes - {change.old}) | {change.new}
    if 'Land' in ch.types:
        abilities = list(with_intrinsic_mana(abilities, subtypes))
    return replace(ch, oracle_text=word_text(ch.oracle_text, change, names=names),
                   abilities=tuple(abilities), subtypes=frozenset(subtypes))
