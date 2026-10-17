"""Wave 43B (spells and statics): the most-played spells and permanents one line short of FULL (CR 2026-09-25), real Oracle text (tests/fixtures/wave43b_cards.json).
Every scenario checks the replay and a save and a load.

* 101.2, 701.6, 603.7, 106.6: "{U}, {T}: The next spell you cast this turn can't be countered." (Mistrise Village [377]) - the next spell cast from now on, not the one before it, not
  the second; "The next instant or sorcery spell you cast this turn can't be countered. Draw a card." (Overmaster); "+1: Add {R} or {G}. Creature spells you cast this turn can't be
  countered." (Domri, Anarch of Bolas [2732]) - every creature spell of its controller for the rest of the turn, those already on the stack too.
* 701.20e, 406.3, 401.4: "Look at the top three cards of your library. Put one of them into your hand, put one of them on the bottom of your library, and exile one of them. You may
  play the exiled card this turn." (Expressive Iteration [877]) - a private look, the exiled card public.
* 101.2, 121.2: "Each opponent can't draw more than one card each turn." (Narset, Parter of Veils [976]): the limit counts what was drawn before Narset came; its controller is not limited.
* 903.4, 702.16, the rulings 2020-11-10: "Equipped creature gets +3/+3 and has protection from each color that's not in your commander's color identity." (Commander's Plate [475]).
* 702.142: "Creatures you control can boast twice during each of your turns rather than once." (Birgi, God of Storytelling [498]) - the line is read; the second boast is the
  restrictions' (wave 4H, tests/test_rules_wave4h_activation_costs.py).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, ask, settle, stops
from tests.test_rules_wave43b_mana import to_bobs_main
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand, zone_of
from tests.wave43b_kit import library, names_in, on_top, open_cards, stack_size, tapped


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


def counter_it(s, victim, pid="p2"):
    """Bob (holding priority after Alice cast ``victim``) casts Counterspell on it; everything resolves."""
    mana(s, pid, U=2)
    counterspell = next(c for c in s.state.cards.values() if c.name == "Counterspell" and c.zone == f"{pid}:hand")
    act(s, pid, type="cast_spell", card_id=counterspell.id, targets=[victim.id])
    settle(s)


# ---- Mistrise Village [377] ------------------------------------------------------------------------------------------------------------------------------
def village_table(cards):
    s = build(cards, ["Mistrise Village", "Grizzly Bears", "Lightning Bolt"], ["Counterspell", "Counterspell"])
    stops(s)
    village = put(s, "Mistrise Village")
    to_hand(s, "Grizzly Bears")
    to_hand(s, "Lightning Bolt")
    for c in [c for c in s.state.cards.values() if c.name == "Counterspell" and c.owner == "p2"]:
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "hand"})
    return s, village


def test_mistrise_village_makes_the_next_spell_uncounterable_and_only_that_one(cards):
    s, village = village_table(cards)
    mana(s, U=1)
    activate(s, "p1", village, "countered")
    settle(s)  # the ability resolves: the watch exists now (603.7)
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)
    bears = card_named(s, "Grizzly Bears")
    counter_it(s, bears)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield"  # 101.2: Counterspell resolves, and the spell is not countered
    assert len(names_in(s, "graveyard", "p2")) == 1 and zone_of(s, "Counterspell", "p2") == "p2:graveyard"
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=[card_named(s, "Grizzly Bears").id])
    bolt = card_named(s, "Lightning Bolt")
    counter_it(s, bolt)
    assert zone_of(s, "Lightning Bolt") == "p1:graveyard" and zone_of(s, "Grizzly Bears") == "p1:battlefield"  # the second spell: countered as ever
    assert s.state.players["p1"].life == 40
    check(s)


def test_mistrise_village_does_nothing_without_its_mana_and_its_effect_ends_with_the_turn(cards):
    s, village = village_table(cards)
    with pytest.raises(ActionError):
        activate(s, "p1", village, "countered")  # {U} can't be paid
    assert not tapped(s, village) and not stack_size(s)
    mana(s, U=1)
    activate(s, "p1", village, "countered")
    settle(s)
    to_bobs_main(s)  # "this turn": the watch ended with Alice's turn (514.2)
    check(s)


# ---- Overmaster / Domri, Anarch of Bolas [2732] ----------------------------------------------------------------------------------------------------------
def test_overmaster_protects_the_next_instant_or_sorcery_only(cards):
    s = build(cards, ["Overmaster", "Lightning Bolt", "Grizzly Bears"], ["Counterspell", "Counterspell"])
    stops(s)
    for n in ("Overmaster", "Lightning Bolt", "Grizzly Bears"):
        to_hand(s, n)
    for c in [c for c in s.state.cards.values() if c.name == "Counterspell" and c.owner == "p2"]:
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Overmaster").id)
    settle(s)
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)  # a creature spell: not "instant or sorcery", so it is NOT protected
    counter_it(s, card_named(s, "Grizzly Bears"))
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard"
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p2"])
    counter_it(s, card_named(s, "Lightning Bolt"))
    assert s.state.players["p2"].life == 37  # the next instant: protected, so Counterspell did nothing to it
    check(s)


def test_domri_protects_every_creature_spell_you_cast_this_turn(cards):
    s = build(cards, ["Domri, Anarch of Bolas", "Grizzly Bears", "Elvish Mystic", "Lightning Bolt"], ["Counterspell", "Counterspell", "Counterspell"])
    stops(s)
    put(s, "Domri, Anarch of Bolas")
    for n in ("Grizzly Bears", "Elvish Mystic", "Lightning Bolt"):
        to_hand(s, n)
    for c in [c for c in s.state.cards.values() if c.name == "Counterspell" and c.owner == "p2"]:
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "hand"})
    activate(s, "p1", card_named(s, "Domri, Anarch of Bolas"), "+1")
    settle(s, answer="R")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)
    counter_it(s, card_named(s, "Grizzly Bears"))
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Elvish Mystic").id)
    counter_it(s, card_named(s, "Elvish Mystic"))
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield" and zone_of(s, "Elvish Mystic") == "p1:battlefield"  # "no creature spells you cast can be countered" (the ruling)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p2"])
    counter_it(s, card_named(s, "Lightning Bolt"))
    assert zone_of(s, "Lightning Bolt") == "p1:graveyard" and s.state.players["p2"].life == 40  # an instant: countered
    check(s)


# ---- Expressive Iteration [877] --------------------------------------------------------------------------------------------------------------------------
def test_expressive_iteration_puts_one_in_hand_one_on_the_bottom_exiles_one_and_may_play_it(cards):
    s = build(cards, ["Expressive Iteration", "Grizzly Bears", "Lightning Bolt", "Elvish Mystic"], forests=6)
    to_hand(s, "Expressive Iteration")
    for n in ("Elvish Mystic", "Lightning Bolt", "Grizzly Bears"):
        on_top(s, n)  # the top three, from the top: Grizzly Bears, Lightning Bolt, Elvish Mystic
    bottom_before = library(s)[-1]
    mana(s, U=1, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Expressive Iteration").id)
    d = ask(s)
    assert d.player == "p1" and sorted(o.label for o in d.options) == ["Elvish Mystic", "Grizzly Bears", "Lightning Bolt"]  # 701.20e: only Alice looks
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "Lightning Bolt")])  # → her hand
    d = ask(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "Elvish Mystic")])  # → the bottom of her library
    settle(s)
    assert "Lightning Bolt" in names_in(s, "hand") and names_in(s, "exile") == ["Grizzly Bears"]
    assert s.state.cards[library(s)[-1]].name == "Elvish Mystic" and library(s)[-1] != bottom_before
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)  # "You may play the exiled card this turn"
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield"
    check(s)


# ---- Narset, Parter of Veils [976] -----------------------------------------------------------------------------------------------------------------------
def test_narset_stops_an_opponent_drawing_a_second_card_in_a_turn_but_not_its_controller(cards):
    s = build(cards, ["Narset, Parter of Veils", "Elvish Visionary"], ["Elvish Visionary"], forests=8)
    to_hand(s, "Narset, Parter of Veils")
    mana(s, U=2, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Narset, Parter of Veils").id)  # (cast, so it enters with its loyalty counters)
    settle(s)
    to_hand(s, "Elvish Visionary")
    mana(s, G=1, C=1)
    hand = len(s.state.zones["p1:hand"])
    cast_creature = card_named(s, "Elvish Visionary")
    act(s, "p1", type="cast_spell", card_id=cast_creature.id)
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand  # the Visionary left the hand, its trigger drew a card: Narset's controller isn't limited
    to_bobs_main(s)  # Bob's draw step: his first card this turn, allowed
    to_hand(s, "Elvish Visionary", "p2")
    bob_hand = len(s.state.zones["p2:hand"])
    mana(s, "p2", G=1, C=1)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Elvish Visionary", "p2").id)
    settle(s)
    assert len(s.state.zones["p2:hand"]) == bob_hand - 1  # the Visionary left; its trigger drew nothing (101.2: he had drawn his one card this turn)
    assert any("can't draw more than 1 card each turn" in " ".join(p.t or p.name or "" for p in line.parts) for line in s.state.log)
    check(s)


# ---- Commander's Plate [475] -----------------------------------------------------------------------------------------------------------------------------
def test_commanders_plate_gives_protection_from_each_color_outside_the_commanders_identity(cards):
    """903.4, 702.16: Alice's commander is Krenko (red): the equipped creature has protection from white, blue, black and green - not from red. +3/+3 as well."""
    from app.rules import protection
    from tests.wave43b_kit import ch

    s = build(cards, ["Commander's Plate", "Grizzly Bears"], ["Wall of Omens", "Hill Giant", "Elvish Mystic"])
    plate, bears = put(s, "Commander's Plate"), put(s, "Grizzly Bears")
    white, red, green = put(s, "Wall of Omens", "p2"), put(s, "Hill Giant", "p2"), put(s, "Elvish Mystic", "p2")
    assert not protection.protected_from(ch(s, bears), ch(s, white))
    act(s, "p1", type="attach", card_ids=[plate.id], to=bears.id)
    assert pt(s, "Grizzly Bears") == (5, 5)
    assert protection.protected_from(ch(s, bears), ch(s, white)) and protection.protected_from(ch(s, bears), ch(s, green))
    assert not protection.protected_from(ch(s, bears), ch(s, red))  # red is in Krenko's color identity
    check(s)
