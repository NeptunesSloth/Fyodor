"""CR 601.2i / 608.2i: public named casts persist across turns."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/named_recast_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_approach_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Approach of the Second Sun')).level == 'FULL'


def cast(s, c, pid='p1'):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority

    wait_priority(s, pid)
    mana(s, pid, W=7)
    act(s, pid, type='cast_spell', card_id=c.id)


def test_first_cast_gains_life_and_puts_source_seventh_from_top(cards):
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Approach of the Second Sun'], [], [])
    source = put(s, 'Approach of the Second Sun', 'hand')
    cast(s, source)
    settle(s)
    assert s.state.rules.winner is None
    assert s.state.players['p1'].life == 47
    assert s.state.zones['p1:library'][6] == source.id, (s.state.cards[source.id].zone, s.state.zones['p1:library'].index(source.id) if source.id in s.state.zones['p1:library'] else None)
    roundtrip(s)


def test_another_cast_on_a_later_turn_wins_and_game_history_survives_reload(cards):
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Approach of the Second Sun'], [], [])
    source = put(s, 'Approach of the Second Sun', 'hand')
    cast(s, source)
    settle(s)
    to_phase(s, 'main1', turn=4)
    roundtrip(s)
    source = put(s, 'Approach of the Second Sun', 'hand')
    cast(s, source)
    settle(s)
    assert s.state.rules.winner == 'p1'
    assert s.state.players['p1'].life == 47
    roundtrip(s)


def test_countered_first_cast_still_counts_for_second_cast(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Approach of the Second Sun'], ['Counterspell'], [])
    source = put(s, 'Approach of the Second Sun', 'hand')
    counter = put(s, 'Counterspell', 'hand', 'p2')
    cast(s, source)
    wait_priority(s, 'p2')
    mana(s, 'p2', U=2)
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    source = put(s, 'Approach of the Second Sun', 'hand')
    cast(s, source)
    settle(s)
    assert s.state.rules.winner == 'p1'
    assert s.state.players['p1'].life == 40
    roundtrip(s)


def test_second_cast_from_library_does_not_win(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Approach of the Second Sun', 'Future Sight'], [], [])
    put(s, 'Future Sight', 'battlefield')
    source = put(s, 'Approach of the Second Sun', 'hand')
    cast(s, source)
    settle(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'library'}, index=0)
    cast(s, source)
    settle(s)
    assert s.state.rules.winner is None
    assert s.state.players['p1'].life == 54
    assert s.state.zones['p1:library'][6] == source.id
    roundtrip(s)


def test_opponents_cast_does_not_satisfy_your_prior_cast_requirement(cards):
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Approach of the Second Sun'], ['Approach of the Second Sun'], [])
    theirs = put(s, 'Approach of the Second Sun', 'hand', 'p2')
    mine = put(s, 'Approach of the Second Sun', 'hand')
    to_phase(s, 'main1', turn=2)
    cast(s, theirs, 'p2')
    settle(s)
    to_phase(s, 'main1', turn=4)
    cast(s, mine)
    settle(s)
    assert s.state.rules.winner is None
    assert s.state.players['p1'].life == 47
    roundtrip(s)


def test_copy_was_not_cast_and_does_not_increment_named_game_history(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Approach of the Second Sun', 'Twincast'], [], [])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = put(s, 'Approach of the Second Sun', 'hand')
    copy = put(s, 'Twincast', 'hand')
    mana(s, W=7)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    mana(s, U=2)
    act(s, 'p1', type='cast_spell', card_id=copy.id, targets=[source.id])
    settle(s)
    assert s.state.rules.winner is None
    assert s.state.players['p1'].life == 54
    assert s.state.rules.named_casts_game['p1']['approach of the second sun'] == 1
    source = put(s, 'Approach of the Second Sun', 'hand')
    cast(s, source)
    settle(s)
    assert s.state.rules.winner == 'p1'
    assert s.state.players['p1'].life == 54
    roundtrip(s)


def test_first_cast_into_empty_library_puts_card_at_bottom_and_gains_life(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Approach of the Second Sun'], [], [])
    source = put(s, 'Approach of the Second Sun', 'hand')
    act(s, 'p1', type='move', card_ids=list(s.state.zones['p1:library']), to={'player': 'p1', 'zone': 'exile'})
    cast(s, source)
    settle(s)
    assert s.state.zones['p1:library'] == [source.id]
    assert s.state.players['p1'].life == 47
    assert s.state.rules.winner is None
    roundtrip(s)


def test_face_down_spell_does_not_count_its_printed_name(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Willbender'], [], [])
    source = put(s, 'Willbender', 'hand')
    mana(s, C=3)
    act(s, 'p1', type='cast_spell', card_id=source.id, face_down=True)
    settle(s)
    assert s.state.cards[source.id].face_down
    assert not s.state.rules.named_casts_game.get('p1', {}).get('willbender')
    roundtrip(s)


def test_cant_win_effect_does_not_make_successful_condition_take_the_otherwise_branch(cards):
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Approach of the Second Sun'], ['Platinum Angel'], [])
    source = put(s, 'Approach of the Second Sun', 'hand')
    cast(s, source)
    settle(s)
    put(s, 'Platinum Angel', 'battlefield', 'p2')
    source = put(s, 'Approach of the Second Sun', 'hand')
    cast(s, source)
    settle(s)
    assert s.state.rules.winner is None
    assert s.state.players['p1'].life == 47
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)
