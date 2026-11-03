"""603.3b: every waiting trigger goes on the stack before a player gets priority. A big board's batch (dozens of landfall
triggers) must fit even when it is bigger than what is left of the action's step budget (Plan.max_steps, a safety valve
against runaway loops): before, the whole action was refused ("too many steps for one action") and the land couldn't be
played. Real Oracle text; replay and a save/load round trip. The budget is shrunk here so a small board shows it."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.rules import plan as plan_mod
from tests.game_helpers import act, deck, enable
from tests.wave9c_kit import check


@pytest.fixture()
def real_cards():
    from app.cards.images import ImageStore
    from app.cards.repository import CardRepository

    db = Path(__file__).resolve().parents[2] / "data" / "cards.sqlite"
    if not db.is_file():
        pytest.skip("needs the real card database at data/cards.sqlite")
    repo = CardRepository(db, ImageStore(db.parent / "images"))
    yield repo
    repo.close()


def crabs(cards, n):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession

    alice = deck(cards, "Krenko, Mob Boss", [(n, "Ruin Crab"), (3, "Mountain")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(80, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    mine = lambda name: [c.id for c in s.state.cards.values() if c.owner == "p1" and c.name == name]  # noqa: E731
    act(s, "p1", type="move", card_ids=mine("Ruin Crab"), to={"player": "p1", "zone": "battlefield"})
    land = mine("Mountain")[0]
    act(s, "p1", type="move", card_ids=[land], to={"player": "p1", "zone": "hand"})
    return s, land


def test_a_trigger_batch_bigger_than_the_step_budget_still_goes_on_the_stack(real_cards, monkeypatch):
    monkeypatch.setattr(plan_mod, "MAX_STEPS", 40)
    s, land = crabs(real_cards, 60)
    act(s, "p1", type="play_land", card_id=land)  # was refused: "The rules engine stopped: too many steps for one action"
    assert s.state.cards[land].zone == "p1:battlefield"
    assert not s.state.rules.pending_triggers  # all 60 went on the stack (603.3b)
    left = len(s.state.zones.get("stack") or [])  # those the automatic passing hadn't resolved yet (engine.loop_pause)
    assert len(s.state.zones["p2:graveyard"]) == min(80, 3 * (60 - left))  # each resolved crab milled three
    check(s)


def test_a_small_batch_resolves_as_before(real_cards, monkeypatch):
    s, land = crabs(real_cards, 3)
    act(s, "p1", type="play_land", card_id=land)
    assert not s.state.zones.get("stack") and len(s.state.zones["p2:graveyard"]) == 9  # three crabs, three cards each
    check(s)
