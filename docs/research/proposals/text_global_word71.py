"""Staged linked entry color-word receipts and dynamic Swirl layer3 contributors."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.game.rules_state import ColorWordEntry71, TextChange71
from app.rules.text_change_instructions71 import COLORS

if TYPE_CHECKING:
    from app.game.rules_state import ContinuousEffect
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import AbilityText, CardInfo, Characteristics
    from app.rules.plan import Plan

ENTRY = 'As this enchantment enters, choose a color word.'
GLOBAL = 'All instances of color words in the text of spells and permanents are changed to the chosen color word.'
MARKER = 'text_global_word71'


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts, statics

    if ability.text == ENTRY:
        native = scripts.define(replace(ability, text='As this enchantment enters, choose a color.'), ch)
        if native is not None:
            return {**native, 'effects': [{'do': 'choose_value', 'who': 'you', 'what': 'color word', 'remember': True}]}
    if ability.kind == 'static' and ability.text == GLOBAL:
        return statics._definition('self', None, [], rules=[MARKER])
    return None


def acquisition(state: GameState, oid: str) -> ContinuousEffect | None:
    if state.rules is None:
        return None
    return max((e for e in state.rules.effects if e.layer == '1' and e.copy_recipe is not None and oid in e.affected),
               key=lambda e: e.timestamp, default=None)


def record_entry(plan: Plan, card_id: str, choices: dict[str, str] | None) -> None:
    if choices is None or choices.get('color word') not in COLORS:
        return
    card = plan.state.cards.get(card_id)
    if card is None or not card.zone.endswith(':battlefield'):
        return
    from app.rules import layers, scripts

    base = layers.copiable(plan.state, card, plan.info)
    definitions = scripts.definitions(base).values()
    if not any(MARKER in d.get('rules', []) for d in definitions):
        return
    oid = plan.oid(card)
    copy = acquisition(plan.state, oid)
    scope = copy.id if copy is not None else None
    alive = {plan.oid(c) for c in plan.state.cards.values() if c.zone.endswith((':battlefield', ':phased'))}
    plan.rules.color_words71 = {key: entries for key, entries in plan.rules.color_words71.items() if key in alive}
    receipt = ColorWordEntry71.model_validate({'card': card_id, 'acquisition': scope, 'word': choices['color word']})
    previous = plan.rules.color_words71.get(oid, [])
    plan.rules.color_words71[oid] = [r for r in previous if r.acquisition != scope] + [receipt]


def global_changes(state: GameState, card: CardInstance, info: CardInfo | None) -> list[tuple[tuple[float, int, int], TextChange71]]:
    if info is None or state.rules is None or not state.rules.color_words71 or not (card.zone.endswith(':battlefield') or card.zone == 'stack'):
        return []
    from app.rules import layers, scripts
    from app.rules.plan import live_players

    live = live_players(state)
    result = []
    for oid, receipts in state.rules.color_words71.items():
        source = state.cards.get(receipts[0].card) if receipts else None
        if source is None or not source.zone.endswith(':battlefield') or source.face_down or source.owner not in live \
                or source.controller not in live or state.rules.object_id(source.id) != oid or state.rules.card_mode(source.id) == 'manual':
            continue
        copy = acquisition(state, oid)
        scope = copy.id if copy is not None else None
        receipt = next((r for r in receipts if r.card == source.id and r.acquisition == scope), None)
        if receipt is None or receipt.word not in COLORS or source.choices.get('Chosen color word') != receipt.word:
            continue
        definitions = scripts.definitions(layers.copiable(state, source, info)).values()
        if not any(MARKER in d.get('rules', []) for d in definitions):
            continue
        key = (float(layers.timestamp(state, source.id)), 0, 0)
        if copy is not None:
            key = max(key, (float(copy.object_seq), 1, copy.timestamp))
        result.append((key, TextChange71(category='color', old=receipt.word, new=receipt.word, all_colors=True)))
    return result
