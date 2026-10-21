"""CR 111.2, 608.2h: conditional attached copy and actual creation fallback."""
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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/conditional_return_destination_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




NAME = 'Emeria Shepherd'


def setup(cards, land='Plains', target='Grizzly Bears', *, resolve=True):
    s = table(cards, [NAME, land, target, "Phantasmal Terrain", 'Spreading Seas', 'Containment Priest', 'Cyclonic Rift', 'Boomerang', 'Lightning Greaves', "Alchemist's Refuge"], ['Grizzly Bears'])
    put(s, "Alchemist's Refuge", 'battlefield')
    source = put(s, NAME, 'battlefield')
    card = put(s, target, 'graveyard')
    incoming = put(s, land, 'hand')
    act(s, 'p1', type='play_land', card_id=incoming.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and any(o.id == card.id for o in d.options)
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[card.id])
    if resolve:
        settle(s)
    return s, source, incoming, card


def answer(s, option):
    d = s.state.rules.decision
    assert d is not None
    assert s.view(d.player)['rules']['decision'].get('options')
    assert not s.view('p2')['rules']['decision'].get('options')
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option])
    settle(s)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('land,destination', [('Plains', 'hand'), ('Plains', 'battlefield'), ('Plains', 'decline'),
                                             ('Forest', 'hand'), ('Forest', 'decline')])
def test_optional_destinations(cards, land, destination):
    s, _, _, card = setup(cards, land)
    d = s.state.rules.decision
    assert d is not None
    assert ('battlefield' in {o.id for o in d.options}) == (land == 'Plains')
    answer(s, destination)
    assert s.state.cards[card.id].zone == 'p1:' + ('graveyard' if destination == 'decline' else destination)
    roundtrip(s)


def cast_land_aura(s, land, name):
    from tests.test_rules_bandmate_references import wait_priority

    wait_priority(s, 'p1')
    from tests.test_rules_wave7b_activation import ability_index

    refuge = next(c for c in s.state.cards.values() if c.name == "Alchemist's Refuge")
    mana(s, G=1, U=1)
    act(s, 'p1', type='activate_ability', card_id=refuge.id, ability=ability_index(s, refuge, 'You may cast'))
    while len(s.state.zones.get('stack', [])) > 1:
        act(s, s.state.rules.priority, type='pass_priority')
    wait_priority(s, 'p1')
    spell = put(s, name, 'hand')
    mana(s, C=1, U=1 if name == 'Spreading Seas' else 2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[land.id])
    while s.state.cards[spell.id].zone == 'stack':
        d = s.state.rules.decision
        if d is not None:
            assert any(o.id == 'Plains' for o in d.options)
            roundtrip(s)
            act(s, d.player, type='choose', decision_id=d.id, option_ids=['Plains'])
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    return spell


@pytest.mark.parametrize('land,aura,battlefield', [('Plains', 'Spreading Seas', False), ('Forest', "Phantasmal Terrain", True)])
def test_triggering_lands_current_type_at_resolution(cards, land, aura, battlefield):
    s, _, incoming, card = setup(cards, land, resolve=False)
    cast_land_aura(s, incoming, aura)
    from tests.test_rules_wave6c_tokens_pumps import chars

    assert ('Plains' in chars(s, s.state.cards[incoming.id]).subtypes) == battlefield
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    assert ('battlefield' in {o.id for o in d.options}) == battlefield
    answer(s, 'battlefield' if battlefield else 'hand')
    assert s.state.cards[card.id].zone == ('p1:battlefield' if battlefield else 'p1:hand')
    roundtrip(s)


def test_triggering_land_lki_preserves_added_plains_type(cards):
    s, _, land, card = setup(cards, 'Forest', resolve=False)
    cast_land_aura(s, land, "Phantasmal Terrain")
    from tests.test_rules_wave6c_tokens_pumps import chars

    assert 'Plains' in chars(s, s.state.cards[land.id]).subtypes
    from tests.test_rules_bandmate_references import wait_priority

    wait_priority(s, 'p1')
    bounce = put(s, 'Boomerang', 'hand')
    mana(s, U=2)
    act(s, 'p1', type='cast_spell', card_id=bounce.id, targets=[land.id])
    while s.state.cards[bounce.id].zone == 'stack':
        act(s, s.state.rules.priority, type='pass_priority')
    settle(s)
    d = s.state.rules.decision
    assert d is not None and 'battlefield' in {o.id for o in d.options}
    answer(s, 'battlefield')
    assert s.state.cards[card.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_target_new_incarnation_fizzles_before_destination_choice(cards):
    s, _, _, card = setup(cards, resolve=False)
    act(s, 'p1', type='move', card_ids=[card.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[card.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert s.state.rules.decision is None and s.state.cards[card.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_source_controller_changes_do_not_change_trigger_controller(cards):
    s, source, _, card = setup(cards, resolve=False)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    answer(s, 'battlefield')
    assert s.state.cards[card.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_battle_card_is_a_nonland_permanent_card(cards):
    s, _, _, card = setup(cards, target='Invasion of Zendikar // Awakened Skyclave')
    answer(s, 'hand')
    assert s.state.cards[card.id].zone == 'p1:hand'
    roundtrip(s)


def test_aura_without_legal_host_remains_in_graveyard(cards):
    s, _, _, card = setup(cards, target='Daybreak Coronet')
    answer(s, 'battlefield')
    assert s.state.cards[card.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_aura_return_chooses_shrouded_opponents_creature_without_targeting(cards):
    s, _, _, card = setup(cards, target='Rancor', resolve=False)
    host = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    greaves = put(s, 'Lightning Greaves', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[greaves.id], to=host.id)
    settle(s)
    answer(s, 'battlefield')
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'aura_enters' and host.id in {o.id for o in d.options}
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[host.id])
    settle(s)
    assert s.state.cards[card.id].attached_to == host.id and s.state.cards[card.id].controller == 'p1'
    roundtrip(s)


def test_native_priest_entry_replacement_is_respected(cards):
    s, _, _, card = setup(cards, resolve=False)
    put(s, 'Containment Priest', 'battlefield')
    settle(s)
    answer(s, 'battlefield')
    assert s.state.cards[card.id].zone == 'p1:exile'
    roundtrip(s)


def test_no_legal_graveyard_target_does_not_offer_optional_return(cards):
    s = table(cards, [NAME, 'Plains', 'Forest'])
    put(s, NAME, 'battlefield')
    put(s, 'Forest', 'graveyard')  # A permanent card, but excluded by nonland.
    land = put(s, 'Plains', 'hand')
    act(s, 'p1', type='play_land', card_id=land.id)
    settle(s)
    assert s.state.rules.decision is None and not s.state.zones.get('stack')
    roundtrip(s)


def test_source_leaving_does_not_remove_pending_return(cards):
    s, source, _, card = setup(cards, resolve=False)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    answer(s, 'battlefield')
    assert s.state.cards[card.id].zone == 'p1:battlefield'
    roundtrip(s)
