"""The upkeep player chooses exact card categories; native phasing owns all returns."""
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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

PHOENIX='Phoenix Fleet Airship'
NAMES=['Tek','Tribal Golem',"Bride's Gown","Groom's Finery",'So Tiny','Burden of Proof',PHOENIX]
DATA = json.loads((Path(__file__).parent/'fixtures/compound_statics90_cards.json').read_text())
ALL = [c['name'] for c in DATA]


@pytest.fixture()
def cards(settings):
    base = {c['name']:c for c in fixture_cards()}
    for i,c in enumerate(DATA):
        base[c['name']]=card(c['name'],number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    s=table(cards,[*ALL,*([PHOENIX]*7)],ALL,ALL)
    to_phase(s,'main1',1)
    return s


def cast(s,name,pid='p1',targets=(),**kwargs):
    source=next(c for c in s.state.cards.values() if c.name==name and c.owner==pid and c.zone not in ('stack',pid+':battlefield'))
    act(s,pid,type='move',card_ids=[source.id],to={'zone':'hand','player':pid})
    mana(s,pid,C=20,W=10,U=10,B=10,R=10,G=10)
    wait_priority(s,pid)
    act(s,pid,type='cast_spell',card_id=source.id,targets=list(targets),sources=[],**kwargs)
    settle(s)
    return source


def ch(s,source):
    return Plan.view(s.state,'p1',s.cards).ch(s.state.cards[source.id])


@pytest.mark.parametrize('name',NAMES)
def test_native_canonical_full_whole_cast(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'
    s=game(cards)
    targets=[]
    if name in ('So Tiny','Burden of Proof'):
        targets=[put(s,'Grizzly Bears','battlefield','p2').id]
    source=cast(s,name,targets=targets)
    assert s.state.cards[source.id].zone=='p1:battlefield'
    roundtrip(s)


def test_native_tek_five_independent_current_land_conditions(cards):
    s=game(cards)
    source=cast(s,'Tek')
    assert ch(s,source).pt==(2,2)
    lands=[put(s,n,'battlefield') for n in ('Plains','Island','Swamp','Mountain','Forest')]
    assert ch(s,source).pt==(4,4) and {'flying','first strike','trample'}<=ch(s,source).keywords
    act(s,'p1',type='set_controller',card_ids=[o.id for o in lands],player='p2')
    assert ch(s,source).pt==(2,2) and not {'flying','first strike','trample'}&ch(s,source).keywords
    roundtrip(s)


def test_native_tribal_five_independent_current_creature_conditions(cards):
    s=game(cards)
    source=cast(s,'Tribal Golem')
    species=[put(s,n,'battlefield') for n in ('Leatherback Baloth','Raging Goblin','Elite Vanguard','Prodigal Sorcerer','Walking Corpse')]
    assert {'trample','haste','first strike','flying'}<=ch(s,source).keywords
    assert any(a.kind=='activated' and 'regenerate' in a.text.lower() for a in ch(s,source).abilities)
    act(s,'p1',type='set_controller',card_ids=[o.id for o in species],player='p2')
    assert not {'trample','haste','first strike','flying'}&ch(s,source).keywords
    assert not any(a.kind=='activated' and 'regenerate' in a.text.lower() for a in ch(s,source).abilities)
    roundtrip(s)


def test_native_phoenix_eight_exact_name_permanents_and_control_changes(cards):
    s=game(cards)
    sources=[cast(s,PHOENIX) for _ in range(7)]
    assert all(not ch(s,o).is_creature for o in sources)
    sources.append(cast(s,PHOENIX))
    assert all(ch(s,o).is_creature for o in sources)
    to_phase(s,'main1',2)
    assert all(ch(s,o).is_creature for o in sources)
    act(s,'p1',type='set_controller',card_ids=[sources[-1].id],player='p2')
    assert all(not ch(s,o).is_creature for o in sources)
    roundtrip(s)


def test_native_tek_tracks_actual_land_type_changes(cards):
    s=game(cards)
    source=cast(s,'Tek')
    land=put(s,'Plains','battlefield')
    assert ch(s,source).pt==(2,4)
    aura=cast(s,'Spreading Seas',targets=[land.id])
    assert ch(s,source).pt==(2,2) and 'flying' in ch(s,source).keywords
    cast(s,'Disenchant',targets=[aura.id])
    assert ch(s,source).pt==(2,4) and 'flying' not in ch(s,source).keywords
    roundtrip(s)


def test_native_tribal_granted_regeneration_survives_loss_of_ability(cards):
    from tests.test_rules_activated_copy_family import answer

    s=game(cards)
    source=cast(s,'Tribal Golem')
    zombie=put(s,'Walking Corpse','battlefield')
    ability=next(a for a in ch(s,source).abilities if a.kind=='activated' and 'regenerate' in a.text.lower())
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=ability.index,sources=[])
    answer(s)
    assert s.state.rules.regen_shields.get(s.state.rules.object_id(source.id),0)==1
    cast(s,'Lightning Bolt',targets=[zombie.id])
    assert s.state.cards[zombie.id].zone=='p1:graveyard'
    assert not any(a.kind=='activated' and 'regenerate' in a.text.lower() for a in ch(s,source).abilities)
    cast(s,'Disenchant',targets=[source.id])
    answer(s)
    assert s.state.cards[source.id].zone=='p1:battlefield' and s.state.cards[source.id].tapped
    assert not s.state.rules.regen_shields.get(s.state.rules.object_id(source.id),0)
    roundtrip(s)


def test_native_spouses_equipment_controller_and_host_controller_are_distinct(cards):
    s=game(cards)
    to_phase(s,'main1',2)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    elf=put(s,'Llanowar Elves','battlefield','p2')
    gown=cast(s,"Bride's Gown",pid='p2')
    finery=cast(s,"Groom's Finery",pid='p2')
    for equipment,host in ((gown,bear),(finery,elf)):
        wait_priority(s,'p2')
        act(s,'p2',type='activate_ability',card_id=equipment.id,ability=1,targets=[host.id],sources=[])
        settle(s)
    assert ch(s,bear).pt==(4,4) and 'first strike' in ch(s,bear).keywords
    assert ch(s,elf).pt==(3,3) and 'deathtouch' in ch(s,elf).keywords
    act(s,'p2',type='set_controller',card_ids=[bear.id],player='p1')
    assert ch(s,bear).pt==(4,4) and 'first strike' in ch(s,bear).keywords
    assert ch(s,elf).pt==(3,1) and 'deathtouch' not in ch(s,elf).keywords
    act(s,'p2',type='set_controller',card_ids=[gown.id],player='p1')
    assert ch(s,bear).pt==(4,2) and 'first strike' not in ch(s,bear).keywords
    # Opponent-controlled named Equipment still counts when its host is yours.
    act(s,'p2',type='set_controller',card_ids=[elf.id],player='p1')
    assert ch(s,bear).pt==(4,4) and 'first strike' in ch(s,bear).keywords
    roundtrip(s)


def test_native_so_tiny_tracks_host_graveyard_and_current_controller(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    cast(s,'So Tiny',targets=[bear.id])
    cast(s,'Tome Scour',targets=['p2'])
    assert ch(s,bear).pt==(0,2)
    cast(s,'Thought Scour',targets=['p2'])
    assert ch(s,bear).pt==(-4,2)
    act(s,'p2',type='set_controller',card_ids=[bear.id],player='p1')
    assert ch(s,bear).pt==(0,2)
    act(s,'p1',type='set_controller',card_ids=[bear.id],player='p2')
    assert ch(s,bear).pt==(-4,2)
    roundtrip(s)


def test_native_burden_controller_type_base_and_counter_layers(cards):
    from app.rules import combat

    s=game(cards)
    detective=put(s,'Novice Inspector','battlefield','p2')
    attacker=put(s,'Novice Inspector','battlefield')
    cast(s,'Burden of Proof',targets=[detective.id])
    assert ch(s,detective).pt==(1,1)
    assert combat.block_problem(s.state,s.state.cards[detective.id],ch(s,detective),s.state.cards[attacker.id],ch(s,attacker),s.cards)
    act(s,'p2',type='set_controller',card_ids=[detective.id],player='p1')
    assert ch(s,detective).pt==(3,4)
    assert combat.block_problem(s.state,s.state.cards[detective.id],ch(s,detective),s.state.cards[attacker.id],ch(s,attacker),s.cards) is None
    act(s,'p1',type='counter',card_ids=[detective.id],kind='+1/+1',delta=1)
    assert ch(s,detective).pt==(4,5)
    act(s,'p1',type='set_controller',card_ids=[detective.id],player='p2')
    assert ch(s,detective).pt==(2,2)
    roundtrip(s)


def test_native_phoenix_actual_sacrifice_and_copies_reach_threshold(cards):
    s=game(cards)
    sources=[cast(s,PHOENIX) for _ in range(7)]
    act(s,'p1',type='counter',card_ids=[sources[0].id],kind='+1/+1',delta=2)
    cast(s,'Novice Inspector')
    clue=next(c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and 'Clue' in ch(s,c).subtypes)
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=clue.id,ability=0,sources=[])
    settle(s)
    to_phase(s,'end',1)
    settle(s)
    fleet=[c for c in s.state.cards.values() if c.zone=='p1:battlefield' and ch(s,c).name==PHOENIX]
    assert len(fleet)==14 and all(ch(s,o).is_creature for o in fleet)
    copies=[o for o in fleet if o.is_token]
    assert len(copies)==7 and all(not o.counters for o in copies)
    assert all(any(a.kind=='triggered' and 'create a token' in a.text.lower() for a in ch(s,o).abilities) for o in copies)
    roundtrip(s)


def test_native_burden_rechecks_actual_detective_type_change(cards):
    s=game(cards)
    bear=put(s,'Grizzly Bears','battlefield')
    cast(s,'Burden of Proof',targets=[bear.id])
    assert ch(s,bear).pt==(1,1)
    nexus=cast(s,'Maskwood Nexus')
    assert ch(s,bear).pt==(4,4)
    cast(s,'Disenchant',targets=[nexus.id])
    assert ch(s,bear).pt==(1,1)
    roundtrip(s)


def test_native_burden_forbids_new_detective_block_atomically(cards):
    from app.game.errors import ActionError

    s=game(cards)
    detective=put(s,'Novice Inspector','battlefield')
    bear=put(s,'Grizzly Bears','battlefield','p2')
    cast(s,'Burden of Proof',targets=[bear.id])
    to_phase(s,'declare_attackers',4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':detective.id,'target':'p2'}])
    to_phase(s,'declare_blockers',4)
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':bear.id,'attacker_id':detective.id}])
    assert s.state.model_dump_json()==before
    act(s,'p2',type='declare_blockers',blocks=[])
    to_phase(s,'main2',4)
    assert s.state.players['p2'].life==39
    roundtrip(s)


def test_native_burden_flash_after_blocks_does_not_unblock_detective(cards):
    s=game(cards)
    detective=put(s,'Novice Inspector','battlefield')
    bear=put(s,'Grizzly Bears','battlefield','p2')
    to_phase(s,'declare_attackers',4)
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':detective.id,'target':'p2'}])
    to_phase(s,'declare_blockers',4)
    act(s,'p2',type='declare_blockers',blocks=[{'blocker_id':bear.id,'attacker_id':detective.id}])
    cast(s,'Burden of Proof',targets=[bear.id])
    to_phase(s,'main2',4)
    assert s.state.players['p2'].life==40 and s.state.cards[bear.id].zone=='p2:graveyard'
    assert s.state.cards[detective.id].zone=='p1:battlefield'
    roundtrip(s)


def test_native_phoenix_last_known_copiable_values_after_real_steel_departure(cards):
    s=game(cards)
    sources=[cast(s,PHOENIX) for _ in range(6)]
    steel=cast(s,'Sculpting Steel')
    d=s.state.rules.decision
    assert d
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if sources[0].id in o.id)])
    settle(s)
    assert ch(s,steel).name==PHOENIX
    cast(s,'Novice Inspector')
    clue=next(c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and 'Clue' in ch(s,c).subtypes)
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=clue.id,ability=0,sources=[])
    settle(s)
    for pid in ('p1','p2','p3'):
        act(s,pid,type='set_prefs',hold_priority=True)
    to_phase(s,'end',1)
    d=s.state.rules.decision
    if d and d.kind=='order':
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[o.id for o in d.options])
    cast(s,'Disenchant',targets=[steel.id])
    settle(s)
    assert s.state.cards[steel.id].zone=='p1:graveyard'
    fleet=[c for c in s.state.cards.values() if c.zone=='p1:battlefield' and ch(s,c).name==PHOENIX]
    assert len(fleet)==13 and sum(o.is_token for o in fleet)==7
    assert all(ch(s,o).is_creature for o in fleet)
    roundtrip(s)


