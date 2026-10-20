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
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/conditional_search_destination_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAMES = ['Loyal Inventor','Guidelight Pathmaker','From Father to Son','Stoic Farmer','Embermouth Sentinel','Nazahn, Revered Bladesmith','Rootpath Purifier']

@pytest.mark.parametrize('name',NAMES)
def test_canonical_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'




def setup(cards):
    data=json.loads((Path(__file__).parent/'fixtures/conditional_search_destination_cards.json').read_text())
    names=[c['name'] for c in data]
    s=table(cards,[*names,"Smuggler's Copter","Korlash, Heir to Blackblade","Rite of Flame"],names,names)
    to_phase(s,'main1',turn=1)
    return s




def cast(s,name,**kw):
    source=put(s,name,'hand')
    mana(s,C=20,W=10,U=10,B=10,R=10,G=10)
    act(s,'p1',type='cast_spell',card_id=source.id,**kw)
    settle(s)
    return source


def accept_search(s):
    d=s.state.rules.decision
    if d.resume['step']=='search_may':
        answer(s,['yes'])
    assert s.state.rules.decision.resume['step']=='search'


def find_named(s,name):
    d=s.state.rules.decision
    return next(o.id for o in d.options if s.state.cards[o.id].name==name)


@pytest.mark.parametrize('name,qualifier,found,destination',[
    ('Loyal Inventor',False,'Sol Ring','top'),
    ('Loyal Inventor',True,'Sol Ring','hand'),
    ('Embermouth Sentinel',False,'Forest','top'),
    ('Embermouth Sentinel',True,'Forest','battlefield'),
    ('Stoic Farmer',False,'Plains','hand'),
    ('Stoic Farmer',True,'Plains','battlefield'),
    ('Guidelight Pathmaker',False,'Sol Ring','battlefield'),
    ('Guidelight Pathmaker',False,'Meteor Golem','hand'),
])
def test_conditional_search_actual_destinations(cards,name,qualifier,found,destination):
    s=setup(cards)
    if qualifier:
        if name=='Loyal Inventor':
            put(s,'Royal Assassin','battlefield')
        elif name=='Embermouth Sentinel':
            put(s,'Shivan Dragon','battlefield')
        else:
            put(s,'Island','battlefield',pid='p2')
    cast(s,name)
    accept_search(s)
    cid=find_named(s,found)
    answer(s,[cid])
    assert s.state.rules.decision is None
    if destination=='top':
        assert s.state.cards[s.state.zones['p1:library'][0]].name==found
        assert cid not in s.state.cards # shuffle renews hidden object IDs
    else:
        assert s.state.cards[cid].zone=='p1:'+destination
        if destination=='battlefield' and name!='Guidelight Pathmaker':
            assert s.state.cards[cid].tapped
    roundtrip(s)


@pytest.mark.parametrize('flashback',[False,True])
def test_from_father_to_son_actual_cast_origin_controls_entry(cards,flashback):
    s=setup(cards)
    source=put(s,'From Father to Son','graveyard' if flashback else 'hand')
    mana(s,C=15,W=10)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    accept_search(s)
    cid=find_named(s,"Smuggler's Copter")
    answer(s,[cid])
    assert s.state.cards[cid].zone==('p1:battlefield' if flashback else 'p1:hand')
    assert s.state.cards[source.id].zone==('p1:exile' if flashback else 'p1:graveyard')
    roundtrip(s)


@pytest.mark.parametrize('found',['Hammer of Nazahn','Bonesplitter'])
def test_actual_nazahn_search_named_hammer_or_other_equipment(cards,found):
    s=setup(cards)
    source=cast(s,'Nazahn, Revered Bladesmith')
    accept_search(s)
    cid=find_named(s,found)
    answer(s,[cid])
    if found=='Hammer of Nazahn':
        for _ in range(3):
            d=s.state.rules.decision
            if d is None:
                break
            answer(s,[d.options[0].id])
        assert s.state.cards[cid].zone=='p1:battlefield'
    else:
        assert s.state.cards[cid].zone=='p1:hand'
    assert s.state.cards[source.id].zone=='p1:battlefield'
    roundtrip(s)


