"""Native mandatory sacrifice success gates effects on the entering object."""
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

NAME = 'Grave Peril'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_sacrifice_entered58_cards.json').read_text())
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


def cast(s, name, pool, targets=(), *, pid='p1', resolve=True):
    wait_priority(s, pid)
    c = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='cast_spell', card_id=c.id, sources=[], targets=list(targets))
    if resolve:
        settle(s)
    return c




def setup(cards, name=NAME):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = cast(s, name, {'C': 1, 'B': 1} if name == NAME else {'C': 3, 'R': 1})
    assert source.zone == 'p1:battlefield' and not s.state.zones['stack']
    return s, source


def entered_pending(cards, name=NAME, creature='Grizzly Bears', pid='p1'):
    from tests.test_rules_counter_event_comparisons50 import resolve_only

    s, source = setup(cards, name)
    if pid != 'p1':
        to_phase(s, 'main1', turn=5)
    pool = {'C': 1, 'G': 1} if creature == 'Grizzly Bears' else {'B': 2} if creature == 'Black Knight' else {'C': 6, 'U': 1}
    entered = cast(s, creature, pool, pid=pid, resolve=False)
    resolve_only(s, entered)
    return s, source, entered


@pytest.mark.parametrize('name', [NAME, 'Flame-Kin War Scout'])
def test_whole_canonicals(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', [NAME, 'Flame-Kin War Scout'])
@pytest.mark.parametrize('pid', ['p1', 'p2'])
def test_native_mandatory_sacrifice_affects_original_entering_creature(cards, name, pid):
    s, source = setup(cards, name)
    if pid == 'p2':
        to_phase(s, 'main1', turn=5)
    bear = cast(s, 'Grizzly Bears', {'C': 1, 'G': 1}, pid=pid)
    assert source.zone == 'p1:graveyard' and bear.zone == pid + ':graveyard'
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('name', [NAME, 'Flame-Kin War Scout'])
def test_native_nonblack_filter_is_only_for_grave_peril(cards, name):
    s, source = setup(cards, name)
    knight = cast(s, 'Black Knight', {'B': 2})
    expected = 'p1:battlefield' if name == NAME else 'p1:graveyard'
    assert source.zone == expected and knight.zone == expected
    roundtrip(s)


@pytest.mark.parametrize('name', [NAME, 'Flame-Kin War Scout'])
def test_native_ward_is_not_charged_for_untargeted_effect(cards, name):
    s, source, terror = entered_pending(cards, name, 'Tolarian Terror', pid='p2')
    settle(s)
    assert source.zone == 'p1:graveyard' and not s.state.players['p1'].mana
    assert s.state.rules.decision is None
    if name == NAME:
        assert terror.zone == 'p2:graveyard'
    else:
        assert terror.zone == 'p2:battlefield' and terror.damage == 4
    roundtrip(s)


@pytest.mark.parametrize('name', [NAME, 'Flame-Kin War Scout'])
@pytest.mark.parametrize('mode', ['bounce', 'control', 'blink'])
def test_native_sacrifice_failure_gates_followup_and_protects_successor(cards, name, mode):
    s, source, bear = entered_pending(cards, name)
    old = s.state.rules.object_id(source.id)
    if mode == 'control':
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
        settle(s)
        assert source.zone == 'p2:battlefield'
    elif mode == 'bounce':
        cast(s, 'Boomerang', {'U': 2}, [source.id])
        assert source.zone == 'p1:hand'
    else:
        cast(s, 'Flicker of Fate', {'C': 1, 'W': 1}, [source.id])
        assert source.zone == 'p1:battlefield' and s.state.rules.object_id(source.id) != old
    assert bear.zone == 'p1:battlefield' and not bear.damage
    roundtrip(s)


@pytest.mark.parametrize('name', [NAME, 'Flame-Kin War Scout'])
def test_native_two_creatures_entering_only_first_successful_sacrifice_has_effect(cards, name):
    s, source = setup(cards, name)
    cast(s, 'Raise the Alarm', {'C': 1, 'W': 1})
    soldiers = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield']
    assert source.zone == 'p1:graveyard' and len(soldiers) == 1 and soldiers[0].name == 'Soldier'
    roundtrip(s)


@pytest.mark.parametrize('name', [NAME, 'Flame-Kin War Scout'])
def test_true_cold_native_sacrifice_receipt_and_event_object(cards, tmp_path, name):
    import subprocess
    import sys

    s, source, bear = entered_pending(cards, name)
    saved = tmp_path / 'sacrifice58.json'
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
assert s.state.cards[sys.argv[3]].zone=='p1:graveyard'
assert s.state.cards[sys.argv[4]].zone=='p1:graveyard'
assert s.state.rules.decision is None
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, bear.id],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('name', [NAME, 'Flame-Kin War Scout'])
def test_native_departed_entering_creature_does_not_counter_untargeted_sacrifice(cards, name):
    s, source, bear = entered_pending(cards, name)
    cast(s, 'Lightning Bolt', {'R': 1}, [bear.id])
    assert bear.zone == 'p1:graveyard' and source.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name', [NAME, 'Flame-Kin War Scout'])
def test_native_exile_replacement_still_counts_as_successful_sacrifice(cards, name):
    s, source = setup(cards, name)
    cast(s, 'Rest in Peace', {'C': 1, 'W': 1})
    bear = cast(s, 'Grizzly Bears', {'C': 1, 'G': 1})
    assert source.zone == 'p1:exile' and bear.zone == 'p1:exile'
    assert s.state.rules.decision is None
    roundtrip(s)
