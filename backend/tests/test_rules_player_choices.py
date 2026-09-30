"""Choices that belong to a named player (app/rules/effects.py "player choices"):

* edicts — "each opponent / target player sacrifices a creature of their choice" (CR 701.21a: the
  sacrificing player chooses among what *they* control; 101.4: several players choose in APNAP
  order, each knowing the earlier choices (101.4b), then everything is sacrificed at once);
* "target opponent chooses a creature they control" (that player's choice, bound for "it");
* a revealed hand — "target opponent reveals their hand. You choose a nonland card from it. That
  player discards that card." (701.20a: revealed to everyone only while the effect needs it: the
  unchosen cards are hidden again once the choice is made; 701.9a: the chosen card is discarded
  by its owner);
* "choose a color / creature type / opponent" (105.1, 205.3m), and the parse of "As ~ enters,
  choose …" (614.1c, 614.12a) for the engine's entering code.

Every scenario checks the observer's decision view is public-only, the game reloads mid-decision
(``GameSession(history.rebuild())``) and replaying the recorded history reproduces the table."""

from __future__ import annotations

import json

import pytest

from app.game.rules_state import Decision
from app.game.session import GameSession
from app.rules import effects, language, selectors
from app.rules.plan import Plan
from app.rules.scripts import parse_effects
from tests.game_helpers import act, zone
from tests.test_rules_effects import build, mana, pass_until_stack_empty, replay_matches, token


def key(phrase):
    return selectors.parse(phrase).key()


# -- parsing ------------------------------------------------------------------------------
@pytest.mark.parametrize(("text", "effects_", "target"), [
    # Diabolic Edict
    ("Target player sacrifices a creature of their choice.",
     [{"do": "edict", "who": "target", "sel": key("creature"), "n": 1, "label": "creature"}], "player"),
    # Oath of Liliana's trigger body / Fleshbag Marauder ("each player")
    ("Each opponent sacrifices a creature of their choice.",
     [{"do": "edict", "who": "each_opponent", "sel": key("creature"), "n": 1, "label": "creature"}], None),
    ("Each player sacrifices two creatures of their choice.",
     [{"do": "edict", "who": "each_player", "sel": key("creatures"), "n": 2, "label": "creatures"}], None),
    # Grave Pact ("each other player": every other player is an opponent in a free-for-all)
    ("Each other player sacrifices a creature.",
     [{"do": "edict", "who": "each_opponent", "sel": key("creature"), "n": 1, "label": "creature"}], None),
    # Wing Shards / Soul Shatter-style selectors
    ("Target player sacrifices an attacking creature of their choice.",
     [{"do": "edict", "who": "target", "sel": key("attacking creature"), "n": 1, "label": "attacking creature"}], "player"),
    ("Each opponent sacrifices a creature or planeswalker of their choice.",
     [{"do": "edict", "who": "each_opponent", "sel": key("creature or planeswalker"), "n": 1, "label": "creature or planeswalker"}],
     None),
    # Goblin War Cry (first sentence)
    ("Target opponent chooses a creature they control.",
     [{"do": "player_chooses", "who": "target", "sel": key("creature"), "n": 1, "label": "creature"}], "opponent"),
    # Thoughtseize
    ("Target player reveals their hand. You choose a nonland card from it. That player discards that card.",
     [{"do": "reveal_hand", "who": "target"},
      {"do": "choose_from_hand", "who": "you", "sel": key("nonland card"), "n": 1, "label": "nonland card", "optional": False,
       "as": "e1"},
      {"do": "discard_named", "who": "ref:e1"}], "player"),
    # Tidehollow Sculler's enters trigger body
    ("Target opponent reveals their hand and you choose a nonland card from it. Exile that card.",
     [{"do": "reveal_hand", "who": "target"},
      {"do": "choose_from_hand", "who": "you", "sel": key("nonland card"), "n": 1, "label": "nonland card", "optional": False,
       "as": "e1"},
      {"do": "exile", "who": "ref:e1"}], "opponent"),
    # Castigate ("you choose … and exile that card"), Nightsnare-style "you may"
    ("Target opponent reveals their hand. You may choose a nonland card from it. Exile that card.",
     [{"do": "reveal_hand", "who": "target"},
      {"do": "choose_from_hand", "who": "you", "sel": key("nonland card"), "n": 1, "label": "nonland card", "optional": True,
       "as": "e1"},
      {"do": "exile", "who": "ref:e1"}], "opponent"),
    ("Choose a color.", [{"do": "choose_value", "who": "you", "what": "color"}], None),
    ("Choose a creature type.", [{"do": "choose_value", "who": "you", "what": "creature type"}], None),
])
def test_parse_player_choice_wordings(text, effects_, target):
    assert parse_effects(text) == (effects_, target, False)


