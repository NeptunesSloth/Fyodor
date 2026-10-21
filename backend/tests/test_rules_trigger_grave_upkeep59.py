"""Native graveyard upkeep identity and intervening creature-count proofs."""
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
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_trigger_leaf51 import choose
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Nether Spirit'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_grave_upkeep59_cards.json').read_text())


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


def setup(cards, zone='graveyard', pid='p1', extra=None):
    s = table(cards, [NAME, NAME, 'Grizzly Bears', 'Island', 'Lightning Bolt'], [NAME, 'Island'], ['Island'])
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = put(s, NAME, zone, pid)
    if extra == NAME:
        other = next(c for c in s.state.cards.values() if c.name == NAME and c.owner == pid and c.id != source.id)
        act(s, pid, type='move', card_ids=[other.id], to={'player': pid, 'zone': 'graveyard'})
    elif extra:
        put(s, extra, 'graveyard', pid)
    return s, source


def test_whole_canonical(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('accept', [True, False])
def test_native_optional_return_ignores_noncreature_graveyard_cards(cards, accept):
    s, source = setup(cards, extra='Island')
    to_phase(s, 'upkeep', turn=7)
    settle(s)
    choose(s, ['yes' if accept else 'no'])
    assert source.zone == ('p1:battlefield' if accept else 'p1:graveyard')
    roundtrip(s)


@pytest.mark.parametrize('zone', ['battlefield', 'hand', 'exile'])
def test_native_wrong_zones_do_not_trigger(cards, zone):
    s, source = setup(cards, zone)
    to_phase(s, 'upkeep', turn=7)
    settle(s)
    assert s.state.rules.decision is None and source.zone == 'p1:' + zone
    roundtrip(s)


@pytest.mark.parametrize('extra', ['Grizzly Bears', NAME])
def test_native_another_creature_prevents_trigger_even_when_removed_after_upkeep(cards, extra):
    s, source = setup(cards, extra=extra)
    if extra == NAME:
        assert sum(c.name == NAME and c.zone == 'p1:graveyard' for c in s.state.cards.values()) == 2
    to_phase(s, 'upkeep', turn=7)
    settle(s)
    assert s.state.rules.decision is None and not s.state.zones.get('stack')
    other = next(c for c in s.state.cards.values() if c.zone == 'p1:graveyard' and c.id != source.id)
    act(s, 'p1', type='move', card_ids=[other.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    assert s.state.rules.decision is None and source.zone == 'p1:graveyard'
    roundtrip(s)


def test_native_new_creature_in_graveyard_blocks_resolution(cards):
    s, source = setup(cards)
    to_phase(s, 'upkeep', turn=7)
    put(s, 'Grizzly Bears', 'graveyard')
    settle(s)
    if s.state.rules.decision is not None:
        choose(s, ['yes'])
    assert source.zone == 'p1:graveyard'
    roundtrip(s)


def test_native_graveyard_round_trip_does_not_return_successor(cards):
    s, source = setup(cards)
    to_phase(s, 'upkeep', turn=7)
    old = s.state.rules.object_id(source.id)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert old != s.state.rules.object_id(source.id)
    settle(s)
    if s.state.rules.decision is not None:
        choose(s, ['yes'])
    assert source.zone == 'p1:graveyard'
    roundtrip(s)


def test_native_only_owner_upkeep_and_owners_creature_count(cards):
    s, source = setup(cards, pid='p2')
    put(s, 'Grizzly Bears', 'graveyard', 'p1')
    to_phase(s, 'upkeep', turn=5)
    settle(s)
    assert s.state.rules.decision.player == 'p2'
    choose(s, ['yes'])
    assert source.zone == 'p2:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('mode', ['yes', 'successor'])
def test_true_cold_graveyard_upkeep(cards, tmp_path, mode):
    import subprocess
    import sys

    import app

    s, source = setup(cards)
    to_phase(s, 'upkeep', turn=7)
    saved = tmp_path / 'grave59.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_trigger_leaf51 import choose
from tests.test_rules_designations import roundtrip
from tests.game_helpers import act
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source=s.state.cards[sys.argv[3]]
if sys.argv[4]=='successor':
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'exile'})
    act(s,'p1',type='move',card_ids=[source.id],to={'player':'p1','zone':'graveyard'})
settle(s)
if s.state.rules.decision is not None: choose(s,['yes'])
assert source.zone==('p1:battlefield' if sys.argv[4]=='yes' else 'p1:graveyard')
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, mode],
                            cwd=Path(app.__file__).resolve().parents[1], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_paid_cast_death_then_next_upkeep_return(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority

    s, source = setup(cards, zone='hand')
    wait_priority(s, 'p1')
    mana(s, C=1, B=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[], targets=[])
    settle(s)
    assert source.zone == 'p1:battlefield'
    bolt = put(s, 'Lightning Bolt', 'hand')
    wait_priority(s, 'p1')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, sources=[], targets=[source.id])
    settle(s)
    assert source.zone == 'p1:graveyard'
    to_phase(s, 'upkeep', turn=7)
    settle(s)
    choose(s, ['yes'])
    assert source.zone == 'p1:battlefield'
    roundtrip(s)
