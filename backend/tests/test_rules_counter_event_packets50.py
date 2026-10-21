"""Committed counter packets retain every kind, actual quantity, and counter putter."""
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

BOLD = 'Bold Plagiarist'
MARVEL = 'Captain Marvel, Apex Avenger'
DATA = json.loads((Path(__file__).parent / 'fixtures/counter_event_packets50_cards.json').read_text())
NAMES = [c['name'] for c in DATA] + ['Grizzly Bears', 'Murder']


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


def setup(cards, name=BOLD):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    source = put(s, name, 'hand')
    mana(s, C=3, B=1) if name == BOLD else mana(s, C=5, W=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    assert source.zone == 'p1:battlefield' and not s.state.players['p1'].mana
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2' if name == BOLD else 'p1')
    return s, source, bear


def gift(s, bear, pid='p2', resolve=True):
    wait_priority(s, pid)
    spell = put(s, 'Gift of the Viper', 'hand', pid)
    mana(s, pid=pid, G=1)
    act(s, pid, type='cast_spell', card_id=spell.id, sources=[], targets=[bear.id])
    if resolve:
        settle(s)
    else:
        resolve_only(s, spell)
    return spell


def accept(s, yes=True):
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes' if yes else 'no'])
    settle(s)


@pytest.mark.parametrize('name', [BOLD, MARVEL])
def test_complete_canonical_supported(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', [BOLD, MARVEL])
def test_native_paid_source_and_one_mixed_kind_instruction(cards, name):
    s, source, bear = setup(cards, name)
    gift(s, bear, 'p2' if name == BOLD else 'p1')
    if name == MARVEL:
        accept(s)
    expected = {'+1/+1': 1, 'reach': 1, 'deathtouch': 1}
    assert source.counters == bear.counters == expected
    assert not s.state.zones['stack']
    roundtrip(s)


def test_bold_copy_is_put_by_opponent_not_trigger_controller(cards):
    s, source, bear = setup(cards)
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield', 'p2')
    gift(s, bear)
    assert bear.counters == {'+1/+1': 2, 'reach': 2, 'deathtouch': 2}
    assert source.counters == {'+1/+1': 4, 'reach': 4, 'deathtouch': 4}
    roundtrip(s)


def test_optional_marvel_can_decline_all_kinds(cards):
    s, source, bear = setup(cards, MARVEL)
    gift(s, bear, 'p1')
    accept(s, False)
    assert not source.counters and len(bear.counters) == 3
    roundtrip(s)


def test_marvel_ignores_kree_at_counter_event(cards):
    s, source, bear = setup(cards, MARVEL)
    kree = put(s, 'Universal Automaton', 'battlefield')
    gift(s, kree, 'p1')
    assert not source.counters and s.state.rules.decision is None
    roundtrip(s)


def test_marvel_rechecks_event_creature_is_not_kree_on_resolution(cards):
    s, source, bear = setup(cards, MARVEL)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    gift(s, bear, 'p1', resolve=False)
    wait_priority(s, 'p1')
    wings = put(s, 'Wings of Velis Vel', 'hand')
    mana(s, C=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=wings.id, sources=[], targets=[bear.id])
    settle(s)
    assert s.state.rules.decision is None and not source.counters
    roundtrip(s)


@pytest.mark.parametrize('name', [BOLD, MARVEL])
def test_counter_packet_survives_removal_of_triggering_counters(cards, name):
    s, source, bear = setup(cards, name)
    gift(s, bear, 'p2' if name == BOLD else 'p1', resolve=False)
    for kind in list(bear.counters):
        act(s, 'p1', type='counter', card_ids=[bear.id], kind=kind, delta=-1)
    settle(s)
    if name == MARVEL:
        accept(s)
    assert source.counters == {'+1/+1': 1, 'reach': 1, 'deathtouch': 1}
    assert not bear.counters
    roundtrip(s)


def test_prohibited_counter_instruction_produces_no_packet_trigger(cards):
    s, source, bear = setup(cards)
    put(s, 'Solemnity', 'battlefield')
    gift(s, bear)
    assert not source.counters and not bear.counters
    assert not s.state.zones['stack'] and s.state.rules.decision is None
    roundtrip(s)


def test_counter_copy_does_not_trigger_opponents_plagiarist(cards):
    s, source, bear = setup(cards)
    opposite = put(s, BOLD, 'battlefield', 'p2')
    gift(s, bear)
    assert source.counters == bear.counters == {'+1/+1': 1, 'reach': 1, 'deathtouch': 1}
    assert not opposite.counters and not s.state.zones['stack']
    roundtrip(s)


@pytest.mark.parametrize('name', [BOLD, MARVEL])
def test_true_cold_mixed_counter_packet_uses_recorded_counts_not_board(cards, tmp_path, name):
    import subprocess
    import sys

    s, source, bear = setup(cards, name)
    gift(s, bear, 'p2' if name == BOLD else 'p1', resolve=False)
    for kind in list(bear.counters):
        act(s, 'p1', type='counter', card_ids=[bear.id], kind=kind, delta=-1)
    saved = tmp_path / 'packet50.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_counter_event_packets50 import accept,MARVEL
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert s.state.zones['stack']
settle(s)
if sys.argv[5]==MARVEL:
 accept(s)
assert s.state.cards[sys.argv[3]].counters=={'+1/+1':1,'reach':1,'deathtouch':1}
assert not s.state.cards[sys.argv[4]].counters
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, bear.id, name],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('name', [BOLD, MARVEL])
def test_wrong_counter_actor_or_creature_controller_does_not_trigger(cards, name):
    s, source, bear = setup(cards, name)
    if name == BOLD:
        bear = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    gift(s, bear, 'p2')
    assert not source.counters and s.state.rules.decision is None
    roundtrip(s)


def test_marvel_own_counters_do_not_recur(cards):
    s, source, bear = setup(cards, MARVEL)
    gift(s, source, 'p1')
    assert source.counters == {'+1/+1': 1, 'reach': 1, 'deathtouch': 1}
    assert not s.state.zones['stack'] and s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('name', [BOLD, MARVEL])
def test_blinked_source_successor_does_not_receive_old_packet(cards, name):
    s, source, bear = setup(cards, name)
    gift(s, bear, 'p2' if name == BOLD else 'p1', resolve=False)
    old = s.state.rules.object_id(source.id)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    assert s.state.rules.object_id(source.id) != old
    settle(s)
    if name == MARVEL:
        accept(s)
    assert not source.counters
    roundtrip(s)


@pytest.mark.parametrize('name,original,copied', [(BOLD, 1, 2), (MARVEL, 2, 4)])
def test_native_replacements_apply_to_original_and_copied_instruction(cards, name, original, copied):
    s, source, bear = setup(cards, name)
    put(s, 'Doubling Season', 'battlefield')
    gift(s, bear, 'p2' if name == BOLD else 'p1')
    if name == MARVEL:
        accept(s)
    assert bear.counters == {k: original for k in ['+1/+1', 'reach', 'deathtouch']}
    assert source.counters == {k: copied for k in ['+1/+1', 'reach', 'deathtouch']}
    roundtrip(s)


def test_native_marvel_indestructible_flying_and_double_strike(cards):
    from app.game.errors import ActionError
    from tests.test_rules_conditional_prevention import attack, damage
    from tests.test_rules_wave30m_durations import to_phase

    s, source, bear = setup(cards, MARVEL)
    wait_priority(s, 'p2')
    murder = put(s, 'Murder', 'hand', 'p2')
    mana(s, pid='p2', C=1, B=2)
    act(s, 'p2', type='cast_spell', card_id=murder.id, sources=[], targets=[source.id])
    settle(s)
    assert murder.zone == 'p2:graveyard' and source.zone == 'p1:battlefield'
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attack(s, [source], turn=7)
    to_phase(s, 'declare_blockers')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': source.id}])
    assert s.state.model_dump_json() == before
    act(s, 'p2', type='declare_blockers', blocks=[])
    damage(s)
    settle(s)
    to_phase(s, 'end_combat')
    assert s.state.players['p2'].life == 32
    roundtrip(s)


def test_native_bold_flash_allows_opponents_upkeep_cast(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    to_phase(s, 'upkeep', turn=5)
    wait_priority(s, 'p1')
    source = put(s, BOLD, 'hand')
    mana(s, C=3, B=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    assert source.zone == 'p1:battlefield' and not s.state.players['p1'].mana
    roundtrip(s)


def test_additional_native_trigger_each_receives_complete_packet_once(cards):
    s, source, bear = setup(cards)
    put(s, 'Delney, Streetwise Lookout', 'battlefield')
    gift(s, bear, resolve=False)
    assert len(s.state.zones['stack']) == 2
    settle(s)
    assert source.counters == {'+1/+1': 2, 'reach': 2, 'deathtouch': 2}
    assert bear.counters == {'+1/+1': 1, 'reach': 1, 'deathtouch': 1}
    roundtrip(s)


def test_actual_vantress_trigger_copy_retains_packet_without_mutating_original(cards):
    s, source, bear = setup(cards)
    gift(s, bear, resolve=False)
    original = s.state.zones['stack'][0]
    wait_priority(s, 'p1')
    spell = put(s, 'Virtue of Knowledge // Vantress Visions', 'hand')
    mana(s, C=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, face=1, targets=[original], sources=[])
    settle(s)
    assert source.counters == {'+1/+1': 2, 'reach': 2, 'deathtouch': 2}
    assert bear.counters == {'+1/+1': 1, 'reach': 1, 'deathtouch': 1}
    roundtrip(s)


@pytest.mark.parametrize('name', [BOLD, MARVEL])
def test_old_save_with_no_counter_packet_does_not_infer_from_current_board(cards, name):
    from app.game.state import GameState

    s, source, bear = setup(cards, name)
    gift(s, bear, 'p2' if name == BOLD else 'p1', resolve=False)
    saved = s.state.model_dump(mode='json')

    def strip_packets(value):
        if isinstance(value, dict):
            value.pop('counter_placements', None)
            for child in value.values():
                strip_packets(child)
        elif isinstance(value, list):
            for child in value:
                strip_packets(child)

    strip_packets(saved)
    s.state = GameState.model_validate(saved)
    settle(s)
    if name == MARVEL:
        accept(s)
    assert not s.state.cards[source.id].counters
    assert s.state.cards[bear.id].counters == {'+1/+1': 1, 'reach': 1, 'deathtouch': 1}


@pytest.mark.parametrize('name', [BOLD, MARVEL])
def test_same_instruction_on_two_creatures_keeps_two_separate_packets(cards, name):
    s, source, bear = setup(cards, name)
    actor = 'p2' if name == BOLD else 'p1'
    second = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    act(s, 'p1', type='set_controller', card_ids=[second.id], player=actor)
    from tests.test_rules_wave30m_durations import to_phase

    if actor == 'p2':
        to_phase(s, 'main1', turn=5)
    wait_priority(s, actor)
    spell = put(s, 'Strength of the Pack', 'hand', actor)
    mana(s, pid=actor, C=4, G=2)
    act(s, actor, type='cast_spell', card_id=spell.id, sources=[])
    resolve_only(s, spell)
    assert len(s.state.zones['stack']) == 2
    settle(s)
    if name == MARVEL:
        accept(s)
        accept(s)
    assert source.counters == {'+1/+1': 4 if name == BOLD else 6}
    assert bear.counters == second.counters == {'+1/+1': 2}
    roundtrip(s)
