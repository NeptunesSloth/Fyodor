"""Wave 31A: "If you do" consequences that read the object the action used (CR 118.12, 608.2c, 608.2h, 400.7), real Oracle text
(tests/fixtures/wave31a_if_you_do_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 118.12: "You may [do something]. If you do, …" checks that the player chose to pay "regardless of what events actually occurred", so a
  chosen action on a legal target is the whole of "did" (put a card on top of the library, damage, untap, destroy, become), and a sacrifice
  or an exile of an object that has already left is not (400.7, 701.21a).
* 608.2h: "its power" of a sacrificed creature is its last known information (the Foot Chopper ruling of 2026-01-27; a token is gone).
* ", then you may [A]. If you do, …" is the sentence "Then you may [A].": a payment (Iron Man's Treasure and the sacrifice, Trystan's Elf).
* "…, where X is the sacrificed creature's mana value" (The Meep): the X the sentence defines names the paid object too (608.2h).
* The sentences after "If you do, B" that act on what A or B moved ("Exile it at the beginning of the next end step.", "Put that card onto
  the battlefield …") belong to B's gate; a sentence that doesn't ("Scry 1.") would be skipped when the player declines, so it isn't read.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_combat import attack
from tests.test_rules_conditionals import to_turn, token_of, until
from tests.test_rules_scripts import ch
from tests.test_rules_wave7b_activation import ability_index
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave31a_if_you_do_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w31a", number=f"I{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def answer(s, say="yes", prefer=(), limit=40):
    """Resolve everything; a "you may" (or a payment's "pay" / "decline") is answered with ``say``, any other choice with ``prefer`` (when offered)
    or its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            ids = [o.id for o in d.options]
            if d.kind == "confirm":
                want = [say]
            elif "decline" in ids:
                want = ["pay" if say == "yes" else "decline"]
            else:
                want = [o for o in prefer if o in ids]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=want if len(want) >= max(1, d.min_choices) else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def hand_size(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


def library(s, pid="p1"):
    return s.state.zones.get(f"{pid}:library", [])


def stack_top(s, names, pid="p1"):
    """Put these cards on top of the library, the first named on top."""
    used: set[str] = set()
    for name in reversed(names):
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.id not in used)
        used.add(c.id)
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")


# -- the reading -------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("text", "read"), [
    ("When this creature enters, you may put target enchantment card from your graveyard on top of your library. If you do, you gain life equal to its mana value.", True),
    ("When this creature enters, you may draw a card. If you do, discard a card. Scry 1.", False),  # (the scry never depended on the draw)
    ("When this creature enters, you may exile target creature card from your graveyard. If you do, you gain 1 life. Draw a card.", False),
    ("When this creature enters, you may exile target creature card from your graveyard. If you do, create a 1/1 white Spirit creature token. "
     "At the beginning of the next end step, sacrifice this creature.", False),  # (the sacrifice is not the token's)
    ("When this creature enters, you may exile target creature card from your graveyard. If you do, create a 1/1 white Spirit creature token. "
     "Exile it at the beginning of the next end step.", True),
    ("When this creature enters, you may draw a card. If you do, you may discard a card.", False),  # (a second choice: not read)
    ("When this creature enters, mill three cards, then you may exile an Elf card from your graveyard. If you do, each opponent loses 2 life.", True),
    ("When this creature enters, mill three cards, then you may draw a card. Scry 1.", False),  # (no "If you do": ", then you may" stays as it was)
])
def test_the_sentences_after_if_you_do_are_read_only_when_they_depend_on_it(text, read):
    assert bool(scripts.definitions(ch("Host", "Creature", text))) is read


def test_a_target_of_b_beside_a_target_of_a_is_not_read():
    """Dead Reckoning: either target may be the one that is illegal as it resolves (the 2010-03-01 rulings: the card gone, no damage) — left to the players."""
    dead = next(c for c in DATA if c["name"] == "Dead Reckoning")
    assert not scripts.definitions(ch("Dead Reckoning", dead["type_line"], dead["oracle_text"]))


