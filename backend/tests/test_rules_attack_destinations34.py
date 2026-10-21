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
from app.rules.sba import power
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import cast, start
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/attack_destinations34_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="atd34", number=str(i), **{k: v for k, v in c.items() if k != "name"}
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
            (Path(__file__).parent / "fixtures/attack_destinations34_cards.json").read_text()
        )
    ]
    return table(cards, names, names, names)


@pytest.mark.parametrize('grouped',[False,True])
def test_independent_requirements_survive_projection(cards,grouped):

    s=setup(cards)
    source=put(s,'Bident of Thassa','battlefield')
    put(s,'Silent Arbiter','battlefield')
    if grouped:
        put(s,'Mogg Flunkies','battlefield',pid='p2')
    a=put(s,'Grizzly Bears','battlefield',pid='p2')
    b=put(s,'Runeclaw Bear','battlefield',pid='p2')
    start(s,turn=2)
    while s.state.rules.priority!='p1':
        act(s,s.state.rules.priority,type='pass_priority')
    mana(s,U=1,C=1)
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    settle(s)
    cast(s,'Incite',[a.id])
    roundtrip(s)
    to_phase(s,'declare_attackers',turn=2)
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_attackers',attackers=[{'card_id':b.id,'target':'p1'}])
    act(s,'p2',type='declare_attackers',attackers=[{'card_id':a.id,'target':'p1'}])
    assert s.state.cards[a.id].attacking.id=='p1'
    roundtrip(s)


NAMES = ['Ravener','Dulcet Sirens','Public Enemy','Galactus, Devourer of Worlds','Ursine Monstrosity','Trench Behemoth',"Silver Surfer, Galactus's Herald","The Brothers' War",'Gideon Jura','Furygale Flocking']

@pytest.mark.parametrize('name',NAMES)
def test_canonical_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def declare(s,attacker,target,pid='p2'):
    act(s,pid,type='declare_attackers',attackers=[{'card_id':attacker.id,'target':target}])


def assert_destination(s,attacker,wanted,turn=2,pid='p2',wrong='p3'):
    to_phase(s,'declare_attackers',turn=turn)
    with pytest.raises(ActionError):
        act(s,pid,type='declare_attackers',attackers=[])
    if wrong is not None:
        with pytest.raises(ActionError):
            declare(s,attacker,wrong,pid)
    declare(s,attacker,wanted,pid)
    assert s.state.cards[attacker.id].attacking.id==wanted
    roundtrip(s)


@pytest.mark.parametrize('name',['Dulcet Sirens','Ravener'])
def test_two_targets_real_activation_or_etb(cards,name):
    s=setup(cards)
    victim=put(s,'Grizzly Bears','battlefield',pid='p2')
    source=put(s,name,'battlefield') if name=='Dulcet Sirens' else None
    if source is not None:
        put(s,'Fervor','battlefield')
    start(s,turn=2)
    if source is not None:
        while s.state.rules.priority!='p1':
            act(s,s.state.rules.priority,type='pass_priority')
        mana(s,U=1)
        act(s,'p1',type='activate_ability',card_id=source.id,ability=0,targets=[victim.id,'p3'],target_counts=[1,1])
        settle(s)
    else:
        c=put(s,name,'hand')
        while s.state.rules.priority!='p1':
            act(s,s.state.rules.priority,type='pass_priority')
        mana(s,U=1,G=1,C=1)
        act(s,'p1',type='cast_spell',card_id=c.id,x_value=1)
        settle(s)
        pick(s,[victim.id])
        pick(s,['p3'])
        settle(s)
    assert_destination(s,victim,'p3',wrong='p1')


def test_public_enemy_uses_host_current_controller(cards):
    s=setup(cards)
    host=put(s,'Runeclaw Bear','battlefield',pid='p1')
    victim=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s,turn=1)
    cast(s,'Public Enemy',[host.id])
    act(s,'p1',type='set_controller',card_ids=[host.id],player='p3')
    assert_destination(s,victim,'p3',wrong='p1')


