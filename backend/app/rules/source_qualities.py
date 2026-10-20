"""Bound source mana values, names, and linked types for protection predicates."""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from app.rules.characteristics import Characteristics

MV_SET = 'Protection from each mana value among artifacts you control'
MV_OTHER = 'Protection from each mana value other than the chosen number'
MV_PARITY = 'Protection from each mana value of the chosen quality'
LINK_TYPES = "Protection from each of the exiled card's card types"
OWN_HEX = 'Hexproof from each of its colors'
MARKERS = {MV_SET, MV_OTHER, MV_PARITY, LINK_TYPES, OWN_HEX}


def source(ch: Characteristics, x: int | None) -> Characteristics:
    """An immutable quality view; global/base mana_value remains unchanged."""
    return replace(ch, mana_value=ch.mana_value + (x or 0) * ch.mana_cost.count('{X}'))


def name_quality(name: str) -> str:
    return 'card name ' + name.encode().hex()


def predicate(word: str) -> Any:
    if (m := re.fullmatch(r'mana value (\d+(?:\.\d+)?)', word)) is not None:
        return lambda ch: ch.mana_value == float(m[1])
    if (m := re.fullmatch(r'mana value other than (\d+)', word)) is not None:
        return lambda ch: ch.mana_value != int(m[1])
    if (m := re.fullmatch(r'(odd|even) mana value', word)) is not None:
        return lambda ch: ch.mana_value % 2 == (1 if m[1] == 'odd' else 0)
    # Encoded names retain case: protection._one must supply the original text.
    if word.startswith('card name '):
        from app.rules import card_names

        try:
            raw = word[len('card name '):]
            name = bytes.fromhex(raw).decode()
        except (ValueError, UnicodeError):
            return None
        return lambda ch: card_names.has_name(ch, name)
    return None


def lines(plan: Any, text: str, source_id: str, recipient: Characteristics) -> list[str] | None:
    if text not in MARKERS:
        return None
    from app.rules import exiled_with, protection

    owner = plan.state.cards.get(source_id)
    if owner is None:
        return []
    if text == OWN_HEX:
        from app.rules.derived_protection import WORDS

        return [f'Hexproof from {word}' for color, word in WORDS.items() if color in recipient.colors]
    if text == MV_SET:
        values = {plan.ch(c).mana_value for c in plan.state.cards.values() if c.controller == owner.controller
                  and c.zone.endswith(':battlefield') and plan.in_game(c) and 'Artifact' in plan.ch(c).types}
        return [f'Protection from mana value {int(n) if float(n).is_integer() else n}' for n in sorted(values)]
    if text == MV_OTHER:
        n = owner.choices.get('Chosen number', '')
        return [f'Protection from mana value other than {n}'] if n.isdigit() else []
    if text == MV_PARITY:
        parity = owner.choices.get('Chosen quality', '').lower()
        return [f'Protection from {parity} mana value'] if parity in ('odd', 'even') else []
    ctx = {'controller': owner.controller, 'source_object': plan.oid(owner), 'source_card': owner.id}
    types = {kind for cid in exiled_with.cards(plan, ctx) for kind in plan.ch(plan.state.cards[cid]).types}
    return [f'Protection from {plural}' for plural, kind in protection.CARD_TYPES.items() if kind in types]


def candidate_x_values(plan: Any, ch: Characteristics) -> list[int]:
    """Represent every MV-protection interval/parity class without a numeric scan.

    Only source MV predicates vary with this announced X. Their boundaries are
    explicit numbers in the live protection lines; parity needs representatives0/1.
    """
    import math

    from app.game.actions import CastSpell

    count = ch.mana_cost.count('{X}')
    if not count:
        return [0]
    ceiling = next(int(m.le) for m in CastSpell.model_fields['x_value'].metadata if getattr(m, 'le', None) is not None)
    candidates = {0, 1}
    for card in plan.state.cards.values():
        if not card.zone.endswith(':battlefield') or not plan.in_game(card):
            continue
        for ability in plan.ch(card).abilities:
            if 'protection from' not in ability.text.lower() or 'mana value' not in ability.text.lower():
                continue
            for n in re.findall(r'\d+(?:\.\d+)?', ability.text):
                boundary = math.floor((float(n) - ch.mana_value) / count)
                candidates.update((boundary - 1, boundary, boundary + 1))
    return sorted(x for x in candidates if 0 <= x <= ceiling)
