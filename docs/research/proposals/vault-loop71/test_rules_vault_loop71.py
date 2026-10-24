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
    for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures/vault_loop71_cards.json').read_text())):
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
    names = list(dict.fromkeys([c['name'] for c in json.loads((Path(__file__).parent/'fixtures/vault_loop71_cards.json').read_text()) if c['name'] != 'Urza, Planeswalker'] + ['Grizzly Bears','Forest','Lightning Bolt']))
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



NAME="Lim-Dûl's Vault"

def test_whole71(cards):
    from app.rules.coverage import of_card_data
    result=of_card_data(cards.resolve(NAME))
    assert result.level=='FULL',result


def test_native_decline_first_keeps_exact_private_five71(cards):
    s=setup(cards)
    packet=top(s,['Grizzly Bears','Mountain','Fireball','Lightning Bolt','Sol Ring'])
    ids=[c.id for c in packet]
    before=set(s.state.zones['p1:library'])
    life=s.state.players['p1'].life
    cast(s,NAME)
    d=s.state.rules.decision
    assert d and d.resume['step']=='pay_or_sacrifice'
    assert s.view('p2')['zones']['p1:library']['known']==[]
    answer(s,['decline'])
    d=s.state.rules.decision
    assert d and d.kind=='order' and {o.id for o in d.options}==set(ids)
    answer(s,list(reversed(ids)))
    assert s.state.zones['p1:library'][:5]==list(reversed(ids))
    assert s.state.players['p1'].life==life
    assert not (before-set(ids)) & set(s.state.cards)
    roundtrip(s)


def test_native_paid_round_bottom_order_then_new_exact_five71(cards):
    s=setup(cards)
    packet=top(s,['Grizzly Bears','Mountain','Fireball','Lightning Bolt','Sol Ring'])
    ids=[c.id for c in packet]
    nextids=list(s.state.zones['p1:library'][5:10])
    life=s.state.players['p1'].life
    cast(s,NAME)
    answer(s,['pay'])
    d=s.state.rules.decision
    assert d and d.kind=='order' and {o.id for o in d.options}==set(ids)
    answer(s,ids)
    assert s.state.zones['p1:library'][-5:]==list(reversed(ids))
    d=s.state.rules.decision
    assert d and d.resume['step']=='pay_or_sacrifice'
    answer(s,['decline'])
    d=s.state.rules.decision
    assert d and {o.id for o in d.options}==set(nextids)
    answer(s,nextids)
    assert s.state.zones['p1:library'][:5]==nextids
    assert s.state.players['p1'].life==life-1
    roundtrip(s)


@pytest.mark.parametrize('checkpoint',['pay','bottom','final'])
def test_true_cold_repeat_and_final_packet71(cards,tmp_path,checkpoint):
    import os
    import subprocess
    import sys

    import app
    s=setup(cards)
    packet=top(s,['Grizzly Bears','Mountain','Fireball','Lightning Bolt','Sol Ring'])
    ids=[c.id for c in packet]
    nextids=list(s.state.zones['p1:library'][5:10])
    life=s.state.players['p1'].life
    cast(s,NAME)
    if checkpoint in ('bottom','final'):
        answer(s,['pay'])
    if checkpoint=='final':
        answer(s,ids)
        answer(s,['decline'])
    path=tmp_path/'vault71.json'
    path.write_text(s.state.model_dump_json())
    code=r'''
import json,sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from tests.game_helpers import act
from tests.test_rules_library_placements import settle
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
checkpoint=sys.argv[3];ids=json.loads(sys.argv[4]);nextids=json.loads(sys.argv[5]);life=int(sys.argv[6])
def answer(chosen):
 d=s.state.rules.decision;assert d
 act(s,d.player,type='choose',decision_id=d.id,option_ids=chosen);settle(s)
assert s.view('p2')['zones']['p1:library']['known']==[]
if checkpoint=='pay':answer(['pay'])
if checkpoint!='final':
 answer(ids)
 assert s.state.zones['p1:library'][-5:]==list(reversed(ids))
 answer(['decline'])
d=s.state.rules.decision;assert d and d.kind=='order' and {o.id for o in d.options}==set(nextids)
answer(list(reversed(nextids)))
assert s.state.zones['p1:library'][:5]==list(reversed(nextids))
assert s.state.players['p1'].life==life-1
assert not s.state.rules.decision and not s.state.rules.stack
'''
    backend=Path(app.__file__).resolve().parent.parent
    run=subprocess.run([sys.executable,'-c',code,str(path),str(cards.db_path),checkpoint,json.dumps(ids),json.dumps(nextids),str(life)],cwd=backend,env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert run.returncode==0,run.stdout+run.stderr


@pytest.mark.parametrize('size',[0,2,5])
def test_short_or_empty_library_repeat_is_as_much_as_possible71(cards,size):
    s=setup(cards)
    put(s,NAME,'hand')
    packet=top(s,['Grizzly Bears','Mountain','Fireball','Lightning Bolt','Sol Ring'][:size])
    ids=[c.id for c in packet]
    rest=[cid for cid in s.state.zones['p1:library'] if cid not in ids]
    act(s,'p1',type='move',card_ids=rest,to={'player':'p1','zone':'graveyard'})
    life=s.state.players['p1'].life
    cast(s,NAME)
    for _ in range(2):
        answer(s,['pay'])
        if size>1:
            d=s.state.rules.decision
            assert d and d.kind=='order' and {o.id for o in d.options}==set(ids)
            answer(s,ids)
    answer(s,['decline'])
    if size>1:
        answer(s,ids)
    assert s.state.zones['p1:library']==ids
    assert s.state.players['p1'].life==life-2
    assert not s.state.rules.decision
    roundtrip(s)


@pytest.mark.parametrize('lock',['Platinum Emperion'])
def test_life_lock_cannot_repeat_and_still_finishes71(cards,lock):
    s=setup(cards)
    packet=top(s,['Grizzly Bears','Mountain','Fireball','Lightning Bolt','Sol Ring'])
    ids=[c.id for c in packet]
    put(s,lock,'battlefield')
    life=s.state.players['p1'].life
    cast(s,NAME)
    d=s.state.rules.decision
    assert d and d.kind=='order'
    answer(s,ids)
    assert s.state.zones['p1:library'][:5]==ids
    assert s.state.players['p1'].life==life
    roundtrip(s)


def test_angel_allows_resolution_life_cost71(cards):
    s=setup(cards)
    top(s,['Grizzly Bears','Mountain','Fireball','Lightning Bolt','Sol Ring'])
    put(s,'Angel of Jubilation','battlefield')
    life=s.state.players['p1'].life
    cast(s,NAME)
    answer(s,['pay'])
    d=s.state.rules.decision
    assert d and d.kind=='order'
    answer(s,[o.id for o in d.options])
    answer(s,['decline'])
    d=s.state.rules.decision
    assert d and d.kind=='order'
    answer(s,[o.id for o in d.options])
    assert s.state.players['p1'].life==life-1
    roundtrip(s)
