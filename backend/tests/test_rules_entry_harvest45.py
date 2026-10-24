"""Explicit unimported scheduler model proofs, not Thief/Zegana admission."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.rules import context, effects, engine, replace
from app.rules import entry_harvest45 as model
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings, monkeypatch):
    base = {c['name']: c for c in fixture_cards()}
    for i, row in enumerate(json.loads((Path(__file__).parent / 'fixtures/entry_harvest45_cards.json').read_text())):
        base[row['name']] = card(row['name'], set_code='ehm', number=str(i), **{
            ('card_faces' if k == 'faces' else k): v for k, v in row.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    monkeypatch.setitem(effects.PRIMITIVES, model.STEP, model.primitive)
    monkeypatch.setitem(effects.RESUME, model.STEP, model.resume)
    # The engine takes a copy of effect continuations when imported. Register the
    # test-only scheduler there too, independent of test collection/import order.
    monkeypatch.setitem(engine.RESUME, model.STEP, model.resume)
    monkeypatch.setitem(replace.SITES, model.PUT_SITE, model.resume_put)
    yield repo
    repo.close()


def scene(cards, names, counters=4, modifiers=False):
    deck = [*names, 'Grizzly Bears', 'Doubling Season', 'Vorinclex, Monstrous Raider', 'Solemnity', 'Jace Beleren']
    s = table(cards, deck, deck, deck)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=bear.id, kind='+1/+1', value=counters)
    act(s, 'p1', type='set_resource', player='p1', key='experience', value=8)
    chosen = []
    for name in names:
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == 'p1' and c.id not in chosen)
        chosen.append(c.id)
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'graveyard'})
    if modifiers:
        put(s, 'Doubling Season', 'battlefield')
        put(s, 'Vorinclex, Monstrous Raider', 'battlefield', pid='p2')
    return s, bear, chosen


def pending(s, bear, incoming):
    plan = Plan(s.state, 'p1', s.cards, None)
    ctx = {'controller': 'p1', 'source_card': bear.id, 'source_object': plan.oid(bear),
           'name': 'Explicit scheduler prototype', 'next': 0, 'stack_id': '', 'body_done': {'do': 'noop'},
           'effects': [{'do': model.STEP, 'binding': 'incoming'}, {'do': 'gain_life', 'who': 'you', 'n': 7}]}
    context.bind_objects(plan, ctx, 'incoming', incoming)
    effects.continue_effects(plan, ctx)
    return GameSession(plan.state, cards=s.cards)


def test_preview_repeatedly_classifies_without_removal_or_quantity_freeze(cards):
    s, bear, ids = scene(cards, ['Thief of Blood', 'Prime Speaker Zegana'])
    plan = Plan(s.state, 'p1', cards, None)
    refs = [context.ref_of(plan, cid) for cid in ids]
    before = plan.state.model_dump(mode='json')
    for _ in range(3):
        frame = model.prepare(plan, {'controller': 'p1'}, refs)
        assert all(e.quantity is None for e in frame.incoming)
        assert not frame.harvests and not plan.steps
    assert plan.state.model_dump(mode='json') == before
    assert plan.state.cards[bear.id].counters['+1/+1'] == 4


@pytest.mark.parametrize('first', [0, 1])
def test_two_thieves_actual_selected_first_gets_originals_other_completed_empty(cards, first):
    s, bear, ids = scene(cards, ['Thief of Blood', 'Thief of Blood'])
    old = [s.state.rules.object_id(cid) for cid in ids]
    s = pending(s, bear, ids)
    d = s.state.rules.decision
    assert d is not None and s.state.cards[bear.id].counters['+1/+1'] == 4
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[old[first]])
    assert s.state.cards[ids[first]].counters.get('+1/+1') == 4
    assert not s.state.cards[ids[1-first]].counters.get('+1/+1')
    assert not s.state.cards[bear.id].counters.get('+1/+1')
    assert s.state.players['p1'].resources['experience'] == 8
    assert s.state.players['p1'].life == 47
    assert all(s.state.cards[cid].zone == 'p1:battlefield' for cid in ids)


@pytest.mark.parametrize('zegana_first', [False, True])
def test_selected_zegana_quantity_seals_before_or_after_real_harvest(cards, zegana_first):
    s, bear, ids = scene(cards, ['Thief of Blood', 'Prime Speaker Zegana'])
    old = [s.state.rules.object_id(cid) for cid in ids]
    s = pending(s, bear, ids)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[old[1 if zegana_first else 0]])
    assert s.state.cards[ids[0]].counters.get('+1/+1') == 4
    assert s.state.cards[ids[1]].counters.get('+1/+1') == (6 if zegana_first else 2)
    assert s.state.players['p1'].life == 47


def test_completed_empty_harvest_receipt_and_quantity_are_saved_before_native_put_choice(cards):
    s, bear, ids = scene(cards, ['Thief of Blood', 'Thief of Blood'], counters=3, modifiers=True)
    original = [s.state.rules.object_id(cid) for cid in ids]
    s = pending(s, bear, ids)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[original[0]])
    d = s.state.rules.decision
    assert d is not None and d.resume['site'] == model.PUT_SITE
    frame = model.EntryBatch.model_validate(d.resume['request']['frame'])
    assert [e.quantity for e in frame.incoming] == [3, 0]
    assert frame.harvests[original[0]].original_total == 3
    assert frame.harvests[original[1]].original_total == 0
    assert not frame.harvests[original[1]].removed
    assert s.state.cards[bear.id].counters.get('+1/+1', 0) == 0
    assert all(s.state.cards[cid].zone == 'p1:graveyard' for cid in ids)


@pytest.mark.parametrize('zegana_first', [False, True])
def test_saved_native_enter_put_cps_never_reharvests_and_preserves_selected_quantity(cards, zegana_first):
    from app.game.state import GameState

    s, bear, ids = scene(cards, ['Thief of Blood', 'Prime Speaker Zegana'], counters=3, modifiers=True)
    old = [s.state.rules.object_id(cid) for cid in ids]
    s = pending(s, bear, ids)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[old[1 if zegana_first else 0]])
    d = s.state.rules.decision
    assert d is not None and d.resume['site'] == model.PUT_SITE
    s = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=cards)
    for _ in range(4):
        d = s.state.rules.decision
        if d is None:
            break
        pick = next(o.id for o in d.options if 'Vorinclex' in o.label)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[pick])
    assert s.state.rules.decision is None
    assert s.state.cards[ids[0]].counters.get('+1/+1') == 2  # native floor3/2 then double
    assert s.state.cards[ids[1]].counters.get('+1/+1') == (4 if zegana_first else 2)
    assert not s.state.cards[bear.id].counters.get('+1/+1')
    assert s.state.players['p1'].life == 47


def test_native_prohibited_entry_put_does_not_undo_nonmove_harvest(cards):
    s, bear, ids = scene(cards, ['Thief of Blood', 'Prime Speaker Zegana'])
    put(s, 'Solemnity', 'battlefield', pid='p2')
    first = s.state.rules.object_id(ids[0])
    s = pending(s, bear, ids)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[first])
    assert all(s.state.cards[cid].zone == 'p1:battlefield' for cid in ids)
    assert all(not s.state.cards[cid].counters.get('+1/+1') for cid in ids)
    assert not s.state.cards[bear.id].counters.get('+1/+1')
    assert s.state.players['p1'].life == 47


def test_native_old_permanent_all_kinds_loyalty_removed_before_saved_entry_but_no_midstage_sba(cards):
    s, bear, ids = scene(cards, ['Thief of Blood', 'Thief of Blood'], modifiers=True)
    land = put(s, 'Forest', 'battlefield')
    walker = put(s, 'Jace Beleren', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=land.id, kind='charge', value=2)
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=3)
    original = s.state.rules.object_id(ids[0])
    s = pending(s, bear, ids)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[original])
    d = s.state.rules.decision
    assert d is not None and d.resume['site'] == model.PUT_SITE
    frame = model.EntryBatch.model_validate(d.resume['request']['frame'])
    assert frame.harvests[original].original_total == 9
    assert {row.kind for row in frame.harvests[original].removed} == {'+1/+1', 'charge', 'loyalty'}
    assert s.state.cards[walker.id].zone == 'p1:battlefield' and not s.state.cards[walker.id].counters.get('loyalty')
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if 'Vorinclex' in o.label)])
    assert s.state.cards[ids[0]].counters.get('+1/+1') == 8
    assert s.state.cards[walker.id].zone == 'p1:graveyard'
    assert s.state.players['p1'].resources['experience'] == 8


def test_cross_controller_request_is_explicitly_rejected_before_any_harvest(cards):
    from app.game.errors import ActionError

    s, _, ids = scene(cards, ['Thief of Blood', 'Thief of Blood'])
    plan = Plan(s.state, 'p1', cards, None)
    frame = model.prepare(plan, {'controller': 'p1'}, [context.ref_of(plan, cid) for cid in ids])
    frame.incoming[1].controller = 'p2'
    before = plan.state.model_dump(mode='json')
    with pytest.raises(ActionError, match='Cross-controller'):
        model.run(plan, frame)
    assert plan.state.model_dump(mode='json') == before and not plan.steps
