"""Wave 110C: Charred Foyer // Warped Space (709.5, 118.9): the right door's "pay {0} rather than pay the mana cost" works only while that door is unlocked."""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.view import hints
from tests.game_helpers import act
from tests.test_rules_conditionals import build, settle, to_hand
from tests.test_rules_effects import mana
from tests.test_rules_wave4i_cost_changers import alt_key
from tests.test_rules_wave15d_activated import roundtrip
from tests.test_rules_wave18g_rooms import room
from tests.test_rules_wave30m_durations import to_phase

FOYER = "Charred Foyer // Warped Space"
EXTRA = [room(FOYER, ("Charred Foyer", "{3}{R}", "At the beginning of your upkeep, exile the top card of your library. You may play it this turn."),
              ("Warped Space", "{4}{R}{R}", "Once each turn, you may pay {0} rather than pay the mana cost for a spell you cast from exile."), ["R"])]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(FOYER)).level == "FULL"


def _upkeep_with_ring(cards, both):
    s = build(cards, FOYER, "Sol Ring")
    c = to_hand(s, FOYER)
    ring = next(x for x in s.state.cards.values() if x.name == "Sol Ring" and x.owner == "p1")
    mana(s, "p1", R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id, face=0)  # the left door: 709.5d
    settle(s)
    if both:
        mana(s, "p1", R=2, C=4)
        act(s, "p1", type="unlock_door", card_id=c.id, door=2)  # 709.5e
        settle(s)
    act(s, "p1", type="move", card_ids=[ring.id], to={"zone": "library"}, position="top")
    to_phase(s, "main1", 3)  # (the upkeep trigger has resolved by then)
    settle(s)
    assert s.state.cards[ring.id].zone == "p1:exile"
    return s, ring


def test_unlocked_door_lets_the_exiled_spell_cost_zero_once_each_turn(cards):
    s, ring = _upkeep_with_ring(cards, True)
    key = alt_key(s, ring)
    act(s, "p1", type="cast_spell", card_id=ring.id, alt_cost=key)  # {0} instead of {1}: no mana in the pool
    settle(s)
    assert s.state.cards[ring.id].zone == "p1:battlefield"
    roundtrip(s)


def test_locked_door_gives_no_alternative_cost(cards):
    s, ring = _upkeep_with_ring(cards, False)
    assert ring.id not in hints(s.state, "p1", s.cards).get("alt_castable", {})
    roundtrip(s)
