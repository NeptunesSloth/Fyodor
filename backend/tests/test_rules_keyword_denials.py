"""CR 101.2 / 611.2c: keyword loss and prohibition for fixed objects."""
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
from tests.test_rules_bandmate_references import keyword, mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/keyword_denials_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_lighthouse_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Arcane Lighthouse')).level == 'FULL'


def activate_lighthouse(s):
    tower = put(s, 'Arcane Lighthouse', 'battlefield')
    to_phase(s, 'main1', turn=4)
    mana(s, C=1)
    act(s, 'p1', type='activate_ability', card_id=tower.id, ability=1)
    settle(s)
    return tower


@pytest.mark.parametrize('victim,kw', [('Gladecover Scout', 'hexproof'), ('Knight of Malice', 'hexproof from')])
def test_lighthouse_removes_existing_hexproof_and_its_variants_then_expires(cards, victim, kw):
    s = table(cards, ['Arcane Lighthouse'], [victim])
    target = put(s, victim, 'battlefield', 'p2')
    assert keyword(s, target, kw)
    activate_lighthouse(s)
    assert not keyword(s, target, kw)
    roundtrip(s)
    to_phase(s, 'main1', turn=5)
    assert keyword(s, target, kw)
    roundtrip(s)


@pytest.mark.parametrize('gear,kw', [('Swiftfoot Boots', 'hexproof'), ('Whispersilk Cloak', 'shroud')])
def test_lighthouse_overrides_later_static_grants_and_they_resume_next_turn(cards, gear, kw):
    s = table(cards, ['Arcane Lighthouse'], ['Grizzly Bears', gear])
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    activate_lighthouse(s)
    equipment = put(s, gear, 'battlefield', 'p2')
    act(s, 'p2', type='attach', card_ids=[equipment.id], to=bear.id)
    assert not keyword(s, bear, kw)
    roundtrip(s)
    to_phase(s, 'main1', turn=5)
    assert keyword(s, bear, kw)
    roundtrip(s)


def test_lighthouse_does_not_follow_later_entrants_or_new_incarnations(cards):
    s = table(cards, ['Arcane Lighthouse'], ['Gladecover Scout', 'Grizzly Bears'])
    scout = put(s, 'Gladecover Scout', 'battlefield', 'p2')
    activate_lighthouse(s)
    later = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p2', type='set_counter', card_id=later.id, kind='hexproof', value=1)
    assert keyword(s, later, 'hexproof')
    act(s, 'p2', type='move', card_ids=[scout.id], to={'player': 'p2', 'zone': 'graveyard'})
    act(s, 'p2', type='move', card_ids=[scout.id], to={'player': 'p2', 'zone': 'battlefield'})
    assert keyword(s, scout, 'hexproof')
    roundtrip(s)


def test_a_keyword_counter_is_not_removed_by_keyword_denial(cards):
    s = table(cards, ['Arcane Lighthouse'], ['Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p2', type='set_counter', card_id=bear.id, kind='hexproof', value=1)
    activate_lighthouse(s)
    assert not keyword(s, bear, 'hexproof') and s.state.cards[bear.id].counters['hexproof'] == 1
    roundtrip(s)
    to_phase(s, 'main1', turn=5)
    assert keyword(s, bear, 'hexproof')
    roundtrip(s)


def test_lighthouse_prevents_resolved_hexproof_grants_without_preventing_the_other_effects(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave6c_tokens_pumps import pt

    s = table(cards, ['Arcane Lighthouse'], ['Grizzly Bears', 'Blossoming Defense'])
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    activate_lighthouse(s)
    wait_priority(s, 'p2')
    spell = put(s, 'Blossoming Defense', 'hand', 'p2')
    mana(s, 'p2', G=1)
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[bear.id])
    settle(s)
    assert pt(s, bear) == (4, 4) and not keyword(s, bear, 'hexproof')
    roundtrip(s)


def test_lighthouse_locks_the_object_even_if_control_changes_or_the_lighthouse_leaves(cards):
    s = table(cards, ['Arcane Lighthouse'], ['Gladecover Scout'])
    scout = put(s, 'Gladecover Scout', 'battlefield', 'p2')
    tower = activate_lighthouse(s)
    act(s, 'p1', type='set_controller', card_ids=[scout.id], player='p1')
    act(s, 'p1', type='move', card_ids=[tower.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert not keyword(s, scout, 'hexproof')
    roundtrip(s)
    to_phase(s, 'main1', turn=5)
    assert keyword(s, scout, 'hexproof')
    roundtrip(s)


def test_lighthouse_prohibition_also_applies_to_a_later_animation_grant(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave6c_tokens_pumps import pt
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Arcane Lighthouse'], ['Lumbering Falls'])
    tower = put(s, 'Arcane Lighthouse', 'battlefield')
    falls = put(s, 'Lumbering Falls', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    mana(s, 'p2', C=2, U=1, G=1)
    index = ability_index(s, falls, 'becomes a 3/3')
    act(s, 'p2', type='activate_ability', card_id=falls.id, ability=index)
    settle(s)
    assert keyword(s, falls, 'hexproof')
    wait_priority(s, 'p1')
    mana(s, C=1)
    act(s, 'p1', type='activate_ability', card_id=tower.id, ability=1)
    settle(s)
    assert not keyword(s, falls, 'hexproof')
    wait_priority(s, 'p2')
    mana(s, 'p2', C=2, U=1, G=1)
    act(s, 'p2', type='activate_ability', card_id=falls.id, ability=index)
    settle(s)
    assert not keyword(s, falls, 'hexproof') and pt(s, falls) == (3, 3)
    roundtrip(s)


@pytest.mark.parametrize('quoted', [False, True])
def test_prohibited_resolved_grants_do_not_reappear_when_the_prohibition_expires_unit(cards, quoted):
    """An isolated layer unit: a hypothetical indefinite grant must not spring into existence later."""
    from app.game.state import GameState
    from app.rules import layers
    from app.rules.plan import Plan

    s = table(cards, ['Arcane Lighthouse'], ['Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    activate_lighthouse(s)
    state = GameState.model_validate_json(s.state.model_dump_json())
    plan = Plan(state, 'p1', cards, None)
    effect = layers.add_effect(plan, affected=[plan.oid(state.cards[bear.id])], layer='6', source=None,
                               controller='p2', duration='permanent',
                               add_keywords=() if quoted else ('hexproof', 'trample'),
                               add_abilities=['Flying, hexproof from white.'] if quoted else [])
    assert effect.blocked_keywords
    state = GameState.model_validate_json(plan.state.model_dump_json())
    plan = Plan(state, 'p1', cards, None)
    layers.end_of_turn(plan)
    ch = plan.ch(plan.state.cards[bear.id])
    assert 'hexproof' not in ch.keywords and 'hexproof from' not in ch.keywords
    assert ('flying' if quoted else 'trample') in ch.keywords
