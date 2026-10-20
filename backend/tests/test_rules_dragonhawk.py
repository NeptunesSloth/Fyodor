"""Exact exile-batch permissions and delayed remaining-card damage."""
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
from tests.test_rules_abundance import set_library
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = "Dragonhawk, Fate's Tempest"


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/dragonhawk_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()





def setup(cards, large=True, defer=False):
    s = table(cards, [NAME, 'Colossal Dreadmaw', 'Grizzly Bears', 'Centaur Courser', 'Lightning Bolt', 'Forest', 'Island', 'Ephemerate', "Y'shtola Rhul", 'Furnace of Rath'], [])
    source = put(s, NAME, 'hand')
    if large:
        put(s, 'Colossal Dreadmaw', 'battlefield')
    top = set_library(s, ['Lightning Bolt', 'Forest', 'Island'])
    mana(s, C=3, R=2)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    if defer:
        for _ in range(15):
            if s.state.cards[source.id].zone != 'stack':
                break
            act(s, s.state.rules.priority, type='pass_priority')
    else:
        settle(s)
    return s, source, top


def finish(s, turn=1):
    to_phase(s, 'end', turn=turn)
    settle(s)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('large,n', [(False, 1), (True, 2)])
def test_actual_enters_counts_self_and_current_big_creatures(cards, large, n):
    s, source, top = setup(cards, large)
    assert all(s.state.cards[c].zone == 'p1:exile' for c in top[:n])
    assert s.state.cards[top[n]].zone == 'p1:library'
    roundtrip(s)
    finish(s)
    assert s.state.players['p2'].life == s.state.players['p3'].life == 40 - 2*n
    roundtrip(s)


def test_actual_play_land_and_paid_spell_reduce_later_damage(cards):
    s, source, top = setup(cards)
    act(s, 'p1', type='play_land', card_id=top[1])
    from app.game.errors import ActionError

    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=top[0], targets=['p2'])
    assert s.state.model_dump(mode='json') == before
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=top[0], targets=['p2'])
    settle(s)
    finish(s)
    assert s.state.players['p2'].life == 37 and s.state.players['p3'].life == 40
    roundtrip(s)


def test_source_departure_does_not_end_permission_or_delayed_damage(cards):
    s, source, top = setup(cards)
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'graveyard'})
    act(s, 'p1', type='play_land', card_id=top[1])
    finish(s)
    assert s.state.players['p2'].life == s.state.players['p3'].life == 38
    roundtrip(s)


def test_exile_departure_and_return_new_oid_not_counted(cards):
    s, source, top = setup(cards)
    act(s, 'p1', type='move', card_ids=[top[0]], to={'zone': 'graveyard'})
    act(s, 'p1', type='move', card_ids=[top[0]], to={'zone': 'exile'})
    from app.game.errors import ActionError

    mana(s, R=1)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=top[0], targets=['p2'])
    assert s.state.model_dump(mode='json') == before
    finish(s)
    assert s.state.players['p2'].life == s.state.players['p3'].life == 38
    roundtrip(s)


@pytest.mark.parametrize('large,n', [(False, 0), (True, 1)])
def test_source_leaves_before_trigger_resolution_count_recomputes(cards, large, n):
    s, source, top = setup(cards, large=large, defer=True)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'graveyard'})
    settle(s)
    assert all(s.state.cards[c].zone == 'p1:exile' for c in top[:n])
    assert s.state.cards[top[n]].zone == 'p1:library'
    assert len(s.state.rules.delayed) == 1
    finish(s)
    assert s.state.players['p2'].life == s.state.players['p3'].life == 40 - 2*n
    roundtrip(s)


def test_original_controller_and_damage_replacement_after_source_control_change(cards):
    s, source, top = setup(cards)
    put(s, 'Furnace of Rath', 'battlefield')
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    finish(s)
    assert s.state.players['p1'].life == 40
    assert s.state.players['p2'].life == s.state.players['p3'].life == 32
    roundtrip(s)


def test_actual_extra_end_step_expires_new_permission_and_fires_new_batch(cards):
    from tests.test_rules_conditionals import until

    s, source, top = setup(cards)
    put(s, "Y'shtola Rhul", 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    finish(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id])
    settle(s)
    assert s.state.players['p2'].life == 36
    assert s.state.rules.extra_phases == ['end', 'cleanup']
    assert not any(p.card in top for p in s.state.rules.permissions)
    # A real instant blink in the first end step creates another distinct exile batch.
    blink = put(s, 'Ephemerate', 'hand')
    mana(s, W=1)
    act(s, 'p1', type='cast_spell', card_id=blink.id, targets=[source.id])
    settle(s)
    assert s.state.cards[top[2]].zone == 'p1:exile'
    assert any(p.card == top[2] for p in s.state.rules.permissions)
    roundtrip(s)
    until(s, lambda s: s.state.turn.phase == 'end' and s.state.rules.extra_phases == ['cleanup'])
    settle(s)
    d = s.state.rules.decision
    if d is not None:
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id])
        settle(s)
    assert not any(p.card == top[2] for p in s.state.rules.permissions)
    assert s.state.players['p2'].life == s.state.players['p3'].life == 34
    assert s.state.turn.number == 1
    roundtrip(s)


def test_actual_attack_creates_another_independent_batch(cards):
    s, source, top = setup(cards)
    to_phase(s, 'main1', turn=4)
    settle(s)
    set_library(s, ['Lightning Bolt', 'Forest', 'Island'])
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    settle(s)
    assert all(s.state.cards[c].zone == 'p1:exile' for c in top[:2])
    assert len(s.state.rules.delayed) == 1
    roundtrip(s)


@pytest.mark.parametrize('power4,n', [(False, 1), (True, 2)])
def test_power_threshold_and_opponent_control_are_read_at_resolution(cards, power4, n):
    s, source, top = setup(cards, defer=True)
    giant = next(c for c in s.state.cards.values() if c.name == 'Colossal Dreadmaw')
    act(s, 'p1', type='set_controller', card_ids=[giant.id], player='p2')
    courser = put(s, 'Centaur Courser', 'battlefield')
    if power4:
        act(s, 'p1', type='set_counter', card_id=courser.id, kind='+1/+1', value=1)
    settle(s)
    assert all(s.state.cards[c].zone == 'p1:exile' for c in top[:n])
    assert s.state.cards[top[n]].zone == 'p1:library'
    roundtrip(s)
