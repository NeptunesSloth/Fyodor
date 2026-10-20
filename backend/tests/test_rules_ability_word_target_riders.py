"""CR 207.2c, 608.2c: ability-word riders refer to the preceding spell target."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/ability_word_target_rider_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Temur Battle Rage'


@pytest.mark.parametrize('name', [NAME, 'Roar of Challenge'])
def test_rage_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def setup(cards):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, 'Roar of Challenge', 'Grizzly Bears', 'Giant Growth'], ['Grizzly Bears', 'Lightning Bolt', 'Counterspell'], [])
    spell = put(s, NAME, 'hand')
    target = put(s, 'Grizzly Bears', 'battlefield')
    return s, spell, target


@pytest.mark.parametrize('power', [2, 3, 4, 6])
def test_target_can_supply_ferocious_but_needs_power_four(cards, power):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, spell, target = setup(cards)
    if power > 2:
        act(s, 'p1', type='set_counter', card_id=target.id, kind='+1/+1', value=power-2)
    mana(s, C=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)
    kws = chars(s, target).keywords
    assert 'double strike' in kws
    assert ('trample' in kws) == (power >= 4)
    roundtrip(s)


@pytest.mark.parametrize('controller', ['p1', 'p2'])
def test_another_creature_can_supply_power_only_if_you_control_it(cards, controller):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, spell, target = setup(cards)
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p2', type='set_counter', card_id=other.id, kind='+1/+1', value=2)
    if controller == 'p1':
        act(s, 'p2', type='set_controller', card_ids=[other.id], player='p1')
    mana(s, C=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)
    assert 'double strike' in chars(s, target).keywords
    assert ('trample' in chars(s, target).keywords) == (controller == 'p1')
    roundtrip(s)


@pytest.mark.parametrize('gain_power', [False, True])
def test_ferocious_is_checked_at_resolution(cards, gain_power):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, spell, target = setup(cards)
    if not gain_power:
        act(s, 'p1', type='set_counter', card_id=target.id, kind='+1/+1', value=2)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, C=1, R=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    if gain_power:
        growth = put(s, 'Giant Growth', 'hand')
        act(s, 'p1', type='cast_spell', card_id=growth.id, targets=[target.id])
    else:
        act(s, 'p1', type='set_counter', card_id=target.id, kind='+1/+1', value=0)
    settle(s)
    assert 'double strike' in chars(s, target).keywords
    assert ('trample' in chars(s, target).keywords) == gain_power
    if gain_power:
        # Both grants last through the end step and expire at cleanup.
        from tests.test_rules_wave30m_durations import to_phase

        to_phase(s, 'end', turn=1)
        assert 'trample' in chars(s, target).keywords
        to_phase(s, 'main1', turn=2)
        assert not ({'trample', 'double strike'} & chars(s, target).keywords)
    roundtrip(s)


@pytest.mark.parametrize('ferocious', [False, True])
def test_roar_of_challenge_reuses_the_same_target_rider(cards, ferocious):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, _, target = setup(cards)
    spell = put(s, 'Roar of Challenge', 'hand')
    if ferocious:
        act(s, 'p1', type='set_counter', card_id=target.id, kind='+1/+1', value=2)
    mana(s, C=2, G=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)
    ch = chars(s, target)
    assert ('indestructible' in ch.keywords) == ferocious
    assert 'lure' in ch.imposed
    roundtrip(s)


def test_rage_with_departed_target_does_not_grant_another_creature_keywords(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, spell, target = setup(cards)
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p2', type='set_counter', card_id=other.id, kind='+1/+1', value=2)
    act(s, 'p2', type='set_controller', card_ids=[other.id], player='p1')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, C=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    mana(s, 'p2', R=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:graveyard'
    assert not ({'trample', 'double strike'} & chars(s, other).keywords)
    roundtrip(s)
