"""Canonical collateral validation of a discarded-object sized counter payment."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Rites of Refusal'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ['reveal_hand_count_family_cards.json', 'rites_of_refusal_cards.json']:
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def answer(s, ids):
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    s.state = GameState.model_validate(s.state.model_dump(mode='json'))
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def setup(cards, *, exile=False, vanished=False):
    s = table(cards, [NAME, 'Counterspell', 'Giant Growth', 'Rest in Peace'], ['Grizzly Bears'])
    source = put(s, NAME, 'hand')
    hand = [put(s, n, 'hand').id for n in ['Counterspell', 'Giant Growth']]
    if exile:
        put(s, 'Rest in Peace', 'battlefield')
        settle(s)
    to_phase(s, 'main1', turn=2)
    wait_priority(s, 'p2')
    spell = put(s, 'Grizzly Bears', 'hand', 'p2')
    mana(s, 'p2', C=1, G=1)
    act(s, 'p2', type='set_prefs', hold_priority=True)
    act(s, 'p2', type='cast_spell', card_id=spell.id)
    wait_priority(s, 'p1')
    mana(s, C=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[spell.id])
    if vanished:
        act(s, 'p1', type='move', card_ids=[spell.id], to={'player': 'p2', 'zone': 'graveyard'})
    settle(s)
    return s, source, spell, hand


def test_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('n,payment', [(0, 'pay'), (0, 'decline'), (1, 'pay'), (1, 'decline'), (2, 'pay'), (2, 'unavailable')])
def test_actual_discard_count_sets_whole_payment(cards, n, payment):
    s, source, spell, hand = setup(cards)
    d = s.state.rules.decision
    assert d and d.player == 'p1' and d.min_choices == 0
    assert set(hand) <= {o.id for o in d.options} and source.id not in {o.id for o in d.options}
    assert s.view('p2')['rules']['decision']['kind'] == 'waiting'
    if payment != 'unavailable' and n:
        mana(s, 'p2', C=3*n)
    answer(s, hand[:n])
    assert all(s.state.cards[c].zone == 'p1:graveyard' for c in hand[:n])
    assert all(s.state.cards[c].zone == 'p1:hand' for c in hand[n:])
    if payment != 'unavailable':
        d = s.state.rules.decision
        assert d and d.player == 'p2' and d.display['cost'] == ('{0}' if n == 0 else f'{{{3*n}}}')
        answer(s, [payment])
    assert s.state.rules.decision is None
    assert s.state.cards[spell.id].zone == ('p2:battlefield' if payment == 'pay' else 'p2:graveyard')
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    if payment == 'pay':
        assert not mana_pool(s, 'p2')
    roundtrip(s)


def test_discard_to_exile_replacement_still_counts_discarded_cards(cards):
    s, _, spell, hand = setup(cards, exile=True)
    mana(s, 'p2', C=6)
    answer(s, hand)
    assert all(s.state.cards[c].zone == 'p1:exile' for c in hand)
    assert s.state.rules.decision.display['cost'] == '{6}'
    answer(s, ['pay'])
    assert s.state.cards[spell.id].zone == 'p2:battlefield'
    assert not mana_pool(s, 'p2')
    roundtrip(s)


def test_target_gone_before_resolution_does_not_discard(cards):
    s, source, spell, hand = setup(cards, vanished=True)
    assert s.state.rules.decision is None
    assert all(s.state.cards[c].zone == 'p1:hand' for c in hand)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[spell.id].zone == 'p2:graveyard'
    roundtrip(s)
