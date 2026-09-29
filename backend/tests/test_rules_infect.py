"""Wither (702.80) and infect (702.90): damage to creatures as -1/-1 counters; infect damage to
players as poison counters (ten is lethal, 704.5c)."""

from __future__ import annotations

from tests.test_rules_combat import attack, automate, block, creature, table


def test_wither_puts_counters_instead_of_damage(cards):
    s = table(cards)
    boggart = creature(s, "p1", "Boggart", "2/2", "Wither")
    wall = creature(s, "p2", "Wall", "0/4")
    automate(s)
    attack(s, (boggart, "p2"))
    block(s, "p2", (wall, boggart))
    w = s.state.cards[wall.id]
    assert w.damage == 0 and w.counters.get("-1/-1") == 2


def test_wither_counters_can_kill(cards):
    s = table(cards)
    boggart = creature(s, "p1", "Boggart", "3/3", "Wither")
    bear = creature(s, "p2", "Bear", "2/2")
    automate(s)
    attack(s, (boggart, "p2"))
    block(s, "p2", (bear, boggart))
    assert bear.id not in s.state.cards or not s.state.cards[bear.id].zone.endswith(":battlefield")
    assert s.state.cards[boggart.id].damage == 2  # the Bear's own damage is ordinary


def test_infect_gives_poison_not_life_loss(cards):
    s = table(cards)
    phyrexian = creature(s, "p1", "Phyrexian", "3/3", "Infect")
    automate(s)
    attack(s, (phyrexian, "p2"))
    p2 = s.state.players["p2"]
    assert p2.life == 40 and p2.resources.get("poison") == 3


def test_ten_poison_loses(cards):
    s = table(cards)
    phyrexian = creature(s, "p1", "Phyrexian", "10/10", "Infect")
    automate(s)
    attack(s, (phyrexian, "p2"))
    assert "p2" in s.state.rules.lost


def test_exalted_pumps_a_creature_attacking_alone(cards):
    from tests.test_rules_effects import run_until

    s = table(cards)
    knight = creature(s, "p1", "Knight", "2/2")
    creature(s, "p1", "Squire", "1/1", "Exalted")
    creature(s, "p1", "Squire", "1/1", "Exalted")  # identical triggers: no ordering prompt
    automate(s)
    attack(s, (knight, "p2"))
    run_until(s, lambda s: s.state.players["p2"].life < 40)
    assert s.state.players["p2"].life == 36  # 2 + two exalted triggers


def test_exalted_does_not_trigger_for_two_attackers(cards):
    from tests.test_rules_effects import run_until

    s = table(cards)
    a = creature(s, "p1", "A", "2/2")
    b = creature(s, "p1", "B", "2/2", "Exalted")
    automate(s)
    attack(s, (a, "p2"), (b, "p2"))
    run_until(s, lambda s: s.state.players["p2"].life < 40)
    assert s.state.players["p2"].life == 36
