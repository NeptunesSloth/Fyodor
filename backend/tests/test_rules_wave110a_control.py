"""Wave 110A: a permanent that enters under an opponent's control, and an effect that makes you declare another player's attackers/blockers.

* Captive Audience, Pendant of Prosperity - "enters under the control of an opponent of your choice" (110.2, 614.12): the permanent is given to the
  chosen opponent while still a spell on the stack, so it enters under them. Pendant's second sentence is done by the artifact's owner (108.3).
* Master Warcraft, Melee, Odric - "You choose which creatures attack/block ..." (508.1a, 509.1a): the effect's controller makes the declaration for
  the active/defending player (the legality of the declaration is unchanged) and learns nothing hidden about that player. Melee's watch: 509.3g,
  506.4 (an unblocked attacker is untapped and removed from combat).
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.visibility import can_see
from tests.wave110a_kit import *

AUDIENCE, PENDANT, WARCRAFT, MELEE, ODRIC = "Captive Audience", "Pendant of Prosperity", "Master Warcraft", "Melee", "Odric, Master Tactician"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([AUDIENCE, PENDANT, WARCRAFT, MELEE, ODRIC])


@pytest.mark.parametrize("name", [AUDIENCE, PENDANT])
def test_enters_under_the_opponents_control(cards, name):
    s = build(cards, [name])
    c = cast(s, name)
    answer(s)
    assert zone_of(s, name) == "p2:battlefield" and s.state.cards[c.id].controller == "p2" and s.state.cards[c.id].owner == "p1"
    check(s)


def test_pendant_gives_both_players_a_card_and_a_land(cards):
    s = build(cards, [PENDANT, "Forest", "Island"], ["Forest", "Island"])
    cast(s, PENDANT)
    answer(s)
    pendant = card_named(s, PENDANT)
    forest, island = to_hand(s, "Forest", "p1"), to_hand(s, "Island", "p2")
    lib1, lib2 = len(s.state.zones["p1:library"]), len(s.state.zones["p2:library"])
    goto(s, "main1", "p2")
    fund(s, "{2}", "p2")
    act(s, "p2", type="activate_ability", card_id=pendant.id, ability=1, sources=[])
    answer(s)
    assert len(s.state.zones["p1:library"]) == lib1 - 1 and len(s.state.zones["p2:library"]) == lib2 - 2  # (p2 also drew for the turn)
    assert s.state.cards[forest.id].zone == "p1:battlefield" and s.state.cards[island.id].zone == "p2:battlefield"  # each may put a land: the first option
    check(s)


def test_master_warcraft_lets_the_caster_declare_the_attack_and_the_blocks(cards):
    s = build(cards, [WARCRAFT, "Grizzly Bears"], ["Hill Giant", "Grizzly Bears"])
    mine = put(s, "Grizzly Bears")
    theirs = put(s, "Hill Giant", "p2")
    wall = put(s, "Grizzly Bears", "p2")
    next_turn(s)
    stops(s)
    fund(s, "{2}{R}{R}")
    cast(s, WARCRAFT, pid="p1", pay=False)
    answer(s)
    to_phase(s, "declare_attackers")
    d = s.state.rules.decision
    assert d.kind == "declare_attackers" and d.player == "p1" and d.decider is None  # (the caster is the active player: the same person)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": mine.id, "target": "p2"}])
    to_phase(s, "declare_blockers")
    d = s.state.rules.decision
    assert d.kind == "declare_blockers" and d.player == "p2" and d.decider == "p1" and d.blind
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[])  # Bob doesn't declare them
    act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": theirs.id, "attacker_id": mine.id}])
    assert s.state.cards[theirs.id].is_blocking and not s.state.cards[wall.id].is_blocking
    check(s)


def test_the_chooser_of_blocks_sees_nothing_hidden_of_the_defender(cards):
    s = build(cards, [WARCRAFT, "Grizzly Bears"], ["Hill Giant", "Grizzly Bears"])
    mine = put(s, "Grizzly Bears")
    theirs = put(s, "Hill Giant", "p2")
    secret = to_hand(s, "Grizzly Bears", "p2")
    next_turn(s)
    stops(s)
    fund(s, "{2}{R}{R}")
    cast(s, WARCRAFT, pid="p1", pay=False)
    answer(s)
    attack(s, mine)
    to_phase(s, "declare_blockers")
    assert s.state.rules.decision.decider == "p1"
    assert not can_see(s.state, s.state.cards[secret.id], "p1")  # 723.4 does not apply: only the choice moves
    assert theirs.id in {o.card_id for o in s.state.rules.decision.options}


def attack(s, *attackers):
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])


def test_melee_untaps_and_removes_an_unblocked_attacker(cards):
    s = build(cards, [MELEE, "Grizzly Bears", "Hill Giant"], ["Hill Giant"])
    a, b = put(s, "Grizzly Bears"), put(s, "Hill Giant")
    wall = put(s, "Hill Giant", "p2")
    next_turn(s)
    stops(s)
    attack(s, a, b)
    cast(s, MELEE)
    answer(s)
    to_phase(s, "declare_blockers")
    d = s.state.rules.decision
    assert d.kind == "declare_blockers" and d.player == "p2" and d.decider == "p1"
    act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": wall.id, "attacker_id": a.id}])
    answer(s)
    assert s.state.cards[wall.id].is_blocking and not s.state.cards[b.id].is_attacking and not s.state.cards[b.id].tapped
    assert s.state.cards[a.id].is_attacking
    check(s)


def test_melee_ends_with_the_combat(cards):
    """The choice lasts "this combat" (it is dropped as the combat ends)."""
    s = build(cards, [MELEE, "Grizzly Bears"], ["Hill Giant"])
    a = put(s, "Grizzly Bears")
    wall = put(s, "Hill Giant", "p2")
    next_turn(s)
    stops(s)
    attack(s, a)
    cast(s, MELEE)
    answer(s)
    to_phase(s, "declare_blockers")
    act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": wall.id, "attacker_id": a.id}])
    answer(s)
    to_phase(s, "main2")
    assert not s.state.rules.declare_choosers
    check(s)


def test_odric_chooses_the_blocks_when_attacking_with_four(cards):
    s = build(cards, [ODRIC, "Grizzly Bears", "Hill Giant", "Llanowar Elves"], ["Hill Giant"])
    odric = put(s, ODRIC)
    bears = [put(s, n) for n in ("Grizzly Bears", "Hill Giant", "Llanowar Elves")]
    wall = put(s, "Hill Giant", "p2")
    next_turn(s)
    stops(s)
    attack(s, odric, *bears)
    answer(s)
    to_phase(s, "declare_blockers")
    d = s.state.rules.decision
    assert d.kind == "declare_blockers" and d.player == "p2" and d.decider == "p1"
    act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": wall.id, "attacker_id": bears[0].id}])
    assert s.state.cards[wall.id].is_blocking
    check(s)


def test_odric_with_only_three_attackers_leaves_the_blocks_to_the_defender(cards):
    s = build(cards, [ODRIC, "Grizzly Bears", "Hill Giant"], ["Hill Giant"])
    odric = put(s, ODRIC)
    bears = [put(s, n) for n in ("Grizzly Bears", "Hill Giant")]
    put(s, "Hill Giant", "p2")
    next_turn(s)
    stops(s)
    attack(s, odric, *bears)
    answer(s)
    to_phase(s, "declare_blockers")
    d = s.state.rules.decision
    assert d.kind == "declare_blockers" and d.decider is None


def test_master_warcraft_cast_by_the_defender_declares_the_active_players_attackers(cards):
    """508.1a: the caster declares which creatures attack for the active player, who may not."""
    s = build(cards, ["Grizzly Bears", "Hill Giant", *["Forest"] * 8], ["Llanowar Elves", WARCRAFT, *["Island"] * 8])
    a, b = put(s, "Grizzly Bears"), put(s, "Hill Giant")
    put(s, "Llanowar Elves", "p2")
    next_turn(s)
    stops(s)
    act(s, "p1", type="pass_priority")
    assert s.state.turn.phase == "main1" and s.state.rules.priority == "p2"
    fund(s, "{2}{R}{R}", "p2")
    cast(s, WARCRAFT, pid="p2", pay=False)
    answer(s)
    to_phase(s, "declare_attackers")
    d = s.state.rules.decision
    assert d.kind == "declare_attackers" and d.player == "p1" and d.decider == "p2" and d.blind
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[])
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2"}])
    assert s.state.cards[a.id].is_attacking and not s.state.cards[b.id].is_attacking
    check(s)
