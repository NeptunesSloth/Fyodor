"""Wave 47B: "reveals a card at random from their hand" / "Look at a card at random in target player's hand" (CR 2026-09-25), real Oracle text
(tests/fixtures/wave47b_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 701.20a: a revealed card is shown to everyone; 701.20e: a looked-at card to the looker alone. The pick among the hand is the table's (nobody has
  seen the cards): the only thing anyone learns is the card picked, and a replay or a load never draws again (the reveal is a recorded step).
* The cards left in the hand stay hidden from everybody, before, during and after (no leak by omission: nothing about them is asked, logged or shown),
  and the picked card is hidden again once the resolution is over.
"""

from __future__ import annotations

import json

import pytest

from app.game.visibility import SPECTATOR
from tests.game_helpers import act
from tests.test_rules_conditionals import through_combat, until
from tests.test_rules_wave34b_activated import activate, settle
from tests.wave9c_kit import check, mana, put, to_hand
from tests.wave47b_kit import build3, cast, life, open_cards, pin_random

HAND = ["Grizzly Bears", "Hill Giant", "Shivan Dragon"]  # mana values 2, 4, 6
MV = {"Grizzly Bears": 2, "Hill Giant": 4, "Shivan Dragon": 6}


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


def bobs_hand(s):
    return list(s.state.zones["p2:hand"])


def seen_by(s, viewer, ids):
    blob = json.dumps(s.view(viewer))
    return [c for c in ids if c in blob]


def table(cards, mine):
    s = build3(cards, mine, bobs=HAND)
    act(s, "p2", type="draw", player="p2", count=3)
    return s


@pytest.mark.parametrize("index", [0, 1, 2])
def test_ignite_memories_reveals_one_card_at_random_and_hurts_for_its_mana_value(cards, monkeypatch, index):
    pin_random(monkeypatch, index)
    s = table(cards, ["Ignite Memories"])
    hand = sorted(bobs_hand(s))
    to_hand(s, "Ignite Memories")
    mana(s, R=1, C=4)
    cast(s, "Ignite Memories", targets=["p2"])
    picked = hand[index]
    name = s.state.cards[picked].name
    assert life(s, "p2") == 40 - MV[name]  # the damage is the revealed card's mana value
    log = json.dumps(s.view("p3")["log"])
    assert [n for n in HAND if f'"name": "{n}"' in log] == [name]  # one card named in the log; the others are not
    others = [c for c in hand if c != picked]
    for viewer in ("p1", "p3", SPECTATOR):
        assert seen_by(s, viewer, others) == []  # the cards left in the hand: hidden from everyone
    assert all(s.state.cards[c].revealed_to == [] for c in hand)  # and the picked one is hidden again
    assert sorted(bobs_hand(s)) == hand
    check(s)


def test_a_random_reveal_from_an_empty_hand_does_nothing(cards):
    s = build3(cards, ["Ignite Memories"], bobs=HAND)
    to_hand(s, "Ignite Memories")
    mana(s, R=1, C=4)
    cast(s, "Ignite Memories", targets=["p2"])
    assert life(s, "p2") == 40 and s.state.rules.decision is None  # (nothing was asked: the hand's size is public anyway)
    check(s)


def test_merfolk_spy_makes_the_player_it_hurt_reveal_a_card_at_random(cards, monkeypatch):
    """"Whenever this creature deals combat damage to a player, that player reveals a card at random from their hand." (the player the trigger is about)"""
    pin_random(monkeypatch, 1)
    s = table(cards, ["Merfolk Spy"])
    spy = put(s, "Merfolk Spy")
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)  # (Bob drew on his own turn)
    hand = sorted(bobs_hand(s))
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": spy.id, "target": "p2"}])
    through_combat(s)
    shown = [x["card"]["name"] for e in s.view("p3")["log"] if any(" revealed " in (p.get("t") or "") for p in e["parts"])
             for g in e["parts"] if "group" in g for x in g["group"]]
    assert shown == [s.state.cards[hand[1]].name]  # one card shown to everyone: the second by the table's order
    assert seen_by(s, "p3", hand) == [] and all(s.state.cards[c].revealed_to == [] for c in hand)  # and hidden again afterwards
    check(s)


@pytest.mark.parametrize("named, expected", [("Island", 3), ("Grizzly Bears", 1)])
def test_nebuchadnezzar_discards_only_the_revealed_cards_with_the_chosen_name(cards, monkeypatch, named, expected):
    """{X}, {T}: Choose a card name. Target opponent reveals X cards at random from their hand. Then that player discards all cards with that name
    revealed this way. Bob holds Grizzly Bears and three Islands; X is 4: all are revealed (nothing else is shown), and only those named go."""
    pin_random(monkeypatch, 0)
    s = build3(cards, ["Nebuchadnezzar"], bobs=["Grizzly Bears"])
    act(s, "p2", type="draw", player="p2", count=3)
    neb = put(s, "Nebuchadnezzar")
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)  # (Bob drew on his own turn)
    hand = sorted(bobs_hand(s))
    assert len(hand) == 4
    mana(s, C=4)
    activate(s, "p1", neb, targets=["p2"], x_value=4)
    d = s.state.rules.decision  # the typed name (a free-text choice; nothing about any hand is in the question)
    assert d is not None and d.player == "p1"
    act(s, "p1", type="choose", decision_id=d.id, name=named)
    settle(s)
    gone = [c for c in hand if s.state.cards[c].zone == "p2:graveyard"]
    assert sorted(s.state.cards[c].name for c in gone) == [named] * expected
    assert all(s.state.cards[c].revealed_to == [] for c in hand if c not in gone)  # the rest are hidden again
    assert seen_by(s, "p3", [c for c in hand if c not in gone]) == []
    check(s)


def test_urza_baubles_look_is_private_to_the_looker(cards, monkeypatch):
    pin_random(monkeypatch)
    s = table(cards, ["Urza's Bauble"])
    hand = sorted(bobs_hand(s))
    bauble = put(s, "Urza's Bauble")
    activate(s, "p1", bauble, targets=["p2"])
    settle(s)
    for viewer in ("p1", "p3", SPECTATOR):
        assert seen_by(s, viewer, hand) == []  # nobody but Alice saw the card, and even she doesn't hold it revealed any more
    assert all(s.state.cards[c].revealed_to == [] for c in hand)
    assert "Grizzly Bears" not in json.dumps(s.view("p3")["log"]) and "Hill Giant" not in json.dumps(s.view("p3")["log"]) \
        and "Shivan Dragon" not in json.dumps(s.view("p3")["log"])
    check(s)
