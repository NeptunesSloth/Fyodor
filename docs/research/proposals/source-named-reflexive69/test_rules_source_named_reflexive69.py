"""Native public-mill selections and exact hand outcomes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures/source_named_reflexive69_cards.json').read_text())):
        extra = {k:v for k,v in c.items() if k not in ('name','set_code','number')}
        if c.get('faces'):
            extra['card_faces'] = c['faces']
        if c.get('related_cards') or c.get('related_tokens'):
            extra['all_parts'] = [*c.get('related_cards', []), *[{**part, 'component': 'token'} for part in c.get('related_tokens', [])]]
        base[c['name']] = card(c['name'], set_code='oc59', number=str(i), **extra)
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()

def setup(cards):
    names = list(dict.fromkeys([c['name'] for c in json.loads((Path(__file__).parent/'fixtures/source_named_reflexive69_cards.json').read_text()) if c['name'] != 'Urza, Planeswalker'] + ['Grizzly Bears','Hill Giant','Forest','Lightning Bolt']))
    names += ['Say Its Name']*3
    s = table(cards, names, names, names)
    to_phase(s, 'main1', 1)
    act(s, 'p1', type='add_mana', player='p1', mana={c:30 for c in ['C','W','U','B','R','G']})
    return s

def answer(s, ids):
    d = s.state.rules.decision
    assert d
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)

def cast(s, name, **kwargs):
    source = put(s, name, 'hand')
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[], **kwargs)
    settle(s)
    return source

def top(s, names):
    cards = [put(s, name, 'hand') for name in names]
    for c in reversed(cards):
        act(s, 'p1', type='move', card_ids=[c.id], to={'player':'p1','zone':'library'}, position='top')
    return cards


def top_for(s,names,owner):
    cards=[put(s,name,'hand',owner) for name in names]
    for c in reversed(cards):
        act(s,owner,type='move',card_ids=[c.id],to={'player':owner,'zone':'library'},position='top')
    return cards



def test_whole_pair(cards):
    from app.rules.coverage import of_card_data
    for name in ['Flitting Guerrilla','Say Its Name']:
        result=of_card_data(cards.resolve(name))
        assert result.level=='FULL', (name,result.manual_parts)


def test_say_native_original_source_and_two_named_others_paid_as_one_group(cards):
    s=setup(cards)
    put(s,'Tormod, the Desecrator','battlefield')
    says=[c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Say Its Name']
    assert len(says)==4
    act(s,'p1',type='move',card_ids=[c.id for c in says[:3]],to={'player':'p1','zone':'graveyard'})
    source=says[0]
    target=put(s,'Altanak, the Thrice-Called','hand')
    library_before=list(s.state.zones['p1:library'])
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,cost_choices=[{'component':0,'cards':[c.id for c in says[1:3]]}],sources=[])
    assert all(c.zone=='p1:exile' for c in says[:3])
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume['step']=='search_zones'
    answer(s,['hand'])
    d=s.state.rules.decision
    assert d and d.resume['step']=='search'
    answer(s,[target.id])
    assert target.zone=='p1:battlefield' and not s.state.rules.decision
    assert s.state.zones['p1:library']==library_before
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Zombie'])==1


def test_flitting_native_each_player_mills_before_optional_original_exile(cards):
    s=setup(cards)
    source=cast(s,'Flitting Guerrilla')
    tops={pid:top_for(s,['Grizzly Bears','Forest'],pid) for pid in s.state.players}
    bolt=put(s,'Lightning Bolt','hand')
    act(s,'p1',type='cast_spell',card_id=bolt.id,sources=[],targets=[source.id])
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume['step']=='pay_or_sacrifice'
    assert source.zone=='p1:graveyard'
    assert all(s.state.cards[c.id].zone==pid+':graveyard' for pid,cards in tops.items() for c in cards)
    answer(s,['decline'])
    assert source.zone=='p1:graveyard' and not s.state.rules.decision
    roundtrip(s)


def test_say_actual_cast_mills_then_optional_current_graveyard_return(cards):
    s=setup(cards)
    old=put(s,'Hill Giant','graveyard')
    milled=top(s,['Forest','Grizzly Bears','Sol Ring'])
    source=cast(s,'Say Its Name')
    d=s.state.rules.decision
    assert d and d.resume['step']=='return_choice' and d.min_choices==0 and d.max_choices==1
    assert {o.id for o in d.options}=={old.id,milled[0].id,milled[1].id}
    answer(s,[milled[0].id])
    assert milled[0].zone=='p1:hand' and old.zone=='p1:graveyard' and source.zone=='p1:graveyard'
    roundtrip(s)


def test_flitting_native_reflexive_targets_announced_only_after_all_mill_and_exile(cards):
    s=setup(cards)
    source=cast(s,'Flitting Guerrilla')
    battle='Invasion of Zendikar // Awakened Skyclave'
    own=top(s,['Grizzly Bears',battle])
    foreign={pid:top_for(s,['Grizzly Bears','Forest'],pid) for pid in ['p2','p3']}
    bolt=put(s,'Lightning Bolt','hand')
    act(s,'p1',type='cast_spell',card_id=bolt.id,sources=[],targets=[source.id])
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume['step']=='pay_or_sacrifice' and not d.resume['ctx'].get('targets')
    assert all(c.zone=='p1:graveyard' for c in own)
    answer(s,['pay'])
    d=s.state.rules.decision
    assert d and d.resume['step'] in ('trigger_target','trigger_group')
    assert source.zone=='p1:exile'
    assert {o.id for o in d.options}=={c.id for c in own}
    answer(s,[own[1].id])
    assert own[1].zone=='p1:library' and s.state.zones['p1:library'][0]==own[1].id
    assert source.zone=='p1:exile'
    assert all(s.state.cards[c.id].zone==pid+':graveyard' for pid,cs in foreign.items() for c in cs)
    roundtrip(s)


def say_ready69(cards):
    s=setup(cards)
    says=[c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Say Its Name']
    act(s,'p1',type='move',card_ids=[c.id for c in says[:3]],to={'player':'p1','zone':'graveyard'})
    return s,says


@pytest.mark.parametrize('bad',['source_hand','one_other','source_selected','other_hand','wrong_name'])
def test_say_negative_payment_requires_source_and_exactly_two_named_original_own_gy_cards(cards,bad):
    from app.game.errors import ActionError
    s,says=say_ready69(cards)
    chosen=[says[1].id,says[2].id]
    if bad=='source_hand':
        act(s,'p1',type='move',card_ids=[says[0].id],to={'player':'p1','zone':'hand'})
    elif bad in ('one_other','other_hand'):
        act(s,'p1',type='move',card_ids=[says[2].id],to={'player':'p1','zone':'hand'})
        if bad=='one_other':
            chosen=[says[1].id]
    elif bad=='source_selected':
        chosen=[says[0].id,says[1].id]
    else:
        wrong=put(s,'Sol Ring','graveyard')
        chosen=[says[1].id,wrong.id]
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=says[0].id,ability=1,cost_choices=[{'component':0,'cards':chosen}],sources=[])
    assert s.state.model_dump_json()==before


@pytest.mark.parametrize('origin',['library','graveyard'])
def test_say_actual_search_origin_and_conditional_library_shuffle(cards,origin):
    s,says=say_ready69(cards)
    target=put(s,'Altanak, the Thrice-Called',origin)
    before=set(s.state.zones['p1:library'])
    act(s,'p1',type='activate_ability',card_id=says[0].id,ability=1,cost_choices=[{'component':0,'cards':[c.id for c in says[1:3]]}],sources=[])
    settle(s)
    assert s.state.rules.decision and s.state.rules.decision.resume['step']=='search_zones'
    answer(s,[origin])
    assert s.state.rules.decision and s.state.rules.decision.resume['step']=='search'
    answer(s,[target.id])
    assert target.zone=='p1:battlefield' and all(c.zone=='p1:exile' for c in says[:3])
    if origin=='library':
        assert not (before & set(s.state.zones['p1:library']))
    else:
        assert before==set(s.state.zones['p1:library'])
    roundtrip(s)


def test_flitting_sacrifice_true_cost_keeps_initial_target_before_reflexive_target_choice(cards):
    s=setup(cards)
    altar=cast(s,'Altar of Dementia')
    source=cast(s,'Flitting Guerrilla')
    own=top(s,['Grizzly Bears','Forest'])
    enemy=top_for(s,['Grizzly Bears','Forest','Hill Giant','Sol Ring'],'p2')
    third=top_for(s,['Grizzly Bears','Forest'],'p3')
    act(s,'p1',type='activate_ability',card_id=altar.id,ability=0,targets=['p2'],cost_choices=[{'component':0,'cards':[source.id]}],sources=[])
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume['step']=='pay_or_sacrifice' and source.zone=='p1:graveyard'
    assert all(c.zone=='p1:graveyard' for c in own)
    assert all(c.zone=='p2:graveyard' for c in enemy[:2]) and enemy[2].zone=='p2:library'
    answer(s,['pay'])
    d=s.state.rules.decision
    assert d and d.resume['step'] in ('trigger_target','trigger_group') and source.zone=='p1:exile'
    answer(s,[own[0].id])
    assert own[0].zone=='p1:library' and s.state.zones['p1:library'][0]==own[0].id
    assert all(c.zone=='p2:graveyard' for c in enemy)
    assert all(c.zone=='p3:graveyard' for c in third)
    roundtrip(s)


@pytest.mark.parametrize('mode',['pay','cancel','missing_originals','missing_packet','stale_source','stale_other','wrong_source'])
def test_true_cold_say_original_cost_packet(cards,tmp_path,mode):
    import os
    import subprocess
    import sys

    import app
    s,says=say_ready69(cards)
    act(s,'p1',type='move',card_ids=[says[3].id],to={'player':'p1','zone':'graveyard'})
    put(s,'Tormod, the Desecrator','battlefield')
    target=put(s,'Altanak, the Thrice-Called','hand')
    act(s,'p1',type='activate_ability',card_id=says[0].id,ability=1,sources=[])
    d=s.state.rules.decision
    assert d and d.resume['step']=='ability_cost'
    assert {o.id for o in d.options}=={c.id for c in says[1:]}
    assert all(c.zone=='p1:graveyard' for c in says)
    saved=tmp_path/'source69.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import json,sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from app.game.errors import ActionError
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_library_placements import settle
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
mode=sys.argv[3];ids=json.loads(sys.argv[4]);target=sys.argv[5]
d=s.state.rules.decision;assert d and d.resume['step']=='ability_cost'
if mode=='missing_originals':
    del d.resume['source_packet69']['originals']
elif mode=='missing_packet':
    del d.resume['source_packet69'];del d.resume['source_packet_required69']
elif mode=='wrong_source':
    d.resume['source_packet69']['source']=ids[3]
elif mode.startswith('stale_'):
    cid=ids[0] if mode=='stale_source' else ids[1]
    old=s.state.rules.object_id(cid)
    plan=Plan(s.state,'p1',repo,None)
    plan.do({'type':'move','card_ids':[cid],'to':{'player':'p1','zone':'hand'}})
    plan.do({'type':'move','card_ids':[cid],'to':{'player':'p1','zone':'graveyard'}})
    assert plan.oid(cid)!=old
    s=GameSession(plan.state,cards=repo);d=s.state.rules.decision
before=s.state.model_dump_json()
if mode in ('pay','cancel'):
    act(s,d.player,type='choose',decision_id=d.id,option_ids=ids[1:3] if mode=='pay' else []);settle(s)
    if mode=='pay':
        assert all(s.state.cards[cid].zone=='p1:exile' for cid in ids[:3])
        assert s.state.cards[ids[3]].zone=='p1:graveyard'
        d=s.state.rules.decision;assert d and d.resume['step']=='search_zones'
        act(s,d.player,type='choose',decision_id=d.id,option_ids=['hand']);settle(s)
        d=s.state.rules.decision;assert d and d.resume['step']=='search'
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[target]);settle(s)
        assert s.state.cards[target].zone=='p1:battlefield'
    else:
        assert all(s.state.cards[cid].zone=='p1:graveyard' for cid in ids)
    assert not s.state.rules.decision
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Zombie'])==(1 if mode=='pay' else 0)
else:
    try: act(s,d.player,type='choose',decision_id=d.id,option_ids=ids[1:3])
    except ActionError: pass
    else: raise AssertionError('Stale or missing original packet was accepted')
    assert s.state.model_dump_json()==before
    assert all(s.state.cards[cid].zone=='p1:graveyard' for cid in ids)
'''
    backend=Path(app.__file__).resolve().parents[1]
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),mode,json.dumps([c.id for c in says]),target.id],cwd=backend,env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert run.returncode==0,run.stdout+run.stderr


@pytest.mark.parametrize('checkpoint',['optional','reflexive','decline'])
def test_true_cold_flitting_native_optional_and_reflexive_stages(cards,tmp_path,checkpoint):
    import os
    import subprocess
    import sys

    import app
    s=setup(cards)
    source=cast(s,'Flitting Guerrilla')
    own=top(s,['Grizzly Bears','Invasion of Zendikar // Awakened Skyclave'])
    for pid in ['p2','p3']:
        top_for(s,['Grizzly Bears','Forest'],pid)
    bolt=put(s,'Lightning Bolt','hand')
    act(s,'p1',type='cast_spell',card_id=bolt.id,sources=[],targets=[source.id])
    settle(s)
    assert s.state.rules.decision and s.state.rules.decision.resume['step']=='pay_or_sacrifice'
    if checkpoint=='reflexive':
        answer(s,['pay'])
        assert s.state.rules.decision and s.state.rules.decision.resume['step'] in ('trigger_target','trigger_group')
    saved=tmp_path/'flitting69.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from tests.game_helpers import act
from tests.test_rules_library_placements import settle
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
source,target,checkpoint=sys.argv[3:]
d=s.state.rules.decision
if checkpoint!='reflexive':
    assert d and d.resume['step']=='pay_or_sacrifice'
    assert s.state.cards[source].zone=='p1:graveyard'
    assert len(s.state.zones.get('p2:graveyard',[]))==len(s.state.zones.get('p3:graveyard',[]))==2
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['decline' if checkpoint=='decline' else 'pay']);settle(s)
if checkpoint=='decline':
    assert s.state.cards[source].zone==s.state.cards[target].zone=='p1:graveyard'
else:
    d=s.state.rules.decision;assert d and d.resume['step'] in ('trigger_target','trigger_group')
    assert s.state.cards[source].zone=='p1:exile' and source not in {o.id for o in d.options}
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[target]);settle(s)
    assert s.state.zones['p1:library'][0]==target and s.state.cards[source].zone=='p1:exile'
assert len(s.state.zones.get('p2:graveyard',[]))==len(s.state.zones.get('p3:graveyard',[]))==2
assert s.state.rules.decision is None
'''
    backend=Path(app.__file__).resolve().parents[1]
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),source.id,own[1].id,checkpoint],cwd=backend,env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert run.returncode==0,run.stdout+run.stderr


def test_flitting_may_exile_before_reflexive_has_no_legal_target(cards):
    s=setup(cards)
    source=cast(s,'Flitting Guerrilla')
    own=top(s,['Sol Ring','Forest'])
    for pid in ['p2','p3']:
        top_for(s,['Grizzly Bears','Forest'],pid)
    bolt=put(s,'Lightning Bolt','hand')
    act(s,'p1',type='cast_spell',card_id=bolt.id,sources=[],targets=[source.id])
    settle(s)
    assert s.state.rules.decision and s.state.rules.decision.resume['step']=='pay_or_sacrifice'
    answer(s,['pay'])
    assert source.zone=='p1:exile' and not s.state.rules.decision
    assert all(c.zone=='p1:graveyard' for c in own)
    roundtrip(s)


@pytest.mark.parametrize('return_original',[False,True])
def test_flitting_original_death_card_removed_in_response_is_not_exiled_again(cards,return_original):
    s=setup(cards)
    crypt=put(s,"Tormod's Crypt",'battlefield','p2')
    source=cast(s,'Flitting Guerrilla')
    tops={pid:top_for(s,['Grizzly Bears','Forest'],pid) for pid in s.state.players}
    bolt=put(s,'Lightning Bolt','hand')
    act(s,'p1',type='cast_spell',card_id=bolt.id,sources=[],targets=[source.id])
    for _ in range(30):
        if bolt.zone!='stack':
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert source.zone=='p1:graveyard' and s.state.zones.get('stack')
    while s.state.rules.priority!='p2':
        act(s,s.state.rules.priority,type='pass_priority')
    act(s,'p2',type='activate_ability',card_id=crypt.id,ability=0,targets=['p1'],sources=[])
    crypt_ability=next(cid for cid,e in s.state.rules.stack.items() if e.kind=='activated' and e.source_card==crypt.id)
    for _ in range(30):
        if crypt_ability not in s.state.zones.get('stack',[]):
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert source.zone=='p1:exile'
    if return_original:
        pull=put(s,'Pull from Eternity','hand')
        act(s,'p1',type='cast_spell',card_id=pull.id,sources=[],targets=[source.id])
    settle(s)
    assert source.zone==('p1:graveyard' if return_original else 'p1:exile')
    assert not s.state.rules.decision
    assert all(s.state.cards[c.id].zone==pid+':graveyard' for pid,cs in tops.items() for c in cs)
    roundtrip(s)
