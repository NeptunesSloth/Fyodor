"""Spent-unit linked exile and an unbounded native free-cast resolution packet."""
from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules import mana as M
    from app.rules.plan import Plan


def parse_mana(text: str, identity: tuple[str, ...], name: str) -> M.ManaAbility | None:
    from app.rules import mana as M
    from app.rules import scripts, selectors

    expected = ("{T}: Add {U}. When you spend this mana to cast an instant or sorcery spell with mana value 3 or less, "
                "you may exile that spell instead of putting it into its owner's graveyard as it resolves.")
    if scripts.self_text(text, name) != expected:
        return None
    base = M.parse_mana_ability('{T}: Add {U}.', identity, card_name=name)
    rider = {'kind': 'trigger', 'spell': selectors.Selector(zones=('stack',), types=('Instant', 'Sorcery'),
        compare=(('mv', '<=', 3),)).key(), 'effects': [{'do': 'exile_on_resolve', 'who': 'event_spell',
            'own': False, 'bind': None, 'then': [], 'optional': True, 'link': True}]}
    return replace(base, on_spend=(json.dumps(rider, sort_keys=True),)) if base is not None else None


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == 'activated' and text == ('{3}{U}{U}, {T}: You may cast any number of spells from among cards exiled with ~ '
        'without paying their mana costs. Activate only as a sorcery.'):
        base = scripts.define(replace(ability, text='{3}{U}{U}, {T}: Draw a card. Activate only as a sorcery.'), ch)
        if base is not None:
            return {**base, 'effects': [{'do': 'foundry_linked_packet'}, {'do': 'free_cast', 'zone': 'that',
                'who': 'ref:foundry_pool', 'exact_refs': True, 'optional': True, 'all': True}]}
    return None


def linked_packet(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, exiled_with

    context.bind_objects(plan, ctx, 'foundry_pool', exiled_with.cards(plan, ctx))
    return True


PRIMITIVES = {'foundry_linked_packet': linked_packet}
