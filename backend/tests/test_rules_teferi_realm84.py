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

REALM = "Teferi's Realm"
DATA = json.loads((Path(__file__).parent/'fixtures/teferi_realm84_cards.json').read_text())
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
    s=table(cards,ALL,ALL,ALL)
    to_phase(s,'main1',1)
    return s


def cast(s,name,pid='p1',targets=(),**kwargs):
    source=put(s,name,'hand',pid)
    mana(s,pid,C=20,W=10,U=10,G=10)
    wait_priority(s,pid)
    act(s,pid,type='cast_spell',card_id=source.id,targets=list(targets),sources=[],**kwargs)
    settle(s)
    return source


def choice(s,value):
    d=s.state.rules.decision
    assert d and d.player=='p2' and {o.id for o in d.options}=={'Artifact','Creature','Land','Non-Aura enchantment'}
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[value])
    settle(s)


def test_realm_whole_cast_and_canonical_native_definition(cards):
    assert coverage.of_card_data(cards.resolve(REALM)).level=='FULL'
    s=game(cards)
    source=cast(s,REALM)
    assert source.zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('category',['Artifact','Creature','Land','Non-Aura enchantment'])
def test_native_realm_selects_all_players_nontokens_of_exact_category(cards,category):
    s=game(cards)
    source=cast(s,REALM)
    ring1=put(s,'Sol Ring','battlefield')
    ring2=put(s,'Sol Ring','battlefield','p2')
    bear=put(s,'Grizzly Bears','battlefield','p2')
    memnite=put(s,'Memnite','battlefield','p3')
    forest=put(s,'Forest','battlefield')
    island=put(s,'Island','battlefield','p2')
    anthem=put(s,'Glorious Anthem','battlefield','p2')
    aura=cast(s,'Rancor',targets=[bear.id])
    cast(s,'Servo Exhibition')
    tokens=[c.id for c in s.state.cards.values() if c.token is not None and c.zone.endswith(':battlefield')]
    assert len(tokens)==2
    act(s,'p1',type='set_counter',card_id=ring2.id,kind='charge',value=2)
    original={c.id:s.state.rules.object_id(c.id) for c in [source,ring1,ring2,bear,memnite,forest,island,anthem,aura]}
    to_phase(s,'upkeep',2)
    settle(s)
    act(s,'p2',type='tap',card_ids=[ring2.id],tapped=True)
    choice(s,category)
    selected={'Artifact':{ring1.id,ring2.id,memnite.id},'Creature':{bear.id,memnite.id,aura.id},
              'Land':{forest.id,island.id},'Non-Aura enchantment':{source.id,anthem.id}}[category]
    for cid,oid in original.items():
        assert s.state.cards[cid].zone.endswith(':phased')==(cid in selected),(category,s.state.cards[cid].name,s.state.cards[cid].zone)
        assert s.state.rules.object_id(cid)==oid
    assert all(s.state.cards[cid].zone=='p1:battlefield' for cid in tokens)
    assert s.state.cards[ring2.id].counters.get('charge')==2
    assert s.state.cards[ring2.id].tapped
    roundtrip(s)


def test_native_realm_land_choice_excludes_actual_forest_dryad_land_creature_tokens(cards):
    s=game(cards)
    cast(s,REALM)
    forest=put(s,'Forest','battlefield','p2')
    cast(s,'Awaken the Woods',x_value=2)
    tokens=[c for c in s.state.cards.values() if c.token is not None and c.zone.endswith(':battlefield')]
    assert len(tokens)==2
    assert all({'Land','Creature'}<=Plan(s.state,'p1',s.cards,None).ch(c).types for c in tokens)
    to_phase(s,'upkeep',2)
    settle(s)
    choice(s,'Land')
    assert s.state.cards[forest.id].zone=='p2:phased'
    assert all(s.state.cards[c.id].zone=='p1:battlefield' for c in tokens)
    roundtrip(s)


def test_native_realm_pending_type_choice_survives_actual_source_destruction(cards):
    s=game(cards)
    source=cast(s,REALM)
    ring=put(s,'Sol Ring','battlefield','p2')
    for pid in ('p1','p2'):
        act(s,pid,type='set_prefs',hold_priority=True)
    to_phase(s,'upkeep',2)
    cast(s,'Disenchant',targets=[source.id])
    assert s.state.cards[source.id].zone=='p1:graveyard'
    choice(s,'Artifact')
    assert s.state.cards[ring.id].zone=='p2:phased'
    roundtrip(s)


def test_only_affected_upkeep_player_can_choose_exact_public_offered_types(cards):
    from app.game.errors import ActionError

    s=game(cards)
    cast(s,REALM)
    to_phase(s,'upkeep',2)
    settle(s)
    d=s.state.rules.decision
    assert d and d.player=='p2'
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='choose',decision_id=d.id,option_ids=['Artifact'])
    assert s.state.model_dump_json()==before
    with pytest.raises(ActionError):
        act(s,'p2',type='choose',decision_id=d.id,option_ids=['Enchantment'])
    assert s.state.model_dump_json()==before
    choice(s,'Non-Aura enchantment')
    roundtrip(s)


@pytest.mark.parametrize('mode',['choice','phased'])
def test_true_fresh_realm_choice_and_world_interval_restore(cards,tmp_path,mode):
    import os
    import subprocess
    import sys

    import app

    s=game(cards)
    source=cast(s,REALM)
    own=put(s,'Sol Ring','battlefield')
    other=put(s,'Sol Ring','battlefield','p2')
    to_phase(s,'upkeep',2)
    settle(s)
    if mode=='phased':
        choice(s,'Non-Aura enchantment')
        assert s.state.cards[source.id].zone=='p1:phased'
    saved=tmp_path/'realm.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_designations import roundtrip
from tests.test_rules_teferi_realm84 import cast
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source,own,other,mode=sys.argv[3:]
def answer(player,value):
 d=s.state.rules.decision
 assert d and d.player==player
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[value]);settle(s)
if mode=='choice':
 answer('p2','Artifact')
 assert s.state.cards[own].zone=='p1:phased' and s.state.cards[other].zone=='p2:phased'
 to_phase(s,'upkeep',3);settle(s);answer('p3','Creature')
 to_phase(s,'upkeep',4);settle(s)
 assert s.state.cards[own].zone=='p1:battlefield' and s.state.cards[other].zone=='p2:phased'
 answer('p1','Creature')
 to_phase(s,'upkeep',5);settle(s)
 assert s.state.cards[other].zone=='p2:battlefield'
 answer('p2','Creature')
else:
 oid=s.state.rules.object_id(source);first=s.state.rules.world_intervals80[oid].since
 to_phase(s,'main1',3)
 new=cast(s,'Concordant Crossroads',pid='p3')
 assert s.state.cards[source].zone=='p1:phased'
 assert s.state.rules.world_intervals80[oid].since==first
 to_phase(s,'main1',4);settle(s)
 assert s.state.cards[source].zone=='p1:graveyard' and s.state.cards[new.id].zone=='p3:battlefield'
roundtrip(s)
repo.close()
'''
    backend=Path(app.__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),source.id,own.id,other.id,mode],
                          cwd=backend,env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr
