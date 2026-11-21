"""Owned imports stay private and survive offline games; CR 103.2b, 400.11, 723.4, 903.11."""
from __future__ import annotations

import json

from tests.test_lobby import ALICE_DECK, BOB_DECK, create_lobby, h, lobby_of, seat
from tests.conftest import claim_host


def test_import_preview_is_private_normalized_and_does_not_replace_the_playing_deck(client):
    gid, code, alice = create_lobby(client)
    bob = client.post('/api/join', json={'code':code,'name':'Bob'}).json()['token']
    client.post(f'/api/games/{gid}/lobby/deck',json={'text':BOB_DECK},headers=h(bob))
    result=client.post(f'/api/games/{gid}/lobby/import',json={'text':'2 Sol Ring\n3 Island','name':'Owned artifacts'},headers=h(bob))
    assert result.status_code==200,result.text
    imported=result.json()
    assert imported['name']=='Owned artifacts' and '2 Sol Ring' in imported['text']
    assert len(imported['entries'])==2 and all(e['printing_id'] for e in imported['entries'])
    assert 'Sol Ring' not in json.dumps(lobby_of(client,gid,alice))
    assert seat(lobby_of(client,gid,bob),'p2')['deck']['card_count']==14


def test_imported_collection_is_owned_by_the_submitting_seat_and_saved_with_game(client):
    gid,code,alice=create_lobby(client)
    bob=client.post('/api/join',json={'code':code,'name':'Bob'}).json()['token']
    imported=client.post(f'/api/games/{gid}/lobby/import',json={'text':'2 Sol Ring\n3 Island'},headers=h(bob)).json()
    client.post(f'/api/games/{gid}/lobby/deck',json={'text':ALICE_DECK},headers=h(alice))
    r=client.post(f'/api/games/{gid}/lobby/deck',json={'text':BOB_DECK,'collection':imported['entries']},headers=h(bob))
    assert r.status_code==200,r.text
    client.post(f'/api/games/{gid}/lobby/start',json={'force':True},headers=h(alice))
    state=client.app.state.services.hub.get(gid).session.state
    assert [e.name for e in state.collections['p2']]==['Sol Ring','Island']
    assert state.collections.get('p1',[])==[]
    for token in [alice,bob]:
        view=client.get(f'/api/games/{gid}/view',headers=h(token)).json()
        assert 'collections' not in view
        own=client.get(f'/api/games/{gid}/collection',headers=h(token)).json()
        assert ('Sol Ring' in json.dumps(own))==(token==bob)
    restored=type(state).model_validate_json(state.model_dump_json())
    assert restored.collections==state.collections


def test_remote_import_cannot_read_host_library_or_set_another_players_collection(client):
    gid,code,alice=create_lobby(client)
    bob=client.post('/api/join',json={'code':code,'name':'Bob'}).json()['token']
    from fastapi.testclient import TestClient
    remote=TestClient(client.app,client=('192.168.1.42',4000))
    r=remote.post(f'/api/games/{gid}/lobby/import',json={'deck_id':'host-private'},headers=h(bob))
    assert r.status_code==403
    assert client.post(f'/api/games/{gid}/lobby/import',json={'text':'1 Sol Ring'}).status_code==403


def test_owned_collection_excludes_starting_cards_and_is_not_a_game_zone(cards):
    from app.game.factory import DeckCard, PlayerSetup, new_game
    from app.game.state import CollectionCard
    ring=cards.resolve('Sol Ring')
    state=new_game([PlayerSetup(name='Alice',cards=[DeckCard('main',1,ring['name'],ring['id'])],
        collection=[CollectionCard(printing_id=ring['id'],oracle_id=ring['oracle_id'],name=ring['name'],quantity=2)])],shuffle=False)
    assert state.collections['p1'][0].quantity==1
    assert len(state.cards)==1 and all(not key.endswith(':collection') for key in state.zones)
    old=state.model_dump()
    old.pop('collections')
    assert type(state).model_validate(old).collections=={}


