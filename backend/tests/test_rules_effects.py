"""M16: triggered abilities, targets, effect primitives, continuous effects and layers, with real
Oracle cards (tests/fixtures) and test tokens. Every scenario also checks that replaying the
recorded history reproduces the table exactly."""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable, zone


def build(cards, *, level="full"):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Elvish Visionary"), (1, "Thornwood Falls"), (1, "Murder"), (1, "Giant Growth"),
                                             (1, "Opt"), (1, "Perilous Myr"), (1, "Ambush Viper"), (8, "Forest"), (5, "Island")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island"), (1, "Ambush Viper")])
    state = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)
    s = GameSession(enable(state, level), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    return s


def rules(s):
    return s.state.rules


def hand(s, pid, name):
    return next(s.state.cards[c] for c in zone(s.state, pid, "hand") if s.state.cards[c].name == name)


def draw_all(s, pid="p1"):
    act(s, pid, type="draw", count=len(zone(s.state, pid, "library")) - 2)


def mana(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def token(s, pid, name, pt="2/2", text=""):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Creature — Test", "power": p,
                                                        "toughness": t, "text": text})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def replay_matches(s):
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def pass_until_stack_empty(s):
    for _ in range(10):
        if not s.state.zones.get("stack") or rules(s).decision is not None:
            return
        act(s, rules(s).priority, type="pass_priority")


def test_enters_trigger_goes_on_the_stack_and_resolves(cards):
    s = build(cards)
    draw_all(s)
    mana(s, G=2)
    visionary = hand(s, "p1", "Elvish Visionary")
    before = len(zone(s.state, "p1", "hand"))
    act(s, "p1", type="cast_spell", card_id=visionary.id)
    # Bob has nothing: the creature resolves, its trigger goes on the stack, resolves, Alice draws.
    assert s.state.cards[visionary.id].zone == "p1:battlefield"
    assert len(zone(s.state, "p1", "hand")) == before - 1 + 1
    log = json.dumps(s.view("p2")["log"])
    assert "put an ability on the stack" in log and "(Elvish Visionary)" in log
    assert rules(s).stack == {} and rules(s).priority == "p1"
    replay_matches(s)


def test_enters_tapped_and_lifegain_trigger(cards):
    s = build(cards)
    draw_all(s)
    falls = hand(s, "p1", "Thornwood Falls")
    act(s, "p1", type="play_land", card_id=falls.id)
    assert s.state.cards[falls.id].tapped  # a replacement effect: it never entered untapped
    assert s.state.players["p1"].life == 41
    replay_matches(s)


def test_destroy_with_a_chosen_target_and_hexproof(cards):
    s = build(cards)
    draw_all(s)
    ox = token(s, "p2", "Ox", "2/4")
    ward = token(s, "p2", "Warded", "1/1", "Hexproof")
    mine = token(s, "p1", "Mine", "1/1", "Hexproof")
    shrouded = token(s, "p1", "Shrouded", "1/1", "Shroud")
    mana(s, B=3)
    murder = hand(s, "p1", "Murder")
    with pytest.raises(ActionError, match="legal target"):
        act(s, "p1", type="cast_spell", card_id=murder.id, targets=[ward.id])  # hexproof: not by an opponent
    act(s, "p1", type="cast_spell", card_id=murder.id)
    d = rules(s).decision
    options = {o.id for o in d.options}
    assert d.player == "p1" and ox.id in options and mine.id in options and ward.id not in options
    assert shrouded.id not in options  # shroud: not even by its controller
    assert "options" not in s.view("p2")["rules"]["decision"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[ox.id])
    assert ox.id not in s.state.cards and s.state.cards[murder.id].zone == "p1:graveyard"  # (a token: it ceased)
    replay_matches(s)


def test_a_target_that_changed_zones_is_illegal_on_resolution(cards):
    s = build(cards)
    draw_all(s)
    act(s, "p1", type="set_prefs", hold_priority=True)
    ox = token(s, "p2", "Ox", "2/4")
    mana(s, B=3)
    murder = hand(s, "p1", "Murder")
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[ox.id])
    act(s, "p2", type="move", card_ids=[ox.id], to={"zone": "exile"})  # flickered away by hand…
    viper = hand(s, "p1", "Ambush Viper")
    act(s, "p1", type="move", card_ids=[viper.id], to={"zone": "battlefield"})
    act(s, "p1", type="pass_priority")
    pass_until_stack_empty(s)
    assert "does nothing: its target is no longer legal" in json.dumps(s.view("p1")["log"])
    assert s.state.cards[murder.id].zone == "p1:graveyard"


def test_giant_growth_uses_layers_and_ends_at_cleanup(cards):
    s = build(cards)
    act(s, "p1", type="draw", count=4)  # (a small hand: no discarding at cleanup)
    bear = token(s, "p1", "Bear", "2/2")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=hand(s, "p1", "Giant Growth").id, targets=[bear.id])
    from app.rules.plan import Plan

    plan = Plan(s.state, "p1", cards, None)
    assert plan.ch(s.state.cards[bear.id]).pt == (6, 6)  # printed 2/2, counter (7c) and +3/+3 (7c)
    assert any(e.name == "+3/+3" for e in s.state.cards[bear.id].effects)  # the visible marker
    act(s, "p1", type="pass_priority")  # main 2
    act(s, "p1", type="pass_priority")  # → Bob's turn: cleanup ended the effect
    plan = Plan(s.state, "p1", cards, None)
    assert plan.ch(s.state.cards[bear.id]).pt == (3, 3) and rules(s).effects == []
    assert not any(e.name == "+3/+3" for e in s.state.cards[bear.id].effects)
    replay_matches(s)


def test_opt_scry_is_a_private_choice_then_draw(cards):
    s = build(cards)
    act(s, "p1", type="draw", count=10)
    opt = hand(s, "p1", "Opt")
    mana(s, U=1)
    top = zone(s.state, "p1", "library")[0]
    act(s, "p1", type="cast_spell", card_id=opt.id)
    d = rules(s).decision
    assert d.kind == "choose_cards" and [o.id for o in d.options] == [top] and d.player == "p1"
    bob_view = json.dumps(s.view("p2"))
    assert top not in bob_view  # the looked-at card stays private
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[top])  # to the bottom
    assert zone(s.state, "p1", "library")[-1] == top and s.state.cards[opt.id].zone == "p1:graveyard"
    replay_matches(s)


def test_dies_trigger_uses_last_known_information(cards):
    s = build(cards)
    myr = token(s, "p1", "Myr Token", "1/1", "When this creature dies, it deals 2 damage to any target.")
    act(s, "p1", type="set_damage", card_ids=[myr.id], delta=1)
    act(s, "p1", type="pass_priority")  # SBA: it dies (and, a token, ceases to exist) — the trigger still happens
    d = rules(s).decision
    assert d.kind == "choose_one" and "choose a target" in d.prompt and "p2" in {o.id for o in d.options}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 38
    dmg = [e for e in rules(s).events if e.kind == "damage"]
    assert dmg and not dmg[0].combat
    replay_matches(s)


def test_may_trigger_asks_and_can_be_remembered(cards):
    s = build(cards)
    a = token(s, "p1", "Scholar", "1/1", "When this creature dies, you may draw a card.")
    act(s, "p1", type="set_damage", card_ids=[a.id], delta=1)
    act(s, "p1", type="pass_priority")
    pass_until_stack_empty(s)
    d = rules(s).decision
    assert d.kind == "confirm" and "Draw 1 card(s)?" in d.prompt and s.view("p1")["rules"]["decision"]["rememberable"]
    before = len(zone(s.state, "p1", "hand"))
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"], remember="yes_this_turn")
    assert len(zone(s.state, "p1", "hand")) == before + 1
    b = token(s, "p1", "Scholar", "1/1", "When this creature dies, you may draw a card.")
    act(s, "p1", type="set_damage", card_ids=[b.id], delta=1)
    act(s, rules(s).priority, type="pass_priority")
    pass_until_stack_empty(s)
    d = rules(s).decision  # another card (of the same name): its own ability, its own answer
    assert d is not None and d.kind == "confirm"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    assert len(zone(s.state, "p1", "hand")) == before + 2


