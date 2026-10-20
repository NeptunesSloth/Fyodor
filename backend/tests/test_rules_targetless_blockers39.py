"""CR506.4b: blocking status survives the departure of the last blocked attacker."""

from __future__ import annotations

import pytest

from app.rules import selectors
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import cast
from tests.test_rules_damage_history_outcomes import cards as cards
from tests.test_rules_damage_history_outcomes import game
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_wave30m_durations import stops, to_phase


def pending(s):
    source = cast(s, "Electryte")
    bear = put(s, "Grizzly Bears", "battlefield")
    blocker = put(s, "Colossal Dreadmaw", "battlefield", "p2")
    stops(s, "declare_attackers", "declare_blockers", "combat_damage", "end_combat")
    to_phase(s, "declare_attackers", turn=4)
    act(
        s,
        "p1",
        type="declare_attackers",
        attackers=[{"card_id": source.id, "target": "p2"}, {"card_id": bear.id, "target": "p2"}],
    )
    to_phase(s, "declare_blockers", turn=4)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": bear.id}])
    to_phase(s, "combat_damage", turn=4)
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    assert s.state.cards[blocker.id].is_blocking and s.state.cards[blocker.id].blocking_without_attacker
    assert s.state.cards[blocker.id].blocking is None and not s.state.cards[blocker.id].blocking_more
    assert s.state.cards[blocker.id].damage == 2
    return blocker


def test_last_attacker_dies_blocker_status_selector_and_cold_trigger(cards, tmp_path):
    s = game(cards)
    blocker = pending(s)
    from app.game.views import card_view

    for pid in ["p1", "p2", "p3"]:
        view = card_view(s.state, s.state.cards[blocker.id], pid)
        assert view.get("blocking_without_attacker") is True and "blocking" not in view
    sel = selectors.parse("blocking creatures")
    assert sel
    assert blocker.id in selectors.candidates(Plan(s.state, "p1", cards, None), sel, "p1")
    import subprocess
    import sys

    saved = tmp_path / "blocker39.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)

c=s.state.cards[sys.argv[3]]
assert c.is_blocking and c.blocking_without_attacker and c.blocking is None
settle(s)
assert s.state.cards[sys.argv[3]].damage==5
roundtrip(s)
repo.close()
"""
    r = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), blocker.id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    settle(s)
    assert s.state.cards[blocker.id].damage == 5
    to_phase(s, "main2", turn=4)
    assert (
        not s.state.cards[blocker.id].is_blocking and not s.state.cards[blocker.id].blocking_without_attacker
    )
    roundtrip(s)


@pytest.mark.parametrize("remove", ["explicit", "zone", "control", "phase"])
def test_explicit_removal_clears_targetless_blocking_before_trigger(cards, remove):
    s = game(cards)
    blocker = pending(s)
    if remove == "explicit":
        act(s, "p2", type="block", card_id=blocker.id, attacker_id=None)
    elif remove == "zone":
        act(s, "p2", type="move", card_ids=[blocker.id], to={"player": "p2", "zone": "hand"})
    elif remove == "control":
        act(s, "p1", type="set_controller", card_ids=[blocker.id], player="p1")
    else:
        act(s, "p2", type="phase_shift", card_ids=[blocker.id], out=True)
    assert (
        not s.state.cards[blocker.id].is_blocking and not s.state.cards[blocker.id].blocking_without_attacker
    )
    settle(s)
    assert s.state.cards[blocker.id].damage <= 2
    roundtrip(s)
