"""Private exile look rights survive source departure without reaching owners or spectators."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests import test_rules_exile_packet_continuations_staged as gameplay
from tests.conftest import connect_game
from tests.game_helpers import act
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_linked_exile_look import assert_look
from tests.test_rules_refused_look import stack_library
from tests.test_rules_wave30m_durations import to_phase

cards = gameplay.cards


@pytest.mark.parametrize('mode', ['arvinox', 'gonti'])
def test_actual_private_exile_rest_and_websocket_look_authority(cards, settings, mode):
    s = gameplay.setup(cards)
    if mode == 'arvinox':
        source = put(s, 'Arvinox, the Mind Flail', 'battlefield')
        card = put(s, 'Doran, the Siege Tower', 'library', 'p2')
        act(s, 'p1', type='move', card_ids=[card.id], to={'player': 'p2', 'zone': 'library'}, position='bottom')
        to_phase(s, 'end', turn=1)
        settle(s)
    else:
        source = put(s, 'Gonti, Night Minister', 'battlefield')
        bear = put(s, 'Grizzly Bears', 'battlefield')
        to_phase(s, 'declare_attackers', turn=4)
        stack_library(s, ['Doran, the Siege Tower'], pid='p2')
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
        to_phase(s, 'main2', turn=4)
        settle(s)
    cid = next(p.card for p in s.state.rules.permissions if p.player == 'p1'
               and s.state.cards[p.card].name == 'Doran, the Siege Tower' and s.state.cards[p.card].owner == 'p2')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert_look(s, cid, ['p1'])
    with TestClient(create_app(settings)) as client:
        room = client.app.state.services.hub.create_room(s, mode='lan')
        for player, seat in room.seats.items():
            seat.token = mode + '-' + player
        room.spectator_tokens.append(mode + '-spectator')
        mine = client.get(f'/api/games/{room.id}/view', headers={'X-Seat-Token': mode + '-p1'}).json()
        assert mine['cards'][cid]['name'] == 'Doran, the Siege Tower'
        for viewer in ['p2', 'p3', 'spectator']:
            token = mode + '-' + viewer
            payload = client.get(f'/api/games/{room.id}/view', headers={'X-Seat-Token': token}).json()
            assert 'name' not in payload['cards'][cid]
            assert 'card_id' not in payload['cards'][cid]
            assert 'Doran, the Siege Tower' not in json.dumps(payload)
            assert s.state.cards[cid].card_id not in json.dumps(payload)
            with connect_game(client, room.id, token) as ws:
                frame = ws.receive_json()
                assert frame['type'] == 'state'
                assert 'name' not in frame['view']['cards'][cid]
                assert 'card_id' not in frame['view']['cards'][cid]
                assert 'Doran, the Siege Tower' not in json.dumps(frame)
                assert s.state.cards[cid].card_id not in json.dumps(frame)
