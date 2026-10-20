"""Canonical gameplay through production grammar, callbacks and native engines."""
from __future__ import annotations

import pytest

from app.rules import scripts
from tests import test_rules_exile_authority_continuations_foundation as foundation
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_exile_packet_continuations_cold import fresh_action
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_refused_look import stack_library
from tests.test_rules_wave4h_activation_costs import ability, ch
from tests.test_rules_wave30m_durations import to_phase

cards = foundation.cards


@pytest.fixture(autouse=True)
def staged():
    """Fresh parse caches only: all grammar and callbacks are production registered."""
    scripts._cached.cache_clear()
    yield
    scripts._cached.cache_clear()


def setup(cards, *names):
    return foundation.setup(cards, *names)


def test_staged_hex_actual_hand_packet_draw_then_normal_paid_cast(cards):
    s = setup(cards, 'Hex Magic')
    held = put(s, 'Grizzly Bears', 'hand')
    stack_library(s, ['Forest'])
    cast(s, 'Hex Magic')
    assert s.state.cards[held.id].zone == 'p1:exile'
    assert len(s.state.zones['p1:hand']) == 1
    act(s, 'p1', type='clear_mana', player='p1')
    mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=held.id)
    settle(s)
    assert s.state.cards[held.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_staged_mnemonic_actual_foreign_paid_cast_and_exact_end_step_return(cards):
    s = setup(cards, 'Mnemonic Betrayal')
    foreign = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    rest = put(s, 'Lightning Bolt', 'graveyard', 'p3')
    source = cast(s, 'Mnemonic Betrayal')
    assert s.state.cards[source.id].zone == 'p1:exile'
    assert s.state.cards[foreign.id].zone == 'p2:exile'
    act(s, 'p1', type='clear_mana', player='p1')
    mana(s, C=2)
    act(s, 'p1', type='cast_spell', card_id=foreign.id)
    settle(s)
    assert s.state.cards[foreign.id].zone == 'p1:battlefield'
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[rest.id].zone == 'p3:graveyard'
    assert s.state.cards[source.id].zone == 'p1:exile'
    roundtrip(s)


def test_staged_xander_actual_exile_then_required_life_alternative_not_mana(cards):
    s = setup(cards, "Xander's Pact")
    cid = stack_library(s, ['Grizzly Bears'], pid='p2')[0]
    stack_library(s, ['Island'], pid='p3')
    cast(s, "Xander's Pact")
    act(s, 'p1', type='clear_mana', player='p1')
    life = s.state.players['p1'].life
    act(s, 'p1', type='cast_spell', card_id=cid, free=True)
    settle(s)
    assert s.state.players['p1'].life == life - 2
    assert s.state.cards[cid].zone == 'p1:battlefield'
    roundtrip(s)


def test_staged_flameskull_real_death_grants_one_shared_play_and_cannot_block(cards):
    s = setup(cards, 'Flameskull', 'Murder')
    source = put(s, 'Flameskull', 'battlefield')
    top = stack_library(s, ['Forest'])[0]
    cast(s, 'Murder', targets=[source.id])
    assert s.state.cards[source.id].zone == 'p1:exile'
    assert s.state.cards[top].zone == 'p1:exile'
    assert len({p.group for p in s.state.rules.permissions if p.card in (source.id, top)}) == 1
    act(s, 'p1', type='play_land', card_id=top)
    assert not any(p.card == source.id for p in s.state.rules.permissions)
    roundtrip(s)


def test_staged_allure_actual_opponent_choice_then_hand_before_immediate_cast(cards):
    s = setup(cards, 'Allure of the Unknown')
    ids = stack_library(s, ['Grizzly Bears', 'Forest', 'Lightning Bolt'])
    cast(s, 'Allure of the Unknown')
    assert s.state.rules.decision.resume['step'] == 'exile_authority41_opponent'
    answer(s, ['p2'])
    assert s.state.rules.decision.player == 'p2'
    answer(s, [ids[0]])
    assert all(s.state.cards[cid].zone == 'p1:hand' for cid in ids[1:])
    d = s.state.rules.decision
    assert d.player == 'p2'
    answer(s, [next(o.id for o in d.options if o.card_id == ids[0])])
    assert s.state.cards[ids[0]].zone == 'p2:battlefield'
    assert s.state.cards[ids[0]].owner == 'p1'
    roundtrip(s)


def test_staged_mist_actual_manifest_then_face_up_exile_cost_and_play(cards):
    s = setup(cards, 'Primordial Mist')
    source = put(s, 'Primordial Mist', 'battlefield')
    cid = stack_library(s, ['Grizzly Bears'])[0]
    to_phase(s, 'end', turn=1)
    settle(s)
    answer(s, ['yes'])
    cid = next(c.id for c in s.state.cards.values() if c.owner == 'p1' and c.zone == 'p1:battlefield' and c.face_down)
    assert s.state.cards[cid].zone == 'p1:battlefield' and s.state.cards[cid].face_down
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, 'Exile'),
        cost_choices=[{'component': 0, 'cards': [cid]}])
    assert s.state.cards[cid].zone == 'p1:exile' and not s.state.cards[cid].face_down
    settle(s)
    mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=cid)
    settle(s)
    assert s.state.cards[cid].zone == 'p1:battlefield'
    assert ch(s, s.state.cards[cid]).name == 'Grizzly Bears'
    roundtrip(s)


