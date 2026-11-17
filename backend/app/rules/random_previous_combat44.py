"""Exact previous-combat choice, using native attack requirements."""
from __future__ import annotations

import secrets
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_TEXT = ('At the beginning of combat on your turn, choose an opponent at random that this creature '
         "didn't attack during your last combat. This creature attacks that player this combat if able. "
         "If you can't choose an opponent this way, tap this creature.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.text != _TEXT:
        return None
    from app.rules import scripts

    native = scripts.define(replace(ability, text='At the beginning of combat on your turn, tap this creature.'), ch)
    return {**native, 'effects': [{'do': 'random_previous_combat44'}]} if native is not None else None


def consume(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import coin_recipes, context, last_combat_receipts44
    from app.rules.plan import decide

    memory = getattr(plan.rules, 'combat_memory', None)
    source_oid = ctx.get('source_object')
    previous = (last_combat_receipts44.previous_players(memory, ctx['controller'], source_oid)
                if memory is not None and source_oid else None)
    if previous is None:
        decide(plan, player=ctx['controller'], kind='manual_resolution',
               prompt=("This older save lacks the previous combat history. Resolve Territorial Hellkite's whole "
                       'trigger by hand, then press Done.'),
               options=[DecisionOption(id='done', label='Done')],
               resume={'step': 'last_combat44_legacy', 'ctx': ctx})
        return False
    pool = sorted(p for p in plan.live() if p != ctx['controller'] and p not in previous)
    if pool:
        from app.rules import randomness  # -- random choices (wave MBC-D) --
        chosen = randomness.choice(plan, plan.rng or secrets.SystemRandom(), pool, kind='player', player=ctx['controller'])
        context.bind_players(ctx, 'r44_hellkite_player', [chosen])
        coin_recipes.insert(ctx, [{'do': 'restrict', 'who': 'self', 'player': 'ref:r44_hellkite_player',
                                  'rules': ['attack_player:@that'], 'duration': 'end_of_combat'}])
    else:
        coin_recipes.insert(ctx, [{'do': 'tap', 'who': 'self'}])
    return True


def legacy_done(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    if chosen != ['done']:
        from app.game.errors import ActionError

        raise ActionError('Resolve this trigger by hand, then choose Done')
    assert d.resume is not None
    effects.continue_effects(plan, d.resume['ctx'])
