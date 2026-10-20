"""Actual native routing through isolated markers; all production hooks held."""
from __future__ import annotations

from app.game.session import GameSession
from app.rules import replace
from app.rules.plan import Plan
from tests.test_rules_designations import put
from tests.test_rules_prevention_frontier_bridge import cards as cards
from tests.test_rules_prevention_frontier_bridge import game
from tests.test_rules_prevention_outcomes import cast


def prepare(cards, monkeypatch, *, redirect):
    s = game(cards)
    gift = put(s, 'Revitalize', 'graveyard')
    p = Plan(s.state.model_copy(deep=True), 'p1', cards, None)
    replace.add_record(p, controller='p3', label='Marked recipient', event='damage',
                       source=p.oid(gift), source_card=gift.id, match={'to': {'pids': ['p3']}},
                       op={'do': 'finite_prevention', 'prevention': True, 'limit': 2, 'allocate': True, 'joint_prevention': True})
    if redirect:
        replace.add_record(p, controller='p1', label='Into the marked recipient', event='damage',
                           source=p.oid(gift), source_card=gift.id, match={'to': {'pids': ['p1']}},
                           op={'do': 'redirect', 'to': 'pid', 'pid': 'p3', 'limit': 2, 'allocate': True})
    return GameSession(p.state, cards=cards)


def test_actual_irrelevant_marked_pool_preserves_native_damage_without_joint_question(cards, monkeypatch):
    s = prepare(cards, monkeypatch, redirect=False)
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    assert s.state.rules.decision is None
    assert s.state.players['p1'].life == 37 and s.state.players['p3'].life == 40
    assert s.state.rules.replacements[0]['op']['limit'] == 2


def test_actual_legacy_finite_redirect_into_marker_rejects_without_consuming_anything(cards, monkeypatch):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    s = prepare(cards, monkeypatch, redirect=True)
    bolt = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    rejected = False
    for _ in range(4):
        before = s.state.model_dump_json()
        try:
            act(s, s.state.rules.priority, type='pass_priority')
        except ActionError as error:
            assert 'original single-recipient chooser' in str(error)
            assert s.state.model_dump_json() == before
            rejected = True
            break
    assert rejected and s.state.rules.decision is None
    assert s.state.players['p1'].life == s.state.players['p3'].life == 40
    assert all(r['op']['limit'] == 2 for r in s.state.rules.replacements)
    assert bolt.id in s.state.rules.stack
