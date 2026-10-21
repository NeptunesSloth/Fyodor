"""Exact temporary Vehicle and ordinary targeted crash trigger."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_CRASH = ('Crash Land — Whenever this Vehicle deals damage, roll a six-sided die. '
          "If the result is equal to this Vehicle's mana value, sacrifice this Vehicle, "
          'then it deals that much damage to any target.')
_PRIMARY = ('At the beginning of combat on your turn, choose target nonland permanent you control. '
            'Until end of turn, it becomes a Vehicle artifact with base power and toughness each equal '
            'to its mana value, and it gains crew 2 and "' + _CRASH + '"')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.text == _PRIMARY:
        native = scripts.define(replace(ability, text='At the beginning of combat on your turn, tap target nonland permanent you control.'), ch)
        if native is not None:
            return {**native, 'effects': [{'do': 'become', 'who': 'target', 'types': ['Artifact'],
                    'artifact_types': ['Vehicle'], 'p': {'mana_value': 'it'}, 't': {'mana_value': 'it'},
                    'abilities': ['Crew 2', _CRASH], 'duration': 'end_of_turn'}]}
    if ability.text == _CRASH:
        native = scripts.define(replace(ability, text='Whenever this creature deals damage, this creature deals 1 damage to any target.'), ch)
        if native is not None:
            return {**native, 'effects': [{'do': 'roll', 'sides': 6, 'count': 1}, {'do': 'rex_crash45'}]}
    return None


def match(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import coin_recipes, values

    cid, oid = ctx.get('source_card'), ctx.get('source_object')
    source = plan.state.cards.get(cid or '')
    known = bool(oid and ((source is not None and plan.oid(source) == oid) or oid in plan.rules.lki))
    original = values._object(plan, ctx, 'self') if known else None
    if original is None:
        from app.game.rules_state import DecisionOption
        from app.rules.plan import decide

        decide(plan, player=ctx['controller'], kind='manual_resolution',
               prompt=(f"The original Vehicle's mana value is unknown in this older save. The final die result is {ctx['die']}. "
                       'Resolve the remaining Crash Land instructions by hand, then press Done.'),
               options=[DecisionOption(id='done', label='Done')], resume={'step': 'rex_unknown45', 'ctx': ctx})
        return False

    # Numeric amount expressions clamp negative numbers; equality must instead
    # inspect the actual finalized result, so -1 never matches a zero mana value.
    if int(ctx['die']) == original[1].mana_value:
        coin_recipes.insert(ctx, [{'do': 'sacrifice', 'who': 'self'}, {'do': 'rex_terminal45'},
                                 {'do': 'damage', 'who': 'target', 'n': {'die': 'result'}}])
    return True


def terminal(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    cid, oid = ctx.get('source_card'), ctx.get('source_object')
    pending = plan.rules.pending_616.get(cid) if cid else None
    if pending is not None and pending.get('oid') == oid:
        from app.rules import replacements

        if replacements.offer_616(plan):
            assert plan.rules.decision is not None
            assert plan.rules.decision.resume is not None
            # Sacrifice and the roll have already occurred. Damage follows the
            # real terminal movement, including the native commander chooser.
            then = {'do': 'continue', 'ctx': ctx}
            plan.rules.decision.resume['then'] = then
            plan.rules.decision.resume['abort_then'] = then
            return False
    return True


PRIMITIVES = {'rex_crash45': match, 'rex_terminal45': terminal}


def unknown_done(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    if chosen != ['done']:
        raise ActionError('Resolve the remaining instructions by hand, then choose Done')
    assert d.resume is not None
    effects.continue_effects(plan, d.resume['ctx'])


RESUME = {'rex_unknown45': unknown_done}
