"""Tide thresholds use native state triggers without an intervening condition."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

HOMARID = 'Homarid'
TIDAL = 'Tidal Influence'
NAMES = [HOMARID, TIDAL, 'Air Elemental']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    rows = json.loads((Path(__file__).parent / 'fixtures/counter_state_thresholds50_cards.json').read_text())
    for i, c in enumerate(rows):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    source = put(s, name, 'hand')
    mana(s, C=2, U=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    assert source.counters == {'tide': 1} and not s.state.players['p1'].mana
    return s, source


@pytest.mark.parametrize('name', [HOMARID, TIDAL])
def test_complete_canonical_supported(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_native_homarid_upkeep_cycle_and_exact_threshold_stats(cards):
    s, source = setup(cards, HOMARID)
    assert Plan(s.state, 'p1', cards, None).ch(source).pt == (1, 1)
    for turn, count, pt in [(7, 2, (2, 2)), (10, 3, (3, 3)), (13, 0, (2, 2)), (16, 1, (1, 1))]:
        to_phase(s, 'upkeep', turn=turn)
        settle(s)
        assert source.counters.get('tide', 0) == count
        assert Plan(s.state, 'p1', cards, None).ch(source).pt == pt
    roundtrip(s)


def test_native_tidal_upkeep_changes_all_blue_creatures_immediately(cards):
    s, source = setup(cards, TIDAL)
    own = put(s, 'Air Elemental', 'battlefield')
    other = put(s, 'Air Elemental', 'battlefield', 'p2')
    assert all(Plan(s.state, 'p1', cards, None).ch(c).pt == (2, 4) for c in [own, other])
    for turn, count, power in [(7, 2, 4), (10, 3, 6), (13, 0, 4)]:
        to_phase(s, 'upkeep', turn=turn)
        settle(s)
        assert source.counters.get('tide', 0) == count
        assert all(Plan(s.state, 'p1', cards, None).ch(c).pt == (power, 4) for c in [own, other])
    roundtrip(s)


def test_tidal_named_permanent_cast_restriction_is_global(cards):
    s, source = setup(cards, TIDAL)
    to_phase(s, 'main1', turn=5)
    second = put(s, TIDAL, 'hand', 'p2')
    mana(s, pid='p2', C=2, U=1)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p2', type='cast_spell', card_id=second.id, sources=[])
    assert s.state.model_dump_json() == before and source.zone == 'p1:battlefield'
    roundtrip(s)


def pending_threshold(cards, name):
    s, source = setup(cards, name)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='tide', delta=2)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='charge', delta=2)
    to_phase(s, 'upkeep', turn=7)
    # Resolve the upkeep counter placement only; preserve the resulting state trigger.
    for _ in range(20):
        if source.counters.get('tide', 0) == 4:
            break
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    assert source.counters.get('tide') == 4 and s.state.zones['stack']
    return s, source


@pytest.mark.parametrize('name', [HOMARID, TIDAL])
def test_threshold_removes_tide_only_even_when_count_falls_before_resolution(cards, name):
    s, source = pending_threshold(cards, name)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='tide', delta=-2)
    settle(s)
    assert source.counters == {'charge': 2}
    roundtrip(s)


@pytest.mark.parametrize('name', [HOMARID, TIDAL])
def test_threshold_original_source_does_not_remove_successors_entry_counter(cards, name):
    s, source = pending_threshold(cards, name)
    old = s.state.rules.object_id(source.id)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    assert s.state.rules.object_id(source.id) != old
    # Manual movement does not apply native entry replacement, so provide the successor's physical counter.
    act(s, 'p1', type='counter', card_ids=[source.id], kind='tide', delta=1)
    settle(s)
    assert source.counters == {'tide': 1}
    roundtrip(s)


@pytest.mark.parametrize('name', [HOMARID, TIDAL])
def test_true_cold_threshold_retains_non_intervening_condition_and_counter_kind(cards, tmp_path, name):
    import subprocess
    import sys

    s, source = pending_threshold(cards, name)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='tide', delta=-2)
    saved = tmp_path / 'tide50.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert s.state.zones['stack']
settle(s)
assert s.state.cards[sys.argv[3]].counters=={'charge':2}
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
