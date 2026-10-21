"""Printed non-target cast counters preserve the original spell and independent instructions."""
from __future__ import annotations

import json
import subprocess
import sys
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

NAMES = ['Lunar Force', 'Hesitation', 'Presence of the Master']
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_cast_counters50_cards.json').read_text())


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


def cast(s, name, pool, targets=(), pid='p1', resolve=True):
    wait_priority(s, pid)
    spell = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='cast_spell', card_id=spell.id, sources=[], targets=list(targets))
    if resolve:
        settle(s)
    return spell


def setup(cards, name):
    names = [c['name'] for c in DATA] + ['Grizzly Bears', 'Sol Ring', 'Counterspell', 'Boomerang', 'Pacifism', 'Lightning Bolt']
    s = table(cards, names, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = cast(s, name, {'C': 3, 'U': 1, 'W': 1})
    assert source.zone == 'p1:battlefield'
    return s, source


@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', NAMES[:2])
@pytest.mark.parametrize('pid', ['p1', 'p2', 'p3'])
def test_real_paid_cast_scope_and_sacrifice(cards, name, pid):
    s, source = setup(cards, name)
    if pid != 'p1':
        to_phase(s, 'main1', turn=5 if pid == 'p2' else 6)
    spell = cast(s, 'Sol Ring', {'C': 1}, pid=pid)
    triggers = name == 'Hesitation' or pid != 'p1'
    assert spell.zone == f'{pid}:' + ('graveyard' if triggers else 'battlefield')
    assert source.zone == 'p1:' + ('graveyard' if triggers else 'battlefield')
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES[:2])
def test_uncounterable_spell_still_requires_sacrifice_and_resolves(cards, name):
    s, source = setup(cards, name)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=5)
    verdict = cast(s, 'Supreme Verdict', {'C': 1, 'W': 2, 'U': 1}, pid='p2')
    assert source.zone == 'p1:graveyard' and verdict.zone == 'p2:graveyard'
    assert bear.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name', ['Lunar Force'])
def test_source_removed_before_trigger_resolution_still_counters(cards, name):
    s, source = setup(cards, name)
    to_phase(s, 'main1', turn=5)
    spell = cast(s, 'Sol Ring', {'C': 1}, pid='p2', resolve=False)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    cast(s, 'Boomerang', {'U': 2}, [source.id])
    assert source.zone == 'p1:hand' and spell.zone == 'p2:graveyard'
    roundtrip(s)


def test_lunar_sacrifices_even_after_original_spell_already_countered(cards):
    s, source = setup(cards, 'Lunar Force')
    to_phase(s, 'main1', turn=5)
    spell = cast(s, 'Sol Ring', {'C': 1}, pid='p2', resolve=False)
    cast(s, 'Counterspell', {'U': 2}, [spell.id])
    assert spell.zone == 'p2:graveyard' and source.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('pid', ['p1', 'p2', 'p3'])
def test_presence_enchantments_are_countered_without_target_choice(cards, pid):
    s, source = setup(cards, 'Presence of the Master')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    if pid != 'p1':
        to_phase(s, 'main1', turn=5 if pid == 'p2' else 6)
    spell = cast(s, 'Pacifism', {'C': 1, 'W': 1}, [bear.id], pid=pid)
    assert spell.zone == f'{pid}:graveyard' and source.zone == 'p1:battlefield'
    assert not bear.attached_to
    roundtrip(s)


def test_presence_ignores_non_enchantment_spells_and_noncast_entry(cards):
    s, source = setup(cards, 'Presence of the Master')
    spell = cast(s, 'Sol Ring', {'C': 1})
    enchantment = put(s, 'Hesitation', 'battlefield', 'p2')
    settle(s)
    assert spell.zone == 'p1:battlefield' and enchantment.zone == 'p2:battlefield'
    assert source.zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_true_cold_original_spell_counter_reference(cards, tmp_path, name):
    s, source = setup(cards, name)
    to_phase(s, 'main1', turn=5)
    if name == 'Presence of the Master':
        bear = put(s, 'Grizzly Bears', 'battlefield')
        spell = cast(s, 'Pacifism', {'C': 1, 'W': 1}, [bear.id], pid='p2', resolve=False)
    else:
        spell = cast(s, 'Sol Ring', {'C': 1}, pid='p2', resolve=False)
    saved = tmp_path / 'cast-counter.json'
    saved.write_text(s.state.model_dump_json())
    code = '''
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
source=s.state.cards[sys.argv[3]]
spell=s.state.cards[sys.argv[4]]
assert s.state.zones['stack']
settle(s)
assert spell.zone=='p2:graveyard'
assert source.zone==('p1:battlefield' if source.name=='Presence of the Master' else 'p1:graveyard')
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, spell.id],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('name', NAMES[:2])
def test_trigger_counters_even_when_controller_can_no_longer_sacrifice(cards, name):
    s, source = setup(cards, name)
    to_phase(s, 'main1', turn=5)
    spell = cast(s, 'Sol Ring', {'C': 1}, pid='p2', resolve=False)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
    settle(s)
    assert source.zone == 'p3:battlefield' and source.controller == 'p3'
    assert spell.zone == 'p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES[:2])
def test_each_pending_trigger_retains_its_own_original_spell(cards, name):
    s, source = setup(cards, name)
    to_phase(s, 'main1', turn=5)
    first = cast(s, 'Sol Ring', {'C': 1}, pid='p2', resolve=False)
    second = cast(s, 'Lightning Bolt', {'R': 1}, ['p1'], pid='p3', resolve=False)
    settle(s)
    assert first.zone == 'p2:graveyard' and second.zone == 'p3:graveyard'
    assert source.zone == 'p1:graveyard' and s.state.players['p1'].life == 40
    roundtrip(s)