# -- Lagonna-Band Storyteller: a card put on top of the library, its mana value ---------------------------------------
@pytest.mark.parametrize("answer_", ["yes", "no"])
def test_lagonna_band_storyteller_gains_life_equal_to_the_cards_mana_value(cards, answer_):
    """118.12: a legal target put on top of the library is "done" (the Arrest is a 3): 3 life; declined, nothing moves and no life is gained."""
    s = build(cards, ["Lagonna-Band Storyteller", "Arrest"])
    arrest = card_named(s, "Arrest")
    act(s, "p1", type="move", card_ids=[arrest.id], to={"player": "p1", "zone": "graveyard"})
    storyteller = to_hand(s, "Lagonna-Band Storyteller")
    mana(s, W=1, C=3)
    act(s, "p1", type="cast_spell", card_id=storyteller.id)
    answer(s, answer_)
    assert (zone_of(s, "Arrest"), life(s)) == (("p1:library", 43) if answer_ == "yes" else ("p1:graveyard", 40))
    assert (library(s)[0] == arrest.id) == (answer_ == "yes")
    check(s)


def test_lagonna_band_storyteller_does_nothing_when_the_target_has_left_the_graveyard(cards):
    """608.2b / 400.7: the only target is gone as the trigger resolves: the ability doesn't resolve, so no life is gained."""
    s = build(cards, ["Lagonna-Band Storyteller", "Arrest"])
    arrest = card_named(s, "Arrest")
    act(s, "p1", type="move", card_ids=[arrest.id], to={"player": "p1", "zone": "graveyard"})
    storyteller = to_hand(s, "Lagonna-Band Storyteller")
    mana(s, W=1, C=3)
    act(s, "p1", type="cast_spell", card_id=storyteller.id)
    d = s.state.rules.decision  # (the trigger's target, chosen as it is put on the stack, 603.3d)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[arrest.id])
    assert s.state.zones.get("stack")
    act(s, "p1", type="move", card_ids=[arrest.id], to={"player": "p1", "zone": "exile"})
    answer(s, "yes")
    assert life(s) == 40 and zone_of(s, "Arrest") == "p1:exile"
    check(s)


# -- Foot Chopper: the sacrificed creature's last known power ------------------------------------------------------
def foot_chopper(cards, counters):
    """Foot Chopper in play (its 1/1 Ninja token is made and equipped), the Ninja given counters, on Alice's next turn."""
    s = build(cards, ["Foot Chopper"])
    chopper = to_hand(s, "Foot Chopper")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=chopper.id)
    answer(s)  # (its enters trigger: the Ninja token is made and equipped)
    ninja = next(c for c in s.state.cards.values() if c.is_token and c.name == "Ninja")
    if counters:
        act(s, "p1", type="counter", card_ids=[ninja.id], kind="+1/+1", delta=counters)
    to_turn(s, 3, "declare_attackers")
    attack(s, (ninja, "p2"))
    return s, ninja


@pytest.mark.parametrize("counters", [0, 2])
def test_foot_chopper_draws_cards_equal_to_the_sacrificed_creatures_last_known_power(cards, counters):
    """608.2h / the Foot Chopper ruling: the token is gone once sacrificed, so "its power" is the 1 + counters it had on the battlefield."""
    s, ninja = foot_chopper(cards, counters)
    before = hand_size(s)
    answer(s, "yes")
    assert ninja.id not in s.state.cards  # (a token ceases to exist in the graveyard, 111.8)
    assert hand_size(s) == before + 1 + counters
    check(s)


def test_foot_chopper_declined_sacrifices_nothing_and_draws_nothing(cards):
    s, ninja = foot_chopper(cards, 1)
    before = hand_size(s)
    answer(s, "no")
    assert s.state.cards[ninja.id].zone == "p1:battlefield" and hand_size(s) == before
    check(s)


def test_foot_chopper_draws_nothing_when_the_creature_left_before_the_trigger_resolved(cards):
    """400.7 / 701.21a: the equipped creature is gone, there is nothing to sacrifice, so "If you do" is false."""
    s, ninja = foot_chopper(cards, 1)
    assert s.state.zones.get("stack")  # (the trigger, waiting)
    act(s, "p1", type="move", card_ids=[ninja.id], to={"player": "p1", "zone": "graveyard"})
    before = hand_size(s)
    answer(s, "yes")
    assert hand_size(s) == before
    check(s)


# -- Séance: three sentences, the last one about the token -----------------------------------------------------------
def seance(cards):
    s = build(cards, ["Séance", "Grizzly Bears"])
    put(s, "Séance")
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "graveyard"})
    until(s, lambda s: s.state.turn.phase == "upkeep" and (s.state.rules.decision is not None or s.state.zones.get("stack")))
    return s, bears


