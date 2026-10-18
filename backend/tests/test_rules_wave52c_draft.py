"""Wave 52C: draft-matters cards (CR 905.2), real Oracle text (tests/fixtures/wave52c_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 905.2: "Some cards have abilities that function during the draft": "Draft this card face up.", "Reveal this card as you draft it.", "As you draft a card, …" do nothing in a game, which
  no draft precedes; the rest of the card is played as printed. A line that reads what a draft would have noted ("the highest number you noted") is not read: Pyretic Hunter and
  Regicide stay partial.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of
from tests.wave52c_kit import drive, move, next_turn, open_repo

FULL = ["Canal Dredger", "Deal Broker", "Cogwork Librarian", "Cogwork Spy", "Lore Seeker", "Archdemon of Paliano", "Illusionary Informant", "Whispergear Sneak",
        "Agent of Acquisitions", "Leovold's Operative", "Animus of Predation", "Cogwork Tracker", "Noble Banneret", "Paliano Vanguard"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", FULL)
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


@pytest.mark.parametrize("name", ["Pyretic Hunter", "Regicide"])
def test_what_a_draft_would_have_noted_is_not_read(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level != "FULL", name


def test_a_draft_creature_is_cast_and_its_own_ability_works(cards):
    s = build(cards, ["Canal Dredger", "Cogwork Spy", "Grizzly Bears"])
    to_hand(s, "Cogwork Spy")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Cogwork Spy").id)
    drive(s)
    assert zone_of(s, "Cogwork Spy") == "p1:battlefield"
    dredger = put(s, "Canal Dredger")
    bears = move(s, "Grizzly Bears", "graveyard")
    next_turn(s)  # (summoning sickness, 302.6)
    act(s, "p1", type="activate_ability", card_id=dredger.id, ability=2, targets=[bears.id])
    drive(s)
    assert zone_of(s, "Grizzly Bears") == "p1:library"  # "Put target card from your graveyard on the bottom of your library."
    assert s.state.zones["p1:library"][-1] == bears.id
    check(s)
