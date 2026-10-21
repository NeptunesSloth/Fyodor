"""Unimported delayed-blink recipes through native choice, exile and delayed return."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests import test_rules_wave38d_companion as companion
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate([*json.loads((Path(__file__).parent/'fixtures'/'exile_outcomes42_cards.json').read_text()),*json.loads((Path(__file__).parent/'fixtures'/'exile_cast_outcomes45_cards.json').read_text()),*json.loads((Path(__file__).parent/'fixtures'/'delayed_blinks50_cards.json').read_text())]):
        base[c['name']]=card(c['name'],set_code='bl50',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()




def test_yorion_native_resolution_choice_own_and_control_nonland_then_exact_return(cards):
    s=gameplay.setup(cards,'Yorion, Sky Nomad','Forest')
    own=put(s,'Grizzly Bears','battlefield')
    foreign=put(s,'Grizzly Bears','battlefield',pid='p2')
    act(s,'p1',type='set_controller',card_ids=[foreign.id],player='p1')
    land=put(s,'Forest','battlefield')
    stolen=put(s,"Ashnod's Altar",'battlefield')
    act(s,'p1',type='set_controller',card_ids=[stolen.id],player='p2')
    cast(s,'Yorion, Sky Nomad')
    d=s.state.rules.decision
    assert d.resume['step']=='sacrifice_choice'
    ids=[o.id for o in d.options]
    assert own.id in ids and foreign.id not in ids and land.id not in ids and stolen.id not in ids
    assert not any(s.state.cards[c].name=='Yorion, Sky Nomad' for c in ids)
    old=s.state.rules.object_id(own.id)
    answer(s,[own.id])
    assert s.state.cards[own.id].zone=='p1:exile'
    assert len(s.state.rules.delayed)==1
    to_phase(s,'end',turn=1)
    from tests.test_rules_library_look import settle
    settle(s)
    assert s.state.cards[own.id].zone=='p1:battlefield'
    assert s.state.rules.object_id(own.id)!=old
    roundtrip(s)


def test_yorion_zero_choice_creates_no_return_of_unselected_objects(cards):
    from tests.test_rules_library_look import settle

    s=gameplay.setup(cards,'Yorion, Sky Nomad')
    own=put(s,'Grizzly Bears','battlefield')
    old=s.state.rules.object_id(own.id)
    cast(s,'Yorion, Sky Nomad')
    answer(s,[])
    to_phase(s,'end',turn=1)
    settle(s)
    assert s.state.cards[own.id].zone=='p1:battlefield'
    assert s.state.rules.object_id(own.id)==old
    roundtrip(s)


def test_yorion_return_survives_source_departure_but_not_new_exile_incarnation(cards):
    from tests.test_rules_library_look import settle

    s=gameplay.setup(cards,'Yorion, Sky Nomad','Murder')
    own=put(s,'Grizzly Bears','battlefield')
    cast(s,'Yorion, Sky Nomad')
    source=next(c for c in s.state.cards.values() if c.name=='Yorion, Sky Nomad' and c.zone=='p1:battlefield')
    answer(s,[own.id])
    cast(s,'Murder',targets=[source.id])
    act(s,'p1',type='move',card_ids=[own.id],to={'zone':'hand','player':'p1'})
    act(s,'p1',type='move',card_ids=[own.id],to={'zone':'exile','player':'p1'})
    to_phase(s,'end',turn=1)
    settle(s)
    assert s.state.cards[own.id].zone=='p1:exile'
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_nahiri_native_endstep_choice_returns_foreign_owned_card_to_owner_at_original_next_upkeep(cards):
    from tests.test_rules_library_look import settle

    s=gameplay.setup(cards,"Nahiri's Resolve")
    source=put(s,"Nahiri's Resolve",'battlefield')
    foreign=put(s,'Grizzly Bears','battlefield',pid='p2')
    act(s,'p1',type='set_controller',card_ids=[foreign.id],player='p1')
    to_phase(s,'end',turn=1)
    settle(s)
    d=s.state.rules.decision
    assert d.resume['step']=='sacrifice_choice'
    assert foreign.id in [o.id for o in d.options]
    answer(s,[foreign.id])
    assert s.state.cards[foreign.id].zone=='p2:exile'
    act(s,'p1',type='move',card_ids=[source.id],to={'zone':'graveyard','player':'p1'})
    to_phase(s,'upkeep',turn=2)
    settle(s)
    assert s.state.cards[foreign.id].zone=='p2:exile'
    to_phase(s,'upkeep',turn=4)
    settle(s)
    assert s.state.cards[foreign.id].zone=='p2:battlefield'
    assert s.state.cards[foreign.id].controller=='p2'
    roundtrip(s)


def test_sudden_native_one_player_all_nonlands_foreign_owner_return_and_lands_stay(cards):
    from tests.test_rules_library_look import settle

    s=gameplay.setup(cards,'Sudden Disappearance')
    own=put(s,'Grizzly Bears','battlefield')
    foreign=put(s,"Ashnod's Altar",'battlefield',pid='p2')
    act(s,'p1',type='set_controller',card_ids=[foreign.id],player='p1')
    land=put(s,'Forest','battlefield')
    opponent=put(s,'Grizzly Bears','battlefield',pid='p2')
    cast(s,'Sudden Disappearance',targets=['p1'])
    assert s.state.cards[own.id].zone=='p1:exile'
    assert s.state.cards[foreign.id].zone=='p2:exile'
    assert s.state.cards[land.id].zone=='p1:battlefield'
    assert s.state.cards[opponent.id].zone=='p2:battlefield'
    to_phase(s,'end',turn=1)
    settle(s)
    assert s.state.cards[own.id].zone=='p1:battlefield'
    assert s.state.cards[foreign.id].zone=='p2:battlefield'
    assert s.state.cards[foreign.id].controller=='p2'
    roundtrip(s)


def test_roll_native_saga_four_chapters_returns_land_and_sacrifices_source_before_fourth_return(cards):
    from tests.test_rules_library_look import settle

    s=gameplay.setup(cards,'Roll-Roll-Roll-Roll')
    land=put(s,'Forest','battlefield')
    source=put(s,'Roll-Roll-Roll-Roll','hand')
    from tests.test_rules_bandmate_references import mana
    mana(s,U=1,C=1)
    act(s,'p1',type='cast_spell',card_id=source.id)
    settle(s)
    for turn in (1,4,7,10):
        if turn!=1:
            to_phase(s,'main1',turn=turn)
            settle(s)
        d=s.state.rules.decision
        assert d.resume['step']=='trigger_group'
        answer(s,[land.id])
        assert s.state.cards[land.id].zone=='p1:exile'
        to_phase(s,'end',turn=turn)
        settle(s)
        assert s.state.cards[land.id].zone=='p1:battlefield'
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_yorion_source_gone_real_card_returns_token_ceases_and_counters_reset(cards):
    from tests.test_rules_library_look import settle

    s=gameplay.setup(cards,'Yorion, Sky Nomad','Murder')
    own=put(s,'Grizzly Bears','battlefield')
    act(s,'p1',type='counter',card_ids=[own.id],kind='+1/+1',delta=2)
    act(s,'p1',type='create_token',player='p1',token={'name':'Blink Soldier','type_line':'Token Creature — Soldier','power':'1','toughness':'1','text':''})
    token=next(c for c in s.state.cards.values() if c.name=='Blink Soldier')
    cast(s,'Yorion, Sky Nomad')
    source=next(c for c in s.state.cards.values() if c.name=='Yorion, Sky Nomad' and c.zone=='p1:battlefield')
    answer(s,[own.id,token.id])
    cast(s,'Murder',targets=[source.id])
    to_phase(s,'end',turn=1)
    settle(s)
    assert s.state.cards[own.id].zone=='p1:battlefield'
    assert not s.state.cards[own.id].counters
    assert not any(c.name=='Blink Soldier' and c.zone.endswith(':battlefield') for c in s.state.cards.values())
    roundtrip(s)


def test_sudden_countered_delayed_ability_never_retries(cards):
    from tests.test_rules_library_look import settle

    s=gameplay.setup(cards,'Sudden Disappearance','Stifle')
    own=put(s,'Grizzly Bears','battlefield')
    cast(s,'Sudden Disappearance',targets=['p1'])
    to_phase(s,'end',turn=1)
    delayed=next(k for k,e in s.state.rules.stack.items() if e.kind=='trigger')
    cast(s,'Stifle',targets=[delayed])
    assert s.state.cards[own.id].zone=='p1:exile'
    to_phase(s,'end',turn=2)
    settle(s)
    assert s.state.cards[own.id].zone=='p1:exile'
    assert not s.state.rules.delayed
    roundtrip(s)


def test_nahiri_static_real_haste_attack_and_plus_one_power(cards):
    s=gameplay.setup(cards,"Nahiri's Resolve")
    put(s,"Nahiri's Resolve",'battlefield')
    bear=put(s,'Grizzly Bears','battlefield')
    to_phase(s,'declare_attackers',turn=1)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':bear.id,'target':'p2'}])
    to_phase(s,'main2',turn=1)
    assert s.state.players['p2'].life==37
    roundtrip(s)


def test_yorion_flying_actual_block_legality_and_combat_damage(cards):
    from app.game.errors import ActionError

    s=gameplay.setup(cards,'Yorion, Sky Nomad')
    blocker=put(s,'Grizzly Bears','battlefield',pid='p2')
    cast(s,'Yorion, Sky Nomad')
    if s.state.rules.decision is not None:
        answer(s,[])
    source=next(c for c in s.state.cards.values() if c.name=='Yorion, Sky Nomad' and c.zone=='p1:battlefield')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    to_phase(s,'declare_blockers',turn=4)
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':blocker.id,'attacker_id':source.id}])
    assert s.state.model_dump_json()==before
    act(s,'p2',type='declare_blockers',blocks=[])
    to_phase(s,'main2',turn=4)
    assert s.state.players['p2'].life==36
    roundtrip(s)


def test_nahiri_choice_includes_noncreature_artifact_excludes_token_land_and_foreign_control(cards):
    from tests.test_rules_library_look import settle

    s=gameplay.setup(cards,"Nahiri's Resolve")
    put(s,"Nahiri's Resolve",'battlefield')
    artifact=put(s,"Ashnod's Altar",'battlefield')
    land=put(s,'Forest','battlefield')
    foreign=put(s,'Grizzly Bears','battlefield',pid='p2')
    act(s,'p1',type='create_token',player='p1',token={'name':'Nahiri Soldier','type_line':'Token Creature — Soldier','power':'1','toughness':'1','text':''})
    token=next(c for c in s.state.cards.values() if c.name=='Nahiri Soldier')
    to_phase(s,'end',turn=1)
    settle(s)
    ids=[o.id for o in s.state.rules.decision.options]
    assert artifact.id in ids
    assert not set(ids)&{token.id,land.id,foreign.id}
    answer(s,[])
    assert not s.state.rules.delayed
    assert s.state.cards[artifact.id].zone=='p1:battlefield'
    roundtrip(s)



def test_yorion_native_companion_deck_validation(cards):
    companion.test_yorion_can_never_be_a_commander_companion(cards)


@pytest.mark.parametrize('command',[False,True])
def test_yorion_native_commander_exile_choice_old_exile_ref_only(cards,command):
    from tests.test_rules_library_look import settle

    s=gameplay.setup(cards,'Yorion, Sky Nomad')
    commander=put(s,'Krenko, Mob Boss','battlefield')
    cast(s,'Yorion, Sky Nomad')
    answer(s,[commander.id])
    assert 'commander' in s.state.rules.decision.resume['step']
    answer(s,['yes' if command else 'no'])
    assert s.state.cards[commander.id].zone==('p1:command' if command else 'p1:exile')
    to_phase(s,'end',turn=1)
    settle(s)
    assert s.state.cards[commander.id].zone==('p1:command' if command else 'p1:battlefield')
    roundtrip(s)


@pytest.mark.parametrize('choose_target',[False,True])
def test_roll_zero_or_illegal_target_does_not_create_a_delayed_return(cards,choose_target):
    from tests.test_rules_library_look import settle

    s=gameplay.setup(cards,'Roll-Roll-Roll-Roll','Murder')
    bear=put(s,'Grizzly Bears','battlefield')
    cast(s,'Roll-Roll-Roll-Roll')
    d=s.state.rules.decision
    assert d.resume['step']=='trigger_group'
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear.id] if choose_target else [])
    if choose_target:
        cast(s,'Murder',targets=[bear.id])
    settle(s)
    assert not s.state.rules.delayed
    assert s.state.cards[bear.id].zone==('p1:graveyard' if choose_target else 'p1:battlefield')
    roundtrip(s)


def test_staged_blink_four_complete_canonical_coverage(cards):
    from app.rules import coverage

    for name in ('Yorion, Sky Nomad',"Nahiri's Resolve",'Roll-Roll-Roll-Roll','Sudden Disappearance'):
        result=coverage.of_card_data(cards.resolve(name))
        assert result.level=='FULL',(name,result)


def test_yorion_old_etb_after_actual_ephemerate_can_choose_new_source_incarnation(cards):
    from tests.test_rules_bandmate_references import mana

    s=gameplay.setup(cards,'Yorion, Sky Nomad','Ephemerate')
    bear=put(s,'Grizzly Bears','battlefield')
    source=put(s,'Yorion, Sky Nomad','hand')
    mana(s,W=2,U=1,C=4)
    act(s,'p1',type='cast_spell',card_id=source.id)
    while s.state.cards[source.id].zone!='p1:battlefield':
        act(s,s.state.rules.priority,type='pass_priority')
    old=s.state.rules.object_id(source.id)
    cast(s,'Ephemerate',targets=[source.id])
    assert s.state.rules.object_id(source.id)!=old
    d=s.state.rules.decision
    assert source.id not in [o.id for o in d.options]
    answer(s,[])
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='sacrifice_choice'
    assert source.id in [o.id for o in d.options]
    answer(s,[source.id])
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.cards[bear.id].zone=='p1:battlefield'
    roundtrip(s)
