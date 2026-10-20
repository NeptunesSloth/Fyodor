"""CR 611.2, 614, 616: trigger-bound player and permanent damage replacements."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/timed_damage_replacement_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAME = 'Lightning, Army of One'


def setup(cards, *, double=False):
    from tests.game_helpers import act
    from tests.test_rules_banding import block, declare_only, until_block
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase
    s = table(cards, [NAME, 'Shock', 'Shock', 'Lightning Bolt', 'Murder', 'Fireshrieker', 'Furnace of Rath', 'Ghostly Flicker'],
              ['Wall of Stone', 'Ajani Goldmane', 'Shock'], ['Wall of Stone', 'Shock'])
    source = put(s, NAME, 'battlefield')
    wall = put(s, 'Wall of Stone', 'battlefield', 'p2')
    if double:
        equipment = put(s, 'Fireshrieker', 'battlefield')
        act(s, 'p1', type='attach', card_ids=[equipment.id], to=source.id)
    declare_only(s, [source], [])
    until_block(s)
    block(s, [])
    to_phase(s, 'main2', turn=4)
    return s, source, wall


def shock(s, target, *, player='p1'):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle
    spell = next(c for c in s.state.cards.values() if c.name == 'Shock' and c.owner == player
                 and c.zone not in ('stack', f'{player}:graveyard', f'{player}:exile'))
    act(s, player, type='move', card_ids=[spell.id], to={'player': player, 'zone': 'hand'})
    mana(s, player, R=1)
    wait_priority(s, player)
    act(s, player, type='cast_spell', card_id=spell.id, targets=[target])
    settle(s)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_first_strike_damage_creates_record_without_retroactive_doubling(cards):
    from tests.test_rules_designations import roundtrip
    s, _, _ = setup(cards)
    assert s.state.players['p2'].life == 37 and s.state.players['p1'].life == 43
    shock(s, 'p2')
    assert s.state.players['p2'].life == 33
    roundtrip(s)


def test_trigger_bound_player_excludes_other_players_and_their_permanents(cards):
    from tests.test_rules_designations import put, roundtrip
    s, _, wall = setup(cards)
    other = put(s, 'Wall of Stone', 'battlefield', 'p3')
    shock(s, wall.id)
    shock(s, other.id)
    assert s.state.cards[wall.id].damage == 4 and s.state.cards[other.id].damage == 2
    roundtrip(s)


@pytest.mark.parametrize('take_control', [True, False])
def test_permanent_membership_follows_current_control(cards, take_control):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    s, _, wall = setup(cards)
    victim = put(s, 'Wall of Stone', 'battlefield', 'p3') if take_control else wall
    act(s, 'p1', type='set_controller', card_ids=[victim.id], player='p2' if take_control else 'p3')
    shock(s, victim.id)
    assert s.state.cards[victim.id].damage == (4 if take_control else 2)
    roundtrip(s)


def test_double_strike_second_hit_is_doubled_and_second_record_stacks(cards):
    from tests.test_rules_designations import roundtrip
    s, _, _ = setup(cards, double=True)
    assert s.state.players['p2'].life == 31 and s.state.players['p1'].life == 49
    shock(s, 'p2')
    assert s.state.players['p2'].life == 23
    roundtrip(s)


@pytest.mark.parametrize('source_change', ['none', 'departure', 'controller'])
def test_record_survives_intervening_turns_and_ends_at_original_controllers_next_turn(cards, source_change):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_wave30m_durations import to_phase
    s, source, _ = setup(cards)
    if source_change == 'departure':
        spell = put(s, 'Murder', 'hand')
        mana(s, B=3)
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id])
        settle(s)
        assert s.state.cards[source.id].zone == 'p1:graveyard'
    elif source_change == 'controller':
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    to_phase(s, 'main1', turn=5)
    shock(s, 'p2')
    assert s.state.players['p2'].life == 33
    to_phase(s, 'main1', turn=6)
    shock(s, 'p2')
    assert s.state.players['p2'].life == 29
    to_phase(s, 'main1', turn=7)
    shock(s, 'p2', player='p3')
    assert s.state.players['p2'].life == 27
    roundtrip(s)


def test_record_from_departed_controller_lasts_until_skipped_next_turn(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase
    s, _, _ = setup(cards)
    act(s, 'p1', type='concede')
    to_phase(s, 'main1', turn=5)
    assert s.state.turn.active_player == 'p2'
    shock(s, 'p2', player='p3')
    assert s.state.players['p2'].life == 33
    to_phase(s, 'main1', turn=6)
    shock(s, 'p2', player='p2')
    assert s.state.players['p2'].life == 29
    to_phase(s, 'main1', turn=8)
    assert s.state.turn.active_player == 'p2'
    assert not any(rec.get('until') == 'next_turn' for rec in s.state.rules.replacements)
    roundtrip(s)


def test_sources_of_any_player_are_doubled_against_bound_player(cards):
    from tests.test_rules_designations import roundtrip
    s, _, _ = setup(cards)
    shock(s, 'p2', player='p3')
    shock(s, 'p2', player='p2')
    assert s.state.players['p2'].life == 29
    roundtrip(s)


def test_record_affects_planeswalker_controlled_by_bound_player(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    s, _, _ = setup(cards)
    walker = put(s, 'Ajani Goldmane', 'battlefield', 'p2')
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=6)
    shock(s, walker.id)
    assert s.state.cards[walker.id].counters['loyalty'] == 2
    roundtrip(s)
