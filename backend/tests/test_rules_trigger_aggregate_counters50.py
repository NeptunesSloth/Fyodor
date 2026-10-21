"""Native common creature types and fixed counter totals drive trigger conditions and dynamic blocking rules."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_counter_event_comparisons50 import resolve_only
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

KIN = 'Littjara Kinseekers'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_aggregate_counters50_cards.json').read_text())
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


def game(cards):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    return s


def cast(s, name, pool, targets=(), *, pid='p1', resolve=True):
    wait_priority(s, pid)
    c = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='cast_spell', card_id=c.id, sources=[], targets=list(targets))
    if resolve:
        settle(s)
    return c


def kin_pending(cards):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    rune = put(s, 'Runeclaw Bear', 'battlefield')
    source = cast(s, KIN, {'C': 3, 'U': 1}, resolve=False)
    resolve_only(s, source)
    assert s.state.zones['stack']
    return s, source, bear, rune


def answer_scry(s):
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1' and d.min_choices == 0
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    settle(s)


@pytest.mark.parametrize('name', [KIN])
def test_whole_canonical_supported(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_kinseekers_native_changeling_common_type_counter_and_scry(cards):
    s, source, bear, rune = kin_pending(cards)
    settle(s)
    assert source.counters == {'+1/+1': 1}
    assert Plan(s.state, 'p1', cards, None).ch(source).pt == (3, 5)
    answer_scry(s)
    assert not s.state.players['p1'].mana
    roundtrip(s)


def test_pairwise_shared_types_do_not_establish_one_type_shared_by_all_three(cards):
    s = game(cards)
    put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Llanowar Elves', 'battlefield')
    source = cast(s, KIN, {'C': 3, 'U': 1})
    assert not source.counters and s.state.rules.decision is None
    roundtrip(s)


def test_kinseekers_rechecks_type_group_and_gates_both_counter_and_scry(cards):
    s, source, bear, rune = kin_pending(cards)
    cast(s, 'Turn to Frog', {'C': 1, 'U': 1}, [rune.id])
    assert not source.counters and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('replacement,n', [('Doubling Season', 2), ('Solemnity', 0)])
def test_kinseekers_native_counter_replacements_do_not_gate_scry(cards, replacement, n):
    s, source, bear, rune = kin_pending(cards)
    put(s, replacement, 'battlefield')
    settle(s)
    assert source.counters.get('+1/+1', 0) == n
    answer_scry(s)
    roundtrip(s)




def test_kinseekers_current_trio_can_differ_from_original_trio(cards):
    s, source, bear, rune = kin_pending(cards)
    put(s, 'Universal Automaton', 'battlefield')
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert source.counters == {'+1/+1': 1}
    answer_scry(s)
    roundtrip(s)


def test_later_type_group_does_not_retroactively_create_entry_trigger(cards):
    s = game(cards)
    put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Llanowar Elves', 'battlefield')
    source = cast(s, KIN, {'C': 3, 'U': 1})
    put(s, 'Runeclaw Bear', 'battlefield')
    settle(s)
    assert not source.counters and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('successor', [False, True])
def test_true_cold_native_type_condition_scry_and_original_source_uid(cards, tmp_path, successor):
    import subprocess
    import sys

    s, source, bear, rune = kin_pending(cards)
    if successor:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    saved = tmp_path / 'kinseekers50.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_trigger_aggregate_counters50 import answer_scry
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert s.state.zones['stack']
settle(s)
assert s.state.cards[sys.argv[3]].counters==({} if sys.argv[4]=='yes' else {'+1/+1':1})
answer_scry(s)
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, 'yes' if successor else 'no'],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
