"""CR 608.2i: physical cards entering a named player graveyard this turn."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/graveyard_entry_history_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


AURA = 'Fraying Sanity'
TRAP = 'Ravenous Trap'


def table(cards):
    from tests.test_rules_shared_damage_choices import table as build
    return build(cards, [AURA, AURA, TRAP, 'Thought Scour', 'Thought Scour', 'Murder', 'Murder',
                         'Pull from Eternity', 'Mind Rot', 'Disenchant', 'Flicker of Fate', "Tormod's Crypt", 'Rest in Peace'],
                 ['Grizzly Bears', 'Unearth', 'Shock', 'Reverberate'], ['Grizzly Bears'])


def cast(s, name, targets=(), *, player='p1', extra=None):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle
    spell = next(c for c in s.state.cards.values() if c.name == name and c.owner == player
                 and c.zone not in ('stack', f'{player}:graveyard', f'{player}:battlefield', f'{player}:exile'))
    act(s, player, type='move', card_ids=[spell.id], to={'player': player, 'zone': 'hand'})
    mana(s, player, U=5, B=5, R=5, W=5)
    wait_priority(s, player)
    act(s, player, type='cast_spell', card_id=spell.id, targets=list(targets), **(extra or {}))
    settle(s)
    return spell


def endstep(s, *, turn=1):
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s, 'end', turn=turn)
    settle(s)


@pytest.mark.parametrize('name', [AURA, TRAP])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_fraying_counts_enchanted_player_not_active_player(cards):
    from tests.test_rules_designations import roundtrip
    s = table(cards)
    cast(s, AURA, ['p2'])
    cast(s, 'Thought Scour', ['p2'])
    before = len(s.state.zones['p2:library'])
    other = len(s.state.zones['p1:library'])
    endstep(s)
    assert len(s.state.zones['p2:library']) == before - 2
    assert len(s.state.zones['p1:library']) == other
    roundtrip(s)


def test_two_fraying_triggers_include_cards_milled_by_first_resolution(cards):
    from tests.test_rules_designations import roundtrip
    s = table(cards)
    cast(s, AURA, ['p2'])
    cast(s, AURA, ['p2'])
    cast(s, 'Thought Scour', ['p2'])
    before = len(s.state.zones['p2:library'])
    endstep(s)
    assert len(s.state.zones['p2:library']) == before - 6
    roundtrip(s)


def test_cards_later_exiled_still_count_as_having_entered_graveyard(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_wave7b_activation import ability_index
    s = table(cards)
    cast(s, AURA, ['p2'])
    cast(s, 'Thought Scour', ['p2'])
    crypt = put(s, "Tormod's Crypt", 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=crypt.id, ability=ability_index(s, crypt, 'Exile'), targets=['p2'])
    settle(s)
    assert not s.state.zones['p2:graveyard']
    before = len(s.state.zones['p2:library'])
    endstep(s)
    assert len(s.state.zones['p2:library']) == before - 2
    roundtrip(s)


def test_entry_from_exile_and_stolen_creature_death_count_for_graveyard_owner(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    s = table(cards)
    cast(s, AURA, ['p2'])
    bear = put(s, 'Grizzly Bears', 'exile', 'p2')
    cast(s, 'Pull from Eternity', [bear.id])
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p2', 'zone': 'battlefield'})
    act(s, 'p1', type='set_controller', card_ids=[bear.id], player='p1')
    cast(s, 'Murder', [bear.id])
    assert s.state.cards[bear.id].zone == 'p2:graveyard'
    before = len(s.state.zones['p2:library'])
    endstep(s)
    assert len(s.state.zones['p2:library']) == before - 2
    roundtrip(s)


def trap(s):
    from tests.test_rules_designations import put
    return put(s, TRAP, 'hand')


def test_ravenous_trap_can_pay_zero_after_three_entries_even_if_graveyard_was_exiled(cards):
    from tests.game_helpers import act, mana_pool
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_wave7b_activation import ability_index
    s = table(cards)
    cast(s, 'Thought Scour', ['p2'])
    bear = put(s, 'Grizzly Bears', 'exile', 'p2')
    cast(s, 'Pull from Eternity', [bear.id])
    crypt = put(s, "Tormod's Crypt", 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=crypt.id, ability=ability_index(s, crypt, 'Exile'), targets=['p2'])
    settle(s)
    spell = trap(s)
    before = mana_pool(s)
    act(s, 'p1', type='cast_spell', card_id=spell.id, alt_cost=f'{spell.id}:0', targets=['p2'])
    settle(s)
    assert mana_pool(s) == before
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_ravenous_trap_requires_one_opponents_three_entries_not_total_across_opponents(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    s = table(cards)
    cast(s, 'Thought Scour', ['p2'])
    bear = put(s, 'Grizzly Bears', 'exile', 'p3')
    cast(s, 'Pull from Eternity', [bear.id])
    spell = trap(s)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, alt_cost=f'{spell.id}:0', targets=['p2'])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_ravenous_condition_is_checked_at_announcement_before_qualifying_opponent_leaves(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    s = table(cards)
    cast(s, 'Thought Scour', ['p2'])
    bear = put(s, 'Grizzly Bears', 'exile', 'p2')
    cast(s, 'Pull from Eternity', [bear.id])
    victim = put(s, 'Grizzly Bears', 'graveyard', 'p3')
    spell = trap(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='cast_spell', card_id=spell.id, alt_cost=f'{spell.id}:0', targets=['p3'])
    assert s.state.cards[spell.id].zone == 'stack'
    act(s, 'p2', type='concede')
    act(s, 'p1', type='set_prefs', hold_priority=False)
    settle(s)
    assert s.state.cards[victim.id].zone == 'p3:exile'
    roundtrip(s)


@pytest.mark.parametrize('copy', [False, True])
def test_tokens_and_copied_permanents_are_not_cards_for_history(cards, copy):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    s = table(cards)
    cast(s, AURA, ['p2'])
    before_ids = set(s.state.cards)
    if copy:
        original = put(s, 'Grizzly Bears', 'battlefield', 'p2')
        act(s, 'p2', type='copy_card', card_id=original.id, player='p2', count=1)
    else:
        act(s, 'p2', type='create_token', player='p2', token={'name': 'Soldier', 'type_line': 'Token Creature — Soldier',
                                                          'power': '1', 'toughness': '1', 'colors': ['W']})
    token = next(c for c in s.state.cards.values() if c.id not in before_ids and c.is_token)
    cast(s, 'Murder', [token.id])
    before = len(s.state.zones['p2:library'])
    endstep(s)
    assert len(s.state.zones['p2:library']) == before
    roundtrip(s)


def test_repeat_entries_of_same_physical_card_and_resolved_instant_sorcery_count(cards):
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase
    s = table(cards)
    cast(s, AURA, ['p2'])
    to_phase(s, 'main1', turn=2)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Murder', [bear.id])
    cast(s, 'Unearth', [bear.id], player='p2')
    cast(s, 'Murder', [bear.id])
    before = len(s.state.zones['p2:library'])
    endstep(s, turn=2)
    assert len(s.state.zones['p2:library']) == before - 3
    roundtrip(s)


def test_copied_spell_is_not_a_third_card_entry_for_ravenous_or_fraying(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase
    s = table(cards)
    cast(s, AURA, ['p2'])
    to_phase(s, 'main1', turn=2)
    first = put(s, 'Shock', 'hand', 'p2')
    copy = put(s, 'Reverberate', 'hand', 'p2')
    mana(s, 'p2', R=3)
    wait_priority(s, 'p2')
    act(s, 'p2', type='set_prefs', hold_priority=True)
    act(s, 'p2', type='cast_spell', card_id=first.id, targets=['p1'])
    act(s, 'p2', type='cast_spell', card_id=copy.id, targets=[first.id])
    act(s, 'p2', type='set_prefs', hold_priority=False)
    settle(s)
    spell = trap(s)
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, alt_cost=f'{spell.id}:0', targets=['p2'])
    before = len(s.state.zones['p2:library'])
    endstep(s, turn=2)
    assert len(s.state.zones['p2:library']) == before - 2
    roundtrip(s)


def test_cards_discarded_from_hand_count(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    s = table(cards)
    cast(s, AURA, ['p2'])
    put(s, 'Shock', 'hand', 'p2')
    put(s, 'Reverberate', 'hand', 'p2')
    put(s, 'Grizzly Bears', 'hand', 'p2')
    cast(s, 'Mind Rot', ['p2'])
    d = s.state.rules.decision
    assert d and d.player == 'p2'
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[o.id for o in d.options][:2])
    settle(s)
    before = len(s.state.zones['p2:library'])
    endstep(s)
    assert len(s.state.zones['p2:library']) == before - 2
    roundtrip(s)


def test_replacement_to_exile_never_counts_as_graveyard_entry(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    s = table(cards)
    cast(s, AURA, ['p2'])
    cast(s, 'Rest in Peace')
    cast(s, 'Thought Scour', ['p2'])
    before = len(s.state.zones['p2:library'])
    endstep(s)
    assert len(s.state.zones['p2:library']) == before
    spell = trap(s)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, alt_cost=f'{spell.id}:0', targets=['p2'])
    roundtrip(s)


def test_departed_aura_uses_its_last_enchanted_player_for_pending_trigger(cards):
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase
    s = table(cards)
    aura = cast(s, AURA, ['p2'])
    cast(s, 'Thought Scour', ['p2'])
    before = len(s.state.zones['p2:library'])
    to_phase(s, 'end', turn=1)
    assert s.state.zones['stack']
    cast(s, 'Disenchant', [aura.id])
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    assert len(s.state.zones['p2:library']) == before - 2
    roundtrip(s)


def test_blinked_aura_attached_to_new_player_does_not_rebind_old_source_trigger(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave30m_durations import to_phase
    s = table(cards)
    aura = cast(s, AURA, ['p2'])
    cast(s, 'Thought Scour', ['p2'])
    old = s.state.rules.object_id(aura.id)
    before = len(s.state.zones['p2:library'])
    other = len(s.state.zones['p3:library'])
    to_phase(s, 'end', turn=1)
    cast(s, 'Flicker of Fate', [aura.id])
    d = s.state.rules.decision
    assert d and any(o.id == 'p3' for o in d.options)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['p3'])
    settle(s)
    assert s.state.rules.object_id(aura.id) != old and s.state.cards[aura.id].attached_player == 'p3'
    assert len(s.state.zones['p2:library']) == before - 2
    assert len(s.state.zones['p3:library']) == other
    roundtrip(s)


def test_new_turn_resets_history_even_when_cards_remain_in_graveyard(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase
    s = table(cards)
    cast(s, AURA, ['p2'])
    cast(s, 'Thought Scour', ['p2'])
    bear = put(s, 'Grizzly Bears', 'exile', 'p2')
    cast(s, 'Pull from Eternity', [bear.id])
    endstep(s)
    to_phase(s, 'main1', turn=2)
    assert len(s.state.zones['p2:graveyard']) == 5  # The Bears entered twice, but are one physical card.
    spell = trap(s)
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, alt_cost=f'{spell.id}:0', targets=['p2'])
    before = len(s.state.zones['p2:library'])
    endstep(s, turn=2)
    assert len(s.state.zones['p2:library']) == before
    roundtrip(s)