def spirits(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Grizzly Bears" and c.zone == "p1:battlefield"]


def test_seance_exiles_the_card_copies_it_and_exiles_the_token_at_the_next_end_step(cards):
    """608.2c / 400.7: the card is exiled, the token is a copy of it with Spirit added, and "Exile it" is the token's own delayed trigger (603.7)."""
    s, bears = seance(cards)
    answer(s, "yes", prefer=(bears.id,))
    assert s.state.cards[bears.id].zone == "p1:exile" and len(spirits(s)) == 1
    assert {"Bear", "Spirit"} <= set(Plan(s.state, "p1", s.cards, None).ch(spirits(s)[0]).subtypes)  # (a copy, "in addition to its other types")
    until(s, lambda s: s.state.turn.number == 3)  # (through the end step of the turn the trigger came in)
    assert not spirits(s) and s.state.cards[bears.id].zone == "p1:exile"
    check(s)


def test_seance_declined_leaves_the_card_and_makes_no_token(cards):
    s, bears = seance(cards)
    answer(s, "no")
    assert s.state.cards[bears.id].zone == "p1:graveyard" and not spirits(s)
    until(s, lambda s: s.state.turn.number == 3)
    assert not spirits(s)  # (no token, so nothing for the delayed trigger to exile)
    check(s)


# -- Containment Construct: "you may play that card this turn" is the exiled card's ----------------------------------
def construct(cards):
    s = build(cards, ["Containment Construct", "Grizzly Bears"])
    put(s, "Containment Construct")
    driver = token_of(s, "p1", "Discarder", "Token Creature — Test", pt="1/1", text="{1}: Discard a card.")
    bears = to_hand(s, "Grizzly Bears")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=driver.id, ability=0)
    return s, bears


@pytest.mark.parametrize("answer_", ["yes", "no"])
def test_containment_construct_exiles_the_discarded_card_and_lets_you_play_it(cards, answer_):
    """118.12: the exile is probed (the card was in the graveyard); then the permission is the exiled card's, until end of turn."""
    s, bears = construct(cards)
    answer(s, answer_, prefer=(bears.id,))
    assert s.state.cards[bears.id].zone == ("p1:exile" if answer_ == "yes" else "p1:graveyard")
    if answer_ == "yes":
        mana(s, G=1, C=1)
        act(s, "p1", type="cast_spell", card_id=bears.id)
        answer(s)
        assert s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


def test_containment_construct_does_nothing_when_the_card_left_the_graveyard_first(cards):
    """400.7: the discarded card is gone from the graveyard as the trigger resolves, so the exile can't be paid and "If you do" is false."""
    s, bears = construct(cards)
    assert s.state.rules.decision.kind == "confirm"  # (asked as the trigger resolves, 603.5; the move below stands for a response)
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "hand"})
    answer(s, "yes")
    assert s.state.cards[bears.id].zone == "p1:hand"
    check(s)


# -- Baneful Omen: the revealed card's mana value ----------------------------------------------------------------------
@pytest.mark.parametrize(("answer_", "top", "lost"), [("yes", "Grizzly Bears", 2), ("no", "Grizzly Bears", 0), ("yes", "Forest", 0)])
def test_baneful_omen_drains_by_the_revealed_cards_mana_value(cards, answer_, top, lost):
    s = build(cards, ["Baneful Omen", "Grizzly Bears"])
    put(s, "Baneful Omen")
    stack_top(s, [top])
    until(s, lambda s: s.state.turn.number == 1 and s.state.turn.phase == "end" and (s.state.rules.decision is not None or s.state.zones.get("stack")))
    answer(s, answer_)
    assert life(s, "p2") == 40 - lost
    check(s)


# -- Cyclops Gladiator: "that creature deals damage equal to its power" ------------------------------------------------
@pytest.mark.parametrize("answer_", ["yes", "no"])
def test_cyclops_gladiator_is_dealt_the_targets_power_not_its_own(cards, answer_):
    """118.12: the damage was chosen, so the target (2/2, dying of it) still deals damage equal to ITS power — 2, not the Gladiator's 4."""
    s = build(cards, ["Cyclops Gladiator"], ["Grizzly Bears"])
    gladiator = put(s, "Cyclops Gladiator")
    bears = put(s, "Grizzly Bears", "p2")
    to_turn(s, 3, "declare_attackers")
    attack(s, (gladiator, "p2"))
    answer(s, answer_, prefer=(bears.id,))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert (s.state.cards[bears.id].zone, s.state.cards[gladiator.id].damage) == (("p2:graveyard", 2) if answer_ == "yes" else ("p2:battlefield", 0))
    check(s)


