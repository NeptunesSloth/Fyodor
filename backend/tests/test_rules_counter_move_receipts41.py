"""Native 122.5 movement gates and distinct original-removal/final-put receipts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import counter_moves
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_linked_aggregates import activate, cast
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / 'fixtures/counter_move_receipts41_cards.json').read_text())
NAMES = [c['name'] for c in DATA]


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='cmv', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return table(cards, NAMES, NAMES, NAMES)


def counters(s, c, kind='+1/+1'):
    return s.state.cards[c.id].counters.get(kind, 0)


@pytest.mark.parametrize('barrier', ['Solemnity', 'Tatterkite'])
def test_actual_nesting_grounds_impossible_put_keeps_original_counter(cards, barrier):
    s = setup(cards)
    land = put(s, 'Nesting Grounds', 'battlefield')
    source = put(s, 'Forest', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+1', delta=2)
    target = put(s, 'Tatterkite' if barrier == 'Tatterkite' else 'Grizzly Bears', 'battlefield')
    if barrier == 'Solemnity':
        put(s, barrier, 'battlefield')
    activate(s, land, ability=1, targets=[source.id, target.id], target_counts=[1, 1])
    settle(s)
    assert counters(s, source) == 2 and counters(s, target) == 0
    roundtrip(s)


@pytest.mark.parametrize('modifier,owner,original,placed', [
    (None, 'p1', 3, 3), (None, 'p1', 2001, 2001), ('Hardened Scales', 'p1', 3, 4),
    ('Doubling Season', 'p1', 3, 6), ('Vorinclex, Monstrous Raider', 'p2', 3, 1),
    ('Vorinclex, Monstrous Raider', 'p2', 1, 0),
])
def test_native_receipt_keeps_original_removal_separate_from_replaced_put(cards, modifier, owner, original, placed):
    s = setup(cards)
    source = put(s, 'Forest', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='+1/+1', value=original)
    if modifier is not None:
        put(s, modifier, 'battlefield', pid=owner)
    plan = Plan(s.state, 'p1', cards, None)
    ctx = {'controller': 'p1'}
    assert counter_moves._do(plan, ctx, {'receipt': 'proof'}, [source.id], target.id, {'+1/+1': original})
    receipt = counter_moves.CounterMoveReceipt.model_validate(ctx['counter_move_receipts']['proof'])
    assert sum(t.amount for t in receipt.removed) == original
    assert sum(t.amount for t in receipt.placed) == placed
    assert plan.state.cards[source.id].counters.get('+1/+1', 0) == 0
    assert plan.state.cards[target.id].counters.get('+1/+1', 0) == placed
    assert counter_moves.CounterMoveReceipt.model_validate_json(receipt.model_dump_json()) == receipt


def test_native_same_object_and_prohibition_produce_explicit_zero_receipts(cards):
    s = setup(cards)
    source = put(s, 'Grizzly Bears', 'battlefield')
    target = put(s, 'Tatterkite', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+1', delta=2)
    for destination in (source, target):
        plan = Plan(s.state, 'p1', cards, None)
        ctx = {'controller': 'p1'}
        assert counter_moves._do(plan, ctx, {'receipt': 'proof'}, [source.id], destination.id, {'+1/+1': 2})
        assert ctx['counter_move_receipts']['proof'] == {'removed': [], 'placed': []}
        assert plan.state.cards[source.id].counters.get('+1/+1', 0) == 2


def wait_counter_order(s, target):
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None:
            if d.resume.get('step') == 'replace_order':
                return d
            option = target.id if target.id in {o.id for o in d.options} else 'yes' if 'yes' in {o.id for o in d.options} else d.options[0].id
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[option])
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('No counter replacement ordering question')


@pytest.mark.parametrize('first,expected', [('Hardened Scales', 6), ('Doubling Season', 5)])
def test_actual_ozolith_cold616_does_not_remove_anything_before_choices(cards, tmp_path, first, expected):
    from tests.test_rules_linked_return_family import cold_choose
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    to_phase(s, 'main1', turn=4)
    source = put(s, 'The Ozolith', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+1', delta=2)
    put(s, 'Hardened Scales', 'battlefield')
    put(s, 'Doubling Season', 'battlefield')
    to_phase(s, 'begin_combat', turn=4)
    d = wait_counter_order(s, target)
    assert d.resume['site'] == 'counter_move_commit'
    assert counters(s, source) == 2 and counters(s, target) == 0
    option = next(o for o in d.options if o.label.startswith(first))
    s = cold_choose(s, cards, tmp_path, [option.id])
    settle(s)
    assert counters(s, source) == 0 and counters(s, target) == expected
    roundtrip(s)


def test_actual_spike_cannibal_aggregates_all_sources_before_one_scales_addition(cards):
    s = setup(cards)
    a = put(s, 'Grizzly Bears', 'battlefield')
    b = put(s, 'Llanowar Elves', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[a.id, b.id], kind='+1/+1', delta=1)
    put(s, 'Hardened Scales', 'battlefield')
    source = put(s, 'Spike Cannibal', 'hand')
    cast(s, source)
    settle(s)
    # Enters with 1+1; the same-kind movement from TWO sources is one put of
    # two counters, increased once to three (not increased once per source).
    assert counters(s, source) == 5
    assert counters(s, a) == counters(s, b) == 0
    roundtrip(s)


def test_actual_any_number_all_kinds_allocations_survive_cold616_without_reopening(cards, tmp_path):
    from tests.test_rules_conditionals import until
    from tests.test_rules_linked_return_family import cold_choose

    s = setup(cards)
    defense = put(s, 'Resourceful Defense', 'battlefield')
    source = put(s, 'Forest', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+1', delta=2)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='charge', delta=3)
    put(s, 'Hardened Scales', 'battlefield')
    put(s, 'Doubling Season', 'battlefield')
    activate(s, defense, ability=1, targets=[source.id, target.id], target_counts=[1, 1])
    for amount in ('2', '1'):
        until(s, lambda x: x.state.rules.decision is not None)
        d = s.state.rules.decision
        assert d.resume['step'] == 'counter_amounts'
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[amount])
    d = wait_counter_order(s, target)
    assert counters(s, source) == 2 and counters(s, source, 'charge') == 3
    frame = counter_moves.CounterMoveFrame.model_validate(d.resume['request']['frame'])
    assert {(entry.kind, entry.amount) for entry in frame.transfers} == {('+1/+1', 2), ('charge', 1)}
    option = next(o for o in d.options if o.label.startswith('Hardened Scales'))
    s = cold_choose(s, cards, tmp_path, [option.id])
    settle(s)
    assert counters(s, source) == 0 and counters(s, source, 'charge') == 2
    assert counters(s, target) == 6 and counters(s, target, 'charge') == 2
    roundtrip(s)


def test_actual_original_source_leaves_before_movement_nothing_is_put(cards):
    s = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    land = put(s, 'Nesting Grounds', 'battlefield')
    source = put(s, 'The Ozolith', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+1', delta=2)
    activate(s, land, ability=1, targets=[source.id, target.id], target_counts=[1, 1])
    cast(s, put(s, 'Naturalize', 'hand'), targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard' and counters(s, target) == 0
    roundtrip(s)


@pytest.mark.parametrize('endpoint', ['source', 'destination'])
def test_actual_cold_counter_movement_never_rebinds_blinked_endpoint(cards, tmp_path, endpoint):
    from tests.test_rules_linked_return_family import cold_choose
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    to_phase(s, 'main1', turn=4)
    source = put(s, 'The Ozolith', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+1', delta=2)
    put(s, 'Hardened Scales', 'battlefield')
    put(s, 'Doubling Season', 'battlefield')
    to_phase(s, 'begin_combat', turn=4)
    d = wait_counter_order(s, target)
    option = next(o for o in d.options if o.label.startswith('Hardened Scales'))
    changed = source if endpoint == 'source' else target
    act(s, 'p1', type='move', card_ids=[changed.id], to={'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[changed.id], to={'zone': 'battlefield'})
    act(s, 'p1', type='counter', card_ids=[changed.id], kind='+1/+1', delta=7)
    s = cold_choose(s, cards, tmp_path, [option.id])
    settle(s)
    assert counters(s, changed) == 7
    assert counters(s, target if endpoint == 'source' else source) == (0 if endpoint == 'source' else 2)
    roundtrip(s)
