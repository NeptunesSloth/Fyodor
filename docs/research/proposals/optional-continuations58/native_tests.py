"""Native mid-resolution optional continuations and late target announcement."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card,fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put,roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase
NAMES=['Eden, Seat of the Sanctum','Blood Spatter Analysis','Serum-Core Chimera','Vengeful Villagers','Winter Soldier, Icy Assassin']
@pytest.fixture
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/optional_continuations58_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='oc58',number=str(i),**{k:v for k,v in c.items() if k not in ('name','set_code')})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()
def setup(cards,name):
    names=[*NAMES,'Grizzly Bears','Sol Ring','Pacifism','Forest','Lightning Bolt','Bonesplitter']
    s=table(cards,names,names,names)
    to_phase(s,'main1',1)
    source=put(s,name,'hand')
    act(s,'p1',type='add_mana',player='p1',mana={'C':20,'R':20,'U':20,'B':20,'W':20})
    return s,source
def answer(s,ids):
    d=s.state.rules.decision
    assert d is not None
    act(s,d.player,type='choose',decision_id=d.id,option_ids=ids)
    settle(s)
@pytest.mark.parametrize('pay',[True,False])
def test_eden_mill_before_optional_sacrifice_and_late_target(cards,pay):
    s,source=setup(cards,NAMES[0])
    act(s,'p1',type='play_land',card_id=source.id)
    target=put(s,'Grizzly Bears','graveyard')
    before=len(s.state.zones['p1:graveyard'])
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    settle(s)
    assert len(s.state.zones['p1:graveyard'])==before+2
    assert source.zone=='p1:battlefield'
    answer(s,['pay' if pay else 'decline'])
    if pay:
        assert source.zone=='p1:graveyard'
        d=s.state.rules.decision
        assert d is not None and target.id in [o.id for o in d.options], (s.state.rules.model_dump(),chosen if 'chosen' in locals() else '')
        assert source.id not in [o.id for o in d.options]
        answer(s,[target.id])
        assert target.zone=='p1:hand'
    else:
        assert source.zone=='p1:battlefield' and target.zone=='p1:graveyard'
        assert s.state.rules.decision is None
    roundtrip(s)

@pytest.mark.parametrize('discard',[True,False])
def test_serum_draw_happens_before_optional_nonland_discard(cards,discard):
    s,source=setup(cards,NAMES[2])
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    target=put(s,'Grizzly Bears','battlefield','p2')
    act(s,'p1',type='counter',card_ids=[source.id],kind='oil',delta=3)
    before=len(s.state.zones['p1:hand'])
    act(s,'p1',type='activate_ability',card_id=source.id,ability=2)
    settle(s)
    assert len(s.state.zones['p1:hand'])==before+1
    assert not source.counters
    answer(s,['yes' if discard else 'no'])
    if discard:
        d=s.state.rules.decision
        assert d is not None
        if d.resume.get('step')=='discard':
            chosen=next(o.id for o in d.options if o.id in s.state.cards)
            answer(s,[chosen])
            d=s.state.rules.decision
        assert d is not None and d.resume.get('step')=='trigger_target'
        assert target.id in [o.id for o in d.options]
        answer(s,[target.id])
        assert target.zone=='p2:graveyard'
    else:
        assert s.state.rules.decision is None and target.zone=='p2:battlefield'
    roundtrip(s)

@pytest.mark.parametrize('initial',[0,4,5])
def test_blood_counter_threshold_only_checked_on_native_death_resolution(cards,initial):
    s,source=setup(cards,NAMES[1])
    # Enter without an opponent creature: its first trigger has no legal target.
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    target=put(s,'Grizzly Bears','graveyard')
    doomed=put(s,'Grizzly Bears','battlefield','p2')
    if initial:
        act(s,'p1',type='counter',card_ids=[source.id],kind='bloodstain',delta=initial)
    assert source.zone=='p1:battlefield'
    bolt=put(s,'Lightning Bolt','hand')
    act(s,'p1',type='cast_spell',card_id=bolt.id,targets=[doomed.id],sources=[])
    settle(s)
    assert doomed.zone=='p2:graveyard'
    if initial>=4:
        assert source.zone=='p1:graveyard'
        d=s.state.rules.decision
        assert d is not None and target.id in [o.id for o in d.options]
        answer(s,[target.id])
        assert target.zone=='p1:hand'
    else:
        assert source.zone=='p1:battlefield' and source.counters=={'bloodstain':1}
        assert s.state.rules.decision is None
    roundtrip(s)

def test_eden_empty_library_still_can_sacrifice_and_return(cards):
    s,source=setup(cards,NAMES[0])
    act(s,'p1',type='play_land',card_id=source.id)
    target=put(s,'Grizzly Bears','graveyard')
    library=list(s.state.zones['p1:library'])
    act(s,'p1',type='move',card_ids=library,to={'player':'p1','zone':'hand'})
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    settle(s)
    answer(s,['pay'])
    assert source.zone=='p1:graveyard'
    answer(s,[target.id])
    assert target.zone=='p1:hand'
    roundtrip(s)

def test_eden_original_source_left_cannot_sacrifice_new_object(cards):
    s,source=setup(cards,NAMES[0])
    act(s,'p1',type='play_land',card_id=source.id)
    target=put(s,'Grizzly Bears','graveyard')
    act(s,'p1',type='set_prefs',hold_priority=True)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'exile'})
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'battlefield'})
    settle(s)
    d=s.state.rules.decision
    if d is not None:
        assert 'pay' not in [o.id for o in d.options]
        answer(s,['decline'])
    assert source.zone=='p1:battlefield' and target.zone=='p1:graveyard'
    roundtrip(s)

@pytest.mark.parametrize('pay',[True,False])
def test_villagers_original_attack_target_tapped_before_sacrifice(cards,pay):
    from tests.test_rules_conditional_prevention import attack
    s,source=setup(cards,NAMES[3])
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    target=put(s,'Grizzly Bears','battlefield','p2')
    artifact=put(s,'Sol Ring','battlefield')
    attack(s,[source],turn=4)
    d=s.state.rules.decision
    assert d is not None and target.id in [o.id for o in d.options]
    answer(s,[target.id])
    assert target.tapped
    d=s.state.rules.decision
    assert d is not None and d.resume.get('opt')
    answer(s,['pay' if pay else 'decline'])
    if pay:
        d=s.state.rules.decision
        if d is not None:
            answer(s,[artifact.id])
        assert artifact.zone=='p1:graveyard'
        assert target.counters.get('stun')==1
    else:
        assert artifact.zone=='p1:battlefield' and not target.counters
    roundtrip(s)

@pytest.mark.parametrize('attach',[True,False])
def test_winter_actual_graveyard_return_then_private_equipment_choice(cards,attach):
    s,source=setup(cards,NAMES[4])
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    equipment=put(s,'Bonesplitter','battlefield')
    opponent=put(s,'Bonesplitter','battlefield','p2')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=2)
    settle(s)
    assert source.zone=='p1:battlefield' and source.counters.get('finality')==1
    d=s.state.rules.decision
    assert d is not None and d.resume.get('step')=='attach_choose'
    assert equipment.id in [o.id for o in d.options] and opponent.id not in [o.id for o in d.options]
    answer(s,[equipment.id] if attach else [])
    assert equipment.attached_to==(source.id if attach else None)
    from app.rules.plan import Plan
    assert Plan(s.state,'p1',cards,None).ch(source).pt==(6 if attach else 2,2)
    bolt=put(s,'Lightning Bolt','hand')
    act(s,'p1',type='cast_spell',card_id=bolt.id,targets=[source.id],sources=[])
    settle(s)
    assert source.zone=='p1:exile'
    roundtrip(s)
