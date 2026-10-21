"""Completed die results captured by real reflexive triggered abilities."""
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
from tests.test_rules_conditionals import until_asked
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave12a_counters_keywords import rolls
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/reflexive_roll_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



BRASS = 'Ancient Brass Dragon'
BRONZE = 'Ancient Bronze Dragon'


@pytest.mark.parametrize('name', [BRASS, BRONZE])
def test_roll_reflexive_dragons_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def setup(cards, name=BRASS):
    s = table(cards, [name, 'Stifle', 'Counterspell', 'Perilous Myr', 'Grizzly Bears', 'Hardened Scales', 'Pixie Guide', 'Wyll, Blade of Frontiers'], ['Perilous Myr', 'Grizzly Bears'], ['Perilous Myr'])
    dragon = put(s, name, 'battlefield')
    to_phase(s, 'main1', turn=4)
    return s, dragon


def combat(s, dragon):
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            assert d.kind == 'declare_attackers'
            act(s, 'p1', type='declare_attackers', attackers=[{'card_id': dragon.id, 'target': 'p2'}])
            break
        act(s, s.state.rules.priority, type='pass_priority')
    for _ in range(40):
        if s.state.zones.get('stack'):
            return
        d = s.state.rules.decision
        if d is not None:
            assert d.kind == 'declare_blockers'
            act(s, d.player, type='declare_blockers', blocks=[])
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('combat trigger never appeared')


def choose(s, ids):
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)


def test_brass_rolls_before_targets_and_returns_from_multiple_graveyards(cards, monkeypatch):
    s, dragon = setup(cards)
    own = put(s, 'Perilous Myr', 'graveyard')
    theirs = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    rolls(monkeypatch, 4)
    combat(s, dragon)
    original = next(iter(s.state.rules.stack.values()))
    assert not original.targets and not original.groups
    d = until_asked(s)
    assert d.kind == 'choose_cards' and {own.id, theirs.id} <= {o.id for o in d.options}
    roundtrip(s)
    choose(s, [own.id, theirs.id])
    reflexive = next(iter(s.state.rules.stack.values()))
    assert reflexive.event.amount == 4 and reflexive.group_specs[0]['total'] == ['mana_value', 'X']
    settle(s)
    assert s.state.cards[own.id].zone == 'p1:battlefield'
    assert s.state.cards[theirs.id].zone.endswith(':battlefield') and s.state.cards[theirs.id].controller == 'p1'
    roundtrip(s)


def test_brass_total_budget_rejects_excess_then_allows_zero(cards, monkeypatch):
    s, dragon = setup(cards)
    a = put(s, 'Perilous Myr', 'graveyard')
    b = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    rolls(monkeypatch, 3)
    combat(s, dragon)
    until_asked(s)
    with pytest.raises(ActionError):
        choose(s, [a.id, b.id])
    choose(s, [])
    settle(s)
    assert s.state.cards[a.id].zone.endswith(':graveyard') and s.state.cards[b.id].zone.endswith(':graveyard')
    roundtrip(s)


def test_bronze_frozen_result_counters_and_counter_replacement(cards, monkeypatch):
    s, dragon = setup(cards, BRONZE)
    scales = put(s, 'Hardened Scales', 'battlefield')
    a = put(s, 'Perilous Myr', 'battlefield')
    b = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    rolls(monkeypatch, 6)
    combat(s, dragon)
    until_asked(s)
    choose(s, [a.id, b.id])
    assert next(iter(s.state.rules.stack.values())).event.amount == 6
    settle(s)
    assert s.state.cards[a.id].counters['+1/+1'] == 7
    assert s.state.cards[b.id].counters['+1/+1'] == 6
    assert s.state.cards[scales.id].zone.endswith(':battlefield')
    roundtrip(s)


@pytest.mark.parametrize('counter_when', ['original', 'reflexive'])
def test_original_and_reflexive_abilities_can_be_countered_separately(cards, monkeypatch, counter_when):
    s, dragon = setup(cards)
    dead = put(s, 'Perilous Myr', 'graveyard')
    rolls(monkeypatch, 5)
    combat(s, dragon)
    if counter_when == 'reflexive':
        until_asked(s)
        choose(s, [dead.id])
    target = next(iter(s.state.rules.stack))
    wait_priority(s, 'p1')
    stifle = put(s, 'Stifle', 'hand')
    mana(s, U=1)
    act(s, 'p1', type='cast_spell', card_id=stifle.id, targets=[target])
    settle(s)
    assert s.state.cards[dead.id].zone.endswith(':graveyard')
    assert not s.state.rules.stack
    roundtrip(s)


def test_brass_reflexive_controller_and_result_survive_source_change_and_departure(cards, monkeypatch):
    s, dragon = setup(cards)
    dead = put(s, 'Perilous Myr', 'graveyard', 'p2')
    rolls(monkeypatch, 2)
    combat(s, dragon)
    act(s, 'p1', type='set_controller', card_ids=[dragon.id], player='p3')
    d = until_asked(s)
    assert d.player == 'p1'
    act(s, 'p1', type='move', card_ids=[dragon.id], to={'player': 'p1', 'zone': 'graveyard'})
    choose(s, [dead.id])
    assert next(iter(s.state.rules.stack.values())).event.amount == 2
    roundtrip(s)
    settle(s)
    assert s.state.cards[dead.id].controller == 'p1' and s.state.cards[dead.id].zone.endswith(':battlefield')
    roundtrip(s)


def test_brass_rechecks_selected_graveyard_objects_on_resolution(cards, monkeypatch):
    s, dragon = setup(cards)
    a = put(s, 'Perilous Myr', 'graveyard')
    b = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    rolls(monkeypatch, 4)
    combat(s, dragon)
    until_asked(s)
    choose(s, [a.id, b.id])
    act(s, 'p1', type='move', card_ids=[a.id], to={'player': 'p1', 'zone': 'hand'})
    settle(s)
    assert s.state.cards[a.id].zone == 'p1:hand'
    assert s.state.cards[b.id].zone.endswith(':battlefield') and s.state.cards[b.id].controller == 'p1'
    roundtrip(s)


def test_bronze_extra_die_ignores_lowest_and_freezes_kept_result(cards, monkeypatch):
    s, dragon = setup(cards, BRONZE)
    put(s, 'Pixie Guide', 'battlefield')
    target = put(s, 'Perilous Myr', 'battlefield')
    rolls(monkeypatch, 3, 12)
    combat(s, dragon)
    until_asked(s)
    choose(s, [target.id])
    assert next(iter(s.state.rules.stack.values())).event.amount == 12
    roundtrip(s)
    settle(s)
    assert s.state.cards[target.id].counters['+1/+1'] == 12
    roundtrip(s)



def test_brass_any_number_can_select_more_than_two_cards(cards, monkeypatch):
    s, dragon = setup(cards)
    selected = [put(s, 'Perilous Myr', 'graveyard'), put(s, 'Grizzly Bears', 'graveyard', 'p2'),
                put(s, 'Perilous Myr', 'graveyard', 'p3')]
    rolls(monkeypatch, 6)
    combat(s, dragon)
    until_asked(s)
    choose(s, [c.id for c in selected])
    roundtrip(s)
    settle(s)
    assert all(s.state.cards[c.id].zone.endswith(':battlefield') and s.state.cards[c.id].controller == 'p1' for c in selected)
    roundtrip(s)
