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
from tests.test_rules_trigger_library_win53 import cast
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Contested Game Ball'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_attacking_player65_cards.json').read_text())


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


NAMES = [c['name'] for c in DATA] + ['Island'] * 12


def setup(cards):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = cast(s, NAME, {'C': 2})
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=True)
    return s, source


def damage_pending(cards, *, multiple=False, target='p1', fog=False):
    s, source = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attackers = [bear]
    if multiple:
        attackers.append(put(s, 'Hill Giant', 'battlefield', 'p2'))
    to_phase(s, 'declare_attackers', turn=5)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': c.id, 'target': target} for c in attackers])
    if fog:
        cast(s, 'Fog', {'G': 1})
    to_phase(s, 'combat_damage', turn=5)
    return s, source, attackers


def test_whole_canonical(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('multiple', [False, True])
def test_native_combat_damage_gives_one_trigger_to_frozen_attacking_player(cards, multiple):
    s, source, attackers = damage_pending(cards, multiple=multiple)
    assert s.state.players['p1'].life == (35 if multiple else 38)
    entries = [e for e in s.state.rules.stack.values() if e.kind == 'trigger' and e.source_card == source.id]
    assert len(entries) == 1 and entries[0].event.attacking_player == 'p2'
    assert source.zone == 'p1:battlefield' and source.tapped
    settle(s)
    assert source.zone == 'p2:battlefield' and source.owner == 'p1' and not source.tapped
    roundtrip(s)


@pytest.mark.parametrize('mode', ['fog', 'other_defender', 'noncombat'])
def test_native_combat_recipient_and_prevention_boundaries(cards, mode):
    if mode == 'noncombat':
        s, source = setup(cards)
        cast(s, 'Lightning Bolt', {'R': 1}, ['p1'])
    else:
        s, source, attackers = damage_pending(cards, target='p3' if mode == 'other_defender' else 'p1', fog=mode == 'fog')
        settle(s)
    assert source.zone == 'p1:battlefield' and source.tapped
    roundtrip(s)


@pytest.mark.parametrize('mode', ['attacker_control', 'ball_control', 'source_departure'])
def test_native_pending_trigger_uses_frozen_attacker_and_original_source(cards, mode):
    s, source, attackers = damage_pending(cards)
    if mode == 'attacker_control':
        act(s, 'p1', type='set_controller', card_ids=[attackers[0].id], player='p3')
    elif mode == 'ball_control':
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
    else:
        cast(s, 'Disenchant', {'C': 1, 'W': 1}, [source.id])
    settle(s)
    assert source.zone == ('p1:graveyard' if mode == 'source_departure' else 'p2:battlefield')
    if mode != 'source_departure':
        assert not source.tapped
    roundtrip(s)


def test_native_attacking_player_departure_before_resolution_does_not_untap_ball(cards):
    s, source, attackers = damage_pending(cards)
    act(s, 'p2', type='concede')
    settle(s)
    assert source.zone == 'p1:battlefield' and source.tapped
    roundtrip(s)


def test_native_resolved_borrowed_ball_control_survives_original_ability_controller_departure(cards):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = put(s, NAME, 'battlefield', 'p3')
    act(s, 'p3', type='set_controller', card_ids=[source.id], player='p1')
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=True)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'declare_attackers', turn=5)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p1'}])
    to_phase(s, 'combat_damage', turn=5)
    settle(s)
    assert source.owner == 'p3' and source.zone == 'p2:battlefield'
    act(s, 'p1', type='concede')
    settle(s)
    assert source.zone == 'p2:battlefield'
    roundtrip(s)


def test_native_paid_activation_draws_counts_then_fifth_sacrifices_for_treasure(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority

    s, source = setup(cards)
    for i in range(5):
        if source.tapped:
            act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
        wait_priority(s, 'p1')
        mana(s, C=2)
        before = len(s.state.zones['p1:hand'])
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[], targets=[])
        settle(s)
        assert len(s.state.zones['p1:hand']) == before + 1
        if i < 4:
            assert source.zone == 'p1:battlefield' and source.counters.get('point') == i + 1
    assert source.zone == 'p1:graveyard'
    assert sum(c.is_token and c.name == 'Treasure' and c.zone == 'p1:battlefield' for c in s.state.cards.values()) == 1
    roundtrip(s)
