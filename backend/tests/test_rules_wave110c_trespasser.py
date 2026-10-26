# ruff: noqa: F811  (the imported `cards` fixture is used as the test argument)
"""Wave 110C: _____ _____ _____ Trespasser. 123.2 (name stickers on the permanent), 611.2a (the pump lasts until end of turn), 509.1b (it can't be blocked)."""

from __future__ import annotations

import pytest

from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from app.rules.sticker_sheets101 import SHEETS
from tests.game_helpers import act, deck, enable
from tests.test_rules_designations import find
from tests.test_rules_sticker_effects101 import (  # noqa: F401  (cards: the fixture DB with the sticker cards)
    FixedSheetRng,
    cards,
    cast,
    pick,
    place,
    question,
)
from tests.wave9c_kit import check
from tests.wave100c_kit import to_phase

NAME = "_____ _____ _____ Trespasser"


def start(cards):
    mine = deck(cards, "Krenko, Mob Boss", [(30, "Forest"), (1, NAME)])
    mine += [DeckCard("stickers", 1, s["name"], s["printing_id"]) for s in list(SHEETS.values())[:10]]
    other = deck(cards, "Atraxa, Praetors' Voice", [(30, "Island")])
    state = enable(new_game([PlayerSetup("Alice", cards=mine), PlayerSetup("Bob", cards=other)], shuffle=False, rng=FixedSheetRng()))
    s = GameSession(state, cards=cards)
    for pid in state.players:
        act(s, pid, type="set_prefs", response="on")
    to_phase(s, "main1", 1)
    return s


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == "FULL"


@pytest.mark.parametrize("stickered", [True, False])
def test_pump_per_name_sticker(cards, stickered):
    """+1/+0 for each name sticker on it (none: +0), and it can't be blocked this turn."""
    s = start(cards)
    c = cast(s, NAME)
    d = question(s)
    if stickered:
        place(s, c.id, kind="name")
    else:
        pick(s, [])
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    c = find(s, NAME)
    base = Plan(s.state, "p1", s.cards, None).ch(c).pt[0]
    act(s, "p1", type="add_mana", player="p1", mana={"U": 1, "C": 3})
    act(s, "p1", type="activate_ability", card_id=c.id, ability=1)
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    assert Plan(s.state, "p1", s.cards, None).ch(find(s, NAME)).pt[0] == base + (1 if stickered else 0)
    assert d is not None
    check(s)


TUSK = "Tusk and Whiskers"


def start_tusk(cards):
    mine = deck(cards, "Krenko, Mob Boss", [(30, "Forest"), (1, TUSK), (1, "Grizzly Bears"), (1, "Sol Ring")])
    mine += [DeckCard("stickers", 1, s["name"], s["printing_id"]) for s in list(SHEETS.values())[:10]]
    other = deck(cards, "Atraxa, Praetors' Voice", [(30, "Island")])
    state = enable(new_game([PlayerSetup("Alice", cards=mine), PlayerSetup("Bob", cards=other)], shuffle=False, rng=FixedSheetRng()))
    s = GameSession(state, cards=cards)
    for pid in state.players:
        act(s, pid, type="set_prefs", response="on")
    to_phase(s, "main1", 1)
    return s


def test_tusk_full(cards):
    assert coverage.of_card_data(cards.resolve(TUSK)).level == "FULL"


def activate_tusk(s, tusk):
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1, "W": 1, "C": 2})
    act(s, "p1", type="activate_ability", card_id=tusk.id, ability=1)
    for _ in range(20):
        if s.state.rules.decision is not None:
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no sticker question")


@pytest.mark.parametrize("kind,target,counters", [("ability", "Grizzly Bears", 1), ("art", "Grizzly Bears", 0), ("ability", "Sol Ring", 0)])
def test_tusk_counter_for_ability_stickers_on_creatures(cards, kind, target, counters):
    """123.2: a +1/+1 counter on the creature that got an ability sticker (not an art sticker, not a noncreature)."""
    from tests.test_rules_designations import put

    s = start_tusk(cards)
    tusk = put(s, TUSK, "battlefield")
    thing = put(s, target, "battlefield")
    to_phase(s, "main1", 3)  # (no longer summoning sick)
    activate_tusk(s, tusk)
    assert s.state.players["p1"].resources["ticket"] == 1
    pick(s, [])  # (the sticker is optional: keep the ticket)
    to_phase(s, "main1", 5)
    activate_tusk(s, tusk)
    assert s.state.players["p1"].resources["ticket"] == 2
    place(s, thing.id, kind=kind, cost=2 if kind == "ability" else None)
    while s.state.rules.decision is not None or s.state.zones.get("stack"):
        if s.state.rules.decision is not None:
            pick(s, [s.state.rules.decision.options[0].id])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[thing.id].counters.get("+1/+1", 0) == counters
    check(s)
