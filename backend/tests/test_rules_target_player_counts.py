"""CR 608.2d, 701.13, 202.3: opponent choices and milled-card mana values."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/target_player_count_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_full(cards):
    assert coverage.of_card_data(cards.resolve('Call the Coppercoats')).level == 'FULL'


def setup(cards, counts=(1, 2, 3), *, doubling=False):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Call the Coppercoats', 'Sol Ring', 'Doubling Season'], ['Leyline of Sanctity'], ['Leyline of Sanctity'])
    for pid, count in zip(['p1', 'p2', 'p3'], counts, strict=True):
        for _ in range(count):
            act(s, pid, type='create_token', player=pid, token={'name': 'Soldier', 'type_line': 'Token Creature — Soldier',
                'power': '1', 'toughness': '1', 'colors': ['W'], 'text': ''})
    put(s, 'Sol Ring', 'battlefield')
    if doubling:
        put(s, 'Doubling Season', 'battlefield')
    return s, put(s, 'Call the Coppercoats', 'hand')


def cast(s, source, targets):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    extra = max(0, len(targets)-1)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2+extra, 'W': 1+extra})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=targets, target_counts=[len(targets)])
    roundtrip(s)
    assert not any(s.state.players['p1'].mana.values())


def soldiers(s):
    return [c for c in s.state.cards.values() if c.controller == 'p1' and c.zone == 'p1:battlefield' and c.name == 'Human Soldier']


@pytest.mark.parametrize('targets,total', [([], 0), (['p2'], 2), (['p3'], 3), (['p2', 'p3'], 5)])
def test_any_number_of_opponents_and_strive_cost(cards, targets, total):
    from tests.test_rules_designations import roundtrip, settle

    s, source = setup(cards)
    cast(s, source, targets)
    settle(s)
    assert len(soldiers(s)) == total
    for c in soldiers(s):
        from tests.test_rules_wave6c_tokens_pumps import chars
        assert c.token and chars(s, c).pt == (1, 1)
    roundtrip(s)


def test_creature_count_is_read_on_resolution(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, source = setup(cards)
    cast(s, source, ['p2', 'p3'])
    creature = next(c for c in s.state.cards.values() if c.controller == 'p2' and c.token)
    act(s, 'p1', type='move', card_ids=[creature.id], to={'player': 'p2', 'zone': 'graveyard'})
    settle(s)
    assert len(soldiers(s)) == 4
    roundtrip(s)


@pytest.mark.parametrize('illegal', [['p2'], ['p2', 'p3']])
def test_only_still_legal_targeted_opponents_are_counted(cards, illegal):
    from tests.test_rules_designations import put, roundtrip, settle

    s, source = setup(cards)
    cast(s, source, ['p2', 'p3'])
    for pid in illegal:
        put(s, 'Leyline of Sanctity', 'battlefield', pid)
    settle(s)
    assert len(soldiers(s)) == (3 if illegal == ['p2'] else 0)
    roundtrip(s)


def test_token_replacement_doubles_combined_count(cards):
    from tests.test_rules_designations import roundtrip, settle

    s, source = setup(cards, doubling=True)
    cast(s, source, ['p2', 'p3'])
    settle(s)
    assert len(soldiers(s)) == 10
    roundtrip(s)


def test_cannot_target_yourself(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, source = setup(cards)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'W': 1})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p1'], target_counts=[1])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_second_target_requires_strive_payment(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, source = setup(cards)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'W': 1})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2', 'p3'], target_counts=[2])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)
