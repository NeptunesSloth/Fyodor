"""Wave 110C: Ravenous Slime (614.6 an opponent's dying creature is exiled instead; its power as it died, 608.2h, becomes +1/+1 counters on the Slime)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave45b_dungeons import drive
from tests.wave110c_kit import build, check, make_db, mana, put, real, to_hand

EXTRA = [real("Ravenous Slime", "{1}{G}{G}", 3, "Creature — Ooze",
              "This creature can't be blocked by creatures with power 2 or less.\nIf a creature an opponent controls would die, instead exile it and put a number of "
              "+1/+1 counters equal to that creature's power on this creature.", ("2", "2"), "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Ravenous Slime")).level == "FULL"


@pytest.mark.parametrize("victim,mine", [("p2", True), ("p1", False)])
def test_counters_only_for_opponent_creature(cards, victim, mine):
    s = build(cards, ["Ravenous Slime", "Lightning Bolt", "Grizzly Bears"], ["Grizzly Bears"])
    slime = put(s, "Ravenous Slime")
    bears = put(s, "Grizzly Bears", victim)
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[bears.id])
    drive(s)
    assert s.state.cards[bears.id].zone == ("p2:exile" if mine else "p1:graveyard")
    assert s.state.cards[slime.id].counters.get("+1/+1", 0) == (2 if mine else 0)
    check(s)
