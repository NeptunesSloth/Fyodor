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

AIR, REQUEST = 'Airlift Chaplain', 'Unexpected Request'

@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures/public_mill_attachment59_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='oc59', number=str(i), **{k:v for k,v in c.items() if k not in ('name','set_code','number')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()

def setup(cards):
    names = [AIR, REQUEST, 'Grizzly Bears', 'Hill Giant', 'Plains', 'Forest', 'Bonesplitter', 'Sol Ring', 'Rest in Peace', 'Lightning Bolt', 'Disperse', 'Darksteel Colossus', 'Progenitus']
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

@pytest.mark.parametrize('selected', ['Plains','Grizzly Bears',None])
def test_airlift_native_public_mill_choice_and_decline(cards, selected):
    s = setup(cards)
    milled = top(s, ['Plains','Grizzly Bears','Hill Giant'])
    source = cast(s, AIR)
    d = s.state.rules.decision
    assert d and set(o.id for o in d.options) == {c.id for c in milled[:2]}, (d.resume if d else None, [(c.id,c.name,c.zone) for c in milled])
    assert all(c.zone=='p1:graveyard' for c in milled)
    chosen = next((c for c in milled if c.name==selected), None)
    answer(s, [chosen.id] if chosen else [])
    assert source.counters == ({} if chosen else {'+1/+1':1})
    assert all(c.zone==('p1:hand' if c is chosen else 'p1:graveyard') for c in milled)
    roundtrip(s)


def test_airlift_milled_exile_public_replacement_still_available(cards):
    s = setup(cards)
    cast(s, 'Rest in Peace')
    milled = top(s, ['Plains','Grizzly Bears','Hill Giant'])
    source = cast(s, AIR)
    d = s.state.rules.decision
    assert d and set(o.id for o in d.options) == {c.id for c in milled[:2]}, (d.resume if d else None, [(c.id,c.name,c.zone) for c in milled])
    assert all(c.zone=='p1:exile' for c in milled)
    answer(s, [milled[0].id])
    assert milled[0].zone=='p1:hand' and not source.counters
    roundtrip(s)

@pytest.mark.parametrize('attach', [True,False])
def test_request_optional_attachment_native_next_end_step(cards, attach):
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p2', type='tap', card_ids=[target.id], tapped=True)
    equipment = put(s, 'Bonesplitter', 'battlefield')
    foreign = put(s, 'Bonesplitter', 'battlefield', 'p2')
    cast(s, REQUEST, targets=[target.id])
    assert target.controller=='p1' and not target.tapped
    d = s.state.rules.decision
    assert d and equipment.id in [o.id for o in d.options] and foreign.id not in [o.id for o in d.options]
    answer(s, [equipment.id] if attach else [])
    assert equipment.attached_to==(target.id if attach else None)
    assert len(s.state.rules.delayed)==int(attach)
    to_phase(s, 'end', 1)
    settle(s)
    assert equipment.attached_to is None
    assert target.controller=='p1'
    roundtrip(s)


@pytest.mark.parametrize('empty', [True, False])
def test_airlift_no_eligible_milled_cards_or_empty_library_gets_counter(cards, empty):
    s = setup(cards)
    if empty:
        source = put(s, AIR, 'hand')
        for cid in list(s.state.zones['p1:library']):
            act(s, 'p1', type='move', card_ids=[cid], to={'player':'p1','zone':'hand'})
        act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
        settle(s)
    else:
        top(s, ['Hill Giant', 'Forest', 'Sol Ring'])
        source = cast(s, AIR)
    if s.state.rules.decision:
        assert not s.state.rules.decision.options
        answer(s, [])
    assert source.counters == {'+1/+1':1}
    roundtrip(s)


def test_airlift_self_shuffle_hidden_replacement_not_offered(cards):
    s = setup(cards)
    milled = top(s, ['Darksteel Colossus','Plains','Grizzly Bears'])
    source = cast(s, AIR)
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {c.id for c in milled[1:]}
    assert milled[0].id not in [o.id for o in d.options]
    answer(s, [milled[1].id])
    assert milled[1].zone=='p1:hand' and not source.counters
    roundtrip(s)


def test_request_delayed_detach_follows_old_equipment_to_different_host(cards):
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    own = put(s, 'Grizzly Bears', 'battlefield')
    equipment = put(s, 'Bonesplitter', 'battlefield')
    cast(s, REQUEST, targets=[target.id])
    answer(s, [equipment.id])
    act(s, 'p1', type='activate_ability', card_id=equipment.id, ability=1, targets=[own.id], sources=[])
    settle(s)
    assert equipment.attached_to==own.id
    to_phase(s, 'end', 1)
    settle(s)
    assert equipment.attached_to is None
    roundtrip(s)


def test_request_delayed_detach_never_detaches_new_equipment_object(cards):
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    equipment = put(s, 'Bonesplitter', 'battlefield')
    cast(s, REQUEST, targets=[target.id])
    answer(s, [equipment.id])
    cast(s, 'Disperse', targets=[equipment.id])
    assert equipment.zone=='p1:hand'
    act(s, 'p1', type='cast_spell', card_id=equipment.id, sources=[])
    settle(s)
    act(s, 'p1', type='activate_ability', card_id=equipment.id, ability=1, targets=[target.id], sources=[])
    settle(s)
    assert equipment.attached_to==target.id
    to_phase(s, 'end', 1)
    settle(s)
    assert equipment.attached_to==target.id
    roundtrip(s)


def test_request_original_target_left_before_resolution_means_no_attachment(cards):
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    equipment = put(s, 'Bonesplitter', 'battlefield')
    source = put(s, REQUEST, 'hand')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[target.id], sources=[])
    act(s, 'p1', type='move', card_ids=[target.id], to={'player':'p2','zone':'exile'})
    settle(s)
    assert source.zone=='p1:graveyard' and equipment.attached_to is None
    assert s.state.rules.decision is None and not s.state.rules.delayed
    roundtrip(s)


