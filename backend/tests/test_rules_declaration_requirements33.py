"""Canonical temporary attack/block requirements and exact paired target bindings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from app.rules.sba import power, toughness
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Provoke', 'Predatory Rampage', 'Academic Dispute', 'Timely Interference', 'Monstrous Step', "Chemister's Trick", 'Incite', 'Auriok Siege Sled', 'Feral Contest', 'Kookus', 'Domineering Will', 'Aggravate']


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/declaration_requirements33_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="nlc31", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [
        c["name"]
        for c in json.loads(
            (Path(__file__).parent / "fixtures/declaration_requirements33_cards.json").read_text()
        )
    ]
    return table(cards, names, names, names)


@pytest.mark.parametrize('name',NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def cast(s,name,targets=(),pid='p1',**kw):
    c=put(s,name,'hand',pid=pid)
    mana(s,pid=pid,W=10,U=10,B=10,R=10,G=10,C=20)
    for _ in range(12):
        if s.state.rules.priority==pid:
            break
        act(s,s.state.rules.priority,type='pass_priority')
    act(s,pid,type='cast_spell',card_id=c.id,targets=list(targets),**kw)
    settle(s)
    return c


def start(s,turn=4):
    from tests.test_rules_wave30m_durations import stops
    stops(s,'upkeep','main1','declare_attackers','declare_blockers','end_combat')
    to_phase(s,'main1',turn=turn)


def force_block(s,attacker,blocker,turn=4):
    from tests.test_rules_wave30p_combat import attack
    to_phase(s,'declare_attackers',turn=turn)
    attack(s,(attacker,'p2'),pid='p1')
    to_phase(s,'declare_blockers',turn=turn)
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_blockers',blocks=[])
    act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':blocker.id,'attacker_id':attacker.id}])
    assert s.state.cards[blocker.id].blocking==attacker.id
    roundtrip(s)


@pytest.mark.parametrize('name',['Provoke','Predatory Rampage','Timely Interference','Monstrous Step','Feral Contest'])
def test_canonical_spell_really_requires_legal_block(cards,name):
    s=setup(cards)
    attacker=put(s,'Grizzly Bears','battlefield')
    blocker=put(s,'Runeclaw Bear','battlefield',pid='p2')
    start(s)
    if name=='Provoke':
        act(s,'p1',type='tap',card_ids=[blocker.id],tapped=True)
    target=[blocker.id]
    kw={}
    if name=='Predatory Rampage':
        target=[]
    if name in ('Monstrous Step','Feral Contest'):
        target=[attacker.id,blocker.id]
        kw={'target_counts':[1,1]}
    if name=='Timely Interference':
        kw={'kicker':1}
    drew=s.state.rules.turn_log.drew.get("p1",0)
    cast(s,name,target,**kw)
    ch=Plan(s.state,"p1",s.cards,None).ch(s.state.cards[attacker.id])
    if name in ("Provoke","Timely Interference"):
        assert s.state.rules.turn_log.drew.get("p1",0)==drew+1
    if name in ("Predatory Rampage","Monstrous Step"):
        assert (power(s.state.cards[attacker.id],ch),toughness(s.state.cards[attacker.id],ch)) == ((5,5) if name=="Predatory Rampage" else (9,9))
    assert s.state.rules.decision is None
    if name=='Provoke':
        assert not s.state.cards[blocker.id].tapped
    if name=='Feral Contest':
        assert s.state.cards[attacker.id].counters.get('+1/+1')==1
    force_block(s,attacker,blocker)


@pytest.mark.parametrize('name',["Chemister's Trick",'Incite','Aggravate'])
def test_canonical_instant_really_requires_opponent_to_attack(cards,name):
    s=setup(cards)
    attacker=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s,turn=2)
    cast(s,name,['p2' if name=='Aggravate' else attacker.id])
    ch=Plan(s.state,'p1',s.cards,None).ch(s.state.cards[attacker.id])
    if name=='Incite':
        assert ch.colors==frozenset({'R'})
    if name=="Chemister's Trick":
        assert power(s.state.cards[attacker.id],ch)==0
    if name=='Aggravate':
        assert s.state.cards[attacker.id].damage==1
    to_phase(s,'declare_attackers',turn=2)
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_attackers',attackers=[])
    act(s,'p2',type='declare_attackers',attackers=[{'card_id':attacker.id,'target':'p1'}])
    assert s.state.cards[attacker.id].attacking.id=='p1'
    roundtrip(s)


def test_siege_sled_typed_artifact_target_must_block_source(cards):
    s=setup(cards)
    attacker=put(s,'Auriok Siege Sled','battlefield')
    blocker=put(s,'Memnite','battlefield',pid='p2')
    start(s)
    mana(s,C=1)
    act(s,'p1',type='activate_ability',card_id=attacker.id,ability=0,targets=[blocker.id])
    settle(s)
    force_block(s,attacker,blocker)


def test_kookus_actual_upkeep_damage_and_source_attack_requirement(cards):
    s=setup(cards)
    kookus=put(s,'Kookus','battlefield')
    from tests.test_rules_wave30m_durations import stops
    stops(s,'upkeep','main1','declare_attackers')
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert s.state.players['p1'].life==37
    to_phase(s,'declare_attackers',turn=4)
    with pytest.raises(ActionError):
        act(s,'p1',type='declare_attackers',attackers=[])
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':kookus.id,'target':'p2'}])
    roundtrip(s)


def test_domineering_will_transfers_and_untaps_then_new_controller_must_block(cards):
    s=setup(cards)
    attacker=put(s,'Grizzly Bears','battlefield')
    blocker=put(s,'Kraken Hatchling','battlefield',pid='p3')
    start(s)
    act(s,'p1',type='tap',card_ids=[blocker.id],tapped=True)
    cast(s,'Domineering Will',['p2',blocker.id],target_counts=[1,1])
    assert s.state.cards[blocker.id].controller=='p2'
    assert not s.state.cards[blocker.id].tapped
    force_block(s,attacker,blocker)
    to_phase(s,'main1',turn=5)
    assert s.state.cards[blocker.id].controller=='p3'
    roundtrip(s)


def test_academic_dispute_optional_reach_then_native_learn_decline(cards):
    s=setup(cards)
    attacker=put(s,'Baneslayer Angel','battlefield')
    blocker=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s)
    cast(s,'Academic Dispute',[blocker.id])
    assert s.state.rules.decision is not None
    pick(s,['yes'])
    settle(s)
    assert s.state.rules.decision is not None
    pick(s,['decline'])
    settle(s)
    force_block(s,attacker,blocker)


def test_rampage_rule_group_tracks_new_opposing_creatures_but_pump_is_snapshot(cards):
    s=setup(cards)
    attacker=put(s,'Grizzly Bears','battlefield')
    old=put(s,'Runeclaw Bear','battlefield',pid='p2')
    start(s)
    cast(s,'Predatory Rampage')
    new=put(s,'Memnite','battlefield',pid='p2')
    own_new=put(s,'Runeclaw Bear','battlefield')
    plan=Plan(s.state,'p1',s.cards,None)
    assert power(s.state.cards[own_new.id],plan.ch(s.state.cards[own_new.id]))==2
    from tests.test_rules_wave30p_combat import attack
    to_phase(s,'declare_attackers',turn=4)
    attack(s,(attacker,'p2'))
    to_phase(s,'declare_blockers',turn=4)
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':old.id,'attacker_id':attacker.id}])
    act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':c.id,'attacker_id':attacker.id} for c in [old,new]])
    roundtrip(s)


@pytest.mark.parametrize('name',['Provoke','Academic Dispute','Timely Interference'])
def test_requirement_cannot_force_illegal_flying_block_and_kicker_is_conditional(cards,name):
    s=setup(cards)
    attacker=put(s,'Baneslayer Angel','battlefield')
    blocker=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s)
    cast(s,name,[blocker.id])
    if name=='Academic Dispute':
        pick(s,['no'])
        settle(s)
        pick(s,['decline'])
        settle(s)
    from tests.test_rules_wave30p_combat import attack
    to_phase(s,'declare_attackers',turn=4)
    attack(s,(attacker,'p2'))
    to_phase(s,'declare_blockers',turn=4)
    if s.state.rules.decision is not None:
        act(s,'p2',type='declare_blockers',blocks=[])
    roundtrip(s)


def test_unkicked_interference_draws_and_reduces_power_without_requiring_block(cards):
    s=setup(cards)
    attacker=put(s,'Grizzly Bears','battlefield')
    blocker=put(s,'Runeclaw Bear','battlefield',pid='p2')
    start(s)
    cast(s,'Timely Interference',[blocker.id])
    from tests.test_rules_wave30p_combat import attack
    to_phase(s,'declare_attackers',turn=4)
    attack(s,(attacker,'p2'))
    to_phase(s,'declare_blockers',turn=4)
    act(s,'p2',type='declare_blockers',blocks=[])
    roundtrip(s)


def test_monstrous_step_can_choose_no_blocker_and_feral_contest_requires_distinct_targets(cards):
    s=setup(cards)
    attacker=put(s,'Grizzly Bears','battlefield')
    start(s)
    cast(s,'Monstrous Step',[attacker.id],target_counts=[1,0])
    assert power(s.state.cards[attacker.id],Plan(s.state,'p1',s.cards,None).ch(s.state.cards[attacker.id]))==9
    source=put(s,'Feral Contest','hand')
    mana(s,G=1,C=2)
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=source.id,targets=[attacker.id,attacker.id],target_counts=[1,1])
    assert s.state.model_dump(mode='json')==before
    roundtrip(s)


def test_siege_sled_restriction_overrides_its_requirement_and_typed_target_is_enforced(cards):
    s=setup(cards)
    source=put(s,'Auriok Siege Sled','battlefield')
    blocker=put(s,'Memnite','battlefield',pid='p2')
    nonartifact=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s)
    mana(s,C=4)
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=[nonartifact.id])
    for index in [0,1]:
        act(s,'p1',type='activate_ability',card_id=source.id,ability=index,targets=[blocker.id])
        settle(s)
    from tests.test_rules_wave30p_combat import attack
    to_phase(s,'declare_attackers',turn=4)
    attack(s,(source,'p2'))
    to_phase(s,'declare_blockers',turn=4)
    act(s,'p2',type='declare_blockers',blocks=[])
    roundtrip(s)


@pytest.mark.parametrize('when',['before','in_response'])
def test_kookus_keeper_name_is_literal_and_upkeep_condition_rechecks(cards,when):
    s=setup(cards)
    source=put(s,'Kookus','battlefield')
    if when=='before':
        put(s,'Keeper of Kookus','battlefield')
    from tests.test_rules_wave30m_durations import stops
    stops(s,'upkeep','main1','declare_attackers')
    to_phase(s,'upkeep',turn=4)
    if when=='in_response':
        assert s.state.zones.get('stack')
        put(s,'Keeper of Kookus','battlefield')
    settle(s)
    assert s.state.players['p1'].life==40
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[])
    assert not s.state.cards[source.id].attacking
    roundtrip(s)


def test_aggravate_uses_actual_damage_not_prevented_or_later_creatures(cards):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    protected=put(s,'Silver Knight','battlefield',pid='p2')
    put(s,'Fervor','battlefield',pid='p2')
    start(s,turn=2)
    cast(s,'Aggravate',['p2'])
    new=put(s,'Memnite','battlefield',pid='p2')
    assert s.state.cards[protected.id].damage==0
    assert s.state.cards[bear.id].damage==1
    to_phase(s,'declare_attackers',turn=2)
    act(s,'p2',type='declare_attackers',attackers=[{'card_id':bear.id,'target':'p1'}])
    assert not s.state.cards[new.id].attacking and not s.state.cards[protected.id].attacking
    roundtrip(s)


def test_attack_requirement_never_forces_payment_of_attack_taxes(cards):
    s=setup(cards)
    attacker=put(s,'Grizzly Bears','battlefield',pid='p2')
    put(s,'Ghostly Prison','battlefield')
    put(s,'Ghostly Prison','battlefield',pid='p3')
    start(s,turn=2)
    cast(s,'Incite',[attacker.id])
    to_phase(s,'declare_attackers',turn=2)
    act(s,'p2',type='declare_attackers',attackers=[])
    roundtrip(s)


def test_block_requirement_never_forces_oppressive_rays_payment(cards):
    s=setup(cards)
    attacker=put(s,'Grizzly Bears','battlefield')
    blocker=put(s,'Runeclaw Bear','battlefield',pid='p2')
    start(s)
    cast(s,'Oppressive Rays',[blocker.id])
    cast(s,'Provoke',[blocker.id])
    from tests.test_rules_wave30p_combat import attack
    to_phase(s,'declare_attackers',turn=4)
    attack(s,(attacker,'p2'))
    to_phase(s,'declare_blockers',turn=4)
    act(s,'p2',type='declare_blockers',blocks=[])
    roundtrip(s)


def test_paired_requirement_stack_survives_cold_restore(cards,tmp_path):
    import subprocess
    import sys
    s=setup(cards)
    attacker=put(s,'Grizzly Bears','battlefield')
    blocker=put(s,'Runeclaw Bear','battlefield',pid='p2')
    start(s)
    source=put(s,'Monstrous Step','hand')
    mana(s,G=2,C=3)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=[attacker.id,blocker.id],target_counts=[1,1])
    saved=tmp_path/'paired-requirement.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import settle
from tests.test_rules_declaration_requirements33 import force_block
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
settle(s)
force_block(s,s.state.cards[sys.argv[3]],s.state.cards[sys.argv[4]])
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),attacker.id,blocker.id],capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('name',['Monstrous Step','Feral Contest'])
def test_pair_keeps_exact_original_attacker_when_first_target_blinks(cards,name):
    s=setup(cards)
    attacker=put(s,'Grizzly Bears','battlefield')
    blocker=put(s,'Runeclaw Bear','battlefield',pid='p2')
    start(s)
    source=put(s,name,'hand')
    mana(s,W=2,G=5,C=10)
    act(s,'p1',type='cast_spell',card_id=source.id,targets=[attacker.id,blocker.id],target_counts=[1,1])
    original=s.state.rules.object_id(attacker.id)
    cast(s,'Cloudshift',[attacker.id])
    assert s.state.rules.object_id(attacker.id)!=original
    assert s.state.cards[attacker.id].counters.get('+1/+1',0)==0
    assert power(s.state.cards[attacker.id],Plan(s.state,'p1',s.cards,None).ch(s.state.cards[attacker.id]))==2
    cast(s,'Expedite',[attacker.id])
    from tests.test_rules_wave30p_combat import attack
    to_phase(s,'declare_attackers',turn=4)
    attack(s,(attacker,'p2'))
    to_phase(s,'declare_blockers',turn=4)
    act(s,'p2',type='declare_blockers',blocks=[])
    roundtrip(s)


def test_academic_learn_discard_and_draw_is_independent_of_optional_reach(cards):
    s=setup(cards)
    blocker=put(s,'Grizzly Bears','battlefield',pid='p2')
    discard=put(s,'Memnite','hand')
    start(s)
    cast(s,'Academic Dispute',[blocker.id])
    pick(s,['no'])
    settle(s)
    before=s.state.rules.turn_log.drew.get('p1',0)
    pick(s,['pay'])
    settle(s)
    assert s.state.rules.decision is not None
    pick(s,[discard.id])
    settle(s)
    assert s.state.cards[discard.id].zone=='p1:graveyard'
    assert s.state.rules.turn_log.drew.get('p1',0)==before+1
    roundtrip(s)


def test_native_modal_target_offset_keeps_paired_requirement_on_correct_creature(cards):
    # Explicit synthetic composition harness: native independent target groups from two modes.
    # The real Monstrous Step/Feral Contest cards are separately tested with canonical Oracle.
    s=setup(cards)
    attacker=put(s,'Grizzly Bears','battlefield')
    blocker=put(s,'Runeclaw Bear','battlefield',pid='p2')
    start(s)
    cast(s,'Modal requirement harness',['p3',attacker.id,blocker.id],target_counts=[1,1,1],modes=[0,1])
    assert s.state.players['p3'].life==41
    assert power(s.state.cards[attacker.id],Plan(s.state,'p1',s.cards,None).ch(s.state.cards[attacker.id]))==9
    force_block(s,attacker,blocker)
