"""Native private inspection and public top information at staged real choices."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests import test_rules_exile_authority_continuations_staged as gameplay
from tests.conftest import connect_game
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_linked_exile_look import assert_look
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_refused_look import stack_library
from tests.test_rules_wave30m_durations import to_phase

cards = gameplay.cards
staged = gameplay.staged


@pytest.mark.parametrize('mode', ['durnan','feral'])
def test_staged_private_library_choice_rest_ws_only_controller_inspects(cards, settings, mode):
    name = 'Durnan of the Yawning Portal' if mode == 'durnan' else 'Feral Encounter'
    s = gameplay.setup(cards, name)
    if mode == 'durnan':
        source = put(s, name, 'battlefield')
        to_phase(s, 'declare_attackers',turn=4)
        cid = stack_library(s,['Grizzly Bears'])[0]
        act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
        settle(s)
    else:
        cid = stack_library(s,['Grizzly Bears'])[0]
        cast(s,name)
    assert s.state.rules.decision is not None
    assert_look(s,cid,['p1'])
    with TestClient(create_app(settings)) as client:
        room=client.app.state.services.hub.create_room(s,mode='lan')
        for player,seat in room.seats.items():
            seat.token=mode+'-'+player
        room.spectator_tokens.append(mode+'-spectator')
        for viewer in ['p1','p2','p3','spectator']:
            token=mode+'-'+viewer
            payload=client.get(f'/api/games/{room.id}/view',headers={'X-Seat-Token':token}).json()
            if viewer=='p1':
                assert payload['cards'][cid]['name']=='Grizzly Bears'
            else:
                assert 'name' not in payload['cards'].get(cid,{}) and 'card_id' not in payload['cards'].get(cid,{})
                assert cid not in json.dumps(payload.get('rules',{}).get('decision',{}))
            with connect_game(client, room.id, token) as ws:
                frame=ws.receive_json()['view']
                assert ('name' in frame['cards'].get(cid,{})) == (viewer=='p1')


def test_staged_soulfire_real_public_next_top_visible_before_dynamic_group_choice(cards):
    s=gameplay.setup(cards,'Soulfire Eruption','Hill Giant','Courser of Kruphix')
    put(s,'Courser of Kruphix','battlefield')
    target=put(s,'Hill Giant','battlefield','p3')
    ids=stack_library(s,['Lightning Bolt','Forest','Grizzly Bears'])
    source=put(s,'Soulfire Eruption','hand')
    mana(s,C=6,R=3)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=['p2','p3',target.id],target_counts=[3])
    settle(s)
    assert s.state.rules.decision.resume['step']=='exile_authority41_soul'
    assert s.state.cards[ids[0]].zone=='p1:exile'
    for viewer in ('p1','p2','p3'):
        assert s.view(viewer)['cards'][ids[1]]['name']=='Forest'
        assert 'name' not in s.view(viewer)['cards'].get(ids[2],{})
