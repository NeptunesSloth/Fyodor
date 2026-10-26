"""Target-dependent activation prices are read from actual announced targets."""
from __future__ import annotations

from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import permissions, scripts

    text = scripts.self_text(ability.text, ch.name)
    common: dict[str, Any] = {'kind': 'static', 'static': 'ability_cost_modifier', 'filter': None,
              'who': 'any', 'floor': False, 'effects': []}
    if text == "~'s equip ability costs {2} less to activate if it targets a colorless creature.":
        return {**common, 'delta': -2, 'source_only': True, 'equip': True, 'target_rule62': 'colorless'}
    if text == 'Equip abilities you activate that target enchanted creature cost {3} less to activate.':
        return {**common, 'who': 'you', 'delta': -3, 'equip': True, 'target_rule62': 'enchanted'}
    if text == 'Abilities your opponents activate that target a Merfolk you control cost {2} more to activate.':
        return {**common, 'delta': 2, 'target_rule62': 'opponent_merfolk'}
    if text == 'Aura spells you cast that target enchanted creature cost {3} less to cast.':
        return {'kind': 'static', 'static': 'cost_modifier', 'caster': 'you', 'filter': permissions.spell_filter('Aura'),
                'delta': -3, 'target_rule62': 'enchanted', 'effects': []}
    return None


def own_change(sentence: str) -> dict[str, Any] | None:
    if sentence == 'This ability costs {1} less to activate if it targets a creature with power 3 or less.':
        return {'dir': -1, 'n': 1, 'own_target_rule62': 'small'}
    if sentence == 'This ability costs {2} less to activate if it targets two creatures you control.':  # (wave 110I) Wayta, Trainer Prodigy: 601.2f, read from the announced targets
        return {'dir': -1, 'n': 2, 'own_target_rule62': 'two_mine'}
    return None


def matches(view: Any, player: str, source: Any, rule: str, targets: tuple[str, ...]) -> bool:
    cards = [view.state.cards[cid] for cid in targets if cid in view.state.cards
             and view.state.cards[cid].zone.endswith(':battlefield')]
    if rule == 'enchanted':
        return source.attached_to is not None and any(c.id == source.attached_to for c in cards)
    if rule == 'two_mine':
        return sum(1 for c in cards if c.controller == player and 'Creature' in view.ch(c).types) >= 2
    for card in cards:
        ch = view.ch(card)
        if rule == 'small' and 'Creature' in ch.types and ch.pt is not None and ch.pt[0] <= 3:
            return True
        if rule == 'colorless' and 'Creature' in ch.types and not ch.colors:
            return True
        if rule == 'opponent_merfolk' and player != source.controller and card.controller == source.controller and 'Merfolk' in ch.subtypes:
            return True
    return False


def available(state: Any, player: str, source: Any, rule: str, targets: tuple[str, ...], info: Any, *, preview: bool = False) -> bool:
    from app.rules.plan import Plan

    view = Plan.view(state, player, info)
    if preview:
        if rule == 'opponent_merfolk':
            return False  # Increases wait for the actual announcement.
        targets = tuple(state.cards)
    return matches(view, player, source, rule, targets)
