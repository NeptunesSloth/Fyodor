"""Counter copies onto new tokens retain the departed source's native object identity."""
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
from tests.test_rules_counter_event_comparisons50 import resolve_only
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

NAMES = ['Ambitious Augmenter', 'Grizzly Bears', 'Hill Giant', 'Giant Growth', 'Lightning Bolt', 'Murder',
         'Counterspell', 'Doubling Season', 'Solemnity', 'The Ozolith', 'Miraculous Recovery', 'Scar']
PAY = {'Ambitious Augmenter': {'G': 1}, 'Grizzly Bears': {'C': 1, 'G': 1}, 'Hill Giant': {'C': 3, 'R': 1},
       'Giant Growth': {'G': 1}, 'Lightning Bolt': {'R': 1}, 'Murder': {'C': 1, 'B': 2},
       'Counterspell': {'U': 2}, 'Miraculous Recovery': {'C': 4, 'W': 1}, 'Scar': {'R': 1}}


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    rows = json.loads((Path(__file__).parent / 'fixtures/counter_lki_tokens50_cards.json').read_text())
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
    mana(s, pid=pid, **PAY[name])
    act(s, pid, type='cast_spell', card_id=source.id, targets=list(targets), sources=[])
    if resolve:
        settle(s)
    return source


def setup(cards):
    s = game(cards)
    source = cast(s, 'Ambitious Augmenter')
    assert not source.counters
    return s, source


def put_mixed_counters(s, source):
    for kind, n in [('+1/+1', 1), ('charge', 2), ('flying', 1)]:
        act(s, 'p1', type='counter', card_ids=[source.id], kind=kind, delta=n)
    assert source.counters == {'+1/+1': 1, 'charge': 2, 'flying': 1}


def fractals(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == 'Fractal' and c.zone == 'p1:battlefield']


def test_whole_canonical_augmenter(cards):
    assert coverage.of_card_data(cards.resolve('Ambitious Augmenter')).level == 'FULL'


def test_increment_resolves_before_triggering_spell(cards):
    s, source = setup(cards)
    bear = cast(s, 'Grizzly Bears', resolve=False)
    for _ in range(20):
        if source.counters.get('+1/+1') == 1:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert source.counters == {'+1/+1': 1} and bear.zone == 'stack'
    settle(s)
    assert bear.zone == 'p1:battlefield'
    roundtrip(s)


def test_increment_persists_when_triggering_spell_is_countered(cards):
    s, source = setup(cards)
    bear = cast(s, 'Grizzly Bears', resolve=False)
    cast(s, 'Counterspell', [bear.id], pid='p2')
    assert bear.zone == 'p1:graveyard' and source.counters == {'+1/+1': 1}
    roundtrip(s)


def test_increment_comparison_rechecks_current_power_and_toughness(cards):
    s, source = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    bear = cast(s, 'Grizzly Bears', resolve=False)
    cast(s, 'Giant Growth', [source.id])
    assert bear.zone == 'p1:battlefield' and not source.counters
    roundtrip(s)


def test_death_copies_every_kind_to_token_and_ozolith_independently(cards):
    s, source = setup(cards)
    put_mixed_counters(s, source)
    ozolith = put(s, 'The Ozolith', 'battlefield')
    cast(s, 'Murder', [source.id], pid='p2')
    token, = fractals(s)
    expected = {'+1/+1': 1, 'charge': 2, 'flying': 1}
    assert token.counters == expected and ozolith.counters == expected
    assert source.zone == 'p1:graveyard'
    from app.rules.plan import Plan

    assert Plan(s.state, 'p1', cards, None).ch(token).pt == (1, 1)
    assert 'flying' in Plan(s.state, 'p1', cards, None).ch(token).keywords
    roundtrip(s)


def test_no_counters_means_death_trigger_creates_nothing(cards):
    s, source = setup(cards)
    cast(s, 'Murder', [source.id], pid='p2')
    assert source.zone == 'p1:graveyard' and not fractals(s)
    roundtrip(s)


