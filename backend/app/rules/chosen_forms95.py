"""Bounded copiable entry forms (208.2b), distinct from chosen-number CDAs."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

PREFIX = 'copiable chosen form: '
# The option labels are stable serialized choices, not card-name dispatch.
_FORMS: dict[str, dict[str, tuple[int, int, str | None, str | None]]] = {
    'As ~ enters, it becomes your choice of a 3/3 creature with flying, a 2/5 creature with vigilance, or a 0/12 creature with defender.': {
        '3/3 flying': (3, 3, 'Flying', None), '2/5 vigilance': (2, 5, 'Vigilance', None), '0/12 defender': (0, 12, 'Defender', None)},
    'As ~ enters, it becomes your choice of a 3/3 artifact creature, a 2/2 artifact creature with flying, or a 1/6 Wall artifact creature with defender in addition to its other types.': {
        '3/3': (3, 3, None, None), '2/2 flying': (2, 2, 'Flying', None), '1/6 Wall defender': (1, 6, 'Defender', 'Wall')},
    'As ~ enters, it becomes your choice of a 3/3 creature, a 2/2 creature with flying, or a 1/6 creature with defender.': {
        '3/3': (3, 3, None, None), '2/2 flying': (2, 2, 'Flying', None), '1/6 defender': (1, 6, 'Defender', None)},
    'As ~ enters or is turned face up, it becomes your choice of 5/1 or 1/5.': {
        '5/1': (5, 1, None, None), '1/5': (1, 5, None, None)},
}


def form(text: str) -> str | None:
    from app.rules.oracle import strip_reminders

    cleaned = strip_reminders(text).strip()
    return cleaned if cleaned in _FORMS else None


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if (key := form(text)) is not None:
        return {'kind': 'replacement', 'replacement': 'enters_choice', 'effects': [
            {'do': 'choose_value', 'who': 'you', 'what': PREFIX + key, 'options': list(_FORMS[key])}]}
    if text == 'At the beginning of your upkeep, you may choose a number between 0 and 7.':
        return {'kind': 'triggered', 'trigger': 'upkeep_you', 'optional': True, 'target': None,
                'effects': [{'do': 'choose_value', 'who': 'you', 'what': 'number',
                             'options': [str(n) for n in range(8)], 'remember': True}]}
    if text == "~'s power is equal to the last chosen number and its toughness is equal to 7 minus that number.":
        value = {'last_chosen_number95': True}
        return {'kind': 'static', 'static': 'cda', 'effects': [], 'p': value, 't': {'minus': [7, value]}}
    return None


def recipe(plan: Plan, original: Any, what: str, answer: str) -> Any:
    from app.game.rules_state import CopyExcept
    from app.rules import copying

    p, t, keyword, subtype = _FORMS[what[len(PREFIX):]][answer]
    return copying.with_excepts(original, [CopyExcept(power=str(p), toughness=str(t),
        add_text=[keyword] if keyword else [], add_subtypes=[subtype] if subtype else [])])


def ensure(plan: Plan, card: Any, controller: str, answers: dict[str, str]) -> None:
    from app.rules import copying, layers

    for what, answer in answers.items():
        if not what.startswith(PREFIX) or what[len(PREFIX):] not in _FORMS or answer not in _FORMS[what[len(PREFIX):]]:
            continue
        oid, label = plan.oid(card), what + ': ' + answer
        if any(effect.layer == '1' and effect.label == label and oid in effect.affected for effect in plan.rules.effects):
            continue
        layers.add_effect(plan, affected=[oid], layer='1', controller=controller,
            source=copying.ENTERING + card.id, duration='permanent',
            copy_recipe=recipe(plan, copying.recipe_of(plan, card), what, answer), label=label)


def number(plan: Plan, ctx: dict[str, Any]) -> int:
    card = plan.state.cards.get(ctx.get('source_card') or '')
    chosen = card.choices.get('Chosen number', '') if card is not None else ''
    return int(chosen) if chosen in tuple(str(n) for n in range(8)) else 0


def prepare_up(plan: Plan, card: Any, *, actor: str, kind: str | None = None,
               tail: dict[str, Any] | None = None) -> bool:
    """Post-payment, pre-flip continuation; never repeats payment on resume."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    face = plan.ch(card.model_copy(update={'face_down': False}))
    key = next((key for ability in face.abilities
                if (key := form(ability.text.replace('this creature', '~'))) is not None
                and 'turned face up' in key), None)
    if key is None:
        return False
    decide(plan, player=card.controller, kind='choose_one', prompt=f'{face.name}: choose its form',
           options=[DecisionOption(id=option, label=option) for option in _FORMS[key]], source=card,
           resume={'step': 'chosen_form_up95', 'card': card.id, 'object': plan.oid(card),
                   'what': PREFIX + key, 'actor': actor, 'kind': kind, 'tail': tail})
    return True


def finish_up(plan: Plan, card: Any, actor: str, kind: str | None = None) -> None:
    from app.rules import casting, replace

    plan.do({'type': 'face_down', 'card_ids': [card.id], 'face_down': False}, actor=actor)
    casting.turned_up(plan, card, actor)
    plan.rules.passed = []
    if kind == 'megamorph':
        replace.put_counters(plan, [(card.id, '+1/+1', 1)], by=actor, then={'do': 'face_up_done'})


def resume_up(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects

    data = decision.resume
    card = plan.state.cards.get(data['card'])
    if card is not None and plan.oid(card) == data['object'] and card.face_down and card.zone.endswith(':battlefield'):
        # A new replacement is applied on every turn-up, even with the same answer.
        from app.rules import copying, layers

        layers.add_effect(plan, affected=[plan.oid(card)], layer='1', controller=card.controller,
            source=copying.ENTERING + card.id, duration='permanent',
            copy_recipe=recipe(plan, copying.recipe_of(plan, card), data['what'], chosen[0]),
            label='Turned-face-up form: ' + chosen[0])
        finish_up(plan, card, data['actor'], data.get('kind'))
    if (tail := data.get('tail')) is not None:
        if tail.get('chosen_form_batch95'):
            run_batch(plan, tail['ctx'], tail['e'], tail['cards'], tail['done'])
        else:
            effects.continue_effects(plan, tail)


RESUME = {'chosen_form_up95': resume_up}


def run_batch(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any], cards: list[str], done: list[str]) -> bool:
    from app.rules import effects, facedown

    while cards:
        cid, cards = cards[0], cards[1:]
        card = plan.state.cards.get(cid)
        if card is None or not card.face_down or not card.zone.endswith(':battlefield'):
            continue
        tail = {'chosen_form_batch95': True, 'ctx': ctx, 'e': effect, 'cards': cards, 'done': [*done, cid]}
        if prepare_up(plan, card, actor=ctx['controller'], tail=tail):
            return False
        if facedown._turn_up(plan, cid, ctx['controller']):
            done.append(cid)
    effects._remember(plan, ctx, effect, done)
    effects.continue_effects(plan, ctx)
    return False
