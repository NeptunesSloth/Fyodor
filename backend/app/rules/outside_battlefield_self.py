"""CR 113.6c: a self characteristic ability explicitly inactive on the battlefield."""
from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.rules.creature_types import CREATURE_TYPES

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics

_FORM = re.compile(
    r"As long as ~ isn't on the battlefield, it's a (?P<p>\d+)/(?P<t>\d+) "
    r"(?P<sub>[A-Z][a-z]+) creature in addition to its other types\.")


def parse(text: str, name: str = '~') -> dict[str, Any] | None:
    # Only the leading subject is normalized: names in another selector are not self.
    for subject in (name, name.split(',')[0].strip()):
        prefix = f"As long as {subject} isn't on the battlefield, "
        if text.startswith(prefix):
            text = "As long as ~ isn't on the battlefield, " + text[len(prefix):]
            break
    m = _FORM.fullmatch(text)
    if m is None or m['sub'] not in CREATURE_TYPES:
        return None
    return {'kind': 'static', 'static': 'outside_battlefield_self', 'effects': [],
            'layer4': {'add_types': ['Creature'], 'add_subtypes': [m['sub']]},
            'base': [int(m['p']), int(m['t'])]}


def parts(ch: Characteristics) -> list[dict[str, Any]]:
    return [d for a in ch.abilities if a.kind == 'static'
            and (d := parse(a.text, ch.name)) is not None]


def apply(ch: Characteristics) -> Characteristics:
    """The self effects outside the battlefield, including prospective spells."""
    for d in parts(ch):
        ch = replace(ch, types=ch.types | frozenset(d['layer4']['add_types']),
                     subtypes=ch.subtypes | frozenset(d['layer4']['add_subtypes']),
                     pt=tuple(d['base']), base_pt=tuple(d['base']))
    return ch
