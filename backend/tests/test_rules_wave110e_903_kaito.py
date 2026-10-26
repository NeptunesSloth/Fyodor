"""Wave 110E: 903.9b with Kaito, Dancing Shadow (resume_kaito): the returned creature is a commander, so its owner is asked before it would be put into
a hand; in the command zone it was not returned, so no "if you do" (loyalty abilities twice, 606.3)."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave110b_s13k import cards  # noqa: F401  (fixture)
from tests.wave110b_kit import attack, build, check, put


@pytest.mark.parametrize("ans,where,twice", [("yes", "p1:command", False), ("no", "p1:hand", True)])
def test_kaito_asks_before_returning_a_commander(cards, ans, where, twice):  # noqa: F811
    s = build(cards, ["Kaito, Dancing Shadow"], [])
    kaito = put(s, "Kaito, Dancing Shadow")
    act(s, "p1", type="counter", card_ids=[kaito.id], kind="loyalty", delta=3 - s.state.cards[kaito.id].counters.get("loyalty", 0))
    krenko = put(s, "Krenko, Mob Boss")
    attack(s, krenko)
    asked = []
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            asked.append("903.9b" in d.prompt)
            pick = ans if "903.9b" in d.prompt else krenko.id if krenko.id in [o.id for o in d.options] else d.options[0].id
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert asked.count(True) == 1 and s.state.cards[krenko.id].zone == where
    act(s, "p1", type="activate_ability", card_id=kaito.id, ability=2)  # 0: Draw a card.
    while s.state.rules.decision is not None:
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    if s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    try:
        act(s, "p1", type="activate_ability", card_id=kaito.id, ability=2)
        second = True
    except Exception:  # noqa: BLE001
        second = False
    assert second == twice
    check(s)
