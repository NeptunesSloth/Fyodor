"""CR 701.57c, 400.7h, 608.2h: discover then inspect the discovered card."""
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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/discover_followup_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




NAME = 'Hit the Mother Lode'


def setup(cards, *, hit='Grizzly Bears', modifier=None):
    modifiers = list(modifier) if isinstance(modifier, tuple) else [modifier] if modifier else []
    deck = [NAME, *([hit] if hit else []), *[m for m in modifiers if m != 'Drannith Magistrate']]
    s = table(cards, deck, ['Drannith Magistrate'])
    for m in modifiers:
        put(s, m, 'battlefield', 'p2' if m == 'Drannith Magistrate' else 'p1')
    if hit:
        found = put(s, hit, 'hand')
        act(s, 'p1', type='move', card_ids=[found.id], to={'player': 'p1', 'zone': 'library'}, index=0)
    else:
        found = None
    source = put(s, NAME, 'hand')
    mana(s, C=4, R=3)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    return s, source, found


def treasure_count(s):
    tokens = [c for c in s.state.cards.values() if c.name == 'Treasure' and c.controller == 'p1']
    assert all(c.tapped for c in tokens)
    return sum(c.quantity for c in tokens)


def answer(s, option):
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option])


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('choice', ['yes', 'no'])
def test_treasures_follow_discover_and_are_not_available_before_cast_finishes(cards, choice):
    s, source, hit = setup(cards)
    assert treasure_count(s) == 0
    answer(s, choice)
    assert treasure_count(s) == 8
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[hit.id].zone == ('stack' if choice == 'yes' else 'p1:hand')
    roundtrip(s)
    settle(s)
    roundtrip(s)


def test_no_discovered_card_produces_no_treasures(cards):
    s, _, _ = setup(cards, hit=None)
    assert s.state.rules.decision is None
    assert treasure_count(s) == 0
    roundtrip(s)


def test_cards_too_expensive_are_not_discovered(cards):
    s, _, hit = setup(cards, hit='Darksteel Colossus')
    assert s.state.rules.decision is None
    assert s.state.cards[hit.id].zone == 'p1:library'
    assert treasure_count(s) == 0
    roundtrip(s)


@pytest.mark.parametrize('choice', ['yes', 'no'])
def test_discovered_mana_value_ten_produces_zero_treasures(cards, choice):
    s, _, _ = setup(cards, hit='Impervious Greatwurm')
    answer(s, choice)
    assert treasure_count(s) == 0
    roundtrip(s)


def test_cast_prohibition_puts_card_in_hand_then_creates_treasures(cards):
    s, _, hit = setup(cards, modifier='Drannith Magistrate')
    assert s.state.rules.decision is None
    assert s.state.cards[hit.id].zone == 'p1:hand'
    assert treasure_count(s) == 8
    roundtrip(s)


@pytest.mark.parametrize('choice,expected', [('yes', 6), ('yes@1', 3), ('no', 6)])
def test_adventure_cast_uses_public_spell_face_and_hand_uses_last_public_card_value(cards, choice, expected):
    s, _, hit = setup(cards, hit='Galvanic Giant // Storm Reading')
    answer(s, choice)
    assert treasure_count(s) == expected
    assert s.state.cards[hit.id].zone == ('p1:hand' if choice == 'no' else 'stack')
    roundtrip(s)


def test_future_treasures_cannot_pay_discovered_spells_mandatory_sacrifice_cost(cards):
    s, _, hit = setup(cards, hit='Shrapnel Blast')
    assert s.state.rules.decision is None  # no artifact exists to pay the mandatory cost
    assert s.state.cards[hit.id].zone == 'p1:hand'
    assert treasure_count(s) == 8
    roundtrip(s)


def test_following_token_creation_uses_shared_replacements(cards):
    s, _, _ = setup(cards, modifier='Doubling Season')
    answer(s, 'no')
    assert treasure_count(s) == 16
    roundtrip(s)


def test_cancelled_cast_goes_to_hand_then_continues_to_treasures(cards):
    s, source, hit = setup(cards, hit='Shrapnel Blast', modifier='Sol Ring')
    answer(s, 'yes')
    d = s.state.rules.decision
    assert d is not None and s.view('p1')['rules']['decision']['cancelable']
    assert treasure_count(s) == 0
    answer(s, 'cancel')
    assert s.state.rules.decision is None
    assert s.state.cards[hit.id].zone == 'p1:hand'
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert treasure_count(s) == 8
    assert any(c.name == 'Sol Ring' and c.zone == 'p1:battlefield' for c in s.state.cards.values())
    roundtrip(s)


@pytest.mark.parametrize('cast_ice,expected', [(False, 6), (True, 8)])
def test_split_card_hand_uses_combined_value_but_cast_half_uses_its_own_value(cards, cast_ice, expected):
    s, _, hit = setup(cards, hit='Fire // Ice', modifier='Sol Ring')
    answer(s, 'yes@1' if cast_ice else 'no')
    if cast_ice:
        assert treasure_count(s) == 0
        ring = next(c for c in s.state.cards.values() if c.name == 'Sol Ring' and c.zone == 'p1:battlefield')
        answer(s, ring.id)
        assert s.state.cards[hit.id].zone == 'stack'
    assert treasure_count(s) == expected
    roundtrip(s)


def test_following_token_replacement_order_preserves_discover_result_and_resolution(cards):
    s, source, hit = setup(cards, modifier=('Doubling Season', 'Peregrin Took'))
    answer(s, 'no')
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'replace_order'
    assert s.state.cards[hit.id].zone == 'p1:hand'
    assert s.state.cards[source.id].zone == 'stack'
    assert treasure_count(s) == 0
    first = next(o.id for o in d.options if o.label.startswith('Doubling Season first'))
    answer(s, first)
    assert treasure_count(s) == 16
    assert sum(c.quantity for c in s.state.cards.values() if c.name == 'Food') == 1
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)
