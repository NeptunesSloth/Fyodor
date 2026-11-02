"""Whole games with the two real Commander decks (tests/fixtures/soak_decks) at the Full automation level, played by tools/soak.py's
bot: every seat picks among the moves the engine offers it (hints, decisions, attackers, blockers). A short seeded run, 2 and 4 players
with the seats alternating the decks: no AutomationError, no unexpected exception, no hint the engine refuses; the history replays and
a save loads back to the table (every 50 actions and at the end); no seat's view shows another seat's hand or library."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools import soak

DB = Path(__file__).resolve().parents[2] / "data" / "cards.sqlite"


@pytest.mark.parametrize(("players", "seed", "turns"), [(2, 11, 6), (4, 21, 6)])
def test_real_decks_play_whole_turns_cleanly(players: int, seed: int, turns: int) -> None:
    if not DB.is_file():
        pytest.skip("needs the real card database (data/cards.sqlite)")
    report = soak.run(DB, games=1, turns=turns, seed=seed, players=players)
    assert not report.problems, report.text()
    assert report.games == 1 and report.actions > 10 and report.turns == turns
