"""Temporary hand exile retains exact exile objects through native continuations."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_JAR = ("Each player exiles all cards from their hand face down and draws seven cards. "
        "At the beginning of the next end step, each player discards their hand and returns to their hand each card they exiled this way.")
_AMNESIA = "Target player exiles all cards from their hand face down, then draws that many cards."
_SUPPRESS = ("Target player exiles all cards from their hand face down. At the beginning of the end step of that player's next turn, "
             "that player returns those cards to their hand.")
_THEFT = ("Target player reveals their hand. You choose an instant or sorcery card from it and exile that card. "
          "You may cast that card for as long as it remains exiled. At the beginning of the next end step, "
          "if you haven't cast the card, return it to its owner's hand.")
_MISCHIEF = ("Target opponent reveals a card at random from their hand. If it's an instant or sorcery card, exile it. "
             "You may cast it without paying its mana cost for as long as it remains exiled. At the beginning of the next end step, "
             "if you haven't cast it, return it to its owner's hand.")


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    text = re.sub(r"\s+", " ", body).strip()
    for wording, mode in [(_JAR, 'jar'), (_AMNESIA, 'amnesia'), (_SUPPRESS, 'suppress')]:
        if text.lower() == wording.lower():
            return [{'do': 'temporary_hand_exile', 'mode': mode}], None if mode == 'jar' else 'player', False
    if text.lower() == _THEFT.lower():
        first = scripts._parse_effects_plain('Target player reveals their hand. You choose an instant or sorcery card from it.')
        if first is not None:
            effects, targets, optional = first
            return [*effects, {'do': 'temporary_hand_card', 'free': False}], targets, optional
    if text.lower() == _MISCHIEF.lower():
        first = scripts._parse_effects_plain('Target opponent reveals a card at random from their hand.')
        if first is not None:
            effects, targets, optional = first
            return [*effects, {'do': 'temporary_hand_card', 'free': True}], targets, optional
    return None


def _delay(plan: Plan, ctx: dict[str, Any], when: dict[str, Any], cards: list[str], *, discard: bool = False) -> None:
    from app.rules import context, delayed

    binding: dict[str, Any] = {}
    context.bind_objects(plan, binding, 'temporary_hand', cards)
    effects: list[dict[str, Any]] = [{'do': 'bind_refs', 'refs': binding['refs']}]
    if discard:
        effects.append({'do': 'discard', 'who': 'each_player', 'n': 0, 'all': True})
    effects.append({'do': 'bounce', 'who': 'ref:temporary_hand'})
    delayed.create_plain(plan, ctx['controller'], ctx.get('source_card') or '', ctx.get('source_object') or '',
                         ctx.get('name') or 'Temporary exile', when, effects)


def exile_hands(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, exiled_with, replace

    mode = e['mode']
    players = plan.apnap() if mode == 'jar' else effects._players(plan, ctx, 'target')
    cards = [c for p in players for c in plan.state.zones.get(f'{p}:hand', [])]
    origins = {c: plan.state.cards[c].zone.split(':')[0] for c in cards}
    effects.exile_cards(plan, ctx, {'do': 'exile', 'face_down': True, 'blind': True}, cards)
    exiled = [c for c in cards if c in plan.state.cards and plan.state.cards[c].zone.endswith(':exile')]
    counts = {p: sum(origins[c] == p for c in exiled) for p in players}
    if mode == 'amnesia':
        exiled_with.record(plan, ctx, exiled)
    else:
        when: dict[str, Any] = {'kind': 'step', 'step': 'end', 'whose': 'next'}
        if mode == 'suppress':
            if not players:
                return True
            when.update(whose='owner', player=players[0], next_turn_only=True)
        _delay(plan, ctx, when, exiled, discard=mode == 'jar')
    if mode == 'suppress':
        return True
    return replace.draw_cards(plan, players, 7 if mode == 'jar' else counts,
                              then={'do': 'continue', 'ctx': ctx}, ctx=ctx)


def exile_card(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, permissions

    cards = [c for c in ctx.get('revealed') or [] if c in plan.state.cards and plan.state.cards[c].zone.endswith(':hand')
             and plan.ch(plan.state.cards[c]).types & {'Instant', 'Sorcery'}]
    effects.exile_cards(plan, ctx, {'do': 'exile'}, cards)
    exiled = [c for c in cards if c in plan.state.cards and plan.state.cards[c].zone.endswith(':exile')]
    context.bind_objects(plan, ctx, 'temporary_cast', exiled)
    permissions.grant_play(plan, ctx, {'who': 'ref:temporary_cast', 'play': False, 'cast': True,
                                     'until': 'permanent', 'from_exile': True, 'free': bool(e['free'])})
    _delay(plan, ctx, {'kind': 'step', 'step': 'end', 'whose': 'next'}, exiled)
    return True


PRIMITIVES = {'temporary_hand_exile': exile_hands, 'temporary_hand_card': exile_card}
