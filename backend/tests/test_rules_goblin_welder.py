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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/goblin_welder_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_full(cards):
    assert coverage.of_card_data(cards.resolve('Goblin Welder')).level == 'FULL'


def setup(cards, out='Sol Ring', incoming='Ornithopter', pid='p1', extras=()):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    names = [c['name'] for c in json.loads((Path(__file__).parent / 'fixtures/goblin_welder_cards.json').read_text())
             if cards.resolve(c['name']) is not None]
    s = table(cards, names, names, names)
    welder = put(s, 'Goblin Welder', 'battlefield')
    to_phase(s, 'main1', turn=4)
    outgoing = put(s, out, 'battlefield', pid)
    returned = put(s, incoming, 'graveyard', pid)
    for name in extras:
        put(s, name, 'battlefield')
    return s, welder, outgoing, returned


def activate(s, welder, outgoing, incoming):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    act(s, 'p1', type='activate_ability', card_id=welder.id, ability=0,
        targets=[outgoing.id, incoming.id], target_counts=[1, 1])
    roundtrip(s)


@pytest.mark.parametrize('pid', ['p1', 'p2', 'p3'])
def test_basic_exchange_is_one_zone_event(cards, pid):
    from tests.test_rules_designations import roundtrip, settle
    s, welder, outgoing, incoming = setup(cards, pid=pid)
    activate(s, welder, outgoing, incoming)
    settle(s)
    assert s.state.cards[outgoing.id].zone == pid+':graveyard'
    assert s.state.cards[incoming.id].zone == pid+':battlefield'
    moves = [step for a in s.history.actions if isinstance(getattr(a, 'r', None), list) for step in a.r
             if step.get('type') == 'move' and step.get('routes')]
    assert len(moves) == 1 and set(moves[0]['card_ids']) == {outgoing.id, incoming.id}
    roundtrip(s)


@pytest.mark.parametrize('gone', ['outgoing', 'incoming', 'both'])
def test_both_targets_must_still_be_legal(cards, gone):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle
    s, welder, outgoing, incoming = setup(cards)
    activate(s, welder, outgoing, incoming)
    for c, key in [(outgoing, 'outgoing'), (incoming, 'incoming')]:
        if gone in (key, 'both'):
            act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    assert s.state.cards[outgoing.id].zone == ('p1:exile' if gone in ('outgoing', 'both') else 'p1:battlefield')
    assert s.state.cards[incoming.id].zone == ('p1:exile' if gone in ('incoming', 'both') else 'p1:graveyard')
    roundtrip(s)


def test_entry_choice_does_not_move_either_target_until_answered(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle
    s, welder, outgoing, incoming = setup(cards, incoming='Phyrexian Revoker')
    activate(s, welder, outgoing, incoming)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    assert s.state.cards[outgoing.id].zone == 'p1:battlefield'
    assert s.state.cards[incoming.id].zone == 'p1:graveyard'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, name='Sol Ring')
    settle(s)
    assert s.state.cards[outgoing.id].zone == 'p1:graveyard'
    assert s.state.cards[incoming.id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('choice', ['exile', 'library:shuffle'])
def test_graveyard_replacement_choice_keeps_both_targets_until_commit(cards, choice):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle
    s, welder, outgoing, incoming = setup(cards, out='Blightsteel Colossus', extras=['Rest in Peace'])
    activate(s, welder, outgoing, incoming)
    settle(s)
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'simultaneous_replacement'
    assert s.state.cards[outgoing.id].zone == 'p1:battlefield'
    assert s.state.cards[incoming.id].zone == 'p1:graveyard'
    roundtrip(s)
    selected = next(str(i) for i, c in enumerate(d.resume['cands']) if c['outcome'] == choice)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[selected])
    settle(s)
    assert any(c.name == 'Blightsteel Colossus' and c.zone == 'p1:'+choice.split(':')[0] for c in s.state.cards.values())
    assert s.state.cards[incoming.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_outgoing_counter_prohibition_applies_to_simultaneous_entry(cards):
    from tests.test_rules_designations import roundtrip, settle

    s, welder, outgoing, incoming = setup(cards, out='Solemnity', incoming='Arcbound Worker', extras=['Mycosynth Lattice'])
    activate(s, welder, outgoing, incoming)
    settle(s)
    assert s.state.cards[outgoing.id].zone == 'p1:graveyard'
    assert s.state.cards[incoming.id].zone == 'p1:graveyard'  # Entered with no counters, then died as a 0/0.
    assert s.state.cards[incoming.id].counters.get('+1/+1', 0) == 0
    roundtrip(s)


def test_sacrifice_prohibition_does_not_prevent_the_independent_return(cards):
    from tests.test_rules_designations import put, roundtrip, settle

    s, welder, outgoing, incoming = setup(cards, pid='p2')
    put(s, 'Tajuru Preserver', 'battlefield', 'p2')
    activate(s, welder, outgoing, incoming)
    settle(s)
    assert s.state.cards[outgoing.id].zone == 'p2:battlefield'
    assert s.state.cards[incoming.id].zone == 'p2:battlefield'
    roundtrip(s)


def test_mismatched_players_graveyard_is_rejected_atomically(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip

    s, welder, outgoing, _ = setup(cards, pid='p2')
    wrong = put(s, 'Ornithopter', 'graveyard')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=welder.id, ability=0,
            targets=[outgoing.id, wrong.id], target_counts=[1, 1])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_activated_ability_survives_welders_departure(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, welder, outgoing, incoming = setup(cards)
    activate(s, welder, outgoing, incoming)
    act(s, 'p1', type='move', card_ids=[welder.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert s.state.cards[outgoing.id].zone == 'p1:graveyard'
    assert s.state.cards[incoming.id].zone == 'p1:battlefield'
    roundtrip(s)
