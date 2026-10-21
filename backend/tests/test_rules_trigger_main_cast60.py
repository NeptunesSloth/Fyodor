"""Native graveyard upkeep identity and intervening creature-count proofs."""
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
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_trigger_leaf51 import choose
from tests.test_rules_trigger_library_win53 import cast
from tests.test_rules_wave30m_durations import to_phase

NAME = "Dovin's Acuity"
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_main_cast60_cards.json').read_text())


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
    names = [NAME, 'Lightning Bolt', 'Grizzly Bears', 'Murder', 'Counterspell']
    s = table(cards, names + ['Island'] * 12, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = cast(s, NAME, {'C': 1, 'W': 1, 'U': 1})
    assert source.zone == 'p1:battlefield' and s.state.players['p1'].life == 42
    return s, source


def test_whole_canonical(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('phase', ['main1', 'main2'])
@pytest.mark.parametrize('accept', [True, False])
def test_native_both_main_phases_optional_owner_hand(cards, phase, accept):
    s, source = setup(cards)
    if phase == 'main2':
        to_phase(s, phase)
    cast(s, 'Lightning Bolt', {'R': 1}, ['p2'])
    assert s.state.rules.decision is not None
    choose(s, ['yes' if accept else 'no'])
    assert source.zone == ('p1:hand' if accept else 'p1:battlefield')
    assert s.state.players['p2'].life == 37
    roundtrip(s)


@pytest.mark.parametrize('phase,turn,pid', [('upkeep', 7, 'p1'), ('declare_attackers', 4, 'p1'), ('main1', 5, 'p1'), ('main1', 4, 'p2')])
def test_native_nonmain_or_other_caster_does_not_trigger(cards, phase, turn, pid):
    s, source = setup(cards)
    if phase != 'main1' or turn != 4:
        to_phase(s, phase, turn=turn)
    cast(s, 'Lightning Bolt', {'R': 1}, ['p3'], pid=pid)
    assert s.state.rules.decision is None and source.zone == 'p1:battlefield'
    assert s.state.players['p3'].life == 37
    roundtrip(s)


def test_native_noninstant_spell_does_not_trigger(cards):
    s, source = setup(cards)
    cast(s, 'Grizzly Bears', {'C': 1, 'G': 1})
    assert source.zone == 'p1:battlefield' and s.state.rules.decision is None
    roundtrip(s)


def test_native_trigger_resolves_before_original_spell_and_survives_counter(cards):
    s, source = setup(cards)
    spell = cast(s, 'Lightning Bolt', {'R': 1}, ['p2'], resolve=False)
    cast(s, 'Counterspell', {'U': 2}, [spell.id], pid='p2')
    assert s.state.players['p2'].life == 40 and spell.zone == 'p1:graveyard'
    choose(s, ['yes'])
    assert source.zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('mode', ['graveyard', 'successor'])
def test_native_source_zones_and_original_object_boundary(cards, mode):
    s, source = setup(cards)
    if mode == 'graveyard':
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
        cast(s, 'Lightning Bolt', {'R': 1}, ['p2'])
        assert s.state.rules.decision is None and source.zone == 'p1:graveyard'
    else:
        cast(s, 'Lightning Bolt', {'R': 1}, ['p2'], resolve=False)
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
        settle(s)
        if s.state.rules.decision is not None:
            choose(s, ['yes'])
        assert source.zone == 'p1:battlefield'
    roundtrip(s)


def test_native_foreign_owned_source_returns_to_owner_after_control_changes(cards):
    s, source = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    to_phase(s, 'main1', turn=5)
    cast(s, 'Lightning Bolt', {'R': 1}, ['p3'], pid='p2')
    assert s.state.rules.decision.player == 'p2'
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p1')
    choose(s, ['yes'])
    assert source.zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('mode', ['yes', 'no'])
def test_true_cold_native_main_phase_cast_optional_return(cards, tmp_path, mode):
    import subprocess
    import sys

    import app

    s, source = setup(cards)
    cast(s, 'Lightning Bolt', {'R': 1}, ['p2'])
    saved = tmp_path / 'main60.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_trigger_leaf51 import choose
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
choose(s,[sys.argv[4]])
assert s.state.cards[sys.argv[3]].zone==('p1:hand' if sys.argv[4]=='yes' else 'p1:battlefield')
assert s.state.players['p2'].life==37
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, mode],
                            cwd=Path(app.__file__).resolve().parents[1], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
