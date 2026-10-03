"""Conditions (app/rules/conditions.py): "If [condition], [effect]" (608.2c) and intervening-if
triggers (603.4: the condition is checked as the ability triggers and again as it resolves)."""

from __future__ import annotations

import pytest

from app.rules import conditions, selectors
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, mana, named, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches


def key(phrase):
    return selectors.parse(phrase).key()


@pytest.mark.parametrize(("text", "expected"), [
    ("you control a Forest", {"value": {"count": key("Forest you control")}, "op": ">=", "n": 1}),
    ("you control two or more Goblins", {"value": {"count": key("Goblins you control")}, "op": ">=", "n": 2}),
    ("you control no creatures", {"value": {"count": key("creatures you control")}, "op": "==", "n": 0}),
    ("you don't control a Forest", {"value": {"count": key("Forest you control")}, "op": "==", "n": 0}),
    ("an opponent controls an artifact", {"value": {"count": key("artifact an opponent controls")}, "op": ">=", "n": 1,
                                          "per_opponent": True}),
    ("you have 5 or less life", {"value": {"life": "you"}, "op": "<=", "n": 5}),
    ("you have no cards in hand", {"value": {"hand": "you"}, "op": "==", "n": 0}),
])
def test_parse(text, expected):
    assert conditions.parse(text) == expected


@pytest.mark.parametrize("text", ["you do", "it was kicked", "you sacrificed a tapped creature this turn", "you control a foo"])
def test_unknown_conditions(text):
    assert conditions.parse(text) is None


def _activate(s, card, **kw):
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=card.id, ability=0, **kw)
    pass_until_stack_empty(s)


def test_if_sentence_skips_only_its_own_effects(cards):
    s = build(cards)
    src = token(s, "p1", "Sage", text="{1}: If you control two or more Goblins, draw a card. You gain 1 life.")
    hand = len(zone(s.state, "p1", "hand"))
    _activate(s, src)
    assert len(zone(s.state, "p1", "hand")) == hand and s.state.players["p1"].life == 41  # no Goblins: no draw
    act(s, "p1", type="create_token", player="p1", token={"name": "G1", "type_line": "Token Creature — Goblin"})
    act(s, "p1", type="create_token", player="p1", token={"name": "G2", "type_line": "Token Creature — Goblin"})
    _activate(s, src)
    assert len(zone(s.state, "p1", "hand")) == hand + 1 and s.state.players["p1"].life == 42
    replay_matches(s)


WATCHER = "Whenever another creature you control enters, if you control a Forest, you gain 1 life."
RECRUITER = "{1}: Create a 1/1 white Soldier creature token."


def test_intervening_if_false_doesnt_trigger(cards):
    s = build(cards)
    token(s, "p1", "Warden", text=WATCHER)
    src = token(s, "p1", "Recruiter", text=RECRUITER)
    _activate(s, src)
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 40 and not s.state.rules.pending_triggers


def test_intervening_if_true_triggers(cards):
    s = build(cards)
    act(s, "p1", type="move", card_ids=[named(s, "Forest").id], to={"zone": "battlefield"})
    token(s, "p1", "Warden", text=WATCHER)
    src = token(s, "p1", "Recruiter", text=RECRUITER)
    _activate(s, src)
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 41
    replay_matches(s)


def test_intervening_if_rechecked_on_resolution(cards):
    s = build(cards)
    forest = named(s, "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "battlefield"})
    s.state.rules.prefs_for("p1").hold_priority = True  # (stop with the trigger on the stack)
    token(s, "p1", "Warden", text=WATCHER)
    src = token(s, "p1", "Recruiter", text=RECRUITER)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    for _ in range(6):  # until the Recruiter's ability has resolved and the Warden's trigger waits
        if any(e.name == "Warden" for e in s.state.rules.stack.values()):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert any(e.name == "Warden" for e in s.state.rules.stack.values())
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "hand"})  # no Forest any more
    for _ in range(6):
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.players["p1"].life == 40  # 603.4: it does nothing
