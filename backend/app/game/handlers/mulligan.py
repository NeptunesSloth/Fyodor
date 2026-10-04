"""Guided opening hands: simultaneous, per-player mulligan decisions under a MulliganPolicy.

Opponents learn only what the table physically shows: how many mulligans someone took, that
they are choosing cards to bottom, and "kept 7 and put 2 cards on the bottom" — never which.
"""

from __future__ import annotations

import time
from typing import Any

from app.game import actions as A
from app.game import ops
from app.game.errors import ActionError
from app.game.handlers.zones import draw_cards, rekey_zone
from app.game.mulligan import to_bottom
from app.game.ops import log, pname, text
from app.game.state import GameState, MulliganPolicy, Pregame, PregameSeat, zone_key


def begin(state: GameState) -> None:
    """Deal opening hands and open the pregame (called when a game is created)."""
    policy = state.settings.mulligan
    if policy is None:
        return
    state.pregame = Pregame(seats={pid: PregameSeat() for pid in state.seat_order})
    for pid in state.seat_order:
        lib = state.zone(zone_key(pid, "library"))
        n = min(policy.starting_hand_size, len(lib))
        if n:
            draw_cards(state, pid, n)
    rule = policy.display_name + (" (not defined yet)" if policy.needs_definition else "")
    log(state, None, time.time(), [text(f"Opening hands dealt. Mulligan rule: {rule}.")], kind="notice")


def _seat(state: GameState, a: A.Base, player: str | None) -> tuple[str, PregameSeat, MulliganPolicy]:
    if state.pregame is None or state.pregame.finished:
        raise ActionError("Opening hands are already settled")
    policy = state.settings.mulligan
    if policy is None:
        raise ActionError("This table has no guided mulligan")
    pid = ops.player(state, player, a.actor)
    if pid != a.actor:
        raise ActionError("Players make their own mulligan decisions")
    seat = state.pregame.seats.get(pid)
    if seat is None:
        raise ActionError("That player isn't in the opening-hand phase")
    return pid, seat, policy


def returned_cards(state: GameState, pid: str, policy: MulliganPolicy, card_ids: list[str] | None) -> list[str]:
    hand = state.zone(zone_key(pid, "hand"))
    if card_ids is None:
        return list(hand)
    if not policy.partial_hand_selection:
        raise ActionError("This mulligan rule sends back the whole hand")
    if len(set(card_ids)) != len(card_ids) or any(cid not in hand for cid in card_ids):
        raise ActionError("Choose cards from your own hand")
    if not card_ids:
        raise ActionError("Choose at least one card to send back")
    return list(card_ids)


def shuffle_size(state: GameState, pid: str, policy: MulliganPolicy, returned: int) -> int:
    """Library size at the moment a mulligan shuffles it (mirrors ``take``)."""
    lib = len(state.zone(zone_key(pid, "library")))
    return lib if policy.set_aside_rejected_hands else lib + returned


def take(state: GameState, a: A.MulliganTake) -> None:
    pid, seat, policy = _seat(state, a, a.player)
    if seat.status != "deciding":
        raise ActionError("You've already kept this hand")
    if policy.needs_definition:
        raise ActionError(f"The {policy.display_name} mulligan isn't defined yet — the host sets it up in table settings")
    if policy.max_mulligans is not None and seat.mulligans >= policy.max_mulligans:
        raise ActionError(f"No more mulligans ({policy.max_mulligans} max)")
    returned = returned_cards(state, pid, policy, a.card_ids)
    partial = a.card_ids is not None
    new_size = len(state.zone(zone_key(pid, "hand"))) if partial else policy.draw_count
    if new_size - min(new_size, to_bottom(policy, seat.mulligans + 1)) < policy.minimum_hand_size:
        raise ActionError(f"A mulligan can't leave you with fewer than {policy.minimum_hand_size} cards")
    lib_key = zone_key(pid, "library")
    dest = zone_key(pid, "setaside") if policy.set_aside_rejected_hands else lib_key
    for cid in returned:
        ops.move_card(state, state.cards[cid], dest, position="bottom")
    if policy.shuffle_between_mulligans:
        if a.r is None:
            raise ActionError("unresolved mulligan")
        rekey_zone(state, lib_key, a.r.perm, a.r.new_ids)
    draw = len(returned) if partial else policy.draw_count
    drawn = draw_cards(state, pid, draw) if draw and state.zone(lib_key) else []
    seat.mulligans += 1
    state.players[pid].mulligans = seat.mulligans
    what = f"sent back {len(returned)} and drew {len(drawn)}" if partial else f"drew {len(drawn)}"
    log(state, a.actor, a.ts, [pname(state, pid), text(f" took mulligan #{seat.mulligans} and {what}.")])


