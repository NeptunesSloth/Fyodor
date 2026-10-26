"""Wave 110A: Ninja Teen level 3 - creature cards in your graveyard have sneak {3}{B} and may be cast from there (702.190a, 113.6); real Oracle text."""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.view import hints
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave30i_sneak import EXTRA as EXTRA_30I
from tests.test_rules_wave30i_sneak import attackers_declared, pod, returned
from tests.wave9c_kit import card_named, check, mana, put, zone_of
from tests.wave110a_kit import EXTRA


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA_30I, *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Ninja Teen")).level == "FULL"


def _table(cards, level):
    s = pod(cards, ["Grizzly Bears", "Raphael, the Nightwatcher", "Ninja Teen"])
    teen = put(s, "Ninja Teen")
    s.state.rules.levels[s.state.rules.object_id(teen.id)] = level
    bear = put(s, "Grizzly Bears")
    raph = card_named(s, "Raphael, the Nightwatcher")
    act(s, "p1", type="move", card_ids=[raph.id], to={"player": "p1", "zone": "graveyard"})
    attackers_declared(s, [(bear, "p2")])
    mana(s, B=1, R=3)
    return s, bear, raph


def test_sneak_cast_from_the_graveyard_at_level_3(cards):
    s, bear, raph = _table(cards, 3)
    alt = next(a["id"] for a in hints(s.state, "p1", cards)["alt_castable"][raph.id] if "{3}{B}" in a.get("label", "{3}{B}"))
    act(s, "p1", type="cast_spell", card_id=raph.id, alt_cost=alt)
    returned(s, bear)
    settle(s)
    r = s.state.cards[raph.id]
    assert r.zone == "p1:battlefield" and r.tapped and r.attacking is not None  # 702.190b
    assert zone_of(s, "Grizzly Bears") == "p1:hand"  # the unblocked creature was returned (702.190a)
    check(s)


def test_no_sneak_from_the_graveyard_below_level_3(cards):
    s, bear, raph = _table(cards, 2)
    assert raph.id not in hints(s.state, "p1", cards).get("alt_castable", {})
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=raph.id, alt_cost=f"{raph.id}:0")
