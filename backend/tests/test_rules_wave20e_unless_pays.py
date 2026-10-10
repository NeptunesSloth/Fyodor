"""Wave 20E: "unless pays" long tail. Real Oracle text; every scenario checks the replay and a save and a load.

* 603.2e / 702.21a / 118.12a: "Whenever this creature becomes the target of a spell or ability an opponent controls, counter that spell
  or ability unless its controller pays {2}." - that spell or ability's controller decides; paying keeps it, declining counters it.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave12a_counters_keywords import answer, real
from tests.wave9c_kit import build, check, life, mana, put, to_hand, zone_of

EXTRA = [
    real('Frost Titan', '{4}{U}{U}', 6, 'Creature — Giant', "Whenever this creature becomes the target of a spell or ability an opponent controls, counter that spell or ability unless its controller pays {2}.", ("6", "6"), 'U'),
    real('Diffusion Sliver', '{1}{U}', 2, 'Creature — Sliver', "Whenever a Sliver creature you control becomes the target of a spell or ability an opponent controls, counter that spell or ability unless its controller pays {2}.", ("1", "1"), 'U'),
    real('Repulsive Mutation', '{X}{G}{U}', 2, 'Instant', "Put X +1/+1 counters on target creature you control. Then counter up to one target spell unless its controller pays mana equal to the greatest power among creatures you control.", None, 'GU'),
    real('Probe Soldier', '{1}{W}', 2, 'Creature — Human Soldier', '', ("1", "1"), 'W'),
    real('Probe Burst', '{R}', 1, 'Instant', 'Probe Burst deals 1 damage to any target.', None, 'R'),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Frost Titan", "Diffusion Sliver"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _target(cards, victim, pay):
    s = build(cards, [victim, "Probe Burst"], ["Probe Burst"])
    titan = put(s, victim)
    burst, mine = to_hand(s, "Probe Burst", "p2"), to_hand(s, "Probe Burst")
    mana(s, "p1", R=1)
    mana(s, "p2", R=1, C=2)  # (the {2} is in the pool: PAY is offered only while it is payable, 118.3)
    act(s, "p1", type="cast_spell", card_id=mine.id, targets=["p2"])  # (Alice's own spell: Bob answers it)
    act(s, "p2", type="cast_spell", card_id=burst.id, targets=[titan.id])
    d = None
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None or not s.state.rules.stack:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p2" and [o.id for o in d.options] == ["pay", "decline"]
    answer(s, "pay" if pay else "decline")
    return s, titan, burst


@pytest.mark.parametrize("victim", ["Frost Titan", "Diffusion Sliver"])
def test_the_targeting_player_pays_or_the_spell_is_countered(cards, victim):
    s, titan, burst = _target(cards, victim, pay=False)
    assert zone_of(s, "Probe Burst", "p2") == "p2:graveyard" and s.state.cards[titan.id].damage == 0
    check(s)
    s, titan, burst = _target(cards, victim, pay=True)
    assert s.state.cards[titan.id].damage == 1 or s.state.cards[titan.id].zone == "p1:graveyard"  # (the Burst resolved: the 1/1 Sliver died)
    check(s)


@pytest.mark.parametrize("alice_mana,paid", [(2, False), (3, True)])
def test_pays_mana_equal_to_the_greatest_power_after_the_counters(cards, alice_mana, paid):
    """608.2c: the counters go on first, so X = 2 makes Bob's 1/1 a 3/3 and the cost {3} (608.2h: read as it resolves)."""
    s = build(cards, ["Probe Burst"], ["Repulsive Mutation", "Probe Soldier"])
    soldier = put(s, "Probe Soldier", "p2")
    mutation, burst = to_hand(s, "Repulsive Mutation", "p2"), to_hand(s, "Probe Burst")
    mana(s, "p1", R=1, C=alice_mana)
    mana(s, "p2", G=1, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=burst.id, targets=["p2"])
    act(s, "p2", type="cast_spell", card_id=mutation.id, targets=[soldier.id, burst.id], target_counts=[1, 1], x_value=2)
    d = None
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None or not s.state.rules.stack:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    if paid:
        assert d is not None and d.player == "p1" and [o.id for o in d.options] == ["pay", "decline"]
        answer(s, "pay")
    else:
        assert d is None or d.kind != "choose_one"  # (118.3: {3} can't be paid from {2}: no offer, it is countered)
    settle(s)
    assert s.state.cards[soldier.id].counters.get("+1/+1") == 2
    assert life(s, "p2") == (39 if paid else 40) and zone_of(s, "Probe Burst") == "p1:graveyard"
    check(s)
