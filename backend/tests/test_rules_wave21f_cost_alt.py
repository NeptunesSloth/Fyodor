"""Wave 21F (cost_alt). Real Oracle text, replay and save/load for each.

* 118.9 / 601.3: "You may cast this card from your graveyard by paying [cost] rather than paying its mana cost." — its own
  alternative cost, not an escape (702.138b).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, build, put, roundtrip

EXTRA = [
    card("Squee, Dubious Monarch", set_code="tst", number="E01", mana_cost="{2}{R}", cmc=3.0, type_line="Legendary Creature — Goblin Noble",
         power="2", toughness="2", colors=["R"], color_identity=["R"], oracle_text="Haste\nWhenever Squee attacks, create a 1/1 red Goblin "
         "creature token that's tapped and attacking.\nYou may cast this card from your graveyard by paying {3}{R} and exiling four other "
         "cards from your graveyard rather than paying its mana cost."),
    card("Scourge of Nel Toth", set_code="tst", number="E02", mana_cost="{5}{B}{B}", cmc=7.0, type_line="Creature — Zombie Dragon",
         power="6", toughness="6", colors=["B"], color_identity=["B"], keywords=["Flying"], oracle_text="Flying\nYou may cast this "
         "creature from your graveyard by paying {B}{B} and sacrificing two creatures rather than paying its mana cost."),
    card("Raffine's Guidance", set_code="tst", number="E03", mana_cost="{W}", cmc=1.0, type_line="Enchantment — Aura", colors=["W"],
         color_identity=["W"], oracle_text="Enchant creature\nEnchanted creature gets +1/+1.\nYou may cast this card from your graveyard "
         "by paying {2}{W} rather than paying its mana cost."),
    card("Test Bear", set_code="tst", number="E04", mana_cost="{2}{G}", cmc=3.0, type_line="Creature — Bear", power="2", toughness="2",
         colors=["G"], color_identity=["G"], oracle_text=""),
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


def test_graveyard_cast_with_mana_and_exiling_other_cards(cards):
    s = build(cards, p1=("Squee, Dubious Monarch", "Test Bear", "Test Bear", "Test Bear", "Test Bear", "Test Bear"))
    squee = put(s, "Squee, Dubious Monarch", "graveyard")
    bears = [c.id for c in s.state.cards.values() if c.name == "Test Bear" and c.owner == "p1"]
    for b in bears[:4]:
        act(s, "p1", type="move", card_ids=[b], to={"player": "p1", "zone": "graveyard"})
    mana(s, R=1, C=3)  # {3}{R}, not {2}{R}
    act(s, "p1", type="cast_spell", card_id=squee.id, alt_cost=f"{squee.id}:2",
        cost_choices=[{"component": 0, "cards": [c.id for c in s.state.cards.values() if c.zone == "p1:graveyard" and c.id != squee.id][:4]}])
    answer(s)
    assert s.state.cards[squee.id].zone == "p1:battlefield"
    assert sum(1 for c in s.state.cards.values() if c.zone == "p1:exile") == 4
    roundtrip(s)


def test_graveyard_cast_by_sacrificing_two_creatures(cards):
    s = build(cards, p1=("Scourge of Nel Toth", "Test Bear", "Test Bear"))
    dragon = put(s, "Scourge of Nel Toth", "graveyard")
    ids = [c.id for c in s.state.cards.values() if c.name == "Test Bear"]
    for i in ids:
        act(s, "p1", type="move", card_ids=[i], to={"player": "p1", "zone": "battlefield"})
    mana(s, B=2)
    with pytest.raises(ActionError):  # one creature isn't two
        act(s, "p1", type="cast_spell", card_id=dragon.id, alt_cost=f"{dragon.id}:1", cost_choices=[{"component": 0, "cards": ids[:1]}])
    act(s, "p1", type="cast_spell", card_id=dragon.id, alt_cost=f"{dragon.id}:1", cost_choices=[{"component": 0, "cards": ids}])
    answer(s)
    assert s.state.cards[dragon.id].zone == "p1:battlefield"
    assert all(s.state.cards[i].zone == "p1:graveyard" for i in ids)
    roundtrip(s)


def test_graveyard_cast_aura_for_its_own_cost(cards):
    s = build(cards, p1=("Raffine's Guidance", "Test Bear"))
    aura = put(s, "Raffine's Guidance", "graveyard")
    bear = put(s, "Test Bear", "battlefield")
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=aura.id, alt_cost=f"{aura.id}:2", targets=[bear.id])
    answer(s)
    assert s.state.cards[aura.id].zone == "p1:battlefield"
    roundtrip(s)
