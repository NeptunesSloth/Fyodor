"""Restricted generic X costs remain generic, with native payment and announced X."""
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
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Crypt Rats','Consume Spirit','Crimson Hellkite','Atalya, Samite Master']

@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/x_mana_restriction_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='xmr',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards,extras=()):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/x_mana_restriction_cards.json').read_text())]
    s=table(cards,names,names,names)
    for pid in ('p1','p2','p3'):
        act(s,pid,type='set_prefs',hold_priority=True)
    for name in extras:
        put(s,name,'battlefield')
    return s


def mana(s,**amount):
    act(s,'p1',type='add_mana',player='p1',mana=amount)


def consume(s,x=3):
    source=put(s,'Consume Spirit','hand')
    act(s,'p1',type='cast_spell',card_id=source.id,x_value=x,targets=['p3'],sources=[])
    return source


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def test_consume_spirit_rejects_nonblack_for_x_without_spending_anything(cards):
    s=setup(cards)
    mana(s,C=4,B=1)
    before=mana_pool(s,'p1')
    with pytest.raises(ActionError):
        consume(s)
    assert mana_pool(s,'p1')==before and not s.state.zones.get('stack')
    roundtrip(s)


def test_other_generic_is_unrestricted_and_x_and_mana_value_remain_announced(cards):
    s=setup(cards)
    mana(s,R=1,B=4)
    source=consume(s)
    entry=s.state.rules.stack[source.id]
    assert entry.x==3
    from app.rules.plan import Plan
    from app.rules.stack_interaction import mana_value
    assert mana_value(s.state.cards[source.id],Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source.id]))==5
    roundtrip(s)
    settle(s)
    assert s.state.players['p3'].life==37 and s.state.players['p1'].life==43
    roundtrip(s)


@pytest.mark.parametrize('black',[0,1])
def test_generic_cost_reduction_can_reduce_restricted_x(cards,black):
    s=setup(cards,['Jet Medallion'])
    if black:
        put(s,'Jet Medallion','battlefield',pid='p2')  # Opponent's Medallion never reduces our cost.
        mana(s,B=2,R=1)
        source=consume(s,x=2)
    else:
        mana(s,B=1,R=1)
        source=consume(s,x=1)
    roundtrip(s)
    settle(s)
    assert s.state.players['p3'].life==40-(2 if black else 1)
    assert s.state.cards[source.id].zone=='p1:graveyard'


def test_training_grounds_reduces_rats_x_but_remainder_requires_black(cards):
    s=setup(cards,['Training Grounds'])
    source=put(s,'Crypt Rats','battlefield')
    mana(s,B=1)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,x_value=3,sources=[])
    roundtrip(s)
    settle(s)
    assert all(p.life==37 for p in s.state.players.values())
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize(('name','color','x','modes'),[('Crimson Hellkite','R',2,None),('Atalya, Samite Master','W',2,[1])])
def test_tapped_activated_x_restriction_native_effect(cards,name,color,x,modes):
    s=setup(cards)
    source=put(s,name,'battlefield')
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    to_phase(s,'main1',turn=4)
    mana(s,**{color:x})
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1 if name=='Crimson Hellkite' else 0,x_value=x,
        targets=[target.id] if name=='Crimson Hellkite' else [],**({'modes':modes} if modes else {}),sources=[])
    assert s.state.cards[source.id].tapped
    roundtrip(s)
    settle(s)
    if name=='Crimson Hellkite':
        assert s.state.cards[target.id].zone=='p2:graveyard'
    else:
        assert s.state.players['p1'].life==42
    roundtrip(s)


def test_krrik_only_substitutes_actual_black_symbol_not_generic_x(cards):
    s=setup(cards,["K'rrik, Son of Yawgmoth"])
    mana(s,C=4)
    with pytest.raises(ActionError):
        consume(s)
    assert s.state.players['p1'].life==40 and mana_pool(s,'p1')['C']==4
    roundtrip(s)


def test_as_though_any_color_can_pay_x_without_changing_actual_mana_spent(cards):
    s=setup(cards,['Mycosynth Lattice'])
    mana(s,C=5)
    source=consume(s)
    assert s.state.rules.payments[s.state.rules.object_id(source.id)].mana_spent=={'C':5}
    roundtrip(s)
    settle(s)
    assert s.state.players['p3'].life==37 and s.state.players['p1'].life==43
    roundtrip(s)


def test_tax_generic_stays_unrestricted_while_reduction_can_apply_to_x_first(cards):
    s=setup(cards,['Jet Medallion','Sphere of Resistance'])
    mana(s,R=2,B=1)
    consume(s,x=1)  # {X}{1}{B} + {1} - {1}: reduce X, pay two unrelated generic with red.
    roundtrip(s)
    settle(s)
    assert s.state.players['p3'].life==39


