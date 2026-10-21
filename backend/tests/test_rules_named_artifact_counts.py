"""Canonical collateral validation for fixed-name mana and granted damage abilities."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_mana_delayed_effects import answer
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base={c['name']:c for c in fixture_cards()}
    for i,c in enumerate(json.loads((Path(__file__).parent/'fixtures/named_artifact_count_cards.json').read_text())):
        base[c['name']]=card(c['name'],set_code='nac',number=str(i),**{k:v for k,v in c.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names=[c['name'] for c in json.loads((Path(__file__).parent/'fixtures/named_artifact_count_cards.json').read_text())]
    s=table(cards,names,names,names)
    for p in ('p1','p2','p3'):
        act(s,p,type='set_prefs',hold_priority=True)
    to_phase(s,'main1',4)
    return s


def grant(s,source):
    return next(a.index for a in Plan(s.state,'p1',s.cards,None).ch(s.state.cards[source.id]).abilities
                if a.cost and 'Food Fight' in a.text)


def fire(s,source,target='p2'):
    wait_priority(s,'p1')
    act(s,'p1',type='add_mana',player='p1',mana={'C':2})
    act(s,'p1',type='activate_ability',card_id=source.id,ability=grant(s,source),sources=[],targets=[target])


@pytest.mark.parametrize('name',['Powerstone Shard','Food Fight'])
def test_full(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def test_shard_counts_exact_artifact_name_and_controller(cards):
    s=game(cards)
    shard=put(s,'Powerstone Shard','battlefield')
    put(s,'Powerstone Shard','battlefield',pid='p2')
    put(s,'Sol Ring','battlefield')
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=shard.id,ability=0)
    assert mana_pool(s,'p1').get('C',0)==1
    assert not s.state.zones.get('stack',[])
    roundtrip(s)


def test_shard_counts_second_owned_shard_and_control_change(cards):
    s=game(cards)
    shard=put(s,'Powerstone Shard','battlefield')
    other=put(s,'Powerstone Shard','battlefield',pid='p2')
    act(s,'p1',type='set_controller',card_ids=[other.id],player='p1')
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=shard.id,ability=0)
    assert mana_pool(s,'p1').get('C',0)==2
    roundtrip(s)


@pytest.mark.parametrize('remaining',[True,False])
def test_food_fight_departed_artifact_uses_current_named_count(cards,remaining):
    s=game(cards)
    fight=put(s,'Food Fight','battlefield')
    put(s,'Food Fight','battlefield',pid='p2')
    source=put(s,'Sol Ring','battlefield')
    fire(s,source)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    if not remaining:
        put(s,'Food Fight','graveyard')
    roundtrip(s)
    answer(s)
    assert s.state.players['p2'].life==40-(2 if remaining else 1)
    assert s.state.cards[fight.id].zone==('p1:battlefield' if remaining else 'p1:graveyard')
    roundtrip(s)


def test_food_fight_damage_source_is_sacrificed_artifact_with_lifelink(cards,tmp_path):
    s=game(cards)
    put(s,'Food Fight','battlefield')
    source=put(s,'Wurmcoil Engine','battlefield')
    fire(s,source)
    # Sacrifice is already paid; removing the grant must not erase the stack ability or source LKI.
    put(s,'Food Fight','graveyard')
    roundtrip(s)
    saved=tmp_path/'food-source-lki.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_mana_delayed_effects import answer
save,db=sys.argv[1:]
r=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=r)
answer(s)
assert s.state.players['p2'].life==39
assert s.state.players['p1'].life==41
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
r.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path)],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    answer(s)
    assert s.state.players['p2'].life==39 and s.state.players['p1'].life==41
    roundtrip(s)


def test_shard_real_sculpting_steel_copy_counts_copied_name(cards):
    s=game(cards)
    shard=put(s,'Powerstone Shard','battlefield')
    spell=put(s,'Sculpting Steel','hand')
    wait_priority(s,'p1')
    act(s,'p1',type='add_mana',player='p1',mana={'C':3})
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[],targets=[])
    settle(s)
    d=s.state.rules.decision
    assert d is not None
    options=[o.id for o in d.options if shard.id in o.id]
    assert options
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[options[0]])
    answer(s)
    assert Plan(s.state,'p1',s.cards,None).ch(s.state.cards[spell.id]).name=='Powerstone Shard'
    wait_priority(s,'p1')
    act(s,'p1',type='activate_ability',card_id=shard.id,ability=0)
    assert mana_pool(s,'p1').get('C',0)==2
    roundtrip(s)


def test_food_fight_two_controlled_named_permanents_count(cards):
    s=game(cards)
    put(s,'Food Fight','battlefield')
    other=put(s,'Food Fight','battlefield',pid='p2')
    act(s,'p1',type='set_controller',card_ids=[other.id],player='p1')
    source=put(s,'Darksteel Citadel','battlefield')
    fire(s,source)
    answer(s)
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.players['p2'].life==37
    roundtrip(s)
