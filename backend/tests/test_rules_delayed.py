"""Delayed triggered abilities (CR 603.7) and effect durations (611.2), app/rules/delayed.py.

A delayed trigger is created as the spell or ability resolves (603.7a) with the objects it refers
to bound then (603.7c: a new object after a zone change isn't them, 400.7), triggers once (603.7b)
at the step or event it names, goes on the stack with the other triggers in APNAP order (603.3b)
and resolves with its own context; it outlives its source, a decision in between, a reload and
undo/redo. "Until your next turn" ends as that turn begins (500.4); "for as long as ~ remains on
the battlefield" ends the moment it leaves (611.2b); "exile … until ~ leaves" returns the card
(610.3) whoever controls ~ by then. Every scenario checks that replay reproduces the table.
"""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_attachments import build, ch, named, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_suspend import until


def rules(s):
    return s.state.rules


def responsive(s):
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack)


def on_battlefield(s, name, pid="p1"):
    c = named(s, name)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def activate(s, card, pid="p1", **kw):
    act(s, pid, type="add_mana", player=pid, mana={"C": 1})
    act(s, pid, type="activate_ability", card_id=card.id, ability=0, **kw)
    pass_until_stack_empty(s)


def next_end_step(s, limit=40):
    """Run on through the next end step (its triggers resolve on the way) into the next turn."""
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn, limit=limit)
    pass_until_stack_empty(s)


def reloaded(s):
    """The table as a fresh session rebuilt from the saved history."""
    return GameSession(s.history.rebuild(), cards=s.cards)


BLINK = "{1}: Exile target creature. Return it to the battlefield under its owner's control at the beginning of the next end step."


# -- the wording (app/rules/scripts.py appended block, app/rules/language.py section) -------------
def parsed(text):
    from app.rules import scripts

    found = scripts.parse_effects(text)
    return found[0] if found else None


@pytest.mark.parametrize("text, head, tail", [
    # trailing and leading "at the beginning of …" (one real card each)
    ("Exile target creature. Return it to the battlefield under its owner's control at the beginning of the next end step.",  # Voyager Staff-style
     {"do": "delayed", "when": {"kind": "step", "step": "end", "whose": "next"}, "n": 1}, "deferred:return_card"),
    ("Create a 1/1 red Elemental creature token. At the beginning of the next end step, sacrifice it.",  # Spinal Embrace-style
     {"do": "delayed", "when": {"kind": "step", "step": "end", "whose": "next"}, "n": 1}, "deferred:sacrifice"),
    ("Create a 1/1 red Elemental creature token. Exile that token at the beginning of your next end step.",  # Akoum Stonewaker
     {"do": "delayed", "when": {"kind": "step", "step": "end", "whose": "you"}, "n": 1}, "deferred:exile"),
    ("Draw a card at the beginning of the next turn's upkeep.",  # Heal
     {"do": "delayed", "when": {"kind": "step", "step": "upkeep", "whose": "next_turn"}, "n": 1}, "deferred:draw"),
    ("Exile target creature you control. Return that card to the battlefield under its owner's control at the beginning of your next upkeep.",  # Kaya, Ghost Assassin
     {"do": "delayed", "when": {"kind": "step", "step": "upkeep", "whose": "you"}, "n": 1}, "deferred:return_card"),
    ("Target creature gets +1/+1 until end of turn. When that creature dies this turn, return it to the battlefield under its owner's control.",  # Graceful Reprieve-style
     {"do": "delayed", "when": {"kind": "event", "event": "die"}, "n": 1, "who": "target", "this_turn": True}, "deferred:return_card"),
    ("Target creature gets +2/+2 until your next turn.", {"do": "until", "duration": "next_turn", "n": 1}, "pump"),  # Garruk, Veiled Butcher-style
    ("Until your next turn, up to one target creature gets -3/-0.", {"do": "until", "duration": "next_turn", "n": 1}, "pump"),  # Jace, the Perfected Mind
    ("Another target permanent gains indestructible for as long as you control ~.",  # Aegis Angel
     {"do": "until", "duration": "source_controlled", "n": 1}, "grant"),
    ("Target creature gets +2/+2 for as long as ~ remains tapped.", {"do": "until", "duration": "source_tapped", "n": 1}, "pump"),  # Flowstone Armor
])
def test_wordings(text, head, tail):
    effects = parsed(text)
    assert effects is not None
    i = next(k for k, e in enumerate(effects) if e["do"] == head["do"])
    assert effects[i] == head and effects[i + 1]["do"] == tail


