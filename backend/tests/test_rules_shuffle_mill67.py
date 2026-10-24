"""Native public-mill selections and exact hand outcomes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures/shuffle_mill67_cards.json').read_text())):
        extra = {k:v for k,v in c.items() if k not in ('name','set_code','number')}
        if c.get('faces'):
            extra['card_faces'] = c['faces']
        if c.get('related_cards') or c.get('related_tokens'):
            extra['all_parts'] = [*c.get('related_cards', []), *[{**part, 'component': 'token'} for part in c.get('related_tokens', [])]]
        base[c['name']] = card(c['name'], set_code='oc59', number=str(i), **extra)
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()

def setup(cards):
    names = list(dict.fromkeys([c['name'] for c in json.loads((Path(__file__).parent/'fixtures/shuffle_mill67_cards.json').read_text()) if c['name'] != 'Urza, Planeswalker'] + ['Grizzly Bears','Hill Giant','Forest','Lightning Bolt']))
    s = table(cards, names, names, names)
    to_phase(s, 'main1', 1)
    act(s, 'p1', type='add_mana', player='p1', mana={c:30 for c in ['C','W','U','B','R','G']})
    return s

def answer(s, ids):
    d = s.state.rules.decision
    assert d
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)

def cast(s, name, **kwargs):
    source = put(s, name, 'hand')
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[], **kwargs)
    settle(s)
    return source

def top(s, names):
    cards = [put(s, name, 'hand') for name in names]
    for c in reversed(cards):
        act(s, 'p1', type='move', card_ids=[c.id], to={'player':'p1','zone':'library'}, position='top')
    return cards


def top_for(s,names,owner):
    cards=[put(s,name,'hand',owner) for name in names]
    for c in reversed(cards):
        act(s,owner,type='move',card_ids=[c.id],to={'player':owner,'zone':'library'},position='top')
    return cards



def test_whole_pair(cards):
    from app.rules.coverage import of_card_data
    for n in ['Psychic Spiral','Stream of Thought']:
        c=next(c for c in cards.search(n) if c['name']==n)
        assert of_card_data(c).level == 'FULL'


def test_spiral_native_exact_shuffled_card_count(cards):
    s=setup(cards)
    gy=[put(s,n,'graveyard') for n in ['Grizzly Bears','Forest','Sol Ring']]
    source=put(s,'Psychic Spiral','hand')
    enemy=top_for(s,['Forest','Grizzly Bears','Hill Giant','Lightning Bolt'],'p2')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],targets=['p2'])
    settle(s)
    assert not s.state.rules.decision
    assert all(s.state.cards[c.id].zone=='p1:library' for c in gy)
    assert all(s.state.cards[c.id].zone=='p2:graveyard' for c in enemy[:3])
    assert s.state.cards[enemy[3].id].zone=='p2:library'
    assert s.state.cards[source.id].zone=='p1:graveyard'


def test_stream_native_resolution_choice_includes_fresh_mill(cards):
    s=setup(cards)
    old=put(s,'Sol Ring','graveyard')
    source=put(s,'Stream of Thought','hand')
    milled=top(s,['Forest','Grizzly Bears','Hill Giant','Lightning Bolt'])
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],targets=['p1'])
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume['step']=='return_choice'
    assert {o.id for o in d.options}=={old.id,*[c.id for c in milled]}
    assert source.id not in {o.id for o in d.options}
    assert d.min_choices==0 and d.max_choices==4
    answer(s,[old.id,milled[0].id,milled[1].id,milled[2].id])
    assert all(s.state.cards[c.id].zone=='p1:library' for c in [old,*milled[:3]])
    assert s.state.cards[milled[3].id].zone=='p1:graveyard'
    assert s.state.cards[source.id].zone=='p1:graveyard'

@pytest.mark.parametrize('spell',['Psychic Spiral','Stream of Thought'])
@pytest.mark.parametrize('command',[False,True])
def test_true_cold_shuffle_commander_replacement_finishes_before_mill_followup(cards,tmp_path,spell,command):
    s=setup(cards)
    commander=next(c for c in s.state.cards.values() if c.owner=='p1' and c.commander_key)
    act(s,'p1',type='move',card_ids=[commander.id],to={'player':'p1','zone':'battlefield'})
    bolt=put(s,'Lightning Bolt','hand')
    act(s,'p1',type='cast_spell',card_id=bolt.id,sources=[],targets=[commander.id])
    settle(s)
    assert s.state.rules.decision and s.state.rules.decision.resume['step']=='commander_zone'
    answer(s,['no'])
    assert commander.zone=='p1:graveyard'
    enemy=top_for(s,['Forest','Grizzly Bears','Hill Giant','Sol Ring','Darksteel Colossus'],'p2')
    source=put(s,spell,'hand')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],targets=['p2'])
    settle(s)
    if spell=='Stream of Thought':
        d=s.state.rules.decision
        assert d and d.resume['step']=='return_choice'
        answer(s,[commander.id])
    d=s.state.rules.decision
    assert d, 'Expected original commander library replacement decision'
    assert d.resume['step']=='commander_first' and commander.zone=='p1:graveyard'
    commander_key=commander.commander_key
    s=cold67(s,cards,tmp_path,['yes' if command else 'no'])
    commander=next(c for c in s.state.cards.values() if c.commander_key==commander_key and c.owner=='p1')
    assert commander.zone==('p1:command' if command else 'p1:library')
    n=4 if spell=='Stream of Thought' else 1 if command else 2
    assert all(s.state.cards[c.id].zone=='p2:graveyard' for c in enemy[:n])
    assert s.state.cards[enemy[n].id].zone=='p2:library'
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def cold67(s,cards,tmp_path,ids):
    import os
    import subprocess
    import sys

    import app
    from app.game.session import GameSession
    from app.game.state import GameState
    saved=tmp_path/'shuffle67.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''import json,sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from tests.game_helpers import act
from tests.test_rules_library_placements import settle
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
d=s.state.rules.decision;assert d and d.resume['step'] in ('commander_first','prepared_mill61')
act(s,d.player,type='choose',decision_id=d.id,option_ids=json.loads(sys.argv[3]));settle(s)
assert s.state.rules.decision is None
p.write_text(s.state.model_dump_json())
'''
    backend=Path(app.__file__).resolve().parents[1]
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),json.dumps(ids)],cwd=backend,env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert run.returncode==0,run.stdout+run.stderr
    return GameSession(GameState.model_validate_json(saved.read_text()),cards=cards)


@pytest.mark.parametrize('spell',['Psychic Spiral','Stream of Thought'])
def test_empty_graveyard_still_shuffles_library(cards,spell):
    s=setup(cards)
    top_for(s,['Forest','Grizzly Bears','Hill Giant','Sol Ring','Rest in Peace','Bruvac the Grandiloquent','Desecrated Tomb','Hope of Ghirapur'],'p2')
    source=put(s,spell,'hand')
    survivor=next(c for c in s.state.cards.values() if c.zone=='p1:library')
    before=survivor.id
    enemy_count=len(s.state.zones['p2:graveyard'])
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],targets=['p2'])
    settle(s)
    assert not s.state.rules.decision
    assert before not in s.state.cards
    assert len(s.state.zones['p2:graveyard'])==enemy_count+(4 if spell=='Stream of Thought' else 0)
    assert s.state.cards[source.id].zone=='p1:graveyard'


def test_stream_can_choose_none_from_nonempty_graveyard(cards):
    s=setup(cards)
    old=put(s,'Sol Ring','graveyard')
    source=put(s,'Stream of Thought','hand')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],targets=['p2'])
    settle(s)
    answer(s,[])
    assert old.zone=='p1:graveyard' and source.zone=='p1:graveyard'
    roundtrip(s)


def test_native_replicate_copy_resolves_before_original_without_casting_copy(cards):
    s=setup(cards)
    top_for(s,['Forest','Grizzly Bears','Hill Giant','Sol Ring','Rest in Peace','Bruvac the Grandiloquent','Desecrated Tomb','Hope of Ghirapur'],'p2')
    old=put(s,'Sol Ring','graveyard')
    source=put(s,'Stream of Thought','hand')
    before=len(s.state.zones.get('p2:graveyard',[]))
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],targets=['p2'],kicker=1)
    choices=0
    for _ in range(100):
        settle(s)
        d=s.state.rules.decision
        if d:
            if d.resume['step']=='copy_target':
                answer(s,['keep'])
            elif d.resume['step']=='return_choice':
                assert source.zone=='stack' and source.id not in {o.id for o in d.options}
                assert old.id in {o.id for o in d.options}
                choices+=1
                answer(s,[])
            else:
                raise AssertionError(d)
        elif not s.state.zones.get('stack'):
            break
    assert choices==2
    assert len(s.state.zones.get('p2:graveyard',[]))==before+8
    assert source.zone=='p1:graveyard' and old.zone=='p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('spell',['Psychic Spiral','Stream of Thought'])
def test_native_bruvac_doubles_instruction_after_shuffle_count(cards,spell):
    s=setup(cards)
    top_for(s,['Forest','Grizzly Bears','Hill Giant','Sol Ring','Rest in Peace','Bruvac the Grandiloquent','Desecrated Tomb','Hope of Ghirapur'],'p2')
    put(s,'Bruvac the Grandiloquent','battlefield')
    put(s,'Sol Ring','graveyard')
    source=put(s,spell,'hand')
    before=len(s.state.zones.get('p2:graveyard',[]))
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],targets=['p2'])
    settle(s)
    if s.state.rules.decision:
        answer(s,[])
    assert len(s.state.zones.get('p2:graveyard',[]))==before+(8 if spell=='Stream of Thought' else 2)
    assert source.zone=='p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('spell',['Psychic Spiral','Stream of Thought'])
def test_native_two_creatures_shuffled_together_trigger_one_tomb_batch(cards,spell):
    s=setup(cards)
    put(s,'Desecrated Tomb','battlefield')
    creatures=[put(s,n,'graveyard') for n in ['Grizzly Bears','Hill Giant']]
    top_for(s,['Forest','Sol Ring','Rest in Peace','Hope of Ghirapur'],'p2')
    source=put(s,spell,'hand')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],targets=['p2'])
    settle(s)
    if spell=='Stream of Thought':
        answer(s,[c.id for c in creatures])
    settle(s)
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Bat'])==1
    assert all(c.zone=='p1:library' for c in creatures)
    roundtrip(s)


def test_native_graveyard_snapshot_keeps_grist_creature_characteristic(cards):
    s=setup(cards)
    put(s,'Desecrated Tomb','battlefield')
    grist=put(s,'Grist, the Hunger Tide','graveyard')
    source=put(s,'Psychic Spiral','hand')
    top_for(s,['Forest','Sol Ring'],'p2')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],targets=['p2'])
    settle(s)
    assert grist.zone=='p1:library'
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Bat'])==1
    roundtrip(s)


@pytest.mark.parametrize('outcome',['exile','library:shuffle'])
def test_true_cold_stream_self_mill_native616_finishes_before_current_graveyard_choice(cards,tmp_path,outcome):
    s=setup(cards)
    cast(s,'Rest in Peace')
    milled=top(s,['Darksteel Colossus','Forest','Grizzly Bears','Hill Giant'])
    source=put(s,'Stream of Thought','hand')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],targets=['p1'])
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume['step']=='prepared_mill61'
    assert all(c.zone=='p1:library' for c in milled)
    choice=next(o.id for o in d.options if o.label.endswith(': '+outcome))
    s=cold67(s,cards,tmp_path,[choice])
    colossus=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Darksteel Colossus')
    assert colossus.zone==('p1:exile' if outcome=='exile' else 'p1:library')
    assert all(s.state.cards[c.id].zone=='p1:exile' for c in milled[1:])
    assert not s.state.zones.get('p1:graveyard')
    assert s.state.cards[source.id].zone=='p1:exile'
    assert not s.state.rules.decision
    roundtrip(s)
