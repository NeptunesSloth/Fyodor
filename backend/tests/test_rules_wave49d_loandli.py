"""Wave 49D: an "either" trigger with a batch half (CR 2026-09-25), real Oracle text (tests/fixtures/wave49d_loandli_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 603.2c: Lo and Li, Royal Advisors' "Whenever an opponent discards a card or mills one or more cards, put a +1/+1 counter on each Advisor you control."
  - each card an opponent discards is its own event, while the cards one opponent mills at once are one ("one or more").
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
from tests.test_rules_wave34b_activated import activate, settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave49d_loandli_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w49d", number=f"L{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def counters(s, name="Lo and Li, Royal Advisors"):
    return s.state.cards[card_named(s, name).id].counters.get("+1/+1", 0)


def test_lo_and_li_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Lo and Li, Royal Advisors")).level == "FULL"


def test_each_discarded_card_is_an_event_but_a_mill_is_one(cards):
    s = build(cards, ["Lo and Li, Royal Advisors", "Mind Rot"], ["Grizzly Bears", "Llanowar Elves"], forests=30)
    put(s, "Lo and Li, Royal Advisors")
    to_hand(s, "Grizzly Bears", "p2")
    to_hand(s, "Llanowar Elves", "p2")
    to_hand(s, "Mind Rot")
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Mind Rot").id, targets=["p2"])
    settle(s)
    assert counters(s) == 2  # two cards discarded: two events
    mana(s, B=1, C=1, U=1)
    activate(s, "p1", card_named(s, "Lo and Li, Royal Advisors"), "mills four", targets=["p2"])
    settle(s)
    assert counters(s) == 3  # four cards milled at once: one more
    check(s)


def test_cards_it_does_not_care_about_do_not_trigger(cards):
    s = build(cards, ["Lo and Li, Royal Advisors", "Mind Rot", "Grizzly Bears", "Llanowar Elves"], [], forests=30)
    put(s, "Lo and Li, Royal Advisors")
    to_hand(s, "Grizzly Bears")
    to_hand(s, "Llanowar Elves")
    to_hand(s, "Mind Rot")
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Mind Rot").id, targets=["p1"])  # her own discard
    settle(s)
    mana(s, B=1, C=1, U=1)
    activate(s, "p1", card_named(s, "Lo and Li, Royal Advisors"), "mills four", targets=["p1"])  # her own mill
    settle(s)
    assert counters(s) == 0
    check(s)