@pytest.mark.parametrize('exception',[False,True])
def test_galactus_current_most_life_and_named_exception(cards,exception):
    s=setup(cards)
    giant=put(s,'Galactus, Devourer of Worlds','battlefield',pid='p2')
    if exception:
        put(s,"Silver Surfer, Galactus's Herald",'battlefield',pid='p2')
    start(s,turn=2)
    act(s,'p1',type='set_life',player='p1',value=45)
    act(s,'p1',type='set_life',player='p3',value=46)
    to_phase(s,'declare_attackers',turn=2)
    if exception:
        act(s,'p2',type='declare_attackers',attackers=[])
        assert s.state.cards[giant.id].attacking is None
        roundtrip(s)
    else:
        with pytest.raises(ActionError):
            declare(s,giant,'p1')
        declare(s,giant,'p3')
        assert s.state.cards[giant.id].attacking.id=='p3'
        roundtrip(s)


def test_ursine_real_trigger_random_destination_mill_and_snapshot_pump(cards):
    s=setup(cards)
    creature=put(s,'Ursine Monstrosity','battlefield')
    put(s,'Forest','graveyard')
    start(s,turn=4)
    to_phase(s,'begin_combat',turn=4)
    settle(s)
    ch=Plan(s.state,'p1',s.cards,None).ch(s.state.cards[creature.id])
    assert 'indestructible' in ch.keywords
    assert power(s.state.cards[creature.id],ch)>=4
    destinations=[r.split(':',1)[1] for r in ch.imposed if r.startswith('attack_player:')]
    assert len(destinations)==1 and destinations[0] in ('p2','p3')
    assert_destination(s,creature,destinations[0],turn=4,pid='p1',wrong='p3' if destinations[0]=='p2' else 'p2')


def test_furygale_tokens_have_separate_destinations_and_haste(cards):
    s=setup(cards)
    start(s)
    cast(s,'Furygale Flocking')
    tokens=[c for c in s.state.cards.values() if c.token and c.zone.endswith(':battlefield') and c.name=='Elemental']
    assert len(tokens)==4
    targets={}
    p=Plan(s.state,'p1',s.cards,None)
    for token in tokens:
        ch=p.ch(token)
        assert {'flying','haste'}<=ch.keywords
        targets[token.id]=next(r.split(':',1)[1] for r in ch.imposed if r.startswith('attack_player:'))
    assert sorted(targets.values())==['p2','p2','p3','p3']
    to_phase(s,'declare_attackers',turn=4)
    with pytest.raises(ActionError):
        act(s,'p1',type='declare_attackers',attackers=[])
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':cid,'target':target} for cid,target in targets.items()])
    roundtrip(s)


def test_gideon_next_opponent_turn_exact_planeswalker(cards):
    s=setup(cards)
    gideon=put(s,'Gideon Jura','battlefield')
    victim=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s,turn=1)
    act(s,'p1',type='set_counter',card_id=gideon.id,kind='loyalty',value=6)
    act(s,'p1',type='activate_ability',card_id=gideon.id,ability=0,targets=['p2'],target_counts=[1])
    settle(s)
    pending=[e for e in s.state.rules.effects if e.declaration_window=='next_turn']
    assert len(pending)==1 and pending[0].declaration_player=='p2'
    roundtrip(s)
    assert_destination(s,victim,gideon.id,wrong='p1')


def test_trench_next_actual_combat_survives_source_leaving(cards):
    s=setup(cards)
    trench=put(s,'Trench Behemoth','battlefield')
    victim=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s,turn=1)
    land=put(s,'Forest','hand')
    act(s,'p1',type='play_land',card_id=land.id)
    settle(s)
    pick(s,[victim.id])
    settle(s)
    assert any(e.declaration_window=='next_combat' and e.declaration_player=='p2' for e in s.state.rules.effects)
    act(s,'p1',type='move',card_ids=[trench.id],to={'zone':'graveyard','player':'p1'})
    roundtrip(s)
    to_phase(s,'declare_attackers',turn=2)
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_attackers',attackers=[])
    declare(s,victim,'p3')
    assert s.state.cards[victim.id].attacking.id=='p3'
    roundtrip(s)


