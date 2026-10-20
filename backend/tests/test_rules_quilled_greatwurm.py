"""Quilled Greatwurm pays six individual counters as well as its normal mana cost."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import costs, coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

NAME = 'Quilled Greatwurm'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/quilled_greatwurm_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, *, counters=6):
    s = table(cards, [NAME, 'Grizzly Bears', 'Everflowing Chalice', 'Dress Down'], ['Grizzly Bears', 'Counterspell'])
    worm = put(s, NAME, 'graveyard')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    if counters:
        act(s, 'p1', type='counter', card_ids=[bear.id], kind='+1/+1', delta=counters)
    return s, worm, bear


def pay_cast(s, worm, **kw):
    act(s, 'p1', type='cast_spell', card_id=worm.id, targets=[], **kw)


def test_full_and_additional_grammar_remains_bounded(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'
    cost = costs.parse_additional_cost('remove six counters from among creatures you control')
    assert cost and cost.components[0].among and cost.components[0].counter == costs.ANY_COUNTER
    for text in ('remove six counters from this creature', 'remove X counters from among creatures you control',
                 'remove any number of counters from among creatures you control'):
        assert costs.parse_additional_cost(text) is None


def test_normal_mana_plus_exact_counters_and_replay(cards):
    s, worm, bear = setup(cards)
    mana(s, G=2, C=4)
    pay_cast(s, worm)
    assert s.state.cards[bear.id].counters.get('+1/+1', 0) == 0
    assert mana_pool(s, 'p1') == {}
    settle(s)
    assert s.state.cards[worm.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_mixed_types_on_multiple_creatures_choose_six_and_save_pending(cards):
    s, worm, bear = setup(cards, counters=3)
    # A second eligible creature with a different counter kind.
    other = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.name == 'Grizzly Bears')
    act(s, 'p1', type='move', card_ids=[other.id], to={'player': 'p1', 'zone': 'battlefield'})
    act(s, 'p1', type='set_controller', card_ids=[other.id], player='p1')
    act(s, 'p1', type='counter', card_ids=[other.id], kind='vigilance', delta=4)
    mana(s, G=2, C=4)
    pay_cast(s, worm)
    d = s.state.rules.decision
    assert d and len(d.options) == 7
    roundtrip(s)
    assert all(o.card_id in (bear.id, other.id) for o in d.options)
    selected = [o.id for o in d.options if o.card_id == bear.id] + [o.id for o in d.options if o.card_id == other.id][:3]
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=selected)
    settle(s)
    assert s.state.cards[bear.id].counters.get('+1/+1', 0) == 0
    assert s.state.cards[other.id].counters['vigilance'] == 1
    assert s.state.cards[worm.id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('shortage', ['counters', 'mana'])
def test_cannot_partially_pay_when_missing_mana_or_counters(cards, shortage):
    s, worm, bear = setup(cards, counters=5 if shortage == 'counters' else 6)
    mana(s, G=2, C=4 if shortage == 'counters' else 3)
    before = dict(mana_pool(s, 'p1'))
    with pytest.raises(ActionError):
        pay_cast(s, worm)
    assert s.state.cards[bear.id].counters['+1/+1'] == (5 if shortage == 'counters' else 6)
    assert mana_pool(s, 'p1') == before
    assert s.state.cards[worm.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_opponent_and_noncreature_counters_do_not_pay(cards):
    s, worm, _ = setup(cards, counters=0)
    other = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    chalice = put(s, 'Everflowing Chalice', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[other.id, chalice.id], kind='charge', delta=6)
    mana(s, G=2, C=4)
    with pytest.raises(ActionError):
        pay_cast(s, worm)
    assert s.state.cards[other.id].counters['charge'] == 6
    assert s.state.cards[chalice.id].counters['charge'] == 6
    roundtrip(s)


def test_hand_cast_does_not_remove_counters(cards):
    s, worm, bear = setup(cards)
    act(s, 'p1', type='move', card_ids=[worm.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, G=2, C=4)
    pay_cast(s, worm)
    settle(s)
    assert s.state.cards[bear.id].counters['+1/+1'] == 6
    assert s.state.cards[worm.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_countering_spell_does_not_refund_payment_and_next_cast_pays_again(cards):
    s, worm, bear = setup(cards, counters=12)
    mana(s, G=2, C=4)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    pay_cast(s, worm)
    d = s.state.rules.decision
    if d:
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[o.id for o in d.options][:6])
    counter = put(s, 'Counterspell', 'hand', pid='p2')
    # Let the opponent answer the first cast.
    act(s, 'p1', type='pass_priority')
    mana(s, pid='p2', U=2)
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[worm.id])
    settle(s)
    assert s.state.cards[worm.id].zone == 'p1:graveyard'
    assert s.state.cards[bear.id].counters['+1/+1'] == 6
    mana(s, G=2, C=4)
    pay_cast(s, worm)
    settle(s)
    assert s.state.cards[worm.id].zone == 'p1:battlefield'
    assert s.state.cards[bear.id].counters.get('+1/+1', 0) == 0
    roundtrip(s)


def test_graveyard_permission_keeps_normal_sorcery_timing(cards):
    s, worm, bear = setup(cards)
    counter = put(s, 'Dress Down', 'hand')
    mana(s, U=1, G=2, C=5)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='cast_spell', card_id=counter.id, targets=[])
    with pytest.raises(ActionError):
        pay_cast(s, worm)
    assert s.state.cards[bear.id].counters['+1/+1'] == 6
    settle(s)
    # Dress Down affects creatures on the battlefield, not this card in the graveyard.
    pay_cast(s, worm)
    settle(s)
    assert s.state.cards[worm.id].zone == 'p1:battlefield'
    roundtrip(s)
