"""Source-sensitive damage counters retain native current/LKI source identities and damage quantities."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

TALON = 'Talon of Pain'
NIGHT = 'Night Dealings'
DATA = json.loads((Path(__file__).parent / 'fixtures/source_damage_counters50_cards.json').read_text())
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
    source = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='cast_spell', card_id=source.id, sources=[], targets=list(targets))
    if resolve:
        settle(s)
    return source


def setup(cards, name):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    source = cast(s, name, {'C': 4} if name == TALON else {'C': 2, 'B': 2})
    assert source.zone == 'p1:battlefield' and not s.state.players['p1'].mana
    return s, source


def count(source):
    return source.counters.get('charge' if source.name == TALON else 'theft', 0)


@pytest.mark.parametrize('name', [TALON, NIGHT])
def test_complete_canonical_supported(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name,expected', [(TALON, 1), (NIGHT, 3)])
def test_native_spell_damage_from_source_that_left_stack(cards, name, expected):
    s, source = setup(cards, name)
    bolt = cast(s, 'Lightning Bolt', {'R': 1}, ['p2'])
    assert bolt.zone == 'p1:graveyard' and count(source) == expected
    assert s.state.players['p2'].life == 37
    roundtrip(s)


@pytest.mark.parametrize('name,expected', [(TALON, 2), (NIGHT, 8)])
def test_one_simultaneous_instruction_counts_each_other_player_not_self(cards, name, expected):
    s, source = setup(cards, name)
    cast(s, 'Flame Rift', {'C': 1, 'R': 1})
    assert all(p.life == 36 for p in s.state.players.values())
    assert count(source) == expected
    roundtrip(s)


@pytest.mark.parametrize('name', [TALON, NIGHT])
def test_self_recipient_creature_recipient_and_opponent_source_do_not_trigger(cards, name):
    s, source = setup(cards, name)
    cast(s, 'Lightning Bolt', {'R': 1}, ['p1'])
    cast(s, 'Lightning Bolt', {'R': 1}, ['p3'], pid='p2')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Pyroclasm', {'C': 1, 'R': 1})
    assert not count(source)
    roundtrip(s)


def test_talon_paid_native_activation_damages_without_triggering_itself(cards):
    s, source = setup(cards, TALON)
    cast(s, 'Flame Rift', {'C': 1, 'R': 1})
    assert count(source) == 2
    wait_priority(s, 'p1')
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[], x_value=2, targets=['p2'])
    assert source.tapped and not source.counters and not s.state.players['p1'].mana
    settle(s)
    assert source.counters == {} and s.state.players['p2'].life == 34
    roundtrip(s)


def test_night_native_paid_counter_cost_search_reveals_exact_nonland_mana_value(cards):
    s, source = setup(cards, NIGHT)
    cast(s, 'Lightning Bolt', {'R': 1}, ['p2'])
    wait_priority(s, 'p1')
    mana(s, C=2, B=2)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[], x_value=3)
    assert not source.counters and not s.state.players['p1'].mana
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    divination = next(c for c in s.state.cards.values() if c.name == 'Divination' and c.zone == 'p1:library')
    assert divination.id in {o.id for o in d.options}
    assert not any(c.name == 'Forest' for c in s.state.cards.values() if c.id in {o.id for o in d.options})
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[divination.id])
    settle(s)
    assert divination.zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('name', [TALON, NIGHT])
def test_counter_cost_cannot_be_paid_without_required_counters(cards, name):
    s, source = setup(cards, name)
    mana(s, **({'C': 2} if name == TALON else {'C': 2, 'B': 2}))
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[], x_value=2,
            **({'targets': ['p2']} if name == TALON else {}))
    assert s.state.model_dump_json() == before
    roundtrip(s)


@pytest.mark.parametrize('name,expected', [(TALON, 1), (NIGHT, 2)])
@pytest.mark.parametrize('prevented', [False, True])
def test_native_creature_combat_and_prevented_damage(cards, name, expected, prevented):
    from tests.test_rules_conditional_prevention import attack
    from tests.test_rules_wave30m_durations import to_phase

    s, source = setup(cards, name)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    attack(s, [bear], turn=7)
    if prevented:
        cast(s, 'Fog', {'G': 1}, pid='p2')
    to_phase(s, 'end_combat')
    settle(s)
    assert count(source) == (0 if prevented else expected)
    assert s.state.players['p2'].life == (40 if prevented else 38)
    roundtrip(s)


@pytest.mark.parametrize('name,n', [(TALON, 1), (NIGHT, 3)])
@pytest.mark.parametrize('replacement,multiplier', [('Doubling Season', 2), ('Solemnity', 0)])
def test_native_counter_replacement_or_prohibition(cards, name, n, replacement, multiplier):
    s, source = setup(cards, name)
    put(s, replacement, 'battlefield')
    cast(s, 'Lightning Bolt', {'R': 1}, ['p2'])
    assert count(source) == n * multiplier and s.state.players['p2'].life == 37
    roundtrip(s)


def pending_damage(cards, name):
    from tests.test_rules_counter_event_comparisons50 import resolve_only

    s, source = setup(cards, name)
    spell = cast(s, 'Lightning Bolt', {'R': 1}, ['p2'], resolve=False)
    resolve_only(s, spell)
    assert spell.zone == 'p1:graveyard' and s.state.zones['stack']
    return s, source


@pytest.mark.parametrize('name', [TALON, NIGHT])
def test_native_blinked_successor_does_not_receive_original_trigger_counters(cards, name):
    s, source = pending_damage(cards, name)
    old = s.state.rules.object_id(source.id)
    if name == TALON:
        wait_priority(s, 'p1')
        flicker = put(s, 'Ghostly Flicker', 'hand')
        land = put(s, 'Forest', 'battlefield')
        mana(s, C=2, U=1)
        act(s, 'p1', type='cast_spell', card_id=flicker.id, sources=[], targets=[source.id, land.id], target_counts=[2])
        settle(s)
    else:
        cast(s, 'Flicker of Fate', {'C': 1, 'W': 1}, [source.id])
    assert s.state.rules.object_id(source.id) != old and not source.counters
    roundtrip(s)


@pytest.mark.parametrize('name,n', [(TALON, 1), (NIGHT, 3)])
def test_pending_trigger_keeps_ability_controller_after_source_control_changes(cards, name, n):
    s, source = pending_damage(cards, name)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    settle(s)
    assert source.controller == 'p2' and count(source) == n
    roundtrip(s)


@pytest.mark.parametrize('mode', ['talon_trigger', 'night_trigger', 'talon_activation', 'night_search'])
def test_true_cold_native_damage_context_and_paid_counter_costs(cards, tmp_path, mode):
    import subprocess
    import sys

    if mode.endswith('trigger'):
        s, source = pending_damage(cards, TALON if mode.startswith('talon') else NIGHT)
    elif mode == 'talon_activation':
        s, source = setup(cards, TALON)
        cast(s, 'Flame Rift', {'C': 1, 'R': 1})
        wait_priority(s, 'p1')
        mana(s, C=2)
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[], x_value=2, targets=['p2'])
        assert source.tapped and not source.counters and not s.state.players['p1'].mana
    else:
        s, source = setup(cards, NIGHT)
        cast(s, 'Lightning Bolt', {'R': 1}, ['p2'])
        wait_priority(s, 'p1')
        mana(s, C=2, B=2)
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[], x_value=3)
        settle(s)
        assert s.state.rules.decision is not None and not source.counters
    saved = tmp_path / 'source50.json'
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
from tests.game_helpers import act
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source=s.state.cards[sys.argv[3]]
mode=sys.argv[4]
if mode=='night_search':
 d=s.state.rules.decision
 assert d is not None and d.player=='p1'
 card=next(c for c in s.state.cards.values() if c.name=='Divination' and c.zone=='p1:library')
 act(s,'p1',type='choose',decision_id=d.id,option_ids=[card.id])
 settle(s)
 assert card.zone=='p1:hand' and not source.counters
elif mode=='talon_activation':
 assert s.state.zones['stack'] and source.tapped and not source.counters
 settle(s)
 assert not source.counters and s.state.players['p2'].life==34
else:
 assert s.state.zones['stack']
 settle(s)
 assert source.counters==({'charge':1} if mode=='talon_trigger' else {'theft':3})
assert not s.state.players['p1'].mana
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, mode],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('name,n', [(TALON, 1), (NIGHT, 3)])
@pytest.mark.parametrize('matching', [False, True])
def test_actual_spell_controller_not_owner_or_caster_determines_source_scope(cards, name, n, matching):
    s, source = setup(cards, name)
    if matching:
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    spell = cast(s, 'Lightning Bolt', {'R': 1}, ['p2'], resolve=False)
    assert spell.owner == 'p1' and spell.controller == 'p1'
    act(s, 'p1', type='set_controller', card_ids=[spell.id], player='p3')
    assert s.state.rules.stack[spell.id].controller == 'p3'
    settle(s)
    assert spell.zone == 'p1:graveyard' and s.state.players['p2'].life == 37
    assert count(source) == (n if matching else 0)
    roundtrip(s)