def test_fixed_named_card_and_genuine_source_names_are_distinct(cards):
    from app.rules import copying, scripts
    text='When Nazahn enters, search your library for an Equipment card and reveal it. If you reveal a card named Hammer of Nazahn this way, put it onto the battlefield. Otherwise, put that card into your hand. Then shuffle.'
    normalized=scripts.self_text(text,'Nazahn, Revered Bladesmith')
    assert normalized.startswith('When ~ enters')
    assert 'named Hammer of Nazahn' in normalized
    renamed=copying.renamed(text,'Nazahn, Revered Bladesmith','Sakashima the Impostor')
    assert renamed.startswith('When Sakashima the Impostor enters')
    assert 'named Hammer of Nazahn' in renamed


def test_actual_sakashima_copy_of_nazahn_keeps_hammer_fixed_name(cards):
    s=setup(cards)
    original=put(s,'Nazahn, Revered Bladesmith','battlefield')
    source=cast(s,'Sakashima the Impostor')
    d=s.state.rules.decision
    assert d is not None
    selected=next((o.id for o in d.options if o.card_id==original.id or o.id==original.id),None)
    assert selected is not None
    answer(s,[selected])
    accept_search(s)
    cid=find_named(s,'Hammer of Nazahn')
    answer(s,[cid])
    for _ in range(3):
        d=s.state.rules.decision
        if d is None:
            break
        answer(s,[d.options[0].id])
    assert s.state.cards[cid].zone=='p1:battlefield'
    assert s.state.cards[source.id].zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('flashback',[False,True])
def test_actual_spell_copy_was_not_cast_from_graveyard(cards,flashback):
    s=setup(cards)
    source=put(s,'From Father to Son','graveyard' if flashback else 'hand')
    rev=put(s,'Reverberate','hand')
    mana(s,C=20,W=10,R=2)
    act(s,'p1',type='set_prefs',hold_priority=True)
    act(s,'p1',type='cast_spell',card_id=source.id)
    act(s,'p1',type='cast_spell',card_id=rev.id,targets=[source.id])
    settle(s)
    for original in [False,True]:
        d=s.state.rules.decision
        assert (d.resume['ctx']['source_card']==source.id)==original
        cid=find_named(s,"Smuggler's Copter")
        answer(s,[cid])
        assert s.state.cards[cid].zone==('p1:battlefield' if original and flashback else 'p1:hand')
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('name',['Loyal Inventor','Guidelight Pathmaker','Embermouth Sentinel'])
def test_optional_search_decline_keeps_library_identical(cards,name):
    s=setup(cards)
    source=put(s,name,'hand')
    mana(s,C=20,U=10,G=10,W=10)
    before=list(s.state.zones['p1:library'])
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    assert s.state.rules.decision.resume['step']=='search_may'
    answer(s,['no'])
    assert s.state.zones['p1:library']==before
    roundtrip(s)


@pytest.mark.parametrize('name',['Loyal Inventor','Guidelight Pathmaker','Stoic Farmer','Embermouth Sentinel','Nazahn, Revered Bladesmith'])
def test_found_zero_finishes_search_and_shuffles_once(cards,name):
    s=setup(cards)
    cast(s,name)
    accept_search(s)
    before=set(s.state.zones['p1:library'])
    answer(s,[])
    assert s.state.rules.decision is None
    assert not before.intersection(s.state.zones['p1:library'])
    roundtrip(s)



