"""CR 603.4, 400.7: mana added by this ability this turn."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/ability_mana_history_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




NAME = 'Carpet of Flowers'


def setup(cards, islands=2):
    s = table(cards, [NAME, NAME, 'Stifle'], ['Island', 'Island', 'Tropical Island'])
    source = put(s, NAME, 'battlefield')
    # distinct printings, no repeated put selecting the same card
    for name in ['Island', 'Tropical Island'][:islands]:
        put(s, name, 'battlefield', 'p2')
    return s, source


def answer(s, option):
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option])
    settle(s)


def trigger(s, phase='main1', turn=4):
    to_phase(s, phase, turn=turn)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    assert d.resume['step'] == 'trigger_target'
    answer(s, 'p2')


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('color', list('WUBRG'))
def test_adds_one_color_and_suppresses_second_main(cards, color):
    s, _ = setup(cards)
    trigger(s)
    answer(s, 'yes')
    answer(s, color)
    assert mana_pool(s)[color] == 2
    to_phase(s, 'main2', turn=4)
    settle(s)
    assert s.state.rules.decision is None
    assert not s.state.zones['stack']
    roundtrip(s)


def test_decline_first_main_can_use_second_main(cards):
    s, _ = setup(cards)
    trigger(s)
    answer(s, 'no')
    trigger(s, 'main2')
    answer(s, 'yes')
    answer(s, 'G')
    assert mana_pool(s)['G'] == 2
    roundtrip(s)


def test_zero_mana_does_not_close_gate(cards):
    s, _ = setup(cards, islands=0)
    trigger(s)
    answer(s, 'yes')
    assert s.state.rules.decision is None
    put(s, 'Island', 'battlefield', 'p2')
    trigger(s, 'main2')
    answer(s, 'yes')
    answer(s, 'U')
    assert mana_pool(s)['U'] == 1
    roundtrip(s)


def test_gate_resets_next_turn(cards):
    s, _ = setup(cards)
    trigger(s)
    answer(s, 'yes')
    answer(s, 'G')
    trigger(s, turn=7)
    answer(s, 'yes')
    answer(s, 'R')
    assert mana_pool(s)['R'] == 2
    roundtrip(s)


def test_new_object_can_add_mana_again_same_turn(cards):
    s, source = setup(cards)
    trigger(s)
    answer(s, 'yes')
    answer(s, 'G')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    trigger(s, 'main2')
    answer(s, 'yes')
    answer(s, 'U')
    assert mana_pool(s)['U'] == 2
    roundtrip(s)


def test_islands_counted_as_resolution_proceeds(cards):
    s, _ = setup(cards, islands=1)
    trigger(s)
    # The target has already been chosen; a new Island before resolution changes X.
    put(s, 'Tropical Island', 'battlefield', 'p2')
    answer(s, 'yes')
    answer(s, 'B')
    assert mana_pool(s)['B'] == 2
    roundtrip(s)


def test_other_players_main_phase_does_not_trigger(cards):
    s, _ = setup(cards)
    to_phase(s, 'main1', turn=2)
    settle(s)
    assert s.state.rules.decision is None
    assert not s.state.zones['stack']
    roundtrip(s)


def test_countering_trigger_keeps_second_main_available(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority

    s, _ = setup(cards)
    to_phase(s, 'main1', turn=4)
    settle(s)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['p2'])
    # Keep the trigger on the stack: unlike answer(), do not pass its priority yet.
    target = s.state.zones['stack'][-1]
    stifle = put(s, 'Stifle', 'hand')
    wait_priority(s, 'p1')
    mana(s, U=1)
    act(s, 'p1', type='cast_spell', card_id=stifle.id, targets=[target])
    settle(s)
    assert s.state.rules.decision is None
    trigger(s, 'main2')
    answer(s, 'yes')
    answer(s, 'R')
    assert mana_pool(s)['R'] == 2
    roundtrip(s)
