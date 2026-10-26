"""Wave 110C: Warp World (701.24a shuffle, 111.1 tokens aren't cards, 303.4f an Aura put onto the battlefield chooses what it enchants, 614.12a entering together,
401.4 owner orders the bottom). Rulings (Gatherer, 2009-10-01 / 2019-05-03): tokens and a commander that went to the command zone still count toward how many cards are
revealed, but a token is never revealed as a card. Same count rule as Glimpse of Tomorrow (2021-06-18)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, to_hand
from tests.wave110c_kit import answer, check, make_db, mana, put, real

WARP = ("Each player shuffles all permanents they own into their library, then reveals that many cards from the top of their library. Each player puts all artifact, "
        "creature, and land cards revealed this way onto the battlefield, then does the same for enchantment cards, then puts all cards revealed this way that weren't put "
        "onto the battlefield on the bottom of their library.")
EXTRA = [real("Warp World", "{5}{R}{R}{R}", 8, "Sorcery", WARP, None, "R"),
         real("Tok", "{W}", 1, "Sorcery", "Create two 1/1 white Soldier creature tokens.", None, "W")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Warp World")).level == "FULL"


def warp(s, *picks):
    to_hand(s, "Warp World")
    mana(s, R=3, C=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Warp World").id, targets=[])
    answer(s, *picks)


def zones(s, pid, zone):
    return sorted(c.name for c in s.state.cards.values() if c.zone == f"{pid}:{zone}" and not c.is_token)


def test_tokens_count_but_are_not_revealed_and_the_rest_goes_to_the_bottom(cards):
    """p1 owns Grizzly Bears and two tokens: 3 cards revealed = the whole library (Bears, Bolt, Counterspell); the instants go to the bottom."""
    s = build(cards, ["Warp World", "Tok", "Grizzly Bears", "Lightning Bolt", "Counterspell"], [], forests=0, islands=0)
    put(s, "Grizzly Bears")
    to_hand(s, "Tok")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Tok").id, targets=[])
    answer(s)
    assert sum(1 for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield") == 2
    warp(s)
    assert zones(s, "p1", "battlefield") == ["Grizzly Bears"]
    assert zones(s, "p1", "library") == ["Counterspell", "Lightning Bolt"]
    assert not [c for c in s.state.cards.values() if c.is_token]
    check(s)


def test_commander_that_goes_to_the_command_zone_still_counts_and_an_aura_enchants(cards):
    """p2's commander is replaced into the command zone (903.9b) yet counts, so p2 reveals Pacifism, which enters after p1's Bears and enchants it (303.4f)."""
    s = build(cards, ["Warp World", "Grizzly Bears"], ["Pacifism"], forests=0, islands=0)
    put(s, "Grizzly Bears")
    commander = next(c for c in s.state.cards.values() if c.owner == "p2" and c.name.startswith("Atraxa"))
    act(s, "p2", type="move", card_ids=[commander.id], to={"player": "p2", "zone": "battlefield"})
    warp(s, "yes")  # (903.9b: asked before the commander would go into the library)
    assert zones(s, "p1", "battlefield") == ["Grizzly Bears"] and zones(s, "p2", "battlefield") == ["Pacifism"]
    assert card_named(s, "Pacifism", "p2").attached_to == card_named(s, "Grizzly Bears").id
    check(s)
