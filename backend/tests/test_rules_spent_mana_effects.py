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

NAMES=['Tellah, Great Sage','Chandra, Dressed to Kill','Wurmquake','Magmablood Archaic','Transcendent Archaic','Exert Influence']


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/spent_mana_effects_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='sme',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/spent_mana_effects_cards.json').read_text())]
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


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('spent',[3,4,7,8,9])
def test_tellah_uses_actual_paid_thresholds_and_total_not_threshold_literal(cards,spent):
    s=game(cards)
    source=put(s,'Tellah, Great Sage','battlefield')
    before=drawn(s)
    cast(s,'Volcanic Geyser',{'R':2,'C':spent-2},['p2'],x_value=spent-2)
    answer(s)
    assert len(permanents(s,'Hero'))==1
    assert drawn(s)-before==(2 if spent>=4 else 0)
    assert s.state.players['p3'].life==40-(spent if spent>=8 else 0)
    assert s.state.cards[source.id].zone==('p1:graveyard' if spent>=8 else 'p1:battlefield')
    roundtrip(s)


@pytest.mark.parametrize('gone',[False,True])
def test_tellah_keeps_cast_payment_after_counter_and_source_lki_if_gone(cards,gone):
    s=game(cards)
    source=put(s,'Tellah, Great Sage','battlefield')
    c=cast(s,'Volcanic Geyser',{'R':2,'C':7},['p2'],x_value=7)
    if gone:
        act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    cast(s,'Counterspell',{'U':2},[c.id])
    answer(s)
    assert s.state.players['p3'].life==31 and s.state.players['p2'].life==31
    assert len(permanents(s,'Hero'))==(1 if gone else 2)
    roundtrip(s)


@pytest.mark.parametrize('pool',[{'C':3},{'R':1,'U':1,'G':1}])
def test_magmablood_pump_counts_actual_colors_on_triggering_spell(cards,pool):
    s=game(cards)
    source=put(s,'Magmablood Archaic','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    before=Plan(s.state,'p1',s.cards,None).ch(source).pt
    # Blaze's printed R can be paid by C only under this actual permission.
    put(s,'Mycosynth Lattice','battlefield')
    cast(s,'Blaze',pool,['p2'],x_value=2)
    answer(s)
    n=sum(c in 'WUBRG' for c in pool)
    plan=Plan(s.state,'p1',s.cards,None)
    assert plan.ch(s.state.cards[bear.id]).pt==(2+n,2)
    assert plan.ch(s.state.cards[source.id]).pt==(before[0]+n,before[1])
    later=put(s,'Willbender','battlefield')
    assert Plan(s.state,'p1',s.cards,None).ch(later).pt==(1,2)
    to_phase(s,'end',1)
    to_phase(s,'upkeep',2)
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[bear.id]).pt==(2,2)
    roundtrip(s)


def test_magmablood_trigger_retains_colors_after_its_spell_is_countered(cards):
    s=game(cards)
    put(s,'Magmablood Archaic','battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    c=cast(s,'Lightning Bolt',{'R':1},['p2'])
    cast(s,'Counterspell',{'U':2},[c.id])
    answer(s)
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[bear.id]).pt==(4,2)
    roundtrip(s)


@pytest.mark.parametrize(('pool','n'),[({'C':7},0),({'C':6,'R':1},1),({'C':4,'U':1,'B':1,'G':1},3)])
def test_transcendent_draws_its_actual_colors_and_discards_only_if_drew(cards,pool,n):
    s=game(cards)
    before=drawn(s)
    held=len(s.state.zones['p1:hand'])
    cast(s,'Transcendent Archaic',pool)
    answer(s)
    assert drawn(s)-before==n
    assert len(s.state.zones['p1:hand'])==(max(0,held+n-2) if n else held)
    roundtrip(s)


def test_transcendent_can_decline_draw_and_does_not_discard(cards):
    s=game(cards)
    before=drawn(s)
    held=list(s.state.zones['p1:hand'])
    cast(s,'Transcendent Archaic',{'C':4,'U':1,'B':1,'G':1})
    answer(s,optional=False)
    assert drawn(s)==before and s.state.zones['p1:hand']==held
    roundtrip(s)


def test_transcendent_draws_stolen_by_notion_thief_do_not_force_controller_discard(cards):
    s=game(cards)
    put(s,'Notion Thief','battlefield',pid='p2')
    held=put(s,'Lightning Bolt','hand')
    before=drawn(s)
    other=drawn(s,'p2')
    cast(s,'Transcendent Archaic',{'C':4,'U':1,'B':1,'G':1})
    answer(s)
    assert drawn(s)==before and drawn(s,'p2')-other==3
    assert s.state.cards[held.id].zone=='p1:hand'
    roundtrip(s)


