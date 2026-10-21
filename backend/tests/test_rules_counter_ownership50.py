"""Jinxed Choker's recipient puts the counter, while each triggered ability keeps its controller."""
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

NAME = 'Jinxed Choker'
NAMES = [NAME, 'Vorinclex, Monstrous Raider', 'Solemnity', 'Memnarch']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    rows = json.loads((Path(__file__).parent / 'fixtures/counter_ownership50_cards.json').read_text())
    for i, c in enumerate(rows):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    source = put(s, NAME, 'hand')
    mana(s, C=3)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    assert source.zone == 'p1:battlefield' and not s.state.players['p1'].mana
    return s, source


def announce_end_target(s, pid='p2'):
    to_phase(s, 'end', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    assert pid in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[pid])


def transfer(s, pid='p2'):
    announce_end_target(s, pid)
    settle(s)


def activate(s, source, pid='p2'):
    wait_priority(s, pid)
    mana(s, pid=pid, C=3)
    act(s, pid, type='activate_ability', card_id=source.id, ability=2, sources=[])
    assert s.state.rules.decision is None
    settle(s)


def choose(s, option):
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'pick_one'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option])
    settle(s)


def test_whole_canonical_jinxed_choker(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('pid,turn', [('p2', 5), ('p3', 6)])
def test_end_step_transfer_and_next_upkeep_damage_follow_new_controller(cards, pid, turn):
    s, source = setup(cards)
    transfer(s, pid)
    assert source.controller == pid and source.counters == {'charge': 1}
    to_phase(s, 'upkeep', turn=turn)
    settle(s)
    assert s.state.players[pid].life == 39
    assert all(p.life == 40 for other, p in s.state.players.items() if other != pid)
    roundtrip(s)


def test_counter_putter_is_target_recipient_for_actor_sensitive_replacement(cards):
    s, source = setup(cards)
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield', 'p2')
    transfer(s)
    assert source.controller == 'p2' and source.counters == {'charge': 2}
    roundtrip(s)


def test_control_transfer_still_occurs_when_counters_are_prohibited(cards):
    s, source = setup(cards)
    put(s, 'Solemnity', 'battlefield')
    transfer(s)
    assert source.controller == 'p2' and not source.counters
    roundtrip(s)


def test_new_controller_pays_and_chooses_add_or_remove_on_resolution(cards):
    s, source = setup(cards)
    transfer(s)
    activate(s, source)
    assert s.state.rules.decision.player == 'p2'
    choose(s, '1')
    assert not source.counters
    activate(s, source)
    assert s.state.rules.decision is None and source.counters == {'charge': 1}
    assert not s.state.players['p2'].mana
    roundtrip(s)


def test_former_controller_cannot_activate_transferred_artifact(cards):
    s, source = setup(cards)
    transfer(s)
    wait_priority(s, 'p1')
    mana(s, C=3)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, sources=[])
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_blinked_successor_is_not_transferred_or_given_old_trigger_counter(cards):
    s, source = setup(cards)
    announce_end_target(s)
    old = s.state.rules.object_id(source.id)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    assert s.state.rules.object_id(source.id) != old
    settle(s)
    assert source.controller == 'p1' and not source.counters
    roundtrip(s)


def test_counter_is_still_put_when_target_already_controls_source_at_resolution(cards):
    s, source = setup(cards)
    announce_end_target(s)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    settle(s)
    assert source.controller == 'p2' and source.counters == {'charge': 1}
    roundtrip(s)


def upkeep_pending(cards):
    s, source = setup(cards)
    transfer(s)
    to_phase(s, 'upkeep', turn=5)
    assert s.state.zones['stack']
    return s, source


def test_upkeep_damage_uses_counter_count_at_resolution(cards):
    s, source = upkeep_pending(cards)
    activate(s, source)
    choose(s, '1')
    assert not source.counters and s.state.players['p2'].life == 40
    roundtrip(s)


def test_upkeep_trigger_keeps_original_controller_when_source_control_changes(cards):
    s, source = upkeep_pending(cards)
    thief = put(s, 'Memnarch', 'battlefield', 'p3')
    wait_priority(s, 'p3')
    mana(s, pid='p3', C=3, U=1)
    act(s, 'p3', type='activate_ability', card_id=thief.id, ability=1, sources=[], targets=[source.id])
    settle(s)
    assert source.controller == 'p3'
    assert s.state.players['p2'].life == 39 and s.state.players['p3'].life == 40
    roundtrip(s)


def test_upkeep_uses_departed_source_last_known_counters(cards):
    s, source = upkeep_pending(cards)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    assert s.state.players['p2'].life == 39
    roundtrip(s)


@pytest.mark.parametrize('mode', ['recipient', 'departed'])
def test_true_cold_recipient_counter_actor_and_departed_upkeep(cards, tmp_path, mode):
    import subprocess
    import sys

    if mode == 'recipient':
        s, source = setup(cards)
        put(s, 'Vorinclex, Monstrous Raider', 'battlefield', 'p2')
        announce_end_target(s)
    else:
        s, source = upkeep_pending(cards)
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    saved = tmp_path / 'choker50.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_counter_ownership50 import activate,choose
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert s.state.zones['stack']
settle(s)
source=s.state.cards[sys.argv[3]]
if sys.argv[4]=='recipient':
 assert source.controller=='p2' and source.counters=={'charge':2}
 activate(s,source)
 choose(s,'1')
 assert source.counters=={'charge':1} and not s.state.players['p2'].mana
else:
 assert source.zone=='p1:exile' and s.state.players['p2'].life==39
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, mode],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
