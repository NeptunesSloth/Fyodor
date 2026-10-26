"""Wave 110O (second half): single-card wordings, real Oracle text (tests/fixtures/wave110o_cards.json). Every scenario checks the replay and a save and a load.

* 601.2b, 118.8, 615.1: Undergrowth's optional {2}{R} (paid as it is cast) makes its combat damage prevention skip red creatures.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave34b_activated import stops
from tests.wave9c_kit import build
from tests.wave110o_kit import (  # noqa: F401
    EXTRA,
    card_db,
    check,
    full,
    life,
    mana,
    now,
    put,
    settle,
    to_hand,
)

UNDERGROWTH = "Undergrowth"


@pytest.mark.parametrize("name", [UNDERGROWTH])
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
