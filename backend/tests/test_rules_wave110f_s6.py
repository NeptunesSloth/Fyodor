"""Wave 110F session 6: promotions on real Oracle text (replay and save/load via tests/wave9c_kit.check).

* 123.2, 603.4, 113.6k: "Whenever you put an art/name sticker on a creature, you may return this card from your graveyard to your hand." (Unlawful Entry, A Good Day to Pie).
"""

from __future__ import annotations

import pytest

from app.cards.repository import CardRepository  # noqa: F401
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.sticker_sheets101 import SHEETS
from tests.game_helpers import act, deck, enable
from tests.test_rules_sticker_effects101 import (  # noqa: F401  (cards: the fixture DB with the sticker cards)
    FixedSheetRng,
    cards,
    cast,
    pick,
    place,
    question,
)
from tests.test_rules_designations import find, put
from tests.wave100c_kit import settle, to_phase
from tests.wave9c_kit import check

SPELLS = ["Unlawful Entry", "A Good Day to Pie"]


def start(cards):
    names = ["Grizzly Bears", "Sol Ring", "Ticketomaton", *SPELLS]
    mine = deck(cards, "Krenko, Mob Boss", [(30, "Forest"), *((1, n) for n in names)])
    mine += [DeckCard("stickers", 1, s["name"], s["printing_id"]) for s in list(SHEETS.values())[:10]]
    other = deck(cards, "Atraxa, Praetors' Voice", [(30, "Island"), (1, "Grizzly Bears")])
    state = enable(new_game([PlayerSetup("Alice", cards=mine), PlayerSetup("Bob", cards=other)], shuffle=False, rng=FixedSheetRng()))
    s = GameSession(state, cards=cards)
    for pid in state.players:
        act(s, pid, type="set_prefs", response="on")
    to_phase(s, "main1", 1)
    return s


@pytest.mark.parametrize("name", SPELLS)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name,kind,zone,returns,target", [
    ("Unlawful Entry", "art", "graveyard", True, "Grizzly Bears"), ("Unlawful Entry", "name", "graveyard", False, "Grizzly Bears"), ("Unlawful Entry", "art", "hand", False, "Grizzly Bears"),
    ("A Good Day to Pie", "name", "graveyard", True, "Grizzly Bears"), ("A Good Day to Pie", "art", "graveyard", False, "Grizzly Bears"),
    ("Unlawful Entry", "art", "graveyard", False, "Sol Ring")])  # (a sticker on a non-creature does not trigger it)
def test_sticker_on_creature_returns_the_spell_from_graveyard(cards, name, kind, zone, returns, target):
    """Only the matching sticker kind, and only from the graveyard: Ticketomaton puts the sticker on a Bear."""
    s = start(cards)
    bear = put(s, target, "battlefield")
    put(s, name, zone)
    cast(s, "Ticketomaton")
    place(s, bear.id, kind=kind)
    for _ in range(10):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            pick(s, [d.options[0].id])
    assert (find(s, name).zone == "p1:hand") is (returns or zone == "hand")
    check(s)