@pytest.mark.parametrize('mode',['self','attached','phoenix'])
def test_true_cold_independent_conditional_grants(cards,tmp_path,mode):
    import os
    import subprocess
    import sys

    import app

    s=game(cards)
    meta={'mode':mode}
    if mode=='self':
        meta['tek']=cast(s,'Tek').id
        meta['golem']=cast(s,'Tribal Golem').id
        meta['conditions']=[put(s,n,'battlefield').id for n in (
            'Plains','Island','Swamp','Mountain','Forest','Leatherback Baloth','Raging Goblin','Elite Vanguard','Prodigal Sorcerer','Walking Corpse')]
    elif mode=='phoenix':
        meta['fleet']=[cast(s,PHOENIX).id for _ in range(8)]
    else:
        tiny=put(s,'Grizzly Bears','battlefield','p2')
        cast(s,'So Tiny',targets=[tiny.id])
        cast(s,'Tome Scour',targets=['p2'])
        cast(s,'Thought Scour',targets=['p2'])
        detective=put(s,'Novice Inspector','battlefield')
        cast(s,'Burden of Proof',targets=[detective.id])
        bear=put(s,'Grizzly Bears','battlefield')
        elf=put(s,'Llanowar Elves','battlefield')
        for name,host in (("Bride's Gown",bear),("Groom's Finery",elf)):
            equipment=cast(s,name)
            wait_priority(s,'p1')
            act(s,'p1',type='activate_ability',card_id=equipment.id,ability=1,targets=[host.id],sources=[])
            settle(s)
        meta.update(tiny=tiny.id,detective=detective.id,bear=bear.id,elf=elf.id)
    saved=tmp_path/'statics90.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
