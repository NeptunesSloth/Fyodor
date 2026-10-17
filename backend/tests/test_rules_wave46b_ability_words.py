"""Wave 46B: ability-word lines whose rest was unread (CR 2026-09-25, real Oracle text, tests/fixtures/wave46b_cards.json). Every scenario checks the replay and a save
and a load.

* 207.2c: an ability word has no rules meaning; "Lieutenant —" / "Threshold —" lines are read as the plain text after them. The words were never the problem:
  the rest of the line was.
* 604.1 / 611.3a: "As long as you control your commander, this creature gets +2/+2 and other creatures you control get +2/+2 and have trample." is two static
  effects of the one permanent, each applying while the condition holds (Thunderfoot Baloth, Angelic Field Marshal).
* 509.1c: "Threshold — As long as there are seven or more cards in your graveyard, all creatures able to block this creature do so." is the lure requirement while
  the graveyard has seven or more cards, on the creature itself (Stone-Tongue Basilisk) or on the creature the Aura enchants (Seton's Desire).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave38a_trailing_ifs import table
from tests.wave9c_kit import card_named, check, mana, pt, put, to_hand
from tests.wave36a_kit import resolve_stack
from tests.wave46b_kit import make_repo


@pytest.fixture()
def cards(settings):
    repo = make_repo(settings)
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Thunderfoot Baloth", "Angelic Field Marshal", "Stone-Tongue Basilisk", "Seton's Desire"])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def ch(s, name, pid="p1"):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id])


def test_thunderfoot_baloth_pumps_itself_and_the_others_only_with_the_commander(cards):
    s = table(cards, ["Thunderfoot Baloth", "Grizzly Bears"])
    put(s, "Thunderfoot Baloth")
    put(s, "Grizzly Bears")
    baloth_before = pt(s, "Thunderfoot Baloth")
    assert pt(s, "Grizzly Bears") == (2, 2) and "trample" not in {k.lower() for k in ch(s, "Grizzly Bears").keywords}
    put(s, "Krenko, Mob Boss")
    assert pt(s, "Thunderfoot Baloth") == (baloth_before[0] + 2, baloth_before[1] + 2)
    assert pt(s, "Grizzly Bears") == (4, 4) and "trample" in {k.lower() for k in ch(s, "Grizzly Bears").keywords}
    check(s)


def test_angelic_field_marshal_gives_creatures_vigilance_with_the_commander(cards):
    s = table(cards, ["Angelic Field Marshal", "Grizzly Bears"])
    put(s, "Angelic Field Marshal")
    put(s, "Grizzly Bears")
    assert "vigilance" not in {k.lower() for k in ch(s, "Grizzly Bears").keywords}
    before = pt(s, "Angelic Field Marshal")
    put(s, "Krenko, Mob Boss")
    assert "vigilance" in {k.lower() for k in ch(s, "Grizzly Bears").keywords}
    assert pt(s, "Angelic Field Marshal") == (before[0] + 2, before[1] + 2) and pt(s, "Grizzly Bears") == (2, 2)
    check(s)


def fill_graveyard(s, n, pid="p1"):
    for cid in list(s.state.zones[f"{pid}:library"])[:n]:
        act(s, pid, type="move", card_ids=[cid], to={"zone": "graveyard"})


def test_stone_tongue_basilisk_forces_blocks_only_with_seven_cards_in_the_graveyard(cards):
    s = table(cards, ["Stone-Tongue Basilisk"])
    put(s, "Stone-Tongue Basilisk")
    fill_graveyard(s, 6)
    assert "lure" not in ch(s, "Stone-Tongue Basilisk").imposed
    fill_graveyard(s, 1)
    assert "lure" in ch(s, "Stone-Tongue Basilisk").imposed
    check(s)


def test_seton_desire_lures_the_enchanted_creature_at_threshold(cards):
    s = table(cards, ["Seton's Desire", "Grizzly Bears"])
    put(s, "Grizzly Bears")
    to_hand(s, "Seton's Desire")
    fill_graveyard(s, 7)
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Seton's Desire").id, targets=[card_named(s, "Grizzly Bears").id])
    resolve_stack(s)
    assert pt(s, "Grizzly Bears") == (4, 4) and "lure" in ch(s, "Grizzly Bears").imposed
    act(s, "p1", type="move", card_ids=[s.state.zones["p1:graveyard"][0]], to={"zone": "exile"})
    assert "lure" not in ch(s, "Grizzly Bears").imposed  # (six cards left; Seton's Desire isn't in it)
    check(s)
