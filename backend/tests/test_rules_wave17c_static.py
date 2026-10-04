"""Wave 17C (the static_other long tail, third pass). Real Oracle text, replay and save/load for each.

* 702.21a: ward costs that aren't mana alone, granted by a static ("Other creatures you control have "Ward—Pay 2 life."") or
  printed with two parts ("Ward—{2}, Pay 2 life.").
* 614.12 / 702.136a: riot granted to the permanents a static names ("Nontoken creatures you control have riot.").
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
    card("Test Small", set_code="tst", number="C01", mana_cost="{G}", cmc=1.0, type_line="Creature — Elf", power="2", toughness="2",
         colors=["G"], color_identity=["G"], oracle_text=""),
    card("Rhythm of the Wild", set_code="tst", number="C02", mana_cost="{1}{R}{G}", cmc=3.0, type_line="Enchantment",
         colors=["G", "R"], color_identity=["G", "R"],
         oracle_text="Creature spells you control can't be countered.\nNontoken creatures you control have riot. (They enter with your "
         "choice of a +1/+1 counter or haste.)"),
    card("Flame Jab", set_code="tst", number="C07", mana_cost="{R}", cmc=1.0, type_line="Sorcery", colors=["R"], color_identity=["R"],
         oracle_text="Flame Jab deals 1 damage to any target.\nRetrace (You may cast this card from your graveyard by discarding a "
         "land card in addition to paying its other costs.)"),
    card("Deeproot Historian", set_code="tst", number="C08", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Merfolk Druid",
         power="2", toughness="2", colors=["G"], color_identity=["G"],
         oracle_text="Merfolk and Druid cards in your graveyard have retrace. (You may cast cards with retrace from your graveyard "
         "by discarding a land card in addition to paying their other costs.)"),
    card("Six", set_code="tst", number="C09", mana_cost="{2}{G}", cmc=3.0, type_line="Legendary Creature — Elemental Spirit Tortoise",
         power="2", toughness="4", colors=["G"], color_identity=["G"],
         oracle_text="Reach\nWhenever Six attacks, mill three cards. You may put a land card from among them into your hand.\n"
         "During your turn, nonland permanent cards in your graveyard have retrace. (You may cast permanent cards from your "
         "graveyard by discarding a land card in addition to paying their other costs.)"),
    card("Hexing Squelcher", set_code="tst", number="C05", mana_cost="{1}{R}", cmc=2.0, type_line="Creature — Goblin Sorcerer",
         power="2", toughness="2", colors=["R"], color_identity=["R"],
         oracle_text="This spell can't be countered.\nWard—Pay 2 life.\nSpells you control can't be countered.\nOther creatures you control have \"Ward—Pay 2 life.\""),
    card("Gisa, the Hellraiser", set_code="tst", number="C06", mana_cost="{3}{B}{B}", cmc=5.0,
         type_line="Legendary Creature — Human Warlock", power="4", toughness="4", colors=["B"], color_identity=["B"],
         oracle_text="Ward—{2}, Pay 2 life.\nSkeletons and Zombies you control get +1/+1 and have menace.\nWhenever you commit a "
         "crime, create two tapped 2/2 blue and black Zombie Rogue creature tokens. This ability triggers only once each turn. "
         "(Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)"),
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


def _bolt(cards, target, p2, extra_mana=None):
    s = build(cards, p1=("Lightning Bolt",), p2=p2)
    for n in p2:
        put(s, n, "battlefield", "p2")
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1, **(extra_mana or {}))
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[find(s, target, "p2").id])
    d = s.state.rules.decision
    while d is not None and d.player != "p1":  # (the ward trigger goes on the stack first)
        act(s, "p1", type="pass_priority")
        d = s.state.rules.decision
    return s, d


def test_granted_ward_pay_life_counters_unless_paid(cards):
    s, _ = _bolt(cards, "Test Small", ("Hexing Squelcher", "Test Small"))
    for _ in range(6):  # 702.21a: the granted ward triggers as the Bolt targets Test Small (not Squelcher: its own, printed)
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and "2 life" in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["decline"])
    answer(s)
    assert find(s, "Test Small", "p2").zone == "p2:battlefield" and s.state.players["p1"].life == 40  # countered
    roundtrip(s)


def test_ward_mana_and_life_two_part_cost(cards):
    s, _ = _bolt(cards, "Gisa, the Hellraiser", ("Gisa, the Hellraiser",), {"C": 2})
    for _ in range(6):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and "2 life" in d.prompt and "{2}" in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    answer(s)
    assert s.state.players["p1"].life == 38  # 702.21a: both parts of the cost, {2} and 2 life
    assert find(s, "Gisa, the Hellraiser", "p2").damage == 3
    roundtrip(s)


def test_granted_riot_asks_on_entering(cards):
    s = build(cards, p1=("Rhythm of the Wild", "Test Small"))
    put(s, "Rhythm of the Wild", "battlefield")
    c = put(s, "Test Small", "hand")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s, limit=30)
    got = find(s, "Test Small")
    assert got.zone == "p1:battlefield" and got.counters.get("+1/+1") == 1  # 702.136a (the first option: the counter)
    roundtrip(s)


def test_retrace_cast_from_graveyard_discarding_a_land(cards):
    s = build(cards, p1=("Flame Jab",))
    jab = put(s, "Flame Jab", "graveyard")
    forest = next(c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "hand"})
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=jab.id, targets=["p2"])
    answer(s)
    assert s.state.players["p2"].life == 39  # 702.81a
    assert s.state.cards[forest.id].zone == "p1:graveyard" and s.state.cards[jab.id].zone == "p1:graveyard"
    with pytest.raises(ActionError):  # no land card left in hand to discard
        mana(s, R=1)
        act(s, "p1", type="cast_spell", card_id=jab.id, targets=["p2"])
    roundtrip(s)


def test_granted_retrace_for_the_named_cards_only(cards):
    s = build(cards, p1=("Deeproot Historian", "Deeproot Historian", "Test Small"))
    hs = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Deeproot Historian"]
    act(s, "p1", type="move", card_ids=[hs[0].id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[hs[1].id], to={"player": "p1", "zone": "graveyard"})
    elf = put(s, "Test Small", "graveyard")
    forest = next(c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "hand"})
    mana(s, G=2, C=1)
    with pytest.raises(ActionError):  # an Elf is neither a Merfolk nor a Druid
        act(s, "p1", type="cast_spell", card_id=elf.id)
    act(s, "p1", type="cast_spell", card_id=hs[1].id)  # 702.81a: a Merfolk Druid has retrace from the other one
    answer(s)
    assert s.state.cards[hs[1].id].zone == "p1:battlefield" and s.state.cards[forest.id].zone == "p1:graveyard"
    roundtrip(s)
