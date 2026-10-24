"""Wave 100E: X values counted from cards and objects (app/rules/xdamage100e.py; CR 2026-09-25). Real Oracle text
(tests/fixtures/wave100e_xdamage_cards.json); every scenario checks the replay and a save and a load.

* 608.2h / 611.2c: a count fixed as it resolves — the tokens of Return of the Mole Man, Candlekeep Inspiration's base power and toughness.
* 613.1d/e, 613.4b: Fractalize sets creature type, colors and base power and toughness until end of turn.
* An exiled card's power and toughness (Bioplasm); a revealed number of cards the revealing player picks (701.20a: Thieving Sprite, Cabal
  Interrogator); a toughness-sized branch (Blood Lust).
"""

from __future__ import annotations

import pytest

from tests import wave100e_kit as kit
from tests.game_helpers import act
from tests.test_rules_wave7b_activation import ability_index
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand
from tests.wave100e_kit import answer, chars, hand, library, pick, set_hand, tokens, zone_of


@pytest.fixture()
def cards(settings):
    yield from kit.repo(settings)


def ready(s, *cs):
    """Creatures that have been under their controller's control since the turn began (302.6)."""
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0


def to_zone(s, c, zone, pid="p1"):
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": zone})


# -- Return of the Mole Man -----------------------------------------------------------------------------------------------------------------------
def test_return_of_the_mole_man_counts_itself_among_the_permanent_cards(cards):
    """Grizzly Bears and a Forest in the graveyard (and an Opt, not a permanent card), then the sacrificed enchantment: three Moloids, each
    with the attack trigger."""
    s = build(cards, ["Return of the Mole Man", "Grizzly Bears", "Opt"])
    mole = put(s, "Return of the Mole Man")
    for name in ("Grizzly Bears", "Opt", "Forest"):
        to_zone(s, card_named(s, name), "graveyard")
    mana(s, G=1, C=5)
    act(s, "p1", type="activate_ability", card_id=mole.id, ability=ability_index(s, mole, "Create X"))
    answer(s)
    moloids = tokens(s, "Moloid", "p1")
    assert zone_of(s, mole) == "p1:graveyard" and len(moloids) == 3
    ch = chars(s, moloids[0])
    assert ch.pt == (1, 1) and "Minion" in ch.subtypes and any("Whenever this creature attacks, you may mill a card" in a.text for a in ch.abilities)
    check(s)


# -- Fractalize -----------------------------------------------------------------------------------------------------------------------------------
def test_fractalize_makes_a_green_and_blue_fractal_of_x_plus_one(cards):
    s = build(cards, ["Fractalize"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    spell = to_hand(s, "Fractalize")
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id], x_value=3)
    answer(s)
    ch = chars(s, bears)
    assert pt(s, "Grizzly Bears", "p2") == (4, 4) and set(ch.colors) == {"G", "U"} and set(ch.subtypes) == {"Fractal"}
    check(s)


# -- Candlekeep Inspiration -----------------------------------------------------------------------------------------------------------------------
def test_candlekeep_inspiration_counts_instants_sorceries_and_adventurers_you_own(cards):
    """Opt and Lightning Bolt in Alice's graveyard, Bonecrusher Giant (an adventurer) in her exile: X 3. Bob's Opt and Alice's Grizzly Bears card
    don't count. Fixed as it resolves: a later instant in the graveyard and a creature entering later change nothing."""
    s = build(cards, ["Candlekeep Inspiration", "Opt", "Lightning Bolt", "Bonecrusher Giant // Stomp", "Grizzly Bears", "Grizzly Bears", "Firebolt"],
              ["Opt"])
    first, second = [c for c in s.state.cards.values() if c.name == "Grizzly Bears"]
    to_zone(s, first, "battlefield")
    for c in (card_named(s, "Opt"), card_named(s, "Lightning Bolt"), second):
        to_zone(s, c, "graveyard")
    to_zone(s, card_named(s, "Bonecrusher Giant // Stomp"), "exile")
    to_zone(s, card_named(s, "Opt", "p2"), "graveyard", "p2")
    spell = to_hand(s, "Candlekeep Inspiration")
    mana(s, U=1, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s)
    assert chars(s, first).pt == (3, 3)
    to_zone(s, card_named(s, "Firebolt"), "graveyard")
    to_zone(s, second, "battlefield")
    assert chars(s, first).pt == (3, 3) and chars(s, second).pt == (2, 2)
    check(s)


# -- Bioplasm -------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("top", "size"), [("Twisted Abomination", (9, 7)), ("Opt", (4, 4))])
def test_bioplasm_gets_the_exiled_creature_cards_power_and_toughness(cards, top, size):
    s = build(cards, ["Bioplasm", top])
    bioplasm = put(s, "Bioplasm")
    ready(s, bioplasm)
    card = card_named(s, top)
    to_zone(s, card, "library")
    assert library(s, "p1")[0] == card.id
    act(s, "p1", type="pass_priority")  # -> declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bioplasm.id, "target": "p2"}])
    answer(s)
    assert zone_of(s, card) == "p1:exile" and pt(s, "Bioplasm") == size
    check(s)


