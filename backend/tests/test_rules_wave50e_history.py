"""Wave 50E: "the damage dealt to you this turn" (CR 2026-09-25), real Oracle text (tests/fixtures/wave50e_history_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 120.3, 608.2h: "You gain life equal to the damage dealt to you this turn. ~ deals damage to target creature you control equal to the damage dealt to you this turn." (Simulacrum), "… put a +1/+1
  counter on this creature for each 1 damage dealt to you this turn." (Discordant Spirit) - all the damage players dealt you this turn, from any source; damage to others doesn't count.
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
from tests.test_rules_conditionals import until
from tests.test_rules_wave12a_counters_keywords import answer
from tests.test_rules_wave34b_activated import settle, stops
from tests.wave9c_kit import build, check, life, mana, pt, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50e_history_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50e", number=f"H{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_the_cards_are_full(cards):
    for c in DATA:
        assert coverage.of_card_data(cards.resolve(c["name"])).level == "FULL", c["name"]


def bolt(s, target, pid="p1"):
    mana(s, pid, R=1)
    act(s, pid, type="cast_spell", card_id=to_hand(s, "Lightning Bolt", pid).id, targets=[target])
    settle(s)


def test_simulacrum_gains_the_damage_and_deals_it_to_your_creature(cards):
    s = build(cards, ["Simulacrum", "Lightning Bolt", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    bolt(s, "p1")  # Alice is dealt 3
    assert life(s) == 37
    mana(s, B=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Simulacrum").id, targets=[bears.id])
    settle(s)
    assert life(s) == 40 and s.state.cards[bears.id].zone == "p1:graveyard"
    check(s)


def test_simulacrum_ignores_damage_dealt_to_others(cards):
    s = build(cards, ["Simulacrum", "Lightning Bolt", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    bolt(s, "p2")  # Bob is dealt 3
    mana(s, B=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Simulacrum").id, targets=[bears.id])
    settle(s)
    assert life(s) == 40 and s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[bears.id].damage == 0
    check(s)


@pytest.mark.parametrize("hit,size", [(True, (5, 5)), (False, (2, 2))])
def test_discordant_spirit_grows_by_the_damage_dealt_to_you_on_an_opponents_turn(cards, hit, size):
    s = build(cards, ["Discordant Spirit"], ["Lightning Bolt"])
    put(s, "Discordant Spirit")
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.priority == "p2", limit=300)
    if hit:
        bolt(s, "p1", "p2")
    stops(s)
    until(s, lambda s: s.state.turn.phase == "end", limit=60)
    answer(s)
    assert pt(s, "Discordant Spirit") == size and life(s) == (37 if hit else 40)
    check(s)
