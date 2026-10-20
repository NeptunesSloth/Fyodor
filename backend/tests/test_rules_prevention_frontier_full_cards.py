"""Full B card damage paths through production parsing, planning and commit."""
from __future__ import annotations

import pytest

from tests.test_rules_designations import put, settle
from tests.test_rules_prevention_frontier_bridge import answer, game
from tests.test_rules_prevention_frontier_bridge import cards as cards
from tests.test_rules_prevention_outcomes import cast, source_choice
from tests.test_rules_wave30m_durations import to_phase


@pytest.mark.parametrize(('name', 'amounts', 'life3', 'bear_damage'), [
    ("Harm's Way", (1, 1), 36, 1), ('Shining Shoal', (1, 1), 36, 1),
    ('Divine Deflection', (1, 1), 36, 1), ('Refraction Trap', (1, 2), 35, 0)])
def test_actual_full_spells_split_simultaneous_damage_and_commit_native_body(cards, name, amounts, life3, bear_damage):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=2)
    quake = cast(s, 'Earthquake', pid='p2', x_value=2, resolve=False)
    spell = cast(s, name, ['p3'], **({'x_value': 2} if name in ('Shining Shoal', 'Divine Deflection') else {}))
    if name != 'Divine Deflection':
        source_choice(s, quake)
    import json

    from app.rules import prevention_frontier_journal as journal
    from app.rules.plan import Plan
    while s.state.rules.decision:
        d = s.state.rules.decision
        q = journal.question(Plan(s.state, d.player, cards, None), journal.Frame.loads(d.resume['frame']))
        answer(s, amounts[0] if json.loads(q.key)[2] == 'p1' else amounts[1])
    assert s.state.rules.decision is None
    assert s.state.players['p1'].life == 39 and s.state.cards[bear.id].damage == bear_damage
    assert s.state.players['p2'].life == 38 and s.state.players['p3'].life == life3
    assert not s.state.rules.replacements and not s.state.rules.stack
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert s.state.cards[quake.id].zone == 'p2:graveyard'


def test_shoal_actual_exile_white_mana_value_x_alternative_cost_and_full_redirect(cards):
    from app.rules import alt_costs
    from app.rules.plan import Plan
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import wait_priority
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    white = put(s, "Acolyte's Reward", 'hand')
    shoal = put(s, 'Shining Shoal', 'hand')
    to_phase(s, 'main1', turn=2)
    quake = cast(s, 'Earthquake', pid='p2', x_value=2, resolve=False)
    wait_priority(s, 'p1')
    p = Plan(s.state, 'p1', cards, None)
    offer, = alt_costs.offers(p.state, 'p1', p.state.cards[shoal.id], p.ch(p.state.cards[shoal.id]), p.info)
    act(s, 'p1', type='cast_spell', card_id=shoal.id, targets=['p3'], x_value=2, alt_cost=offer.key, sources=[])
    assert s.state.cards[white.id].zone == 'p1:exile'
    receipt = s.state.rules.payments[s.state.rules.object_id(shoal.id)]
    assert receipt.exiled == [white.id] and not receipt.mana_spent
    settle(s)
    source_choice(s, quake)
    answer(s, 1)
    answer(s, 1)
    assert s.state.players['p1'].life == 39 and s.state.cards[bear.id].damage == 1
    assert s.state.players['p3'].life == 36
    assert not s.state.rules.replacements and not s.state.rules.stack


def test_cover_actual_trample_source_shares_budget_across_blocker_and_player_but_other_source_independent(cards):
    import json

    from app.rules import prevention_frontier_journal as journal
    from app.rules.plan import Plan
    from tests.game_helpers import act
    from tests.test_rules_damage_redirection import attack, damage
    s = game(cards)
    cover = put(s, 'Cover of Winter', 'battlefield')
    blocker = put(s, 'Grizzly Bears', 'battlefield')
    big = put(s, 'Colossal Dreadmaw', 'battlefield', 'p2')
    other = put(s, 'Centaur Courser', 'battlefield', 'p2')
    act(s, 'p1', type='counter', card_ids=[cover.id], kind='age', delta=3)
    attack(s, [big, other], pid='p2', target='p1', turn=2)
    to_phase(s, 'declare_blockers')
    act(s, 'p1', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': big.id}])
    settle(s)
    damage(s)
    while s.state.rules.decision:
        d = s.state.rules.decision
        if d.resume.get('step') == 'block_split':
            act(s, d.player, type='choose', decision_id=d.id, amounts=[2 if o.id == blocker.id else 4 for o in d.options])
            settle(s)
            continue
        q = journal.question(Plan(s.state, d.player, cards, None), journal.Frame.loads(d.resume['frame']))
        source_oid, _, target, *_ = json.loads(q.key)
        value = 3 if source_oid.startswith(other.id + '.') else (2 if target == 'p1' else 1)
        answer(s, value)
    assert s.state.players['p1'].life == 38
    assert s.state.cards[blocker.id].zone == 'p1:battlefield' and s.state.cards[blocker.id].damage == 1
    assert s.state.cards[big.id].damage == 2
    assert s.state.cards[cover.id].counters['age'] == 3
    assert not any(key.startswith('source_limited:') for key in s.state.rules.prevention)


@pytest.mark.parametrize('name', ["Harm's Way", 'Shining Shoal', 'Divine Deflection', 'Refraction Trap'])
def test_actual_unpreventable_damage_leaves_prevention_budget_and_no_rider_but_still_redirects(cards, name):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=2)
    cast(s, 'Skullcrack', ['p3'], pid='p2')
    quake = cast(s, 'Earthquake', pid='p2', x_value=2, resolve=False)
    cast(s, name, ['p3'], **({'x_value': 2} if name in ('Shining Shoal', 'Divine Deflection') else {}))
    if name != 'Divine Deflection':
        source_choice(s, quake)
    if name in ("Harm's Way", 'Shining Shoal'):
        answer(s, 1)
        answer(s, 1)
        assert s.state.players['p1'].life == 39 and s.state.cards[bear.id].damage == 1
        assert s.state.players['p3'].life == 33
        assert not any(r.get('event') == 'damage' for r in s.state.rules.replacements)
    else:
        assert s.state.rules.decision is None and s.state.players['p1'].life == 38
        assert s.state.cards[bear.id].zone == 'p1:graveyard' and s.state.players['p3'].life == 35
        records = [r for r in s.state.rules.replacements if r.get('event') == 'damage']
        assert len(records) == 1
        assert records[0]['op']['limit'] == (2 if name == 'Divine Deflection' else 3)


@pytest.mark.parametrize('name', ["Harm's Way", 'Shining Shoal', 'Refraction Trap'])
def test_actual_chosen_source_original_oid_excludes_new_incarnation_without_spending(cards, name):
    from tests.game_helpers import act
    from tests.test_rules_damage_redirection import activate
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, 'Pestilence', 'battlefield', 'p2')
    cast(s, name, ['p3'], **({'x_value': 2} if name == 'Shining Shoal' else {}))
    source_choice(s, source)
    original = s.state.rules.replacements[0]['match']['source']['oids']
    act(s, 'p2', type='move', card_ids=[source.id], to={'player': 'p2', 'zone': 'graveyard'})
    act(s, 'p2', type='move', card_ids=[source.id], to={'player': 'p2', 'zone': 'battlefield'})
    assert s.state.rules.object_id(source.id) not in original
    activate(s, source, 'deals 1 damage', pid='p2')
    assert s.state.rules.decision is None
    assert s.state.players['p1'].life == s.state.players['p2'].life == s.state.players['p3'].life == 39
    assert s.state.cards[bear.id].damage == 1
    assert len(s.state.rules.replacements) == 1


@pytest.mark.parametrize('name', ['Divine Deflection', 'Refraction Trap'])
def test_immediate_rider_uses_announced_exact_original_target_not_new_incarnation(cards, name):
    from tests.game_helpers import act
    from tests.test_rules_damage_redirection import activate
    s = game(cards)
    source = put(s, 'Pestilence', 'battlefield', 'p2')
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, name, [target.id], **({'x_value': 2} if name == 'Divine Deflection' else {}))
    if name == 'Refraction Trap':
        source_choice(s, source)
    original = s.state.rules.object_id(target.id)
    act(s, 'p2', type='move', card_ids=[target.id], to={'player': 'p2', 'zone': 'graveyard'})
    act(s, 'p2', type='move', card_ids=[target.id], to={'player': 'p2', 'zone': 'battlefield'})
    assert s.state.rules.object_id(target.id) != original
    activate(s, source, 'deals 1 damage', pid='p2')
    answer(s, 1)
    assert s.state.players['p1'].life == 40 and s.state.players['p2'].life == s.state.players['p3'].life == 39
    assert s.state.cards[target.id].zone == 'p2:battlefield' and s.state.cards[target.id].damage == 1
    assert s.state.rules.decision is None


@pytest.mark.parametrize('name', ["Harm's Way", 'Shining Shoal'])
def test_actual_redirect_to_original_player_leaves_same_recipient_damage_and_redirects_other(cards, name):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=2)
    quake = cast(s, 'Earthquake', pid='p2', x_value=2, resolve=False)
    cast(s, name, ['p1'], **({'x_value': 2} if name == 'Shining Shoal' else {}))
    source_choice(s, quake)
    answer(s, 2)
    assert s.state.players['p1'].life == 36 and s.state.players['p2'].life == s.state.players['p3'].life == 38
    assert s.state.cards[bear.id].damage == 0 and not s.state.rules.replacements
    assert s.state.rules.decision is None


