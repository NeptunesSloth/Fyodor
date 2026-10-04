"""Wave 18E (casting extras). Real Oracle text, replay and save/load for each.

* 702.42a: entwine — "Choose both if you pay the entwine cost" (paid as kicker is: ``CastSpell.kicker`` = 1).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card("Rain of Rust", set_code="tst", number="D01", mana_cost="{3}{R}{R}", cmc=5.0, type_line="Instant", colors=["R"],
         color_identity=["R"], oracle_text="Choose one —\n• Destroy target artifact.\n• Destroy target land.\nEntwine {3}{R} "
         "(Choose both if you pay the entwine cost.)"),
    card("Test Relic", set_code="tst", number="D02", mana_cost="{2}", cmc=2.0, type_line="Artifact", oracle_text=""),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_entwine_chooses_both_modes_for_the_entwine_cost(cards):
    s = build(cards, p1=("Rain of Rust",), p2=("Test Relic",))
    rain = put(s, "Rain of Rust", "hand")
    relic = put(s, "Test Relic", "battlefield", pid="p2")
    land = next(c for c in s.state.cards.values() if c.owner == "p2" and c.name == "Island")
    act(s, "p2", type="move", card_ids=[land.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, R=3, C=6)
    act(s, "p1", type="cast_spell", card_id=rain.id, kicker=1, targets=[relic.id, land.id])  # 702.42a: both modes, a target each
    answer(s)
    assert s.state.cards[relic.id].zone == "p2:graveyard" and s.state.cards[land.id].zone == "p2:graveyard"
    assert find(s, "Rain of Rust").zone == "p1:graveyard"
    roundtrip(s)


def test_unentwined_chooses_one_mode(cards):
    s = build(cards, p1=("Rain of Rust",), p2=("Test Relic",))
    rain = put(s, "Rain of Rust", "hand")
    relic = put(s, "Test Relic", "battlefield", pid="p2")
    mana(s, R=2, C=3)
    act(s, "p1", type="cast_spell", card_id=rain.id, modes=[0], targets=[relic.id])
    answer(s)
    assert s.state.cards[relic.id].zone == "p2:graveyard"
    roundtrip(s)
