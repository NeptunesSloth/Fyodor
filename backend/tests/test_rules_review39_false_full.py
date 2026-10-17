"""Review 39: cards waves 45A-47A made FULL that played wrong (CR 2026-09-25), real Oracle text (tests/fixtures/review39_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 601.2b, 118.7b/c/f: a hybrid symbol is announced as one of its halves and a Phyrexian symbol as its colored mana before the total cost is
  determined, so a colored reduction takes it off (Morophon's ruling of 2019-06-14: {2}{W/U}{W/U} can become {2}{W}{U}, then {2}). Morophon,
  Edgewalker and Ragemonger ("reduces only the amount of colored mana you pay") and Eluge's {U} never took a hybrid or Phyrexian symbol off.
* 615.12: a prevention effect applied to damage that can't be prevented prevents none of it, but its additional effect still happens, and its
  "that many" is the damage it applied to, not the damage prevented (Polukranos 2020-01-24, Jared Carthalion True Heir 2020-11-10, Gloom Surgeon
  2012-05-01; "for each 1 damage prevented this way" stays 0: Phyrexian Hydra 2011-06-01). Under Spider-Punk Polukranos kept every counter.
* 702.195a: storied is an ability of the permanent as it is now (613): a Thorin that lost all its abilities gives no enduring story (it was read off
  the printed card).
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
from tests.test_rules_effects import pass_until_stack_empty
from tests.test_rules_permissions import cost_of
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "review39_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r39", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
EDGEWALKER, MOROPHON, ELUGE = "Edgewalker", "Morophon, the Boundless", "Eluge, the Shoreless Sea"


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def choose(s, ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def cost(s, name, pid="p1"):
    return cost_of(s, s.state.cards[card_named(s, name, pid).id], s.cards)


# ---- 601.2b, 118.7: colored reductions take hybrid and Phyrexian symbols off ------------------------------------------------------------------------
def test_edgewalker_takes_both_hybrid_symbols_off_moonrise_cleric(cards):
    s = build(cards, [EDGEWALKER, "Moonrise Cleric"], [])
    put(s, EDGEWALKER)
    assert cost(s, "Moonrise Cleric") == "{1}"  # {1}{W/B}{W/B}: announced as {1}{W}{B}, then {W}{B} less
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Moonrise Cleric").id)  # one red mana pays it
    pass_until_stack_empty(s)
    assert s.state.cards[card_named(s, "Moonrise Cleric").id].zone == "p1:battlefield"
    check(s)


def test_morophon_takes_a_phyrexian_symbol_of_its_color_off(cards):
    s = build(cards, [MOROPHON, "Porcelain Legionnaire"], [])
    mana(s, R=7)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, MOROPHON).id)
    pass_until_stack_empty(s)
    choose(s, [next(o.id for o in s.state.rules.decision.options if o.label == "Soldier" or o.id == "Soldier")])
    pass_until_stack_empty(s)
    assert cost(s, "Porcelain Legionnaire") == "{2}"  # {2}{W/P}: the {W/P} paid as {W}, which Morophon takes off (118.7f)
    check(s)


def test_eluge_takes_blue_hybrid_symbols_off_the_first_instant(cards):
    s = build(cards, [ELUGE, "Shadow of Doubt"], [])
    put(s, ELUGE)
    for land in [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:2]:
        act(s, "p1", type="move", card_ids=[land.id], to={"player": "p1", "zone": "battlefield"})
        act(s, "p1", type="set_counter", card_id=land.id, kind="flood", value=1)
    assert cost(s, "Shadow of Doubt") == "{0}"  # {U/B}{U/B} announced as {U}{U}, both taken off (no generic to fall back on)
    check(s)


# ---- 615.12: "that many" riders with damage that can't be prevented ---------------------------------------------------------------------------------
POLUKRANOS, PUNK = "Polukranos, Unchained", "Spider-Punk"


def bolt_polukranos(cards, punk):
    s = build(cards, [POLUKRANOS, PUNK, "Lightning Bolt"], [])
    mana(s, B=3, G=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, POLUKRANOS).id)
    pass_until_stack_empty(s)
    if punk:
        put(s, PUNK)
    polu = card_named(s, POLUKRANOS)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[polu.id])
    pass_until_stack_empty(s)
    return s, s.state.cards[polu.id]


def test_polukranos_prevents_the_damage_and_removes_that_many_counters(cards):
    s, polu = bolt_polukranos(cards, punk=False)
    assert polu.zone == "p1:battlefield" and polu.counters.get("+1/+1") == 3 and polu.damage == 0
    check(s)


def test_under_spider_punk_polukranos_is_dealt_the_damage_and_still_loses_that_many_counters(cards):
    s, polu = bolt_polukranos(cards, punk=True)
    assert polu.zone == "p1:graveyard"  # 3 damage dealt and 3 counters removed together: a 3/3 with 3 damage (its ruling of 2020-01-24)
    check(s)


# ---- 702.195a: storied is read off the permanent as it is ----------------------------------------------------------------------------------------
def test_thorin_without_its_abilities_gives_no_enduring_story(cards):
    s = build(cards, ["Thorin Oakenshield", "Turn to Frog", "Memnite", "Ornithopter"], [])
    thorin = put(s, "Thorin Oakenshield")
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Turn to Frog").id, targets=[thorin.id])
    pass_until_stack_empty(s)
    put(s, "Memnite")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Ornithopter").id)  # the third legendary or artifact permanent, but nothing has storied now
    pass_until_stack_empty(s)
    assert "p1" not in s.state.rules.enduring_story
    check(s)


def test_thorin_with_two_artifacts_gives_an_enduring_story(cards):
    s = build(cards, ["Thorin Oakenshield", "Memnite", "Ornithopter"], [])
    put(s, "Thorin Oakenshield")
    put(s, "Memnite")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Ornithopter").id)
    pass_until_stack_empty(s)
    assert "p1" in s.state.rules.enduring_story
    check(s)

