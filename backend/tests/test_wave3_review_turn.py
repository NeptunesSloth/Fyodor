"""Wave 3 final review: the precombat main phase runs the Saga lore turn-based action (714.3c) and the rad
trigger (728.1) together."""

from __future__ import annotations

from tests.game_helpers import act
from tests.test_rules_effects import replay_matches
from tests.test_rules_sagas import (  # noqa: F401
    build,
    card_db,
    cast,
    knights,
    lore,
    main_phase,
    respond_on,
    rules,
    settle,
)


def test_lore_counter_and_rad_trigger_both_happen_as_the_precombat_main_phase_begins(cards):
    s = build(cards, "History of Benalia")
    respond_on(s)
    saga = cast(s, "History of Benalia", W=2, C=1)
    settle(s)
    assert lore(s, saga) == 1 and len(knights(s)) == 1
    act(s, "p1", type="resource", player="p1", key="rad", delta=2)
    library = len(s.state.zones["p1:library"])
    main_phase(s, 3)
    assert lore(s, saga) == 2
    names = sorted(e.name for e in rules(s).stack.values()) + sorted(t.name for t in rules(s).pending_triggers)
    d = rules(s).decision
    if d is not None and d.kind == "order":  # (two triggers of Alice's at once: she orders them, 603.3b)
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
        names = sorted(e.name for e in rules(s).stack.values())
    assert any("Rad" in n for n in names) and any("Benalia" in n for n in names), names
    settle(s)
    assert len(knights(s)) == 2
    assert len(s.state.zones["p1:library"]) == library - 1 - 2  # the turn-3 draw, then two milled by the rad counters (728.1)
    replay_matches(s)
