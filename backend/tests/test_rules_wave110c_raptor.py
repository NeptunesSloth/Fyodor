"""Wave 110C: Amped Raptor. 107.14: {E}{E} as it enters; only if it was cast from the hand, exile cards from the top until a nonland card (701.20), which may be cast by paying
{E} equal to its mana value instead of its mana cost (118.9, 601.2b-h): not castable when the energy falls short."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_refused_look import stack_library
from tests.wave9c_kit import build
from tests.wave110c_kit import answer, check, make_db, mana, put, real, to_hand

RAPTOR = ("First strike\nWhen this creature enters, you get {E}{E} (two energy counters). Then if you cast it from your hand, exile cards from the top of your library until "
          "you exile a nonland card. You may cast that card by paying an amount of {E} equal to its mana value rather than paying its mana cost.")
EXTRA = [real("Amped Raptor", "{1}{R}", 2, "Creature — Dinosaur", RAPTOR, ("3", "1"), "R"),
         real("Two Drop", "{1}{G}", 2, "Creature — Test", "", ("2", "2"), "G"),
         real("Reanimate Test", "{B}", 1, "Sorcery", "Return target creature card from your graveyard to the battlefield.", None, "B"),
         real("Three Drop", "{3}", 3, "Creature — Test", "", ("1", "1"), "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Amped Raptor")).level == "FULL"


def energy(s):
    return s.state.players["p1"].resources.get("energy", 0)


def play(cards, top, from_hand=True):
    s = build(cards, ["Amped Raptor", "Two Drop", "Three Drop", "Reanimate Test"])
    ids = stack_library(s, top)
    if from_hand:
        mana(s, R=1, C=1)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Amped Raptor").id)
    else:
        raptor = to_hand(s, "Amped Raptor")
        act(s, "p1", type="move", card_ids=[raptor.id], to={"player": "p1", "zone": "graveyard"})
        mana(s, B=1)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Reanimate Test").id, targets=[raptor.id])  # (returned, not cast)
    return s, ids


def finish(s, cast_it):
    """Resolve to the offer, then cast the exiled card (``cast_it``) or leave it."""
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1] if cast_it else [])
        elif s.state.rules.stack:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def test_cast_from_hand_exiles_to_a_nonland_and_pays_energy_equal_to_its_mana_value(cards):
    s, ids = play(cards, ["Forest", "Two Drop", "Three Drop"])
    finish(s, True)
    assert s.state.cards[ids[1]].zone == "p1:battlefield" and energy(s) == 0
    assert s.state.cards[ids[0]].zone == "p1:exile"  # (the land stays exiled)
    check(s)


def test_a_card_costing_more_energy_than_you_have_cannot_be_cast(cards):
    s, ids = play(cards, ["Three Drop", "Two Drop"])
    finish(s, True)
    assert s.state.cards[ids[0]].zone == "p1:exile" and energy(s) == 2
    check(s)


def test_not_cast_from_hand_only_gets_energy(cards):
    s, ids = play(cards, ["Two Drop"], from_hand=False)
    finish(s, True)
    assert s.state.cards[ids[0]].zone == "p1:library" and energy(s) == 2  # (the energy came, the look did not)
    check(s)
