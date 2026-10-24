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


# -- Shellshock -----------------------------------------------------------------------------------------------------------------------------------
def test_shellshock_x_to_one_creature_per_opponent_and_a_mutagen_per_creature_dealt_damage(cards):
    s = build(cards, ["Shellshock"], ["Probe Wall"])
    wall = put(s, "Probe Wall", "p2")
    spell = to_hand(s, "Shellshock")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[wall.id], target_counts=[1], x_value=2)
    answer(s)
    assert s.state.cards[wall.id].damage == 2 and len(tokens(s, "Mutagen", "p1")) == 1
    check(s)


# -- Ravenous Gigantotherium ----------------------------------------------------------------------------------------------------------------------
def test_ravenous_gigantotherium_divides_its_power_and_each_target_bites_back(cards):
    """Power 3 divided 2 / 1 between Bob's Bears (they die) and Wall; the Bears still deal their 2 back, the 0-power Wall nothing."""
    s = build(cards, ["Ravenous Gigantotherium"], ["Grizzly Bears", "Probe Wall"])
    bears, wall = put(s, "Grizzly Bears", "p2"), put(s, "Probe Wall", "p2")
    beast = to_hand(s, "Ravenous Gigantotherium")
    mana(s, G=2, C=5)
    act(s, "p1", type="cast_spell", card_id=beast.id)
    d = pick(s, "choose_cards", bears.id, wall.id)
    assert d.max_choices == 3
    d = s.state.rules.decision
    assert d is not None and d.kind == "divide"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[], amounts=[2, 1])
    answer(s)
    assert zone_of(s, bears) == "p2:graveyard" and s.state.cards[wall.id].damage == 1 and s.state.cards[beast.id].damage == 2
    check(s)


# -- Archery Training -----------------------------------------------------------------------------------------------------------------------------
def test_archery_training_the_creature_shoots_x_where_x_counts_the_auras_arrows(cards):
    """The Wall has the Aura's ability; X is the arrow counters on the Aura (607.1a), not on the Wall: 2 to the attacking 5/3."""
    s = build(cards, ["Archery Training", "Twisted Abomination", "Probe Wall"])
    bears, wall = put(s, "Twisted Abomination"), put(s, "Probe Wall")
    aura = to_hand(s, "Archery Training")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[wall.id])
    answer(s)
    act(s, "p1", type="counter", card_ids=[aura.id], kind="arrow", delta=2)
    act(s, "p1", type="counter", card_ids=[wall.id], kind="arrow", delta=5)  # (counters on the creature itself don't count)
    ready(s, bears, wall)
    kit.full_control(s)
    while not (s.state.rules.decision and s.state.rules.decision.kind == "declare_attackers"):
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    act(s, "p1", type="activate_ability", card_id=wall.id, ability=ability_index(s, wall, "arrow counters"), targets=[bears.id])
    answer(s)
    assert s.state.cards[bears.id].damage == 2 and s.state.cards[wall.id].tapped
    check(s)


# -- Reinforce X (Wren's Run Hydra; Swell of Courage reads the same) ----------------------------------------------------------------------------
def test_wrens_run_hydra_reinforce_x_puts_the_x_paid(cards):
    """702.77a: "{X}{G}{G}, Discard this card: Put X +1/+1 counters on target creature." from the hand, X 2."""
    s = build(cards, ["Wren's Run Hydra", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    hydra = to_hand(s, "Wren's Run Hydra")
    mana(s, G=2, C=2)
    act(s, "p1", type="activate_ability", card_id=hydra.id, ability=ability_index(s, hydra, "Discard this card"), targets=[bears.id], x_value=2)
    answer(s)
    assert zone_of(s, hydra) == "p1:graveyard" and s.state.cards[bears.id].counters.get("+1/+1") == 2
    check(s)


# -- Tester of the Tangential ---------------------------------------------------------------------------------------------------------------------
def test_tester_of_the_tangential_pays_x_and_moves_x_counters(cards):
    """Three +1/+1 counters on it; at the beginning of combat Alice pays {2}: two move onto the Bears (the reflexive target, 603.12)."""
    s = build(cards, ["Tester of the Tangential", "Grizzly Bears"])
    tester, bears = put(s, "Tester of the Tangential"), put(s, "Grizzly Bears")
    act(s, "p1", type="counter", card_ids=[tester.id], kind="+1/+1", delta=3)
    for forest in [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:2]:  # (mana empties between steps: lands pay)
        to_zone(s, forest, "battlefield")
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    answer(s, "yes", "x:2", bears.id)
    assert s.state.cards[bears.id].counters.get("+1/+1") == 2 and s.state.cards[tester.id].counters.get("+1/+1") == 1
    check(s)


# -- Multiple Choice ------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("x", [4, 3])
def test_multiple_choice_x_four_does_every_line_x_three_only_the_token(cards, x):
    """X 4: scry 1 and draw, Bob (chosen) returns his Bears, a 4/4 Elemental. X 3: only the Elemental — nothing is asked."""
    s = build(cards, ["Multiple Choice"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    spell = to_hand(s, "Multiple Choice")
    before = hand(s)
    mana(s, U=1, C=x)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=x)
    answer(s, "yes", "p2", bears.id)
    assert len(tokens(s, "Elemental", "p1")) == 1
    assert (zone_of(s, bears), hand(s)) == (("p2:hand", before) if x == 4 else ("p2:battlefield", before - 1))
    check(s)


# -- Change of Plans ------------------------------------------------------------------------------------------------------------------------------
def test_change_of_plans_two_connive_then_one_phases_out(cards):
    """X 2: both connive (draw, discard: Opt is a nonland card, a +1/+1 counter each), then Alice phases out only the Bears."""
    s = build(cards, ["Change of Plans", "Grizzly Bears", "Llanowar Elves", *["Opt"] * 4])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    spell = to_hand(s, "Change of Plans")
    set_hand(s, "p1", 3)
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id, elves.id], target_counts=[2], x_value=2)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and "any number of them" in d.prompt:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])
            break
        if d is not None:
            opts = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o for o in opts if s.state.cards.get(o) and s.state.cards[o].name == "Opt"][:1] or opts[: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    answer(s)
    assert zone_of(s, bears) == "p1:phased" and zone_of(s, elves) == "p1:battlefield"
    assert s.state.cards[bears.id].counters.get("+1/+1") == 1 and s.state.cards[elves.id].counters.get("+1/+1") == 1
    check(s)


# -- Flame Discharge ------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("modified", "dealt"), [(False, 2), (True, 4)])
def test_flame_discharge_x_plus_two_with_a_modified_creature_as_it_was_cast(cards, modified, dealt):
    """X 2 to the Wall; the Bears with a +1/+1 counter as casting finished (601.2i): 4 — even with the counter gone by resolution."""
    s = build(cards, ["Flame Discharge", "Grizzly Bears"], ["Probe Wall"])
    wall, bears = put(s, "Probe Wall", "p2"), put(s, "Grizzly Bears")
    if modified:
        act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=1)
    spell = to_hand(s, "Flame Discharge")
    mana(s, R=1, C=2)
    kit.full_control(s)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[wall.id], x_value=2)
    if modified:
        act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=-1)
    answer(s)
    assert s.state.cards[wall.id].damage == dealt
    check(s)
