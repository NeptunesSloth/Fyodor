"""Native entry/face-up unions preserve object identity and actual entry counter replacements."""
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
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

CASE = 'Case of the Pilfered Proof'
OOZE = 'Printlifter Ooze'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_faceup_union50_cards.json').read_text())
NAMES = [c['name'] for c in DATA] + ['Novice Inspector', 'Novice Inspector']


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


def game(cards):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    return s


def put(s, name, zone='battlefield', pid='p1'):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith(':battlefield'))
    act(s, pid, type='move', card_ids=[c.id], to={'player': pid, 'zone': zone})
    return s.state.cards[c.id]


def cast(s, name, pool, *, pid='p1', face_down=False, targets=(), resolve=True):
    wait_priority(s, pid)
    source = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='cast_spell', card_id=source.id, sources=[], targets=list(targets), face_down=face_down)
    if resolve:
        settle(s)
    return source


def up(s, source, pool, *, pid='p1', resolve=True):
    wait_priority(s, pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='turn_face_up', card_id=source.id, sources=[])
    if resolve:
        settle(s)


def tokens(s, name):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.zone == 'p1:battlefield']


@pytest.mark.parametrize('name', [CASE])
def test_complete_canonical_supported(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_case_native_entry_counter_and_three_detective_solve_token_replacement(cards):
    s = game(cards)
    source = cast(s, CASE, {'C': 1, 'W': 1})
    for _ in range(3):
        inspector = cast(s, 'Novice Inspector', {'W': 1})
        assert inspector.counters == {'+1/+1': 1}
    assert len(tokens(s, 'Clue')) == 3
    to_phase(s, 'end', turn=4)
    settle(s)
    assert 'Solved' in source.choices
    cast(s, 'Raise the Alarm', {'C': 1, 'W': 1})
    assert len(tokens(s, 'Soldier')) == 2 and len(tokens(s, 'Clue')) == 4
    roundtrip(s)


def finish_witness(s, witness):
    for _ in range(40):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            return
        ids = {o.id for o in d.options}
        chosen = ([o.id for o in d.options] if d.kind == 'order' else ['no'] if 'no' in ids else
                  [witness.id] if witness.id in ids else [d.options[0].id])
        act(s, d.player, type='choose', decision_id=d.id, option_ids=chosen)
    raise AssertionError('Native witness choices did not finish')


def test_case_native_face_up_detective_counter_and_non_detective_negative(cards):
    s = game(cards)
    cast(s, CASE, {'C': 1, 'W': 1})
    witness = cast(s, 'Granite Witness', {'C': 3}, face_down=True)
    assert not witness.counters
    up(s, witness, {'U': 2}, resolve=False)
    finish_witness(s, witness)
    assert witness.counters == {'+1/+1': 1}
    ooze = cast(s, OOZE, {'C': 1, 'G': 1})
    assert not ooze.counters
    roundtrip(s)


def test_case_opponent_detective_does_not_get_counter(cards):
    s = game(cards)
    cast(s, CASE, {'C': 1, 'W': 1})
    to_phase(s, 'main1', turn=5)
    inspector = cast(s, 'Novice Inspector', {'W': 1}, pid='p2')
    assert not inspector.counters
    roundtrip(s)


def test_case_solve_condition_is_rechecked_at_resolution(cards):
    s = game(cards)
    source = cast(s, CASE, {'C': 1, 'W': 1})
    inspectors = [cast(s, 'Novice Inspector', {'W': 1}) for _ in range(3)]
    to_phase(s, 'end', turn=4)
    assert s.state.zones['stack']
    act(s, 'p1', type='move', card_ids=[inspectors[0].id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert 'Solved' not in source.choices
    roundtrip(s)


def pending_case_entry(cards):
    from tests.test_rules_counter_event_comparisons50 import resolve_only

    s = game(cards)
    cast(s, CASE, {'C': 1, 'W': 1})
    inspector = cast(s, 'Novice Inspector', {'W': 1}, resolve=False)
    resolve_only(s, inspector)
    return s, inspector


def test_case_departed_detective_trigger_does_not_counter_blinked_successor(cards):
    s, inspector = pending_case_entry(cards)
    old = s.state.rules.object_id(inspector.id)
    act(s, 'p1', type='move', card_ids=[inspector.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[inspector.id], to={'player': 'p1', 'zone': 'battlefield'})
    assert s.state.rules.object_id(inspector.id) != old
    settle(s)
    assert not inspector.counters
    roundtrip(s)


def test_case_changed_controller_does_not_erase_original_entry_trigger(cards):
    s, inspector = pending_case_entry(cards)
    act(s, 'p1', type='set_controller', card_ids=[inspector.id], player='p2')
    settle(s)
    assert inspector.controller == 'p2' and inspector.counters == {'+1/+1': 1}
    roundtrip(s)


def test_true_cold_case_native_entry_reference_and_investigate(cards, tmp_path):
    import subprocess
    import sys

    s, inspector = pending_case_entry(cards)
    saved = tmp_path / 'case50.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_trigger_faceup_union50 import tokens
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert s.state.zones['stack'] or s.state.rules.decision is not None
settle(s)
assert s.state.cards[sys.argv[3]].counters=={'+1/+1':1} and len(tokens(s,'Clue'))==1
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), inspector.id],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('replacement,counter,clues', [('Doubling Season', 2, 2), ('Solemnity', 0, 1)])
def test_case_native_counter_replacement_and_prohibition(cards, replacement, counter, clues):
    s = game(cards)
    cast(s, CASE, {'C': 1, 'W': 1})
    put(s, replacement)
    inspector = cast(s, 'Novice Inspector', {'W': 1})
    assert inspector.counters.get('+1/+1', 0) == counter
    assert len(tokens(s, 'Clue')) == clues
    roundtrip(s)
