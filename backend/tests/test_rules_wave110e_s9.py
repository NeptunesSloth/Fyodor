"""Wave 110E session 9: Oracle-text scenarios for cards promoted this session (each docstring names the rule)."""
from __future__ import annotations

import pytest

import tests.test_rules_wave110e_cards as base
from app.rules import coverage
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import answer, card_db  # noqa: F401  (the fixture)
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

BATTLE = real("Uphill Battle", "{3}{R}", 4, "Enchantment", "Creatures played by your opponents enter tapped.", None, "R")
BEAR = real("Test Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G")
DJINN = real("Djinn Illuminatus", "{3}{U/R}{U/R}", 5, "Creature — Djinn",
             "({U/R} can be paid with either {U} or {R}.)\nFlying\nEach instant and sorcery spell you cast has replicate. The replicate cost is equal to its mana cost. "
             "(When you cast it, copy it for each time you paid its replicate cost. You may choose new targets for the copies.)", ("3", "5"), "UR")
SIP = real("Test Sip", "{U}", 1, "Instant", "You gain 1 life.", None, "U")
BOLT = real("Test Tonic", "{1}{G}", 2, "Sorcery", "You gain 1 life.", None, "G")
ARBORIA = real("Arboria", "{2}{G}", 3, "World Enchantment",
               "Creatures can't attack a player unless that player cast a spell or put a nontoken permanent onto the battlefield during their last turn.", None, "G")
base.EXTRA.extend([ARBORIA, BATTLE, BEAR, DJINN, SIP, BOLT])


@pytest.mark.parametrize("name", [c["name"] for c in (BATTLE, DJINN, ARBORIA)])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _cast_bear(cards, battle_owner):
    s = build(cards, ["Test Bear", *(["Uphill Battle"] if battle_owner == "p1" else [])], ["Uphill Battle"] if battle_owner == "p2" else [])
    from tests.game_helpers import act

    put(s, "Uphill Battle", battle_owner)
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Bear").id)
    answer(s)
    return s, card_named(s, "Test Bear")


def test_uphill_battle_opponents_cast_creature_enters_tapped(cards):
    """614.1d, 305.1: a creature an opponent of the controller casts enters tapped."""
    s, bear = _cast_bear(cards, "p2")
    assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.cards[bear.id].tapped
    check(s)


def test_uphill_battle_own_cast_and_non_cast_entries_untapped(cards):
    """Its controller's creatures are not "played by your opponents"; a creature put onto the battlefield (not cast) enters untapped."""
    s, bear = _cast_bear(cards, "p1")
    assert s.state.cards[bear.id].zone == "p1:battlefield" and not s.state.cards[bear.id].tapped
    s = build(cards, ["Test Bear"], ["Uphill Battle"])
    put(s, "Uphill Battle", "p2")
    bear = put(s, "Test Bear")
    assert not s.state.cards[bear.id].tapped
    check(s)


@pytest.mark.parametrize(("spell", "cost"), [("Test Sip", {"U": 3}), ("Test Tonic", {"G": 3, "C": 3})])
def test_djinn_illuminatus_gives_instants_and_sorceries_replicate(cards, spell, cost):
    """702.56a: the spell has replicate (cost = its mana cost); each time paid, one copy (two payments: 3 life in all)."""
    from tests.game_helpers import act
    from tests.wave9c_kit import life

    s = build(cards, ["Djinn Illuminatus", spell])
    put(s, "Djinn Illuminatus")
    mana(s, **cost)
    before = life(s, "p1")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, spell).id, kicker=2)
    answer(s)
    assert life(s, "p1") == before + 3
    check(s)


def test_djinn_illuminatus_gives_no_replicate_to_creature_spells(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act

    s = build(cards, ["Djinn Illuminatus", "Test Bear"])
    put(s, "Djinn Illuminatus")
    mana(s, G=3, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Bear").id, kicker=1)


def _arboria_turn3(cards, p2_does):
    """Alice has Arboria and a creature; Bob's turn 2 is idle, plays a land, casts a spell or makes only a token; then Alice's turn 3 main phase."""
    from tests.game_helpers import act
    from tests.test_rules_conditionals import creature

    s = build(cards, ["Arboria", "Test Bear"], ["Test Sip"])
    put(s, "Arboria")
    bear = put(s, "Test Bear")
    for _ in range(300):
        if s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    if p2_does == "land":
        act(s, "p2", type="play_land", card_id=to_hand(s, "Island", "p2").id)
    elif p2_does == "spell":
        mana(s, "p2", U=1)
        act(s, "p2", type="cast_spell", card_id=to_hand(s, "Test Sip", "p2").id)
        answer(s)
    elif p2_does == "token":
        creature(s, "p2", "Bobbit", "1/1")
    for _ in range(300):
        if s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    return s, bear


@pytest.mark.parametrize(("p2_does", "may_attack"), [("nothing", False), ("token", False), ("land", True), ("spell", True)])
def test_arboria_attack_only_a_player_who_cast_or_put_a_nontoken_permanent_last_turn(cards, p2_does, may_attack):
    """508.1c: creatures can't attack a player unless that player cast a spell or put a nontoken permanent onto the battlefield (a land played counts, a token does not)."""
    from app.rules import combat
    from app.rules.plan import Plan

    s, bear = _arboria_turn3(cards, p2_does)
    plan = Plan(s.state, "p1", s.cards, None)
    assert combat.attack_forbidden(plan, plan.ch(s.state.cards[bear.id]), "p2") is (not may_attack)
    check(s)


def test_arboria_a_player_with_no_turn_yet_cannot_be_attacked(cards):
    """No last turn means no spell and no nontoken permanent: Bob has not taken a turn yet, so Alice's creatures can't attack him."""
    from app.rules import combat
    from app.rules.plan import Plan

    s = build(cards, ["Arboria", "Test Bear"])
    put(s, "Arboria")
    bear = put(s, "Test Bear")
    plan = Plan(s.state, "p1", s.cards, None)
    assert combat.attack_forbidden(plan, plan.ch(s.state.cards[bear.id]), "p2") is True
