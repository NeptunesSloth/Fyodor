"""Wave 110O (second half): single-card wordings, real Oracle text (tests/fixtures/wave110o_cards.json). Every scenario checks the replay and a save and a load.

* 601.2b, 118.8, 615.1: Undergrowth's optional {2}{R} (paid as it is cast) makes its combat damage prevention skip red creatures.
* 603.7a, 701.9, 603.2c: Pure Intentions returns the cards an opponent's spell or ability made you discard (one batch), and itself at the next end step.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave34b_activated import stops
from tests.wave9c_kit import build
from tests.wave110o_kit import (  # noqa: F401
    EXTRA,
    card_db,
    card_named,
    ch,
    check,
    full,
    life,
    mana,
    now,
    put,
    settle,
    to_hand,
    to_phase,
)

UNDERGROWTH = "Undergrowth"


@pytest.mark.parametrize("name", [UNDERGROWTH, "Pure Intentions"])
def test_the_cards_are_full(name):
    assert full(name)


def passes_to_bob(s):
    for _ in range(20):
        if s.state.rules.priority == "p2" and not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("Bob never got priority")


@pytest.mark.parametrize("kicked", [False, True])
def test_undergrowth_prevents_all_combat_damage_but_red_creatures_when_the_extra_cost_is_paid(cards, kicked):
    s = build(cards, ["Mardu Scout", "Grizzly Bears"], [UNDERGROWTH])
    scout, bears = put(s, "Mardu Scout"), put(s, "Grizzly Bears")
    for c in (scout, bears):
        s.state.rules.controlled_since[c.id].turn = 0
    stops(s)
    while s.state.rules.decision is None or s.state.rules.decision.kind != "declare_attackers":
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in (scout, bears)])
    passes_to_bob(s)
    spell = to_hand(s, UNDERGROWTH, "p2")
    mana(s, "p2", **({"G": 1, "R": 1, "C": 2} if kicked else {"G": 1}))
    act(s, "p2", type="cast_spell", card_id=spell.id, **({"kicker": 1} if kicked else {}))
    settle(s)
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert life(s, "p2") == 40 - (2 if kicked else 0)  # (the red Scout's 2 is not prevented when {2}{R} was paid; the green Bears' 2 always is)
    check(s)


PURE, ROT = "Pure Intentions", "Mind Rot"


def bobs_rot(cards, hand, in_response=True):
    """Bob's first main phase, Alice's hand exactly ``hand``; Bob casts Mind Rot on Alice and Alice (with priority) casts Pure Intentions."""
    s = build(cards, [PURE, "Grizzly Bears", "Llanowar Elves", "Barren Moor"], [ROT])
    for c in [c for c in s.state.cards.values() if c.zone == "p1:hand"]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "library"}, position="bottom")
    mine = [to_hand(s, n) for n in hand]
    stops(s)
    to_phase(s, "main1", turn=2)
    rot = to_hand(s, ROT, "p2")
    mana(s, "p2", B=1, C=2)
    act(s, "p2", type="cast_spell", card_id=rot.id, targets=["p1"])
    return s, mine


def alice_casts_pure(s):
    pure = card_named(s, PURE)
    mana(s, "p1", W=1)
    act(s, "p1", type="cast_spell", card_id=pure.id)


def finish(s, picks=()):
    """Resolve the stack; Alice's discard picks are ``picks`` (card ids)."""
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        if d is not None:
            ids = [o.id for o in d.options if o.card_id in picks][: max(1, d.min_choices)] or [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def test_pure_intentions_returns_the_cards_an_opponents_spell_made_you_discard(cards):
    s, (pure, bears, elves) = bobs_rot(cards, [PURE, "Grizzly Bears", "Llanowar Elves"])
    alice_casts_pure(s)
    finish(s, picks={bears.id, elves.id})
    assert now(s, bears).zone == "p1:hand" and now(s, elves).zone == "p1:hand" and now(s, pure).zone == "p1:graveyard"
    check(s)


def test_pure_intentions_ignores_a_discard_you_pay_as_a_cost(cards):
    s, (pure, moor, bears) = bobs_rot(cards, [PURE, "Barren Moor", "Grizzly Bears"])
    alice_casts_pure(s)
    while not (s.state.rules.priority == "p1" and len(s.state.zones["stack"]) == 1):
        act(s, s.state.rules.priority, type="pass_priority")
    mana(s, "p1", B=1)
    act(s, "p1", type="activate_ability", card_id=moor.id, ability=next(a.index for a in ch(s, moor).abilities if a.text.startswith("Cycling")))
    finish(s)
    assert now(s, moor).zone == "p1:graveyard"  # (cycling discards it as a cost: not a spell or ability an opponent controls, 701.9, 118.8)
    assert now(s, bears).zone == "p1:hand"  # (Mind Rot's discards came back)
    check(s)


def test_pure_intentions_discarded_by_an_opponents_spell_returns_at_the_next_end_step(cards):
    s, (pure, bears) = bobs_rot(cards, [PURE, "Grizzly Bears"])
    finish(s)
    assert now(s, pure).zone == "p1:graveyard" and now(s, bears).zone == "p1:graveyard"
    for _ in range(40):
        if s.state.turn.phase == "end" or s.state.rules.decision is not None and s.state.rules.decision.kind in ("declare_attackers", "declare_blockers"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    settle(s)
    assert now(s, pure).zone == "p1:hand" and now(s, bears).zone == "p1:graveyard"  # (only Pure Intentions itself: the other card stays)
    check(s)