def test_collection_companion_must_be_owned_legal_and_meet_the_starting_deck(settings):
    from fastapi.testclient import TestClient

    from app.cards.importer import build_database
    from app.main import create_app
    from tests.fixtures.cards import fixture_cards
    from tests.test_rules_wave38d_companion import EXTRA
    settings.ensure_dirs()
    build_database([*fixture_cards(),*EXTRA],settings.cards_db_path)
    with TestClient(create_app(settings)) as client:
        claim_host(client)
        gid,_,alice=create_lobby(client)
        imported=client.post(f'/api/games/{gid}/lobby/import',json={'text':'1 Keruga, the Macrosage'},headers=h(alice)).json()
        companion=imported['entries'][0]['printing_id']
        assert imported['companions']==[{'name':'Keruga, the Macrosage','printing_id':companion}]
        base={'text':"Commander\n1 Atraxa, Praetors' Voice\nDeck\n10 Island",'companion_id':companion}
        assert client.post(f'/api/games/{gid}/lobby/deck',json=base,headers=h(alice)).status_code==422
        body={**base,'collection':imported['entries']}
        good=client.post(f'/api/games/{gid}/lobby/deck',json=body,headers=h(alice))
        assert good.status_code==200,good.text
        illegal=client.post(f'/api/games/{gid}/lobby/deck',json={**body,'text':base['text']+'\n1 Sol Ring'},headers=h(alice))
        assert illegal.status_code==422 and 'mana value' in illegal.json()['detail']
        lutri=client.post(f'/api/games/{gid}/lobby/import',json={'text':'1 Lutri, the Spellchaser'},headers=h(alice)).json()
        duplicates=client.post(f'/api/games/{gid}/lobby/deck',json={
            'text':base['text']+'\n2 Sol Ring','collection':lutri['entries'],
            'companion_id':lutri['entries'][0]['printing_id']},headers=h(alice))
        assert duplicates.status_code==422 and 'share a name' in duplicates.json()['detail']

        assert client.post(f'/api/games/{gid}/lobby/start',json={'force':True},headers=h(alice)).status_code==200
        state=client.app.state.services.hub.get(gid).session.state
        assert len(state.zones['p1:companion'])==1
        assert state.cards[state.zones['p1:companion'][0]].name=='Keruga, the Macrosage'
        assert state.collections['p1']==[]


def test_collection_survives_an_offline_host_restart_and_saved_game_load(settings,card_db):
    from fastapi.testclient import TestClient

    from app.config import load_settings
    from app.main import create_app
    with TestClient(create_app(settings)) as first:
        claim_host(first)
        gid,code,alice=create_lobby(first)
        bob=first.post('/api/join',json={'code':code,'name':'Bob'}).json()['token']
        imported=first.post(f'/api/games/{gid}/lobby/import',json={'text':'2 Sol Ring'},headers=h(bob)).json()
        first.post(f'/api/games/{gid}/lobby/deck',json={'text':BOB_DECK,'collection':imported['entries']},headers=h(bob))
        first.post(f'/api/games/{gid}/lobby/deck',json={'text':ALICE_DECK},headers=h(alice))
        first.post(f'/api/games/{gid}/lobby/start',json={'force':True},headers=h(alice))
        saved=first.post(f'/api/games/{gid}/save',json={'name':'Private collection'},headers=h(alice))
        assert saved.status_code==201,saved.text
        sid=saved.json()['id']
    offline=load_settings({'FYODOR_DATA_DIR':str(settings.data_dir),'FYODOR_ALLOW_NETWORK':'0',
                          'FYODOR_FRONTEND_DIST':str(settings.frontend_dist)})
    with TestClient(create_app(offline)) as fresh:
        claim_host(fresh)
        loaded=fresh.post(f'/api/saves/{sid}/load',json={})
        assert loaded.status_code==201,loaded.text
        state=fresh.app.state.services.hub.get(loaded.json()['game']['id']).session.state
        assert [(c.name,c.quantity) for c in state.collections['p2']]==[('Sol Ring',2)]
        assert state.collections['p1']==[]


def test_saving_or_forgetting_owned_decks_updates_an_already_selected_decks_collection(client):
    gid,code,alice=create_lobby(client)
    bob=client.post('/api/join',json={'code':code,'name':'Bob'}).json()['token']
    client.post(f'/api/games/{gid}/lobby/deck',json={'text':BOB_DECK},headers=h(bob))
    client.post(f'/api/games/{gid}/lobby/ready',json={'ready':True},headers=h(bob))
    imported=client.post(f'/api/games/{gid}/lobby/import',json={'text':'2 Grizzly Bears'},headers=h(bob)).json()
    synced=client.post(f'/api/games/{gid}/lobby/collection',json={'collection':imported['entries']},headers=h(bob))
    assert synced.status_code==200,synced.text
    assert not seat(synced.json(),'p2')['ready']
    assert seat(synced.json(),'p2')['deck']['card_count']==14
    assert 'Grizzly Bears' not in json.dumps(lobby_of(client,gid,alice))
    # Older clients choosing a deck without a collection field do not erase a prior synchronization.
    client.post(f'/api/games/{gid}/lobby/deck',json={'text':BOB_DECK},headers=h(bob))
    room=client.app.state.services.hub.get(gid)
    assert room.lobby_seats['p2'].collection[0].quantity==2
    cleared=client.post(f'/api/games/{gid}/lobby/collection',json={'collection':[]},headers=h(bob))
    assert cleared.status_code==200
    assert room.lobby_seats['p2'].collection==[]
