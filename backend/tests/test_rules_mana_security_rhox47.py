from pathlib import Path
import pytest
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import alt_costs, casting, mana as M
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_activated_copy_family import answer

@pytest.fixture
def cards():
    repo=CardRepository(Path(__file__).resolve().parents[2] / 'data/cards.sqlite',ImageStore(Path(__file__).resolve().parents[2] / 'data/images'))
    yield repo
    repo.close()

def setup(cards,names=()):
    s=table(cards,['Security Rhox',*names],[],[])
    rhox=put(s,'Security Rhox','hand')
    for name in names:put(s,name,'battlefield')
    to_phase(s,'main1',4);wait_priority(s,'p1')
    return s,rhox

def token(s,kind='Treasure',creature=False):
    before=set(s.state.cards)
    spec={'name':kind,'type_line':f'Token Artifact {"Creature " if creature else ""}— {kind}', 'text':'{T}, Sacrifice this token: Add one mana of any color.'}
    if creature:spec.update(power='1',toughness='1')
    act(s,'p1',type='create_token',player='p1',token=spec)
    return next(c for k,c in s.state.cards.items() if k not in before)

def produce(s,card,color):
    act(s,'p1',type='activate_ability',card_id=card.id,ability=0,mana_choice=color)
    d=s.state.rules.decision
    if d is not None and [color] in (d.resume or {}).get('options', []):
        selected=d.resume['options'].index([color])
        act(s,'p1',type='choose',decision_id=d.id,option_ids=[d.options[selected].id])
    answer(s)
    wait_priority(s,'p1')

def offer(s,rhox):
    p=Plan(s.state,'p1',s.cards,None)
    return next(o for o in alt_costs.offers(s.state,'p1',rhox,p.ch(rhox),s.cards) if o.producer_requirement is not None)

def refuse(s,**action):
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):act(s,'p1',**action)
    assert s.state.model_dump_json()==before

@pytest.mark.parametrize('kind',['Treasure','Gold'])
def test_actual_selected_alt_requires_treasure_not_other_artifact(cards,kind):
    s,r=setup(cards);a=token(s,kind);b=token(s,kind)
    # Token text is the mana source, not the name of the resulting mana.
    for card,color in [(a,'R'),(b,'G')]:act(s,'p1',type='activate_ability',card_id=card.id,ability=0,mana_choice=color)
    key=offer(s,r).key
    if kind!='Treasure':
        refuse(s,type='cast_spell',card_id=r.id,alt_cost=key);return
    act(s,'p1',type='cast_spell',card_id=r.id,alt_cost=key);answer(s)
    assert s.state.cards[r.id].zone=='p1:battlefield';roundtrip(s)

def test_equal_nominal_normal_rg_is_unrestricted_selected_alt_is_restricted(cards):
    s,r=setup(cards,["Heartless Summoning"])
    act(s,'p1',type='add_mana',player='p1',mana={'R':1,'G':1})
    assert casting.castable(s.state,'p1',r,cards)
    assert casting.alt_castable(s.state,'p1',r,cards)==[]
    refuse(s,type='cast_spell',card_id=r.id,alt_cost=offer(s,r).key)
    act(s,'p1',type='cast_spell',card_id=r.id);answer(s)
    assert s.state.cards[r.id].zone=='p1:battlefield'

@pytest.mark.parametrize('reduced',[False,True])
def test_actual_tax_and_reduction_apply_to_selected_alternative(cards,reduced):
    names=['Sphere of Resistance']+(["Rhonas's Monument"] if reduced else [])
    s,r=setup(cards,names)
    for color in ['R','G']:
        t=token(s);act(s,'p1',type='activate_ability',card_id=t.id,ability=0,mana_choice=color)
    act(s,'p1',type='add_mana',player='p1',mana={'C':1})
    if not reduced:
        refuse(s,type='cast_spell',card_id=r.id,alt_cost=offer(s,r).key)
        t=token(s);act(s,'p1',type='activate_ability',card_id=t.id,ability=0,mana_choice='W')
    act(s,'p1',type='cast_spell',card_id=r.id,alt_cost=offer(s,r).key);answer(s)
    assert s.state.cards[r.id].zone=='p1:battlefield'
    assert s.state.players['p1'].mana.get('C')==1

def test_unrelated_foreign_alternative_is_not_rhox_alternative(cards):
    s,r=setup(cards,['Fist of Suns'])
    act(s,'p1',type='add_mana',player='p1',mana={c:1 for c in 'WUBRG'})
    p=Plan(s.state,'p1',cards,None)
    other=next(o for o in alt_costs.offers(s.state,'p1',r,p.ch(r),cards) if o.producer_requirement is None)
    act(s,'p1',type='cast_spell',card_id=r.id,alt_cost=other.key);answer(s)
    assert s.state.cards[r.id].zone=='p1:battlefield'

def test_creature_treasure_sacrifice_and_independent_bonus_do_not_share_producer(cards):
    s,r=setup(cards,['Kinnan, Bonder Prodigy','Sphere of Resistance'])
    a=token(s,creature=True);b=token(s,creature=True)
    to_phase(s,'main1',7);wait_priority(s,'p1')
    for card,color in [(a,'R'),(b,'G')]:
        produce(s,card,color)
    units=s.state.players['p1'].mana_units
    assert len(units)==4
    assert sum('Treasure' in u.tags and 'Creature' in u.tags for u in units)==2
    assert sum('Treasure' not in u.tags for u in units)==2
    refuse(s,type='cast_spell',card_id=r.id,alt_cost=offer(s,r).key)
    t=token(s);produce(s,t,'U')
    assert {u.sym for u in s.state.players['p1'].mana_units if 'Treasure' in u.tags} >= {'R','G'}, [(u.sym,u.tags) for u in s.state.players['p1'].mana_units]
    act(s,'p1',type='cast_spell',card_id=r.id,alt_cost=offer(s,r).key);answer(s)
    assert s.state.cards[r.id].zone=='p1:battlefield'
    assert all('Treasure' not in u.tags for u in s.state.players['p1'].mana_units)

