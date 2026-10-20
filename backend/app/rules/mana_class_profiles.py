"""Class-level restricted mana and a cast spell acting as a damage source."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    expected = ("Whenever you cast an instant or sorcery spell, that spell deals damage to each opponent equal to the number "
                "of instant and sorcery spells you've cast this turn.")
    if ability.kind == 'triggered' and text == expected:
        base = scripts.define(replace(ability, text=text.replace('that spell deals', '~ deals')), ch)
        if base is not None:
            from app.rules import selectors

            return {**base, 'trigger': 'event', 'cond': {'event': 'cast', 'subject': 'player', 'player': 'you',
                'spell': selectors.Selector(zones=('stack',), types=('Instant', 'Sorcery')).key()},
                'effects': [{**e, 'do': 'event_spell_damage'} if e.get('do') == 'damage' else e
                                      for e in base['effects']]}
    return None


def event_spell_damage(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    refs = context._object_refs(ctx, context.EVENT, was=True)
    if not refs:
        return True
    ref = refs[0]
    # _ability_source natively reads this exact spell while on the stack, then
    # its stack LKI after departure, including X, lifelink and spell protection.
    original = {**ctx, 'controller': ctx.get('_class_controller', ctx['controller'])}
    card = plan.state.cards.get(ref.card)
    snap = plan.rules.lki.get(ref.object_id)
    controller = card.controller if card is not None and plan.oid(card) == ref.object_id and card.zone == 'stack' else (
        snap.controller if snap is not None else original['controller'])
    view = {**ctx, 'controller': controller, '_class_controller': original['controller'],
            'source_card': ref.card, 'source_object': ref.object_id,
            'refs': {**ctx.get('refs', {}), 'class_opponents': {'kind': 'players',
                'players': effects._players(plan, original, e['who'])}}}
    return effects.damage(plan, view, {**e, 'do': 'damage', 'who': 'ref:class_opponents',
        'n': effects._amount(plan, original, e['n'])})


PRIMITIVES = {'event_spell_damage': event_spell_damage}
