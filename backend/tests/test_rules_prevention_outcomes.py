"""Canonical prevention outcomes and separately marked native prerequisite prototypes."""
from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.rules import context, coverage, effects, replace
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_damage_redirection import activate, cast, choose, number
from tests.test_rules_damage_rider_continuations import cards as cards
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


def finite_pending(cards, *, furnace=False):
    """Low-level native finite-prevention prototype, not a printed Oracle claim."""
    s = table(cards, ['Forest'], ["Healer's Hawk", 'Forest'], ['Grizzly Bears', 'Furnace of Rath', 'Forest'])
    first = put(s, "Healer's Hawk", 'battlefield', 'p2')
    second = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    if furnace:
        put(s, 'Furnace of Rath', 'battlefield', 'p3')
    plan = Plan(s.state.model_copy(deep=True), 'p3', cards, None)
    replace.add_record(plan, event='damage', match={'to': {'pids': ['p1']}},
                       op={'do': 'finite_prevention', 'prevention': True, 'limit': 3, 'allocate': True,
                           'rider': {'if': True, 'aggregation': 'batch',
                                     'effects': [{'do': 'gain_life', 'who': 'you', 'n': {'ref_amount': 'prevented'}}]}},
                       controller='p3', source=None, source_card=None, label='Finite prevention prototype')
    ctx = {'controller': 'p3', 'source_card': second.id, 'source_object': plan.oid(second),
           'name': 'Native prototype', 'stack_id': '', 'next': 0, 'body_done': {'do': 'noop'},
           'effects': [{'do': 'damage', 'who': 'player:p1', 'src': 'ref:first', 'n': 4, 'with_next': True},
                       {'do': 'damage', 'who': 'player:p1', 'src': 'ref:second', 'n': 4}]}
    context.bind_objects(plan, ctx, 'first', [first.id])
    context.bind_objects(plan, ctx, 'second', [second.id])
    effects.continue_effects(plan, ctx)
    return GameSession(plan.state, cards=cards), first.id


def allocate(s, first):
    d = s.state.rules.decision
    frame = d.resume['frame']
    row = frame['request']['rows'][frame['i']]
    number(s, 1 if row['source_card'] == first else 2)


def test_finite_prevention_arbitrary_split_is_chosen_by_affected_player_and_aggregates_rider(cards):
    s, first = finite_pending(cards)
    assert s.state.rules.decision.player == 'p1'  # record controller is p3
    assert s.state.players['p1'].life == 40
    roundtrip(s)
    allocate(s, first)
    assert s.state.players['p1'].life == 35
    assert s.state.players['p2'].life == 43  # prevent1 of lifelink damage, not all3
    assert s.state.players['p3'].life == 43  # one immediate gain of actual prevented3
    assert not s.state.rules.replacements
    roundtrip(s)


def test_finite_prevention_furnace_order_and_saved_allocation_use_actual_capacity(cards):
    s, first = finite_pending(cards, furnace=True)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            break
        if d.resume['step'] == 'redirect_amount':
            allocate(s, first)
        else:
            if 'map' in d.resume:
                answer = next(k for k, value in d.resume['map'].items()
                              if 'Furnace of Rath' in d.prompt and any(c.name == 'Furnace of Rath' and c.id in value for c in s.state.cards.values()))
            else:
                answer = next(o.id for o in d.options if 'Furnace of Rath' in o.label)
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[answer])
            settle(s)
    assert s.state.rules.decision is None
    assert s.state.players['p1'].life == 27
    assert s.state.players['p2'].life == 47
    assert s.state.players['p3'].life == 43
    roundtrip(s)



NATIVE = ['Comeuppance', 'Phyrexian Vindicator', 'Selfless Squire', 'New Way Forward',
          'Judgment of Alexander', 'Hallow', "Acolyte's Reward", 'Channel Harm', 'Vengeful Archon',
          'Brace for Impact', 'Scars of the Veteran', 'Samite Ministration', 'Shadowbane', 'Sacred Boon',
          'Blood of the Martyr']

def game(cards):
    import json
    from pathlib import Path
    names = [r['name'] for r in json.loads((Path(__file__).parent / 'fixtures/prevention_outcomes_cards.json').read_text())]
    return table(cards, names, names, ['Forest'])

@pytest.mark.parametrize('name', NATIVE)
def test_outcome_whole_card_coverage(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts

def test_comeuppance_noncreature_reflects_and_excludes_own_damage(cards):
    s = game(cards)
    cast(s, 'Comeuppance')
    roundtrip(s)
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    assert s.state.players['p1'].life == 40
    assert s.state.players['p2'].life == 37
    cast(s, 'Lightning Bolt', ['p1'])
    assert s.state.players['p1'].life == 37

def test_sacred_boon_counters_wait_until_next_end_step(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    cast(s, 'Sacred Boon', [bear.id])
    roundtrip(s)
    cast(s, 'Lightning Bolt', [bear.id], pid='p2')
    assert s.state.cards[bear.id].damage == 0
    assert not s.state.cards[bear.id].counters
    roundtrip(s)
    to_phase(s, 'end')
    settle(s)
    assert s.state.cards[bear.id].counters.get('+0/+1') == 3

def test_selfless_squire_watches_other_prevention(cards):
    s = game(cards)
    squire = cast(s, 'Selfless Squire')
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s, 'main1', turn=2)  # the Squire's own ETB prevention has expired
    cast(s, 'Comeuppance')
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    while s.state.rules.decision:
        d = s.state.rules.decision
        choose(s, [d.options[0].id])
    settle(s)
    assert s.state.cards[squire.id].counters.get('+1/+1') == 3

def test_vindicator_creates_targeted_trigger_after_damage(cards):
    s = game(cards)
    v = put(s, 'Phyrexian Vindicator', 'battlefield')
    cast(s, 'Lightning Bolt', [v.id], pid='p2')
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    assert all(o.id != v.id for o in d.options)
    choose(s, ['p2'])
    assert s.state.players['p2'].life == 37
    assert s.state.cards[v.id].damage == 0


def source_choice(s, source):
    d = s.state.rules.decision
    assert d
    choose(s, [next(o.id for o in d.options if o.card_id == source.id)])

def test_hallow_binds_original_stack_spell_and_gains_actual_prevented(cards):
    s = game(cards)
    bolt = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    cast(s, 'Hallow', [bolt.id])
    assert s.state.players['p1'].life == 43
    assert s.state.players['p2'].life == 40
    roundtrip(s)

@pytest.mark.parametrize('name,black', [('Shadowbane', True), ('Shadowbane', False), ('Samite Ministration', True), ('Samite Ministration', False)])
def test_source_color_outcomes_are_prevention_bound(cards, name, black):
    s = game(cards)
    source = put(s, 'Pestilence' if black else 'Prodigal Pyromancer', 'battlefield', 'p2')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s, 'main1', turn=2)
    cast(s, name)
    source_choice(s, source)
    roundtrip(s)
    activate(s, source, 'each creature' if black else 'deals 1 damage', [] if black else ['p1'], pid='p2')
    # Both are black/red for Samite, only black for Shadowbane.
    assert s.state.players['p1'].life == (41 if black or name == 'Samite Ministration' else 40)
    roundtrip(s)

def test_acolyte_devotion_prevents_and_deals_to_announced_target(cards):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Phyrexian Vindicator', 'battlefield')
    cast(s, "Acolyte's Reward", [bear.id, 'p2'], target_counts=[1, 1])
    roundtrip(s)
    cast(s, 'Lightning Bolt', [bear.id], pid='p2')
    assert s.state.players['p2'].life == 37
    assert s.state.cards[bear.id].damage == 0

def test_archon_announces_target_and_retains_unspent_budget(cards):
    s = game(cards)
    archon = put(s, 'Vengeful Archon', 'battlefield')
    activate(s, archon, 'Prevent the next', ['p2'], x_value=5)
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    assert s.state.players['p1'].life == 40
    assert s.state.players['p2'].life == 37
    roundtrip(s)
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    assert s.state.players['p1'].life == 39
    assert s.state.players['p2'].life == 35

@pytest.mark.parametrize('accept', [False, True])
def test_channel_harm_optional_damage_chooser_survives_cold(cards, accept):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Channel Harm', [bear.id])
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    assert s.state.players['p1'].life == 40
    assert s.state.rules.decision.player == 'p1'
    roundtrip(s)
    choose(s, ['yes' if accept else 'no'])
    assert s.state.cards[bear.id].zone == ('p2:graveyard' if accept else 'p2:battlefield')

def test_scars_alternate_cost_and_delayed_counter(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    cast(s, 'Scars of the Veteran', [bear.id])
    cast(s, 'Lightning Bolt', [bear.id], pid='p2')
    assert not s.state.cards[bear.id].counters
    roundtrip(s)
    to_phase(s, 'end')
    settle(s)
    assert s.state.cards[bear.id].counters.get('+0/+1') == 3


def test_brace_immediate_counters_and_exact_old_object(cards):
    s = game(cards)
    angel = put(s, 'Razia, Boros Archangel', 'battlefield')
    cast(s, 'Brace for Impact', [angel.id])
    roundtrip(s)
    cast(s, 'Lightning Bolt', [angel.id], pid='p2')
    assert s.state.cards[angel.id].counters.get('+1/+1') == 3
    assert s.state.cards[angel.id].damage == 0
    act(s, 'p1', type='move', card_ids=[angel.id], to={'player':'p1','zone':'hand'})
    put(s, 'Razia, Boros Archangel', 'battlefield')
    cast(s, 'Lightning Bolt', [angel.id], pid='p2')
    assert s.state.cards[angel.id].zone == 'p1:graveyard'

def test_scars_native_white_card_exile_alternative_cost(cards):
    from app.rules.view import hints
    from tests.test_rules_bandmate_references import wait_priority
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    scars = put(s, 'Scars of the Veteran', 'hand')
    white = put(s, 'Sacred Boon', 'hand')
    wait_priority(s, 'p1')
    alternatives = hints(s.state, 'p1', cards)['alt_castable'][scars.id]
    alt = next(a for a in alternatives if 'exile' in a['label'])
    act(s, 'p1', type='cast_spell', card_id=scars.id, targets=[bear.id], alt_cost=alt['id'])
    settle(s)
    assert s.state.cards[white.id].zone == 'p1:exile'
    cast(s, 'Lightning Bolt', [bear.id], pid='p2')
    assert s.state.cards[bear.id].damage == 0
    roundtrip(s)

def test_new_way_forward_reflexive_damage_and_draw_resolve_on_stack(cards):
    from tests.test_rules_abundance import set_library
    s = game(cards)
    source = put(s, 'Pestilence', 'battlefield', 'p2')
    top = set_library(s, ['Forest', 'Lightning Bolt'])
    cast(s, 'New Way Forward')
    source_choice(s, source)
    roundtrip(s)
    activate(s, source, 'each creature', pid='p2')
    assert s.state.players['p1'].life == 40
    assert s.state.players['p2'].life == 38
    assert s.state.cards[top[0]].zone == 'p1:hand'
    roundtrip(s)

def test_judgment_delayed_commander_damage(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards)
    put(s, 'Krenko, Mob Boss', 'battlefield')
    source = put(s, 'Prodigal Pyromancer', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    cast(s, 'Judgment of Alexander')
    activate(s, source, 'deals 1 damage', ['p1'], pid='p2')
    assert s.state.players['p1'].life == 40
    assert s.state.cards[source.id].zone == 'p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('accept', [False, True])
def test_blood_original_controller_makes_actual_optional_replacement_choice(cards, accept):
    s = game(cards)
    victim = put(s, 'Centaur Courser', 'battlefield', 'p2')
    cast(s, 'Blood of the Martyr')
    roundtrip(s)
    cast(s, 'Lightning Bolt', [victim.id], pid='p2')
    assert s.state.rules.decision.player == 'p1'
    roundtrip(s)
    d = s.state.rules.decision
    answer = next(o.id for o in d.options if ('decline' in o.id or o.id == 'no') != accept)
    choose(s, [answer])
    assert s.state.players['p1'].life == (37 if accept else 40)
    assert s.state.cards[victim.id].zone == ('p2:battlefield' if accept else 'p2:graveyard')

def test_vindicator_trigger_is_counterable_and_zero_prevention_does_not_trigger(cards):
    s = game(cards)
    v = put(s, 'Phyrexian Vindicator', 'battlefield')
    cast(s, 'Lightning Bolt', [v.id], pid='p2')
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
    assert s.state.players['p2'].life == 40
    trigger = s.state.zones['stack'][-1]
    cast(s, 'Stifle', [trigger], pid='p2')
    assert s.state.players['p2'].life == 40
    cast(s, 'Skullcrack', ['p1'], pid='p2')
    cast(s, 'Lightning Bolt', [v.id], pid='p2')
    assert s.state.rules.decision is None
    assert s.state.cards[v.id].damage == 3
    roundtrip(s)

def test_sacred_boon_accumulates_across_events_and_excludes_new_incarnation(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards)
    victim = put(s, 'Centaur Courser', 'battlefield')
    cast(s, 'Sacred Boon', [victim.id])
    cast(s, 'Shock', [victim.id], pid='p2')
    cast(s, 'Lightning Bolt', [victim.id], pid='p2')
    assert s.state.cards[victim.id].damage == 2
    roundtrip(s)
    to_phase(s, 'end')
    settle(s)
    assert s.state.cards[victim.id].counters.get('+0/+1') == 3

@pytest.mark.parametrize('name', ['Sacred Boon', 'Scars of the Veteran'])
def test_delayed_counter_watcher_does_not_find_returned_creature(cards, name):
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards)
    victim = put(s, 'Centaur Courser', 'battlefield')
    cast(s, name, [victim.id])
    cast(s, 'Lightning Bolt', [victim.id], pid='p2')
    cast(s, 'Cloudshift', [victim.id])
    roundtrip(s)
    to_phase(s, 'end')
    settle(s)
    assert not s.state.cards[victim.id].counters


def test_archon_actual_native_shield_supports_arbitrary_one_plus_two_distribution(cards):
    s = game(cards)
    first = put(s, "Healer's Hawk", 'battlefield', 'p2')
    second = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    archon = put(s, 'Vengeful Archon', 'battlefield')
    activate(s, archon, 'Prevent the next', ['p2'], x_value=3)
    plan = Plan(s.state.model_copy(deep=True), 'p2', cards, None)
    ctx = {'controller': 'p2', 'source_card': second.id, 'source_object': plan.oid(second),
           'name': 'Native simultaneous damage harness', 'stack_id': '', 'next': 0, 'body_done': {'do': 'noop'},
           'effects': [{'do': 'damage', 'who': 'player:p1', 'src': 'ref:first', 'n': 4, 'with_next': True},
                       {'do': 'damage', 'who': 'player:p1', 'src': 'ref:second', 'n': 4}]}
    context.bind_objects(plan, ctx, 'first', [first.id])
    context.bind_objects(plan, ctx, 'second', [second.id])
    effects.continue_effects(plan, ctx)
    s = GameSession(plan.state, cards=cards)
    roundtrip(s)
    allocate(s, first.id)
    assert s.state.players['p1'].life == 35
    assert s.state.players['p2'].life == 40  # lifelink3 minus the Archon's actual reflected3
    assert not s.state.rules.replacements
    roundtrip(s)


@pytest.mark.parametrize('name', ['Cover of Winter', "Harm's Way", 'Shining Shoal', 'Divine Deflection',
                                  'Refraction Trap'])
def test_unproved_cross_recipient_announcement_and_state_loop_remain_partial(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'PARTIAL'


def test_any_other_uses_original_source_object_across_cold_departure(cards):
    from app.rules import targets
    s = game(cards)
    original = put(s, 'Phyrexian Vindicator', 'battlefield')
    plan = Plan(s.state, 'p1', cards, None)
    oid = plan.oid(original)
    source = targets.source_of(plan, original.id, object_id=oid)
    assert original.id not in targets.legal_targets(plan, 'any_other', 'p1', source, original.id, source_object=oid)
    act(s, 'p1', type='move', card_ids=[original.id], to={'player': 'p1', 'zone': 'hand'})
    roundtrip(s)
    put(s, 'Phyrexian Vindicator', 'battlefield')
    roundtrip(s)
    plan = Plan(s.state, 'p1', cards, None)
    assert plan.oid(original.id) != oid
    source = targets.source_of(plan, original.id, object_id=oid)
    assert original.id in targets.legal_targets(plan, 'any_other', 'p1', source, original.id, source_object=oid)
    # Legacy callers that have no original OID retain their existing exclusion.
    assert original.id not in targets.legal_targets(plan, 'any_other', 'p1', source, original.id)


def test_hallow_tracks_permanent_spell_as_it_becomes_permanent(cards):
    s = game(cards)
    put(s, 'Fervor', 'battlefield', 'p2')
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s, 'main1', turn=2)
    source = cast(s, 'Prodigal Pyromancer', pid='p2', resolve=False)
    cast(s, 'Hallow', [source.id])
    roundtrip(s)
    activate(s, source, 'deals 1 damage', ['p1'], pid='p2')
    assert s.state.players['p1'].life == 41
    roundtrip(s)

def test_squire_etb_prevention_outlives_its_source(cards):
    s = game(cards)
    squire = cast(s, 'Selfless Squire')
    cast(s, 'Murder', [squire.id], pid='p2')
    roundtrip(s)
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    assert s.state.players['p1'].life == 40
    assert s.state.cards[squire.id].zone == 'p1:graveyard'


def test_samite_prevents_green_combat_source_without_life_trigger(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards)
    source = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'declare_attackers', turn=2)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p1'}])
    settle(s)
    cast(s, 'Samite Ministration')
    source_choice(s, source)
    roundtrip(s)
    to_phase(s, 'combat_damage')
    settle(s)
    assert s.state.players['p1'].life == 40
    roundtrip(s)
