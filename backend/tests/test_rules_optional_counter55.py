"""Actual optional source counters pay before reflexive target selection."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import attack, damage
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Slumbering Walker','Leatherhead, Swamp Stalker']


@pytest.fixture
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/optional_counter55_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='oc55',number=str(i),**{k:v for k,v in c.items() if k not in ('name','set_code')})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards,name):
    names=[*NAMES,'Grizzly Bears','Sol Ring','Pacifism','Lightning Bolt','Forest','Fear of Sleep Paralysis']
    s=table(cards,names,names,names)
    to_phase(s,'main1',1)
    source=put(s,name,'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'G':10,'W':10,'C':10})
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    return s,source


def answer(s,ids):
    d=s.state.rules.decision
    assert d is not None
    act(s,d.player,type='choose',decision_id=d.id,option_ids=ids)
    settle(s)


def test_walker_actual_entry_counters_pay_before_reanimation_target(cards):
    s,source=setup(cards,'Slumbering Walker')
    assert source.counters=={'-1/-1':2} and Plan(s.state,'p1',cards,None).ch(source).pt==(2,5)
    target=put(s,'Grizzly Bears','graveyard')
    to_phase(s,'end',1)
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.resume.get('opt') and target.zone=='p1:graveyard'
    answer(s,['pay'])
    assert source.counters=={'-1/-1':1} and target.zone=='p1:graveyard'
    d=s.state.rules.decision
    assert d is not None and d.resume.get('step')=='trigger_target'
    answer(s,[target.id])
    assert target.zone=='p1:battlefield' and Plan(s.state,'p1',cards,None).ch(source).pt==(3,6)
    roundtrip(s)


def test_leatherhead_actual_trample_then_reflexive_damaged_player_target_only(cards):
    s,source=setup(cards,'Leatherhead, Swamp Stalker')
    assert source.counters=={'hexproof':1} and 'hexproof' in Plan(s.state,'p1',cards,None).ch(source).keywords
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import wait_priority
    bolt=put(s,'Lightning Bolt','hand','p2')
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'R':1})
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p2',type='cast_spell',card_id=bolt.id,targets=[source.id],sources=[])
    assert s.state.model_dump_json()==before
    target=put(s,'Sol Ring','battlefield','p2')
    unrelated=put(s,'Sol Ring','battlefield','p3')
    blocker=put(s,'Grizzly Bears','battlefield','p2')
    attack(s,[source],turn=4)
    to_phase(s,'declare_blockers')
    act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':blocker.id,'attacker_id':source.id}])
    settle(s)
    damage(s)
    d=s.state.rules.decision
    if d is not None and d.resume.get('step')=='block_split':
        act(s,d.player,type='choose',decision_id=d.id,amounts=[2 if o.id==blocker.id else 3 for o in d.options])
        settle(s)
    assert blocker.zone=='p2:graveyard' and s.state.players['p2'].life==37
    d=s.state.rules.decision
    assert d is not None and d.resume.get('opt')
    answer(s,['pay'])
    assert not source.counters and 'hexproof' not in Plan(s.state,'p1',cards,None).ch(source).keywords
    d=s.state.rules.decision
    assert d is not None and target.id in [o.id for o in d.options]
    assert unrelated.id not in [o.id for o in d.options]
    answer(s,[target.id])
    assert target.zone=='p2:graveyard' and unrelated.zone=='p3:battlefield'
    wait_priority(s,'p2')
    act(s,'p2',type='add_mana',player='p2',mana={'R':1})
    act(s,'p2',type='cast_spell',card_id=bolt.id,targets=[source.id],sources=[])
    settle(s)
    assert source.zone=='p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('kind',['-1/-1','shield'])
def test_mixed_counter_kind_is_chosen_and_paid_once_before_reanimation(cards,kind):
    s,source=setup(cards,'Slumbering Walker')
    target=put(s,'Grizzly Bears','graveyard')
    act(s,'p1',type='counter',card_ids=[source.id],kind='shield',delta=1)
    to_phase(s,'end',1)
    settle(s)
    answer(s,['pay'])
    d=s.state.rules.decision
    assert d is not None and d.resume.get('counter_pick55') and source.counters=={'-1/-1':2,'shield':1}
    chosen=next(o.id for o in d.options if o.label.startswith(kind+' counter'))
    answer(s,[chosen])
    assert source.counters.get(kind,0)==(1 if kind=='-1/-1' else 0)
    assert target.zone=='p1:graveyard'
    answer(s,[target.id])
    assert target.zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('where',['offer','counter_choice'])
def test_decline_does_not_remove_counter_or_create_reflexive_target(cards,where):
    s,source=setup(cards,'Slumbering Walker')
    target=put(s,'Grizzly Bears','graveyard')
    act(s,'p1',type='counter',card_ids=[source.id],kind='shield',delta=1)
    to_phase(s,'end',1)
    settle(s)
    if where=='offer':
        answer(s,['decline'])
    else:
        answer(s,['pay'])
        assert s.state.rules.decision.resume.get('counter_pick55')
        answer(s,[])
    assert source.counters=={'-1/-1':2,'shield':1}
    assert target.zone=='p1:graveyard' and s.state.rules.decision is None
    roundtrip(s)


def test_no_counters_cannot_pay_and_does_not_choose_target(cards):
    s,source=setup(cards,'Slumbering Walker')
    target=put(s,'Grizzly Bears','graveyard')
    act(s,'p1',type='counter',card_ids=[source.id],kind='-1/-1',delta=-2)
    to_phase(s,'end',1)
    settle(s)
    assert s.state.rules.decision is None and target.zone=='p1:graveyard'
    roundtrip(s)


def test_counter_choice_from_other_permanent_is_rejected_atomically(cards):
    from app.game.errors import ActionError
    from app.rules import cost_payment
    s,source=setup(cards,'Slumbering Walker')
    put(s,'Grizzly Bears','graveyard')
    other=put(s,'Sol Ring','battlefield')
    act(s,'p1',type='counter',card_ids=[source.id],kind='shield',delta=1)
    act(s,'p1',type='counter',card_ids=[other.id],kind='charge',delta=1)
    to_phase(s,'end',1)
    settle(s)
    answer(s,['pay'])
    d=s.state.rules.decision
    token=next(iter(cost_payment.counter_tokens(Plan(s.state,'p1',cards,None),[other.id])))
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[token])
    assert s.state.model_dump_json()==before
    answer(s,[])
    roundtrip(s)


def test_trigger_cannot_pay_with_new_source_incarnation(cards):
    s,source=setup(cards,'Slumbering Walker')
    target=put(s,'Grizzly Bears','graveyard')
    act(s,'p1',type='set_prefs',hold_priority=True)
    to_phase(s,'end',1)
    assert s.state.zones.get('stack')
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'exile'})
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'battlefield'})
    if not source.counters:
        act(s,'p1',type='counter',card_ids=[source.id],kind='-1/-1',delta=2)
    settle(s)
    assert s.state.rules.decision is None and target.zone=='p1:graveyard' and source.counters
    roundtrip(s)


def test_return_target_must_have_current_power_two_or_less_and_be_in_own_graveyard(cards):
    s,source=setup(cards,'Slumbering Walker')
    target=put(s,'Grizzly Bears','graveyard')
    big=put(s,'Leatherhead, Swamp Stalker','graveyard')
    other=put(s,'Grizzly Bears','graveyard','p2')
    to_phase(s,'end',1)
    settle(s)
    answer(s,['pay'])
    d=s.state.rules.decision
    ids=[o.id for o in d.options]
    assert target.id in ids and big.id not in ids and other.id not in ids
    answer(s,[target.id])
    roundtrip(s)


@pytest.mark.parametrize('which',['source','target'])
def test_paid_reflexive_does_not_require_source_but_tracks_original_target_incarnation(cards,which):
    s,source=setup(cards,'Slumbering Walker')
    target=put(s,'Grizzly Bears','graveyard')
    to_phase(s,'end',1)
    settle(s)
    answer(s,['pay'])
    act(s,'p1',type='set_prefs',hold_priority=True)
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[target.id])
    victim=source if which=='source' else target
    act(s,'p1',type='move',card_ids=[victim.id],to={'player':'p1','zone':'exile'})
    if which=='target':
        act(s,'p1',type='move',card_ids=[target.id],to={'player':'p1','zone':'graveyard'})
    settle(s)
    assert target.zone==('p1:battlefield' if which=='source' else 'p1:graveyard')
    assert source.counters.get('-1/-1',0)==(0 if which=='source' else 1)
    roundtrip(s)


@pytest.mark.parametrize('shield',[False,True])
def test_nonremovable_stun_counter_is_never_available_to_pay(cards,shield):
    s,source=setup(cards,'Slumbering Walker')
    target=put(s,'Grizzly Bears','graveyard')
    act(s,'p1',type='counter',card_ids=[source.id],kind='-1/-1',delta=-2)
    put(s,'Fear of Sleep Paralysis','battlefield','p2')
    settle(s)
    if s.state.rules.decision is not None:
        answer(s,[])
    act(s,'p1',type='counter',card_ids=[source.id],kind='stun',delta=1)
    if shield:
        act(s,'p1',type='counter',card_ids=[source.id],kind='shield',delta=1)
    to_phase(s,'end',1)
    settle(s)
    if shield:
        answer(s,['pay'])
        assert source.counters=={'stun':1}
        answer(s,[target.id])
        assert target.zone=='p1:battlefield'
    else:
        assert s.state.rules.decision is None and target.zone=='p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name',NAMES)
def test_true_cold_choice_of_any_counter_then_reflexive_target(cards,tmp_path,name):
    import subprocess
    import sys
    s,source=setup(cards,name)
    act(s,'p1',type='counter',card_ids=[source.id],kind='shield',delta=1)
    if name=='Slumbering Walker':
        target=put(s,'Grizzly Bears','graveyard')
        unrelated=put(s,'Grizzly Bears','graveyard','p2')
        to_phase(s,'end',1)
        settle(s)
    else:
        target=put(s,'Sol Ring','battlefield','p2')
        unrelated=put(s,'Sol Ring','battlefield','p3')
        attack(s,[source],turn=4)
        damage(s)
    answer(s,['pay'])
    assert s.state.rules.decision.resume.get('counter_pick55')
    saved=tmp_path/'counter-choice.json'
    saved.write_text(s.state.model_dump_json())
    code=r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_placements import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
name,source,target,unrelated=sys.argv[3:7]
d=s.state.rules.decision
assert d.resume.get('counter_pick55')
token=next(o.id for o in d.options if o.label.startswith('shield counter'))
act(s,d.player,type='choose',decision_id=d.id,option_ids=[token])
settle(s)
assert not s.state.cards[source].counters.get('shield',0)
assert s.state.cards[source].counters.get('-1/-1' if name=='Slumbering Walker' else 'hexproof',0)==(2 if name=='Slumbering Walker' else 1)
d=s.state.rules.decision
assert d is not None and target in [o.id for o in d.options] and unrelated not in [o.id for o in d.options]
act(s,d.player,type='choose',decision_id=d.id,option_ids=[target])
settle(s)
assert s.state.cards[target].zone==('p1:battlefield' if name=='Slumbering Walker' else 'p2:graveyard')
roundtrip(s)
repo.close()
"""
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),name,source.id,target.id,unrelated.id],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('name',NAMES)
def test_complete_canonical(cards,name):
    from app.rules import coverage
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def test_leatherhead_decline_preserves_hexproof_and_does_not_destroy(cards):
    s,source=setup(cards,'Leatherhead, Swamp Stalker')
    target=put(s,'Sol Ring','battlefield','p2')
    attack(s,[source],turn=4)
    damage(s)
    answer(s,['decline'])
    assert source.counters=={'hexproof':1} and target.zone=='p2:battlefield'
    assert s.state.rules.decision is None
    roundtrip(s)
