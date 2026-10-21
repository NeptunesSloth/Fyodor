"""CR 701.21a / 608.2h: types of the creatures sacrificed to pay for an ability."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/sacrificed_kind_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Thallid Omnivore', 'Boneyard Desecrator'])
def test_sacrificed_kind_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def activate(s, source, payment):
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'B': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1 if source.name == 'Boneyard Desecrator' else 0,
        cost_choices=[{'component': 1, 'cards': [payment.id]}])


@pytest.mark.parametrize('name', ['Thallid Omnivore', 'Boneyard Desecrator'])
@pytest.mark.parametrize('payment', ['Grizzly Bears', 'Changeling Outcast'])
def test_cost_sacrificed_kind_uses_the_paid_creatures_last_characteristics(cards, name, payment):
    from app.rules.plan import Plan
    from tests.test_rules_wave5j_token_copies import tokens

    s = table(cards, [name, payment])
    source = put(s, name, 'battlefield')
    paid = put(s, payment, 'battlefield')
    activate(s, source, paid)
    assert paid.id in s.state.zones['p1:graveyard']
    roundtrip(s)
    settle(s)
    qualifies = payment == 'Changeling Outcast'
    if name == 'Thallid Omnivore':
        assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).pt == (5, 5)
        assert s.state.players['p1'].life == (42 if qualifies else 40)
    else:
        assert s.state.cards[source.id].counters['+1/+1'] == 1
        assert len([c for c in tokens(s) if c.name == 'Treasure']) == int(qualifies)
    roundtrip(s)


def test_saproling_token_payment_is_remembered_after_the_token_ceases_to_exist(cards):
    from tests.test_rules_wave5j_token_copies import tokens

    s = table(cards, ['Thallid Omnivore', 'Saproling Migration'])
    source = put(s, 'Thallid Omnivore', 'battlefield')
    migration = put(s, 'Saproling Migration', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'G': 1})
    act(s, 'p1', type='cast_spell', card_id=migration.id, targets=[])
    settle(s)
    paid = next(c for c in tokens(s) if c.name == 'Saproling')
    activate(s, source, paid)
    assert paid.id not in s.state.cards
    roundtrip(s)
    settle(s)
    assert s.state.players['p1'].life == 42
    roundtrip(s)


def test_each_pending_activation_reads_its_own_sacrificed_creature(cards):
    s = table(cards, ['Thallid Omnivore', 'Changeling Outcast', 'Grizzly Bears'])
    source = put(s, 'Thallid Omnivore', 'battlefield')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    first = put(s, 'Changeling Outcast', 'battlefield')
    second = put(s, 'Grizzly Bears', 'battlefield')
    activate(s, source, first)
    activate(s, source, second)
    roundtrip(s)
    settle(s)
    assert s.state.players['p1'].life == 42
    roundtrip(s)


@pytest.mark.parametrize('source_leaves', [False, True])
def test_sacrifice_trigger_condition_survives_the_source_leaving(cards, source_leaves):
    from tests.test_rules_wave5j_token_copies import tokens

    s = table(cards, ['Boneyard Desecrator', 'Changeling Outcast'])
    source = put(s, 'Boneyard Desecrator', 'battlefield')
    paid = put(s, 'Changeling Outcast', 'battlefield')
    activate(s, source, paid)
    if source_leaves:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert len([c for c in tokens(s) if c.name == 'Treasure']) == 1
    roundtrip(s)


def test_an_aura_can_remove_the_sacrificed_creatures_qualifying_type(cards):
    from tests.test_rules_wave5j_token_copies import tokens

    s = table(cards, ['Boneyard Desecrator', 'Changeling Outcast', 'Lignify'])
    source = put(s, 'Boneyard Desecrator', 'battlefield')
    paid = put(s, 'Changeling Outcast', 'battlefield')
    aura = put(s, 'Lignify', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'G': 1})
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[paid.id])
    settle(s)
    activate(s, source, paid)
    settle(s)
    assert s.state.cards[source.id].counters['+1/+1'] == 1
    assert not [c for c in tokens(s) if c.name == 'Treasure']
    roundtrip(s)


def test_only_battlefield_type_changes_are_used_for_the_payment(cards):
    s = table(cards, ['Thallid Omnivore', 'Grizzly Bears', 'Arcane Adaptation'])
    source = put(s, 'Thallid Omnivore', 'battlefield')
    paid = put(s, 'Grizzly Bears', 'battlefield')
    adaptation = put(s, 'Arcane Adaptation', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'U': 1})
    act(s, 'p1', type='cast_spell', card_id=adaptation.id, targets=[])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['Saproling'])
    settle(s)
    activate(s, source, paid)
    # Remove the granting effect before the ability resolves: use the paid object's snapshot.
    act(s, 'p1', type='move', card_ids=[adaptation.id], to={'player': 'p1', 'zone': 'graveyard'})
    roundtrip(s)
    settle(s)
    assert s.state.players['p1'].life == 42
    roundtrip(s)


@pytest.mark.parametrize('name', ['Thallid Omnivore', 'Boneyard Desecrator'])
def test_a_replacement_exiling_the_sacrificed_card_does_not_undo_the_payment(cards, name):
    from tests.test_rules_wave5j_token_copies import tokens

    s = table(cards, [name, 'Changeling Outcast', 'Rest in Peace'])
    source = put(s, name, 'battlefield')
    paid = put(s, 'Changeling Outcast', 'battlefield')
    put(s, 'Rest in Peace', 'battlefield')
    activate(s, source, paid)
    assert paid.id in s.state.zones['p1:exile']
    roundtrip(s)
    settle(s)
    if name == 'Thallid Omnivore':
        assert s.state.players['p1'].life == 42
    else:
        assert len([c for c in tokens(s) if c.name == 'Treasure']) == 1
    roundtrip(s)


def test_effect_sacrifices_and_distinct_alternative_cost_choices_remain_manual(cards):
    from app.rules import conditions

    assert conditions.parse('a Saproling was sacrificed this way') is None
    assert coverage.of_card_data(cards.resolve('Tyrant of Discord')).level == 'PARTIAL'
    assert coverage.of_card_data(cards.resolve('Lethal Throwdown')).level == 'PARTIAL'
