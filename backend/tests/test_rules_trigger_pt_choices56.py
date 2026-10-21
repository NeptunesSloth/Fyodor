"""Native exact multi-target switching and optional base-PT trigger choices."""
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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Inversion Behemoth'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_pt_choices56_cards.json').read_text())
NAMES = [c['name'] for c in DATA]


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


def cast(s, name, pool, targets=(), *, pid='p1', resolve=True):
    wait_priority(s, pid)
    c = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='cast_spell', card_id=c.id, sources=[], targets=list(targets))
    if resolve:
        settle(s)
    return c




def pt(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, 'p1', s.cards, None).ch(c).pt


def setup(cards, name=NAME):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    put(s, name, 'hand')
    before = len(s.state.zones['p1:hand'])
    source = cast(s, name, {'C': 4} if name == NAME else {'C': 2, 'U': 2})
    if name == 'Master of Winds':
        assert len(s.state.zones['p1:hand']) == before + 1
        d = s.state.rules.decision
        assert d is not None and d.player == 'p1'
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[d.options[0].id])
        settle(s)
        assert len(s.state.zones['p1:hand']) == before
    return s, source


def inversion_pending(cards, *, count=2, damage=False):
    s, source = setup(cards)
    spider = put(s, 'Giant Spider', 'battlefield')
    if damage:
        cast(s, 'Lightning Bolt', {'R': 1}, [source.id])
        assert source.damage == 3 and source.zone == 'p1:battlefield'
    to_phase(s, 'begin_combat')
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    ids = [source.id, spider.id][:count]
    act(s, 'p1', type='choose', decision_id=d.id,
        option_ids=[next(o.id for o in d.options if o.card_id == cid) for cid in ids])
    return s, source, spider


@pytest.mark.parametrize('name', [NAME, 'Master of Winds'])
def test_whole_canonicals(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('count', [0, 2])
def test_native_inversion_zero_or_multiple_targets_and_cleanup(cards, count):
    s, source, spider = inversion_pending(cards, count=count)
    settle(s)
    assert pt(s, source) == ((9, 2) if count else (2, 9))
    assert pt(s, spider) == ((4, 2) if count else (2, 4))
    to_phase(s, 'main1', turn=5)
    assert pt(s, source) == (2, 9) and pt(s, spider) == (2, 4)
    roundtrip(s)


def test_native_inversion_pump_layering_after_switch(cards):
    s, source, spider = inversion_pending(cards)
    settle(s)
    cast(s, 'Giant Growth', {'G': 1}, [source.id])
    assert pt(s, source) == (12, 5) and pt(s, spider) == (4, 2)
    roundtrip(s)


def test_native_inversion_marked_damage_becomes_lethal(cards):
    s, source, spider = inversion_pending(cards, damage=True)
    settle(s)
    assert source.zone == 'p1:graveyard' and pt(s, spider) == (4, 2)
    roundtrip(s)


@pytest.mark.parametrize('mode', ['blink_target', 'source_departure'])
def test_native_inversion_exact_target_refs_and_source_independence(cards, mode):
    s, source, spider = inversion_pending(cards)
    old = s.state.rules.object_id(source.id)
    if mode == 'blink_target':
        cast(s, 'Flicker of Fate', {'C': 1, 'W': 1}, [source.id])
        assert s.state.rules.object_id(source.id) != old and pt(s, source) == (2, 9)
    else:
        cast(s, 'Boomerang', {'U': 2}, [source.id])
        assert source.zone == 'p1:hand'
    assert pt(s, spider) == (4, 2)
    roundtrip(s)


def winds_pending(cards, spell='Lightning Bolt', pid='p1'):
    s, source = setup(cards, 'Master of Winds')
    pool, targets = {'R': 1}, ['p2']
    if spell == 'Divination' or spell == 'Prodigal Sorcerer':
        pool, targets = {'C': 2, 'U': 1}, []
    elif spell == 'Grizzly Bears':
        pool, targets = {'C': 1, 'G': 1}, []
    elif spell == 'Sol Ring':
        pool, targets = {'C': 1}, []
    cast(s, spell, pool, targets, pid=pid, resolve=False)
    settle(s)
    return s, source


def pick_winds(s, choice):
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1' and {o.id for o in d.options} == {'yes', 'no'}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['no' if choice is None else 'yes'])
    settle(s)
    if choice is not None:
        d = s.state.rules.decision
        assert d is not None and {o.label for o in d.options} == {'4/1', '1/4'}
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[str(choice)])
        settle(s)


@pytest.mark.parametrize('choice,expected', [(None, (1, 4)), (0, (4, 1)), (1, (1, 4))])
def test_native_winds_all_three_resolution_choices_and_cleanup(cards, choice, expected):
    from app.rules.plan import Plan

    s, source = winds_pending(cards)
    pick_winds(s, choice)
    assert pt(s, source) == expected
    assert 'flying' in Plan(s.state, 'p1', cards, None).ch(source).keywords
    assert s.state.players['p2'].life == 37
    to_phase(s, 'main1', turn=5)
    assert pt(s, source) == (1, 4)
    roundtrip(s)


@pytest.mark.parametrize('spell', ['Divination', 'Prodigal Sorcerer', 'Grizzly Bears', 'Sol Ring'])
def test_native_winds_exact_spell_type_union(cards, spell):
    s, source = winds_pending(cards, spell)
    if spell in ('Divination', 'Prodigal Sorcerer'):
        pick_winds(s, 0)
        assert pt(s, source) == (4, 1)
    else:
        assert s.state.rules.decision is None and pt(s, source) == (1, 4)
    roundtrip(s)


def test_native_winds_opponents_instant_does_not_trigger(cards):
    s, source = setup(cards, 'Master of Winds')
    cast(s, 'Lightning Bolt', {'R': 1}, ['p3'], pid='p2')
    assert s.state.rules.decision is None and pt(s, source) == (1, 4)
    assert s.state.players['p3'].life == 37
    roundtrip(s)


@pytest.mark.parametrize('mode', ['inversion', 'winds'])
def test_true_cold_native_switch_and_base_pt_choice(cards, tmp_path, mode):
    import subprocess
    import sys

    if mode == 'inversion':
        s, source, spider = inversion_pending(cards)
        other = spider.id
    else:
        s, source = winds_pending(cards)
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes'])
        settle(s)
        other = source.id
    saved = tmp_path / 'pt56.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
from tests.test_rules_trigger_pt_choices56 import pt
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source=s.state.cards[sys.argv[3]]
if sys.argv[4]=='inversion':
    assert s.state.zones['stack']
    settle(s)
    assert pt(s,source)==(9,2) and pt(s,s.state.cards[sys.argv[5]])==(4,2)
else:
    d=s.state.rules.decision
    assert d is not None and {o.label for o in d.options}=={'4/1','1/4'}
    act(s,'p1',type='choose',decision_id=d.id,option_ids=['0'])
    settle(s)
    assert pt(s,source)==(4,1)
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, mode, other],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_winds_base_effects_overwrite_while_counters_and_pump_remain(cards):
    s, source = winds_pending(cards)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+1', delta=1)
    pick_winds(s, 0)
    assert pt(s, source) == (5, 2)
    cast(s, 'Giant Growth', {'G': 1}, [source.id], resolve=False)
    settle(s)
    pick_winds(s, 1)
    assert pt(s, source) == (5, 8)
    roundtrip(s)


def test_native_winds_lowered_toughness_makes_marked_damage_lethal(cards):
    s, source = setup(cards, 'Master of Winds')
    cast(s, 'Lightning Bolt', {'R': 1}, [source.id], resolve=False)
    settle(s)
    pick_winds(s, None)
    assert source.damage == 3 and source.zone == 'p1:battlefield'
    cast(s, 'Divination', {'C': 2, 'U': 1}, resolve=False)
    settle(s)
    pick_winds(s, 0)
    assert source.zone == 'p1:graveyard'
    roundtrip(s)


def test_native_inversion_all_targets_illegal_does_not_switch_blinked_successor(cards):
    s, source, spider = inversion_pending(cards, count=1)
    old = s.state.rules.object_id(source.id)
    cast(s, 'Flicker of Fate', {'C': 1, 'W': 1}, [source.id])
    assert s.state.rules.object_id(source.id) != old
    assert pt(s, source) == (2, 9) and pt(s, spider) == (2, 4)
    roundtrip(s)


def test_native_inversion_opponent_targets_and_resolution_control_change(cards):
    s, source = setup(cards)
    spider = put(s, 'Giant Spider', 'battlefield', 'p2')
    to_phase(s, 'begin_combat')
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id,
        option_ids=[next(o.id for o in d.options if o.card_id == cid) for cid in [source.id, spider.id]])
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    settle(s)
    assert source.zone == 'p2:battlefield' and pt(s, source) == (9, 2) and pt(s, spider) == (4, 2)
    roundtrip(s)
