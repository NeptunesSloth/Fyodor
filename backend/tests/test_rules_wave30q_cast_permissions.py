"""Wave 30Q: per-turn casting and playing from the graveyard (CR 2026-09-25), real Oracle text
(tests/fixtures/wave30q_cast_permissions_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 601.3, 305.1: casting or playing from the graveyard needs a permission; the permission changes where, never when (normal timing, the land drop, 305.2).
* Muldrotha (rulings 2020-11-10): one land and one permanent spell of EACH permanent type per turn; a card of several types counts as one of them,
  the caster's choice ("you may cast an artifact creature spell as your artifact spell and another as your creature spell"); costs are paid in full.
* 601.2b / 118.8: "by paying 3 life / sacrificing a creature in addition to paying its other costs" is an additional cost; 119.4: life is paid only from
  a life total at least that high. 122.6 / 614.1c: "that artifact enters tapped / with a finality counter on it" are entering replacements.
* 700.6: historic is an artifact, a legendary or a Saga; 611.2a: Chainer's "this turn" permission ends in the cleanup step, one creature spell.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.casting import castable
from app.rules.plan import Plan
from app.rules.view import hints
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave30h_linked_exile import put_in, settle, to_turn, zone  # noqa: F401
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30q_cast_permissions_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t30q", number=f"Q{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Muldrotha, the Gravetide", "Titania, Nature's Force", "Zask, Skittering Swarmlord", "Hazezon, Shaper of Sand", "Chainer, Nightmare Adept",
        "Edgar, Master Machinist", "Noctis, Prince of Lucis", "Leonardo, Sewer Samurai", "Serra Paragon", "The Eighth Doctor", "Festival of Embers",
        "Maestros Ascendancy", "Arcade Gannon", "Liliana, Untouched by Death"]
MULDROTHA = "Muldrotha, the Gravetide"


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def cast(s, name, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, **kw)


def castable_now(s, cards, name, pid="p1"):
    return castable(s.state, pid, card_named(s, name, pid), cards, check_priority=False)


def grave(s, *names, pid="p1"):
    for n in names:
        put_in(s, n, "graveyard", pid)


def answer(s, label):
    """Answer the open choice with the option of that label."""
    d = s.state.rules.decision
    assert d is not None, "nothing was asked"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == label)])


def asked(s):
    d = s.state.rules.decision
    return None if d is None else sorted(o.label for o in d.options)


def refused(s, name, pid="p1", **kw):
    with pytest.raises(ActionError):
        cast(s, name, pid, **kw)


# ---- Muldrotha, the Gravetide ----------------------------------------------------------------------------------------------------------------
def test_muldrotha_one_land_and_one_permanent_spell_of_each_type_a_turn(cards):
    """"During each of your turns, you may play a land and cast a permanent spell of each permanent type from your graveyard." An artifact creature
    asks which type it uses (the Perilous Myr is the creature, so the Shimmer Myr is still the artifact); the second creature, the second artifact and
    a second land are refused; an enchantment creature uses the type that is left. A new turn starts over; on Bob's turn nothing is offered."""
    s = build(cards, [MULDROTHA, "Perilous Myr", "Shimmer Myr", "Grizzly Bears", "Courser of Kruphix", "Bonesplitter", "Gideon Jura",
                      "Command Tower", "Ambush Viper", "Swords to Plowshares"], ["Grizzly Bears"])
    put(s, MULDROTHA)
    grave(s, "Perilous Myr", "Shimmer Myr", "Grizzly Bears", "Courser of Kruphix", "Bonesplitter", "Gideon Jura", "Command Tower",
          "Forest", "Swords to Plowshares", "Ambush Viper")
    grave(s, "Grizzly Bears", pid="p2")
    mana(s, G=14, W=2)
    h = hints(s.state, "p1", cards)
    ids = lambda *ns: {card_named(s, n).id for n in ns}  # noqa: E731
    assert ids("Perilous Myr", "Grizzly Bears", "Bonesplitter", "Gideon Jura") <= set(h["castable"])
    assert card_named(s, "Swords to Plowshares").id not in h["castable"] and card_named(s, "Grizzly Bears", "p2").id not in h["castable"]
    assert ids("Command Tower", "Forest") <= set(h["playable_lands"])
    assert card_named(s, "Grizzly Bears", "p2").id not in hints(s.state, "p2", cards).get("castable", [])  # (Bob can't cast Alice's, nor she his)
    cast(s, "Perilous Myr")
    assert asked(s) == ["Artifact", "Creature"]  # (an artifact creature: choose one as you cast it)
    check(s)  # (the question is part of the saved game)
    answer(s, "Creature")
    settle(s)
    assert zone(s, "p1", "battlefield").count("Perilous Myr") == 1
    assert not castable_now(s, cards, "Grizzly Bears") and castable_now(s, cards, "Shimmer Myr")  # (the creature use is gone; the artifact one is not)
    refused(s, "Grizzly Bears")
    cast(s, "Shimmer Myr")
    assert asked(s) is None  # (only the artifact use is left: nothing to choose)
    settle(s)
    assert not castable_now(s, cards, "Bonesplitter")
    refused(s, "Bonesplitter")
    cast(s, "Courser of Kruphix")  # an enchantment creature: the creature use is gone, the enchantment one is not
    assert asked(s) is None
    settle(s)
    cast(s, "Gideon Jura")
    settle(s)
    assert {"Perilous Myr", "Shimmer Myr", "Courser of Kruphix", "Gideon Jura"} <= set(zone(s, "p1", "battlefield"))
    assert not any(castable_now(s, cards, n) for n in ("Grizzly Bears", "Bonesplitter", "Perilous Myr"))
    act(s, "p1", type="play_land", card_id=card_named(s, "Command Tower").id)  # the land use (and the land drop)
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=card_named(s, "Forest").id)  # 305.2: one land play
    check(s)
    to_turn(s, 2)  # Bob's turn: "during each of YOUR turns"
    mana(s, G=2)
    assert not castable_now(s, cards, "Ambush Viper")  # (a flash creature, with the mana: only "your turns" stops it)
    to_turn(s, 3)
    mana(s, G=4)
    assert castable_now(s, cards, "Ambush Viper") and castable_now(s, cards, "Bonesplitter")  # a new turn, new uses
    check(s)


def test_muldrotha_a_countered_spell_still_used_up_its_type(cards):
    """The use is spent when the spell is cast, not when it resolves: a countered artifact creature (cast as the creature) leaves the creature use
    gone and the artifact one free, and the card in the graveyard is a new object that may be cast again that way (Muldrotha ruling: "you have a
    chance to cast it")."""
    s = build(cards, [MULDROTHA, "Perilous Myr", "Grizzly Bears"], ["Counterspell"])
    put(s, MULDROTHA)
    grave(s, "Perilous Myr", "Grizzly Bears")
    counter = to_hand(s, "Counterspell", "p2")
    mana(s, G=8)
    mana(s, "p2", U=2)
    cast(s, "Perilous Myr")
    answer(s, "Creature")
    while s.state.rules.priority != "p2":
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[card_named(s, "Perilous Myr").id])
    settle(s)
    assert card_named(s, "Perilous Myr").zone == "p1:graveyard"
    assert not castable_now(s, cards, "Grizzly Bears") and castable_now(s, cards, "Perilous Myr")  # (as the artifact)
    cast(s, "Perilous Myr")
    assert asked(s) is None
    settle(s)
    assert card_named(s, "Perilous Myr").zone == "p1:battlefield"
    check(s)


# ---- a land's own kind: Titania, Hazezon -----------------------------------------------------------------------------------------------------
def test_titania_plays_forests_from_the_graveyard_using_the_land_drop(cards):
    """"You may play Forests from your graveyard." A Forest Island counts, an Island does not, Bob's graveyard is not Alice's; it uses the land play
    (305.2: Titania's ruling) and Titania's "Whenever a Forest you control enters" sees it."""
    s = build(cards, ["Titania, Nature's Force", "Breeding Pool", "Island"], ["Forest"])
    put(s, "Titania, Nature's Force")
    grave(s, "Breeding Pool", "Island", "Forest")
    grave(s, "Forest", pid="p2")
    h = hints(s.state, "p1", cards)["playable_lands"]
    assert card_named(s, "Breeding Pool").id in h and card_named(s, "Island").id not in h and card_named(s, "Forest", "p2").id not in h
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=card_named(s, "Island").id)
    act(s, "p1", type="play_land", card_id=card_named(s, "Breeding Pool").id)
    settle(s)
    assert card_named(s, "Breeding Pool").zone == "p1:battlefield" and zone(s, "p1", "battlefield").count("Elemental") == 1  # the 5/3 token
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=card_named(s, "Forest").id)  # (the land play is used)
    check(s)
    to_turn(s, 3)
    assert card_named(s, "Forest").id in hints(s.state, "p1", cards)["playable_lands"]
    check(s)


def test_hazezon_plays_desert_lands_but_no_other_land_from_the_graveyard(cards):
    s = build(cards, ["Hazezon, Shaper of Sand", "Sandstorm Verge", "Command Tower"])
    put(s, "Hazezon, Shaper of Sand")
    grave(s, "Sandstorm Verge", "Command Tower")
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=card_named(s, "Command Tower").id)
    act(s, "p1", type="play_land", card_id=card_named(s, "Sandstorm Verge").id)
    settle(s)
    assert card_named(s, "Sandstorm Verge").zone == "p1:battlefield" and zone(s, "p1", "battlefield").count("Sand Warrior") == 2
    check(s)


# ---- Zask: lands and one kind of spell ------------------------------------------------------------------------------------------------------
def test_zask_plays_lands_and_casts_insect_spells_from_the_graveyard(cards):
    s = build(cards, ["Zask, Skittering Swarmlord", "Dune Beetle", "Grizzly Bears", "Command Tower"])
    put(s, "Zask, Skittering Swarmlord")
    grave(s, "Dune Beetle", "Grizzly Bears", "Command Tower")
    mana(s, B=2, G=2)
    assert castable_now(s, cards, "Dune Beetle") and not castable_now(s, cards, "Grizzly Bears")
    refused(s, "Grizzly Bears")
    cast(s, "Dune Beetle")
    settle(s)
    assert card_named(s, "Dune Beetle").zone == "p1:battlefield"
    act(s, "p1", type="play_land", card_id=card_named(s, "Command Tower").id)
    check(s)


# ---- a quality of the spell: Lurrus, Leonardo, Arcade Gannon ---------------------------------------------------------------------------------
def test_lurrus_casts_one_permanent_spell_with_mana_value_two_or_less_a_turn(cards):
    """"Once during each of your turns, you may cast a permanent spell with mana value 2 or less from your graveyard." (Companion is a separate matter.)"""
    s = build(cards, ["Lurrus of the Dream-Den", "Perilous Myr", "Shimmer Myr", "Grizzly Bears", "Lightning Bolt"])
    put(s, "Lurrus of the Dream-Den")
    grave(s, "Perilous Myr", "Shimmer Myr", "Grizzly Bears", "Lightning Bolt")
    mana(s, G=8)
    assert [castable_now(s, cards, n) for n in ("Perilous Myr", "Shimmer Myr", "Grizzly Bears", "Lightning Bolt")] == [True, False, True, False]
    cast(s, "Perilous Myr")
    settle(s)
    assert not castable_now(s, cards, "Grizzly Bears")  # (once)
    refused(s, "Grizzly Bears")
    check(s)
    to_turn(s, 3)
    mana(s, G=2)
    assert castable_now(s, cards, "Grizzly Bears") and not castable_now(s, cards, "Shimmer Myr")
    check(s)


def test_arcade_gannon_casts_an_artifact_or_human_spell_up_to_the_quest_counters(cards):
    s = build(cards, ["Arcade Gannon", "Young Pyromancer", "Thorn of the Black Rose", "Arcane Signet", "Grizzly Bears"])
    put(s, "Arcade Gannon")
    grave(s, "Young Pyromancer", "Thorn of the Black Rose", "Arcane Signet", "Grizzly Bears")
    mana(s, R=3, G=3, B=3)
    names = ("Young Pyromancer", "Thorn of the Black Rose", "Arcane Signet", "Grizzly Bears")
    assert [castable_now(s, cards, n) for n in names] == [False] * 4  # (no quest counters: mana value 0 or less)
    act(s, "p1", type="set_counter", card_id=card_named(s, "Arcade Gannon").id, kind="quest", value=2)
    assert [castable_now(s, cards, n) for n in names] == [True, False, True, False]  # (a Human or an artifact, mana value 2 or less)
    cast(s, "Arcane Signet")
    settle(s)
    assert not castable_now(s, cards, "Young Pyromancer")  # (once)
    check(s)


def test_leonardo_casts_small_creatures_on_his_controllers_turn_and_they_enter_with_a_finality_counter(cards):
    """"During your turn, you may cast creature spells with power or toughness 1 or less from your graveyard. If you cast a spell this way, that
    creature enters with a finality counter on it." (122.1h: it is exiled instead of dying.)"""
    s = build(cards, ["Leonardo, Sewer Samurai", "Llanowar Elves", "Grizzly Bears", "Ambush Viper", "Lightning Bolt"])
    put(s, "Leonardo, Sewer Samurai")
    grave(s, "Llanowar Elves", "Grizzly Bears", "Ambush Viper")
    mana(s, G=6)
    assert castable_now(s, cards, "Llanowar Elves") and not castable_now(s, cards, "Grizzly Bears") and castable_now(s, cards, "Ambush Viper")  # (a 2/1: toughness 1)
    to_turn(s, 2)
    mana(s, G=2)
    assert not castable_now(s, cards, "Ambush Viper")  # "During your turn" (it has flash and the mana: only the permission's "your turn" stops it)
    to_turn(s, 3)
    mana(s, G=6)
    assert castable_now(s, cards, "Ambush Viper")
    cast(s, "Llanowar Elves")
    settle(s)
    elves = card_named(s, "Llanowar Elves")
    assert elves.zone == "p1:battlefield" and elves.counters.get("finality") == 1
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=[elves.id])
    settle(s)
    assert card_named(s, "Llanowar Elves").zone == "p1:exile"  # the finality counter
    check(s)


# ---- additional costs: Noctis, Maestros Ascendancy ------------------------------------------------------------------------------------------
def test_noctis_casts_artifacts_for_three_life_and_they_enter_with_a_finality_counter(cards):
    s = build(cards, ["Noctis, Prince of Lucis", "Bonesplitter", "Perilous Myr", "Grizzly Bears"])
    put(s, "Noctis, Prince of Lucis")
    grave(s, "Bonesplitter", "Perilous Myr", "Grizzly Bears")
    mana(s, G=4)
    assert castable_now(s, cards, "Bonesplitter") and castable_now(s, cards, "Perilous Myr") and not castable_now(s, cards, "Grizzly Bears")
    cast(s, "Bonesplitter")
    settle(s)
    assert s.state.players["p1"].life == 37 and card_named(s, "Bonesplitter").counters.get("finality") == 1  # (any number a turn: not "once")
    cast(s, "Perilous Myr")
    settle(s)
    assert s.state.players["p1"].life == 34 and card_named(s, "Perilous Myr").zone == "p1:battlefield"
    check(s)


def test_noctis_cannot_pay_life_it_does_not_have(cards):
    """119.4: a player can pay life only if their life total is at least that much."""
    s = build(cards, ["Noctis, Prince of Lucis", "Bonesplitter"])
    put(s, "Noctis, Prince of Lucis")
    grave(s, "Bonesplitter")
    mana(s, G=2)
    act(s, "p1", type="set_life", player="p1", value=2)
    assert not castable_now(s, cards, "Bonesplitter")
    refused(s, "Bonesplitter")
    assert card_named(s, "Bonesplitter").zone == "p1:graveyard" and s.state.players["p1"].life == 2
    check(s)


def test_festival_of_embers_casts_instants_and_sorceries_from_the_graveyard_on_your_turn_for_one_life_each(cards):
    s = build(cards, ["Festival of Embers", "Lightning Bolt", "Pyroclasm", "Grizzly Bears", "Opt"])
    put(s, "Festival of Embers")
    grave(s, "Lightning Bolt", "Pyroclasm", "Grizzly Bears", "Opt")
    mana(s, R=3, U=1)
    assert castable_now(s, cards, "Lightning Bolt") and castable_now(s, cards, "Pyroclasm") and not castable_now(s, cards, "Grizzly Bears")
    cast(s, "Lightning Bolt", targets=["p2"])
    settle(s)
    cast(s, "Pyroclasm")  # (any number of them: not "once")
    settle(s)
    assert s.state.players["p1"].life == 38 and s.state.players["p2"].life == 37
    assert card_named(s, "Lightning Bolt").zone == "p1:exile" and card_named(s, "Pyroclasm").zone == "p1:exile"  # (Festival's own "exile it instead")
    check(s)
    assert castable_now(s, cards, "Opt")
    to_turn(s, 2)
    mana(s, U=1)
    assert not castable_now(s, cards, "Opt")  # "During your turn" (an instant, with the mana, but it is Bob's turn)
    check(s)


def test_maestros_ascendancy_sacrifices_a_creature_to_cast_an_instant_once_a_turn_and_exiles_it(cards):
    s = build(cards, ["Maestros Ascendancy", "Lightning Bolt", "Murder", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    put(s, "Maestros Ascendancy")
    grave(s, "Lightning Bolt", "Murder")
    mana(s, R=3, B=3)
    assert not castable_now(s, cards, "Lightning Bolt")  # (no creature to sacrifice)
    put(s, "Grizzly Bears")
    elves = put(s, "Llanowar Elves")
    target = put(s, "Grizzly Bears", "p2")
    assert castable_now(s, cards, "Lightning Bolt")
    cast(s, "Lightning Bolt", targets=[target.id])
    d = s.state.rules.decision
    assert d is not None  # which creature to sacrifice (601.2b)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id == elves.id)])
    settle(s)
    assert card_named(s, "Llanowar Elves").zone == "p1:graveyard" and card_named(s, "Grizzly Bears").zone == "p1:battlefield"
    assert card_named(s, "Lightning Bolt").zone == "p1:exile" and card_named(s, "Grizzly Bears", "p2").zone == "p2:graveyard"
    assert not castable_now(s, cards, "Murder")  # (once during each of your turns: a creature is left to sacrifice)
    refused(s, "Murder", targets=[card_named(s, "Grizzly Bears").id])
    check(s)


# ---- riders: Edgar tapped, Serra Paragon / The Eighth Doctor gain an ability, with one use for a land or a spell ----------------------------
def test_edgar_casts_an_artifact_from_the_graveyard_and_it_enters_tapped(cards):
    s = build(cards, ["Edgar, Master Machinist", "Perilous Myr", "Shimmer Myr"])
    put(s, "Edgar, Master Machinist")
    grave(s, "Perilous Myr", "Shimmer Myr")
    mana(s, G=6)
    cast(s, "Perilous Myr")
    settle(s)
    assert card_named(s, "Perilous Myr").zone == "p1:battlefield" and card_named(s, "Perilous Myr").tapped
    refused(s, "Shimmer Myr")  # once
    check(s)


def test_serra_paragon_plays_a_land_or_casts_a_permanent_spell_once_and_it_is_exiled_when_it_dies(cards):
    """One use for either: a land or a permanent spell with mana value 3 or less; the permanent gains "When this permanent is put into a graveyard from
    the battlefield, exile it and you gain 2 life." (the land too)"""
    s = build(cards, ["Serra Paragon", "Grizzly Bears", "Forest", "Murder", "Gideon Jura"])
    put(s, "Serra Paragon")
    grave(s, "Grizzly Bears", "Gideon Jura")
    put_in(s, "Forest", "graveyard")
    mana(s, G=2, B=3)
    assert castable_now(s, cards, "Grizzly Bears") and not castable_now(s, cards, "Gideon Jura")  # (mana value 5)
    cast(s, "Grizzly Bears")
    settle(s)
    to_hand(s, "Murder")
    cast(s, "Murder", targets=[card_named(s, "Grizzly Bears").id])
    settle(s)
    assert card_named(s, "Grizzly Bears").zone == "p1:exile" and s.state.players["p1"].life == 42
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=card_named(s, "Forest").id)  # (the one use was the spell)
    check(s)
    to_turn(s, 3)
    forest = next(c for c in s.state.cards.values() if c.zone == "p1:graveyard" and c.name == "Forest")
    other = next(c for c in s.state.cards.values() if c.zone == "p1:library" and c.name == "Forest")
    act(s, "p1", type="move", card_ids=[other.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="play_land", card_id=forest.id)  # the land too: "If you do, it gains …"
    assert any("exile it and you gain 2 life" in ab.text for ab in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[forest.id]).abilities)
    assert not any("gain 2 life" in ab.text for ab in Plan(s.state, "p1", s.cards, None).ch(other).abilities)  # (only that land)
    check(s)


def test_the_eighth_doctor_plays_a_historic_land_or_casts_a_historic_permanent_and_it_is_exiled_instead_of_leaving(cards):
    s = build(cards, ["The Eighth Doctor", "Honest Rutstein", "Gaea's Cradle", "Grizzly Bears", "Murder"])
    put(s, "The Eighth Doctor")
    grave(s, "Honest Rutstein", "Gaea's Cradle", "Grizzly Bears")
    put_in(s, "Forest", "graveyard")
    mana(s, B=4, G=4)
    h = hints(s.state, "p1", cards)
    assert card_named(s, "Honest Rutstein").id in h["castable"] and card_named(s, "Grizzly Bears").id not in h["castable"]
    assert card_named(s, "Gaea's Cradle").id in h["playable_lands"] and next(c.id for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:graveyard") not in h["playable_lands"]
    cast(s, "Honest Rutstein")
    settle(s)
    assert not castable_now(s, cards, "Honest Rutstein") and card_named(s, "Gaea's Cradle").id not in hints(s.state, "p1", cards)["playable_lands"]  # (one use)
    to_hand(s, "Murder")
    cast(s, "Murder", targets=[card_named(s, "Honest Rutstein").id])
    settle(s)
    assert card_named(s, "Honest Rutstein").zone == "p1:exile"
    check(s)


# ---- Chainer: a permission for this turn ------------------------------------------------------------------------------------------------------
def test_chainer_discards_for_one_creature_spell_from_the_graveyard_this_turn(cards):
    """"Discard a card: You may cast a creature spell from your graveyard this turn. Activate only once each turn." One creature spell, of that
    kind, this turn (the Chainer ruling: it is a permission, not a choice made as the ability resolves); an unused one ends with the turn, and a
    creature cast from the graveyard has haste until your next turn (the second ability)."""
    s = build(cards, ["Chainer, Nightmare Adept", "Grizzly Bears", "Llanowar Elves", "Bonesplitter", "Lightning Bolt"])
    chainer = put(s, "Chainer, Nightmare Adept")
    grave(s, "Grizzly Bears", "Llanowar Elves", "Bonesplitter")
    to_hand(s, "Lightning Bolt")
    mana(s, G=6)
    assert not castable_now(s, cards, "Grizzly Bears")  # (nothing yet)
    act(s, "p1", type="activate_ability", card_id=chainer.id, ability=0)
    d = s.state.rules.decision
    if d is not None and d.kind != "choose_one":
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id == card_named(s, "Lightning Bolt").id)])
    settle(s)
    assert card_named(s, "Lightning Bolt").zone == "p1:graveyard"
    assert castable_now(s, cards, "Grizzly Bears") and castable_now(s, cards, "Llanowar Elves") and not castable_now(s, cards, "Bonesplitter")
    cast(s, "Grizzly Bears")
    settle(s)
    assert card_named(s, "Grizzly Bears").zone == "p1:battlefield" and not castable_now(s, cards, "Llanowar Elves")  # (one creature spell)
    assert "haste" in Plan(s.state, "p1", s.cards, None).ch(card_named(s, "Grizzly Bears")).keywords  # (not cast from the hand)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=chainer.id, ability=0)  # (once each turn)
    assert card_named(s, "Grizzly Bears").counters == {} and card_named(s, "Chainer, Nightmare Adept").zone == "p1:battlefield"
    check(s)
    to_turn(s, 3)  # an unused permission ends with the turn (611.2a, 514.2): activate again, cast nothing
    mana(s, G=2)
    to_hand(s, "Lightning Bolt")
    act(s, "p1", type="activate_ability", card_id=chainer.id, ability=0)
    d = s.state.rules.decision
    if d is not None:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id == card_named(s, "Lightning Bolt").id)])
    settle(s)
    assert castable_now(s, cards, "Llanowar Elves")
    to_turn(s, 5)
    mana(s, G=2)
    assert not castable_now(s, cards, "Llanowar Elves")
    check(s)


def test_liliana_untouched_by_death_lets_you_cast_any_number_of_zombie_spells_this_turn(cards):
    """"−3: You may cast Zombie spells from your graveyard this turn." Any number (spells, not "a spell"), only Zombies, only this turn."""
    s = build(cards, ["Liliana, Untouched by Death", "Dregscape Zombie", "Twisted Abomination", "Grizzly Bears"])
    lili = put(s, "Liliana, Untouched by Death")
    act(s, "p1", type="set_counter", card_id=lili.id, kind="loyalty", value=4)
    grave(s, "Dregscape Zombie", "Twisted Abomination", "Grizzly Bears")
    mana(s, B=8)
    assert not castable_now(s, cards, "Dregscape Zombie")
    act(s, "p1", type="activate_ability", card_id=lili.id, ability=2)
    settle(s)
    assert castable_now(s, cards, "Dregscape Zombie") and castable_now(s, cards, "Twisted Abomination") and not castable_now(s, cards, "Grizzly Bears")
    cast(s, "Dregscape Zombie")
    settle(s)
    assert castable_now(s, cards, "Twisted Abomination")  # (not used up by the first)
    check(s)
    to_turn(s, 3)
    mana(s, B=8)
    assert not castable_now(s, cards, "Twisted Abomination")
    check(s)