def test_non_power_counters_are_copied_but_zero_toughness_token_dies(cards):
    s, source = setup(cards)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='charge', delta=2)
    ozolith = put(s, 'The Ozolith', 'battlefield')
    cast(s, 'Murder', [source.id], pid='p2')
    # Both departing creatures contribute: Augmenter, then its charge-only 0/0 token.
    assert ozolith.counters == {'charge': 4} and not fractals(s)
    roundtrip(s)


def test_native_replacements_double_tokens_and_all_put_counters(cards):
    s, source = setup(cards)
    put_mixed_counters(s, source)
    put(s, 'Doubling Season', 'battlefield')
    cast(s, 'Murder', [source.id], pid='p2')
    tokens = fractals(s)
    assert len(tokens) == 2
    assert all(c.counters == {'+1/+1': 2, 'charge': 4, 'flying': 2} for c in tokens)
    roundtrip(s)


def test_prohibited_counter_puts_leave_zero_toughness_tokens_to_die(cards):
    s, source = setup(cards)
    put_mixed_counters(s, source)
    put(s, 'Solemnity', 'battlefield')
    cast(s, 'Murder', [source.id], pid='p2')
    assert source.zone == 'p1:graveyard' and not fractals(s)
    roundtrip(s)


def reanimated_successor(cards):
    s, source = setup(cards)
    put_mixed_counters(s, source)
    old = s.state.rules.object_id(source.id)
    murder = cast(s, 'Murder', [source.id], pid='p2', resolve=False)
    resolve_only(s, murder)
    assert source.zone == 'p1:graveyard' and s.state.zones['stack']
    recovery = cast(s, 'Miraculous Recovery', [source.id], resolve=False)
    resolve_only(s, recovery)
    assert source.zone == 'p1:battlefield' and s.state.rules.object_id(source.id) != old
    act(s, 'p1', type='counter', card_ids=[source.id], kind='charge', delta=9)
    return s, source


def test_death_trigger_reads_departed_source_not_reanimated_successor(cards):
    s, source = reanimated_successor(cards)
    settle(s)
    token, = fractals(s)
    assert token.counters == {'+1/+1': 1, 'charge': 2, 'flying': 1}
    assert source.counters == {'+1/+1': 1, 'charge': 9}
    roundtrip(s)


def test_lethal_negative_counter_is_copied_and_new_token_also_dies(cards):
    s, source = setup(cards)
    ozolith = put(s, 'The Ozolith', 'battlefield')
    cast(s, 'Scar', [source.id], pid='p2')
    assert source.zone == 'p1:graveyard' and not fractals(s)
    assert ozolith.counters == {'-1/-1': 2}
    roundtrip(s)


@pytest.mark.parametrize('mode', ['successor', 'doubled'])
def test_true_cold_death_counter_copy_and_native_token_replacements(cards, tmp_path, mode):
    import subprocess
    import sys

    if mode == 'successor':
        s, source = reanimated_successor(cards)
        expected = {'+1/+1': 1, 'charge': 2, 'flying': 1}
        count = 1
    else:
        s, source = setup(cards)
        put_mixed_counters(s, source)
        put(s, 'Doubling Season', 'battlefield')
        murder = cast(s, 'Murder', [source.id], pid='p2', resolve=False)
        resolve_only(s, murder)
        expected = {'+1/+1': 2, 'charge': 4, 'flying': 2}
        count = 2
    saved = tmp_path / 'augmenter50.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import json,sys
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
tokens=[c for c in s.state.cards.values() if c.is_token and c.name=='Fractal' and c.zone=='p1:battlefield']
assert len(tokens)==int(sys.argv[4])
assert all(c.counters==json.loads(sys.argv[5]) for c in tokens)
if sys.argv[6]=='successor':
 assert s.state.cards[sys.argv[3]].counters=={'+1/+1':1,'charge':9}
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, str(count), json.dumps(expected), mode],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
