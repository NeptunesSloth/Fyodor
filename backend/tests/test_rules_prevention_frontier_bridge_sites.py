"""Actual native saved sites through the unregistered joint bridge."""
from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.rules import prevention_frontier_bridge as bridge
from app.rules import prevention_frontier_journal as journal
from app.rules import replace
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_abundance import set_library
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_prevention_frontier_bridge import answer, game
from tests.test_rules_prevention_frontier_bridge import cards as cards
from tests.test_rules_prevention_frontier_grounding import setup
from tests.test_rules_prevention_frontier_journal import finish


def finite_rider(s):
    gift = put(s, 'Revitalize', 'graveyard')
    put(s, 'Abundance', 'battlefield')
    top = set_library(s, ['Forest', 'Lightning Bolt'])
    p = Plan(s.state.model_copy(deep=True), 'p1', s.cards, None)
    replace.add_record(p, controller='p1', label='Joint continuation proof', event='damage',
                       source=p.oid(gift), source_card=gift.id, match={'to': {'players': 'you'}},
                       op={'do': 'finite_prevention', 'limit': 1, 'allocate': True, 'prevention': True, 'joint_prevention': True,
                           'rider': {'effects': [{'do': 'draw', 'who': 'you', 'n': 1}]}})
    return GameSession(p.state, cards=s.cards), top[0]


def mana_pending(cards):
    from tests.test_rules_bandmate_references import mana
    s = game(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = put(s, 'Llanowar Wastes', 'battlefield')
    spell = put(s, 'Grizzly Bears', 'hand')
    mana(s, C=1)
    s, top = finite_rider(s)
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[source.id])
    assert s.state.rules.decision.resume['step'] == bridge.STEP
    assert s.state.cards[source.id].tapped
    assert spell.id not in s.state.rules.stack
    assert s.state.rules.spells_this_turn('p1', s.state.turn.number) == 0
    return s, spell.id, top


def combat_pending(cards):
    from tests.test_rules_damage_redirection import attack, damage
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards)
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    act(s, 'p1', type='set_monarch', player='p1')
    s, top = finite_rider(s)
    attack(s, [attacker], pid='p2', target='p1', turn=2)
    damage(s)
    assert s.state.rules.decision.resume['step'] == bridge.STEP
    assert s.state.players['p1'].life == 40
    return s, attacker.id, top


def test_actual_saved_mana_payment_joint_then_rider_then_cast_exactly_once(cards):
    s, spell, top = mana_pending(cards)
    roundtrip(s)
    answer(s, 1)
    assert s.state.rules.decision.resume['step'] != bridge.STEP
    assert spell not in s.state.rules.stack
    assert s.state.rules.spells_this_turn('p1', s.state.turn.number) == 0
    assert s.state.players['p1'].life == 40
    roundtrip(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['decline'])
    assert s.state.cards[top].zone == 'p1:hand'
    assert s.state.cards[spell].zone == 'stack'
    assert s.state.rules.spells_this_turn('p1', s.state.turn.number) == 1
    settle(s)
    assert s.state.cards[spell].zone == 'p1:battlefield'
    assert not s.state.rules.replacements


def test_actual_combat_joint_then_rider_then_monarch_exactly_once(cards):
    s, attacker, top = combat_pending(cards)
    roundtrip(s)
    answer(s, 1)
    assert s.state.players['p1'].life == 39 and s.state.table.monarch == 'p1'
    assert not any(t.name == 'The Monarch' for t in s.state.rules.pending_triggers)
    roundtrip(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['decline'])
    settle(s)
    assert s.state.cards[top].zone == 'p1:hand'
    assert s.state.players['p1'].life == 39 and s.state.table.monarch == 'p2'
    assert not s.state.rules.replacements
    roundtrip(s)
    settle(s)
    assert s.state.players['p1'].life == 39


def test_preview_reports_unresolved_question_purely_and_completed_preview_is_native(cards):
    p, _, events = setup(cards)
    for rec in p.rules.replacements:
        rec['op']['joint_prevention'] = True
    before = p.state.model_dump_json()
    request = replace.damage_outcome(p, events, answers={}, order=None, ask=False)
    assert isinstance(request, bridge.JointAsk)
    assert p.state.model_dump_json() == before and p.rules.decision is None
    saved, _ = finish(p, journal.start(p, events, batch='preview'))
    result = replace.damage_outcome(p, events, answers={bridge.PREFIX: saved.dumps()}, order=None, ask=False)
    assert isinstance(result, replace.DamageOutcome)
    assert sum(r['amount'] for r in result.preventions) == 6
    assert p.state.model_dump_json() == before and p.rules.decision is None


@pytest.mark.parametrize(('mode', 'life1', 'life3'), [('before', 38, 32), ('after', 37, 34), ('mixed', 37, 33)])
def test_actual_furnace_distinct_recipient_orders_and_redirect_lineage(cards, mode, life1, life3):
    import json

    from tests.test_rules_prevention_frontier_bridge import earth_harm
    s, bear, _ = earth_harm(cards, furnace=True)
    while s.state.rules.decision is not None:
        d = s.state.rules.decision
        q = journal.question(Plan(s.state, d.player, s.cards, None), journal.Frame.loads(d.resume['frame']))
        assert isinstance(q, journal.Question)
        if q.kind == 'amount':
            answer(s, 1)
        else:
            target = json.loads(q.key)[2]
            furnace_first = mode == 'after' or (mode == 'mixed' and target == 'p1')
            cs = {c.id: c for c in replace.damage_candidates(Plan(s.state, d.player, s.cards, None))}
            chosen = next(c for c in q.candidates if ('Furnace of Rath' in cs[c].label) == furnace_first)
            answer(s, chosen)
    assert s.state.players['p1'].life == life1
    assert s.state.players['p2'].life == 36 and s.state.players['p3'].life == life3
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    assert not s.state.rules.replacements and not s.state.rules.stack


