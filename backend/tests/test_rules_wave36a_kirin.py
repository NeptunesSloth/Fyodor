"""Wave 36A: "with that spell's mana value" (Celestial Kirin, Infernal Kirin), researched against CR 2026-09-25, real Oracle text
(tests/fixtures/wave36a_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 603.2, 601.2i: the trigger happens as the spell becomes cast and goes on the stack above it, so it resolves first, while the spell is still on
  the stack; "that spell's mana value" is read from the spell on the stack (202.3e: the X chosen for it counts), as the ability goes on the stack.
* 701.20e, 400.1: "reveals their hand" shows the whole hand (a public look), and "discards all cards with …" picks the cards of that value from it (701.9a).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import build, card_named, cast, check, mana, put, to_hand
from tests.wave36a_kit import offered, pick, zone

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave36a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w36a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Celestial Kirin", "Infernal Kirin"])
def test_the_kirins_are_full(name):
    from tests.test_rules_scripts import ch as characteristics

    c = next(c for c in DATA if c["name"] == name)
    chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
    assert coverage.of_characteristics(chs).level == "FULL", (name, coverage.of_characteristics(chs).manual_parts)


def test_celestial_kirin_destroys_every_permanent_with_the_value_of_the_spell_cast(cards):
    """Reach Through Mists (an Arcane spell, mana value 1): every permanent with mana value 1 goes, whoever controls it; the Kirin (4), the
    Bears (2) and a land (0) stay; the spell is still on the stack when the trigger resolves, and then resolves itself."""
    s = build(cards, ["Celestial Kirin", "Reach Through Mists", "Llanowar Elves", "Grizzly Bears"], theirs=["Llanowar Elves", "Grizzly Bears"], forests=20)
    put(s, "Celestial Kirin")
    put(s, "Llanowar Elves")
    put(s, "Grizzly Bears")
    put(s, "Llanowar Elves", "p2")
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Reach Through Mists")
    mana(s, U=1)
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Reach Through Mists")
    assert zone(s, "Llanowar Elves") == "p1:graveyard" and zone(s, "Llanowar Elves", "p2") == "p2:graveyard"
    assert zone(s, "Grizzly Bears") == "p1:battlefield" and zone(s, "Grizzly Bears", "p2") == "p2:battlefield"
    assert zone(s, "Celestial Kirin") == "p1:battlefield"
    assert zone(s, "Reach Through Mists") == "p1:graveyard" and len(s.state.zones["p1:hand"]) == hand  # (it resolved: -1 for casting, +1 drawn)
    check(s)


def test_celestial_kirin_ignores_a_spell_that_is_neither_a_spirit_nor_an_arcane(cards):
    s = build(cards, ["Celestial Kirin", "Opt", "Llanowar Elves"], forests=20)
    put(s, "Celestial Kirin")
    put(s, "Llanowar Elves")
    to_hand(s, "Opt")
    mana(s, U=1)
    cast(s, "Opt")
    settle(s)
    assert zone(s, "Llanowar Elves") == "p1:battlefield"
    check(s)


def test_infernal_kirin_makes_the_target_player_discard_the_cards_of_that_value(cards):
    s = build(cards, ["Infernal Kirin", "Reach Through Mists"], theirs=["Llanowar Elves", "Grizzly Bears", "Young Wolf"], forests=20)
    put(s, "Infernal Kirin")
    to_hand(s, "Llanowar Elves", "p2")
    to_hand(s, "Grizzly Bears", "p2")
    to_hand(s, "Young Wolf", "p2")
    to_hand(s, "Reach Through Mists")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Reach Through Mists").id)
    assert offered(s) == ["Alice", "Bob"]  # (target player)
    pick(s, "Bob")
    settle(s)
    assert zone(s, "Llanowar Elves", "p2") == "p2:graveyard" and zone(s, "Grizzly Bears", "p2") == "p2:hand" and zone(s, "Young Wolf", "p2") == "p2:graveyard"
    check(s)
