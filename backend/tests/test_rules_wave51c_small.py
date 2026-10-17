"""Wave 51C: popular cards still short of FULL (CR 2026-09-25), real Oracle text (tests/fixtures/wave51c_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 608.2c, 118.12a: "Counter target noncreature spell unless its controller pays {1}. Ferocious - If you control a creature with power 4 or
  greater, counter that spell instead." (Stubborn Denial): the condition is checked as the spell resolves; when it holds nobody is offered a payment.
* 404.1, 608.2c: "Draw a card. If a graveyard has twenty or more cards in it, draw three cards instead." (Visions of Beyond): any player's graveyard.
* 402.2, 122.1: "Your maximum hand size is twenty." and "you win the game if there are twenty or more counters on it or you have twenty or more
  cards in hand" (Twenty-Toed Toad): counters of every kind together.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, hand_size
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import pick, until_asked
from tests.test_rules_wave34b_activated import attack, next_turn, stops
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave51c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w51c", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Stubborn Denial", "Visions of Beyond", "Twenty-Toed Toad"])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def settle(s, limit=40):
    """Resolve everything; a choice is answered with its first option."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


# -- Stubborn Denial ---------------------------------------------------------------------------------------------------------------------------
def deny_bolt(cards, ferocious_for):
    """Alice bolts Bob; Bob answers with Stubborn Denial; ``ferocious_for`` (p1 / p2 / None) controls a Craw Wurm (power 6) first."""
    s = build(cards, ["Lightning Bolt", "Craw Wurm"], ["Stubborn Denial", "Craw Wurm"])
    if ferocious_for:
        put(s, "Craw Wurm", ferocious_for)
    bolt = to_hand(s, "Lightning Bolt")
    denial = to_hand(s, "Stubborn Denial", "p2")
    act(s, "p2", type="set_prefs", response="on")
    mana(s, "p2", U=1)
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=denial.id, targets=[bolt.id])
    return s, bolt


@pytest.mark.parametrize("pays", [True, False])
def test_stubborn_denial_without_a_big_creature_asks_for_one(cards, pays):
    s, bolt = deny_bolt(cards, None)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and [o.id for o in d.options] == ["pay", "decline"]
    pick(s, "pay" if pays else "decline")
    settle(s)
    assert (life(s, "p2"), zone_of(s, "Lightning Bolt")) == ((37, "p1:graveyard") if pays else (40, "p1:graveyard"))
    check(s)


def test_stubborn_denial_counters_outright_with_a_power_four_creature(cards):
    s, bolt = deny_bolt(cards, "p2")
    assert until_asked(s) is None  # (nothing to pay: the spell is countered as the ability resolves)
    assert life(s, "p2") == 40 and zone_of(s, "Lightning Bolt") == "p1:graveyard"
    assert s.state.players["p1"].mana.get("C", 0) == 1  # (the {1} was never asked for)
    check(s)


def test_stubborn_denial_ignores_the_big_creature_of_the_spells_caster(cards):
    s, bolt = deny_bolt(cards, "p1")  # ("you control": Stubborn Denial's controller, Bob)
    d = until_asked(s)
    assert d is not None and d.player == "p1"
    pick(s, "pay")
    settle(s)
    assert life(s, "p2") == 37
    check(s)


# -- Visions of Beyond -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("owner,drawn", [("p2", 3), (None, 1)])
def test_visions_of_beyond_looks_at_every_graveyard(cards, owner, drawn):
    s = build(cards, ["Visions of Beyond"], islands=30)
    if owner:  # twenty cards into Bob's graveyard
        ids = [c.id for c in s.state.cards.values() if c.owner == owner and c.zone == f"{owner}:library"][:20]
        act(s, owner, type="move", card_ids=ids, to={"player": owner, "zone": "graveyard"})
    to_hand(s, "Visions of Beyond")
    mana(s, U=1, C=1)
    before = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Visions of Beyond").id)
    settle(s)
    assert len(s.state.zones["p1:hand"]) == before - 1 + drawn
    check(s)


# -- Twenty-Toed Toad --------------------------------------------------------------------------------------------------------------------------
def toad_table(cards, in_hand, counters=0):
    s = build(cards, ["Twenty-Toed Toad"], forests=45)
    toad = put(s, "Twenty-Toed Toad")
    if counters:
        act(s, "p1", type="counter", card_ids=[toad.id], kind="charge", delta=counters)
    next_turn(s)
    extra = in_hand - len(s.state.zones["p1:hand"])
    ids = [c.id for c in s.state.cards.values() if c.zone == "p1:library"][:extra]
    act(s, "p1", type="move", card_ids=ids, to={"player": "p1", "zone": "hand"})
    return s, toad


def test_toad_hand_size_is_twenty(cards):
    s = build(cards, ["Twenty-Toed Toad"])
    assert hand_size.maximum(Plan(s.state, "p1", s.cards, None), "p1") == 7
    put(s, "Twenty-Toed Toad")
    assert hand_size.maximum(Plan(s.state, "p1", s.cards, None), "p1") == 20
    check(s)


@pytest.mark.parametrize("in_hand,counters,wins", [(20, 0, True), (19, 0, False), (3, 20, True), (3, 19, False)])
def test_toad_wins_on_twenty_cards_or_twenty_counters(cards, in_hand, counters, wins):
    s, toad = toad_table(cards, in_hand, counters)
    stops(s)
    attack(s, toad)
    settle(s)
    assert (s.state.rules.winner == "p1") is wins
    check(s)
