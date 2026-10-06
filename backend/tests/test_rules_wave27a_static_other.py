"""Wave 27A (static_other): "… unless its controller has ~ deal N damage to them." (CR 118.12a, 120.3).

* Lava Blister: the land's controller chooses (privately, 118.12a) to have the spell deal 6 damage to them; if they do, the land stays.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card('Lava Blister', set_code='tst', number='Q01', mana_cost='{R}', cmc=1.0, type_line='Sorcery', oracle_text='Destroy target nonbasic land unless its controller has Lava Blister deal 6 damage to them.', colors=['R'], color_identity=['R'], keywords=[], layout='normal'),  # noqa: E501
    card('Test Tower', set_code='tst', number='Q02', mana_cost='', cmc=0.0, type_line='Land', oracle_text='', colors=[], color_identity=[]),  # noqa: E501
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_coverage_full(cards):
    assert coverage.of_card_data(cards.resolve("Lava Blister")).level == "FULL"


def _blister(cards, choice):
    s = build(cards, p1=("Lava Blister",), p2=("Test Tower",))
    land = put(s, "Test Tower", "battlefield", pid="p2")
    put(s, "Lava Blister", "hand")
    mana(s, R=3)
    act(s, "p1", type="cast_spell", card_id=find(s, "Lava Blister").id, targets=[land.id])
    for _ in range(5):  # resolve: the land's controller is asked
        d = s.state.rules.decision
        if d is not None:
            assert d.player == "p2"
            act(s, "p2", type="choose", decision_id=d.id, option_ids=[choice])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    answer(s)
    return s, land


def test_paying_with_damage_keeps_the_land(cards):
    s, land = _blister(cards, "pay")
    assert s.state.cards[land.id].zone == "p2:battlefield" and s.state.players["p2"].life == 34
    roundtrip(s)


def test_declining_destroys_the_land(cards):
    s, land = _blister(cards, "decline")
    assert s.state.cards[land.id].zone == "p2:graveyard" and s.state.players["p2"].life == 40
    roundtrip(s)
