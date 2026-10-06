"""Wave 27A (static_other): "… unless its controller has ~ deal N damage to them." (CR 118.12a, 120.3).

* Lava Blister: the land's controller chooses (privately, 118.12a) to have the spell deal 6 damage to them; if they do, the land stays.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck
from tests.test_rules_combat import attack, automate, block, creature
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card('Lava Blister', set_code='tst', number='Q01', mana_cost='{R}', cmc=1.0, type_line='Sorcery', oracle_text='Destroy target nonbasic land unless its controller has Lava Blister deal 6 damage to them.', colors=['R'], color_identity=['R'], keywords=[], layout='normal'),  # noqa: E501
    card('Sizzling Barrage', set_code='tst', number='Q03', mana_cost='{3}{R}', cmc=4.0, type_line='Instant', oracle_text='Sizzling Barrage deals 4 damage to target creature that blocked this turn.', colors=['R'], color_identity=['R'], keywords=[], layout='normal'),  # noqa: E501
    card('Lupine Prototype', set_code='tst', number='Q04', mana_cost='{2}', cmc=2.0, type_line='Artifact Creature — Wolf Construct', oracle_text="This creature can't attack or block unless a player has no cards in hand.\nWhenever this creature attacks, it gets +1/+1 until end of turn.", power='5', toughness='5', colors=[], color_identity=[], keywords=[]),  # noqa: E501
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


def _combat(cards):
    """Alice attacks Bob with Sneak; Bob blocks with Guard (Idle stays back); Alice holds Sizzling Barrage."""
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Sizzling Barrage"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    sneak, guard, idle = creature(s, "p1", "Sneak"), creature(s, "p2", "Guard", "2/9"), creature(s, "p2", "Idle", "2/9")
    put(s, "Sizzling Barrage", "hand")
    automate(s)
    attack(s, (sneak, "p2"))
    block(s, "p2", (guard, sneak))
    return s, guard, idle


def test_barrage_hits_only_a_creature_that_blocked(cards):
    s, guard, idle = _combat(cards)
    mana(s, R=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=find(s, "Sizzling Barrage").id, targets=[idle.id])
    act(s, "p1", type="cast_spell", card_id=find(s, "Sizzling Barrage").id, targets=[guard.id])
    answer(s)
    assert s.state.cards[guard.id].damage == 6  # 4 from the spell + 2 combat damage as the stack empties
    roundtrip(s)


def test_lupine_prototype_needs_a_player_with_no_cards_in_hand(cards):
    assert coverage.of_card_data(cards.resolve("Lupine Prototype")).level == "FULL"
