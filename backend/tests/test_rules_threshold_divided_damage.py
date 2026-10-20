"""CR 601.2d, 608.2b: conditional X totals are divided as the spell is cast."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/threshold_divided_damage_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Shatterskull Smashing // Shatterskull, the Hammer Pass'


def setup(cards):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, 'Reverberate'], ['Wall of Frost', 'Jace Beleren', 'Swords to Plowshares'], [])
    spell = put(s, NAME, 'hand')
    wall = put(s, 'Wall of Frost', 'battlefield', 'p2')
    pw = put(s, 'Jace Beleren', 'battlefield', 'p2')
    from tests.game_helpers import act

    act(s, 'p2', type='set_counter', card_id=pw.id, kind='loyalty', value=20)
    return s, spell, wall, pw


def test_smashing_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('x,division', [(2, [1, 1]), (5, [1, 4]), (6, [1, 11]), (6, [5, 7]), (7, [3, 11])])
def test_threshold_changes_total_before_division_without_changing_announced_x(cards, x, division):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, wall, pw = setup(cards)
    mana(s, C=x, R=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=x, targets=[wall.id, pw.id], target_counts=[2], division=division)
    entry = s.state.rules.stack[spell.id]
    assert entry.x == x
    roundtrip(s)
    settle(s)
    assert s.state.cards[wall.id].damage == division[0]
    assert s.state.cards[pw.id].counters['loyalty'] == 20 - division[1]
    roundtrip(s)


@pytest.mark.parametrize('x', [0, 1, 6])
def test_up_to_allows_no_targets_at_any_x(cards, x):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, wall, pw = setup(cards)
    mana(s, C=x, R=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=x, targets=[], target_counts=[0])
    settle(s)
    assert s.state.cards[wall.id].damage == 0
    assert s.state.cards[pw.id].counters['loyalty'] == 20
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('division', [[0, 12], [3, 3], [6, 5]])
def test_invalid_division_is_rejected_atomically(cards, division):
    from pydantic import ValidationError

    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip

    s, spell, wall, pw = setup(cards)
    mana(s, C=6, R=2)
    before = s.state.model_dump_json()
    with pytest.raises((ActionError, ValidationError)):
        act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=6, targets=[wall.id, pw.id], target_counts=[2], division=division)
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_one_x_requires_only_one_target(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, wall, _ = setup(cards)
    mana(s, C=1, R=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=1, targets=[wall.id], target_counts=[1])
    settle(s)
    assert s.state.cards[wall.id].damage == 1
    roundtrip(s)


@pytest.mark.parametrize('all_illegal', [False, True])
def test_illegal_target_shares_are_not_redistributed(cards, all_illegal):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, wall, pw = setup(cards)
    mana(s, C=6, R=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=6, targets=[wall.id, pw.id], target_counts=[2], division=[5, 7])
    act(s, 'p2', type='move', card_ids=[wall.id], to={'player': 'p2', 'zone': 'hand'})
    if all_illegal:
        act(s, 'p2', type='move', card_ids=[pw.id], to={'player': 'p2', 'zone': 'hand'})
    settle(s)
    if not all_illegal:
        assert s.state.cards[pw.id].counters['loyalty'] == 13
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_copy_preserves_announced_x_and_the_full_division(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, spell, wall, pw = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, C=6, R=4)
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=6, targets=[wall.id, pw.id], target_counts=[2], division=[1, 11])
    copy = put(s, 'Reverberate', 'hand')
    act(s, 'p1', type='cast_spell', card_id=copy.id, targets=[spell.id])
    settle(s)
    assert s.state.cards[wall.id].damage == 2
    assert s.state.cards[pw.id].zone == 'p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_land_face_still_plays_with_optional_life_payment(cards, pay):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, spell, _, _ = setup(cards)
    act(s, 'p1', type='play_land', card_id=spell.id, face=1, pay_life=pay)
    assert s.state.cards[spell.id].zone == 'p1:battlefield'
    assert s.state.cards[spell.id].face == 1
    assert s.state.cards[spell.id].tapped != pay
    assert s.state.players['p1'].life == 40 - (3 if pay else 0)
    roundtrip(s)


@pytest.mark.parametrize('division', [[12], [1, 11]])
def test_zero_targets_rejects_leftover_division_atomically(cards, division):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip

    s, spell, _, _ = setup(cards)
    mana(s, C=6, R=2)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=6, targets=[], target_counts=[0], division=division)
    assert s.state.model_dump_json() == before
    roundtrip(s)
