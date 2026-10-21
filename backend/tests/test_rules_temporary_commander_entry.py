"""CR 903.8, 603.7c: temporary commander entry and delayed return."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/temporary_commander_entry_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Hellkite Courser'


def test_courser_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup_courser(cards, *, end_step=False):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, [NAME, 'Vedalken Orrery'], [])
    source = put(s, NAME, 'hand')
    commander = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.zone == 'p1:command')
    if end_step:
        put(s, 'Vedalken Orrery', 'battlefield')
        to_phase(s, 'end', turn=1)
    mana(s, R=6)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    return s, source, commander


def choose(s, commander=None):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    d = s.state.rules.decision
    assert d and d.player == 'p1'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[commander.id] if commander else [])
    settle(s)


def test_commander_enters_without_cast_or_tax_gains_haste_and_returns_at_end_step(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import to_phase

    s, _, commander = setup_courser(cards)
    choose(s, commander)
    assert s.state.cards[commander.id].zone == 'p1:battlefield' and 'haste' in chars(s, commander).keywords
    assert not s.state.players['p1'].commander_casts and not any(s.state.players['p1'].commander_tax.values())
    act(s, 'p1', type='activate_ability', card_id=commander.id, ability=ability_index(s, commander, 'Create'))
    settle(s)
    assert any(c.is_token and c.name == 'Goblin' for c in s.state.cards.values())
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[commander.id].zone == 'p1:command'
    roundtrip(s)


def test_declining_leaves_commander_in_command_zone(cards):
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave30m_durations import to_phase

    s, _, commander = setup_courser(cards)
    choose(s)
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[commander.id].zone == 'p1:command'
    roundtrip(s)


@pytest.mark.parametrize('change', ['source_leaves', 'control', 'blink', 'graveyard'])
def test_delayed_return_tracks_commander_object_and_survives_source_departure(cards, change):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave30m_durations import to_phase

    s, source, commander = setup_courser(cards)
    choose(s, commander)
    if change == 'source_leaves':
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    elif change == 'control':
        act(s, 'p1', type='set_controller', card_ids=[commander.id], player='p2')
    else:
        act(s, 'p1', type='move', card_ids=[commander.id], to={'player': 'p1', 'zone': 'graveyard'})
        if change == 'blink':
            act(s, 'p1', type='move', card_ids=[commander.id], to={'player': 'p1', 'zone': 'battlefield'})
    if change == 'graveyard':
        act(s, 'p1', type='pass_priority')
        d = s.state.rules.decision
        assert d and d.resume['step'] == 'commander_zone'
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['no'])
    roundtrip(s)
    to_phase(s, 'end', turn=1)
    settle(s)
    expected = 'p1:battlefield' if change == 'blink' else 'p1:graveyard' if change == 'graveyard' else 'p1:command'
    assert s.state.cards[commander.id].zone == expected
    roundtrip(s)


def test_entry_during_end_step_waits_until_the_next_end_step_and_haste_persists(cards):
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave30m_durations import to_phase

    s, _, commander = setup_courser(cards, end_step=True)
    choose(s, commander)
    assert s.state.cards[commander.id].zone == 'p1:battlefield'
    to_phase(s, 'main1', turn=2)
    assert 'haste' in chars(s, commander).keywords
    roundtrip(s)
    to_phase(s, 'end', turn=2)
    settle(s)
    assert s.state.cards[commander.id].zone == 'p1:command'
    roundtrip(s)


def test_partner_pair_offers_both_owned_commanders_and_returns_only_the_chosen_one(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import act, deck, enable
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave30m_durations import to_phase

    p1 = deck(cards, 'Rograkh, Son of Rohgahh', [(1, NAME), (20, 'Mountain')]) + deck(cards, 'Silas Renn, Seeker Adept', [])
    p2 = deck(cards, "Atraxa, Praetors' Voice", [(20, 'Island')])
    s = GameSession(enable(new_game([PlayerSetup('Alice', cards=p1), PlayerSetup('Bob', cards=p2)], shuffle=False)), cards=cards)
    act(s, 'p1', type='pass_priority')
    for pid in ['p1', 'p2']:
        act(s, pid, type='set_prefs', response='on')
    source = put(s, NAME, 'hand')
    pair = [c for c in s.state.cards.values() if c.owner == 'p1' and c.zone == 'p1:command']
    mana(s, R=6)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {c.id for c in pair}
    picked = next(c for c in pair if c.name == 'Silas Renn, Seeker Adept')
    choose(s, picked)
    assert s.state.cards[picked.id].zone == 'p1:battlefield' and 'haste' in chars(s, picked).keywords
    assert all(s.state.cards[c.id].zone == 'p1:command' for c in pair if c.id != picked.id)
    to_phase(s, 'end', turn=1)
    settle(s)
    assert all(s.state.cards[c.id].zone == 'p1:command' for c in pair)
    assert not s.state.players['p1'].commander_casts
    roundtrip(s)
