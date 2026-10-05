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
from tests.wave9c_kit import build, card_named, check, put, to_hand

EXTRA = [
    real('Probe Heist', '{1}', 1, 'Sorcery', 'Gain control of all artifacts and creatures target opponent controls.', None),
    real('Probe Soldier', '{1}{W}', 2, 'Creature — Human Soldier', '', ("1", "1"), 'W'),
    real('Probe Rock', '{3}', 3, 'Artifact', '', None),
    real('Probe Land', '', 0, 'Land', '', None),
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
