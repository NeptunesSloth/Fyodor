"""Wave 47B: "exile a permanent card from your graveyard at random" (Sin, Spira's Punishment) and "your Ring-bearer" (Galadriel, Elven-Queen) (CR 2026-09-25),
real Oracle text (tests/fixtures/wave47b_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* The graveyard is public (404.2): the table picks one of the matching cards at random and the move is a recorded step, so a replay or a load takes the
  same card. "If the exiled card is a land card, repeat this process": the exiled card is the one asked about (the token is a copy of it, but it may not
  exist), and each turn of the process picks again among what is left.
* Sin's ruling 2025-06-06: the token copies exactly what was printed on the card; "tapped" is the token's.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave34b_activated import ask, settle
from tests.wave9c_kit import card_named, check, mana, to_hand
from tests.wave47b_kit import build3, cast, open_cards, pin_random


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


def in_graveyard(s, name):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


def sin_table(cards, monkeypatch, index, graveyard):
    pin_random(monkeypatch, index)
    s = build3(cards, ["Sin, Spira's Punishment", *graveyard])
    gone = [in_graveyard(s, n) for n in graveyard]
    to_hand(s, "Sin, Spira's Punishment")
    mana(s, B=1, G=1, U=1, C=4)
    cast(s, "Sin, Spira's Punishment")  # (its enters trigger)
    return s, gone


def tokens(s):
    return sorted((c.name, c.tapped) for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield")


@pytest.mark.parametrize("index", [0, 1])
def test_sin_exiles_a_permanent_card_at_random_and_repeats_after_a_land(cards, monkeypatch, index):
    s, gone = sin_table(cards, monkeypatch, index, ["Forest", "Grizzly Bears"])
    first = sorted(c.id for c in gone)[index]
    exiled = [c for c in gone if s.state.cards[c.id].zone == "p1:exile"]
    if s.state.cards[first].name == "Forest":  # a land: the process repeats and takes the other card
        assert len(exiled) == 2 and tokens(s) == [("Forest", True), ("Grizzly Bears", True)]
    else:  # not a land: it stops, and the land stays in the graveyard
        assert [c.name for c in exiled] == ["Grizzly Bears"] and tokens(s) == [("Grizzly Bears", True)]
    check(s)


def test_sin_takes_only_permanent_cards_and_stops_when_there_are_none(cards, monkeypatch):
    s, gone = sin_table(cards, monkeypatch, 0, ["Lightning Bolt"])  # an instant is no permanent card
    assert s.state.cards[gone[0].id].zone == "p1:graveyard" and tokens(s) == []
    check(s)


# -- "discard a card at random": the cards picked (nobody chooses, nobody is asked) go to the graveyard, public from then on --------------------------
def hand_only(s, *keep, pid="p1"):
    for c in list(s.state.zones[f"{pid}:hand"]):
        if s.state.cards[c].name not in keep:
            act(s, pid, type="move", card_ids=[c], to={"zone": "graveyard"})


def test_cragganwick_cremator_deals_the_power_of_a_creature_card_discarded_at_random(cards):
    s = build3(cards, ["Cragganwick Cremator", "Grizzly Bears"])
    to_hand(s, "Cragganwick Cremator")
    to_hand(s, "Grizzly Bears")
    hand_only(s, "Cragganwick Cremator", "Grizzly Bears")
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Cragganwick Cremator").id)
    d = ask(s)  # the target of the enters trigger (a player or planeswalker): Bob
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    settle(s)
    assert s.state.cards[card_named(s, "Grizzly Bears").id].zone == "p1:graveyard"  # the only card in the hand
    assert s.state.players["p2"].life == 38  # its power is 2
    check(s)


def test_cragganwick_cremator_deals_nothing_for_a_card_that_is_no_creature(cards):
    s = build3(cards, ["Cragganwick Cremator"])
    to_hand(s, "Cragganwick Cremator")
    hand_only(s, "Cragganwick Cremator")
    act(s, "p1", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")], to={"zone": "hand"})
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Cragganwick Cremator").id)
    settle(s)
    assert s.state.players["p2"].life == 40 and s.state.rules.decision is None
    check(s)


def test_skull_rend_makes_each_opponent_discard_two_cards_at_random(cards, monkeypatch):
    pin_random(monkeypatch, 0)
    s = build3(cards, ["Skull Rend"], bobs=["Grizzly Bears", "Hill Giant", "Shivan Dragon"], carols=["Grizzly Bears", "Hill Giant", "Shivan Dragon"])
    for pid in ("p2", "p3"):
        act(s, pid, type="draw", player=pid, count=3)
    hands = {pid: sorted(s.state.zones[f"{pid}:hand"]) for pid in ("p2", "p3")}
    to_hand(s, "Skull Rend")
    mana(s, B=1, R=1, C=3)
    cast(s, "Skull Rend")
    for pid, hand in hands.items():
        assert sorted(s.state.zones[f"{pid}:hand"]) == hand[2:] and s.state.players[pid].life == 38  # (two cards gone, the table picked them)
    assert s.state.players["p1"].life == 40
    check(s)


def test_reckless_handling_discards_at_random_after_the_search_and_hurts_for_an_artifact(cards):
    s = build3(cards, ["Reckless Handling", "Sol Ring"])
    to_hand(s, "Reckless Handling")
    hand_only(s, "Reckless Handling")  # (so Sol Ring is the only artifact card around, and the discard can be Sol Ring itself)
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Reckless Handling").id)
    settle(s)
    assert s.state.cards[card_named(s, "Sol Ring").id].zone == "p1:graveyard"  # the only card in the hand
    assert (s.state.players["p2"].life, s.state.players["p3"].life) == (38, 38)  # an artifact card was discarded this way
    check(s)


# -- "Will of the council — At the beginning of combat on your turn, if another Elf entered …, each player votes for dominion or guidance …" ---------
def ballot(s, pid, label):
    d = s.state.rules.decision
    assert d is not None and d.player == pid, (d.player if d else None, pid)
    act(s, pid, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == label)])


def galadriel_at_combat(cards):
    s = build3(cards, ["Galadriel, Elven-Queen", "Llanowar Elves"])
    to_hand(s, "Galadriel, Elven-Queen")
    mana(s, G=2, U=1, C=1)
    cast(s, "Galadriel, Elven-Queen")
    to_hand(s, "Llanowar Elves")
    mana(s, G=1)
    cast(s, "Llanowar Elves")  # another Elf entered under Alice's control this turn
    until(s, lambda s: s.state.rules.decision is not None and s.state.turn.phase == "begin_combat")
    return s


def test_galadriel_dominion_with_more_votes_tempts_and_puts_a_counter_on_the_ring_bearer(cards):
    s = galadriel_at_combat(cards)
    ballot(s, "p1", "dominion")  # votes in turn order, starting with Alice
    ballot(s, "p2", "dominion")
    ballot(s, "p3", "guidance")
    d = s.state.rules.decision  # the Ring tempts Alice: she chooses her Ring-bearer
    assert d is not None and d.player == "p1"
    bearer = next(o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name == "Llanowar Elves")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bearer])
    settle(s)
    assert s.state.cards[bearer].counters.get("+1/+1") == 1  # "your Ring-bearer", not the source
    assert not s.state.cards[card_named(s, "Galadriel, Elven-Queen").id].counters.get("+1/+1")
    check(s)


@pytest.mark.parametrize("votes", [("guidance", "guidance", "dominion"), ("dominion", "guidance", "guidance")])
def test_galadriel_guidance_with_more_votes_draws_a_card(cards, votes):
    s = galadriel_at_combat(cards)
    hand = len(s.state.zones["p1:hand"])
    for pid, vote in zip(("p1", "p2", "p3"), votes, strict=True):
        ballot(s, pid, vote)
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1 and not s.state.rules.ring_bearers
    check(s)
