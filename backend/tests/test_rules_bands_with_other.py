"""CR 702.22b-k: qualified bands and their combat damage assignment."""
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
from tests.test_rules_banding import attacks, block, damage_choice, declare_only, divide, until_block
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/bands_with_other_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Cathedral of Serra', "Adventurers' Guildhouse", 'Mountain Stronghold', 'Unholy Citadel', "Seafarer's Quay", 'Master of the Hunt', 'Shelkin Brownie', 'Tolaria'])
def test_bands_with_other_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def qualified(s, c):
    from app.rules.banding import qualities
    from app.rules.plan import Plan

    return qualities(Plan(s.state, 'p1', s.cards, None), s.state.cards[c.id])


@pytest.mark.parametrize('land,matching,wrong', [
    ('Cathedral of Serra', 'Isamaru, Hound of Konda', 'Baral, Chief of Compliance'),
    ("Adventurers' Guildhouse", 'Thrun, the Last Troll', 'Isamaru, Hound of Konda'),
    ('Mountain Stronghold', 'Ragavan, Nimble Pilferer', 'Isamaru, Hound of Konda'),
    ('Unholy Citadel', 'Kokusho, the Evening Star', 'Isamaru, Hound of Konda'),
    ("Seafarer's Quay", 'Baral, Chief of Compliance', 'Isamaru, Hound of Konda'),
])
def test_each_land_grants_its_matching_legendary_creatures_the_qualified_ability(cards, land, matching, wrong):
    s = table(cards, [land, matching, wrong, 'Savannah Lions'], [matching])
    source = put(s, land, 'battlefield')
    mine = put(s, matching, 'battlefield')
    other_color = put(s, wrong, 'battlefield')
    nonlegend = put(s, 'Savannah Lions', 'battlefield')
    opponent = put(s, matching, 'battlefield', 'p2')
    assert qualified(s, mine)
    assert not qualified(s, other_color) and not qualified(s, nonlegend) and not qualified(s, opponent)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert not qualified(s, mine)
    roundtrip(s)


def test_one_holder_can_band_with_multiple_other_legendary_creatures_without_ordinary_banding(cards):
    s = table(cards, ['Cathedral of Serra', 'Isamaru, Hound of Konda', 'Baral, Chief of Compliance', 'Ragavan, Nimble Pilferer'], ['Gigantosaurus'])
    put(s, 'Cathedral of Serra', 'battlefield')
    creatures = [put(s, name, 'battlefield') for name in ['Isamaru, Hound of Konda', 'Baral, Chief of Compliance', 'Ragavan, Nimble Pilferer']]
    giant = put(s, 'Gigantosaurus', 'battlefield', 'p2')
    assert qualified(s, creatures[0]) and not qualified(s, creatures[1]) and not qualified(s, creatures[2])
    attacks(s, [(c, 'p2') for c in creatures], [creatures])
    block(s, [(giant, creatures[0])])
    assert all(s.state.cards[giant.id].blocks(c.id) for c in creatures)
    assert damage_choice(s).player == 'p1'
    divide(s, {creatures[2].id: 10})
    assert creatures[2].id in s.state.zones['p1:graveyard']
    assert all(c.id in s.state.zones['p1:battlefield'] for c in creatures[:2])
    roundtrip(s)


def test_a_nonmatching_creature_cannot_join_a_qualified_band(cards):
    from app.game.errors import ActionError
    from tests.test_rules_banding import attack_step

    s = table(cards, ['Cathedral of Serra', 'Isamaru, Hound of Konda', 'Baral, Chief of Compliance', 'Grizzly Bears'])
    put(s, 'Cathedral of Serra', 'battlefield')
    creatures = [put(s, name, 'battlefield') for name in ['Isamaru, Hound of Konda', 'Baral, Chief of Compliance', 'Grizzly Bears']]
    attack_step(s)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in creatures],
            bands=[[c.id for c in creatures]])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


@pytest.mark.parametrize('other_name', ['Baral, Chief of Compliance', 'Grizzly Bears'])
def test_defending_qualified_banding_needs_another_matching_creature_to_change_the_chooser(cards, other_name):
    s = table(cards, ['Gigantosaurus'], ['Cathedral of Serra', 'Isamaru, Hound of Konda', other_name])
    giant = put(s, 'Gigantosaurus', 'battlefield')
    put(s, 'Cathedral of Serra', 'battlefield', 'p2')
    holder = put(s, 'Isamaru, Hound of Konda', 'battlefield', 'p2')
    other = put(s, other_name, 'battlefield', 'p2')
    attacks(s, [(giant, 'p2')])
    block(s, [(holder, giant), (other, giant)])
    d = damage_choice(s)
    assert d.player == ('p2' if other_name == 'Baral, Chief of Compliance' else 'p1')
    divide(s, {holder.id: 10})
    roundtrip(s)


def test_master_of_the_hunt_creates_named_tokens_that_can_band_together(cards):
    from tests.test_rules_wave5j_token_copies import tokens

    s = table(cards, ['Master of the Hunt'], ['Gigantosaurus'])
    master = put(s, 'Master of the Hunt', 'battlefield')
    giant = put(s, 'Gigantosaurus', 'battlefield', 'p2')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 6, 'G': 6})
    for _ in range(3):
        act(s, 'p1', type='activate_ability', card_id=master.id, ability=0)
    settle(s)
    wolves = [c for c in tokens(s) if c.name == 'Wolves of the Hunt']
    assert len(wolves) == 3 and all(qualified(s, c) for c in wolves)
    roundtrip(s)
    attacks(s, [(c, 'p2') for c in wolves], [wolves])
    block(s, [(giant, wolves[0])])
    assert damage_choice(s).player == 'p1'
    divide(s, {wolves[0].id: 10})
    assert wolves[0].id not in s.state.cards
    assert all(c.id in s.state.zones['p1:battlefield'] for c in wolves[1:])
    roundtrip(s)


def test_losing_the_qualified_ability_keeps_the_band_but_restores_the_normal_chooser(cards):
    s = table(cards, ['Shelkin Brownie', 'Cathedral of Serra', 'Isamaru, Hound of Konda', 'Baral, Chief of Compliance'], ['Gigantosaurus'])
    brownie = put(s, 'Shelkin Brownie', 'battlefield')
    put(s, 'Cathedral of Serra', 'battlefield')
    holder = put(s, 'Isamaru, Hound of Konda', 'battlefield')
    other = put(s, 'Baral, Chief of Compliance', 'battlefield')
    giant = put(s, 'Gigantosaurus', 'battlefield', 'p2')
    declare_only(s, [holder, other], [[holder, other]])
    act(s, 'p1', type='activate_ability', card_id=brownie.id, ability=0, targets=[holder.id])
    settle(s)
    assert not qualified(s, holder)
    until_block(s)
    block(s, [(giant, holder)])
    assert s.state.cards[giant.id].blocks(other.id)
    assert damage_choice(s).player == 'p2'
    divide(s, {other.id: 10})
    assert holder.id in s.state.zones['p1:battlefield']
    roundtrip(s)


def priority(s, pid):
    for _ in range(6):
        if s.state.rules.priority == pid:
            return
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('priority did not reach the player')


def test_tolaria_obeys_its_upkeep_limit_and_later_ordinary_banding_does_not_restore_qualified_banding(cards):
    from app.game.errors import ActionError
    from tests.test_rules_banding import has_banding
    from tests.test_rules_wave30m_durations import to_phase

    names = ['Tolaria', 'Cathedral of Serra', 'Rhys the Redeemed', 'Baton of Morale', "Adventurers' Guildhouse"]
    s = table(cards, names)
    land = put(s, 'Tolaria', 'battlefield')
    put(s, 'Cathedral of Serra', 'battlefield')
    rhys = put(s, 'Rhys the Redeemed', 'battlefield')
    baton = put(s, 'Baton of Morale', 'battlefield')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=land.id, ability=1, targets=[rhys.id])
    assert s.state.model_dump(mode='json') == before
    to_phase(s, 'upkeep', turn=2)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=baton.id, ability=0, targets=[rhys.id])
    settle(s)
    assert has_banding(s, rhys) and qualified(s, rhys)
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=land.id, ability=1, targets=[rhys.id])
    settle(s)
    assert s.state.cards[land.id].tapped
    assert not has_banding(s, rhys) and not qualified(s, rhys)
    roundtrip(s)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=baton.id, ability=0, targets=[rhys.id])
    settle(s)
    assert has_banding(s, rhys) and not qualified(s, rhys)
    # A later static grant wins at its own timestamp; the old land's grant stayed suppressed.
    put(s, "Adventurers' Guildhouse", 'battlefield')
    assert qualified(s, rhys)
    roundtrip(s)


def test_shelkin_brownie_removes_qualified_forms_without_removing_ordinary_banding(cards):
    from tests.test_rules_banding import has_banding
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Shelkin Brownie', 'Cathedral of Serra', 'Rhys the Redeemed', 'Baton of Morale'])
    brownie = put(s, 'Shelkin Brownie', 'battlefield')
    put(s, 'Cathedral of Serra', 'battlefield')
    rhys = put(s, 'Rhys the Redeemed', 'battlefield')
    baton = put(s, 'Baton of Morale', 'battlefield')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=baton.id, ability=0, targets=[rhys.id])
    settle(s)
    assert has_banding(s, rhys) and qualified(s, rhys)
    act(s, 'p1', type='activate_ability', card_id=brownie.id, ability=0, targets=[rhys.id])
    settle(s)
    assert has_banding(s, rhys) and not qualified(s, rhys)
    roundtrip(s)


def test_losing_all_qualified_forms_then_gaining_one_later_does_not_restore_the_other(cards):
    from tests.test_rules_wave5j_token_copies import tokens
    from tests.test_rules_wave30m_durations import to_phase

    names = ['Master of the Hunt', 'Shelkin Brownie', 'Leyline of Singularity',
             "Adventurers' Guildhouse", "Adventurers' Guildhouse"]
    s = table(cards, names)
    master = put(s, 'Master of the Hunt', 'battlefield')
    brownie = put(s, 'Shelkin Brownie', 'battlefield')
    put(s, 'Leyline of Singularity', 'battlefield')
    first_land = put(s, "Adventurers' Guildhouse", 'battlefield')
    second_land = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == first_land.name and c.id != first_land.id)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'G': 2})
    act(s, 'p1', type='activate_ability', card_id=master.id, ability=0)
    settle(s)
    wolf = next(c for c in tokens(s) if c.name == 'Wolves of the Hunt')
    assert len(qualified(s, wolf)) == 2
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='activate_ability', card_id=brownie.id, ability=0, targets=[wolf.id])
    settle(s)
    assert not qualified(s, wolf)
    roundtrip(s)
    act(s, 'p1', type='move', card_ids=[second_land.id], to={'player': 'p1', 'zone': 'battlefield'})
    remaining = qualified(s, wolf)
    assert len(remaining) == 1 and remaining[0].supertypes == ('Legendary',)
    roundtrip(s)


def test_unknown_qualified_banding_forms_stay_manual():
    from app.rules import banding, granted

    assert banding.quality('bands with other blue creatures') is None
    assert granted.quote('bands with other blue creatures') is None