@pytest.mark.parametrize(('pool','takes'),[({'C':4,'U':1},False),({'C':3,'U':1,'R':1},True)])
def test_exert_power_bound_is_checked_on_resolution_not_target_legality(cards,pool,takes):
    s=game(cards)
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    cast(s,'Exert Influence',pool,[target.id])
    answer(s)
    assert s.state.cards[target.id].controller==('p1' if takes else 'p2')
    roundtrip(s)


def test_exert_uses_changed_power_at_resolution(cards):
    s=game(cards)
    target=put(s,'Grizzly Bears','battlefield',pid='p2')
    cast(s,'Exert Influence',{'C':3,'U':1,'R':1},[target.id])
    act(s,'p1',type='set_counter',card_id=target.id,kind='+1/+1',value=1)
    answer(s)
    assert s.state.cards[target.id].controller=='p2'
    roundtrip(s)


@pytest.mark.parametrize('qualified',[0,1,2])
def test_wurmquake_creates_first_then_one_extra_per_qualifying_opponent(cards,qualified):
    s=game(cards)
    for pid in ('p2','p3')[:qualified]:
        act(s,'p1',type='resource',player=pid,key='poison',delta=3)
    cast(s,'Wurmquake',{'C':4,'G':2})
    answer(s)
    worms=permanents(s,'Wurm')
    assert len(worms)==1+qualified
    assert all(Plan(s.state,'p1',s.cards,None).ch(c).pt==(6,6) for c in worms)
    roundtrip(s)


def test_wurmquake_repeats_original_recipe_through_token_replacement(cards):
    s=game(cards)
    put(s,'Divine Visitation','battlefield')
    act(s,'p1',type='resource',player='p2',key='poison',delta=3)
    cast(s,'Wurmquake',{'C':4,'G':2})
    answer(s)
    angels=permanents(s,'Angel')
    assert len(angels)==2
    assert all(Plan(s.state,'p1',s.cards,None).ch(c).pt==(4,4) for c in angels)
    roundtrip(s)


def chandra_ultimate(s):
    from tests.test_rules_abundance import set_library

    source=put(s,'Chandra, Dressed to Kill','battlefield')
    act(s,'p1',type='set_counter',card_id=source.id,kind='loyalty',value=7)
    ids=set_library(s,['Lightning Bolt','Grizzly Bears','Forest','Sol Ring','Blaze'])
    ability=next(a.index for a in Plan(s.state,'p1',s.cards,None).ch(source).abilities if 'Exile the top five' in a.text)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability,sources=[])
    answer(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert all(s.state.cards[cid].zone=='p1:exile' for cid in ids)
    return {s.state.cards[cid].name:cid for cid in ids}


def test_chandra_ultimate_grants_only_red_paid_spells_and_emblem_actual_payment(cards):
    from app.game.errors import ActionError

    s=game(cards)
    exiled=chandra_ultimate(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':1})
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=exiled['Sol Ring'],sources=[])
    act(s,'p1',type='add_mana',player='p1',mana={'R':1})
    act(s,'p1',type='cast_spell',card_id=exiled['Lightning Bolt'],targets=['p2'],sources=[])
    answer(s)
    assert s.state.players['p2'].life==37 and s.state.players['p3'].life==39
    act(s,'p1',type='add_mana',player='p1',mana={'C':1,'R':1})
    act(s,'p1',type='cast_spell',card_id=exiled['Blaze'],targets=['p2'],sources=[],x_value=2)
    answer(s)
    assert s.state.players['p2'].life==35 and s.state.players['p3'].life==36
    roundtrip(s)


def test_chandra_emblem_keeps_actual_payment_after_trigger_spell_countered(cards):
    s=game(cards)
    exiled=chandra_ultimate(s)
    act(s,'p1',type='add_mana',player='p1',mana={'C':3,'R':1})
    act(s,'p1',type='cast_spell',card_id=exiled['Blaze'],targets=['p2'],sources=[],x_value=3)
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='trigger_target'
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['p3'])
    cast(s,'Counterspell',{'U':2},[exiled['Blaze']])
    answer(s)
    assert s.state.players['p2'].life==40 and s.state.players['p3'].life==36
    roundtrip(s)


def test_transcendent_actual_permanent_spell_copy_spends_zero_for_its_draw(cards):
    s=game(cards)
    before=drawn(s)
    held=len(s.state.zones['p1:hand'])
    c=cast(s,'Transcendent Archaic',{'C':4,'U':1,'B':1,'G':1})
    cast(s,'Double Major',{'U':1,'G':1},[c.id])
    answer(s)
    assert drawn(s)-before==3
    assert len(s.state.zones['p1:hand'])==held+1
    assert len(permanents(s,'Avatar'))==2
    roundtrip(s)


def test_wurmquake_copy_spends_zero_and_its_zero_zero_tokens_die(cards):
    s=game(cards)
    c=cast(s,'Wurmquake',{'C':4,'G':2})
    cast(s,'Reverberate',{'R':2},[c.id])
    answer(s)
    worms=permanents(s,'Wurm')
    assert len(worms)==1 and Plan(s.state,'p1',s.cards,None).ch(worms[0]).pt==(6,6)
    roundtrip(s)


def test_wurmquake_free_cast_has_no_surviving_zero_zero_tokens(cards):
    s=game(cards)
    put(s,'Omniscience','battlefield')
    act(s,'p1',type='resource',player='p2',key='poison',delta=3)
    cast(s,'Wurmquake',{},free=True)
    answer(s)
    assert not permanents(s,'Wurm')
    roundtrip(s)


def test_wurmquake_flashback_uses_actual_ten_mana_not_printed_six(cards):
    s=game(cards)
    c=put(s,'Wurmquake','graveyard')
    act(s,'p1',type='add_mana',player='p1',mana={'C':8,'G':2})
    act(s,'p1',type='cast_spell',card_id=c.id,sources=[])
    answer(s)
    worms=permanents(s,'Wurm')
    assert len(worms)==1 and Plan(s.state,'p1',s.cards,None).ch(worms[0]).pt==(10,10)
    assert s.state.cards[c.id].zone=='p1:exile'
    roundtrip(s)


def test_exert_copy_does_not_inherit_actual_colors_spent_on_original(cards):
    s=game(cards)
    original_target=put(s,'Grizzly Bears','battlefield',pid='p2')
    copy_target=put(s,'Willbender','battlefield',pid='p3')
    c=cast(s,'Exert Influence',{'C':3,'U':1,'R':1},[original_target.id])
    cast(s,'Reverberate',{'R':2},[c.id])
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='copy_target'
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[copy_target.id])
    answer(s)
    assert s.state.cards[original_target.id].controller=='p1'
    assert s.state.cards[copy_target.id].controller=='p3'
    roundtrip(s)


def test_transcendent_draw_prevention_does_not_discard_held_cards(cards):
    s=game(cards)
    put(s,'Spirit of the Labyrinth','battlefield')
    assert drawn(s)>=1
    held=list(s.state.zones['p1:hand'])
    before=drawn(s)
    cast(s,'Transcendent Archaic',{'C':4,'U':1,'B':1,'G':1})
    answer(s)
    assert drawn(s)==before and s.state.zones['p1:hand']==held
    roundtrip(s)


def test_wurmquake_both_native_creation_instructions_apply_token_doubling(cards):
    s=game(cards)
    put(s,'Doubling Season','battlefield')
    act(s,'p1',type='resource',player='p2',key='poison',delta=3)
    cast(s,'Wurmquake',{'C':4,'G':2})
    answer(s)
    assert len(permanents(s,'Wurm'))==4
    roundtrip(s)


def test_wurmquake_extra_token_recipe_does_not_include_chatterfang_extra_squirrels(cards):
    s=game(cards)
    put(s,'Chatterfang, Squirrel General','battlefield')
    act(s,'p1',type='resource',player='p2',key='poison',delta=3)
    cast(s,'Wurmquake',{'C':4,'G':2})
    answer(s)
    assert len(permanents(s,'Wurm'))==2 and len([c for c in permanents(s,'Squirrel') if c.is_token])==2
    roundtrip(s)


def test_transcendent_draw_replacement_cold_resume_counts_actual_draws_not_cards_put_in_hand(cards,tmp_path):
    import subprocess
    import sys

    from tests.test_rules_abundance import set_library

    s=game(cards)
    put(s,'Abundance','battlefield')
    set_library(s,['Forest','Island','Swamp'])
    held=len(s.state.zones['p1:hand'])
    before=drawn(s)
    cast(s,'Transcendent Archaic',{'C':4,'U':1,'B':1,'G':1})
    settle(s)
    d=s.state.rules.decision
    assert d is not None and 'yes' in {o.id for o in d.options}
    act(s,d.player,type='choose',decision_id=d.id,option_ids=['yes'])
    settle(s)
    assert s.state.rules.decision is not None and 'decline' in {o.id for o in s.state.rules.decision.options}
    roundtrip(s)
    saved=tmp_path/'transcendent-abundance.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved,database,held,before=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
for _ in range(80):
    d=s.state.rules.decision
    if d is not None:
        ids={o.id for o in d.options}
        if 'decline' in ids:
            chosen=[next(o.id for o in d.options if o.id!='decline')]
        elif 'land' in ids:
            chosen=['land']
        elif d.kind=='order':
            chosen=[o.id for o in d.options]
        else:
            raise AssertionError('Unexpected decision '+d.prompt)
        s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':chosen})
    elif s.state.zones['stack']:
        s.perform(s.state.rules.priority,{'type':'pass_priority'})
    else:
        break
