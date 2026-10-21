"""Attached-artifact controller damage uses current information or exact LKI."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Gremlin Infestation'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_attached_artifact67_cards.json').read_text())


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


def setup(cards, owner='p2'):
    names = [c['name'] for c in DATA]
    s = table(cards, names, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    artifact = put(s, 'Sol Ring', 'battlefield', owner)
    aura = put(s, NAME, 'hand')
    mana(s, C=3, R=1)
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[artifact.id], sources=[])
    settle(s)
    assert aura.zone == 'p1:battlefield' and aura.attached_to == artifact.id
    return s, aura, artifact


def test_complete_actual_canonical(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('owner', ['p1', 'p2', 'p3'])
def test_native_paid_aura_damages_artifact_controller_on_auras_end_step(cards, owner):
    s, aura, artifact = setup(cards, owner)
    before = s.state.players[owner].life
    to_phase(s, 'end', turn=4)
    settle(s)
    assert s.state.players[owner].life == before - 2
    assert aura.attached_to == artifact.id
    roundtrip(s)


def test_opponents_end_step_does_not_trigger(cards):
    s, _, _ = setup(cards)
    to_phase(s, 'end', turn=4)
    settle(s)
    before = {p: s.state.players[p].life for p in s.state.players}
    to_phase(s, 'end', turn=5)
    settle(s)
    assert {p: s.state.players[p].life for p in s.state.players} == before
    roundtrip(s)


def test_control_change_before_resolution_uses_current_artifact_controller(cards):
    s, _, artifact = setup(cards)
    to_phase(s, 'end', turn=4)
    act(s, 'p1', type='set_controller', card_ids=[artifact.id], player='p3')
    before = {p: s.state.players[p].life for p in s.state.players}
    settle(s)
    assert s.state.players['p3'].life == before['p3'] - 2
    assert s.state.players['p2'].life == before['p2']
    roundtrip(s)


def test_departed_aura_still_uses_original_host_current_controller(cards):
    s, aura, artifact = setup(cards)
    to_phase(s, 'end', turn=4)
    act(s, 'p1', type='move', card_ids=[aura.id], to={'player':'p1','zone':'graveyard'})
    act(s, 'p1', type='set_controller', card_ids=[artifact.id], player='p3')
    before = s.state.players['p3'].life
    settle(s)
    assert s.state.players['p3'].life == before - 2
    roundtrip(s)


def test_host_departure_uses_last_controller_and_creates_token_for_aura_controller(cards):
    s, aura, artifact = setup(cards)
    to_phase(s, 'end', turn=4)
    act(s, 'p1', type='set_controller', card_ids=[artifact.id], player='p3')
    act(s, 'p1', type='move', card_ids=[artifact.id], to={'player':'p2','zone':'graveyard'})
    before = s.state.players['p3'].life
    settle(s)
    assert s.state.players['p3'].life == before - 2
    assert aura.zone == 'p1:graveyard'
    tokens = [c for c in s.state.cards.values() if c.name == 'Gremlin' and c.zone.endswith(':battlefield')]
    assert len(tokens) == 1 and tokens[0].controller == 'p1'
    roundtrip(s)


def test_blinked_host_successor_does_not_replace_original_controller(cards):
    s, _, artifact = setup(cards)
    to_phase(s, 'end', turn=4)
    act(s, 'p1', type='move', card_ids=[artifact.id], to={'player':'p2','zone':'exile'})
    act(s, 'p1', type='move', card_ids=[artifact.id], to={'player':'p2','zone':'battlefield'})
    act(s, 'p1', type='set_controller', card_ids=[artifact.id], player='p3')
    before = {p:s.state.players[p].life for p in s.state.players}
    settle(s)
    assert s.state.players['p2'].life == before['p2'] - 2
    assert s.state.players['p3'].life == before['p3']
    assert not any(c.name == 'Gremlin' for c in s.state.cards.values())
    roundtrip(s)


def test_true_cold_pending_trigger_retains_departed_host_lki(cards, tmp_path):
    s, _, artifact = setup(cards)
    to_phase(s, 'end', turn=4)
    act(s, 'p1', type='set_controller', card_ids=[artifact.id], player='p3')
    act(s, 'p1', type='move', card_ids=[artifact.id], to={'player':'p2','zone':'graveyard'})
    saved = tmp_path / 'gremlin.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
before=s.state.players['p3'].life
settle(s)
assert s.state.players['p3'].life==before-2
assert sum(c.name=='Gremlin' and c.zone=='p1:battlefield' for c in s.state.cards.values())==1
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path)], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
