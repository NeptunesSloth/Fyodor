"""Graveyard-source return instructions preserve native new-object and event bindings."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.rules_state import Capture
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan


def parse(body: str, it: str | None) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    body = body[:1].upper() + body[1:]
    if body == 'You may return this card from your graveyard to the battlefield, then attach it to that creature.' and it == 'event':
        return ([{'do': 'return_card', 'who': 'self_gy', 'to': 'battlefield', 'under': 'you', 'as': 'returned57'},
                 {'do': 'attach_to', 'src': 'ref:returned57', 'who': 'event'}], None, True)
    if body == 'You may return this card from your graveyard to the battlefield face up or face down.':
        return ([{'do': 'pick_one', 'options': [
            {'label': 'Return face up', 'effects': [{'do': 'return_card', 'who': 'self_gy', 'to': 'battlefield', 'under': 'you'}]},
            {'label': 'Return face down', 'effects': [{'do': 'return_card', 'who': 'self_gy', 'to': 'battlefield', 'under': 'you', 'face_down': True}]},
        ]}], None, True)
    if body == 'Create a 2/2 colorless Wizard Soldier creature token named Cadet, then put a +1/+1 counter on each other Wizard token you control.':
        first = scripts.parse_effects('Create a 2/2 colorless Wizard Soldier creature token named Cadet.')
        if first is None or len(first[0]) != 1:
            return None
        first[0][0]['as'] = 'cadet57'
        return ([*first[0], {'do': 'add_counters', 'who': 'controlled:you|sel:{"subtypes":["Wizard"],"token":true}',
                            'kind': '+1/+1', 'n': 1, 'exclude': 'cadet57'}], None, False)
    return None


def event(text: str) -> dict[str, Any] | None:
    from app.rules import events, selectors

    if text == 'you cast your commander':
        cond = events.parse_condition('you cast a commander spell')
        if cond is None:
            return None
        return {**cond, "spell": replace(selectors.from_key(cond["spell"]), owner="you").key()}
    if text == 'an opponent is dealt damage by a red instant or sorcery spell you control or by a red planeswalker you control':
        conditions = [events.parse_condition(f'{source} deals damage to an opponent')
                      for source in ['a red instant or sorcery spell you control', 'a red planeswalker you control']]
        if all(condition is not None for condition in conditions):
            return {'event': 'either', 'conds': conditions}
    return None


def condition(text: str) -> dict[str, Any] | None:
    if text == 'its madness cost was paid':
        return {'object': 'self', 'cast': {'alt': 'madness'}}
    if text == 'an opponent was dealt noncombat damage last turn':
        return {'history': 'damage', 'who': 'opponent', 'combat': False, 'last': True, 'n': 1}
    return None


def freeze_attachments(plan: Plan, before: Capture) -> None:
    from app.game.rules_state import AttachedObjectFact

    for cid in before.types:
        snap = before.snaps.get(cid)
        if snap is None:
            continue
        if not snap.attached_objects_known:
            continue
        snap.attachments_before = []
        for attached_id, attached_oid in snap.attached_objects.items():
            card = plan.state.cards.get(attached_id)
            if card is None or plan.oid(card) != attached_oid or not card.zone.endswith(':battlefield') or not plan.in_game(card):
                continue
            ch = plan.ch(card)
            snap.attachments_before.append(AttachedObjectFact(object_id=attached_oid, controller=card.controller,
                                                              types=sorted(ch.types), subtypes=sorted(ch.subtypes)))


def enchanted_before(controller: str, info: dict[str, Any]) -> bool:
    snap = info.get('snap')
    return bool(snap is not None and snap.attachments_before is not None and any(
        fact.controller == controller and 'Aura' in fact.subtypes for fact in snap.attachments_before))


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import events, scripts

    text = scripts.self_text(ability.text, ch.name)
    prefix = 'Whenever a creature dies, if an Aura you controlled was attached to it, '
    if ability.kind != 'triggered' or not text.startswith(prefix):
        return None
    parsed = scripts.parse_effects(text[len(prefix):], 'event')
    cond = events.parse_condition('a creature dies')
    if parsed is None or cond is None:
        return None
    return {'kind': 'triggered', 'trigger': 'event', 'cond': {**cond, 'aura_controller57': True},
            'effects': parsed[0], 'optional': parsed[2], **scripts.target_fields(parsed[1])}
