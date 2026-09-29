"""Generic trigger conditions (app/rules/events.py) matched against the event log (triggers.py):
CR 603.2 (trigger events), 603.2c ("one or more" triggers once per event), 603.6c/603.10a
(leaves-the-battlefield abilities look back in time), 119.9 (a life gain is one event), 508.1m /
508.3a ("whenever you attack" vs "whenever a creature attacks")."""

from __future__ import annotations

import pytest

from app.rules import events, selectors
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, mana, named, to_hand, token
from tests.test_rules_combat import attack, automate, creature, table
from tests.test_rules_effects import pass_until_stack_empty, replay_matches


def key(phrase):
    return selectors.parse(phrase).key()


# -- parsing ------------------------------------------------------------------------------
@pytest.mark.parametrize(("cond", "expected"), [
    ("you gain life", {"event": "gain_life", "subject": "player", "player": "you"}),
    ("an opponent loses life", {"event": "lose_life", "subject": "player", "player": "opponent"}),
    ("you attack", {"event": "you_attack", "subject": "player", "player": "you"}),
    ("a creature you control attacks",
     {"event": "attack", "subject": "sel", "sel": key("creature you control"), "aggregate": False}),
    ("one or more creatures you control attack",
     {"event": "attack", "subject": "sel", "sel": key("creatures you control"), "aggregate": True}),
    ("another creature you control dies",
     {"event": "die", "subject": "sel", "sel": key("another creature you control"), "aggregate": False}),
    ("~ or another Elf you control enters",
     {"event": "enter", "subject": "self_or", "sel": key("another Elf you control")}),
    ("you draw your second card each turn", {"event": "draw", "subject": "player", "player": "you", "nth": 2}),
    ("~ becomes tapped", {"event": "tapped", "subject": "self"}),
    ("~ enters or dies", {"event": "multi", "events": ["enter", "die"]}),
])
def test_parse_condition(cond, expected):
    assert events.parse_condition(cond) == expected


def test_cast_conditions_select_spells_on_the_stack():
    c = events.parse_condition("an opponent casts a noncreature spell")
    assert c["event"] == "cast" and c["player"] == "opponent"
    assert selectors.from_key(c["spell"]).not_types == ("Creature",)


@pytest.mark.parametrize("cond", [
    "you commit a crime",  # (an event we don't model)
    "a foo enters",
    "you cast your first spell each turn",
    "~ becomes the target of a spell",
])
def test_unknown_conditions_stay_manual(cond):
    assert events.parse_condition(cond) is None