def test_airlift_commander_hand_replacement_is_still_paid_choice(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable
    names = [AIR, REQUEST, 'Grizzly Bears', 'Hill Giant', 'Plains', 'Bonesplitter']
    decks = [deck(cards, 'Honest Rutstein', [(1,n) for n in names]+[(20,'Forest')]),
             deck(cards, 'Krenko, Mob Boss', [(20,'Forest')]),
             deck(cards, 'Krenko, Mob Boss', [(20,'Forest')])]
    s = GameSession(enable(new_game([PlayerSetup(str(i),cards=d) for i,d in enumerate(decks)],shuffle=False)),cards=cards)
    act(s,'p1',type='pass_priority')
    for pid in s.state.players:
        act(s,pid,type='set_prefs',response='on')
    to_phase(s,'main1',1)
    act(s,'p1',type='add_mana',player='p1',mana={'C':10,'W':10})
    commander = next(c for c in s.state.cards.values() if c.owner=='p1' and c.commander_key)
    top(s, ['Plains','Grizzly Bears'])
    act(s,'p1',type='move',card_ids=[commander.id],to={'player':'p1','zone':'library'},position='top')
    source = cast(s,AIR)
    d = s.state.rules.decision
    assert d and d.resume['step']=='pick_looked' and commander.id in [o.id for o in d.options]
    answer(s,[commander.id])
    d=s.state.rules.decision
    assert d and d.resume['step']=='commander_instead'
    answer(s,['yes'])
    assert commander.zone=='p1:command' and not source.counters
    roundtrip(s)


@pytest.mark.parametrize('name',[AIR,REQUEST])
def test_genuine_cold_public_pick_or_delayed_attach_continuation(cards,tmp_path,name):
    import os
    import subprocess
    import sys
    s=setup(cards)
    if name==AIR:
        cast(s,'Rest in Peace')
        milled=top(s,['Plains','Grizzly Bears','Hill Giant'])
        source=cast(s,AIR)
        chosen=milled[0]
        target=source
    else:
        target=put(s,'Grizzly Bears','battlefield','p2')
        chosen=put(s,'Bonesplitter','battlefield')
        source=cast(s,REQUEST,targets=[target.id])
    assert s.state.rules.decision
    saved=tmp_path/'pending59.json'
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
from tests.test_rules_wave30m_durations import to_phase
saved,db,name,source,chosen,target=sys.argv[1:]
p=Path(saved);repo=CardRepository(Path(db),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
d=s.state.rules.decision;assert d and chosen in [o.id for o in d.options]
act(s,d.player,type='choose',decision_id=d.id,option_ids=[chosen]);settle(s)
if name=='Airlift Chaplain':
 assert s.state.cards[chosen].zone=='p1:hand' and not s.state.cards[source].counters
else:
 assert s.state.cards[chosen].attached_to==target and len(s.state.rules.delayed)==1
 s=GameSession(GameState.model_validate_json(s.state.model_dump_json()),cards=repo)
 to_phase(s,'end',1);settle(s)
 assert s.state.cards[chosen].attached_to is None
roundtrip(s)
"""
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),name,source.id,chosen.id,target.id],capture_output=True,text=True,timeout=60,env=os.environ.copy())
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('name',[AIR,REQUEST])
def test_whole_printed_optional59_cards_are_full(cards,name):
    from app.rules import coverage
    assert coverage.of_card_data(cards.resolve(name)).level=='FULL'


@pytest.mark.parametrize('outcome',['exile','library:shuffle'])
def test_airlift_competing_zone_replacement_finishes_before_public_pick(cards,outcome):
    s=setup(cards)
    cast(s,'Rest in Peace')
    milled=top(s,['Darksteel Colossus','Plains','Grizzly Bears'])
    source=cast(s,AIR)
    d=s.state.rules.decision
    assert d and d.resume.get('step')=='prepared_mill61'
    assert all(c.zone=='p1:library' for c in milled)
    option=next(o.id for o in d.options if o.label.endswith(': '+outcome))
    answer(s,[option])
    d=s.state.rules.decision
    assert d and d.resume.get('step')=='pick_looked'
    assert {o.id for o in d.options}=={c.id for c in milled[1:]}
    answer(s,[milled[1].id])
    assert milled[1].zone=='p1:hand' and not source.counters
    roundtrip(s)


def test_airlift_prepares_two_competing_routes_before_any_shuffle(cards):
    s=setup(cards)
    cast(s,'Rest in Peace')
    milled=top(s,['Darksteel Colossus','Progenitus','Plains'])
    source=cast(s,AIR)
    d=s.state.rules.decision
    assert d and d.resume['step']=='prepared_mill61'
    answer(s,[next(o.id for o in d.options if o.label.endswith(': exile'))])
    d=s.state.rules.decision
    assert d and d.resume['step']=='prepared_mill61'
    assert all(c.zone=='p1:library' for c in milled)
    answer(s,[next(o.id for o in d.options if o.label.endswith(': library:shuffle'))])
    d=s.state.rules.decision
    assert d and [o.id for o in d.options]==[milled[2].id]
    assert milled[0].zone=='p1:exile'
    answer(s,[milled[2].id])
    assert milled[2].zone=='p1:hand' and not source.counters
    roundtrip(s)


def test_genuine_cold_pending_prepared_mill_choice59(cards,tmp_path):
    import os
    import subprocess
    import sys
    s=setup(cards)
    cast(s,'Rest in Peace')
    milled=top(s,['Darksteel Colossus','Progenitus','Plains'])
    source=cast(s,AIR)
    d=s.state.rules.decision
    assert d and d.resume['step']=='prepared_mill61'
    answer(s,[next(o.id for o in d.options if o.label.endswith(': exile'))])
    assert s.state.rules.decision.resume['step']=='prepared_mill61'
    saved=tmp_path/'prepared59.json'
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
d=s.state.rules.decision;assert d and d.resume['step']=='prepared_mill61'
option=next(o.id for o in d.options if o.label.endswith(': library:shuffle'))
act(s,d.player,type='choose',decision_id=d.id,option_ids=[option]);settle(s)
d=s.state.rules.decision;assert d and d.resume['step']=='pick_looked'
assert [o.id for o in d.options]==[sys.argv[3]]
act(s,d.player,type='choose',decision_id=d.id,option_ids=[sys.argv[3]]);settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:hand' and not s.state.cards[sys.argv[4]].counters
roundtrip(s)
"""
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),milled[2].id,source.id],capture_output=True,text=True,timeout=60,env=os.environ.copy())
    assert result.returncode==0,result.stdout+result.stderr