def test_a_deferred_effect_is_not_an_antecedent_for_a_later_sentence():
    # Elemental Appeal: "that creature" is the token, not what the deferred exile will record
    effects = parsed("Create a 7/1 red Elemental creature token with trample and haste. Exile it at the beginning of the "
                     "next end step. If this spell was kicked, that creature gets +7/+0 until end of turn.")
    assert [e["do"] for e in effects] == ["create_token", "delayed", "deferred:exile", "kicked_gate", "pump"]
    assert effects[2]["who"] == "ref:e0" and effects[4]["who"] == "ref:e0"


def test_pronouns_inside_a_deferred_effect_bind_to_the_earlier_instruction():
    effects = parsed("Exile target creature. Return it to the battlefield under its owner's control at the beginning of the next end step.")
    assert effects[0]["as"] == "e0" and effects[2]["who"] == "ref:e0"
    assert parsed("When that creature dies this turn, return it to its owner's hand.") is None  # (no antecedent: manual)


@pytest.mark.parametrize("text", [
    "Destroy it at the beginning of the next end step if it didn't attack this turn.",  # Norritt: a condition on the deferred effect
    "Target creature gets +2/+2 until your next turn. Draw a card for as long as ~ remains tapped.",  # not a continuous effect
    "When a creature dealt damage this way dies this turn, create a 1/1 black Skeleton creature token.",  # Skeletonize: several objects
    "At the beginning of the next end step, sacrifice it.",  # nothing earlier for "it" to be
])
def test_refusals(text):
    assert parsed(text) is None


def test_tapped_watch_destroys_the_tapped_creature():
    """Wave 110A: tapping makes no new object (701.26a), so "it" is the creature that became tapped (Don't Move)."""
    got = parsed("Exile target creature. Until your next turn, whenever a creature becomes tapped, destroy it.")
    assert got is not None and got[-1] == {"do": "deferred:destroy", "who": "event"}


