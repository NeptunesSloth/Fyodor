"""Wave 13B: blocking additional creatures (509.1a) — "can block an additional creature each combat", "can block any number of
creatures", and a blocker dividing its combat damage among the attackers it blocks (510.1d)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act, turn_on
from tests.test_rules_combat import attack, block, creature, decision, table
from tests.test_rules_conditionals import settle
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave6c_tokens_pumps import reloaded

WALL = "This creature can block an additional creature each combat."


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


def board(cards, wall_text=WALL, extra=""):
    s = table(cards)
    a1 = creature(s, "p1", "Raider", "2/2", extra)
    a2 = creature(s, "p1", "Axe", "3/3")
    wall = creature(s, "p2", "Wall", "3/3", wall_text)
    creature(s, "p1", "Third", "1/1")
    creature(s, "p1", "Fourth", "1/1")
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → Alice's main 1
    return s, a1, a2, wall


def to_blocks(s, *attackers):
    act(s, "p1", type="pass_priority")  # → combat
    attack(s, *((a, "p2") for a in attackers))


def test_blocker_with_an_additional_block_divides_its_damage(cards):
    s, a1, a2, wall = board(cards)
    to_blocks(s, a1, a2)
    block(s, "p2", (wall, a1), (wall, a2))
    d = decision(s)
    assert d.kind == "divide" and d.player == "p2" and [o.card_id for o in d.options] == [a1.id, a2.id]
    with pytest.raises(ActionError):
        act(s, "p2", type="choose", decision_id=d.id, amounts=[1, 1])  # must add up to its power (510.1d)
    act(s, "p2", type="choose", decision_id=d.id, amounts=[3, 0])  # a share may be 0
    st = s.state
    assert a1.id not in st.cards  # the 2/2 token took 3 and died
    assert st.cards[a2.id].zone == "p1:battlefield"
    assert wall.id not in st.cards  # 2 + 3 damage from the two attackers
    check(s)


def test_one_block_only_without_the_extra_ability(cards):
    s, a1, a2, wall = board(cards, wall_text="")
    to_blocks(s, a1, a2)
    with pytest.raises(ActionError, match="only block one"):
        block(s, "p2", (wall, a1), (wall, a2))
    with pytest.raises(ActionError, match="twice"):
        block(s, "p2", (wall, a1), (wall, a1))


def test_additions_stack_and_this_turn_effects_count(cards):
    s, a1, a2, wall = board(cards, extra="{0}: Target creature can block an additional creature this turn.")
    a3, a4 = (next(c for c in s.state.cards.values() if c.name == n) for n in ("Third", "Fourth"))
    for _ in range(2):
        act(s, "p1", type="activate_ability", card_id=a1.id, ability=0, targets=[wall.id])
        settle(s)
    to_blocks(s, a1, a2, a3, a4)  # the wall's own ability and two activations: four attackers
    block(s, "p2", (wall, a1), (wall, a2), (wall, a3), (wall, a4))
    assert decision(s).kind == "divide"
    act(s, "p2", type="choose", decision_id=decision(s).id, amounts=[1, 1, 1, 0])
    check(s)


def test_must_be_blocked_is_still_required_of_a_blocker_with_a_block_to_spare(cards):
    s, a1, a2, wall = board(cards, extra="This creature must be blocked if able.")
    to_blocks(s, a1, a2)
    with pytest.raises(ActionError, match="must be blocked"):
        block(s, "p2", (wall, a2))
    block(s, "p2", (wall, a2), (wall, a1))
    act(s, "p2", type="choose", decision_id=decision(s).id, amounts=[1, 2])
    check(s)


def test_any_number_and_a_trigger_counting_the_creatures_it_blocks(cards):
    text = ("This creature can block any number of creatures.\n"
            "Whenever this creature blocks, it gets +1/+1 until end of turn for each creature it's blocking.")
    s, a1, a2, wall = board(cards, wall_text=text)
    to_blocks(s, a1, a2)
    block(s, "p2", (wall, a1), (wall, a2))
    while decision(s) is None:  # the trigger resolves, then the damage step asks
        act(s, s.state.rules.priority, type="pass_priority")
    d = decision(s)
    assert d.kind == "divide" and d.display["total"] == 5  # a 3/3 that blocks two creatures is a 5/5 (510.1a)
    act(s, "p2", type="choose", decision_id=d.id, amounts=[2, 3])
    assert a1.id not in s.state.cards and a2.id not in s.state.cards  # (the 5/5 takes 5 as well)
    check(s)