@pytest.mark.parametrize("text", [
    "Defending player sacrifices a creature of their choice.",  # which defending player (508.5)? not read
    "Each opponent reveals their hand. You choose a card from it. That player discards that card.",  # whose hand?
    "Each opponent sacrifices a creature or Vehicle of their choice.",  # (no such selector)
    "Target opponent chooses a creature.",  # any creature, not one they control: not read
    "Target opponent sacrifices a creature they control of their choice.",
    "Choose a card name.",  # no card-name vocabulary
    "Choose a number.",
])
def test_unread_choice_wordings_stay_manual(text):
    assert parse_effects(text) is None


def test_enters_choice_is_a_replacement_definition_not_a_trigger():
    """614.1c / 603.6d: "As ~ enters, choose …" is a replacement effect, made before it enters
    (614.12a) — parsed for the engine's entering code, never as an enters trigger."""
    assert language.enters_choice("As ~ enters, choose a creature type.") == {
        "kind": "replacement", "replacement": "enters_choice",
        "effects": [{"do": "choose_value", "who": "you", "what": "creature type", "remember": True}]}
    assert language.enters_choice("As ~ enters, choose a card name.") is None
    assert parse_effects("As ~ enters, choose a color.") is None  # (not an effect sentence)


# -- helpers --------------------------------------------------------------------------------
def activate(s, card, **kw):
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=card.id, ability=0, **kw)
    pass_until_stack_empty(s)


def choose(s, option_ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=option_ids)
    pass_until_stack_empty(s)


def assert_observer_sees_only_who(s, observer, chooser_name):
    """The other player's decision view is the public fact alone (app/rules/view.py)."""
    d = s.view(observer)["rules"]["decision"]
    assert d["public"] == {"type": "PLAYER_MAKING_CHOICE", "chooser": chooser_name}
    assert d["kind"] == "waiting" and "options" not in d and d["source_id"] is None and "display" not in d


def reloaded(s):
    """The table rebuilt from its history mid-decision: the same decision is pending."""
    again = GameSession(s.history.rebuild(), cards=s.cards)
    assert again.state.rules.decision is not None
    assert again.state.rules.decision.model_dump() == s.state.rules.decision.model_dump()
    return again


# -- edicts ---------------------------------------------------------------------------------
def test_edict_the_sacrificing_opponent_chooses(cards):
    s = build(cards)
    bear = token(s, "p2", "Bear")
    wolf = token(s, "p2", "Wolf", "3/3")
    mine = token(s, "p1", "Mine")
    src = token(s, "p1", "Edict Maker", "1/1", text="{1}: Each opponent sacrifices a creature of their choice.")
    activate(s, src)
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and d.kind == "choose_cards"  # Bob decides, not Alice (701.21a)
    assert {o.id for o in d.options} == {bear.id, wolf.id} and (d.min_choices, d.max_choices) == (1, 1)
    assert_observer_sees_only_who(s, "p1", "Bob")
    again = reloaded(s)
    act(again, "p2", type="choose", decision_id=again.state.rules.decision.id, option_ids=[wolf.id])
    assert wolf.id not in again.state.cards  # (the reloaded table continues the same way)
    choose(s, [wolf.id])
    assert wolf.id not in s.state.cards and bear.id in s.state.cards and mine.id in s.state.cards
    assert s.state.rules.decision is None
    replay_matches(s)


