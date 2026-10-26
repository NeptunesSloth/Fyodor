"""Typed resolution choices for existing attackers (508.7), without a new attack declaration."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.game.rules_state import DecisionOption, ObjectRef

if TYPE_CHECKING:
    from app.rules.plan import Plan

SINGLE = 'you may reselect which player or permanent target attacking creature is attacking.'
ALL = 'for each attacking creature, you may reselect which player or permanent that creature is attacking.'
FORCED = ('choose target player and any number of target attacking creatures their opponents control. '
          'Those creatures are now attacking that player.')
TEXTS = frozenset(
    f'When this {kind} enters during the declare attackers step, {effect}'
    for kind, effect in [('creature', SINGLE), ('artifact', SINGLE), ('creature', ALL), ('creature', FORCED)]
)


class Reselection(BaseModel):
    ctx: dict[str, Any]
    pending: list[ObjectRef] = Field(default_factory=list)
    current: ObjectRef | None = None
    destinations: dict[str, ObjectRef] = Field(default_factory=dict)
    players_only: bool = False  # -- (wave 110D) -- Capricopian: "which player this creature is attacking", never a planeswalker or battle


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ability.kind != 'triggered' or ability.text not in TEXTS:
        return None
    native = scripts.define(replace(ability, text='When this creature enters, draw a card.'), ch)
    if native is None:
        return None
    out = {**native, 'trigger': 'event',
           'cond': {'event': 'enter', 'subject': 'self', 'during_step': 'declare_attackers'},
           'effects': [{'do': 'attacker_reselect73', 'mode': 'all' if ability.text.endswith(ALL) else
                        'forced' if ability.text.endswith(FORCED) else 'single'}]}
    if ability.text.endswith(SINGLE):
        out['target'] = {'what': 'attacking_creature', 'min': 1, 'max': 1}
    elif ability.text.endswith(FORCED):
        out['targets'] = [{'what': 'player', 'min': 1, 'max': 1},
                          {'what': selectors.Selector(types=('Creature',), attacking=True).key(),
                           'min': 0, 'max': 250, 'of': 0, 'controller_opponents_of': 0}]
    return out


def bind_opponents(plan: Plan, spec: dict[str, Any], groups: list[list[Any]]) -> str:
    from app.rules import player_relative, selectors

    at = spec['controller_opponents_of']
    players = player_relative.players_of(plan, groups[at]) if at < len(groups) else []
    sel = selectors.from_key(spec['what'])
    if len(players) != 1:
        return replace(sel, controller='player:').key()
    alternatives = tuple(replace(sel, controller='player:' + pid).key() for pid in plan.live() if pid != players[0])
    return selectors.Selector(either=alternatives).key() if alternatives else replace(sel, controller='player:').key()


def destinations(plan: Plan, attacker: Any) -> dict[str, ObjectRef | None]:
    """508.7c: structural opponent/controller/protector tests, no declaration costs or restrictions."""
    from app.rules import battles, context

    opponents = [pid for pid in plan.live() if pid != attacker.controller]
    out: dict[str, ObjectRef | None] = {pid: None for pid in opponents}
    for card in plan.state.cards.values():
        if not card.zone.endswith(':battlefield') or not plan.in_game(card):
            continue
        ch = plan.ch(card)
        if ('Planeswalker' in ch.types and card.controller in opponents
                or 'Battle' in ch.types and battles.protector(plan.state, card) in opponents):
            ref = context.ref_of(plan, card.id)
            if ref is not None:
                out[card.id] = ref
    return out


def _attacker(plan: Plan, ref: ObjectRef | None) -> Any:
    from app.rules import context

    card = context._same(plan, ref) if ref is not None else None
    if (card is None or not card.zone.endswith(':battlefield') or not plan.in_game(card)
            or not card.is_attacking or not plan.ch(card).is_creature):
        return None
    return card


def _apply(plan: Plan, attacker: Any, destination: str) -> None:
    from app.rules.token_grammar import _attack_with

    # The table attack action changes the current destination only. Actual
    # declaration history and trigger events are produced separately by combat.declare.
    _attack_with(plan, [attacker.id], destination, attacker.controller)


def effect(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    if e['mode'] == 'forced':
        players = effects._players(plan, ctx, 'target:0')
        if len(players) == 1 and players[0] in plan.live():
            for cid in effects._cards(plan, ctx, 'target:1'):
                card = plan.state.cards[cid]
                if card.is_attacking and card.controller != players[0]:
                    _apply(plan, card, players[0])
        return True
    if e['mode'] == 'self_player110d':
        me = plan.state.cards.get(ctx.get('source_card') or '')
        refs = [ref for ref in [context.ref_of(plan, me.id) if me is not None and me.is_attacking and me.zone.endswith(':battlefield')
                                and plan.in_game(me) else None] if ref is not None]
        return ask(plan, Reselection(ctx=ctx, pending=refs, players_only=True))
    cards = (list(plan.state.cards.values()) if e['mode'] == 'all' else [plan.state.cards[cid] for cid in effects._cards(plan, ctx, 'target')])
    refs = [ref for card in cards if card.is_attacking and card.zone.endswith(':battlefield')
            and plan.in_game(card) and (ref := context.ref_of(plan, card.id)) is not None]
    return ask(plan, Reselection(ctx=ctx, pending=refs))


def ask(plan: Plan, data: Reselection) -> bool:
    from app.rules.plan import decide

    while data.pending:
        data.current = data.pending.pop(0)
        attacker = _attacker(plan, data.current)
        if attacker is None:
            continue
        choices = destinations(plan, attacker)
        if data.players_only:
            choices = {key: ref for key, ref in choices.items() if ref is None}
        data.destinations = {key: ref for key, ref in choices.items() if ref is not None}
        options = [DecisionOption(id='decline', label='Keep current attack destination')]
        options += [DecisionOption(id=key, label=plan.name(key) if ref is None else plan.state.cards[key].name,
                                   card_id=key if ref is not None else None) for key, ref in choices.items()]
        decide(plan, player=data.ctx['controller'], kind='choose_one', prompt=f'Reselect whom {attacker.name} is attacking',
               options=options, resume={'step': 'attacker_reselect73', 'data': data.model_dump(mode='json')})
        return False
    return True


def resume(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import context, effects

    data = Reselection.model_validate(decision.resume['data'])
    attacker = _attacker(plan, data.current)
    key = chosen[0] if chosen else 'decline'
    if attacker is not None and key != 'decline' and key in destinations(plan, attacker) and (not data.players_only or key in plan.live()):
        ref = data.destinations.get(key)
        if ref is None and key in plan.live() or ref is not None and context._same(plan, ref) is not None:
            _apply(plan, attacker, key)
    if ask(plan, data):
        effects.continue_effects(plan, data.ctx)
