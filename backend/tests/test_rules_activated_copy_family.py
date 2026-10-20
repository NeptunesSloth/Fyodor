"""Canonical payment-dependent effects reuse native casts, triggers and choices."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, history
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Ashnod the Uncaring','Verrak, Warped Sengir','Pit Automaton','Dynaheir, Invoker Adept','Magus Lucea Kane']


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/activated_copy_family_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='sme',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/activated_copy_family_cards.json').read_text())]
    s=table(cards,names,names,names)
    for p in ('p1','p2','p3'):
        act(s,p,type='set_prefs',hold_priority=True)
    return s


def cast(s,name,pool,targets=(),pid='p1',**kwargs):
    wait_priority(s,pid)
    c=put(s,name,'hand',pid=pid)
    if pool:
        act(s,pid,type='add_mana',player=pid,mana=pool)
    act(s,pid,type='cast_spell',card_id=c.id,targets=list(targets),sources=[],**kwargs)
    return c


def answer(s,optional=True):
    for _ in range(100):
        settle(s)
        d=s.state.rules.decision
        if d is None:
            return
        ids={o.id for o in d.options}
        if 'keep' in ids:
            chosen=['keep']
        elif 'yes' in ids:
            chosen=['yes' if optional else 'no']
        elif 'pay' in ids and 'decline' in ids:
            chosen=['pay' if optional else 'decline']
        elif 'p3' in ids:
            chosen=['p3']
        else:
            chosen=[o.id for o in d.options][:max(1,d.min_choices)]
        act(s,d.player,type='choose',decision_id=d.id,option_ids=chosen)
    raise AssertionError('Decisions did not finish')


def drawn(s,pid='p1'):
    return history.log_for(Plan(s.state,'p1',s.cards,None)).drew.get(pid,0)


def permanents(s,word,pid='p1'):
    plan=Plan(s.state,pid,s.cards,None)
    return [c for c in s.state.cards.values() if c.zone==pid+':battlefield' and word in plan.ch(c).subtypes]


def setup(cards,name):
    s=game(cards)
    source=put(s,name,'battlefield')
    to_phase(s,'main1',4)
    return s,source


def activate(s,source,index=0,pool=None,targets=(),**kw):
    wait_priority(s,'p1')
    if pool:
        act(s,'p1',type='add_mana',player='p1',mana=pool)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=index,targets=list(targets),**kw)


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('accept',[False,True])
def test_ashnod_copies_actual_sacrifice_activation_without_paying_cost_twice(cards,accept):
    s,_=setup(cards,'Ashnod the Uncaring')
    tymaret=put(s,'Tymaret, the Murder King','battlefield')
    victim=put(s,'Grizzly Bears','battlefield')
    activate(s,tymaret,pool={'R':1,'C':1},targets=['p2'],cost_choices=[{'component':1,'cards':[victim.id]}])
    answer(s,optional=accept)
    assert s.state.players['p2'].life==40-(4 if accept else 2)
    assert s.state.cards[victim.id].zone=='p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('accept',[False,True])
def test_verrak_actual_greed_pays_original_direct_life_again(cards,accept):
    s,_=setup(cards,'Verrak, Warped Sengir')
    greed=put(s,'Greed','battlefield')
    before=drawn(s)
    activate(s,greed,pool={'B':1})
    answer(s,optional=accept)
    assert drawn(s)-before==(2 if accept else 1)
    assert s.state.players['p1'].life==40-(4 if accept else 2)
    roundtrip(s)


def test_dynaheir_four_actual_mana_copies_azure_mage(cards):
    s,source=setup(cards,'Dynaheir, Invoker Adept')
    activate(s,source,2)
    answer(s)
    mage=put(s,'Azure Mage','battlefield')
    before=drawn(s)
    activate(s,mage,pool={'U':1,'C':3})
    answer(s)
    assert drawn(s)-before==2
    assert not s.state.rules.delayed
    roundtrip(s)


def test_pit_automaton_prepares_exhaust_copy_preserving_x(cards):
    s,source=setup(cards,'Pit Automaton')
    activate(s,source,2,pool={'C':2})
    answer(s)
    mobile=put(s,'Boommobile','battlefield')
    activate(s,mobile,1,pool={'C':5,'R':1},targets=['p2'],x_value=3)
    answer(s)
    assert s.state.players['p2'].life==34
    assert s.state.cards[mobile.id].counters.get('+1/+1')==2
    roundtrip(s)


def test_magus_mana_ability_does_not_use_stack_and_copies_x_spell_without_spending_its_mana(cards):
    s,source=setup(cards,'Magus Lucea Kane')
    activate(s,source,1)
    assert not s.state.zones['stack']
    assert len(s.state.rules.delayed)==1
    act(s,'p1',type='clear_mana',player='p1')
    cast(s,'Walking Ballista',{'C':4},x_value=2)
    answer(s)
    copies=[c for c in s.state.cards.values() if c.zone=='p1:battlefield' and Plan(s.state,'p1',s.cards,None).ch(c).name=='Walking Ballista']
    assert len(copies)==2 and all(c.counters.get('+1/+1')==2 for c in copies)
    assert not s.state.rules.delayed
    roundtrip(s)


def test_verrak_excludes_upstream_mana_confluence_life_from_greed_repayment(cards):
    s,_=setup(cards,'Verrak, Warped Sengir')
    greed=put(s,'Greed','battlefield')
    confluence=put(s,'Mana Confluence','battlefield')
    before=drawn(s)
    activate(s,greed,sources=[confluence.id])
    answer(s)
    assert drawn(s)-before==2
    assert s.state.players['p1'].life==35  # 1 for mana; 2 for Greed; exactly 2 again.
    roundtrip(s)


def test_verrak_does_not_trigger_on_life_paid_only_for_input_mana(cards):
    s,_=setup(cards,'Verrak, Warped Sengir')
    mage=put(s,'Azure Mage','battlefield')
    confluence=put(s,'Mana Confluence','battlefield')
    before=drawn(s)
    activate(s,mage,pool={'C':3},sources=[confluence.id])
    answer(s)
    assert drawn(s)-before==1 and s.state.players['p1'].life==39
    roundtrip(s)


def test_dynaheir_reduced_cost_does_not_consume_watch_then_full_cost_does(cards):
    s,source=setup(cards,'Dynaheir, Invoker Adept')
    activate(s,source,2)
    answer(s)
    mage=put(s,'Azure Mage','battlefield')
    training=put(s,'Training Grounds','battlefield')
    before=drawn(s)
    activate(s,mage,pool={'U':1,'C':1})
    answer(s)
    assert drawn(s)-before==1 and len(s.state.rules.delayed)==1
    act(s,'p1',type='move',card_ids=[training.id],to={'player':'p1','zone':'exile'})
    activate(s,mage,pool={'U':1,'C':3})
    answer(s)
    assert drawn(s)-before==3 and not s.state.rules.delayed
    roundtrip(s)


def test_dynaheir_grants_only_activation_haste_to_other_new_creatures(cards):
    s,_=setup(cards,'Dynaheir, Invoker Adept')
    pyro=put(s,'Prodigal Pyromancer','battlefield')
    activate(s,pyro,targets=['p2'])
    answer(s)
    assert s.state.players['p2'].life==39
    assert 'haste' not in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[pyro.id]).keywords
    roundtrip(s)


def test_magus_single_union_watch_consumed_by_x_activation_not_again_by_x_spell(cards):
    s,source=setup(cards,'Magus Lucea Kane')
    activate(s,source,1)
    mobile=put(s,'Boommobile','battlefield')
    activate(s,mobile,1,pool={'R':1,'C':3},targets=['p2'],x_value=3)
    answer(s)
    assert s.state.players['p2'].life==34 and not s.state.rules.delayed
    cast(s,'Walking Ballista',{'C':2},x_value=1)
    answer(s)
    copies=[c for c in s.state.cards.values() if c.zone=='p1:battlefield' and Plan(s.state,'p1',s.cards,None).ch(c).name=='Walking Ballista']
    assert len(copies)==1
    roundtrip(s)


def test_magus_does_not_consume_watch_on_no_x_then_copies_x_zero(cards):
    s,source=setup(cards,'Magus Lucea Kane')
    activate(s,source,1)
    mage=put(s,'Azure Mage','battlefield')
    activate(s,mage,pool={'U':1,'C':1})
    answer(s)
    assert len(s.state.rules.delayed)==1
    cast(s,'Walking Ballista',{},x_value=0)
    answer(s)
    assert not s.state.rules.delayed
    assert not [c for c in s.state.cards.values() if c.zone=='p1:battlefield' and Plan(s.state,'p1',s.cards,None).ch(c).name=='Walking Ballista']
    roundtrip(s)


def test_verrak_saved_trigger_keeps_direct_life_after_original_ability_countered(cards):
    s,_=setup(cards,'Verrak, Warped Sengir')
    greed=put(s,'Greed','battlefield')
    before=drawn(s)
    activate(s,greed,pool={'B':1})
    ability=next(cid for cid,e in s.state.rules.stack.items() if e.kind=='activated' and e.source_card==greed.id)
    cast(s,'Stifle',{'U':1},[ability],pid='p2')
    roundtrip(s)
    answer(s)
    assert drawn(s)-before==1 and s.state.players['p1'].life==36
    roundtrip(s)


def test_pit_watch_ignores_ordinary_activation_and_outlives_source(cards):
    s,source=setup(cards,'Pit Automaton')
    activate(s,source,2,pool={'C':2})
    answer(s)
    mage=put(s,'Azure Mage','battlefield')
    activate(s,mage,pool={'U':1,'C':3})
    answer(s)
    assert len(s.state.rules.delayed)==1
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'exile'})
    roundtrip(s)
    mobile=put(s,'Boommobile','battlefield')
    activate(s,mobile,1,pool={'C':3,'R':1},targets=['p2'],x_value=1)
    answer(s)
    assert s.state.players['p2'].life==38 and not s.state.rules.delayed
    roundtrip(s)


def test_dynaheir_saved_watch_outlives_source_and_expires_this_turn(cards):
    s,source=setup(cards,'Dynaheir, Invoker Adept')
    activate(s,source,2)
    answer(s)
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'exile'})
    roundtrip(s)
    mage=put(s,'Azure Mage','battlefield')
    before=drawn(s)
    activate(s,mage,pool={'U':1,'C':3})
    answer(s)
    assert drawn(s)-before==2
    roundtrip(s)


def test_magus_watch_cleanup_expiry(cards):
    s,source=setup(cards,'Magus Lucea Kane')
    activate(s,source,1)
    assert len(s.state.rules.delayed)==1
    roundtrip(s)
    to_phase(s,'main1',7)
    assert not s.state.rules.delayed
    cast(s,'Walking Ballista',{'C':2},x_value=1)
    answer(s)
    copies=[c for c in s.state.cards.values() if c.zone=='p1:battlefield' and Plan(s.state,'p1',s.cards,None).ch(c).name=='Walking Ballista']
    assert len(copies)==1
    roundtrip(s)


def test_magus_saved_copy_retargets_without_changing_original_or_paying_exhaust_again(cards):
    s,source=setup(cards,'Magus Lucea Kane')
    activate(s,source,1)
    mobile=put(s,'Boommobile','battlefield')
    activate(s,mobile,1,pool={'R':1,'C':3},targets=['p2'],x_value=3)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.resume.get('step')=='copy_target'
    assert 'p3' in {o.id for o in d.options}
    roundtrip(s)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['p3'])
    answer(s)
    assert s.state.players['p2'].life==37 and s.state.players['p3'].life==37
    assert s.state.cards[mobile.id].counters.get('+1/+1')==2
    roundtrip(s)


def test_magus_copies_countered_original_x_spell_from_native_lki(cards):
    s,source=setup(cards,'Magus Lucea Kane')
    activate(s,source,1)
    act(s,'p1',type='clear_mana',player='p1')
    spell=cast(s,'Walking Ballista',{'C':4},x_value=2)
    cast(s,'Counterspell',{'U':2},[spell.id],pid='p2')
    roundtrip(s)
    answer(s)
    copies=[c for c in s.state.cards.values() if c.zone=='p1:battlefield' and Plan(s.state,'p1',s.cards,None).ch(c).name=='Walking Ballista']
    assert len(copies)==1 and copies[0].is_token and copies[0].counters.get('+1/+1')==2
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    roundtrip(s)


def test_verrak_cannot_repay_direct_life_after_platinum_emperion_enters(cards):
    s,_=setup(cards,'Verrak, Warped Sengir')
    greed=put(s,'Greed','battlefield')
    before=drawn(s)
    activate(s,greed,pool={'B':1})
    put(s,'Platinum Emperion','battlefield')
    answer(s)
    assert drawn(s)-before==1 and s.state.players['p1'].life==38
    roundtrip(s)


def test_ashnod_copies_burnished_hart_after_its_source_was_sacrificed(cards):
    s,_=setup(cards,'Ashnod the Uncaring')
    hart=put(s,'Burnished Hart','battlefield')
    before=len(s.state.zones['p1:battlefield'])
    activate(s,hart,pool={'C':3})
    roundtrip(s)
    answer(s)
    assert s.state.cards[hart.id].zone=='p1:graveyard'
    # Helper chooses one basic from each of the two independent up-to-two searches.
    assert len(s.state.zones['p1:battlefield'])==before+1
    roundtrip(s)


def test_dynaheir_does_not_grant_attack_haste_to_other_new_creatures(cards):
    from app.game.errors import ActionError

    s,_=setup(cards,'Dynaheir, Invoker Adept')
    pyro=put(s,'Prodigal Pyromancer','battlefield')
    to_phase(s,'declare_attackers',4)
    with pytest.raises(ActionError,match='sick|haste|attack'):
        act(s,'p1',type='declare_attackers',attackers=[{'card_id':pyro.id,'target':'p2'}])
    assert not s.state.cards[pyro.id].tapped
    roundtrip(s)


def test_dynaheir_other_exclusion_does_not_replace_its_own_intrinsic_haste(cards):
    from dataclasses import replace

    from app.rules import cast_limits, casting

    s,source=setup(cards,'Dynaheir, Invoker Adept')
    put(s,'Dynaheir, Invoker Adept','hand')
    source=put(s,'Dynaheir, Invoker Adept','battlefield')
    ch=Plan(s.state,'p1',s.cards,None).ch(source)
    assert not cast_limits.as_though_haste(s.state,source,s.cards)
    assert casting.can_use_tap_abilities(s.state,source,ch,s.cards)
    # Isolate the printed other-only permission from Dynaheir's independent haste.
    assert not casting.can_use_tap_abilities(s.state,source,replace(ch,lost=ch.lost|{'haste'}),s.cards)
    roundtrip(s)


@pytest.mark.parametrize('source_name',['Magus Lucea Kane','Dynaheir, Invoker Adept'])
def test_x_cycling_uses_actual_receipt_and_copies_only_draw_not_cycle_event(cards,source_name):
    s,source=setup(cards,source_name)
    activate(s,source,1 if source_name=='Magus Lucea Kane' else 2)
    answer(s)
    act(s,'p1',type='clear_mana',player='p1')
    shark=put(s,'Shark Typhoon','hand')
    before=drawn(s)
    activate(s,shark,1,pool={'U':1,'C':3},x_value=2)
    original=next(e for e in s.state.rules.stack.values() if e.kind=='activated' and e.source_card==shark.id)
    assert original.x==2
    roundtrip(s)
    answer(s)
    assert drawn(s)-before==2
    sharks=[c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield' and 'Shark' in Plan(s.state,'p1',s.cards,None).ch(c).subtypes]
    assert len(sharks)==1 and Plan(s.state,'p1',s.cards,None).ch(sharks[0]).pt==(2,2)
    assert s.state.cards[shark.id].zone=='p1:graveyard' and not s.state.rules.delayed
    roundtrip(s)


def test_magus_ignores_x_in_card_mana_cost_when_activated_cycling_cost_has_no_x(cards):
    s,source=setup(cards,'Magus Lucea Kane')
    activate(s,source,1)
    decree=put(s,'Decree of Justice','hand')
    before=drawn(s)
    activate(s,decree,1,pool={'W':1})
    answer(s,optional=False)
    assert drawn(s)-before==1 and len(s.state.rules.delayed)==1
    roundtrip(s)


def test_ashnod_does_not_count_lotus_petal_sacrificed_for_input_mana(cards):
    s,_=setup(cards,'Ashnod the Uncaring')
    mage=put(s,'Azure Mage','battlefield')
    petal=put(s,'Lotus Petal','battlefield')
    before=drawn(s)
    activate(s,mage,pool={'C':3},sources=[petal.id])
    answer(s)
    assert drawn(s)-before==1 and s.state.cards[petal.id].zone=='p1:graveyard'
    roundtrip(s)


def test_special_cycling_callback_resumes_after_injected_low_level_mana_draw(cards,monkeypatch,tmp_path):
    # Deliberate engine injection below Oracle classification; not a printed mana ability.
    from tests.payment_rider_injection import inject_mana_draw_rider

    inject_mana_draw_rider(monkeypatch,{'Mana Confluence'})
    s,source=setup(cards,'Magus Lucea Kane')
    activate(s,source,1)
    act(s,'p1',type='clear_mana',player='p1')
    put(s,'Abundance','battlefield')
    confluence=put(s,'Mana Confluence','battlefield')
    shark=put(s,'Shark Typhoon','hand')
    before=drawn(s)
    activate(s,shark,1,pool={'C':3},sources=[confluence.id],x_value=2)
    d=s.state.rules.decision
    assert d is not None and 'decline' in {o.id for o in d.options}
    assert s.state.cards[shark.id].zone=='p1:hand'
    roundtrip(s)
    import subprocess
    import sys

    saved=tmp_path/'cycling-callback.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from pytest import MonkeyPatch
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.payment_rider_injection import inject_mana_draw_rider
from tests.test_rules_activated_copy_family import drawn
from tests.test_rules_designations import settle
save,db,shark,before=sys.argv[1:]
patch=MonkeyPatch()
inject_mana_draw_rider(patch,{'Mana Confluence'})
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
for _ in range(30):
    settle(s)
    d=s.state.rules.decision
    if d is None: break
    ids={o.id for o in d.options}
    choice='decline' if 'decline' in ids else 'keep' if 'keep' in ids else d.options[0].id
    s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[choice]})
assert drawn(s)-int(before)==3
assert s.state.cards[shark].zone=='p1:graveyard'
assert not s.state.rules.delayed and not s.state.zones['stack']
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),shark.id,str(before)],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    for _ in range(20):
        settle(s)
        d=s.state.rules.decision
        if d is None:
            break
        ids={o.id for o in d.options}
        choice='decline' if 'decline' in ids else 'keep' if 'keep' in ids else d.options[0].id
        roundtrip(s)
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[choice])
    assert drawn(s)-before==3
    assert s.state.cards[shark.id].zone=='p1:graveyard'
    assert not s.state.rules.delayed and not s.state.zones['stack']
    sharks=[c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield' and 'Shark' in Plan(s.state,'p1',s.cards,None).ch(c).subtypes]
    assert len(sharks)==1
    roundtrip(s)
