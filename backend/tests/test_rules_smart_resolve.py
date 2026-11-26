"""-- smart resolve -- RESOLVE (``pass_priority`` until ``own_triggers``): one press resolves the top object and goes on through the run
of the player's own triggered abilities under it, and stops (priority back) as soon as the top is anything else, a card they drew could
answer now, or ``OWN_RUN`` objects resolved; the Shabraz + Grimoire loop of tests/test_rules_runaway_chains.py still pauses."""

from __future__ import annotations

import pytest

from app.rules.engine import OWN_RUN
from tests.game_helpers import act
from tests.test_rules_runaway_chains import (  # noqa: F401 - (card_db: the fixture with Shabraz and the Grimoire)
    GRIMOIRE,
    SHABRAZ,
    card_db,
    counters,
    hand,
    hold_and_cast_grimoire,
    in_library_at,
    named,
    stack_names,
    table,
)
from tests.wave9c_kit import check

SMART = {"type": "pass_priority", "until": "own_triggers"}


@pytest.mark.parametrize("kind", ["dummy", "two"])
def test_one_press_goes_through_a_run_of_own_triggers_and_a_loop_still_pauses(cards, kind):
    s = table(cards, kind)  # nothing to answer with: the loop would go on until the library is empty
    hold_and_cast_grimoire(s)
    library = len(s.state.zones["p1:library"])
    act(s, "p1", **SMART)  # the Grimoire (her spell) resolves; then her own triggers, one after another
    drew = library - len(s.state.zones["p1:library"])
    assert drew > 5  # (more than the Grimoire's enters trigger: the run went on through the Shabraz / Grimoire triggers)
    assert s.state.rules.winner is None and s.state.zones.get("stack") and s.state.rules.priority == "p1"  # …and stopped
    assert s.state.rules.prefs["p1"].pass_until is None
    act(s, "p1", **SMART)  # another press: another bounded run
    assert s.state.rules.winner is None and s.state.zones.get("stack")
    assert library - len(s.state.zones["p1:library"]) <= drew + OWN_RUN
    check(s)


@pytest.mark.parametrize("kind", ["dummy", "two"])
def test_a_drawn_instant_stops_the_run(cards, kind):
    s = table(cards, kind)
    mountain = next(c for c in s.state.cards.values() if c.name == "Mountain" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[mountain.id], to={"player": "p1", "zone": "battlefield"})  # {R} open
    in_library_at(s, "Lightning Bolt", 3)  # drawn by the enters trigger
    hold_and_cast_grimoire(s)
    act(s, "p1", **SMART)
    assert "Lightning Bolt" in hand(s) and s.state.rules.priority == "p1" and len(s.state.zones["stack"]) == 5
    assert s.state.rules.winner is None
    check(s)


def test_the_run_is_over_when_the_top_is_a_spell_or_someone_elses_object(cards):
    import random

    from app.game.rules_state import PlayerPrefs
    from app.rules.engine import own_run_over, stack_signature
    from app.rules.plan import Plan

    s = table(cards, "two")
    act(s, "p1", type="move", card_ids=[named(s, "Lightning Bolt").id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=named(s, "Lightning Bolt").id, targets=["p2"])
    plan = Plan(s.state, "p1", cards, random.Random(1))
    entry = plan.rules.stack[s.state.zones["stack"][-1]]
    prefs = PlayerPrefs(pass_until="own_triggers", pass_mark=f"{stack_signature(plan)}|0")
    assert own_run_over(plan, "p1", prefs)  # her own spell on top: one press each
    entry.kind = "trigger"
    assert not own_run_over(plan, "p1", prefs)  # her own triggered ability: the run goes on
    entry.controller = "p2"
    assert own_run_over(plan, "p1", prefs)  # someone else's: over
    entry.controller = "p1"
    prefs.pass_mark = f"other|{OWN_RUN - 1}"
    assert own_run_over(plan, "p1", prefs)  # the cap
    s.state.rules.prefs["p1"].hold_priority = False
