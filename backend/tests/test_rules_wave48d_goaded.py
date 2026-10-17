"""Wave 48D: a goaded creature through last known information (CR 2026-09-25), real Oracle text (tests/fixtures/wave48d_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 701.15b: a goaded creature is a designation of the object (goad has no Oracle meaning except through the effect), so "Whenever a goaded creature dies" asks
  whether it was goaded as it last existed (603.10a, 608.2h); a creature that is not goaded (or no longer is, 701.15a) does not count.
* Baeloth Barrityl: "Whenever a goaded attacking or blocking creature dies, you create a Treasure token."
* Puppet Master: "Whenever one or more goaded creatures deal combat damage to one of your opponents, create a Treasure token." (Disrupt Decorum goads Bob's
  creature; in a three-player game it attacks Carol, a player other than Alice who goaded it)
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave34b_activated import stops
from tests.wave9c_kit import build, check, mana, put, to_hand
from tests.wave47b_kit import build3
from tests.wave48d_kit import cast, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


def until(s, ok, limit=200):
    for _ in range(limit):
        if ok(s):
            return
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never got there")


def asked(kind, player):
    return lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == kind and s.state.rules.decision.player == player


def treasures(s, pid="p1"):
    return len([c for c in s.state.cards.values() if c.name == "Treasure" and c.owner == pid and c.zone.endswith("battlefield")])


def ready(s, name, pid):
    c = put(s, name, pid)
    s.state.rules.controlled_since[c.id].turn = 0  # (no summoning sickness on Bob's turn)
    return c


def baeloth_table(cards):
    s = build(cards, ["Baeloth Barrityl, Entertainer", "Shock"], ["Llanowar Elves", "Grizzly Bears"])
    baeloth = ready(s, "Baeloth Barrityl, Entertainer", "p1")
    return s, baeloth, ready(s, "Llanowar Elves", "p2"), ready(s, "Grizzly Bears", "p2")


def bobs_attack(s, *attackers):
    """Bob's declare attackers step: these creatures attack Alice, who is asked to block next."""
    stops(s)
    until(s, asked("declare_attackers", "p2"))
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p1"} for a in attackers])
    until(s, asked("declare_blockers", "p1"))


def block(s, blocker, attacker):
    act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": attacker.id}])
    until(s, lambda s: s.state.turn.phase == "end_combat")


def test_baeloth_makes_a_treasure_when_a_goaded_attacking_creature_dies(cards):
    s, baeloth, elves, _ = baeloth_table(cards)
    bobs_attack(s, elves)  # power 1 is less than Baeloth's 2: goaded, it has to attack a player other than Alice if able (and can only attack her)
    block(s, baeloth, elves)
    assert s.state.cards[elves.id].zone == "p2:graveyard"
    assert treasures(s) == 1  # 603.10a: it was goaded as it last existed
    check(s)


def test_baeloth_ignores_an_attacking_creature_that_was_not_goaded(cards):
    s, baeloth, elves, bears = baeloth_table(cards)
    bobs_attack(s, elves, bears)  # the Elves are goaded and have to attack; the Bears' power 2 is not less than Baeloth's 2: not goaded
    block(s, baeloth, bears)
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    assert treasures(s) == 0
    check(s)


def test_baeloth_ignores_a_goaded_creature_that_dies_outside_combat(cards):
    s, _, elves, _ = baeloth_table(cards)
    to_hand(s, "Shock")
    mana(s, R=1)
    cast(s, "Shock", targets=[elves.id])
    assert s.state.cards[elves.id].zone == "p2:graveyard"
    assert treasures(s) == 0  # goaded, but neither attacking nor blocking
    check(s)


def puppet_table(cards):
    s = build3(cards, ["Puppet Master, String Puller", "Disrupt Decorum"], bobs=["Hill Giant", "Llanowar Elves"], carols=[])
    put(s, "Puppet Master, String Puller")
    giant = ready(s, "Hill Giant", "p2")
    return s, giant


def goaded_attack(s, giant, victim="p3"):
    """Alice goads Bob's creatures (Disrupt Decorum), Bob's turn: the Hill Giant attacks Carol."""
    to_hand(s, "Disrupt Decorum")
    mana(s, R=2, C=2)
    cast(s, "Disrupt Decorum")
    stops(s)
    until(s, asked("declare_attackers", "p2"))
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": giant.id, "target": victim}])
    until(s, lambda s: s.state.turn.phase == "end_combat")


def test_puppet_master_makes_a_treasure_when_a_goaded_creature_hurts_another_opponent(cards):
    s, giant = puppet_table(cards)
    goaded_attack(s, giant)
    assert s.state.players["p3"].life == 37
    assert treasures(s) == 1
    check(s)


def test_puppet_master_ignores_a_creature_that_is_not_goaded(cards):
    s, giant = puppet_table(cards)
    stops(s)
    until(s, asked("declare_attackers", "p2"))
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": giant.id, "target": "p3"}])
    until(s, lambda s: s.state.turn.phase == "end_combat")
    assert s.state.players["p3"].life == 37 and treasures(s) == 0
    check(s)
