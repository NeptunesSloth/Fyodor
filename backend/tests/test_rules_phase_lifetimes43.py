"""Exact native source-duration lifetime and player-departure foundation."""
import pytest

from app.game.rules_state import ObjectRef
from app.game.state import GameState
from app.rules import phase_lifetimes43 as leaf
from app.rules.plan import Plan
from tests import test_rules_sacrifice_entry_outcomes43 as fixtures
from tests.game_helpers import act
from tests.test_rules_designations import put
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    yield from fixtures.cards.__wrapped__(settings)


def setup(cards, bear_pid='p1'):
    s = table(cards, ['Glorious Anthem', 'Grizzly Bears', 'Bonesplitter'], ['Grizzly Bears'], ['Grizzly Bears'])
    source = put(s, 'Glorious Anthem', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid=bear_pid)
    plan = Plan(s.state, 'p1', cards, None)
    ref = ObjectRef(card=source.id, object_id=plan.oid(source.id), zone='p1:battlefield')
    return plan, source.id, bear.id, ref


def test_exact_source_phasing_does_not_end_lifetime_but_actual_departure_does(cards):
    plan, source, bear, ref = setup(cards)
    original = plan.oid(bear)
    got = leaf.phase_out(plan, ref, [bear], 'p1')
    assert [r.object_id for r in got] == [original]
    plan.do({'type': 'phase_shift', 'card_ids': [source], 'out': True})
    leaf.expire(plan)
    assert leaf.held(plan, bear) and plan.state.cards[bear].zone == 'p1:phased'
    plan = Plan(GameState.model_validate_json(plan.state.model_dump_json()), 'p1', cards, None)
    leaf.expire(plan)
    assert leaf.held(plan, bear)
    plan.do({'type': 'move', 'card_ids': [source], 'to': {'zone': 'graveyard'}})
    leaf.expire(plan)
    assert plan.state.cards[bear].zone == 'p1:battlefield'
    assert plan.oid(bear) == original and not plan.rules.phase_lifetimes
    assert any(e.counter == 'phase_in' and e.object_id == original for e in plan.rules.events)


def test_source_already_departed_never_starts_duration_or_phases_creatures(cards):
    plan, source, bear, ref = setup(cards)
    plan.do({'type': 'move', 'card_ids': [source], 'to': {'zone': 'graveyard'}})
    plan.do({'type': 'move', 'card_ids': [source], 'to': {'zone': 'battlefield'}})
    assert leaf.phase_out(plan, ref, [bear], 'p1') == []
    assert not plan.rules.phase_lifetimes and plan.state.cards[bear].zone == 'p1:battlefield'


def test_source_itself_can_phase_out_with_packet_without_ending_duration(cards):
    plan, source, bear, ref = setup(cards)
    leaf.phase_out(plan, ref, [source, bear], 'p1')
    leaf.expire(plan)
    assert all(plan.state.cards[c].zone == 'p1:phased' and leaf.held(plan, c) for c in (source, bear))
    assert plan.oid(source) == ref.object_id


def test_actual_indirect_attachment_keeps_identity_and_is_not_a_direct_receipt(cards):
    s = table(cards, ['Glorious Anthem', 'Grizzly Bears', 'Bonesplitter'])
    source = put(s, 'Glorious Anthem', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    gear = put(s, 'Bonesplitter', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[gear.id], to=bear.id)
    act(s, 'p1', type='counter', card_ids=[bear.id], kind='+1/+1', delta=2)
    plan = Plan(s.state, 'p1', cards, None)
    ref = ObjectRef(card=source.id, object_id=plan.oid(source.id))
    oid, gear_oid = plan.oid(bear.id), plan.oid(gear.id)
    assert [r.card for r in leaf.phase_out(plan, ref, [bear.id, gear.id], 'p1')] == [bear.id]
    assert plan.state.cards[gear.id].phased_indirect
    plan.do({'type': 'move', 'card_ids': [source.id], 'to': {'zone': 'graveyard'}})
    leaf.expire(plan)
    assert all(plan.state.cards[c].zone == 'p1:battlefield' for c in (bear.id, gear.id))
    assert plan.oid(bear.id) == oid and plan.oid(gear.id) == gear_oid
    assert plan.state.cards[gear.id].attached_to == bear.id
    assert plan.state.cards[bear.id].counters == {'+1/+1': 2}
    assert not plan.state.cards[gear.id].phased_indirect


@pytest.mark.parametrize('owner_leaves', [False, True])
def test_actual_player_departure_distinguishes_owner_from_reverted_source_control(cards, owner_leaves):
    from app.rules.leave import leave_game

    plan, source, bear, ref = setup(cards, bear_pid='p3')
    # The native table move records a change of control without a new object.
    plan.do({'type': 'move', 'card_ids': [source], 'to': {'zone': 'battlefield', 'player': 'p2'}})
    assert plan.oid(source) == ref.object_id
    leaf.phase_out(plan, ref, [bear], 'p1')
    leaver = 'p1' if owner_leaves else 'p2'
    plan.rules.conceded.append(leaver)
    leave_game(plan, leaver)
    leaf.expire(plan)
    if owner_leaves:
        assert not plan.rules.phase_lifetimes
        assert plan.state.cards[bear].zone == 'p3:battlefield'
    else:
        assert plan.state.cards[source].controller == 'p1'
        assert plan.oid(source) == ref.object_id and leaf.held(plan, bear)
        assert plan.state.cards[bear].zone == 'p3:phased'
