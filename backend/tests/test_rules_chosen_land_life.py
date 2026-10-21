"""An entering land chooses its basic land type before the life payment."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

NAME = 'Multiversal Passage'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/chosen_land_life_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='cll', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def begin(cards, permanent=None, life=None):
    s = table(cards, [NAME, 'Blood Moon', 'Amulet of Vigor', 'Spelunking', 'Dryad of the Ilysian Grove',
                      'Yasharn, Implacable Earth', 'Platinum Emperion', 'Vesuva', 'Exploration'], [])
    if permanent:
        put(s, permanent, 'battlefield')
    if life is not None:
        act(s, 'p1', type='set_life', player='p1', value=life)
    land = put(s, NAME, 'hand')
    act(s, 'p1', type='play_land', card_id=land.id)
    return s, land


def choose(s, option):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option])
    roundtrip(s)


def test_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('kind,color', [('Plains', 'W'), ('Island', 'U'), ('Swamp', 'B'), ('Mountain', 'R'), ('Forest', 'G')])
@pytest.mark.parametrize('pay', [False, True])
def test_choose_type_then_pay_and_use_intrinsic_mana(cards, kind, color, pay):
    s, land = begin(cards)
    assert s.state.cards[land.id].zone == 'p1:hand' and s.state.players['p1'].life == 40
    choose(s, kind)
    assert s.state.cards[land.id].zone == 'p1:hand'
    assert {o.id for o in s.state.rules.decision.options} == {'pay', 'tapped'}
    choose(s, 'pay' if pay else 'tapped')
    c = s.state.cards[land.id]
    assert c.zone == 'p1:battlefield' and c.tapped == (not pay)
    assert c.choices['Chosen basic land type'] == kind
    assert s.state.players['p1'].life == (38 if pay else 40)
    ch = Plan(s.state, 'p1', cards, None).ch(c)
    assert ch.subtypes == {kind} and 'Basic' not in ch.supertypes
    if pay:
        ability = next(a.index for a in ch.abilities if a.kind == 'mana')
        act(s, 'p1', type='activate_ability', card_id=land.id, ability=ability)
        assert mana_pool(s, 'p1') == {color: 1}
    roundtrip(s)


def test_blood_moon_removes_both_own_abilities_before_entry(cards):
    s, land = begin(cards, 'Blood Moon')
    assert s.state.rules.decision is None
    assert s.state.cards[land.id].zone == 'p1:battlefield' and not s.state.cards[land.id].tapped
    assert not s.state.cards[land.id].choices and s.state.players['p1'].life == 40
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[land.id]).subtypes == {'Mountain'}
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_spelunking_allows_optional_payment_even_though_land_will_be_untapped(cards, pay):
    s, land = begin(cards, 'Spelunking')
    choose(s, 'Island')
    choose(s, 'pay' if pay else 'tapped')
    settle(s)
    assert not s.state.cards[land.id].tapped
    assert s.state.players['p1'].life == (38 if pay else 40)
    roundtrip(s)


@pytest.mark.parametrize('permanent,life', [(None, 1), ('Platinum Emperion', 40)])
def test_cannot_pay_life_still_chooses_type_and_enters_tapped(cards, permanent, life):
    s, land = begin(cards, permanent, life)
    choose(s, 'Forest')
    assert s.state.rules.decision is None and s.state.cards[land.id].tapped
    assert s.state.players['p1'].life == life
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[land.id]).subtypes == {'Forest'}
    roundtrip(s)


def test_yasharn_does_not_prohibit_life_payment_for_an_entry_replacement(cards):
    s, land = begin(cards, 'Yasharn, Implacable Earth')
    choose(s, 'Island')
    choose(s, 'pay')
    assert s.state.players['p1'].life == 38 and not s.state.cards[land.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('early', [False, True])
def test_subtype_defining_ability_precedes_dryad_regardless_of_timestamp(cards, early):
    s, land = begin(cards, 'Dryad of the Ilysian Grove' if early else None)
    choose(s, 'Island')
    choose(s, 'pay')
    if not early:
        put(s, 'Dryad of the Ilysian Grove', 'battlefield')
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[land.id])
    assert ch.subtypes == {'Plains', 'Island', 'Swamp', 'Mountain', 'Forest'}
    assert len([a for a in ch.abilities if a.kind == 'mana']) == 5
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_reclaimer_putting_land_in_tapped_still_allows_optional_life_payment(cards, pay):
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, [NAME, 'Elvish Reclaimer', 'Forest'], [])
    reclaimer = put(s, 'Elvish Reclaimer', 'battlefield')
    put(s, 'Forest', 'battlefield')
    to_phase(s, 'main1', turn=4)
    put(s, NAME, 'library')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[reclaimer.id])
    index = next(a.index for a in ch.abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=reclaimer.id, ability=index)
    # The cost may ask which land to sacrifice before the search resolves.
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    target = next(o for o in d.options if o.card_id and s.state.cards[o.card_id].name == NAME)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[target.id])
    choose(s, 'Swamp')
    assert 'tapped either way' in s.state.rules.decision.prompt
    choose(s, 'pay' if pay else 'tapped')
    settle(s)
    assert s.state.cards[target.card_id].tapped
    assert s.state.players['p1'].life == (38 if pay else 40)
    roundtrip(s)


@pytest.mark.parametrize('payment', ['pay', 'tapped'])
def test_vesuva_copies_rules_but_makes_its_own_type_choice(cards, payment):
    s, original = begin(cards)
    choose(s, 'Island')
    choose(s, 'pay')
    put(s, 'Exploration', 'battlefield')
    copy = put(s, 'Vesuva', 'hand')
    act(s, 'p1', type='play_land', card_id=copy.id)
    choose(s, original.id)
    choose(s, 'Forest')
    assert 'tapped either way' in s.state.rules.decision.prompt
    choose(s, payment)
    c = s.state.cards[copy.id]
    assert c.tapped and c.choices['Chosen basic land type'] == 'Forest'
    assert Plan(s.state, 'p1', cards, None).ch(c).subtypes == {'Forest'}
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[original.id]).subtypes == {'Island'}
    roundtrip(s)
