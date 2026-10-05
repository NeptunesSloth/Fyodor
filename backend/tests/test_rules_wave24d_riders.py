"""Wave 24D: a mana ability's riders ("You gain 2 life.", "~ deals 2 damage to you.") after a sacrifice cost belong to the
player who activated it, not to the owner the sacrificed card is back with (603.7e-style; the 23B review fixed upkeep_draw).
The test cards are synthetic (no printed card pairs a sacrifice-self mana ability with those riders)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from tests import test_rules_wave23b_stack as W
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import build, put, roundtrip

EXTRA = [
    card("Probe Petal", set_code="tst", number="24D-P1", mana_cost="{0}", cmc=0.0, type_line="Artifact",
         oracle_text="{T}, Sacrifice this artifact: Add {G}. You gain 2 life."),
    card("Probe Thorn", set_code="tst", number="24D-P2", mana_cost="{0}", cmc=0.0, type_line="Artifact",
         oracle_text="{T}, Sacrifice this artifact: Add {G}. This artifact deals 2 damage to you."),
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + W.EXTRA + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name, delta", [("Probe Petal", 2), ("Probe Thorn", -2)])
def test_rider_goes_to_the_activator(cards, name, delta):
    s = build(cards, p1=(name,))
    c = put(s, name, "battlefield")
    W.prefs(s)
    W.p2_priority(s)
    act(s, "p1", type="set_controller", card_ids=[c.id], player="p2")
    before = {p: s.state.players[p].life for p in ("p1", "p2")}
    mana(s, "p2", C=0)
    act(s, "p2", type="activate_ability", card_id=c.id, ability=0)
    assert s.state.cards[c.id].zone == "p1:graveyard" and s.state.cards[c.id].controller == "p1"  # (back with its owner)
    assert s.state.players["p1"].life == before["p1"]
    assert s.state.players["p2"].life == before["p2"] + delta
    roundtrip(s)
