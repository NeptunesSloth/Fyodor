"""Wave 20E: control change. Real Oracle text; every scenario checks the replay and a save and a load.

* 613.1b / 608.2c: "Gain control of all artifacts and creatures target opponent controls." (Tezzeret, Master of Metal; Ashiok, Sculptor of
  Fears: "… all creatures target opponent controls.") - the permanents that player controls as the ability resolves, for good.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, cast, check, mana, put, to_hand

EXTRA = [
    real('Probe Heist', '{1}', 1, 'Sorcery', 'Gain control of all artifacts and creatures target opponent controls.', None),
    real('Probe Soldier', '{1}{W}', 2, 'Creature — Human Soldier', '', ("1", "1"), 'W'),
    real('Probe Rock', '{3}', 3, 'Artifact', '', None),
    real('Probe Land', '', 0, 'Land', '', None),
    real('Dominating Vampire', '{2}{R}{R}', 4, 'Creature — Vampire', 'When this creature enters, gain control of target creature with mana value less than or equal to the number of Vampires you control until end of turn. Untap that creature. It gains haste until end of turn.', ("3", "3"), 'R'),
    real('Probe Thrull', '{B}', 1, 'Creature — Thrull', '', ("1", "1"), 'B'),
    real('Probe Giant', '{5}', 5, 'Creature — Giant', '', ("5", "5")),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Probe Heist"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_all_artifacts_and_creatures_the_opponent_controls(cards):
    s = build(cards, ["Probe Heist"], ["Probe Soldier", "Probe Rock", "Probe Land"])
    soldier, rock = put(s, "Probe Soldier", "p2"), put(s, "Probe Rock", "p2")
    land = card_named(s, "Forest")  # (Alice's own: not touched)
    heist = to_hand(s, "Probe Heist")
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1})
    act(s, "p1", type="cast_spell", card_id=heist.id, targets=["p2"])
    for _ in range(10):
        if not s.state.rules.stack:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[soldier.id].controller == "p1" and s.state.cards[rock.id].controller == "p1"
    assert s.state.cards[soldier.id].owner == "p2" and land.owner == "p1"
    check(s)


def test_a_target_with_mana_value_up_to_the_number_of_vampires_you_control(cards):
    """608.2c / 115.1: one Vampire (itself) is controlled, so only a creature with mana value 1 or less is a legal target."""
    s = build(cards, ["Dominating Vampire"], ["Probe Thrull", "Probe Giant"])
    thrull, giant = put(s, "Probe Thrull", "p2"), put(s, "Probe Giant", "p2")
    to_hand(s, "Dominating Vampire")
    mana(s, "p1", R=2, C=2)
    cast(s, "Dominating Vampire")  # (the Thrull is the only legal target: chosen as the trigger goes on the stack, 603.3d)
    assert s.state.cards[thrull.id].controller == "p1" and s.state.cards[giant.id].controller == "p2"
    check(s)
