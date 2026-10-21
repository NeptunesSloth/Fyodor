"""CR 702.84a, 602.2: energy unearth and shared activation costs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/unearth_energy_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Salvation Colossus'


def test_colossus_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup_unearth(cards, name=NAME, *, energy=8, tax=False):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, [name, 'Suppression Field', 'Grizzly Bears'], ['Stifle', 'Unsummon'])
    source = put(s, name, 'graveyard')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    if energy:
        act(s, 'p1', type='resource', player='p1', key='energy', delta=energy)
    if tax:
        put(s, 'Suppression Field', 'battlefield')
    return s, source, bear, ability_index(s, source, 'Unearth')


@pytest.mark.parametrize('energy', [8, 10])
@pytest.mark.parametrize('tax', [False, True])
def test_energy_payment_shared_tax_haste_and_end_step_exile(cards, energy, tax):
    from app.rules.casting import activatable
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave30m_durations import to_phase

    s, source, _, index = setup_unearth(cards, energy=energy, tax=tax)
    if tax:
        mana(s, C=2)
    assert {'card_id': source.id, 'ability': index} in activatable(s.state, 'p1', s.cards, check_priority=False)
    roundtrip(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    assert s.state.players['p1'].resources['energy'] == energy - 8
    assert not any(s.state.players['p1'].mana.values())
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield' and 'haste' in chars(s, source).keywords
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:exile'
    roundtrip(s)


@pytest.mark.parametrize('energy,tax', [(7, False), (8, True)])
def test_incomplete_energy_or_mana_tax_payment_is_atomic(cards, energy, tax):
    from app.game.errors import ActionError
    from app.rules.casting import activatable
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, source, _, index = setup_unearth(cards, energy=energy, tax=tax)
    assert {'card_id': source.id, 'ability': index} not in activatable(s.state, 'p1', s.cards, check_priority=False)
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    assert s.state.players['p1'].resources['energy'] == energy and s.state.cards[source.id].zone == 'p1:graveyard'
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_unearth_is_sorcery_speed_and_not_available_in_combat(cards):
    from app.game.errors import ActionError
    from app.rules.casting import activatable
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, source, _, index = setup_unearth(cards)
    to_phase(s, 'begin_combat', turn=1)
    assert {'card_id': source.id, 'ability': index} not in activatable(s.state, 'p1', s.cards, check_priority=False)
    with pytest.raises(ActionError, match='sorcery'):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    assert s.state.players['p1'].resources['energy'] == 8
    roundtrip(s)


def test_countered_unearth_spends_energy_but_card_can_be_unearthed_again(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle

    s, source, _, index = setup_unearth(cards)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    ability = s.state.zones['stack'][-1]
    wait_priority(s, 'p2')
    counter = put(s, 'Stifle', 'hand', 'p2')
    mana(s, 'p2', U=1)
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[ability])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard' and s.state.players['p1'].resources['energy'] == 0
    act(s, 'p1', type='resource', player='p1', key='energy', delta=8)
    roundtrip(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield' and s.state.players['p1'].resources['energy'] == 0
    roundtrip(s)


def test_bouncing_unearthed_colossus_exiles_it_instead(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle

    s, source, _, index = setup_unearth(cards)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    settle(s)
    wait_priority(s, 'p2')
    bounce = put(s, 'Unsummon', 'hand', 'p2')
    mana(s, 'p2', U=1)
    act(s, 'p2', type='cast_spell', card_id=bounce.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:exile'
    roundtrip(s)


def test_graveyard_new_object_is_not_returned_by_old_activation(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, source, _, index = setup_unearth(cards)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard' and s.state.players['p1'].resources['energy'] == 0
    roundtrip(s)


@pytest.mark.parametrize('tax', [False, True])
def test_mana_unearth_uses_the_same_tax_and_available_action_path(cards, tax):
    from app.rules.casting import activatable
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave30m_durations import to_phase

    s, source, _, index = setup_unearth(cards, 'Hellspark Elemental', tax=tax)
    mana(s, C=3 if tax else 1, R=1)
    assert {'card_id': source.id, 'ability': index} in activatable(s.state, 'p1', s.cards, check_priority=False)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    assert not any(s.state.players['p1'].mana.values()) and s.state.players['p1'].resources['energy'] == 8
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:exile'
    roundtrip(s)


def test_unearthed_colossus_can_attack_immediately_and_buffs_other_creatures(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave30m_durations import to_phase

    s, source, bear, index = setup_unearth(cards)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    settle(s)
    to_phase(s, 'declare_attackers', turn=1)
    d = s.state.rules.decision
    assert d and d.kind == 'declare_attackers'
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    settle(s)
    assert chars(s, bear).pt == (4, 4) and 'indestructible' in chars(s, bear).keywords
    assert not s.state.cards[source.id].tapped  # vigilance
    roundtrip(s)
    to_phase(s, 'main1', turn=2)
    assert s.state.cards[source.id].zone == 'p1:exile'
    assert chars(s, bear).pt == (2, 2) and 'indestructible' not in chars(s, bear).keywords
    roundtrip(s)
