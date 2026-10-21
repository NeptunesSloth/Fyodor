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

DATA = json.loads((Path(__file__).parent / 'fixtures/combat_soulbond_partner70_cards.json').read_text())
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


NAME = 'Flowering Lumberknot'

def setup(cards):
    s = table(cards, [c['name'] for c in DATA] + ['Grizzly Bears'], ['Grizzly Bears'], ['Grizzly Bears'])
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    start(s)
    return s, enemy


def choice(s, value):
    d = s.state.rules.decision
    assert d is not None and value in [o.id for o in d.options]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[value])
    settle(s)


def cast(s, name, targets=()):
    c = put(s, name, 'hand')
    mana(s, C=8, W=5, U=5, G=5, R=5)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=c.id, targets=list(targets), sources=[])
    settle(s)
    return c


def paired(cards):
    s, enemy = setup(cards)
    host = cast(s, NAME)
    wing = cast(s, 'Wingcrafter')
    if s.state.rules.decision and any(o.id == 'yes' for o in s.state.rules.decision.options):
        choice(s, 'yes')
    if s.state.rules.decision:
        choice(s, host.id)
    assert len(s.state.rules.pairs) == 2
    return s, host, wing, enemy


def attack(s, host):
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id':host.id,'target':'p2'}])


def refused(s, host):
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        attack(s, host)
    assert before == s.state.model_dump_json()


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_unpaired_cannot_attack(cards):
    s, _ = setup(cards)
    host = cast(s, NAME)
    to_phase(s, 'declare_attackers', turn=7)
    refused(s, host)
    roundtrip(s)


def test_native_paid_pair_can_attack(cards):
    s, host, _, _ = paired(cards)
    to_phase(s, 'declare_attackers', turn=7)
    attack(s, host)
    assert host.is_attacking
    roundtrip(s)


def test_losing_soulbond_keeps_pair_but_prevents_attack(cards):
    s, host, wing, _ = paired(cards)
    to_phase(s, 'main1', turn=7)
    cast(s, 'Humble', [wing.id])
    assert len(s.state.rules.pairs) == 2
    assert 'soulbond' not in Plan(s.state, 'p1', s.cards, None).ch(wing).keywords
    to_phase(s, 'declare_attackers', turn=7)
    refused(s, host)
    roundtrip(s)


def test_phase_out_ends_pair_for_duration_not_zone_change(cards):
    s, host, wing, _ = paired(cards)
    to_phase(s, 'main1', turn=7)
    cast(s, 'Reality Ripple', [wing.id])
    assert wing.zone.endswith(':phased') and not s.state.rules.pairs
    to_phase(s, 'declare_attackers', turn=7)
    refused(s, host)
    roundtrip(s)


def test_control_change_ends_pair(cards):
    s, host, wing, _ = paired(cards)
    to_phase(s, 'main1', turn=7)
    act(s, 'p1', type='set_controller', card_ids=[wing.id], player='p3')
    assert not s.state.rules.pairs
    to_phase(s, 'declare_attackers', turn=7)
    refused(s, host)
    roundtrip(s)


def test_losing_pair_after_declaration_does_not_remove_attacker(cards):
    s, host, wing, _ = paired(cards)
    to_phase(s, 'declare_attackers', turn=7)
    attack(s, host)
    cast(s, 'Reality Ripple', [wing.id])
    assert not s.state.rules.pairs and host.is_attacking
    roundtrip(s)


def blockers(s, enemy):
    to_phase(s, 'declare_attackers', turn=8)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id':enemy.id,'target':'p1'}])
    to_phase(s, 'declare_blockers', turn=8)


def block(s, host, enemy):
    act(s, 'p1', type='declare_blockers', blocks=[{'blocker_id':host.id,'attacker_id':enemy.id}])


def test_paired_can_block_and_later_unpair_does_not_undo(cards):
    s, host, wing, enemy = paired(cards)
    blockers(s, enemy)
    block(s, host, enemy)
    cast(s, 'Reality Ripple', [wing.id])
    assert not s.state.rules.pairs and host.is_blocking
    roundtrip(s)


def test_unpaired_cannot_block(cards):
    s, enemy = setup(cards)
    host = cast(s, NAME)
    blockers(s, enemy)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        block(s, host, enemy)
    assert before == s.state.model_dump_json()
    roundtrip(s)


def test_cold_pair_pending_attack(cards, tmp_path):
    import os
    import subprocess
    import sys

    import app

    s, host, wing, _ = paired(cards)
    to_phase(s, 'declare_attackers', turn=7)
    saved = tmp_path / 'flowering70.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_combat_soulbond_partner70 import attack
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
host=s.state.cards[sys.argv[3]]
assert len(s.state.rules.pairs)==2
attack(s,host)
assert host.is_attacking
roundtrip(s)
"""
    backend = Path(app.__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), host.id],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
                            capture_output=True, text=True, timeout=180, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