# -- Gamekeeper: the sentences after B belong to its gate ----------------------------------------------------------------
def gamekeeper(cards):
    s = build(cards, ["Gamekeeper", "Grizzly Bears", "Lightning Bolt"])
    keeper = put(s, "Gamekeeper")
    stack_top(s, ["Forest", "Forest", "Grizzly Bears"])
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[keeper.id])
    return s, keeper


@pytest.mark.parametrize("answer_", ["yes", "no"])
def test_gamekeeper_reveals_until_a_creature_and_puts_the_rest_into_the_graveyard(cards, answer_):
    s, keeper = gamekeeper(cards)
    answer(s, answer_)
    forests = lambda zone: sum(1 for c in s.state.cards.values() if c.name == "Forest" and c.zone == zone)  # noqa: E731
    if answer_ == "yes":
        assert (s.state.cards[keeper.id].zone, zone_of(s, "Grizzly Bears"), forests("p1:graveyard")) == ("p1:exile", "p1:battlefield", 2)
    else:
        assert (s.state.cards[keeper.id].zone, zone_of(s, "Grizzly Bears"), forests("p1:graveyard")) == ("p1:graveyard", "p1:library", 0)
    check(s)


def test_gamekeeper_puts_nothing_onto_the_battlefield_when_it_left_the_graveyard_first(cards):
    """400.7 / 118.12: the exile can't be paid (the card is gone), so none of the three sentences after it runs: nothing is revealed or moved."""
    s, keeper = gamekeeper(cards)
    assert s.state.rules.decision.kind == "confirm"  # (asked as the trigger resolves, 603.5; the move below stands for a response)
    act(s, "p1", type="move", card_ids=[keeper.id], to={"player": "p1", "zone": "hand"})
    answer(s, "yes")
    assert zone_of(s, "Grizzly Bears") == "p1:library" and not any(c.name == "Forest" and c.zone == "p1:graveyard" for c in s.state.cards.values())
    check(s)


# -- Kabira Evangel: a chosen color ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("answer_", ["yes", "no"])
def test_kabira_evangel_grants_protection_from_the_chosen_color_only_if_you_chose(cards, answer_):
    """118.12: choosing a color is the whole of "did"; "the chosen color" is the one just chosen (702.16b: a red spell can't target it)."""
    s = build(cards, ["Kabira Evangel", "Lightning Bolt"])
    kabira = to_hand(s, "Kabira Evangel")
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=kabira.id)
    answer(s, answer_, prefer=("Red",))
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    if answer_ == "yes":
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[kabira.id])
    else:
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[kabira.id])
    check(s)


# -- The Meep: "where X is the sacrificed creature's mana value" ------------------------------------------------------------
@pytest.mark.parametrize("answer_", ["yes", "no"])
def test_the_meep_sets_base_power_and_toughness_to_the_sacrificed_creatures_mana_value(cards, answer_):
    """608.2h: the Grizzly Bears (a 2) are gone when X is read — their last known mana value; every creature you control is a 2/2, the Meep too."""
    s = build(cards, ["The Meep", "Grizzly Bears"])
    meep, bears = put(s, "The Meep"), put(s, "Grizzly Bears")
    token_of(s, "p1", "Big Token", "Token Creature — Test", pt="4/4")
    to_turn(s, 3, "declare_attackers")
    attack(s, (meep, "p2"))
    answer(s, answer_, prefer=(bears.id,))
    assert (pt(s, "The Meep"), pt(s, "Big Token"), zone_of(s, "Grizzly Bears")) == (
        ((2, 2), (2, 2), "p1:graveyard") if answer_ == "yes" else ((0, 4), (4, 4), "p1:battlefield"))
    check(s)


# -- Iron Man: "1 plus the sacrificed artifact's mana value" ----------------------------------------------------------------
def test_iron_man_searches_for_an_artifact_one_more_than_the_sacrificed_ones_mana_value(cards):
    """608.2h: the Sol Ring (1) is gone, so the search is for a mana value of 2 — only the Arcane Signet matches (not the other Sol Ring, a 1)."""
    s = build(cards, ["Iron Man, Titan of Innovation", "Sol Ring", "Sol Ring", "Arcane Signet"])
    iron = put(s, "Iron Man, Titan of Innovation")
    ring = put(s, "Sol Ring")
    signet = card_named(s, "Arcane Signet")
    act(s, "p1", type="pass_priority")  # → combat
    attack(s, (iron, "p2"))
    answer(s, "yes", prefer=(ring.id,))
    assert zone_of(s, "Sol Ring") == "p1:graveyard" and s.state.cards[ring.id].zone == "p1:graveyard"
    assert s.state.cards[signet.id].zone == "p1:battlefield" and s.state.cards[signet.id].tapped
    assert sum(1 for c in s.state.cards.values() if c.name == "Sol Ring" and c.zone == "p1:battlefield") == 0
    check(s)


# -- Identity Thief: the exiled card comes back at the end step, the copy "of that creature" -------------------------------
@pytest.mark.parametrize("answer_", ["yes", "no"])
def test_identity_thief_copies_the_exiled_creature_and_returns_it_at_the_next_end_step(cards, answer_):
    s = build(cards, ["Identity Thief"], ["Grizzly Bears"])
    thief, bears = put(s, "Identity Thief"), put(s, "Grizzly Bears", "p2")
    to_turn(s, 3, "declare_attackers")
    attack(s, (thief, "p2"))
    answer(s, answer_, prefer=(bears.id,))
    if answer_ == "yes":
        assert s.state.cards[bears.id].zone == "p2:exile" and s.state.cards[thief.id].zone == "p1:battlefield"
        assert pt(s, "Identity Thief") == (2, 2)  # (a copy of the Grizzly Bears until end of turn)
        until(s, lambda s: s.state.turn.number == 4)  # (through the end step of this turn)
        assert s.state.cards[bears.id].zone == "p2:battlefield" and pt(s, "Identity Thief") == (0, 3)
    else:
        assert s.state.cards[bears.id].zone == "p2:battlefield" and pt(s, "Identity Thief") == (0, 3)
    check(s)


def test_the_gate_of_if_you_do_holds_the_sentences_after_b():
    """Gamekeeper: the reveal, the pick and the rest of the library all hang on the exile (skip 3), so a card that never left isn't followed by them."""
    keeper = next(c for c in DATA if c["name"] == "Gamekeeper")
    d = scripts.definitions(ch("Gamekeeper", keeper["type_line"], keeper["oracle_text"]))[0]
    gate = next(e for e in d["effects"] if e["do"] == "only_if")
    assert gate["skip"] == len(d["effects"]) - d["effects"].index(gate) - 1 == 3


# -- Scion of the Ur-Dragon: 118.12b, "If you do" asks whether the player searched --------------------------------------------
@pytest.mark.parametrize("library_has_a_dragon", [True, False])
def test_scion_of_the_ur_dragon_becomes_a_copy_of_the_card_it_found(cards, library_has_a_dragon):
    """118.12b: the clause checks that the player searched, not that they found anything; "that card" is the one found (a Shivan Dragon, a 5/5),
    and with none to find there is nothing to copy."""
    s = build(cards, ["Scion of the Ur-Dragon", *(["Shivan Dragon"] if library_has_a_dragon else [])])
    scion = put(s, "Scion of the Ur-Dragon")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=scion.id, ability=ability_index(s, scion, "Search"))
    answer(s)
    c = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[scion.id])
    assert (c.name, pt(s, "Scion of the Ur-Dragon")) == (
        ("Shivan Dragon", (5, 5)) if library_has_a_dragon else ("Scion of the Ur-Dragon", (4, 4)))
    assert (zone_of(s, "Shivan Dragon") == "p1:graveyard") if library_has_a_dragon else True
    check(s)


# -- Zealot il-Vec: the damage was chosen, so it was done, though it was prevented --------------------------------------
@pytest.mark.parametrize("answer_", ["yes", "no"])
def test_zealot_il_vec_still_prevents_its_combat_damage_when_the_damage_it_dealt_was_prevented(cards, answer_):
    """118.12 / the Zealot il-Vec ruling of 2006-09-25: "If you choose to have it deal 1 damage to a creature and that damage is prevented or replaced,
    its combat damage will still be prevented." Mending Hands stops the 1; the Zealot (shadow, unblocked) still deals no combat damage to Bob."""
    s = build(cards, ["Zealot il-Vec", "Mending Hands"], ["Grizzly Bears"])
    zealot, bears = put(s, "Zealot il-Vec"), put(s, "Grizzly Bears", "p2")
    to_turn(s, 3, "main1")
    hands = to_hand(s, "Mending Hands")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=hands.id, targets=[bears.id])
    answer(s)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    attack(s, (zealot, "p2"))
    answer(s, answer_, prefer=(bears.id,))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert (life(s, "p2"), s.state.cards[bears.id].damage) == ((40, 0) if answer_ == "yes" else (39, 0))
    check(s)
# -- end --
