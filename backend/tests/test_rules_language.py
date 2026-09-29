"""The generic effect grammar (app/rules/language.py) on the selector (selectors.py) and value
(values.py) models: parsing, and the final game state when abilities using it resolve."""

from __future__ import annotations

import pytest

from app.rules import selectors
from app.rules.language import parse_sentence
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, mana, named, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches


def key(phrase):
    return selectors.parse(phrase).key()


# -- parsing ------------------------------------------------------------------------------
@pytest.mark.parametrize(("text", "effects", "target"), [
    ("draw two cards", [{"do": "draw", "who": "you", "n": 2}], None),
    ("target player draws x cards", [{"do": "draw", "who": "target", "n": {"x": 1}}], "player"),
    ("each opponent loses 2 life", [{"do": "lose_life", "who": "each_opponent", "n": 2}], None),
    ("each opponent discards a card", [{"do": "discard", "who": "each_opponent", "n": 1}], None),
    ("target opponent mills three cards", [{"do": "mill", "who": "target", "n": 3}], "opponent"),
    ("remove a time counter from ~", [{"do": "remove_counters", "who": "self", "kind": "time", "n": 1}], None),
])
def test_parse_simple(text, effects, target):
    assert parse_sentence(text) == (effects, target)


def test_parse_selectors_and_values():
    effects, target = parse_sentence("you gain 1 life for each creature you control")
    assert effects == [{"do": "gain_life", "who": "you", "n": {"count": key("creature you control")}}] and target is None
    effects, target = parse_sentence("~ deals x damage to target creature, where x is the number of goblins you control")
    assert effects[0]["n"] == {"count": key("goblins you control")} and target == key("creature")
    effects, _ = parse_sentence("~ deals 2 damage to each creature and each player")
    assert [e["who"] for e in effects] == [key("creature"), "each_player"]
    effects, _ = parse_sentence("each opponent sacrifices a creature")
    assert effects == [{"do": "sacrifice_choice", "who": "each_opponent", "sel": key("creature"), "n": 1}]
    effects, target = parse_sentence("return target creature card from your graveyard to the battlefield")
    assert effects[0]["do"] == "return_card" and target == key("creature card from your graveyard")
    effects, _ = parse_sentence("creatures you control get +1/+1 until end of turn")
    assert effects == [{"do": "pump", "who": key("creature you control"), "p": 1, "t": 1}]


@pytest.mark.parametrize("text", [
    "its controller draws a card",  # (a subject we don't model yet)
    "draw a card for each foo you control",
    "destroy target creature and target artifact",
    "return ~ to your hand",
])
def test_unknown_wordings_stay_manual(text):
    assert parse_sentence(text) is None


# -- resolution -----------------------------------------------------------------------------
def activate(s, card, **kw):
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=card.id, ability=0, **kw)
    pass_until_stack_empty(s)


def test_gain_life_for_each(cards):
    s = build(cards)
    for i in range(3):
        token(s, "p1", f"Elf{i}")
    src = token(s, "p1", "Healer", text="{1}: You gain 1 life for each creature you control.")
    activate(s, src)
    assert s.state.players["p1"].life == 44  # three Elves and the Healer
    replay_matches(s)


def test_damage_each_creature_and_each_player(cards):
    s = build(cards)
    mine = token(s, "p1", "Mine", "3/3")
    theirs = token(s, "p2", "Theirs", "1/1")
    src = token(s, "p1", "Quake", "5/5", text="{1}: This creature deals 1 damage to each creature and each player.")
    activate(s, src)
    assert s.state.players["p1"].life == 39 and s.state.players["p2"].life == 39
    assert s.state.cards[mine.id].damage == 1 and theirs.id not in s.state.cards  # the 1/1 token died
    replay_matches(s)


def test_each_opponent_sacrifices_their_choice(cards):
    s = build(cards)
    a = token(s, "p2", "A")
    b = token(s, "p2", "B")
    src = token(s, "p1", "Edict", text="{1}: Each opponent sacrifices a creature.")
    activate(s, src)
    d = s.state.rules.decision
    assert d.player == "p2" and {o.id for o in d.options} == {a.id, b.id}
    assert s.view("p1")["rules"]["decision"].get("options") is None  # only Bob sees his choices
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[a.id])
    pass_until_stack_empty(s)
    assert a.id not in s.state.cards and b.id in s.state.cards


def test_counters_on_each_and_removal(cards):
    s = build(cards)
    x = token(s, "p1", "X")
    y = token(s, "p1", "Y")
    enemy = token(s, "p2", "Enemy")
    src = token(s, "p1", "Captain", text="{1}: Put a +1/+1 counter on each other creature you control.")
    activate(s, src)
    assert s.state.cards[x.id].counters == {"+1/+1": 1} and s.state.cards[y.id].counters == {"+1/+1": 1}
    assert not s.state.cards[src.id].counters and not s.state.cards[enemy.id].counters  # "other", "you control"
    replay_matches(s)


def test_return_creature_card_from_graveyard_to_battlefield(cards):
    s = build(cards)
    dead = named(s, "Forest")  # (a card in the graveyard that isn't a creature can't be chosen)
    act(s, "p1", type="move", card_ids=[dead.id], to={"zone": "graveyard"})
    src = token(s, "p1", "Necro", text="{1}: Return target creature card from your graveyard to the battlefield.")
    mana(s, C=1)
    with pytest.raises(Exception, match="legal target"):
        act(s, "p1", type="activate_ability", card_id=src.id, ability=0, targets=[dead.id])


