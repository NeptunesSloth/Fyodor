"""A command-zone permission lets Wrenn's controller play owned graveyard permanents."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave7b_activation import ability_index

NAME = 'Wrenn and Realmbreaker'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    rows = json.loads((Path(__file__).parent / 'fixtures/wrenn_emblem_cards.json').read_text())
    for i, c in enumerate(rows):
        base[c['name']] = card(c['name'], set_code='wre', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name=NAME, loyalty=7):
    s = table(cards, [name, 'Sol Ring', 'Grizzly Bears', 'Lightning Bolt', 'Forest'], ['Sol Ring', 'Counterspell'])
    source = put(s, name, 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=loyalty)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'You get an emblem'))
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert any(c.zone == 'p1:command' and c.token and c.token.type_line == 'Emblem' for c in s.state.cards.values())
    roundtrip(s)
    return s


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_actual_ultimate_grants_paid_casting_after_source_dies(cards):
    s = setup(cards)
    ring = put(s, 'Sol Ring', 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='cast_spell', card_id=ring.id, sources=[])
    assert mana_pool(s, 'p1') == {}
    settle(s)
    assert s.state.cards[ring.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_graveyard_land_still_uses_normal_land_play_limit(cards):
    s = setup(cards)
    land = put(s, 'Forest', 'graveyard')
    act(s, 'p1', type='play_land', card_id=land.id)
    assert s.state.cards[land.id].zone == 'p1:battlefield'
    act(s, 'p1', type='move', card_ids=[land.id], to={'player': 'p1', 'zone': 'graveyard'})
    with pytest.raises(ActionError):
        act(s, 'p1', type='play_land', card_id=land.id)
    roundtrip(s)


def test_nonpermanent_spells_and_opponents_graveyards_remain_ineligible(cards):
    s = setup(cards)
    bolt = put(s, 'Lightning Bolt', 'graveyard')
    other = put(s, 'Sol Ring', 'graveyard', pid='p2')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'C': 1})
    for source, targets in [(bolt, ['p2']), (other, [])]:
        before = s.state.model_dump_json()
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=source.id, targets=targets)
        assert s.state.model_dump_json() == before
    roundtrip(s)


def test_permission_does_not_waive_mana_cost_or_sorcery_timing(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    ring = put(s, 'Sol Ring', 'graveyard')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=ring.id)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    to_phase(s, 'main1', turn=s.state.turn.number + 1)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=ring.id)
    roundtrip(s)


def test_countered_permanent_can_be_cast_again_as_a_new_graveyard_object(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s = setup(cards)
    ring = put(s, 'Sol Ring', 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='cast_spell', card_id=ring.id)
    counter = put(s, 'Counterspell', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 2})
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[ring.id])
    settle(s)
    assert s.state.cards[ring.id].zone == 'p1:graveyard'
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=ring.id)
    settle(s)
    assert s.state.cards[ring.id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name', ['Wrenn and Six', 'Jaya Ballard'])
def test_related_permission_emblems_are_fully_supported(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_wrenn_six_emblem_retrace_requires_actual_land_discard_and_keeps_spell_in_graveyard(cards):
    s = setup(cards, 'Wrenn and Six')
    bolt = put(s, 'Lightning Bolt', 'graveyard')
    land = put(s, 'Forest', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
    d = s.state.rules.decision
    if d is not None:
        assert land.id in {o.id for o in d.options}
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[land.id])
    settle(s)
    assert s.state.players['p2'].life == 37
    assert s.state.cards[land.id].zone == s.state.cards[bolt.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('countered', [False, True])
def test_jaya_emblem_paid_graveyard_spell_is_exiled_on_resolution_or_counter(cards, countered):
    from tests.test_rules_bandmate_references import wait_priority

    s = setup(cards, 'Jaya Ballard', loyalty=8)
    bolt = put(s, 'Lightning Bolt', 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p2'])
    if countered:
        counter = put(s, 'Counterspell', 'hand', pid='p2')
        act(s, 'p2', type='add_mana', player='p2', mana={'U': 2})
        wait_priority(s, 'p2')
        act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[bolt.id])
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:exile'
    assert s.state.players['p2'].life == (40 if countered else 37)
    roundtrip(s)


def test_tamiyo_emblem_casts_from_hand_without_mana_but_not_from_graveyard(cards):
    s = setup(cards, 'Tamiyo, Field Researcher')
    bear = put(s, 'Grizzly Bears', 'hand')
    act(s, 'p1', type='cast_spell', card_id=bear.id, free=True)
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    ring = put(s, 'Sol Ring', 'graveyard')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=ring.id, free=True)
    roundtrip(s)
