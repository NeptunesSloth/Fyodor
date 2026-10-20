"""CR 118.3, 122.1, 701.9a: alternative nouns in activation costs."""
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
from tests.test_rules_designations import build, put, roundtrip, settle


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/cost_noun_alternatives_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='cna', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('payment,valid', [('Mountain', True), ('Lightning Bolt', True), ('Sol Ring', False)])
def test_regulator_accepts_either_mountain_or_red_card(cards, payment, valid):
    assert coverage.of_card_data(cards.resolve("Chandra's Regulator")).level == 'FULL'
    s = build(cards, ["Chandra's Regulator", payment])
    source = put(s, "Chandra's Regulator", 'battlefield')
    c = put(s, payment, 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    before = len(s.state.zones['p1:hand'])
    if valid:
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, cost_choices=[{'component': 2, 'cards': [c.id]}])
        assert s.state.cards[c.id].zone == 'p1:graveyard'
        settle(s)
        assert len(s.state.zones['p1:hand']) == before
    else:
        snapshot = s.state.model_dump(mode='json')
        with pytest.raises(ActionError):
            act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, cost_choices=[{'component': 2, 'cards': [c.id]}])
        assert snapshot == s.state.model_dump(mode='json')
    roundtrip(s)


@pytest.mark.parametrize('kind', ['Artifact', 'Creature', 'Land', 'Planeswalker'])
def test_diviner_can_remove_a_counter_from_each_allowed_type(cards, kind):
    from tests.test_rules_wave34b_activated import next_turn

    assert coverage.of_card_data(cards.resolve('Soul Diviner')).level == 'FULL'
    s = build(cards, ['Soul Diviner', 'Gideon Jura'])
    source = put(s, 'Soul Diviner', 'battlefield')
    next_turn(s)
    if kind == 'Planeswalker':
        c = put(s, 'Gideon Jura', 'battlefield')
    else:
        act(s, 'p1', type='create_token', player='p1', token={'name': 'Payment', 'type_line': 'Token ' + kind, 'power': '2', 'toughness': '2'})
        c = next(c for c in s.state.cards.values() if c.name == 'Payment')
    act(s, 'p1', type='counter', card_ids=[c.id], kind='charge', delta=1)
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    if s.state.rules.decision:
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[next(o.id for o in d.options if 'charge' in o.label)])
    settle(s)
    assert s.state.cards[c.id].counters.get('charge', 0) == 0
    assert len(s.state.zones['p1:hand']) == before + 1
    roundtrip(s)


@pytest.mark.parametrize('pay', [True, False])
def test_regulator_loyalty_copy_still_works(cards, pay):
    from tests.test_rules_designations import pick
    from tests.test_rules_wave31d_spell_copies import hold

    s = build(cards, ["Chandra's Regulator", 'Chandra Nalaar'])
    put(s, "Chandra's Regulator", 'battlefield')
    chandra = put(s, 'Chandra Nalaar', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=chandra.id, kind='loyalty', value=6)
    hold(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='activate_ability', card_id=chandra.id, ability=0, targets=['p2'])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    pick(s, ['pay' if pay else 'decline'])
    settle(s)
    # Copying permits choosing new targets; retaining the original is legal.
    if s.state.rules.decision:
        d = s.state.rules.decision
        pick(s, [next(o.id for o in d.options if 'keep' in o.label.lower())])
        settle(s)
    assert s.state.players['p2'].life == (38 if pay else 39)
    assert s.state.cards[chandra.id].counters['loyalty'] == 7
    roundtrip(s)


@pytest.mark.parametrize('owner,kind,with_counter', [('p2', 'Artifact', True), ('p1', 'Enchantment', True), ('p1', 'Artifact', False)])
def test_diviner_rejects_ineligible_counter_payments(cards, owner, kind, with_counter):
    from app.rules import casting
    from tests.test_rules_wave34b_activated import next_turn

    s = build(cards, ['Soul Diviner'])
    source = put(s, 'Soul Diviner', 'battlefield')
    next_turn(s)
    act(s, owner, type='create_token', player=owner, token={'name': 'Payment', 'type_line': 'Token ' + kind})
    c = next(c for c in s.state.cards.values() if c.name == 'Payment')
    if with_counter:
        act(s, owner, type='counter', card_ids=[c.id], kind='charge', delta=1)
    assert not any(h['card_id'] == source.id for h in casting.activatable(s.state, 'p1', cards))
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    assert before == s.state.model_dump(mode='json')
    roundtrip(s)


def test_cost_alternatives_remain_conservative():
    from app.rules import costs, optional_payment

    text = 'Discard a Mountain card or a red card'
    c = costs.parse_ability_cost(text)
    assert not c.unsupported and c.activation_only
    assert optional_payment.parse(text) is None
    for text in ['Discard a Mountain card or a red card at random',
                 'Discard two Mountain cards or two red cards',
                 'Remove a counter from an artifact, mystery, land, or planeswalker you control']:
        assert costs.parse_ability_cost(text).unsupported