def test_apnap_order_and_ordering_your_own_triggers(cards):
    s = build(cards)
    mine1 = token(s, "p1", "Alpha", "1/1", "When this creature dies, you gain 1 life.")
    mine2 = token(s, "p1", "Beta", "1/1", "When this creature dies, you gain 2 life.")
    theirs = token(s, "p2", "Gamma", "1/1", "When this creature dies, you gain 5 life.")
    for c in (mine1, mine2, theirs):
        act(s, c.owner, type="set_damage", card_ids=[c.id], delta=1)
    act(s, "p2", type="set_prefs", response="on")  # (so the stack can be looked at before it resolves)
    act(s, "p1", type="pass_priority")  # all three die simultaneously
    d = rules(s).decision
    assert d.kind == "order" and d.player == "p1" and {o.label for o in d.options} == {"Alpha", "Beta"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in sorted(d.options, key=lambda o: o.label)])
    stack = [rules(s).stack[c].name for c in s.state.zones["stack"]]
    assert stack == ["Alpha", "Beta", "Gamma"]  # active player's first (bottom), Bob's on top: Bob's resolves first
    pass_until_stack_empty(s)
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (43, 45)
    replay_matches(s)


def run_until(s, done):
    """Pass priority / skip combat until ``done(s)``."""
    for _ in range(60):
        if done(s):
            return
        d = rules(s).decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, rules(s).priority, type="pass_priority")
    raise AssertionError("never got there")


def test_upkeep_and_attack_triggers(cards):
    s = build(cards)
    token(s, "p1", "Healer", "1/1", "At the beginning of your upkeep, you gain 1 life.")
    raider = token(s, "p1", "Raider", "2/2", "Whenever this creature attacks, it gets +1/+1 until end of turn.")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert s.state.players["p1"].life == 41  # Alice's upkeep trigger (turn 3) resolved; not on Bob's turn
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": raider.id, "target": "p2"}])
    pass_until_stack_empty(s)
    from app.rules.plan import Plan

    assert Plan(s.state, "p1", cards, None).ch(s.state.cards[raider.id]).pt == (3, 3)
    replay_matches(s)


def test_activated_pump_ability(cards):
    s = build(cards)
    fire = token(s, "p1", "Firebreather", "1/1", "{R}: This creature gets +1/+0 until end of turn.")
    mana(s, R=2)
    for _ in range(2):
        act(s, "p1", type="activate_ability", card_id=fire.id, ability=0)
        pass_until_stack_empty(s)
    from app.rules.plan import Plan

    assert Plan(s.state, "p1", cards, None).ch(s.state.cards[fire.id]).pt == (3, 1)
    assert s.state.players["p1"].mana == {}
    replay_matches(s)


def test_flash_creature_at_instant_speed(cards):
    s = build(cards)
    act(s, "p2", type="draw", count=11)
    viper = hand(s, "p2", "Ambush Viper")
    act(s, "p2", type="set_prefs", response="on")
    act(s, "p1", type="pass_priority")  # Bob gets priority in Alice's main phase
    assert rules(s).priority == "p2"
    act(s, "p2", type="add_mana", player="p2", mana={"G": 2})
    act(s, "p2", type="cast_spell", card_id=viper.id)
    pass_until_stack_empty(s)
    assert s.state.cards[viper.id].zone == "p2:battlefield"


def test_assisted_confirms_triggers(cards):
    s = build(cards, level="assisted")
    a = token(s, "p1", "Alpha", "1/1", "When this creature dies, you gain 1 life.")
    act(s, "p1", type="set_damage", card_ids=[a.id], delta=1)
    act(s, "p1", type="pass_priority")
    d = rules(s).decision
    if d is not None and d.kind == "confirm" and d.prompt.startswith("State-based"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
        d = rules(s).decision
    assert d.kind == "confirm" and d.prompt == "Triggered: Alpha"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["no"])
    assert rules(s).pending_triggers == [] and s.state.players["p1"].life == 40  # handled by hand
