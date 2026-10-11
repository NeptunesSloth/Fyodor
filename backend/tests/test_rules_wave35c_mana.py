"""Wave 35C: unspent mana (CR 500.4, 614.1a, 106.4, 106.6, 616.1), real Oracle text (tests/fixtures/wave35c_cards.json). Every scenario checks the replay and
a save and a load.

* "If you would lose unspent mana, that mana becomes colorless instead." (Kruphix, God of Horizons; Omnath, Locus of the Void; Horizon Stone): as a step or
  phase ends the pool stays, colorless; restrictions and riders stay with the mana (Gatherer rulings); once the permanent leaves, the mana is lost as usual.
  Two such effects agree on what happens, so there is no 616.1 order to ask. Mana an effect keeps (106.4) is kept as it was.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, until
from tests.wave9c_kit import build, check, mana, put, reloaded
from tests.wave35c_kit import cards, pool  # noqa: F401


@pytest.mark.parametrize("name", ["Kruphix, God of Horizons", "Omnath, Locus of the Void", "Horizon Stone"])
def test_the_promoted_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_kruphix_keeps_the_pool_colorless_across_steps_and_turns(cards):
    s = build(cards, ["Kruphix, God of Horizons"], [])
    put(s, "Kruphix, God of Horizons")
    mana(s, "p1", R=2, G=1, C=1)
    act(s, "p1", type="pass_priority")  # main 1 → main 2: the step ends, the mana would be lost
    assert pool(s) == {"C": 4}
    s = reloaded(s)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    assert pool(s) == {"C": 4}  # still there on the next turn
    check(s)


def test_the_pool_is_lost_as_usual_without_a_source_and_two_sources_ask_nothing(cards):
    s = build(cards, ["Kruphix, God of Horizons", "Horizon Stone"], [])
    mana(s, "p1", R=3)
    act(s, "p1", type="pass_priority")
    assert pool(s) == {}  # nothing keeps it
    kruphix, stone = put(s, "Kruphix, God of Horizons"), put(s, "Horizon Stone")
    mana(s, "p1", W=2)
    act(s, "p1", type="pass_priority")  # → Bob's turn: two replacements, one result, no question (616.1)
    assert pool(s) == {"C": 2} and s.state.rules.decision is None
    act(s, "p1", type="move", card_ids=[kruphix.id, stone.id], to={"zone": "graveyard"})
    mana(s, "p1", U=1)
    act(s, s.state.rules.priority, type="pass_priority")  # (Bob's main phase ends)
    assert pool(s) == {}  # both gone: lost as usual (500.4)
    check(s)


def test_an_opponents_effect_does_nothing_for_your_pool(cards):
    s = build(cards, [], ["Horizon Stone"])
    put(s, "Horizon Stone", "p2")
    mana(s, "p1", B=2)
    mana(s, "p2", B=2)
    act(s, "p1", type="pass_priority")
    assert pool(s, "p1") == {} and pool(s, "p2") == {"C": 2}
    check(s)


def test_restricted_mana_stays_restricted_when_it_becomes_colorless(cards):
    """The Gatherer rulings: a restriction stays with the mana. Ancient Ziggurat's green mana (creature spells only) is colorless creature-only mana, and
    unrestricted mana of other colors stays too."""
    s = build(cards, ["Omnath, Locus of the Void", "Ancient Ziggurat"], [])
    put(s, "Omnath, Locus of the Void")
    ziggurat = put(s, "Ancient Ziggurat")
    s.state.rules.controlled_since[ziggurat.id].turn = 0
    act(s, "p1", type="activate_ability", card_id=ziggurat.id, ability=0, mana_choice="G")
    settle(s)
    units = s.state.players["p1"].mana_units
    assert [(u.sym, bool(u.only)) for u in units] == [("G", True)]
    mana(s, "p1", R=1)
    act(s, "p1", type="pass_priority")
    units = s.state.players["p1"].mana_units
    assert [(u.sym, bool(u.only)) for u in units] == [("C", True)] and pool(s) == {"C": 1}
    s = reloaded(s)
    assert [(u.sym, bool(u.only)) for u in s.state.players["p1"].mana_units] == [("C", True)]
    check(s)
