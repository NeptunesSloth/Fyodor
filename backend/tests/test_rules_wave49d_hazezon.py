"""Wave 49D: Hazezon Tamar (CR 2026-09-25), real Oracle text (tests/fixtures/wave49d_small_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 603.7: "When Hazezon enters, create X 1/1 Sand Warrior creature tokens that are red, green, and white at the beginning of your next upkeep, where X is the
  number of lands you control at that time." - a delayed triggered ability; X is counted when it resolves, not when Hazezon entered. It doesn't matter if
  Hazezon is still on the battlefield then (his ruling).
* "When Hazezon leaves the battlefield, exile all Sand Warriors." - permanents with both creature types; a Warrior that isn't a Sand is unaffected.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave49d_small_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w49d", number=f"S{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def lands_in(s, n):
    """Move n more Forests from Alice's library to the battlefield."""
    for c in [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][:n]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})


def warriors(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Sand Warrior" and c.zone == "p1:battlefield"]


def cast_hazezon(s):
    to_hand(s, "Hazezon Tamar")
    mana(s, R=1, G=1, W=1, C=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Hazezon Tamar").id)
    settle(s)


def murder_hazezon(s):
    to_hand(s, "Murder")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[card_named(s, "Hazezon Tamar").id])
    settle(s)
    assert s.state.cards[card_named(s, "Hazezon Tamar").id].zone == "p1:graveyard"


def test_hazezon_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Hazezon Tamar")).level == "FULL"


def test_the_sand_warriors_count_the_lands_at_the_next_upkeep(cards):
    s = build(cards, ["Hazezon Tamar", "Murder"], [], forests=30)
    stops(s)
    lands_in(s, 3)
    cast_hazezon(s)
    assert not warriors(s)  # nothing yet: a delayed trigger
    lands_in(s, 2)  # two more lands before Alice's next upkeep: X counts them
    to_phase(s, "upkeep", turn=s.state.turn.number + 2)
    settle(s)
    made = warriors(s)
    assert len(made) == 5
    p = Plan(s.state, "p1", s.cards, None).ch(made[0])
    assert (p.colors, p.subtypes, str(p.power), str(p.toughness)) == (frozenset("RGW"), frozenset({"Sand", "Warrior"}), "1", "1")
    check(s)


def test_the_sand_warriors_come_even_if_hazezon_left(cards):
    s = build(cards, ["Hazezon Tamar", "Murder"], [], forests=30)
    stops(s)
    lands_in(s, 4)
    cast_hazezon(s)
    murder_hazezon(s)  # his second ability has nothing to exile yet
    to_phase(s, "upkeep", turn=s.state.turn.number + 2)
    settle(s)
    assert len(warriors(s)) == 4  # the ruling: they "remain on the battlefield indefinitely"
    check(s)


def test_hazezon_leaving_exiles_only_creatures_with_both_types(cards):
    s = build(cards, ["Hazezon Tamar", "Centaur Courser", "Murder"], [], forests=30)
    stops(s)
    lands_in(s, 2)
    cast_hazezon(s)
    courser = put(s, "Centaur Courser")  # a Warrior, no Sand
    to_phase(s, "upkeep", turn=s.state.turn.number + 2)
    settle(s)
    assert len(warriors(s)) == 2
    murder_hazezon(s)
    assert not warriors(s) and s.state.cards[courser.id].zone == "p1:battlefield"
    check(s)
