"""Wave 49D: "pay … and exile it" (CR 2026-09-25), real Oracle text (tests/fixtures/wave49d_small_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 118.3, 400.7: Kinzu of the Bleak Coven's "you may pay 2 life and exile it. If you do, create a token that's a copy of that creature, except it's 1/1
  and has toxic 1." - exiling the dead card is part of the cost, so the payment is offered only while that card is still in the graveyard it went to
  (Timothar's ruling: "If you can't exile the card, perhaps because another effect moved the card before the triggered ability started resolving,
  you can't pay {1} and won't create a token"). The token copies the creature as it last existed on the battlefield (Kinzu's ruling), and a
  characteristic-defining power and toughness isn't copied once the exception sets them (707.9d).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle, stops
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave49d_small_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w49d", number=f"S{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(c)


def bolt_own(s, victim):
    """Alice's Lightning Bolt kills her own creature; the trigger resolves (Alice answers its payment ``answer``)."""
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=[victim.id])


def test_kinzu_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Kinzu of the Bleak Coven")).level == "FULL"


def test_kinzu_pays_life_and_exiles_the_creature_for_a_one_one_toxic_copy(cards):
    s = build(cards, ["Kinzu of the Bleak Coven", "Grizzly Bears", "Lightning Bolt"], [])
    put(s, "Kinzu of the Bleak Coven")
    bears = put(s, "Grizzly Bears")
    bolt_own(s, bears)
    settle(s, answer="pay")
    assert s.state.cards[bears.id].zone == "p1:exile" and life(s) == 38
    (copy,) = [c for c in s.state.cards.values() if c.is_token and c.name == "Grizzly Bears"]
    c = ch(s, copy)
    assert copy.zone == "p1:battlefield" and (str(c.power), str(c.toughness)) == ("1", "1") and "toxic" in c.keywords
    check(s)


def test_kinzu_declined_leaves_the_creature_in_the_graveyard(cards):
    s = build(cards, ["Kinzu of the Bleak Coven", "Grizzly Bears", "Lightning Bolt"], [])
    put(s, "Kinzu of the Bleak Coven")
    bears = put(s, "Grizzly Bears")
    bolt_own(s, bears)
    settle(s, answer="decline")
    assert s.state.cards[bears.id].zone == "p1:graveyard" and life(s) == 40
    assert not [c for c in s.state.cards.values() if c.is_token]
    check(s)


def test_kinzu_cannot_pay_once_the_card_has_left_the_graveyard(cards):
    s = build(cards, ["Kinzu of the Bleak Coven", "Grizzly Bears", "Lightning Bolt"], [])
    stops(s)
    put(s, "Kinzu of the Bleak Coven")
    bears = put(s, "Grizzly Bears")
    bolt_own(s, bears)
    while s.state.cards[bears.id].zone != "p1:graveyard":  # the Bolt resolves; Kinzu's trigger is then on the stack
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.decision is None and s.state.zones["stack"]
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "exile"})  # in response to the trigger, the card is moved away
    settle(s, answer="pay")
    assert s.state.cards[bears.id].zone == "p1:exile" and life(s) == 40  # no payment was offered
    assert not [c for c in s.state.cards.values() if c.is_token]
    check(s)


def test_kinzu_ignores_an_opponents_creature_and_its_own_death(cards):
    s = build(cards, ["Kinzu of the Bleak Coven", "Lightning Bolt"], ["Grizzly Bears"])
    kinzu = put(s, "Kinzu of the Bleak Coven")
    theirs = put(s, "Grizzly Bears", "p2")
    to_hand(s, "Lightning Bolt")
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=[theirs.id])
    settle(s, answer="pay")
    assert s.state.cards[theirs.id].zone == "p2:graveyard" and life(s) == 40 and kinzu.zone == "p1:battlefield"
    assert not [c for c in s.state.cards.values() if c.is_token]
    check(s)


def test_kinzus_copy_of_a_characteristic_defining_creature_stays_one_one(cards):
    s = build(cards, ["Kinzu of the Bleak Coven", "Tarmogoyf", "Lightning Bolt"], [])
    put(s, "Kinzu of the Bleak Coven")
    goyf = put(s, "Tarmogoyf")
    bolt_own(s, goyf)
    settle(s, answer="pay")
    (copy,) = [c for c in s.state.cards.values() if c.is_token and c.name == "Tarmogoyf"]
    assert s.state.cards[goyf.id].zone == "p1:exile" and copy.zone == "p1:battlefield"
    assert (str(ch(s, copy).power), str(ch(s, copy).toughness)) == ("1", "1")  # 707.9d: the card types in the graveyard (the Bolt's one) don't size it
    check(s)
