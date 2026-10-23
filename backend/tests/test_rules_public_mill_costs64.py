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
    for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures/public_mill_costs64_cards.json').read_text())):
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
    names = list(dict.fromkeys([c['name'] for c in json.loads((Path(__file__).parent/'fixtures/public_mill_costs64_cards.json').read_text())] + ['Grizzly Bears','Hill Giant','Forest','Lightning Bolt']))
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


BARROW='Barrowgoyf'


def test_whole64(cards):
    from app.rules import coverage, public_mill_costs64
    assert coverage.of_card_data(cards.resolve(BARROW)).level=='FULL'
    assert public_mill_costs64.parse('You may mill three cards. If you do, return a creature card to your hand.') is None


@pytest.mark.parametrize('pay',[False,True])
def test_barrow_actual_combat_mill_cost_accept_or_decline(cards,pay):
    from app.rules.plan import Plan
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    put(s,'Forest','graveyard')
    put(s,'Lightning Bolt','graveyard')
    source=put(s,BARROW,'battlefield')
    to_phase(s,'main1',7)
    selected=top(s,['Grizzly Bears','Hill Giant','Greenhouse // Rickety Gazebo'])
    assert Plan(s.state,'p1',cards,None).ch(source).pt==(2,3)
    to_phase(s,'declare_attackers',turn=7)
    attack(s,(source,'p2'))
    for _ in range(80):
        d=s.state.rules.decision
        if d:
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert d and d.resume.get('step')=='optional_mill_cost64' and d.resume['n']==2
    answer(s,['yes' if pay else 'no'])
    if pay:
        d=s.state.rules.decision
        assert d and d.resume.get('step')=='pick_looked' and {o.id for o in d.options}=={c.id for c in selected[:2]}
        assert selected[2].zone=='p1:library'
        answer(s,[selected[0].id])
        assert selected[0].zone=='p1:hand' and selected[1].zone=='p1:graveyard'
    else:
        assert all(c.zone=='p1:library' for c in selected)
    assert s.state.players['p2'].life==38 and s.state.players['p1'].life==42
    roundtrip(s)


def test_barrow_cannot_pay_mill_cost_with_too_few_library_cards(cards):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    put(s,'Forest','graveyard')
    put(s,'Lightning Bolt','graveyard')
    source=put(s,BARROW,'battlefield')
    to_phase(s,'main1',7)
    only=top(s,['Grizzly Bears'])[0]
    remove=[cid for cid in s.state.zones['p1:library'] if cid!=only.id]
    act(s,'p1',type='move',card_ids=remove,to={'player':'p1','zone':'exile'})
    to_phase(s,'declare_attackers',turn=7)
    attack(s,(source,'p2'))
    for _ in range(80):
        assert s.state.rules.decision is None
        if s.state.players['p2'].life==38 and not s.state.zones.get('stack'):
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert s.state.players['p2'].life==38 and s.state.zones['p1:library']==[only.id]
    roundtrip(s)


@pytest.mark.parametrize('outcome',['exile','library:shuffle'])
@pytest.mark.parametrize('cold',[False,True])
def test_barrow_accepted_cost_waits_for_native_competing_replacement_then_picks_only_public_cards(cards,tmp_path,outcome,cold):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    put(s,'Forest','graveyard')
    put(s,'Lightning Bolt','graveyard')
    source=put(s,BARROW,'battlefield')
    to_phase(s,'main1',7)
    put(s,'Leyline of the Void','battlefield','p2')
    selected=top(s,['Darksteel Colossus','Grizzly Bears'])
    to_phase(s,'declare_attackers',turn=7)
    attack(s,(source,'p2'))
    for _ in range(80):
        d=s.state.rules.decision
        if d:
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert d and d.resume.get('step')=='optional_mill_cost64'
    answer(s,['yes'])
    d=s.state.rules.decision
    assert d and d.resume.get('step')=='prepared_mill61'
    assert all(c.zone=='p1:library' for c in selected)
    if cold:
        import os
        import subprocess
        import sys

        import app
        saved=tmp_path/'barrow616.json'
        saved.write_text(s.state.model_dump_json())
        code=r"""
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
assert d and d.resume['step']=='prepared_mill61'
choice=next(o.id for o in d.options if o.label.endswith(': '+sys.argv[4]))
act(s,d.player,type='choose',decision_id=d.id,option_ids=[choice]);settle(s)
d=s.state.rules.decision
assert d and d.resume['step']=='pick_looked'
assert {o.label for o in d.options}==({'Grizzly Bears','Darksteel Colossus'} if sys.argv[4]=='exile' else {'Grizzly Bears'})
act(s,d.player,type='choose',decision_id=d.id,option_ids=[sys.argv[3]]);settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:hand'
colossus=next(c for c in s.state.cards.values() if c.owner=='p1' and c.name=='Darksteel Colossus')
assert colossus.zone==('p1:exile' if sys.argv[4]=='exile' else 'p1:library')
assert s.state.players['p1'].life==42 and s.state.rules.decision is None
roundtrip(s)
"""
        backend=Path(app.__file__).resolve().parents[1]
        run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),selected[1].id,outcome],cwd=backend,env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
        assert run.returncode==0,run.stdout+run.stderr
        return
    answer(s,[next(o.id for o in d.options if o.label.endswith(': '+outcome))])
    d=s.state.rules.decision
    assert d and d.resume.get('step')=='pick_looked'
    expected={selected[1].id}|({selected[0].id} if outcome=='exile' else set())
    assert {o.id for o in d.options}==expected
    answer(s,[selected[1].id])
    assert selected[1].zone=='p1:hand' and s.state.players['p1'].life==42
    roundtrip(s)


