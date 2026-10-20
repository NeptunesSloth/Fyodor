"""CR 707.9d, 608.2h: half-size copies after a creature dies."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/half_size_copies_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_saw_in_half_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Saw in Half')).level == 'FULL'


@pytest.mark.parametrize('name,boost,expected', [('Grizzly Bears', False, (1, 1)), ('Hill Giant', False, (2, 2)), ('Hill Giant', True, (3, 3))])
@pytest.mark.parametrize('pid', ['p1', 'p2'])
def test_half_copies_use_last_known_stats_and_are_created_by_targets_controller(cards, name, boost, expected, pid):
    from tests.game_helpers import act
    from tests.test_rules_attachments import ch
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Saw in Half', name, 'Giant Growth'], [name], [])
    creature = put(s, name, 'battlefield', pid)
    if boost:
        growth = put(s, 'Giant Growth', 'hand')
        mana(s, G=1)
        act(s, 'p1', type='cast_spell', card_id=growth.id, targets=[creature.id])
        settle(s)
    spell = put(s, 'Saw in Half', 'hand')
    mana(s, B=3)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[creature.id])
    settle(s)
    assert s.state.cards[creature.id].zone == f'{pid}:graveyard'
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone.endswith(':battlefield')]
    assert len(tokens) == 2
    assert {c.controller for c in tokens} == {pid}
    assert {c.owner for c in tokens} == {pid}
    assert {(int(ch(s, c).power), int(ch(s, c).toughness)) for c in tokens} == {expected}
    assert {ch(s, c).name for c in tokens} == {name}
    roundtrip(s)


@pytest.mark.parametrize('replacement', [False, True])
def test_no_tokens_when_creature_does_not_die(cards, replacement):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    name = 'Grizzly Bears' if replacement else 'Darksteel Myr'
    s = table(cards, ['Saw in Half', 'Rest in Peace'], [name], [])
    if replacement:
        put(s, 'Rest in Peace', 'battlefield')
    creature = put(s, name, 'battlefield', 'p2')
    spell = put(s, 'Saw in Half', 'hand')
    mana(s, B=3)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[creature.id])
    settle(s)
    assert s.state.cards[creature.id].zone == ('p2:exile' if replacement else 'p2:battlefield')
    assert not any(c.is_token for c in s.state.cards.values())
    roundtrip(s)


def test_negative_power_is_halved_with_signed_rounding(cards):
    from tests.game_helpers import act
    from tests.test_rules_attachments import ch
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Saw in Half', 'Disfigure'], ['Wall of Wood'], [])
    wall = put(s, 'Wall of Wood', 'battlefield', 'p2')
    disfigure = put(s, 'Disfigure', 'hand')
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=disfigure.id, targets=[wall.id])
    settle(s)
    assert ch(s, wall).pt == (-2, 1)
    spell = put(s, 'Saw in Half', 'hand')
    mana(s, B=3)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[wall.id])
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.is_token]
    assert len(tokens) == 2
    assert {ch(s, c).pt for c in tokens} == {(-1, 1)}
    assert all('defender' in ch(s, c).keywords for c in tokens)
    roundtrip(s)


def test_half_copies_of_token_use_last_known_recipe_after_source_ceases_to_exist(cards):
    from tests.game_helpers import act
    from tests.test_rules_attachments import ch
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Saw in Half'], [], [])
    source_data = cards.resolve('Llanowar Elves')
    act(s, 'p1', type='create_token', player='p2', token={'name': source_data['name'],
        'type_line': 'Token ' + source_data['type_line'], 'power': source_data['power'],
        'toughness': source_data['toughness'], 'text': source_data['oracle_text'], 'colors': ['G']})
    source = next(c for c in s.state.cards.values() if c.is_token)
    spell = put(s, 'Saw in Half', 'hand')
    mana(s, B=3)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id])
    settle(s)
    assert source.id not in s.state.cards
    tokens = [c for c in s.state.cards.values() if c.is_token]
    assert len(tokens) == 2
    assert {c.controller for c in tokens} == {'p2'}
    assert {ch(s, c).pt for c in tokens} == {(1, 1)}
    assert all(any('Add {G}' in a.text for a in ch(s, c).abilities) for c in tokens)
    roundtrip(s)


def test_copy_base_sizes_replace_characteristic_defining_ability(cards):
    from tests.game_helpers import act
    from tests.test_rules_attachments import ch
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Saw in Half'], ['Tarmogoyf'], [])
    put(s, 'Forest', 'graveyard')
    source = put(s, 'Tarmogoyf', 'battlefield', 'p2')
    assert ch(s, source).pt == (1, 2)
    spell = put(s, 'Saw in Half', 'hand')
    mana(s, B=3)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id])
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.is_token]
    assert len(tokens) == 2
    assert {ch(s, c).pt for c in tokens} == {(1, 1)}
    assert all(not any('power is equal' in a.text for a in ch(s, c).abilities) for c in tokens)
    roundtrip(s)
