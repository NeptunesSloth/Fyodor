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
    for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures/gwenom_top70_cards.json').read_text())):
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
    names = list(dict.fromkeys([c['name'] for c in json.loads((Path(__file__).parent/'fixtures/gwenom_top70_cards.json').read_text()) if c['name'] != 'Urza, Planeswalker'] + ['Grizzly Bears','Forest','Lightning Bolt']))
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



def grant70(cards):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    source=put(s,'Gwenom, Remorseless','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    attack(s,(source,'p2'))
    settle(s)
    assert any(p.look_top and p.life_mv and p.free for p in s.state.rules.permissions)
    to_phase(s,'main2',turn=4)
    return s,source


def test_whole70(cards):
    from app.rules.coverage import of_card_data
    assert of_card_data(cards.resolve('Gwenom, Remorseless')).level=='FULL'


def test_actual_attack_life_cast_and_private_top70(cards):
    from app.game.errors import ActionError
    s,source=grant70(cards)
    bears=top(s,['Grizzly Bears'])[0]
    assert [0,bears.id] in s.view('p1')['zones']['p1:library']['known']
    assert s.view('p2')['zones']['p1:library']['known']==[]
    act(s,'p1',type='add_mana',player='p1',mana={'G':20,'C':20})
    before=s.state.players['p1'].life
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=bears.id,sources=[])
    act(s,'p1',type='cast_spell',card_id=bears.id,sources=[],free=True)
    settle(s)
    assert bears.zone=='p1:battlefield'
    assert s.state.players['p1'].life==before-2
    roundtrip(s)


def test_land_limit_current_top_and_source_departure70(cards):
    from app.game.errors import ActionError
    s,source=grant70(cards)
    forest,mountain=top(s,['Forest','Mountain'])
    before=s.state.players['p1'].life
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    act(s,'p1',type='play_land',card_id=forest.id)
    assert forest.zone=='p1:battlefield'
    with pytest.raises(ActionError):
        act(s,'p1',type='play_land',card_id=mountain.id)
    assert mountain.zone=='p1:library' and s.state.players['p1'].life==before
    assert [0,mountain.id] in s.view('p1')['zones']['p1:library']['known']
    to_phase(s,'main1',turn=5)
    assert not any(p.look_top for p in s.state.rules.permissions)
    roundtrip(s)


@pytest.mark.parametrize('lock',['Platinum Emperion','Angel of Jubilation','insufficient'])
def test_life_payment_restrictions70(cards,lock):
    from app.game.errors import ActionError
    s,source=grant70(cards)
    bears=top(s,['Grizzly Bears'])[0]
    if lock=='insufficient':
        act(s,'p1',type='life',player='p1',delta=1-s.state.players['p1'].life)
    else:
        put(s,lock,'battlefield')
    before=s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=bears.id,sources=[],free=True)
    assert s.state.model_dump_json()==before


def test_x_life_alternative_zero70(cards):
    from app.game.errors import ActionError
    s,_=grant70(cards)
    spell=top(s,['Fireball'])[0]
    life=s.state.players['p1'].life
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=spell.id,sources=[],free=True,x_value=3,targets=['p2'])
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[],free=True,x_value=0,targets=['p2'])
    assert s.state.players['p1'].life==life-1
    settle(s)
    roundtrip(s)


def test_modal_back_is_land_front_uses_spell_mv70(cards):
    s,_=grant70(cards)
    spell=top(s,['Shatterskull Smashing // Shatterskull, the Hammer Pass'])[0]
    life=s.state.players['p1'].life
    act(s,'p1',type='play_land',card_id=spell.id,face=1)
    d=s.state.rules.decision
    assert d and 'life' in d.prompt
    answer(s,[o.id for o in d.options if o.id!='pay'])
    assert spell.zone=='p1:battlefield' and s.state.players['p1'].life==life
    roundtrip(s)


def test_true_cold_attack_grant_survives_source_and_casts_dynamic_top70(cards,tmp_path):
    import os
    import subprocess
    import sys

    import app
    s,source=grant70(cards)
    bears=top(s,['Grizzly Bears'])[0]
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
    path=tmp_path/'gwenom70.json'
    path.write_text(s.state.model_dump_json())
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
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
bears=sys.argv[3];before=s.state.players['p1'].life
assert [0,bears] in s.view('p1')['zones']['p1:library']['known']
assert s.view('p2')['zones']['p1:library']['known']==[]
try:
    act(s,'p1',type='cast_spell',card_id=bears,sources=[])
except ActionError:pass
else:raise AssertionError('Normal mana bypassed required life')
act(s,'p1',type='cast_spell',card_id=bears,sources=[],free=True);settle(s)
assert s.state.cards[bears].zone=='p1:battlefield'
assert s.state.players['p1'].life==before-2
'''
    env={**os.environ,'PYTHONPATH':str(Path(app.__file__).resolve().parent.parent)}
    proc=subprocess.run([sys.executable,'-c',code,str(path),str(cards.db_path),bears.id],env=env,capture_output=True,text=True)
    assert proc.returncode==0,proc.stdout+proc.stderr


def test_trigger_original_controller_survives_actual_response_theft70(cards):
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    source=put(s,'Gwenom, Remorseless','battlefield')
    to_phase(s,'declare_attackers',turn=4)
    attack(s,(source,'p2'))
    assert s.state.rules.stack and not s.state.rules.permissions
    # Respond to the native attack trigger with an actual control-changing instant.
    ray=put(s,'Word of Seizing','hand','p2')
    act(s,'p2',type='add_mana',player='p2',mana={'R':2,'C':3})
    while s.state.rules.priority!='p2':
        act(s,s.state.rules.priority,type='pass_priority')
    act(s,'p2',type='cast_spell',card_id=ray.id,sources=[],targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].controller=='p2'
    grants=[p for p in s.state.rules.permissions if p.life_mv]
    assert len(grants)==1 and grants[0].player=='p1'
    roundtrip(s)


def test_zonal_legacy_free_boolean70(cards):
    from app.rules import permissions
    from app.rules.plan import Plan
    s=setup(cards)
    bears=top(s,['Grizzly Bears'])[0]
    p=Plan(s.state,'p1',cards,None)
    permissions.grant_play(p,{'controller':'p1','name':'Legacy free authority'},
        {'play':False,'cast':True,'zone':'library_top','until':'end_of_turn','free':True})
    s.state=p.state
    before=s.state.players['p1'].life
    act(s,'p1',type='cast_spell',card_id=bears.id,sources=[],free=True)
    settle(s)
    assert s.state.cards[bears.id].zone=='p1:battlefield' and s.state.players['p1'].life==before
    assert any(g.free and not g.life_mv for g in s.state.rules.permissions)
    from app.game.state import GameState
    assert GameState.model_validate_json(s.state.model_dump_json()) == s.state


def test_mandatory_additional_discard_paid_separately70(cards):
    from app.game.errors import ActionError
    s,_=grant70(cards)
    spell=top(s,['Tormenting Voice'])[0]
    hand=list(s.state.zones['p1:hand'])
    if hand:
        act(s,'p1',type='move',card_ids=hand,to={'player':'p1','zone':'graveyard'})
    before=s.state.players['p1'].life
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=spell.id,sources=[],free=True)
    assert s.state.players['p1'].life==before
    fodder=put(s,'Forest','hand')
    act(s,'p1',type='cast_spell',card_id=spell.id,sources=[],free=True,cost_choices=[{'component':0,'cards':[fodder.id]}])
    assert s.state.cards[fodder.id].zone=='p1:graveyard'
    assert s.state.players['p1'].life==before-2
    settle(s)
    roundtrip(s)


def test_no_authority_before_attack_and_normal_timing70(cards):
    from app.game.errors import ActionError
    from tests.test_rules_wave30p_combat import attack
    s=setup(cards)
    source=put(s,'Gwenom, Remorseless','battlefield')
    bears=top(s,['Grizzly Bears'])[0]
    assert s.view('p1')['zones']['p1:library']['known']==[]
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=bears.id,sources=[],free=True)
    to_phase(s,'declare_attackers',turn=4)
    attack(s,(s.state.cards[source.id],'p2'))
    settle(s)
    bears=top(s,['Grizzly Bears'])[0]
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=bears.id,sources=[],free=True)
    assert any(p.life_mv for p in s.state.rules.permissions)
    roundtrip(s)