@pytest.mark.parametrize('legacy',[False,True])
def test_true_cold_selected_alternative_freezes_producer_rule_and_actual_old_units(cards,tmp_path,legacy):
    import subprocess,sys,json
    s,r=setup(cards)
    t=token(s)
    act(s,'p1',type='set_prefs',payment='self')
    act(s,'p1',type='cast_spell',card_id=r.id,alt_cost=offer(s,r).key)
    d=s.state.rules.decision
    assert d.resume['step']=='pay_mana'
    assert d.resume['payment_context']['producer_requirement']=='treasure_permanent'
    act(s,'p1',type='activate_ability',card_id=t.id,ability=0,mana_choice='R')
    assert t.id not in s.state.cards
    data=s.state.model_dump(mode='json')
    if legacy:
        for unit in data['players']['p1']['mana_units']:unit.pop('production_zone',None)
    path=tmp_path/'rhox-payment.json';path.write_text(json.dumps(data))
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.state import GameState
from app.game.session import GameSession
from app.game.errors import ActionError
from tests.test_rules_activated_copy_family import answer
repo=CardRepository(Path.cwd().parent / 'data/cards.sqlite',ImageStore(Path.cwd().parent / 'data/images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
r=sys.argv[2];legacy=sys.argv[3]=='True'
assert s.state.rules.decision.resume['payment_context']['producer_requirement']=='treasure_permanent'
before=set(s.state.cards)
s.perform('p1',{'type':'create_token','player':'p1','token':{'name':'Treasure','type_line':'Token Artifact — Treasure','text':'{T}, Sacrifice this token: Add one mana of any color.'}})
t=next(c for k,c in s.state.cards.items() if k not in before)
s.perform('p1',{'type':'activate_ability','card_id':t.id,'ability':0,'mana_choice':'G'})
d=s.state.rules.decision
if legacy:
 assert d.resume['step']=='pay_mana'
 before=s.state.model_dump_json()
 try:s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':['pay']})
 except ActionError:pass
 else:raise AssertionError('unknown old producer paid')
 assert s.state.model_dump_json()==before
else:
 if s.state.cards[r].zone!='stack':
  assert d.resume['step']=='pay_mana'
  s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':['pay']})
 assert s.state.cards[r].zone=='stack'
 assert not s.state.players['p1'].mana_units
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result=subprocess.run([sys.executable,'-c',code,str(path),r.id,str(legacy)],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stderr

def test_actual_auto_treasure_sources_fund_selected_alternative(cards):
    s,r=setup(cards);a=token(s);b=token(s)
    assert casting.alt_castable(s.state,'p1',r,cards)==[{'id':offer(s,r).key,'label':offer(s,r).label}]
    act(s,'p1',type='cast_spell',card_id=r.id,alt_cost=offer(s,r).key);answer(s)
    assert s.state.cards[r.id].zone=='p1:battlefield'
    assert a.id not in s.state.cards and b.id not in s.state.cards
    roundtrip(s)

def test_actual_free_cast_is_not_selected_rhox_alternative(cards):
    s,r=setup(cards,['Omniscience'])
    act(s,'p1',type='add_mana',player='p1',mana={'R':1,'G':1})
    act(s,'p1',type='cast_spell',card_id=r.id,free=True,sources=[]);answer(s)
    assert s.state.cards[r.id].zone=='p1:battlefield'
    assert s.state.players['p1'].mana=={'R':1,'G':1}


def test_native_additional_kicker_cost_is_also_treasure_restricted(cards,tmp_path):
    """Synthetic additional-cost boundary preserves the exact printed Rhox line."""
    from app.cards.importer import build_database
    from tests.fixtures.cards import card,fixture_cards
    rows={c['name']:c for c in fixture_cards()}
    raw=cards.resolve('Security Rhox');name='Rhox Additional Cost Boundary'
    values={k:raw[k] for k in ('mana_cost','cmc','type_line','oracle_text','colors','color_identity','power','toughness')}
    values['oracle_text']+='\nKicker {1}'
    rows[name]=card(name,set_code='rhox47',number='1',**values)
    database=tmp_path/'kicker.sqlite';build_database(rows.values(),database)
    repo=CardRepository(database,ImageStore(tmp_path/'images'))
    try:
        s=table(repo,[name],[],[]);r=put(s,name,'hand');to_phase(s,'main1',4);wait_priority(s,'p1')
        for color in ['R','G']:
            t=token(s);produce(s,t,color)
        act(s,'p1',type='add_mana',player='p1',mana={'C':1})
        refuse(s,type='cast_spell',card_id=r.id,alt_cost=offer(s,r).key,kicker=1)
        t=token(s);produce(s,t,'W')
        act(s,'p1',type='cast_spell',card_id=r.id,alt_cost=offer(s,r).key,kicker=1);answer(s)
        assert s.state.cards[r.id].zone=='p1:battlefield'
        assert s.state.players['p1'].mana.get('C')==1
        roundtrip(s)
    finally:repo.close()


def test_canonical_whole_card_coverage(cards):
    from app.rules import coverage
    assert coverage.of_card_data(cards.resolve('Security Rhox')).level=='FULL'
