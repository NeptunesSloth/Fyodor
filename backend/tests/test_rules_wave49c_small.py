"""Wave 49C: single-wording gaps of cards ranked 25,000 and up (CR 2026-09-25), real Oracle text (tests/fixtures/wave49c_small_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 702.129a: "Eternalize—{2}{W}{W}, Discard a card." (Sunscourge Champion, Sinuous Striker) - the keyword's cost has a second part, a discard from the hand (the card with
  eternalize is in the graveyard, so it cannot discard itself); with no other card in hand the ability cannot be activated.
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
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, card_named, check, life, mana, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave49c_small_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w49c", number=f"S{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Sunscourge Champion", "Sinuous Striker"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_the_cards_are_full(cards):
    for name in FULL:
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def eternalize(s, name="Sunscourge Champion", hand_left=1):
    """The card in the graveyard and (``hand_left``) a Forest in hand to discard; returns the card."""
    champ = card_named(s, name)
    act(s, "p1", type="move", card_ids=[champ.id], to={"zone": "graveyard"})
    if hand_left:
        to_hand(s, "Forest")
    mana(s, W=2, C=2)
    return champ


def test_eternalize_with_a_discard_makes_the_token_and_discards_a_card(cards):
    s = build(cards, ["Sunscourge Champion"])
    champ = eternalize(s)
    discarded = s.state.zones["p1:hand"][0]
    act(s, "p1", type="activate_ability", card_id=champ.id, ability=1)
    settle(s)
    assert s.state.cards[champ.id].zone == "p1:exile" and s.state.cards[discarded].zone == "p1:graveyard" and not s.state.zones["p1:hand"]
    (token,) = [c for c in s.state.cards.values() if c.token is not None and c.name == "Sunscourge Champion"]
    ch = Plan(s.state, "p1", s.cards, None).ch(token)
    assert ch.colors == {"B"} and "Zombie" in ch.subtypes and ch.pt == (4, 4)  # 702.129a
    assert life(s) == 44  # its enters trigger gains life equal to its power
    check(s)


def test_eternalize_with_a_discard_needs_a_card_in_hand(cards):
    s = build(cards, ["Sunscourge Champion"])
    champ = eternalize(s, hand_left=0)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=champ.id, ability=1)
    check(s)
