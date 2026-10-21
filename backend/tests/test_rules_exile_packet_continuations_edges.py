"""Authority expires and object departures never renew an exile packet permission."""
from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests import test_rules_exile_packet_continuations_staged as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_refused_look import stack_library
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave4h_activation_costs import ability, ch
from tests.test_rules_wave30m_durations import to_phase

cards = gameplay.cards


@pytest.mark.parametrize('name', [c['name'] for c in json.loads(gameplay.DATA.read_text())][:20])
def test_exact_canonical_definitions_are_complete(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('mode', ['stolen', 'nivix', 'burning', 'chandra'])
def test_timed_packet_permission_does_not_follow_departure_and_return(cards, mode):
    s = gameplay.setup(cards)
    top = stack_library(s, ['Lightning Bolt'], pid='p2' if mode == 'stolen' else 'p1')
    cid = top[0]
    if mode == 'stolen':
        cast(s, 'Stolen Goods', targets=['p2'])
    elif mode == 'nivix':
        source = put(s, 'Nivix, Aerie of the Firemind', 'battlefield')
        mana(s, C=2, U=1, R=1)
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, '{2}'))
        settle(s)
    elif mode == 'burning':
        cast(s, 'Burning Curiosity')
    else:
        source = put(s, 'Chandra, Heart of Fire', 'battlefield')
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
        settle(s)
    owner = s.state.cards[cid].owner
    act(s, 'p1', type='move', card_ids=[cid], to={'player': owner, 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[cid], to={'player': owner, 'zone': 'exile'})
    mana(s, R=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=cid, targets=['p2'], free=mode == 'stolen')
    roundtrip(s)


def test_stolen_goods_obeys_normal_timing_and_end_of_turn_expiry(cards):
    s = gameplay.setup(cards)
    cid = stack_library(s, ['Grizzly Bears'], pid='p2')[0]
    cast(s, 'Stolen Goods', targets=['p2'])
    to_phase(s, 'declare_attackers', turn=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=cid, free=True)
    to_phase(s, 'main1', turn=4)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=cid, free=True)
    roundtrip(s)


def test_nivix_cannot_cast_permanent_and_permission_ends_by_next_upkeep(cards):
    s = gameplay.setup(cards)
    source = put(s, 'Nivix, Aerie of the Firemind', 'battlefield')
    cid = stack_library(s, ['Grizzly Bears'])[0]
    mana(s, C=2, U=1, R=1, G=2)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, '{2}'))
    settle(s)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=cid)
    to_phase(s, 'upkeep', turn=4)
    assert not any(p.card == cid for p in s.state.rules.permissions)
    roundtrip(s)


def test_meeting_exact_color_count_uses_spell_colors_and_restricted_mana_rejects_four_color_hand_spell(cards):
    s = gameplay.setup(cards)
    cid = stack_library(s, ['Doran, the Siege Tower'])[0]
    held = put(s, 'Glint-Eye Nephilim', 'hand')
    source = put(s, 'Meeting of the Five', 'hand')
    mana(s, C=3, W=1, U=1, B=1, R=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    # The rejected four-color spell has toughness2; the accepted three-color
    # spell has toughness5. This distinguishes colors from the old stat fallback.
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=held.id)
    assert len(s.state.players['p1'].mana_units) == 10
    act(s, 'p1', type='cast_spell', card_id=cid)
    settle(s)
    assert s.state.cards[cid].zone == 'p1:battlefield'
    assert len(s.state.players['p1'].mana_units) == 7
    roundtrip(s)


