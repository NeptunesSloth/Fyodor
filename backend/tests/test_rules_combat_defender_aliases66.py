"""Real Aura and Equipment permissions ignore defender alone on the current host."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import combat, coverage, scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/combat_defender_aliases66_cards.json').read_text())
NAMES = ['Animate Wall', "Warmonger's Chariot"]


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
    names = [c['name'] for c in DATA] + ['Grizzly Bears', 'Sol Ring']
    s = table(cards, names, names, names)
    start(s)
    wall = cast(s, 'Wall of Omens')
    return s, wall


def cast(s, name, targets=(), *, resolve=True):
    c = put(s, name, 'hand')
    mana(s, C=8, W=4, U=2, B=2, R=2, G=2)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=c.id, targets=list(targets), sources=[])
    if resolve:
        settle(s)
    return c


def chars(s, c):
    return Plan(s.state, 'p1', s.cards, None).ch(c)


def attach(s, name, target):
    source = cast(s, name, [target.id] if name == 'Animate Wall' else [])
    if name != 'Animate Wall':
        index = next(a.index for a in chars(s, source).abilities if 'equip' in a.keywords)
        mana(s, C=3)
        wait_priority(s, 'p1')
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, targets=[target.id], sources=[])
        settle(s)
    return source


def attack(s, c, turn=7):
    to_phase(s, 'declare_attackers', turn=turn)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'}])


@pytest.mark.parametrize('name', NAMES)
def test_complete_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', NAMES)
def test_paid_host_keeps_defender_but_actually_attacks(cards, name):
    s, wall = setup(cards)
    to_phase(s, 'main1', turn=7)
    assert 'defender' in (combat.attack_problem(s.state, wall, chars(s, wall)) or '')
    source = attach(s, name, wall)
    assert 'defender' in chars(s, wall).keywords
    assert 'attack_despite_defender' in scripts.statics(chars(s, wall))
    assert source.attached_to == wall.id
    if name != 'Animate Wall':
        assert chars(s, wall).pt == (2, 6)
    attack(s, wall)
    assert wall.attacking.id == 'p2'
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_permission_does_not_bypass_summoning_sickness(cards, name):
    s, wall = setup(cards)
    attach(s, name, wall)
    to_phase(s, 'declare_attackers', turn=4)
    before = s.state.model_dump_json()
    assert 'summoning sickness' in (combat.attack_problem(s.state, wall, chars(s, wall)) or '')
    with pytest.raises(ActionError):
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': wall.id, 'target': 'p2'}])
    assert s.state.model_dump_json() == before
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_permission_does_not_bypass_other_attack_prohibition(cards, name):
    s, wall = setup(cards)
    attach(s, name, wall)
    cast(s, 'Pacifism', [wall.id])
    to_phase(s, 'declare_attackers', turn=7)
    before = s.state.model_dump_json()
    assert "can't attack" in (combat.attack_problem(s.state, wall, chars(s, wall)) or "")
    with pytest.raises(ActionError):
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': wall.id, 'target': 'p2'}])
    assert s.state.model_dump_json() == before
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_destroyed_attachment_restores_defender_prohibition(cards, name):
    s, wall = setup(cards)
    source = attach(s, name, wall)
    cast(s, 'Disenchant', [source.id])
    assert source.zone == 'p1:graveyard'
    to_phase(s, 'declare_attackers', turn=7)
    before = s.state.model_dump_json()
    assert 'defender' in (combat.attack_problem(s.state, wall, chars(s, wall)) or '')
    with pytest.raises(ActionError):
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': wall.id, 'target': 'p2'}])
    assert s.state.model_dump_json() == before
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_blinked_successor_does_not_keep_attachment_permission(cards, name):
    s, wall = setup(cards)
    source = attach(s, name, wall)
    before = s.state.rules.object_id(wall.id)
    cast(s, 'Cloudshift', [wall.id])
    assert s.state.rules.object_id(wall.id) != before and source.attached_to is None
    assert 'attack_despite_defender' not in scripts.statics(chars(s, wall))
    assert 'defender' in (combat.attack_problem(s.state, wall, chars(s, wall)) or '')
    if name == 'Animate Wall':
        assert source.zone == 'p1:graveyard'
    roundtrip(s)


def test_enchant_wall_rejects_nonwall_atomically(cards):
    s, _ = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, 'Animate Wall', 'hand')
    mana(s, W=1)
    wait_priority(s, 'p1')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=[bear.id], sources=[])
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_chariot_native_equip_pumps_nondefender_and_can_be_moved(cards):
    s, wall = setup(cards)
    source = attach(s, NAMES[1], wall)
    bear = cast(s, 'Grizzly Bears')
    index = next(a.index for a in chars(s, source).abilities if 'equip' in a.keywords)
    mana(s, C=3)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, targets=[bear.id], sources=[])
    settle(s)
    assert chars(s, wall).pt == (0, 4) and chars(s, bear).pt == (4, 4)
    assert 'defender' in (combat.attack_problem(s.state, wall, chars(s, wall)) or '')
    attack(s, bear)
    roundtrip(s)


def test_chariot_equipped_wall_deals_native_combat_damage(cards):
    s, wall = setup(cards)
    attach(s, NAMES[1], wall)
    attack(s, wall)
    before = s.state.players['p2'].life
    to_phase(s, 'combat_damage', turn=7)
    settle(s)
    assert s.state.players['p2'].life == before - 2
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_true_cold_attachment_permission_allows_current_host_attack(cards, name, tmp_path):
    import os
    import subprocess
    import sys

    import app

    s, wall = setup(cards)
    attach(s, name, wall)
    to_phase(s, 'main1', turn=7)
    saved = tmp_path / 'defender66.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_combat_defender_aliases66 import attack, chars
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
wall=s.state.cards[sys.argv[3]]
assert 'defender' in chars(s,wall).keywords
attack(s,wall)
assert wall.attacking.id=='p2'
roundtrip(s)
"""
    backend = Path(app.__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), wall.id],
        cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