# -- life gain: one trigger per event (119.9, 119.10) ------------------------------------
def test_life_gain_triggers_once_per_event(cards):
    s = build(cards)
    watcher = token(s, "p1", "Ajani's Pet", text="Whenever you gain life, put a +1/+1 counter on this creature.")
    src = token(s, "p1", "Font", text="{1}: You gain 3 life.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 43
    assert s.state.cards[watcher.id].counters == {"+1/+1": 1}  # 3 life, one event, one trigger
    replay_matches(s)


def test_opponent_life_loss_triggers_per_opponent(cards):
    s = build(cards)
    token(s, "p1", "Leech", text="Whenever an opponent loses life, you gain 1 life.")
    src = token(s, "p1", "Drain", text="{1}: Each opponent loses 2 life.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 38 and s.state.players["p1"].life == 41


# -- deaths: simultaneous events, "one or more", last known information ------------------
@pytest.mark.parametrize(("text", "gain"), [
    ("Whenever another creature you control dies, you gain 1 life.", 2),  # one trigger per creature
    ("Whenever one or more other creatures you control die, you gain 1 life.", 1),  # one per batch (603.2c)
    ("Whenever a creature an opponent controls dies, you gain 1 life.", 1),
])
def test_simultaneous_deaths(cards, text, gain):
    s = build(cards)
    token(s, "p1", "Watcher", "5/5", text=text)
    token(s, "p1", "A", "1/1")
    token(s, "p1", "B", "1/1")
    token(s, "p2", "C", "1/1")
    src = token(s, "p1", "Quake", "5/5", text="{1}: This creature deals 1 damage to each creature.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 40 + gain, text
    replay_matches(s)


def test_the_watcher_dying_with_them_still_sees_them(cards):
    # 603.10a: "whenever another creature dies" looks back in time; the Watcher dies in the
    # same event as the others and still triggers for each of them.
    s = build(cards)
    token(s, "p1", "Watcher", "1/1", text="Whenever another creature dies, you gain 1 life.")
    token(s, "p1", "A", "1/1")
    src = token(s, "p1", "Quake", "5/5", text="{1}: This creature deals 1 damage to each creature.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 41  # A died; the Watcher itself isn't "another"


# -- draws -------------------------------------------------------------------------------
def test_second_card_each_turn(cards):
    s = build(cards)
    token(s, "p1", "Scholar", text="Whenever you draw your second card each turn, you gain 2 life.")
    src = token(s, "p1", "Sage", text="{1}: Draw three cards.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    # (the first player skips their first draw (103.8a): of these three, exactly one is the second)
    assert s.state.players["p1"].life == 42
    replay_matches(s)


def test_draw_triggers_per_card(cards):
    s = build(cards)
    token(s, "p1", "Reader", text="Whenever you draw a card, you gain 1 life.")
    hand = len(zone(s.state, "p1", "hand"))
    src = token(s, "p1", "Sage", text="{1}: Draw two cards.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p1", "hand")) == hand + 2 and s.state.players["p1"].life == 42


# -- combat: "you attack" vs "a creature attacks" vs "one or more attack" -----------------
@pytest.mark.parametrize(("text", "gain"), [
    ("Whenever you attack, you gain 1 life.", 1),
    ("Whenever a creature you control attacks, you gain 1 life.", 2),
    ("Whenever one or more creatures you control attack, you gain 1 life.", 1),
    ("Whenever this creature attacks, you gain 1 life.", 0),  # (the watcher stays home)
])
def test_attack_triggers(cards, text, gain):
    s = table(cards)
    creature(s, "p1", "Watcher", "1/1", text=text)
    a = creature(s, "p1", "A")
    b = creature(s, "p1", "B")
    automate(s)
    attack(s, (a, "p2"), (b, "p2"))
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 40 + gain, text
    replay_matches(s)


# -- "it": the object the event happened to (bound when it triggers; 400.7) -----------------
def test_counter_on_the_creature_that_entered(cards):
    s = build(cards)
    watcher = token(s, "p1", "Mentor", text="Whenever another creature you control enters, put a +1/+1 counter on it.")
    src = token(s, "p1", "Muster", text="{1}: Create a 1/1 white Soldier creature token.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    newcomer = named(s, "Soldier")
    assert s.state.cards[newcomer.id].counters == {"+1/+1": 1}
    assert not s.state.cards[watcher.id].counters  # (not the source)
    replay_matches(s)


def test_it_is_gone_if_it_changed_zones(cards):
    s = build(cards, "Elvish Visionary")
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"  # (stop with the triggers on the stack)
    token(s, "p1", "Mentor", text="Whenever another creature you control enters, put a +1/+1 counter on it.")
    elf = to_hand(s, "Elvish Visionary")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=elf.id)
    for _ in range(8):  # until the Elf has resolved and the triggers wait on the stack
        if s.state.cards[elf.id].zone == "p1:battlefield" and s.state.zones.get("stack"):
            break
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.zones.get("stack")
    act(s, "p1", type="move", card_ids=[elf.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[elf.id], to={"zone": "battlefield"})  # a new object (400.7)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    assert not s.state.cards[elf.id].counters


def test_attacking_creature_gets_the_bonus(cards):
    s = table(cards)
    creature(s, "p1", "Captain", "1/1", text="Whenever a creature you control attacks, it gets +1/+0 until end of turn.")
    a = creature(s, "p1", "A")
    automate(s)
    attack(s, (a, "p2"))
    pass_until_stack_empty(s)
    from app.rules.plan import Plan

    assert Plan(s.state, "p1", cards, None).ch(s.state.cards[a.id]).pt == (3, 2)
    replay_matches(s)


# -- review regressions ---------------------------------------------------------------------
def _activate(s, card, **kw):
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=card.id, ability=0, **kw)
    pass_until_stack_empty(s)


def test_dealt_lethal_damage_still_triggers(cards):
    # 510.3a / 603.10a: the creature was dealt the damage, even though it then died
    s = build(cards)
    token(s, "p1", "Priest", "1/1", text="Whenever this creature is dealt damage, you gain 1 life.")
    src = token(s, "p1", "Quake", "5/5", text="{1}: This creature deals 1 damage to each creature.")
    _activate(s, src)
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 41
    replay_matches(s)


def test_entered_then_sacrificed_still_entered(cards):
    # 603.6a: it entered, even though it left again before the trigger was collected
    s = build(cards)
    token(s, "p1", "Watcher", "5/5", text="Whenever a creature you control enters, you gain 1 life.")
    src = token(s, "p1", "Stitcher", text="{1}: Create a 1/1 blue Homunculus creature token, then sacrifice a creature.")
    _activate(s, src)
    d = s.state.rules.decision
    hom = named(s, "Homunculus")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[hom.id])
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 41
    replay_matches(s)


def test_target_player_draws_then_discards(cards):
    # the second clause's subject is the first's (not "you")
    s = build(cards)
    act(s, "p2", type="draw", player="p2", count=1)
    src = token(s, "p1", "Looter", text="{1}: Target player draws a card, then discards a card.")
    h1, h2 = len(zone(s.state, "p1", "hand")), len(zone(s.state, "p2", "hand"))
    _activate(s, src, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p2"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p2", "hand")) == h2 and len(zone(s.state, "p1", "hand")) == h1


def test_tutor_to_top_is_not_revealed(cards):
    # 701.23e: nothing is revealed unless the text says so
    s = build(cards)
    src = token(s, "p1", "Vamp", text="{1}: Search your library for a card, then shuffle and put that card on top.")
    _activate(s, src)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    pass_until_stack_empty(s)
    top = s.state.cards[zone(s.state, "p1", "library")[0]]
    assert top.name not in str(s.view("p2")["log"])
