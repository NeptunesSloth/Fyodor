"""Real Oracle: exile-controller LKI and simultaneous searched-land entry."""
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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

WINDS='Winds of Abandon'
SETTLE='Settle the Wreckage'


@pytest.fixture()
def cards(settings):
    raw=json.loads((Path(__file__).parent/'fixtures/exile_land_compensation_cards.json').read_text())
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(raw):
        base[c['name']]=card(c['name'],set_code='elc',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/exile_land_compensation_cards.json').read_text())]
    return table(cards,names,names,names)


def cast(s,name=WINDS,targets=(),overload=False):
    source=put(s,name,'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':4 if overload else 2 if name==SETTLE else 1,'W':2 if overload or name==SETTLE else 1})
    act(s,'p1',type='cast_spell',card_id=source.id,targets=list(targets),**({'alt_cost':f'{source.id}:1'} if overload else {}))
    roundtrip(s)
    settle(s)
    return source


def answer(s,ids):
    d=s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s,d.decider or d.player,type='choose',decision_id=d.id,option_ids=list(ids))
    settle(s)


def find(s,n=1):
    d=s.state.rules.decision
    assert d is not None and d.kind=='choose_cards'
    assert all('Basic' in s.cards.get(s.state.cards[o.card_id].card_id)['type_line'] for o in d.options)
    ids=[o.id for o in d.options[:n]]
    answer(s,ids)
    return ids


def steps(s,kind):
    return [step for a in s.history.actions if isinstance(getattr(a,'r',None),list) for step in a.r if step.get('type')==kind]


def bear(s,pid='p2'):
    return put(s,'Grizzly Bears','battlefield',pid=pid)


def token(s,pid='p2',name='Refund token'):
    before=set(s.state.cards)
    act(s,pid,type='create_token',player=pid,token={'name':name,'type_line':'Token Creature — Soldier','power':'1','toughness':'1','text':''})
    return next(c for cid,c in s.state.cards.items() if cid not in before)


def attacking(s,creatures,pid='p2'):
    to_phase(s,'declare_attackers',turn=2)
    act(s,pid,type='declare_attackers',attackers=[{'card_id':c.id,'target':'p1'} for c in creatures])
    wait_priority(s,'p1')


@pytest.mark.parametrize('name',[WINDS,SETTLE])
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def test_normal_winds_searches_for_last_controller_not_owner(cards):
    s=setup(cards)
    c=bear(s,'p1')
    act(s,'p1',type='set_controller',card_ids=[c.id],player='p2')
    cast(s,targets=[c.id])
    assert s.state.cards[c.id].zone=='p1:exile'
    d=s.state.rules.decision
    assert d is not None and d.player=='p2' and d.max_choices==1
    found=find(s)
    assert all(s.state.cards[cid].zone=='p2:battlefield' and s.state.cards[cid].tapped for cid in found)
    assert [a['player'] for a in steps(s,'shuffle')]==['p2']
    roundtrip(s)


def test_overload_collects_private_searches_then_enters_all_found_lands_together(cards):
    s=setup(cards)
    own=bear(s,'p1')
    a=bear(s)
    b=bear(s,'p3')
    cast(s,overload=True)
    assert s.state.cards[own.id].zone=='p1:battlefield'
    assert s.state.cards[a.id].zone=='p2:exile' and s.state.cards[b.id].zone=='p3:exile'
    assert s.state.rules.decision.player=='p2'
    first=find(s)
    assert all(s.state.cards[cid].zone=='p2:library' for cid in first)
    assert not steps(s,'shuffle')
    assert s.state.rules.decision.player=='p3'
    second=find(s)
    assert all(s.state.cards[cid].zone.endswith(':battlefield') and s.state.cards[cid].tapped for cid in first+second)
    batches=[a for a in steps(s,'move') if a.get('to',{}).get('zone')=='battlefield'
             and set(a.get('card_ids',[]))==set(first+second)]
    assert len(batches)==1  # one real simultaneous entry action, across controllers
    assert [a['player'] for a in steps(s,'shuffle')]==['p2','p3']
    roundtrip(s)


def test_tokens_are_counted_even_after_ceasing_to_exist(cards):
    s=setup(cards)
    c=token(s)
    cast(s,targets=[c.id])
    assert c.id not in s.state.cards
    assert s.state.rules.decision.player=='p2' and s.state.rules.decision.max_choices==1
    find(s)
    assert [a['player'] for a in steps(s,'shuffle')]==['p2']
    roundtrip(s)


def test_many_creatures_controlled_by_one_player_give_that_many_search_slots(cards):
    s=setup(cards)
    bear(s)
    token(s)
    token(s,name='Other token')
    cast(s,overload=True)
    d=s.state.rules.decision
    assert d.player=='p2' and d.max_choices==1
    found=[]
    for _ in range(3):
        d=s.state.rules.decision
        assert d.player=='p2' and d.max_choices==1
        assert not set(found)&{o.id for o in d.options}
        found+=find(s)
    assert len(set(found))==3 and all(s.state.cards[cid].tapped for cid in found)
    assert [a['player'] for a in steps(s,'shuffle')]==['p2']
    roundtrip(s)


