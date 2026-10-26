"""Shared helpers of the wave 36A scenario tests (on top of tests/wave9c_kit.py: a table with Alice and Bob, rules automation on)."""

from __future__ import annotations

from app.rules.mana_units import visible_pool
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.wave9c_kit import card_named


def zone(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].zone


def to_gy(s, name, pid="p1"):
    """Put the card into its owner's graveyard the way a table does (a move: the engine logs the arrival and where it came from)."""
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


def mill(s, name, pid="p1"):
    """The card from a library into its owner's graveyard (701.17a): put back into the library first if it was drawn since."""
    c = card_named(s, name, pid)
    if not s.state.cards[c.id].zone.endswith(":library"):
        act(s, pid, type="move", card_ids=[c.id], to={"zone": "library"})
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})


def next_own_turn(s):
    """Play on to Alice's next turn: what is in a graveyard by then was put there on an earlier turn, and what she controls isn't summoning sick."""
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number == turn + 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None, limit=400)


def finish_turn(s):
    """Play on to the next turn's first main phase (this turn's end-step triggers resolve on the way)."""
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn and s.state.turn.phase == "main1" and s.state.rules.decision is None)


def offered(s):
    """Pass priority until a choice comes up; the labels of what it offers (sorted)."""
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind not in ("declare_blockers", "declare_attackers"),
          limit=60)
    return sorted(o.label for o in s.state.rules.decision.options)


def pick(s, *labels):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == label) for label in labels])


def to_attackers(s):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")


def attack(s, *attackers):
    to_attackers(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2"} for a in attackers])


def ready(s, *names, pid="p1"):
    """The permanents have been under their controller's control since the turn began (no summoning sickness, 302.6)."""
    for name in names:
        s.state.rules.controlled_since[card_named(s, name, pid).id].turn = 0


def attack_as(s, pid, attackers, target):
    """``pid`` declares the attackers (a list of cards) against ``target`` (a player id or a planeswalker's card id)."""
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, pid, type="declare_attackers", attackers=[{"card_id": a.id, "target": target} for a in attackers])


def block(s, pid, *pairs):
    """``pid`` declares blockers: (blocker, attacker) pairs."""
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    act(s, pid, type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id} for b, a in pairs])


def to_turn_of(s, pid):
    """Play on (nobody attacks, nothing is cast) to the first main phase of ``pid``'s next turn."""
    until(s, lambda s: s.state.turn.active_player == pid and s.state.turn.phase == "main1" and s.state.rules.decision is None, limit=200)


def resolve_stack(s, limit=20):
    """Let the stack resolve (a choice that comes up is answered with the first options); stop at a declaration of attackers or blockers."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("the stack never emptied")


def pool(s, pid="p1"):
    return {k: v for k, v in visible_pool(s.state, pid).items() if v}
