"""The Great Work grants dynamic access to all graveyards."""
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
from tests.test_rules_conditionals import until_asked
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/great_work_cards.json').read_text())):
        if 'faces' in c:
            c = {**c, 'card_faces': c['faces']}
            c.pop('faces')
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()





def setup(cards):
    s = table(cards, ['Urabrask // The Great Work', 'Lightning Bolt', 'Ponder', 'Mountain', 'Contentious Plan'],
              ['Lightning Bolt', 'Ponder', 'Grizzly Bears', 'Counterspell'], ['Lightning Bolt', 'Dark Ritual'])
    source = put(s, 'Urabrask // The Great Work', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='lore', value=2)
    act(s, 'p1', type='set_face', card_id=source.id, face=1)
    old_oid = s.state.rules.object_id(source.id)
    spell = put(s, 'Contentious Plan', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    until_asked(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].face == 0
    assert s.state.rules.object_id(source.id) != old_oid
    assert s.state.cards[source.id].counters.get('lore', 0) == 0
    assert any(p.zone_owner == 'any' for p in s.state.rules.permissions)
    return s, source


def gy(s, name, player='p1'):
    return put(s, name, 'graveyard', pid=player)


def test_actual_both_faces_full(cards):
    c = cards.resolve('Urabrask // The Great Work')
    assert len(c['faces']) == 2
    assert 'Until end of turn' in c['faces'][1]['oracle_text']
    assert coverage.of_card_data(c).level == 'FULL'


@pytest.mark.parametrize('owner', ['p1', 'p2', 'p3'])
def test_spell_from_any_graveyard_costs_mana_and_exiles_on_resolution(cards, owner):
    from tests.game_helpers import mana_pool
    from tests.test_rules_bandmate_references import wait_priority
    s, _ = setup(cards)
    spell = gy(s, 'Lightning Bolt', owner)
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'], sources=[])
    until_asked(s)
    if s.state.rules.decision:
        d = s.state.rules.decision
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['p2'])
    settle(s)
    assert s.state.cards[spell.id].zone == f'{owner}:exile'
    # Front-face Urabrask adds R and deals one extra damage for this cast.
    assert s.state.players['p2'].life == 36
    assert mana_pool(s).get('R') == 1
    roundtrip(s)


def remove_source(s, source):
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})


def test_permission_survives_source_leaving_and_sees_future_graveyard_arrivals(cards):
    from tests.game_helpers import mana_pool
    from tests.test_rules_bandmate_references import wait_priority
    s, source = setup(cards)
    remove_source(s, source)
    spell = gy(s, 'Lightning Bolt', 'p3')  # was not in any graveyard as the permission was made
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    wait_priority(s, 'p1')
    roundtrip(s)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'], sources=[])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p3:exile'
    assert s.state.players['p2'].life == 37
    assert not mana_pool(s)
    roundtrip(s)


def test_permission_does_not_waive_costs(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import wait_priority
    s, source = setup(cards)
    remove_source(s, source)
    spell = gy(s, 'Lightning Bolt', 'p2')
    wait_priority(s, 'p1')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'], sources=[])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_permission_does_not_grant_creatures_or_other_players_access(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import wait_priority
    s, _ = setup(cards)
    bear = gy(s, 'Grizzly Bears', 'p2')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bear.id, sources=[])
    bolt = gy(s, 'Lightning Bolt', 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'R': 1})
    wait_priority(s, 'p2')
    with pytest.raises(ActionError):
        act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p1'], sources=[])
    roundtrip(s)


def test_countered_spell_is_exiled_instead_of_owners_graveyard(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s, source = setup(cards)
    remove_source(s, source)
    spell = gy(s, 'Lightning Bolt', 'p3')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'], sources=[])
    counter = put(s, 'Counterspell', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 2})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[spell.id], sources=[])
    roundtrip(s)
    settle(s)
    assert s.state.cards[spell.id].zone == 'p3:exile'
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_sorcery_timing_is_not_waived(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_fight_excess_mana import advance
    s, source = setup(cards)
    remove_source(s, source)
    spell = gy(s, 'Ponder', 'p2')
    advance(s)
    assert s.state.turn.phase != 'main1'
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1})
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    roundtrip(s)


def test_permission_expires_when_turn_ends(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_fight_excess_mana import advance
    s, source = setup(cards)
    remove_source(s, source)
    spell = gy(s, 'Lightning Bolt', 'p2')
    turn = s.state.turn.number
    for _ in range(30):
        if s.state.turn.number != turn:
            break
        advance(s)
    assert s.state.turn.number != turn
    assert not any(p.zone_owner == 'any' for p in s.state.rules.permissions)
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'], sources=[])
    roundtrip(s)
