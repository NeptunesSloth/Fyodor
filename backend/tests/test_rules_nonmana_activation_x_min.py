"""CR 107.3/602.2: minimum announced nonmana X uses native sacrifice costs."""
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
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

NAME = 'Ruthless Technomancer'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/nonmana_activation_x_min_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='nax', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s = table(cards, [NAME, 'Sol Ring', 'Sol Ring', 'Ornithopter', 'Grizzly Bears'], ['Swords to Plowshares'])
    source = put(s, NAME, 'battlefield')
    settle(s)
    assert s.state.rules.decision is None
    junk = [put(s, n, 'battlefield') for n in ['Sol Ring', 'Ornithopter']]
    target = put(s, 'Grizzly Bears', 'graveyard')
    mana(s, C=2, B=1)
    return s, source, junk, target


def activate(s, source, junk, target, x):
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1,
        targets=[target.id], x_value=x, cost_choices=[{'component': 1, 'cards': [c.id for c in junk]}])


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('x', [None, 0, 1])
def test_missing_zero_or_insufficient_target_power_x_is_rejected_before_payment(cards, x):
    s, source, junk, target = setup(cards)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        activate(s, source, junk[:x or 0], target, x)
    assert s.state.model_dump(mode='json') == before
    assert mana_pool(s, 'p1') == {'C': 2, 'B': 1}
    roundtrip(s)


def test_two_artifacts_pay_exact_x_and_return_power_two_target(cards):
    s, source, junk, target = setup(cards)
    activate(s, source, junk, target, 2)
    assert all(s.state.cards[c.id].zone == 'p1:graveyard' for c in junk)
    assert mana_pool(s, 'p1') == {}
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_zero_x_rejected_even_with_a_zero_power_legal_target(cards):
    s, source, junk, _ = setup(cards)
    target = junk[1]
    act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p1', 'zone': 'graveyard'})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        activate(s, source, [], target, 0)
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_target_leaving_graveyard_fizzles_after_artifacts_paid(cards):
    s, source, junk, target = setup(cards)
    activate(s, source, junk, target, 2)
    act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    assert all(s.state.cards[c.id].zone == 'p1:graveyard' for c in junk)
    assert s.state.cards[target.id].zone == 'p1:exile'
    roundtrip(s)


def test_source_can_leave_without_changing_announced_x(cards):
    s, source, junk, target = setup(cards)
    activate(s, source, junk, target, 2)
    wait_priority(s, 'p2')
    removal = put(s, 'Swords to Plowshares', 'hand', 'p2')
    mana(s, 'p2', W=1)
    act(s, 'p2', type='cast_spell', card_id=removal.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:exile'
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_native_sacrifice_prompt_saves_announced_x_and_target(cards):
    s, source, junk, target = setup(cards)
    spare = next(c for c in s.state.cards.values() if c.name == 'Sol Ring' and c.id != junk[0].id)
    act(s, 'p1', type='move', card_ids=[spare.id], to={'player': 'p1', 'zone': 'battlefield'})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[target.id], x_value=2)
    d = s.state.rules.decision
    assert d is not None and d.kind == 'choose_cards'
    assert d.min_choices == 0 and d.max_choices == 2
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[junk[0].id])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[c.id for c in junk])
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_positive_minimum_x_can_return_a_zero_power_creature(cards):
    s, source, junk, _ = setup(cards)
    target = junk[1]
    act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p1', 'zone': 'graveyard'})
    activate(s, source, [junk[0]], target, 1)
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.cards[junk[0].id].zone == 'p1:graveyard'
    roundtrip(s)