else:
    raise AssertionError('Unfinished draw replacement')
assert len(s.state.zones['p1:hand'])==int(held)+3
assert s.state.rules.turn_log.drew.get('p1',0)==int(before)
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),str(held),str(before)],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


def test_chandra_first_loyalty_ability_uses_native_stack_and_adds_red(cards):
    from tests.game_helpers import mana_pool

    s=game(cards)
    source=put(s,'Chandra, Dressed to Kill','battlefield')
    act(s,'p1',type='set_counter',card_id=source.id,kind='loyalty',value=3)
    ability=next(a.index for a in Plan(s.state,'p1',s.cards,None).ch(source).abilities if 'Add {R}' in a.text)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability,targets=['p2'],target_counts=[1],sources=[])
    answer(s)
    assert s.state.cards[source.id].counters['loyalty']==4
    assert mana_pool(s,'p1')=={'R':1} and s.state.players['p2'].life==39
    roundtrip(s)


def test_chandra_second_loyalty_ability_exiles_then_permits_red_card(cards):
    from tests.test_rules_abundance import set_library

    s=game(cards)
    source=put(s,'Chandra, Dressed to Kill','battlefield')
    act(s,'p1',type='set_counter',card_id=source.id,kind='loyalty',value=3)
    ids=set_library(s,['Lightning Bolt','Forest','Island'])
    ability=next(a.index for a in Plan(s.state,'p1',s.cards,None).ch(source).abilities if 'Exile the top card' in a.text)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability,sources=[])
    answer(s)
    assert s.state.cards[ids[0]].zone=='p1:exile'
    act(s,'p1',type='add_mana',player='p1',mana={'R':1})
    act(s,'p1',type='cast_spell',card_id=ids[0],targets=['p2'],sources=[])
    answer(s)
    assert s.state.cards[source.id].counters['loyalty']==4 and s.state.players['p2'].life==37
    roundtrip(s)


def test_chandra_ultimate_exile_permission_expires_after_this_turn(cards):
    from app.game.errors import ActionError

    s=game(cards)
    exiled=chandra_ultimate(s)
    to_phase(s,'upkeep',2)
    wait_priority(s,'p1')
    act(s,'p1',type='add_mana',player='p1',mana={'R':1})
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=exiled['Lightning Bolt'],targets=['p2'],sources=[])
    assert s.state.cards[exiled['Lightning Bolt']].zone=='p1:exile'
    roundtrip(s)


def test_tellah_delve_contributions_are_not_mana_spent(cards):
    s=game(cards)
    source=put(s,'Tellah, Great Sage','battlefield')
    discarded=[put(s,n,'graveyard') for n in ['Forest','Island','Mountain','Swamp','Plains','Sol Ring','Memnite']]
    before=drawn(s)
    cast(s,'Treasure Cruise',{'U':1},contributions=[{'kind':'delve','card':c.id} for c in discarded])
    answer(s)
    assert drawn(s)-before==3  # Cruise only: its printed mana value8 does not satisfy Tellah's4.
    assert s.state.cards[source.id].zone=='p1:battlefield' and s.state.players['p3'].life==40
    assert len(permanents(s,'Hero'))==1
    roundtrip(s)


def test_wurmquake_counts_only_other_players_at_three_or_more_poison(cards):
    s=game(cards)
    for p,n in [('p1',9),('p2',2),('p3',3)]:
        act(s,'p1',type='resource',player=p,key='poison',delta=n)
    cast(s,'Wurmquake',{'C':4,'G':2})
    answer(s)
    assert len(permanents(s,'Wurm'))==2
    roundtrip(s)


def test_tellah_actual_payment_and_source_lki_survive_cold_load_after_counter(cards,tmp_path):
    import subprocess
    import sys

    s=game(cards)
    source=put(s,'Tellah, Great Sage','battlefield')
    c=cast(s,'Volcanic Geyser',{'R':2,'C':7},['p2'],x_value=7)
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    counter=cast(s,'Counterspell',{'U':2},[c.id])
    for _ in range(15):
        if s.state.cards[counter.id].zone!='stack':
            break
        assert s.state.rules.decision is None
        act(s,s.state.rules.priority,type='pass_priority')
    assert s.state.cards[c.id].zone=='p1:graveyard' and s.state.zones['stack']
    roundtrip(s)
    before=drawn(s)
    saved=tmp_path/'tellah-countered.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved,database,before=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
for _ in range(30):
    if not s.state.zones['stack']:
        break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority,{'type':'pass_priority'})
else:
    raise AssertionError('Tellah did not finish')
assert s.state.players['p2'].life==31 and s.state.players['p3'].life==31
assert s.state.rules.turn_log.drew.get('p1',0)==int(before)+2
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),str(before)],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
