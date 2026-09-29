"""Tabletop object behaviour: rotation, lock/protect, attachments, groups, stacks, mana."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.fixtures.cards import GOBLIN
from tests.game_helpers import act, find, make_session, zone


@pytest.fixture()
def s(cards):
    session = make_session(cards)
    act(session, "p1", type="draw", count=15)
    return session


def play(s, name, x=100, y=100):
    c = find(s.state, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "battlefield"}, x=x, y=y)
    return c


def test_rotation_is_independent_of_tapping(s):
    sol = play(s, "Sol Ring")
    act(s, "p1", type="rotate", card_ids=[sol.id], delta=45)
    act(s, "p1", type="tap", card_ids=[sol.id])
    assert sol.rotation == 45 and sol.tapped
    act(s, "p1", type="rotate", card_ids=[sol.id], degrees=-30)
    assert sol.rotation == 330


def test_locked_cards_do_not_move(s):
    sol = play(s, "Sol Ring")
    act(s, "p1", type="set_lock", card_ids=[sol.id], value=True)
    with pytest.raises(ActionError, match="locked"):
        act(s, "p1", type="set_position", moves=[[sol.id, 5, 5]])
    with pytest.raises(ActionError, match="locked"):
        act(s, "p1", type="move", card_ids=[sol.id], to={"zone": "graveyard"})
    sol = s.state.cards[sol.id]  # failed actions rebuild state from history
    act(s, "p1", type="tap", card_ids=[sol.id])  # tapping is still allowed
    act(s, "p1", type="set_lock", card_ids=[sol.id])
    act(s, "p1", type="set_position", moves=[[sol.id, 5, 5]])
    assert (sol.x, sol.y) == (5, 5)


def test_commanders_protected_and_protected_tokens_need_force(s):
    assert find(s.state, "Krenko, Mob Boss").protected
    act(s, "p1", type="create_token", token={"card_id": GOBLIN["id"]})
    tok = next(c for c in s.state.cards.values() if c.is_token)
    act(s, "p1", type="set_protect", card_ids=[tok.id], value=True)
    with pytest.raises(ActionError, match="protected"):
        act(s, "p1", type="delete_card", card_ids=[tok.id])
    act(s, "p1", type="delete_card", card_ids=[tok.id], force=True)
    assert tok.id not in s.state.cards


def test_attachments_follow_host_and_detach_when_host_leaves(s):
    elves = play(s, "Llanowar Elves", 300, 300)
    sol = play(s, "Sol Ring", 10, 10)
    act(s, "p1", type="attach", card_ids=[sol.id], to=elves.id)
    assert sol.attached_to == elves.id
    ids = zone(s.state, "p1", "battlefield")
    assert ids.index(sol.id) < ids.index(elves.id)  # tucked underneath
    act(s, "p1", type="set_position", moves=[[elves.id, 400, 350]])
    assert (sol.x - elves.x, sol.y - elves.y) == sol.attach_offset
    act(s, "p1", type="set_position", moves=[[elves.id, 100, 100]], with_attachments=False)
    assert (sol.x, sol.y) != (100 + sol.attach_offset[0], 100 + sol.attach_offset[1])
    with pytest.raises(ActionError):
        act(s, "p1", type="attach", card_ids=[elves.id], to=sol.id)  # cycle
    elves, sol = s.state.cards[elves.id], s.state.cards[sol.id]
    act(s, "p1", type="move", card_ids=[elves.id], to={"zone": "graveyard"})
    assert sol.attached_to is None and sol.zone == "p1:battlefield"
    s.undo("p1")
    assert s.state.cards[sol.id].attached_to == elves.id  # attachment survives undo


def test_groups(s):
    a, b = play(s, "Sol Ring"), play(s, "Llanowar Elves")
    act(s, "p1", type="group", card_ids=[a.id, b.id])
    assert a.group and a.group == b.group
    act(s, "p1", type="ungroup", card_ids=[a.id])
    assert a.group is None and b.group is None


def test_token_stacks(s):
    act(s, "p1", type="create_token", token={"card_id": GOBLIN["id"]}, count=12)
    stack = next(c for c in s.state.cards.values() if c.is_token)
    assert stack.quantity == 12 and len([c for c in s.state.cards.values() if c.is_token]) == 1
    act(s, "p1", type="stack_adjust", card_id=stack.id, delta=5)
    assert stack.quantity == 17
    act(s, "p1", type="split_stack", card_id=stack.id, count=4)
    small = next(c for c in s.state.cards.values() if c.is_token and c.id != stack.id)
    assert (stack.quantity, small.quantity) == (13, 4)
    act(s, "p1", type="tap", card_ids=[small.id])
    with pytest.raises(ActionError, match="identical"):
        act(s, "p1", type="merge_tokens", card_ids=[stack.id, small.id])
    stack, small = s.state.cards[stack.id], s.state.cards[small.id]
    act(s, "p1", type="tap", card_ids=[small.id])
    act(s, "p1", type="merge_tokens", card_ids=[stack.id, small.id])
    assert stack.quantity == 17 and small.id not in s.state.cards
    act(s, "p1", type="expand_stack", card_id=stack.id)
    assert len([c for c in s.state.cards.values() if c.is_token]) == 17
    with pytest.raises(ActionError, match="real cards never merge"):
        act(s, "p1", type="merge_tokens", card_ids=[stack.id, play(s, "Sol Ring").id])
    small_create = act(s, "p1", type="create_token", token={"card_id": GOBLIN["id"]}, count=3)
    assert small_create.stacked is False  # small counts stay individual by default


def test_mana_pool_is_manual_unless_the_table_opts_in(s):
    act(s, "p1", type="add_mana", mana={"C": 2, "G": 1})
    assert s.state.players["p1"].mana == {"C": 2, "G": 1}
    act(s, "p1", type="add_mana", mana={"C": -1})
    assert s.state.players["p1"].mana == {"C": 1, "G": 1}
    act(s, "p1", type="phase", to="next")
    assert s.state.players["p1"].mana == {"C": 1, "G": 1}  # conservative default: nothing clears itself
    act(s, "p1", type="clear_mana")
    assert s.state.players["p1"].mana == {}
    act(s, "p1", type="configure", clear_mana_on_step=True)
    act(s, "p1", type="add_mana", mana={"R": 3})
    act(s, "p1", type="phase", to="next")
    assert s.state.players["p1"].mana == {}