m=json.loads(sys.argv[3])
def ch(cid):return Plan.view(s.state,'p1',repo).ch(s.state.cards[cid])
if m['mode']=='self':
 assert ch(m['tek']).pt==(4,4) and {'flying','first strike','trample'}<=ch(m['tek']).keywords
 assert {'trample','haste','first strike','flying'}<=ch(m['golem']).keywords
 assert any(a.kind=='activated' and 'regenerate' in a.text.lower() for a in ch(m['golem']).abilities)
 act(s,'p1',type='set_controller',card_ids=m['conditions'],player='p2')
 assert ch(m['tek']).pt==(2,2) and not {'flying','first strike','trample'}&ch(m['tek']).keywords
 assert not {'trample','haste','first strike','flying'}&ch(m['golem']).keywords
 assert not any(a.kind=='activated' and 'regenerate' in a.text.lower() for a in ch(m['golem']).abilities)
elif m['mode']=='phoenix':
 assert all(ch(cid).is_creature for cid in m['fleet'])
 act(s,'p1',type='set_controller',card_ids=[m['fleet'][-1]],player='p2')
 assert all(not ch(cid).is_creature for cid in m['fleet'])
else:
 assert ch(m['tiny']).pt==(-4,2) and ch(m['detective']).pt==(3,4)
 assert ch(m['bear']).pt==(4,4) and 'first strike' in ch(m['bear']).keywords
 assert ch(m['elf']).pt==(3,3) and 'deathtouch' in ch(m['elf']).keywords
 act(s,'p2',type='set_controller',card_ids=[m['tiny']],player='p1')
 act(s,'p1',type='set_controller',card_ids=[m['detective'],m['bear']],player='p2')
 assert ch(m['tiny']).pt==(0,2) and ch(m['detective']).pt==(1,1)
 assert ch(m['bear']).pt==(4,4) and ch(m['elf']).pt==(3,1)
 assert 'deathtouch' not in ch(m['elf']).keywords
roundtrip(s);repo.close()
'''
    backend=Path(app.__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),json.dumps(meta)],cwd=backend,
                          env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr
