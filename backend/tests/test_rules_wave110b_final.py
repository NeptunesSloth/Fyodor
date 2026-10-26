"""Wave 110B final pass (real Oracle text in tests/fixtures/wave110b_cards.json).

* Clandestine Chameleon: 613.1f / 123.2 it has the abilities of ability stickers on other permanents its owner owns and on cards in its owner's graveyard, and no others.
"""

from __future__ import annotations

import pytest

from app.game.state import StickerDefinition101, StickerPlacement101
from app.rules import coverage
from tests.game_helpers import act
from tests.wave110b_kit import build, card_named, ch, put, repository


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Clandestine Chameleon")).level == "FULL"


def at(s, name, zone, pid):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": zone})
    return c


def stick(s, c, text="Flying"):
    s.state.cards[c.id].stickers101.append(StickerPlacement101(sticker=StickerDefinition101(id=f"t{c.id}", kind="ability", cost=1, label=text, text=text), owner="p1"))


@pytest.mark.parametrize("zone,owner,flies", [("battlefield", "p1", True), ("graveyard", "p1", True), ("hand", "p1", False), ("battlefield", "p2", False)])
def test_chameleon_gets_sticker_abilities(cards, zone, owner, flies):
    s = build(cards, ["Clandestine Chameleon", "Grizzly Bears"], ["Grizzly Bears"])
    cham = put(s, "Clandestine Chameleon")
    bears = at(s, "Grizzly Bears", zone, owner)
    assert "flying" not in ch(s, cham).keywords
    stick(s, bears)
    assert ("flying" in ch(s, cham).keywords) is flies


def test_chameleon_ignores_its_own_and_others_unaffected(cards):
    s = build(cards, ["Clandestine Chameleon", "Grizzly Bears"])
    cham, bears = put(s, "Clandestine Chameleon"), put(s, "Grizzly Bears")
    stick(s, bears)
    assert "flying" in ch(s, cham).keywords and "flying" in ch(s, bears).keywords
    assert card_named(s, "Grizzly Bears").stickers101  # the Bears keep their sticker; the Chameleon only copies the ability
    assert not s.state.cards[cham.id].stickers101