def test_cover_same_source_fresh_budget_in_first_strike_and_regular_damage_rounds(cards):
    from tests.game_helpers import act
    from tests.test_rules_damage_redirection import attack, damage
    from tests.test_rules_designations import roundtrip
    s = game(cards)
    cover = put(s, 'Cover of Winter', 'battlefield')
    attacker = put(s, 'Mirran Crusader', 'battlefield', 'p2')
    act(s, 'p1', type='counter', card_ids=[cover.id], kind='age', delta=1)
    attack(s, [attacker], pid='p2', target='p1', turn=2)
    damage(s)
    seen = 0
    for _ in range(10):
        if s.state.rules.decision:
            roundtrip(s)
            answer(s, 1)
            seen += 1
            if seen == 2:
                break
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    assert seen == 2 and s.state.players['p1'].life == 38
    assert s.state.cards[cover.id].counters['age'] == 1
    assert not any(k.startswith('source_limited:') for k in s.state.rules.prevention)


def test_cover_combat_only_does_not_prevent_actual_noncombat_creature_damage(cards):
    from tests.test_rules_damage_redirection import activate
    s = game(cards)
    cover = put(s, 'Cover of Winter', 'battlefield')
    source = put(s, 'Prodigal Pyromancer', 'battlefield', 'p2')
    from tests.game_helpers import act
    act(s, 'p1', type='counter', card_ids=[cover.id], kind='age', delta=3)
    to_phase(s, 'main1', turn=2)
    activate(s, source, 'deals 1 damage', ['p1'], pid='p2')
    assert s.state.rules.decision is None and s.state.players['p1'].life == 39
    assert s.state.cards[cover.id].counters['age'] == 3


@pytest.mark.parametrize('name', ["Harm's Way", 'Shining Shoal', 'Divine Deflection', 'Refraction Trap'])
def test_actual_permanent_scope_protects_planeswalker_except_shoal_creature_scope(cards, name):
    s = game(cards)
    walker = cast(s, 'Narset, Parter of Veils')
    original = s.state.cards[walker.id].counters['loyalty']
    bolt = cast(s, 'Lightning Bolt', [walker.id], pid='p2', resolve=False)
    cast(s, name, ['p3'], **({'x_value': 2} if name in ('Shining Shoal', 'Divine Deflection') else {}))
    if name != 'Divine Deflection':
        source_choice(s, bolt)
    if name == 'Shining Shoal':
        assert s.state.rules.decision is None and s.state.cards[walker.id].counters['loyalty'] == original - 3
        assert s.state.players['p3'].life == 40 and s.state.rules.replacements[0]['op']['limit'] == 2
    else:
        n = 3 if name == 'Refraction Trap' else 2
        answer(s, n)
        assert s.state.cards[walker.id].counters['loyalty'] == original - (3 - n)
        assert s.state.players['p3'].life == 40 - n and not s.state.rules.replacements


def test_divine_deflection_one_turn_pool_is_shared_across_different_actual_combat_sources(cards):
    import json

    from app.rules import prevention_frontier_journal as journal
    from app.rules.plan import Plan
    from tests.test_rules_damage_redirection import attack, damage
    s = game(cards)
    first = put(s, 'Centaur Courser', 'battlefield', 'p2')
    second = put(s, 'Rumbling Baloth', 'battlefield', 'p2')
    attack(s, [first, second], pid='p2', target='p1', turn=2)
    cast(s, 'Divine Deflection', ['p3'], x_value=3)
    damage(s)
    while s.state.rules.decision:
        d = s.state.rules.decision
        q = journal.question(Plan(s.state, d.player, cards, None), journal.Frame.loads(d.resume['frame']))
        source = json.loads(q.key)[0]
        answer(s, 1 if source.startswith(first.id + '.') else 2)
    assert s.state.players['p1'].life == 36 and s.state.players['p3'].life == 37
    assert not s.state.rules.replacements and s.state.rules.decision is None


def cycle_pending(cards):
    s = game(cards)
    to_phase(s, 'main1', turn=2)
    quake = cast(s, 'Earthquake', pid='p2', x_value=2, resolve=False)
    cast(s, "Harm's Way", ['p2'], resolve=False)
    cast(s, "Harm's Way", ['p1'], pid='p2')
    source_choice(s, quake)
    source_choice(s, quake)
    return s


def test_actual_two_controllers_harm_pools_form_joint_redirect_cycle_with_interior_vectors(cards):
    from tests.test_rules_designations import roundtrip
    s = cycle_pending(cards)
    for _ in range(4):
        roundtrip(s)
        answer(s, 1)
    assert s.state.rules.decision is None and not s.state.rules.replacements
    assert all(s.state.players[p].life == 38 for p in ('p1', 'p2', 'p3'))
    assert not s.state.rules.stack
