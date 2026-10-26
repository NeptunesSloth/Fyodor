"""Wave 110K: Scampire (real Oracle text, tests/fixtures/wave110k_cards.json). Every scenario checks the replay and a save and a load.

* 123.4, 602.2: its activated ability returns only a creature card in your graveyard that has a sticker on it (a sticker put on a card in a graveyard stays
  on it), gives it haste and exiles it at the beginning of the next end step; only as a sorcery.
"""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.rules import coverage
from app.rules.sticker_sheets101 import SHEETS
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_sticker_effects101 import FixedSheetRng, pick, place, question
from tests.wave9c_kit import check
from tests.wave100c_kit import chars, move, one, settle, to_phase, zone
from tests.wave110k_kit import DATA


@pytest.fixture()
def cards(settings):
    data = next(c for c in DATA if c["name"] == "Scampire")
    rows = {c["name"]: c for c in fixture_cards()}
    rows[data["name"]] = card(data["name"], set_code="w110k", number="S001", **{k: v for k, v in data.items() if k != "name"})
    settings.ensure_dirs()
    build_database(rows.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def table(cards):
    from app.game.factory import DeckCard, PlayerSetup, new_game

    mine = deck(cards, "Krenko, Mob Boss", [(30, "Forest"), (1, "Scampire"), (1, "Grizzly Bears"), (1, "Llanowar Elves")])
    selected = [s for name in ("Eldrazi Guacamole Tightrope", "Ancestral Hot Dog Minotaur", "Trendy Circus Pirate") for s in SHEETS.values() if s["name"] == name]
    mine += [DeckCard("stickers", 1, s["name"], s["printing_id"]) for s in selected]
    other = deck(cards, "Atraxa, Praetors' Voice", [(30, "Island")])
    state = enable(new_game([PlayerSetup("Alice", cards=mine), PlayerSetup("Bob", cards=other)], shuffle=False, rng=FixedSheetRng()))
    s = GameSession(state, cards=cards)
    for pid in state.players:
        act(s, pid, type="set_prefs", response="on")
    to_phase(s, "main1", 1)
    return s


def stickered(s):
    """Scampire cast with Grizzly Bears and Llanowar Elves in the graveyard, an art sticker put on the Bears."""
    bears, elves = one(s, "Grizzly Bears"), one(s, "Llanowar Elves")
    move(s, bears, "graveyard")
    move(s, elves, "graveyard")
    scampire = one(s, "Scampire")
    move(s, scampire, "hand")
    act(s, "p1", type="add_mana", player="p1", mana={c: 20 for c in ("C", "W", "U", "B", "R", "G")})
    act(s, "p1", type="cast_spell", card_id=scampire.id)
    place(s, bears.id)
    settle(s)
    return scampire, bears, elves


def test_scampire_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Scampire")).level == "FULL"


def test_scampire_returns_only_a_stickered_creature_card_with_haste_and_exiles_it_at_the_end(cards):
    s = table(cards)
    scampire, bears, elves = stickered(s)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3, "B": 1})
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=scampire.id, ability=1, targets=[elves.id])
    act(s, "p1", type="activate_ability", card_id=scampire.id, ability=1, targets=[bears.id])
    settle(s)
    assert zone(s, bears) == "p1:battlefield" and "haste" in chars(s, bears).keywords and zone(s, elves) == "p1:graveyard"
    to_phase(s, "end", 1)
    settle(s)
    assert zone(s, bears) == "p1:exile"
    check(s)
