"""Canonical turn-dependent Bear form through native layers and gameplay."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_characteristic_recipes39 import ch
from tests.test_rules_declaration_requirements33 import cast, start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    data = json.loads((Path(__file__).parent / "fixtures/circle_moon_druid40_cards.json").read_text())
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(data):
        base[c["name"]] = card(
            c["name"], set_code="cm40", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return table(
        cards,
        ["Circle of the Moon Druid", "Humility", "Jump Scare", "Act of Aggression"],
        ["Circle of the Moon Druid", "Act of Aggression"],
        ["Circle of the Moon Druid"],
    )


def test_actual_cast_turns_counters(cards):
    s = setup(cards)
    start(s)
    c = cast(s, "Circle of the Moon Druid")
    assert ch(s, c).subtypes == {"Bear"} and ch(s, c).pt == (4, 2)
    act(s, "p1", type="counter", card_ids=[c.id], kind="+1/+1", delta=1)
    assert ch(s, c).pt == (5, 3)
    roundtrip(s)
    to_phase(s, "main1", turn=5)
    assert ch(s, c).subtypes == {"Human", "Elf", "Druid"} and ch(s, c).pt == (3, 5)
    roundtrip(s)


@pytest.mark.parametrize("circle_first", [False, True])
def test_humility_both_orders(cards, circle_first):
    s = setup(cards)
    start(s)
    if not circle_first:
        cast(s, "Humility")
    c = cast(s, "Circle of the Moon Druid")
    if circle_first:
        cast(s, "Humility")
    assert ch(s, c).subtypes == {"Bear"} and ch(s, c).pt == ((1, 1) if circle_first else (4, 2))
    roundtrip(s)


def test_later_native_type_grant_preserves_noncreature_types(cards):
    s = setup(cards)
    start(s)
    c = cast(s, "Circle of the Moon Druid")
    cast(s, "Jump Scare", [c.id], target_counts=[1])
    assert ch(s, c).types == {"Creature", "Enchantment"} and ch(s, c).subtypes == {"Bear", "Horror"}
    assert ch(s, c).pt == (6, 4) and "flying" in ch(s, c).keywords
    roundtrip(s)


def test_outside_battlefield_keeps_printed_values(cards):
    s = setup(cards)
    start(s)
    c = put(s, "Circle of the Moon Druid", "hand")
    assert ch(s, c).subtypes == {"Human", "Elf", "Druid"} and ch(s, c).pt == (2, 4)


def test_all_printed_lines_full(cards):
    assert coverage.of_card_data(cards.resolve("Circle of the Moon Druid")).level == "FULL"


def test_form_follows_current_controller_after_actual_control_spell(cards):
    s = setup(cards)
    start(s)
    c = cast(s, "Circle of the Moon Druid")
    cast(s, "Act of Aggression", [c.id], pid="p2", target_counts=[1], life_symbols=[])
    assert s.state.cards[c.id].controller == "p2"
    assert ch(s, c).subtypes == {"Human", "Elf", "Druid"} and ch(s, c).pt == (2, 4)
    roundtrip(s)
    to_phase(s, "main1", turn=5)
    assert s.state.cards[c.id].controller == "p1"
    cast(s, "Act of Aggression", [c.id], pid="p2", target_counts=[1], life_symbols=[])
    assert s.state.cards[c.id].controller == "p2"
    assert ch(s, c).subtypes == {"Bear"} and ch(s, c).pt == (4, 2)
    roundtrip(s)
