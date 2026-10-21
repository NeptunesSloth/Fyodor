"""Rage Forger binds optional damage to the actual attacking creature."""
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

NAME = 'Rage Forger'
DATA = json.loads((Path(__file__).parent / 'fixtures/optional_attacker_damage74_cards.json').read_text())


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
    s = table(cards, [NAME, 'Sakura-Tribe Elder', 'Llanowar Elves'], ['Grizzly Bears'])
    start(s)
    return s


def test_whole_printed_etb_only_other_controlled_shamans(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'
    s = setup(cards)
    shaman = put(s, 'Sakura-Tribe Elder', 'battlefield')
    other = put(s, 'Llanowar Elves', 'battlefield')
    source = put(s, NAME, 'hand')
    wait_priority(s, 'p1')
    mana(s, C=2, R=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert shaman.counters == {'+1/+1': 1}
    assert not other.counters and not source.counters
    roundtrip(s)


def test_actual_attacker_is_optional_damage_source_with_lifelink(cards):
    from tests.test_rules_conditional_prevention import attack

    s = setup(cards)
    put(s, NAME, 'battlefield')
    attacker = put(s, 'Llanowar Elves', 'battlefield')
    for kind in ['+1/+1', 'lifelink']:
        act(s, 'p1', type='counter', card_ids=[attacker.id], kind=kind, delta=1)
    attack(s, [attacker], turn=7)
    d = s.state.rules.decision
    assert d
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['p2'])
    settle(s)
    d = s.state.rules.decision
    assert d and d.kind == 'confirm'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['yes'])
    settle(s)
    assert s.state.players['p1'].life == 41 and s.state.players['p2'].life == 39
    roundtrip(s)


def pending_attack(s, *, kind='+1/+1', name='Llanowar Elves'):
    from tests.test_rules_conditional_prevention import attack

    source = put(s, NAME, 'battlefield')
    attacker = put(s, name, 'battlefield')
    if kind:
        act(s, 'p1', type='counter', card_ids=[attacker.id], kind=kind, delta=1)
    attack(s, [attacker], turn=7)
    return source, attacker


@pytest.mark.parametrize('kind', [None, 'shield'])
def test_attack_without_plus_counter_does_not_trigger(cards, kind):
    s = setup(cards)
    pending_attack(s, kind=kind)
    assert s.state.rules.decision is None and not s.state.zones.get('stack')
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_optional_damage_may_be_declined(cards):
    s = setup(cards)
    pending_attack(s)
    d = s.state.rules.decision
    assert d
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['p2'])
    settle(s)
    d = s.state.rules.decision
    assert d and d.kind == 'confirm'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['no'])
    settle(s)
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_attacking_creature_departure_retains_its_own_lifelink_lki(cards):
    s = setup(cards)
    _, attacker = pending_attack(s, name='Sakura-Tribe Elder')
    act(s, 'p1', type='counter', card_ids=[attacker.id], kind='lifelink', delta=1)
    d = s.state.rules.decision
    assert d
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['p2'])
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=attacker.id, ability=0)
    settle(s)
    d = s.state.rules.decision
    if d and d.resume.get('step') == 'search':
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
        settle(s)
    d = s.state.rules.decision
    assert d and d.kind == 'confirm'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['yes'])
    settle(s)
    assert s.state.players['p1'].life == 41 and s.state.players['p2'].life == 39
    roundtrip(s)


def test_true_cold_optional_damage_keeps_attacker_source(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    _, attacker = pending_attack(s)
    act(s, 'p1', type='counter', card_ids=[attacker.id], kind='lifelink', delta=1)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['p2'])
    settle(s)
    assert s.state.rules.decision.kind == 'confirm'
    saved = tmp_path / 'rage74.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=['yes'])
settle(s)
assert s.state.players['p1'].life==41 and s.state.players['p2'].life==39
GameState.model_validate_json(s.state.model_dump_json())
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path)],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
