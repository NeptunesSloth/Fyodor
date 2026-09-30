"""Combat trigger variants (app/rules/events.py, triggers.py): whom a creature attacks (508.3a,
508.3b, 508.3e, 508.6), "attacks and isn't blocked" (509.3g, 509.1h), combat damage to a player or
planeswalker (510.2, 120.1), "is dealt combat damage", "attacks while you control …", and the
source that left the battlefield still having dealt its damage (603.10a, 510.2)."""

from __future__ import annotations

import pytest

from app.rules import events, scripts
from tests.game_helpers import act, find
from tests.test_rules_combat import attack, automate, block, creature, table
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_scripts import ch


def life(s, pid):
    return s.state.players[pid].life


def through_combat(s, blocks=None):
    """Play on to the second main phase: each defending player blocks as given (else not at all)."""
    blocks = blocks or {}
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            # (the declaration is the blocking player's private decision: others see no options)
            for other in s.state.players:
                if other != d.player:
                    assert "options" not in s.view(other)["rules"]["decision"]
            block(s, d.player, *blocks.get(d.player, ()))
            continue
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
            continue
        if s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


def walker(s, pid, name="Walker", loyalty=5):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Legendary Planeswalker — Test"})
    w = find(s.state, name, pid)
    act(s, pid, type="counter", card_ids=[w.id], kind="loyalty", delta=loyalty)
    return w


# -- parsing --------------------------------------------------------------------------------------
@pytest.mark.parametrize(("cond", "expected"), [
    ("~ attacks and isn't blocked", {"subject": "self", "event": "unblocked"}),
    ("a creature attacks you or a planeswalker you control", {"event": "attack", "defender": "you_or_pw"}),
    ("a creature with flying attacks you", {"event": "attack", "defender": "you"}),
    ("~ attacks a player", {"event": "attack", "defender": "player", "subject": "self"}),
    ("a player attacks you", {"event": "you_attack", "player": "any", "defender": "you"}),
    ("an opponent attacks you with two or more creatures", {"event": "you_attack", "defender": "you", "min_attackers": 2}),
    ("three or more creatures attack you", {"event": "you_attack", "defender": "you", "min_attackers": 3}),
    ("a player attacks with three or more creatures", {"event": "you_attack", "player": "any", "min_attackers": 3}),
    ("enchanted player is attacked", {"event": "you_attack", "defender": "enchanted_player"}),
    ("~ deals combat damage to a player or planeswalker", {"event": "deal_damage", "to": "player_or_pw", "combat": True}),
    ("~ deals combat damage to a player or battle", {"event": "deal_damage", "to": "player", "combat": True}),
    ("a creature deals combat damage to one of your opponents", {"event": "deal_damage", "to": "opponent"}),
    ("~ is dealt combat damage", {"event": "dealt_damage", "subject": "self", "combat": True}),
    ("you're dealt combat damage", {"event": "dealt_damage", "subject": "player", "player": "you", "combat": True}),
    ("~ attacks for the first time each turn", {"event": "attack", "first_each_turn": True}),
    ("~ or equipped creature attacks", {"event": "attack", "subject": "self_or_host"}),
    ("equipped creature attacks alone", {"event": "attack", "subject": "host", "alone": True}),
])
def test_parse(cond, expected):
    got = events.parse_condition(cond)
    assert got is not None, cond
    assert {k: got.get(k) for k in expected} == expected, got


@pytest.mark.parametrize("cond", [
    "~ attacks a battle",  # (310: battles aren't modelled)
    "~ deals combat damage to a battle",
    "~ deals damage to a player or battle",  # (noncombat damage can reach a battle: 120.3h)
    "~ attacks while saddled",  # (702.171: saddle isn't modelled)
    "~ attacks while you control a foo",
])
def test_refused(cond):
    assert events.parse_condition(cond) is None


def test_while_is_read_as_it_triggers():
    c = events.parse_condition("~ attacks while you control a creature with power 4 or greater")
    assert c is not None and c["event"] == "attack" and c["while"]["op"] == ">="


def test_that_creature_is_the_attacker():
    d = scripts.definitions(ch("Guard", "Creature", "Whenever a creature attacks you or a planeswalker you control, "
                                                    "this creature deals 1 damage to that creature."))
    assert d and d[0]["cond"]["defender"] == "you_or_pw"


