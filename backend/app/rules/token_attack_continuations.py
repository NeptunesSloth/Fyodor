"""Exact post-creation 508.4 choices; replacement-created creatures choose individually."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.game.rules_state import DecisionOption, ObjectRef

if TYPE_CHECKING:
    from app.rules.plan import Plan

BINDING = '_attacking_creation_receipts'


class CreatedAtom(BaseModel):
    atom: str
    objects: list[ObjectRef] = Field(default_factory=list)


class AttackItem(BaseModel):
    token: ObjectRef
    player: str


class AttackTerminal(BaseModel):
    ctx: dict[str, Any]
    recipients: dict[str, str]
    pending: list[AttackItem] = Field(default_factory=list)


def terminal(ctx: dict[str, Any], players: list[str]) -> dict[str, Any]:
    data = AttackTerminal(ctx=ctx, recipients={'opponent:' + pid: pid for pid in players})
    return {'do': 'token_attack_created', **data.model_dump(mode='json'), 'ctx': ctx}


def finish(plan: Plan, raw: dict[str, Any]) -> bool:
    data = AttackTerminal.model_validate(raw)
    # The choke point writes the actual output, including multipliers/additions,
    # into its live context. A saved terminal contains the same context value.
    receipts = data.ctx.pop(BINDING, [])
    raw["ctx"].pop(BINDING, None)
    for value in receipts:
        atom = CreatedAtom.model_validate(value)
        player = data.recipients.get(atom.atom)
        if player is not None:
            data.pending.extend(AttackItem(token=ref, player=player) for ref in atom.objects)
    return ask(plan, data)


def ask(plan: Plan, data: AttackTerminal) -> bool:
    from app.rules import context
    from app.rules.plan import decide
    from app.rules.token_grammar import _attack_with

    while data.pending:
        item = data.pending.pop(0)
        token = context._same(plan, item.token)
        if (token is None or not token.zone.endswith(':battlefield') or not plan.in_game(token) or token.controller != plan.active
                or 'Creature' not in plan.ch(token).types or item.player not in plan.live()
                or item.player == token.controller or plan.state.turn.phase not in
                ('declare_attackers', 'declare_blockers', 'combat_damage', 'end_combat')):
            continue
        walkers: dict[str, ObjectRef] = {}
        for card in plan.state.cards.values():
            if (card.zone.endswith(':battlefield') and card.controller == item.player
                    and plan.in_game(card) and 'Planeswalker' in plan.ch(card).types):
                ref = context.ref_of(plan, card.id)
                if ref is not None:
                    walkers[card.id] = ref
        if not walkers:
            _attack_with(plan, [token.id], item.player, token.controller)
            continue
        options = [DecisionOption(id=item.player, label=plan.name(item.player))]
        options += [DecisionOption(id=cid, label=plan.state.cards[cid].name or 'Planeswalker', card_id=cid) for cid in walkers]
        decide(plan, player=token.controller, kind='choose_one', prompt='Choose the player or planeswalker this token enters attacking',
               options=options, resume={'step': 'token_attack_created', 'data': data.model_dump(mode='json'),
                                       'item': item.model_dump(mode='json'),
                                       'walkers': {cid: ref.model_dump(mode='json') for cid, ref in walkers.items()}})
        return False
    return True


def resume(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import context, effects
    from app.rules.token_grammar import _attack_with

    data = AttackTerminal.model_validate(decision.resume['data'])
    item = AttackItem.model_validate(decision.resume['item'])
    token = context._same(plan, item.token)
    target = chosen[0] if chosen else ''
    valid = target == item.player and target in plan.live()
    if target in decision.resume['walkers']:
        walker = context._same(plan, ObjectRef.model_validate(decision.resume['walkers'][target]))
        valid = (walker is not None and walker.zone.endswith(':battlefield') and plan.in_game(walker) and walker.controller == item.player
                 and item.player in plan.live() and 'Planeswalker' in plan.ch(walker).types)
    if (valid and token is not None and token.zone.endswith(':battlefield') and plan.in_game(token) and token.controller == decision.player
            and token.controller == plan.active and 'Creature' in plan.ch(token).types
            and plan.state.turn.phase in ('declare_attackers', 'declare_blockers', 'combat_damage', 'end_combat')):
        _attack_with(plan, [token.id], target, token.controller)
    if ask(plan, data):
        effects.continue_effects(plan, data.ctx)


def after(plan: Plan, raw: dict[str, Any]) -> None:
    from app.rules import effects

    if finish(plan, raw):
        effects.continue_effects(plan, raw['ctx'])


def register() -> None:
    from app.rules import replace
    replace.THEN['token_attack_created'] = after