# -- "at the beginning of the next end step": the object as bound (603.7c) ----------------------
def test_exile_and_return_at_the_next_end_step_survives_a_reload(cards):
    s = build(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    blinker = token(s, "p1", "Blinker", "2/2", text=BLINK)
    activate(s, blinker, targets=[elves.id])
    assert s.state.cards[elves.id].zone == "p1:exile"
    (t,) = rules(s).delayed
    assert t.when == {"kind": "step", "step": "end", "whose": "next"} and t.controller == "p1" and t.once
    assert t.refs["e0"]["objects"][0]["zone"] == "p1:exile"  # the exiled card, where it went (400.7j)
    assert t.model_dump(mode="json") == rules(s).model_dump(mode="json")["delayed"][0]  # JSON-native
    s = reloaded(s)  # (saved and loaded with the trigger waiting)
    assert len(rules(s).delayed) == 1
    next_end_step(s)
    assert s.state.cards[elves.id].zone == "p1:battlefield" and not rules(s).delayed
    replay_matches(s)


def test_delayed_trigger_fires_after_its_source_left(cards):
    s = build(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    blinker = token(s, "p1", "Blinker", "2/2", text=BLINK)
    activate(s, blinker, targets=[elves.id])
    act(s, "p1", type="move", card_ids=[blinker.id], to={"zone": "graveyard"})  # the source is gone
    assert blinker.id not in s.state.cards
    next_end_step(s)
    assert s.state.cards[elves.id].zone == "p1:battlefield"  # 603.7d-e: its controller still controls the ability
    replay_matches(s)


def test_an_object_that_left_and_came_back_is_not_affected(cards):
    # 603.7c / 400.7: the bound object left exile (by hand) and returned: a new object, not "it"
    s = build(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    blinker = token(s, "p1", "Blinker", "2/2", text=BLINK)
    activate(s, blinker, targets=[elves.id])
    act(s, "p1", type="move", card_ids=[elves.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[elves.id], to={"zone": "exile"})
    next_end_step(s)
    assert s.state.cards[elves.id].zone == "p1:exile" and not rules(s).delayed  # it triggered, did nothing, and is spent
    replay_matches(s)


def test_sacrifice_it_at_the_next_end_step_and_undo_redo_in_between(cards):
    s = build(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    src = token(s, "p1", "Firebreather", "2/2",
                text="{1}: Target creature gets +2/+0 until end of turn. Sacrifice it at the beginning of the next end step.")
    activate(s, src, targets=[elves.id])
    assert ch(s, elves).pt == (3, 1)
    act(s, "p1", type="create_token", player="p1", token={"name": "Extra", "type_line": "Token Creature — Test"})
    s.undo("p1")
    s.redo("p1")
    assert len(rules(s).delayed) == 1
    next_end_step(s)
    assert s.state.cards[elves.id].zone == "p1:graveyard"
    replay_matches(s)


def test_two_players_delayed_triggers_go_on_the_stack_in_apnap_order(cards):
    s = build(cards)
    responsive(s)
    alice = token(s, "p1", "Alice Clock", "1/1", text="{1}: Draw a card at the beginning of the next end step.")
    bob = token(s, "p2", "Bob Clock", "1/1", text="{1}: Draw a card at the beginning of the next end step.")
    activate(s, alice)
    act(s, "p1", type="pass_priority")
    assert rules(s).priority == "p2"
    act(s, "p2", type="add_mana", player="p2", mana={"C": 1})
    act(s, "p2", type="activate_ability", card_id=bob.id, ability=0)
    pass_until_stack_empty(s)
    assert {t.controller for t in rules(s).delayed} == {"p1", "p2"}
    until(s, lambda s: s.state.turn.phase == "end", limit=60)
    stack = [rules(s).stack[c] for c in s.state.zones.get("stack", []) if c in rules(s).stack]
    # 603.3b: the active player's goes on first, the other player's on top (so it resolves first)
    assert [e.controller for e in stack] == ["p1", "p2"]
    hands = {p: len(zone(s.state, p, "hand")) for p in ("p1", "p2")}
    act(s, rules(s).priority, type="pass_priority")
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p2", "hand")) == hands["p2"] + 1
    pass_until_stack_empty(s)
    act(s, rules(s).priority, type="pass_priority")
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p1", "hand")) == hands["p1"] + 1
    replay_matches(s)


def test_a_decision_between_creation_and_firing(cards):
    s = build(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    blinker = token(s, "p1", "Blinker", "2/2", text=BLINK)
    activate(s, blinker, targets=[elves.id])
    seer = token(s, "p1", "Seer", "1/1", text="{1}: Scry 1.")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="activate_ability", card_id=seer.id, ability=0)
    pass_until_stack_empty(s)
    d = rules(s).decision
    assert d is not None and len(rules(s).delayed) == 1
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    next_end_step(s)
    assert s.state.cards[elves.id].zone == "p1:battlefield"
    replay_matches(s)


def test_the_next_end_step_created_during_an_end_step_is_the_following_turns(cards):
    s = build(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    blinker = token(s, "p1", "Blinker", "2/2", text=BLINK)
    responsive(s)
    until(s, lambda s: s.state.turn.phase == "end", limit=40)
    activate(s, blinker, targets=[elves.id])
    turn = s.state.turn.number
    assert s.state.cards[elves.id].zone == "p1:exile" and s.state.turn.phase == "end"
    until(s, lambda s: s.state.turn.number > turn, limit=40)
    assert s.state.cards[elves.id].zone == "p1:exile"  # not this end step: it had already begun
    until(s, lambda s: s.state.turn.phase == "end", limit=60)
    until(s, lambda s: s.state.turn.number > turn + 1, limit=40)
    assert s.state.cards[elves.id].zone == "p1:battlefield"
    replay_matches(s)


def test_draw_at_the_beginning_of_the_next_turns_upkeep(cards):
    s = build(cards)
    src = token(s, "p1", "Bauble", "1/1", text="{1}: Draw a card at the beginning of the next turn's upkeep.")
    activate(s, src)
    hand = len(zone(s.state, "p1", "hand"))
    responsive(s)
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn and s.state.turn.phase == "upkeep", limit=60)
    assert s.state.turn.active_player == "p2" and len(zone(s.state, "p1", "hand")) == hand
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p1", "hand")) == hand + 1
    replay_matches(s)


def test_a_dies_trigger_deferring_to_the_end_step_keeps_its_event(cards):
    s = build(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    token(s, "p1", "Mourner", "2/2",
          text="Whenever another creature you control dies, return it to its owner's hand at the beginning of the next end step.")
    act(s, "p1", type="set_damage", card_ids=[elves.id], value=1)
    act(s, "p1", type="pass_priority")
    pass_until_stack_empty(s)
    assert s.state.cards[elves.id].zone == "p1:graveyard"
    (t,) = rules(s).delayed
    assert t.event is not None and t.event["new_objects"][0]["zone"] == "p1:graveyard"  # 400.7e
    next_end_step(s)
    assert s.state.cards[elves.id].zone == "p1:hand"
    replay_matches(s)


# -- "when that creature dies this turn": bound to that object, once, this turn ----------------
REVIVE = ("{1}: Target creature gets +1/+1 until end of turn. When that creature dies this turn, "
          "return it to the battlefield under its owner's control.")


def kill(s, card):
    act(s, "p1", type="set_damage", card_ids=[card.id], value=9)
    act(s, rules(s).priority, type="pass_priority")  # state-based actions
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)


def test_when_that_creature_dies_this_turn_returns_it_once(cards):
    s = build(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    src = token(s, "p1", "Reviver", "2/2", text=REVIVE)
    activate(s, src, targets=[elves.id])
    (t,) = rules(s).delayed
    assert t.when == {"kind": "event", "event": "die"} and t.until_turn == s.state.turn.number
    before = rules(s).object_id(elves.id)
    kill(s, elves)
    assert s.state.cards[elves.id].zone == "p1:battlefield" and rules(s).object_id(elves.id) != before
    assert not rules(s).delayed  # 603.7b: once
    kill(s, elves)
    assert s.state.cards[elves.id].zone == "p1:graveyard"
    replay_matches(s)


def test_the_new_object_after_a_zone_change_does_not_trigger_it(cards):
    s = build(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    src = token(s, "p1", "Reviver", "2/2", text=REVIVE)
    activate(s, src, targets=[elves.id])
    act(s, "p1", type="move", card_ids=[elves.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[elves.id], to={"zone": "battlefield"})  # a new object (400.7)
    kill(s, elves)
    assert s.state.cards[elves.id].zone == "p1:graveyard" and len(rules(s).delayed) == 1
    replay_matches(s)


def test_this_turn_stops_at_cleanup(cards):
    s = build(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    src = token(s, "p1", "Reviver", "2/2", text=REVIVE)
    activate(s, src, targets=[elves.id])
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn, limit=60)
    assert not rules(s).delayed  # 514.2
    kill(s, elves)
    assert s.state.cards[elves.id].zone == "p1:graveyard"
    replay_matches(s)


def test_nothing_to_watch_when_the_creature_already_left(cards):
    # 603.7a: the creature left before the ability resolved: the delayed trigger is never created
    s = build(cards, "Llanowar Elves")
    responsive(s)
    elves = on_battlefield(s, "Llanowar Elves")
    src = token(s, "p1", "Reviver", "2/2", text=REVIVE)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0, targets=[elves.id])
    act(s, "p1", type="move", card_ids=[elves.id], to={"zone": "graveyard"})  # in response
    pass_until_stack_empty(s)
    act(s, rules(s).priority, type="pass_priority")
    pass_until_stack_empty(s)
    assert not s.state.zones.get("stack") and not rules(s).delayed
    replay_matches(s)


# -- durations (611.2) --------------------------------------------------------------------------
def test_until_your_next_turn_ends_as_that_turn_begins(cards):
    s = build(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    src = token(s, "p1", "Blesser", "2/2", text="{1}: Target creature gets +2/+2 until your next turn.")
    activate(s, src, targets=[elves.id])
    (e,) = rules(s).effects
    assert e.duration == "next_turn" and e.until_player == "p1" and ch(s, elves).pt == (3, 3)
    assert any(m.text == "until your next turn" for m in s.state.cards[elves.id].effects)
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn, limit=60)
    assert s.state.turn.active_player == "p2" and ch(s, elves).pt == (3, 3)  # past cleanup (514.2): still on
    s = reloaded(s)
    until(s, lambda s: s.state.turn.active_player == "p1" and s.state.turn.number > turn + 1, limit=80)
    assert ch(s, elves).pt == (1, 1) and not rules(s).effects  # 500.4
    assert not any(m.text == "until your next turn" for m in s.state.cards[elves.id].effects)
    replay_matches(s)


def test_cant_attack_or_block_until_your_next_turn(cards):
    s = build(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    src = token(s, "p1", "Arrester", "2/2", text="{1}: Target creature can't attack until your next turn.")
    activate(s, src, targets=[elves.id])
    assert "cant_attack" in ch(s, elves).imposed
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn, limit=60)
    assert "cant_attack" in ch(s, elves).imposed
    until(s, lambda s: s.state.turn.active_player == "p1" and s.state.turn.number > turn + 1, limit=80)
    assert "cant_attack" not in ch(s, elves).imposed
    replay_matches(s)


def test_this_turn_effect_keeps_going_when_control_changes(cards):
    # 611.2c: the set of objects is locked in; who controls the creature later doesn't matter
    s = build(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    src = token(s, "p1", "Blesser", "2/2", text="{1}: Target creature gets +2/+2 until your next turn.")
    activate(s, src, targets=[elves.id])
    act(s, "p1", type="set_controller", card_ids=[elves.id], player="p2")
    assert ch(s, elves).pt == (3, 3)
    replay_matches(s)


def test_for_as_long_as_the_source_remains_on_the_battlefield(cards):
    s = build(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    src = token(s, "p1", "Anchor", "2/2", text="{1}: Target creature gets +2/+2 for as long as ~ remains on the battlefield.")
    activate(s, src, targets=[elves.id])
    assert ch(s, elves).pt == (3, 3) and rules(s).effects[0].duration == "source_on_battlefield"
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn, limit=60)
    assert ch(s, elves).pt == (3, 3)  # (not an "until end of turn" effect)
    act(s, "p1", type="move", card_ids=[src.id], to={"zone": "exile"})
    act(s, rules(s).priority, type="pass_priority")  # the engine looks at the table again
    assert ch(s, elves).pt == (1, 1) and not rules(s).effects  # 611.2b
    replay_matches(s)


def test_for_as_long_as_does_nothing_if_the_source_already_left(cards):
    s = build(cards, "Llanowar Elves")
    responsive(s)
    elves = on_battlefield(s, "Llanowar Elves")
    src = token(s, "p1", "Anchor", "2/2", text="{1}: Target creature gets +2/+2 for as long as ~ remains on the battlefield.")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0, targets=[elves.id])
    act(s, "p1", type="move", card_ids=[src.id], to={"zone": "exile"})  # in response
    pass_until_stack_empty(s)
    act(s, rules(s).priority, type="pass_priority")
    pass_until_stack_empty(s)
    assert not s.state.zones.get("stack") and ch(s, elves).pt == (1, 1) and not rules(s).effects
    replay_matches(s)


def test_for_as_long_as_you_control_the_source(cards):
    s = build(cards, "Llanowar Elves")
    elves = on_battlefield(s, "Llanowar Elves")
    src = token(s, "p1", "Aegis", "2/2", text="{1}: Target creature gains indestructible for as long as you control ~.")
    activate(s, src, targets=[elves.id])
    assert "indestructible" in ch(s, elves).keywords
    act(s, "p1", type="set_controller", card_ids=[src.id], player="p2")
    act(s, rules(s).priority, type="pass_priority")
    assert "indestructible" not in ch(s, elves).keywords
    replay_matches(s)


# -- "exile … until ~ leaves the battlefield" (610.3) ----------------------------------------------
def test_exile_until_leaves_with_a_selector_and_a_control_change(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(10, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Grizzly Bears"), (9, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    atraxa = named(s, "Grizzly Bears")
    act(s, "p2", type="move", card_ids=[atraxa.id], to={"player": "p2", "zone": "battlefield"})
    jailer = token(s, "p1", "Jailer", "2/2",
                   text="{1}: Exile target artifact or creature an opponent controls until ~ leaves the battlefield.")
    activate(s, jailer, targets=[atraxa.id])
    assert s.state.cards[atraxa.id].zone == "p2:exile"
    act(s, "p1", type="set_controller", card_ids=[jailer.id], player="p2")  # 610.3: the link is to the object
    act(s, "p2", type="set_damage", card_ids=[jailer.id], value=2)
    act(s, rules(s).priority, type="pass_priority")  # state-based actions: the Jailer dies → the Bears come back
    assert jailer.id not in s.state.cards and s.state.cards[atraxa.id].zone == "p2:battlefield"
    replay_matches(s)
