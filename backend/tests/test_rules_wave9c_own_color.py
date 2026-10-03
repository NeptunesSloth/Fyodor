"""Wave 9C: a creature's own color and abilities under a graveyard condition ("Threshold — As long as there are seven or more
cards in your graveyard, this creature gets +1/+1, is black, and has "…"": Possessed Aven, Possessed Barbarian / Centaur /
Nomad, Wayward Angel), researched against CR 2026-09-25.

* 613.1e (layer 5): "is black" sets its color to black (105.3), replacing blue; 613.1f (layer 6): the quoted ability is
  granted; 613.4c (layer 7c): +1/+1. 611.3a: a static applies at any moment its condition is true, never locked in.
* The condition reads the graveyard, never the colors being derived (613.8 dependencies are not modelled), so only
  conditions of that kind may gate a color change.
Every scenario uses real Oracle text and checks the replay and a save and a load.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, pt, put

EXTRA = [
    card('Possessed Aven', set_code='wc', number='E01', mana_cost='{2}{U}{U}', cmc=4.0, type_line='Creature — Bird Soldier Horror', oracle_text='Flying\nThreshold — As long as there are seven or more cards in your graveyard, this creature gets +1/+1, is black, and has "{2}{B}, {T}: Destroy target blue creature."', colors=['U'], color_identity=['B', 'U'], keywords=['Flying', 'Threshold'], power='3', toughness='3'),  # noqa: E501
    card('Wayward Angel', set_code='wc', number='E02', mana_cost='{4}{W}{W}', cmc=6.0, type_line='Creature — Angel Horror', oracle_text='Flying, vigilance\nThreshold — As long as there are seven or more cards in your graveyard, this creature gets +3/+3, is black, has trample, and has "At the beginning of your upkeep, sacrifice a creature."', colors=['W'], color_identity=['W'], keywords=['Flying', 'Vigilance', 'Threshold'], power='4', toughness='4'),  # noqa: E501
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def current(s, name):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name).id])


def fill_graveyard(s, n):
    for c in [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][:n]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})


def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
        assert coverage.of_characteristics(chs).level == "FULL", c["name"]


@pytest.mark.parametrize("cond", [
    "you control a green permanent",  # (reads colors: not a condition a color change may depend on)
    "an opponent controls a creature"])
def test_a_color_change_under_a_board_condition_stays_manual(cond):
    from tests.test_rules_scripts import ch as characteristics

    text = f"As long as {cond}, this creature gets +1/+1 and is black."
    assert coverage.of_characteristics(characteristics("Test", "Creature — Bird", text)).level != "FULL", text


def test_possessed_aven_turns_black_with_seven_cards_in_the_graveyard(cards):
    s = build(cards, ("Possessed Aven",), ())
    put(s, "Possessed Aven")
    ch = current(s, "Possessed Aven")
    assert ch.colors == frozenset({"U"}) and pt(s, "Possessed Aven") == (3, 3)
    fill_graveyard(s, 6)
    assert current(s, "Possessed Aven").colors == frozenset({"U"})
    fill_graveyard(s, 1)
    ch = current(s, "Possessed Aven")
    assert ch.colors == frozenset({"B"}) and pt(s, "Possessed Aven") == (4, 4)  # (black instead of blue: replaced, 105.3)
    assert any("Destroy target blue creature" in a.text for a in ch.abilities)
    check(s)


def test_the_color_goes_back_when_the_graveyard_shrinks(cards):
    s = build(cards, ("Possessed Aven",), ())
    put(s, "Possessed Aven")
    fill_graveyard(s, 7)
    assert current(s, "Possessed Aven").colors == frozenset({"B"})
    gy = [c for c in s.state.cards.values() if c.zone == "p1:graveyard"]
    act(s, "p1", type="move", card_ids=[gy[0].id], to={"zone": "exile"})
    assert current(s, "Possessed Aven").colors == frozenset({"U"})
    check(s)


def test_wayward_angel_gets_trample_and_the_upkeep_sacrifice(cards):
    s = build(cards, ("Wayward Angel",), ())
    put(s, "Wayward Angel")
    fill_graveyard(s, 7)
    ch = current(s, "Wayward Angel")
    assert ch.colors == frozenset({"B"}) and pt(s, "Wayward Angel") == (7, 7)
    assert "trample" in {k.lower() for k in ch.keywords}
    assert any("sacrifice a creature" in a.text for a in ch.abilities)
    check(s)