def test_edict_apnap_order_knows_earlier_choices_and_sacrifices_together(cards):
    """101.4: Alice (active) chooses first, then Bob, who is told her choice (101.4b); nothing is
    sacrificed until everyone has chosen, then all at once."""
    s = build(cards)
    a1, a2 = token(s, "p1", "Alpha"), token(s, "p1", "Beta")
    b1, b2 = token(s, "p2", "Gamma"), token(s, "p2", "Delta")
    src = token(s, "p1", "Doom", "1/1", text="{1}: Each player sacrifices a creature of their choice.")
    activate(s, src)
    d = s.state.rules.decision
    assert d.player == "p1" and {o.id for o in d.options} == {a1.id, a2.id, src.id}
    assert_observer_sees_only_who(s, "p2", "Alice")
    choose(s, [a1.id])
    d = s.state.rules.decision
    assert d.player == "p2" and {o.id for o in d.options} == {b1.id, b2.id}
    assert "Alpha" in d.prompt  # Bob knows what Alice chose (101.4b)
    assert a1.id in s.state.cards and s.state.cards[a1.id].zone == "p1:battlefield"  # not yet sacrificed (101.4)
    assert_observer_sees_only_who(s, "p1", "Bob")
    reloaded(s)
    choose(s, [b2.id])
    assert a1.id not in s.state.cards and b2.id not in s.state.cards
    assert a2.id in s.state.cards and b1.id in s.state.cards
    events = [e for e in s.state.rules.events if e.kind == "zone_change"] if hasattr(s.state.rules.events, "__iter__") else []
    assert len({e.batch for e in events if e.from_zone and e.from_zone.endswith(":battlefield")}) <= 1  # one batch
    replay_matches(s)


def test_edict_no_choice_when_a_player_has_one_or_none(cards):
    s = build(cards)
    only = token(s, "p2", "Only")
    src = token(s, "p1", "Edict Maker", "1/1", text="{1}: Each opponent sacrifices a creature of their choice.")
    activate(s, src)
    assert s.state.rules.decision is None and only.id not in s.state.cards  # one creature: no choice to make
    activate(s, src)
    assert s.state.rules.decision is None  # none: skipped, nothing happens
    replay_matches(s)


def test_targeted_edict_binds_the_sacrificed_creature(cards):
    """"… of their choice. You gain life equal to its power": the chosen creature's last known
    information (608.2h) — bound by the edict, not by the ability's controller's choice."""
    s = build(cards)
    big = token(s, "p2", "Big", "5/5")
    token(s, "p2", "Small", "1/1")
    src = token(s, "p1", "Drainer", "1/1",
                text="{1}: Target opponent sacrifices a creature of their choice. You gain life equal to its power.")
    activate(s, src, targets=["p2"])
    d = s.state.rules.decision
    assert d.player == "p2"
    choose(s, [big.id])
    assert big.id not in s.state.cards and s.state.players["p1"].life == 45
    replay_matches(s)


# -- "target opponent chooses a creature they control" --------------------------------------
def test_target_opponent_chooses_a_creature_they_control(cards):
    s = build(cards)
    bear = token(s, "p2", "Bear")
    wolf = token(s, "p2", "Wolf")
    src = token(s, "p1", "Picker", "1/1", text="{1}: Target opponent chooses a creature they control. Destroy it.")
    activate(s, src, targets=["p2"])
    d = s.state.rules.decision
    assert d.player == "p2" and {o.id for o in d.options} == {bear.id, wolf.id}
    assert_observer_sees_only_who(s, "p1", "Bob")
    reloaded(s)
    choose(s, [bear.id])
    assert bear.id not in s.state.cards and wolf.id in s.state.cards
    replay_matches(s)


# -- a revealed hand -------------------------------------------------------------------------
def bobs_hand(s):
    return list(zone(s.state, "p2", "hand"))


def bob_holds(s, name):
    """Bob's own card (from his library) put into his hand."""
    card = next(c for c in s.state.cards.values() if c.name == name and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[card.id], to={"player": "p2", "zone": "hand"})
    return card


