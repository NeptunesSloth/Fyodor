"""Canonical printed-way, announced bargain, and additive own reductions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import casting, coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars

NAMES=['Visions of Glory','Visions of Dominance','Visions of Ruin','Visions of Duplicity','Visions of Dread','Ice Out',"Johann's Stopgap",'Hamlet Glutton',"Assassin's Ink",'Geistlight Snare']
EXTRA=['Sol Ring','Grizzly Bears','Forest','Island','Opt','Llanowar Elves','Solemnity','Kami of Ancient Law','Snapcaster Mage','Sphere of Resistance','Trinisphere','Shivan Dragon','Shock','Lotus Petal']

@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/conditional_own_discounts_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='cod',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    ns=[*NAMES,*EXTRA]
    return table(cards,ns,ns,ns)

@pytest.mark.parametrize('name',NAMES)
def test_canonical_cards_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'

@pytest.mark.parametrize('name,color',[('Visions of Glory','W'),('Visions of Dominance','G'),('Visions of Ruin','R'),('Visions of Duplicity','U'),('Visions of Dread','B')])
def test_printed_flashback_discount_keeps_colored_cost(cards,name,color):
    s=game(cards)
    source=put(s,name,'graveyard')
    cost=casting.spell_cost(s.state,source,chars(s,source),info=s.cards,player='p1')
    assert cost.generic==4
    assert cost.colored==(color,color)
    # An explicit alternative/free casting is a different way of casting.
    assert casting.spell_cost(s.state,source,chars(s,source),info=s.cards,player='p1',free=True).generic==0
    roundtrip(s)


def test_glory_actual_flashback_creates_humans_and_exiles(cards):
    s=game(cards)
    put(s,'Grizzly Bears','battlefield')
    source=put(s,'Visions of Glory','graveyard')
    mana(s,C=4,W=2)
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:exile'
    assert len([c for c in s.state.cards.values() if c.token and c.zone=='p1:battlefield' and c.name=='Human'])==1
    assert not any(mana_pool(s).values())
    roundtrip(s)

@pytest.mark.parametrize('bargain',[False,True])
def test_glutton_actual_announced_bargain_sacrifices_once(cards,bargain):
    s=game(cards)
    source=put(s,'Hamlet Glutton','hand')
    ring=put(s,'Sol Ring','battlefield')
    mana(s,C=3 if bargain else 5,G=2)
    act(s,'p1',type='cast_spell',card_id=source.id,optional_costs=[f'{source.id}:bargain'] if bargain else [],sources=[])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert s.state.cards[ring.id].zone==('p1:graveyard' if bargain else 'p1:battlefield')
    assert s.state.players['p1'].life==43
    assert not any(mana_pool(s).values())
    roundtrip(s)

@pytest.mark.parametrize('artifact,enchantment',[(False,False),(True,False),(False,True),(True,True)])
def test_assassins_independent_reductions_and_actual_destruction(cards,artifact,enchantment):
    s=game(cards)
    if artifact:
        put(s,'Sol Ring','battlefield')
    if enchantment:
        put(s,'Solemnity','battlefield')
    victim=put(s,'Grizzly Bears','battlefield','p2')
    source=put(s,"Assassin's Ink",'hand')
    cost=casting.spell_cost(s.state,source,chars(s,source),info=s.cards,player='p1')
    assert cost.generic==2-int(artifact)-int(enchantment)
    mana(s,C=cost.generic,B=2)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=[victim.id],sources=[])
    settle(s)
    assert s.state.cards[victim.id].zone=='p2:graveyard'
    assert not any(mana_pool(s).values())
    roundtrip(s)

@pytest.mark.parametrize('spirit,enchantment',[(False,False),(True,False),(False,True),(True,True)])
def test_geistlight_independent_reductions(cards,spirit,enchantment):
    s=game(cards)
    if spirit:
        put(s,'Kami of Ancient Law','battlefield')
    if enchantment:
        put(s,'Solemnity','battlefield')
    source=put(s,'Geistlight Snare','hand')
    assert casting.spell_cost(s.state,source,chars(s,source),info=s.cards,player='p1').generic==2-int(spirit)-int(enchantment)
    roundtrip(s)


def test_dread_opponent_chooses_own_graveyard_caster_gets_creature(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','graveyard','p2')
    elf=put(s,'Llanowar Elves','graveyard','p2')
    own=put(s,'Grizzly Bears','graveyard')
    source=put(s,'Visions of Dread','graveyard')
    mana(s,C=4,B=2)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=['p2'],sources=[])
    settle(s)
    d=s.state.rules.decision
    assert d and d.player=='p2'
    assert {o.id for o in d.options}=={bear.id,elf.id}
    roundtrip(s)
    act(s,'p2',type='choose',decision_id=d.id,option_ids=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    assert s.state.cards[bear.id].owner=='p2'
    assert s.state.cards[elf.id].zone=='p2:graveyard'
    assert s.state.cards[own.id].zone=='p1:graveyard'
    assert s.state.cards[source.id].zone=='p1:exile'
    roundtrip(s)


def test_printed_flashback_normal_hand_and_tax_floor(cards):
    s=game(cards)
    source=put(s,'Visions of Glory','hand')
    assert casting.spell_cost(s.state,source,chars(s,source),info=s.cards,player='p1').generic==4
    put(s,'Sphere of Resistance','battlefield','p2')
    source=put(s,'Visions of Glory','graveyard')
    assert casting.spell_cost(s.state,source,chars(s,source),info=s.cards,player='p1').generic==5
    roundtrip(s)

@pytest.mark.parametrize('name,color',[('Visions of Dominance','G'),('Visions of Ruin','R'),('Visions of Duplicity','U')])
def test_remaining_visions_actual_flashback_bodies(cards,name,color):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield','p2')
    b=put(s,'Llanowar Elves','battlefield','p3')
    artifact=put(s,'Sol Ring','battlefield','p2')
    source=put(s,name,'graveyard')
    targets=[a.id] if name.endswith('Dominance') else [a.id,b.id] if name.endswith('Duplicity') else []
    mana(s,**{'C':4,color:2})
    act(s,'p1',type='cast_spell',card_id=source.id,targets=targets,target_counts=[2] if name.endswith('Duplicity') else [],sources=[])
    settle(s)
    if name.endswith('Dominance'):
        assert s.state.cards[a.id].counters.get('+1/+1')==2
    elif name.endswith('Ruin'):
        assert s.state.cards[artifact.id].zone=='p2:graveyard'
        assert len([c for c in s.state.cards.values() if c.token and c.name=='Treasure' and c.zone=='p1:battlefield'])==1
    else:
        assert s.state.cards[a.id].zone=='p3:battlefield'
        assert s.state.cards[b.id].zone=='p2:battlefield'
    assert s.state.cards[source.id].zone=='p1:exile'
    roundtrip(s)


def test_printed_vs_snapcaster_way_discount_and_native_saved_choice(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s=game(cards)
    source=put(s,'Visions of Glory','graveyard')
    mage=put(s,'Snapcaster Mage','hand')
    mana(s,C=1,U=1)
    act(s,'p1',type='cast_spell',card_id=mage.id,sources=[])
    settle(s)
    d=s.state.rules.decision
    if d:
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[source.id])
        settle(s)
    wait_priority(s,'p1')
    ch=chars(s,source)
    assert casting.spell_cost(s.state,source,ch,info=s.cards,player='p1',flashback_choice=0).generic==4
    # Snapcaster gives its printed mana cost, not the printed flashback way.
    other=casting.spell_cost(s.state,source,ch,info=s.cards,player='p1',flashback_choice=1)
    assert other.generic==4 and other.colored==('W',)
    mana(s,C=4,W=1)
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    d=s.state.rules.decision
    assert d and d.resume['step']=='flashback_choice'
    roundtrip(s)
    act(s,'p1',type='choose',decision_id=d.id,option_ids=['1'])
    settle(s)
    assert s.state.cards[source.id].zone=='p1:exile'
    roundtrip(s)


def test_commander_in_hand_is_not_eligible_for_printed_discount(cards):
    s=game(cards)
    put(s,'Krenko, Mob Boss','hand')
    source=put(s,'Visions of Glory','graveyard')
    assert casting.spell_cost(s.state,source,chars(s,source),info=s.cards,player='p1').generic==8
    roundtrip(s)

@pytest.mark.parametrize('name,generic,blue', [('Ice Out',0,2),("Johann's Stopgap",1,1)])
def test_other_bargain_discounts_paid_by_one_native_sacrifice(cards,name,generic,blue):
    from app.rules.view import hints
    from tests.test_rules_bandmate_references import wait_priority
    s=game(cards)
    ring=put(s,'Sol Ring','battlefield')
    source=put(s,name,'hand')
    targets=[]
    if name=='Ice Out':
        opt=put(s,'Opt','hand','p2')
        mana(s,pid='p2',U=1)
        wait_priority(s,'p2')
        act(s,'p2',type='cast_spell',card_id=opt.id,sources=[])
        wait_priority(s,'p1')
        targets=[opt.id]
    else:
        target=put(s,'Grizzly Bears','battlefield','p2')
        targets=[target.id]
    mana(s,C=generic,U=blue)
    offered=hints(s.state,'p1',s.cards)['optional_costs'][source.id]
    assert offered and offered[0]['id']==f'{source.id}:bargain'
    act(s,'p1',type='cast_spell',card_id=source.id,targets=targets,optional_costs=[offered[0]['id']],sources=[])
    settle(s)
    assert s.state.cards[ring.id].zone=='p1:graveyard'
    if name=='Ice Out':
        assert s.state.cards[opt.id].zone=='p2:graveyard'
    else:
        assert s.state.cards[target.id].zone=='p2:hand'
    assert not any(mana_pool(s).values())
    roundtrip(s)


def test_actual_geistlight_counter_unless_payment_uses_both_reductions(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s=game(cards)
    put(s,'Kami of Ancient Law','battlefield')
    put(s,'Solemnity','battlefield')
    opt=put(s,'Opt','hand','p2')
    mana(s,pid='p2',U=1)
    wait_priority(s,'p2')
    act(s,'p2',type='cast_spell',card_id=opt.id,sources=[])
    wait_priority(s,'p1')
    source=put(s,'Geistlight Snare','hand')
    mana(s,U=1)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=[opt.id],sources=[])
    settle(s)
    d=s.state.rules.decision
    if d:
        act(s,d.player,type='choose',decision_id=d.id,option_ids=['decline'])
        settle(s)
    assert s.state.cards[opt.id].zone=='p2:graveyard'
    assert not any(mana_pool(s).values())
    roundtrip(s)


def test_artifact_condition_is_locked_before_native_mana_sacrifice(cards):
    s=game(cards)
    petal=put(s,'Lotus Petal','battlefield')
    victim=put(s,'Grizzly Bears','battlefield','p2')
    source=put(s,"Assassin's Ink",'hand')
    mana(s,C=1,B=1)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=[victim.id],sources=[petal.id])
    settle(s)
    assert s.state.cards[petal.id].zone=='p1:graveyard'
    assert s.state.cards[victim.id].zone=='p2:graveyard'
    assert not any(mana_pool(s).values())
    roundtrip(s)


def test_owned_commander_discount_ignores_controller_and_excludes_stolen_commander(cards):
    s=game(cards)
    own=put(s,'Krenko, Mob Boss','battlefield')
    act(s,'p1',type='set_controller',card_ids=[own.id],player='p2')
    other=put(s,"Atraxa, Praetors' Voice",'battlefield','p2')
    act(s,'p1',type='set_controller',card_ids=[other.id],player='p1')
    source=put(s,'Visions of Glory','graveyard')
    assert casting.spell_cost(s.state,source,chars(s,source),info=s.cards,player='p1').generic==4
    put(s,'Krenko, Mob Boss','hand')
    assert casting.spell_cost(s.state,source,chars(s,source),info=s.cards,player='p1').generic==8
    roundtrip(s)


def test_dread_native_choice_resumes_in_fresh_process(cards,tmp_path):
    import subprocess
    import sys

    s=game(cards)
    bear=put(s,'Grizzly Bears','graveyard','p2')
    put(s,'Llanowar Elves','graveyard','p2')
    source=put(s,'Visions of Dread','graveyard')
    mana(s,C=4,B=2)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=['p2'],sources=[])
    settle(s)
    saved=tmp_path/'dread.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
save,db,source,bear=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
assert d.player=='p2'
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[bear]})
for _ in range(12):
 if not s.state.zones['stack']:break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert s.state.cards[source].zone=='p1:exile'
assert s.state.cards[bear].zone=='p1:battlefield'
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),source.id,bear.id],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr

@pytest.mark.parametrize('text',[
    'This spell costs {1} more to cast if you control an artifact and {1} less to cast if you control an enchantment.',
    'This spell costs {U} less to cast if you control an artifact and {1} less to cast if you control an enchantment.',
    'This spell costs {1} less to cast if you control an artifact and {1} less to cast if you own a purple unicorn.',
])
def test_unknown_or_mixed_compound_discount_is_not_approximated(text):
    from app.rules import conditional_own_discounts
    assert conditional_own_discounts.self_change(text) is None
