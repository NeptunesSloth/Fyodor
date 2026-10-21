"""Guardian loses defender and gains lasting trample via native combat triggers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Guardian of the Ages'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_defender_release53_cards.json').read_text())
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




def setup(cards):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = cast(s, NAME, {'C': 7})
    return s, source


def keywords(s, source):
    from app.rules.plan import Plan

    return Plan(s.state, 'p1', s.cards, None).ch(source).keywords


def attack_pending(cards, target='p1', multiple=False):
    s, source = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    if target == 'walker':
        target = cast(s, 'Jace Beleren', {'C': 1, 'U': 2}).id
    attackers = [bear]
    if multiple:
        attackers.append(put(s, 'Hill Giant', 'battlefield', 'p2'))
    to_phase(s, 'declare_attackers', turn=5)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': c.id, 'target': target} for c in attackers])
    return s, source


def test_whole_canonical(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_initial_defender_prevents_real_attack(cards):
    s, source = setup(cards)
    to_phase(s, 'declare_attackers', turn=7)
    with pytest.raises(ActionError):
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    assert 'defender' in keywords(s, source) and 'trample' not in keywords(s, source)


@pytest.mark.parametrize('target', ['p1', 'walker', 'p3'])
def test_native_attack_scope_and_permanent_keywords(cards, target):
    s, source = attack_pending(cards, target)
    settle(s)
    triggered = target != 'p3'
    assert ('trample' in keywords(s, source)) == triggered
    assert ('defender' in keywords(s, source)) != triggered
    to_phase(s, 'main1', turn=7)
    assert ('trample' in keywords(s, source)) == triggered
    assert ('defender' in keywords(s, source)) != triggered
    roundtrip(s)


def test_native_multiple_attackers_resolution_defender_recheck(cards):
    s, source = attack_pending(cards, multiple=True)
    settle(s)
    assert 'trample' in keywords(s, source) and 'defender' not in keywords(s, source)
    assert sum(1 for g in s.state.rules.effects if 'trample' in g.add_keywords and 'defender' in g.remove_keywords) == 1
    roundtrip(s)


def test_native_source_successor_retains_defender(cards):
    s, source = attack_pending(cards)
    assert s.state.zones['stack']
    old = s.state.rules.object_id(source.id)
    cast(s, 'Flicker of Fate', {'C': 1, 'W': 1}, [source.id])
    assert s.state.rules.object_id(source.id) != old
    assert 'defender' in keywords(s, source) and 'trample' not in keywords(s, source)
    roundtrip(s)


def test_native_resolution_rechecks_defender_before_permanent_grant(cards):
    s, source = attack_pending(cards)
    cast(s, 'Turn to Frog', {'C': 1, 'U': 1}, [source.id])
    to_phase(s, 'main1', turn=7)
    assert 'defender' in keywords(s, source) and 'trample' not in keywords(s, source)
    roundtrip(s)


@pytest.mark.parametrize('mode', ['pending', 'permanent'])
def test_true_cold_pending_and_permanent_defender_exchange(cards, tmp_path, mode):
    import subprocess
    import sys

    s, source = attack_pending(cards)
    if mode == 'permanent':
        settle(s)
        to_phase(s, 'main1', turn=7)
    saved = tmp_path / 'guardian53.json'
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
from tests.test_rules_trigger_defender_release53 import keywords
from tests.test_rules_wave30m_durations import to_phase
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source=s.state.cards[sys.argv[3]]
if sys.argv[4]=='pending':
    assert s.state.zones['stack']
    settle(s)
    to_phase(s,'main1',turn=7)
assert 'trample' in keywords(s,source) and 'defender' not in keywords(s,source)
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, mode],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_released_guardian_attacks_and_tramples_over_blocker(cards):
    from tests.test_rules_conditional_prevention import attack, damage

    s, source = attack_pending(cards)
    settle(s)
    blocker = put(s, 'Hill Giant', 'battlefield', 'p2')
    attack(s, [source], turn=7)
    to_phase(s, 'declare_blockers')
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': source.id}])
    damage(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    act(s, 'p1', type='choose', decision_id=d.id, amounts=[3, 4])
    settle(s)
    assert s.state.players['p2'].life == 36
    assert blocker.zone == 'p2:graveyard' and source.zone == 'p1:battlefield'
    roundtrip(s)
