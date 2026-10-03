"""Wave 14A: the attacking player divides combat damage among the creatures blocking it (510.1c), and a trampler's
excess beyond lethal on every blocker goes where its controller chooses (702.19b; deathtouch makes 1 lethal, 702.2c)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_combat import attack, automate, block, creature, decision, table
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave6c_tokens_pumps import reloaded


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


def choose(s, amounts):
    act(s, "p1", type="choose", decision_id=decision(s).id, amounts=amounts)


def test_two_blockers_the_attacker_divides_freely(cards):
    s = table(cards)
    ogre = creature(s, "p1", "Ogre", "5/5")
    a = creature(s, "p2", "Guard", "2/2")
    b = creature(s, "p2", "Giant", "4/4")
    automate(s)
    attack(s, (ogre, "p2"))
    block(s, "p2", (a, ogre), (b, ogre))
    d = decision(s)
    assert d.kind == "divide" and d.player == "p1" and [o.card_id for o in d.options] == [a.id, b.id]
    reloaded(s)  # a save taken while the division is open
    with pytest.raises(ActionError):
        choose(s, [2, 2])  # all 5 (510.1c)
    choose(s, [0, 5])  # 510.1c: no lethal-first order any more — all of it may go to the Giant
    assert a.id in s.state.cards and b.id not in s.state.cards
    assert s.state.players["p2"].life == 40
    check(s)


def test_trample_excess_only_after_lethal_on_every_blocker(cards):
    s = table(cards)
    wurm = creature(s, "p1", "Wurm", "6/6", "Trample")
    a = creature(s, "p2", "Guard", "2/2")
    b = creature(s, "p2", "Giant", "3/3")
    automate(s)
    attack(s, (wurm, "p2"))
    block(s, "p2", (a, wurm), (b, wurm))
    d = decision(s)
    assert [o.id for o in d.options] == [a.id, b.id, "p2"] and d.display["lethal"] == [2, 3]
    for bad in ([1, 2, 3], [2, 2, 2]):
        with pytest.raises(ActionError, match="lethal"):
            choose(s, bad)  # damage to the player needs lethal on both blockers (702.19b)
    choose(s, [2, 3, 1])
    assert s.state.players["p2"].life == 39 and a.id not in s.state.cards and b.id not in s.state.cards
    check(s)


def test_deathtouch_trample_and_excess_on_a_blocker(cards):
    s = table(cards)
    viper = creature(s, "p1", "Viper", "4/4", "Deathtouch, trample")
    a = creature(s, "p2", "Guard", "3/3")
    automate(s)
    attack(s, (viper, "p2"))
    block(s, "p2", (a, viper))
    assert decision(s).display["lethal"] == [1]  # 702.2c: 1 deathtouch damage is lethal
    choose(s, [4, 0])  # the excess may also stay on the blocker
    assert a.id not in s.state.cards and s.state.players["p2"].life == 40
    check(s)


def test_no_choice_means_no_question(cards):
    s = table(cards)
    wurm = creature(s, "p1", "Wurm", "3/3", "Trample")
    ox = creature(s, "p1", "Ox", "3/3")
    a = creature(s, "p2", "Guard", "3/3")
    b = creature(s, "p2", "Wall", "1/4")
    automate(s)
    attack(s, (wurm, "p2"), (ox, "p2"))
    block(s, "p2", (a, wurm), (b, ox))  # no excess for the trampler, one blocker for the other: auto-assigned
    assert decision(s) is None or decision(s).kind != "divide"
    assert a.id not in s.state.cards
    check(s)
