"""Authoritative selected-cost capture before symbol announcements erase X."""
from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from app.rules import casting
from app.rules import mana as M
from app.rules.plan import Plan
from app.rules.spell_cost_stages import PreparedCost
from tests.test_rules_designations import put
from tests.test_rules_mana_followthrough_profiles import cards  # noqa: F401
from tests.test_rules_shared_damage_choices import table


@pytest.mark.parametrize('name,x,free,alternative,additional,expected,total', [
    ('Walking Ballista', 0, False, None, (), True, 0),
    ('Walking Ballista', 3, False, None, (), True, 6),
    ('Walking Ballista', 0, True, None, (), False, 0),
    ('Walking Ballista', 0, False, '{3}', (), False, 3),
    ('Grizzly Bears', 2, False, '{X}{G}', (), True, 3),
    ('Grizzly Bears', 0, False, None, ('{X}',), True, 2),
    ('Grizzly Bears', 3, False, None, ('{X}',), True, 5),
    ('Grizzly Bears', 0, True, None, ('{X}',), True, 0),
    ('Grizzly Bears', 0, False, None, (), False, 2),
])
def test_selected_raw_cost_capture_and_native_json(cards, name, x, free, alternative, additional, expected, total):  # noqa: F811
    s = table(cards, [name], [], [])
    spell = put(s, name, 'hand')
    ch = Plan(s.state, 'p1', cards, None).ch(spell)
    captured = []
    cost = casting.spell_cost(s.state, spell, ch, x, cards, free=free,
                             alternative=M.parse_cost(alternative) if alternative is not None else None,
                             additional=tuple(M.parse_cost(c) for c in additional), capture=captured)
    assert cost.generic + len(cost.colored) == total
    assert captured[0].selected_cost_has_x is expected
    adapter = TypeAdapter(PreparedCost)
    restored = adapter.validate_json(adapter.dump_json(captured[0]))
    assert restored.selected_cost_has_x is expected
    assert restored.evaluate() == captured[0].evaluate()


def test_legacy_prepared_cost_does_not_invent_selected_raw_history():
    adapter = TypeAdapter(PreparedCost)
    data = adapter.dump_python(PreparedCost(M.parse_cost('{3}')), mode='json')
    data.pop('selected_cost_has_x')
    assert adapter.validate_python(data).selected_cost_has_x is None


@pytest.mark.parametrize('legacy', [False, True])
def test_legacy_printed_x_purpose_never_establishes_selected_cost_history(legacy):
    purpose = TypeAdapter(casting.Purpose).validate_python({'cost_x': legacy})
    assert purpose.selected_cost_has_x is None
    restriction = 'q:{"cost_x":true}'
    assert not casting.spend_allowed(restriction, purpose)
    assert casting.spend_allowed(restriction, casting.Purpose(selected_cost_has_x=True))
    assert not casting.spend_allowed(restriction, casting.Purpose(selected_cost_has_x=False))
