"""Loops and single targets, real Oracle text.

* 603.3d / 601.2c: a triggered ability with exactly one legal target takes it without asking (Sanguine Bond with one opponent).
* 104.4b / 732.4: a loop of mandatory actions is a draw only if no player can stop it, which the engine can't know (a held
  instant), so it never ends the game itself: a long chain pauses the automatic passing between two resolutions, every
  player gets priority back, and passing again carries on (engine.loop_pause).
Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.state import GameState
from app.rules import coverage
from app.rules.plan import live_players
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import replay_matches
from tests.test_rules_permissions import build, put

EXTRA = [
    card("Sanguine Bond", set_code="tst", number="LP1", mana_cost="{3}{B}{B}", cmc=5.0, type_line="Enchantment",
         oracle_text="Whenever you gain life, target opponent loses that much life.", colors=["B"], color_identity=["B"]),
    card("Exquisite Blood", set_code="tst", number="LP2", mana_cost="{4}{B}", cmc=5.0, type_line="Enchantment",
         oracle_text="Whenever an opponent loses life, you gain that much life.", colors=["B"], color_identity=["B"]),
    card("Platinum Angel", set_code="tst", number="LP3", mana_cost="{7}", cmc=7.0, type_line="Artifact Creature — Angel",
         oracle_text="Flying\nYou can't lose the game and your opponents can't win the game.", power="4", toughness="4",
         keywords=["Flying"]),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped


def combo(cards, bob=((10, "Island"),)):
    s = build(cards, [(1, "Sanguine Bond"), (1, "Exquisite Blood")], bob)
    put(s, "Sanguine Bond", "battlefield")
    put(s, "Exquisite Blood", "battlefield")
    act(s, "p1", type="create_token", player="p1", token={"name": "Agent", "type_line": "Token Artifact — Test",
                                                          "text": "{1}: You gain 1 life.", "colors": []})
    agent = next(c for c in s.state.cards.values() if c.name == "Agent")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="activate_ability", card_id=agent.id, ability=0)
    return s


def passes(s, limit):
    """Pass whenever the stack holds something; return how many passes it took. No question may come up."""
    for n in range(limit):
        r = s.state.rules
        assert r.decision is None, r.decision.prompt
        if not s.state.zones.get("stack") or r.draw_reason or len(live_players(s.state)) < 2:
            return n
        act(s, r.priority, type="pass_priority")
    return limit


@pytest.mark.parametrize("name", ["Sanguine Bond", "Exquisite Blood"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_one_opponent_is_the_target_without_a_question_and_the_drain_ends_the_game(cards):
    s = combo(cards)
    passes(s, 60)
    assert s.state.players["p2"].life <= 0 and "p2" in s.state.rules.lost
    roundtrip(s)


def test_a_loop_that_cannot_end_pauses_instead_of_failing(cards):
    s = combo(cards, bob=((1, "Platinum Angel"), (9, "Island")))
    put(s, "Platinum Angel", "battlefield", "p2")
    act(s, s.state.rules.priority, type="pass_priority")  # Bob can't lose: the drain never stops on its own
    assert s.state.zones.get("stack"), "the loop paused with its next ability still on the stack"
    assert any("keeps repeating" in str(e.model_dump()) for e in s.state.log[-5:])
    assert s.state.rules.priority == "p1" and s.state.rules.passed == []  # the active player has their choices back
    life = s.state.players["p2"].life
    act(s, "p1", type="pass_priority")
    act(s, s.state.rules.priority, type="pass_priority")  # passing again carries on, and pauses again
    assert s.state.players["p2"].life < life and "p2" not in s.state.rules.lost
    roundtrip(s)
