"""Actual native damage-value spells, illegal targets, original costs and saved announcements."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import pick, put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent/'fixtures/damage_values102_cards.json').read_text())
NAMES = [c['name'] for c in DATA[:5]]


@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i,c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='c102', number=str(i), **{k:v for k,v in c.items() if k not in ('name','set_code','number')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in DATA] + ['Grizzly Bears','Forest']
    s = table(cards,names,names,names)
    to_phase(s,'main1',turn=1)
    for pid in ['p1','p2','p3']:
        act(s,pid,type='set_prefs',full_control=True,hold_priority=True)
        act(s,pid,type='add_mana',player=pid,mana={c:50 for c in 'CWUBRG'})
    return s


def cast(s,name,*,pid='p1',resolve=True,**kwargs):
    source = put(s,name,'hand',pid=pid)
    wait_priority(s,pid)
    if name=='Vengeful Rebirth' and 'target_counts' not in kwargs:
        kwargs['target_counts']=[1,1]
    act(s,pid,type='cast_spell',card_id=source.id,sources=[],**kwargs)
    if resolve:
        settle(s)
    return source


def cold(s,tmp_path,body,ids):
    import app
    saved = tmp_path/'damage102.json'
    saved.write_text(s.state.model_dump_json())
    code = '''import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import pick,roundtrip
from tests.test_rules_library_look import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
ids=json.loads(sys.argv[3])
'''+body+'\nroundtrip(s)\nrepo.close()\n'
    result = subprocess.run([sys.executable,'-c',code,str(saved),str(s.cards.db_path),json.dumps(ids)],cwd=Path(app.__file__).resolve().parents[1],capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('name',NAMES)
def test_actual_whole_definition102(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def test_fireball_actual_cost_rounding_and_mixed_targets102(cards):
    s=setup(cards)
    wall=put(s,'Wall of Stone','battlefield',pid='p2')
    source=cast(s,'Fireball',x_value=7,targets=[wall.id,'p2','p3'],target_counts=[3],resolve=False)
    record=next(p for p in s.state.rules.payments.values() if p.card==source.id)
    assert record.total_cost=='{9}{R}' and sum(record.mana_spent.values())==10
    settle(s)
    assert s.state.players['p2'].life==38 and s.state.players['p3'].life==38
    assert s.state.cards[wall.id].damage==2
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('zero',[True,False])
def test_fireball_zero_targets_or_more_targets_than_x102(cards,zero):
    s=setup(cards)
    before={p:s.state.players[p].life for p in ['p1','p2','p3']}
    cast(s,'Fireball',x_value=1,targets=[] if zero else ['p2','p3'],target_counts=[0 if zero else 2])
    assert {p:s.state.players[p].life for p in before}==before


def test_fireball_native_response_changes_divisor_at_resolution102(cards):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    cast(s,'Fireball',x_value=7,targets=[bear.id,'p2','p3'],target_counts=[3],resolve=False)
    cast(s,'Lightning Bolt',targets=[bear.id])
    assert s.state.players['p2'].life==37 and s.state.players['p3'].life==37


def test_mega_flare_kicked_prefix_once_then_native_simultaneous_damage102(cards):
    s=setup(cards)
    a=put(s,'Rhox Brute','battlefield',pid='p2')
    b=put(s,'Rhox Brute','battlefield',pid='p3')
    cast(s,'Mega Flare',kicker=1,targets=[a.id,b.id],target_counts=[1,1])
    dragons=[c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.name=='Dragon']
    assert len(dragons)==1
    assert s.state.cards[a.id].zone=='p2:graveyard' and s.state.cards[b.id].zone=='p3:graveyard'


def test_mega_flare_zero_targets_still_creates_one_kicked_dragon102(cards):
    s=setup(cards)
    cast(s,'Mega Flare',kicker=1,targets=[],target_counts=[0,0])
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.name=='Dragon'])==1


def test_mega_flare_targets_remain_bound_to_original_opponent102(cards):
    s=setup(cards)
    a=put(s,'Rhox Brute','battlefield',pid='p2')
    b=put(s,'Wall of Stone','battlefield',pid='p3')
    put(s,'Earth Elemental','battlefield')
    cast(s,'Mega Flare',targets=[a.id,b.id],target_counts=[1,1],resolve=False)
    cast(s,'Ray of Command',targets=[a.id])
    assert s.state.cards[a.id].controller=='p1' and s.state.cards[a.id].damage==0
    assert s.state.cards[b.id].damage==4


@pytest.mark.parametrize('land',[False,True])
def test_rebirth_actual_return_mana_value_land_and_self_exile102(cards,land):
    s=setup(cards)
    target=put(s,'Forest' if land else 'Earth Elemental','graveyard')
    source=cast(s,'Vengeful Rebirth',targets=[target.id,'p2'])
    assert s.state.cards[target.id].zone=='p1:hand'
    assert s.state.players['p2'].life==(40 if land else 35)
    assert s.state.cards[source.id].zone=='p1:exile'


def test_rebirth_missing_return_does_not_deal_damage_but_still_self_exiles102(cards):
    s=setup(cards)
    target=put(s,'Earth Elemental','graveyard')
    crypt=put(s,"Tormod's Crypt",'battlefield')
    source=cast(s,'Vengeful Rebirth',targets=[target.id,'p2'],resolve=False)
    act(s,'p1',type='activate_ability',card_id=crypt.id,ability=0,targets=['p1'],sources=[])
    settle(s)
    assert s.state.players['p2'].life==40 and s.state.cards[source.id].zone=='p1:exile'


def test_rebirth_illegal_damage_target_returns_card_and_self_exiles102(cards):
    s=setup(cards)
    target=put(s,'Earth Elemental','graveyard')
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    source=cast(s,'Vengeful Rebirth',targets=[target.id,bear.id],resolve=False)
    cast(s,'Lightning Bolt',targets=[bear.id])
    assert s.state.cards[target.id].zone=='p1:hand' and s.state.cards[source.id].zone=='p1:exile'


def test_delirium_native_active_player_target_tapped_target_and_noncombat102(cards):
    s=setup(cards)
    own=put(s,'Earth Elemental','battlefield',pid='p2')
    wrong=put(s,'Earth Elemental','battlefield',pid='p3')
    spell=put(s,'Delirium','hand')
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=spell.id,targets=[own.id],sources=[])
    to_phase(s,'main1',turn=2)
    act(s,'p1',type='add_mana',player='p1',mana={'B':5,'R':5,'C':10})
    wait_priority(s,'p1')
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=spell.id,targets=[wrong.id],sources=[])
    assert s.state.model_dump(mode='json')==before
    act(s,'p2',type='tap',card_ids=[own.id],tapped=True)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[own.id],sources=[])
    settle(s)
    assert s.state.players['p2'].life==36 and s.state.cards[own.id].tapped
    cast(s,'Lightning Bolt',targets=[own.id])
    assert s.state.cards[own.id].damage==3


@pytest.mark.parametrize('behold',[False,True])
def test_piercing_exhale_real_behold_optional_cost_and_surveil102(cards,behold):
    s=setup(cards)
    own=put(s,'Earth Elemental','battlefield')
    victim=put(s,'Rhox Brute','battlefield',pid='p2')
    dragon=put(s,'Shivan Dragon','hand')
    source=put(s,'Piercing Exhale','hand')
    extra={'optional_costs':[source.id+':behold'],'cost_choices':[{'component':0,'cards':[dragon.id]}]} if behold else {}
    before=list(s.state.zones['p1:library'])
    act(s,'p1',type='cast_spell',card_id=source.id,targets=[own.id,victim.id],target_counts=[1,1],sources=[],**extra)
    settle(s)
    if behold:
        assert s.state.cards[victim.id].damage==4 and s.state.rules.decision
        pick(s,[])
        settle(s)
        if s.state.rules.decision:
            assert s.state.rules.decision.kind=='order'
            pick(s,[o.id for o in s.state.rules.decision.options])
            settle(s)
    assert s.state.rules.decision is None and s.state.cards[victim.id].zone=='p2:graveyard'
    assert s.state.zones['p1:library']==before


def test_genuine_cold_fireball_target_announcement_remembers_x_cost_and_division102(cards,tmp_path):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    bolt=put(s,'Lightning Bolt','hand')
    source=put(s,'Fireball','hand')
    act(s,'p1',type='cast_spell',card_id=source.id,x_value=7,sources=[])
    assert s.state.rules.decision
    cold(s,tmp_path,"""pick(s,[ids['bear'],'p2','p3'])
