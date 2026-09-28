"""Manual table tracking: effects, damage, choices, stack notes, exile groups, arrows, cleanup."""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.storage.saves import load_payload
from tests.fixtures.cards import GOBLIN, TREASURE
from tests.game_helpers import act, find, make_session


@pytest.fixture()
def s(cards):
    session = make_session(cards)
    act(session, "p1", type="draw", count=15)
    act(session, "p2", type="draw", count=15)
    return session


def play(s, pid, name, x=100, y=100):
    c = find(s.state, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "battlefield"}, x=x, y=y)
    return s.state.cards[c.id]


def test_effects_and_damage_are_manual_and_public(s):
    elves = play(s, "p1", "Llanowar Elves")
    act(s, "p1", type="add_effect", card_ids=[elves.id], name="+3/+3", value="+3/+3")
    act(s, "p1", type="add_effect", card_ids=[elves.id], name="Flying", color="#88aaff")
    act(s, "p1", type="add_effect", card_ids=[elves.id], name="Protection", text="from red")
    act(s, "p1", type="set_damage", card_ids=[elves.id], delta=4)
    act(s, "p1", type="set_damage", card_ids=[elves.id], delta=-1)
    elves = s.state.cards[elves.id]
    assert [e.name for e in elves.effects] == ["+3/+3", "Flying", "Protection"] and elves.damage == 3
    theirs = s.view("p2")["cards"][elves.id]
    assert theirs["damage"] == 3 and theirs["effects"][1] == {"id": elves.effects[1].id, "name": "Flying", "color": "#88aaff"}
    # nothing expires or destroys anything on its own
    act(s, "p1", type="next_turn")
    act(s, "p2", type="next_turn")
    assert s.state.cards[elves.id].zone == "p1:battlefield" and s.state.cards[elves.id].damage == 3
    act(s, "p1", type="remove_effect", card_ids=[elves.id], effect_id=elves.effects[0].id)
    assert len(s.state.cards[elves.id].effects) == 2
    with pytest.raises(ActionError, match="battlefield or the stack"):
        act(s, "p1", type="set_damage", card_ids=[find(s.state, "Mountain", "p1").id], value=2)
    # markers don't follow a card that changes zones
    act(s, "p1", type="move", card_ids=[elves.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[elves.id], to={"zone": "battlefield"})
    assert s.state.cards[elves.id].effects == [] and s.state.cards[elves.id].damage == 0


def test_face_down_markers_are_public_identity_is_not(s):
    delver = find(s.state, "Delver of Secrets // Insectile Aberration", "p1")
    act(s, "p1", type="move", card_ids=[delver.id], to={"zone": "battlefield"}, face_down=True, x=5, y=5)
    act(s, "p1", type="set_damage", card_ids=[delver.id], value=1)
    act(s, "p1", type="set_choice", card_id=delver.id, key="Chosen color", value="Blue")
    theirs = s.view("p2")["cards"][delver.id]
    assert theirs["hidden"] and theirs["damage"] == 1 and "choices" not in theirs
    assert s.view("p1")["cards"][delver.id]["choices"] == {"Chosen color": "Blue"}


def test_choices(s):
    sol = play(s, "p1", "Sol Ring")
    act(s, "p1", type="set_choice", card_id=sol.id, key="Named card", value="Walking Ballista")
    act(s, "p1", type="set_choice", card_id=sol.id, key="Chosen type", value="Dragon")
    assert s.view("p2")["cards"][sol.id]["choices"] == {"Named card": "Walking Ballista", "Chosen type": "Dragon"}
    act(s, "p1", type="set_choice", card_id=sol.id, key="Chosen type", value=None)
    assert s.state.cards[sol.id].choices == {"Named card": "Walking Ballista"}
    act(s, "p1", type="set_choice", card_id=sol.id, key="x", value="<b>bold</b>\x00")
    assert "\x00" not in s.state.cards[sol.id].choices["x"]


def test_stack_x_modes_and_cast_labels(s):
    bolt = find(s.state, "Lightning Bolt", "p1")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "stack"})
    act(s, "p1", type="set_stack_info", card_id=bolt.id, x=7, modes=["Destroy artifact", "Draw a card"], tags=["Kicked"])
    info = s.view("p2")["cards"][bolt.id]["stack_info"]
    assert info == {"x": 7, "modes": ["Destroy artifact", "Draw a card"], "tags": ["Kicked"]}
    act(s, "p1", type="set_stack_info", card_id=bolt.id, modes=["Return creature"])  # change before resolving
    assert s.state.cards[bolt.id].stack_info.modes == ["Return creature"] and s.state.cards[bolt.id].stack_info.x == 7
    act(s, "p1", type="resolve_top")
    assert s.state.cards[bolt.id].stack_info is None
    with pytest.raises(ActionError, match="on the stack"):
        act(s, "p1", type="set_stack_info", card_id=bolt.id, x=1)


def test_exile_groups(s):
    ids = [find(s.state, n, "p1").id for n in ("Sol Ring", "Fire // Ice")]
    act(s, "p1", type="move", card_ids=ids, to={"zone": "exile"})
    act(s, "p1", type="set_exile_group", card_ids=ids, group="Prosper")
    assert {s.view("p2")["cards"][i]["exile_group"] for i in ids} == {"Prosper"}
    act(s, "p1", type="move", card_ids=[ids[0]], to={"zone": "hand"})
    assert s.state.cards[ids[0]].exile_group is None


