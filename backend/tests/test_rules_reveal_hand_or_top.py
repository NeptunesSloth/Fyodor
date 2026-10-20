"""CR 107.3/602.2: hidden hand-or-top choices preserve information and native entry."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave31c_copies import to_phase

NAME = 'Eladamri, Korvecdal'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/reveal_hand_or_top_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='rht', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, extra=()):
    s = table(cards, [NAME, 'Llanowar Elves', 'Grizzly Bears', 'Ornithopter', 'Sol Ring',
                      'Containment Priest', "Grafdigger's Cage", *extra], ['Swords to Plowshares'])
    source = put(s, NAME, 'battlefield')
    creatures = [put(s, n, 'battlefield') for n in ['Llanowar Elves', 'Grizzly Bears']]
    to_phase(s, 'main1', turn=4)
    wait_priority(s, 'p1')
    mana(s, G=1)
    return s, source, creatures


def activate(s, source, creatures):
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2,
        cost_choices=[{'component': 2, 'cards': [c.id for c in creatures]}])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume.get('step') == 'reveal_hand_or_top_creature'
    return d


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('where', ['hand', 'library'])
@pytest.mark.parametrize('name,enters', [('Ornithopter', True), ('Sol Ring', False)])
def test_reveal_hand_or_top_then_enter_only_creature(cards, where, name, enters):
    s, source, creatures = setup(cards)
    picked = put(s, name, where)
    if where == 'library':
        act(s, 'p1', type='move', card_ids=[picked.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    d = activate(s, source, creatures)
    assert all(s.state.cards[c.id].tapped for c in [source, *creatures])
    assert s.view('p2')['rules']['decision']['kind'] == 'waiting'
    option = 'top' if where == 'library' else f'hand:{picked.id}'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[option])
    settle(s)
    assert s.state.cards[picked.id].zone == ('p1:battlefield' if enters else f'p1:{where}')
    assert s.view('p2')['cards'][picked.id]['name'] == name
    roundtrip(s)


def test_tap_cost_cannot_count_the_source_again(cards):
    s, source, creatures = setup(cards)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=2,
            cost_choices=[{'component': 2, 'cards': [source.id, creatures[0].id]}])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


@pytest.mark.parametrize('permanent,where,zone', [
    ('Containment Priest', 'hand', 'exile'),
    ('Containment Priest', 'library', 'exile'),
    ("Grafdigger's Cage", 'library', 'library'),
    ("Grafdigger's Cage", 'hand', 'battlefield'),
])
def test_native_entry_restrictions_apply_from_the_actual_revealed_zone(cards, permanent, where, zone):
    s, source, creatures = setup(cards)
    put(s, permanent, 'battlefield')
    picked = put(s, 'Ornithopter', where)
    if where == 'library':
        act(s, 'p1', type='move', card_ids=[picked.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    d = activate(s, source, creatures)
    act(s, 'p1', type='choose', decision_id=d.id,
        option_ids=['top' if where == 'library' else f'hand:{picked.id}'])
    settle(s)
    assert s.state.cards[picked.id].zone == f'p1:{zone}'
    roundtrip(s)


def test_removed_source_does_not_reveal_top_card_in_the_private_options(cards):
    s, source, creatures = setup(cards)
    picked = put(s, 'Ornithopter', 'library')
    act(s, 'p1', type='move', card_ids=[picked.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2,
        cost_choices=[{'component': 2, 'cards': [c.id for c in creatures]}])
    wait_priority(s, 'p2')
    removal = put(s, 'Swords to Plowshares', 'hand', 'p2')
    mana(s, 'p2', W=1)
    act(s, 'p2', type='cast_spell', card_id=removal.id, targets=[source.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume.get('step') == 'reveal_hand_or_top_creature'
    assert s.state.cards[source.id].zone == 'p1:exile'
    option = next(o for o in d.options if o.id == 'top')
    assert option.card_id is None and picked.name not in option.label
    assert picked.id not in s.view('p1')['cards']
    assert s.view('p2')['rules']['decision']['kind'] == 'waiting'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['top'])
    settle(s)
    assert s.state.cards[picked.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_no_cards_in_either_zone_finishes_after_paying_activation_costs(cards):
    s, source, creatures = setup(cards)
    for zone in ['hand', 'library']:
        ids = list(s.state.zones[f'p1:{zone}'])
        if ids:
            act(s, 'p1', type='move', card_ids=ids, to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2,
        cost_choices=[{'component': 2, 'cards': [c.id for c in creatures]}])
    settle(s)
    assert s.state.rules.decision is None
    assert all(s.state.cards[c.id].tapped for c in [source, *creatures])
    assert not s.state.rules.lost
    roundtrip(s)


def test_own_turn_restriction_rejects_activation_before_any_costs(cards):
    s, source, creatures = setup(cards)
    to_phase(s, 'main1', turn=5)
    wait_priority(s, 'p1')
    mana(s, G=1)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=2,
            cost_choices=[{'component': 2, 'cards': [c.id for c in creatures]}])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_intrinsic_creature_card_reveals_then_enters_as_a_planeswalker(cards):
    s, source, creatures = setup(cards, ['Grist, the Hunger Tide'])
    picked = put(s, 'Grist, the Hunger Tide', 'hand')
    d = activate(s, source, creatures)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[f'hand:{picked.id}'])
    settle(s)
    assert s.state.cards[picked.id].zone == 'p1:battlefield'
    assert s.state.cards[picked.id].counters.get('loyalty') == 3
    roundtrip(s)