def test_actual_affected_order_and_distinct_pool_owner_numeric_authority(cards):
    from app.game.errors import ActionError
    from tests.test_rules_prevention_outcomes import cast
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards)
    put(s, 'Furnace of Rath', 'battlefield')
    gift = put(s, 'Revitalize', 'graveyard', 'p3')
    to_phase(s, 'main1', turn=2)
    p = Plan(s.state.model_copy(deep=True), 'p2', cards, None)
    replace.add_record(p, controller='p3', label='Distinct amount authority', event='damage', match={},
                       source=p.oid(gift), source_card=gift.id,
                       op={'do': 'finite_prevention', 'limit': 1, 'allocate': True, 'prevention': True, 'joint_prevention': True})
    s = GameSession(p.state, cards=cards)
    cast(s, 'Earthquake', pid='p2', x_value=2)
    d = s.state.rules.decision
    frame = journal.Frame.loads(d.resume['frame'])
    q = journal.question(Plan(s.state, d.player, cards, None), frame)
    assert q.kind == 'order' and q.actor == 'p2'
    cs = {c.id: c for c in replace.damage_candidates(Plan(s.state, d.player, cards, None))}
    answer(s, next(c for c in q.candidates if cs[c].op['do'] == 'finite_prevention'))
    d = s.state.rules.decision
    assert d.player == 'p3'
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=[], name='1')
    assert s.state.model_dump_json() == before
    answer(s, 1)
    while s.state.rules.decision:
        d = s.state.rules.decision
        p = Plan(s.state, d.player, cards, None)
        f = journal.Frame.loads(d.resume['frame'])
        q = journal.question(p, f)
        if q.kind == 'order':
            answer(s, q.candidates[0])
        else:
            answer(s, 0)
    assert s.state.players['p2'].life == 38
    assert s.state.players['p1'].life == s.state.players['p3'].life == 36
    assert not s.state.rules.replacements


def test_actual_pending_bridge_rejects_changed_candidate_manifest_atomically(cards):
    from app.game.errors import ActionError
    from tests.test_rules_prevention_frontier_bridge import earth_harm
    s, _, _ = earth_harm(cards)
    s.state.rules.replacements[0]['op']['limit'] += 1
    before = s.state.model_dump_json()
    d = s.state.rules.decision
    with pytest.raises(ActionError, match='stale'):
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[], name='1')
    assert s.state.model_dump_json() == before


def test_saved_frame_rejects_changed_original_damage_source_without_committing(cards):
    from app.game.errors import ActionError
    p, _, events = setup(cards)
    for rec in p.rules.replacements:
        rec['op']['joint_prevention'] = True
    saved = journal.start(p, events, batch='exact-original-source')
    changed = [dict(e) for e in events]
    changed[0]['source_oid'] += '.new'
    before = p.state.model_dump_json()
    with pytest.raises(ActionError, match='changed'):
        bridge.plan_damage(p, changed, answers={bridge.PREFIX: saved.dumps()}, order=None, ask=True)
    assert p.state.model_dump_json() == before


def test_actual_legacy_synchronous_mana_caller_rejects_joint_question_without_dropping_damage(cards):
    from app.game.errors import ActionError
    from app.rules import casting
    s = game(cards)
    source = put(s, 'Llanowar Wastes', 'battlefield')
    s, _ = finite_rider(s)
    p = Plan(s.state, 'p1', cards, None)
    before = p.state.model_dump_json()
    with pytest.raises(ActionError, match='saved payment continuation'):
        casting.mana_ability_damage(p, p.state.cards[source.id], 'p1', 1)
    assert p.state.model_dump_json() == before and p.rules.decision is None


@pytest.mark.parametrize('recipient', ['p1', 'p3'])
def test_actual_mana_legacy_finite_interaction_rejects_relevant_only_and_preserves_payment_atomically(cards, recipient):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import mana
    s = game(cards)
    source = put(s, 'Llanowar Wastes', 'battlefield')
    spell = put(s, 'Grizzly Bears', 'hand')
    mana(s, C=1)
    s, _ = finite_rider(s)
    p = Plan(s.state, 'p1', cards, None)
    replace.add_record(p, controller='p3', label='Legacy numeric chooser', event='damage', source=None, source_card=None,
                       match={'to': {'pids': [recipient]}},
                       op={'do': 'finite_prevention', 'prevention': True, 'limit': 1, 'allocate': True})
    s = GameSession(p.state, cards=cards)
    before = s.state.model_dump_json()
    if recipient == 'p1':
        with pytest.raises(ActionError, match='original single-recipient chooser'):
            act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[source.id])
        assert s.state.model_dump_json() == before
        assert not s.state.cards[source.id].tapped and s.state.rules.decision is None
        assert s.state.players['p1'].mana == {'C': 1}
    else:
        act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[source.id])
        answer(s, 1)
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['decline'])
        settle(s)
        assert s.state.cards[spell.id].zone == 'p1:battlefield'
        assert s.state.players['p1'].life == 40
        assert len(s.state.rules.replacements) == 1 and s.state.rules.replacements[0]['op']['limit'] == 1
