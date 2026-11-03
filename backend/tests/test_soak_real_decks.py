"""Whole games with the pod's real Commander decks (tests/fixtures/soak_decks) at the Full automation level, played by tools/soak.py's
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


POD_DECKS = ("kiora_underdasea.txt", "ian_malcolm_group_play.txt", "grand_arbiter_augustin_iv_interesting.txt",
             "disa_the_restless_disa_eldrazo.txt", "zedruu_the_greathearted_grouphug.txt", "atraxa_exp_bar_low.txt")


def test_the_pods_other_decks_play_whole_turns_cleanly() -> None:
    """The pod's six other Archidekt decks (UnderDaSea, Group play, Interesting, Disa the Restless eldrazo, grouphug, my exp bar is
    low), four seats a game, two games so every deck sits down."""
    if not DB.is_file():
        pytest.skip("needs the real card database (data/cards.sqlite)")
    report = soak.run(DB, games=2, turns=5, seed=3101, players=4, deck_files=POD_DECKS)
    assert not report.problems, report.text()
    assert report.games == 2 and report.actions > 20
    # the report says what each deck did (no problems means little if a deck never got going)
    assert set(report.decks) == {Path(n).stem for n in POD_DECKS}, report.text()
    assert all(use.seated >= 1 for use in report.decks.values()) and "what each deck did" in report.text()


def test_a_seed_replays_the_same_game_alone_or_in_a_run() -> None:
    """One seed is one game: the second game of a run (seed 42) is the game a run of seed 42 alone plays, and a run plays the same
    games twice. (The session's undo-request recorder took its randomness from the engine's module source, which the soak didn't pin:
    a failing seed couldn't be replayed.)"""
    if not DB.is_file():
        pytest.skip("needs the real card database (data/cards.sqlite)")
    run = soak.run(DB, games=2, turns=8, seed=41, players=2)
    again = soak.run(DB, games=2, turns=8, seed=41, players=2)
    alone = soak.run(DB, games=1, turns=8, seed=42, players=2)
    assert run.digests == again.digests
    assert run.digests[1] == alone.digests[0]