@pytest.mark.parametrize('planeswalker', [False, True])
def test_curse_opponent_controlled_attacker_gets_grant_only_when_attacking_enchanted_player(cards, planeswalker):
    s = gameplay.setup(cards)
    cast(s, 'Curse of Hospitality', targets=['p2'])
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    walker = put(s, 'Jace, Architect of Thought', 'battlefield', 'p2')
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=4)
    to_phase(s, 'declare_attackers', turn=3)
    cid = stack_library(s, ['Island'], pid='p2')[0]
    act(s, 'p3', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': walker.id if planeswalker else 'p2'}])
    settle(s)
    assert ('trample' in ch(s, s.state.cards[bear.id]).keywords) == (not planeswalker)
    to_phase(s, 'main2', turn=3)
    settle(s)
    if planeswalker:
        assert s.state.cards[cid].zone == 'p2:library'
        assert not any(p.card == cid for p in s.state.rules.permissions)
    else:
        assert s.state.cards[cid].zone == 'p2:exile'
        assert any(p.card == cid and p.player == 'p3' for p in s.state.rules.permissions)
        assert not any(p.card == cid and p.player == 'p1' for p in s.state.rules.permissions)
        act(s, 'p3', type='play_land', card_id=cid)
        assert s.state.cards[cid].zone == 'p3:battlefield'
    roundtrip(s)


def test_gonti_treasure_belongs_to_foreign_spell_caster_and_own_spell_does_not_trigger(cards):
    s = gameplay.setup(cards)
    put(s, 'Gonti, Night Minister', 'battlefield')
    to_phase(s, 'main1', turn=3)
    cid = stack_library(s, ['Grizzly Bears'], pid='p2')[0]
    source = put(s, 'Stolen Goods', 'hand', 'p3')
    mana(s, pid='p3', C=3, U=1)
    act(s, 'p3', type='cast_spell', card_id=source.id, targets=['p2'])
    settle(s)
    assert not any(c.name == 'Treasure' for c in s.state.cards.values())
    act(s, 'p3', type='cast_spell', card_id=cid, free=True)
    settle(s)
    treasures = [c for c in s.state.cards.values() if c.name == 'Treasure']
    assert len(treasures) == 1 and treasures[0].controller == 'p3'
    roundtrip(s)


@pytest.mark.parametrize('planeswalker', [False, True])
def test_liara_counts_attacked_players_not_attackers_or_planeswalker_defenders(cards, planeswalker):
    s = gameplay.setup(cards)
    put(s, 'Commander Liara Portyr', 'battlefield')
    first = put(s, 'Grizzly Bears', 'battlefield')
    second = put(s, 'Memnite', 'battlefield')
    walker = put(s, 'Jace, Architect of Thought', 'battlefield', 'p2')
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=4)
    to_phase(s, 'declare_attackers', turn=4)
    top = stack_library(s, ['Lightning Bolt', 'Opt'])
    attackers = [{'card_id': first.id, 'target': walker.id if planeswalker else 'p2'},
                 {'card_id': second.id, 'target': walker.id if planeswalker else 'p3'}]
    act(s, 'p1', type='declare_attackers', attackers=attackers)
    settle(s)
    n = 0 if planeswalker else 2
    assert s.state.rules.cost_modifiers[-1].delta == -n
    assert sum(s.state.cards[cid].zone == 'p1:exile' for cid in top) == n
    roundtrip(s)


def test_crabomination_emerge_sacrificed_artifact_reduces_generic_before_etb(cards):
    s = table(cards, ['Crabomination', 'Sol Ring'], ['Grizzly Bears'], [])
    to_phase(s, 'main1', turn=1)
    victim = put(s, 'Sol Ring', 'battlefield')
    source = put(s, 'Crabomination', 'hand')
    stack_library(s, ['Grizzly Bears'], pid='p2')
    mana(s, C=4, B=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=f'{source.id}:0',
        cost_choices=[{'component': 0, 'cards': [victim.id]}])
    assert s.state.cards[victim.id].zone == 'p1:graveyard'
    assert not s.state.players['p1'].mana_units
    settle(s)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['p2'])
    settle(s)
    d = s.state.rules.decision
    assert d.resume['step'] == 'free_cast_pick'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)
