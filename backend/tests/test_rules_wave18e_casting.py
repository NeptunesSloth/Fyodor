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
    card("Mizzium Mortars", set_code="tst", number="D03", mana_cost="{1}{R}", cmc=2.0, type_line="Sorcery", colors=["R"],
         color_identity=["R"], oracle_text="Mizzium Mortars deals 4 damage to target creature you don't control.\nOverload {3}{R}{R}{R} "
         "(You may cast this spell for its overload cost. If you do, change its text by replacing all instances of \"target\" with "
         "\"each.\")"),
    card("Stirring Address", set_code="tst", number="D04", mana_cost="{1}{W}", cmc=2.0, type_line="Instant", colors=["W"],
         color_identity=["W"], oracle_text="Target creature you control gets +2/+2 until end of turn.\nOverload {5}{W} (You may cast "
         "this spell for its overload cost. If you do, change its text by replacing all instances of \"target\" with \"each.\")"),
    card("Test Bear", set_code="tst", number="D05", mana_cost="{2}{G}", cmc=3.0, type_line="Creature — Bear", power="2", toughness="2",
         colors=["G"], color_identity=["G"], oracle_text=""),
    card("Test Relic", set_code="tst", number="D02", mana_cost="{2}", cmc=2.0, type_line="Artifact", oracle_text=""),
]


def pt(s, card):
    from tests.test_rules_attachments import ch

    return ch(s, card).pt


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


def test_overload_replaces_target_with_each(cards):
    s = build(cards, p1=("Mizzium Mortars",), p2=("Test Bear", "Test Bear"))
    mortars = put(s, "Mizzium Mortars", "hand")
    bears = [c for c in s.state.cards.values() if c.owner == "p2" and c.name == "Test Bear"]
    for b in bears:
        act(s, "p2", type="move", card_ids=[b.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, R=4, C=3)
    act(s, "p1", type="cast_spell", card_id=mortars.id, alt_cost=f"{mortars.id}:1")  # 702.96b: no targets are chosen
    answer(s)
    assert all(s.state.cards[b.id].zone == "p2:graveyard" for b in bears)  # 4 damage to each creature you don't control
    roundtrip(s)


def test_overload_only_affects_what_the_wording_names(cards):
    s = build(cards, p1=("Stirring Address", "Test Bear"), p2=("Test Bear",))
    addr = put(s, "Stirring Address", "hand")
    mine = put(s, "Test Bear", "battlefield")
    theirs = put(s, "Test Bear", "battlefield", pid="p2")
    mana(s, W=1, C=5)
    act(s, "p1", type="cast_spell", card_id=addr.id, alt_cost=f"{addr.id}:1")
    answer(s)
    assert (pt(s, mine), pt(s, theirs)) == ((4, 4), (2, 2))  # "Each creature you control gets +2/+2 until end of turn"
    roundtrip(s)
