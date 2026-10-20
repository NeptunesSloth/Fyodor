"""Canonical suspended objects share exact counter operations and native suspend triggers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import casting, coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_remaining_talents import pay
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Taigam, Master Opportunist', 'Jhoira of the Ghitu', 'The Eleventh Doctor', 'The Parting of the Ways', 'Sinister Concierge', 'The Wedding of River Song', 'Ecstatic Beauty', 'Rory Williams', 'Curse of the Cabal']
EXTRA=['Rings of Brighthearth','Abundance','Memnite','Anointed Procession','Clockspinning','Suspend','Reverberate','Doubling Season','Hardened Scales','Counterspell','Disenchant','Shock','Solemnity','Rift Bolt','Doom Blade','Rest in Peace','Lightning Greaves','Hymn to Tourach','Raise the Alarm','Opt','Sol Ring','Grizzly Bears','Llanowar Elves','Forest']

@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/suspend_grant_followthrough_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='scf',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    ns=[*NAMES,*EXTRA]
    return table(cards,ns,ns,ns)


def suspend(s,name,pid='p1'):
    source=put(s,name,'hand',pid)
    ch=chars(s,source)
    ab=next(a.index for a in ch.abilities if 'suspend' in a.keywords)
    n,cost=casting.suspend_info(ch,ab)
    from app.rules import mana as M
    parsed=M.parse_cost(cost)
    pool={'C':parsed.generic}
    for color in parsed.colored:
        pool[color]=pool.get(color,0)+1
    mana(s,pid=pid,**pool)
    wait_priority(s,pid)
    act(s,pid,type='activate_ability',card_id=source.id,ability=ab,sources=[])
    assert s.state.cards[source.id].zone==f'{pid}:exile'
    assert s.state.cards[source.id].counters.get('time')==n
    return source


def choose(s,value):
    d=s.state.rules.decision
    assert d and value in {o.id for o in d.options},(d,value)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[value])
    settle(s)


def cast(s,name,target=None,pid='p1',**kwargs):
    source=put(s,name,'hand',pid)
    pay(s,pid,name)
    wait_priority(s,pid)
    act(s,pid,type='cast_spell',card_id=source.id,targets=[target] if target else [],sources=[],**kwargs)
    settle(s)
    return source


@pytest.mark.parametrize('name',NAMES)
def test_canonical_full(cards,name):
    result=coverage.of_card_data(cards.resolve(name))
    assert result.level=='FULL', result


def test_jhoira_actual_paid_hand_exile_and_four_counters(cards):
    s=game(cards)
    source=put(s,'Jhoira of the Ghitu','battlefield')
    bear=put(s,'Grizzly Bears','hand')
    mana(s,C=2)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,sources=[])
    d=s.state.rules.decision
    assert d
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:exile'
    assert s.state.cards[bear.id].counters['time']==4
    assert bear.id in s.state.rules.suspended
    roundtrip(s)


def test_ecstatic_actual_top_three_only_printed_suspend_gains_counters(cards):
    from tests.test_rules_abundance import set_library
    s=game(cards)
    set_library(s,['Rift Bolt','Grizzly Bears','Forest'])
    source=cast(s,'Ecstatic Beauty')
    exile=[c for c in s.state.cards.values() if c.zone=='p1:exile']
    assert {c.name for c in exile}=={'Rift Bolt','Grizzly Bears','Forest'}
    bolt=next(c for c in exile if c.name=='Rift Bolt')
    bear=next(c for c in exile if c.name=='Grizzly Bears')
    assert bolt.counters['time']==4
    assert not bear.counters.get('time')
    assert bear.id not in s.state.rules.suspended
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_rory_actual_cast_exiles_original_and_investigates(cards):
    s=game(cards)
    source=cast(s,'Rory Williams')
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.cards[source.id].counters['time']==3
    assert source.id in s.state.rules.suspended
    assert any(c.name=='Clue' and c.zone=='p1:battlefield' for c in s.state.cards.values())
    roundtrip(s)


def test_taigam_second_spell_copy_hits_once_original_suspended(cards):
    s=game(cards)
    put(s,'Taigam, Master Opportunist','battlefield')
    cast(s,'Sol Ring')
    before=s.state.players['p2'].life
    source=cast(s,'Shock','p2')
    assert s.state.players['p2'].life==before-2
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.cards[source.id].counters['time']==4
    roundtrip(s)


def test_sinister_actual_death_exiles_source_and_target(cards):
    s=game(cards)
    source=put(s,'Sinister Concierge','battlefield')
    bear=put(s,'Grizzly Bears','battlefield','p2')
    cast(s,'Shock',source.id)
    d=s.state.rules.decision
    assert d
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear.id])
    settle(s)
    choose(s,'yes')
    for cid,pid in [(source.id,'p1'),(bear.id,'p2')]:
        assert s.state.cards[cid].zone==f'{pid}:exile'
        assert s.state.cards[cid].counters['time']==3
        assert cid in s.state.rules.suspended
    roundtrip(s)


def test_parting_actual_chapter_one_exiles_five_nonland_amounts(cards):
    from tests.test_rules_abundance import set_library
    s=game(cards)
    names=['Forest','Grizzly Bears','Rift Bolt','Sol Ring','Shock']
    ids=set_library(s,names)
    cast(s,'The Parting of the Ways')
    for cid,name,amount in zip(ids,names,[0,2,3,1,1],strict=True):
        c=s.state.cards[cid]
        assert c.zone=='p1:exile'
        assert c.counters.get('time',0)==amount
        assert (cid in s.state.rules.suspended)==(name!='Forest')
    roundtrip(s)


def test_eleventh_actual_combat_optional_hand_exile(cards):
    s=game(cards)
    doctor=put(s,'The Eleventh Doctor','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    bear=put(s,'Grizzly Bears','hand')
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':doctor.id,'target':'p2'}])
    to_phase(s,'combat_damage')
    settle(s)
    choose(s,'pay')
    d=s.state.rules.decision
    assert d
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:exile'
    assert s.state.cards[bear.id].counters['time']==2
    roundtrip(s)


def test_wedding_both_players_draw_then_optional_exile(cards):
    s=game(cards)
    first=put(s,'Grizzly Bears','hand')
    second=put(s,'Sol Ring','hand','p2')
    hands={p:len(s.state.zones[f'{p}:hand']) for p in ['p1','p2']}
    cast(s,'The Wedding of River Song','p2')
    choose(s,'pay')
    d=s.state.rules.decision
    assert d and d.player=='p1'
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[first.id])
    settle(s)
    assert len(s.state.zones['p2:hand'])==hands['p2']+2
    choose(s,'pay')
    d=s.state.rules.decision
    assert d and d.player=='p2'
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[second.id])
    settle(s)
    assert s.state.cards[first.id].counters['time']==2
    assert s.state.cards[second.id].counters['time']==1
    assert first.id in s.state.rules.suspended and second.id in s.state.rules.suspended
    # Time travel is a separate optional native instruction after both sequences.
    roundtrip(s)


def test_curse_opponent_upkeep_may_sacrifice_to_add_two(cards):
    s=game(cards)
    source=suspend(s,'Curse of the Cabal')
    bear=put(s,'Grizzly Bears','battlefield','p2')
    to_phase(s,'upkeep',turn=2)
    settle(s)
    d=s.state.rules.decision
    assert d and d.player=='p2'
    choose(s,'pay')
    d=s.state.rules.decision
    if d:
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear.id])
        settle(s)
    assert s.state.cards[bear.id].zone=='p2:graveyard'
    assert s.state.cards[source.id].counters['time']==4
    roundtrip(s)


def test_taigam_countered_original_uses_spell_lki_without_exiling_graveyard(cards):
    s=game(cards)
    put(s,'Taigam, Master Opportunist','battlefield')
    cast(s,'Sol Ring')
    source=put(s,'Shock','hand')
    mana(s,R=1)
    wait_priority(s,'p1')
    act(s,'p1',type='cast_spell',card_id=source.id,targets=['p3'],sources=[])
    counter=put(s,'Counterspell','hand','p2')
    mana(s,pid='p2',U=2)
    wait_priority(s,'p2')
    act(s,'p2',type='cast_spell',card_id=counter.id,targets=[source.id],sources=[])
    settle(s)
    assert s.state.players['p3'].life==38
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert not s.state.cards[source.id].counters.get('time')
    assert source.id not in s.state.rules.suspended
    assert s.state.rules.decision is None
    roundtrip(s)


def test_jhoira_paid_object_excludes_new_incarnation(cards):
    s=game(cards)
    source=put(s,'Jhoira of the Ghitu','battlefield')
    bear=put(s,'Grizzly Bears','hand')
    mana(s,C=2)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,sources=[])
    d=s.state.rules.decision
    assert d
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear.id])
    assert s.state.cards[bear.id].zone=='p1:exile'
    act(s,'p1',type='move',card_ids=[bear.id],to={'player':'p1','zone':'graveyard'})
    act(s,'p1',type='move',card_ids=[bear.id],to={'player':'p1','zone':'exile'})
    settle(s)
    assert s.state.cards[bear.id].counters.get('time',0)==0
    assert bear.id not in s.state.rules.suspended
    roundtrip(s)


@pytest.mark.parametrize('name',['Forest','Grizzly Bears'])
def test_eleventh_can_exile_land_at_zero_or_decline(cards,name):
    s=game(cards)
    doctor=put(s,'The Eleventh Doctor','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    chosen=put(s,name,'hand')
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':doctor.id,'target':'p2'}])
    to_phase(s,'combat_damage')
    settle(s)
    if name=='Grizzly Bears':
        choose(s,'decline')
        assert s.state.cards[chosen.id].zone=='p1:hand'
        assert chosen.id not in s.state.rules.suspended
    else:
        choose(s,'pay')
        d=s.state.rules.decision
        if d:
            act(s,d.player,type='choose',decision_id=d.id,option_ids=[chosen.id])
            settle(s)
        assert s.state.cards[chosen.id].zone=='p1:exile'
        assert chosen.id in s.state.rules.suspended
        assert not s.state.cards[chosen.id].counters.get('time')
        assert s.state.rules.decision is None
    roundtrip(s)


def test_rory_last_counter_cast_from_exile_does_not_repeat_cast_trigger(cards):
    s=game(cards)
    source=cast(s,'Rory Williams')
    act(s,'p1',type='set_counter',card_id=source.id,kind='time',value=1)
    cast(s,'Clockspinning',source.id)
    choose(s,'time')
    choose(s,'remove')
    choose(s,'yes')
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert source.id not in s.state.rules.suspended
    assert sum(c.name=='Clue' and c.zone=='p1:battlefield' for c in s.state.cards.values())==1
    assert 'haste' in chars(s,s.state.cards[source.id]).keywords
    roundtrip(s)


def test_sinister_can_exile_itself_with_no_target_and_decline(cards):
    s=game(cards)
    source=put(s,'Sinister Concierge','battlefield')
    cast(s,'Shock',source.id)
    d=s.state.rules.decision
    assert d
    if d.resume.get('step')!='suspend_departed_source':
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[])
        settle(s)
    choose(s,'no')
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert source.id not in s.state.rules.suspended
    roundtrip(s)


@pytest.mark.parametrize('stage',['jhoira','sinister','wedding'])
def test_native_choices_resume_in_fresh_process(cards,tmp_path,stage):
    import subprocess
    import sys
    s=game(cards)
    target=put(s,'Grizzly Bears','hand')
    if stage=='jhoira':
        source=put(s,'Jhoira of the Ghitu','battlefield')
        mana(s,C=2)
        act(s,'p1',type='activate_ability',card_id=source.id,ability=0,sources=[])
    elif stage=='sinister':
        source=put(s,'Sinister Concierge','battlefield')
        target=put(s,'Grizzly Bears','battlefield','p2')
        cast(s,'Shock',source.id)
        d=s.state.rules.decision
        assert d
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[target.id])
        settle(s)
    else:
        cast(s,'The Wedding of River Song','p2')
    assert s.state.rules.decision
    saved=tmp_path/f'{stage}.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
save,db,target,stage=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
for _ in range(40):
 d=s.state.rules.decision
 if d:
  options={o.id for o in d.options}
  pick='yes' if 'yes' in options else 'pay' if stage=='wedding' and d.player=='p1' and 'pay' in options else target if target in options else 'decline' if 'decline' in options else d.options[0].id
  s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[pick]})
 elif s.state.zones['stack']:
  s.perform(s.state.rules.priority,{'type':'pass_priority'})
 else:break
else:raise AssertionError('did not finish')
assert s.state.cards[target].zone.endswith(':exile')
assert s.state.cards[target].counters['time'] in (2,3,4)
assert target in s.state.rules.suspended
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),target.id,stage],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


def test_jhoira_rings_copy_adds_four_again_to_same_paid_card(cards):
    s=game(cards)
    put(s,'Rings of Brighthearth','battlefield')
    source=put(s,'Jhoira of the Ghitu','battlefield')
    bear=put(s,'Grizzly Bears','hand')
    mana(s,C=4)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=0,sources=[])
    d=s.state.rules.decision
    assert d
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear.id])
    settle(s)
    choose(s,'pay')
    assert s.state.cards[bear.id].counters['time']==8
    assert s.state.rules.decision is None
    roundtrip(s)


def test_taigam_permanent_copy_is_one_token_not_doubled(cards):
    s=game(cards)
    put(s,'Taigam, Master Opportunist','battlefield')
    put(s,'Anointed Procession','battlefield')
    cast(s,'Sol Ring')
    source=cast(s,'Grizzly Bears')
    copies=[c for c in s.state.cards.values() if c.name=='Grizzly Bears' and c.is_token and c.zone=='p1:battlefield']
    assert len(copies)==1
    assert s.state.cards[source.id].zone=='p1:exile'
    roundtrip(s)


def test_wedding_zero_mana_value_nonland_gains_suspend_without_time(cards):
    s=game(cards)
    target=put(s,'Memnite','hand')
    cast(s,'The Wedding of River Song','p2')
    choose(s,'pay')
    d=s.state.rules.decision
    assert d
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[target.id])
    settle(s)
    choose(s,'decline')
    assert s.state.cards[target.id].zone=='p1:exile'
    assert not s.state.cards[target.id].counters.get('time')
    assert target.id in s.state.rules.suspended
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('change',['source','target'])
def test_sinister_original_source_or_only_target_new_incarnation_excluded(cards,change):
    s=game(cards)
    source=put(s,'Sinister Concierge','battlefield')
    bear=put(s,'Grizzly Bears','battlefield','p2')
    cast(s,'Shock',source.id)
    d=s.state.rules.decision
    assert d
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear.id])
    moved=source if change=='source' else bear
    pid='p1' if change=='source' else 'p2'
    original='graveyard' if change=='source' else 'battlefield'
    act(s,pid,type='move',card_ids=[moved.id],to={'player':pid,'zone':'hand'})
    act(s,pid,type='move',card_ids=[moved.id],to={'player':pid,'zone':original})
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.cards[bear.id].zone=='p2:battlefield'
    assert source.id not in s.state.rules.suspended and bear.id not in s.state.rules.suspended
    roundtrip(s)


def test_curse_has_no_upkeep_trigger_outside_exile_or_at_zero_time(cards):
    s=game(cards)
    source=suspend(s,'Curse of the Cabal')
    act(s,'p1',type='set_counter',card_id=source.id,kind='time',value=0)
    put(s,'Grizzly Bears','battlefield','p2')
    to_phase(s,'upkeep',turn=2)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].counters.get('time',0)==0
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    to_phase(s,'upkeep',turn=3)
    settle(s)
    assert s.state.rules.decision is None
    roundtrip(s)


def test_stolen_sinister_uses_death_controller_but_original_owner_exile(cards):
    s=game(cards)
    source=put(s,'Sinister Concierge','battlefield')
    bear=put(s,'Grizzly Bears','battlefield','p3')
    act(s,'p1',type='set_controller',card_ids=[source.id],player='p2')
    cast(s,'Shock',source.id)
    d=s.state.rules.decision
    assert d and d.player=='p2'
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear.id])
    settle(s)
    assert s.state.rules.decision.player=='p2'
    choose(s,'yes')
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.cards[source.id].counters['time']==3
    assert s.state.cards[bear.id].zone=='p3:exile'
    roundtrip(s)


def test_wedding_abundance_replacement_resumes_each_draw_then_optional_tail(cards):
    from tests.test_rules_abundance import set_library
    s=game(cards)
    put(s,'Abundance','battlefield')
    set_library(s,['Forest','Grizzly Bears','Sol Ring','Shock'])
    source=cast(s,'The Wedding of River Song','p2')
    for _ in range(10):
        d=s.state.rules.decision
        assert d
        if d.resume.get('step')=='pay_or_sacrifice':
            break
        options={o.id for o in d.options}
        pick='nonland' if 'nonland' in options else next(o.id for o in d.options if o.id!='decline')
        choose(s,pick)
    else:
        pytest.fail('draw replacement failed to reach optional hand exile')
    choose(s,'decline')
    d=s.state.rules.decision
    assert d and d.player=='p2'
    choose(s,'decline')
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_ecstatic_native_exile_play_requires_normal_cost_and_gives_no_suspend_haste(cards):
    from tests.test_rules_abundance import set_library
    s=game(cards)
    ids=set_library(s,['Grizzly Bears','Forest','Rift Bolt'])
    cast(s,'Ecstatic Beauty')
    bear=s.state.cards[ids[0]]
    act(s,'p1',type='play_land',card_id=ids[1])
    assert s.state.cards[ids[1]].zone=='p1:battlefield'
    pay(s,'p1','Grizzly Bears')
    wait_priority(s,'p1')
    act(s,'p1',type='cast_spell',card_id=bear.id,sources=[])
    settle(s)
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    assert 'haste' not in chars(s,s.state.cards[bear.id]).keywords
    roundtrip(s)
