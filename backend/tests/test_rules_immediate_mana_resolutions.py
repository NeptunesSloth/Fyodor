"""Canonical actual mana abilities resolve native instructions without using the stack."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_discard_outcomes import cold_run
from tests.test_rules_hidden_card_facts import choose
from tests.test_rules_mana_delayed_effects import answer, cast
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA=Path(__file__).parent/'fixtures/immediate_mana_resolutions_cards.json'
NAMES=[c['name'] for c in json.loads(DATA.read_text())][:16]

@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads(DATA.read_text())):
        base[c['name']]=card(c['name'],set_code='imr37',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    r=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield r
    r.close()

def game(cards):
    names=[c['name'] for c in json.loads(DATA.read_text())]
    s=table(cards,names,names,names)
    for p in ['p1','p2','p3']:
        act(s,p,type='set_prefs',hold_priority=True)
    to_phase(s,'main1',4)
    return s

def pool(s,color,pid='p1'):
    p=s.state.players[pid]
    return p.mana.get(color,0)+sum(u.sym==color for u in p.mana_units)

def activate(s,c,index=0,**kw):
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=c.id,ability=index,**kw)

@pytest.mark.parametrize('name',NAMES[:11])
def test_stage_one_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def test_cryptolith_adds_mana_and_loses_life_no_stack(cards):
    s=game(cards)
    c=put(s,NAMES[0],'battlefield')
    before={p:s.state.players[p].life for p in ['p1','p2','p3']}
    activate(s,c,index=1,mana_choice='G')
    assert not s.state.zones.get('stack') and pool(s,'G')==1
    assert all(s.state.players[p].life==before[p]-1 for p in before)
    roundtrip(s)


def test_cryptolith_transform_all_players_life_gate(cards):
    s=game(cards)
    c=put(s,NAMES[0],'battlefield')
    for p in ['p1','p2','p3']:
        act(s,p,type='set_life',player=p,value=10)
    to_phase(s,'upkeep',7)
    answer(s)
    roundtrip(s)
    assert s.state.cards[c.id].face==1

@pytest.mark.parametrize('ogre',[False,True])
def test_tomb_conditional_damage(cards,ogre):
    s=game(cards)
    c=put(s,'Tomb of Urami','battlefield')
    if ogre:
        put(s,'Ogre Resister','battlefield')
    before=s.state.players['p1'].life
    activate(s,c)
    assert pool(s,'B')==1 and s.state.players['p1'].life==before-(0 if ogre else 1)
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_foraging_actual_chosen_color_and_once_limit(cards):
    s=game(cards)
    c=put(s,'Foraging Wickermaw','battlefield')
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    activate(s,c,index=1,mana_choice='R')
    assert pool(s,'R')==1
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[c.id]).colors==frozenset({'R'})
    with pytest.raises(ActionError):
        activate(s,c,index=1,mana_choice='U')
    roundtrip(s)


def test_cryptex_collect_evidence_then_unlock(cards):
    s=game(cards)
    c=put(s,'Cryptex','battlefield')
    a=put(s,'Sol Ring','graveyard')
    b=put(s,'Counterspell','graveyard')
    activate(s,c,mana_choice='U')
    settle(s)
    choose(s,[a.id,b.id])
    answer(s)
    roundtrip(s)
    assert pool(s,'U')==1 and s.state.cards[c.id].counters.get('unlock')==1
    assert all(s.state.cards[x].zone=='p1:exile' for x in [a.id,b.id])
    assert not s.state.zones.get('stack')

@pytest.mark.parametrize('name,color',[('Initiates of the Ebon Hand','B'),('Farrelite Priest','W')])
def test_fourth_actual_mana_activation_creates_delayed_sacrifice(cards,name,color):
    s=game(cards)
    c=put(s,name,'battlefield')
    act(s,'p1',type='add_mana',player='p1',mana={'C':4})
    for _ in range(3):
        activate(s,c)
    assert not s.state.rules.delayed
    activate(s,c)
    assert pool(s,color)==4 and s.state.rules.delayed
    to_phase(s,'end',4)
    answer(s)
    roundtrip(s)
    assert s.state.cards[c.id].zone=='p1:graveyard'


def test_manaforge_three_actual_activations_then_atomic_reject(cards):
    s=game(cards)
    c=put(s,'Manaforge Cinder','battlefield')
    act(s,'p1',type='add_mana',player='p1',mana={'C':4})
    for _ in range(3):
        activate(s,c,mana_choice='R')
    assert pool(s,'R')==3
    with pytest.raises(ActionError):
        activate(s,c,mana_choice='B')
    assert pool(s,'R')==3 and pool(s,'C')==1
    roundtrip(s)


def test_ignus_native_return_self_cost_and_source_oid(cards):
    s=game(cards)
    c=put(s,'Grinning Ignus','battlefield')
    old=Plan(s.state,'p1',s.cards,None).oid(c)
    act(s,'p1',type='add_mana',player='p1',mana={'R':1})
    activate(s,c)
    answer(s)
    roundtrip(s)
    assert s.state.cards[c.id].zone=='p1:hand' and pool(s,'R')==1 and pool(s,'C')==2
    assert {u.src for u in s.state.players['p1'].mana_units}=={old}
    assert not s.state.zones.get('stack')


def test_bloom_exile_private_hand_cost_for_two_mana(cards):
    s=game(cards)
    c=put(s,'Cadaverous Bloom','battlefield')
    a=put(s,'Forest','hand')
    activate(s,c,mana_choice='G')
    choose(s,[a.id])
    answer(s)
    roundtrip(s)
    assert s.state.cards[a.id].zone=='p1:exile' and pool(s,'G')==2
    assert not s.state.zones.get('stack')


def test_jack_graveyard_self_exile_mana_no_stack(cards):
    s=game(cards)
    c=put(s,"Jack-o'-Lantern",'graveyard')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1})
    activate(s,c,index=1,mana_choice='B')
    answer(s)
    roundtrip(s)
    assert s.state.cards[c.id].zone=='p1:exile' and pool(s,'B')==1
    assert not s.state.zones.get('stack')

@pytest.mark.parametrize('x',[0,1])
def test_springjack_x_goats_mana_and_life_including_zero(cards,x):
    s=game(cards)
    c=put(s,'Springjack Pasture','battlefield')
    goat=put(s,'Mountain Goat','battlefield')
    before=s.state.players['p1'].life
    activate(s,c,index=2,x_value=x,mana_choice='G')
    if x and s.state.rules.decision is not None:
        choose(s,[goat.id])
    answer(s)
    roundtrip(s)
    assert pool(s,'G')==x and s.state.players['p1'].life==before+x
    assert s.state.cards[c.id].tapped
    assert s.state.cards[goat.id].zone==('p1:graveyard' if x else 'p1:battlefield')

@pytest.mark.parametrize('name',NAMES[11:])
def test_stage_two_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def test_victory_true_mana_beneficiary_and_other_untap(cards):
    s=game(cards)
    c=put(s,'Victory Chimes','battlefield')
    activate(s,c,index=1)
    assert not s.state.zones.get('stack')
    choose(s,['p2'])
    answer(s)
    assert pool(s,'C','p2')==1 and pool(s,'C')==0 and s.state.cards[c.id].tapped
    to_phase(s,'upkeep',5)
    assert not s.state.cards[c.id].tapped
    roundtrip(s)


def test_searchlight_beneficiary_chooses_color_cold(cards,tmp_path):
    s=game(cards)
    c=put(s,'Spectral Searchlight','battlefield')
    activate(s,c)
    choose(s,['p2'])
    d=s.state.rules.decision
    assert d.player=='p2' and {'W','U','B','R','G'}=={o.id for o in d.options}
    assert not s.state.zones.get('stack')
    cold_run(s,cards,tmp_path,"""
