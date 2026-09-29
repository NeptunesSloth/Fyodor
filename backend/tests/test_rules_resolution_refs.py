"""Explicit within-resolution references: a later instruction of a resolving spell or ability
refers to what an earlier one did ("it", "its controller", "its toughness", "that player", "cards
exiled this way") through a binding the earlier primitive recorded (app/rules/context.py), never
by looking at the board later. CR 400.7 (a moved object is a new object), 400.7j (an effect finds
what it moved to a public zone), 608.2h (last known information), 108.4a (owner for a card with no
controller), 111.7 / 111.8 (a token that left is gone for good)."""

from __future__ import annotations

import json

import pytest

from app.rules import scripts
from app.rules.plan import Plan
from app.rules.scripts import parse_effects
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, mana, named, to_hand, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches


def activate(s, card, **kw):
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=card.id, ability=0, **kw)
    pass_until_stack_empty(s)


def plan_of(s):
    return Plan(s.state, "p1", s.cards, None)


# -- the grammar pass -----------------------------------------------------------------------
def test_pronouns_bind_to_the_introducing_instruction():
    effects, target, _ = parse_effects("Destroy target creature. Its controller gains life equal to its toughness.")
    assert effects == [{"do": "destroy", "who": "target", "as": "e0"},
                       {"do": "gain_life", "who": "ref:e0.controller", "n": {"toughness": "ref:e0"}}]
    assert target == "creature"
    effects, _, _ = parse_effects("Exile target creature. Return it to the battlefield under its owner's control.")
    assert effects[1] == {"do": "return_card", "who": "ref:e0", "to": "battlefield", "tapped": False, "under": "owner"}
    effects, _, _ = parse_effects("Sacrifice a creature. You gain life equal to its power.")
    assert effects[0]["as"] == "e0" and effects[1]["n"] == {"power": "ref:e0"}
    effects, _, _ = parse_effects("Exile all creatures. Return cards exiled this way to the battlefield under their owners' control.")
    assert effects[1]["who"] == "ref:e0"
    effects, _, _ = parse_effects("Destroy target creature. Its controller creates a 3/3 green Beast creature token.")
    assert effects[1]["do"] == "create_token" and effects[1]["who"] == "ref:e0.controller"


def test_that_player_is_the_target_player_where_unambiguous():
    effects, target, _ = parse_effects("Target player discards a card. That player loses 2 life.")
    assert [e["who"] for e in effects] == ["target", "target"] and target == "player"
    effects, _, _ = parse_effects("Target player sacrifices a creature. That player loses life equal to its toughness.")
    assert effects[1] == {"do": "lose_life", "who": "target", "n": {"toughness": "ref:e0"}}
    # no target player: the trigger event's player (checked against the trigger by _event_refs_ok)
    effects, _, _ = parse_effects("That player draws a card.")
    assert effects[0]["who"] == "event_player"
    # both a trigger about a player and a target player: which? (manual)
    assert parse_effects("Target player draws a card. That player loses 1 life.", event_player=True) is None


@pytest.mark.parametrize("text", [
    "Destroy target creature and target artifact. Its controller loses 2 life.",  # two candidates
    "Its controller draws a card.",  # nothing introduced it
    "Destroy target creature. Return cards exiled this way to the battlefield under their owners' control.",  # not exiled
    "Draw a card. Its controller loses 2 life.",  # a draw introduces no object
])
def test_ambiguous_or_unintroduced_references_stay_manual(text):
    assert parse_effects(text) is None


def test_lines_of_a_spell_keep_their_own_bindings():
    from tests.test_rules_scripts import ch

    spell = ch("X", "Sorcery", "Destroy target creature. Its controller loses 2 life.\n"
                               "Exile target artifact. Its controller loses 1 life.")
    effects = scripts.spell_definition(spell)["effects"]
    assert [e.get("as") for e in effects] == ["l0_e0", None, "l1_e0", None]
    assert [e["who"] for e in effects] == ["target:0", "ref:l0_e0.controller", "target:1", "ref:l1_e0.controller"]


