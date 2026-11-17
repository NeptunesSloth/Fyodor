"""-- bot levels -- the test opponent plays at Simple, Intermediate or Advanced (app/game/bot.py): each level differs in a key decision.
Simple: lands and spells, naive attacks, no abilities; Intermediate: + abilities, tricks, the crack-back, threat-based removal; Advanced:
+ the most mana-efficient spells, counterspells at threats, board wipes only when behind, a play early in its opening hand. The level is
recorded on the seat (set_bot_level is an action like any): replays and saves keep it; a save from before the levels reads as Intermediate."""

from __future__ import annotations

import pytest

from app.game import bot
from app.game.errors import ActionError
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_test_opponent import human_move, play, replay_matches
from tests.test_test_opponent_abilities import board, cards  # noqa: F401 - the fixture with the test cards


def level(s, name: str) -> None:
    if s.state.players["p2"].bot_level != name:
        act(s, "p1", type="set_bot_level", player="p2", level=name)


def casts(s) -> list[str]:
    return [s.state.cards[a.card_id].name for a in s.history.actions if a.type == "cast_spell" and a.actor == "p2"]


def to_alices_main(s) -> None:
    for _ in range(100):
        r = s.state.rules
        if s.state.turn.phase == "main1" and r.priority == "p1" and r.decision is None:
            return
        if bot.step(s) is None:
            human_move(s)
    raise AssertionError("never got to Alice's main phase")


# ---------------------------------------------------------------------------- the level on the seat


def test_the_level_is_recorded_shown_and_replayed(cards):
    s, _ = board(cards, theirs=("Grizzly Bears",))
    assert s.state.players["p2"].bot_level == "intermediate"
    level(s, "advanced")
    assert s.state.players["p2"].bot_level == "advanced"
    view = bot.observe(s.state, "p1", cards)
    assert next(p for p in view["players"] if p["id"] == "p2")["bot_level"] == "advanced"
    with pytest.raises(ActionError, match="already"):
        act(s, "p1", type="set_bot_level", player="p2", level="advanced")
    with pytest.raises(ActionError):
        act(s, "p1", type="set_bot_level", player="p1", level="simple")  # (Alice isn't an opponent the server plays for)
    replay_matches(s)


def test_a_save_from_before_the_levels_reads_as_intermediate(cards):
    s, _ = board(cards)
    saved = s.state.model_dump(mode="json")
    del saved["players"]["p2"]["bot_level"]
    assert GameState.model_validate(saved).players["p2"].bot_level == "intermediate"


# ---------------------------------------------------------------------------- what each level does


def test_simple_never_activates_abilities_intermediate_does(cards):
    for name, pings in (("simple", 0), ("intermediate", 1)):
        s, ids = board(cards, mine=("Llanowar Elves",), theirs=("Test Pinger",))
        level(s, name)
        play(s, until_turn=2)
        assert len([a for a in s.history.actions if a.type == "activate_ability" and a.actor == "p2"]) == pings, name


def test_the_crack_back_keeps_a_blocker_home_from_intermediate_on(cards):
    """At 4 life against two 2/2s its 3/3 stays home (Intermediate); Simple attacks anyway; at 20 life Intermediate attacks too."""
    for name, life, attacks in (("intermediate", 4, False), ("simple", 4, True), ("intermediate", 20, True)):
        s, _ = board(cards, life=life, mine=("Grizzly Bears", "Grizzly Bears"), theirs=("Test Ogre",))
        level(s, name)
        play(s, until_turn=2)
        declared = [a for a in s.history.actions if a.type == "declare_attackers" and a.actor == "p2"]
        assert bool(declared and declared[-1].attackers) == attacks, (name, life)


def test_advanced_casts_the_most_mana_efficient_spells(cards):
    """Four mana and a 3-drop and two 2-drops: Advanced casts both 2-drops; Intermediate the most expensive first (the 3-drop alone)."""
    for name, expect in (("advanced", ["Grizzly Bears", "Grizzly Bears"]), ("intermediate", ["Test Ogre"])):
        s, _ = board(cards, theirs=("Forest", "Forest", "Mountain"), top=[(1, "Test Ogre"), (2, "Grizzly Bears")])
        level(s, name)
        play(s, until_turn=2)
        assert sorted(casts(s)) == expect, name
        replay_matches(s)


def test_advanced_counters_a_commander_intermediate_lets_it_resolve(cards):
    for name, countered in (("advanced", True), ("intermediate", False)):
        s, _ = board(cards, mine=("Mountain", "Mountain", "Mountain", "Mountain"), theirs=("Island", "Island"), top=[(1, "Counterspell")])
        level(s, name)
        to_alices_main(s)
        krenko = s.state.zones["p1:command"][0]
        act(s, "p1", type="cast_spell", card_id=krenko)
        play(s, until_turn=1)
        assert ("Counterspell" in casts(s)) == countered, name
        assert (s.state.cards[krenko].zone != "p1:battlefield") == countered, name
        replay_matches(s)


def test_advanced_wipes_the_board_only_when_behind(cards):
    for theirs, wipes in ((("Mountain", "Mountain"), True), (("Mountain", "Mountain", "Grizzly Bears", "Grizzly Bears", "Test Ogre"), False)):
        s, _ = board(cards, mine=("Llanowar Elves", "Grizzly Bears"), theirs=theirs, top=[(1, "Pyroclasm")])
        level(s, "advanced")
        play(s, until_turn=2)
        assert ("Pyroclasm" in casts(s)) == wipes, theirs


def test_advanced_mulligans_a_hand_with_nothing_to_play_early(cards):
    """Three lands and four 5-drops: Intermediate keeps (2-5 lands), Advanced mulligans once."""
    from app.game.mulligan import resolve_policy
    from tests.test_test_opponent import table

    heavy = [(3, "Forest"), (4, "Gideon Jura"), *[(1, n) for _ in range(10) for n in ("Forest", "Grizzly Bears")]]
    for name, mulligans in (("intermediate", 0), ("advanced", 1)):
        s = table(cards, opponent=heavy, mulligan="london")
        level(s, name)
        for _ in range(10):
            if bot.step(s) is None and not human_move(s):
                break
        assert s.state.pregame.seats["p2"].mulligans == mulligans, name