from tests.test_rules_hidden_card_facts import choose
from tests.test_rules_immediate_mana_resolutions import pool
choose(s,['G'])
assert pool(s,'G','p2')==1 and pool(s,'G')==0
assert s.state.cards[args[0]].tapped
assert s.state.rules.priority=='p1'
""",c.id)


def test_stadium_ordinary_etb_beneficiary_color(cards):
    s=game(cards)
    c=cast(s,'Stadium Vendors',{'R':1,'C':3})
    settle(s)
    choose(s,['p2'])
    assert s.state.rules.decision.player=='p2'
    choose(s,['U'])
    answer(s)
    roundtrip(s)
    assert s.state.cards[c.id].zone=='p1:battlefield' and pool(s,'U','p2')==2


def test_valleymaker_sacrifice_forest_true_mana_body(cards):
    s=game(cards)
    c=put(s,'Valleymaker','battlefield')
    land=put(s,'Forest','battlefield')
    to_phase(s,'main1',7)
    activate(s,c,index=1)
    if s.state.rules.decision and land.id in {o.id for o in s.state.rules.decision.options}:
        choose(s,[land.id])
    assert s.state.cards[land.id].zone=='p1:graveyard'
    assert not s.state.zones.get('stack')
    choose(s,['p2'])
    answer(s)
    roundtrip(s)
    assert pool(s,'G','p2')==3


def test_valleymaker_targeted_mountain_ability_uses_stack(cards):
    s=game(cards)
    c=put(s,'Valleymaker','battlefield')
    land=put(s,'Mountain','battlefield')
    bear=put(s,'Trained Armodon','battlefield','p2')
    to_phase(s,'main1',7)
    activate(s,c,index=0,targets=[bear.id])
    if s.state.rules.decision and land.id in {o.id for o in s.state.rules.decision.options}:
        choose(s,[land.id])
    assert s.state.zones.get('stack')
    answer(s)
    roundtrip(s)
    assert s.state.cards[land.id].zone=='p1:graveyard' and s.state.cards[bear.id].zone=='p2:graveyard'


def test_radiant_lotus_targeted_direct_sacrifice_receipt(cards):
    s=game(cards)
    c=put(s,'Radiant Lotus','battlefield')
    ring=put(s,'Sol Ring','battlefield')
    activate(s,c,targets=['p2'])
    choose(s,[c.id,ring.id])
    assert s.state.zones.get('stack')
    settle(s)
    choose(s,['Green'])
    answer(s)
    roundtrip(s)
    assert pool(s,'G','p2')==6 and pool(s,'G')==0
    assert all(s.state.cards[x].zone=='p1:graveyard' for x in [c.id,ring.id])


def test_searchlight_reflection_doubles_recipient_not_activator(cards):
    s=game(cards)
    c=put(s,'Spectral Searchlight','battlefield')
    put(s,'Mana Reflection','battlefield')
    activate(s,c)
    choose(s,['p2'])
    choose(s,['R'])
    answer(s)
    assert pool(s,'R','p2')==2 and pool(s,'R')==0
    roundtrip(s)


def test_cryptex_counter_replacement_cold_without_repaying(cards,tmp_path):
    s=game(cards)
    c=put(s,'Cryptex','battlefield')
    put(s,'Doubling Season','battlefield')
    put(s,'Winding Constrictor','battlefield')
    a=put(s,'Sol Ring','graveyard')
    b=put(s,'Counterspell','graveyard')
    activate(s,c,mana_choice='U')
    settle(s)
    choose(s,[a.id,b.id])
    assert s.state.rules.decision is not None
    assert pool(s,'U')==1
    cold_run(s,cards,tmp_path,"""
