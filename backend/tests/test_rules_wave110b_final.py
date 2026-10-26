"""Wave 110B final pass (real Oracle text in tests/fixtures/wave110b_cards.json).

* Clandestine Chameleon: 613.1f / 123.2 it has the abilities of ability stickers on other permanents its owner owns and on cards in its owner's graveyard, and no others.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.state import StickerDefinition101, StickerPlacement101
from app.rules import coverage
from tests.game_helpers import act
from tests.wave110b_kit import build, card_named, ch, check, mana, put, repository, settle


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["Clandestine Chameleon", "Ichor Elixir"])  # Ichor Elixir: 901.3, 901.9 planar dice are Planechase-only; none is rolled in Commander
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


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


BRINK = "Back from the Brink"


@pytest.mark.parametrize("name", [BRINK])
def test_brink_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def to_gy(s, name, pid="p1"):
    return at(s, name, "graveyard", pid)


def brink_ability(s, c):
    return next((a.index for a in ch(s, c).abilities if "Exile this card from your graveyard" in a.text and "token" in a.text), None)


def tokens(s, name):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.zone == "p1:battlefield"]


def activate(s, c):
    act(s, "p1", type="activate_ability", card_id=c.id, ability=brink_ability(s, c))
    settle(s)


def test_brink_exile_and_pay_mana_cost_makes_a_token_copy(cards):
    """602.2b the exile is part of the cost; 118.1 the mana cost is paid (not cast); 707.2 a token copy that has the card's characteristics; opponents' graveyards are not used."""
    s = build(cards, ["Back from the Brink", "Hill Giant", "Endless One"], ["Hill Giant"])
    put(s, BRINK)
    giant, one, theirs = to_gy(s, "Hill Giant"), to_gy(s, "Endless One"), to_gy(s, "Hill Giant", "p2")
    settle(s)
    assert brink_ability(s, theirs) is None and brink_ability(s, giant) is not None
    mana(s, R=1, C=3)
    activate(s, giant)
    assert s.state.cards[giant.id].zone == "p1:exile"
    assert len(tokens(s, "Hill Giant")) == 1 and "Creature" in ch(s, tokens(s, "Hill Giant")[0]).types
    assert not s.state.players["p1"].mana or sum(s.state.players["p1"].mana.values()) == 0
    check(s)


def test_brink_x_in_mana_cost_is_zero_and_needs_the_mana(cards):
    """Ruling 2011-09-22: X is 0 in the cost paid (Endless One costs {0}); without the mana the activation is refused."""
    s = build(cards, ["Back from the Brink", "Hill Giant", "Endless One"], [])
    put(s, BRINK)
    giant, one = to_gy(s, "Hill Giant"), to_gy(s, "Endless One")
    settle(s)
    with pytest.raises(ActionError):
        activate(s, giant)  # (no mana)
    assert s.state.cards[giant.id].zone == "p1:graveyard"
    activate(s, one)
    assert s.state.cards[one.id].zone == "p1:exile" and not tokens(s, "Endless One")  # (the 0/0 token copy dies at once: X is 0 for the copy too)
    assert any("token" in "".join(x.t or "" for x in e.parts).lower() for e in s.state.log[-8:])
    check(s)


def test_brink_double_faced_card_pays_front_face_cost_and_copies_front_face(cards):
    """Ruling 2011-09-22: a double-faced creature card exiled this way costs its front face's mana cost and the token is a copy of the front face."""
    s = build(cards, ["Back from the Brink", "Delver of Secrets // Insectile Aberration"], [])
    put(s, BRINK)
    delver = to_gy(s, "Delver of Secrets // Insectile Aberration")
    settle(s)
    assert brink_ability(s, delver) is not None
    mana(s, U=1)
    activate(s, delver)
    assert s.state.cards[delver.id].zone == "p1:exile" and len(tokens(s, "Delver of Secrets")) == 1
    check(s)