# -- resolution -----------------------------------------------------------------------------
def test_destroyed_creature_lki_toughness_and_controller(cards):
    s = build(cards)
    ogre = token(s, "p2", "Ogre", "2/2")
    act(s, "p2", type="counter", card_ids=[ogre.id], kind="+1/+1", delta=3)
    src = token(s, "p1", "Slayer", text="{1}: Destroy target creature. Its controller gains life equal to its toughness.")
    activate(s, src, targets=[ogre.id])
    assert ogre.id not in s.state.cards  # (a token: it ceased to exist)
    assert s.state.players["p2"].life == 45  # its toughness as it last existed: 5, not the printed 2 (608.2h)
    assert s.state.players["p1"].life == 40
    replay_matches(s)


def test_indestructible_target_is_still_its_controller(cards):
    s = build(cards)
    wall = token(s, "p2", "Wall", "0/4", text="Indestructible")
    src = token(s, "p1", "Slayer", text="{1}: Destroy target creature. Its controller gains life equal to its toughness.")
    activate(s, src, targets=[wall.id])
    assert wall.id in s.state.cards and s.state.players["p2"].life == 44  # not destroyed; "its controller" still gains
    replay_matches(s)


def test_flicker_returns_a_new_object(cards):
    s = build(cards, "Elvish Visionary")
    elf = to_hand(s, "Elvish Visionary")
    act(s, "p1", type="move", card_ids=[elf.id], to={"zone": "battlefield"})
    taunt = token(s, "p1", "Taunter", text="{1}: Target creature can't block this turn.")
    activate(s, taunt, targets=[elf.id])
    old_oid = s.state.rules.object_id(elf.id)
    assert "cant_block" in plan_of(s).ch(s.state.cards[elf.id]).imposed
    hand = len(zone(s.state, "p1", "hand"))
    flicker = token(s, "p1", "Blinker", text="{1}: Exile target creature. Return it to the battlefield under its owner's control.")
    activate(s, flicker, targets=[elf.id])
    pass_until_stack_empty(s)  # (its enters trigger: draw a card)
    card = s.state.cards[elf.id]
    assert card.zone == "p1:battlefield" and card.controller == "p1"
    assert s.state.rules.object_id(elf.id) != old_oid  # a new object (400.7): found in exile by "it" (400.7j)
    assert "cant_block" not in plan_of(s).ch(card).imposed  # the old object's restriction doesn't apply to it
    assert len(zone(s.state, "p1", "hand")) == hand + 1  # it entered again: its enters trigger fired
    replay_matches(s)


def test_flickered_token_ceases_to_exist_and_cant_return(cards):
    s = build(cards)
    bear = token(s, "p2", "Bear")
    flicker = token(s, "p1", "Blinker", text="{1}: Exile target creature. Return it to the battlefield under its owner's control.")
    activate(s, flicker, targets=[bear.id])
    assert bear.id not in s.state.cards  # 111.7 / 111.8: gone, and it can't come back
    assert not [c for c in s.state.cards.values() if c.name == "Bear"]
    replay_matches(s)


def test_destroyed_creatures_controller_gets_the_token(cards):
    s = build(cards)
    ogre = token(s, "p2", "Ogre")
    src = token(s, "p1", "Beastcaller", text="{1}: Destroy target creature. Its controller creates a 3/3 green Beast creature token.")
    activate(s, src, targets=[ogre.id])
    beast = named(s, "Beast")
    assert beast.controller == "p2" and beast.owner == "p2"  # the destroyed creature's controller (LKI, 608.2h)
    replay_matches(s)


def test_sacrifice_choice_then_its_power_across_a_pause(cards):
    s = build(cards)
    big = token(s, "p1", "Big", "4/4")
    src = token(s, "p1", "Altar", "1/1", text="{1}: Sacrifice a creature. You gain life equal to its power.")
    activate(s, src)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and {o.id for o in d.options} == {big.id, src.id}
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")  # (saved while paused)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[big.id])
    pass_until_stack_empty(s)
    assert big.id not in s.state.cards and s.state.players["p1"].life == 44
    replay_matches(s)


