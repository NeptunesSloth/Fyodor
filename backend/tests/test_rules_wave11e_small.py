"""Wave 11E: small wording fixes, researched against CR 2026-09-25.

* "Remove a +1/+1 counter from this creature: It deals 1 damage to any target." (Triskelion): the only object the cost
  names is the source, so "it" is the source (608.2h; 602.2: the counter is a cost).
* Triggers on the permanent an Aura / Equipment is attached to (603.2): "When enchanted creature becomes the target of
  a spell or ability" (Ice Cage) and "Whenever enchanted creature blocks or becomes blocked by a creature, destroy the
  other creature at end of combat" (Venom; 509.3b / 509.3d: the creature on the other side).
* "Instant and sorcery spells you control can't be countered." (Sphinx of the Final Word; 101.2, 701.6): the counter
  does nothing to such a spell, but the rest of the counterspell still happens (608.2c).
"""

from __future__ import annotations

import pytest

from app.cards.importer import build_database
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import mana, to_hand, token
from tests.test_rules_conditionals import settle, until
from tests.test_rules_wave4h_activation_costs import activate, counters, roundtrip, set_counters
from tests.test_rules_wave5c_combat import build, put
from tests.test_rules_conditionals import life, on_field
from tests.test_rules_wave5b_stack_interaction import EXTRA as COUNTERS
from tests.test_rules_wave5b_stack_interaction import alice_casts, bob_answers
from tests.test_rules_wave5b_stack_interaction import build as build_counters
from tests.test_rules_wave5b_stack_interaction import roundtrip as roundtrip_counters
from tests.test_rules_wave6d_trigger_bodies import bob_attacks_into, gone

EXTRA = [
    card('Sphinx of the Final Word', set_code="tst", number="Q04", mana_cost='{U}{U}{U}{U}{U}', cmc=5.0, type_line='Creature — Sphinx', oracle_text="Flash\nThis spell can't be countered.\nFlying\nInstant and sorcery spells you control can't be countered.", power='5', toughness='5', colors=['U'], color_identity=['U'], keywords=['Flash', 'Flying']),  # noqa: E501
    card('Triskelion', set_code="tst", number="Q01", mana_cost='{6}', cmc=6.0, type_line='Artifact Creature — Construct', oracle_text='Triskelion enters with three +1/+1 counters on it.\nRemove a +1/+1 counter from Triskelion: It deals 1 damage to any target.', power='1', toughness='1', colors=[], color_identity=[]),  # noqa: E501
    card('Ice Cage', set_code="tst", number="Q02", mana_cost='{1}{U}', cmc=2.0, type_line='Enchantment — Aura', oracle_text="Enchant creature\nEnchanted creature can't attack or block.\nWhen enchanted creature becomes the target of a spell or ability, destroy Ice Cage.", colors=['U'], color_identity=['U'], keywords=['Enchant']),  # noqa: E501
    card('Venom', set_code="tst", number="Q03", mana_cost='{1}{G}', cmc=2.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nWhenever enchanted creature blocks or becomes blocked by a non-Wall creature, destroy the other creature at end of combat.', colors=['G'], color_identity=['G'], keywords=['Enchant']),  # noqa: E501
]


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *COUNTERS, *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Triskelion", "Ice Cage", "Venom"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_triskelion_it_is_the_source_and_ice_cage_sees_the_target(cards):
    s = build(cards, "Triskelion", "Ice Cage")
    tri = put(s, "Triskelion")
    set_counters(s, tri, "+1/+1", 3)
    bear = token(s, "p1", "Bear")
    cage = to_hand(s, "Ice Cage")
    mana(s, U=1, G=1)
    act(s, "p1", type="cast_spell", card_id=cage.id, targets=[bear.id])
    settle(s)
    assert s.state.cards[cage.id].zone == "p1:battlefield"
    assert counters(s, tri, "+1/+1") == 3
    activate(s, tri, "Remove a +1/+1", targets=[bear.id])
    settle(s)
    assert counters(s, tri, "+1/+1") == 2  # (the cost)
    assert s.state.cards[bear.id].damage == 1 and s.state.cards[tri.id].damage == 0  # (Triskelion dealt it)
    assert s.state.cards[cage.id].zone == "p1:graveyard"  # (Ice Cage: the enchanted creature became a target)
    roundtrip(s)


def test_venom_destroys_the_attacker_it_blocked_at_end_of_combat(cards):
    s = build(cards, "Venom")
    bear = token(s, "p1", "Bear", "2/5")
    venom = to_hand(s, "Venom")
    mana(s, G=1, U=1)
    act(s, "p1", type="cast_spell", card_id=venom.id, targets=[bear.id])
    settle(s)
    raider = bob_attacks_into(s, bear)
    until(s, lambda s: s.state.turn.phase == "combat_damage" and not s.state.zones.get("stack"))
    assert s.state.cards[raider.id].zone == "p2:battlefield" and s.state.rules.delayed
    roundtrip(s)
    until(s, lambda s: s.state.turn.phase == "main2" and not s.state.zones.get("stack"))
    assert gone(s, raider, "p2") and s.state.cards[bear.id].zone == "p1:battlefield"
    roundtrip(s)


def test_spells_you_control_cant_be_countered(cards):
    s = build_counters(cards, p1=("Lightning Bolt", "Sphinx of the Final Word"), p2=("Countersquall",))
    on_field(s, "Sphinx of the Final Word", "p1")
    bolt = alice_casts(s, "Lightning Bolt", targets=["p2"], R=1)
    bob_answers(s, "Countersquall", bolt.id, U=1, B=1)
    settle(s)
    assert s.state.cards[bolt.id].zone == "p1:graveyard"
    assert life(s, "p2") == 37 and life(s, "p1") == 38  # (the Bolt resolved; "its controller loses 2 life" still happened, 608.2c)
    roundtrip_counters(s)
