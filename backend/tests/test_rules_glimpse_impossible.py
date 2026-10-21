"""Exact exile references and actual graveyard outcomes determine Spawn creation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_abundance import set_library
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Glimpse the Impossible'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/glimpse_impossible_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='gic', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, top=None, permanent=None, phase=None, turn=None):
    s = table(cards, [NAME, 'Lightning Bolt', 'Forest', 'Island', 'Rest in Peace',
                      'Doubling Season', 'Leyline of the Void', 'Vedalken Orrery'], ['Crafty Cutpurse', 'Leyline of the Void'])
    if permanent:
        put(s, permanent, 'battlefield')
    source = put(s, NAME, 'hand')
    if phase:
        put(s, 'Vedalken Orrery', 'battlefield')
        to_phase(s, phase, turn=turn)
    ids = set_library(s, ['Lightning Bolt', 'Forest', 'Island'] if top is None else top)
    mana(s, C=2, R=1)
    if phase:
        from tests.test_rules_bandmate_references import wait_priority

        wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    assert all(s.state.cards[cid].zone == 'p1:exile' for cid in ids[:3])
    roundtrip(s)
    return s, source, ids


def spawns(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == 'Eldrazi Spawn'
            and c.zone.endswith(':battlefield')]


def finish(s):
    to_phase(s, 'end')
    settle(s)
    roundtrip(s)


def test_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('top,n', [([], 0), (['Forest'], 1), (['Forest', 'Island'], 2),
                                 (['Lightning Bolt', 'Forest', 'Island'], 3)])
def test_actual_cleanup_creates_one_spawn_per_card_put_in_graveyard(cards, top, n):
    s, _, ids = setup(cards, top)
    finish(s)
    assert len(spawns(s)) == n
    assert all(s.state.cards[cid].zone == 'p1:graveyard' for cid in ids)
    for token in spawns(s):
        act(s, 'p1', type='activate_ability', card_id=token.id, ability=0)
    assert mana_pool(s, 'p1') == ({} if n == 0 else {'C': n})
    roundtrip(s)


def test_playing_land_and_paying_for_spell_leaves_one_spawn(cards):
    s, _, ids = setup(cards)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=ids[0], targets=['p2'], sources=[])
    act(s, 'p1', type='play_land', card_id=ids[1])
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=ids[0], targets=['p2'], sources=[])
    settle(s)
    finish(s)
    assert len(spawns(s)) == 1 and s.state.players['p2'].life == 37
    assert s.state.cards[ids[1]].zone == 'p1:battlefield'


def test_no_surviving_exile_cards_means_no_delayed_trigger(cards):
    s, _, ids = setup(cards, ['Forest'])
    act(s, 'p1', type='play_land', card_id=ids[0])
    to_phase(s, 'end')
    assert not s.state.rules.stack and not s.state.rules.pending_triggers
    assert not spawns(s)
    roundtrip(s)


def test_last_exiled_card_leaves_in_response_so_resolution_does_nothing(cards):
    s, _, ids = setup(cards, ['Lightning Bolt'])
    to_phase(s, 'end')
    assert s.state.rules.stack
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=ids[0], targets=['p2'], sources=[])
    settle(s)
    assert not spawns(s) and s.state.players['p2'].life == 37
    roundtrip(s)


@pytest.mark.parametrize('permanent,n', [('Rest in Peace', 0), ('Doubling Season', 6)])
def test_native_replacements_apply_to_actual_graveyard_and_token_outcomes(cards, permanent, n):
    s, _, ids = setup(cards, permanent=permanent)
    finish(s)
    assert len(spawns(s)) == n
    if permanent == 'Rest in Peace':
        assert all(s.state.cards[cid].zone == 'p1:exile' for cid in ids)


def test_exile_departure_and_return_is_new_object_not_a_cleanup_subject(cards):
    s, source, ids = setup(cards)
    act(s, 'p1', type='move', card_ids=[ids[0]], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='move', card_ids=[ids[0]], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    finish(s)
    assert s.state.cards[ids[0]].zone == 'p1:exile' and len(spawns(s)) == 2


def test_opponents_next_end_step_is_the_cleanup_deadline(cards):
    s, _, ids = setup(cards, phase='main1', turn=2)
    assert s.state.turn.active_player == 'p2'
    finish(s)
    assert s.state.turn.number == 2 and len(spawns(s)) == 3
    assert all(s.state.cards[cid].zone == 'p1:graveyard' for cid in ids)


def test_created_in_end_step_waits_for_next_players_end_step(cards):
    s, _, _ = setup(cards, phase='end', turn=1)
    assert not spawns(s) and len(s.state.rules.delayed) == 1
    to_phase(s, 'main1', turn=2)
    assert not spawns(s) and not s.state.rules.permissions
    finish(s)
    assert len(spawns(s)) == 3


def test_opponents_graveyard_replacement_results_in_no_spawn(cards):
    s, _, ids = setup(cards)
    put(s, 'Leyline of the Void', 'battlefield', pid='p2')
    finish(s)
    assert not spawns(s) and all(s.state.cards[cid].zone == 'p1:exile' for cid in ids)


def test_real_cutpurse_replaces_the_whole_spawn_batch(cards):
    s, _, _ = setup(cards)
    to_phase(s, 'end')
    thief = put(s, 'Crafty Cutpurse', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 1, 'C': 3})
    from tests.test_rules_bandmate_references import wait_priority

    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=thief.id, sources=[])
    settle(s)
    assert len(spawns(s)) == 3 and all(c.controller == 'p2' and c.owner == 'p2' for c in spawns(s))
    roundtrip(s)
