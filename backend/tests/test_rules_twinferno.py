"""Twinferno creates a controller-specific, once-only cast watch for this turn."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_emblem_spell_keyword import finish
from tests.test_rules_shared_damage_choices import table

NAME = 'Twinferno'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    rows = json.loads((Path(__file__).parent / 'fixtures/twinferno_cards.json').read_text())
    for i, c in enumerate(rows):
        base[c['name']] = card(c['name'], set_code='twf', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, mode=0):
    s = table(cards, [NAME, 'Lightning Bolt', 'Cultivate', 'Divination', 'Grizzly Bears', 'Sol Ring'], ['Lightning Bolt', 'Counterspell', 'Stifle'])
    source = put(s, NAME, 'hand')
    host = put(s, 'Grizzly Bears', 'battlefield') if mode else None
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'R': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, modes=[mode], targets=[host.id] if host else [])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)
    return s, host


def cast(s, name, mana, targets=(), pid='p1'):
    from tests.test_rules_bandmate_references import wait_priority

    source = put(s, name, 'hand', pid=pid)
    act(s, pid, type='add_mana', player=pid, mana=mana)
    wait_priority(s, pid)
    act(s, pid, type='cast_spell', card_id=source.id, targets=list(targets), sources=[])
    finish(s)
    roundtrip(s)
    return source


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_watch_copies_next_instant_once_after_ignoring_artifact(cards):
    s, _ = setup(cards)
    cast(s, 'Sol Ring', {'C': 1})
    assert len([c for c in s.state.cards.values() if c.name == 'Sol Ring' and c.zone.endswith(':battlefield')]) == 1
    cast(s, 'Lightning Bolt', {'R': 1}, ['p2'])
    assert s.state.players['p2'].life == 34
    cast(s, 'Lightning Bolt', {'R': 1}, ['p2'])
    assert s.state.players['p2'].life == 31


def test_opponents_instant_does_not_consume_watch(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s, _ = setup(cards)
    wait_priority(s, 'p2')
    cast(s, 'Lightning Bolt', {'R': 1}, ['p1'], pid='p2')
    assert s.state.players['p1'].life == 37
    wait_priority(s, 'p1')
    cast(s, 'Lightning Bolt', {'R': 1}, ['p2'])
    assert s.state.players['p2'].life == 34


def test_next_sorcery_is_copied_and_both_copies_draw_normally(cards):
    s, _ = setup(cards)
    put(s, 'Divination', 'hand')
    before = len(s.state.zones['p1:hand'])
    cast(s, 'Divination', {'C': 2, 'U': 1})
    assert len(s.state.zones['p1:hand']) == before + 3


def test_unused_watch_expires_when_turn_ends(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s, _ = setup(cards)
    to_phase(s, 'main1', turn=s.state.turn.number + 1)
    cast(s, 'Lightning Bolt', {'R': 1}, ['p2'])
    assert s.state.players['p2'].life == 37


def test_other_mode_grants_double_strike_until_end_of_turn(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s, host = setup(cards, mode=1)
    assert 'double strike' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[host.id]).keywords
    to_phase(s, 'main1', turn=s.state.turn.number + 1)
    assert 'double strike' not in Plan(s.state, 'p1', cards, None).ch(s.state.cards[host.id]).keywords
    roundtrip(s)


def test_countering_original_still_leaves_the_watch_trigger_to_copy_its_last_known_spell(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s, _ = setup(cards)
    bolt = put(s, 'Lightning Bolt', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
    counter = put(s, 'Counterspell', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 2})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[bolt.id])
    finish(s)
    assert s.state.players['p2'].life == 37
    assert s.state.cards[bolt.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_copy_can_choose_a_different_player_without_changing_original_target(cards):
    s, _ = setup(cards)
    assert any(e['do'] == 'copy_new_targets' for e in s.state.rules.delayed[0].effects), s.state.rules.delayed[0]
    bolt = put(s, 'Lightning Bolt', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {'keep', 'p3'} <= {o.id for o in d.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p3'])
    finish(s)
    assert s.state.players['p2'].life == 37
    assert s.state.players['p3'].life == 37
    roundtrip(s)
