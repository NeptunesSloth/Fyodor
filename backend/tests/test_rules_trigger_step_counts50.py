"""Step-player counts remain separate from the source/ability controller."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, mana_units
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import stops, to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_step_counts50_cards.json').read_text())


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


def setup(cards):
    names = [c['name'] for c in DATA] + ['Sol Ring', 'Grizzly Bears']
    s = table(cards, names, names, names)
    start(s)
    stops(s, 'upkeep', 'main1', 'main2')
    ring = put(s, 'Sol Ring', 'battlefield', 'p2')
    thopter = put(s, 'Ornithopter', 'battlefield', 'p2')
    put(s, 'Sol Ring', 'battlefield', 'p3')
    source = put(s, 'Blinkmoth Urn', 'hand')
    mana(s, C=5)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    assert source.zone == 'p1:battlefield' and not pool(s, 'p1')
    return s, source, ring, thopter


def pool(s, pid):
    return mana_units.visible_pool(s.state, pid)


def begin(s, turn=5):
    to_phase(s, 'main1', turn=turn)
    assert s.state.zones['stack']


def test_complete_canonical_urn(cards):
    assert coverage.of_card_data(cards.resolve('Blinkmoth Urn')).level == 'FULL'


@pytest.mark.parametrize('player,turn,amount', [('p1', 7, 1), ('p2', 5, 2), ('p3', 6, 1)])
def test_active_player_gets_mana_for_own_artifacts_only(cards, player, turn, amount):
    s, _, _, _ = setup(cards)
    begin(s, turn)
    settle(s)
    assert pool(s, player) == {'C': amount}
    assert all(not pool(s, p) for p in ['p1', 'p2', 'p3'] if p != player)
    roundtrip(s)


def test_postcombat_main_phase_does_not_trigger_again(cards):
    s, _, _, _ = setup(cards)
    begin(s)
    settle(s)
    to_phase(s, 'main2', turn=5)
    settle(s)
    assert not s.state.zones['stack'] and not pool(s, 'p2')
    roundtrip(s)


def test_tapped_before_first_main_never_triggers_even_if_then_untapped(cards):
    s, source, _, _ = setup(cards)
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=True)
    to_phase(s, 'main1', turn=5)
    assert not s.state.zones['stack']
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    settle(s)
    assert not pool(s, 'p2')
    roundtrip(s)


def test_tapped_during_stack_fails_intervening_if_on_resolution(cards):
    s, source, _, _ = setup(cards)
    begin(s)
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=True)
    settle(s)
    assert not pool(s, 'p2')
    roundtrip(s)


def test_current_artifacts_are_counted_when_trigger_resolves(cards):
    s, _, ring, _ = setup(cards)
    begin(s)
    act(s, 'p2', type='move', card_ids=[ring.id], to={'player': 'p2', 'zone': 'graveyard'})
    settle(s)
    assert pool(s, 'p2') == {'C': 1}
    roundtrip(s)


@pytest.mark.parametrize('tapped', [False, True])
def test_departed_source_uses_last_known_untapped_condition(cards, tapped):
    s, source, _, _ = setup(cards)
    begin(s)
    if tapped:
        act(s, 'p1', type='tap', card_ids=[source.id], tapped=True)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert pool(s, 'p2') == ({} if tapped else {'C': 2})
    roundtrip(s)


def test_true_cold_count_uses_step_player_after_source_control_changes(cards, tmp_path):
    import os
    import subprocess
    import sys

    import app

    s, source, _, _ = setup(cards)
    begin(s)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    saved = tmp_path / 'blinkmoth50.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
from app.rules import mana_units
def pool(s,pid): return mana_units.visible_pool(s.state,pid)
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
settle(s)
assert pool(s, 'p2')=={'C':3}
assert not pool(s, 'p1') and not pool(s, 'p3')
roundtrip(s)
"""
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path)],
        cwd=Path(app.__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_zero_artifacts_adds_no_mana(cards):
    s, _, ring, thopter = setup(cards)
    act(s, 'p2', type='move', card_ids=[ring.id, thopter.id], to={'player': 'p2', 'zone': 'graveyard'})
    begin(s)
    settle(s)
    assert not pool(s, 'p2')
    roundtrip(s)


def test_generated_colorless_mana_is_actually_spendable_by_step_player(cards):
    s, _, _, _ = setup(cards)
    begin(s)
    settle(s)
    bear = put(s, 'Grizzly Bears', 'hand', 'p2')
    mana(s, pid='p2', G=1)
    act(s, 'p2', type='cast_spell', card_id=bear.id, sources=[])
    settle(s)
    assert bear.zone == 'p2:battlefield'
    assert pool(s, 'p2') == {'C': 1}
    roundtrip(s)
