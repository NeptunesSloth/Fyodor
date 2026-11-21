"""Conditional inspected-card replacements preserve one verdict through native choices."""
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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import answer, settle
from tests.test_rules_refused_look import stack_library
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase
from tests.conftest import claim_host


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/optional_library_look_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAMES = ['Planar Atlas','Fertile Thicket','Cream of the Crop',"Quest for Ula's Temple",'Nissa, Steward of Elements']

@pytest.mark.parametrize('name',NAMES)
def test_canonical_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'




def setup(cards):
    data=json.loads((Path(__file__).parent/'fixtures/optional_library_look_cards.json').read_text())
    names=[c['name'] for c in data]
    s=table(cards,names,names,names)
    to_phase(s,'main1',turn=1)
    return s



def cast(s,name,**kw):
    source=put(s,name,'hand')
    mana(s,C=15,U=10,G=10,R=5,W=5,B=5)
    act(s,'p1',type='cast_spell',card_id=source.id,**kw)
    settle(s)
    return source


def finish_order(s):
    d=s.state.rules.decision
    if d is not None:
        assert d.resume['step']=='order_library'
        answer(s,[o.id for o in d.options])
    roundtrip(s)


@pytest.mark.parametrize('name,n',[('Planar Atlas',4),('Fertile Thicket',5)])
@pytest.mark.parametrize('accept',[False,True])
def test_optional_initial_peek_decline_leaves_library_untouched(cards,name,n,accept):
    s=setup(cards)
    top=stack_library(s,['Forest','Grizzly Bears','Island','Shivan Dragon','Mountain'])
    if name=='Fertile Thicket':
        source=put(s,name,'hand')
        act(s,'p1',type='play_land',card_id=source.id)
        settle(s)
    else:
        cast(s,name)
    d=s.state.rules.decision
    assert d is not None
    answer(s,['yes' if accept else 'no'])
    if accept:
        d=s.state.rules.decision
        assert d.resume['step']=='pick_looked'
        answer(s,[top[0]])
        finish_order(s)
        assert s.state.zones['p1:library'][0]==top[0]
        assert not s.state.cards[top[0]].revealed_to
    else:
        assert s.state.zones['p1:library'][:5]==top
        assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('topname,accept',[('Grizzly Bears',True),('Grizzly Bears',False),('Forest',False)])
def test_quest_private_peek_separate_reveal_choice_and_counter(cards,topname,accept):
    s=setup(cards)
    quest=put(s,"Quest for Ula's Temple",'battlefield')
    top=stack_library(s,[topname])[0]
    to_phase(s,'upkeep',turn=4)
    settle(s)
    answer(s,['yes'])
    d=s.state.rules.decision
    assert d.resume['step']=='pick_looked'
    answer(s,[top] if accept else [])
    assert s.state.cards[quest.id].counters.get('quest',0)==int(accept)
    assert s.state.zones['p1:library'][0]==top
    assert not s.state.cards[top].revealed_to
    roundtrip(s)


@pytest.mark.parametrize('topname,eligible',[('Forest',True),('Grizzly Bears',True),('Shivan Dragon',False)])
def test_nissa_native_loyalty_cast_and_exact_optional_entry(cards,topname,eligible):
    s=setup(cards)
    nissa=cast(s,'Nissa, Steward of Elements',x_value=2)
    assert s.state.cards[nissa.id].counters['loyalty']==2
    top=stack_library(s,[topname])[0]
    act(s,'p1',type='activate_ability',card_id=nissa.id,ability=1)
    settle(s)
    d=s.state.rules.decision
    assert d.resume['step']=='pick_looked'
    assert bool(d.options)==eligible
    answer(s,[top] if eligible else [])
    assert s.state.cards[top].zone==('p1:battlefield' if eligible else 'p1:library')
    roundtrip(s)


@pytest.mark.parametrize('response,n',[('none',2),('Giant Growth',5),('Swords to Plowshares',2),('Grasp of Darkness',0)])
def test_cream_reads_resolution_power_or_departed_creatures_lki(cards,response,n):
    s=setup(cards)
    put(s,'Cream of the Crop','battlefield')
    bear=put(s,'Grizzly Bears','hand')
    act(s,'p1',type='set_prefs',hold_priority=True)
    mana(s,C=8,G=3,W=2,B=2)
    act(s,'p1',type='cast_spell',card_id=bear.id)
    for _ in range(8):
        if s.state.cards[bear.id].zone=='p1:battlefield':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    if response!='none':
        spell=put(s,response,'hand')
        act(s,'p1',type='cast_spell',card_id=spell.id,targets=[bear.id])
    top=stack_library(s,['Forest','Island','Mountain','Shivan Dragon','Dryad Arbor'])
    settle(s)
    answer(s,['yes'])
    if n:
        d=s.state.rules.decision
        assert d.resume['step']=='pick_looked'
        assert len(d.options)==n
        assert d.min_choices==1
        answer(s,[top[n-1]])
        finish_order(s)
        assert s.state.zones['p1:library'][0]==top[n-1]
    else:
        assert s.state.rules.decision is None
        assert s.state.zones['p1:library'][:5]==top
    roundtrip(s)


