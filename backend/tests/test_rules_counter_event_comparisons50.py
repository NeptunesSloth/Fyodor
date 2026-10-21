"""Pelt Collector checks an intervening condition against current or last-known objects."""
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
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Pelt Collector', 'Giant Growth', 'Grizzly Bears', 'Hill Giant', 'Colossal Dreadmaw',
         'Lightning Bolt', 'Dive Down', 'Pyroclasm', 'Flicker of Fate', 'Llanowar Elves', 'Downsize', 'Ornithopter']
PAY = {'Pelt Collector': {'G': 1}, 'Giant Growth': {'G': 1}, 'Grizzly Bears': {'C': 1, 'G': 1},
       'Hill Giant': {'C': 3, 'R': 1}, 'Colossal Dreadmaw': {'C': 4, 'G': 2}, 'Lightning Bolt': {'R': 1},
       'Dive Down': {'U': 1}, 'Pyroclasm': {'C': 1, 'R': 1}, 'Flicker of Fate': {'C': 1, 'W': 1},
       'Llanowar Elves': {'G': 1}, 'Downsize': {'U': 1}, 'Ornithopter': {}}


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    rows = json.loads((Path(__file__).parent / 'fixtures/counter_event_comparisons50_cards.json').read_text())
    for i, c in enumerate(rows):
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


def cast(s, name, targets=(), pid='p1', resolve=True):
    source = put(s, name, 'hand', pid)
    wait_priority(s, pid)
    if PAY[name]:
        mana(s, pid=pid, **PAY[name])
    act(s, pid, type='cast_spell', card_id=source.id, targets=list(targets), sources=[])
    if resolve:
        settle(s)
    return source


def resolve_only(s, spell):
    for _ in range(30):
        if spell.zone != 'stack':
            return
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('Spell never resolved')


def setup(cards):
    s = game(cards)
    source = cast(s, 'Pelt Collector')
    assert not source.counters  # Its own entry never triggers the other-creature ability.
    return s, source


def test_full_canonical_pelt(cards):
    assert coverage.of_card_data(cards.resolve('Pelt Collector')).level == 'FULL'


def test_entry_power_and_counter_growth_enable_actual_trample(cards):
    from app.rules.plan import Plan
    from tests.test_rules_conditional_prevention import attack, damage

    s, source = setup(cards)
    for name, n in [('Grizzly Bears', 1), ('Hill Giant', 2), ('Colossal Dreadmaw', 3)]:
        cast(s, name)
        assert source.counters.get('+1/+1') == n
        assert ('trample' in Plan(s.state, 'p1', cards, None).ch(source).keywords) == (n >= 3)
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attack(s, [source], turn=7)
    to_phase(s, 'declare_blockers')
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': source.id}])
    damage(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, 'p1', type='choose', decision_id=d.id, amounts=[2, 2])
    settle(s)
    assert blocker.zone == 'p2:graveyard' and s.state.players['p2'].life == 38
    roundtrip(s)


def test_equal_power_and_opponent_entry_do_not_trigger(cards):
    s, source = setup(cards)
    cast(s, 'Llanowar Elves')
    assert not source.counters
    to_phase(s, 'main1', turn=5)
    cast(s, 'Grizzly Bears', pid='p2')
    assert not source.counters
    roundtrip(s)


def test_death_reads_greater_last_known_power(cards):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    source = cast(s, 'Pelt Collector')
    cast(s, 'Lightning Bolt', [bear.id])
    assert bear.zone == 'p1:graveyard' and source.counters == {'+1/+1': 1}
    roundtrip(s)


def test_intervening_if_rechecks_current_source_power(cards):
    s, source = setup(cards)
    bear = cast(s, 'Grizzly Bears', resolve=False)
    resolve_only(s, bear)
    assert s.state.zones['stack'] and not source.counters
    cast(s, 'Giant Growth', [source.id])
    assert not source.counters
    roundtrip(s)


def test_simultaneous_two_two_deaths_produce_only_one_counter(cards):
    s = game(cards)
    first = put(s, 'Grizzly Bears', 'battlefield')
    second = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='set_controller', card_ids=[second.id], player='p1')
    source = cast(s, 'Pelt Collector')
    cast(s, 'Dive Down', [source.id])
    cast(s, 'Pyroclasm')
    assert first.zone == 'p1:graveyard' and second.zone == 'p2:graveyard'
    assert source.zone == 'p1:battlefield' and source.counters == {'+1/+1': 1}
    roundtrip(s)


def test_entered_object_lki_ignores_blinked_physical_successor(cards):
    s, source = setup(cards)
    bear = cast(s, 'Grizzly Bears', resolve=False)
    resolve_only(s, bear)
    old = s.state.rules.object_id(bear.id)
    growth = cast(s, 'Giant Growth', [bear.id], resolve=False)
    resolve_only(s, growth)
    flicker = cast(s, 'Flicker of Fate', [bear.id], resolve=False)
    resolve_only(s, flicker)
    assert s.state.rules.object_id(bear.id) != old
    settle(s)
    assert source.counters == {'+1/+1': 2}
    roundtrip(s)


@pytest.mark.parametrize('mode,expected', [('old_object_lki', 2), ('source_power_changed', 0)])
def test_true_cold_intervening_comparison_and_object_identity(cards, tmp_path, mode, expected):
    import subprocess
    import sys

    s, source = setup(cards)
    bear = cast(s, 'Grizzly Bears', resolve=False)
    resolve_only(s, bear)
    target = bear if mode == 'old_object_lki' else source
    growth = cast(s, 'Giant Growth', [target.id], resolve=False)
    resolve_only(s, growth)
    if mode == 'old_object_lki':
        flicker = cast(s, 'Flicker of Fate', [bear.id], resolve=False)
        resolve_only(s, flicker)
    saved = tmp_path / 'pelt50.json'
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
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert s.state.zones['stack']
settle(s)
assert s.state.cards[sys.argv[3]].counters.get('+1/+1',0)==int(sys.argv[4])
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, str(expected)],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_negative_source_power_allows_zero_power_entering_creature(cards):
    s, source = setup(cards)
    cast(s, 'Downsize', [source.id], pid='p2')
    cast(s, 'Ornithopter')
    assert source.counters == {'+1/+1': 1}
    roundtrip(s)


def test_entering_creature_current_power_is_rechecked_at_resolution(cards):
    s, source = setup(cards)
    bear = cast(s, 'Grizzly Bears', resolve=False)
    resolve_only(s, bear)
    cast(s, 'Downsize', [bear.id], pid='p2')
    assert not source.counters
    roundtrip(s)


def test_simultaneously_dying_collector_cannot_gain_counter_in_time_to_survive(cards):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    source = cast(s, 'Pelt Collector')
    cast(s, 'Pyroclasm')
    assert source.zone == 'p1:graveyard' and bear.zone == 'p1:graveyard'
    assert not source.counters
    roundtrip(s)
