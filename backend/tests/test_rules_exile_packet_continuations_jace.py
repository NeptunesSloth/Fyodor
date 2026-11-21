"""Jace's libraries are inspected together; native searches finish before casting."""
from __future__ import annotations

import json

import pytest

from app.game.visibility import SPECTATOR, can_see
from tests import test_rules_exile_packet_continuations_staged as gameplay
from tests.conftest import connect_game
from tests.game_helpers import act
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_exile_packet_continuations_cold import fresh_action
from tests.test_rules_library_look import settle
from tests.test_rules_refused_look import stack_library
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave4h_activation_costs import ch
from tests.test_rules_wave30m_durations import to_phase

cards = gameplay.cards


def setup(cards):
    names = ['Jace, Architect of Thought', 'Memnite', 'Forest', 'Forest', 'Forest', 'Forest',
             'Aven Mindcensor', 'Stranglehold', 'Opposition Agent', 'Grizzly Bears']
    s = table(cards, names, names, names)
    to_phase(s, 'main1', turn=1)
    return s


def ultimate(s):
    source = put(s, 'Jace, Architect of Thought', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=8)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2)
    settle(s)
    return source


def test_jace_all_libraries_private_before_first_find_and_cold_then_all_searches_before_cast(cards, tmp_path):
    s = setup(cards)
    tops = {p: stack_library(s, ['Memnite', 'Forest'], pid=p) for p in ['p1', 'p2', 'p3']}
    ultimate(s)
    assert s.state.rules.decision.resume['step'] == 'search'
    for owner in ['p2', 'p3']:
        for cid in tops[owner]:
            assert can_see(s.state, s.state.cards[cid], 'p1')
            for viewer in ['p2', 'p3', SPECTATOR]:
                if viewer != owner:
                    assert not can_see(s.state, s.state.cards[cid], viewer)
    d = s.state.rules.decision
    s = fresh_action(s, cards, tmp_path / 'jace.json', 'p1',
                     {'type': 'choose', 'decision_id': d.id, 'option_ids': [tops['p1'][0]]})
    for owner in ['p2', 'p3']:
        assert s.state.rules.decision.resume['step'] == 'search'
        assert s.state.cards[tops[owner][0]].zone == owner + ':library'
        answer(s, [tops[owner][0]])
    for cid in [tops[p][0] for p in ['p3', 'p1', 'p2']]:
        d = s.state.rules.decision
        assert d.resume['step'] == 'free_cast_pick'
        answer(s, [next(o.id for o in d.options if o.card_id == cid)])
    assert s.state.rules.decision is None
    assert all(s.state.cards[tops[p][0]].zone == 'p1:battlefield' for p in tops)
    roundtrip(s)


@pytest.mark.parametrize('restriction', ['Aven Mindcensor', 'Stranglehold', 'Opposition Agent'])
def test_jace_native_search_restrictions_apply_to_inspection_and_finds(cards, restriction):
    s = setup(cards)
    put(s, restriction, 'battlefield', 'p2')
    tops = {p: stack_library(s, ['Forest', 'Forest', 'Forest', 'Forest', 'Memnite'], pid=p)
            for p in ['p1', 'p2', 'p3']}
    ultimate(s)
    if restriction == 'Stranglehold':
        assert s.state.rules.decision is None
        assert not s.state.rules.permissions
        assert all(cid not in s.state.cards for ids in tops.values() for cid in ids)
        return
    if restriction == 'Aven Mindcensor':
        for owner in tops:
            assert tops[owner][4] not in [o.id for o in s.state.rules.decision.options]
            if owner != 'p1':
                assert not can_see(s.state, s.state.cards[tops[owner][4]], 'p1')
            answer(s, [])
        assert s.state.rules.decision is None
    else:
        d = s.state.rules.decision
        assert d.decider == 'p2'
        answer(s, [tops['p1'][4]])
        assert any(p.player == 'p2' and p.card == tops['p1'][4] for p in s.state.rules.permissions)
        for _owner in ['p2', 'p3']:
            assert s.state.rules.decision.decider is None
            answer(s, [])
        assert s.state.rules.decision is None
        assert not any(p.player == 'p1' and p.card == tops['p1'][4] for p in s.state.rules.permissions)
    roundtrip(s)


def test_jace_plus_watches_opponent_attack_against_other_player_after_source_leaves(cards):
    s = setup(cards)
    source = put(s, 'Jace, Architect of Thought', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    settle(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    to_phase(s, 'declare_attackers', turn=2)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p3'}])
    settle(s)
    assert ch(s, s.state.cards[bear.id]).pt[0] == 1
    to_phase(s, 'main2', turn=2)
    assert s.state.players['p3'].life == 39
    to_phase(s, 'main1', turn=4)
    assert not [d for d in s.state.rules.delayed if d.until_player == 'p1']
    assert ch(s, s.state.cards[bear.id]).pt[0] == 2
    roundtrip(s)


@pytest.mark.parametrize('empty', [False, True])
def test_jace_minus_two_real_opponent_piles_empty_pile_and_private_bottom_order(cards, empty):
    s = setup(cards)
    source = put(s, 'Jace, Architect of Thought', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=4)
    top = stack_library(s, ['Memnite', 'Forest', 'Grizzly Bears'])
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    settle(s)
    assert s.state.rules.decision.resume['step'] == 'pile_opponent'
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    answer(s, ['p2'])
    assert s.state.rules.decision.player == 'p2'
    answer(s, [] if empty else [top[0]])
    answer(s, ['1'])
    d = s.state.rules.decision
    assert d is not None and d.kind == 'order' and d.player == 'p1'
    rest = top if empty else top[1:]
    answer(s, list(reversed(rest)))
    assert s.state.zones['p1:library'][-len(rest):] == rest
    if not empty:
        assert s.state.cards[top[0]].zone == 'p1:hand'
    roundtrip(s)


def test_jace_all_library_inspection_rest_and_websocket_are_private(cards, settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    s = setup(cards)
    tops = {p: stack_library(s, ['Memnite'], pid=p) for p in ['p1', 'p2', 'p3']}
    ultimate(s)
    with TestClient(create_app(settings)) as client:
        room = client.app.state.services.hub.create_room(s, mode='lan')
        for player, seat in room.seats.items():
            seat.token = 'jace-' + player
        room.spectator_tokens.add('jace-spectator')
        mine = client.get(f'/api/games/{room.id}/view', headers={'X-Seat-Token': 'jace-p1'}).json()
        assert all(mine['cards'][tops[p][0]]['name'] == 'Memnite' for p in tops)
        for viewer in ['p2', 'p3', 'spectator']:
            token = 'jace-' + viewer
            payload = client.get(f'/api/games/{room.id}/view', headers={'X-Seat-Token': token}).json()
            assert 'options' not in payload['rules']['decision']
            assert 'Memnite' not in json.dumps(payload)
            for owner in tops:
                assert 'name' not in payload['cards'].get(tops[owner][0], {})
            with connect_game(client, room.id, token) as ws:
                frame = ws.receive_json()
                assert frame['type'] == 'state'
                assert 'options' not in frame['view']['rules']['decision']
                assert 'Memnite' not in json.dumps(frame)
                for owner in tops:
                    assert 'name' not in frame['view']['cards'].get(tops[owner][0], {})
