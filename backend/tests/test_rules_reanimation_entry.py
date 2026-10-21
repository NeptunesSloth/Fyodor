"""Paid-color entry riders and simultaneous cross-owner reanimation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/reanimation_entry_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='rea', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', ['Vigor Mortis', 'Aberrant Return'])
def test_full(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('green,extra,expected', [(False, None, 0), (True, None, 1),
                                               (True, 'Doubling Season', 2), (True, 'Solemnity', 0)])
def test_vigor_uses_actual_green_payment_and_native_entry_counters(cards, green, extra, expected):
    s = table(cards, ['Vigor Mortis', 'Grizzly Bears', *([extra] if extra else [])])
    target = put(s, 'Grizzly Bears', 'graveyard')
    if extra:
        put(s, extra, 'battlefield')
    spell = put(s, 'Vigor Mortis', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 2, 'G': int(green), 'C': 2 - int(green)})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.cards[target.id].counters.get('+1/+1', 0) == expected
    roundtrip(s)


def test_spend_as_though_does_not_turn_actual_blue_mana_into_green(cards):
    s = table(cards, ['Vigor Mortis', 'Grizzly Bears', 'Mycosynth Lattice'])
    put(s, 'Mycosynth Lattice', 'battlefield')
    target = put(s, 'Grizzly Bears', 'graveyard')
    spell = put(s, 'Vigor Mortis', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 4})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert not s.state.cards[target.id].counters
    roundtrip(s)


@pytest.mark.parametrize('count', [1, 2, 3])
def test_aberrant_returns_chosen_objects_from_multiple_graveyards(cards, count):
    s = table(cards, ['Aberrant Return', 'Hill Giant', 'Llanowar Elves'], ['Grizzly Bears'])
    targets = [put(s, 'Hill Giant', 'graveyard'), put(s, 'Grizzly Bears', 'graveyard', 'p2'),
               put(s, 'Llanowar Elves', 'graveyard')][:count]
    spell = put(s, 'Aberrant Return', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 2, 'C': 5})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[c.id for c in targets], target_counts=[count])
    settle(s)
    for old in targets:
        obj = s.state.cards[old.id]
        if old.name == 'Llanowar Elves':
            assert obj.zone == 'p1:graveyard'
        else:
            assert obj.zone == 'p1:battlefield' and obj.controller == 'p1'
            assert obj.counters == {'-1/-1': 1}
    roundtrip(s)


def test_aberrant_requires_at_least_one_and_distinct_targets(cards):
    s = table(cards, ['Aberrant Return', 'Hill Giant'])
    target = put(s, 'Hill Giant', 'graveyard')
    spell = put(s, 'Aberrant Return', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 2, 'C': 5})
    for targets in [[], [target.id, target.id]]:
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=spell.id, targets=targets, target_counts=[len(targets)])
    assert s.state.cards[spell.id].zone == 'p1:hand'
    roundtrip(s)


def test_green_floating_but_unspent_does_not_add_counter(cards):
    s = table(cards, ['Vigor Mortis', 'Grizzly Bears', 'Omniscience'])
    put(s, 'Omniscience', 'battlefield')
    target = put(s, 'Grizzly Bears', 'graveyard')
    spell = put(s, 'Vigor Mortis', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id], free=True)
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert not s.state.cards[target.id].counters
    roundtrip(s)


def test_paid_color_rider_survives_entry_choice_and_json_reload(cards):
    from app.game.session import GameSession
    from app.game.state import GameState

    s = table(cards, ['Vigor Mortis', 'Phantasmal Image', 'Grizzly Bears'])
    target = put(s, 'Phantasmal Image', 'graveyard')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell = put(s, 'Vigor Mortis', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 2, 'G': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)
    assert s.state.rules.decision is not None
    s = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=cards)
    pick(s, [bear.id])
    settle(s)
    assert s.state.cards[target.id].counters == {'+1/+1': 1}
    roundtrip(s)


def test_aberrant_resolves_remaining_legal_target(cards):
    s = table(cards, ['Aberrant Return', 'Hill Giant'], ['Grizzly Bears'])
    giant = put(s, 'Hill Giant', 'graveyard')
    bear = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    spell = put(s, 'Aberrant Return', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 2, 'C': 5})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[giant.id, bear.id], target_counts=[2])
    act(s, 'p2', type='move', card_ids=[bear.id], to={'player': 'p2', 'zone': 'exile'})
    settle(s)
    assert s.state.cards[bear.id].zone == 'p2:exile'
    assert s.state.cards[giant.id].zone == 'p1:battlefield'
    assert s.state.cards[giant.id].counters == {'-1/-1': 1}
    roundtrip(s)


def test_copy_does_not_inherit_green_spent_on_original(cards):
    s = table(cards, ['Vigor Mortis', 'Reverberate', 'Grizzly Bears', 'Hill Giant'])
    bear = put(s, 'Grizzly Bears', 'graveyard')
    giant = put(s, 'Hill Giant', 'graveyard')
    spell = put(s, 'Vigor Mortis', 'hand')
    copy = put(s, 'Reverberate', 'hand')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 2, 'G': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id])
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 2})
    act(s, 'p1', type='cast_spell', card_id=copy.id, targets=[spell.id])
    settle(s)
    assert s.state.rules.decision is not None
    pick(s, [giant.id])
    settle(s)
    assert s.state.cards[giant.id].zone == 'p1:battlefield'
    assert not s.state.cards[giant.id].counters
    assert s.state.cards[bear.id].counters == {'+1/+1': 1}
    roundtrip(s)
