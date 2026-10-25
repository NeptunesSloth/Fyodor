"""Wave 110D: activation costs that name a group, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 601.2h, 118.3: a cost is paid in full or not at all — "two creature cards from a single graveyard" (Night Soil), "a Fungus card from a graveyard"
  (Thelon of Havenwood), "two untapped creatures you control that share a creature type" (Weight of Conscience, 205.3m), "two cards from your hand that share
  a color" (Illuminated Folio, 701.20a, 105.2c), "five untapped attacking creatures you control named Templar Knight", "a creature named Feral Shadow, a
  creature named Breathstealer, and this creature" (Urborg Panther), "a suspected creature" (Rune-Brand Juggler, 701.60), "an instant or sorcery spell you
  control" (Nivmagus Elemental: the spell is exiled, not countered).
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build, card_named
from tests.wave110d_kit import (  # noqa: F401
    EXTRA,
    activate,
    card_db,
    cast_on,
    check,
    fresh,
    full,
    grave_new,
    hand_new,
    life,
    mana,
    move,
    next_turn,
    now,
    put,
    put_new,
    refused,
    settle,
    to_bottom,
    to_hand,
    to_phase,
)

CARDS = ["Nivmagus Elemental", "Rune-Brand Juggler", "Night Soil", "Thelon of Havenwood", "Weight of Conscience", "Illuminated Folio", "Templar Knight",
         "Urborg Panther"]


@pytest.mark.parametrize("name", CARDS)
def test_the_cards_are_full(name):
    assert full(name)


def test_nivmagus_elemental_exiles_a_spell_you_control(cards):
    s = build(cards, ["Nivmagus Elemental", "Lightning Bolt", "Grizzly Bears"])
    nivmagus = put(s, "Nivmagus Elemental")
    bear = to_hand(s, "Grizzly Bears")
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bear.id)
    refused(s, "You can't pay", nivmagus, "Exile an instant or sorcery spell")  # a creature spell can't pay it
    act(s, "p1", type="pass_priority")
    settle(s)
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    activate(s, nivmagus, "Exile an instant or sorcery spell")  # in response
    assert now(s, bolt).zone == "p1:exile" and life(s, "p2") == 40  # exiled, not countered: it never resolved
    assert now(s, nivmagus).counters == {"+1/+1": 2}
    check(s)


def test_rune_brand_juggler_sacrifices_only_a_suspected_creature(cards):
    s = build(cards, ["Rune-Brand Juggler", "Repeat Offender", "Grizzly Bears"], ["Grizzly Bears"])
    juggler, offender, bear = put(s, "Rune-Brand Juggler"), put(s, "Repeat Offender"), put(s, "Grizzly Bears", "p2")
    mana(s, B=1, R=1, C=3)
    refused(s, "You can.t pay|Choose|isn.t|aren.t", juggler, "{3}{B}{R}, Sacrifice a suspected creature", targets=[bear.id])  # nobody is suspected
    mana(s, B=3)
    activate(s, offender, "{2}{B}")  # "Otherwise, suspect it."
    assert offender.id in {c for c in s.state.cards} and s.state.rules.suspected
    activate(s, juggler, "{3}{B}{R}, Sacrifice a suspected creature", targets=[bear.id])
    assert now(s, offender).zone == "p1:graveyard" and now(s, bear).zone == "p2:graveyard"  # -5/-5 killed the Bears
    check(s)


def test_night_soil_needs_both_cards_in_one_graveyard(cards):
    s = build(cards, ["Night Soil", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears", "Llanowar Elves"])
    soil = put(s, "Night Soil")
    mine, theirs = grave_new(s, "Grizzly Bears"), grave_new(s, "Grizzly Bears", "p2")
    mana(s, C=1)
    refused(s, "You can.t pay|Choose|isn.t|aren.t", soil, "{1}, Exile two creature cards")  # one in each graveyard
    elves = grave_new(s, "Llanowar Elves", "p2")
    activate(s, soil, "{1}, Exile two creature cards", cost_choices=[{"component": 1, "cards": [theirs.id, elves.id]}])
    assert now(s, theirs).zone == "p2:exile" and now(s, elves).zone == "p2:exile" and now(s, mine).zone == "p1:graveyard"
    assert any(c.name == "Saproling" for c in s.state.cards.values())
    check(s)


def test_night_soil_refuses_a_pair_split_over_two_graveyards(cards):
    s = build(cards, ["Night Soil", "Grizzly Bears"], ["Llanowar Elves"])
    soil = put(s, "Night Soil")
    mine, theirs = grave_new(s, "Grizzly Bears"), grave_new(s, "Llanowar Elves", "p2")
    mana(s, C=1)
    refused(s, "You can.t pay|Choose|isn.t|aren.t", soil, "{1}, Exile two creature cards", cost_choices=[{"component": 1, "cards": [mine.id, theirs.id]}])
    check(s)


def test_thelon_puts_a_spore_counter_on_every_fungus(cards):
    s = build(cards, ["Thelon of Havenwood", "Thallid"], ["Thallid", "Thallid"])
    thelon, mine, theirs = put(s, "Thelon of Havenwood"), put(s, "Thallid"), put_new(s, "Thallid", "p2")
    mana(s, B=1, G=1)
    refused(s, "You can.t pay|Choose|isn.t|aren.t", thelon, "{B}{G}, Exile a Fungus card")  # no Fungus card in a graveyard
    fungus = grave_new(s, "Thallid", "p2")
    activate(s, thelon, "{B}{G}, Exile a Fungus card")
    assert now(s, fungus).zone == "p2:exile"
    assert now(s, mine).counters == {"spore": 1} and now(s, theirs).counters == {"spore": 1}  # each Fungus on the battlefield, anyone's
    check(s)


def test_weight_of_conscience_taps_two_creatures_that_share_a_type(cards):
    s = build(cards, ["Weight of Conscience", "Grizzly Bears", "Grizzly Bears", "Llanowar Elves"], ["Llanowar Elves"])
    victim = put(s, "Llanowar Elves", "p2")
    aura = cast_on(s, "Weight of Conscience", victim)
    bear = put_new(s, "Grizzly Bears")
    elves = put(s, "Llanowar Elves")
    refused(s, "You can.t pay|Choose|isn.t|aren.t", aura, "Tap two untapped creatures", cost_choices=[{"component": 0, "cards": [bear.id, elves.id]}])  # a Bear and an Elf share no type
    bear2 = put_new(s, "Grizzly Bears")
    activate(s, aura, "Tap two untapped creatures", cost_choices=[{"component": 0, "cards": [bear.id, bear2.id]}])
    assert now(s, bear).tapped and now(s, bear2).tapped and not now(s, elves).tapped
    assert now(s, victim).zone == "p2:exile"
    check(s)


def test_illuminated_folio_reveals_two_cards_that_share_a_color(cards):
    s = build(cards, ["Illuminated Folio", "Grizzly Bears", "Llanowar Elves", "Lightning Bolt"])  # (a Bear and an Elf: both green)
    folio = put(s, "Illuminated Folio")
    bear, elves, bolt = to_hand(s, "Grizzly Bears"), to_hand(s, "Llanowar Elves"), to_hand(s, "Lightning Bolt")
    mana(s, C=1)
    refused(s, "You can.t pay|Choose|isn.t|aren.t", folio, "{1}, {T}, Reveal two cards", cost_choices=[{"component": 2, "cards": [bear.id, bolt.id]}])  # green and red share no color
    n = len(s.state.zones["p1:hand"])
    activate(s, folio, "{1}, {T}, Reveal two cards", cost_choices=[{"component": 2, "cards": [bear.id, elves.id]}])
    assert len(s.state.zones["p1:hand"]) == n + 1  # drew a card; the revealed cards stay in the hand
    assert now(s, bear).zone == "p1:hand" and now(s, folio).tapped
    check(s)


def test_urborg_panther_sacrifices_the_three_named_creatures(cards):
    s = build(cards, ["Urborg Panther", "Feral Shadow", "Breathstealer", "Spirit of the Night"])
    panther, shadow, stealer = put(s, "Urborg Panther"), put(s, "Feral Shadow"), put(s, "Breathstealer")
    spirit = card_named(s, "Spirit of the Night")
    assert spirit.zone == "p1:library"
    activate(s, panther, "Sacrifice a creature named Feral Shadow")
    assert all(now(s, c).zone == "p1:graveyard" for c in (panther, shadow, stealer))
    assert now(s, spirit).zone == "p1:battlefield"
    check(s)


def test_urborg_panther_needs_both_named_creatures(cards):
    s = build(cards, ["Urborg Panther", "Feral Shadow", "Breathstealer", "Spirit of the Night"])
    panther, _ = put(s, "Urborg Panther"), put(s, "Feral Shadow")
    refused(s, "You can.t pay|Choose|isn.t|aren.t", panther, "Sacrifice a creature named Feral Shadow")  # no Breathstealer
    check(s)


def knights_attacking(cards, n):
    s = build(cards, ["Templar Knight"] * 5 + ["Mox Opal"])
    knights = [put_new(s, "Templar Knight") for _ in range(5)]
    to_bottom(s, fresh(s, "Mox Opal"))  # (nobody draws it; it is there to be found)
    next_turn(s)
    next_turn(s)  # Alice's turn 3: the Knights have been under her control since it began
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="set_stops", own=["declare_attackers"], smart_pass=False)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": k.id, "target": "p2"} for k in knights[:n]])
    mana(s, W=1)
    return s, knights


def test_templar_knight_needs_five_attacking_knights(cards):
    s, knights = knights_attacking(cards, 4)
    refused(s, "You can.t pay", knights[0], "{W}, Tap five untapped attacking")
    check(s)


def test_templar_knight_five_attackers_fetch_a_legendary_artifact(cards):
    s, knights = knights_attacking(cards, 5)
    activate(s, knights[0], "{W}, Tap five untapped attacking")
    assert all(now(s, k).tapped for k in knights)  # (vigilance kept them untapped to pay)
    assert any(c.name == "Mox Opal" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    check(s)
