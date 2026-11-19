"""-- player ease -- the mana readout by the hand (``rules.mana_ready``), the hand's pay preview (read-only, own hand only) and the
Undo button's label (``undo_label``: what it takes back)."""

from __future__ import annotations

import json

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.view import pay_preview
from tests.game_helpers import act, deck, enable


def table(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Cabal Coffers"), (3, "Swamp"), (2, "Mountain"), (1, "Lightning Bolt"), (1, "Grizzly Bears")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Lightning Bolt"), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    lands = [c.id for c in s.state.cards.values() if c.owner == "p1" and c.name in ("Cabal Coffers", "Swamp", "Mountain")]
    act(s, "p1", type="move", card_ids=lands, to={"zone": "battlefield"})
    return s


def card(s, name, owner):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == owner)


def test_mana_readout_counts_and_names_the_mana(cards):
    s = table(cards)
    ready = s.view("p1")["rules"]["mana_ready"]
    assert ready["count"] == 6 and ready["symbols"] == ["B", "B", "B", "R", "R"]  # (three Swamps, two Mountains; the Coffers: in the count)
    assert "mana_ready" not in s.view("__spectator__").get("rules", {})


def test_pay_preview_taps_the_red_and_changes_nothing(cards):
    s = table(cards)
    bolt = card(s, "Lightning Bolt", "p1")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "hand"})
    before = json.dumps(s.state.model_dump(mode="json"), sort_keys=True)
    tapped = pay_preview(s.state, "p1", bolt.id, s.cards)
    assert tapped is not None and len(tapped) == 1 and s.state.cards[tapped[0]].name == "Mountain"
    assert json.dumps(s.state.model_dump(mode="json"), sort_keys=True) == before


def test_pay_preview_is_only_about_your_own_hand(cards):
    s = table(cards)
    theirs = card(s, "Lightning Bolt", "p2")
    act(s, "p2", type="move", card_ids=[theirs.id], to={"zone": "hand"})
    assert pay_preview(s.state, "p1", theirs.id, s.cards) is None


def test_undo_label_names_what_undo_takes_back(cards):
    s = table(cards)
    bears = card(s, "Grizzly Bears", "p1")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"G": 2})
    act(s, "p1", type="cast_spell", card_id=bears.id)
    from app.game import undo_requests

    assert undo_requests.view_fields(s, "p2", host=True, others=None)["undo_label"] == "cast Grizzly Bears"
