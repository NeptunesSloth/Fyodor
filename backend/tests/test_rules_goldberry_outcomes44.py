"""Canonical Goldberry native movement and accepted resolution-payment proofs."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.rules import effects
from app.rules import goldberry_outcomes44 as leaf
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, row in enumerate(json.loads((Path(__file__).parent / 'fixtures/goldberry_outcomes44_cards.json').read_text())):
        base[row['name']] = card(row['name'], set_code='gbk', number=str(i), **{
            ('card_faces' if k == 'faces' else k): v for k, v in row.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = ['Goldberry, River-Daughter', 'Grizzly Bears', 'Vorinclex, Monstrous Raider', 'Solemnity', 'Swords to Plowshares', 'Abundance', 'Fear of Sleep Paralysis', 'Cloudshift', 'Metallic Mimic']
    s = table(cards, names, names, names)
    return s, put(s, 'Goldberry, River-Daughter', 'battlefield'), put(s, 'Grizzly Bears', 'battlefield')


def body(s, source, target, mode):
    plan = Plan(s.state, 'p1', s.cards, None)
    ctx = {'controller': 'p1', 'source_card': source.id, 'source_object': plan.oid(source),
           'name': 'Explicit Goldberry kernel', 'stack_id': '', 'next': 0, 'body_done': {'do': 'noop'},
           'effects': [{'do': leaf.STEP, 'mode': mode}],
           'targets': [{'id': target.id, 'object_id': plan.oid(target)}]}
    effects.continue_effects(plan, ctx)
    return GameSession(plan.state, cards=s.cards)


def test_staged_collect_original_kind_difference_exactly_one_each(cards):
    s, gold, bear = setup(cards)
    for obj, kind, n in [(gold, '+1/+1', 2), (bear, '+1/+1', 3), (bear, 'loyalty', 4), (bear, 'stun', 2)]:
        act(s, 'p1', type='set_counter', card_id=obj.id, kind=kind, value=n)
    s = body(s, gold, bear, 'collect')
    assert s.state.rules.decision is None
    assert s.state.cards[gold.id].counters == {'+1/+1': 2, 'loyalty': 1, 'stun': 1}
    assert s.state.cards[bear.id].counters == {'+1/+1': 3, 'loyalty': 3, 'stun': 1}


def test_staged_mandatory_move_modified_to_zero_still_draws_once(cards):
    s, gold, bear = setup(cards)
    act(s, 'p1', type='set_counter', card_id=gold.id, kind='+1/+1', value=1)
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield', pid='p2')
    before = len(s.state.zones['p1:hand'])
    s = body(s, gold, bear, 'pay')
    # One available counter forces the mandatory minimum without an optional zero.
    assert s.state.rules.decision is None
    assert s.state.cards[gold.id].counters.get('+1/+1', 0) == 0
    assert s.state.cards[bear.id].counters.get('+1/+1', 0) == 0
    assert len(s.state.zones['p1:hand']) == before + 1


def test_staged_impossible_destination_does_not_start_payment_or_draw(cards):
    s, gold, bear = setup(cards)
    act(s, 'p1', type='set_counter', card_id=gold.id, kind='+1/+1', value=1)
    put(s, 'Solemnity', 'battlefield', pid='p2')
    before = len(s.state.zones['p1:hand'])
    s = body(s, gold, bear, 'pay')
    assert s.state.rules.decision is None
    assert s.state.cards[gold.id].counters.get('+1/+1') == 1
    assert len(s.state.zones['p1:hand']) == before


def test_staged_actual_cast_tap_collect_and_blue_tap_payment_draw(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import to_phase

    names = ['Goldberry, River-Daughter', 'Grizzly Bears', 'Vorinclex, Monstrous Raider', 'Solemnity', 'Swords to Plowshares', 'Abundance', 'Fear of Sleep Paralysis', 'Cloudshift', 'Metallic Mimic']
    s = table(cards, names, names, names)
    gold = put(s, 'Goldberry, River-Daughter', 'hand')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    mana(s, C=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=gold.id)
    settle(s)
    assert s.state.cards[gold.id].zone == 'p1:battlefield'
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[gold.id]).pt == (1, 3)
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='set_counter', card_id=bear.id, kind='charge', value=2)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=gold.id, ability=0, targets=[bear.id])
    settle(s)
    assert s.state.cards[gold.id].tapped and s.state.cards[gold.id].counters.get('charge') == 1
    assert s.state.cards[bear.id].counters.get('charge') == 1
    to_phase(s, 'main1', turn=7)
    mana(s, U=1)
    before = len(s.state.zones['p1:hand'])
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=gold.id, ability=1, targets=[bear.id])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[gold.id].tapped and not s.state.cards[gold.id].counters.get('charge')
    assert s.state.cards[bear.id].counters.get('charge') == 2
    assert len(s.state.zones['p1:hand']) == before + 1


@pytest.mark.parametrize('failure', ['sick', 'tapped', 'mana', 'self', 'opponent'])
def test_staged_actual_activation_negative_cost_and_target_preflight_is_atomic(cards, failure):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_wave30m_durations import to_phase

    s, gold, bear = setup(cards)
    if failure != 'sick':
        to_phase(s, 'main1', turn=4)
    if failure != 'mana':
        mana(s, U=1)
    if failure == 'tapped':
        act(s, 'p1', type='tap', card_ids=[gold.id], tapped=True)
    target = gold if failure == 'self' else put(s, 'Grizzly Bears', 'battlefield', pid='p2') if failure == 'opponent' else bear
    wait_priority(s, 'p1')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=gold.id, ability=1, targets=[target.id])
    assert s.state.model_dump(mode='json') == before


def test_staged_actual_no_counter_payment_still_spends_activation_blue_and_tap(cards):
    from app.rules import mana_units
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import to_phase

    s, gold, bear = setup(cards)
    to_phase(s, 'main1', turn=4)
    mana(s, U=1)
    before = len(s.state.zones['p1:hand'])
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=gold.id, ability=1, targets=[bear.id])
    settle(s)
    assert s.state.cards[gold.id].tapped and mana_units.visible_pool(s.state, 'p1') == {}
    assert len(s.state.zones['p1:hand']) == before


def test_staged_actual_mandatory_quantity_refuses_zero_then_moves_one_and_draws(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import to_phase

    s, gold, bear = setup(cards)
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='set_counter', card_id=gold.id, kind='charge', value=2)
    mana(s, U=1)
    before_hand = len(s.state.zones['p1:hand'])
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=gold.id, ability=1, targets=[bear.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'counter_amounts'
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[], name='0')
    assert s.state.model_dump(mode='json') == before
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[], name='1')
    settle(s)
    assert s.state.cards[gold.id].counters.get('charge') == 1
    assert s.state.cards[bear.id].counters.get('charge') == 1
    assert len(s.state.zones['p1:hand']) == before_hand + 1


@pytest.mark.parametrize('mode', [0, 1])
@pytest.mark.parametrize('removed', ['source', 'target'])
def test_staged_actual_departure_before_resolution_never_moves_or_draws(cards, mode, removed):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle
    from tests.test_rules_linked_aggregates import cast
    from tests.test_rules_wave30m_durations import to_phase

    s, gold, bear = setup(cards)
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    payer = bear if mode == 0 else gold
    act(s, 'p1', type='set_counter', card_id=payer.id, kind='charge', value=1)
    mana(s, U=1)
    before = len(s.state.zones['p1:hand'])
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=gold.id, ability=mode, targets=[bear.id])
    removal = put(s, 'Swords to Plowshares', 'hand')
    victim = gold if removed == 'source' else bear
    cast(s, removal, targets=[victim.id])
    settle(s)
    assert s.state.cards[victim.id].zone == 'p1:exile'
    remaining = bear if removed == 'source' else gold
    assert s.state.cards[remaining.id].counters.get('charge', 0) == (1 if remaining.id == payer.id else 0)
    assert len(s.state.zones['p1:hand']) == before


@pytest.mark.parametrize('double_first', [False, True])
def test_staged_actual_cold_move_replacement_put_zero_or_one_both_draw_one(cards, tmp_path, double_first):
    from tests.native_counter44 import cold_choose
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import to_phase

    s, gold, bear = setup(cards)
    to_phase(s, 'main1', turn=4)
    own = put(s, 'Vorinclex, Monstrous Raider', 'battlefield')
    other = put(s, 'Vorinclex, Monstrous Raider', 'battlefield', pid='p2')
    act(s, 'p1', type='set_counter', card_id=gold.id, kind='charge', value=1)
    mana(s, U=1)
    before = len(s.state.zones['p1:hand'])
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=gold.id, ability=1, targets=[bear.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['site'] == 'counter_move_commit'
    assert s.state.cards[gold.id].counters.get('charge') == 1
    preferred = s.state.rules.object_id(own.id if double_first else other.id)
    option = next(o.id for o in d.options if preferred in d.resume['map'][o.id])
    s = cold_choose(s, cards, tmp_path, [option])
    settle(s)
    assert not s.state.cards[gold.id].counters.get('charge')
    assert s.state.cards[bear.id].counters.get('charge', 0) == (1 if double_first else 0)
    assert len(s.state.zones['p1:hand']) == before + 1


def test_staged_actual_cold_mixed_quantity_zero_one_kind_forces_other_kind_payment(cards, tmp_path):
    from tests.native_counter44 import cold_choose
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import to_phase

    s, gold, bear = setup(cards)
    to_phase(s, 'main1', turn=4)
    for kind, n in [('charge', 2), ('stun', 1)]:
        act(s, 'p1', type='set_counter', card_id=gold.id, kind=kind, value=n)
    mana(s, U=1)
    before = len(s.state.zones['p1:hand'])
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=gold.id, ability=1, targets=[bear.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['kind'] == 'charge'
    assert d.resume['then']['source_refs'][0]['object_id'] == s.state.rules.object_id(gold.id)
    assert d.resume['then']['destination_ref']['object_id'] == s.state.rules.object_id(bear.id)
    s = cold_choose(s, cards, tmp_path, [], name='0')
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[gold.id].counters.get('charge') == 2 and not s.state.cards[gold.id].counters.get('stun')
    assert s.state.cards[bear.id].counters.get('stun') == 1
    assert len(s.state.zones['p1:hand']) == before + 1


def test_staged_actual_cold_draw_replacement_does_not_repeat_move_payment(cards, tmp_path):
    from tests.native_counter44 import cold_choose
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import to_phase

    s, gold, bear = setup(cards)
    to_phase(s, 'main1', turn=4)
    put(s, 'Abundance', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=gold.id, kind='charge', value=1)
    mana(s, U=1)
    before = len(s.state.zones['p1:hand'])
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=gold.id, ability=1, targets=[bear.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and any(o.id == 'decline' for o in d.options)
    assert not s.state.cards[gold.id].counters.get('charge') and s.state.cards[bear.id].counters.get('charge') == 1
    s = cold_choose(s, cards, tmp_path, ['decline'])
    settle(s)
    assert s.state.rules.decision is None
    assert not s.state.cards[gold.id].counters.get('charge') and s.state.cards[bear.id].counters.get('charge') == 1
    assert len(s.state.zones['p1:hand']) == before + 1


@pytest.mark.parametrize('ability', [0, 1])
def test_staged_actual_fear_forbidden_stun_movement_never_starts_payment(cards, ability):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import to_phase

    s, gold, bear = setup(cards)
    to_phase(s, 'main1', turn=4)
    put(s, 'Fear of Sleep Paralysis', 'battlefield', pid='p2')
    settle(s)
    source = bear if ability == 0 else gold
    act(s, 'p1', type='set_counter', card_id=source.id, kind='stun', value=1)
    mana(s, U=1)
    before = len(s.state.zones['p1:hand'])
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=gold.id, ability=ability, targets=[bear.id])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[gold.id].tapped
    assert s.state.cards[source.id].counters.get('stun') == 1
    assert len(s.state.zones['p1:hand']) == before


@pytest.mark.parametrize('ability', [0, 1])
def test_actual_blinked_source_with_new_entry_counters_is_not_original_move_object(cards, ability):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import to_phase

    s, gold, bear = setup(cards)
    mimic = put(s, 'Metallic Mimic', 'hand')
    mana(s, C=2)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=mimic.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['Nymph'])
    settle(s)
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='set_counter', card_id=bear.id if ability == 0 else gold.id, kind='charge', value=1)
    original = s.state.rules.object_id(gold.id)
    mana(s, U=1, W=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=gold.id, ability=ability, targets=[bear.id])
    blink = put(s, 'Cloudshift', 'hand')
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='cast_spell', card_id=blink.id, targets=[gold.id])
    settle(s)
    assert s.state.rules.decision is None and s.state.rules.object_id(gold.id) != original
    assert s.state.cards[gold.id].counters == {'+1/+1': 1}
    assert s.state.cards[bear.id].counters.get('charge', 0) == (1 if ability == 0 else 0)
    assert not s.state.cards[bear.id].counters.get('+1/+1')
    assert len(s.state.zones['p1:hand']) == before - 1
