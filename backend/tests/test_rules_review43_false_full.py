"""Review 43: cards waves 50G-50J made FULL that played wrong (CR 2026-09-25), real Oracle text (tests/fixtures/review43_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 101.2, 601.3: Haakon, Stromgald Scourge's "You may cast this card from your graveyard, but not from anywhere else." was read only by the cast from a zone;
  a cast as something resolves (cascade, 608.2g) still offered him from exile. The ruling (2006-07-15): he can't be cast from any zone other than the
  graveyard, even if an effect would otherwise allow it.
* 702.192a: a paradigm card that left exile stopped its delayed trigger. The ruling (2026-03-20): once the spell has resolved, it doesn't matter what happens
  to the card in exile; the trigger still makes the copy each first main phase (by hand while the card is elsewhere).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until_asked
from tests.test_rules_wave34b_activated import next_turn, settle
from tests.wave9c_kit import build, card_named, check, mana, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "review43_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r43", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_cascade_doesnt_offer_haakon_from_exile(cards):
    s = build(cards, ["Bloodbraid Elf", "Haakon, Stromgald Scourge"])
    elf = to_hand(s, "Bloodbraid Elf")
    haakon = card_named(s, "Haakon, Stromgald Scourge")
    act(s, "p1", type="move", card_ids=[haakon.id], to={"player": "p1", "zone": "library"}, position="top")
    mana(s, R=1, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=elf.id)
    assert until_asked(s) is None  # (no "cast it?" question: he can't be cast from exile)
    assert s.state.zones["p1:library"][-1] == haakon.id  # 702.85a: the card not cast goes to the bottom
    check(s)


def test_a_paradigm_card_that_left_exile_still_makes_its_copy(cards):
    s = build(cards, ["Decorum Dissertation"])
    dis = to_hand(s, "Decorum Dissertation")
    mana(s, B=2, C=3)
    act(s, "p1", type="cast_spell", card_id=dis.id, targets=["p2"])
    settle(s)
    assert zone_of(s, "Decorum Dissertation") == "p1:exile"
    act(s, "p2", type="move", card_ids=[dis.id], to={"player": "p1", "zone": "graveyard"})  # (Pull from Eternity, say)
    next_turn(s)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and d.kind == "manual_resolution" and "Create a copy of Decorum Dissertation in exile" in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["done"])
    settle(s)
    check(s)
