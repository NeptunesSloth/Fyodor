"""Owners choose exact target objects on library top or bottom across three zones."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.view import hints
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Subtlety', 'Aether Gust', 'Endless Detour']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/owner_library_choice_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return table(cards, [*NAMES, 'Grizzly Bears', 'Lightning Bolt', 'Carnage Tyrant', 'Chandra, Torch of Defiance', 'Forest', 'Sol Ring', 'Commandeer'],
                 ['Grizzly Bears', 'Lightning Bolt', 'Carnage Tyrant', 'Chandra, Torch of Defiance', 'Forest', 'Sol Ring'])


def answer(s, player, place):
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == player and {o.id for o in d.options} == {'top', 'bottom'}
    roundtrip(s)
    act(s, player, type='choose', decision_id=d.id, option_ids=[place])
    settle(s)


@pytest.mark.parametrize('name', NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize(('target_name', 'cost'), [
    ('Grizzly Bears', {'G': 1, 'C': 1}), ('Chandra, Torch of Defiance', {'R': 2, 'C': 2}),
    ('Carnage Tyrant', {'G': 2, 'C': 4}),
])
@pytest.mark.parametrize('place', ['top', 'bottom'])
def test_actual_subtlety_moves_creature_or_planeswalker_spell_even_uncounterable(cards, target_name, cost, place):
    s = setup(cards)
    spell = put(s, target_name, 'hand', pid='p2')
    to_phase(s, 'main1', turn=2)
    wait_priority(s, 'p2')
    mana(s, pid='p2', **cost)
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[])
    wait_priority(s, 'p1')
    subtlety = put(s, 'Subtlety', 'hand')
    mana(s, U=2, C=2)
    act(s, 'p1', type='cast_spell', card_id=subtlety.id, targets=[])
    settle(s)
    d = s.state.rules.decision
    assert d and spell.id in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[spell.id])
    answer(s, 'p2', place)
    assert s.state.cards[spell.id].zone == 'p2:library'
    assert s.state.zones['p2:library'][0 if place == 'top' else -1] == spell.id
    assert s.state.cards[subtlety.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_subtlety_can_choose_no_target(cards):
    s = setup(cards)
    subtlety = put(s, 'Subtlety', 'hand')
    mana(s, U=2, C=2)
    act(s, 'p1', type='cast_spell', card_id=subtlety.id, targets=[])
    settle(s)
    d = s.state.rules.decision
    if d:
        assert d.min_choices == 0
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
        settle(s)
    assert s.state.cards[subtlety.id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('zone', ['battlefield', 'stack'])
@pytest.mark.parametrize('place', ['top', 'bottom'])
def test_aether_gust_red_or_green_spell_or_permanent_owner_chooses(cards, zone, place):
    s = setup(cards)
    target = put(s, 'Grizzly Bears' if zone == 'battlefield' else 'Lightning Bolt', 'hand', pid='p2')
    if zone == 'battlefield':
        act(s, 'p2', type='move', card_ids=[target.id], to={'player': 'p2', 'zone': 'battlefield'})
    else:
        wait_priority(s, 'p2')
        mana(s, pid='p2', R=1)
        act(s, 'p2', type='cast_spell', card_id=target.id, targets=['p3'])
        wait_priority(s, 'p1')
    gust = put(s, 'Aether Gust', 'hand')
    mana(s, U=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=gust.id, targets=[target.id])
    answer(s, 'p2', place)
    assert s.state.zones['p2:library'][0 if place == 'top' else -1] == target.id
    assert s.state.players['p3'].life == 40
    roundtrip(s)


@pytest.mark.parametrize(('zone', 'name'), [('stack', 'Lightning Bolt'), ('battlefield', 'Sol Ring'), ('graveyard', 'Grizzly Bears'), ('graveyard', 'Forest')])
@pytest.mark.parametrize('place', ['top', 'bottom'])
def test_endless_detour_target_union_and_owner_choice(cards, zone, name, place):
    s = setup(cards)
    target = put(s, name, 'hand' if zone == 'stack' else zone, pid='p2')
    if zone == 'stack':
        wait_priority(s, 'p2')
        mana(s, pid='p2', R=1)
        act(s, 'p2', type='cast_spell', card_id=target.id, targets=['p3'])
        wait_priority(s, 'p1')
    detour = put(s, 'Endless Detour', 'hand')
    mana(s, G=1, W=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=detour.id, targets=[target.id])
    answer(s, 'p2', place)
    assert s.state.zones['p2:library'][0 if place == 'top' else -1] == target.id
    assert s.state.players['p3'].life == 40
    roundtrip(s)


@pytest.mark.parametrize(('zone', 'name'), [('battlefield', 'Forest'), ('hand', 'Grizzly Bears'), ('exile', 'Grizzly Bears')])
def test_endless_detour_refuses_objects_outside_its_union(cards, zone, name):
    s = setup(cards)
    target = put(s, name, zone, pid='p2')
    detour = put(s, 'Endless Detour', 'hand')
    mana(s, G=1, W=1, U=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=detour.id, targets=[target.id])
    assert s.state.cards[detour.id].zone == 'p1:hand'


def test_owner_library_choice_does_not_move_a_new_incarnation(cards):
    s = setup(cards)
    target = put(s, 'Sol Ring', 'battlefield', pid='p2')
    detour = put(s, 'Endless Detour', 'hand')
    mana(s, G=1, W=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=detour.id, targets=[target.id])
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p2'
    act(s, 'p2', type='move', card_ids=[target.id], to={'player': 'p2', 'zone': 'exile'})
    act(s, 'p2', type='move', card_ids=[target.id], to={'player': 'p2', 'zone': 'battlefield'})
    roundtrip(s)
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['bottom'])
    settle(s)
    assert s.state.cards[target.id].zone == 'p2:battlefield'
    roundtrip(s)


def test_stolen_spell_owner_not_current_controller_chooses_library_placement(cards):
    from tests.test_rules_narset_rebound import steal_bolt
    s = setup(cards)
    bolt = put(s, 'Lightning Bolt', 'hand', pid='p2')
    wait_priority(s, 'p2')
    mana(s, pid='p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    steal_bolt(s, bolt, player='p1', target='keep')
    gust = put(s, 'Aether Gust', 'hand')
    mana(s, U=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=gust.id, targets=[bolt.id])
    answer(s, 'p2', 'bottom')
    assert s.state.zones['p2:library'][-1] == bolt.id
    assert s.state.players['p3'].life == 40
    roundtrip(s)


def test_actual_subtlety_evoke_exiles_blue_card_then_sacrifices(cards):
    s = setup(cards)
    subtlety = put(s, 'Subtlety', 'hand')
    blue = put(s, 'Aether Gust', 'hand')
    (offer,) = hints(s.state, 'p1', cards)['alt_castable'][subtlety.id]
    act(s, 'p1', type='cast_spell', card_id=subtlety.id, alt_cost=offer['id'], targets=[])
    settle(s)
    while s.state.rules.decision:
        d = s.state.rules.decision
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
        settle(s)
    assert s.state.cards[blue.id].zone == 'p1:exile'
    assert s.state.cards[subtlety.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_aether_gust_still_respects_hexproof_on_battlefield(cards):
    s = setup(cards)
    tyrant = put(s, 'Carnage Tyrant', 'battlefield', pid='p2')
    gust = put(s, 'Aether Gust', 'hand')
    mana(s, U=1, C=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=gust.id, targets=[tyrant.id])
    assert s.state.cards[gust.id].zone == 'p1:hand'


def test_subtlety_trigger_does_not_target_instant_spells(cards):
    s = setup(cards)
    bolt = put(s, 'Lightning Bolt', 'hand', pid='p2')
    wait_priority(s, 'p2')
    mana(s, pid='p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    wait_priority(s, 'p1')
    subtlety = put(s, 'Subtlety', 'hand')
    mana(s, U=2, C=2)
    act(s, 'p1', type='cast_spell', card_id=subtlety.id, targets=[])
    settle(s)
    d = s.state.rules.decision
    if d:
        assert bolt.id not in {o.id for o in d.options}
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
        settle(s)
    assert s.state.cards[bolt.id].zone == 'p2:graveyard'
    assert s.state.players['p3'].life == 37
    roundtrip(s)
