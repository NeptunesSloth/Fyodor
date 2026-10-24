"""Native public milling and delayed optional Equipment continuations."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures/post_mill_continuations60_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='oc59', number=str(i), **{k:v for k,v in c.items() if k not in ('name','set_code','number')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()

def setup(cards):
    names = [CACHE, MIDNIGHT, DUMMY, 'Bruvac the Grandiloquent', 'Squirrel Sovereign', 'Chatterfang, Squirrel General', 'Environmental Sciences', 'Ashes of the Fallen', 'Wheel of Sun and Moon', 'Grizzly Bears', 'Hill Giant', 'Plains', 'Forest', 'Bonesplitter', 'Sol Ring', 'Rest in Peace', 'Lightning Bolt', 'Disperse', 'Darksteel Colossus']
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


@pytest.mark.parametrize('controlled,selected',[(True,None),(False,'Squirrel Sovereign'),(False,'Forest'),(False,None),(True,'Squirrel Sovereign')])
def test_cache_native_mill_pick_and_actual_squirrel_conditions(cards,controlled,selected):
    s=setup(cards)
    if controlled:
        put(s,'Chatterfang, Squirrel General','battlefield')
    milled=top(s,['Squirrel Sovereign','Forest','Grizzly Bears','Lightning Bolt'])
    source=cast(s,CACHE)
    d=s.state.rules.decision
    assert source.zone=='stack'
    assert d and {o.id for o in d.options}=={c.id for c in milled[:3]}
    chosen=next((c for c in milled if c.name==selected),None)
    answer(s,[chosen.id] if chosen else [])
    assert source.zone=='p1:graveyard'
    food=[c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Food']
    assert len(food)==int(controlled or selected=='Squirrel Sovereign')
    if chosen:
        assert chosen.zone=='p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('rip',[True,False])
@pytest.mark.parametrize('pick',[True,False])
def test_midnight_native_public_return_choice(cards,rip,pick):
    s=setup(cards)
    if rip:
        cast(s,'Rest in Peace')
    milled=top(s,['Forest','Grizzly Bears','Lightning Bolt','Sol Ring'])
    cast(s,MIDNIGHT)
    d=s.state.rules.decision
    assert d and {o.id for o in d.options}=={milled[i].id for i in [0,1,3]}
    answer(s,[milled[1].id] if pick else [])
    expected='p1:exile' if rip else 'p1:graveyard'
    assert all(c.zone==('p1:hand' if pick and c is milled[1] else expected) for c in milled)
    roundtrip(s)


@pytest.mark.parametrize('lesson',[True,False])
@pytest.mark.parametrize('rip',[True,False])
def test_dummy_native_mill_land_return_and_lesson_life(cards,lesson,rip):
    s=setup(cards)
    source=cast(s,DUMMY)
    to_phase(s,'main1',4)
    act(s,'p1',type='add_mana',player='p1',mana={'C':20,'W':20})
    if rip:
        cast(s,'Rest in Peace')
    milled=top(s,['Environmental Sciences' if lesson else 'Forest'])[0]
    before=s.state.players['p1'].life
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    settle(s)
    d=s.state.rules.decision
    assert d
    assert [o.id for o in d.options]==([] if lesson else [milled.id])
    answer(s,[] if lesson else [milled.id])
    assert s.state.players['p1'].life==before+(2 if lesson else 0)
    if not lesson:
        assert milled.zone=='p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('name',[CACHE,MIDNIGHT,DUMMY])
def test_whole_printed_post_mill60_cards_are_full(cards,name):
    from app.rules import coverage
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


def test_cache_captures_returned_squirrel_before_graveyard_type_grant_ends(cards):
    from app.rules.plan import Plan
    s=setup(cards)
    cast(s,'Ashes of the Fallen')
    d=s.state.rules.decision
    assert d and 'Squirrel' in [o.id for o in d.options]
    answer(s,['Squirrel'])
    milled=top(s,['Grizzly Bears','Forest','Lightning Bolt','Sol Ring'])
    cast(s,CACHE)
    assert 'Squirrel' in Plan(s.state,'p1',cards,None).ch(milled[0]).subtypes
    answer(s,[milled[0].id])
    assert milled[0].zone=='p1:hand' and 'Squirrel' not in Plan(s.state,'p1',cards,None).ch(milled[0]).subtypes
    food=[c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Food']
    assert len(food)==1
    roundtrip(s)


@pytest.mark.parametrize('cold',[True,False])
def test_cache_commander_hand_replacement_is_not_actual_squirrel_return(cards,tmp_path,cold):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable
    names=[CACHE,'Forest','Grizzly Bears','Lightning Bolt','Sol Ring']
    decks=[deck(cards,'Chatterfang, Squirrel General',[(1,n) for n in names]+[(20,'Forest')]),
           deck(cards,'Krenko, Mob Boss',[(20,'Forest')]),deck(cards,'Krenko, Mob Boss',[(20,'Forest')])]
    s=GameSession(enable(new_game([PlayerSetup(str(i),cards=d) for i,d in enumerate(decks)],shuffle=False)),cards=cards)
    act(s,'p1',type='pass_priority')
    for pid in s.state.players:
        act(s,pid,type='set_prefs',response='on')
    to_phase(s,'main1',1)
    act(s,'p1',type='add_mana',player='p1',mana={'C':10,'G':10})
    commander=next(c for c in s.state.cards.values() if c.owner=='p1' and c.commander_key)
    top(s,['Forest','Grizzly Bears','Lightning Bolt'])
    act(s,'p1',type='move',card_ids=[commander.id],to={'player':'p1','zone':'library'},position='top')
    cast(s,CACHE)
    d=s.state.rules.decision
    assert d and commander.id in [o.id for o in d.options]
    answer(s,[commander.id])
    d=s.state.rules.decision
    assert d and d.resume['step']=='post_mill_command60'
    assert commander.zone=='p1:graveyard'
    if cold:
        import os
        import subprocess
        import sys
        saved=tmp_path/'commander60.json'
        saved.write_text(s.state.model_dump_json())
        code=r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_placements import settle
from tests.test_rules_designations import roundtrip
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
d=s.state.rules.decision;assert d and d.resume['step']=='post_mill_command60'
act(s,d.player,type='choose',decision_id=d.id,option_ids=['yes']);settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:command'
assert not [c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Food']
roundtrip(s)
"""
        result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),commander.id],capture_output=True,text=True,timeout=60,env=os.environ.copy())
        assert result.returncode==0,result.stdout+result.stderr
        return
    answer(s,['yes'])
    assert commander.zone=='p1:command'
    assert not [c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Food']
    roundtrip(s)


@pytest.mark.parametrize('name',[CACHE,MIDNIGHT,DUMMY])
def test_genuine_cold_post_mill60_decision(cards,tmp_path,name):
    import os
    import subprocess
    import sys
    s=setup(cards)
    if name==DUMMY:
        source=cast(s,DUMMY)
        to_phase(s,'main1',4)
        selected=top(s,['Environmental Sciences'])[0]
        act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
        settle(s)
    else:
        cast(s,'Rest in Peace')
        selected=top(s,['Squirrel Sovereign','Forest','Grizzly Bears','Lightning Bolt'])[0]
        source=cast(s,name)
    assert s.state.rules.decision
    saved=tmp_path/'postmill60.json'
    saved.write_text(s.state.model_dump_json())
    code=r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_placements import settle
from tests.test_rules_designations import roundtrip
saved,db,name,source,selected=sys.argv[1:]
p=Path(saved);repo=CardRepository(Path(db),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
d=s.state.rules.decision;assert d
ids=[] if name=='Sparring Dummy' else [selected]
act(s,d.player,type='choose',decision_id=d.id,option_ids=ids);settle(s)
if name=='Sparring Dummy':
 assert s.state.players['p1'].life==42
else:
 assert s.state.cards[selected].zone=='p1:hand'
 food=[c for c in s.state.cards.values() if c.is_token and c.name=='Food' and c.zone=='p1:battlefield']
 assert len(food)==int(name=='Cache Grab')
roundtrip(s)
"""
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),name,source.id,selected.id],capture_output=True,text=True,timeout=60,env=os.environ.copy())
    assert result.returncode==0,result.stdout+result.stderr


def test_dummy_bruvac_mills_two_offers_one_land_and_gains_life_once(cards):
    s=setup(cards)
    source=cast(s,DUMMY)
    to_phase(s,'main1',4)
    put(s,'Bruvac the Grandiloquent','battlefield','p2')
    milled=top(s,['Forest','Environmental Sciences'])
    before=s.state.players['p1'].life
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
    settle(s)
    assert all(c.zone=='p1:graveyard' for c in milled)
    d=s.state.rules.decision
    assert d and [o.id for o in d.options]==[milled[0].id]
    answer(s,[milled[0].id])
    assert milled[0].zone=='p1:hand' and s.state.players['p1'].life==before+2
    roundtrip(s)


def test_cache_empty_library_with_controlled_squirrel_still_creates_usable_food(cards):
    s=setup(cards)
    source=put(s,CACHE,'hand')
    # This Squirrel has no token replacement rider.
    put(s,'Squirrel Sovereign','battlefield')
    for cid in list(s.state.zones['p1:library']):
        act(s,'p1',type='move',card_ids=[cid],to={'player':'p1','zone':'hand'})
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[])
    settle(s)
    assert s.state.rules.decision is None
    foods=[c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.is_token and c.name=='Food']
    assert len(foods)==1
    before=s.state.players['p1'].life
    act(s,'p1',type='activate_ability',card_id=foods[0].id,ability=0,sources=[])
    settle(s)
    assert s.state.players['p1'].life==before+3
    roundtrip(s)


@pytest.mark.parametrize('name',[CACHE,MIDNIGHT,DUMMY])
@pytest.mark.parametrize('outcome',['exile','library:shuffle'])
def test_post_mill60_prepared_616_completes_before_public_pick(cards,name,outcome):
    s=setup(cards)
    if name==DUMMY:
        source=cast(s,DUMMY)
        to_phase(s,'main1',4)
        act(s,'p1',type='add_mana',player='p1',mana={'C':20,'W':20})
    cast(s,'Rest in Peace')
    milled=top(s,['Darksteel Colossus','Squirrel Sovereign','Forest','Sol Ring'])
    if name==DUMMY:
        act(s,'p1',type='activate_ability',card_id=source.id,ability=1)
        settle(s)
    else:
        source=cast(s,name)
    d=s.state.rules.decision
    assert d and d.resume['step']=='prepared_mill61'
    assert milled[0].zone=='p1:library'
    answer(s,[next(o.id for o in d.options if o.label.endswith(': '+outcome))])
    d=s.state.rules.decision
    if name==DUMMY:
        if d:
            assert not d.options
            answer(s,[])
        assert s.state.players['p1'].life==40
    else:
        assert d and d.resume['step'] in ('post_mill_pick60','pick_looked')
        assert (milled[0].id in [o.id for o in d.options])==(outcome=='exile')
        answer(s,[milled[1].id])
        assert milled[1].zone=='p1:hand'
        foods=[c for c in s.state.cards.values() if c.is_token and c.name=='Food' and c.zone=='p1:battlefield']
        assert len(foods)==int(name==CACHE)
    roundtrip(s)
