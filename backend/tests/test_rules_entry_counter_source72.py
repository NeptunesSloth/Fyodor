"""Bloodspore's printed devour and source-bound entry replacement use native events."""
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
from tests.test_rules_wave48b_devour import devour_cast

NAME = 'Bloodspore Thrinax'
DATA = json.loads((Path(__file__).parent / 'fixtures/entry_counter_source72_cards.json').read_text())


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
    s = table(cards, [NAME, 'Grizzly Bears', 'Llanowar Elves', 'Krenko, Mob Boss', 'Solemnity', 'Doubling Season', 'Living Death'], ['Grizzly Bears'])
    start(s)
    return s


def test_whole_card_native_devour_and_following_entry(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'
    s = setup(cards)
    a = put(s, 'Grizzly Bears', 'battlefield')
    b = put(s, 'Llanowar Elves', 'battlefield')
    source = devour_cast(s, NAME, [a.id, b.id], C=2, G=2)
    assert source.counters == {'+1/+1': 2}
    assert a.zone == b.zone == 'p1:graveyard'
    entering = put(s, 'Krenko, Mob Boss', 'hand')
    wait_priority(s, 'p1')
    mana(s, C=2, R=2)
    act(s, 'p1', type='cast_spell', card_id=entering.id)
    settle(s)
    assert entering.counters == {'+1/+1': 2}
    assert not put(s, 'Grizzly Bears', 'battlefield', 'p2').counters
    roundtrip(s)


@pytest.mark.parametrize('n', [0, 3])
def test_source_current_counter_count_is_read_each_entry(cards, n):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    if n:
        act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+1', delta=n)
    entering = put(s, 'Krenko, Mob Boss', 'hand')
    wait_priority(s, 'p1')
    mana(s, C=2, R=2)
    act(s, 'p1', type='cast_spell', card_id=entering.id)
    settle(s)
    assert entering.counters.get('+1/+1', 0) == n
    roundtrip(s)


def cast_krenko(s):
    entering = put(s, 'Krenko, Mob Boss', 'hand')
    wait_priority(s, 'p1')
    mana(s, C=2, R=2)
    act(s, 'p1', type='cast_spell', card_id=entering.id)
    settle(s)
    return entering


def test_source_departure_removes_entry_replacement(cards):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+1', delta=3)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert not cast_krenko(s).counters
    roundtrip(s)


def test_native_counter_prohibition_stops_bloodspore_entry_counters(cards):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+1', delta=3)
    put(s, 'Solemnity', 'battlefield')
    assert not cast_krenko(s).counters
    roundtrip(s)


def test_native_simultaneous_reanimation_does_not_borrow_new_source(cards):
    s = setup(cards)
    source = put(s, NAME, 'graveyard')
    other = put(s, 'Grizzly Bears', 'graveyard')
    spell = put(s, 'Living Death', 'hand')
    wait_priority(s, 'p1')
    mana(s, C=3, B=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert source.zone == other.zone == 'p1:battlefield'
    assert not source.counters and not other.counters
    roundtrip(s)


def test_true_cold_native_pending_entry_reads_original_source_counters(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+1', delta=3)
    entering = put(s, 'Krenko, Mob Boss', 'hand')
    wait_priority(s, 'p1')
    mana(s, C=2, R=2)
    act(s, 'p1', type='cast_spell', card_id=entering.id)
    saved = tmp_path / 'entry-source72.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:battlefield'
assert s.state.cards[sys.argv[3]].counters=={'+1/+1':3}
GameState.model_validate_json(s.state.model_dump_json())
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), entering.id],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_counter_replacement_addition_then_doubling(cards):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+1', delta=3)
    put(s, 'Doubling Season', 'battlefield')
    entering = cast_krenko(s)
    while s.state.rules.decision is not None:
        d = s.state.rules.decision
        assert '616.1' in d.prompt
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
        settle(s)
    assert entering.zone == 'p1:battlefield' and entering.counters == {'+1/+1': 6}
    assert source.counters == {'+1/+1': 3}
    roundtrip(s)
