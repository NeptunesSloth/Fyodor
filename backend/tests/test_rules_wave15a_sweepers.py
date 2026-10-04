"""Wave 15A (the static_other long tail): group selectors and sweepers. Real Oracle text, replay and save/load for each.

* 701.21a: "sacrifices all permanents they control that are one or more colors" (every match, at once, 101.4).
* 701.8 / 400.3: "destroy all A you don't control and all B you don't control" (one group of two kinds under one qualifier).
* 700.6 / 205.4: "nonland permanents that aren't legendary / that aren't historic", "creatures that aren't enchanted".
* 107.1: "power greater than N" (strictly).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, build, put, roundtrip

EXTRA = [
    card("All Is Dust", set_code="tst", number="A01", mana_cost="{7}", cmc=7.0, type_line="Sorcery",
         oracle_text="Each player sacrifices all permanents they control that are one or more colors."),
    card("In Garruk's Wake", set_code="tst", number="A02", mana_cost="{7}{B}{B}", cmc=9.0, type_line="Sorcery",
         oracle_text="Destroy all creatures you don't control and all planeswalkers you don't control."),
    card("Urza's Ruinous Blast", set_code="tst", number="A03", mana_cost="{4}{W}", cmc=5.0, type_line="Legendary Sorcery",
         oracle_text="Exile all nonland permanents that aren't legendary."),
    card("Winds of Rath", set_code="tst", number="A04", mana_cost="{3}{W}{W}", cmc=5.0, type_line="Sorcery",
         oracle_text="Destroy all creatures that aren't enchanted. They can't be regenerated."),
    card("Desynchronization", set_code="tst", number="A05", mana_cost="{3}{U}", cmc=4.0, type_line="Sorcery",
         oracle_text="Return each nonland permanent that's not historic to its owner's hand."),
    card("Test Big", set_code="tst", number="A06", mana_cost="{1}{W}", cmc=2.0, type_line="Creature — Knight", power="5", toughness="5",
         colors=["W"], color_identity=["W"], oracle_text=""),
    card("Test Small", set_code="tst", number="A07", mana_cost="{G}", cmc=1.0, type_line="Creature — Elf", power="2", toughness="2",
         colors=["G"], color_identity=["G"], oracle_text=""),
    card("Test Relic", set_code="tst", number="A08", mana_cost="{2}", cmc=2.0, type_line="Artifact", oracle_text=""),
    card("Test Legend", set_code="tst", number="A09", mana_cost="{1}{G}", cmc=2.0, type_line="Legendary Creature — Elf", power="1",
         toughness="1", colors=["G"], color_identity=["G"], oracle_text=""),
    card("Broken Wings", set_code="tst", number="A11", mana_cost="{2}{G}", cmc=3.0, type_line="Instant", colors=["G"],
         color_identity=["G"], oracle_text="Destroy target artifact, enchantment, or creature with flying."),
    card("Test Flyer", set_code="tst", number="A12", mana_cost="{1}{U}", cmc=2.0, type_line="Creature — Bird", power="2",
         toughness="2", colors=["U"], color_identity=["U"], oracle_text="Flying"),
    card("Test Pest", set_code="tst", number="A10", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Elf", power="3", toughness="3",
         colors=["G"], color_identity=["G"], oracle_text=""),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA if c["oracle_text"]])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def hand(s, name, pid="p1"):
    return put(s, name, "hand", pid)


def cast(s, name, **m):
    c = hand(s, name)
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)


def zone(s, name, pid="p1"):
    return next(c.zone for c in s.state.cards.values() if c.name == name and c.owner == pid)


def test_all_is_dust_sacrifices_every_colored_permanent_of_each_player(cards):
    s = build(cards, p1=("All Is Dust", "Test Big", "Test Relic"), p2=("Test Small",))
    put(s, "Test Big", "battlefield"), put(s, "Test Relic", "battlefield"), put(s, "Test Small", "battlefield", "p2")
    cast(s, "All Is Dust", C=7)
    assert zone(s, "Test Big") == "p1:graveyard" and zone(s, "Test Small", "p2") == "p2:graveyard"
    assert zone(s, "Test Relic") == "p1:battlefield"
    roundtrip(s)


def test_in_garruks_wake_destroys_only_the_opponents_creatures(cards):
    s = build(cards, p1=("In Garruk's Wake", "Test Big"), p2=("Test Small", "Test Relic"))
    put(s, "Test Big", "battlefield"), put(s, "Test Small", "battlefield", "p2"), put(s, "Test Relic", "battlefield", "p2")
    cast(s, "In Garruk's Wake", C=7, B=2)
    assert zone(s, "Test Big") == "p1:battlefield" and zone(s, "Test Small", "p2") == "p2:graveyard"
    assert zone(s, "Test Relic", "p2") == "p2:battlefield"
    roundtrip(s)


def test_ruinous_blast_leaves_legendary_permanents_and_lands(cards):
    s = build(cards, p1=("Urza's Ruinous Blast", "Test Big", "Test Legend"), p2=("Test Relic",))
    put(s, "Test Big", "battlefield"), put(s, "Test Legend", "battlefield"), put(s, "Test Relic", "battlefield", "p2")
    cast(s, "Urza's Ruinous Blast", C=4, W=1)
    assert zone(s, "Test Big") == "p1:exile" and zone(s, "Test Relic", "p2") == "p2:exile"
    assert zone(s, "Test Legend") == "p1:battlefield"
    roundtrip(s)


def test_desynchronization_keeps_historic_permanents(cards):
    s = build(cards, p1=("Desynchronization", "Test Big", "Test Relic", "Test Legend"))
    for n in ("Test Big", "Test Relic", "Test Legend"):
        put(s, n, "battlefield")
    cast(s, "Desynchronization", C=3, U=1)
    assert zone(s, "Test Big") == "p1:hand"
    assert zone(s, "Test Relic") == "p1:battlefield" and zone(s, "Test Legend") == "p1:battlefield"  # artifact, legendary: historic
    roundtrip(s)


def test_winds_of_rath_spares_enchanted_creatures(cards):
    s = build(cards, p1=("Winds of Rath", "Test Big", "Test Small"))
    big = put(s, "Test Big", "battlefield")
    put(s, "Test Small", "battlefield")
    act(s, "p1", type="create_token", player="p1", token={"name": "Aura", "type_line": "Token Enchantment — Aura", "text": ""})
    aura = next(c for c in s.state.cards.values() if c.name == "Aura")
    act(s, "p1", type="attach", card_ids=[aura.id], to=big.id)
    cast(s, "Winds of Rath", C=3, W=2)
    assert zone(s, "Test Big") == "p1:battlefield" and zone(s, "Test Small") == "p1:graveyard"
    roundtrip(s)


def test_broken_wings_the_qualifier_binds_to_creatures_only(cards):
    from app.game.errors import ActionError

    s = build(cards, p1=("Broken Wings",), p2=("Test Relic", "Test Flyer", "Test Small"))
    for n in ("Test Relic", "Test Flyer", "Test Small"):
        put(s, n, "battlefield", "p2")
    wings = hand(s, "Broken Wings")
    mana(s, G=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=wings.id, targets=[next(c.id for c in s.state.cards.values() if c.name == "Test Small")])
    for name in ("Test Relic", "Test Flyer"):
        act(s, "p1", type="cast_spell", card_id=wings.id, targets=[next(c.id for c in s.state.cards.values() if c.name == name)])
        answer(s)
        assert zone(s, name, "p2") == "p2:graveyard"
        wings = put(s, "Broken Wings", "hand")
        mana(s, G=1, C=2)
    assert zone(s, "Test Small", "p2") == "p2:battlefield"
    roundtrip(s)
