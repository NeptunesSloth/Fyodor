"""Wave 110N: Siren's Call (508.1d must attack, 603.7 the end step destruction of non-Wall creatures that did not attack and were controlled all turn)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

SIREN = "Siren's Call"
EXTRA = [
    real("Stone Wall", "{1}", 1, "Creature — Wall", "Defender", ("0", "4")),
    real("Sleepy Beast", "{2}", 2, "Creature — Beast", "Defender", ("2", "2")),
    real("Fresh Recruit", "{1}", 1, "Creature — Human", "", ("1", "1")),
]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([SIREN])


def bobs_upkeep(s):
    act(s, "p1", type="set_stops", own=STEPS + ["upkeep"], others=STEPS + ["upkeep"], smart_pass=False)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "upkeep" and s.state.rules.priority == "p1")


def play_turn(s, attackers):
    """Bob's turn 2 to its end step; his attack declaration is ``attackers``."""
    for _ in range(100):
        d = s.state.rules.decision
        if s.state.turn.phase == "end" and s.state.turn.number == 2:
            return
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[{"card_id": c, "target": "p1"} for c in attackers])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no end step")


def setup(cards):
    s = build(cards, [SIREN], ["Grizzly Bears", "Stone Wall", "Sleepy Beast", "Fresh Recruit"])
    ids = {n: put(s, n, "p2").id for n in ("Grizzly Bears", "Stone Wall", "Sleepy Beast")}  # (there since before Bob's turn begins)
    bobs_upkeep(s)
    cast(s, SIREN)
    answer(s)
    ids["Fresh Recruit"] = card_named(s, "Fresh Recruit", "p2").id  # it comes under his control after his turn began: Siren's Call ignores it
    act(s, "p2", type="move", card_ids=[ids["Fresh Recruit"]], to={"player": "p2", "zone": "battlefield"})
    return s, ids


def test_it_forces_the_attack_and_destroys_what_did_not_attack(cards):
    s, ids = setup(cards)
    stops(s)
    play_turn(s, [ids["Grizzly Bears"]])
    answer(s)
    where = {n: s.state.cards[c].zone for n, c in ids.items()}
    assert where == {"Grizzly Bears": "p2:battlefield", "Stone Wall": "p2:battlefield", "Sleepy Beast": "p2:graveyard", "Fresh Recruit": "p2:battlefield"}
    check(s)


def test_the_creatures_must_attack_if_able(cards):
    s, ids = setup(cards)
    stops(s)
    with pytest.raises(ActionError):
        play_turn(s, [])
    check(s)


def test_it_can_only_be_cast_on_an_opponents_turn_before_attackers(cards):
    s = build(cards, [SIREN])
    with pytest.raises(ActionError):  # Alice's own turn
        cast(s, SIREN)
    check(s)
