"""Mana costs to declare a particular creature attacking or blocking, regardless of defender."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import mana as M

if TYPE_CHECKING:
    from app.rules.plan import Plan

_KIND = 'creature_combat_cost'
_STATIC = re.compile(r"^(?P<subject>~|this creature|enchanted creature) can't (?P<mode>attack or block|attack) unless (?:you pay|its controller pays) (?P<mana>(?:\{[^}]+\})+)(?: for each (?P<count>.+?))?\.$", re.IGNORECASE)


def parse(text: str) -> dict[str, Any] | None:
    from app.rules import values

    if text == "Each creature with one or more counters on it can't attack you or planeswalkers you control unless its controller pays {X}, where X is the number of counters on that creature.":
        return {'kind': 'static', 'static': _KIND, 'who': 'global', 'mode': 'attack', 'per_counter': True, 'effects': []}
    if text == "Creatures can't attack planeswalkers you control unless their controller pays {1} for each creature they control that's attacking a planeswalker you control.":
        return {'kind': 'static', 'static': _KIND, 'who': 'global', 'mode': 'attack', 'effects': []}
    found = _STATIC.fullmatch(text.strip())
    if found is None:
        return None
    cost = M.parse_cost(found['mana'])
    if cost.x or cost.unsupported:
        return None
    value: Any = 1
    if found['count']:
        phrase = found['count'].replace('counter on it', 'counters on this creature')
        value = values.parse_count(phrase)
        if value is None:
            return None
    return {'kind': 'static', 'static': _KIND, 'who': 'attached' if found['subject'].lower() == 'enchanted creature' else 'self',
            'mana': found['mana'], 'n': value, 'mode': found['mode'].lower(), 'effects': []}


def total(plan: Plan, creatures: list[str], *, mode: str = 'attack', defenders: dict[str, str] | None = None, destination_only: bool = False) -> M.ManaCost:
    """Read each real static ability once per declared creature, after ability granting/removal."""
    from app.rules import scripts, values

    selected = set(creatures)
    generic = 0
    colored: list[str] = []
    hybrid: list[tuple[str, ...]] = []
    phyrexian: list[str] = []
    for source in plan.state.cards.values():
        if not source.zone.endswith(':battlefield') or not plan.in_game(source):
            continue
        for definition in scripts.definitions(plan.ch(source)).values():
            if definition.get('static') != _KIND:
                continue
            if mode not in definition.get('mode', 'attack or block'):
                continue
            if definition.get('who') == 'global':
                for cid in selected:
                    if applies(plan, definition, source.controller, cid, (defenders or {}).get(cid)):
                        generic += sum(plan.state.cards[cid].counters.values()) if definition.get('per_counter') else 1
                continue
            if destination_only:
                continue
            target = source.id if definition['who'] == 'self' else source.attached_to
            if target not in selected:
                continue
            context = {'controller': source.controller, 'source_card': source.id, 'source_object': plan.oid(source)}
            n = max(0, values.evaluate(plan, context, definition['n']))
            cost = M.parse_cost(definition['mana'])
            generic += cost.generic * n
            colored += list(cost.colored) * n
            hybrid += list(cost.hybrid) * n
            phyrexian += list(cost.phyrexian) * n
    for cid in (() if destination_only else selected):
        for rule in plan.ch(plan.state.cards[cid]).imposed:
            parts = rule.split(':')
            if len(parts) == 4 and parts[:2] == ['declaration_cost', mode]:
                generic += int(parts[2])
    return M.ManaCost(generic=generic, colored=tuple(colored), hybrid=tuple(hybrid), phyrexian=tuple(phyrexian))


def applies(plan: Plan, definition: dict[str, Any], controller: str, cid: str, defender: str | None) -> bool:
    if defender is None:
        return False
    card = plan.state.cards.get(defender)
    planeswalker = card is not None and card.controller == controller and 'Planeswalker' in plan.ch(card).types
    if definition.get('per_counter'):
        return (defender == controller or planeswalker) and sum(plan.state.cards[cid].counters.values()) > 0
    return planeswalker