@pytest.mark.parametrize('response,topname,eligible',[("Hero's Downfall",'Grizzly Bears',True),('Lightning Bolt','Grizzly Bears',False),('Lightning Bolt','Forest',True)])
def test_nissa_response_departure_reads_last_loyalty_and_land_is_unrestricted(cards,response,topname,eligible):
    s=setup(cards)
    nissa=cast(s,'Nissa, Steward of Elements',x_value=3)
    top=stack_library(s,[topname])[0]
    act(s,'p1',type='set_prefs',hold_priority=True)
    act(s,'p1',type='activate_ability',card_id=nissa.id,ability=1)
    spell=put(s,response,'hand')
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[nissa.id])
    settle(s)
    d=s.state.rules.decision
    assert d.resume['step']=='pick_looked'
    assert bool(d.options)==eligible
    answer(s,[top] if eligible else [])
    assert s.state.cards[top].zone==('p1:battlefield' if eligible else 'p1:library')
    assert s.state.cards[nissa.id].zone=='p1:graveyard'
    roundtrip(s)


def test_quest_recognizes_grist_as_creature_card_outside_battlefield(cards):
    s=setup(cards)
    quest=put(s,"Quest for Ula's Temple",'battlefield')
    top=stack_library(s,['Grist, the Hunger Tide'])[0]
    to_phase(s,'upkeep',turn=4)
    settle(s)
    answer(s,['yes'])
    d=s.state.rules.decision
    assert [o.id for o in d.options]==[top]
    answer(s,[top])
    assert s.state.cards[quest.id].counters['quest']==1
    roundtrip(s)


def test_nissa_recognizes_grist_creature_card_within_loyalty_bound(cards):
    s=setup(cards)
    nissa=cast(s,'Nissa, Steward of Elements',x_value=3)
    top=stack_library(s,['Grist, the Hunger Tide'])[0]
    act(s,'p1',type='activate_ability',card_id=nissa.id,ability=1)
    settle(s)
    assert [o.id for o in s.state.rules.decision.options]==[top]
    answer(s,[top])
    assert s.state.cards[top].zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('modifier,count',[('Doubling Season',2),('Solemnity',0)])
def test_quest_reveal_is_independent_of_native_counter_replacement(cards,modifier,count):
    s=setup(cards)
    quest=put(s,"Quest for Ula's Temple",'battlefield')
    put(s,modifier,'battlefield')
    top=stack_library(s,['Grizzly Bears'])[0]
    to_phase(s,'upkeep',turn=4)
    settle(s)
    answer(s,['yes'])
    answer(s,[top])
    assert s.state.cards[quest.id].counters.get('quest',0)==count
    assert not s.state.cards[top].revealed_to
    roundtrip(s)


def test_quest_source_destroyed_in_response_still_peeks_without_countering_new_object(cards):
    s=setup(cards)
    quest=put(s,"Quest for Ula's Temple",'battlefield')
    top=stack_library(s,['Grizzly Bears'])[0]
    to_phase(s,'upkeep',turn=4)
    cast(s,'Disenchant',targets=[quest.id])
    answer(s,['yes'])
    answer(s,[top])
    assert s.state.cards[quest.id].zone=='p1:graveyard'
    assert not s.state.cards[quest.id].counters
    assert not s.state.cards[top].revealed_to
    roundtrip(s)


def test_nissa_stale_library_object_is_not_put_onto_battlefield(cards):
    s=setup(cards)
    nissa=cast(s,'Nissa, Steward of Elements',x_value=2)
    top=stack_library(s,['Grizzly Bears'])[0]
    act(s,'p1',type='activate_ability',card_id=nissa.id,ability=1)
    settle(s)
    act(s,'p1',type='move',card_ids=[top],to={'zone':'exile'})
    act(s,'p1',type='move',card_ids=[top],to={'zone':'library'},position='top')
    answer(s,[top])
    assert s.state.cards[top].zone=='p1:library'
    roundtrip(s)


