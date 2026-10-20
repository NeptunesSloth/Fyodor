"""CR 111.2, 608.2h: conditional attached copy and actual creation fallback."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/delayed_fewer_counters_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




NAME = 'Nine-Lives Familiar'


def setup(cards, modifier=None):
    s = table(cards, [NAME, *(['Murder'] * 10), 'Solemnity', 'Doubling Season', 'Containment Priest', 'Migratory Greathorn', 'Cackling Counterpart', 'Winding Constrictor'])
    if modifier:
        put(s, modifier, 'battlefield')
    source = put(s, NAME, 'hand')
    mana(s, C=1, B=2)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    return s, source


def kill(s, source, *, resolve=True):
    from tests.test_rules_bandmate_references import wait_priority

    wait_priority(s, 'p1')
    spell = next(c for c in s.state.cards.values() if c.name == 'Murder' and c.owner == 'p1'
                 and c.zone in ('p1:library', 'p1:hand'))
    act(s, 'p1', type='move', card_ids=[spell.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, C=1, B=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id])
    if resolve:
        settle(s)
    return spell


def next_end(s, turn=None):
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, 'end', turn=turn)
    settle(s)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_actual_cast_and_delayed_return_have_eight_then_seven_counters(cards):
    s, source = setup(cards)
    assert s.state.cards[source.id].counters == {'revival': 8}
    kill(s, source)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)
    next_end(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].counters == {'revival': 7}
    roundtrip(s)


def test_doubling_replaces_entry_after_predeath_count_is_fixed(cards):
    s, source = setup(cards, 'Doubling Season')
    assert s.state.cards[source.id].counters == {'revival': 16}
    kill(s, source)
    next_end(s)
    assert s.state.cards[source.id].counters == {'revival': 30}
    roundtrip(s)


def test_solemnity_prevents_cast_counters_and_death_has_no_return(cards):
    s, source = setup(cards, 'Solemnity')
    assert s.state.cards[source.id].counters == {}
    kill(s, source)
    assert not s.state.rules.delayed
    next_end(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_repeated_deaths_exhaust_all_eight_revival_counters_then_stop(cards):
    s, source = setup(cards)
    for turn, remaining in enumerate(range(7, -1, -1), start=1):
        kill(s, source)
        assert s.state.cards[source.id].zone == 'p1:graveyard'
        roundtrip(s)
        next_end(s, turn=turn)
        assert s.state.cards[source.id].zone == 'p1:battlefield'
        assert s.state.cards[source.id].counters.get('revival', 0) == remaining
        roundtrip(s)
    kill(s, source)
    assert not s.state.rules.delayed
    next_end(s, turn=9)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_graveyard_exile_and_return_is_a_new_object_and_cannot_return(cards):
    s, source = setup(cards)
    kill(s, source)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    next_end(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_counter_count_is_fixed_but_replacements_are_read_at_entry(cards):
    s, source = setup(cards, 'Doubling Season')
    kill(s, source)
    doubling = next(c for c in s.state.cards.values() if c.name == 'Doubling Season')
    act(s, 'p1', type='move', card_ids=[doubling.id], to={'player': 'p1', 'zone': 'exile'})
    next_end(s)
    assert s.state.cards[source.id].counters == {'revival': 15}
    roundtrip(s)


def test_solemnity_added_before_return_prevents_counters_then_no_further_return(cards):
    s, source = setup(cards)
    kill(s, source)
    put(s, 'Solemnity', 'battlefield')
    next_end(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield' and s.state.cards[source.id].counters == {}
    kill(s, source)
    assert not s.state.rules.delayed
    next_end(s, turn=2)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_priest_replaces_delayed_return(cards):
    s, source = setup(cards)
    kill(s, source)
    put(s, 'Containment Priest', 'battlefield')
    next_end(s)
    assert s.state.cards[source.id].zone == 'p1:exile' and s.state.cards[source.id].counters == {}
    roundtrip(s)


def test_merged_cards_both_return_with_frozen_count(cards):
    from tests.test_rules_wave18d_merged import mutate

    s, source = setup(cards)
    other = mutate(s, 'Migratory Greathorn', source, over='under', C=2, G=1)
    assert s.state.cards[source.id].counters == {'revival': 8}
    kill(s, source)
    assert s.state.cards[source.id].zone == s.state.cards[other.id].zone == 'p1:graveyard'
    roundtrip(s)
    next_end(s)
    for c in [source, other]:
        assert s.state.cards[c.id].zone == 'p1:battlefield'
        assert s.state.cards[c.id].counters == {'revival': 7}
    roundtrip(s)


def test_graveyard_incarnation_changed_before_original_trigger_cannot_be_captured(cards):
    s, source = setup(cards)
    spell = kill(s, source, resolve=False)
    while s.state.cards[spell.id].zone == 'stack':
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert len(s.state.rules.delayed) == 1  # Created with the old GY ref, then returns nothing.
    next_end(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_return_under_owner_control_even_when_another_player_controlled_dead_source(cards):
    s, source = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    kill(s, source)
    next_end(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].counters == {'revival': 7}
    roundtrip(s)


def test_death_during_end_step_waits_until_next_end_step(cards):
    s, source = setup(cards)
    next_end(s)
    kill(s, source)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)
    next_end(s, turn=2)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].counters == {'revival': 7}
    roundtrip(s)


def test_uncast_reanimation_does_not_supply_eight_counters(cards):
    s = table(cards, [NAME, 'Reanimate', *(['Murder'] * 2)])
    source = put(s, NAME, 'graveyard')
    spell = put(s, 'Reanimate', 'hand')
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield' and s.state.cards[source.id].counters == {}
    kill(s, source)
    assert not s.state.rules.delayed
    next_end(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_token_qualifying_death_creates_empty_delayed_return_after_token_ceases(cards):
    s, source = setup(cards)
    spell = put(s, 'Cackling Counterpart', 'hand')
    mana(s, C=1, U=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id])
    settle(s)
    token = next(c for c in s.state.cards.values() if c.is_token and c.name == 'Nine-Lives Familiar')
    assert token.counters == {}  # Copy wasn't cast; it doesn't inherit the original's counters.
    act(s, 'p1', type='set_counter', card_id=token.id, kind='revival', value=1)
    kill(s, token)
    assert token.id not in s.state.cards and len(s.state.rules.delayed) == 1
    roundtrip(s)
    next_end(s)
    assert not [c for c in s.state.cards.values() if c.is_token and c.name == 'Nine-Lives Familiar']
    assert s.state.cards[source.id].counters == {'revival': 8}
    roundtrip(s)


@pytest.mark.parametrize('first,expected', [('Doubling Season', 31), ('Winding Constrictor', 32)])
def test_delayed_return_counter_replacement_order_pauses_before_entry(cards, first, expected):
    s, source = setup(cards, 'Doubling Season')
    put(s, 'Winding Constrictor', 'battlefield')
    kill(s, source)
    next_end(s)
    d = s.state.rules.decision
    assert d is not None and '616.1' in d.prompt
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[source.id].counters == {}
    choice = next(o.id for o in d.options if o.label.startswith(first))
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[choice])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].counters == {'revival': expected}
    roundtrip(s)
