"""Native duration and selected cast-authority foundations; no41 grammar hooks."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.rules import casting, context, delayed, history, permissions, scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_exile_packet_continuations_cold import fresh_action
from tests.test_rules_library_look import settle
from tests.test_rules_refused_look import stack_library
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave4h_activation_costs import ch
from tests.test_rules_wave30m_durations import to_phase

DATA = Path(__file__).parent / 'fixtures/exile_authority_continuation_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='eac', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, *names):
    names = ['Grizzly Bears', 'Memnite', 'Lightning Bolt', 'Forest', 'Island', *names]
    # Memnite is a canonical collateral printing from40, not a synthetic zero-cost creature.
    s = table(cards, names, names, names)
    to_phase(s, 'main1', turn=1)
    return s


def grant_packet(s, ids, *, holder='p1', **fields):
    plan = Plan(s.state, 'p1', s.cards, random.Random(1))
    plan.do({'type': 'move', 'card_ids': ids, 'to': {'zone': 'exile'}}, actor='p1')
    ctx = {'controller': holder, 'name': 'Duration foundation'}
    context.bind_objects(plan, ctx, 'packet', ids)
    permissions.grant_play(plan, ctx, {'do': 'grant_play', 'who': 'ref:packet', 'play': True, 'cast': True,
                                     'from_exile': True, 'until': 'end_of_turn', **fields})
    return GameSession(plan.state, cards=s.cards)


def test_next_turn_only_window_uses_native_condition_and_real_cost_then_expires(cards, tmp_path):
    s = setup(cards)
    ids = stack_library(s, ['Grizzly Bears', 'Lightning Bolt'])
    s = grant_packet(s, ids, until='end_of_next_turn', after_turn=1, when={'turn': 'yours'})
    mana(s, C=1, G=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=ids[0])
    to_phase(s, 'main1', turn=4)
    mana(s, C=1, G=1)
    s = fresh_action(s, cards, tmp_path / 'next-turn.json', 'p1', {'type': 'cast_spell', 'card_id': ids[0]})
    assert s.state.cards[ids[0]].zone == 'p1:battlefield'
    to_phase(s, 'main1', turn=7)
    mana(s, R=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=ids[1], targets=['p2'])
    roundtrip(s)


def test_duration_player_end_step_is_distinct_from_beneficiary(cards):
    s = setup(cards)
    to_phase(s, 'end', turn=1)
    ids = stack_library(s, ['Lightning Bolt', 'Grizzly Bears'], pid='p2')
    s = grant_packet(s, ids, holder='p2', until='next_end_step', until_player='p1')
    to_phase(s, 'main1', turn=2)
    mana(s, pid='p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=ids[0], targets=['p3'])
    settle(s)
    assert s.state.players['p3'].life == 37
    to_phase(s, 'end', turn=2)
    assert any(p.card == ids[1] for p in s.state.rules.permissions)
    to_phase(s, 'main1', turn=5)
    mana(s, pid='p2', C=1, G=1)
    with pytest.raises(ActionError):
        act(s, 'p2', type='cast_spell', card_id=ids[1])
    roundtrip(s)


def test_next_turn_combat_end_permission_allows_end_step_instant_then_expires_before_main2(cards):
    s = setup(cards)
    to_phase(s, 'main2', turn=1)
    ids = stack_library(s, ['Lightning Bolt', 'Grizzly Bears'])
    s = grant_packet(s, ids, until='next_combat_end', until_player='p1')
    to_phase(s, 'end_combat', turn=4)
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=ids[0], targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    to_phase(s, 'main2', turn=4)
    mana(s, C=1, G=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=ids[1])
    roundtrip(s)


@pytest.mark.parametrize('mode', ['land', 'entry', 'spell', 'handspell'])
def test_native_play_origin_history_distinguishes_real_exile_plays_from_entries(cards, mode):
    s = setup(cards)
    land = mode in ('land', 'entry')
    cid = stack_library(s, ['Forest' if land else 'Lightning Bolt'])[0]
    s = grant_packet(s, [cid])
    if mode == 'entry':
        act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'battlefield'})
    elif mode == 'land':
        act(s, 'p1', type='play_land', card_id=cid)
    else:
        if mode == 'handspell':
            put(s, 'Lightning Bolt', 'hand')
        mana(s, R=1)
        act(s, 'p1', type='cast_spell', card_id=cid, targets=['p2'])
        settle(s)
    roundtrip(s)
    plan = Plan(s.state, 'p1', cards, random.Random(1))
    assert history.holds(plan, {'controller': 'p1'}, {'history': 'played_from_exile'}) == (mode in ('land', 'spell'))


@pytest.mark.parametrize('opponent_target', [False, True])
def test_delayed_future_target_groups_choose_only_on_trigger_and_use_actual_damage_source(cards, opponent_target):
    s = setup(cards)
    own = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    native = scripts.parse_effects("Target creature you control deals damage equal to its power to up to one target creature you don't control.")
    body = {'do': 'damage', 'who': 'watch_target:1', 'src': 'watch_target:0', 'n': {'power': 'watch_target:0'}}
    head = {'do': 'delayed', 'when': {'kind': 'step', 'step': 'begin_combat', 'whose': 'next'},
            'n': 1, 'this_turn': True, 'targets': native[1]}
    plan = Plan(s.state, 'p1', cards, random.Random(1))
    ctx = {'controller': 'p1', 'name': 'Future targets foundation', 'effects': [head, body], 'next': 1}
    delayed.create(plan, ctx, head)
    s = GameSession(plan.state, cards=cards)
    assert s.state.rules.decision is None
    roundtrip(s)
    to_phase(s, 'begin_combat', turn=1)
    settle(s)
    d = s.state.rules.decision
    answer(s, [next(o.id for o in d.options if o.card_id == own.id)])
    d = s.state.rules.decision
    answer(s, [next(o.id for o in d.options if o.card_id == other.id)] if opponent_target else [])
    assert s.state.cards[own.id].zone == 'p1:battlefield' and s.state.cards[own.id].damage == 0
    assert s.state.cards[other.id].zone == ('p2:graveyard' if opponent_target else 'p2:battlefield')
    roundtrip(s)


def test_selected_permission_affinity_is_cumulative_and_is_an_actual_spell_ability(cards):
    s = setup(cards, 'Myr Enforcer', 'Sol Ring')
    put(s, 'Sol Ring', 'battlefield')
    put(s, 'Memnite', 'battlefield')
    cid = stack_library(s, ['Myr Enforcer'])[0]
    s = grant_packet(s, [cid], spell_keywords=['affinity for artifacts'])
    mana(s, C=3)
    assert casting.castable(s.state, 'p1', s.state.cards[cid], cards)
    act(s, 'p1', type='cast_spell', card_id=cid)
    assert not s.state.players['p1'].mana_units
    assert sum('affinity' in ability.keywords for ability in ch(s, s.state.cards[cid]).abilities) == 2
    settle(s)
    assert s.state.cards[cid].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('selected', ['ordinary', 'undaunted'])
def test_spell_keyword_belongs_only_to_selected_authority_and_normal_way_cannot_borrow_reduction(cards, selected):
    s = setup(cards)
    cid = stack_library(s, ['Grizzly Bears'])[0]
    s = grant_packet(s, [cid])
    ordinary = s.state.rules.permissions[-1].id
    plan = Plan(s.state, 'p1', cards, random.Random(2))
    ctx = {'controller': 'p1', 'name': 'Undaunted authority'}
    context.bind_objects(plan, ctx, 'packet', [cid])
    permissions.grant_play(plan, ctx, {'do': 'grant_play', 'who': 'ref:packet', 'play': False, 'cast': True,
                                     'until': 'end_of_turn', 'spell_keywords': ['undaunted']})
    s = GameSession(plan.state, cards=cards)
    undaunted = s.state.rules.permissions[-1].id
    mana(s, G=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=cid, via=ordinary)
    if selected == 'ordinary':
        mana(s, C=1)
        act(s, 'p1', type='cast_spell', card_id=cid, via=ordinary)
        assert 'undaunted' not in ch(s, s.state.cards[cid]).keywords
    else:
        act(s, 'p1', type='cast_spell', card_id=cid)
        d = s.state.rules.decision
        assert d.resume['step'] == 'slot' and len(d.options) == 2
        answer(s, [undaunted])
    settle(s)
    assert s.state.cards[cid].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('pool,works', [({'C': 2}, True), ({'C': 1, 'R': 1}, True), ({'R': 2}, False), ({'G': 1, 'R': 1}, True)])
def test_colorless_only_as_color_permission_retains_actual_mana_types(cards, pool, works):
    s = setup(cards)
    cid = stack_library(s, ['Grizzly Bears'])[0]
    s = grant_packet(s, [cid], spend='colorless_color')
    mana(s, **pool)
    assert casting.castable(s.state, 'p1', s.state.cards[cid], cards) == works
    if works:
        act(s, 'p1', type='cast_spell', card_id=cid)
        settle(s)
        assert s.state.cards[cid].zone == 'p1:battlefield'
    else:
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=cid)
    roundtrip(s)


@pytest.mark.parametrize('raw,pool,life,works,paidlife', [
    ('{C}{G}', {'C': 2}, 0, True, 0),
    ('{C}{G}', {'G': 2}, 0, False, 0),
    ('{2/W}', {'C': 1}, 0, True, 0),
    ('{2/W}', {'R': 1}, 0, False, 0),
    ('{W/U}', {'C': 1}, 0, True, 0),
    ('{W/U}', {'R': 1}, 0, False, 0),
    ('{G/P}', {'C': 1}, 0, True, 0),
    ('{G/P}', {'R': 1}, 2, True, 2),
    ('{G/P}', {'R': 1}, 1, False, 0),
    ('{X}{G}', {'C': 3}, 0, True, 0),
])
def test_colorless_mask_native_allocation_preserves_real_colorless_hybrid_phyrexian_and_x(raw, pool, life, works, paidlife):
    from app.rules import mana as native
    cost = native.spend_as(native.parse_cost(raw).with_x(2), 'colorless_color')
    if not works:
        with pytest.raises(native.ManaError):
            native.solve(cost, pool, [], life=life)
    else:
        paid = native.solve(cost, pool, [], life=life)
        assert paid.life == paidlife
        assert set(paid.spent) <= set(pool)
        if pool == {'C': 1}:
            assert paid.spent == {'C': 1}


def test_colorless_mask_does_not_release_real_powerstone_spending_restriction(cards):
    from app.rules import effects
    from tests.test_rules_wave4h_activation_costs import ability
    s=setup(cards)
    plan=Plan(s.state,'p1',cards,random.Random(3))
    native=scripts.parse_effects('You create a Powerstone token.')
    assert native is not None
    ctx={'controller':'p1','name':'Native Powerstone'}
    for effect in native[0]:
        assert effects.PRIMITIVES[effect['do']](plan,ctx,effect)
    s=GameSession(plan.state,cards=cards)
    stone=next(c for c in s.state.cards.values() if c.name=='Powerstone')
    act(s,'p1',type='activate_ability',card_id=stone.id,ability=ability(s,stone,'{T}'))
    assert len(s.state.players['p1'].mana_units)==1
    cid=stack_library(s,['Grizzly Bears'])[0]
    s=grant_packet(s,[cid],spend='colorless_color')
    mana(s,C=1)
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=cid)
    mana(s,C=1)
    act(s,'p1',type='cast_spell',card_id=cid)
    settle(s)
    assert len(s.state.players['p1'].mana_units)==1
    record=next(p for p in s.state.rules.payments.values() if p.card==cid)
    assert record.mana_spent=={'C':2}
    roundtrip(s)