@pytest.mark.parametrize('mode', ['bismuth', 'cruelclaw'])
def test_staged_required_immediate_alternative_uses_native_atomic_cast_payment(cards, tmp_path, mode):
    name = 'Bismuth Mindrender' if mode == 'bismuth' else 'The Infamous Cruelclaw'
    s = setup(cards, name)
    source = put(s, name, 'battlefield')
    to_phase(s, 'declare_attackers', turn=4)
    cid = stack_library(s, ['Grizzly Bears'], pid='p2' if mode == 'bismuth' else 'p1')[0]
    discard = put(s, 'Lightning Bolt', 'hand') if mode == 'cruelclaw' else None
    act(s, 'p1', type='clear_mana', player='p1')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    to_phase(s, 'combat_damage', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d.resume['step'] == 'free_cast_pick'
    life = s.state.players['p1'].life
    option = next(o.id for o in d.options if o.card_id == cid)
    if mode == 'bismuth':
        s = fresh_action(s, cards, tmp_path / 'life-alternative.json', 'p1',
                         {'type': 'choose', 'decision_id': d.id, 'option_ids': [option]})
        assert s.state.players['p1'].life == life - 2
    else:
        answer(s, [option])
        d = s.state.rules.decision
        if d is not None:
            answer(s, [next(o.id for o in d.options if o.card_id == discard.id)])
        assert s.state.cards[discard.id].zone == 'p1:graveyard'
    assert s.state.cards[cid].zone == 'p1:battlefield'
    record = next(p for p in s.state.rules.payments.values() if p.card == cid)
    assert record.alternative == ('life_mv' if mode == 'bismuth' else 'discard')
    roundtrip(s)


@pytest.mark.parametrize('name', ['Chiss-Goria, Forge Tyrant', 'Durnan of the Yawning Portal'])
def test_staged_attack_selected_keyword_authority_actual_paid_cast(cards, name):
    s = setup(cards, name, 'Myr Enforcer', 'Swamp', 'Mountain')
    source = put(s, name, 'battlefield')
    target = 'Myr Enforcer' if name.startswith('Chiss') else 'Grizzly Bears'
    if name.startswith('Chiss'):
        put(s, 'Memnite', 'battlefield')
    to_phase(s, 'declare_attackers', turn=4)
    cid = stack_library(s, [target, 'Forest', 'Island', 'Mountain', 'Swamp'])[0]
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    settle(s)
    if name.startswith('Durnan'):
        d = s.state.rules.decision
        answer(s, [next(o.id for o in d.options if o.card_id == cid)])
        settle(s)
        d = s.state.rules.decision
        if d is not None:
            answer(s, [o.id for o in d.options])
        settle(s)
    assert s.state.cards[cid].zone == 'p1:exile'
    to_phase(s, 'main2', turn=4)
    mana(s, **({'C': 5} if name.startswith('Chiss') else {'G': 1}))
    act(s, 'p1', type='cast_spell', card_id=cid)
    keyword = 'affinity' if name.startswith('Chiss') else 'undaunted'
    assert sum(keyword in a.keywords for a in ch(s, s.state.cards[cid]).abilities) == (2 if keyword == 'affinity' else 1)
    settle(s)
    assert s.state.cards[cid].zone == 'p1:battlefield'
    roundtrip(s)


def test_staged_relay_real_storm_copy_separate_next_turn_packet(cards):
    from app.game.errors import ActionError
    s = setup(cards, 'Galvanic Relay')
    first = put(s, 'Memnite', 'hand')
    act(s, 'p1', type='cast_spell', card_id=first.id)
    settle(s)
    ids = stack_library(s, ['Forest', 'Island'])
    cast(s, 'Galvanic Relay')
    assert all(s.state.cards[c].zone == 'p1:exile' for c in ids)
    with pytest.raises(ActionError):
        act(s, 'p1', type='play_land', card_id=ids[0])
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='play_land', card_id=ids[0])
    assert s.state.cards[ids[0]].zone == 'p1:battlefield'
    roundtrip(s)


