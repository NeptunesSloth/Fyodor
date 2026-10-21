"""CR 608.2d, 701.13, 202.3: opponent choices and milled-card mana values."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/optional_repeat_roll_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_full(cards):
    assert coverage.of_card_data(cards.resolve('Delina, Wild Mage')).level == 'FULL'


def trigger(cards, monkeypatch, results, *, target='Grizzly Bears', extras=(), leave=False, source_leaves=False, counters=0):
    from tests.game_helpers import act
    from tests.test_rules_banding import declare_only
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave12a_counters_keywords import rolls
    from tests.test_rules_wave30m_durations import to_phase

    names = [c['name'] for c in json.loads((Path(__file__).parent / 'fixtures/optional_repeat_roll_cards.json').read_text())]
    s = table(cards, names, [], [])
    source = put(s, 'Delina, Wild Mage', 'battlefield')
    to_phase(s, 'main1', turn=4)
    chosen = source if target == source.name else put(s, target, 'battlefield')
    for name in extras:
        put(s, name, 'battlefield')
    if counters:
        act(s, 'p1', type='set_counter', card_id=chosen.id, kind='+1/+1', value=counters)
    rolls(monkeypatch, *results)
    declare_only(s, [source], [])
    settle(s)
    d = s.state.rules.decision
    assert d and chosen.id in {o.id for o in d.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[chosen.id])
    if leave or source_leaves:
        moved = chosen if leave else source
        act(s, 'p1', type='move', card_ids=[moved.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    attack_tokens(s)
    return s, source, chosen


def attack_tokens(s, defender='p3'):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    while (d := s.state.rules.decision) is not None and d.resume['step'] == 'token_attack':
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[defender])
        settle(s)


def again(s, yes):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    d = s.state.rules.decision
    assert d and d.resume['step'] == 'optional_repeat_roll'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes' if yes else 'no'])
    settle(s)
    attack_tokens(s)


def copies(s, name):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.zone == 'p1:battlefield']


@pytest.mark.parametrize('die', [1, 14])
def test_low_result_makes_one_tapped_attacking_copy_and_stops(cards, monkeypatch, die):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, _, _ = trigger(cards, monkeypatch, [die], counters=2)
    made = copies(s, 'Grizzly Bears')
    assert len(made) == 1 and made[0].tapped
    assert made[0].attacking is not None and made[0].attacking.id == 'p3'
    assert chars(s, made[0]).pt == (2, 2)  # Counters are not copiable values.
    assert s.state.rules.decision is None
    assert s.state.rules.turn_log.rolled['p1'] == 1
    assert 'end of combat' in chars(s, made[0]).oracle_text.lower()
    roundtrip(s)


@pytest.mark.parametrize('die', [15, 20])
def test_high_result_can_stop_without_another_roll(cards, monkeypatch, die):
    from tests.test_rules_designations import roundtrip

    s, _, _ = trigger(cards, monkeypatch, [die])
    assert len(copies(s, 'Grizzly Bears')) == 1
    again(s, False)
    assert s.state.rules.decision is None and s.state.rules.turn_log.rolled['p1'] == 1
    roundtrip(s)


def test_repeated_high_rolls_each_make_a_copy_then_low_roll_stops(cards, monkeypatch):
    from tests.test_rules_designations import roundtrip

    s, _, _ = trigger(cards, monkeypatch, [20, 15, 2])
    again(s, True)
    assert len(copies(s, 'Grizzly Bears')) == 2
    again(s, True)
    assert len(copies(s, 'Grizzly Bears')) == 3
    assert s.state.rules.decision is None and s.state.rules.turn_log.rolled['p1'] == 3
    roundtrip(s)


def test_copying_delina_does_not_create_more_attack_triggers_or_legend_conflicts(cards, monkeypatch):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, source, _ = trigger(cards, monkeypatch, [1], target='Delina, Wild Mage')
    made = copies(s, source.name)
    assert len(made) == 1 and 'Legendary' not in chars(s, made[0]).supertypes
    assert source.id in s.state.cards and s.state.rules.turn_log.rolled['p1'] == 1
    roundtrip(s)


def test_tokens_exile_from_their_own_end_combat_ability(cards, monkeypatch):
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave30m_durations import to_phase

    s, source, _ = trigger(cards, monkeypatch, [19, 1])
    again(s, True)
    ids = [c.id for c in copies(s, 'Grizzly Bears')]
    to_phase(s, 'end_combat')
    settle(s)
    assert all(cid not in s.state.cards or s.state.cards[cid].zone == 'p1:exile' for cid in ids)
    assert source.id in s.state.cards
    roundtrip(s)


def test_token_replacement_doubles_copies_without_doubling_die_rolls(cards, monkeypatch):
    from tests.test_rules_designations import roundtrip

    s, _, _ = trigger(cards, monkeypatch, [15], extras=['Anointed Procession'])
    assert len(copies(s, 'Grizzly Bears')) == 2
    again(s, False)
    assert s.state.rules.turn_log.rolled['p1'] == 1
    roundtrip(s)


def test_new_pixie_copy_adds_advantage_to_the_next_roll(cards, monkeypatch):
    from tests.test_rules_designations import roundtrip

    s, _, _ = trigger(cards, monkeypatch, [1, 20, 1, 2, 3], target='Pixie Guide')
    again(s, True)
    assert len(copies(s, 'Pixie Guide')) == 2
    assert s.state.rules.turn_log.rolled['p1'] == 2  # Ignored rolls never happened.
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('extra', ['Wyll, Blade of Frontiers', 'Barbarian Class'])
def test_existing_die_replacements_apply_to_every_repeat(cards, monkeypatch, extra):
    from tests.test_rules_designations import roundtrip

    s, _, _ = trigger(cards, monkeypatch, [1, 20, 1, 2], extras=[extra])
    again(s, True)
    assert len(copies(s, 'Grizzly Bears')) == 2
    assert s.state.rules.turn_log.rolled['p1'] == 2
    assert s.state.rules.decision is None
    if extra == 'Wyll, Blade of Frontiers':
        wyll = next(c for c in s.state.cards.values() if c.name == extra and c.zone == 'p1:battlefield')
        assert wyll.counters.get('+1/+1', 0) == 2
    roundtrip(s)


def test_illegal_target_prevents_rolling_or_creating_any_token(cards, monkeypatch):
    from tests.test_rules_designations import roundtrip

    s, _, _ = trigger(cards, monkeypatch, [], leave=True)
    assert not copies(s, 'Grizzly Bears')
    assert s.state.rules.turn_log.rolled.get('p1', 0) == 0
    roundtrip(s)


def test_source_departure_does_not_stop_a_legal_targeted_attack_trigger(cards, monkeypatch):
    from tests.test_rules_designations import roundtrip

    s, _, _ = trigger(cards, monkeypatch, [1], source_leaves=True)
    assert len(copies(s, 'Grizzly Bears')) == 1
    roundtrip(s)


def test_copying_a_delina_token_copies_its_own_exile_ability(cards, monkeypatch):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave30m_durations import to_phase

    s, _, _ = trigger(cards, monkeypatch, [1])
    token = copies(s, 'Grizzly Bears')[0]
    spell = put(s, 'Cackling Counterpart', 'hand')
    mana(s, U=2, C=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[token.id])
    settle(s)
    made = copies(s, 'Grizzly Bears')
    assert len(made) == 2
    assert all('end of combat' in chars(s, c).oracle_text.lower() for c in made)
    ids = [c.id for c in made]
    to_phase(s, 'end_combat')
    settle(s)
    assert all(cid not in s.state.cards or s.state.cards[cid].zone == 'p1:exile' for cid in ids)
    roundtrip(s)


def test_wyll_copy_does_not_see_the_roll_before_it_entered(cards, monkeypatch):
    from tests.test_rules_designations import roundtrip

    s, _, original = trigger(cards, monkeypatch, [1, 20], target='Wyll, Blade of Frontiers')
    again(s, False)
    assert s.state.cards[original.id].counters.get('+1/+1', 0) == 1
    made = copies(s, original.name)
    assert len(made) == 1 and made[0].counters.get('+1/+1', 0) == 0
    roundtrip(s)


def test_wyll_copies_watch_only_later_iterations(cards, monkeypatch):
    from tests.test_rules_designations import roundtrip

    s, _, original = trigger(cards, monkeypatch, [1, 20, 1, 2, 3], target='Wyll, Blade of Frontiers')
    first = copies(s, original.name)[0].id
    again(s, True)
    made = copies(s, original.name)
    second = next(c for c in made if c.id != first)
    assert s.state.cards[original.id].counters.get('+1/+1', 0) == 2
    assert s.state.cards[first].counters.get('+1/+1', 0) == 1
    assert second.counters.get('+1/+1', 0) == 0
    roundtrip(s)
