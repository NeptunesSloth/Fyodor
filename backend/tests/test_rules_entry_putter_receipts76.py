"""Chants observe the actual per-entry putter and native full counter payment."""
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

NAMES = ["Tourach's Chant", "Thelon's Chant"]
DATA = json.loads((Path(__file__).parent / 'fixtures/entry_putter_receipts76_cards.json').read_text())


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


ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Forest']


def setup(cards):
    s = table(cards, ALL, ALL, ALL)
    start(s)
    return s


@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical_is_read(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name,land', [(NAMES[0], 'Forest'), (NAMES[1], 'Swamp')])
def test_actual_other_player_land_play_decline_damages_putter(cards, name, land):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, name, 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    incoming = put(s, land, 'hand', 'p2')
    to_phase(s, 'main1', turn=5)
    act(s, 'p2', type='play_land', card_id=incoming.id)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p2'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['decline'])
    settle(s)
    assert s.state.players['p2'].life == 37 and s.state.players['p1'].life == 40
    roundtrip(s)


def pay_counter(s, payer, recipient):
    d = s.state.rules.decision
    assert d and d.player == payer and 'pay' in [o.id for o in d.options]
    act(s, payer, type='choose', decision_id=d.id, option_ids=['pay'])
    d = s.state.rules.decision
    if d:
        assert d.player == payer and recipient.id in [o.id for o in d.options]
        act(s, payer, type='choose', decision_id=d.id, option_ids=[recipient.id])
    settle(s)


@pytest.mark.parametrize('name,land', [(NAMES[0], 'Forest'), (NAMES[1], 'Swamp')])
def test_actual_putter_pays_counter_cost_on_own_creature(cards, name, land):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, name, 'battlefield')
    recipient = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    other = put(s, 'Llanowar Elves', 'battlefield')
    incoming = put(s, land, 'hand', 'p2')
    to_phase(s, 'main1', turn=5)
    act(s, 'p2', type='play_land', card_id=incoming.id)
    settle(s)
    pay_counter(s, 'p2', recipient)
    assert recipient.counters == {'-1/-1': 1} and not other.counters
    assert s.state.players['p2'].life == s.state.players['p1'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('name,land', [(NAMES[0], 'Forest'), (NAMES[1], 'Swamp')])
def test_without_creature_cost_is_not_offered_and_actual_putter_takes_damage(cards, name, land):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, name, 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield')
    incoming = put(s, land, 'hand', 'p2')
    to_phase(s, 'main1', turn=5)
    act(s, 'p2', type='play_land', card_id=incoming.id)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.players['p2'].life == 37 and s.state.players['p1'].life == 40
    roundtrip(s)


def decline_all(s):
    payers = []
    for _ in range(20):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            return payers
        if 'decline' in [o.id for o in d.options]:
            payers.append(d.player)
            act(s, d.player, type='choose', decision_id=d.id, option_ids=['decline'])
        elif d.min_choices == 0:
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
        else:
            raise AssertionError((d.kind, d.prompt))
    raise AssertionError('Unexpected repeated decision')


@pytest.mark.parametrize('spell,pool', [('Exhume', {'C': 1, 'B': 1}), ('Living Death', {'C': 3, 'B': 2})])
def test_simultaneous_actual_two_player_putters_are_not_first_mover(cards, spell, pool):
    s = setup(cards)
    put(s, NAMES[0], 'battlefield', 'p3')
    a = put(s, 'Dryad Arbor', 'graveyard')
    b = put(s, 'Dryad Arbor', 'graveyard', 'p2')
    source = put(s, spell, 'hand')
    wait_priority(s, 'p1')
    mana(s, **pool)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    payers = decline_all(s)
    assert sorted(payers) == ['p1', 'p2']
    assert a.zone == 'p1:battlefield' and b.zone == 'p2:battlefield'
    assert s.state.players['p1'].life == s.state.players['p2'].life == 37
    assert s.state.players['p3'].life == 40
    roundtrip(s)


def test_jailbreak_actual_putter_differs_from_returned_forest_controller(cards):
    s = setup(cards)
    put(s, NAMES[0], 'battlefield', 'p3')
    incoming = put(s, 'Forest', 'graveyard', 'p2')
    put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, 'Jailbreak', 'hand')
    wait_priority(s, 'p1')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[incoming.id])
    payers = decline_all(s)
    assert payers == ['p1']
    assert incoming.zone == 'p2:battlefield' and incoming.controller == 'p2'
    assert s.state.players['p1'].life == 37 and s.state.players['p2'].life == 40
    roundtrip(s)


def test_actual_forest_token_creation_has_creator_putter_receipt(cards):
    s = setup(cards)
    put(s, NAMES[0], 'battlefield', 'p3')
    source = put(s, 'Awaken the Woods', 'hand')
    wait_priority(s, 'p1')
    mana(s, C=2, G=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, x_value=2)
    payers = decline_all(s)
    assert payers == ['p1', 'p1']
    assert s.state.players['p1'].life == 34 and s.state.players['p3'].life == 40
    forests = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield']
    assert len(forests) == 2
    roundtrip(s)


@pytest.mark.parametrize('name,color,land', [(NAMES[0], 'B', 'Swamp'), (NAMES[1], 'G', 'Forest')])
@pytest.mark.parametrize('pay', [False, True])
def test_printed_own_upkeep_native_payment_or_sacrifice(cards, name, color, land, pay):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = put(s, name, 'hand')
    mana(s, C=1, **{color: 2})
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    resource = put(s, land, 'battlefield')
    to_phase(s, 'upkeep', turn=7)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    print('UPKEEP', pay, d.kind, [(o.id,o.label) for o in d.options])
    if pay:
        act(s, 'p1', type='activate_ability', card_id=resource.id, ability=0)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay' if pay else 'sacrifice'])
    settle(s)
    assert source.zone == ('p1:battlefield' if pay else 'p1:graveyard')
    roundtrip(s)


@pytest.mark.parametrize('support,paid', [('Solemnity', False), ('Vizier of Remedies', True)])
def test_optional_counter_cost_distinguishes_forbidden_placement_and_zero_replacement(cards, support, paid):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    put(s, NAMES[0], 'battlefield')
    recipient = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, support, 'battlefield', 'p2')
    incoming = put(s, 'Forest', 'hand', 'p2')
    to_phase(s, 'main1', turn=5)
    act(s, 'p2', type='play_land', card_id=incoming.id)
    settle(s)
    if paid:
        pay_counter(s, 'p2', recipient)
    else:
        assert s.state.rules.decision is None
    assert not recipient.counters
    assert s.state.players['p2'].life == (40 if paid else 37)
    roundtrip(s)


def test_manual_move_cannot_forge_server_entry_putter_receipt(cards):
    s = setup(cards)
    put(s, NAMES[0], 'battlefield')
    incoming = put(s, 'Forest', 'hand')
    act(s, 'p1', type='move', card_ids=[incoming.id], to={'player': 'p1', 'zone': 'battlefield'},
        entry_putters={incoming.id: 'p2'})
    settle(s)
    assert s.state.rules.decision is None and s.state.players['p2'].life == 40
    roundtrip(s)
