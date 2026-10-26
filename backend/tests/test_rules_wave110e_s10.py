"""Wave 110E session 10: Oracle-text scenarios for cards promoted this session (each docstring names the rule)."""
from __future__ import annotations

import pytest

import tests.test_rules_wave110e_cards as base
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import stops, to_phase
from tests.test_rules_wave110e_cards import answer, card_db, cast  # noqa: F401  (the fixture)
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put

REPROACH = real("Teferi's Reproach", "{2}{W}{W}", 4, "Instant",
                "Choose target opponent. Until that player's next turn, they gain protection from everything and their life total can't change. "
                "All nonland permanents they control phase out. (While they're phased out, they're treated as though they don't exist. "
                "They phase in before that player untaps during their next untap step.)\nExile Teferi's Reproach.", None, "W")
BEAR = real("Test Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G")
DRAIN = real("Test Drain", "{B}", 1, "Sorcery", "Each opponent loses 3 life.", None, "B")
BLADE = real("Sanctuary Blade", "{2}", 2, "Artifact — Equipment",
             "As this Equipment becomes attached to a creature, choose a color.\nEquipped creature gets +2/+0 and has protection from the last chosen color.\nEquip {3}", None, "")
MONITOR = real("Monitor Monitor", "{2}{U}", 3, "Creature — Human Wizard",
               "When this creature enters, open an Attraction. (Put the top card of your Attraction deck onto the battlefield.)\n"
               "Once each turn, you may pay {1} to reroll one or more dice you rolled.", ("1", "3"), "U")
ROLL = real("Test Roll", "{B}", 1, "Sorcery", "Roll a six-sided die. You gain life equal to the result.", None, "B")
base.EXTRA.extend([REPROACH, BEAR, DRAIN, BLADE, MONITOR, ROLL])


@pytest.mark.parametrize("name", ["Teferi's Reproach", "Sanctuary Blade", "Monitor Monitor"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_teferis_reproach_shields_the_opponent_until_their_next_turn(cards):
    """702.16j, 119.7, 702.26: target opponent has protection from everything, life can't change, nonland permanents phase out; all end at their turn."""
    s = build(cards, ["Teferi's Reproach", "Test Drain"], ["Test Bear", "Test Bear"])
    bear = put(s, "Test Bear", "p2")
    mana(s, W=2, C=2, B=1)
    cast(s, "Teferi's Reproach", ["p2"])
    answer(s)
    assert s.state.cards[bear.id].zone.endswith(":phased")
    cast(s, "Test Drain")
    answer(s)
    assert life(s, "p2") == 40
    check(s)
    stops(s, "upkeep")
    to_phase(s, "upkeep", 2)
    assert not s.state.cards[bear.id].zone.endswith(":phased")
    assert not s.state.rules.life_locks and not s.state.rules.player_shields
    check(s)


def _keywords(s, card):
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card.id])
    return {k.lower() for k in ch.keywords} | {a.text.lower() for a in ch.abilities}


def _equip(s, blade, bear, color):
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=blade.id, ability=2, targets=[bear.id])
    answer(s, *([color] if color else []))


def test_sanctuary_blade_chooses_a_color_each_time_it_becomes_attached(cards):
    """701.3a: the controller chooses as it becomes attached (equip); the grant uses the last chosen color: +2/+0 and protection from it."""
    s = build(cards, ["Sanctuary Blade", "Test Bear", "Test Bear"])
    blade, bear = put(s, "Sanctuary Blade"), put(s, "Test Bear")
    _equip(s, blade, bear, "Red")
    assert s.state.cards[bear.id].attached_to is None and s.state.cards[blade.id].attached_to == bear.id
    assert pt(s, "Test Bear") == (4, 2) and "protection from red" in _keywords(s, bear)
    check(s)
    bear2 = card_named(s, "Test Bear")
    other = next(c for c in s.state.cards.values() if c.name == "Test Bear" and c.id != bear.id and c.owner == "p1")
    put_bear = act(s, "p1", type="move", card_ids=[other.id], to={"player": "p1", "zone": "battlefield"})  # noqa: F841
    _equip(s, blade, other, "Green")
    assert s.state.cards[blade.id].attached_to == other.id
    assert "protection from green" in _keywords(s, other) and "protection from red" not in _keywords(s, other)
    assert "protection from red" not in _keywords(s, bear2) or bear2.id == other.id
    check(s)


@pytest.mark.parametrize(("reroll", "second", "life"), [(True, 6, 46), (True, 1, 41), (False, 6, 42)])
def test_monitor_monitor_rerolls_before_the_result_counts(cards, monkeypatch, reroll, second, life):
    """706.2a-b: paying {1} rerolls the chosen dice and the new natural result is final; declining keeps the first roll; once each turn."""
    from tests.test_rules_random_consequences import faces

    s = build(cards, ["Monitor Monitor", "Test Roll", "Test Roll"])
    put(s, "Monitor Monitor")
    faces(monkeypatch, [2, second, 4])
    mana(s, B=1, C=1)
    cast(s, "Test Roll")
    d = s.state.rules.decision
    assert d is not None and d.options[0].id.startswith("roll_adjust42:")
    if not reroll:
        pick(s, ["done"])
    else:
        pick(s, [d.options[0].id])
        assert [o.id for o in s.state.rules.decision.options][0] == "pay"
        pick(s, ["pay"])
        assert s.state.rules.decision.kind == "choose_cards"
        pick(s, ["0"])
    answer(s)
    assert life_of(s) == life
    check(s)
    if reroll:  # once each turn: the second roll is not offered another reroll
        mana(s, B=1, C=1)
        cast(s, "Test Roll")
        answer(s)
        assert life_of(s) == life + 4


def pick(s, ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def life_of(s):
    return s.state.players["p1"].life
