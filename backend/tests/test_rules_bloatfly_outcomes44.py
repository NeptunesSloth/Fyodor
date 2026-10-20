"""Canonical Bloatfly native prevention, actual-removal, radiation and cold proofs."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import context, effects
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, row in enumerate(json.loads((Path(__file__).parent / 'fixtures/bloatfly_outcomes44_cards.json').read_text())):
        base[row['name']] = card(row['name'], set_code='bfk', number=str(i), **{
            ('card_faces' if k == 'faces' else k): v for k, v in row.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, counters=1):
    names = ['Bloatfly Swarm', 'Grizzly Bears', 'Glorious Anthem', 'Vorinclex, Monstrous Raider']
    s = table(cards, names, names, names)
    swarm = put(s, 'Bloatfly Swarm', 'battlefield')
    put(s, 'Glorious Anthem', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=swarm.id, kind='+1/+1', value=counters)
    first = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    second = put(s, 'Grizzly Bears', 'battlefield', pid='p3')
    return s, swarm, first, second


def damage(s, swarm, sources, simultaneous, unpreventable=False, amount=2):
    plan = Plan(s.state, 'p1', s.cards, None)
    body = []
    ctx = {'controller': 'p1', 'source_card': swarm.id, 'source_object': plan.oid(swarm),
           'name': 'Explicit staged damage kernel', 'stack_id': '', 'next': 0, 'body_done': {'do': 'noop'}}
    context.bind_objects(plan, ctx, 'recipient', [swarm.id])
    for i, source in enumerate(sources):
        context.bind_objects(plan, ctx, f'source{i}', [source.id])
        body.append({'do': 'damage', 'who': 'ref:recipient', 'src': f'ref:source{i}', 'n': amount, 'unpreventable': unpreventable,
                     **({'with_next': True} if simultaneous and i < len(sources) - 1 else {})})
    ctx['effects'] = body
    effects.continue_effects(plan, ctx)
    return plan


@pytest.mark.parametrize('simultaneous', [True, False])
def test_staged_simultaneous_applicability_precedes_counter_removal_but_sequential_sees_commit(cards, simultaneous):
    s, swarm, first, second = setup(cards)
    plan = damage(s, swarm, [first, second], simultaneous)
    assert plan.rules.decision is None
    assert plan.state.cards[swarm.id].counters.get('+1/+1', 0) == 0
    assert all(p.resources.get('rad', 0) == 1 for p in plan.state.players.values())
    assert plan.state.cards[swarm.id].damage == (0 if simultaneous else 2)


def test_staged_grouped_damage_removes_only_original_available_counters(cards):
    s, swarm, first, second = setup(cards, counters=3)
    plan = damage(s, swarm, [first, second], True)
    assert plan.state.cards[swarm.id].counters.get('+1/+1', 0) == 0
    assert all(p.resources.get('rad', 0) == 3 for p in plan.state.players.values())
    assert plan.state.cards[swarm.id].damage == 0


def test_staged_unpreventable_damage_still_removes_nominal_counters_and_gives_rad(cards):
    s, swarm, first, _ = setup(cards, counters=3)
    plan = damage(s, swarm, [first], False, unpreventable=True)
    assert plan.state.cards[swarm.id].damage == 2
    assert plan.state.cards[swarm.id].counters.get('+1/+1') == 1
    assert all(p.resources.get('rad', 0) == 2 for p in plan.state.players.values())


def test_staged_no_counter_source_does_not_prevent_or_give_rad(cards):
    s, swarm, first, _ = setup(cards, counters=0)
    plan = damage(s, swarm, [first], False)
    assert plan.state.cards[swarm.id].damage == 2
    assert all(not p.resources.get('rad') for p in plan.state.players.values())


def test_staged_saved_rad_replacement_does_not_repeat_original_removal(cards):
    from app.game import actions as A
    from app.game.state import GameState
    from app.rules import engine

    s, swarm, first, _ = setup(cards, counters=4)
    # The fixture includes their real static replacement definitions.
    for pid in ('p1', 'p2'):
        put(s, 'Vorinclex, Monstrous Raider', 'battlefield', pid=pid)
    plan = damage(s, swarm, [first], False, amount=3)
    assert plan.rules.decision is not None
    assert plan.state.cards[swarm.id].counters.get('+1/+1') == 1
    saved = GameState.model_validate_json(plan.state.model_dump_json())
    restored = Plan(saved, 'p1', cards, None)
    for _ in range(4):
        d = restored.rules.decision
        if d is None:
            break
        restored.actor = d.player
        engine.choose(restored, A.Choose(decision_id=d.id, option_ids=[d.options[0].id]))
    assert restored.rules.decision is None
    assert restored.state.cards[swarm.id].counters.get('+1/+1') == 1


@pytest.mark.parametrize('first_label,rad', [('Bloatfly Swarm', 2), ('Joint bridge kernel', 1)])
def test_staged_joint_bridge_preserves_post_damage_rider_in_both_orders(cards, first_label, rad):
    from app.game import actions as A
    from app.game.state import GameState
    from app.rules import engine, replace

    s, swarm, first, _ = setup(cards, counters=3)
    plan = Plan(s.state, 'p1', cards, None)
    # Explicit marked native allocated-prevention kernel, not a printed card claim.
    replace.add_record(plan, event='damage', match={'to': {'objects': {'oids': [plan.oid(swarm)]}}},
                       op={'do': 'finite_prevention', 'limit': 1, 'allocate': True,
                           'prevention': True, 'joint_prevention': True}, controller='p1',
                       source=plan.oid(swarm), source_card=swarm.id, label='Joint bridge kernel')
    from app.game.session import GameSession

    s = GameSession(plan.state, cards=cards)
    out = damage(s, swarm, [first], False)
    assert out.rules.decision is not None
    assert out.state.cards[swarm.id].counters.get('+1/+1') == 3
    assert all(not p.resources.get('rad') for p in out.state.players.values())
    out = Plan(GameState.model_validate_json(out.state.model_dump_json()), 'p1', cards, None)
    initial = True
    for _ in range(8):
        d = out.rules.decision
        if d is None:
            break
        out.actor = d.player
        if any(o.group == 'number' for o in d.options):
            answer = A.Choose(decision_id=d.id, option_ids=[], name='1')
        else:
            pick = next((o.id for o in d.options if initial and o.label == first_label), d.options[0].id)
            answer = A.Choose(decision_id=d.id, option_ids=[pick])
        initial = False
        engine.choose(out, answer)
    assert out.rules.decision is None
    assert out.state.cards[swarm.id].counters.get('+1/+1') == 3 - rad
    assert out.state.cards[swarm.id].damage == 0
    assert all(p.resources.get('rad') == rad for p in out.state.players.values())


def test_staged_actual_cast_flying_bolt_removal_and_source_less_radiation(cards):
    from tests.test_rules_abundance import set_library
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle
    from tests.test_rules_wave30m_durations import to_phase

    names = ['Bloatfly Swarm', 'Lightning Bolt', 'Forest', 'Forest', 'Forest']
    s = table(cards, names, names, names)
    swarm = put(s, 'Bloatfly Swarm', 'hand')
    mana(s, C=3, B=1)
    act(s, 'p1', type='cast_spell', card_id=swarm.id)
    settle(s)
    assert s.state.cards[swarm.id].counters.get('+1/+1') == 5
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[swarm.id])
    assert ch.pt == (5, 5) and 'flying' in ch.keywords
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[swarm.id])
    settle(s)
    assert s.state.cards[swarm.id].counters.get('+1/+1') == 2
    assert s.state.cards[swarm.id].damage == 0
    assert all(p.resources.get('rad') == 3 for p in s.state.players.values())
    set_library(s, ['Forest', 'Forest', 'Lightning Bolt', 'Forest'])
    to_phase(s, 'main1', turn=4)
    settle(s)
    assert s.state.players['p1'].life == 39 and s.state.players['p1'].resources.get('rad') == 2


def test_staged_actual_overkill_body_finishes_before_zero_toughness_death(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle

    names = ['Bloatfly Swarm', 'Lightning Bolt']
    s = table(cards, names, names, names)
    swarm = put(s, 'Bloatfly Swarm', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=swarm.id, kind='+1/+1', value=2)
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[swarm.id])
    settle(s)
    assert s.state.cards[swarm.id].zone == 'p1:graveyard'
    assert all(p.resources.get('rad') == 2 for p in s.state.players.values())


@pytest.mark.parametrize('double_first', [False, True])
def test_staged_actual_cold_zero_toughness_source_finishes_rad_then_dies(cards, tmp_path, double_first):
    from tests.native_counter44 import cold_choose
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle

    names = ['Bloatfly Swarm', 'Lightning Bolt', 'Vorinclex, Monstrous Raider']
    s = table(cards, names, names, names)
    swarm = put(s, 'Bloatfly Swarm', 'battlefield')
    own = put(s, 'Vorinclex, Monstrous Raider', 'battlefield')
    other = put(s, 'Vorinclex, Monstrous Raider', 'battlefield', pid='p2')
    act(s, 'p1', type='set_counter', card_id=swarm.id, kind='+1/+1', value=3)
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[swarm.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    assert s.state.cards[swarm.id].zone == 'p1:battlefield'
    assert not s.state.cards[swarm.id].counters.get('+1/+1')
    preferred = s.state.rules.object_id(own.id if double_first else other.id)
    option = next(o.id for o in d.options if preferred in d.resume['map'][o.id])
    s = cold_choose(s, cards, tmp_path, [option])
    for _ in range(3):
        d = s.state.rules.decision
        if d is None:
            break
        preferred = s.state.rules.object_id(other.id if d.player == 'p2' else own.id)
        option = next(o.id for o in d.options if preferred in d.resume['map'][o.id])
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[option])
    settle(s)
    assert s.state.rules.decision is None and s.state.cards[swarm.id].zone == 'p1:graveyard'
    assert s.state.cards[bolt.id].zone == 'p1:graveyard'
    assert s.state.players['p1'].resources.get('rad', 0) == (3 if double_first else 2)
    # Vorinclex checks the PUTTER (p1), independently for each recipient.
    # Choosing p2's Vorinclex first halves3→1, then p1 doubles→2.
    assert s.state.players['p2'].resources.get('rad', 0) == 2
    assert s.state.players['p3'].resources.get('rad', 0) == 3


def test_staged_actual_two_simultaneous_flying_blockers_see_one_counter_before_rider(cards):
    from tests.test_rules_conditionals import until
    from tests.test_rules_damage_redirection import attack
    from tests.test_rules_designations import settle

    names = ['Bloatfly Swarm', "Healer's Hawk", 'Glorious Anthem']
    s = table(cards, names, names, names)
    swarm = put(s, 'Bloatfly Swarm', 'battlefield')
    put(s, 'Glorious Anthem', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=swarm.id, kind='+1/+1', value=1)
    first = put(s, "Healer's Hawk", 'battlefield', pid='p2')
    second = put(s, "Healer's Hawk", 'battlefield', pid='p3')
    act(s, 'p1', type='set_controller', card_ids=[second.id], player='p2')
    attack(s, [swarm])
    until(s, lambda t: t.state.rules.decision is not None and t.state.rules.decision.kind == 'declare_blockers')
    d = s.state.rules.decision
    act(s, d.player, type='declare_blockers', blocks=[
        {'blocker_id': first.id, 'attacker_id': swarm.id},
        {'blocker_id': second.id, 'attacker_id': swarm.id}])
    until(s, lambda t: t.state.rules.decision is not None and t.state.rules.decision.kind == 'divide')
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, amounts=[1, 1])
    settle(s)
    assert s.state.cards[swarm.id].zone == 'p1:battlefield'
    assert not s.state.cards[swarm.id].counters.get('+1/+1') and s.state.cards[swarm.id].damage == 0
    assert all(p.resources.get('rad') == 1 for p in s.state.players.values())
    assert s.state.players['p2'].life == 40


def test_staged_actual_skullcrack_unpreventable_still_runs_counter_and_rad_body(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle

    names = ['Bloatfly Swarm', 'Skullcrack', 'Lightning Bolt']
    s = table(cards, names, names, names)
    swarm = put(s, 'Bloatfly Swarm', 'hand')
    mana(s, C=3, B=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=swarm.id)
    settle(s)
    skull = put(s, 'Skullcrack', 'hand')
    mana(s, C=1, R=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=skull.id, targets=['p3'])
    settle(s)
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[swarm.id])
    settle(s)
    assert s.state.cards[swarm.id].zone == 'p1:graveyard'
    assert all(p.resources.get('rad') == 3 for p in s.state.players.values())


@pytest.mark.parametrize('furnace_first', [False, True])
def test_staged_actual_furnace_order_uses_damage_at_application_and_actual_available_removal(cards, furnace_first):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle

    names = ['Bloatfly Swarm', 'Furnace of Rath', 'Lightning Bolt']
    s = table(cards, names, names, names)
    swarm = put(s, 'Bloatfly Swarm', 'hand')
    mana(s, C=3, B=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=swarm.id)
    settle(s)
    put(s, 'Furnace of Rath', 'battlefield', pid='p2')
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[swarm.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    label = 'Furnace of Rath' if furnace_first else 'Bloatfly Swarm'
    pick = next(o.id for o in d.options if label in o.label)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[pick])
    settle(s)
    n = 5 if furnace_first else 3
    assert all(p.resources.get('rad') == n for p in s.state.players.values())
    assert s.state.cards[swarm.id].zone == ('p1:graveyard' if furnace_first else 'p1:battlefield')
    if not furnace_first:
        assert s.state.cards[swarm.id].counters.get('+1/+1') == 2 and s.state.cards[swarm.id].damage == 0


def test_staged_actual_blinked_target_is_new_object_old_bolt_has_no_damage_or_rad(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle

    names = ['Bloatfly Swarm', 'Cloudshift', 'Lightning Bolt']
    s = table(cards, names, names, names)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    swarm = put(s, 'Bloatfly Swarm', 'hand')
    mana(s, C=3, B=1)
    act(s, 'p1', type='cast_spell', card_id=swarm.id)
    settle(s)
    original = s.state.rules.object_id(swarm.id)
    bolt = put(s, 'Lightning Bolt', 'hand')
    blink = put(s, 'Cloudshift', 'hand')
    mana(s, R=1, W=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[swarm.id])
    act(s, 'p1', type='cast_spell', card_id=blink.id, targets=[swarm.id])
    settle(s)
    assert s.state.rules.object_id(swarm.id) != original
    assert s.state.cards[swarm.id].zone == 'p1:battlefield'
    assert s.state.cards[swarm.id].counters.get('+1/+1') == 5 and s.state.cards[swarm.id].damage == 0
    assert s.state.cards[bolt.id].zone == 'p1:graveyard'
    assert all(not p.resources.get('rad') for p in s.state.players.values())


@pytest.mark.parametrize('modifier', ['Doubling Season', 'Solemnity'])
def test_staged_actual_counter_scope_entry_multiplier_and_player_counter_prohibition(cards, modifier):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle

    names = ['Bloatfly Swarm', 'Lightning Bolt', modifier]
    s = table(cards, names, names, names)
    if modifier == 'Doubling Season':
        put(s, modifier, 'battlefield')
    swarm = put(s, 'Bloatfly Swarm', 'hand')
    mana(s, C=3, B=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=swarm.id)
    settle(s)
    assert s.state.cards[swarm.id].counters.get('+1/+1') == (10 if modifier == 'Doubling Season' else 5)
    if modifier == 'Solemnity':
        put(s, modifier, 'battlefield', pid='p2')
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[swarm.id])
    settle(s)
    assert s.state.cards[swarm.id].counters.get('+1/+1') == (7 if modifier == 'Doubling Season' else 2)
    assert all(p.resources.get('rad', 0) == (3 if modifier == 'Doubling Season' else 0) for p in s.state.players.values())


@pytest.mark.parametrize('separate_sources', [False, True])
def test_actual_repeated_prevention_does_not_mutate_shared_cached_rider_definition(cards, separate_sources):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import settle

    names = ['Bloatfly Swarm', 'Bloatfly Swarm', 'Lightning Bolt', 'Lightning Bolt', 'Glorious Anthem']
    s = table(cards, names, names, names)
    put(s, 'Glorious Anthem', 'battlefield')
    swarms = []
    for _ in range(2 if separate_sources else 1):
        source = next(c for c in s.state.cards.values() if c.name == 'Bloatfly Swarm'
                      and c.owner == 'p1' and c.id not in {old.id for old in swarms})
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
        mana(s, C=3, B=1)
        wait_priority(s, 'p1')
        act(s, 'p1', type='cast_spell', card_id=source.id)
        settle(s)
        swarms.append(source)
    bolts = []
    for i in range(2):
        bolt = next(c for c in s.state.cards.values() if c.name == 'Lightning Bolt'
                    and c.owner == 'p1' and c.id not in bolts)
        bolts.append(bolt.id)
        act(s, 'p1', type='move', card_ids=[bolt.id], to={'player': 'p1', 'zone': 'hand'})
        mana(s, R=1)
        wait_priority(s, 'p1')
        act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[swarms[i if separate_sources else 0].id])
        settle(s)
        expected = 3 if i == 0 else 6 if separate_sources else 5
        assert all(p.resources.get('rad') == expected for p in s.state.players.values())
    from app.rules import scripts

    p = Plan(s.state, 'p1', cards, None)
    definition = next(d for d in scripts.definitions(p.ch(p.state.cards[swarms[0].id])).values()
                      if d.get('event') == 'damage')
    assert definition['op']['rider']['effects'] == [{'do': 'bloatfly_outcome44'}]