def test_mandatory_failed_find_still_shuffles(cards):
    s=setup(cards)
    c=bear(s)
    cast(s,targets=[c.id])
    answer(s,[])
    assert [a['player'] for a in steps(s,'shuffle')]==['p2']
    roundtrip(s)


def test_winds_cannot_target_own_creature(cards):
    s=setup(cards)
    own=bear(s,'p1')
    source=put(s,WINDS,'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'W':1})
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=source.id,targets=[own.id])
    assert s.state.model_dump(mode='json')==before
    roundtrip(s)


@pytest.mark.parametrize('accept',[False,True])
def test_settle_exiles_only_attackers_then_optional_search(cards,accept):
    s=setup(cards)
    a=bear(s)
    b=token(s)
    idle=put(s,'Dryad Arbor','battlefield',pid='p2')
    attacking(s,[a,b])
    cast(s,SETTLE,targets=['p2'])
    assert s.state.cards[a.id].zone=='p2:exile' and b.id not in s.state.cards
    assert s.state.cards[idle.id].zone=='p2:battlefield'
    d=s.state.rules.decision
    assert d.player=='p2' and d.kind=='confirm'
    answer(s,['yes' if accept else 'no'])
    if accept:
        assert s.state.rules.decision.max_choices==2
        find(s,2)
    assert [a['player'] for a in steps(s,'shuffle')]==(['p2'] if accept else [])
    roundtrip(s)


@pytest.mark.parametrize('accept',[False,True])
def test_settle_zero_attackers_can_search_for_zero_and_shuffle_if_accepted(cards,accept):
    s=setup(cards)
    cast(s,SETTLE,targets=['p2'])
    assert s.state.rules.decision.player=='p2' and s.state.rules.decision.kind=='confirm'
    answer(s,['yes' if accept else 'no'])
    if accept and s.state.rules.decision is not None:
        assert s.state.rules.decision.max_choices==0
        answer(s,[])
    assert [a['player'] for a in steps(s,'shuffle')]==(['p2'] if accept else [])
    roundtrip(s)


def test_mandatory_prohibited_search_still_shuffles_affected_library(cards):
    s=setup(cards)
    put(s,'Stranglehold','battlefield')
    c=bear(s)
    cast(s,targets=[c.id])
    assert s.state.rules.decision is None
    assert [a['player'] for a in steps(s,'shuffle')]==['p2']
    roundtrip(s)


def test_optional_prohibited_settle_search_does_not_shuffle(cards):
    s=setup(cards)
    put(s,'Stranglehold','battlefield')
    c=bear(s)
    attacking(s,[c])
    cast(s,SETTLE,targets=['p2'])
    assert s.state.rules.decision is None and not steps(s,'shuffle')
    roundtrip(s)


def test_ashiok_does_not_stop_another_players_spell_causing_controller_to_search(cards):
    s=setup(cards)
    ashiok=put(s,'Ashiok, Dream Render','battlefield')
    act(s,'p1',type='set_counter',card_id=ashiok.id,kind='loyalty',value=5)
    c=bear(s)
    cast(s,targets=[c.id])
    assert s.state.rules.decision.player=='p2'
    find(s)
    assert [a['player'] for a in steps(s,'shuffle')]==['p2']
    roundtrip(s)


def test_native_mindcensor_limits_compensation_search_to_top_four(cards):
    s=setup(cards)
    put(s,'Aven Mindcensor','battlefield')
    basic=next(c for c in s.state.cards.values() if c.owner=='p2' and c.name=='Island')
    act(s,'p2',type='move',card_ids=[basic.id],to={'player':'p2','zone':'library'},index=0)
    top=set(s.state.zones['p2:library'][:4])
    c=bear(s)
    cast(s,targets=[c.id])
    d=s.state.rules.decision
    assert d.options and {o.card_id for o in d.options}<=top
    find(s)
    roundtrip(s)


def test_native_opposition_agent_controls_and_exiles_the_compensation_find(cards):
    from app.rules.view import rules_view

    s=setup(cards)
    put(s,'Opposition Agent','battlefield')
    c=bear(s)
    cast(s,targets=[c.id])
    d=s.state.rules.decision
    assert d.player=='p2' and d.decider=='p1'
    assert rules_view(s.state,'p3',s.cards)['decision']['kind']=='waiting'
    found=find(s)
    assert all(s.state.cards[cid].zone=='p2:exile' for cid in found)
    assert any(p.card in found and p.player=='p1' for p in s.state.rules.permissions)
    assert [a['player'] for a in steps(s,'shuffle')]==['p2']
    roundtrip(s)


