"""Untargeted least-stat native upkeep choices use current complete characteristics."""
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

NAME = 'Drop of Honey'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_extreme_choices57_cards.json').read_text())
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




def setup(cards, name=NAME, board=(('Ornithopter', 'p2'), ('Giant Spider', 'p1'))):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    creatures = [put(s, n, 'battlefield', p) for n, p in board]
    pool = {'G': 1} if name == NAME else {'W': 1} if name == 'Porphyry Nodes' else {'C': 5}
    source = cast(s, name, pool)
    return s, source, creatures


def pending(cards, name=NAME, board=(('Ornithopter', 'p2'), ('Giant Spider', 'p1'))):
    s, source, creatures = setup(cards, name, board)
    to_phase(s, 'upkeep', turn=7)
    return s, source, creatures


@pytest.mark.parametrize('name', [NAME, 'Porphyry Nodes', 'Purging Scythe'])
def test_complete_canonicals(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', [NAME, 'Porphyry Nodes', 'Purging Scythe'])
def test_native_global_untargeted_unique_minimum(cards, name):
    s, source, (small, big) = pending(cards, name)
    settle(s)
    assert small.zone == 'p2:graveyard' and big.zone == 'p1:battlefield'
    assert source.zone == 'p1:battlefield' and all(p.life == 40 for p in s.state.players.values())
    roundtrip(s)


@pytest.mark.parametrize('name', [NAME, 'Porphyry Nodes'])
def test_native_empty_board_state_sacrifices_enchantment(cards, name):
    s, source, _ = setup(cards, name, ())
    assert source.zone == 'p1:graveyard'
    roundtrip(s)


def test_native_empty_board_scythe_has_no_choice_or_damage(cards):
    s, source, _ = pending(cards, 'Purging Scythe', ())
    settle(s)
    assert source.zone == 'p1:battlefield' and s.state.rules.decision is None
    assert all(p.life == 40 for p in s.state.players.values())
    roundtrip(s)


@pytest.mark.parametrize('name', [NAME, 'Porphyry Nodes', 'Purging Scythe'])
def test_native_ties_choose_at_resolution_from_all_players(cards, name):
    board = (('Ornithopter', 'p2'), ('Grizzly Bears', 'p1')) if name == 'Purging Scythe' else (
        ('Grizzly Bears', 'p2'), ('Giant Spider', 'p1'))
    s, source, (other, selected) = pending(cards, name, board)
    assert s.state.rules.decision is None
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1' and {o.card_id for o in d.options} == {other.id, selected.id}
    act(s, 'p1', type='choose', decision_id=d.id,
        option_ids=[next(o.id for o in d.options if o.card_id == selected.id)])
    settle(s)
    assert selected.zone == 'p1:graveyard' and other.zone == 'p2:battlefield'
    assert source.zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name', [NAME, 'Porphyry Nodes'])
@pytest.mark.parametrize('tied', [False, True])
def test_native_indestructible_excluded_from_choice_but_included_in_minimum(cards, name, tied):
    board = (('Darksteel Myr', 'p2'), ('Ornithopter' if tied else 'Giant Spider', 'p1'))
    s, source, (myr, other) = pending(cards, name, board)
    settle(s)
    assert myr.zone == 'p2:battlefield' and other.zone == ('p1:graveyard' if tied else 'p1:battlefield')
    assert s.state.rules.decision is None and source.zone == 'p1:battlefield'
    roundtrip(s)


def test_native_scythe_damages_indestructible_actual_least_toughness(cards):
    s, source, (myr, other) = pending(cards, 'Purging Scythe', (('Darksteel Myr', 'p2'), ('Ornithopter', 'p1')))
    settle(s)
    assert myr.zone == 'p2:battlefield' and myr.damage == 2
    assert other.zone == 'p1:battlefield' and not other.damage and source.zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name', [NAME, 'Porphyry Nodes', 'Purging Scythe'])
def test_native_final_pumped_stats_are_chosen_at_resolution(cards, name):
    s, source, (small, big) = pending(cards, name)
    cast(s, 'Giant Growth', {'G': 1}, [small.id])
    assert small.zone == 'p2:battlefield'
    if name == 'Purging Scythe':
        assert big.zone == 'p1:battlefield' and big.damage == 2 and not small.damage
    else:
        assert big.zone == 'p1:graveyard'
    assert source.zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name', [NAME, 'Porphyry Nodes'])
def test_native_choice_ignores_shroud(cards, name):
    s, source, (wall, spider) = pending(cards, name, (('Wall of Denial', 'p2'), ('Giant Spider', 'p1')))
    settle(s)
    assert wall.zone == 'p2:graveyard' and spider.zone == 'p1:battlefield' and source.zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name', [NAME, 'Porphyry Nodes'])
def test_native_destroy_cannot_use_existing_regeneration_shield(cards, name):
    from tests.test_rules_conditional_prevention import activate

    s, source, (boa,) = pending(cards, name, (('River Boa', 'p1'),))
    activate(s, boa, 'Regenerate')
    assert boa.zone == 'p1:graveyard' and source.zone == 'p1:graveyard'
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('name', [NAME, 'Porphyry Nodes'])
def test_native_empty_state_old_trigger_cannot_sacrifice_blinked_successor(cards, name):
    from tests.test_rules_counter_event_comparisons50 import resolve_only

    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = cast(s, name, {'G': 1} if name == NAME else {'W': 1}, resolve=False)
    resolve_only(s, source)
    assert source.zone == 'p1:battlefield' and s.state.zones['stack']
    old = s.state.rules.object_id(source.id)
    spell = cast(s, 'Raise the Alarm', {'C': 1, 'W': 1}, resolve=False)
    resolve_only(s, spell)
    spell = cast(s, 'Flicker of Fate', {'C': 1, 'W': 1}, [source.id], resolve=False)
    resolve_only(s, spell)
    settle(s)
    assert s.state.rules.object_id(source.id) != old and source.zone == 'p1:battlefield'
    assert len([c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield']) == 2
    roundtrip(s)


@pytest.mark.parametrize('name', [NAME, 'Porphyry Nodes', 'Purging Scythe'])
def test_true_cold_native_least_choice_resolution(cards, tmp_path, name):
    import subprocess
    import sys

    board = (('Ornithopter', 'p2'), ('Grizzly Bears', 'p1')) if name == 'Purging Scythe' else (
        ('Grizzly Bears', 'p2'), ('Giant Spider', 'p1'))
    s, source, (other, selected) = pending(cards, name, board)
    settle(s)
    assert s.state.rules.decision is not None
    saved = tmp_path / 'extreme57.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
assert d is not None and d.player=='p1'
act(s,'p1',type='choose',decision_id=d.id,option_ids=[next(o.id for o in d.options if o.card_id==sys.argv[3])])
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:graveyard'
assert s.state.cards[sys.argv[4]].zone=='p2:battlefield'
assert s.state.cards[sys.argv[5]].zone=='p1:battlefield'
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), selected.id, other.id, source.id],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('name', [NAME, 'Porphyry Nodes', 'Purging Scythe'])
def test_native_source_departure_does_not_cancel_least_stat_effect(cards, name):
    s, source, (small, big) = pending(cards, name)
    cast(s, 'Boomerang', {'U': 2}, [source.id])
    assert source.zone == 'p1:hand' and small.zone == 'p2:graveyard' and big.zone == 'p1:battlefield'
    roundtrip(s)


def test_native_scythe_lethal_damage_can_use_regeneration_shield(cards):
    from tests.test_rules_conditional_prevention import activate

    s, source, (boa,) = pending(cards, 'Purging Scythe', (('River Boa', 'p1'),))
    activate(s, boa, 'Regenerate')
    assert boa.zone == 'p1:battlefield' and boa.tapped and not boa.damage
    assert source.zone == 'p1:battlefield' and not s.state.rules.regen_shields
    roundtrip(s)
