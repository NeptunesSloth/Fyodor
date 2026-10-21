"""Celestial Regulator chooses one target and binds its conditional next untap."""
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

NAME = 'Celestial Regulator'
DATA = json.loads((Path(__file__).parent / 'fixtures/conditional_tap_counter73_cards.json').read_text())


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
    s = table(cards, [NAME, 'Llanowar Elves', 'Sol Ring'], ['Grizzly Bears'])
    start(s)
    return s


@pytest.mark.parametrize('has_counter', [False, True])
def test_whole_card_taps_and_conditionally_skips_actual_next_untap(cards, has_counter):
    from tests.test_rules_wave30m_durations import to_phase

    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'
    s = setup(cards)
    creature = put(s, 'Llanowar Elves', 'battlefield')
    if has_counter:
        act(s, 'p1', type='counter', card_ids=[creature.id], kind='shield', delta=1)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    source = put(s, NAME, 'hand')
    wait_priority(s, 'p1')
    mana(s, C=1, W=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    d = s.state.rules.decision
    assert d
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[target.id])
    settle(s)
    assert target.tapped
    to_phase(s, 'main1', turn=5)
    assert target.tapped is has_counter
    roundtrip(s)


def pending_trigger(s):
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    source = put(s, NAME, 'hand')
    wait_priority(s, 'p1')
    mana(s, C=1, W=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    d = s.state.rules.decision
    assert d
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[target.id])
    return source, target


@pytest.mark.parametrize('add', [False, True])
def test_counter_condition_is_checked_at_resolution(cards, add):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    creature = put(s, 'Llanowar Elves', 'battlefield')
    if not add:
        act(s, 'p1', type='counter', card_ids=[creature.id], kind='charge', delta=1)
    _, target = pending_trigger(s)
    act(s, 'p1', type='counter', card_ids=[creature.id], kind='charge', delta=1 if add else -1)
    settle(s)
    to_phase(s, 'main1', turn=5)
    assert target.tapped is add
    roundtrip(s)


def test_artifact_counter_does_not_satisfy_creature_condition(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    artifact = put(s, 'Sol Ring', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[artifact.id], kind='charge', delta=1)
    _, target = pending_trigger(s)
    settle(s)
    to_phase(s, 'main1', turn=5)
    assert not target.tapped
    roundtrip(s)


def test_true_cold_pending_native_trigger_keeps_target_and_next_untap(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    creature = put(s, 'Llanowar Elves', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[creature.id], kind='shield', delta=1)
    _, target = pending_trigger(s)
    saved = tmp_path / 'regulator73.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
settle(s)
assert s.state.cards[sys.argv[3]].tapped
# The real next turn's untap is skipped; the following controller turn is ordinary.
to_phase(s,'main1',turn=5)
assert s.state.cards[sys.argv[3]].tapped
to_phase(s,'main1',turn=8)
assert not s.state.cards[sys.argv[3]].tapped
GameState.model_validate_json(s.state.model_dump_json())
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), target.id],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
