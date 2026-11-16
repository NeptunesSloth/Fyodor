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


def record_entry(plan: Plan, card_id: str, controller: str, choices: dict[str, str] | None) -> None:
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
    receipt = ColorWordEntry71.model_validate({'card': card_id, 'acquisition': scope, 'word': choices['color word'], 'provenance': 'native_entry', 'chosen_by': controller})
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


def prospective(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None) -> Characteristics:
    """601.2a/601.3: read the prospective spell's text before target/cost choices."""
    if state.planechase is not None and "Sorcery" in ch.types:  # -- planechase more 4 (wave G2) -- Deceptive Divination: the sorcery spell it would be
        from app.rules import planar_more4

        ch = planar_more4.prospective(state, card, ch, info)
    if ch.is_land or state.rules is None or not state.rules.color_words71:
        return ch
    from app.rules import text_word_changes71

    incoming = card.model_copy(update={'zone': 'stack'})
    for _, change in sorted(global_changes(state, incoming, info), key=lambda item: item[0]):
        ch = text_word_changes71.apply(ch, change, getattr(info, 'name_at', None))
    return ch


def record_acquisition(plan: Plan, affected: list[str], scope: str) -> None:
    """Gaining an as-enters ability on the battlefield makes no choice (607.2d)."""
    from app.game.rules_state import ColorWordEntry71
    from app.rules import layers, scripts

    for card in plan.state.cards.values():
        oid = plan.oid(card)
        if oid not in affected or not card.zone.endswith(':battlefield'):
            continue
        if not any(MARKER in d.get('rules', []) for d in scripts.definitions(layers.copiable(plan.state, card, plan.info)).values()):
            continue
        previous = plan.rules.color_words71.get(oid, [])
        plan.rules.color_words71[oid] = [r for r in previous if r.acquisition != scope] + [ColorWordEntry71(card=card.id, acquisition=scope, word=None, provenance='native_no_choice')]


def missing_sources(plan: Plan) -> list[CardInstance]:
    """An old save's public choice string cannot prove an acquired ability's choice."""
    from app.rules import layers, scripts

    result = []
    for card in plan.state.cards.values():
        if not card.zone.endswith(':battlefield') or card.face_down or plan.manual(card):
            continue
        if not any(MARKER in d.get('rules', []) for d in scripts.definitions(layers.copiable(plan.state, card, plan.info)).values()):
            continue
        oid = plan.oid(card)
        copy = acquisition(plan.state, oid)
        scope = copy.id if copy is not None else None
        receipt = next((r for r in plan.rules.color_words71.get(oid, []) if r.card == card.id and r.acquisition == scope), None)
        if receipt is None or (receipt.word is not None and card.choices.get('Chosen color word') != receipt.word):
            result.append(card)
    return result


def recover(plan: Plan, intent: Any) -> bool:
    from app.game.errors import ActionError
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    if plan.rules.decision is not None and (plan.rules.decision.resume or {}).get('step') == 'restore_global_word71':
        return False
    missing = missing_sources(plan)
    if not missing:
        return False
    if plan.rules.decision is not None:
        raise ActionError('A saved Swirl the Mists source lacks its original color-word receipt. Restore that source before continuing this saved decision, or set it to manual automation.')
    source = missing[0]
    decide(plan, player=source.controller, kind='choose_one',
           prompt='Manual recovery: the original color word and chooser for this Swirl the Mists ability are not recorded. Confirm the original public word with the table, or choose No word if none was chosen. This does not make a new as-enters choice.',
           options=[*[DecisionOption(id=w, label=f'Restore original {w} word') for w in COLORS], DecisionOption(id='none', label='No word was chosen')],
           resume={'step': 'restore_global_word71', 'source': source.id, 'object': plan.oid(source),
                   'actor': plan.actor, 'intent': intent.model_dump(mode='json'),
                   'priority': plan.rules.priority}, source=source)
    return True


def resume_restore(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game import actions as A
    from app.game.errors import ActionError
    from app.game.rules_state import ColorWordEntry71

    if len(chosen) != 1 or chosen[0] not in (*COLORS, 'none'):
        raise ActionError('Restore one original color word, or No word')
    source = plan.state.cards.get(d.resume['source'])
    if source is None or not source.zone.endswith(':battlefield') or plan.oid(source) != d.resume['object']:
        plan.note('The original text-changing source left; its old choice was not assigned to a new object')
    else:
        word = None if chosen[0] == 'none' else chosen[0]
        copy = acquisition(plan.state, plan.oid(source))
        scope = copy.id if copy is not None else None
        previous = plan.rules.color_words71.get(plan.oid(source), [])
        plan.rules.color_words71[plan.oid(source)] = [r for r in previous if r.acquisition != scope] + [ColorWordEntry71.model_validate({'card': source.id, 'acquisition': scope, 'word': word, 'provenance': 'manual_restore', 'restored_by': d.player})]
        plan.do({'type': 'set_choice', 'card_id': source.id, 'key': 'Chosen color word', 'value': word or 'No word'}, actor=source.controller)
    old_actor, plan.actor = plan.actor, d.resume['actor']
    try:
        intent = A.parse_action(d.resume['intent'])
        plan.rules.priority = d.resume.get('priority')
        if recover(plan, intent):
            return
        from app.game.rules_state import DecisionOption
        from app.rules.plan import decide

        if plan.actor not in plan.live():
            plan.note('The earlier action was canceled because its player left the game')
            return
        decide(plan, player=plan.actor, kind='choose_one',
               prompt='Continue your previously requested action, or cancel it and choose again?',
               options=[DecisionOption(id='continue', label='Continue previous action'),
                        DecisionOption(id='cancel', label='Cancel previous action')],
               resume={'step': 'restore_global_continue71', 'actor': plan.actor,
                       'intent': intent.model_dump(mode='json'), 'priority': plan.rules.priority}, source=source)
    finally:
        plan.actor = old_actor



def resume_continue(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game import actions as A
    from app.game.errors import ActionError
    from app.rules import engine

    plan.rules.priority = d.resume.get('priority')
    if chosen == ['cancel']:
        plan.note('Canceled the previous action after restoring the original color word')
        return
    if chosen != ['continue']:
        raise ActionError('Continue or cancel the previous action')
    old_actor, plan.actor = plan.actor, d.resume['actor']
    try:
        intent = A.parse_action(d.resume['intent'])
        if intent.type in engine.ACTION_INTENTS or intent.type == 'pass_priority':
            engine.miracle.clear(plan)
        if intent.type in engine.ACTION_INTENTS:
            plan.rules.actions += 1
            plan.rules.last_actor = plan.actor
        engine.INTENTS[intent.type](plan, intent)
        engine.remember_intent(plan, intent)
    finally:
        plan.actor = old_actor