def test_rootpath_supplies_real_basic_creature_land_prohibited_entry_without_top_fallback(cards,monkeypatch):
    from app.rules.plan import Plan
    s=setup(cards)
    put(s,'Rootpath Purifier','battlefield')
    put(s,'Shivan Dragon','battlefield')
    put(s,"Grafdigger's Cage",'battlefield')
    cast(s,'Embermouth Sentinel')
    accept_search(s)
    cid=find_named(s,'Dryad Arbor')
    assert 'Basic' in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[cid]).supertypes
    from app.game import resolve as resolving
    native_shuffle=resolving.shuffle_data
    original_index=s.state.zones['p1:library'].index(cid)
    def controlled_shuffle(size,rng):
        data=native_shuffle(size,rng)
        perm=list(range(size))
        if perm[0]==original_index:
            perm=perm[1:]+perm[:1]
        return data.model_copy(update={'perm':perm})
    monkeypatch.setattr(resolving,'shuffle_data',controlled_shuffle)
    answer(s,[cid])
    assert s.state.rules.decision is None
    assert not any(c.name=='Dryad Arbor' and c.zone=='p1:battlefield' for c in s.state.cards.values())
    # Entry was prohibited. The card stayed in and was shuffled with the library;
    # no fallback move may put the renewed hidden object on top afterward.
    assert cid not in s.state.cards
    steps=s.history.actions[-1].r
    assert isinstance(steps,list)
    shuffles=[i for i,step in enumerate(steps) if step['type']=='shuffle']
    assert len(shuffles)==1
    assert not any(step['type']=='move' and step.get('to',{}).get('zone')=='library' for step in steps[shuffles[0]+1:])
    assert s.state.cards[s.state.zones['p1:library'][0]].name!='Dryad Arbor'
    roundtrip(s)


def test_rootpath_only_affects_controlled_lands_and_own_library_lands(cards):
    from app.rules.plan import Plan
    s=setup(cards)
    source=put(s,'Rootpath Purifier','battlefield')
    own=put(s,'Mistveil Plains','battlefield')
    theirs=put(s,'Mistveil Plains','battlefield',pid='p2')
    library=next(c for c in s.state.cards.values() if c.name=='Dryad Arbor' and c.owner=='p1')
    their_library=next(c for c in s.state.cards.values() if c.name=='Dryad Arbor' and c.owner=='p2')
    def basic(cid):
        return 'Basic' in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[cid]).supertypes
    assert basic(own.id) and basic(library.id)
    assert not basic(theirs.id) and not basic(their_library.id)
    act(s,'p1',type='move',card_ids=[library.id],to={'zone':'hand'})
    assert not basic(library.id)
    act(s,'p1',type='move',card_ids=[library.id],to={'zone':'graveyard'})
    assert not basic(library.id)
    act(s,'p1',type='move',card_ids=[library.id],to={'zone':'library'},position='top')
    assert basic(library.id)
    act(s,'p1',type='set_controller',card_ids=[source.id],player='p2')
    assert not basic(own.id) and not basic(library.id)
    assert basic(theirs.id) and basic(their_library.id)
    roundtrip(s)



@pytest.mark.parametrize('name',['Rite of Flame','Kindle','Korlash, Heir to Blackblade','Relentless Rats','Shadowborn Apostle','Seven Dwarves'])
def test_named_literal_consumers_keep_existing_full_cards(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def test_rite_of_flame_counts_fixed_name_across_all_graveyards(cards):
    from tests.game_helpers import mana_pool
    s=setup(cards)
    mine=[c.id for c in s.state.cards.values() if c.owner=='p1' and c.name=='Rite of Flame']
    act(s,'p1',type='move',card_ids=[mine[0]],to={'zone':'hand'})
    act(s,'p1',type='move',card_ids=[mine[1]],to={'zone':'graveyard'})
    put(s,'Rite of Flame','graveyard',pid='p2')
    mana(s,R=1)
    act(s,'p1',type='cast_spell',card_id=mine[0])
    settle(s)
    assert mana_pool(s)['R']==4
    roundtrip(s)


def test_actual_sakashima_grandeur_discards_original_fixed_named_card(cards):
    s=setup(cards)
    put(s,'Swamp','battlefield')
    original=put(s,'Korlash, Heir to Blackblade','battlefield')
    source=cast(s,'Sakashima the Impostor')
    d=s.state.rules.decision
    chosen=next(o.id for o in d.options if o.card_id==original.id or o.id==original.id)
    answer(s,[chosen])
    discard=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Korlash, Heir to Blackblade' and c.id!=original.id)
    act(s,'p1',type='move',card_ids=[discard.id],to={'zone':'hand'})
    from app.rules import scripts
    from app.rules.plan import Plan
    definitions=scripts.definitions(Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source.id]))
    index=next(i for i,d in definitions.items() if d.get('kind')=='activated' and any(e.get('do')=='search' for e in d.get('effects',[])))
    act(s,'p1',type='activate_ability',card_id=source.id,ability=index,cost_choices=[{'component':0,'cards':[discard.id]}])
    settle(s)
    assert s.state.cards[discard.id].zone=='p1:graveyard'
    assert s.state.rules.decision.resume['step']=='search'
    answer(s,[])
    roundtrip(s)



