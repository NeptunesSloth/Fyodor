"""Wave 23B: abilities on the stack as objects (CR 113.7, 115.1, 701.6a, 707.10), researched against the stored Comprehensive Rules.

* 707.10 / 603.2: "Whenever you activate an ability that targets a creature or player, copy that ability. You may choose new targets
  for the copy." (Ertha Jo); "Whenever an ability of equipped creature is activated, if it isn't a mana ability, copy that ability"
  (Illusionist's Bracers); "Copy target triggered ability you control twice." (Mister Fantastic). The copy isn't activated or cast
  (707.10), so it doesn't trigger these again; a mana ability never uses the stack (605.3b).
Real Oracle text; each scenario replays the history and survives a save/load round trip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_suspend import until
from tests.test_rules_wave9b_exile_permission import answer, build, put, roundtrip

EXTRA = [
    card('Ertha Jo, Frontier Mentor', set_code='tst', number='S01', mana_cost='{2}{R}{W}', cmc=4.0, type_line='Legendary Creature — Kor Advisor', oracle_text='When Ertha Jo enters, create a 1/1 white Kor Soldier creature token.\nWhenever you activate an ability that targets a creature or player, copy that ability. You may choose new targets for the copy.', power='2', toughness='4', colors=['R', 'W'], color_identity=['R', 'W']),  # noqa: E501
    card("Illusionist's Bracers", set_code='tst', number='S02', mana_cost='{2}', cmc=2.0, type_line='Artifact — Equipment', oracle_text="Whenever an ability of equipped creature is activated, if it isn't a mana ability, copy that ability. You may choose new targets for the copy.\nEquip {3}"),  # noqa: E501
    card("Battlemage's Bracers", set_code='tst', number='S03', mana_cost='{1}', cmc=1.0, type_line='Artifact — Equipment', oracle_text="Equipped creature gets +1/+1.\nWhenever an ability of equipped creature is activated, if it isn't a mana ability, you may pay {1}. If you do, copy that ability. You may choose new targets for the copy.\nEquip {3}"),  # noqa: E501
    card('Mister Fantastic', set_code='tst', number='S04', mana_cost='{R}{G}{W}{U}', cmc=4.0, type_line='Legendary Creature — Human Scientist Hero', oracle_text='Defender\n{R}{G}{W}{U}, {T}: Copy target triggered ability you control twice. You may choose new targets for the copies.', power='2', toughness='3', colors=['G', 'R', 'U', 'W'], color_identity=['G', 'R', 'U', 'W'], keywords=['Defender']),  # noqa: E501
    card('Rod of Ruin', set_code='tst', number='S05', mana_cost='{4}', cmc=4.0, type_line='Artifact', oracle_text='{3}, {T}: Rod of Ruin deals 1 damage to any target.'),  # noqa: E501
    card('Test Pinger', set_code='tst', number='S06', mana_cost='{2}', cmc=2.0, type_line='Creature — Human', oracle_text='Haste\n{T}: Test Pinger deals 1 damage to any target.', power='1', toughness='1', colors=[], color_identity=[], keywords=['Haste']),  # noqa: E501
    card('Test Dork', set_code='tst', number='S10', mana_cost='{1}', cmc=1.0, type_line='Creature — Elf', oracle_text='Haste\n{T}: Add {G}.', power='1', toughness='1', colors=[], color_identity=[], keywords=['Haste']),  # noqa: E501
    card('Test Tremors', set_code='tst', number='S07', mana_cost='{2}', cmc=2.0, type_line='Enchantment', oracle_text='Whenever a creature you control enters, this enchantment deals 1 damage to each opponent.'),  # noqa: E501
    card('Test Fodder', set_code='tst', number='S08', mana_cost='{1}', cmc=1.0, type_line='Creature — Elf', oracle_text='', power='1', toughness='1', colors=[], color_identity=[]),  # noqa: E501
    card('Test Ox', set_code='tst', number='S09', mana_cost='{2}', cmc=2.0, type_line='Creature — Ox', oracle_text='', power='3', toughness='3', colors=[], color_identity=[]),  # noqa: E501
]
FULL = ["Ertha Jo, Frontier Mentor", "Illusionist's Bracers", "Battlemage's Bracers", "Mister Fantastic"]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def life(s, pid):
    return s.state.players[pid].life


# -- Ertha Jo: an ability that targets a creature or player (707.10) -----------------------------------------------------------
def test_ertha_jo_copies_an_ability_that_targets_a_player(cards):
    s = build(cards, p1=("Ertha Jo, Frontier Mentor", "Rod of Ruin"))
    put(s, "Ertha Jo, Frontier Mentor", "battlefield")
    rod = put(s, "Rod of Ruin", "battlefield")
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=rod.id, ability=0, targets=["p2"])
    answer(s)  # the trigger (603.2), the copy (707.10); the copy keeps its target ("choose new targets": decline)
    assert life(s, "p2") == 38  # the ability and its copy
    roundtrip(s)


def test_ertha_jo_ignores_a_mana_ability_and_a_targetless_one(cards):
    s = build(cards, p1=("Ertha Jo, Frontier Mentor", "Test Pinger", "Test Dork"))
    put(s, "Ertha Jo, Frontier Mentor", "battlefield")
    elves = put(s, "Test Dork", "battlefield")
    act(s, "p1", type="activate_ability", card_id=elves.id, ability=1)  # {T}: Add {G} (605.3b: no stack, nothing to copy)
    assert not s.state.zones.get("stack")
    roundtrip(s)


# -- Illusionist's Bracers: an ability of the equipped creature -----------------------------------------------------------------
def _equip(s, gear, creature):
    from app.rules import characteristics as chars
    from app.rules.layers import derive

    c = s.state.cards[gear.id]
    equip = next(a for a in derive(s.state, c, chars.of(c, s.cards), s.cards).abilities if "equip" in a.keywords)
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=gear.id, ability=equip.index, targets=[creature.id])
    answer(s)
    assert s.state.cards[gear.id].attached_to == creature.id


def test_bracers_copy_the_equipped_creatures_ability(cards):
    s = build(cards, p1=("Illusionist's Bracers", "Test Pinger"))
    gear = put(s, "Illusionist's Bracers", "battlefield")
    pinger = put(s, "Test Pinger", "battlefield")
    _equip(s, gear, pinger)
    act(s, "p1", type="activate_ability", card_id=pinger.id, ability=1, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 38
    roundtrip(s)


def test_bracers_do_nothing_for_an_unequipped_creature(cards):
    s = build(cards, p1=("Illusionist's Bracers", "Test Pinger", "Test Ox"))
    put(s, "Illusionist's Bracers", "battlefield")
    pinger = put(s, "Test Pinger", "battlefield")
    act(s, "p1", type="activate_ability", card_id=pinger.id, ability=1, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 39
    roundtrip(s)


def _battlemages(cards, pick):
    s = build(cards, p1=("Battlemage's Bracers", "Test Pinger"))
    gear = put(s, "Battlemage's Bracers", "battlefield")
    pinger = put(s, "Test Pinger", "battlefield")
    _equip(s, gear, pinger)
    mana(s, C=1)  # (before the trigger resolves: the payment is made as it does)
    act(s, "p1", type="activate_ability", card_id=pinger.id, ability=1, targets=["p2"])
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id in (pick, "keep"))])  # (new targets: keep)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return s


def test_battlemages_bracers_pay_for_the_copy(cards):
    s = _battlemages(cards, "pay")
    assert life(s, "p2") == 38 and s.state.players["p1"].mana == {}
    roundtrip(s)


def test_battlemages_bracers_decline_the_copy(cards):
    s = _battlemages(cards, "decline")
    assert life(s, "p2") == 39 and s.state.players["p1"].mana == {"C": 1}
    roundtrip(s)


# -- Mister Fantastic: a triggered ability you control, twice ---------------------------------------------------------------
def test_mister_fantastic_copies_a_triggered_ability_twice(cards):
    s = build(cards, p1=("Mister Fantastic", "Test Tremors", "Test Fodder"))
    mf = put(s, "Mister Fantastic", "battlefield")
    put(s, "Test Tremors", "battlefield")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")  # (no longer summoning sick)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack)
    fodder = put(s, "Test Fodder", "hand")
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=fodder.id)
    for _ in range(4):  # the creature spell resolves; Tremors triggers (603.2): one damage to each opponent, on the stack
        act(s, s.state.rules.priority, type="pass_priority")
        if any(s.state.cards[c].ability is not None for c in s.state.zones.get("stack", [])):
            break
    (trigger,) = s.state.zones["stack"]
    mana(s, R=1, G=1, W=1, U=1)
    act(s, "p1", type="activate_ability", card_id=mf.id, ability=1, targets=[trigger])
    answer(s)
    assert life(s, "p2") == 37  # the trigger and its two copies (707.10)
    roundtrip(s)
