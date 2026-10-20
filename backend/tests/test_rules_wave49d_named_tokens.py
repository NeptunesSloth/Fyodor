"""Wave 49D: tokens named for a card keep the card's mana cost (CR 2026-09-25), real Oracle text
(tests/fixtures/wave49d_named_tokens_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 111.3 / 707.2: "Create a Tarmogoyf token." (Disa the Restless, Tarmogoyf Nest) and "create a Gingerbrute token." (Ginger, Queen of Sweets) make a token that is a
  copy of the card of that name (the rulings): the token has the card's mana cost {1}{G} / {1}, so its mana value is 2 / 1, and a copy of that token has it too.
* Ral and the Implicit Maze's Spellgorger Weird token {2}{R} is the same case.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.rules_state import snapshot
from app.rules import coverage, triggers
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import (
    activate,
    ask,
    attach,
    attack,
    next_turn,
    priority_to,
    settle,
    stops,
    to_phase,
)
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave49d_named_tokens_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w49d", number=f"N{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Disa the Restless", "Tarmogoyf Nest", "Ginger, Queen of Sweets", "Ral and the Implicit Maze"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def tokens(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.controller == pid and c.zone == f"{pid}:battlefield"]


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(c)


def test_the_cards_are_full(cards):
    for name in FULL:
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_disa_makes_a_tarmogoyf_token_with_the_cards_mana_cost(cards):
    s = build(cards, ["Disa the Restless", "Grizzly Bears", "Lightning Bolt"], [])
    stops(s)
    disa, bears, bolt = (put(s, n) for n in ("Disa the Restless", "Grizzly Bears", "Lightning Bolt"))
    act(s, "p1", type="move", card_ids=[bolt.id], to={"player": "p1", "zone": "graveyard"})
    next_turn(s)
    attack(s, bears)
    to_phase(s, "combat_damage")
    settle(s)
    (goyf,) = tokens(s, "Tarmogoyf")
    c = ch(s, goyf)
    assert (c.mana_cost, c.mana_value, c.colors, c.subtypes) == ("{1}{G}", 2.0, frozenset({"G"}), frozenset({"Lhurgoyf"}))
    assert pt(s, "Tarmogoyf") == (1, 2)  # its P/T is the card's characteristic-defining ability (the Bolt's one type)
    snap = snapshot(s.state, goyf.id)  # 608.2h: as it last existed, it still has the mana cost
    assert snap.token_mana_cost == "{1}{G}" and triggers._lki_characteristics(Plan(s.state, "p1", s.cards, None), snap).mana_value == 2.0
    check(s)


def test_disa_makes_nothing_when_no_creature_connects(cards):
    s = build(cards, ["Disa the Restless", "Grizzly Bears"], ["Grizzly Bears"])
    stops(s)
    put(s, "Disa the Restless")
    bears = put(s, "Grizzly Bears")
    blocker = put(s, "Grizzly Bears", "p2")
    next_turn(s)
    attack(s, bears)
    assert ask(s).kind == "declare_blockers"
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": bears.id}])
    to_phase(s, "main2")
    settle(s)
    assert not tokens(s, "Tarmogoyf")
    check(s)


def test_tarmogoyf_nest_gives_its_land_the_ability(cards):
    s = build(cards, ["Tarmogoyf Nest"], [])
    land = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[land.id], to={"player": "p1", "zone": "battlefield"})
    nest = put(s, "Tarmogoyf Nest")
    mana(s, G=1, C=1)
    with pytest.raises(StopIteration):  # (the helper finds no such ability) a land without the Nest has no such ability
        activate(s, "p1", land, "Tarmogoyf")
    attach(s, nest, land)
    activate(s, "p1", land, "Tarmogoyf")
    settle(s)
    (goyf,) = tokens(s, "Tarmogoyf")
    assert ch(s, goyf).mana_value == 2.0 and s.state.cards[land.id].tapped
    check(s)


def test_a_copy_of_the_token_keeps_the_mana_cost(cards):
    s = build(cards, ["Tarmogoyf Nest", "Clone"], [])
    land = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[land.id], to={"player": "p1", "zone": "battlefield"})
    nest = put(s, "Tarmogoyf Nest")
    mana(s, G=1, C=1)
    attach(s, nest, land)
    activate(s, "p1", land, "Tarmogoyf")
    settle(s)
    (goyf,) = tokens(s, "Tarmogoyf")
    to_hand(s, "Clone")
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Clone").id)
    settle(s, answer=goyf.id)
    clone = s.state.cards[card_named(s, "Clone").id]
    assert ch(s, clone).name == "Tarmogoyf"
    assert ch(s, clone).mana_cost == "{1}{G}" and ch(s, goyf).mana_cost == "{1}{G}"
    check(s)


def test_a_token_copy_of_the_token_keeps_the_mana_cost(cards):
    s = build(cards, ["Tarmogoyf Nest", "Cackling Counterpart"], [])
    land = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[land.id], to={"player": "p1", "zone": "battlefield"})
    attach(s, put(s, "Tarmogoyf Nest"), land)
    mana(s, G=1, C=1)
    activate(s, "p1", land, "Tarmogoyf")
    settle(s)
    (goyf,) = tokens(s, "Tarmogoyf")
    to_hand(s, "Cackling Counterpart")
    mana(s, U=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Cackling Counterpart").id, targets=[goyf.id])
    settle(s)
    assert [ch(s, t).mana_cost for t in tokens(s, "Tarmogoyf")] == ["{1}{G}"] * 2
    check(s)


def test_ginger_makes_a_gingerbrute_at_each_upkeep_while_she_is_monarch(cards):
    s = build(cards, ["Ginger, Queen of Sweets"], [], forests=40)
    stops(s)
    ginger = to_hand(s, "Ginger, Queen of Sweets")
    mana(s, C=6)
    act(s, "p1", type="cast_spell", card_id=ginger.id)
    settle(s)
    assert s.state.table.monarch == "p1"
    to_phase(s, "upkeep", turn=s.state.turn.number + 1)  # Bob's upkeep: "each upkeep"
    settle(s)
    (brute,) = tokens(s, "Gingerbrute")
    c = ch(s, brute)
    assert (c.mana_cost, c.mana_value, str(c.power), str(c.toughness)) == ("{1}", 1.0, "1", "1") and c.subtypes == {"Food", "Golem"}
    mana(s, "p1", C=3)
    priority_to(s, "p1")
    assert not any("cant_be_blocked" in r for r in ch(s, brute).imposed)
    activate(s, "p1", brute, "can't be blocked")  # its card's ability: this turn only creatures with haste can block it
    settle(s)
    assert any("cant_be_blocked" in r for r in ch(s, brute).imposed)
    priority_to(s, "p1")
    activate(s, "p1", brute, "Sacrifice")
    settle(s)
    assert not tokens(s, "Gingerbrute") and life(s) == 43
    check(s)


def test_ginger_makes_nothing_without_the_monarchy(cards):
    s = build(cards, ["Ginger, Queen of Sweets"], [], forests=40)
    stops(s)
    put(s, "Ginger, Queen of Sweets")  # moved by hand: no "enters" trigger, nobody is the monarch
    assert s.state.table.monarch is None
    to_phase(s, "upkeep", turn=s.state.turn.number + 1)
    settle(s)
    assert not tokens(s, "Gingerbrute")
    check(s)


def test_ral_makes_a_spellgorger_weird(cards):
    s = build(cards, ["Ral and the Implicit Maze", "Lightning Bolt"], [], forests=40)
    ral = to_hand(s, "Ral and the Implicit Maze")
    mana(s, R=2, C=3)
    act(s, "p1", type="cast_spell", card_id=ral.id)
    settle(s)
    for _ in range(2):
        to_phase(s, "main1", turn=s.state.turn.number + 2)
        settle(s)
    (weird,) = tokens(s, "Spellgorger Weird")
    c = ch(s, weird)
    assert (c.mana_cost, c.mana_value, c.colors) == ("{2}{R}", 3.0, frozenset({"R"}))
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p2"])  # a noncreature spell: the token's own ability puts a counter on it
    settle(s)
    assert s.state.cards[weird.id].counters.get("+1/+1") == 1
    check(s)
