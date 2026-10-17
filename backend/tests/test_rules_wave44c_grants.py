"""Wave 44C (graveyard keyword grants): commanders one static line short of FULL (CR 2026-09-25), real Oracle text (tests/fixtures/wave44c_cards.json).
Every scenario checks the replay and a save and a load.

* 702.133a, 113.6m: "Each instant and sorcery card in your graveyard that's exactly two colors has jump-start." (Niv-Mizzet, Supreme [13516]) - a two-color card only, from
  the graveyard, discarding a card; the card is exiled after it.
* 702.97a, 113.6m: "Each creature card in your graveyard has scavenge. The scavenge cost is equal to its mana cost." (Varolz, the Scar-Striped [12829]) - your graveyard's creature
  cards only; the counters are its power as it last existed.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, settle
from tests.wave44c_kit import DATA, ch, life, open_cards
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", ["Niv-Mizzet, Supreme", "Varolz, the Scar-Striped"])
def test_coverage_full(cards, name):
    data = next(c for c in DATA if c["name"] == name)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or [data], "oracle_id": name}).level == "FULL"


def to_graveyard(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})
    return c


# ---- Niv-Mizzet, Supreme [13516] ----------------------------------------------------------------------------------------------------------------------
def test_niv_mizzet_lets_a_two_color_instant_be_cast_from_the_graveyard_and_exiles_it(cards):
    s = build(cards, ["Niv-Mizzet, Supreme", "Lightning Helix", "Hill Giant"], [])
    put(s, "Niv-Mizzet, Supreme")
    helix = to_graveyard(s, "Lightning Helix")
    discard = to_hand(s, "Hill Giant")
    mana(s, R=1, W=1)
    act(s, "p1", type="cast_spell", card_id=helix.id, targets=["p2"])
    settle(s)
    assert life(s, "p2") == 40 - 3 and life(s, "p1") == 40 + 3
    assert zone_of(s, "Lightning Helix") == "p1:exile" and zone_of(s, "Hill Giant") == "p1:graveyard" and s.state.cards[discard.id].zone == "p1:graveyard"  # jump-start's discard
    check(s)


def test_niv_mizzet_gives_nothing_to_a_one_color_instant_nor_without_it(cards):
    s = build(cards, ["Niv-Mizzet, Supreme", "Lightning Bolt", "Lightning Helix", "Hill Giant"], [])
    put(s, "Niv-Mizzet, Supreme")
    bolt = to_graveyard(s, "Lightning Bolt")
    helix = to_graveyard(s, "Lightning Helix")
    to_hand(s, "Hill Giant")
    mana(s, R=2, W=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])  # one color: no jump-start
    act(s, "p1", type="move", card_ids=[card_named(s, "Niv-Mizzet, Supreme").id], to={"zone": "graveyard"})
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=helix.id, targets=["p2"])  # the static is gone with its source
    check(s)


# ---- Varolz, the Scar-Striped [12829] -----------------------------------------------------------------------------------------------------------------
def test_varolz_gives_a_creature_card_in_your_graveyard_scavenge_at_its_mana_cost(cards):
    s = build(cards, ["Varolz, the Scar-Striped", "Hill Giant", "Grizzly Bears"], [])
    put(s, "Varolz, the Scar-Striped")
    giant = to_graveyard(s, "Hill Giant")  # {3}{R}, 3/3
    bears = put(s, "Grizzly Bears")
    settle(s)
    assert any("Exile this card from your graveyard" in a.text for a in ch(s, giant).abilities)
    mana(s, R=1, C=3)
    activate(s, "p1", giant, "Exile this card from your graveyard", targets=[bears.id])
    settle(s)
    assert zone_of(s, "Hill Giant") == "p1:exile"
    assert s.state.cards[bears.id].counters.get("+1/+1") == 3  # the Giant's power as it last existed
    check(s)


def test_varolz_gives_scavenge_to_no_creature_card_of_an_opponent_nor_to_a_noncreature_card(cards):
    s = build(cards, ["Varolz, the Scar-Striped", "Lightning Bolt", "Grizzly Bears"], ["Hill Giant"])
    put(s, "Varolz, the Scar-Striped")
    giant = to_graveyard(s, "Hill Giant", "p2")
    bolt = to_graveyard(s, "Lightning Bolt")
    bears = put(s, "Grizzly Bears")
    settle(s)
    for c in (giant, bolt):
        assert not any("Exile this card from your graveyard" in a.text for a in ch(s, c).abilities)
    assert bears.id in s.state.cards
    check(s)
