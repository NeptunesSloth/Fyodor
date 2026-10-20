"""CR 608.2c, 303.4i, 301.5e: ordered Spree modes and nontargeted entry attachment."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/spree_reanimation_extrema_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', ['Getaway Glamer', 'One Last Job'])
def test_remaining_spree_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def setup(cards, name):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase
    s = table(cards, [name, 'Grizzly Bears', 'Runeclaw Bear', 'Colossal Dreadmaw', 'Rancor', 'Swiftfoot Boots', 'Lightning Greaves', 'Bomat Bazaar Barge', 'Progenitus'], ['Colossal Dreadmaw', 'Grizzly Bears'], [])
    spell = put(s, name, 'hand')
    to_phase(s, 'main1', turn=4)
    return s, spell


def cast(s, spell, modes, targets):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    mana(s, C=10, W=3)
    act(s, 'p1', type='cast_spell', card_id=spell.id, modes=modes, targets=targets)


@pytest.mark.parametrize('rival,dead', [('Runeclaw Bear', True), ('Colossal Dreadmaw', False)])
def test_glamer_destroy_checks_all_creatures_and_allows_ties(cards, rival, dead):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    s, spell = setup(cards, 'Getaway Glamer')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, rival, 'battlefield')
    cast(s, spell, [1], [bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == ('p1:graveyard' if dead else 'p1:battlefield')
    roundtrip(s)


def test_glamer_blink_higher_power_before_testing_second_mode(cards):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    s, spell = setup(cards, 'Getaway Glamer')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    larger = put(s, 'Colossal Dreadmaw', 'battlefield')
    cast(s, spell, [0, 1], [larger.id, bear.id])
    settle(s)
    assert s.state.cards[larger.id].zone == 'p1:exile'
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('attachment,returns', [('Rancor', False), ('Swiftfoot Boots', True)])
def test_job_without_creature_aura_stays_equipment_enters_unattached(cards, attachment, returns):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    s, spell = setup(cards, 'One Last Job')
    item = put(s, attachment, 'graveyard')
    cast(s, spell, [2], [item.id])
    settle(s)
    assert s.state.cards[item.id].zone == ('p1:battlefield' if returns else 'p1:graveyard')
    assert not s.state.cards[item.id].attached_to
    roundtrip(s)


@pytest.mark.parametrize('attachment', ['Rancor', 'Swiftfoot Boots'])
def test_job_attachment_uses_creature_returned_by_first_mode(cards, attachment):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    s, spell = setup(cards, 'One Last Job')
    bear = put(s, 'Grizzly Bears', 'graveyard')
    item = put(s, attachment, 'graveyard')
    cast(s, spell, [0, 2], [bear.id, item.id])
    settle(s)
    assert s.state.cards[bear.id].zone == s.state.cards[item.id].zone == 'p1:battlefield'
    assert s.state.cards[item.id].attached_to == bear.id
    roundtrip(s)


def test_job_returned_vehicle_does_not_supply_creature_for_aura(cards):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, spell = setup(cards, 'One Last Job')
    vehicle = put(s, 'Bomat Bazaar Barge', 'graveyard')
    aura = put(s, 'Rancor', 'graveyard')
    cast(s, spell, [1, 2], [vehicle.id, aura.id])
    settle(s)
    assert s.state.cards[vehicle.id].zone == 'p1:battlefield'
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_job_attaching_equipment_ignores_hosts_shroud(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, spell = setup(cards, 'One Last Job')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    greaves = put(s, 'Lightning Greaves', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[greaves.id], to=bear.id)
    boots = put(s, 'Swiftfoot Boots', 'graveyard')
    cast(s, spell, [2], [boots.id])
    settle(s)
    assert s.state.cards[boots.id].attached_to == bear.id
    roundtrip(s)


def test_glamer_other_players_creatures_count_at_resolution(cards):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, spell = setup(cards, 'Getaway Glamer')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    larger = put(s, 'Colossal Dreadmaw', 'battlefield', 'p2')
    cast(s, spell, [1], [bear.id])
    # Its relative power is irrelevant when choosing the target; removal before
    # resolution changes the comparison's result.
    from tests.game_helpers import act
    act(s, 'p2', type='move', card_ids=[larger.id], to={'player': 'p2', 'zone': 'exile'})
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('attachment,returns', [('Rancor', False), ('Swiftfoot Boots', True)])
def test_job_protection_prevents_attachment_even_without_targeting(cards, attachment, returns):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, spell = setup(cards, 'One Last Job')
    put(s, 'Progenitus', 'battlefield')
    item = put(s, attachment, 'graveyard')
    cast(s, spell, [2], [item.id])
    settle(s)
    assert s.state.cards[item.id].zone == ('p1:battlefield' if returns else 'p1:graveyard')
    assert not s.state.cards[item.id].attached_to
    roundtrip(s)


def test_job_host_choice_is_resolution_only_and_excludes_opponents(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import put, roundtrip

    s, spell = setup(cards, 'One Last Job')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Runeclaw Bear', 'battlefield')
    opponent = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    boots = put(s, 'Swiftfoot Boots', 'graveyard')
    cast(s, spell, [2], [boots.id])
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert {o.id for o in d.options} == {bear.id, other.id}
    assert opponent.id not in {o.id for o in d.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[other.id])
    settle(s)
    assert s.state.cards[boots.id].attached_to == other.id
    roundtrip(s)


def test_job_illegal_creature_target_does_not_supply_attachment_host(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, spell = setup(cards, 'One Last Job')
    bear = put(s, 'Grizzly Bears', 'graveyard')
    aura = put(s, 'Rancor', 'graveyard')
    cast(s, spell, [0, 2], [bear.id, aura.id])
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:exile'
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    roundtrip(s)