def test_team_pump_is_locked_in(cards):
    s = build(cards)
    a = token(s, "p1", "A")
    src = token(s, "p1", "Banner", text="{1}: Creatures you control get +1/+1 until end of turn.")
    activate(s, src)
    late = token(s, "p1", "Late")
    from app.rules.plan import Plan

    plan = Plan(s.state, "p1", cards, None)
    assert plan.ch(s.state.cards[a.id]).pt == (3, 3) and plan.ch(s.state.cards[late.id]).pt == (2, 2)  # 611.2c


def test_each_opponent_discards_privately(cards):
    s = build(cards)
    act(s, "p2", type="draw", player="p2", count=3)
    src = token(s, "p1", "Mind Rot", text="{1}: Each opponent discards two cards.")
    activate(s, src)
    d = s.state.rules.decision
    assert d.player == "p2" and d.min_choices == 2
    assert s.view("p1")["rules"]["decision"].get("options") is None
    hand = zone(s.state, "p2", "hand")
    act(s, "p2", type="choose", decision_id=d.id, option_ids=hand[:2])
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p2", "hand")) == 1 and len(zone(s.state, "p2", "graveyard")) == 2


def test_cant_block_this_turn_ends_at_cleanup(cards):
    s = build(cards)
    wall = token(s, "p2", "Wall", "0/4")
    src = token(s, "p1", "Taunter", text="{1}: Target creature can't block this turn.")
    activate(s, src, targets=[wall.id])
    from app.rules.plan import Plan

    assert "cant_block" in Plan(s.state, "p1", cards, None).ch(s.state.cards[wall.id]).imposed
    act(s, "p1", type="pass_priority", until="next_turn")
    for _ in range(10):
        if s.state.turn.active_player == "p2":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert "cant_block" not in Plan(s.state, "p1", cards, None).ch(s.state.cards[wall.id]).imposed  # 514.2


def test_compound_draw_and_lose_life(cards):
    s = build(cards)
    hand = len(zone(s.state, "p1", "hand"))
    src = token(s, "p1", "Sage", text="{1}: You draw two cards and you lose 2 life.")
    activate(s, src)
    assert len(zone(s.state, "p1", "hand")) == hand + 2 and s.state.players["p1"].life == 38
    replay_matches(s)


def test_enchanted_creature_reference(cards):
    s = build(cards, "Holy Strength")
    bear = token(s, "p1", "Bear")
    act(s, "p1", type="create_token", player="p1", token={
        "name": "Chains", "type_line": "Token Enchantment — Aura", "text": "Enchant creature\n{1}: Tap enchanted creature."})
    chains = named(s, "Chains")
    act(s, "p1", type="attach", card_ids=[chains.id], to=bear.id)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=chains.id, ability=1)
    pass_until_stack_empty(s)
    assert s.state.cards[bear.id].tapped


def test_search_basic_land_to_hand_is_private(cards):
    s = build(cards)
    src = token(s, "p1", "Seeker", text="{1}: Search your library for a basic land card, reveal it, put it into your hand, then shuffle.")
    activate(s, src)
    d = s.state.rules.decision
    assert d.player == "p1" and d.max_choices == 1 and d.options
    assert all(s.state.cards[o.id].name == "Forest" for o in d.options)
    assert s.view("p2")["rules"]["decision"].get("options") is None  # nobody else learns the library
    hand = len(zone(s.state, "p1", "hand"))
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p1", "hand")) == hand + 1
    replay_matches(s)


def test_search_up_to_two_onto_the_battlefield_tapped(cards):
    s = build(cards)
    src = token(s, "p1", "Ramp", text="{1}: Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.")
    activate(s, src)
    d = s.state.rules.decision
    assert (d.min_choices, d.max_choices) == (0, 2)
    picked = [o.id for o in d.options[:2]]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=picked)
    pass_until_stack_empty(s)
    assert all(s.state.cards[c].zone == "p1:battlefield" and s.state.cards[c].tapped for c in picked)


def test_search_then_put_on_top(cards):
    s = build(cards)
    src = token(s, "p1", "Tutor", text="{1}: Search your library for a card, reveal it, then shuffle and put that card on top.")
    size = len(zone(s.state, "p1", "library"))
    activate(s, src)
    d = s.state.rules.decision
    pick = d.options[-1].id
    name = s.state.cards[pick].name
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[pick])
    pass_until_stack_empty(s)
    top = zone(s.state, "p1", "library")[0]  # (a shuffle gives library cards new ids)
    assert s.state.cards[top].name == name and len(zone(s.state, "p1", "library")) == size
    replay_matches(s)


def test_look_at_top_put_one_rest_to_graveyard(cards):
    s = build(cards)
    src = token(s, "p1", "Oracle", text="{1}: Look at the top three cards of your library. Put one of them into your hand and the rest into your graveyard.")
    top3 = zone(s.state, "p1", "library")[:3]
    activate(s, src)
    d = s.state.rules.decision
    assert {o.id for o in d.options} == set(top3) and (d.min_choices, d.max_choices) == (1, 1)
    assert s.view("p2")["rules"]["decision"].get("options") is None  # only the looking player sees them
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[top3[1]])
    pass_until_stack_empty(s)
    assert s.state.cards[top3[1]].zone == "p1:hand"
    assert all(s.state.cards[c].zone == "p1:graveyard" for c in (top3[0], top3[2]))
    replay_matches(s)


def test_look_at_top_may_reveal_matching_rest_random_bottom(cards):
    s = build(cards)
    src = token(s, "p1", "Scout", text="{1}: Look at the top four cards of your library. You may reveal a creature card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.")
    top4 = zone(s.state, "p1", "library")[:4]
    activate(s, src)
    assert s.state.rules.decision is None  # (no creature card among them: nothing to choose)
    library = zone(s.state, "p1", "library")
    assert set(library[-4:]) == set(top4)  # all four went to the bottom
    replay_matches(s)
