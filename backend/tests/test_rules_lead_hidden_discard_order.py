"""Lead fix after review 36: a hand's order is hidden information (it is the order the cards were drawn in unless the player moved them), so
cards an effect puts from a hand into a graveyard together must not land in the hand's order (404.3 lets the owner arrange them; when the
owner isn't asked, the engine picks an order that reads nothing hidden). Real Oracle text: Malfegor (tests/fixtures/wave21r_cards.json, from
data/cards.sqlite)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import build, cast, check, mana, to_hand

MALFEGOR = next(c for c in json.loads((Path(__file__).parent / "fixtures" / "wave21r_cards.json").read_text("utf-8"))
                if c["name"] == "Malfegor")


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    extra = card("Malfegor", set_code="ld01", number="1", **{k: v for k, v in MALFEGOR.items() if k != "name"})
    build_database([*fixture_cards(), extra], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


HAND = ["Opt", "Murder", "Giant Growth"]


def discard_hand(cards, order):
    s = build(cards, ["Malfegor", *HAND], [])
    for name in order:
        to_hand(s, name)
    to_hand(s, "Malfegor")
    mana(s, B=2, R=2, C=2)
    cast(s, "Malfegor")
    settle(s)
    pile = [s.state.cards[c].name for c in s.state.zones["p1:graveyard"]]
    return s, pile


def test_a_discarded_hand_lands_in_an_order_that_does_not_depend_on_the_hand(cards):
    s1, first = discard_hand(cards, HAND)
    s2, second = discard_hand(cards, list(reversed(HAND)))
    assert sorted(first) == sorted(HAND) and first == second
    check(s1)
    check(s2)