def test_reveal_hand_controller_chooses_and_the_owner_discards(cards):
    s = build(cards)
    act(s, "p2", type="draw", player="p2", count=2)  # two Islands (shuffle=False)
    viper = bob_holds(s, "Ambush Viper")
    hand = bobs_hand(s)
    islands = [c for c in hand if c != viper.id]
    src = token(s, "p1", "Seizer", "1/1",
                text="{1}: Target opponent reveals their hand. You choose a nonland card from it. That player discards that card.")
    activate(s, src, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and [o.id for o in d.options] == [viper.id]  # the controller chooses
    assert all(s.state.cards[c].revealed_to == ["*"] for c in hand)  # 701.20a: revealed to everyone
    alice = json.dumps(s.view("p1"))
    assert viper.id in alice and all(c in alice for c in islands)  # Alice sees the whole hand
    assert_observer_sees_only_who(s, "p2", "Alice")
    again = reloaded(s)
    act(again, "p1", type="choose", decision_id=again.state.rules.decision.id, option_ids=[viper.id])
    assert again.state.cards[viper.id].zone == "p2:graveyard"
    choose(s, [viper.id])
    assert s.state.cards[viper.id].zone == "p2:graveyard"  # discarded by its owner (701.9a)
    assert bobs_hand(s) == islands and all(s.state.cards[c].revealed_to == [] for c in islands)  # hidden again
    alice = json.dumps(s.view("p1"))
    assert not any(c in alice for c in islands)  # nothing identifying Bob's remaining cards is in Alice's view
    assert s.state.rules.decision is None
    replay_matches(s)


def test_reveal_hand_nothing_to_choose_hides_it_again(cards):
    s = build(cards)
    act(s, "p2", type="draw", player="p2", count=2)  # two Islands
    hand = bobs_hand(s)
    src = token(s, "p1", "Seizer", "1/1",
                text="{1}: Target opponent reveals their hand. You choose a nonland card from it. That player discards that card.")
    activate(s, src, targets=["p2"])
    assert s.state.rules.decision is None  # no nonland card: nothing to choose, nothing discarded
    assert bobs_hand(s) == hand and all(s.state.cards[c].revealed_to == [] for c in hand)
    assert not any(c in json.dumps(s.view("p1")) for c in hand)
    replay_matches(s)


def test_reveal_hand_may_choose_and_exile(cards):
    s = build(cards)
    act(s, "p2", type="draw", player="p2", count=2)
    viper = bob_holds(s, "Ambush Viper")
    src = token(s, "p1", "Sculler", "1/1",
                text="{1}: Target opponent reveals their hand. You may choose a nonland card from it. Exile that card.")
    activate(s, src, targets=["p2"])
    d = s.state.rules.decision
    assert d.min_choices == 0 and d.max_choices == 1
    choose(s, [])  # chose not to
    assert s.state.cards[viper.id].zone == "p2:hand" and s.state.cards[viper.id].revealed_to == []
    activate(s, src, targets=["p2"])
    choose(s, [viper.id])
    assert s.state.cards[viper.id].zone == "p2:exile"
    replay_matches(s)


# -- "choose a color" ------------------------------------------------------------------------
def test_choose_a_color_is_a_public_choice(cards):
    s = build(cards)
    src = token(s, "p1", "Prism", "1/1", text="{1}: Choose a color.")
    activate(s, src)
    d = s.state.rules.decision
    assert d.player == "p1" and [o.id for o in d.options] == ["White", "Blue", "Black", "Red", "Green"]
    assert_observer_sees_only_who(s, "p2", "Alice")
    reloaded(s)
    choose(s, ["Blue"])
    assert s.state.rules.decision is None
    assert any("chooses Blue" in json.dumps(entry.model_dump(mode="json")) for entry in s.state.log[-6:])  # announced to everyone
    replay_matches(s)


def test_choice_made_as_it_entered_is_written_on_the_object(cards):
    """The ``remember`` form (for "As ~ enters, choose …", 614.12a): the answer becomes the object's
    public ``choices`` entry, which a zone change clears (400.7)."""
    s = build(cards)
    src = token(s, "p1", "Sprawl", "1/1")
    plan = Plan(s.state, "p1", s.cards, None)
    ctx = {"controller": "p1", "source_card": src.id, "source_object": plan.oid(src), "name": "Sprawl", "targets": [],
           "stack_id": "none", "kind": "activated", "effects": [], "next": 0, "x": None, "event": None}
    assert effects.choose_value(plan, ctx, {"do": "choose_value", "who": "you", "what": "creature type", "remember": True, "as": "c0"}) is False
    d = plan.state.rules.decision
    assert d.player == "p1" and "Elf" in {o.id for o in d.options} and len(d.options) > 200  # 205.3m
    effects.resume_choose_value(plan, Decision(id=d.id, player="p1", kind="choose_one", prompt="", resume=d.resume), ["Elf"])
    assert plan.state.cards[src.id].choices == {"Chosen creature type": "Elf"}
    assert ctx["refs"]["c0"] == {"kind": "choice", "what": "creature type", "value": "Elf"}
