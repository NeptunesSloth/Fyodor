"""-- playtest (nov 18) -- the combat prompts list each creature by the face that is up (712.8: a transformed Delver of Secrets is "Insectile
Aberration", not "Delver of Secrets // Insectile Aberration"), and the declare-attackers prompt carries each creature's power/toughness and
combat keywords (``display.stats``, as the blockers prompt does) for the table's rows and its "attack with all" summary."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable


def table(cards):
    alice = deck(cards, "Atraxa, Praetors' Voice", [(1, "Delver of Secrets // Insectile Aberration"), (1, "Grizzly Bears"), (10, "Island")])
    bob = deck(cards, "Krenko, Mob Boss", [(1, "Grizzly Bears"), (10, "Mountain")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def put(s, name, pid):
    c = next(c for c in s.state.cards.values() if c.name.startswith(name) and c.owner == pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def play_to(s, kind, pid, limit=200):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == kind and d.player == pid:
            return s.view(pid)["rules"]["decision"]
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            raise AssertionError(d.prompt)
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"{pid} never got {kind}")


def test_attackers_prompt_lists_the_face_up_and_each_creatures_stats(cards):
    s = table(cards)
    delver = put(s, "Delver of Secrets", "p1")
    act(s, "p1", type="set_face", card_id=delver.id, face=1)
    put(s, "Grizzly Bears", "p1")
    act(s, "p1", type="create_token", player="p1", token={"name": "Goblin", "power": "1", "toughness": "1", "type_line": "Token Creature — Goblin"},
        count=2, stacked=False)
    d = play_to(s, "declare_attackers", "p1")
    attackers = [o for o in d["options"] if o["id"].startswith("a:")]
    labels = {o["card_id"]: o["label"] for o in attackers}
    assert labels[delver.id] == "Insectile Aberration"
    assert sorted(labels.values()) == ["Goblin", "Goblin", "Grizzly Bears", "Insectile Aberration"]
    stats = d["display"]["stats"]
    assert set(stats) == {o["card_id"] for o in attackers}
    assert stats[delver.id] == {"pt": "3/2", "keywords": ["flying"]}
    assert sorted(v["pt"] for v in stats.values()) == ["1/1", "1/1", "2/2", "3/2"]
    assert s.view("p2")["rules"]["decision"].get("display") is None  # the attacker's guide is the chooser's alone


def test_blockers_prompt_lists_the_face_up(cards):
    s = table(cards)
    delver = put(s, "Delver of Secrets", "p1")
    act(s, "p1", type="set_face", card_id=delver.id, face=1)
    bears = put(s, "Grizzly Bears", "p2")
    play_to(s, "declare_attackers", "p2")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
    d = play_to(s, "declare_blockers", "p1")
    labels = {o["id"]: o["label"] for o in d["options"]}
    assert labels[f"b:{delver.id}"] == "Insectile Aberration"
    assert labels[f"a:{bears.id}"] == "Grizzly Bears"


def test_trample_division_lists_each_blockers_lethal_damage_and_the_rest(cards):
    alice = deck(cards, "Atraxa, Praetors' Voice", [(1, "Garruk's Horde"), (10, "Forest")])
    bob = deck(cards, "Krenko, Mob Boss", [(2, "Grizzly Bears"), (10, "Mountain")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    horde = put(s, "Garruk's Horde", "p1")
    bears = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"]
    for b in bears:
        act(s, "p2", type="move", card_ids=[b.id], to={"player": "p2", "zone": "battlefield"})
    for _ in range(4):
        d = play_to(s, "declare_attackers", "p1")
        if any(o["id"] == f"a:{horde.id}" for o in d["options"]):
            break
        act(s, "p1", type="declare_attackers", attackers=[])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": horde.id, "target": "p2"}])
    play_to(s, "declare_blockers", "p2")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": horde.id} for b in bears])
    for _ in range(50):
        d = s.state.rules.decision
        if d is not None and d.kind == "divide":
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options[: max(1, d.min_choices)]])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    shown = s.view("p1")["rules"]["decision"]
    assert shown["kind"] == "divide" and [o["id"] for o in shown["options"]] == [*(b.id for b in bears), "p2"]
    display = shown["display"]
    assert (display["need"], display["free"], display["deathtouch"], display["total"]) == ([2, 2], 2, False, 7)
    assert display["stats"][bears[0].id] == {"pt": "2/2", "keywords": [], "damage": 0}