from tests.test_rules_immediate_mana_resolutions import pool
from tests.test_rules_mana_delayed_effects import answer
answer(s)
assert s.state.cards[args[0]].counters.get('unlock') in (3,4)
assert pool(s,'U')==1
assert all(s.state.cards[x].zone=='p1:exile' for x in args[1:])
assert not s.state.zones.get('stack')
""",c.id,a.id,b.id)


def test_jack_cannot_activate_from_battlefield(cards):
    s=game(cards)
    c=put(s,"Jack-o'-Lantern",'battlefield')
    act(s,'p1',type='add_mana',player='p1',mana={'C':1})
    with pytest.raises(ActionError):
        activate(s,c,index=1,mana_choice='U')
    assert pool(s,'C')==1 and s.state.cards[c.id].zone=='p1:battlefield'
    roundtrip(s)


def test_tomb_damage_replacement_pauses_original_cast_cold(cards,tmp_path):
    s=game(cards)
    c=put(s,'Tomb of Urami','battlefield')
    put(s,'Furnace of Rath','battlefield')
    put(s,"Urza's Armor",'battlefield')
    spell=put(s,'Dark Ritual','hand')
    wait_priority(s,'p1')
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[c.id])
    assert s.state.rules.decision is not None
    assert s.state.cards[c.id].tapped
    cold_run(s,cards,tmp_path,"""
