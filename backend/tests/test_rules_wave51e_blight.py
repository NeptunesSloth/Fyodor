"""Wave 51E: blight as an instruction, counters that stay with a card, "if it isn't your main phase" (CR 2026-09-25), real Oracle text
(tests/fixtures/wave51e_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 701.68a / 701.68b: "blight N" is "put N -1/-1 counters on a creature you control" - Sinister Gnarlbark's "draw a card and blight 1", High Perfect
  Morcant's "each opponent blights 1" (each opponent chooses one creature of theirs, all the counters on it - the ruling).
* 601.2b / 702.? (additional costs): "As an additional cost to cast this spell, you may blight 1." - Cinder Strike (4 damage instead), Pyrrhic Strike
  ("If this spell's additional cost was paid, choose both instead.").
* 122.2: Skullbriar's "Counters remain on Skullbriar as it moves to any zone other than a player's hand or library." (the rulings: not put on again).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import ask, settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave51e_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w51e", number=f"E{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
SKULL = "Skullbriar, the Walking Grave"
MORCANT = "High Perfect Morcant"


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def counters(s, c):
    return dict(s.state.cards[c.id].counters)


def cast(s, name, **kw):
    act(s, "p1", type="cast_spell", card_id=card_named(s, name).id, **kw)


def choose(s, *ids):
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards", d
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))


# --- High Perfect Morcant: "each opponent blights 1" ---------------------------------------------------------------------------------------


def test_morcant_each_opponent_blights_one_creature_of_their_choice(cards):
    s = build(cards, [MORCANT], ["Grizzly Bears", "Young Wolf"])
    bears, wolf = put(s, "Grizzly Bears", "p2"), put(s, "Young Wolf", "p2")
    to_hand(s, MORCANT)
    mana(s, B=1, G=1, C=2)
    cast(s, MORCANT)
    d = ask(s)
    assert d.player == "p2" and {o.id for o in d.options} == {bears.id, wolf.id}  # 701.68a: Bob chooses, among the creatures he controls
    choose(s, bears.id)
    settle(s)
    assert counters(s, bears) == {"-1/-1": 1} and pt(s, "Grizzly Bears", "p2") == (1, 1) and counters(s, wolf) == {}
    check(s)


def test_morcant_with_no_creature_to_blight_nothing_happens(cards):
    s = build(cards, [MORCANT], [])
    to_hand(s, MORCANT)
    mana(s, B=1, G=1, C=2)
    cast(s, MORCANT)
    settle(s)  # 701.68b: an opponent who controls no creatures can't blight
    assert counters(s, card_named(s, MORCANT)) == {} and s.state.rules.decision is None
    check(s)


# --- Sinister Gnarlbark: "draw a card and blight 1" ----------------------------------------------------------------------------------------


def test_gnarlbark_draws_and_puts_a_minus_counter_on_a_creature_you_control(cards):
    s = build(cards, ["Sinister Gnarlbark", "Grizzly Bears"], [])
    bark, bears = put(s, "Sinister Gnarlbark"), put(s, "Grizzly Bears")
    stops(s)
    hand = len(s.state.zones["p1:hand"])
    to_phase(s, "end")
    d = ask(s)
    assert d.player == "p1" and {o.id for o in d.options} == {bark.id, bears.id}
    choose(s, bears.id)
    settle(s)
    assert counters(s, bears) == {"-1/-1": 1} and len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


# --- Cinder Strike / Pyrrhic Strike: "you may blight N" as an additional cost ------------------------------------------------------------------


def test_cinder_strike_without_blight_deals_two(cards):
    s = build(cards, ["Cinder Strike", "Grizzly Bears"], ["Grizzly Bears", "Young Wolf"])
    big = put(s, "Grizzly Bears", "p2")
    act(s, "p2", type="counter", card_ids=[big.id], kind="+1/+1", delta=1)  # a 3/3
    to_hand(s, "Cinder Strike")
    mana(s, R=1)
    cast(s, "Cinder Strike", targets=[big.id])
    settle(s)
    assert s.state.cards[big.id].zone == "p2:battlefield" and s.state.cards[big.id].damage == 2  # not paid: 2 damage
    check(s)


def test_cinder_strike_with_blight_kills_the_bigger_creature(cards):
    s = build(cards, ["Cinder Strike", "Grizzly Bears"], ["Grizzly Bears"])
    mine = put(s, "Grizzly Bears")
    big = put(s, "Grizzly Bears", "p2")
    act(s, "p2", type="counter", card_ids=[big.id], kind="+1/+1", delta=2)  # a 4/4
    to_hand(s, "Cinder Strike")
    mana(s, R=1)
    strike = card_named(s, "Cinder Strike")
    cast(s, "Cinder Strike", targets=[big.id], optional_costs=[f"{strike.id}:blight"])
    settle(s)
    assert counters(s, mine) == {"-1/-1": 1} and s.state.cards[big.id].zone == "p2:graveyard"  # paid: 4 damage instead
    check(s)


def test_pyrrhic_strike_chooses_both_modes_only_with_the_blight(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Pyrrhic Strike", "Grizzly Bears"], ["Sol Ring", "Phantasmal Forces"])
    mine = put(s, "Grizzly Bears")
    ring, finks = put(s, "Sol Ring", "p2"), put(s, "Phantasmal Forces", "p2")
    to_hand(s, "Pyrrhic Strike")
    mana(s, W=1, C=2)
    strike = card_named(s, "Pyrrhic Strike")
    with pytest.raises(ActionError, match="Choose 1 mode"):
        act(s, "p1", type="cast_spell", card_id=strike.id, modes=[0, 1], targets=[ring.id, finks.id])  # not paid: one mode
    act(s, "p1", type="cast_spell", card_id=strike.id, modes=[0, 1], targets=[ring.id, finks.id], optional_costs=[f"{strike.id}:blight"])
    settle(s)
    assert s.state.cards[mine.id].zone == "p1:graveyard"  # blight 2: both counters on the one 2/2 creature (701.68a), which dies
    assert s.state.cards[ring.id].zone == "p2:graveyard" and s.state.cards[finks.id].zone == "p2:graveyard"
    check(s)


# --- Dose of Dawnglow: "Then if it isn't your main phase, blight 2." ----------------------------------------------------------------------


def test_dose_of_dawnglow_blights_only_outside_your_main_phase(cards):
    s = build(cards, ["Dose of Dawnglow", "Young Wolf", "Albino Troll"], [])
    wolf = card_named(s, "Young Wolf")
    act(s, "p1", type="move", card_ids=[wolf.id], to={"player": "p1", "zone": "graveyard"})
    troll = put(s, "Albino Troll")
    to_hand(s, "Dose of Dawnglow")
    mana(s, B=1, C=4)
    cast(s, "Dose of Dawnglow", targets=[wolf.id])
    settle(s)  # Alice's own main phase: no blight
    assert counters(s, troll) == {} and s.state.cards[wolf.id].zone == "p1:battlefield"
    check(s)


def test_dose_of_dawnglow_blights_two_in_the_end_step(cards):
    s = build(cards, ["Dose of Dawnglow", "Young Wolf", "Albino Troll"], [])
    wolf = card_named(s, "Young Wolf")
    act(s, "p1", type="move", card_ids=[wolf.id], to={"player": "p1", "zone": "graveyard"})
    troll = put(s, "Albino Troll")
    to_hand(s, "Dose of Dawnglow")
    stops(s)
    to_phase(s, "end", turn=1)
    mana(s, B=1, C=4)
    cast(s, "Dose of Dawnglow", targets=[wolf.id])
    d = ask(s)
    assert d.player == "p1" and {o.id for o in d.options} == {troll.id, wolf.id}  # not Alice's main phase: blight 2 on a creature of hers
    choose(s, troll.id)
    settle(s)
    assert counters(s, troll) == {"-1/-1": 2} and s.state.cards[wolf.id].zone == "p1:battlefield"
    check(s)


# --- Skullbriar: "Counters remain on Skullbriar as it moves to any zone other than a player's hand or library." -----------------------------


def test_skullbriar_keeps_its_counters_in_the_graveyard_and_on_coming_back(cards):
    s = build(cards, [SKULL, "Lightning Bolt", "Dose of Dawnglow"], [])
    sk = put(s, SKULL)
    act(s, "p1", type="counter", card_ids=[sk.id], kind="+1/+1", delta=2)
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=[sk.id])
    settle(s)
    assert s.state.cards[sk.id].zone == "p1:graveyard" and counters(s, sk) == {"+1/+1": 2}  # 122.2 doesn't clear them: the ability says so
    to_hand(s, "Dose of Dawnglow")
    mana(s, B=1, C=4)
    cast(s, "Dose of Dawnglow", targets=[sk.id])
    settle(s)
    assert s.state.cards[sk.id].zone == "p1:battlefield" and counters(s, sk) == {"+1/+1": 2} and pt(s, SKULL) == (3, 3)  # back with them
    check(s)


def test_skullbriar_loses_its_counters_in_a_hand(cards):
    s = build(cards, [SKULL, "Capsize"], [])
    sk = put(s, SKULL)
    act(s, "p1", type="counter", card_ids=[sk.id], kind="+1/+1", delta=2)
    to_hand(s, "Capsize")
    mana(s, U=2, C=1)
    cast(s, "Capsize", targets=[sk.id])
    settle(s, answer="no")
    assert s.state.cards[sk.id].zone == "p1:hand" and counters(s, sk) == {}  # a player's hand is the exception
    check(s)


def test_another_creature_keeps_nothing_when_it_dies(cards):
    s = build(cards, ["Grizzly Bears", "Lightning Bolt"], [])
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=1)
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard" and counters(s, bears) == {}
    check(s)