def test_cards_exiled_this_way_return_and_a_token_does_not(cards):
    s = build(cards, "Elvish Visionary")
    elf = to_hand(s, "Elvish Visionary")
    act(s, "p1", type="move", card_ids=[elf.id], to={"zone": "battlefield"})
    bear = token(s, "p2", "Bear")
    act(s, "p1", type="create_token", player="p1", token={
        "name": "Mass Blink", "type_line": "Token Artifact",
        "text": "{1}: Exile all creatures. Return cards exiled this way to the battlefield under their owners' control."})
    src = named(s, "Mass Blink")
    old = s.state.rules.object_id(elf.id)
    activate(s, src)
    pass_until_stack_empty(s)
    assert s.state.cards[elf.id].zone == "p1:battlefield" and s.state.rules.object_id(elf.id) != old
    assert bear.id not in s.state.cards  # 111.8: the token can't move again
    replay_matches(s)


def test_that_player_after_target_player_discards(cards):
    s = build(cards)
    act(s, "p2", type="draw", player="p2", count=2)
    src = token(s, "p1", "Tormentor", text="{1}: Target player discards a card. That player loses 2 life.")
    activate(s, src, targets=["p2"])
    d = s.state.rules.decision
    assert d.player == "p2"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p2", "graveyard")) == 1 and s.state.players["p2"].life == 38
    replay_matches(s)


def test_bindings_never_reach_the_other_players_view(cards):
    s = build(cards)
    act(s, "p2", type="draw", player="p2", count=2)
    bear = token(s, "p2", "Bear")
    src = token(s, "p1", "Repulser", text="{1}: Return target creature to its owner's hand. Its controller discards a card.")
    activate(s, src, targets=[bear.id])
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and bear.id not in s.state.cards  # (a token bounced: gone)
    # the paused resolution (with its bindings) is server-only: not in anyone's view, and the
    # chooser's hidden options are only theirs
    assert d.resume["ctx"]["refs"]["e0"]["objects"][0]["card"] == bear.id  # (the binding exists, server-side)
    for viewer in ("p1", "p2"):
        text = json.dumps(s.view(viewer))
        assert '"e0"' not in text and '"resume"' not in text and '"refs"' not in text
    assert s.view("p1")["rules"]["decision"].get("options") is None
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p2", "graveyard")) == 1
    replay_matches(s)


def test_its_controller_of_a_bounced_card_is_its_last_controller(cards):
    # 608.2h: the card is in a hidden zone now; "its controller" is who controlled it on the
    # battlefield (a card in a hand has no controller: 108.4a would say its owner, but the
    # effect reads the object as it was)
    s = build(cards, "Elvish Visionary")
    elf = to_hand(s, "Elvish Visionary")
    act(s, "p1", type="move", card_ids=[elf.id], to={"zone": "battlefield"})
    src = token(s, "p1", "Repulser", text="{1}: Return target creature to its owner's hand. Its controller loses 2 life.")
    activate(s, src, targets=[elf.id])
    assert s.state.cards[elf.id].zone == "p1:hand" and s.state.players["p1"].life == 38
    replay_matches(s)


def test_its_power_of_the_source_and_of_the_object_named():
    # "~ deals damage equal to its power": its own; after a sacrifice, "that creature's power" is
    # the sacrificed creature's, as it last existed (608.2h)
    effects, _, _ = parse_effects("Tap target creature. ~ deals damage equal to its power to that creature.")
    assert effects[1] == {"do": "damage", "who": "target", "n": {"power": "self"}}
    effects, _, _ = parse_effects("It deals damage equal to its power to any target.", it="self_gone")
    assert effects == [{"do": "damage", "who": "target", "n": {"power": "self"}}]
    effects, _, _ = parse_effects("Sacrifice a creature. ~ deals damage equal to that creature's power to each player.")
    assert effects[1] == {"do": "damage", "who": "each_player", "n": {"power": "ref:e0"}}


def test_card_exiled_from_a_graveyard_keeps_its_printed_toughness_and_owner(cards):
    # a graveyard card has no last known information (it wasn't a permanent): the physical card
    # tells its printed characteristics and its owner (108.4a: a card there has no controller)
    s = build(cards, "Elvish Visionary")
    elf = to_hand(s, "Elvish Visionary")
    act(s, "p1", type="move", card_ids=[elf.id], to={"zone": "graveyard"})
    src = token(s, "p1", "Maggot", text="{1}: Exile target creature card from a graveyard. Its owner gains life equal to that card's toughness.")
    activate(s, src, targets=[elf.id])
    assert s.state.cards[elf.id].zone == "p1:exile" and s.state.players["p1"].life == 41  # Elvish Visionary is a 1/1
    replay_matches(s)
