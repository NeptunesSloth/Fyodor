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
    for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures/collateral69_cards.json').read_text())):
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
    names = list(dict.fromkeys([c['name'] for c in json.loads((Path(__file__).parent/'fixtures/collateral69_cards.json').read_text()) if c['name'] != 'Urza, Planeswalker'] + ['Grizzly Bears','Hill Giant','Forest','Lightning Bolt']))
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



NAMES=['Geistblast',"Gollum's Bite",'Wither and Bloom']


def test_collateral_whole_classification69(cards):
    from app.rules.coverage import of_card_data
    for name in NAMES:
        result=of_card_data(cards.resolve(name))
        assert result.level=='FULL',(name,result)


@pytest.mark.parametrize('name',NAMES)
def test_actual_normal_cast_is_only_spell_body69(cards,name):
    s=setup(cards)
    friendly=put(s,'Grizzly Bears','battlefield')
    if name=='Geistblast':
        target='p2'
    else:
        target=put(s,'Grizzly Bears' if name=="Gollum's Bite" else 'Hill Giant','battlefield','p2').id
    source=cast(s,name,targets=[target])
    assert source.zone=='p1:graveyard'
    assert not s.state.rules.decision and not s.state.rules.stack
    assert s.state.rules.ring_tempted.get('p1',0)==0
    assert friendly.counters.get('+1/+1',0)==0
    if name=='Geistblast':
        assert s.state.players['p2'].life==38
    else:
        assert s.state.cards[target].zone=='p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name,cost',[("Gollum's Bite",3),('Wither and Bloom',1)])
def test_actual_graveyard_activation_sorcery_timing_and_cost69(cards,name,cost):
    from app.game.errors import ActionError
    s=setup(cards)
    source=put(s,name,'graveyard')
    friendly=put(s,'Grizzly Bears','battlefield')
    kwargs={} if name=="Gollum's Bite" else {'targets':[friendly.id]}
    to_phase(s,'declare_attackers',turn=1)
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=1,sources=[],**kwargs)
    assert s.state.model_dump_json()==before
    to_phase(s,'main2',turn=1)
    act(s,'p1',type='add_mana',player='p1',mana={'C':10,'B':10,'R':2})
    act(s,'p1',type='set_prefs',hold_priority=True)
    bolt=put(s,'Lightning Bolt','hand')
    act(s,'p1',type='cast_spell',card_id=bolt.id,sources=[],targets=['p2'])
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='activate_ability',card_id=source.id,ability=1,sources=[],**kwargs)
    assert s.state.model_dump_json()==before
    settle(s)
    mana=s.state.players['p1'].mana.copy()
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,sources=[],**kwargs)
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.players['p1'].mana['B']==mana['B']-1
    assert s.state.players['p1'].mana['C']==mana['C']-cost
    settle(s)
    if name=="Gollum's Bite":
        d=s.state.rules.decision
        if d is not None:
            assert d.player=='p1'
            answer(s,[friendly.id])
        assert s.state.rules.ring_tempted['p1']==1
        assert s.state.rules.ring_bearers['p1']==s.state.rules.object_id(friendly.id)
    else:
        assert s.state.cards[friendly.id].counters.get('+1/+1')==1
    assert not s.state.rules.decision
    roundtrip(s)


def geist_copy69(cards):
    s=setup(cards)
    source=cast(s,'Geistblast',targets=['p2'])
    assert source.zone=='p1:graveyard' and s.state.players['p2'].life==38
    act(s,'p1',type='set_prefs',hold_priority=True)
    bolt=put(s,'Lightning Bolt','hand')
    act(s,'p1',type='cast_spell',card_id=bolt.id,sources=[],targets=['p2'])
    mana=s.state.players['p1'].mana.copy()
    act(s,'p1',type='activate_ability',card_id=source.id,ability=1,sources=[],targets=[bolt.id])
    assert s.state.cards[source.id].zone=='p1:exile'
    assert s.state.players['p1'].mana['C']==mana['C']-2 and s.state.players['p1'].mana['U']==mana['U']-1
    settle(s)
    d=s.state.rules.decision
    assert d and d.prompt.startswith('Copy of Lightning Bolt') and 'p3' in {o.id for o in d.options}
    return s,source,bolt


def test_geistblast_actual_exile_paid_copy_retargets_only_copy69(cards):
    s,source,bolt=geist_copy69(cards)
    answer(s,['p3'])
    assert s.state.players['p2'].life==35 and s.state.players['p3'].life==37
    assert s.state.cards[source.id].zone=='p1:exile' and s.state.cards[bolt.id].zone=='p1:graveyard'
    assert not s.state.rules.stack and not s.state.rules.decision
    roundtrip(s)


def test_true_cold_geistblast_paid_copy_target_question69(cards,tmp_path):
    import os
    import subprocess
    import sys

    import app
    s,source,bolt=geist_copy69(cards)
    path=tmp_path/'collateral69.json'
    path.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from tests.game_helpers import act
from tests.test_rules_library_placements import settle
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
source,bolt=sys.argv[3:5]
assert s.state.cards[source].zone=='p1:exile'
assert [t.id for t in s.state.rules.stack[bolt].targets]==['p2']
d=s.state.rules.decision;assert d and d.prompt.startswith('Copy of Lightning Bolt')
act(s,d.player,type='choose',decision_id=d.id,option_ids=['p3']);settle(s)
assert s.state.players['p2'].life==35 and s.state.players['p3'].life==37
assert s.state.cards[source].zone=='p1:exile' and s.state.cards[bolt].zone=='p1:graveyard'
assert not s.state.rules.decision and not s.state.rules.stack
'''
    backend=Path(app.__file__).resolve().parent.parent
    run=subprocess.run([sys.executable,'-c',code,str(path),str(cards.db_path),source.id,bolt.id],cwd=backend,env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert run.returncode==0,run.stdout+run.stderr
