"""Production completed-event receipts; source permission remains unimported."""
import pytest

from app.rules import history
from app.rules.plan import Plan
from tests.test_rules_designations import roundtrip
from tests.test_rules_numeric_roll_finalization42 import activate_troll
from tests.test_rules_random_consequences import faces
from tests.test_rules_random_native_outcomes42 import cards as cards
from tests.test_rules_random_native_outcomes42 import setup
from tests.test_rules_wave30m_durations import to_phase


@pytest.mark.parametrize('result', [5, 6, 20])
def test_actual_completed_roll_receipt_uses_exact_player_and_final_result(cards, monkeypatch, result):
    s = setup(cards)
    faces(monkeypatch, [result])
    activate_troll(s)
    plan = Plan(s.state, 'p1', cards, None)
    condition = {'history': 'rolled_result', 'result': 6}
    assert history.holds(plan, {'controller': 'p1'}, condition) == (result == 6)
    assert not history.holds(plan, {'controller': 'p2'}, condition)
    assert [(f.player, f.amount) for f in s.state.rules.turn_log.facts if f.kind == 'roll_die'] == [('p1', result)]
    roundtrip(s)


def test_exact_result_receipt_survives_save_and_expires_at_native_turn_change(cards, monkeypatch):
    s = setup(cards)
    faces(monkeypatch, [6])
    activate_troll(s)
    roundtrip(s)
    condition = {'history': 'rolled_result', 'result': 6}
    assert history.holds(Plan(s.state, 'p1', cards, None), {'controller': 'p1'}, condition)
    to_phase(s, 'main1', turn=4)
    assert not history.holds(Plan(s.state, 'p1', cards, None), {'controller': 'p1'}, condition)
    roundtrip(s)
