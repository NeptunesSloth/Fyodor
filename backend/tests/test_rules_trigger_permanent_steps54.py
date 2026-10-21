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

NAMES = ['Mask of Intolerance','Zealots en-Dal']
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_permanent_steps54_cards.json').read_text())


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
    names = [c['name'] for c in DATA] + ['Sol Ring','Grizzly Bears']
    s = table(cards, names, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = cast(s, name, {'C': 2} if name == NAMES[0] else {'C': 3,'W': 1})
    assert source.zone == 'p1:battlefield'
    return s, source


@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('lands,hit', [(['Swamp','Mountain','Island','Forest'],True),(['Badlands','Tropical Island'],True),(['Badlands','Bayou'],False),(['Swamp','Mountain','Island','Wastes'],False)])
def test_mask_distinct_basic_types_not_land_count_or_basic_supertype(cards, lands, hit):
    s, _ = setup(cards, NAMES[0])
    for name in lands:
        put(s, name, 'battlefield', 'p2')
    to_phase(s, 'upkeep', turn=5)
    settle(s)
    assert s.state.players['p2'].life == 40-3*int(hit)
    assert s.state.players['p1'].life == 40
    roundtrip(s)


def test_mask_only_step_players_controlled_lands_count(cards):
    s, source = setup(cards, NAMES[0])
    put(s, 'Badlands', 'battlefield')
    put(s, 'Tropical Island', 'battlefield')
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
    to_phase(s, 'upkeep', turn=5)
    settle(s)
    assert all(p.life == 40 for p in s.state.players.values())
    to_phase(s, 'upkeep', turn=7)
    settle(s)
    assert s.state.players['p1'].life == 37 and s.state.players['p2'].life == 40
    roundtrip(s)


def test_mask_rechecks_original_step_player_domain_at_resolution(cards):
    s, _ = setup(cards, NAMES[0])
    put(s, 'Badlands', 'battlefield', 'p2')
    tropical = put(s, 'Tropical Island', 'battlefield', 'p2')
    to_phase(s, 'upkeep', turn=5)
    cast(s, 'Boomerang', {'U': 2}, [tropical.id])
    assert tropical.zone == 'p2:hand' and s.state.players['p2'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('extra,hit', [('Watchwolf',True),('Dryad Arbor',True),('Seat of the Synod',True),('Sol Ring',False),('Grizzly Bears',False)])
def test_zealots_all_nonland_permanents_white_includes_multicolor_and_ignores_lands(cards, extra, hit):
    s, _ = setup(cards, NAMES[1])
    put(s, extra, 'battlefield')
    to_phase(s, 'upkeep', turn=7)
    settle(s)
    assert s.state.players['p1'].life == 40+int(hit)
    roundtrip(s)


def test_zealots_native_nonwhite_token_response_prevents_life_gain(cards):
    s, _ = setup(cards, NAMES[1])
    to_phase(s, 'upkeep', turn=7)
    cast(s, 'Sprout', {'G': 1})
    assert s.state.players['p1'].life == 40
    roundtrip(s)


def pending(cards, name):
    s, source = setup(cards, name)
    if name == NAMES[0]:
        put(s, 'Badlands', 'battlefield', 'p2')
        put(s, 'Tropical Island', 'battlefield', 'p2')
    to_phase(s, 'upkeep', turn=5 if name == NAMES[0] else 7)
    assert s.state.zones['stack']
    return s, source


@pytest.mark.parametrize('name', NAMES)
def test_condition_becoming_true_after_step_does_not_retroactively_trigger(cards, name):
    s, _ = setup(cards, name)
    if name == NAMES[0]:
        put(s, 'Badlands', 'battlefield', 'p2')
        put(s, 'Island', 'battlefield', 'p2')
        to_phase(s, 'upkeep', turn=5)
        settle(s)
        put(s, 'Forest', 'battlefield', 'p2')
    else:
        ring = put(s, 'Sol Ring', 'battlefield')
        to_phase(s, 'upkeep', turn=7)
        cast(s, 'Boomerang', {'U': 2}, [ring.id])
    settle(s)
    assert all(p.life == 40 for p in s.state.players.values())
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_pending_effect_survives_native_source_departure(cards, name):
    s, source = pending(cards, name)
    if name == NAMES[0]:
        cast(s, 'Boomerang', {'U': 2}, [source.id])
        assert source.zone == 'p1:hand' and s.state.players['p2'].life == 37
    else:
        cast(s, 'Murder', {'C': 1,'B': 2}, [source.id])
        assert source.zone == 'p1:graveyard' and s.state.players['p1'].life == 41
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_source_controller_change_keeps_original_trigger_players(cards, name):
    s, source = pending(cards, name)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
    settle(s)
    assert s.state.players['p1'].life == (40 if name == NAMES[0] else 41)
    assert s.state.players['p2'].life == (37 if name == NAMES[0] else 40)
    assert s.state.players['p3'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_true_cold_both_native_step_conditions(cards, tmp_path, name):
    import app

    s, source = pending(cards, name)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
    saved = tmp_path / 'permanent-steps.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
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
assert s.state.players['p1'].life==(40 if sys.argv[3]=='Mask of Intolerance' else 41)
assert s.state.players['p2'].life==(37 if sys.argv[3]=='Mask of Intolerance' else 40)
assert s.state.players['p3'].life==40
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), name],
                            capture_output=True, text=True, timeout=90, cwd=Path(app.__file__).resolve().parents[1])
    assert result.returncode == 0, result.stdout + result.stderr


def test_mask_single_land_with_all_basic_types_qualifies(cards):
    s, _ = setup(cards, NAMES[0])
    land = put(s, 'Forest', 'battlefield', 'p2')
    cast(s, "Nylea's Presence", {'C': 1,'G': 1}, [land.id])
    to_phase(s, 'upkeep', turn=5)
    settle(s)
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_mask_control_transfer_rechecks_original_step_player_not_new_land_controller(cards):
    s, _ = pending(cards, NAMES[0])
    put(s, 'Badlands', 'battlefield', 'p3')
    land = next(c for c in s.state.cards.values() if c.name == 'Tropical Island' and c.zone == 'p2:battlefield')
    act(s, 'p1', type='set_controller', card_ids=[land.id], player='p3')
    settle(s)
    assert all(p.life == 40 for p in s.state.players.values())
    roundtrip(s)
