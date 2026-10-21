"""CR 608.2h: exiled creature power and nontargeted commander counters."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/exile_power_counters_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = "Astarion's Thirst"


def test_thirst_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup_thirst(cards, *, commander=True, pump=False, multiplier=False, solemnity=False, shroud=False, hold=False):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, 'Giant Growth', 'Vorinclex, Monstrous Raider', 'Solemnity', 'Lightning Greaves', 'Downsize'], ['Grizzly Bears'])
    recipient = put(s, 'Krenko, Mob Boss', 'battlefield') if commander else None
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    if multiplier:
        put(s, 'Vorinclex, Monstrous Raider', 'battlefield')
    if solemnity:
        put(s, 'Solemnity', 'battlefield')
    if shroud:
        greaves = put(s, 'Lightning Greaves', 'battlefield')
        act(s, 'p1', type='attach', card_ids=[greaves.id], to=recipient.id)
    if pump:
        growth = put(s, 'Giant Growth', 'hand')
        mana(s, G=1)
        act(s, 'p1', type='cast_spell', card_id=growth.id, targets=[target.id])
        settle(s)
    source = put(s, NAME, 'hand')
    if hold:
        act(s, 'p1', type='set_prefs', hold_priority=True)
    mana(s, B=4)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[target.id])
    return s, source, target, recipient


@pytest.mark.parametrize('pump', [False, True])
@pytest.mark.parametrize('multiplier', [False, True])
def test_uses_battlefield_power_and_applies_counter_replacements(cards, pump, multiplier):
    from tests.test_rules_designations import roundtrip, settle

    s, _, target, commander = setup_thirst(cards, pump=pump, multiplier=multiplier)
    settle(s)
    d = s.state.rules.decision
    assert d is None  # The sole eligible recipient is chosen automatically.
    assert s.state.cards[target.id].zone == 'p2:exile'
    assert s.state.cards[commander.id].counters['+1/+1'] == (5 if pump else 2) * (2 if multiplier else 1)
    roundtrip(s)


@pytest.mark.parametrize('shroud', [False, True])
def test_commander_is_chosen_without_targeting(cards, shroud):
    from tests.test_rules_designations import roundtrip, settle

    s, _, _, commander = setup_thirst(cards, shroud=shroud)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[commander.id].counters['+1/+1'] == 2
    roundtrip(s)


@pytest.mark.parametrize('solemnity', [False, True])
def test_no_commander_or_counter_prohibition_still_exiles_target(cards, solemnity):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, _, target, commander = setup_thirst(cards, commander=solemnity, solemnity=solemnity)
    settle(s)
    if (d := s.state.rules.decision) is not None:
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[commander.id])
        settle(s)
    assert s.state.cards[target.id].zone == 'p2:exile'
    if commander:
        assert not s.state.cards[commander.id].counters.get('+1/+1')
    roundtrip(s)


def test_only_spell_target_leaving_makes_spell_do_nothing(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, _, target, commander = setup_thirst(cards)
    act(s, 'p2', type='move', card_ids=[target.id], to={'player': 'p2', 'zone': 'graveyard'})
    settle(s)
    assert s.state.rules.decision is None
    assert not s.state.cards[commander.id].counters.get('+1/+1')
    roundtrip(s)


def test_a_controlled_opponents_commander_is_an_eligible_recipient(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle

    s, _, _, own = setup_thirst(cards)
    borrowed = put(s, "Atraxa, Praetors' Voice", 'battlefield', 'p2')
    act(s, 'p2', type='set_controller', card_ids=[borrowed.id], player='p1')
    settle(s)
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {own.id, borrowed.id}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[borrowed.id])
    settle(s)
    assert s.state.cards[borrowed.id].counters['+1/+1'] == 2
    assert not s.state.cards[own.id].counters.get('+1/+1')
    roundtrip(s)


def test_exiled_token_still_supplies_last_known_power(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME], ['Raise the Alarm'])
    commander = put(s, 'Krenko, Mob Boss', 'battlefield')
    alarm = put(s, 'Raise the Alarm', 'hand', 'p2')
    wait_priority(s, 'p2')
    mana(s, 'p2', W=2)
    act(s, 'p2', type='cast_spell', card_id=alarm.id)
    settle(s)
    token = next(c for c in s.state.cards.values() if c.is_token and c.name == 'Soldier')
    source = put(s, NAME, 'hand')
    wait_priority(s, 'p1')
    mana(s, B=4)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[token.id])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[commander.id].counters['+1/+1'] == 1 and token.id not in s.state.cards
    roundtrip(s)


def test_negative_power_after_response_puts_no_counters(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle

    s, _, target, commander = setup_thirst(cards, hold=True)
    downsize = put(s, 'Downsize', 'hand')
    mana(s, U=1)
    act(s, 'p1', type='cast_spell', card_id=downsize.id, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p2:exile'
    assert not s.state.cards[commander.id].counters.get('+1/+1')
    roundtrip(s)
