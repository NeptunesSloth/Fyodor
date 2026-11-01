"""-- token stacks (gap 2) -- The rules engine never sees a logical token stack.

A token stack ("Goblin ×10": ``CardInstance.quantity`` > 1) is one card on the table standing for N identical tokens: a sandbox
convenience. The rules work with objects: a token is an object (109.1), each token on the battlefield is a permanent (110.1), and a token
is subject to everything that affects permanents (111.6). Counting ("for each Goblin you control"), tapping one, sacrificing one Treasure,
attacking with each creature and "whenever a token enters" all need every token on its own. So with automation on:

* tokens made by hand are made as separate objects (``resolve``: the client's ``stacked`` is ignored), and identical tokens are not
  merged into one (``handlers.objects.merge_tokens`` refuses);
* a stack that exists anyway (made while automation was off, kept in an older save, grown with ``stack_adjust``) is spread out before
  the engine reads the table: when automation is turned on or resumed (``reconcile``) and before every intent (``engine.begin``);
* spreading a stack by hand (``split_stack`` / ``expand_stack``) is the same: ``engine.apply`` calls :func:`adopt`.

Spreading is no event: the tokens were already there. So each new object gets no "enters" event (nothing triggers, no token is
"created" this turn) and inherits the stack's own rules history instead: how long it has been under its controller's control (302.6,
summoning sickness), its manual/assisted mode, and — when the stack entered this turn — that entry and its "created a token" fact.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.game.state import GameState

if TYPE_CHECKING:
    from app.rules.plan import Plan


def stacks(state: GameState) -> list[str]:
    """The permanents standing for more than one token (the table's order). A token anywhere else ceases to exist (111.7)."""
    return [cid for cid, c in state.cards.items() if c.is_token and c.quantity > 1 and c.zone.endswith((":battlefield", ":phased"))]


def spread(plan: Plan) -> None:
    """Spread every token stack into separate objects (recorded steps of the intent or reconciliation)."""
    for cid in stacks(plan.state):
        before = set(plan.state.cards)
        plan.do({"type": "expand_stack", "card_id": cid})
        adopt(plan.state, cid, [c for c in plan.state.cards if c not in before])


def adopt(state: GameState, source: str, new_ids: list[str]) -> None:
    """``new_ids`` were split off the stack ``source``: they are tokens that were already there, not new ones (see above)."""
    rules = state.rules
    if rules is None or not new_ids or source not in state.cards:
        return
    new = set(new_ids)
    src_oid = rules.object_id(source)
    rules.events = [e for e in rules.events if e.card not in new]
    log = rules.turn_log
    current = log.turn == state.turn.number
    if current:
        log.entered = [e for e in log.entered if e.card not in new]
    entry = next((e for e in log.entered if e.object_id == src_oid), None) if current else None
    facts = [f for f in log.facts if f.object_id == src_oid and f.kind == "token"] if current else []
    new_oids = {rules.object_id(cid) for cid in new_ids}
    origin = src_oid in rules.entry_life_origins
    rules.entry_life_origins = [o for o in rules.entry_life_origins if o not in new_oids]
    mark = rules.controlled_since.get(source)
    mode = rules.card_modes.get(source)
    for cid in new_ids:
        oid = rules.object_id(cid)
        if mark is not None:
            rules.controlled_since[cid] = mark.model_copy()
        if mode is not None:
            rules.card_modes[cid] = mode
        if entry is not None:
            log.entered.append(entry.model_copy(update={"card": cid, "object_id": oid}))
        log.facts.extend(f.model_copy(update={"object_id": oid}) for f in facts)
        if origin:
            rules.entry_life_origins.append(oid)