act(s,'p1',type='cast_spell',card_id=ids['bolt'],targets=[ids['bear']],sources=[])
settle(s)
assert s.state.players['p2'].life==37 and s.state.players['p3'].life==37
""",{'bear':bear.id,'bolt':bolt.id})


def test_genuine_cold_mega_flare_partial_group_does_not_repeat_kicker_prefix102(cards,tmp_path):
    s=setup(cards)
    a=put(s,'Rhox Brute','battlefield',pid='p2')
    b=put(s,'Wall of Stone','battlefield',pid='p3')
    ray=put(s,'Ray of Command','hand')
    source=put(s,'Mega Flare','hand')
    act(s,'p1',type='cast_spell',card_id=source.id,kicker=1,targets=[a.id],target_counts=[1],sources=[])
    assert s.state.rules.decision
    cold(s,tmp_path,"""pick(s,[ids['b']])
act(s,'p1',type='cast_spell',card_id=ids['ray'],targets=[ids['a']],sources=[])
settle(s)
assert s.state.cards[ids['a']].controller=='p1' and s.state.cards[ids['a']].damage==0
assert s.state.cards[ids['b']].damage==6
assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.name=='Dragon'])==1
""",{'a':a.id,'b':b.id,'ray':ray.id})


def test_rebirth_both_original_targets_illegal_is_countered_not_self_exiled102(cards):
    s=setup(cards)
    target=put(s,'Earth Elemental','graveyard')
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    crypt=put(s,"Tormod's Crypt",'battlefield')
    source=cast(s,'Vengeful Rebirth',targets=[target.id,bear.id],resolve=False)
    act(s,'p1',type='activate_ability',card_id=crypt.id,ability=0,targets=['p1'],sources=[])
    cast(s,'Lightning Bolt',targets=[bear.id])
    assert s.state.cards[source.id].zone=='p1:graveyard'


def test_delirium_actual_blocked_combat_prevents_both_directions102(cards):
    s=setup(cards)
    attacker=put(s,'Rhox Brute','battlefield',pid='p2')
    blocker=put(s,'Grizzly Bears','battlefield')
    to_phase(s,'main1',turn=2)
    act(s,'p1',type='add_mana',player='p1',mana={'B':4,'R':4,'C':10})
    act(s,'p2',type='add_mana',player='p2',mana={'U':4,'C':10})
    cast(s,'Delirium',targets=[attacker.id])
    cast(s,'Cerulean Wisps',pid='p2',targets=[attacker.id])
    assert not s.state.cards[attacker.id].tapped
    to_phase(s,'declare_attackers',turn=2)
    act(s,'p2',type='declare_attackers',attackers=[{'card_id':attacker.id,'target':'p1'}])
    to_phase(s,'declare_blockers',turn=2)
    assert s.state.rules.decision.kind=='declare_blockers'
    act(s,'p1',type='declare_blockers',blocks=[{'blocker_id':blocker.id,'attacker_id':attacker.id}])
    to_phase(s,'main2',turn=2)
    assert s.state.cards[attacker.id].damage==0 and s.state.cards[blocker.id].damage==0


def test_mega_flare_one_native_simultaneous_damage_lifelink_event102(cards):
    s=setup(cards)
    put(s,'Soulfire Grand Master','battlefield')
    pride=put(s,"Ajani's Pridemate",'battlefield')
    put(s,'Earth Elemental','battlefield')
    a=put(s,'Wall of Stone','battlefield',pid='p2')
    b=put(s,'Wall of Stone','battlefield',pid='p3')
    cast(s,'Mega Flare',targets=[a.id,b.id],target_counts=[1,1])
    assert s.state.cards[a.id].damage==4 and s.state.cards[b.id].damage==4
    assert s.state.players['p1'].life==48
    assert s.state.cards[pride.id].counters.get('+1/+1',0)==1


def test_delirium_component_fixed_active_recipient_after_native_tap_control_change102(cards):
    """The active recipient is not re-derived from the tapped creature's new controller."""
    from app.rules import damage_values102, effects
    from app.rules.plan import Plan
    from app.rules.targets import ref

    s=setup(cards)
    creature=put(s,'Earth Elemental','battlefield',pid='p2')
    source=put(s,'Delirium','hand')
    to_phase(s,'main1',turn=2)
    act(s,'p1',type='counter',card_ids=[creature.id],kind='lifelink',delta=1)
    plan=Plan(s.state,'p1',cards,None)
    parsed=damage_values102.parse('Tap target creature that player controls. That creature deals damage equal to its power to the player. Prevent all combat damage that would be dealt to and dealt by the creature this turn.')
    assert parsed is not None
    sequence=parsed[0]
    ctx={'controller':'p1','source_card':source.id,'source_object':plan.oid(source),'name':'Delirium',
         'targets':[ref(plan,creature.id).model_dump(mode='json')],'effects':sequence,'next':1}
    assert damage_values102.bind_active(plan,ctx,sequence[0])
    ctx['next']=2
    assert effects.tap(plan,ctx,sequence[1])
    plan.do({'type':'set_controller','card_ids':[creature.id],'player':'p3'},actor='p1')
    ctx['next']=3
    assert effects.damage(plan,ctx,sequence[2])
    assert plan.state.cards[creature.id].controller=='p3'
    assert plan.state.players['p2'].life==36 and plan.state.players['p3'].life==44
