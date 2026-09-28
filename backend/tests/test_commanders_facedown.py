"""Multiple commanders (partner & co.), no forced command-zone returns, face-down kinds."""

from __future__ import annotations

import json

from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.storage.saves import load_payload
from tests.game_helpers import act, deck, find


def partner_session(cards) -> GameSession:
    d = deck(cards, "Krenko, Mob Boss", [(1, "Delver of Secrets"), (10, "Mountain")])
    lim = cards.resolve("Lim-Dûl the Necromancer")
    d.append(DeckCard("commander", 1, lim["name"], lim["id"]))  # a second commander (partner-style pair)
    other = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    state = new_game([PlayerSetup("Mike", cards=d), PlayerSetup("Jonathan", cards=other)])
    return GameSession(state, cards=cards)


def test_each_commander_tracks_its_own_tax_casts_and_damage(cards):
    s = partner_session(cards)
    krenko, lim = find(s.state, "Krenko, Mob Boss"), find(s.state, "Lim-Dûl the Necromancer")
    assert krenko.commander_key != lim.commander_key and krenko.zone == lim.zone == "p1:command"
    for _ in range(2):
        act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "stack"})
        act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "command"})
    act(s, "p1", type="move", card_ids=[lim.id], to={"zone": "stack"})
    mike = s.state.players["p1"]
    assert mike.commander_tax == {krenko.commander_key: 4, lim.commander_key: 2}
    assert mike.commander_casts == {krenko.commander_key: 2, lim.commander_key: 1}
    act(s, "p2", type="commander_damage", player="p2", commander=krenko.commander_key, delta=8)
    act(s, "p2", type="commander_damage", player="p2", commander=lim.commander_key, delta=3)
    assert s.state.players["p2"].commander_damage == {krenko.commander_key: 8, lim.commander_key: 3}
    cmds = {c["name"]: c for c in next(p for p in s.view("p2")["players"] if p["id"] == "p1")["commanders"]}
    assert cmds["Krenko, Mob Boss"]["tax"] == 4 and cmds["Krenko, Mob Boss"]["casts"] == 2
    assert cmds["Lim-Dûl the Necromancer"]["tax"] == 2 and cmds["Lim-Dûl the Necromancer"]["casts"] == 1
    # commander damage is damage (life goes down), but nobody is ever eliminated automatically
    assert s.state.players["p2"].life == 29 and s.state.seat_order == ["p1", "p2"]


def test_commanders_go_where_you_put_them(cards):
    s = partner_session(cards)
    krenko = find(s.state, "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "graveyard"})
    assert krenko.zone == "p1:graveyard"  # no automatic return; the player chooses
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "command"})
    assert krenko.zone == "p1:command"


def test_face_down_kinds_are_public_identity_stays_private(cards):
    s = partner_session(cards)
    act(s, "p1", type="draw", count=6)
    delver = find(s.state, "Delver of Secrets // Insectile Aberration")
    act(s, "p1", type="move", card_ids=[delver.id], to={"zone": "battlefield"}, face_down=True, face_down_kind="morph", x=10, y=10)
    theirs = s.view("p2")["cards"][delver.id]
    assert theirs["hidden"] and theirs["face_down_kind"] == "morph" and "name" not in theirs
    assert "Delver" not in json.dumps({k: v for k, v in s.view("p2").items() if k != "log"})
    mine = s.view("p1")["cards"][delver.id]
    assert mine["name"].startswith("Delver") and mine["face_down_kind"] == "morph"
    # manifest the top card, exile face down, turn face up
    top = s.state.zones["p1:library"][0]
    act(s, "p1", type="move", card_ids=[top], to={"zone": "battlefield"}, face_down=True, face_down_kind="manifest", x=50, y=10)
    assert s.state.cards[top].face_down_kind == "manifest"
    mountain = find(s.state, "Mountain", "p1")
    act(s, "p1", type="move", card_ids=[mountain.id], to={"zone": "exile"}, face_down=True)
    assert s.state.cards[mountain.id].face_down_kind == "exile"
    act(s, "p1", type="face_down", card_ids=[delver.id], face_down=False)
    assert s.state.cards[delver.id].face_down_kind is None and s.view("p2")["cards"][delver.id]["name"].startswith("Delver")
    # turning face down again with a kind
    act(s, "p1", type="face_down", card_ids=[delver.id], face_down=True, kind="disguise")
    assert s.view("p2")["cards"][delver.id]["face_down_kind"] == "disguise"
    # survives save/load
    state, _ = load_payload({"state": s.state.model_dump(mode="json"), "history": s.history.to_dict()})
    assert state.cards[delver.id].face_down_kind == "disguise"


def test_manifest_and_cloak_the_top_of_a_library(cards):
    s = partner_session(cards)
    top2 = s.state.zones["p1:library"][:2]
    act(s, "p1", type="put_top_face_down", count=2, kind="cloak")
    assert all(s.state.cards[c].zone == "p1:battlefield" and s.state.cards[c].face_down_kind == "cloak" for c in top2)
    bob = s.view("p2")
    assert all(bob["cards"][c]["hidden"] and bob["cards"][c]["face_down_kind"] == "cloak" for c in top2)
    assert "cloaked the top 2 cards" in json.dumps(bob["log"])
