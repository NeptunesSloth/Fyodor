"""Conditional declaration requirements preserve origin, legality and native optimization."""
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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/combat_named_exception69_cards.json').read_text())
NAMES = ['Akron Legionnaire', 'Sakashima the Impostor', 'Shield Sphere', 'Ornithopter']


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
    names = [NAMES[0], *NAMES, 'Grizzly Bears', 'Sol Ring']
    s = table(cards, names, names, names)
    bears = {p: put(s, 'Grizzly Bears', 'battlefield', p) for p in ['p1', 'p2', 'p3']}
    flyer = put(s, 'Ornithopter', 'battlefield')
    wall = put(s, 'Shield Sphere', 'battlefield')
    start(s)
    return s, bears, flyer, wall


def choose(s, value):
    d = s.state.rules.decision
    assert d is not None and value in [o.id for o in d.options]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[value])
    settle(s)


def cast(s, name, targets=(), *, pid='p1', direction=None):
    source = put(s, name, 'hand', pid)
    mana(s, pid=pid, C=8, W=4, U=4, R=4, G=4, B=4)
    wait_priority(s, pid)
    act(s, pid, type='cast_spell', card_id=source.id, targets=list(targets), sources=[])
    settle(s)
    if direction is not None:
        choose(s, direction)
        assert source.choices.get('Chosen direction') == direction
    return source


def declare(s, bear, target, *, pid='p1', turn=4):
    to_phase(s, 'declare_attackers', turn=turn)
    act(s, pid, type='declare_attackers', attackers=[{'card_id': bear.id, 'target': target}])


def refuse(s, bear, target, *, pid='p1', turn=4):
    to_phase(s, 'declare_attackers', turn=turn)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, pid, type='declare_attackers', attackers=[{'card_id': bear.id, 'target': target}])
    assert s.state.model_dump_json() == before




def test_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve(NAMES[0])).level == 'FULL'


def test_only_own_nonartifact_nonakron_creatures_are_forbidden(cards):
    s, bears, flyer, _ = setup(cards)
    cast(s, NAMES[0])
    refuse(s, bears['p1'], 'p2', turn=7)
    declare(s, flyer, 'p2', turn=7)
    declare(s, bears['p2'], 'p1', pid='p2', turn=8)
    roundtrip(s)


def test_two_actual_paid_legionnaires_both_attack(cards):
    s, _, _, _ = setup(cards)
    first = cast(s, NAMES[0])
    second = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == NAMES[0] and c.id != first.id)
    act(s, 'p1', type='move', card_ids=[second.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, C=8, W=4)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=second.id, targets=[], sources=[])
    settle(s)
    to_phase(s, 'declare_attackers', turn=7)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in [first, second]])
    assert all(c.attacking.id == 'p2' for c in [first, second])
    roundtrip(s)


def test_exception_grants_no_haste_and_does_not_ignore_defender(cards):
    s, _, _, wall = setup(cards)
    source = cast(s, NAMES[0])
    refuse(s, source, 'p2')
    refuse(s, wall, 'p2', turn=7)
    declare(s, source, 'p2', turn=7)
    roundtrip(s)


def test_sakashima_retains_literal_akron_name_exception(cards):
    s, _, _, _ = setup(cards)
    source = cast(s, NAMES[0])
    renamed = cast(s, NAMES[1])
    choose(s, source.id)
    ch = Plan(s.state, 'p1', s.cards, None).ch(renamed)
    assert ch.name == NAMES[1] and ch.pt == (8, 4)
    assert any('creatures named Akron Legionnaire' in a.text for a in ch.abilities)
    refuse(s, renamed, 'p2', turn=7)
    declare(s, source, 'p2', turn=7)
    roundtrip(s)


def test_prohibition_follows_current_source_controller(cards):
    s, bears, _, _ = setup(cards)
    source = cast(s, NAMES[0])
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    declare(s, bears['p1'], 'p2')
    refuse(s, bears['p2'], 'p1', pid='p2', turn=5)
    declare(s, source, 'p1', pid='p2', turn=5)
    roundtrip(s)


def test_current_controller_scope_genuine_cold_reload(cards, tmp_path):
    import os
    import subprocess
    import sys

    import app

    s, bears, _, _ = setup(cards)
    source = cast(s, NAMES[0])
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    to_phase(s, 'main1', turn=5)
    saved = tmp_path / 'akron69.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_combat_named_exception69 import refuse, declare
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
bear=s.state.cards[sys.argv[3]]
source=s.state.cards[sys.argv[4]]
refuse(s,bear,'p1',pid='p2',turn=5)
declare(s,source,'p1',pid='p2',turn=5)
assert source.attacking.id=='p1'
roundtrip(s)
"""
    backend = Path(app.__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), bears['p2'].id, source.id],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
                            capture_output=True, text=True, timeout=180, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
