"""Loyalty abilities (CR 606): activated abilities whose cost puts on or removes loyalty counters,
activated only as a sorcery and once per turn per permanent (606.3), not for more loyalty than
the permanent has (606.6); −X chooses X on activation (107.3k); 0 loyalty dies (704.5i)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, named, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches

WALKER = "+1: You gain 2 life.\n−2: Draw two cards.\n−X: This planeswalker deals X damage to target creature."


def walker(s, loyalty=3, text=WALKER):
    act(s, "p1", type="create_token", player="p1", token={
        "name": "Test Walker", "type_line": "Token Legendary Planeswalker — Test", "text": text})
    w = named(s, "Test Walker")
    act(s, "p1", type="counter", card_ids=[w.id], kind="loyalty", delta=loyalty)
    return w


def use(s, w, ability, **kw):
    act(s, "p1", type="activate_ability", card_id=w.id, ability=ability, **kw)
    pass_until_stack_empty(s)


def test_plus_ability_adds_loyalty_and_resolves(cards):
    s = build(cards)
    w = walker(s)
    use(s, w, 0)
    assert s.state.cards[w.id].counters["loyalty"] == 4 and s.state.players["p1"].life == 42
    replay_matches(s)


def test_only_one_loyalty_ability_per_turn(cards):
    s = build(cards)
    w = walker(s)
    use(s, w, 0)
    with pytest.raises(ActionError, match="already used a loyalty ability"):
        act(s, "p1", type="activate_ability", card_id=w.id, ability=1)


def test_minus_ability_needs_the_loyalty(cards):
    s = build(cards)
    w = walker(s, loyalty=1)
    with pytest.raises(ActionError, match="enough loyalty"):  # 606.6
        act(s, "p1", type="activate_ability", card_id=w.id, ability=1)
    hand = len(zone(s.state, "p1", "hand"))
    act(s, "p1", type="counter", card_ids=[w.id], kind="loyalty", delta=1)
    use(s, w, 1)
    assert len(zone(s.state, "p1", "hand")) == hand + 2
    assert w.id not in s.state.cards  # 0 loyalty: to the graveyard (704.5i); a token then ceases to exist


def test_only_as_a_sorcery(cards):
    s = build(cards)
    w = walker(s)
    src = token(s, "p1", "Slow", text="{1}: You gain 1 life.")
    s.state.rules.prefs_for("p1").hold_priority = True  # (keep priority with it on the stack)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)  # something on the stack
    with pytest.raises(ActionError, match="main phase while the stack is empty"):
        act(s, "p1", type="activate_ability", card_id=w.id, ability=0)


def test_minus_x(cards):
    s = build(cards)
    w = walker(s, loyalty=3)
    ogre = token(s, "p2", "Ogre", "3/3")
    with pytest.raises(ActionError, match="doesn't have 4 loyalty"):
        act(s, "p1", type="activate_ability", card_id=w.id, ability=2, x_value=4, targets=[ogre.id])
    use(s, w, 2, x_value=2, targets=[ogre.id])
    assert s.state.cards[w.id].counters["loyalty"] == 1 and s.state.cards[ogre.id].damage == 2
    replay_matches(s)


def test_a_walker_put_onto_the_battlefield_gets_its_loyalty(cards):
    # 306.5b: "enters with" its printed loyalty however it enters
    s = build(cards, "Test Walker Card")
    jace = named(s, "Test Walker Card")
    act(s, "p1", type="move", card_ids=[jace.id], to={"zone": "graveyard"})
    src = token(s, "p1", "Necro", text="{1}: Return target planeswalker card from your graveyard to the battlefield.")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    use(s, src, 0, targets=[jace.id])
    assert s.state.cards[jace.id].zone == "p1:battlefield" and s.state.cards[jace.id].counters.get("loyalty") == 3
    replay_matches(s)


def test_cast_walker_enters_with_loyalty_and_damage_removes_it(cards):
    # 306.5b on resolution; 120.3c: damage to a planeswalker removes that many loyalty counters
    s = build(cards, "Test Walker Card")
    w = named(s, "Test Walker Card")
    act(s, "p1", type="move", card_ids=[w.id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"U": 2, "C": 2})
    act(s, "p1", type="cast_spell", card_id=w.id)
    pass_until_stack_empty(s)
    assert s.state.cards[w.id].zone == "p1:battlefield" and s.state.cards[w.id].counters["loyalty"] == 3
    src = token(s, "p1", "Shock", text="{1}: This creature deals 2 damage to target planeswalker.")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    use(s, src, 0, targets=[w.id])
    assert s.state.cards[w.id].counters["loyalty"] == 1
    replay_matches(s)
