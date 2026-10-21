"""CR 118.12, 611.2b: a duration marker scopes an optional action."""
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
from tests.test_rules_designations import build, put, roundtrip, settle


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/optional_duration_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='odu', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_squatters_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Orcish Squatters')).level == 'FULL'


def combat_setup(cards, resolve=True):
    from tests.test_rules_review_combat import stops
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ['Orcish Squatters'])
    source = put(s, 'Orcish Squatters', 'battlefield')
    land = put(s, 'Island', 'battlefield', 'p2')
    stops(s)
    to_phase(s, 'declare_attackers', turn=3)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    d = s.state.rules.decision
    assert d is not None and any(o.id == land.id for o in d.options), (s.state.turn, d)
    from tests.test_rules_designations import pick
    pick(s, [land.id])
    if resolve:
        settle(s)
        assert s.state.rules.decision is not None
    roundtrip(s)
    return s, source, land


@pytest.mark.parametrize('yes', [True, False])
def test_optional_control_cost_also_gates_no_combat_damage(cards, yes):
    from tests.test_rules_designations import pick
    from tests.test_rules_wave30m_durations import to_phase

    s, source, land = combat_setup(cards)
    pick(s, ['yes' if yes else 'no'])
    settle(s)
    to_phase(s, 'main2', turn=3)
    assert s.state.cards[land.id].controller == ('p1' if yes else 'p2')
    assert s.state.players['p2'].life == (40 if yes else 38)
    to_phase(s, 'main1', turn=4)
    assert s.state.cards[land.id].controller == ('p1' if yes else 'p2')
    roundtrip(s)


@pytest.mark.parametrize('change', ['leave', 'control', 'return'])
def test_source_condition_ends_control_and_does_not_restart(cards, change):
    from tests.test_rules_designations import pick
    from tests.test_rules_wave30m_durations import to_phase

    s, source, land = combat_setup(cards)
    pick(s, ['yes'])
    settle(s)
    to_phase(s, 'main2', turn=3)
    assert s.state.cards[land.id].controller == 'p1'
    if change == 'control':
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
        act(s, s.state.rules.priority, type='pass_priority')
        assert s.state.cards[land.id].controller == 'p2', s.state.rules.effects
        act(s, 'p2', type='set_controller', card_ids=[source.id], player='p1')
    else:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
        act(s, s.state.rules.priority, type='pass_priority')
        assert s.state.cards[land.id].controller == 'p2', s.state.rules.effects
        if change == 'return':
            act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    assert s.state.cards[land.id].controller == 'p2', s.state.rules.effects
    roundtrip(s)


def test_target_leaving_and_returning_invalidates_the_whole_ability(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s, source, land = combat_setup(cards, resolve=False)
    act(s, 'p2', type='move', card_ids=[land.id], to={'player': 'p2', 'zone': 'hand'})
    act(s, 'p2', type='move', card_ids=[land.id], to={'player': 'p2', 'zone': 'battlefield'})
    settle(s)
    assert s.state.rules.decision is None
    to_phase(s, 'main2', turn=3)
    assert s.state.cards[land.id].controller == 'p2', s.state.rules.effects
    assert s.state.players['p2'].life == 38
    roundtrip(s)


def test_duration_that_ended_before_resolution_cannot_start(cards):
    from tests.test_rules_designations import pick
    from tests.test_rules_wave30m_durations import to_phase

    s, source, land = combat_setup(cards, resolve=False)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    settle(s)
    if s.state.rules.decision is not None:
        pick(s, ['yes'])
        settle(s)
    to_phase(s, 'main2', turn=3)
    assert s.state.cards[land.id].controller == 'p2', s.state.rules.effects
    assert s.state.players['p2'].life == 40
    from app.rules.plan import Plan
    assert 'assign_none' not in Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).imposed
    roundtrip(s)
