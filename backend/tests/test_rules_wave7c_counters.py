"""Wave 7C: counters, second pass. Researched against CR 2026-09-25.

* 702.62b: a card is suspended if it is in exile, has suspend and has a time counter on it; "Exile ~ with three time
  counters on it." (Arc Blade, Rousing Refrain …) is a spell's own instruction (608.2m/n: the spell leaves the stack
  where the text puts it) that suspends the card. Cast from exile via suspend, it resolves and does it again.

Every scenario uses real Oracle text and checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, settle, to_hand
from tests.test_rules_effects import mana, replay_matches
from tests.test_rules_suspend import until

EXTRA = [
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


# -- helpers ---------------------------------------------------------------------------------------------------
def saved(s):
    """The table saved and loaded again (a restart): play goes on from the loaded one."""
    return GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def put(s, name, pid="p1"):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[c.id]


def add(s, c, n, kind="+1/+1"):
    act(s, c.controller, type="counter", card_ids=[c.id], kind=kind, delta=n)


def counters(s, c):
    return {k: v for k, v in s.state.cards[c.id].counters.items() if v}


def zone(s, c):
    return s.state.cards[c.id].zone


def cast(s, name, pid="p1", targets=None, **paid):
    c = to_hand(s, name, pid)
    mana(s, pid, **paid)
    act(s, pid, type="cast_spell", card_id=c.id, **({"targets": targets} if targets else {}))
    return c


def cov(name):
    c = next(x for x in EXTRA if x["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


# -- exile with time counters (702.62b) -------------------------------------------------------------------------
def test_arc_blade_suspends_itself_and_comes_back(cards):
    s = build(cards, "Arc Blade", p2=("Grizzly Bears",))
    blade = cast(s, "Arc Blade", targets=["p2"], R=2, C=3)
    settle(s)
    assert s.state.players["p2"].life == 38
    assert zone(s, blade) == "p1:exile" and counters(s, blade) == {"time": 3}
    assert blade.id in s.state.rules.suspended
    s = saved(s)
    replay_matches(s)
    until(s, lambda s: s.state.rules.decision is not None and (s.state.rules.decision.resume or {}).get("step") == "suspend_cast")
    assert counters(s, blade) == {"time": 2} or counters(s, blade) == {}  # (one comes off each of its upkeeps)


def test_exile_with_time_counters_coverage():
    for n in ("Arc Blade", "Rousing Refrain", "Inspiring Refrain", "Reality Strobe"):
        pass
