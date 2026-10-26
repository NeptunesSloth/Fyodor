"""Wave 110I s10.

* 702.145c, 701.28, 303.4f: Curse of Leeches turning over (day returns) is attached by its controller to a player they choose, before state-based actions
  (704.5m) could put the unattached Aura into the graveyard; its upkeep trigger then drains the enchanted player.
"""
from __future__ import annotations

import pytest

from tests.fixtures.cards import card
from tests.game_helpers import act
from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import fixture_cards
from tests.test_rules_designations import REAL, build, find, put, resolve, roundtrip
from tests.test_rules_effects import mana, run_until

CURSE = ("Enchant player\nAs this permanent transforms into Curse of Leeches, attach it to a player.\nAt the beginning of enchanted player's upkeep, "
         "they lose 1 life and you gain 1 life.\nDaybound (If a player casts no spells during their own turn, it becomes night next turn.)")
LURKER = "Lifelink\nNightbound (If a player casts at least two spells during their own turn, it becomes day next turn.)"
EXTRA = [card("Curse of Leeches // Leeching Lurker", set_code="tst", number="L1", layout="transform", mana_cost="{2}{B}", cmc=3.0,
              type_line="Enchantment — Aura Curse // Creature — Leech Horror", colors=["B"], color_identity=["B"], image_uris=None,
              card_faces=[{"object": "card_face", "name": "Curse of Leeches", "mana_cost": "{2}{B}", "type_line": "Enchantment — Aura Curse", "oracle_text": CURSE, "colors": ["B"]},
                          {"object": "card_face", "name": "Leeching Lurker", "mana_cost": "", "type_line": "Creature — Leech Horror", "oracle_text": LURKER,
                           "power": "2", "toughness": "2", "colors": ["B"]}])]
NAME = EXTRA[0]["name"]


@pytest.fixture()
def card_db(settings):
    return settings.cards_db_path


@pytest.fixture()
def cards(settings, card_db):
    build_database(fixture_cards() + REAL + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(card_db, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("target", ["p1", "p2"])
def test_curse_of_leeches(cards, target):
    """Night falls (Alice cast nothing), then Bob casts two spells: in Alice's untap step the Lurker turns back into the Curse and Alice picks the player
    it enchants before state-based actions; the Curse stays and drains that player in their upkeep."""
    from tests.wave9c_kit import check

    s = build(cards, [NAME], bob=[(2, "Opt"), (10, "Island")])
    curse = put(s, NAME, "battlefield")
    act(s, "p1", type="attach", card_ids=[curse.id], to="p2")
    run_until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    assert s.state.table.day_night == "night" and s.state.cards[curse.id].face == 1 and not s.state.cards[curse.id].attached_player
    for opt in [c for c in s.state.cards.values() if c.name == "Opt" and c.owner == "p2"]:
        act(s, "p2", type="move", card_ids=[opt.id], to={"player": "p2", "zone": "hand"})
        mana(s, "p2", U=1)
        act(s, "p2", type="cast_spell", card_id=opt.id)
        resolve(s, [])
    run_until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "choose_one" and "attach" in s.state.rules.decision.prompt)
    d = s.state.rules.decision
    assert d.player == "p1" and {o.id for o in d.options} == {"p1", "p2"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[target])
    c = s.state.cards[curse.id]
    assert s.state.table.day_night == "day" and c.face == 0 and c.zone == "p1:battlefield" and c.attached_player == target
    roundtrip(s)
    check(s)
