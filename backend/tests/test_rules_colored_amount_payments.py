"""Colored optional mana amounts, including zero and reflexive source LKI."""
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
from tests.test_rules_conditionals import until_asked
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/colored_amount_payment_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




def setup(cards, red=0):
    s = table(cards, ['Leyline Tyrant', 'Dark Ritual', 'Mountain'], ['Murder', 'Stifle'], ['Shock', 'Grizzly Bears'])
    source = put(s, 'Leyline Tyrant', 'battlefield')
    if red:
        act(s, 'p1', type='add_mana', player='p1', mana={'R': red})
    act(s, 'p2', type='set_life', player='p2', value=200)
    spell = put(s, 'Murder', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'B': 2, 'C': 1})
    from tests.test_rules_bandmate_references import wait_priority
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[source.id], sources=[])
    until_asked(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    return s, source


def answer(s, amount):
    d = s.state.rules.decision
    assert d.options[0].id == '__number__'
    act(s, d.player, type='choose', decision_id=d.id, name=str(amount))


def target(s, who='p2'):
    d = s.state.rules.decision
    assert d and who in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[who])


def test_full(cards):
    assert coverage.of_card_data(cards.resolve('Leyline Tyrant')).level == 'FULL'


@pytest.mark.parametrize('amount', [0, 1, 73])
def test_paid_amount_becomes_reflexive_damage_after_source_died(cards, amount):
    from tests.game_helpers import mana_pool
    s, source = setup(cards, red=73)
    roundtrip(s)
    answer(s, amount)
    assert s.state.players['p2'].life == 200
    assert s.state.rules.decision is not None  # even paying zero creates the reflexive target choice
    target(s)
    roundtrip(s)
    settle(s)
    assert s.state.players['p2'].life == 200 - amount
    assert mana_pool(s).get('R', 0) == 73 - amount
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_pass_does_not_create_reflexive_target_choice(cards):
    from tests.game_helpers import mana_pool
    s, _ = setup(cards, red=73)
    answer(s, 'pass')
    assert s.state.rules.decision is None
    assert mana_pool(s).get('R') == 73
    assert s.state.players['p2'].life == 200
    roundtrip(s)


@pytest.mark.parametrize('amount', [74, 999999999])
def test_unaffordable_amount_rejected_without_paying_or_allocating_large_cost(cards, amount):
    from app.game.errors import ActionError
    s, _ = setup(cards, red=73)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError, match="can't pay"):
        answer(s, amount)
    assert s.state.model_dump(mode='json') == before
    answer(s, 0)
    target(s)
    settle(s)
    roundtrip(s)


def test_reflexive_ability_can_be_countered_after_red_is_paid(cards):
    from tests.game_helpers import mana_pool
    from tests.test_rules_bandmate_references import wait_priority
    s, _ = setup(cards, red=73)
    answer(s, 73)
    target(s)
    ability = next(iter(s.state.rules.stack))
    counter = put(s, 'Stifle', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[ability], sources=[])
    roundtrip(s)
    settle(s)
    assert s.state.players['p2'].life == 200
    assert mana_pool(s).get('R', 0) == 0
    assert not s.state.rules.stack
    roundtrip(s)


def test_other_colors_do_not_pay_red_amount(cards):
    from app.game.errors import ActionError
    s, _ = setup(cards)
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 73, 'C': 73})
    with pytest.raises(ActionError, match="can't pay"):
        answer(s, 1)
    answer(s, 'pass')
    roundtrip(s)


@pytest.mark.parametrize('value', ['-1', '1.5', '1000000000', 'red'])
def test_invalid_typed_number_leaves_payment_pending(cards, value):
    from app.game.errors import ActionError
    s, _ = setup(cards, red=73)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        answer(s, value)
    assert s.state.model_dump(mode='json') == before
    answer(s, 'pass')


def test_many_red_mana_payments_have_compact_log_and_payment_record(cards):
    from tests.game_helpers import mana_pool
    s, _ = setup(cards)
    for _ in range(3):
        act(s, 'p1', type='add_mana', player='p1', mana={'R': 100})
    answer(s, 300)
    target(s)
    settle(s)
    assert s.state.players['p2'].life == -100
    assert mana_pool(s).get('R', 0) == 0
    roundtrip(s)


def test_reflexive_uses_dead_source_after_its_graveyard_card_moves(cards):
    s, source = setup(cards, red=73)
    answer(s, 73)
    target(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    roundtrip(s)
    settle(s)
    assert s.state.players['p2'].life == 127
    assert s.state.cards[source.id].zone == 'p1:exile'
    roundtrip(s)


@pytest.mark.parametrize("manual", [False, True])
def test_can_tap_red_mana_source_while_number_prompt_is_pending(cards, manual):
    from tests.game_helpers import mana_pool
    s, _ = setup(cards)
    land = put(s, 'Mountain', 'battlefield')
    if manual:
        act(s, 'p1', type='activate_ability', card_id=land.id, ability=0)
        assert s.state.cards[land.id].tapped
        assert s.state.rules.decision.options[0].id == '__number__'
    answer(s, 1)
    target(s)
    settle(s)
    assert s.state.players['p2'].life == 199
    assert mana_pool(s).get('R', 0) == 0
    roundtrip(s)