# -- "attacks and isn't blocked" (509.3g) ---------------------------------------------------------------
def test_attacks_and_isnt_blocked(cards):
    s = table(cards)
    text = "Whenever this creature attacks and isn't blocked, you gain 2 life."
    a = creature(s, "p1", "Sneak A", "2/2", text)
    b = creature(s, "p1", "Sneak B", "2/2", text)
    guard = creature(s, "p2", "Guard", "0/4")
    automate(s)
    attack(s, (a, "p2"), (b, "p2"))
    assert life(s, "p1") == 40  # (not as attackers are declared: 508.3f)
    through_combat(s, {"p2": [(guard, a)]})
    assert life(s, "p1") == 42  # only the unblocked one
    replay_matches(s)


def test_unblocked_when_nobody_can_block(cards):
    s = table(cards)
    a = creature(s, "p1", "Sneak", "2/2", "Whenever this creature attacks and isn't blocked, you gain 2 life.")
    automate(s)
    attack(s, (a, "p2"))
    through_combat(s)
    assert life(s, "p1") == 42 and life(s, "p2") == 38
    replay_matches(s)


# -- whom it attacks: three players (508.3a, 508.3e, 508.5a) --------------------------------------------
def test_attacks_you_or_a_planeswalker_you_control(cards):
    s = table(cards, players=3)
    creature(s, "p2", "Bob's Watch", "0/1", "Whenever a creature attacks you or a planeswalker you control, you gain 1 life.")
    creature(s, "p3", "Carol's Watch", "0/1", "Whenever a creature attacks you or a planeswalker you control, you gain 1 life.")
    creature(s, "p3", "Carol's Door", "0/1", "Whenever a creature attacks you, you gain 10 life.")
    pw = walker(s, "p3")
    x = creature(s, "p1", "X")
    y = creature(s, "p1", "Y")
    z = creature(s, "p1", "Z")
    automate(s)
    attack(s, (x, "p2"), (y, "p2"), (z, pw.id))
    pass_until_stack_empty(s)
    # Bob: two creatures attack him (one trigger each); Carol: one attacks her planeswalker, none her
    assert life(s, "p2") == 42 and life(s, "p3") == 41
    through_combat(s)
    replay_matches(s)


def test_that_creature_is_the_one_attacking(cards):
    s = table(cards, players=3)
    creature(s, "p3", "Thorns", "0/4", "Whenever a creature attacks you or a planeswalker you control, "
                                       "this creature deals 1 damage to that creature.")
    x = creature(s, "p1", "X", "1/1")
    y = creature(s, "p1", "Y", "1/1")
    automate(s)
    attack(s, (x, "p2"), (y, "p3"))
    pass_until_stack_empty(s)
    assert x.id in s.state.cards and y.id not in s.state.cards  # only the creature attacking Carol
    through_combat(s)
    assert life(s, "p2") == 39 and life(s, "p3") == 40
    replay_matches(s)


def test_a_player_attacks_you_once_per_player_attacked(cards):
    s = table(cards, players=3)
    creature(s, "p2", "Bob's Bell", "0/1", "Whenever a player attacks you, you gain 1 life.")
    creature(s, "p3", "Carol's Bell", "0/1", "Whenever an opponent attacks you with two or more creatures, you gain 5 life.")
    x, y, z = (creature(s, "p1", n) for n in ("X", "Y", "Z"))
    automate(s)
    attack(s, (x, "p2"), (y, "p2"), (z, "p3"))
    pass_until_stack_empty(s)
    assert life(s, "p2") == 41  # once, however many creatures attack Bob (508.3e)
    assert life(s, "p3") == 40  # only one creature attacks Carol
    through_combat(s)
    replay_matches(s)


@pytest.mark.parametrize(("n", "gain"), [(2, 0), (3, 1)])
def test_three_or_more_creatures_attack_you(cards, n, gain):
    s = table(cards)
    creature(s, "p2", "Alarm", "0/1", "Whenever three or more creatures attack you, you gain 1 life.")
    attackers = [creature(s, "p1", f"A{i}") for i in range(n)]
    automate(s)
    attack(s, *[(a, "p2") for a in attackers])
    pass_until_stack_empty(s)
    assert life(s, "p2") == 40 + gain
    replay_matches(s)


# -- combat damage: to a player or planeswalker; dealt combat damage; 603.10a ----------------------------
@pytest.mark.parametrize(("text", "gain"), [
    ("Whenever this creature deals combat damage to a player or planeswalker, you gain 1 life.", 1),
    ("Whenever this creature deals combat damage to a player, you gain 1 life.", 0),
    ("Whenever this creature deals combat damage to a planeswalker, you gain 1 life.", 1),
])
def test_damage_to_a_planeswalker(cards, text, gain):
    s = table(cards)
    pw = walker(s, "p2")
    a = creature(s, "p1", "Raider", "2/2", text)
    automate(s)
    attack(s, (a, pw.id))
    through_combat(s)
    assert s.state.cards[pw.id].counters["loyalty"] == 3
    assert life(s, "p1") == 40 + gain, text
    replay_matches(s)