def test_brothers_war_two_players_attack_each_other_dynamic_entrants(cards):
    s=setup(cards)
    victim=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s,turn=1)
    cast(s,"The Brothers' War")
    assert len([c for c in s.state.cards.values() if c.token and c.name=='Powerstone'])==2
    to_phase(s,'main1',turn=4)
    settle(s)
    pick(s,['p2'])
    pick(s,['p3'])
    settle(s)
    bounded=[e for e in s.state.rules.effects if e.duration=='next_turn']
    assert len(bounded)==2 and all(e.until_player=='p1' and e.turn==4 for e in bounded)
    saga=next(c for c in s.state.cards.values() if c.name=="The Brothers' War" and c.zone.endswith(':battlefield'))
    act(s,'p1',type='move',card_ids=[saga.id],to={'zone':'graveyard','player':'p1'})
    late=put(s,'Runeclaw Bear','battlefield',pid='p2')
    to_phase(s,'declare_attackers',turn=5)
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_attackers',attackers=[{'card_id':victim.id,'target':'p1'},{'card_id':late.id,'target':'p3'}])
    act(s,'p2',type='declare_attackers',attackers=[{'card_id':victim.id,'target':'p3'},{'card_id':late.id,'target':'p3'}])
    assert s.state.cards[victim.id].attacking.id=='p3'
    to_phase(s,'main1',turn=7)
    ch=Plan(s.state,'p1',s.cards,None).ch(s.state.cards[victim.id])
    assert not any(rule.startswith('attack_player:') for rule in ch.imposed)
    roundtrip(s)


def test_silver_surfer_damage_binds_damaged_player_until_next_turn_end(cards):
    from tests.test_rules_wave30p_combat import attack

    s=setup(cards)
    surfer=put(s,"Silver Surfer, Galactus's Herald",'battlefield')
    victim=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s,turn=4)
    to_phase(s,'declare_attackers',turn=4)
    attack(s,(surfer,'p3'))
    to_phase(s,'combat_damage',turn=4)
    settle(s)
    pick(s,[victim.id])
    settle(s)
    bounded=[e for e in s.state.rules.effects if e.duration=='end_of_next_turn' and 'attack_player:p3' in e.imposes]
    assert len(bounded)==1 and bounded[0].until_player=='p1' and bounded[0].turn==4
    assert_destination(s,victim,'p3',turn=5,wrong='p1')
    to_phase(s,'main1',turn=7)
    ch=Plan(s.state,'p1',s.cards,None).ch(s.state.cards[victim.id])
    assert 'attack_player:p3' in ch.imposed
    to_phase(s,'main1',turn=8)
    ch=Plan(s.state,'p2',s.cards,None).ch(s.state.cards[victim.id])
    assert 'attack_player:p3' not in ch.imposed
    roundtrip(s)


@pytest.mark.parametrize('static_source',[False,True])
def test_static_or_printed_requirement_adds_to_external_requirement(cards,static_source):
    s=setup(cards)
    bident=put(s,'Bident of Thassa','battlefield')
    put(s,'Silent Arbiter','battlefield')
    a=put(s,'Grizzly Bears' if static_source else 'Juggernaut','battlefield',pid='p2')
    b=put(s,'Runeclaw Bear','battlefield',pid='p2')
    start(s,turn=1)
    if static_source:
        cast(s,'Bloodshed Fever',[a.id])
    to_phase(s,'main1',turn=2)
    while s.state.rules.priority!='p1':
        act(s,s.state.rules.priority,type='pass_priority')
    mana(s,U=1,C=1)
    act(s,'p1',type='activate_ability',card_id=bident.id,ability=1)
    settle(s)
    to_phase(s,'declare_attackers',turn=2)
    with pytest.raises(ActionError):
        declare(s,b,'p1')
    declare(s,a,'p1')
    roundtrip(s)