# -- Thieving Sprite / Cabal Interrogator ---------------------------------------------------------------------------------------------------------
def test_thieving_sprite_reveals_one_card_per_faerie_bob_picks_alice_chooses(cards):
    """Alice controls the Sprite and another Faerie: Bob (holding four) picks two to reveal, Alice chooses one of those, Bob discards it."""
    s = build(cards, ["Thieving Sprite", "Probe Faerie"], islands=20)
    put(s, "Probe Faerie")
    set_hand(s, "p2", 4)
    sprite = to_hand(s, "Thieving Sprite")
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=sprite.id)
    pick(s, "choose_one", "p2")  # (the trigger's target)
    held = list(s.state.zones["p2:hand"])
    d = pick(s, "choose_cards", held[1], held[2])
    assert d.player == "p2" and (d.min_choices, d.max_choices) == (2, 2)
    d = pick(s, "choose_cards", held[2])
    assert d.player == "p1" and {o.id for o in d.options} == {held[1], held[2]}
    answer(s)
    assert s.state.cards[held[2]].zone == "p2:graveyard" and hand(s, "p2") == 3
    check(s)


def test_cabal_interrogator_reveals_x_cards(cards):
    s = build(cards, ["Cabal Interrogator"], islands=20)
    interrogator = put(s, "Cabal Interrogator")
    ready(s, interrogator)
    set_hand(s, "p2", 3)
    held = list(s.state.zones["p2:hand"])
    mana(s, B=1, C=1)
    act(s, "p1", type="activate_ability", card_id=interrogator.id, ability=ability_index(s, interrogator, "reveals X cards"), targets=["p2"], x_value=1)
    d = pick(s, "choose_cards", held[0])
    assert d.player == "p2" and d.max_choices == 1
    answer(s)
    assert s.state.cards[held[0]].zone == "p2:graveyard" and hand(s, "p2") == 2
    check(s)


# -- Blood Lust -----------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("victim", "size"), [("Probe Wall", (4, 2)), ("Grizzly Bears", (6, 1)), ("Twisted Abomination", (9, 1))])
def test_blood_lust_minus_four_or_down_to_one_toughness(cards, victim, size):
    """Toughness 6: +4/-4; toughness 2 and 3: +4/-X where X is toughness minus 1 (down to 1)."""
    s = build(cards, ["Blood Lust"], [victim])
    target = put(s, victim, "p2")
    spell = to_hand(s, "Blood Lust")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[target.id])
    answer(s)
    assert pt(s, victim, "p2") == size
    check(s)


# -- Zoyowa's Justice -----------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cast", [True, False])
def test_zoyowas_justice_its_owner_shuffles_it_in_and_discovers_its_mana_value(cards, cast):
    """Bob's Twisted Abomination (mana value 6) goes into his library; Bob discovers 6 — his only nonland card is that one: he casts it free,
    or puts it into his hand."""
    s = build(cards, ["Zoyowa's Justice"], ["Twisted Abomination"])
    big = put(s, "Twisted Abomination", "p2")
    spell = to_hand(s, "Zoyowa's Justice")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[big.id])
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p2"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["yes" if cast else "no"])
    answer(s)
    found = card_named(s, "Twisted Abomination", "p2")
    assert found.zone == ("p2:battlefield" if cast else "p2:hand") and zone_of(s, spell) == "p1:graveyard"
    assert all(s.state.cards[c].name == "Island" for c in library(s, "p2"))
    check(s)


# -- Sylvan Offering ------------------------------------------------------------------------------------------------------------------------------
def test_sylvan_offering_you_and_the_chosen_opponent_each_get_both_token_sets(cards):
    s = build(cards, ["Sylvan Offering"])
    spell = to_hand(s, "Sylvan Offering")
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=2)
    pick(s, "choose_one", "p2")
    pick(s, "choose_one", "p2")
    answer(s)
    for pid in ("p1", "p2"):
        (treefolk,) = tokens(s, "Treefolk", pid)
        assert chars(s, treefolk).pt == (2, 2) and len(tokens(s, "Elf Warrior", pid)) == 2
    check(s)


# -- Mind Bomb ------------------------------------------------------------------------------------------------------------------------------------
def test_mind_bomb_each_player_takes_three_minus_what_they_discarded(cards):
    """Alice discards one card (dealt 2), Bob three (dealt 0)."""
    s = build(cards, ["Mind Bomb"], islands=20)
    spell = to_hand(s, "Mind Bomb")
    set_hand(s, "p1", 3)
    set_hand(s, "p2", 4)
    mine, theirs = [c for c in s.state.zones["p1:hand"] if c != spell.id], list(s.state.zones["p2:hand"])
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = pick(s, "choose_cards", mine[0])
    assert d.player == "p1"
    d = pick(s, "choose_cards", *theirs[:3])
    assert d.player == "p2"
    answer(s)
    assert s.state.players["p1"].life == 38 and s.state.players["p2"].life == 40 and hand(s, "p2") == 1 and hand(s, "p1") == 1
    check(s)


# -- Breakthrough ---------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("x", "kept"), [(1, 1), (0, 0), (9, 6)])
def test_breakthrough_draws_four_and_keeps_x(cards, x, kept):
    """Two cards in hand besides Breakthrough, four drawn: six; keep X, discard the rest."""
    s = build(cards, ["Breakthrough", *["Opt"] * 6])
    spell = to_hand(s, "Breakthrough")
    set_hand(s, "p1", 3)
    mana(s, U=1, C=x)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=x)
    answer(s)
    assert hand(s) == kept
    check(s)
