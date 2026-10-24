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

REALM = 'Hall of Gemstone'
DATA = json.loads((Path(__file__).parent/'fixtures/hall_gemstone86_cards.json').read_text())
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


def choose(s,color='Red'):
    d=s.state.rules.decision
    assert d and d.player=='p2' and {o.id for o in d.options}=={'White','Blue','Black','Red','Green'}
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[color])
    settle(s)


def setup(cards,color='Red'):
    s=game(cards)
    source=cast(s,REALM)
    to_phase(s,'upkeep',2)
    settle(s)
    choose(s,color)
    to_phase(s,'main1',2)
    return s,source


def test_canonical_whole_cast(cards):
    assert coverage.of_card_data(cards.resolve(REALM)).level=='FULL'
    s=game(cards)
    assert cast(s,REALM).zone=='p1:battlefield'


@pytest.mark.parametrize('name,symbol,n',[('Forest','R',1),('Snow-Covered Wastes','C',1),('Sol Ring','C',2)])
def test_native_land_colors_colorless_and_nonland(cards,name,symbol,n):
    s,_=setup(cards)
    source=put(s,name,'battlefield','p2')
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=source.id,ability=0)
    settle(s)
    assert sum(u.sym==symbol for u in s.state.players['p2'].mana_units)==n
    assert len(s.state.players['p2'].mana_units)==n
    roundtrip(s)


def test_native_restricted_land_retains_spending_restriction(cards):
    s,_=setup(cards)
    land=put(s,'Ancient Ziggurat','battlefield','p2')
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=land.id,ability=0,mana_choice='G')
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume['step']=='staged_base_mana'
    act(s,'p2',type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if o.label=='{G}')])
    settle(s)
    units=s.state.players['p2'].mana_units
    assert len(units)==1 and units[0].sym=='R' and units[0].only, (s.state.turn, s.state.rules.decision, s.state.players['p2'].mana, s.state.rules.tap_mana)
    roundtrip(s)


def test_native_multicolor_amount_retained(cards):
    s,_=setup(cards)
    land=put(s,'Izzet Boilerworks','battlefield','p2')
    if s.state.cards[land.id].tapped:
        act(s,'p2',type='tap',card_ids=[land.id],tapped=False)
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=land.id,ability=2)
    settle(s)
    assert [u.sym for u in s.state.players['p2'].mana_units]==['R','R']
    roundtrip(s)


def test_actual_source_departure_keeps_trigger_and_cleanup_expires_rule(cards):
    s=game(cards)
    source=cast(s,REALM)
    land=put(s,'Forest','battlefield','p2')
    for pid in ('p1','p2'):
        act(s,pid,type='set_prefs',hold_priority=True)
    to_phase(s,'upkeep',2)
    cast(s,'Disenchant',targets=[source.id])
    assert s.state.cards[source.id].zone=='p1:graveyard'
    choose(s,'Blue')
    to_phase(s,'main1',2)
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=land.id,ability=0)
    settle(s)
    assert [u.sym for u in s.state.players['p2'].mana_units]==['U']
    to_phase(s,'main1',3)
    assert not any(x.get('turn')==s.state.turn.number for x in s.state.rules.tap_mana)
    act(s,'p2',type='tap',card_ids=[land.id],tapped=False)
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=land.id,ability=0)
    settle(s)
    assert [u.sym for u in s.state.players['p2'].mana_units]==['G']
    roundtrip(s)


@pytest.mark.parametrize('mode',['choice','resolved'])
def test_true_cold_hall_choice_or_temporary_rule(cards,tmp_path,mode):
    import os
    import subprocess
    import sys

    import app

    s=game(cards)
    cast(s,REALM)
    land=put(s,'Forest','battlefield','p2')
    to_phase(s,'upkeep',2)
    settle(s)
    if mode=='resolved':
        choose(s,'Black')
    saved=tmp_path/'hall.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_designations import roundtrip
from tests.test_rules_hall_gemstone86 import choose
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_library_look import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
land,mode=sys.argv[3:]
if mode=='choice':choose(s,'Black')
to_phase(s,'main1',2);wait_priority(s,'p2')
act(s,'p2',type='activate_ability',card_id=land,ability=0);settle(s)
assert [u.sym for u in s.state.players['p2'].mana_units]==['B']
roundtrip(s);repo.close()
'''
    backend=Path(app.__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),land.id,mode],cwd=backend,
                          env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('hall_first',[True,False])
def test_native_tapping_player_orders_competing_replacements(cards,hall_first):
    s,_=setup(cards)
    put(s,'Contamination','battlefield')
    land=put(s,'Forest','battlefield','p2')
    wait_priority(s,'p2')
    act(s,'p2',type='activate_ability',card_id=land.id,ability=0)
    settle(s)
    d=s.state.rules.decision
    assert d and d.player=='p2' and d.resume['step']=='reveal_mana_replace'
    replacements=d.resume['data']['replacements']
    selected=next(str(i) for i,r in enumerate(replacements) if (r['op']['do']=='colored_recolor86')==hall_first)
    act(s,'p2',type='choose',decision_id=d.id,option_ids=[selected])
    settle(s)
    assert [u.sym for u in s.state.players['p2'].mana_units]==(['B'] if hall_first else ['R'])
    roundtrip(s)