def test_arrows_multi_target_public_only_and_pruned(s):
    bolt = find(s.state, "Lightning Bolt", "p1")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "stack"})
    elves = play(s, "p1", "Llanowar Elves")
    act(s, "p1", type="create_arrow", source=bolt.id, targets=[elves.id, "p2"], label="3 damage")
    arrows = s.view("p2")["arrows"]
    assert arrows[0]["source"] == bolt.id and arrows[0]["targets"] == [elves.id, "p2"]
    hidden = find(s.state, "Counterspell", "p2")
    with pytest.raises(ActionError, match="public objects"):
        act(s, "p1", type="create_arrow", source=bolt.id, targets=[hidden.id])
    act(s, "p1", type="move", card_ids=[elves.id], to={"zone": "graveyard"})
    assert s.state.arrows[0].targets == ["p2"]  # the dead target drops out
    act(s, "p1", type="resolve_top")
    assert s.state.arrows == []  # source left the stack: arrow gone
    act(s, "p1", type="create_arrow", source="p1", targets=["p2"], kind="custom", label="monarch deal")
    act(s, "p1", type="remove_arrow", arrow_id=s.state.arrows[0].id)
    assert s.state.arrows == []


def test_combat_clear_keeps_cards(s):
    krenko = play(s, "p1", "Krenko, Mob Boss")
    atraxa = play(s, "p2", "Atraxa, Praetors' Voice")
    elves = play(s, "p1", "Llanowar Elves", 300)
    act(s, "p1", type="attack", card_ids=[krenko.id], target={"kind": "card", "id": atraxa.id})  # attack a planeswalker/battle
    act(s, "p1", type="attack", card_ids=[elves.id], target={"kind": "player", "id": "p2"})
    act(s, "p1", type="create_arrow", source=krenko.id, targets=[atraxa.id], kind="attack")
    counterspell = find(s.state, "Command Tower", "p2")
    act(s, "p2", type="move", card_ids=[counterspell.id], to={"zone": "battlefield"})
    act(s, "p2", type="tap", card_ids=[counterspell.id])
    act(s, "p1", type="cleanup", what=["combat"])
    assert all(c.attacking is None and c.blocking is None for c in s.state.cards.values())
    assert s.state.arrows == [] and s.state.cards[counterspell.id].tapped  # cards untouched


def test_cleanup_tools_and_token_provenance(s):
    smith = play(s, "p1", "Sol Ring")
    act(s, "p1", type="create_token", token={"card_id": TREASURE["id"]}, count=6, source_id=smith.id)
    act(s, "p1", type="create_token", token={"card_id": GOBLIN["id"]}, count=2)
    treasure = next(c for c in s.state.cards.values() if c.is_token and c.name == "Treasure")
    assert treasure.token_source.name == "Sol Ring" and treasure.quantity == 6
    assert s.view("p2")["cards"][treasure.id]["token_source"]["name"] == "Sol Ring"
    elves = play(s, "p1", "Llanowar Elves")
    act(s, "p1", type="add_effect", card_ids=[elves.id], name="Trample")
    act(s, "p1", type="set_damage", card_ids=[elves.id], value=2)
    act(s, "p1", type="add_mana", mana={"G": 2})
    act(s, "p1", type="cleanup", what=["damage", "effects", "mana", "tokens"])
    assert not any(c.is_token for c in s.state.cards.values())
    assert s.state.cards[elves.id].damage == 0 and s.state.cards[elves.id].effects == []
    assert s.state.players["p1"].mana == {}
    assert "cleared damage, temporary effects, mana pools, 3 tokens" in json.dumps(s.view("p1")["log"])


def test_change_copy_target(s):
    elves = play(s, "p1", "Llanowar Elves")
    sol = play(s, "p1", "Sol Ring", 300)
    act(s, "p1", type="copy_card", card_id=elves.id)
    copy = next(c for c in s.state.cards.values() if c.copy_of)
    act(s, "p1", type="counter", card_ids=[copy.id], kind="+1/+1", delta=2)
    act(s, "p1", type="set_copy_source", card_id=copy.id, source_id=sol.id)
    copy = s.state.cards[copy.id]
    assert copy.copy_of.source_name == "Sol Ring" and copy.name == "Sol Ring" and copy.counters == {"+1/+1": 2}
    assert copy.owner == "p1" and copy.is_token


def test_marks_survive_save_load_and_undo(s):
    elves = play(s, "p1", "Llanowar Elves")
    act(s, "p1", type="add_effect", card_ids=[elves.id], name="Hexproof")
    act(s, "p1", type="set_damage", card_ids=[elves.id], value=1)
    state, history = load_payload({"state": s.state.model_dump(mode="json"), "history": s.history.to_dict()})
    assert state.cards[elves.id].effects[0].name == "Hexproof" and state.cards[elves.id].damage == 1
    s.undo("p1")
    assert s.state.cards[elves.id].damage == 0 and s.state.cards[elves.id].effects[0].name == "Hexproof"