from tests.test_rules_immediate_mana_resolutions import pool
from tests.test_rules_mana_delayed_effects import answer
answer(s)
assert s.state.cards[args[0]].zone=='p1:graveyard'
assert pool(s,'B')==3
assert s.state.players['p1'].life in (39,40)
assert s.state.cards[args[1]].tapped
""",spell.id,c.id)


def test_jack_own_graveyard_activates_during_payment_cold(cards,tmp_path):
    s=game(cards)
    c=put(s,"Jack-o'-Lantern",'graveyard')
    spell=put(s,'Counterspell','hand')
    target=put(s,'Dark Ritual','hand','p2')
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'B':1})
    act(s,'p2',type='cast_spell',card_id=target.id,sources=[])
    wait_priority(s,'p1')
    s.state.rules.prefs['p1'].payment='self'
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'U':1})
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[target.id])
    assert s.state.rules.decision.resume['step']=='pay_mana'
    act(s,'p1',type='activate_ability',card_id=c.id,ability=1)
    assert s.state.cards[c.id].zone=='p1:exile'
    cold_run(s,cards,tmp_path,"""
from tests.test_rules_hidden_card_facts import choose
from tests.test_rules_mana_delayed_effects import answer
choose(s,[next(o.id for o in s.state.rules.decision.options if o.label=='{U}')])
answer(s)
assert s.state.cards[args[0]].zone=='p1:exile'
assert s.state.cards[args[1]].zone=='p1:graveyard'
assert s.state.cards[args[2]].zone=='p2:graveyard'
""",c.id,spell.id,target.id)


def test_fourth_activation_delayed_sacrifice_cold(cards,tmp_path):
    s=game(cards)
    c=put(s,'Initiates of the Ebon Hand','battlefield')
    act(s,'p1',type='add_mana',player='p1',mana={'C':4})
    for _ in range(4):
        activate(s,c)
    assert pool(s,'B')==4 and s.state.rules.delayed
    cold_run(s,cards,tmp_path,"""
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_mana_delayed_effects import answer
to_phase(s,'end',4)
answer(s)
assert s.state.cards[args[0]].zone=='p1:graveyard'
""",c.id)


def test_ignus_rejects_activation_inside_spell_payment(cards):
    s=game(cards)
    c=put(s,'Grinning Ignus','battlefield')
    spell=put(s,'Stadium Vendors','hand')
    wait_priority(s,'p1')
    s.state.rules.prefs['p1'].payment='self'
    act(s,'p1',type='add_mana',player='p1',mana={'R':1})
    act(s,'p1',type='cast_spell',card_id=spell.id)
    assert s.state.rules.decision.resume['step']=='pay_mana'
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=c.id,ability=0)
    assert pool(s,'R')==1 and s.state.cards[c.id].zone=='p1:battlefield'
    roundtrip(s)


def test_cryptolith_false_intervening_condition_does_not_transform(cards):
    s=game(cards)
    c=put(s,NAMES[0],'battlefield')
    for p in ['p1','p2','p3']:
        act(s,p,type='set_life',player=p,value=10)
    to_phase(s,'upkeep',7)
    assert s.state.zones.get('stack')
    act(s,'p1',type='set_life',player='p3',value=11)
    answer(s)
    assert s.state.cards[c.id].face==0
    roundtrip(s)


def test_aurora_transformed_face_attacks_each_opponent(cards):
    s=game(cards)
    c=put(s,NAMES[0],'battlefield')
    for p in ['p1','p2','p3']:
        act(s,p,type='set_life',player=p,value=10)
    to_phase(s,'upkeep',7)
    answer(s)
    assert s.state.cards[c.id].face==1
    to_phase(s,'declare_attackers',7)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':c.id,'target':'p2'}])
    answer(s)
    assert s.state.players['p2'].life<=7 and s.state.players['p3'].life==7
    assert s.state.players['p1'].life==10
    roundtrip(s)
