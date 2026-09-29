"""Milestone 15b: state-based actions and the commander's trip to the command zone."""

from __future__ import annotations

import json

from tests.game_helpers import act, find
from tests.test_rules_casting import build, put, rules


def test_lethal_damage_and_zero_toughness(cards):
    s = build(cards, [(1, "Llanowar Elves"), (3, "Forest")], [(5, "Island")])
    elves = put(s, "p1", "Llanowar Elves", "battlefield")
    act(s, "p1", type="create_token", token={"name": "Squirrel", "type_line": "Token Creature — Squirrel",
                                             "power": "1", "toughness": "1"})
    delver = find(s.state, "Squirrel", "p1")
    act(s, "p1", type="set_damage", card_ids=[elves.id], value=1)  # by hand: nothing happens yet
    act(s, "p1", type="counter", card_ids=[delver.id], kind="-1/-1", delta=1)
    assert s.state.cards[elves.id].zone == "p1:battlefield"
    act(s, "p1", type="pass_priority")  # the engine acts: state-based actions first
    assert s.state.cards[elves.id].zone == "p1:graveyard" and delver.id not in s.state.cards  # tokens cease to exist
    log = json.dumps(s.view("p2")["log"])
    assert "lethal damage" in log and "0 toughness" in log


def test_counters_annihilate_and_indestructible(cards):
    s = build(cards, [(3, "Forest")], [(5, "Island")])
    act(s, "p1", type="create_token", token={"name": "Wall", "type_line": "Token Creature — Wall", "power": "0",
                                             "toughness": "2", "text": "Indestructible"})
    wall = find(s.state, "Wall", "p1")
    act(s, "p1", type="counter", card_ids=[wall.id], kind="+1/+1", delta=2)
    act(s, "p1", type="counter", card_ids=[wall.id], kind="-1/-1", delta=1)
    act(s, "p1", type="set_damage", card_ids=[wall.id], value=9)
    act(s, "p1", type="pass_priority")
    wall = s.state.cards[wall.id]
    assert wall.counters == {"+1/+1": 1} and wall.zone == "p1:battlefield"  # indestructible: damage doesn't kill
    act(s, "p1", type="counter", card_ids=[wall.id], kind="-1/-1", delta=4)
    act(s, "p1", type="pass_priority")
    assert wall.id not in s.state.cards  # 0 toughness → graveyard → a token there ceases to exist


def test_players_lose_and_the_last_one_wins(cards):
    s = build(cards, [(3, "Forest")], [(5, "Island")])
    act(s, "p2", type="set_life", player="p2", value=0)
    act(s, "p1", type="pass_priority")
    r = rules(s)
    assert r.lost == {"p2": "0 or less life"} and r.winner == "p1" and r.priority == "p1"
    view = s.view("p2")["rules"]
    assert view["winner"] == "p1" and view["lost"] == {"p2": "0 or less life"}
    assert "Bob loses the game" in json.dumps(s.view("p1")["log"])


def test_poison_and_commander_damage(cards):
    from app.game.factory import DeckCard, PlayerSetup, new_game
    from app.game.rules_state import start_rules
    from app.game.session import GameSession

    def deck(name):
        cmd = cards.resolve(name)
        return [DeckCard("commander", 1, cmd["name"], cmd["id"]), DeckCard("main", 5, "Forest", cards.resolve("Forest")["id"])]

    state = new_game([PlayerSetup("A", cards=deck("Krenko, Mob Boss")), PlayerSetup("B", cards=deck("Atraxa, Praetors' Voice")),
                      PlayerSetup("C", cards=deck("Krenko, Mob Boss"))], shuffle=False)
    state.settings.automation = "rules"
    start_rules(state)
    s = GameSession(state, cards=cards)
    krenko = find(s.state, "Krenko, Mob Boss", "p1")
    act(s, "p2", type="resource", player="p2", key="poison", delta=10)
    act(s, "p3", type="commander_damage", player="p3", commander=krenko.commander_key, delta=21, affect_life=False)
    act(s, "p1", type="pass_priority")
    assert rules(s).lost == {"p2": "10 poison counters", "p3": "21 combat damage from one commander"}
    assert rules(s).winner == "p1"


def test_legend_rule_asks_which_to_keep(cards):
    s = build(cards, [(3, "Forest")], [(5, "Island")])
    krenko = find(s.state, "Krenko, Mob Boss", "p1")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    act(s, "p1", type="copy_card", card_id=krenko.id)
    act(s, "p1", type="pass_priority")
    d = rules(s).decision
    assert d and d.player == "p1" and "Legend rule" in d.prompt and len(d.options) == 2
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[krenko.id])
    krenkos = [c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss"]
    assert [c.id for c in krenkos if c.zone.endswith("battlefield")] == [krenko.id]


def test_commander_may_return_to_the_command_zone(cards):
    s = build(cards, [(3, "Forest")], [(5, "Island")])
    krenko = find(s.state, "Krenko, Mob Boss", "p1")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "graveyard"})
    act(s, "p1", type="pass_priority")
    d = rules(s).decision
    assert d and d.kind == "confirm" and d.player == "p1" and "command zone" in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["no"])
    assert s.state.cards[krenko.id].zone == "p1:graveyard" and rules(s).decision is None
    act(s, "p1", type="pass_priority")  # not asked again while it stays there
    assert rules(s).decision is None and rules(s).priority == "p2"
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "exile"})
    act(s, "p2", type="pass_priority")  # whoever acts next: the offer comes first
    d = rules(s).decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    assert s.state.cards[krenko.id].zone == "p1:command"


def test_drawing_from_an_empty_library_loses(cards):
    s = build(cards, [(1, "Forest")], [(5, "Island")])
    act(s, "p1", type="move", card_ids=[c for c in s.state.zones["p1:library"]], to={"zone": "exile"})
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="pass_priority")  # Bob's turn …
    act(s, "p2", type="pass_priority")
    act(s, "p2", type="pass_priority")  # … Alice's draw step: nothing to draw
    assert rules(s).lost.get("p1") == "drew from an empty library" and rules(s).winner == "p2"
