"""World upkeep abilities preserve the original payer, source and target authority."""
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

PILLAR = 'Pillar Tombs of Aku'
DATA = []
for filename in ['world_upkeep83_cards.json','world_rule80_cards.json','upkeep_target_choice65_cards.json']:
    DATA += json.loads((Path(__file__).parent/'fixtures'/filename).read_text())
ALL = list(dict.fromkeys([c['name'] for c in DATA]+['Grizzly Bears','Llanowar Elves','Forest']))


@pytest.fixture()
def cards(settings):
    base = {c['name']:c for c in fixture_cards()}
    for i,c in enumerate(DATA):
        base[c['name']] = card(c['name'],number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    s=table(cards,ALL,ALL,ALL)
    to_phase(s,'main1',1)
    return s


def cast(s,name,pid='p1',targets=()):
    source=put(s,name,'hand',pid)
    mana(s,pid,C=10,B=5,W=5,U=5,G=5)
    wait_priority(s,pid)
    act(s,pid,type='cast_spell',card_id=source.id,targets=list(targets),sources=[])
    settle(s)
    return source


def choose(s,value):
    d=s.state.rules.decision
    assert d and value in [o.id for o in d.options],d
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[value])
    settle(s)


@pytest.mark.parametrize('name',[PILLAR,'The Abyss'])
def test_canonical_world_upkeep_whole_definition(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('pay',[False,True])
def test_pillar_actual_cast_affected_player_sacrifices_or_source_controller_loses_world(cards,pay):
    s=game(cards)
    source=cast(s,PILLAR)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    elf=put(s,'Llanowar Elves','battlefield','p2')
    to_phase(s,'upkeep',2)
    settle(s)
    assert s.state.rules.decision.player=='p2'
    choose(s,'pay' if pay else 'decline')
    if pay:
        assert s.state.rules.decision.player=='p2'
        choose(s,bear.id)
    assert s.state.cards[source.id].zone==('p1:battlefield' if pay else 'p1:graveyard')
    assert s.state.cards[bear.id].zone==('p2:graveyard' if pay else 'p2:battlefield')
    assert s.state.cards[elf.id].zone=='p2:battlefield'
    assert s.state.players['p2'].life==(40 if pay else 35)
    roundtrip(s)


def test_pillar_no_creature_cannot_pay_and_does_not_wait_for_manual_choice(cards):
    s=game(cards)
    source=cast(s,PILLAR)
    to_phase(s,'upkeep',2)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.players['p2'].life==35


@pytest.mark.parametrize('replacement',[False,True])
def test_pillar_actual_cost_sacrifice_is_paid_with_indestructible_or_public_exile(cards,replacement):
    s=game(cards)
    if replacement:
        cast(s,'Rest in Peace')
    source=cast(s,PILLAR)
    creature=put(s,'Darksteel Myr','battlefield','p2')
    to_phase(s,'upkeep',2)
    settle(s)
    choose(s,'pay')
    assert s.state.cards[creature.id].zone==('p2:exile' if replacement else 'p2:graveyard')
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert s.state.players['p2'].life==40


def test_pillar_sigarda_makes_opponents_ability_sacrifice_cost_unpayable(cards):
    s=game(cards)
    source=cast(s,PILLAR)
    sigarda=put(s,'Sigarda, Host of Herons','battlefield','p2')
    to_phase(s,'upkeep',2)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.cards[sigarda.id].zone=='p2:battlefield'
    assert s.state.players['p2'].life==35


def test_pillar_original_controller_cannot_sacrifice_world_after_control_changed(cards):
    s=game(cards)
    source=cast(s,PILLAR)
    put(s,'Grizzly Bears','battlefield','p2')
    to_phase(s,'upkeep',2)
    settle(s)
    assert s.state.rules.decision.player=='p2'
    act(s,'p1',type='set_controller',card_ids=[source.id],player='p3')
    choose(s,'decline')
    assert s.state.cards[source.id].zone=='p3:battlefield' and s.state.cards[source.id].controller=='p3'
    assert s.state.players['p2'].life==35


def test_abyss_actual_black_mana_cast_then_actual_newer_world_sends_it_to_graveyard(cards):
    s=game(cards)
    source=cast(s,'The Abyss')
    assert s.state.cards[source.id].zone=='p1:battlefield'
    to_phase(s,'main1',3)
    new=cast(s,'Concordant Crossroads',pid='p3')
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.cards[new.id].zone=='p3:battlefield'
    roundtrip(s)


def test_pillar_actual_cloudshift_new_incarnation_is_not_sacrificed_by_old_upkeep(cards):
    s=game(cards)
    cast(s,'Opalescence')
    source=cast(s,PILLAR)
    put(s,'Grizzly Bears','battlefield','p2')
    for pid in ('p1','p2'):
        act(s,pid,type='set_prefs',hold_priority=True)
    to_phase(s,'upkeep',2)
    original=s.state.rules.object_id(source.id)
    cast(s,'Cloudshift',targets=[source.id])
    assert s.state.rules.object_id(source.id)!=original
    assert s.state.rules.decision.player=='p2'
    choose(s,'decline')
    assert s.state.players['p2'].life==35
    assert s.state.cards[source.id].zone=='p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('pay',[False,True])
def test_pillar_true_cold_original_payer_and_creature_cost(cards,tmp_path,pay):
    import os
    import subprocess
    import sys

    import app

    s=game(cards)
    source=cast(s,PILLAR)
    bear=put(s,'Grizzly Bears','battlefield','p2')
    elf=put(s,'Llanowar Elves','battlefield','p2')
    to_phase(s,'upkeep',2)
    settle(s)
    assert s.state.rules.decision.player=='p2'
    saved=tmp_path/'pillar.json'
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
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source,bear,elf,pay=sys.argv[3:]
d=s.state.rules.decision
assert d and d.player=='p2'
act(s,d.player,type='choose',decision_id=d.id,option_ids=['pay' if pay=='yes' else 'decline'])
settle(s)
if pay=='yes':
 d=s.state.rules.decision
 assert d and d.player=='p2' and {o.id for o in d.options}=={bear,elf}
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear])
 settle(s)
assert s.state.players['p2'].life==(40 if pay=='yes' else 35)
assert s.state.cards[source].zone==('p1:battlefield' if pay=='yes' else 'p1:graveyard')
assert s.state.cards[bear].zone==('p2:graveyard' if pay=='yes' else 'p2:battlefield')
assert s.state.cards[elf].zone=='p2:battlefield'
roundtrip(s)
repo.close()
'''
    backend=Path(app.__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),source.id,bear.id,elf.id,'yes' if pay else 'no'],
                          cwd=backend,env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr
