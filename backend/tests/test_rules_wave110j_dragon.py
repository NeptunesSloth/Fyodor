"""Wave 110J: Quicksilver Dragon (115.7a, 115.9c): any spell may be targeted; the target changes only if that spell's single target is the Dragon."""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import on_field, settle
from tests.test_rules_effects import mana
from tests.test_rules_wave5b_stack_interaction import alice_casts, build, roundtrip
from tests.test_rules_wave12a_counters_keywords import real

TEXT = ("Flying\n{U}: If target spell has only one target and that target is this creature, change that spell's target to another creature.\n"
        "Morph {4}{U}")
EXTRA = [real("Quicksilver Dragon", "{4}{U}{U}", 6, "Creature — Dragon", TEXT, ("5", "5"), "U")]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Quicksilver Dragon")).level == "FULL"


def activate(s, dragon, spell):
    mana(s, "p2", U=1)
    act(s, "p2", type="activate_ability", card_id=dragon.id, ability=1, targets=[spell.id])


def test_bolt_aimed_only_at_the_dragon_goes_to_another_creature(cards):
    s = build(cards, ["Lightning Bolt", "Grizzly Bears"], ["Quicksilver Dragon"])
    bears, dragon = on_field(s, "Grizzly Bears"), on_field(s, "Quicksilver Dragon", "p2")
    bolt = alice_casts(s, "Lightning Bolt", targets=[dragon.id], R=1)
    activate(s, dragon, bolt)
    settle(s)
    assert s.state.cards[bears.id].zone.endswith(":graveyard") and s.state.cards[dragon.id].damage == 0
    roundtrip(s)


def test_bolt_aimed_at_a_player_is_left_alone(cards):
    s = build(cards, ["Lightning Bolt", "Grizzly Bears"], ["Quicksilver Dragon"])
    on_field(s, "Grizzly Bears")
    dragon = on_field(s, "Quicksilver Dragon", "p2")
    bolt = alice_casts(s, "Lightning Bolt", targets=["p2"], R=1)
    activate(s, dragon, bolt)
    settle(s)
    assert s.state.players["p2"].life == 37 and s.state.cards[dragon.id].damage == 0
    roundtrip(s)