@pytest.mark.parametrize('name',['Loyal Inventor','Guidelight Pathmaker','Stoic Farmer','Embermouth Sentinel','Nazahn, Revered Bladesmith'])
def test_opposition_agent_diversion_cannot_be_overridden_by_destination_branch(cards,name):
    s=setup(cards)
    put(s,'Opposition Agent','battlefield',pid='p2')
    put(s,'Royal Assassin','battlefield')
    put(s,'Shivan Dragon','battlefield')
    put(s,'Island','battlefield',pid='p3')
    cast(s,name)
    accept_search(s)
    d=s.state.rules.decision
    assert d.decider=='p2'
    cid=d.options[0].id
    roundtrip(s)
    act(s,'p2',type='choose',decision_id=d.id,option_ids=[cid])
    settle(s)
    assert s.state.cards[cid].zone=='p1:exile'
    assert any(p.player=='p2' and p.card==cid for p in s.state.rules.permissions)
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('found,visible',[('Sol Ring',True),('Meteor Golem',False)])
def test_search_choice_and_result_privacy_http_and_ws(cards,settings,found,visible):
    from fastapi.testclient import TestClient

    from app.main import create_app
    s=setup(cards)
    cast(s,'Guidelight Pathmaker')
    accept_search(s)
    cid=find_named(s,found)
    with TestClient(create_app(settings)) as client:
        deck_id=client.post('/api/decks',json={'text':'Commander\n1 Krenko, Mob Boss\nDeck\n20 Forest'}).json()['id']
        game=client.post('/api/games',json={'mode':'lan','players':[{'name':'Alice','deck_id':deck_id},{'name':'Bob','deck_id':deck_id}]}).json()
        gid=game['game']['id']
        bob=client.post('/api/join',json={'code':game['game']['code'],'name':'Bob'}).json()['token']
        spec=client.post('/api/join',json={'code':game['game']['code'],'spectate':True}).json()['token']
        client.app.state.services.hub.get(gid).game=s
        for done in [False,True]:
            if done:
                answer(s,[cid])
            for token in [bob,spec]:
                response=client.get(f'/api/games/{gid}/view',headers={'X-Seat-Token':token})
                assert response.status_code==200
                with client.websocket_connect(f'/ws/games/{gid}?token={token}') as ws:
                    frame=ws.receive_json()
                    assert frame['type']=='state'
                assert (cid in response.text)==(done and visible)
                assert (cid in json.dumps(frame))==(done and visible)
    roundtrip(s)


def test_actual_rootpath_copy_and_source_departure_update_basic_status(cards):
    from app.rules.plan import Plan
    s=setup(cards)
    original=put(s,'Rootpath Purifier','battlefield')
    source=cast(s,'Sakashima the Impostor')
    d=s.state.rules.decision
    chosen=next(o.id for o in d.options if o.card_id==original.id or o.id==original.id)
    answer(s,[chosen])
    land=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Dryad Arbor')
    def basic():
        return 'Basic' in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[land.id]).supertypes
    assert basic()
    cast(s,'Swords to Plowshares',targets=[original.id])
    assert basic()
    spell=next(c for c in s.state.cards.values() if c.owner=='p2' and c.name=='Swords to Plowshares')
    act(s,'p1',type='move',card_ids=[spell.id],to={'player':'p2','zone':'hand'})
    from tests.test_rules_bandmate_references import wait_priority
    wait_priority(s,'p2')
    mana(s,pid='p2',W=1)
    act(s,'p2',type='cast_spell',card_id=spell.id,targets=[source.id])
    settle(s)
    assert not basic()
    roundtrip(s)
