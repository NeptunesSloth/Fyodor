"""CR 614.8/603.7: effects tied to using one particular regeneration shield."""
from __future__ import annotations

import re
import secrets
from copy import deepcopy
from typing import Any

from app.game.rules_state import RegenerationShield
from app.rules.plan import Plan

_DELAYED = re.compile(r'^(?P<head>.*?Regenerate (?:~|target creature)\.) When it regenerates this way, (?P<rider>.+)$')
_CONTROL = re.compile(r'^Regenerate target creature\. You gain control of that creature if it regenerates this way\.$')


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    immediate = _CONTROL.fullmatch(body) is not None
    match = _DELAYED.fullmatch(body)
    if not immediate and match is None:
        return None
    head = 'Regenerate target creature.' if immediate else match['head'] if match else ''
    rider = 'You gain control of it.' if immediate else match['rider'] if match else ''
    base = scripts._parse_effects_plain(head)
    following = scripts._parse_effects_plain(rider[0].upper() + rider[1:], 'self', event_player=True)
    if base is None or following is None or following[1] is not None or following[2]:
        return None
    effects, target, optional = base
    if not effects or effects[-1].get('do') != 'regenerate':
        return None
    return [*effects[:-1], {**effects[-1], 'regeneration_rider': following[0], 'immediate': immediate}], target, optional


def capture(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any], cid: str) -> None:
    from app.rules import context
    from app.rules.effects import _players

    bound: dict[str, Any] = {'refs': deepcopy(ctx.get('refs') or {})}
    context.bind_objects(plan, bound, 'regenerated', [cid])
    players = _players(plan, ctx, 'target')
    effects = deepcopy(effect['regeneration_rider'])
    # "it" is the protected permanent; "that player" is the opponent chosen
    # while the creating ability resolved, never a future controller.
    for e in effects:
        if e.get('who') == 'self':
            e['who'] = 'ref:regenerated'
        elif e.get('who') == 'event_player':
            context.bind_players(bound, 'regeneration_player', players)
            e['who'] = 'ref:regeneration_player'
    plan.rules.regeneration_riders.append(RegenerationShield(
        id=secrets.token_hex(8), object_id=plan.oid(cid), controller=ctx['controller'],
        source_card=ctx['source_card'], source_object=ctx['source_object'], name=ctx.get('name') or 'Regeneration',
        effects=effects, refs=bound['refs'], immediate=bool(effect.get('immediate'))))


def shields(plan: Plan, oid: str) -> list[RegenerationShield]:
    return [s for s in plan.rules.regeneration_riders if s.object_id == oid]


def apply(plan: Plan, shield: RegenerationShield) -> None:
    if shield.immediate:
        from app.rules.effects import gain_control

        ctx = {'controller': shield.controller, 'source_card': shield.source_card,
               'source_object': shield.source_object, 'name': shield.name, 'refs': shield.refs}
        for effect in shield.effects:
            # The only immediate grammar currently supported is Debt's control
            # change, which neither targets nor makes replacement decisions.
            assert effect['do'] == 'gain_control'
            gain_control(plan, ctx, effect)
        return
    from app.rules import trigger_multipliers, triggers

    triggers._add(plan, controller=shield.controller, source_card=shield.source_card,
                  source_object=shield.source_object, name=shield.name, index=trigger_multipliers.DELAYED,
                  definition={'kind': 'triggered', 'trigger': 'delayed',
                              'effects': [{'do': 'bind_refs', 'refs': shield.refs}, *shield.effects]})