def test_floor_generic_does_not_restore_restricted_x_reduced_away(cards):
    s=setup(cards,['Jet Medallion','Trinisphere'])
    mana(s,R=2,B=1)
    consume(s,x=1)
    roundtrip(s)
    settle(s)
    assert s.state.players['p3'].life==39


def test_krrik_can_pay_the_fixed_black_symbol_with_life_but_requires_mana_for_x(cards):
    s=setup(cards,["K'rrik, Son of Yawgmoth"])
    mana(s,R=1,B=2)
    consume(s,x=2)
    assert s.state.players['p1'].life==38
    roundtrip(s)
    settle(s)
    assert s.state.players['p1'].life==40 and s.state.players['p3'].life==38


def test_free_alternative_keeps_x_zero_and_requires_no_restricted_mana(cards):
    s=setup(cards,['Omniscience'])
    source=put(s,'Consume Spirit','hand')
    act(s,'p1',type='cast_spell',card_id=source.id,x_value=0,targets=['p3'],sources=[],free=True)
    assert s.state.rules.stack[source.id].x==0
    roundtrip(s)
    settle(s)
    assert s.state.players['p3'].life==40 and s.state.players['p1'].life==40


def test_convoke_generic_contribution_pays_x_without_spending_mana(cards):
    s=setup(cards,['Wand of the Worldsoul'])
    bear=put(s,'Grizzly Bears','battlefield')
    wand=next(c for c in s.state.cards.values() if c.name=='Wand of the Worldsoul' and c.zone=='p1:battlefield')
    act(s,'p1',type='activate_ability',card_id=wand.id,ability=2)
    settle(s)
    mana(s,R=1,B=1)
    source=put(s,'Consume Spirit','hand')
    act(s,'p1',type='cast_spell',card_id=source.id,x_value=1,targets=['p3'],sources=[],contributions=[{'kind':'convoke','card':bear.id}])
    record=s.state.rules.payments[s.state.rules.object_id(source.id)]
    assert record.mana_spent=={'B':1,'R':1}
    assert [(c.kind,c.pays) for c in record.contributions]==[('convoke','1')]
    roundtrip(s)
    settle(s)
    assert s.state.players['p3'].life==39


def test_self_payment_omitted_color_selects_black_and_cold_save_retains_constraint(cards):
    from tests.test_rules_payment import engine_payment

    s=setup(cards)
    land=put(s,'Dimir Guildgate','battlefield')
    if s.state.cards[land.id].tapped:
        act(s,'p1',type='tap',card_ids=[land.id],tapped=False)
    engine_payment(s,'p1','self')
    mana(s,R=1,B=1)
    source=put(s,'Consume Spirit','hand')
    act(s,'p1',type='cast_spell',card_id=source.id,x_value=1,targets=['p3'])
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='pay_mana'
    assert d.resume['x_payment']['n']==1
    assert s.view('p1')['rules']['decision']['display']['remaining']!=''
    roundtrip(s)
    act(s,'p1',type='activate_ability',card_id=land.id,ability=1)
    assert s.state.rules.decision is None
    record=s.state.rules.payments[s.state.rules.object_id(source.id)]
    assert record.mana_spent=={'R':1,'B':2}
    roundtrip(s)


def test_cancelled_payment_preserves_x_mana_restriction_when_reannounced(cards):
    from tests.test_rules_payment import engine_payment

    s=setup(cards)
    engine_payment(s,'p1','self')
    mana(s,R=3,B=1)
    source=put(s,'Consume Spirit','hand')
    act(s,'p1',type='cast_spell',card_id=source.id,x_value=2,targets=['p3'])
    d=s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s,'p1',type='choose',decision_id=d.id,option_ids=['cancel'])
    assert s.state.cards[source.id].zone=='p1:hand' and mana_pool(s,'p1')=={'R':3,'B':1}
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=source.id,x_value=2,targets=['p3'],sources=[])
    roundtrip(s)


@pytest.mark.parametrize('x',[1,2])
def test_training_grounds_minimum_keeps_the_unreduced_one_mana_in_x_black(cards,x):
    s=setup(cards,['Training Grounds'])
    source=put(s,'Crypt Rats','battlefield')
    mana(s,R=1)
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=0,x_value=x,sources=[])
    assert mana_pool(s,'p1')=={'R':1}
    mana(s,B=1)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,x_value=x,sources=[])
    roundtrip(s)
    settle(s)
    assert all(p.life==40-x for p in s.state.players.values())


def test_atalya_prevention_mode_keeps_white_x_and_actual_damage_prevention(cards):
    s=setup(cards)
    source=put(s,'Atalya, Samite Master','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    to_phase(s,'main1',turn=4)
    mana(s,U=2)
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=0,x_value=2,modes=[0],targets=[bear.id],sources=[])
    mana(s,W=2)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,x_value=2,modes=[0],targets=[bear.id],sources=[])
    settle(s)
    bolt=put(s,'Lightning Bolt','hand')
    mana(s,R=1)
    act(s,'p1',type='cast_spell',card_id=bolt.id,targets=[bear.id],sources=[])
    roundtrip(s)
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:battlefield' and s.state.cards[bear.id].damage==1
    roundtrip(s)


