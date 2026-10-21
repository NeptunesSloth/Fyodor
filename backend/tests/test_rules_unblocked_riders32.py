"""Canonical gameplay checks for collateral named-selector promotions."""

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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Delif's Cone", "Delif's Cube", "Gaze of Pain", "Farrel's Mantle", "Rysorian Badger"]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/unblocked_riders32_cards.json").read_text())
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
            (Path(__file__).parent / "fixtures/unblocked_riders32_cards.json").read_text()
        )
    ]
    return table(cards, names, names, names)


@pytest.mark.parametrize("name", NAMES)
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def cast(s, name, targets=()):
    c=put(s,name,'hand')
    mana(s,W=5,U=5,B=5,R=5,G=5,C=10)
    act(s,'p1',type='cast_spell',card_id=c.id,targets=list(targets))
    settle(s)
    return c


def unblocked(s, attacker, defender='p2', turn=4, pid='p1'):
    from tests.test_rules_wave30m_durations import stops
    from tests.test_rules_wave30p_combat import attack
    stops(s,'main1','declare_attackers','declare_blockers','combat_damage','end_combat')
    to_phase(s,'declare_attackers',turn=turn)
    attack(s,(attacker,defender),pid=pid)
    to_phase(s,'declare_blockers',turn=turn)
    if s.state.rules.decision is not None and s.state.rules.decision.kind == 'declare_blockers':
        act(s,defender,type='declare_blockers',blocks=[])
    settle(s)


@pytest.mark.parametrize('yes',[False,True])
def test_cone_gain_and_assignment_choice_after_sacrificed_source(cards,yes):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    cone=put(s,"Delif's Cone",'battlefield')
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='activate_ability',card_id=cone.id,ability=0,targets=[bear.id])
    settle(s)
    assert s.state.cards[cone.id].zone=='p1:graveyard'
    unblocked(s,bear)
    d=s.state.rules.decision
    assert d is not None, 'unblocked watch did not trigger'
    roundtrip(s)
    pick(s,['yes' if yes else 'no'])
    settle(s)
    to_phase(s,'end_combat',turn=4)
    assert s.state.players['p1'].life==40+(2 if yes else 0)
    assert s.state.players['p2'].life==40-(0 if yes else 2)
    roundtrip(s)


def test_cube_suppresses_attacker_and_counts_original_artifact(cards):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    cube=put(s,"Delif's Cube",'battlefield')
    to_phase(s,'main1',turn=4)
    mana(s,C=2)
    act(s,'p1',type='activate_ability',card_id=cube.id,ability=0,targets=[bear.id])
    settle(s)
    unblocked(s,bear)
    assert s.state.cards[cube.id].counters.get('cube')==1
    assert s.state.cards[bear.id].counters.get('cube',0)==0
    to_phase(s,'end_combat',turn=4)
    assert s.state.players['p2'].life==40
    roundtrip(s)


@pytest.mark.parametrize('name',["Gaze of Pain","Farrel's Mantle"])
def test_unblocked_optional_damage_has_event_attacker_source(cards,name):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    victim=put(s,'Runeclaw Bear','battlefield',pid='p2')
    to_phase(s,'main1',turn=4)
    cast(s,name,[bear.id] if name=="Farrel's Mantle" else [])
    unblocked(s,bear)
    d=s.state.rules.decision
    assert d is not None
    pick(s,[victim.id])
    settle(s)
    d=s.state.rules.decision
    assert d is not None
    pick(s,['yes'])
    settle(s)
    assert s.state.cards[victim.id].zone=='p2:graveyard'
    to_phase(s,'end_combat',turn=4)
    assert s.state.players['p2'].life==40
    roundtrip(s)


@pytest.mark.parametrize('number',[0,1,2])
def test_badger_accepts_zero_or_more_targets_and_counts_exiled_cards(cards,number):
    s=setup(cards)
    badger=put(s,'Rysorian Badger','battlefield')
    targets=[put(s,name,'graveyard',pid='p2') for name in ['Grizzly Bears','Runeclaw Bear']]
    unrelated=put(s,'Grizzly Bears','graveyard',pid='p3')
    unblocked(s,badger)
    d=s.state.rules.decision
    assert d is not None
    assert unrelated.id not in {o.id for o in d.options}
    pick(s,[c.id for c in targets[:number]])
    settle(s)
    assert s.state.rules.decision is not None
    pick(s,['yes'])
    settle(s)
    to_phase(s,'end_combat',turn=4)
    assert s.state.players['p1'].life==40+number
    assert s.state.players['p2'].life==40
    for i,c in enumerate(targets):
        assert s.state.cards[c.id].zone==('p2:exile' if i<number else 'p2:graveyard')
    roundtrip(s)


@pytest.mark.parametrize('modifier',[None,'Erebos, God of the Dead','Tainted Remedy'])
def test_cone_life_cost_respects_prohibition_but_replacement_is_still_paid(cards,modifier):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    cone=put(s,"Delif's Cone",'battlefield')
    if modifier:
        put(s,modifier,'battlefield',pid='p2')
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='activate_ability',card_id=cone.id,ability=0,targets=[bear.id])
    settle(s)
    unblocked(s,bear)
    if modifier=='Erebos, God of the Dead':
        assert s.state.rules.decision is None
    else:
        assert s.state.rules.decision is not None
        pick(s,['yes'])
        settle(s)
    to_phase(s,'end_combat',turn=4)
    assert s.state.players['p1'].life == (38 if modifier=='Tainted Remedy' else 40 if modifier else 42)
    assert s.state.players['p2'].life == (38 if modifier=='Erebos, God of the Dead' else 40)
    roundtrip(s)


