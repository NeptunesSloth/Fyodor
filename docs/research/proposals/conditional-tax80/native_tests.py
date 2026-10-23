"""Native alternative and upkeep taxes retain actual payers and affected objects."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['We Say Thee Nay!', 'Dispelling Exhale', 'Swallowed by Leviathan']
DATA = json.loads((Path(__file__).parent / 'fixtures/conditional_tax80_cards.json').read_text())
ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Lightning Bolt', 'Counterspell', 'Forest', 'Island', 'Mountain']


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


def game(cards):
    s = table(cards, ALL, ALL, ALL)
    to_phase(s, 'main1', 1)
    return s


def choose(s, ids, resolve=True):
    d = s.state.rules.decision
    assert d
    result = act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    if resolve:
        settle(s)
    return result


def cast(s, name, targets=(), pid='p1', resolve=True, **extra):
    c = put(s, name, 'hand', pid)
    wait_priority(s, pid)
    act(s, pid, type='add_mana', player=pid, mana={'C': 30, 'W': 4, 'U': 5, 'R': 2, 'B': 3, 'G': 3})
    act(s, pid, type='cast_spell', card_id=c.id, targets=list(targets), sources=[], **extra)
    if resolve:
        settle(s)
    return c


@pytest.mark.parametrize('name', NAMES)
def test_canonical_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def tax_game(cards, name, optional=False, where='hand', depart=False):
    s = game(cards)
    act(s, 'p2', type='set_prefs', hold_priority=True)
    target = cast(s, 'Lightning Bolt', ['p3'], pid='p2', resolve=False)
    act(s, 'p2', type='clear_mana', player='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 6})
    source = put(s, name, 'hand')
    extra = {}
    helper = None
    if optional:
        key = 'teamwork' if name == NAMES[0] else 'behold'
        helper = put(s, 'Grizzly Bears' if key == 'teamwork' else 'Shivan Dragon', 'battlefield' if key == 'teamwork' else where)
        extra = {'optional_costs': [source.id + ':' + key], 'cost_choices': [{'component': 0, 'cards': [helper.id]}]}
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 4, 'C': 8})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[target.id], sources=[], **extra)
    if depart:
        act(s, 'p1', type='move', card_ids=[helper.id], to={'zone':'graveyard'})
    settle(s)
    return s, source, target, helper


@pytest.mark.parametrize('name,optional,pick', [(n,o,p) for n in NAMES[:2] for o in [False,True] for p in ['pay','decline']])
def test_actual_cast_receipt_controls_single_payment(cards, name, optional, pick):
    from app.rules.mana_units import visible_pool
    s, source, target, helper = tax_game(cards, name, optional)
    d = s.state.rules.decision
    assert d and d.kind != 'manual_resolution' and d.player == 'p2'
    if optional and name == NAMES[0]:
        assert s.state.cards[helper.id].tapped
    choose(s, [pick])
    assert visible_pool(s.state, 'p2') == {'C': 6-(4 if optional else 2) if pick == 'pay' else 6}
    assert s.state.players['p3'].life == (37 if pick == 'pay' else 40)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)

@pytest.mark.parametrize('where', ['hand', 'battlefield'])
def test_beheld_original_dragon_receipt_survives_departure(cards, where):
    s, source, target, helper = tax_game(cards, NAMES[1], True, where, depart=True)
    choose(s, ['pay'])
    from app.rules.mana_units import visible_pool
    assert visible_pool(s.state,'p2') == {'C':2}
    assert s.state.players['p3'].life == 37
    roundtrip(s)


@pytest.mark.parametrize('sent,pick', [(0,'pay'),(2,'pay'),(2,'decline')])
def test_surveil_completes_before_tax_uses_actual_graveyard(cards, sent, pick):
    s, source, target, _ = tax_game(cards, NAMES[2])
    d=s.state.rules.decision
    assert d and d.player=='p1' and 'surveil' in d.prompt.lower()
    chosen=[o.id for o in d.options[:sent]]
    choose(s,chosen)
    for _ in range(3):
        d=s.state.rules.decision
        if not d or d.player=='p2':
            break
        choose(s,[o.id for o in d.options])
    d=s.state.rules.decision
    assert d and d.player=='p2' and d.kind!='manual_resolution'
    choose(s,[pick])
    from app.rules.mana_units import visible_pool
    assert visible_pool(s.state,'p2')=={'C':6-(sent if pick=='pay' else 0)}
    assert s.state.players['p3'].life==(37 if pick=='pay' else 40)
    assert len(s.state.zones['p1:graveyard'])==sent+1
    roundtrip(s)

@pytest.mark.parametrize('name',NAMES)
def test_fresh_process_pending_real_tax_or_private_surveil(cards,tmp_path,name):
    import subprocess
    import sys
    s,source,target,_=tax_game(cards,name,optional=name!=NAMES[2])
    saved=tmp_path/'tax.json'
    saved.write_text(s.state.model_dump_json())
    code=r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.mana_units import visible_pool
from tests.game_helpers import act
from tests.test_rules_library_look import settle
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
name=sys.argv[3]
def choose(ids):
 d=s.state.rules.decision
 assert d and d.kind!='manual_resolution'
 act(s,d.player,type='choose',decision_id=d.id,option_ids=ids)
 settle(s)
if name=='Swallowed by Leviathan':
 d=s.state.rules.decision
 assert d.player=='p1' and 'surveil' in d.prompt.lower()
 choose([o.id for o in d.options])
 expected=4
else: expected=2
d=s.state.rules.decision
assert d and d.player=='p2'
choose(['pay'])
assert visible_pool(s.state,'p2')=={'C':expected}
assert s.state.players['p3'].life==37
assert GameState.model_validate_json(s.state.model_dump_json()).model_dump(mode='json')==s.state.model_dump(mode='json')
r.close()
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved),str(cards.db_path),name],cwd='/workspace/Fyodor/backend',capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr

@pytest.mark.parametrize('name',NAMES[:2])
def test_optional_receipt_requires_actual_legal_cast_cost(cards,name):
    from app.game.errors import ActionError
    s=game(cards)
    act(s,'p2',type='set_prefs',hold_priority=True)
    target=cast(s,'Lightning Bolt',['p3'],pid='p2',resolve=False)
    source=put(s,name,'hand')
    wait_priority(s,'p1')
    act(s,'p1',type='add_mana',player='p1',mana={'U':4,'C':8})
    key='teamwork' if name==NAMES[0] else 'behold'
    wrong=put(s,'Forest','battlefield')
    before=s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s,'p1',type='cast_spell',card_id=source.id,targets=[target.id],sources=[],optional_costs=[source.id+':'+key],cost_choices=[{'component':0,'cards':[wrong.id]}])
    assert s.state.model_dump(mode='json')==before
