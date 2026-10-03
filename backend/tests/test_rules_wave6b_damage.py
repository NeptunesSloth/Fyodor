"""Wave 6B: damage and damage-prevention wordings (app/rules/damage_history.py and the blocks marked wave 6B).
Researched against CR 2026-09-25.

* Objects that were dealt damage, or dealt damage, this turn (608.2i; 120.3; 400.7): "target creature that was
  dealt damage this turn", "each creature that dealt damage [to you] this turn". Prevented damage was never dealt
  (615.1), and a permanent that left and came back is a new object.

Every scenario checks the replay and a save/load round trip."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, scripts
from app.rules.characteristics import Characteristics
from app.rules.oracle import parse_abilities
from tests.fixtures.cards import card, fixture_cards
from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_attachments import build, mana, named, to_hand, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches

# Real Oracle wording (the local card database, current).
EXTRA = [
    card('Crushing Pain', set_code="tst", number="B601", mana_cost="{1}{R}", cmc=2.0, type_line="Instant — Arcane",
         oracle_text='Crushing Pain deals 6 damage to target creature that was dealt damage this turn.', colors=['R'],
         color_identity=['R']),
    card('Retaliate', set_code="tst", number="B602", mana_cost="{2}{W}{W}", cmc=4.0, type_line="Instant",
         oracle_text='Destroy all creatures that dealt damage to you this turn.', colors=['W'], color_identity=['W']),
    card('Restore the Peace', set_code="tst", number="B603", mana_cost="{1}{W}{U}", cmc=3.0, type_line="Instant",
         oracle_text="Return each creature that dealt damage this turn to its owner's hand.", colors=['U', 'W'],
         color_identity=['U', 'W']),
    card('Swift Demise', set_code="tst", number="B604", mana_cost="{2}{B}", cmc=3.0, type_line="Instant",
         oracle_text="Swift Demise deals 1 damage to target creature. Then destroy each creature you don't control that was "
                     "dealt damage this turn.", colors=['B'], color_identity=['B']),
]

PINGER = "Haste\n{T}: This creature deals 1 damage to any target."


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def life(s, pid="p1"):
    return s.state.players[pid].life


def parse(text):
    ab = parse_abilities(text)[0]
    return scripts.definitions(Characteristics(name="Test", abilities=(ab,))).get(ab.index)


def roundtrip(s):
    replay_matches(s)  # (the recorded history rebuilds the same table)
    saved = s.state.model_dump_json()
    loaded = GameSession(GameState.model_validate_json(saved), cards=s.cards)  # a save, loaded
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def cast(s, name, targets=None, **paid):
    spell = to_hand(s, name)
    mana(s, **paid)
    act(s, "p1", type="cast_spell", card_id=spell.id, **({"targets": targets} if targets else {}))
    pass_until_stack_empty(s)


def ping(s, pinger, target, pid="p1"):
    act(s, pid, type="activate_ability", card_id=pinger.id, ability=1, targets=[target])
    pass_until_stack_empty(s)


def zone(s, c):
    return s.state.cards[c.id].zone if c.id in s.state.cards else None


@pytest.mark.parametrize("name", ["Crushing Pain", "Retaliate", "Restore the Peace", "Swift Demise"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- damage history ---------------------------------------------------------------------------------------------
def test_only_a_creature_dealt_damage_this_turn_is_a_legal_target(cards):
    s = build(cards, "Crushing Pain")
    pinger = token(s, "p1", "Pinger", "1/1", PINGER)
    ogre = token(s, "p2", "Ogre", "7/7")
    bear = token(s, "p2", "Bear", "7/7")
    ping(s, pinger, ogre.id)
    spell = to_hand(s, "Crushing Pain")
    mana(s, R=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id])  # never dealt damage
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[ogre.id])
    pass_until_stack_empty(s)
    assert zone(s, ogre) != "p2:battlefield"  # 1 + 6 damage: lethal
    assert zone(s, bear) == "p2:battlefield"
    roundtrip(s)


def test_damage_dealt_earlier_in_the_same_resolution_counts(cards):
    s = build(cards, "Swift Demise")
    ogre = token(s, "p2", "Ogre", "7/7")
    bear = token(s, "p2", "Bear", "7/7")
    mine = token(s, "p1", "Mine", "7/7")
    pinger = token(s, "p1", "Pinger", "1/1", PINGER)
    ping(s, pinger, mine.id)
    cast(s, "Swift Demise", targets=[ogre.id], B=1, C=2)
    assert zone(s, ogre) != "p2:battlefield"  # dealt 1 damage by the spell itself, then destroyed
    assert zone(s, bear) == "p2:battlefield"  # dealt none
    assert zone(s, mine) == "p1:battlefield"  # dealt damage, but "you don't control" leaves it out
    roundtrip(s)


def test_creatures_that_dealt_damage_to_you(cards):
    s = build(cards, "Retaliate")
    at_me = token(s, "p1", "At Me", "1/1", PINGER)
    at_bob = token(s, "p1", "At Bob", "1/1", PINGER)
    ping(s, at_me, "p1")
    ping(s, at_bob, "p2")
    cast(s, "Retaliate", W=2, C=2)
    assert zone(s, at_me) != "p1:battlefield"  # it dealt damage to Alice
    assert zone(s, at_bob) == "p1:battlefield"  # it dealt damage, but to Bob
    roundtrip(s)


def test_creatures_that_dealt_damage_to_anything(cards):
    s = build(cards, "Restore the Peace")
    pinger = token(s, "p1", "Pinger", "1/1", PINGER)
    idle = token(s, "p1", "Idle", "1/1", PINGER)
    ogre = token(s, "p2", "Ogre", "7/7")
    ping(s, pinger, ogre.id)
    cast(s, "Restore the Peace", W=1, U=1, C=1)
    assert zone(s, pinger) != "p1:battlefield"  # dealt damage to a creature: returned (a token ceases to exist)
    assert zone(s, idle) == "p1:battlefield"
    assert zone(s, ogre) == "p2:battlefield"  # it was dealt damage, it dealt none
    roundtrip(s)
