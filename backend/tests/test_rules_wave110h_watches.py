"""Wave 110H: turn watches whose own target names the event's player (CR 603.7, 603.7c, 603.3d, 611.2a).

* The Sea Devils III: "Until end of turn, whenever a Salamander deals combat damage to a player, it deals that much damage to target creature that
  player controls." The damaged player is bound as the watch triggers; the damage comes from the Salamander (the event's dealer).
"""
from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import through_combat, until
from tests.wave9c_kit import build, check, put

SEA = ("(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\n"
       "I, II — Create a 2/2 green Alien Salamander creature token with islandwalk. (It can't be blocked as long as defending player controls an Island.)\n"
       "III — Until end of turn, whenever a Salamander deals combat damage to a player, it deals that much damage to target creature that player controls.")
EXTRA = [
    card("The Sea Devils", set_code="tst", number="110H20", mana_cost="{2}{G}", cmc=3.0, type_line="Enchantment — Saga", oracle_text=SEA),
    card("Test Salamander", set_code="tst", number="110H21", mana_cost="{2}", cmc=2.0, type_line="Creature — Salamander", power="3", toughness="3"),
    card("Test Wall", set_code="tst", number="110H22", mana_cost="{2}", cmc=2.0, type_line="Creature — Wall", power="0", toughness="9"),
]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_sea_devils_full(cards):
    assert coverage.of_card_data(cards.resolve("The Sea Devils")).level == "FULL"


def test_chapter_three_redirects_salamander_damage_to_a_creature_the_player_controls(cards):
    """603.7c: a Salamander's combat damage to the player is dealt again, by it, to a creature that player controls."""
    s = build(cards, ["The Sea Devils", "Test Salamander"], ["Test Wall"], forests=20)
    saga = put(s, "The Sea Devils")
    act(s, "p1", type="counter", card_ids=[saga.id], kind="lore", delta=2)
    attacker = put(s, "Test Salamander")
    wall = put(s, "Test Wall", "p2")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    until(s, lambda s: not s.state.zones.get("stack"))
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": attacker.id, "target": "p2"}])
    through_combat(s)
    assert s.state.players["p2"].life == 40 - 3 and s.state.cards[wall.id].damage == 3
    check(s)