def test_staged_rocco_each_owner_authority_and_real_land_trigger_counter_food(cards):
    s = setup(cards, 'Rocco, Street Chef')
    source = put(s, 'Rocco, Street Chef', 'battlefield')
    ids = [stack_library(s, ['Forest'], pid=pid)[0] for pid in ('p1', 'p2', 'p3')]
    to_phase(s, 'end', turn=1)
    settle(s)
    assert {(p.card, p.player) for p in s.state.rules.permissions if p.card in ids} == set(zip(ids, ('p1', 'p2', 'p3'), strict=True))
    to_phase(s, 'main1', turn=2)
    act(s, 'p2', type='play_land', card_id=ids[1])
    settle(s)
    d = s.state.rules.decision
    answer(s, [next(o.id for o in d.options if o.card_id == source.id)])
    settle(s)
    assert s.state.cards[source.id].counters.get('+1/+1') == 1
    assert any(c.name == 'Food' and c.controller == 'p1' for c in s.state.cards.values())
    roundtrip(s)


@pytest.mark.parametrize('played', [False, True])
def test_staged_visions_actual_upkeep_play_and_end_step_intervening_condition(cards, played):
    s = setup(cards, 'Visions of Phyrexia')
    put(s, 'Visions of Phyrexia', 'battlefield')
    cid = stack_library(s, ['Forest'])[0]
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    assert s.state.cards[cid].zone == 'p1:exile'
    to_phase(s, 'main1', turn=4)
    before = sum(c.name == 'Powerstone' for c in s.state.cards.values())
    if played:
        act(s, 'p1', type='play_land', card_id=cid)
    to_phase(s, 'end', turn=4)
    settle(s)
    stones = [c for c in s.state.cards.values() if c.name == 'Powerstone']
    assert len(stones) == before + (0 if played else 1)
    if not played:
        assert stones[-1].tapped
    roundtrip(s)


def test_staged_abstruse_actual_foreign_exile_then_only_colorless_spent_as_color(cards):
    from app.game.errors import ActionError
    s = setup(cards, 'Abstruse Appropriation')
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Abstruse Appropriation', targets=[target.id])
    assert s.state.cards[target.id].zone == 'p2:exile'
    act(s, 'p1', type='clear_mana', player='p1')
    mana(s, R=2)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=target.id)
    act(s, 'p1', type='clear_mana', player='p1')
    mana(s, C=2)
    act(s, 'p1', type='cast_spell', card_id=target.id)
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_staged_soulfire_dynamic_apnap_cursor_selects_next_only_after_actual_exile_damage(cards):
    s = setup(cards, 'Soulfire Eruption', 'Hill Giant')
    target = put(s, 'Hill Giant', 'battlefield', 'p3')
    ids = stack_library(s, ['Lightning Bolt', 'Forest', 'Grizzly Bears'])
    source = put(s, 'Soulfire Eruption', 'hand')
    mana(s, C=6, R=3)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p3', target.id, 'p2'], target_counts=[3])
    settle(s)
    assert s.state.players['p2'].life == 39
    d = s.state.rules.decision
    assert d.resume['step'] == 'exile_authority41_soul'
    assert {o.id for o in d.options} == {'p3', target.id}
    assert s.state.cards[ids[0]].zone == 'p1:exile'
    assert s.state.cards[ids[1]].zone == 'p1:library'
    assert s.state.players['p3'].life == 40 and s.state.cards[target.id].damage == 0
    roundtrip(s)
    answer(s, [target.id])
    settle(s)
    assert s.state.players['p3'].life == 38
    assert s.state.cards[target.id].damage == 0
    assert all(s.state.cards[c].zone == 'p1:exile' for c in ids)
    assert all(any(p.card == c and p.play for p in s.state.rules.permissions) for c in ids)
    roundtrip(s)


def test_staged_feral_future_targets_damage_without_fighting(cards):
    s = setup(cards, 'Feral Encounter')
    own = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cid = stack_library(s, ['Memnite'])[0]
    cast(s, 'Feral Encounter')
    d = s.state.rules.decision
    answer(s, [next(o.id for o in d.options if o.card_id == cid)])
    settle(s)
    assert s.state.cards[cid].zone == 'p1:exile'
    act(s, 'p1', type='cast_spell', card_id=cid)
    settle(s)
    to_phase(s, 'begin_combat', turn=1)
    settle(s)
    answer(s, [next(o.id for o in s.state.rules.decision.options if o.card_id == own.id)])
    answer(s, [next(o.id for o in s.state.rules.decision.options if o.card_id == other.id)])
    settle(s)
    assert s.state.cards[other.id].zone == 'p2:graveyard'
    assert s.state.cards[own.id].damage == 0
    roundtrip(s)