def powder(state: GameState, a: A.MulliganPowder) -> None:
    """-- opening hand (wave 18C) -- 103.5b: "any time you could mulligan" (Serum Powder): while deciding, exile every card in hand
    (the exiled cards are public, 406.3) and draw that many; no mulligan is taken."""
    pid, seat, _ = _seat(state, a, a.player)
    hand = list(state.zone(zone_key(pid, "hand")))
    if seat.status != "deciding" or a.card_id not in hand:
        raise ActionError("You can only do that with the card in your hand while deciding about a mulligan")
    if not a.verified:
        raise ActionError("That card has no such ability")
    cards = [state.cards[c] for c in hand]
    for card in cards:
        ops.move_card(state, card, zone_key(pid, "exile"))
    drawn = draw_cards(state, pid, len(cards))
    log(state, a.actor, a.ts, [pname(state, pid), text(" exiled their hand ("), ops.group(state, cards),
                                text(f") with {state.cards[a.card_id].name} and drew {len(drawn)}.")])


def keep(state: GameState, a: A.MulliganKeep) -> None:
    pid, seat, policy = _seat(state, a, a.player)
    if seat.status != "deciding":
        raise ActionError("You've already kept this hand")
    hand = len(state.zone(zone_key(pid, "hand")))
    n = min(hand, to_bottom(policy, seat.mulligans))
    if n == 0:
        _finish_seat(state, a, pid, seat, policy, kept_from=hand, bottomed=0)
        return
    seat.status, seat.to_bottom = "bottoming", n
    log(state, a.actor, a.ts, [pname(state, pid), text(f" keeps {hand} and is choosing {n} to put on the bottom.")])


def bottom(state: GameState, a: A.MulliganBottom) -> None:
    pid, seat, policy = _seat(state, a, a.player)
    if seat.status != "bottoming":
        raise ActionError("Nothing to put on the bottom right now")
    hand = state.zone(zone_key(pid, "hand"))
    if len(set(a.card_ids)) != len(a.card_ids) or any(cid not in hand for cid in a.card_ids):
        raise ActionError("Choose cards from your own hand")
    if len(a.card_ids) != seat.to_bottom:
        raise ActionError(f"Choose exactly {seat.to_bottom} card{'s' if seat.to_bottom != 1 else ''} (you chose {len(a.card_ids)})")
    kept_from = len(hand)
    lib_key = zone_key(pid, "library")
    for cid in a.card_ids:
        ops.move_card(state, state.cards[cid], lib_key, position="bottom")
    _finish_seat(state, a, pid, seat, policy, kept_from=kept_from, bottomed=len(a.card_ids))


def _finish_seat(state: GameState, a: A.MulliganKeep | A.MulliganBottom, pid: str, seat: PregameSeat, policy: MulliganPolicy,
                 *, kept_from: int, bottomed: int) -> None:
    aside_key = zone_key(pid, "setaside")
    aside = list(state.zone(aside_key))
    if policy.final_shuffle and aside:
        lib_key = zone_key(pid, "library")
        for cid in aside:
            ops.move_card(state, state.cards[cid], lib_key, position="bottom")
        if a.r is None:
            raise ActionError("unresolved final shuffle")
        rekey_zone(state, lib_key, a.r.perm, a.r.new_ids)
    seat.status, seat.to_bottom = "kept", 0
    seat.kept = len(state.zone(zone_key(pid, "hand")))
    msg = f" kept {kept_from}" + (f" and put {bottomed} card{'s' if bottomed != 1 else ''} on the bottom." if bottomed else ".")
    if policy.final_shuffle and aside:
        msg += f" {len(aside)} set-aside card{'s were' if len(aside) != 1 else ' was'} shuffled into their library."
    log(state, a.actor, a.ts, [pname(state, pid), text(msg)])
    _maybe_finish(state, a.actor, a.ts, a.opening)


def _maybe_finish(state: GameState, actor: str | None, ts: float, opening: list[dict[str, Any]] | None = None) -> None:
    pregame = state.pregame
    if pregame is not None and all(s.status == "kept" for s in pregame.seats.values()):
        pregame.finished = True
        first = state.players[state.turn.active_player].name
        log(state, actor, ts, [text(f"Everyone has kept. {first} goes first — good luck!")])
        if opening:  # -- opening hand (wave 18C) -- 103.6: the opening-hand decisions come before the first turn
            from app.game.handlers.rules import replay_steps

            replay_steps(state, opening)


def finish(state: GameState, a: A.MulliganFinish) -> None:
    """Host override (the API only lets the host send this)."""
    pregame = state.pregame
    if pregame is None or pregame.finished:
        raise ActionError("Opening hands are already settled")
    waiting = [state.players[pid].name for pid, s in pregame.seats.items() if s.status != "kept"]
    for pid, seat in pregame.seats.items():
        if seat.status != "kept":
            seat.status, seat.to_bottom = "kept", 0
            seat.kept = len(state.zone(zone_key(pid, "hand")))
    pregame.finished = True
    note = f" ({', '.join(waiting)} kept what they held)" if waiting else ""
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" started the game{note}.")])
    if a.opening:  # -- opening hand (wave 18C) -- 103.6
        from app.game.handlers.rules import replay_steps

        replay_steps(state, a.opening)
