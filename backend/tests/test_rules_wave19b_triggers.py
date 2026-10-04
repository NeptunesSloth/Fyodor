"""Wave 19B: the trigger long tail, fourth pass (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load.

* 508.1b: "deals 1 damage to the player or planeswalker it's attacking" - what the attacker the trigger is about attacks now.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.test_rules_conditionals import token_of
from tests.test_rules_wave5c_combat import build as combat_build
from tests.test_rules_wave5c_combat import declare, to_attack, to_blocks
from tests.test_rules_wave5c_combat import put as combat_put
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check, life

EXTRA = [
    real('Hellrider', '{2}{R}{R}', 4, 'Creature — Devil', "Haste\nWhenever a creature you control attacks, this creature deals 1 damage to the player or planeswalker it's attacking.", ("3", "3"), 'R'),
    real('Scorch Spitter', '{1}{R}', 2, 'Creature — Lizard', "Whenever this creature attacks, it deals 1 damage to the player or planeswalker it's attacking.", ("2", "1"), 'R'),
]

NAMES = [e["name"] for e in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_hellrider_damages_what_each_attacker_attacks(cards):
    # 508.1b: one trigger per attacking creature; Carol is attacked by one of them, Bob by the other
    s = combat_build(cards, "Hellrider", players=3)
    combat_put(s, "Hellrider")
    a = token_of(s, "p1", "Ape", "Token Creature — Ape", "2/2", "Haste")
    b = token_of(s, "p1", "Bat", "Token Creature — Bat", "2/2", "Haste")
    to_attack(s)
    declare(s, (a, "p2"), (b, "p3"))
    to_blocks(s)
    assert (life(s, "p2"), life(s, "p3")) == (39, 39)
    check(s)


def test_scorch_spitter_damages_the_player_it_attacks(cards):
    s = combat_build(cards, "Scorch Spitter")
    spitter = combat_put(s, "Scorch Spitter")
    to_attack(s, 3)
    declare(s, (spitter, "p2"))
    to_blocks(s)
    assert life(s, "p2") == 39
    check(s)
