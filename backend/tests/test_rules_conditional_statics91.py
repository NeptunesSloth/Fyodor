"""Conditional attachment and Army animation use native continuous effects."""
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

NAMES=['Short Circuit','Grond, the Gatebreaker']
DATA = json.loads((Path(__file__).parent/'fixtures/conditional_statics91_cards.json').read_text())
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
    targets=[put(s,'Grizzly Bears','battlefield','p2').id] if name=='Short Circuit' else []
    source=cast(s,name,targets=targets)
    assert s.state.cards[source.id].zone=='p1:battlefield'
    roundtrip(s)


def test_native_short_circuit_tracks_actual_crew_and_cleanup(cards):
    s=game(cards)
    ship=cast(s,'Sky Skiff')
    elf=put(s,'Llanowar Elves','battlefield')
    aura=cast(s,'Short Circuit',targets=[ship.id])
    assert not ch(s,ship).is_creature and 'flying' in ch(s,ship).keywords
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=ship.id,ability=1,crew=[elf.id],sources=[])
    settle(s)
    assert ch(s,ship).is_creature and ch(s,ship).pt==(-1,3) and 'flying' not in ch(s,ship).keywords
    to_phase(s,'main1',2)
    assert s.state.cards[aura.id].zone=='p1:battlefield'
    assert not ch(s,ship).is_creature and 'flying' in ch(s,ship).keywords
    roundtrip(s)


def test_native_grond_own_turn_army_and_independent_crew(cards):
    s=game(cards)
    source=cast(s,'Grond, the Gatebreaker')
    assert not ch(s,source).is_creature
    cast(s,'Lazotep Reaver')
    army=next(c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and 'Army' in ch(s,c).subtypes)
    bear=put(s,'Grizzly Bears','battlefield')
    assert ch(s,source).is_creature
    act(s,'p1',type='set_controller',card_ids=[army.id],player='p2')
    assert not ch(s,source).is_creature
    act(s,'p2',type='set_controller',card_ids=[army.id],player='p1')
    assert ch(s,source).is_creature
    to_phase(s,'main1',2)
    assert not ch(s,source).is_creature
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=source.id,ability=2,crew=[army.id,bear.id],sources=[])
    settle(s)
    assert ch(s,source).is_creature
    to_phase(s,'main1',3)
    assert not ch(s,source).is_creature
    to_phase(s,'main1',4)
    assert ch(s,source).is_creature
    roundtrip(s)


@pytest.mark.parametrize('mode',['active','expired'])
def test_true_cold_conditional_static_expiry(cards,tmp_path,mode):
    import os
    import subprocess
    import sys

    import app

    s=game(cards)
    meta={'mode':mode}
    ship=cast(s,'Sky Skiff')
    elf=put(s,'Llanowar Elves','battlefield')
    aura=cast(s,'Short Circuit',targets=[ship.id])
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=ship.id,ability=1,crew=[elf.id],sources=[])
    settle(s)
    grond=cast(s,'Grond, the Gatebreaker')
    cast(s,'Lazotep Reaver')
    meta.update(ship=ship.id,aura=aura.id,grond=grond.id)
    if mode=='expired':
        to_phase(s,'main1',2)
    saved=tmp_path/'conditional91.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
m=json.loads(sys.argv[3])
def ch(cid):return Plan.view(s.state,'p1',repo).ch(s.state.cards[cid])
if m['mode']=='active':
 assert ch(m['ship']).is_creature and ch(m['ship']).pt==(-1,3) and 'flying' not in ch(m['ship']).keywords
 assert ch(m['grond']).is_creature
 to_phase(s,'main1',2)
assert not ch(m['ship']).is_creature and 'flying' in ch(m['ship']).keywords
assert s.state.cards[m['aura']].zone=='p1:battlefield' and not ch(m['grond']).is_creature
to_phase(s,'main1',4)
assert ch(m['grond']).is_creature
assert not ch(m['ship']).is_creature and 'flying' in ch(m['ship']).keywords
roundtrip(s);repo.close()
'''
    backend=Path(app.__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),json.dumps(meta)],cwd=backend,
                          env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr
