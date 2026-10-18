"""Regressions for the independent review of the multi-target / costs / conditions batch."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import conditions, scripts
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_attachments import build, mana, named, to_hand, token
from tests.test_rules_combat import creature, table
from tests.test_rules_effects import pass_until_stack_empty
from tests.test_rules_scripts import ch


def test_multi_sentence_intervening_if_gates_the_whole_ability(cards):
    # 603.4: false as it would trigger → it doesn't trigger at all (no life from the 2nd sentence)
    s = build(cards)
    token(s, "p1", "Goblin Friend")
    act(s, "p1", type="create_token", player="p1", token={"name": "Gob", "type_line": "Token Creature — Goblin"})
    token(s, "p1", "Warden", text="Whenever another creature you control enters, if you control no Goblins, "
                                  "draw a card. You gain 5 life.")
    src = token(s, "p1", "Recruiter", text="{1}: Create a 1/1 white Soldier creature token.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 40


def test_other_in_an_event_condition_is_other_than_the_entering_permanent():
    # Roiling Canopy-style: "other" than the Forest that entered, not the source (review 52: Valakut's and Roiling Canopy's rulings, "five or more Forests other
    # than that new one"; played in test_rules_wave52b_small.py)
    text = "Whenever a Forest you control enters, if you control at least five other Forests, you gain 1 life."
    assert "other_event" in str(scripts.definitions(ch("X", "Enchantment", text)))


def test_an_opponent_controls_counts_each_opponent_separately(cards):
    s = table(cards, players=3)
    creature(s, "p2", "B1")
    creature(s, "p3", "C1")
    cond = conditions.parse("an opponent controls two or more creatures")
    plan = Plan(s.state, "p1", cards, None)
    assert not conditions.holds(plan, {"controller": "p1"}, cond)  # one each: no single opponent has two
    creature(s, "p3", "C2")
    assert conditions.holds(Plan(s.state, "p1", cards, None), {"controller": "p1"}, cond)


def test_legendary_sorcery_needs_a_legendary_creature_or_planeswalker(cards):
    s = build(cards, "Test Legendary Sorcery")
    spell = to_hand(s, "Test Legendary Sorcery")
    mana(s, R=1)
    with pytest.raises(ActionError, match="legendary creature or planeswalker"):  # 205.4e
        act(s, "p1", type="cast_spell", card_id=spell.id)
    krenko = named(s, "Krenko, Mob Boss")  # a legendary creature
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    act(s, "p1", type="cast_spell", card_id=spell.id)
    assert s.state.cards[spell.id].zone in ("stack", "p1:graveyard")  # (cast; it may have resolved already)


def test_prompts_dont_name_a_spell_still_in_hand(cards):
    s = build(cards, "Test Barrage")
    token(s, "p2", "Ogre", "3/3")
    spell = to_hand(s, "Test Barrage")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    assert s.state.cards[spell.id].zone == "p1:hand"  # (targets are chosen before it moves)
    assert "Test Barrage" in s.view("p1")["rules"]["decision"]["prompt"]
    assert "Test Barrage" not in s.view("p2")["rules"]["decision"]["prompt"]


def test_a_land_that_enters_tapped_does_so_when_an_effect_puts_it_onto_the_battlefield(cards):
    # 614.1c: "enters tapped" applies however it enters, not only from the stack / as a land play
    s = build(cards, "Barren Moor")
    moor = named(s, "Barren Moor")
    src = token(s, "p1", "Ramp", text="{1}: Search your library for a land card, put it onto the battlefield, then shuffle.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    moor_now = next(o.id for o in d.options if s.state.cards[o.id].name == "Barren Moor")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[moor_now])
    pass_until_stack_empty(s)
    moor = named(s, "Barren Moor")
    assert moor.zone == "p1:battlefield" and moor.tapped
