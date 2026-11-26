"""Call to the Kindred reads the current or exact last enchanted creature."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.conftest import claim_host, connect_game
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_qualified_attached_tutors import cold
from tests.test_rules_refused_look import stack_library
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA=Path(__file__).parent/'fixtures/attached_kindred_look_cards.json'


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads(DATA.read_text())):
        base[c['name']]=card(c['name'],set_code='akl',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names=[c['name'] for c in json.loads(DATA.read_text())]
    s=table(cards,[*names,'Forest','Island','Plains'],names,names)
    to_phase(s,'main1',turn=1)
    host=put(s,'Grizzly Bears','battlefield')
    aura=cast(s,'Call to the Kindred',targets=[host.id])
    top=stack_library(s,['Runeclaw Bear','Llanowar Elves','Forest','Spore Frog','Island'])
    act(s,'p1',type='set_stops',own=['upkeep'],others=[],smart_pass=False)
    act(s,'p1',type='set_prefs',hold_priority=True)
    to_phase(s,'upkeep',turn=4)
    return s,host,aura,top


def accept(s):
    settle(s)
    assert {o.id for o in s.state.rules.decision.options}=={'yes','no'}
    answer(s,['yes'])


def finish(s):
    d=s.state.rules.decision
    assert d.kind=='order' and d.resume['step']=='order_library'
    ids=[o.id for o in d.options]
    answer(s,list(reversed(ids)))
    return ids


def test_call_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve('Call to the Kindred')).level=='FULL'


def test_actual_aura_optional_look_shared_type_entry_then_private_any_order(cards):
    s,host,aura,top=setup(cards)
    accept(s)
    assert {o.id for o in s.state.rules.decision.options}=={top[0]}
    answer(s,[top[0]])
    assert s.state.cards[top[0]].zone=='p1:battlefield'
    rest=finish(s)
    assert set(rest)==set(top[1:])
    assert s.state.zones['p1:library'][-4:]==rest
    assert s.state.cards[aura.id].attached_to==host.id
    roundtrip(s)


def test_optional_decline_looks_at_nothing_and_does_not_reorder(cards):
    s,_,_,top=setup(cards)
    before=list(s.state.zones['p1:library'])
    settle(s)
    assert all(not s.state.cards[c].revealed_to for c in top)
    answer(s,['no'])
    assert s.state.zones['p1:library']==before
    assert all(not s.state.cards[c].revealed_to for c in top)
    roundtrip(s)


def test_accepted_look_may_decline_creature_and_bottom_all_five_cold(cards):
    s,_,_,top=setup(cards)
    accept(s)
    s=cold(s,cards)
    answer(s,[])
    rest=finish(s)
    assert set(rest)==set(top)
    assert s.state.zones['p1:library'][-5:]==rest
    roundtrip(s)


def test_host_dies_before_resolution_uses_exact_last_battlefield_types_cold(cards):
    s,host,aura,top=setup(cards)
    cast(s,'Murder',targets=[host.id])
    assert s.state.cards[host.id].zone=='p1:graveyard'
    assert s.state.cards[aura.id].zone=='p1:graveyard'
    s=cold(s,cards)
    accept(s)
    assert {o.id for o in s.state.rules.decision.options}=={top[0]}
    answer(s,[top[0]])
    finish(s)
    assert s.state.cards[top[0]].zone=='p1:battlefield'
    roundtrip(s)


def test_host_current_creature_types_are_read_at_resolution(cards):
    s,host,aura,top=setup(cards)
    cast(s,'Turn to Frog',targets=[host.id])
    # The response resolves before the pending upkeep ability's optional gate.
    accept(s)
    assert {o.id for o in s.state.rules.decision.options}=={top[3]}
    answer(s,[top[3]])
    finish(s)
    assert s.state.cards[top[3]].zone=='p1:battlefield'
    assert s.state.cards[aura.id].zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('replacement',['Containment Priest',"Grafdigger's Cage"])
def test_native_entry_redirection_or_prohibition_keeps_correct_rest(cards,replacement):
    s,_,_,top=setup(cards)
    put(s,replacement,'battlefield','p2')
    accept(s)
    answer(s,[top[0]])
    rest=finish(s)
    if replacement=='Containment Priest':
        assert s.state.cards[top[0]].zone=='p1:exile'
        assert set(rest)==set(top[1:])
    else:
        assert s.state.cards[top[0]].zone=='p1:library'
        assert set(rest)==set(top)
    roundtrip(s)


def test_aura_destroyed_alone_still_reads_original_living_host(cards):
    s,host,aura,top=setup(cards)
    cast(s,'Krosan Grip',targets=[aura.id])
    assert s.state.cards[aura.id].zone=='p1:graveyard'
    assert s.state.cards[host.id].zone=='p1:battlefield'
    accept(s)
    assert {o.id for o in s.state.rules.decision.options}=={top[0]}
    answer(s,[top[0]])
    finish(s)
    assert s.state.cards[top[0]].zone=='p1:battlefield'
    roundtrip(s)


def test_blinked_host_uses_old_frog_lki_not_reentered_bear(cards):
    from app.rules.plan import Plan
    from tests.test_rules_bandmate_references import mana

    s,host,aura,top=setup(cards)
    spell=put(s,'Turn to Frog','hand')
    mana(s,C=10,U=5,W=5)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[host.id])
    for _ in range(15):
        if 'Frog' in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[host.id]).subtypes:
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert 'Frog' in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[host.id]).subtypes
    assert s.state.zones['stack']
    old=s.state.rules.object_id(host.id)
    cast(s,'Cloudshift',targets=[host.id])
    assert s.state.rules.object_id(host.id)!=old
    assert 'Bear' in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[host.id]).subtypes
    assert s.state.cards[aura.id].zone=='p1:graveyard'
    s=cold(s,cards)
    accept(s)
    assert {o.id for o in s.state.rules.decision.options}=={top[3]}
    answer(s,[top[3]])
    finish(s)
    assert s.state.cards[top[3]].zone=='p1:battlefield'
    assert s.state.cards[top[0]].zone=='p1:library'
    roundtrip(s)


def test_call_optional_private_look_and_bottom_order_rest_ws(cards,settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    s,_,_,top=setup(cards)
    settle(s)
    with TestClient(create_app(settings)) as client:
        claim_host(client)
        deck=client.post('/api/decks',json={'text':'Commander\n1 Krenko, Mob Boss\nDeck\n20 Forest'}).json()['id']
        game=client.post('/api/games',json={'mode':'lan','players':[{'name':'Alice','deck_id':deck},{'name':'Bob','deck_id':deck}]}).json()
        gid=game['game']['id']
        bob=client.post('/api/join',json={'code':game['game']['code'],'name':'Bob'}).json()['token']
        spec=client.post('/api/join',json={'code':game['game']['code'],'spectate':True}).json()['token']
        client.app.state.services.hub.get(gid).game=s
        for stage in range(4):
            if stage==1:
                answer(s,['yes'])
            elif stage==2:
                answer(s,[top[0]])
            elif stage==3:
                finish(s)
            for token in [bob,spec]:
                response=client.get(f'/api/games/{gid}/view',headers={'X-Seat-Token':token})
                assert response.status_code==200
                with connect_game(client, gid, token) as ws:
                    frame=ws.receive_json()
                    assert frame['type']=='state'
                for raw in [response.text,json.dumps(frame)]:
                    assert (top[0] in raw)==(stage>=2)
                    assert all(cid not in raw for cid in top[1:])
    roundtrip(s)
