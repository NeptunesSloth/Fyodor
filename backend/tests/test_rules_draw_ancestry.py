"""Private exact draw ancestry survives cold saves without entering view projections."""
from __future__ import annotations

import json

import pytest

from app.game.rules_state import TurnLog
from app.game.visibility import SPECTATOR
from tests.test_rules_wave9b_exile_permission import roundtrip
from tests.test_rules_wave29c_reveal_drawn import card_db, enter_the_lair, lair  # noqa: F401


def test_old_draw_log_has_no_invented_ancestry():
    assert TurnLog.model_validate({'turn': 1, 'drawn': {'p1': ['o1']}}).drawn_applied == {}


@pytest.mark.parametrize('replacer', [None, 'Blood Scrivener', 'Phial of Galadriel'])
def test_native_draw_ancestry_is_exact_private_and_cold(cards, replacer):
    s, door = lair(cards, replacer, empty_hand=replacer is not None)
    enter_the_lair(s, door)
    log = s.state.rules.turn_log
    actual = log.drawn.get('p1', [])
    assert actual
    assert set(actual) <= log.drawn_applied.keys()
    if replacer is None:
        assert not any(log.drawn_applied[oid] for oid in actual)
    else:
        replaced = log.drawn_replaced['p1']
        assert replaced and all(log.drawn_applied[oid] for oid in replaced)
        assert any(not log.drawn_applied[oid] for oid in actual if oid not in replaced)
    before = dict(log.drawn_applied)
    for viewer in ('p1', 'p2', SPECTATOR):
        projected = json.dumps(s.view(viewer))
        assert 'drawn_applied' not in projected and 'drawn_replaced' not in projected
    roundtrip(s)
    assert s.state.rules.turn_log.drawn_applied == before