def test_overloaded_winds_bypasses_creature_protection_and_keeps_own_creatures(cards):
    s=setup(cards)
    protected=put(s,'Blood Baron of Vizkopa','battlefield',pid='p2')
    own=bear(s,'p1')
    source=put(s,WINDS,'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'W':1})
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=source.id,targets=[protected.id])
    assert s.state.model_dump(mode='json')==before
    cast(s,overload=True)
    assert s.state.cards[protected.id].zone=='p2:exile' and s.state.cards[own.id].zone=='p1:battlefield'
    find(s)
    roundtrip(s)


def test_settle_targets_player_and_exiles_hexproof_attackers(cards):
    s=setup(cards)
    c=bear(s)
    attacking(s,[c])
    spell=put(s,'Heroic Intervention','hand',pid='p2')
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'C':1,'G':1})
    act(s,'p2',type='cast_spell',card_id=spell.id)
    settle(s)
    wait_priority(s,'p1')
    cast(s,SETTLE,targets=['p2'])
    assert s.state.cards[c.id].zone=='p2:exile'
    answer(s,['yes'])
    find(s)
    roundtrip(s)


def test_animated_noncreature_card_exiled_this_way_counts_by_permanent_lki(cards):
    s=setup(cards)
    nexus=put(s,'Inkmoth Nexus','battlefield',pid='p2')
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'C':1})
    act(s,'p2',type='activate_ability',card_id=nexus.id,ability=1)
    settle(s)
    wait_priority(s,'p1')
    cast(s,targets=[nexus.id])
    assert s.state.cards[nexus.id].zone=='p2:exile'
    assert s.state.rules.decision.max_choices==1
    find(s)
    roundtrip(s)


@pytest.mark.parametrize('name',[WINDS,SETTLE])
def test_winds_searches_once_per_exile_while_settle_searches_once_for_the_total(cards,name):
    s=setup(cards)
    put(s,'Ob Nixilis, Unshackled','battlefield')
    creatures=[bear(s),token(s,name='Search token A'),token(s,name='Search token B')]
    if name==SETTLE:
        attacking(s,creatures)
        cast(s,name,targets=['p2'])
        answer(s,['yes'])
        find(s,3)
    else:
        cast(s,overload=True)
        for _ in creatures:
            find(s)
    assert s.state.players['p2'].life==(10 if name==WINDS else 30)
    assert [a['player'] for a in steps(s,'shuffle')]==['p2']
    roundtrip(s)


def test_overload_with_no_opposing_creatures_does_not_search_or_shuffle(cards):
    s=setup(cards)
    own=bear(s,'p1')
    cast(s,overload=True)
    assert s.state.cards[own.id].zone=='p1:battlefield'
    assert s.state.rules.decision is None and not steps(s,'shuffle')
    roundtrip(s)


def test_commander_exiled_then_moved_to_command_zone_still_gets_compensation(cards):
    s=setup(cards)
    commander=put(s,"Atraxa, Praetors' Voice",'battlefield',pid='p2')
    cast(s,targets=[commander.id])
    d=s.state.rules.decision
    if d is not None and d.kind=='confirm' and 'command zone' in d.prompt:
        answer(s,['yes'])
    assert s.state.rules.decision.player=='p2' and s.state.rules.decision.max_choices==1
    find(s)
    d=s.state.rules.decision
    assert d is not None and d.kind=='confirm' and 'command zone' in d.prompt
    answer(s,['yes'])
    assert s.state.cards[commander.id].zone=='p2:command'
    assert [a['player'] for a in steps(s,'shuffle')]==['p2']
    roundtrip(s)


def test_settle_cannot_target_player_with_hexproof(cards):
    s=setup(cards)
    put(s,'Leyline of Sanctity','battlefield',pid='p2')
    source=put(s,SETTLE,'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':2,'W':2})
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=source.id,targets=['p2'])
    assert s.state.model_dump(mode='json')==before
    roundtrip(s)


def test_repeated_mindcensor_searches_cannot_refind_reserved_cards_or_see_fifth_card(cards):
    s=setup(cards)
    put(s,'Aven Mindcensor','battlefield')
    basics=[c.id for c in s.state.cards.values() if c.owner=='p2' and c.name=='Island'][:4]
    assert len(basics)==4
    act(s,'p2',type='move',card_ids=basics,to={'player':'p2','zone':'library'},index=0)
    top=set(s.state.zones['p2:library'][:4])
    bear(s)
    for i in range(4):
        token(s,name=f'Mindcensor token {i}')
    cast(s,overload=True)
    found=[]
    for _ in range(4):
        d=s.state.rules.decision
        assert d.player=='p2' and {o.id for o in d.options}<=top-set(found)
        found+=find(s)
        assert all(s.state.cards[cid].zone=='p2:library' for cid in found)
    d=s.state.rules.decision
    assert d is not None and not d.options
    answer(s,[])
    assert len(set(found))==4 and all(s.state.cards[cid].zone=='p2:battlefield' for cid in found)
    assert [a['player'] for a in steps(s,'shuffle')]==['p2']
    roundtrip(s)
