"""Last Laugh's native state trigger and death/damage chain preserve original objects."""
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

NAME = 'Last Laugh'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_empty_board50_cards.json').read_text())
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


def empty_pending(cards):
    s = game(cards)
    source = cast(s, NAME, {'C': 2, 'B': 2}, resolve=False)
    resolve_only(s, source)
    assert source.zone == 'p1:battlefield' and s.state.zones['stack']
    return s, source


def repopulated(cards, successor=False):
    s, source = empty_pending(cards)
    alarm = cast(s, 'Raise the Alarm', {'C': 1, 'W': 1}, resolve=False)
    resolve_only(s, alarm)
    soldiers = [c for c in s.state.cards.values() if c.is_token and c.name == 'Soldier' and c.zone == 'p1:battlefield']
    assert len(soldiers) == 2 and s.state.zones['stack']
    if successor:
        old = s.state.rules.object_id(source.id)
        flicker = cast(s, 'Flicker of Fate', {'C': 1, 'W': 1}, [source.id], resolve=False)
        resolve_only(s, flicker)
        assert s.state.rules.object_id(source.id) != old
    return s, source


def test_complete_canonical_supported(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_native_paid_empty_board_sacrifices_without_self_death_damage(cards):
    s, source = empty_pending(cards)
    settle(s)
    assert source.zone == 'p1:graveyard' and all(p.life == 40 for p in s.state.players.values())
    assert not s.state.players['p1'].mana
    roundtrip(s)


def test_native_creature_prevents_empty_board_state_trigger(cards):
    s = game(cards)
    put(s, 'Grizzly Bears', 'battlefield')
    source = cast(s, NAME, {'C': 2, 'B': 2})
    assert source.zone == 'p1:battlefield' and not s.state.zones['stack']
    assert all(p.life == 40 for p in s.state.players.values())
    roundtrip(s)


def test_native_permanent_deaths_chain_damage_and_final_state_sacrifice(cards):
    s = game(cards)
    own = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Runeclaw Bear', 'battlefield', 'p2')
    elf = put(s, 'Llanowar Elves', 'battlefield', 'p3')
    land = put(s, 'Island', 'battlefield', 'p3')
    source = cast(s, NAME, {'C': 2, 'B': 2})
    cast(s, 'Lightning Bolt', {'R': 1}, [elf.id])
    assert elf.zone == 'p3:graveyard' and own.damage == other.damage == 1
    assert all(p.life == 39 for p in s.state.players.values())
    cast(s, 'Stone Rain', {'C': 2, 'R': 1}, [land.id])
    assert own.zone == 'p1:graveyard' and other.zone == 'p2:graveyard'
    assert source.zone == 'p1:graveyard' and all(p.life == 36 for p in s.state.players.values())
    roundtrip(s)


def test_new_creatures_do_not_cancel_already_triggered_state_sacrifice(cards):
    s, source = repopulated(cards)
    settle(s)
    assert source.zone == 'p1:graveyard'
    assert len([c for c in s.state.cards.values() if c.is_token and c.name == 'Soldier' and c.zone == 'p1:battlefield']) == 2
    assert all(p.life == 40 for p in s.state.players.values())
    roundtrip(s)


def test_native_blinked_successor_does_not_satisfy_old_state_trigger_source(cards):
    s, source = repopulated(cards, True)
    settle(s)
    assert source.zone == 'p1:battlefield' and not s.state.zones['stack']
    roundtrip(s)


@pytest.mark.parametrize('mode', ['empty', 'repopulated', 'successor'])
def test_true_cold_native_empty_state_and_original_source_identity(cards, tmp_path, mode):
    import subprocess
    import sys

    s, source = empty_pending(cards) if mode == 'empty' else repopulated(cards, mode == 'successor')
    saved = tmp_path / 'lastlaugh50.json'
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
source=s.state.cards[sys.argv[3]]
assert source.zone==('p1:battlefield' if sys.argv[4]=='successor' else 'p1:graveyard')
assert all(p.life==40 for p in s.state.players.values())
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, mode],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
