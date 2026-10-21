"""Canonical arithmetic uses actual removals, paid costs, and native counter replacements."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_remaining_talents import pay
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave7b_activation import ability_index
from tests.test_rules_wave30m_durations import to_phase

NAMES=['Sarulf, Realm Eater','Lightning Coils','Lily Bowen, Raging Grandma','Sage of Hours','Nuclear Fallout']


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/counter_arithmetic_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='car',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    ns=[*NAMES,'Grizzly Bears','Sol Ring','Forest','Shalai, Voice of Plenty','Doubling Season','Hardened Scales','Vorinclex, Monstrous Raider','Solemnity','Shock','Giant Growth','Rings of Brighthearth','Necrotic Ooze','Reverberate','Boon Reflection','Tainted Remedy']
    return table(cards,ns,ns,ns)


def cast(s,name,*,x=None,targets=None,finish=True):
    c=put(s,name,'hand')
    pay(s,'p1',name)
    if x:
        act(s,'p1',type='add_mana',mana={'C':x})
    kwargs={'x_value':x} if x is not None else {}
    act(s,'p1',type='cast_spell',card_id=c.id,sources=[],targets=targets or [],**kwargs)
    if finish:
        settle(s)
    return c


def counter(s,c,n,kind='+1/+1'):
    act(s,'p1',type='set_counter',card_id=c.id,kind=kind,value=n)


def choose(s,value):
    d=s.state.rules.decision
    assert d and value in {o.id for o in d.options}, (d.kind if d else None,d.prompt if d else None,value)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[value])
    settle(s)


def ch(s,c):
    return Plan(s.state,'p1',s.cards,None).ch(s.state.cards[c.id])


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('amount,expected',[(0,0),(4,0),(5,1),(9,1),(10,2),(1005,201)])
def test_sage_cost_removes_all_and_turns_use_complete_paid_groups(cards,amount,expected):
    s=game(cards)
    source=cast(s,'Sage of Hours')
    counter(s,source,amount)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability_index(s,source,'For each five'),sources=[])
    assert not s.state.cards[source.id].counters
    settle(s)
    assert len(s.state.rules.extra_turns)==expected
    roundtrip(s)


def test_sage_cost_snapshot_survives_source_left_before_resolution(cards):
    s=game(cards)
    source=cast(s,'Sage of Hours')
    counter(s,source,10)
    act(s,'p1',type='set_prefs',hold_priority=True)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability_index(s,source,'For each five'),sources=[])
    put(s,'Sage of Hours','graveyard')
    settle(s)
    assert len(s.state.rules.extra_turns)==2
    roundtrip(s)


def test_sarulf_optional_removal_and_exile_current_boundary_preserve_land_source(cards):
    s=game(cards)
    source=cast(s,'Sarulf, Realm Eater')
    a=put(s,'Grizzly Bears','battlefield','p2')
    b=put(s,'Shalai, Voice of Plenty','battlefield','p3')
    land=put(s,'Forest','battlefield','p2')
    counter(s,source,2)
    counter(s,source,1,kind='vigilance')
    to_phase(s,'upkeep',turn=4)
    settle(s)
    roundtrip(s)
    choose(s,'yes')
    assert s.state.cards[a.id].zone=='p2:exile'
    assert s.state.cards[b.id].zone=='p3:battlefield'
    assert s.state.cards[land.id].zone=='p2:battlefield'
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert s.state.cards[source.id].counters=={'vigilance':1}
    roundtrip(s)


def test_sarulf_decline_preserves_all_counters_and_other_permanents(cards):
    s=game(cards)
    source=cast(s,'Sarulf, Realm Eater')
    target=put(s,'Sol Ring','battlefield','p2')
    counter(s,source,3)
    to_phase(s,'upkeep',turn=4)
    settle(s)
    choose(s,'no')
    assert s.state.cards[source.id].counters=={'+1/+1':3}
    assert s.state.cards[target.id].zone=='p2:battlefield'
    roundtrip(s)


def test_coils_actual_nontoken_death_then_five_counters_create_haste_tokens_and_exile(cards):
    s=game(cards)
    source=put(s,'Lightning Coils','battlefield')
    target=put(s,'Grizzly Bears','battlefield')
    counter(s,source,4,kind='charge')
    cast(s,'Shock',targets=[target.id])
    assert s.state.cards[source.id].counters=={'charge':5}
    to_phase(s,'upkeep',turn=4)
    settle(s)
    tokens=[c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield']
    assert len(tokens)==5
    assert all(ch(s,c).pt==(3,1) and 'haste' in ch(s,c).keywords for c in tokens)
    assert not s.state.cards[source.id].counters
    roundtrip(s)
    to_phase(s,'end',turn=4)
    settle(s)
    assert not [c for c in s.state.cards.values() if c.is_token and c.zone.endswith(':battlefield')]
    roundtrip(s)


@pytest.mark.parametrize('initial,expected,life_gain',[(16,32,0),(17,1,16)])
def test_lily_resolution_branch_uses_derived_power_not_raw_counter_count(cards,initial,expected,life_gain):
    s=game(cards)
    source=cast(s,'Lily Bowen, Raging Grandma')
    assert s.state.cards[source.id].counters=={'+1/+1':2}
    # Lily is printed0/0. Set the actual quantity to the tested power boundary.
    counter(s,source,initial)
    before=s.state.players['p1'].life
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert s.state.cards[source.id].counters=={'+1/+1':expected}
    assert s.state.players['p1'].life==before+life_gain
    roundtrip(s)


@pytest.mark.parametrize('x',[0,1,3])
def test_nuclear_fallout_pump_twice_x_but_each_player_rad_only_x(cards,x):
    s=game(cards)
    a=put(s,'Shalai, Voice of Plenty','battlefield')
    b=put(s,'Shalai, Voice of Plenty','battlefield','p2')
    cast(s,'Nuclear Fallout',x=x)
    for pid in s.state.players:
        assert s.state.players[pid].resources.get('rad',0)==x
    if x==3:
        assert s.state.cards[a.id].zone=='p1:graveyard' and s.state.cards[b.id].zone=='p2:graveyard'
    else:
        assert ch(s,a).pt==(3-2*x,4-2*x) and ch(s,b).pt==(3-2*x,4-2*x)
        to_phase(s,'upkeep',turn=2)
        assert ch(s,a).pt==(3,4) and ch(s,b).pt==(3,4)
    roundtrip(s)


def test_sage_rings_copy_reuses_original_paid_counter_quantity(cards):
    s=game(cards)
    source=cast(s,'Sage of Hours')
    put(s,'Rings of Brighthearth','battlefield')
    counter(s,source,5)
    act(s,'p1',type='add_mana',mana={'C':2})
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability_index(s,source,'For each five'),sources=[])
    settle(s)
    assert not s.state.cards[source.id].counters
    choose(s,'pay')
    while s.state.rules.decision and 'keep' in {o.id for o in s.state.rules.decision.options}:
        choose(s,'keep')
    assert len(s.state.rules.extra_turns)==2
    roundtrip(s)


def test_borrowed_sage_cost_reads_actual_ooze_source_counters(cards):
    s=game(cards)
    put(s,'Sage of Hours','graveyard')
    source=put(s,'Necrotic Ooze','battlefield')
    counter(s,source,10)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability_index(s,source,'For each five'),sources=[])
    settle(s)
    assert not s.state.cards[source.id].counters
    assert len(s.state.rules.extra_turns)==2
    roundtrip(s)


def test_sage_paid_quantity_and_turn_primitive_resume_after_cold_load(cards,tmp_path):
    import subprocess
    import sys
    s=game(cards)
    source=cast(s,'Sage of Hours')
    counter(s,source,10)
    act(s,'p1',type='set_prefs',hold_priority=True)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability_index(s,source,'For each five'),sources=[])
    assert not s.state.cards[source.id].counters
    saved=tmp_path/'sage.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
save,db=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
for _ in range(12):
 if not s.state.zones['stack']:break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert len(s.state.rules.extra_turns)==2
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path)],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


def test_sarulf_left_battlefield_cannot_remove_lki_counters_or_exile(cards):
    s=game(cards)
    source=cast(s,'Sarulf, Realm Eater')
    target=put(s,'Sol Ring','battlefield','p2')
    counter(s,source,3)
    to_phase(s,'upkeep',turn=4)
    put(s,'Sarulf, Realm Eater','graveyard')
    settle(s)
    assert not s.state.rules.decision
    assert s.state.cards[target.id].zone=='p2:battlefield'
    roundtrip(s)


def test_sarulf_removal_can_make_lethal_damage_but_exile_happens_first(cards):
    s=game(cards)
    source=cast(s,'Sarulf, Realm Eater')
    target=put(s,'Grizzly Bears','battlefield','p2')
    counter(s,source,3)
    to_phase(s,'upkeep',turn=4)
    act(s,'p1',type='set_damage',card_ids=[source.id],value=5)
    settle(s)
    choose(s,'yes')
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.cards[target.id].zone=='p2:exile'
    roundtrip(s)


def test_coils_token_doubling_delayed_exile_covers_all_replacements_only(cards):
    s=game(cards)
    source=put(s,'Lightning Coils','battlefield')
    counter(s,source,5,kind='charge')
    put(s,'Doubling Season','battlefield')
    to_phase(s,'upkeep',turn=4)
    settle(s)
    tokens=[c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield']
    assert len(tokens)==10
    act(s,'p1',type='create_token',player='p1',token={'name':'Later Token','power':'1','toughness':'1','type_line':'Token Creature','colors':[]})
    to_phase(s,'end',turn=4)
    settle(s)
    remaining=[c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield']
    assert [c.name for c in remaining]==['Later Token']
    roundtrip(s)


def test_coils_threshold_rechecks_actual_counters_at_resolution(cards):
    s=game(cards)
    source=put(s,'Lightning Coils','battlefield')
    counter(s,source,5,kind='charge')
    to_phase(s,'upkeep',turn=4)
    counter(s,source,4,kind='charge')
    settle(s)
    assert s.state.cards[source.id].counters=={'charge':4}
    assert not [c for c in s.state.cards.values() if c.is_token and c.zone=='p1:battlefield']
    roundtrip(s)


def test_lily_uses_power_modified_by_actual_giant_growth_before_trigger_resolves(cards):
    s=game(cards)
    source=cast(s,'Lily Bowen, Raging Grandma')
    counter(s,source,14)
    to_phase(s,'upkeep',turn=4)
    before=s.state.players['p1'].life
    cast(s,'Giant Growth',targets=[source.id])
    assert s.state.cards[source.id].counters=={'+1/+1':1}
    assert s.state.players['p1'].life==before+13
    roundtrip(s)


def test_lily_actual_removed_amount_uses_native_gain_replacement(cards):
    s=game(cards)
    source=cast(s,'Lily Bowen, Raging Grandma')
    counter(s,source,17)
    put(s,'Boon Reflection','battlefield')
    before=s.state.players['p1'].life
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert s.state.cards[source.id].counters=={'+1/+1':1}
    assert s.state.players['p1'].life==before+32
    roundtrip(s)


def test_nuclear_copy_preserves_x_for_both_signed_pump_and_player_counters(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s=game(cards)
    target=put(s,'Shalai, Voice of Plenty','battlefield')
    act(s,'p1',type='set_prefs',hold_priority=True)
    original=cast(s,'Nuclear Fallout',x=1,finish=False)
    wait_priority(s,'p1')
    cast(s,'Reverberate',targets=[original.id])
    while s.state.rules.decision and 'keep' in {o.id for o in s.state.rules.decision.options}:
        choose(s,'keep')
    assert s.state.cards[target.id].zone=='p1:graveyard'
    assert all(p.resources.get('rad',0)==2 for p in s.state.players.values())
    roundtrip(s)


@pytest.mark.parametrize('block',[False,True])
def test_nuclear_player_counter_replacement_and_prohibition_stay_native(cards,block):
    s=game(cards)
    put(s,'Solemnity' if block else 'Vorinclex, Monstrous Raider','battlefield')
    cast(s,'Nuclear Fallout',x=1)
    assert all(p.resources.get('rad',0)==(0 if block else 2) for p in s.state.players.values())
    roundtrip(s)
