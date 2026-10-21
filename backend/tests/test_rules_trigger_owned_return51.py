"""Owned hand returns include simultaneous departed watchers and tokens."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import app
from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

NAMES = ['Stormfront Riders']
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_owned_return51_cards.json').read_text())


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


def cast(s, name, pool, targets=(), pid='p1', resolve=True):
    wait_priority(s, pid)
    spell = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='cast_spell', card_id=spell.id, sources=[], targets=list(targets))
    if resolve:
        settle(s)
    return spell



def setup(cards):
    names = [c['name'] for c in DATA] + ['Grizzly Bears','Llanowar Elves','Forest','Island']
    s = table(cards, names, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    return s


def soldiers(s):
    return [c for c in s.state.cards.values() if c.name == 'Soldier' and c.token is not None and c.zone == 'p1:battlefield']


def enter(s, companions=()):
    source = cast(s, NAMES[0], {'C': 4,'W': 1})
    d = s.state.rules.decision
    if d is not None:
        picks = [c.id for c in companions] if companions else [source.id]
        assert set(picks) <= {o.id for o in d.options}
        act(s, d.player, type='choose', decision_id=d.id, option_ids=picks)
        settle(s)
    return source


def test_full_canonical(cards):
    assert coverage.of_card_data(cards.resolve(NAMES[0])).level == 'FULL'


def test_native_paid_lone_entry_returns_self_and_triggers_soldier(cards):
    s = setup(cards)
    source = enter(s)
    assert source.zone == 'p1:hand' and len(soldiers(s)) == 1
    roundtrip(s)


def test_native_simultaneous_source_and_other_creature_return_each_trigger(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    source = cast(s, NAMES[0], {'C': 4,'W': 1})
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[source.id,bear.id])
        settle(s)
    assert source.zone == bear.zone == 'p1:hand' and len(soldiers(s)) == 2
    roundtrip(s)


def established(s):
    pair = [put(s, n, 'battlefield') for n in ('Grizzly Bears','Llanowar Elves')]
    source = enter(s, pair)
    assert source.zone == 'p1:battlefield' and len(soldiers(s)) == 2
    return source


@pytest.mark.parametrize('owner,controller,delta', [('p1','p2',1),('p2','p1',0)])
def test_returned_hand_owner_not_previous_controller_decides_trigger(cards, owner, controller, delta):
    s = setup(cards)
    established(s)
    creature = put(s, 'Grizzly Bears', 'battlefield', owner)
    act(s, 'p1', type='set_controller', card_ids=[creature.id], player=controller)
    before = len(soldiers(s))
    cast(s, 'Boomerang', {'U': 2}, [creature.id])
    assert creature.zone == f'{owner}:hand' and len(soldiers(s)) == before+delta
    roundtrip(s)


def test_native_returned_token_triggers_before_ceasing_to_exist(cards):
    s = setup(cards)
    established(s)
    token = soldiers(s)[0]
    before = len(soldiers(s))
    cast(s, 'Boomerang', {'U': 2}, [token.id])
    assert len(soldiers(s)) == before and token.id not in s.state.cards
    roundtrip(s)


def test_native_token_replacement_applies_each_simultaneous_return(cards):
    s = setup(cards)
    put(s, 'Doubling Season', 'battlefield')
    pair = [put(s, n, 'battlefield') for n in ('Grizzly Bears','Llanowar Elves')]
    source = enter(s, pair)
    assert source.zone == 'p1:battlefield' and len(soldiers(s)) == 4
    roundtrip(s)


@pytest.mark.parametrize('paired', [False, True])
def test_true_cold_native_entry_return_and_leave_lookback(cards, tmp_path, paired):
    from tests.test_rules_counter_event_comparisons50 import resolve_only

    s = setup(cards)
    if paired:
        put(s, 'Grizzly Bears', 'battlefield')
    source = cast(s, NAMES[0], {'C': 4,'W': 1}, resolve=False)
    resolve_only(s, source)
    assert source.zone == 'p1:battlefield' and s.state.zones['stack']
    saved = tmp_path / 'stormfront.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
from tests.game_helpers import act
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source=s.state.cards[sys.argv[3]]
assert s.state.zones['stack']
settle(s)
if s.state.rules.decision is not None:
 d=s.state.rules.decision
 assert d.min_choices==d.max_choices==len(d.options)
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[o.id for o in d.options])
 settle(s)
assert source.zone=='p1:hand'
soldiers=[c for c in s.state.cards.values() if c.name=='Soldier' and c.token is not None and c.zone=='p1:battlefield']
assert len(soldiers)==int(sys.argv[4])
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, str(2 if paired else 1)],
                            capture_output=True, text=True, timeout=90, cwd=Path(app.__file__).resolve().parents[1])
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('self_return', [False,True])
def test_foreign_controlled_watcher_only_counts_its_controllers_hand(cards, self_return):
    s = setup(cards)
    source = established(s)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    creature = source if self_return else put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Boomerang', {'U': 2}, [creature.id])
    tokens = [c for c in s.state.cards.values() if c.name == 'Soldier' and c.token is not None and c.zone == 'p2:battlefield']
    assert len(tokens) == (0 if self_return else 1)
    assert creature.zone == ('p1:hand' if self_return else 'p2:hand')
    roundtrip(s)


@pytest.mark.parametrize('foreign', [False,True])
def test_noncreature_source_return_uses_self_identity_and_original_hand_owner(cards, foreign):
    from app.rules.plan import Plan

    s = setup(cards)
    source = established(s)
    cast(s, 'One with the Stars', {'C': 3,'U': 1}, [source.id])
    assert 'Creature' not in Plan(s.state, 'p1', s.cards, None).ch(source).types
    if foreign:
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    before = len(soldiers(s))
    cast(s, 'Boomerang', {'U': 2}, [source.id])
    assert source.zone == 'p1:hand' and len(soldiers(s)) == before + (0 if foreign else 1)
    p2tokens = [c for c in s.state.cards.values() if c.name == 'Soldier' and c.token is not None and c.zone == 'p2:battlefield']
    assert not p2tokens
    roundtrip(s)
