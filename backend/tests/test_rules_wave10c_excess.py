"""Wave 10C: excess damage from deathtouch / wither sources (CR 2026-09-25).

* 120.4a: "Any amount of damage greater than 1 is excess damage if the source dealing that damage to a creature has deathtouch";
  702.2c: any nonzero deathtouch damage is lethal for excess.
* 120.3d: wither damage is the same damage, dealt as -1/-1 counters: lethal damage is unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave9b_excess import EXTRA, cast, count
from tests.test_rules_wave9b_exile_permission import build, find, put, roundtrip


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def _slice(cards, text, marked=0):
    s = build(cards, p1=("Windswift Slice",), p2=("Grizzly Bears",))
    act(s, "p1", type="create_token", player="p1", token={"name": "Brute", "type_line": "Token Creature — Test", "power": "4",
                                                         "toughness": "4", "text": text})
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    if marked:
        act(s, "p1", type="set_damage", card_ids=[bears.id], value=marked)
    cast(s, "Windswift Slice", [find(s, "Brute").id, bears.id], counts=[1, 1], R=0, G=3)
    return s, bears


def test_plain_source_baseline(cards):
    s, bears = _slice(cards, "")
    assert count(s, "Elf Warrior") == 2  # 4 damage against a 2/2
    roundtrip(s)


def test_deathtouch_damage_beyond_one_is_excess(cards):
    s, bears = _slice(cards, "Deathtouch")
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    assert count(s, "Elf Warrior") == 3  # all but 1 of the 4
    roundtrip(s)


def test_wither_is_ordinary_damage_for_excess(cards):
    s, bears = _slice(cards, "Wither")
    assert count(s, "Elf Warrior") == 2  # 4 damage as -1/-1 counters; lethal damage is still 2
    roundtrip(s)
