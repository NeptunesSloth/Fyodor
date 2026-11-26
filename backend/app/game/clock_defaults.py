"""-- turn clock (stage 3) -- the safest legal default for each wait, for a player whose clock reached zero when the host chose "Act
for the player". A pure function of the table: the answers to try in order (the first the engine accepts is the one); ``[]`` leaves the
wait to the table. It never concedes or eliminates anyone, and reads only what the waited-on player may see (their own decision and,
while bottoming, their own hand). The engine stays the judge of every answer; ``app.game.dummy.answers`` gives the fallbacks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game import dummy
from app.game.rules_state import cancelable
from app.game.state import GameState
from app.game.turn_clock import waiting_on

if TYPE_CHECKING:
    from app.rules.characteristics import CardInfo

RULES_CONFIRMS = frozenset({"sba_confirm", "combat_damage", "trigger_confirm"})  # ASSISTED: the rules say it happens
TABLE_ONLY = frozenset({"manual_resolution", "reconcile"})  # what only the table knows


def answers(state: GameState, pid: str, info: CardInfo | None) -> list[dict[str, Any]]:
    """The payloads to try for ``pid``'s wait, safest first (``[]``: nothing to answer, or left to the table)."""
    key = waiting_on(state).get(pid)
    if key is None:
        return []
    if key.startswith("m:"):
        seat = state.pregame.seats.get(pid) if state.pregame is not None else None
        if seat is None:
            return []
        if seat.status == "deciding":
            # 103.5: keeping is the declaration not to take a mulligan; 103.5b: an "any time you could mulligan" action (Serum
            # Powder) is optional ("may") and is not used
            return [{"type": "mulligan_keep"}]
        # 103.5: the player puts that many cards on the bottom: the first ones of the hand, in hand order
        hand = state.zones.get(f"{pid}:hand", [])[:seat.to_bottom]
        return [{"type": "mulligan_bottom", "card_ids": hand}] if hand else []
    if key.startswith("p:"):
        return [{"type": "pass_priority"}]  # 117.3d: a player who takes no action passes (this priority only: no "until")
    d = state.rules.decision if state.rules is not None else None
    if d is None or d.kind in TABLE_ONLY:
        return []

    def choose(ids: list[str]) -> dict[str, Any]:
        return {"type": "choose", "decision_id": d.id, "option_ids": ids}

    out: list[dict[str, Any]] = []
    if cancelable(d):
        out.append(choose(["cancel"]))  # 601.2, 733.1: a cast still being announced is reversed (the card returns where it was)
    if d.kind == "declare_attackers":
        out.append({"type": "declare_attackers", "attackers": []})  # 508.1a: "which creatures ..., if any, will attack"
        must = (d.display or {}).get("must_attack") or {}
        # 508.1d: a requirement must be obeyed when it can be: each creature that must attack, at the first place it may
        forced = [{"card_id": cid, "target": places[0]} for cid, places in must.items() if places]
        if forced:
            out.append({"type": "declare_attackers", "attackers": forced})
        return _tidy(out)
    if d.kind == "declare_blockers":
        out.append({"type": "declare_blockers", "blocks": []})  # 509.1a: "which creatures ..., if any, will block"
        # 509.1c: when a creature must block, the blocks the engine's own pair check allows (the dummy's "all", then each chump)
        out += [b for b in dummy.answers(d, state=state, info=info, blocks="all") if b.get("blocks")]
        return _tidy(out)
    offered = {o.id for o in d.options}
    if d.kind == "confirm":
        if (d.resume or {}).get("step") in RULES_CONFIRMS:
            # 704.3 (state-based actions are performed), 510.2 (assigned combat damage is dealt), 603.3 (a triggered ability is put on
            # the stack): ASSISTED only asks the table to confirm what the rules say happens
            out.append(choose(["yes"]))
        elif "no" in offered:
            out.append(choose(["no"]))  # 603.5, 608.2d: a "may" is the player's choice, made as it resolves: declined
    if d.min_choices <= 0:
        out.append(choose([]))  # an optional ("up to") choice: nothing chosen
    # 608.2d, 700.2: otherwise the first legal options (``order``: as offered; ``divide``: as evenly as allowed, 601.2d; typed names)
    out += dummy.answers(d, state=state, info=info)
    return _tidy(out)


def _tidy(out: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each answer once, in order, at most ``dummy.MAX_TRIES + 2``."""
    seen: list[dict[str, Any]] = []
    for p in out:
        if p not in seen:
            seen.append(p)
    return seen[:dummy.MAX_TRIES + 2]