@pytest.mark.parametrize('steal',[False,True])
def test_farrel_chooser_is_current_host_controller_and_damage_host_power_plus_two(cards,steal):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    victim=put(s,'Baneslayer Angel','battlefield')
    to_phase(s,'main1',turn=4)
    aura=cast(s,"Farrel's Mantle",[bear.id])
    unblocked(s,bear,defender='p3',turn=5,pid='p2')
    d=s.state.rules.decision
    assert d is not None and d.player=='p1'
    assert bear.id not in {o.id for o in d.options}
    pick(s,[victim.id])
    if steal:
        while s.state.rules.priority!='p3':
            act(s,s.state.rules.priority,type='pass_priority')
        spell=put(s,'Act of Aggression','hand',pid='p3')
        mana(s,pid='p3',R=2,C=3)
        act(s,'p3',type='cast_spell',card_id=spell.id,targets=[bear.id])
        if s.state.rules.decision is not None:
            d=s.state.rules.decision
            assert d.player=='p3'
            pick(s,[next(o.id for o in d.options if o.id != 'cancel')])
    settle(s)
    d=s.state.rules.decision
    assert d is not None and d.player==('p3' if steal else 'p2')
    assert s.state.cards[aura.id].controller=='p1'
    pick(s,['yes'])
    settle(s)
    assert s.state.cards[victim.id].damage==4
    to_phase(s,'end_combat',turn=5)
    assert s.state.players['p3'].life==40
    roundtrip(s)


@pytest.mark.parametrize('chosen',[1,2])
def test_badger_target_removed_before_resolution_fizzles_only_if_all_illegal(cards,chosen):
    s=setup(cards)
    badger=put(s,'Rysorian Badger','battlefield')
    corpses=[put(s,name,'graveyard',pid='p2') for name in ['Grizzly Bears','Runeclaw Bear']]
    unblocked(s,badger)
    pick(s,[c.id for c in corpses[:chosen]])
    # Exile the first target with a real instant while the Badger ability waits on the stack.
    spell=put(s,'Cremate','hand')
    mana(s,B=1)
    act(s,'p1',type='cast_spell',card_id=spell.id,targets=[corpses[0].id])
    settle(s)
    if chosen==2:
        assert s.state.rules.decision is not None
        pick(s,['yes'])
        settle(s)
    else:
        assert s.state.rules.decision is None
    to_phase(s,'end_combat',turn=4)
    assert s.state.players['p1'].life==40+(1 if chosen==2 else 0)
    assert s.state.players['p2'].life==(40 if chosen==2 else 38)
    roundtrip(s)


@pytest.mark.parametrize('gone',['artifact','attacker'])
def test_cube_source_leaves_or_attacker_blinks_after_watch_creation(cards,gone):
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    cube=put(s,"Delif's Cube",'battlefield')
    to_phase(s,'main1',turn=4)
    mana(s,C=2)
    act(s,'p1',type='activate_ability',card_id=cube.id,ability=0,targets=[bear.id])
    settle(s)
    if gone=='artifact':
        cast(s,'Naturalize',[cube.id])
    else:
        old=s.state.rules.object_id(bear.id)
        cast(s,'Cloudshift',[bear.id])
        assert s.state.rules.object_id(bear.id)!=old
        cast(s,'Expedite',[bear.id])
    unblocked(s,bear)
    assert s.state.cards[cube.id].counters.get('cube',0)==0
    to_phase(s,'end_combat',turn=4)
    assert s.state.players['p2'].life==(40 if gone=='artifact' else 38)
    roundtrip(s)


@pytest.mark.parametrize('barred',[False,True])
def test_cone_zero_power_cost_is_payable_unless_life_gain_forbidden(cards,barred):
    s=setup(cards)
    attacker=put(s,'Kraken Hatchling','battlefield')
    cone=put(s,"Delif's Cone",'battlefield')
    if barred:
        put(s,'Erebos, God of the Dead','battlefield',pid='p2')
    to_phase(s,'main1',turn=4)
    act(s,'p1',type='activate_ability',card_id=cone.id,ability=0,targets=[attacker.id])
    settle(s)
    unblocked(s,attacker)
    if barred:
        assert s.state.rules.decision is None
    else:
        assert s.state.rules.decision is not None
        pick(s,['yes'])
        settle(s)
    ch=Plan(s.state,'p1',s.cards,None).ch(s.state.cards[attacker.id])
    assert ('assign_none' in ch.imposed) is not barred
    assert s.state.players['p1'].life==40
    roundtrip(s)


def test_farrel_current_controller_choice_resumes_in_fresh_process(cards,tmp_path):
    import subprocess
    import sys
    s=setup(cards)
    bear=put(s,'Grizzly Bears','battlefield',pid='p2')
    victim=put(s,'Baneslayer Angel','battlefield')
    to_phase(s,'main1',turn=4)
    cast(s,"Farrel's Mantle",[bear.id])
    unblocked(s,bear,defender='p3',turn=5,pid='p2')
    pick(s,[victim.id])
    settle(s)
    assert s.state.rules.decision.player=='p2'
    saved=tmp_path/'farrel.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import pick,settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert s.state.rules.decision.player=='p2'
pick(s,['yes'])
settle(s)
assert s.state.cards[sys.argv[3]].damage==4
roundtrip(s)
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),victim.id],capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr
