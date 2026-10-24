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
    for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures/library_leng72_cards.json').read_text())):
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
    names = list(dict.fromkeys([c['name'] for c in json.loads((Path(__file__).parent/'fixtures/library_leng72_cards.json').read_text()) if c['name'] != 'Urza, Planeswalker'] + ['Grizzly Bears','Forest','Lightning Bolt']))
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



def test_actual_mind_rot_offers_leng_effect_discard72(cards):
    s=setup(cards)
    put(s,'Library of Leng','battlefield','p2')
    chosen=[put(s,n,'hand','p2') for n in ['Grizzly Bears','Forest']]
    other=[cid for cid in s.state.zones['p2:hand'] if cid not in [c.id for c in chosen]]
    if other:
        act(s,'p2',type='move',card_ids=other,to={'player':'p2','zone':'library'},position='bottom')
    cast(s,'Mind Rot',targets=['p2'])
    d=s.state.rules.decision
    assert d and any('Library of Leng' in o.label for o in d.options)
    assert all(s.state.cards[c.id].zone=='p2:hand' for c in chosen)


def mindrot72(cards,names=('Grizzly Bears','Forest'),extras=()):
    s=setup(cards)
    put(s,'Library of Leng','battlefield','p2')
    put(s,'Waste Not','battlefield')
    put(s,'Megrim','battlefield')
    for n in extras:
        put(s,n,'battlefield')
    chosen=[put(s,n,'hand','p2') for n in names]
    other=[cid for cid in s.state.zones['p2:hand'] if cid not in [c.id for c in chosen]]
    if other:
        act(s,'p2',type='move',card_ids=other,to={'player':'p2','zone':'library'},position='bottom')
    cast(s,'Mind Rot',targets=['p2'])
    return s,chosen


def choose_leng72(s,accept=True):
    d=s.state.rules.decision
    assert d and d.resume['step']=='grouped_discard_replace'
    option=next(o for o in d.options if ('Library of Leng' in o.label)==accept)
    answer(s,[option.id])


def triggers72(s):
    while s.state.rules.decision and s.state.rules.decision.resume.get('step')=='order_triggers':
        answer(s,[o.id for o in s.state.rules.decision.options])


def test_hidden_two_discard_single_event_private_order_generic_not_typed_triggers72(cards):
    s,chosen=mindrot72(cards)
    ids=[c.id for c in chosen]
    life=s.state.players['p2'].life
    choose_leng72(s)
    assert all(s.state.cards[cid].zone=='p2:hand' for cid in ids)
    choose_leng72(s)
    d=s.state.rules.decision
    assert d and d.kind=='order' and d.player=='p2'
    assert all(s.state.cards[cid].zone=='p2:hand' for cid in ids)
    mana=s.state.players['p1'].mana.copy()
    answer(s,list(reversed(ids)))
    triggers72(s)
    assert s.state.zones['p2:library'][:2]==list(reversed(ids))
    assert s.view('p1')['zones']['p2:library']['known']==[]
    assert s.state.players['p2'].life==life-4
    assert not any(c.is_token and c.name=='Zombie' for c in s.state.cards.values())
    assert s.state.players['p1'].mana==mana
    facts=[f for f in s.state.rules.turn_log.facts if f.kind=='discard' and f.player=='p2']
    assert len(facts)==2 and all(not f.characteristics_defined and f.types==[] and f.discarded_results==[] for f in facts)
    roundtrip(s)


def test_optional_individual_leng_choice_keeps_normal_public_characteristics72(cards):
    s,chosen=mindrot72(cards)
    first=s.state.rules.decision.resume['card']
    choose_leng72(s,False)
    choose_leng72(s,True)
    # Only one goes on top, so no private library-ordering decision.
    triggers72(s)
    assert not s.state.rules.decision
    assert s.state.cards[first].zone=='p2:graveyard'
    other=next(c.id for c in chosen if c.id!=first)
    assert s.state.zones['p2:library'][0]==other
    typed=[f for f in s.state.rules.turn_log.facts if f.kind=='discard' and f.characteristics_defined]
    assert len(typed)==1
    roundtrip(s)


def test_actual_additional_discard_cost_never_offers_leng72(cards):
    s=setup(cards)
    put(s,'Library of Leng','battlefield')
    fodder=put(s,'Grizzly Bears','hand')
    source=put(s,'Tormenting Voice','hand')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],cost_choices=[{'component':0,'cards':[fodder.id]}])
    settle(s)
    assert not s.state.rules.decision and s.state.cards[fodder.id].zone=='p1:graveyard'
    roundtrip(s)


def test_leng_competes_with_rest_in_peace_cannot_decline_mandatory_exile72(cards):
    s,chosen=mindrot72(cards,extras=('Rest in Peace',))
    d=s.state.rules.decision
    assert any('Library of Leng' in o.label for o in d.options)
    assert any('Rest in Peace' in o.label for o in d.options)
    assert not any('Discard normally' in o.label for o in d.options)
    first=d.resume['card']
    choose_leng72(s)
    choose_leng72(s,False)
    triggers72(s)
    assert s.state.zones['p2:library'][0]==first
    other=next(c.id for c in chosen if c.id!=first)
    assert s.state.cards[other].zone=='p2:exile'
    assert not s.state.rules.decision
    roundtrip(s)


def test_leng_selected_before_madness_has_no_madness_cast72(cards):
    s,chosen=mindrot72(cards,names=('Circular Logic','Forest'))
    saw=False
    for _ in range(2):
        d=s.state.rules.decision
        saw=saw or any('Madness' in o.label for o in d.options)
        choose_leng72(s)
    assert saw
    d=s.state.rules.decision
    answer(s,[o.id for o in d.options])
    triggers72(s)
    assert not s.state.rules.decision
    assert {c.id for c in chosen}==set(s.state.zones['p2:library'][:2])
    roundtrip(s)


def test_true_cold_hidden_originals_choices_order_and_generic_observers72(cards,tmp_path):
    import os
    import subprocess
    import sys

    import app
    s,chosen=mindrot72(cards)
    ids=[c.id for c in chosen]
    choose_leng72(s)
    path=tmp_path/'leng72.json'
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
ids=json.loads(sys.argv[3]);life=s.state.players['p2'].life
assert all(s.state.cards[c].zone=='p2:hand' for c in ids)
def answer(chosen):
 d=s.state.rules.decision;assert d
 act(s,d.player,type='choose',decision_id=d.id,option_ids=chosen);settle(s)
d=s.state.rules.decision
answer([next(o.id for o in d.options if 'Library of Leng' in o.label)])
d=s.state.rules.decision;assert d and d.kind=='order'
assert all(s.state.cards[c].zone=='p2:hand' for c in ids)
answer(list(reversed(ids)))
while s.state.rules.decision and s.state.rules.decision.resume.get('step')=='order_triggers':
 answer([o.id for o in s.state.rules.decision.options])
assert not s.state.rules.decision
assert s.state.zones['p2:library'][:2]==list(reversed(ids))
assert s.view('p1')['zones']['p2:library']['known']==[]
assert s.state.players['p2'].life==life-4
assert not any(c.is_token and c.name=='Zombie' for c in s.state.cards.values())
facts=[f for f in s.state.rules.turn_log.facts if f.kind=='discard' and f.player=='p2']
assert len(facts)==2 and all(not f.characteristics_defined and f.types==[] and f.batch>0 for f in facts)
'''
    backend=Path(app.__file__).resolve().parent.parent
    run=subprocess.run([sys.executable,'-c',code,str(path),str(cards.db_path),json.dumps(ids)],cwd=backend,env={**os.environ,'PYTHONPATH':str(backend)},capture_output=True,text=True,timeout=180)
    assert run.returncode==0,run.stdout+run.stderr


def sirocco72(cards,names):
    s=setup(cards)
    put(s,'Library of Leng','battlefield','p2')
    put(s,'Waste Not','battlefield')
    put(s,'Megrim','battlefield')
    chosen=[put(s,n,'hand','p2') for n in names]
    other=[cid for cid in s.state.zones['p2:hand'] if cid not in [c.id for c in chosen]]
    if other:
        act(s,'p2',type='move',card_ids=other,to={'player':'p2','zone':'library'},position='bottom')
    cast(s,'Sirocco',targets=['p2'])
    d=s.state.rules.decision
    assert d and d.resume['step']=='life_cards86'
    answer(s,[])
    return s,chosen


def test_actual_sirocco_revealed_discard_top_keeps_typed_characteristics72(cards):
    s,chosen=sirocco72(cards,('Counterspell','Circular Logic'))
    ids=[c.id for c in chosen]
    before=len(s.state.zones['p1:hand'])
    life=s.state.players['p2'].life
    for _ in range(2):
        d=s.state.rules.decision
        assert d and d.resume['step']=='life_route86'
        answer(s,[next(o.id for o in d.options if 'Library of Leng' in o.label)])
        assert all(s.state.cards[c].zone=='p2:hand' for c in ids)
    d=s.state.rules.decision
    assert d and d.kind=='order'
    answer(s,ids)
    triggers72(s)
    assert not s.state.rules.decision
    assert s.state.zones['p2:library'][:2]==ids
    assert len(s.state.zones['p1:hand'])==before+2
    assert s.state.players['p2'].life==life-4
    facts=[f for f in s.state.rules.turn_log.facts if f.kind=='discard' and f.player=='p2']
    assert len(facts)==2 and all(f.characteristics_defined and 'Instant' in f.types for f in facts)
    roundtrip(s)


def test_sirocco_public_discard_snapshot_survives_actual_nexus_shuffle72(cards):
    s,chosen=sirocco72(cards,('Nexus of Fate','Counterspell'))
    ids=[c.id for c in chosen]
    before=len(s.state.zones['p1:hand'])
    life=s.state.players['p2'].life
    for _ in range(2):
        d=s.state.rules.decision
        assert d and d.resume['step']=='life_route86'
        name=s.state.cards[d.resume['card']].name
        label='Nexus of Fate' if name=='Nexus of Fate' else 'Library of Leng'
        answer(s,[next(o.id for o in d.options if label in o.label)])
    triggers72(s)
    assert not s.state.rules.decision
    assert all(cid not in s.state.cards for cid in ids)
    assert len(s.state.zones['p1:hand'])==before+2
    assert s.state.players['p2'].life==life-4
    roundtrip(s)


@pytest.mark.parametrize('command',[True,False])
def test_actual_commander_library_replacement_before_discard_commit72(cards,command):
    s=setup(cards)
    put(s,'Library of Leng','battlefield')
    commander=put(s,'Krenko, Mob Boss','hand')
    forest=put(s,'Forest','hand')
    ids=[commander.id,forest.id]
    others=[cid for cid in s.state.zones['p1:hand'] if cid not in ids]
    # Keep the actual spell as the third hand card until it is cast.
    source=put(s,'Mind Rot','hand')
    others=[cid for cid in s.state.zones['p1:hand'] if cid not in [*ids,source.id]]
    if others:
        act(s,'p1',type='move',card_ids=others,to={'player':'p1','zone':'library'},position='bottom')
    act(s,'p1',type='cast_spell',card_id=source.id,sources=[],targets=['p1'])
    settle(s)
    choose_leng72(s)
    choose_leng72(s)
    d=s.state.rules.decision
    assert d and d.resume['step']=='leng_command72'
    assert all(s.state.cards[cid].zone=='p1:hand' for cid in ids)
    answer(s,['yes' if command else 'no'])
    if not command:
        d=s.state.rules.decision
        assert d and d.kind=='order'
        answer(s,ids)
    assert s.state.cards[commander.id].zone==('p1:command' if command else 'p1:library')
    assert s.state.cards[forest.id].zone=='p1:library'
    assert not s.state.rules.decision
    roundtrip(s)


def test_actual_random_discard_owner_sees_each_random_original_before_top_choice72(cards):
    s=setup(cards)
    put(s,'Library of Leng','battlefield','p2')
    cast(s,'Burning Inquiry')
    d=s.state.rules.decision
    assert d and d.player=='p2' and d.resume['step']=='grouped_discard_replace'
    request=d.resume['request']
    ids=[e['card'] for e in request['cards'] if e['owner']=='p2']
    assert len(ids)==3 and len(set(ids))==3
    for _ in range(3):
        d=s.state.rules.decision
        cid=d.resume['card']
        assert s.state.cards[cid].name in d.prompt
        assert all(s.state.cards[c].zone=='p2:hand' for c in ids)
        choose_leng72(s)
    d=s.state.rules.decision
    assert d and d.kind=='order' and {o.id for o in d.options}==set(ids)
    answer(s,ids)
    assert s.state.zones['p2:library'][:3]==ids
    facts=[f for f in s.state.rules.turn_log.facts if f.kind=='discard' and f.player=='p2']
    assert len(facts)==3 and all(not f.characteristics_defined for f in facts)
    roundtrip(s)


def test_whole_library_leng72(cards):
    from app.rules.coverage import of_card_data
    assert of_card_data(cards.resolve('Library of Leng')).level=='FULL'


@pytest.mark.parametrize('leng_last',[True,False])
def test_hand_limit_timestamp_and_rule_cleanup_discard_excludes_leng72(cards,leng_last):
    from tests.test_rules_keyed_player_bindings import maximum
    s=setup(cards)
    order=['Null Profusion','Library of Leng'] if leng_last else ['Library of Leng','Null Profusion']
    for name in order:
        put(s,name,'battlefield')
    assert maximum(s)==(None if leng_last else 2)
    if not leng_last:
        chosen=[put(s,n,'hand') for n in ['Grizzly Bears','Forest','Mountain']]
        ids=[c.id for c in chosen]
        other=[cid for cid in s.state.zones['p1:hand'] if cid not in ids]
        if other:
            act(s,'p1',type='move',card_ids=other,to={'player':'p1','zone':'library'},position='bottom')
        to_phase(s,'cleanup',turn=1)
        d=s.state.rules.decision
        assert d and d.resume['step']=='cleanup_discard'
        answer(s,[ids[0]])
        assert not s.state.rules.decision and s.state.cards[ids[0]].zone=='p1:graveyard'
    roundtrip(s)
