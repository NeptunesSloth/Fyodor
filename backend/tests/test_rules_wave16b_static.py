"""Wave 16B (the static_other long tail, continued). Real Oracle text, replay and save/load for each.

* 702.69a: Gravestorm (a copy for each permanent put into a graveyard from the battlefield this turn).
* 702.127a: Aftermath (the half is cast only from a graveyard; exiled instead of going anywhere else as it leaves the stack).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card("Consign // Oblivion", set_code="tst", number="B01", layout="split", mana_cost="{1}{U} // {4}{B}", cmc=7.0,
         type_line="Instant // Sorcery — Aftermath", colors=["B", "U"], color_identity=["B", "U"], image_uris=None,
         card_faces=[
             {"object": "card_face", "name": "Consign", "mana_cost": "{1}{U}", "type_line": "Instant", "colors": ["U"],
              "oracle_text": "Return target nonland permanent to its owner's hand."},
             {"object": "card_face", "name": "Oblivion", "mana_cost": "{4}{B}", "type_line": "Sorcery — Aftermath", "colors": ["B"],
              "oracle_text": "Aftermath (Cast this spell only from your graveyard. Then exile it.)\nTarget opponent discards two cards."}]),
    card("Ominous Harvest", set_code="tst", number="B02", mana_cost="{1}{B}", cmc=2.0, type_line="Sorcery", colors=["B"],
         color_identity=["B"], oracle_text="Gravestorm (When you cast this spell, copy it for each permanent put into a graveyard "
         "from the battlefield this turn.)\nTarget player draws a card and loses 1 life."),
    card("Test Small", set_code="tst", number="B03", mana_cost="{G}", cmc=1.0, type_line="Creature — Elf", power="2", toughness="2",
         colors=["G"], color_identity=["G"], oracle_text=""),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_aftermath_half_only_from_the_graveyard_then_exiled(cards):
    s = build(cards, p1=("Consign // Oblivion",))
    c = put(s, "Consign // Oblivion", "hand")
    mana(s, C=2, B=3)
    with pytest.raises(ActionError):  # 702.127a: not from the hand
        act(s, "p1", type="cast_spell", card_id=c.id, face=1, targets=["p2"])
    put(s, "Consign // Oblivion", "graveyard")
    with pytest.raises(ActionError):  # the first half has no flashback: only the aftermath half is cast from there
        act(s, "p1", type="cast_spell", card_id=c.id, face=0, targets=[])
    ids = [x for x in s.state.zones["p2:library"][:3]]
    act(s, "p2", type="move", card_ids=ids, to={"player": "p2", "zone": "hand"})
    hand_before = len(s.state.zones["p2:hand"])
    act(s, "p1", type="cast_spell", card_id=c.id, face=1, targets=["p2"])
    answer(s)
    assert len(s.state.zones["p2:hand"]) == hand_before - 2
    assert find(s, "Consign // Oblivion").zone == "p1:exile"  # 702.127a: exiled instead of put anywhere else
    roundtrip(s)


def test_gravestorm_copies_for_each_permanent_that_went_to_a_graveyard(cards):
    s = build(cards, p1=("Ominous Harvest", "Test Small"))
    put(s, "Test Small", "battlefield")
    put(s, "Test Small", "graveyard")  # (a permanent put into a graveyard from the battlefield this turn)
    c = put(s, "Ominous Harvest", "hand")
    life, hand = s.state.players["p2"].life, len(s.state.zones["p2:hand"])
    mana(s, C=1, B=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    answer(s)
    assert s.state.players["p2"].life == life - 2 and len(s.state.zones["p2:hand"]) == hand + 2  # the spell and one copy
    roundtrip(s)
