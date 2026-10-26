"""Wave 110I session 11: Ore-Rich Stalactite // Cosmium Catalyst (702.167a craft materials, random pick, free cast from exile)."""
from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, check, life, mana, put
from tests.wave110a_kit import answer

STAL = ("{T}: Add {R}. Spend this mana only to cast an instant or sorcery spell.\nCraft with four or more red instant and/or sorcery cards {3}{R}{R} ({3}{R}{R}, "
        "Exile this artifact, Exile the four or more from your graveyard: Return this card transformed under its owner's control. Craft only as a sorcery.)")
CAT = "{1}{R}, {T}: Choose an exiled card used to craft this artifact at random. You may cast that card without paying its mana cost."
NAME = "Ore-Rich Stalactite // Cosmium Catalyst"
EXTRA = [card(NAME, set_code="tst", number="S1", layout="transform", mana_cost="{1}{R} // ", cmc=2.0, type_line="Artifact // Artifact", colors=["R"], color_identity=["R"],
              image_uris=None, keywords=[],
              card_faces=[{"name": "Ore-Rich Stalactite", "mana_cost": "{1}{R}", "type_line": "Artifact", "oracle_text": STAL, "colors": ["R"]},
                          {"name": "Cosmium Catalyst", "mana_cost": "", "type_line": "Artifact", "oracle_text": CAT, "colors": ["R"]}]),
         real("Shock Probe", "{R}", 1, "Instant", "Shock Probe deals 2 damage to any target.", None, "R")]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == "FULL"


def test_cosmium_catalyst(cards):
    """The four crafted Shock Probes are the exiled cards used to craft it: the Catalyst picks one at random and its controller may cast it for free (Bob takes 2)."""
    s = build(cards, [NAME, *["Shock Probe"] * 5])
    stal = put(s, NAME)
    probes = [c for c in s.state.cards.values() if c.name == "Shock Probe" and c.owner == "p1"]
    for c in probes[:4]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, "p1", R=2, C=3)
    act(s, "p1", type="activate_ability", card_id=stal.id, ability=1, cost_choices=[{"component": 2, "cards": [c.id for c in probes[:4]]}])
    answer(s)
    assert s.state.cards[stal.id].face == 1 and all(s.state.cards[c.id].zone == "p1:exile" for c in probes[:4])
    mana(s, "p1", R=1, C=1)
    act(s, "p1", type="activate_ability", card_id=stal.id, ability=0)
    answer(s, None, "p2")  # (the one card offered, then the target)
    assert life(s, "p2") == 38 and sum(c.zone == "p1:exile" for c in probes[:4]) == 3
    check(s)
