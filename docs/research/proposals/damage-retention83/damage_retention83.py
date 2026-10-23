"""Current printed or granted static rules control native cleanup damage removal."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.plan import Plan

RULE = 'damage_retained_cleanup'
_PATTERN = re.compile(r"^Damage isn't removed from (?P<what>~|this creature|it|creatures|creatures your opponents control) during cleanup steps\.$")


def static(text: str) -> dict[str, Any] | None:
    from app.rules import statics

    if text in ("As long as this creature is on the battlefield, damage isn't removed from it during cleanup steps.",
                "As long as ~ is on the battlefield, damage isn't removed from it during cleanup steps."):
        text = "Damage isn't removed from ~ during cleanup steps."
    m = _PATTERN.fullmatch(text)
    if m is None:
        return None
    subject = '~' if m['what'] in ('~', 'this creature', 'it') else m['what'].capitalize()
    native = statics.parse(subject + " can't block.")
    return {**native, 'rules': [RULE]} if native is not None else None


def cleanup(plan: Plan) -> None:
    # 514.2: read the rules immediately before simultaneous removal/expiry. Literal
    # ability grants lasting until end of turn still apply to this cleanup action.
    damaged = [c for c in plan.state.cards.values() if c.damage]
    if not damaged:
        return
    clear = [c.id for c in damaged if not c.zone.endswith(':battlefield') or RULE not in plan.ch(c).imposed]
    if len(clear) == len(damaged):
        plan.do({'type': 'cleanup', 'what': ['damage']}, actor=plan.active)
        return
    for start in range(0, len(clear), 250):
        plan.do({'type': 'cleanup', 'what': ['damage'], 'card_ids': clear[start:start + 250]}, actor=plan.active)


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == 'When ~ enters the battlefield, it deals 4 damage to any target.':
        return scripts.define(replace(ability, text='When this enchantment enters, ~ deals 4 damage to any target.'), ch)
    saga = ('I — ~ deals 4 damage to each creature and each planeswalker. '
            '~ gains "Damage isn\'t removed from creatures during cleanup steps."')
    if text == saga:
        native = scripts.define(replace(ability, text='I — ~ deals 4 damage to each creature and each planeswalker.'), ch)
        quote = "Damage isn't removed from creatures during cleanup steps."
        return {**native, 'effects': [*native['effects'], {'do': 'grant', 'who': 'self', 'keywords': [],
                                                         'abilities': [quote], 'duration': 'permanent'}]} if native is not None else None
    return None


def condition(text: str) -> dict[str, Any] | None:
    return {'damaged_creatures83': 3} if text.strip().rstrip('.').casefold() == 'three or more creatures are damaged' else None


def holds(plan: Plan, cond: dict[str, Any]) -> bool:
    return sum(1 for card in plan.state.cards.values() if card.zone.endswith(':battlefield')
               and card.damage > 0 and 'Creature' in plan.ch(card).types) >= cond['damaged_creatures83']


def resolved_static(definition: dict[str, Any]) -> bool:
    return definition.get("rules") == [RULE]
