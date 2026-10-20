"""Scholar's revealed search retains its native origin and optional catch-up destination."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

NAME='Scholar of New Horizons'

@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/scholar_new_horizons_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='snh',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards,counts=(1,2,0)):
    names=[NAME,'Plains','Hallowed Fountain','Savannah','Island','Forest','Ashiok, Dream Render','Aven Mindcensor','Opposition Agent','Stranglehold']
    s=table(cards,names,names,names)
    for pid,n in zip(('p1','p2','p3'),counts,strict=True):
        act(s,pid,type='set_prefs',hold_priority=True,stops_my_turn=['main1'])
        lands=[c.id for c in s.state.cards.values() if c.owner==pid and c.name==('Forest' if pid=='p1' else 'Island')][:n]
        assert len(lands)==n
        if lands:
            act(s,pid,type='move',card_ids=lands,to={'player':pid,'zone':'battlefield'})
    source=put(s,NAME,'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'W':1})
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].counters['+1/+1']==1
    until(s,lambda s:s.state.turn.number==4 and s.state.turn.phase=='main1' and s.state.rules.decision is None)
    for name in ('Plains','Hallowed Fountain','Savannah'):
        put(s,name,'library')
    return s,source


def activate(s,source):
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    assert s.state.cards[source.id].tapped
    assert s.state.cards[source.id].counters.get('+1/+1',0)==0
    settle(s)


def answer(s,ids):
    d=s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s,d.decider or d.player,type='choose',decision_id=d.id,option_ids=ids)
    settle(s)


def find(s,name):
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='search'
    option=next(o for o in d.options if o.card_id and s.state.cards[o.card_id].name==name)
    cid=option.card_id
    answer(s,[option.id])
    return cid


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level=='FULL'


@pytest.mark.parametrize(('counts','accept','zone'),[((1,2,0),True,'battlefield'),((1,2,0),False,'hand'),((1,1,1),None,'hand'),((2,1,1),None,'hand'),((1,0,2),True,'battlefield')])
def test_search_destination_uses_individual_opponent_land_comparison_and_choice(cards,counts,accept,zone):
    s,source=setup(cards,counts)
    activate(s,source)
    d=s.state.rules.decision
    assert {'Plains','Hallowed Fountain','Savannah'} <= {s.state.cards[o.card_id].name for o in d.options if o.card_id}
    assert all(s.state.cards[o.card_id].name!='Island' for o in d.options if o.card_id)
    cid=find(s,'Savannah')
    if accept is not None:
        d=s.state.rules.decision
        assert d is not None and d.resume['step']=='conditional_search_destination'
        assert s.state.cards[cid].zone=='p1:library'
        answer(s,['yes' if accept else 'no'])
    assert s.state.cards[cid].zone=='p1:'+zone
    if zone=='battlefield':
        assert s.state.cards[cid].tapped
    assert s.state.rules.decision is None
    roundtrip(s)


def test_fail_to_find_is_legal_and_still_finishes_without_destination_choice(cards):
    s,source=setup(cards)
    activate(s,source)
    before=set(s.state.zones['p1:library'])
    answer(s,[])
    assert set(s.state.zones['p1:library'])!=before  # native shuffle replaces hidden IDs
    assert s.state.rules.decision is None
    roundtrip(s)


def test_search_prohibition_skips_selection_and_cost_is_still_paid(cards):
    s,source=setup(cards)
    put(s,'Stranglehold','battlefield',pid='p2')
    before=list(s.state.zones['p1:library'])
    activate(s,source)
    assert s.state.rules.decision is None
    assert s.state.zones['p1:library']!=before  # mandatory search's shuffle is independent
    roundtrip(s)


def test_cannot_activate_without_counter_cost(cards):
    s,source=setup(cards)
    act(s,'p1',type='set_counter',card_id=source.id,kind='+1/+1',value=0)
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    assert not s.state.cards[source.id].tapped
    roundtrip(s)


def test_cost_can_remove_another_controlled_permanents_non_plus_counter(cards):
    s,source=setup(cards)
    act(s,'p1',type='set_counter',card_id=source.id,kind='+1/+1',value=0)
    land=next(c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.name=='Forest')
    act(s,'p1',type='set_counter',card_id=land.id,kind='charge',value=1)
    activate(s,source)
    assert s.state.cards[land.id].counters.get('charge',0)==0
    find(s,'Plains')
    answer(s,['no'])
    assert s.state.cards[land.id].counters.get('charge',0)==0
    roundtrip(s)


def test_opposition_agent_overrides_destination_and_controls_native_search(cards):
    s,source=setup(cards)
    put(s,'Opposition Agent','battlefield',pid='p2')
    activate(s,source)
    d=s.state.rules.decision
    assert d is not None and d.decider=='p2'
    cid=find(s,'Plains')
    assert s.state.cards[cid].zone=='p1:exile'
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('initially_ahead',[False,True])
def test_land_condition_is_evaluated_at_resolution_even_after_source_leaves(cards,initially_ahead):
    s,source=setup(cards,(1,2,0) if initially_ahead else (1,1,0))
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    if initially_ahead:
        lands=[c.id for c in s.state.cards.values() if c.zone=='p2:battlefield' and c.name=='Island']
        act(s,'p2',type='move',card_ids=lands,to={'player':'p2','zone':'graveyard'})
    else:
        land=next(c for c in s.state.cards.values() if c.owner=='p2' and c.name=='Island' and c.zone!='p2:battlefield')
        act(s,'p2',type='move',card_ids=[land.id],to={'player':'p2','zone':'battlefield'})
    roundtrip(s)
    settle(s)
    cid=find(s,'Plains')
    if not initially_ahead:
        assert s.state.rules.decision.resume['step']=='conditional_search_destination'
        answer(s,['yes'])
    assert s.state.cards[cid].zone==('p1:hand' if initially_ahead else 'p1:battlefield')
    roundtrip(s)


def test_mindcensor_limits_search_and_only_found_card_is_publicly_revealed(cards):
    from tests.test_rules_abundance import set_library

    s,source=setup(cards)
    top=set_library(s,['Forest','Island','Forest','Plains','Savannah'])
    put(s,'Aven Mindcensor','battlefield',pid='p2')
    activate(s,source)
    d=s.state.rules.decision
    assert d is not None and {o.card_id for o in d.options}=={top[3]}
    assert s.view('p2')['rules']['decision']['kind']=='waiting'
    cid=find(s,'Plains')
    assert s.view('p2')['cards'].get(cid,{}).get('name')=='Plains'
    assert not s.view('p2')['cards'].get(top[4],{}).get('name')
    answer(s,['yes'])
    assert s.state.cards[cid].zone=='p1:battlefield' and s.state.cards[cid].tapped
    roundtrip(s)


def test_found_shockland_retains_library_origin_and_forced_tapped_entry(cards):
    s,source=setup(cards)
    activate(s,source)
    cid=find(s,'Hallowed Fountain')
    assert s.state.cards[cid].zone=='p1:library'
    life=s.state.players['p1'].life
    answer(s,['yes'])
    assert s.state.cards[cid].zone=='p1:battlefield' and s.state.cards[cid].tapped
    assert s.state.players['p1'].life==life
    assert s.state.rules.decision is None
    roundtrip(s)
