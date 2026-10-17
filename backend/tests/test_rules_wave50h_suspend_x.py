"""Wave 50H: "Suspend X—{X}{3}{U}. X can't be 0." and "Whenever a time counter is removed from this card while it's exiled, …" (CR 702.62, 107.3d, 2026-09-25), real Oracle
text (tests/fixtures/wave50h_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 107.3d: the X of a suspend cost is chosen by the player taking the special action, immediately before they pay that cost; the card is exiled with X time counters
  (Aeon Chronicler, Benalish Commander); X can't be 0 (the printed line).
* 702.62a: the upkeep ticks and the card's own trigger functions in exile: it triggers each time a time counter is removed from it, only there, only for its owner's upkeep.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import next_turn
from tests.wave9c_kit import build, card_named, check, mana, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50h_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50h", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def suspend_index(s, name):
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name).id])
    return next(a.index for a in ch.abilities if "suspend" in a.keywords)


def hand(s):
    return len([c for c in s.state.cards.values() if c.zone == "p1:hand"])


@pytest.mark.parametrize("name", ["Aeon Chronicler", "Benalish Commander"])
def test_suspend_x_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_x_is_announced_and_cant_be_0(cards):
    s = build(cards, ["Aeon Chronicler"])
    chron = to_hand(s, "Aeon Chronicler")
    mana(s, U=1, C=5)
    ab = suspend_index(s, "Aeon Chronicler")
    assert {"card_id": chron.id, "ability": ab, "x": True} in s.view("p1")["rules"]["hints"]["activatable"]  # the client asks for X first (107.3d)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=chron.id, ability=ab)  # no X announced
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=chron.id, ability=ab, x_value=0)  # "X can't be 0"
    assert zone_of(s, "Aeon Chronicler") == "p1:hand"
    check(s)


def test_each_time_counter_removed_in_exile_triggers_the_card(cards):
    s = build(cards, ["Aeon Chronicler"])
    chron = to_hand(s, "Aeon Chronicler")
    mana(s, U=1, C=5)  # {X}{3}{U} with X = 2
    act(s, "p1", type="activate_ability", card_id=chron.id, ability=suspend_index(s, "Aeon Chronicler"), x_value=2)
    assert zone_of(s, "Aeon Chronicler") == "p1:exile" and s.state.cards[chron.id].counters.get("time") == 2
    assert s.state.players["p1"].mana == {}  # {2}{3}{U}: all spent
    before = hand(s)
    next_turn(s)  # Bob's turn (no tick: 702.62a is "your upkeep"), then Alice's: a counter comes off, the trigger draws, so does her draw step
    assert s.state.cards[chron.id].counters.get("time") == 1 and hand(s) == before + 2
    check(s)
    next_turn(s)  # the last counter: draw again, and the free cast is offered (the first option casts it)
    assert hand(s) == before + 4 and zone_of(s, "Aeon Chronicler") in ("p1:battlefield", "p1:stack")
    check(s)


def test_the_last_counter_triggers_its_own_ability_and_offers_the_cast_whichever_is_first(cards):
    # Benalish Commander ruling: both trigger when the last time counter is removed; the Soldier is made even if the card is cast first
    s = build(cards, ["Benalish Commander"])
    cmd = to_hand(s, "Benalish Commander")
    mana(s, W=2, C=1)  # {X}{W}{W} with X = 1
    act(s, "p1", type="activate_ability", card_id=cmd.id, ability=suspend_index(s, "Benalish Commander"), x_value=1)
    assert s.state.cards[cmd.id].counters.get("time") == 1
    next_turn(s)
    soldiers = [c for c in s.state.cards.values() if c.is_token and c.name == "Soldier" and c.zone == "p1:battlefield"]
    assert len(soldiers) == 1 and zone_of(s, "Benalish Commander") == "p1:battlefield"
    check(s)
