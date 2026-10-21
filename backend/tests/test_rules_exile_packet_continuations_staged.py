"""Canonical native exile packet gameplay; production hooks and real game actions."""
from __future__ import annotations

import pytest

from tests import test_rules_exile_packet_continuations_foundation as foundation
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_refused_look import stack_library
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave4h_activation_costs import ability
from tests.test_rules_wave30m_durations import to_phase

DATA = foundation.DATA
cards = foundation.cards



def setup(cards):
    import json

    ns = [c['name'] for c in json.loads(DATA.read_text())]
    ns += ['Murder', 'Grizzly Bears', 'Opt', 'Lightning Bolt']
    s = table(cards, ns, ns, ns)
    to_phase(s, 'main1', turn=1)
    return s


def test_native_stolen_goods_actual_delayed_free_cast_uses_exact_nonland_found(cards):
    s = setup(cards)
    top = stack_library(s, ['Island', 'Grizzly Bears'], pid='p2')
    cast(s, 'Stolen Goods', targets=['p2'])
    assert s.state.rules.decision is None
    assert all(s.state.cards[c].zone == 'p2:exile' for c in top)
    act(s, 'p1', type='cast_spell', card_id=top[1], free=True)
    settle(s)
    assert s.state.cards[top[1]].zone == 'p1:battlefield'
    assert s.state.cards[top[1]].owner == 'p2'
    assert s.state.cards[top[0]].zone == 'p2:exile'
    roundtrip(s)


def test_native_nivix_actual_activation_then_normal_cost_instant_cast(cards):
    s = setup(cards)
    source = put(s, 'Nivix, Aerie of the Firemind', 'battlefield')
    top = stack_library(s, ['Lightning Bolt'])
    mana(s, C=2, U=1, R=2)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, '{2}'))
    settle(s)
    assert s.state.rules.decision is None and s.state.cards[top[0]].zone == 'p1:exile'
    act(s, 'p1', type='cast_spell', card_id=top[0], targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_native_muse_actual_x_free_cast_then_hand_and_random_bottom_partition(cards):
    s = setup(cards)
    top = stack_library(s, ['Lightning Bolt', 'Murder', 'Grizzly Bears'])
    cast(s, 'Muse Vortex', x_value=3)
    assert s.state.rules.decision is not None
    option = next(o.id for o in s.state.rules.decision.options if o.card_id == top[0])
    answer(s, [option])
    answer(s, ['p2'])
    assert s.state.players['p2'].life == 37
    assert s.state.cards[top[1]].zone == 'p1:hand'
    assert s.state.cards[top[2]].zone == 'p1:library'
    roundtrip(s)


def test_native_augury_actual_land_entry_then_native_type_slot_free_cast(cards):
    s = setup(cards)
    top = stack_library(s, ['Forest', 'Memnite', 'Ornithopter', 'Phyrexian Walker'])
    cast(s, "Aminatou's Augury")
    assert s.state.rules.decision is not None
    answer(s, [top[0]])
    assert s.state.cards[top[0]].zone == 'p1:battlefield'
    assert s.state.rules.lands_this_turn('p1', s.state.turn.number) == 0
    for i, kind in enumerate(['Artifact', 'Creature']):
        act(s, 'p1', type='cast_spell', card_id=top[i + 1], free=True)
        if i == 0:
            option = next(o.id for o in s.state.rules.decision.options if kind + ' permission' in o.label)
            answer(s, [option])
        settle(s)
        assert s.state.cards[top[i + 1]].zone == 'p1:battlefield'
    roundtrip(s)


def test_native_dead_mans_chest_lki_owner_library_and_source_independent_any_type_cast(cards):
    s = setup(cards)
    host = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    top = stack_library(s, ['Lightning Bolt', 'Opt'], pid='p2')
    aura = cast(s, "Dead Man's Chest", targets=[host.id])
    cast(s, 'Murder', targets=[host.id])
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    assert all(s.state.cards[c].zone == 'p2:exile' for c in top)
    act(s, 'p1', type='clear_mana', player='p1')
    mana(s, C=1)
    act(s, 'p1', type='cast_spell', card_id=top[0], targets=['p3'])
    settle(s)
    assert s.state.players['p3'].life == 37
    assert s.state.cards[top[0]].zone == 'p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('decline', [True, False])
def test_native_bre_actual_end_step_immediate_cast_or_exact_hand_fallback(cards, decline):
    s = setup(cards)
    put(s, 'Bre of Clan Stoutarm', 'battlefield')
    act(s, 'p1', type='life', player='p1', delta=3)
    top = stack_library(s, ['Forest', 'Lightning Bolt'])
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.rules.decision is not None
    if decline:
        answer(s, [])
        assert s.state.cards[top[1]].zone == 'p1:hand'
    else:
        option = next(o.id for o in s.state.rules.decision.options if o.card_id == top[1])
        answer(s, [option])
        answer(s, ['p2'])
        assert s.state.players['p2'].life == 37
    assert s.state.cards[top[0]].zone == 'p1:exile'
    roundtrip(s)


def test_native_crabomination_exiles_exact_library_and_random_hand_grave_packet(cards):
    s = setup(cards)
    old_hand = list(s.state.zones['p2:hand'])
    if old_hand:
        act(s, 'p2', type='move', card_ids=old_hand, to={'player': 'p2', 'zone': 'exile'})
    hand = put(s, 'Grizzly Bears', 'hand', 'p2')
    grave = put(s, 'Opt', 'graveyard', 'p2')
    top = stack_library(s, ['Lightning Bolt'], pid='p2')
    cast(s, 'Crabomination')
    answer(s, ['p2'])
    d = s.state.rules.decision
    assert d is not None
    assert {o.card_id for o in d.options if o.card_id} == {hand.id, grave.id, top[0]}
    option = next(o.id for o in d.options if o.card_id == top[0])
    answer(s, [option])
    answer(s, ['p2'])
    assert s.state.cards[hand.id].zone == 'p2:exile' and s.state.cards[grave.id].zone == 'p2:exile'
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_native_magus_actual_sacrifice_shuffle_then_free_normal_timing_permission(cards):
    s = setup(cards)
    source = put(s, 'Magus of the Mind', 'battlefield')
    to_phase(s, 'main1', turn=4)
    library = list(s.state.zones['p1:library'])
    act(s, 'p1', type='move', card_ids=library, to={'player': 'p1', 'zone': 'exile'})
    stack_library(s, ['Memnite'])
    mana(s, U=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, '{U}'))
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    permissions = [p for p in s.state.rules.permissions if p.player == 'p1' and p.free]
    assert len(permissions) == 1
    cid = permissions[0].card
    assert s.state.cards[cid].name == 'Memnite'
    act(s, 'p1', type='cast_spell', card_id=cid, free=True)
    settle(s)
    assert s.state.cards[cid].zone == 'p1:battlefield'
    roundtrip(s)