def test_staged_fury_actual_giant_pump_trample_and_damage_packet(cards):
    s = setup(cards, "Fire Giant's Fury", 'Hill Giant')
    giant = put(s, 'Hill Giant', 'battlefield')
    to_phase(s, 'main1', turn=4)
    cast(s, "Fire Giant's Fury", targets=[giant.id])
    assert s.state.rules.decision is None
    assert ch(s, s.state.cards[giant.id]).pt == (5, 5), (s.state.zones.get('stack'), s.state.rules.effects)
    assert 'trample' in ch(s, s.state.cards[giant.id]).keywords
    ids = stack_library(s, ['Grizzly Bears', 'Memnite', 'Forest', 'Island', 'Lightning Bolt'])
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': giant.id, 'target': 'p2'}])
    to_phase(s, 'combat_damage', turn=4)
    settle(s)
    assert s.state.players['p2'].life == 35
    assert all(s.state.cards[c].zone == 'p1:exile' for c in ids)
    assert all(any(p.card == c and p.play for p in s.state.rules.permissions) for c in ids)
    roundtrip(s)


def test_staged_breeches_actual_pirate_damage_foreign_play(cards):
    s = setup(cards, 'Breeches, Brazen Plunderer')
    source = put(s, 'Breeches, Brazen Plunderer', 'battlefield')
    to_phase(s, 'declare_attackers', turn=4)
    cid = stack_library(s, ['Grizzly Bears'], pid='p2')[0]
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    to_phase(s, 'combat_damage', turn=4)
    settle(s)
    assert s.state.cards[cid].zone == 'p2:exile'
    to_phase(s, 'main2', turn=4)
    mana(s, C=2)
    act(s, 'p1', type='cast_spell', card_id=cid)
    settle(s)
    assert s.state.cards[cid].zone == 'p1:battlefield'
    roundtrip(s)


def test_staged_cannonade_actual_raid_then_next_combat_boundary(cards):
    from app.game.errors import ActionError
    s = setup(cards, 'Brazen Cannonade')
    put(s, 'Brazen Cannonade', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    cid = stack_library(s, ['Memnite'])[0]
    to_phase(s, 'main2', turn=4)
    settle(s)
    assert s.state.cards[cid].zone == 'p1:exile'
    to_phase(s, 'main1', turn=7)
    assert any(p.card == cid for p in s.state.rules.permissions)
    to_phase(s, 'main2', turn=7)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=cid)
    roundtrip(s)


@pytest.mark.parametrize('promised', [False, True])
def test_staged_heist_gift_then_reveal_actual_hand_permission_only_if_promised(cards, promised):
    s = setup(cards, "Cruelclaw's Heist")
    selected = put(s, 'Grizzly Bears', 'hand', 'p2')
    stack_library(s, ['Forest'], pid='p3')
    source = put(s, "Cruelclaw's Heist", 'hand')
    mana(s, B=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'],
        optional_costs=[f'{source.id}:gift'] if promised else [])
    if promised:
        d = s.state.rules.decision
        answer(s, ['p3'])
    settle(s)
    d = s.state.rules.decision
    assert any(o.card_id == selected.id for o in d.options), d
    answer(s, [next(o.id for o in d.options if o.card_id == selected.id)])
    settle(s)
    assert s.state.cards[selected.id].zone == 'p2:exile'
    assert any(p.card == selected.id for p in s.state.rules.permissions) == promised
    if promised:
        act(s, 'p1', type='clear_mana', player='p1')
        mana(s, R=2)
        act(s, 'p1', type='cast_spell', card_id=selected.id)
        settle(s)
        assert s.state.cards[selected.id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name', [
    'Mnemonic Betrayal','Hex Magic','Rocco, Street Chef','Visions of Phyrexia','Galvanic Relay',
    'Brazen Cannonade','Breeches, Brazen Plunderer','Primordial Mist','Flameskull','Allure of the Unknown',
    'Feral Encounter','Chiss-Goria, Forge Tyrant','Durnan of the Yawning Portal','Bismuth Mindrender',
    'The Infamous Cruelclaw',"Xander's Pact",'Abstruse Appropriation',"Cruelclaw's Heist",'Soulfire Eruption',"Fire Giant's Fury",
])
def test_staged_canonical_all_printed_lines_recognized_after_gameplay_gates(cards,name):
    from app.rules import coverage
    result=coverage.of_card_data(cards.resolve(name))
    assert result.level=='FULL',result