@pytest.mark.parametrize('black',[1,2])
def test_actual_paid_tamiyo_card_copy_menu_and_payment_keep_x_restriction(cards,black):
    s=setup(cards)
    original=put(s,'Consume Spirit','graveyard')
    saga=put(s,'The Tale of Tamiyo','battlefield')
    act(s,'p1',type='counter',card_ids=[saga.id],kind='lore',delta=3)
    plan=put(s,'Contentious Plan','hand')
    mana(s,C=1,U=1)
    act(s,'p1',type='cast_spell',card_id=plan.id,sources=[])
    settle(s)
    def answer(ids):
        d=s.state.rules.decision
        assert d is not None
        roundtrip(s)
        act(s,d.player,type='choose',decision_id=d.id,option_ids=ids)
        settle(s)
    assert s.state.rules.decision.resume['step']=='proliferate'
    answer([saga.id])
    assert s.state.rules.decision.resume['step']=='trigger_group'
    answer([original.id])
    mana(s,B=black,R=3-black)
    copy_id=next(o.id for o in s.state.rules.decision.options if o.label=='Consume Spirit')
    answer([copy_id])
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='free_x'
    ids={o.id for o in d.options}
    assert ('x:1' in ids)==(black==2)
    answer(['x:1' if black==2 else 'x:0'])
    answer(['p3'])
    assert s.state.players['p3'].life==40-(1 if black==2 else 0)
    assert s.state.players['p1'].life==40+(1 if black==2 else 0)
    assert s.state.cards[original.id].zone=='p1:exile'
    roundtrip(s)


def test_locked_zero_restricted_x_survives_sacrificing_reducer_for_mana(cards):
    s=setup(cards,['Jet Medallion','Krark-Clan Ironworks'])
    act(s,'p1',type='set_prefs',payment='self')
    jet=next(c for c in s.state.cards.values() if c.name=='Jet Medallion' and c.zone=='p1:battlefield')
    iron=next(c for c in s.state.cards.values() if c.name=='Krark-Clan Ironworks' and c.zone=='p1:battlefield')
    mana(s,B=1)
    source=put(s,'Consume Spirit','hand')
    act(s,'p1',type='cast_spell',card_id=source.id,x_value=1,targets=['p3'])
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='pay_mana' and d.resume['x_payment']['n']==0
    roundtrip(s)
    act(s,'p1',type='activate_ability',card_id=iron.id,ability=0,cost_choices=[{'component':0,'cards':[jet.id]}])
    d=s.state.rules.decision
    if d is not None and d.resume.get('step')!='pay_mana':
        assert jet.id in {o.id for o in d.options}
        roundtrip(s)
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[jet.id])
    assert s.state.rules.decision is None
    assert s.state.cards[jet.id].zone=='p1:graveyard'
    assert s.state.rules.payments[s.state.rules.object_id(source.id)].mana_spent=={'B':1,'C':1}
    roundtrip(s)
    settle(s)
    assert s.state.players['p3'].life==39
    roundtrip(s)


def test_restricted_self_payment_resumes_in_genuinely_cold_process(cards,tmp_path):
    import subprocess
    import sys

    s=setup(cards)
    land=put(s,'Dimir Guildgate','battlefield')
    act(s,'p1',type='set_prefs',payment='self')
    mana(s,R=1,B=1)
    source=put(s,'Consume Spirit','hand')
    act(s,'p1',type='cast_spell',card_id=source.id,x_value=1,targets=['p3'])
    assert s.state.rules.decision.resume['x_payment']['n']==1
    saved=tmp_path/'restricted-x.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
save,db,land,spell=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
s.perform('p1',{'type':'activate_ability','card_id':land,'ability':1})
assert s.state.rules.decision is None
record=s.state.rules.payments[s.state.rules.object_id(spell)]
assert record.x==1 and record.mana_spent=={'B':2,'R':1}
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    out=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),land.id,source.id],
                       cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert out.returncode==0,out.stderr


def test_actual_crypt_rats_x_1000_is_not_limited_by_python_recursion(cards):
    s=setup(cards)
    source=put(s,'Crypt Rats','battlefield')
    for pid in ('p1','p2','p3'):
        act(s,pid,type='set_life',player=pid,value=2000)
    for _ in range(10):
        mana(s,B=100)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,x_value=1000,sources=[])
    assert sum(mana_pool(s,'p1').values())==0
    entry=next(e for e in s.state.rules.stack.values() if e.kind=='activated')
    assert entry.x==1000
    roundtrip(s)
    settle(s)
    assert all(p.life==1000 for p in s.state.players.values())
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)