def test_native_strago_actual_creature_cast_gets_haste_and_end_step_sacrifice(cards):
    s = setup(cards)
    source = put(s, 'Strago and Relm', 'battlefield')
    to_phase(s, 'main1', turn=4)
    top = stack_library(s, ['Island', 'Grizzly Bears'], pid='p2')
    mana(s, C=2, R=1)
    act(s, 'p1', type='activate_ability', card_id=source.id,
        ability=ability(s, source, 'Sketch and Lore'), targets=['p2'])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    assert any(o.card_id == top[1] for o in d.options), d.model_dump()
    answer(s, [next(o.id for o in d.options if o.card_id == top[1])])
    assert s.state.cards[top[1]].zone == 'p1:battlefield'
    import random

    from app.rules.plan import Plan

    assert 'haste' in Plan(s.state, 'p1', cards, random.Random(1)).ch(s.state.cards[top[1]]).keywords
    to_phase(s, 'end', turn=4)
    settle(s)
    assert s.state.cards[top[1]].zone == 'p2:graveyard'
    assert s.state.cards[top[0]].zone == 'p2:exile'
    roundtrip(s)


def test_native_triple_triad_strict_foreign_mana_value_ceiling_and_own_free_card(cards):
    s = setup(cards)
    put(s, 'Triple Triad', 'battlefield')
    to_phase(s, 'end', turn=3)
    own = stack_library(s, ['Grizzly Bears'])
    lesser = stack_library(s, ['Lightning Bolt'], pid='p2')
    equal = stack_library(s, ['Grizzly Bears'], pid='p3')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    allowed = {p.card for p in s.state.rules.permissions if p.player == 'p1' and p.free}
    assert own[0] in allowed and lesser[0] in allowed and equal[0] not in allowed
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='cast_spell', card_id=own[0], free=True)
    settle(s)
    assert s.state.cards[own[0]].zone == 'p1:battlefield'
    act(s, 'p1', type='cast_spell', card_id=lesser[0], free=True, targets=['p3'])
    settle(s)
    assert s.state.players['p3'].life == 37
    roundtrip(s)


def test_native_chandra_first_loyalty_discards_then_exiles_exact_three(cards):
    s = setup(cards)
    source = put(s, 'Chandra, Heart of Fire', 'battlefield')
    held = put(s, 'Murder', 'hand')
    top = stack_library(s, ['Forest', 'Grizzly Bears', 'Lightning Bolt'])
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    settle(s)
    assert s.state.cards[held.id].zone == 'p1:graveyard'
    assert all(s.state.cards[c].zone == 'p1:exile' for c in top)
    act(s, 'p1', type='play_land', card_id=top[0])
    assert s.state.cards[top[0]].zone == 'p1:battlefield'
    mana(s, G=2)
    act(s, 'p1', type='cast_spell', card_id=top[1])
    settle(s)
    assert s.state.cards[top[1]].zone == 'p1:battlefield'
    roundtrip(s)


def test_native_arvinox_raw_foreign_threshold_then_private_bottom_cast_source_independent(cards):
    from tests.test_rules_wave4h_activation_costs import ch

    s = setup(cards)
    source = put(s, 'Arvinox, the Mind Flail', 'battlefield')
    assert not ch(s, source).is_creature
    foreign = []
    for name in ['Memnite', 'Ornithopter', 'Phyrexian Walker']:
        c = put(s, name, 'battlefield', 'p2')
        act(s, 'p1', type='set_controller', card_ids=[c.id], player='p1')
        foreign.append(c.id)
    assert ch(s, s.state.cards[source.id]).is_creature
    act(s, 'p1', type='move', card_ids=[foreign[0]], to={'player': 'p2', 'zone': 'graveyard'})
    assert not ch(s, s.state.cards[source.id]).is_creature
    bottom = put(s, 'Grizzly Bears', 'library', 'p2')
    # Native move-to-bottom preserves this exact physical card before the end-step trigger.
    act(s, 'p1', type='move', card_ids=[bottom.id], to={'player': 'p2', 'zone': 'library'}, position='bottom')
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[bottom.id].zone == 'p2:exile' and s.state.cards[bottom.id].face_down
    assert any(p.card == bottom.id and p.player == 'p1' for p in s.state.rules.permissions)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    to_phase(s, 'main1', turn=4)
    mana(s, W=2)
    act(s, 'p1', type='cast_spell', card_id=bottom.id)
    settle(s)
    assert s.state.cards[bottom.id].zone == 'p1:battlefield'
    assert s.state.cards[bottom.id].owner == 'p2' and not s.state.cards[bottom.id].face_down
    roundtrip(s)


def test_native_chandra_ultimate_native_combined_search_then_normal_cost_cast(cards):
    from tests.game_helpers import mana_pool

    s = setup(cards)
    source = put(s, 'Chandra, Heart of Fire', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=9)
    grave = put(s, 'Lightning Bolt', 'graveyard')
    library = stack_library(s, ['Burning Curiosity'])[0]
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and any(o.card_id == grave.id for o in d.options)
    assert d.max_choices >= 2
    answer(s, [next(o.id for o in d.options if o.card_id == cid) for cid in [grave.id, library]])
    assert s.state.cards[grave.id].zone == 'p1:exile'
    assert s.state.cards[library].zone == 'p1:exile'
    assert mana_pool(s).get('R', 0) == 6
    act(s, 'p1', type='cast_spell', card_id=grave.id, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    act(s, 'p1', type='cast_spell', card_id=library)
    settle(s)
    assert s.state.cards[library].zone == 'p1:graveyard'
    roundtrip(s)


def test_native_rampage_destroys_only_opponent_artifacts_counts_prior_death_and_returns_hasty_creature(cards):
    from tests.test_rules_wave4h_activation_costs import ch

    s = setup(cards)
    own = put(s, 'Memnite', 'battlefield')
    enemy = put(s, 'Ornithopter', 'battlefield', 'p2')
    prior = put(s, 'Phyrexian Walker', 'battlefield', 'p3')
    act(s, 'p3', type='move', card_ids=[prior.id], to={'player': 'p3', 'zone': 'graveyard'})
    top = stack_library(s, ['Grizzly Bears', 'Lightning Bolt'])
    cast(s, "Anzrag's Rampage")
    d = s.state.rules.decision
    assert d is not None and any(o.card_id == top[0] for o in d.options)
    answer(s, [next(o.id for o in d.options if o.card_id == top[0])])
    assert s.state.cards[own.id].zone == 'p1:battlefield'
    assert s.state.cards[enemy.id].zone == 'p2:graveyard'
    assert s.state.cards[top[0]].zone == 'p1:battlefield'
    assert s.state.cards[top[1]].zone == 'p1:exile'
    assert 'haste' in ch(s, s.state.cards[top[0]]).keywords
    roundtrip(s)
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[top[0]].zone == 'p1:hand'


def test_native_meeting_actual_three_color_spell_permission_and_restricted_mana(cards):
    from app.game.errors import ActionError

    s = setup(cards)
    top = stack_library(s, ['Rhox War Monk', 'Lightning Bolt'])
    second = put(s, 'Meeting of the Five', 'hand')
    mana(s, C=3, W=1, U=1, B=1, R=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=second.id)
    settle(s)
    assert len([u for u in s.state.players['p1'].mana_units if u.only]) == 10
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=top[1], targets=['p2'])
    act(s, 'p1', type='cast_spell', card_id=top[0])
    settle(s)
    assert s.state.cards[top[0]].zone == 'p1:battlefield'
    assert len([u for u in s.state.players['p1'].mana_units if u.only]) == 7
    roundtrip(s)


def test_native_mezzio_actual_attack_exiles_all_players_and_blitz_sacrifices(cards):
    s = setup(cards)
    source = put(s, 'Mezzio Mugger', 'hand')
    mana(s, C=2, R=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=f'{source.id}:1')
    settle(s)
    top1 = stack_library(s, ['Lightning Bolt'])
    top2 = stack_library(s, ['Grizzly Bears'], pid='p2')
    top3 = stack_library(s, ['Murder'], pid='p3')
    to_phase(s, 'declare_attackers', turn=1)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    settle(s)
    assert all(s.state.cards[c].zone.endswith(':exile') for c in [*top1, *top2, *top3])
    to_phase(s, 'main2', turn=1)
    mana(s, W=2)
    act(s, 'p1', type='cast_spell', card_id=top2[0])
    settle(s)
    assert s.state.cards[top2[0]].zone == 'p1:battlefield'
    before_draw = len(s.state.zones['p1:hand'])
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert len(s.state.zones['p1:hand']) == before_draw + 1
    roundtrip(s)


def test_native_bre_other_creature_activation_and_nivix_colorless_independent(cards):
    from tests.game_helpers import mana_pool
    from tests.test_rules_wave4h_activation_costs import ch

    s = setup(cards)
    bre = put(s, 'Bre of Clan Stoutarm', 'battlefield')
    host = put(s, 'Grizzly Bears', 'battlefield')
    land = put(s, 'Nivix, Aerie of the Firemind', 'battlefield')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='activate_ability', card_id=land.id, ability=0)
    assert mana_pool(s).get('C', 0) == 1
    mana(s, W=1)
    act(s, 'p1', type='activate_ability', card_id=bre.id, ability=0, targets=[host.id])
    settle(s)
    assert {'flying', 'lifelink'} <= ch(s, s.state.cards[host.id]).keywords
    roundtrip(s)


def test_native_chandra_second_loyalty_deals_real_two_damage(cards):
    s = setup(cards)
    source = put(s, 'Chandra, Heart of Fire', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 38
    roundtrip(s)


def test_native_gonti_foreign_spell_creates_treasure_for_actual_caster(cards):
    s = setup(cards)
    put(s, 'Gonti, Night Minister', 'battlefield')
    top = stack_library(s, ['Grizzly Bears'], pid='p2')
    cast(s, 'Stolen Goods', targets=['p2'])
    act(s, 'p1', type='cast_spell', card_id=top[0], free=True)
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.name == 'Treasure' and c.zone.endswith(':battlefield')]
    assert len(tokens) == 1 and tokens[0].controller == 'p1'
    roundtrip(s)


def test_native_gonti_actual_combat_damage_private_packet_can_play_foreign_land(cards):
    s = setup(cards)
    put(s, 'Gonti, Night Minister', 'battlefield')
    source = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'declare_attackers', turn=4)
    top = stack_library(s, ['Island'], pid='p2')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    to_phase(s, 'main2', turn=4)
    settle(s)
    permitted = [p.card for p in s.state.rules.permissions if p.player == 'p1' and p.card in s.state.cards and s.state.cards[p.card].owner == 'p2']
    assert len(permitted) == 1, ([p.model_dump() for p in s.state.rules.permissions], [(c.name, c.zone) for c in s.state.cards.values() if c.zone.endswith(':exile')])
    top = permitted
    assert s.state.cards[top[0]].zone == 'p2:exile' and s.state.cards[top[0]].face_down
    assert any(p.player == 'p1' and p.card == top[0] for p in s.state.rules.permissions)
    act(s, 'p1', type='play_land', card_id=top[0])
    assert s.state.cards[top[0]].zone == 'p1:battlefield' and not s.state.cards[top[0]].face_down
    roundtrip(s)


def test_native_curse_actual_enchant_player_trample_and_damage_packet(cards):
    from tests.test_rules_wave4h_activation_costs import ch

    s = setup(cards)
    curse = cast(s, 'Curse of Hospitality', targets=['p2'])
    source = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'declare_attackers', turn=4)
    top = stack_library(s, ['Island'], pid='p2')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    settle(s)
    assert 'trample' in ch(s, s.state.cards[source.id]).keywords
    to_phase(s, 'main2', turn=4)
    settle(s)
    assert s.state.cards[top[0]].zone == 'p2:exile'
    act(s, 'p1', type='move', card_ids=[curse.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='play_land', card_id=top[0])
    assert s.state.cards[top[0]].zone == 'p1:battlefield'
    roundtrip(s)


def test_native_crabomination_emerge_from_artifact_actual_paid_cost(cards):
    s = setup(cards)
    victim = put(s, 'Memnite', 'battlefield')
    source = put(s, 'Crabomination', 'hand')
    mana(s, C=5, B=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=f'{source.id}:0',
        cost_choices=[{'component': 0, 'cards': [victim.id]}])
    assert s.state.cards[victim.id].zone == 'p1:graveyard'
    settle(s)
    answer(s, ['p2'])
    decision = s.state.rules.decision
    assert decision is not None
    answer(s, [])
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('blight', [False, True])
def test_native_burning_curiosity_actual_optional_blight_and_next_turn_play(blight, cards):
    s = setup(cards)
    host = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, 'Burning Curiosity', 'hand')
    top = stack_library(s, ['Lightning Bolt', 'Forest', 'Murder'])
    mana(s, C=2, R=1)
    act(s, 'p1', type='cast_spell', card_id=source.id,
        optional_costs=[f'{source.id}:blight'] if blight else [],
        cost_choices=[{'component': 0, 'cards': [host.id]}] if blight else [])
    settle(s)
    assert s.state.cards[top[0]].zone == 'p1:exile' and s.state.cards[top[1]].zone == 'p1:exile'
    assert (s.state.cards[top[2]].zone == 'p1:exile') == blight
    assert s.state.cards[host.id].counters.get('-1/-1', 0) == int(blight)
    to_phase(s, 'main1', turn=4)
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=top[0], targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    act(s, 'p1', type='play_land', card_id=top[1])
    assert s.state.cards[top[1]].zone == 'p1:battlefield'
    roundtrip(s)


def test_native_liara_frozen_attack_player_count_reduces_all_exile_permissions_not_hand(cards):
    from app.game.errors import ActionError

    s = setup(cards)
    liara = put(s, 'Commander Liara Portyr', 'battlefield')
    attacker = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Arvinox, the Mind Flail', 'battlefield')
    other_card = put(s, 'Grizzly Bears', 'library', 'p2')
    act(s, 'p1', type='move', card_ids=[other_card.id], to={'player': 'p2', 'zone': 'library'}, position='bottom')
    to_phase(s, 'end', turn=1)
    settle(s)
    other = [p.card for p in s.state.rules.permissions if p.player == 'p1' and p.card in s.state.cards
             and s.state.cards[p.card].name == 'Grizzly Bears' and s.state.cards[p.card].owner == 'p2']
    assert len(other) == 1
    to_phase(s, 'declare_attackers', turn=4)
    top = stack_library(s, ['Rhox War Monk'])
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': attacker.id, 'target': 'p2'}])
    settle(s)
    modifier = s.state.rules.cost_modifiers[-1]
    assert modifier.delta == -1 and modifier.from_zones == ['exile']
    act(s, 'p1', type='move', card_ids=[liara.id], to={'player': 'p1', 'zone': 'graveyard'})
    to_phase(s, 'main2', turn=4)
    act(s, 'p1', type='clear_mana', player='p1')
    mana(s, G=1)
    # Arvinox grants ordinary paid casting, so Liara must supply the generic reduction.
    act(s, 'p1', type='cast_spell', card_id=other[0])
    settle(s)
    assert s.state.cards[other[0]].zone == 'p1:battlefield'
    held = put(s, 'Grizzly Bears', 'hand')
    mana(s, G=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=held.id)
    assert s.state.cards[top[0]].zone == 'p1:exile'
    roundtrip(s)
