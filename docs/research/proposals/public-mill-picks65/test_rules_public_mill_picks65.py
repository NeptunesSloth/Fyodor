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

CACHE, MIDNIGHT, DUMMY = 'Cache Grab', 'Midnight Tilling', 'Sparring Dummy'

@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures/public_mill_picks65_cards.json').read_text())):
        extra = {k:v for k,v in c.items() if k not in ('name','set_code','number')}
        if c.get('faces'):
            extra['card_faces'] = c['faces']
        base[c['name']] = card(c['name'], set_code='oc59', number=str(i), **extra)
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()

def setup(cards):
    names = list(dict.fromkeys([c['name'] for c in json.loads((Path(__file__).parent/'fixtures/public_mill_picks65_cards.json').read_text())] + ['Grizzly Bears','Hill Giant','Forest','Lightning Bolt']))
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


ROOM='Greenhouse // Rickety Gazebo'
NASHI='Nashi, Searcher in the Dark'

@pytest.mark.parametrize('name',[ROOM,NASHI])
def test_whole65(cards,name):
    from app.rules import coverage
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('rip',[False,True])
@pytest.mark.parametrize('count',[0,1,2])
def test_room_actual_unlock_selects_up_to_two_actual_public_permanents(cards,rip,count):
    s=setup(cards)
    if rip:
        cast(s,'Rest in Peace')
    source=put(s,ROOM,'battlefield')
    chosen=top(s,['Grizzly Bears','Forest','Lightning Bolt','Hill Giant'])
    act(s,'p1',type='unlock_door',card_id=source.id,door=2)
    settle(s)
    d=s.state.rules.decision
    assert d and d.resume.get('step')=='public_pick65' and d.max_choices==2 and d.min_choices==0
    assert {o.id for o in d.options}=={chosen[0].id,chosen[1].id,chosen[3].id}
    answer(s,[c.id for c in chosen[:count]])
    assert all(c.zone=='p1:hand' for c in chosen[:count])
    assert all(c.zone==('p1:exile' if rip else 'p1:graveyard') for c in chosen[count:])
    roundtrip(s)


@pytest.mark.parametrize('count',[0,1,2])
def test_nashi_native_combat_returns_any_number_and_counts_actual_hand(cards,count):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    source=put(s,NASHI,'battlefield')
    to_phase(s,'main1',7)
    selected=top(s,['Hardened Scales','Grumgully, the Generous'])
    to_phase(s,'declare_attackers',turn=7)
    attack(s,(source,'p2'))
    for _ in range(80):
        d=s.state.rules.decision
        if d:
            assert d.resume.get('step')=='public_pick65'
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert d and {o.id for o in d.options}=={c.id for c in selected} and d.max_choices==2
    answer(s,[c.id for c in selected[:count]])
    assert all(c.zone=='p1:hand' for c in selected[:count])
    assert source.counters.get('+1/+1',0)==(0 if count else 1)
    roundtrip(s)


@pytest.mark.parametrize('command',[False,True])
@pytest.mark.parametrize('cold',[False,True])
def test_nashi_waits_for_real_commander_hand_outcome(cards,tmp_path,command,cold):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    source=put(s,NASHI,'battlefield')
    to_phase(s,'main1',7)
    original=next(c for c in s.state.cards.values() if c.owner=='p1' and c.commander_key)
    top(s,['Lightning Bolt'])
    act(s,'p1',type='move',card_ids=[original.id],to={'player':'p1','zone':'library'},position='top')
    to_phase(s,'declare_attackers',turn=7)
    attack(s,(source,'p2'))
    for _ in range(80):
        d=s.state.rules.decision
        if d:
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert d and d.resume.get('step')=='public_pick65'
    answer(s,[original.id])
    d=s.state.rules.decision
    assert d and d.resume.get('step')=='public_command65'
    assert original.zone=='p1:graveyard' and not source.counters.get('+1/+1')
    if cold:
        import os
        import subprocess
        import sys

        import app
        saved=tmp_path/'nashi65.json'
        saved.write_text(s.state.model_dump_json())
        code=r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from tests.game_helpers import act
from tests.test_rules_library_placements import settle
from tests.test_rules_designations import roundtrip
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
d=s.state.rules.decision
assert d and d.resume['step']=='public_command65'
act(s,d.player,type='choose',decision_id=d.id,option_ids=[sys.argv[5]])
settle(s)
assert s.state.cards[sys.argv[3]].zone==('p1:command' if sys.argv[5]=='yes' else 'p1:hand')
assert s.state.cards[sys.argv[4]].counters.get('+1/+1',0)==(1 if sys.argv[5]=='yes' else 0)
roundtrip(s)
'''
        backend=Path(app.__file__).resolve().parents[1]
        run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),original.id,source.id,'yes' if command else 'no'],cwd=backend,env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
        assert run.returncode==0,run.stdout+run.stderr
        return
    answer(s,['yes' if command else 'no'])
    assert original.zone==('p1:command' if command else 'p1:hand')
    assert source.counters.get('+1/+1',0)==int(command)
    roundtrip(s)


def test_room_two_actual_creatures_leave_graveyard_in_one_native_event(cards):
    from app.rules import coverage
    assert coverage.of_card_data(cards.resolve('Desecrated Tomb')).level=='FULL'
    s=setup(cards)
    put(s,'Desecrated Tomb','battlefield')
    room=put(s,ROOM,'battlefield')
    selected=top(s,['Grizzly Bears','Hill Giant','Lightning Bolt','Forest'])
    act(s,'p1',type='unlock_door',card_id=room.id,door=2)
    settle(s)
    answer(s,[c.id for c in selected[:2]])
    assert all(c.zone=='p1:hand' for c in selected[:2])
    assert len([c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Bat'])==1
    roundtrip(s)


@pytest.mark.parametrize('face',[0,1])
def test_room_actual_cast_each_door_and_front_grants_land_mana(cards,face):
    from app.game.errors import ActionError
    from app.rules import casting
    from tests.game_helpers import mana_pool
    s=setup(cards)
    selected=top(s,['Grizzly Bears','Forest','Lightning Bolt','Hill Giant'])
    room=put(s,ROOM,'hand')
    act(s,'p1',type='cast_spell',card_id=room.id,sources=[],face=face)
    settle(s)
    assert room.zone=='p1:battlefield'
    if face:
        d=s.state.rules.decision
        assert d and d.resume.get('step')=='public_pick65'
        answer(s,[selected[0].id,selected[1].id])
        assert all(c.zone=='p1:hand' for c in selected[:2])
    else:
        assert not s.state.rules.decision and all(c.zone=='p1:library' for c in selected)
        land=put(s,'Forest','battlefield')
        index=next(i for i,ab in casting.mana_abilities(s.state,land,cards) if any('U' in option for option in ab.options))
        before=mana_pool(s,'p1').get('U',0)
        act(s,'p1',type='activate_ability',card_id=land.id,ability=index,mana_choice='U')
        assert land.tapped and mana_pool(s,'p1').get('U',0)==before+1
    with pytest.raises(ActionError):
        act(s,'p1',type='unlock_door',card_id=room.id,door=face+1)
    roundtrip(s)
