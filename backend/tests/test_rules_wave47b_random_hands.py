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
