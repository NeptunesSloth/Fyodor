"""The upkeep player chooses exact card categories; native phasing owns all returns."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

REALM = "Winter's Night"
DATA = json.loads((Path(__file__).parent/'fixtures/winter_night85_cards.json').read_text())
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
    mana(s,pid,C=20,W=10,U=10,G=10,R=10)
    wait_priority(s,pid)
    act(s,pid,type='cast_spell',card_id=source.id,targets=list(targets),sources=[],**kwargs)
    settle(s)
    return source


def test_native_whole_cast_full(cards):
    assert coverage.of_card_data(cards.resolve(REALM)).level=='FULL'
    s=game(cards)
    assert cast(s,REALM).zone=='p1:battlefield'


@pytest.mark.parametrize('name,symbol,extra', [('Snow-Covered Forest','G',True),('Snow-Covered Wastes','C',True),('Forest','G',False)])
def test_native_produced_type_and_only_snow_lands(cards,name,symbol,extra):
    s=game(cards)
    cast(s,REALM)
    # Casting helper's unused mana is irrelevant to the actual land activation.
    for sym,n in dict(s.state.players['p1'].mana).items():
        if n:
            act(s,'p1',type='add_mana',mana={sym:-n})
    land=put(s,name,'battlefield')
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=land.id,ability=0)
    settle(s)
    units=s.state.players['p1'].mana_units
    assert sum(u.sym==symbol for u in units)==1+int(extra)
    assert bool(s.state.rules.stay_tapped)==extra
    assert not s.state.zones.get('stack')
    if extra:
        assert s.state.rules.stay_tapped[0]['oid']==s.state.rules.object_id(land.id)
    roundtrip(s)


@pytest.mark.parametrize('mode',['ordinary','untapped','control','source'])
def test_native_next_untap_consumed_and_controller_following(cards,mode):
    s=game(cards)
    source=cast(s,REALM)
    land=put(s,'Snow-Covered Forest','battlefield')
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=land.id,ability=0)
    settle(s)
    if mode=='untapped':
        act(s,'p1',type='tap',card_ids=[land.id],tapped=False)
    if mode=='control':
        act(s,'p1',type='set_controller',card_ids=[land.id],player='p2')
    if mode=='source':
        cast(s,'Concordant Crossroads')
        assert s.state.cards[source.id].zone=='p1:graveyard'
    turn=2 if mode=='control' else 4
    to_phase(s,'main1',turn)
    assert s.state.cards[land.id].tapped==(mode!='untapped')
    assert not s.state.rules.stay_tapped
    if mode=='untapped':
        act(s,s.state.cards[land.id].controller,type='tap',card_ids=[land.id],tapped=True)
    to_phase(s,'main1',turn+3)
    assert not s.state.cards[land.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('mode',['ordinary','control'])
def test_true_cold_next_untap_restores(cards,tmp_path,mode):
    import os
    import subprocess
    import sys

    import app

    s=game(cards)
    cast(s,REALM)
    land=put(s,'Snow-Covered Forest','battlefield')
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=land.id,ability=0)
    settle(s)
    if mode=='control':
        act(s,'p1',type='set_controller',card_ids=[land.id],player='p2')
    saved=tmp_path/'winter.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
land,mode=sys.argv[3:];turn=2 if mode=='control' else 4
to_phase(s,'main1',turn)
assert s.state.cards[land].tapped and not s.state.rules.stay_tapped
to_phase(s,'main1',turn+3)
assert not s.state.cards[land].tapped
roundtrip(s);repo.close()
'''
    backend=Path(app.__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),land.id,mode],cwd=backend,
                          env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr
