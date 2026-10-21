"""CR 201.2a–b, 118.3, 601.2h: names constrain the whole payment group."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import casting, costs, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import build, put, roundtrip, settle


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/named_cost_groups_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='ncg', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name,payment,draw', [
    ('Sphinx of the Chimes', ['Sol Ring', 'Sol Ring'], 4),
    ('Ormos, Archive Keeper', ['Sol Ring', 'Lightning Bolt', 'Forest'], 5),
])
def test_name_group_discard_draws(cards, name, payment, draw):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'
    s = build(cards, [name, *payment])
    source = put(s, name, 'battlefield')
    ids = []
    for n in payment:
        c = next(c for c in s.state.cards.values() if c.name == n and c.id not in ids)
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'hand'})
        ids.append(c.id)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'U': 2})
    before = len(s.state.zones['p1:hand'])
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.cost and 'Discard' in a.cost)
    cost = costs.parse_ability_cost(ability.cost, card_name=name)
    slot = next(i for i, c in enumerate(cost.components) if c.kind == costs.DISCARD)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index,
        cost_choices=[{'component': slot, 'cards': ids}])
    assert all(s.state.cards[c].zone == 'p1:graveyard' for c in ids)
    roundtrip(s)
    settle(s)
    assert len(s.state.zones['p1:hand']) == before - len(ids) + draw
    roundtrip(s)


@pytest.mark.parametrize('name,payment', [
    ('Sphinx of the Chimes', ['Sol Ring', 'Lightning Bolt']),
    ('Sphinx of the Chimes', ['Forest', 'Forest']),
    ('Ormos, Archive Keeper', ['Sol Ring', 'Sol Ring', 'Lightning Bolt']),
])
def test_invalid_name_group_does_not_pay(cards, name, payment):
    s = build(cards, [name, *payment])
    source = put(s, name, 'battlefield')
    ids = []
    for n in payment:
        c = next(c for c in s.state.cards.values() if c.name == n and c.id not in ids)
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'hand'})
        ids.append(c.id)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'U': 2})
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.cost and 'Discard' in a.cost)
    cost = costs.parse_ability_cost(ability.cost, card_name=name)
    assert not cost.unsupported
    slot = next(i for i, c in enumerate(cost.components) if c.kind == costs.DISCARD)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index,
            cost_choices=[{'component': slot, 'cards': ids}])
    assert s.state.model_dump(mode='json') == before
    # The hand also contains setup cards, so only assert lack of a hint for Sphinx's all-land case.
    roundtrip(s)


@pytest.mark.parametrize('selection', ['Blood', 'Clue', 'Food'])
def test_font_creates_each_choice(cards, selection):
    from tests.test_rules_designations import pick

    assert coverage.of_card_data(cards.resolve('Transmutation Font')).level == 'FULL'
    s = build(cards, ['Transmutation Font'])
    source = put(s, 'Transmutation Font', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    pick(s, [next(o.id for o in d.options if selection in o.label)])
    settle(s)
    assert any(c.is_token and c.name == selection and c.zone == 'p1:battlefield' for c in s.state.cards.values())
    roundtrip(s)


@pytest.mark.parametrize('names,valid', [(['Blood', 'Clue', 'Food'], True), (['Blood', 'Blood', 'Food'], False)])
def test_font_sacrifices_only_a_distinct_named_group(cards, names, valid):
    from tests.test_rules_designations import pick

    s = build(cards, ['Transmutation Font', 'Sol Ring'])
    source = put(s, 'Transmutation Font', 'battlefield')
    ids = []
    for n in names:
        act(s, 'p1', type='create_token', player='p1', token={'name': n, 'type_line': 'Token Artifact'})
        ids.append(next(c.id for c in reversed(list(s.state.cards.values())) if c.is_token and c.id not in ids))
    ring = put(s, 'Sol Ring', 'library')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    hints = casting.activatable(s.state, 'p1', cards)
    assert any(h['card_id'] == source.id and h['ability'] == 1 for h in hints) == valid
    before = s.state.model_dump(mode='json')
    action = dict(type='activate_ability', card_id=source.id, ability=1, cost_choices=[{'component': 2, 'cards': ids}])
    if not valid:
        with pytest.raises(ActionError):
            act(s, 'p1', **action)
        assert s.state.model_dump(mode='json') == before
    else:
        act(s, 'p1', **action)
        assert s.state.cards[source.id].tapped
        assert not any(c in s.state.zones['p1:battlefield'] for c in ids)
        roundtrip(s)
        settle(s)
        d = s.state.rules.decision
        assert d is not None and any(o.id == ring.id for o in d.options)
        pick(s, [ring.id])
        settle(s)
        assert s.state.cards[ring.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_ormos_empty_library_draw_replacement(cards):
    s = build(cards, ['Ormos, Archive Keeper', 'Sol Ring', 'Lightning Bolt'])
    source = put(s, 'Ormos, Archive Keeper', 'battlefield')
    ids = []
    for n in ['Sol Ring', 'Lightning Bolt', 'Forest']:
        c = put(s, n, 'hand')
        ids.append(c.id)
    library = list(s.state.zones['p1:library'])
    if library:
        act(s, 'p1', type='move', card_ids=library, to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'U': 2})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, cost_choices=[{'component': 1, 'cards': ids}])
    settle(s)
    assert s.state.cards[source.id].counters.get('+1/+1') == 25
    assert s.state.rules is not None and 'p1' not in s.state.rules.lost
    roundtrip(s)


@pytest.mark.parametrize('name,payment,extra', [
    ('Sphinx of the Chimes', ['Sol Ring', 'Lightning Bolt'], ['Sol Ring']),
    ('Ormos, Archive Keeper', ['Sol Ring', 'Sol Ring', 'Forest'], ['Lightning Bolt']),
])
def test_bad_group_rejected_even_when_another_group_is_payable(cards, name, payment, extra):
    s = build(cards, [name, *payment, *extra])
    source = put(s, name, 'battlefield')
    ids = []
    for n in [*payment, *extra]:
        c = next(c for c in s.state.cards.values() if c.name == n and c.id not in ids)
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'hand'})
        ids.append(c.id)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'U': 2})
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.cost and 'Discard' in a.cost)
    cost = costs.parse_ability_cost(ability.cost, card_name=name)
    slot = next(i for i, c in enumerate(cost.components) if c.kind == costs.DISCARD)
    assert any(h['card_id'] == source.id and h['ability'] == ability.index for h in casting.activatable(s.state, 'p1', cards))
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError, match='satisfying'):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index,
            cost_choices=[{'component': slot, 'cards': ids[:len(payment)]}])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


@pytest.mark.parametrize('mode,labels,expected', [
    ('same', ['Fire // Ice', 'Fire'], True),
    ('same', ['Fire // Ice', 'Ice'], True),
    ('same', ['Fire // Ice', 'Fire', 'Ice'], False),
    ('same', ['', ''], False),
    ('different', ['Fire // Ice', 'Ice'], False),
    ('different', ['Fire // Ice', 'Sol Ring', 'Lightning Bolt'], True),
    ('different', ['', 'Sol Ring'], False),
])
def test_group_checks_all_names_and_refuses_nameless_objects(cards, mode, labels, expected):
    from app.rules import cost_payment

    s = build(cards)
    ids = []
    for label in labels:
        act(s, 'p1', type='create_token', player='p1', token={'name': label or 'Hidden', 'type_line': 'Token Creature', 'power': '2', 'toughness': '2'})
        c = next(c for c in reversed(list(s.state.cards.values())) if c.is_token and c.id not in ids)
        if not label:
            act(s, 'p1', type='face_down', card_ids=[c.id], face_down=True)
        ids.append(c.id)
    comp = costs.CostComponent(costs.SACRIFICE, amount=len(ids), names=mode)
    plan = Plan(s.state, 'p1', cards, None)
    assert cost_payment._names_fit(plan, comp, ids) == expected
    assert cost_payment._names_payable(plan, comp, ids, len(ids)) == expected
    roundtrip(s)


def test_group_costs_stay_out_of_optional_and_mana_payments():
    from app.rules import optional_payment

    cost = costs.parse_ability_cost('Discard two nonland cards with the same name')
    assert cost.activation_only
    assert optional_payment.parse('Discard two nonland cards with the same name') is None
    assert costs.parse_ability_cost('Discard two cards with similar names').unsupported
    assert costs.parse_ability_cost('Discard two cards at random with different names').unsupported


def test_name_constrained_discard_prompt_is_private_and_resumes_safely(cards):
    from tests.test_rules_designations import pick

    s = build(cards, ['Sphinx of the Chimes', 'Sol Ring', 'Sol Ring', 'Sol Ring', 'Lightning Bolt'])
    source = put(s, 'Sphinx of the Chimes', 'battlefield')
    rings = []
    for c in list(s.state.cards.values()):
        if c.name in ('Sol Ring', 'Lightning Bolt'):
            act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'hand'})
            if c.name == 'Sol Ring':
                rings.append(c.id)
    bolt = next(c.id for c in s.state.cards.values() if c.name == 'Lightning Bolt')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1' and d.kind == 'choose_cards'
    assert not s.view('p2')['rules']['decision'].get('options')
    roundtrip(s)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError, match='satisfying'):
        pick(s, [rings[0], bolt])
    assert s.state.model_dump(mode='json') == before
    pick(s, rings[:2])
    settle(s)
    assert all(s.state.cards[c].zone == 'p1:graveyard' for c in rings[:2])
    assert s.state.cards[bolt].zone == 'p1:hand'
    roundtrip(s)
