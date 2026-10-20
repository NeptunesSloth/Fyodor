"""Negative hand-origin events distinguish physical zone owner from caster and watcher."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, events, triggers
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Ghostly Pilferer'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/negative_cast_origin_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s = table(cards, ['Mindleech Mass', 'Lightning Bolt', 'Deep Analysis', 'One with the Multiverse'], [NAME, 'Staggershock'])
    pilferer = put(s, NAME, 'battlefield', pid='p2')
    return s, pilferer


def test_canonical_card_stays_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_actual_mindleech_cast_from_opponents_hand_triggers_pilferer(cards):
    from tests.test_rules_conditionals import until_asked
    from tests.test_rules_wave33a_turn_triggers import attack
    from tests.test_rules_wave53a_events import mass_prompt

    s, _ = setup(cards)
    mass = put(s, 'Mindleech Mass', 'battlefield')
    stag = put(s, 'Staggershock', 'hand', pid='p2')
    to_phase(s, 'main1', turn=4)
    before = len(s.state.zones['p2:hand'])
    attack(s, mass)
    d = mass_prompt(s)
    while d.kind == 'confirm' and 'look at the hand' not in d.prompt:
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes'])
        d = mass_prompt(s)
    assert 'look at the hand' in d.prompt
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['ok'])
    d = until_asked(s)
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[stag.id])
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p3'])
    settle(s)
    assert len(s.state.zones['p2:hand']) == before  # One card leaves hand; one Pilferer draw.
    assert s.state.cards[stag.id].zone == 'p2:graveyard'
    assert s.state.players['p3'].life == 38
    roundtrip(s)


@pytest.mark.parametrize('origin', ['hand', 'graveyard', 'library'])
def test_actual_hand_and_nonhand_casts_preserve_existing_semantics(cards, origin):
    s, _ = setup(cards)
    before = len(s.state.zones['p2:hand'])
    if origin == 'graveyard':
        spell = put(s, 'Deep Analysis', 'graveyard')
        mana(s, U=1, C=1)
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p1'])
    else:
        spell = put(s, 'Lightning Bolt', origin)
        if origin == 'library':
            put(s, 'One with the Multiverse', 'battlefield')
            act(s, 'p1', type='move', card_ids=[spell.id], to={'player': 'p1', 'zone': 'library'}, position='top')
        mana(s, R=1)
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p3'])
    settle(s)
    assert len(s.state.zones['p2:hand']) == before + int(origin != 'hand')
    roundtrip(s)


@pytest.mark.parametrize(('word', 'origin', 'expected'), [
    ('your', 'p1:hand', True), ('your', 'p2:hand', False), ('your', 'p3:hand', True),
    ('their', 'p1:hand', False), ('their', 'p2:hand', True), ('their', 'p3:hand', True),
    ('your', 'p1:graveyard', True), ('their', 'p1:exile', True),
    ('your', 'hand', False), ('their', 'hand', False), ('their', None, False),
])
def test_negative_origin_condition_binds_your_to_watcher_their_to_caster(cards, word, origin, expected):
    from app.rules.plan import Plan

    s, watcher = setup(cards)
    plan = Plan(s.state, 'p1', cards, None)
    cond = events.parse_condition(f'an opponent casts a spell from anywhere other than {word} hand')
    assert cond and cond['from_owner'] == ('you' if word == 'your' else 'caster')
    fact = ('cast', None, None, 'p1', {'from': origin, 'actor': 'p1'})
    assert triggers._details_ok(plan, cond, watcher, fact) is expected


def test_negative_their_hand_does_not_guess_a_missing_cast_actor(cards):
    from app.rules.plan import Plan

    s, watcher = setup(cards)
    condition = events.parse_condition('an opponent casts a spell from anywhere other than their hand')
    assert condition is not None
    fact = ('cast', None, None, None, {'from': 'p1:hand'})
    assert not triggers._details_ok(Plan(s.state, 'p1', cards, None), condition, watcher, fact)
