"""Canonical untargeted counter distributions are allocated at resolution."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_remaining_talents import pay
from tests.test_rules_shared_damage_choices import table

NAMES=['Vastwood Hydra','Feast of the Victorious Dead','Invoke Justice','Stumpsquall Hydra','Blessing of Frost']


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/counter_distribution_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='ucd',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=[*NAMES,'Grizzly Bears','Doubling Season','Hardened Scales','Solemnity','Vorinclex, Monstrous Raider','Shock','Snow-Covered Forest','Snow-Covered Island','Forest',"Smuggler's Copter",'Reverberate','Shalai, Voice of Plenty',"Black Sun's Zenith",'Protean Hydra','Arcbound Worker','Phyrexian Triniform']
    return table(cards,names,names,names)


def cast(s,name,*,x=None,targets=None,sources=None,auto_pay=True):
    c=put(s,name,'hand')
    if auto_pay:
        pay(s,'p1',name)
        if x:
            act(s,'p1',type='add_mana',mana={'C':x})
    args={'x_value':x} if x is not None else {}
    if targets is not None:
        args['targets']=targets
        if len(targets)>1:
            args['target_counts']=[1]*len(targets)
    act(s,'p1',type='cast_spell',card_id=c.id,sources=sources or [],**args)
    settle(s)
    return c


def choose(s,value):
    d=s.state.rules.decision
    assert d and value in {o.id for o in d.options}, (d.kind if d else None,d.prompt if d else None,value)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[value])
    settle(s)


def finish_recipients(s):
    d=s.state.rules.decision
    if d is not None and d.resume.get('stage')=='recipients':
        choose(s,'done')
    else:
        assert d is None or d.resume.get('stage')=='amount'


def number(s,n):
    d=s.state.rules.decision
    assert d and d.resume['step']=='distribute_counters_resolving' and d.resume['stage']=='amount'
    act(s,d.player,type='choose',decision_id=d.id,name=str(n))
    settle(s)


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def test_hydra_actual_x_cast_death_lki_not_current_graveyard_counters(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    b=put(s,'Shalai, Voice of Plenty','battlefield')
    source=cast(s,'Vastwood Hydra',x=2)
    assert s.state.cards[source.id].counters=={'+1/+1':2}
    cast(s,'Shock',targets=[source.id])
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert not s.state.cards[source.id].counters
    choose(s,a.id)
    choose(s,b.id)
    assert s.state.cards[a.id].counters=={'+1/+1':1}
    assert s.state.cards[b.id].counters=={'+1/+1':1}
    roundtrip(s)


def test_stumpsquall_distribution_source_and_opponents_commander(cards):
    s=game(cards)
    opponent=put(s,"Atraxa, Praetors' Voice",'battlefield','p2')
    source=cast(s,'Stumpsquall Hydra',x=5)
    choose(s,source.id)
    choose(s,opponent.id)
    finish_recipients(s)
    number(s,2)
    assert s.state.cards[source.id].counters=={'+1/+1':2}
    assert s.state.cards[opponent.id].counters=={'+1/+1':3}
    roundtrip(s)


def test_stumpsquall_x_zero_has_no_allocation(cards):
    s=game(cards)
    source=cast(s,'Stumpsquall Hydra',x=0)
    assert not s.state.rules.decision
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert not s.state.cards[source.id].counters
    roundtrip(s)


def test_nonzero_any_number_may_choose_zero_recipients(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    cast(s,'Stumpsquall Hydra',x=4)
    finish_recipients(s)
    assert not s.state.cards[a.id].counters
    assert not s.state.rules.decision
    roundtrip(s)


def test_invoke_actual_return_recipient_chosen_after_new_object_enters(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','graveyard')
    cast(s,'Invoke Justice',targets=[a.id,'p1'])
    assert s.state.cards[a.id].zone=='p1:battlefield'
    choose(s,a.id)
    finish_recipients(s)
    assert s.state.cards[a.id].counters=={'+1/+1':4}
    roundtrip(s)


def test_invoke_target_other_player_noncreature_vehicle_is_recipient(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','graveyard')
    vehicle=put(s,"Smuggler's Copter",'battlefield','p2')
    cast(s,'Invoke Justice',targets=[a.id,'p2'])
    d=s.state.rules.decision
    assert d and a.id not in {o.id for o in d.options}
    choose(s,vehicle.id)
    finish_recipients(s)
    assert s.state.cards[vehicle.id].counters=={'+1/+1':4}
    assert not s.state.cards[a.id].counters
    roundtrip(s)


def test_blessing_no_snow_still_draws_for_already_large_creatures(cards):
    s=game(cards)
    put(s,'Shalai, Voice of Plenty','battlefield')
    a=put(s,'Grizzly Bears','battlefield')
    act(s,'p1',type='set_counter',card_id=a.id,kind='+1/+1',value=2)
    before=len(s.state.zones['p1:hand'])
    cast(s,'Blessing of Frost')
    assert not s.state.rules.decision
    assert len(s.state.zones['p1:hand'])==before+1
    assert s.state.cards[a.id].counters=={'+1/+1':2}
    roundtrip(s)


def test_blessing_actual_snow_sources_counts_snow_spent_and_draws_after_counters(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    forest=put(s,'Snow-Covered Forest','battlefield')
    island=put(s,'Snow-Covered Island','battlefield')
    act(s,'p1',type='add_mana',mana={'G':1,'C':1})
    before=len(s.state.zones['p1:hand'])
    cast(s,'Blessing of Frost',sources=[forest.id,island.id],auto_pay=False)
    choose(s,a.id)
    finish_recipients(s)
    assert s.state.cards[a.id].counters=={'+1/+1':2}
    assert len(s.state.zones['p1:hand'])==before+1
    roundtrip(s)


def test_feast_counts_creatures_of_each_controller_and_gains_same_amount(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s=game(cards)
    put(s,'Feast of the Victorious Dead','battlefield')
    a=put(s,'Grizzly Bears','battlefield')
    b=put(s,'Grizzly Bears','battlefield','p2')
    recipient=put(s,'Shalai, Voice of Plenty','battlefield')
    cast(s,'Shock',targets=[a.id])
    cast(s,'Shock',targets=[b.id])
    before=s.state.players['p1'].life
    to_phase(s,'end')
    settle(s)
    assert s.state.players['p1'].life==before+2
    choose(s,recipient.id)
    finish_recipients(s)
    assert s.state.cards[recipient.id].counters=={'+1/+1':2}
    roundtrip(s)


def test_feast_intervening_if_no_deaths_never_triggers(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s=game(cards)
    put(s,'Feast of the Victorious Dead','battlefield')
    put(s,'Grizzly Bears','battlefield')
    before=s.state.players['p1'].life
    to_phase(s,'end')
    settle(s)
    assert not s.state.rules.decision
    assert s.state.players['p1'].life==before
    roundtrip(s)


def test_impossible_counter_recipients_not_offered(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    put(s,'Solemnity','battlefield')
    cast(s,'Stumpsquall Hydra',x=3)
    assert not s.state.rules.decision
    assert not s.state.cards[a.id].counters
    roundtrip(s)


def test_nonempty_selection_must_allocate_entire_total_without_zero_shares(cards):
    from app.game.errors import ActionError
    s=game(cards)
    a=put(s,'Grizzly Bears','graveyard')
    b=put(s,'Shalai, Voice of Plenty','battlefield')
    cast(s,'Invoke Justice',targets=[a.id,'p1'])
    choose(s,a.id)
    choose(s,b.id)
    finish_recipients(s)
    before=s.state.model_dump(mode='json')
    for n in (0,4):
        with pytest.raises(ActionError):
            number(s,n)
        assert s.state.model_dump(mode='json')==before
    number(s,1)
    assert s.state.cards[a.id].counters=={'+1/+1':1}
    assert s.state.cards[b.id].counters=={'+1/+1':3}
    roundtrip(s)


def test_native_replacement_pause_preserves_original_allocations(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','graveyard')
    b=put(s,'Shalai, Voice of Plenty','battlefield')
    put(s,'Doubling Season','battlefield')
    put(s,'Hardened Scales','battlefield')
    cast(s,'Invoke Justice',targets=[a.id,'p1'])
    choose(s,a.id)
    choose(s,b.id)
    finish_recipients(s)
    number(s,1)
    assert not s.state.cards[a.id].counters and not s.state.cards[b.id].counters
    count=0
    while s.state.rules.decision:
        d=s.state.rules.decision
        assert d.resume['step']=='replace_order'
        roundtrip(s)
        choose(s,d.options[0].id)
        count+=1
    assert count>=2
    assert s.state.cards[a.id].counters['+1/+1'] in (3,4)
    assert s.state.cards[b.id].counters['+1/+1'] in (7,8)
    roundtrip(s)


def test_saved_recipient_and_amount_choices_resume_in_new_process(cards,tmp_path):
    import subprocess
    import sys
    s=game(cards)
    a=put(s,'Grizzly Bears','graveyard')
    b=put(s,'Shalai, Voice of Plenty','battlefield')
    cast(s,'Invoke Justice',targets=[a.id,'p1'])
    choose(s,a.id)
    saved=tmp_path/'distribution.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
save,db,a,b=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
assert d.resume['stage']=='recipients'
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[b]})
d=s.state.rules.decision
assert d.resume['stage']=='amount'
s=GameSession(GameState.model_validate_json(s.state.model_dump_json()),cards=repo)
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'name':'1'})
assert s.state.cards[a].counters=={'+1/+1':1}
assert s.state.cards[b].counters=={'+1/+1':3}
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),a.id,b.id],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


def test_selected_blinked_object_does_not_receive_previous_objects_allocation(cards):
    s=game(cards)
    a=put(s,'Grizzly Bears','graveyard')
    b=put(s,'Shalai, Voice of Plenty','battlefield')
    cast(s,'Invoke Justice',targets=[a.id,'p1'])
    choose(s,a.id)
    choose(s,b.id)
    finish_recipients(s)
    put(s,'Grizzly Bears','hand')
    put(s,'Grizzly Bears','battlefield')
    number(s,1)
    assert not s.state.cards[a.id].counters
    assert s.state.cards[b.id].counters=={'+1/+1':3}
    roundtrip(s)


def test_distribution_amounts_are_typed_without_small_option_cap(cards):
    s=game(cards)
    opponent=put(s,"Atraxa, Praetors' Voice",'battlefield','p2')
    source=cast(s,'Stumpsquall Hydra',x=99)
    choose(s,source.id)
    choose(s,opponent.id)
    finish_recipients(s)
    number(s,73)
    assert s.state.cards[source.id].counters=={'+1/+1':73}
    assert s.state.cards[opponent.id].counters=={'+1/+1':26}
    roundtrip(s)


def test_hydra_lethal_minus_counters_reads_pre_sba_cancellation_plus_counters(cards):
    s=game(cards)
    recipient=put(s,'Shalai, Voice of Plenty','battlefield')
    source=cast(s,'Vastwood Hydra',x=2)
    cast(s,"Black Sun's Zenith",x=3)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.cards[recipient.id].counters=={'-1/-1':3}
    choose(s,recipient.id)
    finish_recipients(s)
    # Two +1/+1 counters were present when Hydra died, despite simultaneous cancellation SBA.
    assert s.state.cards[recipient.id].counters=={'-1/-1':1}
    roundtrip(s)


def test_blessing_spell_copy_has_no_snow_spent_and_original_keeps_actual_two(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s=game(cards)
    a=put(s,'Grizzly Bears','battlefield')
    forest=put(s,'Snow-Covered Forest','battlefield')
    island=put(s,'Snow-Covered Island','battlefield')
    act(s,'p1',type='set_prefs',hold_priority=True)
    original=put(s,'Blessing of Frost','hand')
    act(s,'p1',type='add_mana',mana={'G':1,'C':1})
    act(s,'p1',type='cast_spell',card_id=original.id,sources=[forest.id,island.id])
    wait_priority(s,'p1')
    copy=put(s,'Reverberate','hand')
    pay(s,'p1','Reverberate')
    act(s,'p1',type='cast_spell',card_id=copy.id,sources=[],targets=[original.id])
    settle(s)
    while s.state.rules.decision and any(o.id=='keep' for o in s.state.rules.decision.options):
        choose(s,'keep')
    # The copy draws zero (the Bears are still 2/2), then the original requests its allocation.
    assert not s.state.cards[a.id].counters
    before=len(s.state.zones['p1:hand'])
    choose(s,a.id)
    finish_recipients(s)
    assert s.state.cards[a.id].counters=={'+1/+1':2}
    assert len(s.state.zones['p1:hand'])==before+1
    roundtrip(s)


def test_simultaneous_counter_annihilation_keeps_each_native_removed_trigger(cards):
    s=game(cards)
    source=cast(s,'Protean Hydra',x=2)
    cast(s,"Black Sun's Zenith",x=3)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert len(s.state.rules.delayed)==2
    roundtrip(s)


def test_simultaneous_counter_annihilation_modular_uses_pre_sba_counters(cards):
    s=game(cards)
    recipient=put(s,'Phyrexian Triniform','battlefield')
    source=cast(s,'Arcbound Worker')
    cast(s,"Black Sun's Zenith",x=2)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.cards[recipient.id].counters=={'-1/-1':2}
    # Modular asks its target as its trigger is put on the stack, then the optional placement.
    while s.state.rules.decision:
        d=s.state.rules.decision
        ids={o.id for o in d.options}
        if recipient.id in ids:
            choose(s,recipient.id)
        elif 'yes' in ids:
            choose(s,'yes')
        else:
            raise AssertionError((d.kind,d.prompt,ids))
    assert s.state.cards[recipient.id].counters=={'-1/-1':1}
    roundtrip(s)