@pytest.mark.parametrize('mode',['accept','missing_count'])
def test_true_cold_original_optional_mill_cost_choice(cards,tmp_path,mode):
    import os
    import subprocess
    import sys

    import app
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    put(s,'Forest','graveyard')
    put(s,'Lightning Bolt','graveyard')
    source=put(s,BARROW,'battlefield')
    to_phase(s,'main1',7)
    selected=top(s,['Grizzly Bears','Hill Giant','Greenhouse // Rickety Gazebo'])
    to_phase(s,'declare_attackers',turn=7)
    attack(s,(source,'p2'))
    for _ in range(80):
        d=s.state.rules.decision
        if d:
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert d and d.resume.get('step')=='optional_mill_cost64' and d.resume['n']==2
    if mode=='missing_count':
        d.resume.pop('n')
    saved=tmp_path/'barrowcost.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_library_placements import settle
from tests.test_rules_designations import roundtrip
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
d=s.state.rules.decision;assert d and d.resume['step']=='optional_mill_cost64'
before=s.state.model_dump_json()
if sys.argv[4]=='missing_count':
 try:act(s,d.player,type='choose',decision_id=d.id,option_ids=['yes'])
 except ActionError:pass
 else:raise AssertionError('Missing original count was accepted')
 assert s.state.model_dump_json()==before
else:
 act(s,d.player,type='choose',decision_id=d.id,option_ids=['yes']);settle(s)
 d=s.state.rules.decision;assert d and d.resume['step']=='pick_looked'
 assert {o.label for o in d.options}=={'Grizzly Bears','Hill Giant'}
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[sys.argv[3]]);settle(s)
 assert s.state.cards[sys.argv[3]].zone=='p1:hand' and s.state.rules.decision is None
 roundtrip(s)
'''
    backend=Path(app.__file__).resolve().parents[1]
    run=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),selected[0].id,mode],cwd=backend,env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert run.returncode==0,run.stdout+run.stderr


def test_barrow_original_payable_cost_survives_bruvac_partial_replacement_mill(cards):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    put(s,'Forest','graveyard')
    put(s,'Lightning Bolt','graveyard')
    source=put(s,BARROW,'battlefield')
    to_phase(s,'main1',7)
    put(s,'Bruvac the Grandiloquent','battlefield','p2')
    selected=top(s,['Grizzly Bears','Hill Giant','Greenhouse // Rickety Gazebo'])
    remove=[cid for cid in s.state.zones['p1:library'] if cid not in {c.id for c in selected}]
    act(s,'p1',type='move',card_ids=remove,to={'player':'p1','zone':'exile'})
    to_phase(s,'declare_attackers',turn=7)
    attack(s,(source,'p2'))
    for _ in range(80):
        d=s.state.rules.decision
        if d and d.kind=='declare_blockers':
            act(s,d.player,type='declare_blockers',blocks=[])
            continue
        if d:
            break
        act(s,s.state.rules.priority,type='pass_priority')
    assert d and d.resume.get('step')=='optional_mill_cost64' and d.resume['n']==2
    answer(s,['yes'])
    d=s.state.rules.decision
    assert d and d.resume.get('step')=='pick_looked' and {o.id for o in d.options}=={c.id for c in selected[:2]}
    assert s.state.zones['p1:library']==[] and all(c.zone=='p1:graveyard' for c in selected)
    answer(s,[selected[0].id])
    assert selected[0].zone=='p1:hand'
    roundtrip(s)