def test_player_or_planeswalker_triggers_for_a_player_too(cards):
    s = table(cards)
    a = creature(s, "p1", "Raider", "2/2", "Whenever this creature deals combat damage to a player or planeswalker, "
                                           "you gain 1 life.")
    automate(s)
    attack(s, (a, "p2"))
    through_combat(s)
    assert life(s, "p1") == 41 and life(s, "p2") == 38
    replay_matches(s)


def test_trampler_that_died_still_dealt_combat_damage(cards):
    # 510.2: all combat damage is dealt at once; the trampler is destroyed by the blocker's damage,
    # and its ability still triggers, looking back to the source as it last existed (603.10a, 608.2h)
    s = table(cards)
    a = creature(s, "p1", "Stomper", "3/1", "Trample\nWhenever this creature deals combat damage to a player, "
                                           "you gain 2 life.")
    chump = creature(s, "p2", "Chump", "1/1")
    automate(s)
    attack(s, (a, "p2"))
    through_combat(s, {"p2": [(chump, a)]})
    assert a.id not in s.state.cards and chump.id not in s.state.cards
    assert life(s, "p2") == 38 and life(s, "p1") == 42
    replay_matches(s)


def test_dealt_combat_damage(cards):
    s = table(cards)
    creature(s, "p2", "Wall", "0/5", "Whenever this creature is dealt combat damage, you gain 3 life.")
    wall = find(s.state, "Wall", "p2")
    creature(s, "p2", "Bob", "0/1", "Whenever you're dealt combat damage, you gain 1 life.")
    a = creature(s, "p1", "A", "2/2")
    b = creature(s, "p1", "B", "2/2")
    automate(s)
    attack(s, (a, "p2"), (b, "p2"))
    through_combat(s, {"p2": [(wall, a)]})
    assert life(s, "p2") == 40 - 2 + 3 + 1
    replay_matches(s)


# -- "attacks while you control …" (the condition is part of the trigger event) --------------------------
@pytest.mark.parametrize(("big", "gain"), [("4/4", 1), ("3/3", 0)])
def test_attacks_while_you_control(cards, big, gain):
    s = table(cards)
    a = creature(s, "p1", "Hopeful", "1/1", "Whenever this creature attacks while you control a creature with power 4 "
                                             "or greater, you gain 1 life.")
    creature(s, "p1", "Friend", big)
    automate(s)
    attack(s, (a, "p2"))
    pass_until_stack_empty(s)
    assert life(s, "p1") == 40 + gain
    replay_matches(s)


def test_first_attack_each_turn_marks_the_creature(cards):
    s = table(cards)
    a = creature(s, "p1", "Eager", "1/1", "Whenever this creature attacks for the first time each turn, you gain 1 life.")
    automate(s)
    attack(s, (a, "p2"))
    pass_until_stack_empty(s)
    assert life(s, "p1") == 41
    replay_matches(s)


def test_one_or_more_attack_a_player_once_per_player(cards):
    # 508.3e: "one or more … attack a player" triggers once for each player attacked
    s = table(cards, players=3)
    creature(s, "p1", "Hobbit Host", "0/1", "Whenever one or more creatures you control attack a player, you gain 1 life.")
    x, y, z = (creature(s, "p1", n) for n in ("X", "Y", "Z"))
    automate(s)
    attack(s, (x, "p2"), (y, "p2"), (z, "p3"))
    pass_until_stack_empty(s)
    assert life(s, "p1") == 42
    through_combat(s)
    replay_matches(s)


def test_unblocked_targets_a_creature_of_its_defending_player(cards):
    # 508.5 / 508.5a: "defending player" of the unblocked creature's own ability is the one it attacks
    s = table(cards, players=3)
    necro = creature(s, "p1", "Necro", "2/2", "Whenever this creature attacks and isn't blocked, "
                                            "destroy target creature defending player controls.")
    bob = creature(s, "p2", "Bob's Wall", "0/1", "Defender")
    carol = creature(s, "p3", "Carol's Wall", "0/1", "Defender")
    automate(s)
    attack(s, (necro, "p3"))
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            block(s, d.player)
            continue
        if d is not None:
            assert {o.id for o in d.options} == {carol.id}  # never Bob's
            assert "options" not in s.view("p2")["rules"]["decision"]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[carol.id])
            continue
        if s.state.turn.phase == "main2":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert carol.id not in s.state.cards and bob.id in s.state.cards
    replay_matches(s)
