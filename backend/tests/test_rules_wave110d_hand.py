"""Wave 110D: Hand of Vecna, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 118.3, 702.6a: "Equip—Pay 1 life for each card in your hand." — the life is counted as the cost is paid.
* 603.2, 611.2: "At the beginning of combat on your turn, equipped creature or a creature you control named Vecna gets +X/+X until end of turn,
  where X is the number of cards in your hand." — read as the equipped creature plus each creature named Vecna (one per player, 704.5j).
"""

from __future__ import annotations

import pytest

from tests.fixtures.cards import fixture_cards
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, life, to_hand
from tests.wave110d_kit import EXTRA, activate, card_db, ch, check, full, mana, put, settle, to_phase  # noqa: F401

VECNA = real("Vecna", "{3}", 3, "Legendary Creature — Zombie", "", ("1", "1"), "B")


@pytest.fixture()
def card_db_vecna(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, VECNA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_hand_of_vecna_is_full():
    assert full("Hand of Vecna")


def test_equip_costs_life_per_card_in_hand_and_pumps_at_combat(cards):
    s = build(cards, ["Hand of Vecna", "Grizzly Bears", "Forest", "Island", "Swamp"])
    hand, bears = put(s, "Hand of Vecna"), put(s, "Grizzly Bears")
    for land in ("Forest", "Island", "Swamp"):
        to_hand(s, land)
    n = len(s.state.zones["p1:hand"])
    assert n >= 3
    mana(s, C=2)
    activate(s, hand, "Equip", targets=[bears.id])
    assert life(s, "p1") == 40 - n and s.state.cards[hand.id].attached_to == bears.id
    to_phase(s, "begin_combat", turn=s.state.turn.number)
    settle(s)
    assert ch(s, bears).pt[0] == 2 + n
    check(s)


def test_creature_named_vecna_gets_pump_without_equipment(cards, card_db_vecna):
    s = build(cards, ["Hand of Vecna", "Vecna", "Grizzly Bears", "Forest", "Island"])
    put(s, "Hand of Vecna")
    vecna, bears = put(s, "Vecna"), put(s, "Grizzly Bears")
    for land in ("Forest", "Island"):
        to_hand(s, land)
    n = len(s.state.zones["p1:hand"])
    to_phase(s, "begin_combat", turn=s.state.turn.number)
    settle(s)
    assert ch(s, vecna).pt[0] == 1 + n and ch(s, bears).pt[0] == 2
    check(s)
