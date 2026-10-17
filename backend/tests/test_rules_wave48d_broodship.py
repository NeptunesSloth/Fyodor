"""Wave 48D: Exploration Broodship's charge-counter striations (CR 2026-09-25), real Oracle text (tests/fixtures/wave48d_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 721.2a: "3+ | You may play an additional land on each of your turns." is "As long as this permanent has 3 or more charge counters on it, …" (305.2: one more
  land play); below the threshold the permanent gives nothing. 611.3a: read as the land is played.
* "8+ | Once during each of your turns, you may cast a permanent spell from your graveyard by sacrificing a land in addition to paying its other costs." is a
  cast permission with an additional cost (601.2b), once during each of your turns, only with 8 or more charge counters on it. Ruling 2025-07-25: you pay all
  costs and follow all timing rules (a creature spell only in your main phase with the stack empty).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules.casting import castable
from tests.game_helpers import act
from tests.test_rules_wave30h_linked_exile import put_in, settle
from tests.wave9c_kit import build, card_named, check, mana, put
from tests.wave48d_kit import open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


def charge(s, ship, n):
    act(s, "p1", type="counter", card_ids=[ship.id], kind="charge", delta=n)


def forests_in_hand(s, n):
    ids = [c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"][:n]
    act(s, "p1", type="move", card_ids=ids, to={"zone": "hand"})
    return ids


def lands_played(s, ids):
    played = 0
    for cid in ids:
        try:
            act(s, "p1", type="play_land", card_id=cid)
        except ActionError:
            break
        played += 1
    return played


def test_broodship_gives_no_extra_land_play_below_three_charge_counters(cards):
    s = build(cards, ["Exploration Broodship"], [])
    ship = put(s, "Exploration Broodship")
    charge(s, ship, 2)
    assert lands_played(s, forests_in_hand(s, 3)) == 1  # 305.2: only the one
    check(s)


def test_broodship_gives_one_extra_land_play_at_three_charge_counters(cards):
    s = build(cards, ["Exploration Broodship"], [])
    ship = put(s, "Exploration Broodship")
    charge(s, ship, 3)
    assert lands_played(s, forests_in_hand(s, 3)) == 2
    check(s)


def test_broodship_loses_the_extra_land_play_when_the_counters_go_away(cards):
    s = build(cards, ["Exploration Broodship"], [])
    ship = put(s, "Exploration Broodship")
    charge(s, ship, 3)
    charge(s, ship, -1)  # 611.3a: read as the land is played
    assert lands_played(s, forests_in_hand(s, 3)) == 1
    check(s)


def castable_now(s, cards, name):
    return castable(s.state, "p1", card_named(s, name), cards, check_priority=False)


def test_broodship_casts_a_permanent_from_the_graveyard_by_sacrificing_a_land_at_eight_counters_once_a_turn(cards):
    s = build(cards, ["Exploration Broodship", "Grizzly Bears", "Grizzly Bears"], [])
    ship = put(s, "Exploration Broodship")
    put_in(s, "Grizzly Bears", "graveyard")
    for c in [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:library"][:1]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    f1, f2 = [c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"][:2]
    act(s, "p1", type="move", card_ids=[f1, f2], to={"player": "p1", "zone": "battlefield"})
    forest = s.state.cards[f1]
    mana(s, G=2)
    bears = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:graveyard"]
    assert len(bears) == 2
    charge(s, ship, 7)
    assert not castable(s.state, "p1", bears[0], cards, check_priority=False)  # 7 charge counters: the permission isn't there
    charge(s, ship, 1)
    assert castable(s.state, "p1", bears[0], cards, check_priority=False)
    act(s, "p1", type="cast_spell", card_id=bears[0].id)
    d = s.state.rules.decision
    assert d is not None  # which land to sacrifice (601.2b)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id == forest.id)])
    settle(s)
    assert s.state.cards[bears[0].id].zone == "p1:battlefield" and s.state.cards[forest.id].zone == "p1:graveyard" and s.state.cards[f2].zone == "p1:battlefield"
    assert not castable(s.state, "p1", bears[1], cards, check_priority=False)  # once during each of your turns
    check(s)