def test_thicket_private_look_public_selection_then_hidden_library_http_and_ws(cards,settings):
    from fastapi.testclient import TestClient

    from app.main import create_app
    s=setup(cards)
    top=stack_library(s,['Forest','Grizzly Bears','Island','Shivan Dragon','Mountain'])
    source=put(s,'Fertile Thicket','hand')
    act(s,'p1',type='play_land',card_id=source.id)
    settle(s)
    with TestClient(create_app(settings)) as client:
        claim_host(client)
        deck_id=client.post('/api/decks',json={'text':'Commander\n1 Krenko, Mob Boss\nDeck\n20 Forest'}).json()['id']
        game=client.post('/api/games',json={'mode':'lan','players':[{'name':'Alice','deck_id':deck_id},{'name':'Bob','deck_id':deck_id}]}).json()
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
                finish_order(s)
            for token in [bob,spec]:
                response=client.get(f'/api/games/{gid}/view',headers={'X-Seat-Token':token})
                assert response.status_code==200
                with client.websocket_connect(f'/ws/games/{gid}?token={token}') as ws:
                    frame=ws.receive_json()
                    assert frame['type']=='state'
                for raw in [response.text,json.dumps(frame)]:
                    assert (top[0] in raw)==(stage==2)
                    assert all(cid not in raw for cid in top[1:])
    roundtrip(s)


@pytest.mark.parametrize('name,allowed',[('Planar Atlas',True),('Fertile Thicket',False)])
def test_basic_land_filter_distinguishes_dryad_arbor(cards,name,allowed):
    s=setup(cards)
    top=stack_library(s,['Dryad Arbor','Grizzly Bears','Island','Shivan Dragon','Mountain'])
    if name=='Planar Atlas':
        cast(s,name)
    else:
        source=put(s,name,'hand')
        act(s,'p1',type='play_land',card_id=source.id)
        settle(s)
    answer(s,['yes'])
    d=s.state.rules.decision
    assert (top[0] in [o.id for o in d.options])==allowed
    answer(s,[])
    finish_order(s)
    assert s.state.zones['p1:library'][0] not in top[:4 if allowed else 5]
    roundtrip(s)


@pytest.mark.parametrize('name',["Quest for Ula's Temple",'Nissa, Steward of Elements'])
def test_ordinary_planeswalker_card_does_not_qualify_as_creature(cards,name):
    s=setup(cards)
    if name==NAMES[4]:
        source=cast(s,name,x_value=3)
        top=stack_library(s,['Jace Beleren'])[0]
        act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
        settle(s)
    else:
        put(s,name,'battlefield')
        top=stack_library(s,['Jace Beleren'])[0]
        to_phase(s,'upkeep',turn=4)
        settle(s)
        answer(s,['yes'])
    assert not s.state.rules.decision.options
    answer(s,[])
    assert s.state.cards[top].zone=='p1:library'
    roundtrip(s)


@pytest.mark.parametrize('loyalty,eligible',[(2,False),(3,True)])
def test_nissa_library_mdfc_checks_front_creature_not_back_land(cards,loyalty,eligible):
    s=setup(cards)
    source=cast(s,NAMES[4],x_value=loyalty)
    top=stack_library(s,['Kazandu Mammoth // Kazandu Valley'])[0]
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    settle(s)
    assert bool(s.state.rules.decision.options)==eligible
    answer(s,[top] if eligible else [])
    assert s.state.cards[top].zone==('p1:battlefield' if eligible else 'p1:library')
    assert s.state.cards[top].face==0
    roundtrip(s)


@pytest.mark.parametrize('name',['Planar Atlas','Fertile Thicket',"Quest for Ula's Temple",'Nissa, Steward of Elements'])
def test_empty_library_finishes_optional_look_and_entry(cards,name):
    from tests.test_rules_refused_look import thin_library
    s=setup(cards)
    if name==NAMES[4]:
        source=cast(s,name,x_value=2)
        thin_library(s,[])
        act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
        settle(s)
    else:
        source=put(s,name,'hand' if name!='Quest for Ula\'s Temple' else 'battlefield')
        thin_library(s,[])
        if name=='Planar Atlas':
            mana(s,C=2)
            act(s,'p1',type='cast_spell',card_id=source.id)
        elif name=='Fertile Thicket':
            act(s,'p1',type='play_land',card_id=source.id)
        else:
            to_phase(s,'upkeep',turn=4)
        settle(s)
        answer(s,['yes'])
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('replacement',['Containment Priest','Hallowed Moonlight',"Grafdigger's Cage"])
def test_nissa_optional_entry_uses_native_creature_entry_replacements(cards,replacement):
    s=setup(cards)
    nissa=cast(s,NAMES[4],x_value=2)
    if replacement=='Hallowed Moonlight':
        cast(s,replacement)
    else:
        put(s,replacement,'battlefield')
    top=stack_library(s,['Grizzly Bears'])[0]
    act(s,'p1',type='activate_ability',card_id=nissa.id,ability=1)
    settle(s)
    answer(s,[top])
    assert s.state.cards[top].zone==('p1:library' if replacement=="Grafdigger's Cage" else 'p1:exile')
    assert s.state.zones['p1:library'][0]==top if replacement=="Grafdigger's Cage" else top not in s.state.zones['p1:library']
    roundtrip(s)