@pytest.mark.parametrize('impossibility',['tax','pacifism'])
def test_destination_does_not_force_cost_or_break_restriction(cards,impossibility):
    s=setup(cards)
    sirens=put(s,'Dulcet Sirens','battlefield')
    victim=put(s,'Grizzly Bears','battlefield',pid='p2')
    put(s,'Fervor','battlefield')
    if impossibility=='tax':
        prison=put(s,'Ghostly Prison','battlefield',pid='p3')
        assert prison.controller=='p3'
    start(s,turn=1)
    if impossibility=='pacifism':
        cast(s,'Pacifism',[victim.id])
    to_phase(s,'main1',turn=2)
    while s.state.rules.priority!='p1':
        act(s,s.state.rules.priority,type='pass_priority')
    mana(s,U=1)
    act(s,'p1',type='activate_ability',card_id=sirens.id,ability=0,targets=[victim.id,'p3'],target_counts=[1,1])
    settle(s)
    to_phase(s,'declare_attackers',turn=2)
    if s.state.rules.decision is not None:
        act(s,'p2',type='declare_attackers',attackers=[])
    else:
        assert s.state.rules.no_attackers
    assert s.state.cards[victim.id].attacking is None
    roundtrip(s)


@pytest.mark.parametrize('change',['other_controller','lose_abilities'])
def test_galactus_requirement_belongs_to_current_ability(cards,change):
    s=setup(cards)
    giant=put(s,'Galactus, Devourer of Worlds','battlefield',pid='p2')
    start(s,turn=2)
    if change=='lose_abilities':
        cast(s,'Humble',[giant.id])
        to_phase(s,'declare_attackers',turn=2)
        act(s,'p2',type='declare_attackers',attackers=[])
    else:
        # A stolen Herald under a different controller is no exception.
        put(s,"Silver Surfer, Galactus's Herald",'battlefield',pid='p3')
        to_phase(s,'declare_attackers',turn=2)
        with pytest.raises(ActionError):
            act(s,'p2',type='declare_attackers',attackers=[])
        declare(s,giant,'p1')
    roundtrip(s)


def test_trench_expires_after_one_combat_not_the_whole_turn(cards):
    s=setup(cards)
    put(s,'Trench Behemoth','battlefield')
    victim=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s,turn=1)
    land=put(s,'Forest','hand')
    act(s,'p1',type='play_land',card_id=land.id)
    settle(s)
    pick(s,[victim.id])
    settle(s)
    to_phase(s,'declare_attackers',turn=2)
    declare(s,victim,'p3')
    to_phase(s,'main2',turn=2)
    cast(s,'Relentless Assault',pid='p2')
    to_phase(s,'declare_attackers',turn=2)
    act(s,'p2',type='declare_attackers',attackers=[])
    roundtrip(s)


def test_gideon_blink_is_not_the_old_required_planeswalker(cards):
    s=setup(cards)
    gideon=put(s,'Gideon Jura','battlefield')
    victim=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s,turn=1)
    act(s,'p1',type='set_counter',card_id=gideon.id,kind='loyalty',value=6)
    act(s,'p1',type='activate_ability',card_id=gideon.id,ability=0,targets=['p2'],target_counts=[1])
    settle(s)
    old=s.state.rules.object_id(gideon.id)
    act(s,'p1',type='move',card_ids=[gideon.id],to={'zone':'exile','player':'p1'})
    act(s,'p1',type='move',card_ids=[gideon.id],to={'zone':'battlefield','player':'p1'})
    assert s.state.rules.object_id(gideon.id)!=old
    to_phase(s,'declare_attackers',turn=2)
    act(s,'p2',type='declare_attackers',attackers=[])
    assert s.state.cards[victim.id].attacking is None
    roundtrip(s)


