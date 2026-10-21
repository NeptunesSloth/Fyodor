"""CR 111.2, 608.2h: conditional attached copy and actual creation fallback."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/attached_copy_fallback_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




NAME = 'Springheart Nantuko'


def setup(cards, *, bestow=True, modifier=None):
    s = table(cards, [NAME, 'Grizzly Bears', 'Forest', 'Murder', 'Rancor', 'Phyrexian Altar', 'Raise the Alarm', "Alchemist's Refuge",
                     *([modifier] if modifier else [])], ['Crafty Cutpurse', 'Murder', 'Raise the Alarm', 'Doubling Season'], ['Crafty Cutpurse'])
    host = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, NAME, 'hand')
    mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[host.id] if bestow else [],
        **({'alt_cost': f'{source.id}:0'} if bestow else {}))
    settle(s)
    if modifier:
        put(s, modifier, 'battlefield')
    return s, source, host


def landfall(s, *, payable=True, resolve=True):
    if payable:
        mana(s, C=1, G=1)
    land = put(s, 'Forest', 'hand')
    act(s, 'p1', type='play_land', card_id=land.id)
    if resolve:
        settle(s)


def answer(s, choice):
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[choice])
    settle(s)


def token_cards(s, name=None, pid='p1'):
    return [c for c in s.state.cards.values() if c.is_token and c.controller == pid and (name is None or c.name == name)]


@pytest.mark.parametrize('name', [NAME, 'Crafty Cutpurse'])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_paid_landfall_copies_host_without_nantuko_pump_and_no_fallback(cards):
    s, source, host = setup(cards)
    assert chars(s, host).pt == (3, 3)
    landfall(s)
    answer(s, 'pay')
    made = token_cards(s, 'Grizzly Bears')
    assert len(made) == 1 and chars(s, made[0]).pt == (2, 2)
    assert not token_cards(s, 'Insect')
    assert s.state.cards[source.id].attached_to == host.id
    roundtrip(s)


@pytest.mark.parametrize('bestow,payable,decline', [(False, True, False), (True, False, False), (True, True, True)])
def test_unattached_unpayable_or_declined_landfall_creates_insect(cards, bestow, payable, decline):
    s, _, _ = setup(cards, bestow=bestow)
    landfall(s, payable=payable)
    if decline:
        answer(s, 'decline')
    assert s.state.rules.decision is None
    assert len(token_cards(s, 'Insect')) == 1
    assert not token_cards(s, 'Grizzly Bears')
    roundtrip(s)


def test_host_leaves_before_resolution_unbestows_and_creates_insect(cards):
    s, source, host = setup(cards)
    landfall(s, resolve=False)
    act(s, 'p1', type='move', card_ids=[host.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert chars(s, source).is_creature
    assert len(token_cards(s, 'Insect')) == 1
    assert not token_cards(s, 'Grizzly Bears')
    roundtrip(s)


def test_host_controller_changes_before_resolution_disallows_payment(cards):
    s, _, host = setup(cards)
    landfall(s, resolve=False)
    act(s, 'p1', type='set_controller', card_ids=[host.id], player='p2')
    settle(s)
    assert s.state.rules.decision is None
    assert len(token_cards(s, 'Insect')) == 1
    roundtrip(s)


def test_source_controller_changes_but_original_trigger_controller_still_may_pay(cards):
    s, source, _ = setup(cards)
    landfall(s, resolve=False)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    answer(s, 'pay')
    assert len(token_cards(s, 'Grizzly Bears', 'p1')) == 1
    assert not token_cards(s, 'Grizzly Bears', 'p2')
    roundtrip(s)


def test_source_leaving_before_trigger_resolution_creates_insect(cards):
    s, source, _ = setup(cards)
    landfall(s, resolve=False)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    settle(s)
    assert s.state.rules.decision is None
    assert len(token_cards(s, 'Insect')) == 1
    roundtrip(s)


@pytest.mark.parametrize('modifier,made,count', [('Doubling Season', 'Grizzly Bears', 2), ('Divine Visitation', 'Angel', 1)])
def test_replacement_tokens_count_as_actual_creation_and_suppress_fallback(cards, modifier, made, count):
    s, _, _ = setup(cards, modifier=modifier)
    landfall(s)
    answer(s, 'pay')
    assert len(token_cards(s, made)) == count
    assert not token_cards(s, 'Insect')
    roundtrip(s)


def test_empty_actual_creation_binding_does_not_satisfy_creation_predicate(cards):
    from app.rules import attached_copy_fallback, context
    from app.rules.plan import Plan

    s, _, _ = setup(cards)
    plan = Plan(s.state, 'p1', s.cards, None)
    ctx = {'controller': 'p1'}
    context.bind_objects(plan, ctx, 'copy', [])
    assert not attached_copy_fallback.created_by_you(plan, ctx, 'ref:copy')
    roundtrip(s)


def cutpurse(s, pid='p2'):
    wait_priority(s, pid)
    thief = put(s, 'Crafty Cutpurse', 'hand', pid)
    mana(s, pid=pid, C=3, U=1)
    act(s, pid, type='cast_spell', card_id=thief.id)
    settle(s)
    return thief


def test_cutpurse_changes_creator_so_failed_you_created_test_also_creates_fallback(cards):
    s, _, _ = setup(cards)
    cutpurse(s)
    landfall(s)
    answer(s, 'pay')
    assert not token_cards(s)
    assert len(token_cards(s, 'Grizzly Bears', 'p2')) == 1
    assert len(token_cards(s, 'Insect', 'p2')) == 1
    assert all(c.owner == 'p2' for c in token_cards(s, pid='p2'))
    roundtrip(s)


@pytest.mark.parametrize('original_doubling,new_doubling,count', [(True, False, 1), (False, True, 2), (True, True, 2)])
def test_creator_replacement_precedes_multipliers_and_uses_new_controllers_replacements(cards, original_doubling, new_doubling, count):
    s, _, _ = setup(cards, modifier='Doubling Season' if original_doubling else None)
    if new_doubling:
        put(s, 'Doubling Season', 'battlefield', 'p2')
    cutpurse(s)
    landfall(s)
    answer(s, 'pay')
    assert s.state.rules.decision is None  # no choice to double before changing the creator (616.1b)
    assert len(token_cards(s, 'Grizzly Bears', 'p2')) == count
    assert len(token_cards(s, 'Insect', 'p2')) == count
    assert not token_cards(s)
    roundtrip(s)


@pytest.mark.parametrize('first,last', [('p2', 'p3'), ('p3', 'p2')])
def test_multiple_cutpurse_replacements_choose_order_and_apply_once_each(cards, first, last):
    s, _, _ = setup(cards)
    cutpurse(s, 'p2')
    cutpurse(s, 'p3')
    landfall(s)
    answer(s, 'pay')
    rec = next(r for r in s.state.rules.replacements if r.get('event') == 'tokens' and r['controller'] == first)
    for name in ['Grizzly Bears', 'Insect']:
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'replace_order' and d.player == 'p1'
        option = next(k for k, cid in d.resume['map'].items() if cid == 'r:' + rec['id'])
        answer(s, option)
        assert len(token_cards(s, name, last)) == 1
    assert not token_cards(s)
    assert not token_cards(s, pid=first)
    roundtrip(s)


def test_cutpurse_effect_survives_its_source_leaving_and_expires_next_turn(cards):
    s, _, _ = setup(cards, bestow=False)
    thief = cutpurse(s)
    act(s, 'p2', type='move', card_ids=[thief.id], to={'player': 'p2', 'zone': 'graveyard'})
    landfall(s, payable=False)
    assert len(token_cards(s, 'Insect', 'p2')) == 1
    to_phase(s, 'main1', turn=2)
    wait_priority(s, 'p1')
    spell = put(s, 'Raise the Alarm', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert sum(c.quantity for c in token_cards(s, 'Soldier')) == 2
    assert not token_cards(s, 'Soldier', 'p2')
    roundtrip(s)


def test_cutpurse_does_not_replace_its_own_controllers_token_creation(cards):
    s, _, _ = setup(cards, bestow=False)
    cutpurse(s)
    wait_priority(s, 'p2')
    spell = put(s, 'Raise the Alarm', 'hand', 'p2')
    mana(s, pid='p2', C=1, W=1)
    act(s, 'p2', type='cast_spell', card_id=spell.id)
    settle(s)
    assert sum(c.quantity for c in token_cards(s, 'Soldier', 'p2')) == 2
    assert not token_cards(s)
    roundtrip(s)


def test_captured_host_is_copied_using_lki_if_sacrificed_to_mana_ability_during_payment(cards):
    s, source, host = setup(cards)
    altar = put(s, 'Phyrexian Altar', 'battlefield')
    landfall(s)
    assert s.state.rules.decision.resume['step'] == 'pay_or_sacrifice'
    act(s, 'p1', type='activate_ability', card_id=altar.id, ability=0, mana_choice='G')
    d = s.state.rules.decision
    assert d is not None
    if d.kind == 'choose_cards':
        answer(s, host.id)
    assert s.state.cards[host.id].zone == 'p1:graveyard'
    assert s.state.rules.decision.resume['step'] == 'pay_or_sacrifice'
    answer(s, 'pay')
    assert chars(s, source).is_creature  # unbestowing is checked once the resolution finishes
    made = token_cards(s, 'Grizzly Bears')
    assert len(made) == 1 and chars(s, made[0]).pt == (2, 2)
    assert not token_cards(s, 'Insect')
    roundtrip(s)


def test_phased_out_source_cannot_offer_attached_copy_payment(cards):
    s, source, _ = setup(cards)
    landfall(s, resolve=False)
    act(s, 'p1', type='phase_shift', card_ids=[source.id], out=True)
    settle(s)
    assert s.state.rules.decision is None
    assert len(token_cards(s, 'Insect')) == 1
    roundtrip(s)


def test_new_bestowed_object_of_same_card_cannot_supply_old_landfall_trigger_host(cards):
    from tests.test_rules_wave7b_activation import ability_index

    s, source, host = setup(cards)
    refuge = put(s, "Alchemist's Refuge", 'battlefield')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    landfall(s, resolve=False)
    old = s.state.rules.object_id(source.id)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, C=10, G=10, U=1)
    act(s, 'p1', type='activate_ability', card_id=refuge.id, ability=ability_index(s, refuge, 'You may cast'))
    while len(s.state.zones['stack']) > 1:
        act(s, s.state.rules.priority, type='pass_priority')
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[host.id], alt_cost=f'{source.id}:0')
    while s.state.cards[source.id].zone == 'stack':
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.rules.object_id(source.id) != old
    assert s.state.cards[source.id].attached_to == host.id
    settle(s)
    assert s.state.rules.decision is None
    assert len(token_cards(s, 'Insect')) == 1
    assert not token_cards(s, 'Grizzly Bears')
    roundtrip(s)
