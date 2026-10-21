"""Canonical Kjeldoran Home Guard combat-condition collateral."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/kjeldoran_home_guard_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()





def setup(cards):
    s = table(cards, ['Kjeldoran Home Guard', 'Relentless Assault', 'Reconnaissance', 'Doubling Season'], ['Grizzly Bears'], ['Grizzly Bears'])
    source = put(s, 'Kjeldoran Home Guard', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    act(s, 'p1', type='next_turn', player='p1', force=True)
    return s, source


def deserters(s):
    return [c for c in s.state.cards.values() if c.zone == 'p1:battlefield' and c.token and c.token.name == 'Deserter']


def test_full_and_attack_adds_desertion_counter_and_correct_token(cards):
    from app.rules.plan import Plan
    from tests.test_rules_clockwork_counters import combat
    assert coverage.of_card_data(cards.resolve('Kjeldoran Home Guard')).level == 'FULL'
    s, source = setup(cards)
    combat(s, source)
    assert s.state.cards[source.id].counters.get('-0/-1') == 1
    tokens = deserters(s)
    assert len(tokens) == 1
    ch = Plan(s.state, 'p1', s.cards, None).ch(tokens[0])
    assert ch.pt == (0, 1) and ch.colors == {'W'} and 'Deserter' in ch.subtypes
    roundtrip(s)


def test_blocking_in_opponents_combat_also_triggers(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s, source = setup(cards)
    attacker = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    act(s, 'p1', type='next_turn', player='p2', force=True)
    act(s, 'p2', type='pass_priority')
    to_phase(s, 'declare_attackers')
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': attacker.id, 'target': 'p1'}])
    to_phase(s, 'declare_blockers')
    act(s, 'p1', type='declare_blockers', blocks=[{'blocker_id': source.id, 'attacker_id': attacker.id}])
    roundtrip(s)
    to_phase(s, 'end_combat')
    settle(s)
    assert s.state.cards[source.id].counters.get('-0/-1') == 1
    assert len(deserters(s)) == 1
    roundtrip(s)


def test_not_participating_or_later_combat_does_not_trigger(cards):
    from tests.test_rules_clockwork_counters import combat
    from tests.test_rules_wave30m_durations import to_phase
    s, source = setup(cards)
    combat(s, source)
    to_phase(s, 'main2')
    spell = put(s, 'Relentless Assault', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 2, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    settle(s)
    combat(s)
    assert s.state.rules.combats >= 2
    assert s.state.cards[source.id].counters.get('-0/-1') == 1
    assert len(deserters(s)) == 1
    roundtrip(s)


def test_counter_and_token_use_native_replacement_effects(cards):
    from tests.test_rules_clockwork_counters import combat
    s, source = setup(cards)
    put(s, 'Doubling Season', 'battlefield')
    combat(s, source)
    assert s.state.cards[source.id].counters.get('-0/-1') == 2
    assert len(deserters(s)) == 2
    roundtrip(s)


def test_source_leaving_after_trigger_does_not_stop_token_instruction(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s, source = setup(cards)
    to_phase(s, 'declare_attackers')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    to_phase(s, 'end_combat')
    assert s.state.rules.stack
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    roundtrip(s)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:hand'
    assert not s.state.cards[source.id].counters.get('-0/-1')
    assert len(deserters(s)) == 1
    roundtrip(s)