def test_destination_and_future_phase_resume_in_fresh_process(cards,tmp_path):
    import subprocess
    import sys

    s=setup(cards)
    put(s,'Trench Behemoth','battlefield')
    victim=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s,turn=1)
    land=put(s,'Forest','hand')
    act(s,'p1',type='play_land',card_id=land.id)
    settle(s)
    assert s.state.rules.decision is not None
    saved=tmp_path/'attack-window.json'
    saved.write_text(s.state.model_dump_json())
    code='''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import pick,settle,roundtrip
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_attack_destinations34 import declare
from app.game.errors import ActionError
from tests.game_helpers import act
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
pick(s,[sys.argv[3]])
settle(s)
to_phase(s,'declare_attackers',turn=2)
try:
 act(s,'p2',type='declare_attackers',attackers=[])
except ActionError:
 pass
else:
 raise AssertionError('saved next-combat requirement disappeared')
declare(s,s.state.cards[sys.argv[3]],'p3')
roundtrip(s)
repo.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),victim.id],capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr


def test_two_target_opponent_can_be_the_creatures_controller(cards):
    s=setup(cards)
    sirens=put(s,'Dulcet Sirens','battlefield')
    victim=put(s,'Grizzly Bears','battlefield',pid='p2')
    put(s,'Fervor','battlefield')
    start(s,turn=2)
    while s.state.rules.priority!='p1':
        act(s,s.state.rules.priority,type='pass_priority')
    mana(s,U=1)
    act(s,'p1',type='activate_ability',card_id=sirens.id,ability=0,targets=[victim.id,'p2'],target_counts=[1,1])
    settle(s)
    to_phase(s,'declare_attackers',turn=2)
    act(s,'p2',type='declare_attackers',attackers=[])
    assert s.state.cards[victim.id].attacking is None
    roundtrip(s)


def test_public_enemy_external_rule_survives_affected_creatures_ability_loss(cards):
    s=setup(cards)
    host=put(s,'Runeclaw Bear','battlefield',pid='p3')
    victim=put(s,'Grizzly Bears','battlefield',pid='p2')
    start(s,turn=1)
    cast(s,'Public Enemy',[host.id])
    to_phase(s,'main1',turn=2)
    cast(s,'Humble',[victim.id])
    assert_destination(s,victim,'p3',wrong='p1')


def test_destination_exact_target_does_not_follow_blink(cards):
    s=setup(cards)
    sirens=put(s,'Dulcet Sirens','battlefield')
    victim=put(s,'Grizzly Bears','battlefield',pid='p2')
    put(s,'Fervor','battlefield')
    start(s,turn=2)
    while s.state.rules.priority!='p1':
        act(s,s.state.rules.priority,type='pass_priority')
    mana(s,U=1)
    act(s,'p1',type='activate_ability',card_id=sirens.id,ability=0,targets=[victim.id,'p3'],target_counts=[1,1])
    settle(s)
    old=s.state.rules.object_id(victim.id)
    act(s,'p2',type='move',card_ids=[victim.id],to={'zone':'exile','player':'p2'})
    act(s,'p2',type='move',card_ids=[victim.id],to={'zone':'battlefield','player':'p2'})
    assert s.state.rules.object_id(victim.id)!=old
    to_phase(s,'declare_attackers',turn=2)
    # The new object is also summoning sick, but critically carries no old requirement.
    ch=Plan(s.state,'p2',s.cards,None).ch(s.state.cards[victim.id])
    assert not any(rule.startswith('attack_player:') for rule in ch.imposed)
    if s.state.rules.decision is not None:
        act(s,'p2',type='declare_attackers',attackers=[])
    roundtrip(s)
