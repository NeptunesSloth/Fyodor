"""Wave 110M: Nihiloor. 603.12a: "When you do" triggers once each time the tap is done, one for each opponent; 115.1 / 608.2h: the target's power is capped by the tapped
creature's as it last existed; 611.2b: "for as long as you control Nihiloor"; 508.1 / 603.2: an attack with a creature an opponent owns. Every scenario checks the replay and a save and a load.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave36a_kit import ready
from tests.wave110m_kit import *

NIHILOOR = "Nihiloor"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([NIHILOOR])


def cast_nihiloor(cards, theirs=("Elite Vanguard", "Hill Giant")):
    s = build(cards, [NIHILOOR, "Grizzly Bears", "Murder"], list(theirs), forests=20)
    bears = put(s, "Grizzly Bears")
    ready(s, "Grizzly Bears")
    for n in theirs:
        put(s, n, "p2")
    cast(s, NIHILOOR)
    return s, bears


def test_tapping_a_creature_steals_a_creature_of_no_greater_power(cards):
    s, bears = cast_nihiloor(cards)
    vanguard = card_named(s, "Elite Vanguard", "p2")
    giant = card_named(s, "Hill Giant", "p2")
    answer(s, bears.id)  # tap the Bears (power 2): the only legal target is the Vanguard, the Giant's power is 3
    assert s.state.cards[bears.id].tapped and s.state.cards[vanguard.id].controller == "p1" and s.state.cards[giant.id].controller == "p2"
    check(s)


def test_tapping_nothing_steals_nothing(cards):
    s, bears = cast_nihiloor(cards)
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
    answer(s)
    assert not s.state.cards[bears.id].tapped and card_named(s, "Elite Vanguard", "p2").controller == "p2"
    check(s)


def test_the_steal_ends_when_nihiloor_leaves(cards):
    s, bears = cast_nihiloor(cards)
    vanguard = card_named(s, "Elite Vanguard", "p2")
    answer(s, bears.id)
    assert s.state.cards[vanguard.id].controller == "p1"
    cast(s, "Murder", [card_named(s, NIHILOOR).id])  # (Nihiloor dies by its own controller's spell)
    answer(s)
    assert s.state.cards[vanguard.id].controller == "p2"
    check(s)


def test_attacking_with_a_creature_an_opponent_owns_drains_its_owner(cards):
    s, bears = cast_nihiloor(cards)
    vanguard = card_named(s, "Elite Vanguard", "p2")
    answer(s, bears.id)
    stops(s)
    next_turn(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": vanguard.id, "target": "p2"}, {"card_id": bears.id, "target": "p2"}])
    answer(s)
    assert life(s) == 42 and life(s, "p2") == 38  # (only the creature p2 owns triggers it, not the Bears)
    check(s)


def test_each_opponent_gets_their_own_tap_and_steal(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    setups = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [(1, NIHILOOR), (1, "Grizzly Bears"), (1, "Hill Giant"), (9, "Forest")])),
              PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(1, "Elite Vanguard"), (9, "Island")])),
              PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(1, "Elite Vanguard"), (9, "Forest")]))]
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    bears, giant = put(s, "Grizzly Bears"), put(s, "Hill Giant")
    ready(s, "Grizzly Bears", "Hill Giant")
    bob, carol = put(s, "Elite Vanguard", "p2"), put(s, "Elite Vanguard", "p3")
    cast(s, NIHILOOR)
    answer(s, bears.id, giant.id)  # Bob's turn of the loop taps the Bears, then Carol's taps the Giant
    assert s.state.cards[bears.id].tapped and s.state.cards[giant.id].tapped
    assert s.state.cards[bob.id].controller == s.state.cards[carol.id].controller == "p1"
    check(s)


# -- Timothar, Baron of Bats -------------------------------------------------------------------------------------------------------------------
TIMOTHAR = "Timothar, Baron of Bats"
test_timothar_full = full_test([TIMOTHAR])


def vampire_dies(cards, pay):
    s = build(cards, [TIMOTHAR, "Test Vampire", "Murder"], ["Elite Vanguard"], forests=20)
    put(s, TIMOTHAR)
    vampire = put(s, "Test Vampire")
    cast(s, "Murder", [vampire.id], extra="{1}")  # (the {1} left in the pool is what pays for the trigger)
    d = None
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay" if pay else "decline"])
    answer(s)
    return s, vampire


def test_paying_one_exiles_the_vampire_and_makes_a_bat(cards):
    s, vampire = vampire_dies(cards, True)
    bats = [c for c in s.state.cards.values() if c.name == "Bat" and c.is_token and c.zone == "p1:battlefield"]
    assert len(bats) == 1 and s.state.cards[vampire.id].zone == "p1:exile"
    assert ch(s, bats[0]).pt == (1, 1) and "flying" in ch(s, bats[0]).keywords
    check(s)


def test_declining_leaves_the_vampire_in_the_graveyard(cards):
    s, vampire = vampire_dies(cards, False)
    assert s.state.cards[vampire.id].zone == "p1:graveyard"
    assert not any(c.name == "Bat" for c in s.state.cards.values())
    check(s)


def test_the_bat_trades_itself_for_the_vampire_when_it_hits_a_player(cards):
    s, vampire = vampire_dies(cards, True)
    bat = next(c for c in s.state.cards.values() if c.name == "Bat" and c.is_token)
    stops(s)
    next_turn(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bat.id, "target": "p2"}])
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.turn.phase in ("declare_attackers", "declare_blockers", "combat_damage", "first_strike_damage", "end_combat") or s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert life(s, "p2") == 39 and s.state.cards[vampire.id].zone == "p1:battlefield" and s.state.cards[vampire.id].tapped
    assert not any(c.name == "Bat" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    check(s)
