"""Graveyard source triggers retain the exact source incarnation and owner."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_trigger_graveyard_owners50 import cast

DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_source_graveyard50_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




def setup(cards, name):
    names = [c['name'] for c in DATA] + ['Grizzly Bears', 'Murder', 'Wrath of God']
    s = table(cards, names, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = put(s, name, 'library')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player':'p1','zone':'library'}, position='top')
    cast(s, 'Tome Scour', ['p1'])
    settle(s)
    return s, source


def await_prompt(s):
    for _ in range(60):
        if s.state.rules.decision is not None:
            return
        assert s.state.zones.get('stack')
        act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('No native prompt opened')


def zombies(s):
    return [c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Zombie']


@pytest.mark.parametrize('name', ['Narcomoeba','Bridge from Below'])
def test_complete_canonical(cards,name):
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('accept',[True,False])
def test_narcomoeba_native_mill_optional_return(cards,accept):
    s,source=setup(cards,'Narcomoeba')
    d=s.state.rules.decision
    assert source.zone=='p1:graveyard' and d is not None and d.player=='p1'
    act(s,'p1',type='choose',decision_id=d.id,option_ids=['yes' if accept else 'no'])
    settle(s)
    assert source.zone==('p1:battlefield' if accept else 'p1:graveyard')
    roundtrip(s)


def test_narcomoeba_battlefield_death_does_not_trigger(cards):
    names=[c['name'] for c in DATA]+['Murder']
    s=table(cards,names,names,names)
    start(s)
    source=put(s,'Narcomoeba','hand')
    mana(s,C=1,U=1)
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    cast(s,'Murder',[source.id])
    settle(s)
    assert source.zone=='p1:graveyard' and s.state.rules.decision is None


@pytest.mark.parametrize('owner,controller,token,exiled',[
    ('p1','p2',1,False),('p2','p1',0,True)])
def test_bridge_graveyard_owner_not_dead_creature_controller(cards,owner,controller,token,exiled):
    s,source=setup(cards,'Bridge from Below')
    creature=put(s,'Grizzly Bears','battlefield',owner)
    act(s,'p1',type='set_controller',card_ids=[creature.id],player=controller)
    cast(s,'Murder',[creature.id])
    settle(s)
    assert len(zombies(s))==token
    assert source.zone==('p1:exile' if exiled else 'p1:graveyard')
    roundtrip(s)


def test_bridge_paid_on_battlefield_has_no_death_effect(cards):
    names=[c['name'] for c in DATA]+['Grizzly Bears','Murder']
    s=table(cards,names,names,names)
    start(s)
    source=put(s,'Bridge from Below','hand')
    mana(s,B=3)
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    creature=put(s,'Grizzly Bears','battlefield')
    cast(s,'Murder',[creature.id])
    settle(s)
    assert source.zone=='p1:battlefield' and not zombies(s)


@pytest.mark.parametrize('owner,exiled',[('p1',False),('p2',True)])
def test_bridge_first_ability_excludes_tokens_second_includes_them(cards,owner,exiled):
    s,source=setup(cards,'Bridge from Below')
    act(s,'p1',type='create_token',player=owner,
        token={'name':'Soldier','type_line':'Token Creature — Soldier','power':'1','toughness':'1'})
    cast(s,'Wrath of God')
    settle(s)
    assert not zombies(s) and source.zone==('p1:exile' if exiled else 'p1:graveyard')


@pytest.mark.parametrize('zombie_first', [True, False])
def test_bridge_simultaneous_deaths_allow_either_resolution_order(cards, zombie_first):
    s, source = setup(cards, 'Bridge from Below')
    put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Wrath of God')
    await_prompt(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1' and d.resume['step'] == 'order_triggers'
    mine = s.state.rules.pending_triggers
    make = next(t.id for t in mine if any(e['do'] == 'create_token' for e in t.ability['effects']))
    remove = next(t.id for t in mine if any(e['do'] == 'exile' for e in t.ability['effects']))
    act(s, 'p1', type='choose', decision_id=d.id,
        option_ids=[remove, make] if zombie_first else [make, remove])
    settle(s)
    assert source.zone == 'p1:exile' and len(zombies(s)) == int(zombie_first)
    roundtrip(s)


def test_bridge_entering_graveyard_with_dying_creature_was_not_active_before_event(cards):
    names = [c['name'] for c in DATA] + ['Grizzly Bears']
    s = table(cards, names, names, names)
    start(s)
    source = put(s, 'Bridge from Below', 'hand')
    mana(s, B=3)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    put(s, 'Grizzly Bears', 'battlefield')
    cast(s, 'Planar Cleansing')
    settle(s)
    assert source.zone == 'p1:graveyard' and not zombies(s)


def test_narcomoeba_pending_return_cannot_follow_a_new_graveyard_incarnation(cards):
    s, source = setup(cards, 'Narcomoeba')
    d = s.state.rules.decision
    assert d is not None
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes'])
    settle(s)
    assert source.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name', ['Narcomoeba', 'Bridge from Below'])
def test_graveyard_source_prompt_survives_genuine_cold_process(cards, tmp_path, name):
    import os
    import subprocess
    import sys

    import app

    s, source = setup(cards, name)
    if name == 'Bridge from Below':
        put(s, 'Grizzly Bears', 'battlefield')
        put(s, 'Grizzly Bears', 'battlefield', 'p2')
        cast(s, 'Wrath of God')
        await_prompt(s)
    assert s.state.rules.decision is not None
    saved = tmp_path / 'source-graveyard.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
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
d=s.state.rules.decision
assert d is not None and d.player=='p1'
if sys.argv[3]=='Narcomoeba':
    act(s,'p1',type='choose',decision_id=d.id,option_ids=['yes'])
    settle(s)
    assert s.state.cards[sys.argv[4]].zone=='p1:battlefield'
else:
    assert d.resume['step']=='order_triggers'
    mine=s.state.rules.pending_triggers
    make=next(t.id for t in mine if any(e['do']=='create_token' for e in t.ability['effects']))
    remove=next(t.id for t in mine if any(e['do']=='exile' for e in t.ability['effects']))
    act(s,'p1',type='choose',decision_id=d.id,option_ids=[remove,make])
    settle(s)
    assert s.state.cards[sys.argv[4]].zone=='p1:exile'
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Zombie'])==1
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), name, source.id],
        cwd=Path(app.__file__).resolve().parents[1],
        env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])},
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
