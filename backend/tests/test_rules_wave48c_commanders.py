"""Wave 48C: commanders with one blocking line (CR 2026-09-25), real Oracle text (tests/fixtures/wave48c_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 106.4, 608.2c: "Destroy target artifact if its mana value is equal to the amount of unspent mana you have." (Glissa Sunseeker): the mana in the pool as the ability resolves.
* 406.3, 701.26a: "exile the top card of your library face down. You may look at and play that card this turn." (Headliner Scarlett): only its owner may look at it.
* 607.2a, 608.2g: "you may cast a card exiled with Krang & Shredder without paying its mana cost" (a card cast from exile is a spell).
* 701.26a: "untap each creature you control, then tap any number of creatures you control" (Augusta, Dean of Order: only an untapped creature can be tapped).
* 611.2a, 613.1d, 613.4c: "target creature you control gets +3/+1 and becomes a Dinosaur in addition to its other types" until end of turn (Stegron, Thran Forge).
* 702.189a, 611.2c: "each creature you control with a counter on it gains firebending 2 until end of turn" (Iroh, Dragon of the West).
* 707.12, 608.2g: "exile up to one target legendary or Rat card from your graveyard and copy it. You may cast the copy." (Nashi, Moon's Legacy).
* 602.2, 118.3: "Tap another untapped creature you control with flying: ~ gains protection from the color of your choice" (Radiant, Serra Archangel).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.visibility import SPECTATOR
from app.rules import coverage
from app.rules.mana_units import visible_pool
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, ask, attack, next_turn, settle, stops, to_phase
from tests.wave9c_kit import build, card_named, cast, check, mana, pt, put, to_hand, zone_of
from tests.wave44c_kit import ch, on_top

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave48c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w48c", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
GLISSA, SCARLETT, KRANG, PLARGG = "Glissa Sunseeker", "Headliner Scarlett", "Krang & Shredder", "Plargg, Dean of Chaos // Augusta, Dean of Order"
STEGRON, RADIANT, FORGE, IROH = "Stegron the Dinosaur Man", "Radiant, Serra Archangel", "Thran Forge", "Iroh, Dragon of the West"
NASHI = "Nashi, Moon's Legacy"
NAMES = [GLISSA, SCARLETT, KRANG, PLARGG, STEGRON, RADIANT, IROH, NASHI]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", [*NAMES, FORGE])
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


# ---- 106.4: Glissa Sunseeker --------------------------------------------------------------------------------------------------------------------
def test_glissa_destroys_an_artifact_whose_mana_value_is_the_unspent_mana(cards):
    s = build(cards, [GLISSA, "Sol Ring", "Arcane Signet"], [])
    glissa = put(s, GLISSA)
    next_turn(s)
    ring, signet = put(s, "Sol Ring"), put(s, "Arcane Signet")
    mana(s, R=1)
    activate(s, "p1", glissa, "Destroy", targets=[signet.id])  # mana value 2, one mana unspent: nothing happens
    settle(s)
    assert zone_of(s, "Arcane Signet") == "p1:battlefield" and s.state.cards[glissa.id].tapped
    act(s, "p1", type="tap", card_ids=[glissa.id], tapped=False)
    activate(s, "p1", glissa, "Destroy", targets=[ring.id])  # mana value 1, one mana unspent
    settle(s)
    assert zone_of(s, "Sol Ring") == "p1:graveyard" and zone_of(s, "Arcane Signet") == "p1:battlefield"
    check(s)


# ---- 406.3: Headliner Scarlett ------------------------------------------------------------------------------------------------------------------
def test_headliner_scarlett_exiles_the_top_card_face_down_and_its_owner_may_play_it_this_turn(cards):
    s = build(cards, [SCARLETT, "Lightning Bolt"], [], forests=30, islands=30)
    put(s, SCARLETT)
    bolt = on_top(s, "Lightning Bolt")
    to_phase(s, "main1", turn=3)
    settle(s)
    exiled = s.state.cards[bolt.id]
    assert exiled.zone == "p1:exile" and exiled.face_down
    assert s.view("p1")["cards"][bolt.id].get("name") == "Lightning Bolt"  # "You may look at": its owner does
    for viewer in ("p2", SPECTATOR):  # nobody else learns what it is (406.3a)
        seen = json.dumps(s.view(viewer))
        assert "Lightning Bolt" not in seen and bolt.card_id not in seen
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])  # "and play that card this turn"
    settle(s)
    assert zone_of(s, "Lightning Bolt") == "p1:graveyard" and s.state.players["p2"].life == 37
    check(s)


def test_headliner_scarlett_card_can_no_longer_be_played_on_a_later_turn(cards):
    s = build(cards, [SCARLETT, "Lightning Bolt"], [], forests=30, islands=30)
    put(s, SCARLETT)
    bolt = on_top(s, "Lightning Bolt")
    to_phase(s, "main1", turn=3)  # not cast: the turn ends and the permission with it
    to_phase(s, "main1", turn=5)
    mana(s, R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    assert s.state.players["p2"].life == 40
    check(s)


# ---- 607.2a, 608.2g: Krang & Shredder -----------------------------------------------------------------------------------------------------------
def krang_table(cards):
    s = build(cards, [KRANG, "Grizzly Bears"], ["Grizzly Bears", "Lightning Bolt"], forests=30, islands=30)
    on_top(s, "Lightning Bolt", "p2")
    on_top(s, "Grizzly Bears", "p2")
    to_hand(s, KRANG)
    mana(s, U=2, G=4)
    cast(s, KRANG)
    return s


def test_krang_and_shredder_casts_the_exiled_card_free_at_the_end_step_after_a_permanent_left(cards):
    s = krang_table(cards)
    exiled = card_named(s, "Grizzly Bears", "p2")
    assert exiled.zone == "p2:exile"  # "exiles cards from the top of their library until they exile a nonland card"
    mine = put(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[mine.id], to={"player": "p1", "zone": "graveyard"})  # a permanent left the battlefield under Alice's control
    to_phase(s, "end")
    settle(s)  # the optional cast is answered yes
    bears = s.state.cards[exiled.id]
    assert bears.zone == "p1:battlefield" and bears.owner == "p2" and bears.controller == "p1"
    check(s)


def test_krang_and_shredder_does_not_trigger_when_no_permanent_left_the_battlefield(cards):
    s = krang_table(cards)
    exiled = card_named(s, "Grizzly Bears", "p2")
    to_phase(s, "main1", turn=3)  # through Alice's end step
    settle(s)
    assert s.state.cards[exiled.id].zone == "p2:exile"  # an intervening "if": nothing to cast
    check(s)


# ---- 701.26a: Augusta, Dean of Order ------------------------------------------------------------------------------------------------------------
def augusta_table(cards):
    s = build(cards, [PLARGG, "Grizzly Bears", "Llanowar Elves"], [], forests=30, islands=30)
    augusta = put(s, PLARGG)
    act(s, "p1", type="set_face", card_id=augusta.id, face=1)
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    next_turn(s)
    attack(s, bears)
    return s, bears, elves


def test_augusta_untaps_everything_when_you_attack_then_taps_the_creatures_you_choose(cards):
    s, bears, elves = augusta_table(cards)
    d = ask(s)
    assert d.player == "p1" and d.min_choices == 0 and not s.state.cards[bears.id].tapped  # "untap each creature you control" came first
    assert {o.card_id for o in d.options} == {s.state.cards[c.id].id for c in (bears, elves)} | {card_named(s, PLARGG).id}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.card_id == elves.id])
    settle(s)
    assert s.state.cards[elves.id].tapped and not s.state.cards[bears.id].tapped
    assert pt(s, "Llanowar Elves") == (2, 1) and pt(s, "Grizzly Bears") == (2, 3)  # tapped +1/+0, untapped +0/+1
    check(s)


def test_augusta_may_tap_none_of_them(cards):
    s, bears, elves = augusta_table(cards)
    d = ask(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert not any(s.state.cards[c.id].tapped for c in (bears, elves))
    check(s)


# ---- 611.2a, 613.1d, 613.4c: Stegron the Dinosaur Man, Thran Forge -----------------------------------------------------------------------------
def test_stegron_discarded_gives_a_creature_plus_three_one_and_the_dinosaur_type_until_end_of_turn(cards):
    s = build(cards, [STEGRON, "Grizzly Bears"], [], forests=30, islands=30)
    bears = put(s, "Grizzly Bears")
    stegron = to_hand(s, STEGRON)
    mana(s, R=2)
    activate(s, "p1", stegron, "Discard this card", targets=[bears.id])  # from the hand
    settle(s)
    assert zone_of(s, STEGRON) == "p1:graveyard"
    assert pt(s, "Grizzly Bears") == (5, 3) and {"Bear", "Dinosaur"} <= ch(s, bears).subtypes  # "in addition to its other types"
    to_phase(s, "main1", turn=3)
    assert pt(s, "Grizzly Bears") == (2, 2) and "Dinosaur" not in ch(s, bears).subtypes  # until end of turn
    check(s)


def test_thran_forge_makes_a_nonartifact_creature_an_artifact_until_end_of_turn(cards):
    s = build(cards, [FORGE, "Grizzly Bears"], [], forests=30, islands=30)
    forge, bears = put(s, FORGE), put(s, "Grizzly Bears")
    mana(s, R=4)
    activate(s, "p1", forge, "Until end of turn", targets=[bears.id])
    settle(s)
    assert pt(s, "Grizzly Bears") == (3, 2) and {"Artifact", "Creature"} <= ch(s, bears).types
    with pytest.raises(ActionError):  # "target nonartifact creature": it is an artifact now
        activate(s, "p1", forge, "Until end of turn", targets=[bears.id])
    to_phase(s, "main1", turn=3)
    assert pt(s, "Grizzly Bears") == (2, 2) and "Artifact" not in ch(s, bears).types
    check(s)


# ---- 602.2, 118.3: Radiant, Serra Archangel -----------------------------------------------------------------------------------------------------
def test_radiant_taps_another_untapped_flyer_to_gain_protection_from_a_color(cards):
    s = build(cards, [RADIANT, "Grizzly Bears", "Mulldrifter"], [], forests=30, islands=30)
    radiant = put(s, RADIANT)
    bears, flyer = put(s, "Grizzly Bears"), put(s, "Mulldrifter")
    with pytest.raises(ActionError):  # Grizzly Bears has no flying: it can't pay
        activate(s, "p1", radiant, "Tap another untapped creature", cost_choices=[{"component": 0, "cards": [bears.id]}])
    activate(s, "p1", radiant, "Tap another untapped creature")
    settle(s)
    assert s.state.cards[flyer.id].tapped and not s.state.cards[bears.id].tapped and not s.state.cards[radiant.id].tapped
    assert "protection" in ch(s, radiant).keywords
    with pytest.raises(ActionError):  # no other untapped creature with flying is left to tap
        activate(s, "p1", radiant, "Tap another untapped creature")
    check(s)


# ---- 702.189a, 611.2c: Iroh, Dragon of the West ----------------------------------------------------------------------------------------------------
def iroh_table(cards):
    s = build(cards, [IROH, "Grizzly Bears", "Llanowar Elves"], [], forests=30, islands=30)
    put(s, IROH)
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=1)
    next_turn(s)
    stops(s)  # both players get priority at every step: the combat can be looked at in the middle
    return s, bears, elves


def pass_until_mana(s, limit=6):
    """Pass priority one step at a time until the attack trigger has added mana (it is kept until end of combat, 702.189a)."""
    for _ in range(limit):
        if visible_pool(s.state, "p1"):
            return
        act(s, s.state.rules.priority, type="pass_priority")


def test_iroh_gives_firebending_to_a_creature_with_a_counter_on_it(cards):
    s, bears, _ = iroh_table(cards)
    attack(s, bears)
    pass_until_mana(s)
    assert visible_pool(s.state, "p1") == {"R": 2}  # firebending 2: "add {R}{R}" as it attacks
    check(s)


def test_iroh_gives_nothing_to_a_creature_without_a_counter(cards):
    s, _, elves = iroh_table(cards)
    attack(s, elves)
    pass_until_mana(s)
    assert not visible_pool(s.state, "p1")
    check(s)


# ---- 707.12: Nashi, Moon's Legacy ---------------------------------------------------------------------------------------------------------------
def nashi_table(cards):
    s = build(cards, [NASHI, GLISSA, "Grizzly Bears"], [], forests=30, islands=30)
    nashi = put(s, NASHI)
    dead = [card_named(s, GLISSA), card_named(s, "Grizzly Bears")]
    act(s, "p1", type="move", card_ids=[c.id for c in dead], to={"player": "p1", "zone": "graveyard"})
    next_turn(s)
    stops(s)
    attack(s, nashi)
    return s, dead[0]


def test_nashi_copies_a_legendary_card_from_the_graveyard_and_casts_the_copy(cards):
    s, glissa = nashi_table(cards)
    d = ask(s)
    assert sorted(s.state.cards[o.card_id].name for o in d.options if o.card_id) == [GLISSA]  # Grizzly Bears is neither legendary nor a Rat
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.card_id == glissa.id])
    mana(s, G=4)
    settle(s)
    assert s.state.cards[glissa.id].zone == "p1:exile"
    copies = [c for c in s.state.cards.values() if c.name == GLISSA and c.zone == "p1:battlefield"]
    assert len(copies) == 1 and copies[0].is_token  # "A copy of a permanent spell becomes a token"
    check(s)


def test_nashi_may_choose_no_card(cards):
    s, glissa = nashi_table(cards)
    d = ask(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert s.state.cards[glissa.id].zone == "p1:graveyard"
    check(s)
