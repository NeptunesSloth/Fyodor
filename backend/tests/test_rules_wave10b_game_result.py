"""Wave 10B: statics about losing and winning the game (app/rules/game_result.py), real Oracle text.

* Platinum Angel / Herald of Eternal Dawn: "You can't lose the game and your opponents can't win the game." (104.3, 104.2):
  0 life doesn't end the game for its controller; once the permanent is gone the next check (704.3) ends it.
* Abyssal Persecutor: "You can't win the game and your opponents can't lose the game.": its controller isn't the winner
  while it stays, the opponents with 0 life stay in the game.
Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_permissions import build, put

EXTRA = [
    card('Platinum Angel', set_code="tst", number="10B200", mana_cost='{7}', cmc=7.0, type_line='Artifact Creature — Angel', oracle_text="Flying\nYou can't lose the game and your opponents can't win the game.", power='4', toughness='4', keywords=['Flying']),  # noqa: E501
    card('Abyssal Persecutor', set_code="tst", number="10B201", mana_cost='{2}{B}{B}', cmc=4.0, type_line='Creature — Demon', oracle_text="Flying, trample\nYou can't win the game and your opponents can't lose the game.", power='6', toughness='6', colors=['B'], color_identity=['B'], keywords=['Flying', 'Trample']),  # noqa: E501
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


@pytest.mark.parametrize("name", ["Platinum Angel", "Abyssal Persecutor"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def lost(s):
    return dict(s.state.rules.lost)


def agent(s, pid, text):
    """A token with an activated ability: ``text`` (its cost is {1}, paid with colorless mana)."""
    act(s, pid, type="create_token", player=pid, token={"name": f"Agent {pid}", "type_line": "Token Artifact — Test",
                                                        "text": text, "colors": []})
    return next(c for c in s.state.cards.values() if c.name == f"Agent {pid}")


def activate(s, card_, pid):
    act(s, pid, type="add_mana", player=pid, mana={"C": 1})
    act(s, pid, type="activate_ability", card_id=card_.id, ability=0)
    pass_until_stack_empty(s)


def test_a_player_with_platinum_angel_stays_in_the_game_at_zero_life_and_loses_when_it_leaves(cards):
    s = build(cards, [(1, "Platinum Angel")], [(1, "Grizzly Bears")])
    angel = put(s, "Platinum Angel", "battlefield")
    drain = agent(s, "p1", "{1}: You lose 43 life.")
    activate(s, drain, "p1")
    assert s.state.players["p1"].life == -3 and "p1" not in lost(s) and s.state.rules.winner is None
    roundtrip(s)
    act(s, "p1", type="move", card_ids=[angel.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="pass_priority")  # (the next check: a table move is not an intent)  # 704.5a at the next check
    assert "p1" in lost(s) and s.state.rules.winner == "p2"
    replay_matches(s)


def test_a_draw_from_an_empty_library_is_not_remembered_while_the_angel_is_there(cards):
    """704.5b: the check that passed with the Angel there used the attempt up; once it leaves nobody loses for it."""
    s = build(cards, [(1, "Platinum Angel")], [(1, "Grizzly Bears")])
    angel = put(s, "Platinum Angel", "battlefield")
    if s.state.zones.get("p1:library"):
        act(s, "p1", type="move", card_ids=list(s.state.zones["p1:library"]), to={"player": "p1", "zone": "graveyard"})
    scholar = agent(s, "p1", "{1}: Draw a card.")
    activate(s, scholar, "p1")
    assert "p1" not in lost(s) and "p1" not in s.state.rules.drew_from_empty
    act(s, "p1", type="move", card_ids=[angel.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="pass_priority")  # (the next check: a table move is not an intent)
    assert "p1" not in lost(s) and s.state.rules.winner is None
    roundtrip(s)


def test_an_opponent_of_platinum_angel_still_loses_normally(cards):
    s = build(cards, [(1, "Platinum Angel")], [(1, "Grizzly Bears")])
    put(s, "Platinum Angel", "battlefield")
    drain = agent(s, "p1", "{1}: Each opponent loses 43 life.")
    activate(s, drain, "p1")
    assert "p2" in lost(s) and s.state.rules.winner == "p1"  # (the Angel's controller can win)
    roundtrip(s)


def test_abyssal_persecutor_keeps_the_opponents_in_and_its_controller_from_winning(cards):
    s = build(cards, [(1, "Abyssal Persecutor")], [(1, "Grizzly Bears")])
    persecutor = put(s, "Abyssal Persecutor", "battlefield")
    drain = agent(s, "p1", "{1}: Each opponent loses 43 life.")
    activate(s, drain, "p1")
    assert s.state.players["p2"].life == -3 and "p2" not in lost(s) and s.state.rules.winner is None  # can't lose
    act(s, "p2", type="concede")  # leaves the game: Alice is the last one, but can't win while it is there
    assert s.state.rules.winner is None
    roundtrip(s)
    act(s, "p1", type="move", card_ids=[persecutor.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="pass_priority")
    assert s.state.rules.winner == "p1"  # nothing stops the win any more
    replay_matches(s)
