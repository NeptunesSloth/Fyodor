"""Milestone 15c: combat through the rules engine."""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, find, turn_on


def table(cards, *, players=2):
    """Sandbox table (creatures are set up by hand first), then automation is switched on."""
    def deck(name):
        cmd = cards.resolve(name)
        return [DeckCard("commander", 1, cmd["name"], cmd["id"]), DeckCard("main", 10, "Forest", cards.resolve("Forest")["id"])]

    names = ["Alice", "Bob", "Carol"][:players]
    commanders = ["Krenko, Mob Boss", "Atraxa, Praetors' Voice", "Krenko, Mob Boss"][:players]
    state = new_game([PlayerSetup(n, cards=deck(c)) for n, c in zip(names, commanders, strict=True)], shuffle=False)
    return GameSession(state, cards=cards)


def creature(s, pid, name, pt="2/2", text=""):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Creature — Test",
                                                       "power": p, "toughness": t, "text": text})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def automate(s):
    turn_on(s)  # existing creatures aren't summoning sick
    act(s, "p1", type="pass_priority")  # → Alice's main 1
    act(s, "p1", type="pass_priority")  # → combat: Alice declares attackers


def attack(s, *pairs):
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in pairs])


def block(s, pid, *pairs):
    act(s, pid, type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id} for b, a in pairs])


def decision(s):
    return s.state.rules.decision


def test_unblocked_commander_deals_combat_and_commander_damage(cards):
    s = table(cards)
    krenko = find(s.state, "Krenko, Mob Boss", "p1")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    automate(s)
    d = decision(s)
    assert d.kind == "declare_attackers" and d.player == "p1"
    assert {o.id for o in d.options} == {f"a:{krenko.id}", "t:p2"}
    view = s.view("p1")["rules"]["decision"]
    assert view["options"] and "options" not in s.view("p2")["rules"]["decision"]
    attack(s, (krenko, "p2"))  # Bob has no creatures: straight to damage
    st = s.state
    assert st.players["p2"].life == 37 and st.players["p2"].commander_damage[krenko.commander_key] == 3
    assert st.cards[krenko.id].tapped and st.turn.phase == "main2"
    assert st.cards[krenko.id].attacking is None  # combat is over: markers cleared
    assert "Combat damage" in json.dumps(s.view("p2")["log"])


def test_blocks_trade_and_first_strike_wins(cards):
    s = table(cards)
    bear = creature(s, "p1", "Bear")
    knight = creature(s, "p1", "Knight", text="First strike")
    wall = creature(s, "p2", "Wolf")
    ox = creature(s, "p2", "Ox")
    automate(s)
    attack(s, (bear, "p2"), (knight, "p2"))
    assert decision(s).kind == "declare_blockers" and decision(s).player == "p2"
    block(s, "p2", (wall, bear), (ox, knight))
    st = s.state
    # Bear and Wolf trade; Knight kills Ox with first strike and takes nothing back
    assert bear.id not in st.cards and wall.id not in st.cards and ox.id not in st.cards
    assert st.cards[knight.id].zone == "p1:battlefield" and st.cards[knight.id].damage == 0
    assert st.players["p2"].life == 40
    assert s.history.rebuild().model_dump(mode="json") == st.model_dump(mode="json")  # replays exactly


def test_trample_deathtouch_and_lifelink(cards):
    s = table(cards)
    wurm = creature(s, "p1", "Wurm", "5/5", "Trample")
    viper = creature(s, "p1", "Viper", "3/3", "Deathtouch, trample, lifelink")
    b1 = creature(s, "p2", "Guard", "2/2")
    b2 = creature(s, "p2", "Giant", "4/4")
    automate(s)
    attack(s, (wurm, "p2"), (viper, "p2"))
    block(s, "p2", (b1, wurm), (b2, viper))
    for amounts in ([2, 3], [1, 2]):  # (wave 14A: a trampler with excess damage divides it, 702.19b)
        act(s, "p1", type="choose", decision_id=decision(s).id, amounts=amounts)
    st = s.state
    # Wurm: 2 to the Guard, 3 trample over. Viper: 1 deathtouch damage is lethal, 2 over; lifelink 3.
    assert st.players["p2"].life == 40 - 3 - 2
    assert st.players["p1"].life == 43
    assert b1.id not in st.cards and b2.id not in st.cards  # lethal and deathtouch
    assert viper.id not in st.cards  # the Giant dealt 4 back to the 3/3 Viper
    assert st.cards[wurm.id].zone == "p1:battlefield" and st.cards[wurm.id].damage == 2



def test_a_huge_trampler_divides_its_damage(cards):
    # -- playtest (nov 18) -- a Mossborn Hydra at 262144 power: its damage assignment was refused (amounts were capped at 10000)
    s = table(cards)
    hydra = creature(s, "p1", "Hydra", "262144/262144", "Trample")
    guard = creature(s, "p2", "Guard", "2/2")
    automate(s)
    attack(s, (hydra, "p2"))
    block(s, "p2", (guard, hydra))
    act(s, "p1", type="choose", decision_id=decision(s).id, amounts=[2, 262142])
    assert s.state.players["p2"].life == 40 - 262142
    assert guard.id not in s.state.cards

def test_evasion_flying_reach_and_menace(cards):
    s = table(cards)
    bird = creature(s, "p1", "Bird", "1/1", "Flying")
    brute = creature(s, "p1", "Brute", "3/3", "Menace")
    cat = creature(s, "p2", "Cat", "2/2")
    spider = creature(s, "p2", "Spider", "1/3", "Reach")
    automate(s)
    attack(s, (bird, "p2"), (brute, "p2"))
    with pytest.raises(ActionError, match="flying"):
        block(s, "p2", (cat, bird))
    with pytest.raises(ActionError, match="menace"):
        block(s, "p2", (cat, brute))
    with pytest.raises(ActionError, match="menace"):
        block(s, "p2", (spider, bird), (cat, brute))  # the Spider may block the Bird, but menace needs two


def test_evasion_legal_blocks(cards):
    s = table(cards)
    bird = creature(s, "p1", "Bird", "1/1", "Flying")
    brute = creature(s, "p1", "Brute", "3/3", "Menace")
    cat = creature(s, "p2", "Cat", "2/2")
    dog = creature(s, "p2", "Dog", "2/2")
    spider = creature(s, "p2", "Spider", "1/3", "Reach")
    automate(s)
    attack(s, (bird, "p2"), (brute, "p2"))
    block(s, "p2", (spider, bird), (cat, brute), (dog, brute))
    act(s, "p1", type="choose", decision_id=decision(s).id, amounts=[2, 1])  # (wave 14A: 510.1c)
    st = s.state
    assert bird.id not in st.cards and st.cards[spider.id].damage == 1  # 1/3 reach kills the 1/1 flyer
    assert brute.id not in st.cards  # 2 + 2 damage on a 3/3
    assert st.players["p2"].life == 40


def test_summoning_sickness_haste_defender_and_vigilance(cards):
    s = table(cards)
    old = creature(s, "p1", "Veteran", "2/2", "Vigilance")
    creature(s, "p1", "Wall", "0/4", "Defender")
    turn_on(s)
    new = creature(s, "p1", "Recruit")  # arrived this turn
    runner = creature(s, "p1", "Runner", "1/1", "Haste")
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="pass_priority")
    eligible = {o.id[2:] for o in decision(s).options if o.id.startswith("a:")}
    assert eligible == {old.id, runner.id} and new.id not in eligible
    attack(s, (old, "p2"), (runner, "p2"))
    assert not s.state.cards[old.id].tapped and s.state.cards[runner.id].tapped
    assert s.state.players["p2"].life == 37


def test_double_strike_and_planeswalkers(cards):
    s = table(cards)
    duelist = creature(s, "p1", "Duelist", "2/2", "Double strike")
    grunt = creature(s, "p1", "Grunt", "2/2")
    act(s, "p2", type="create_token", player="p2", token={"name": "Walker", "type_line": "Token Legendary Planeswalker — Test"})
    walker = find(s.state, "Walker", "p2")
    act(s, "p2", type="counter", card_ids=[walker.id], kind="loyalty", delta=3)
    automate(s)
    assert f"t:{walker.id}" in {o.id for o in decision(s).options}
    attack(s, (duelist, "p2"), (grunt, walker.id))
    st = s.state
    assert st.players["p2"].life == 36  # 2 first-strike + 2 regular
    assert st.cards[walker.id].counters["loyalty"] == 1


def test_no_attack_skips_combat_and_multiplayer_blockers_in_turn_order(cards):
    s = table(cards, players=3)
    a1 = creature(s, "p1", "Axe")
    a2 = creature(s, "p1", "Bow")
    b = creature(s, "p2", "Bob's Guard")
    c = creature(s, "p3", "Carol's Guard")
    automate(s)
    attack(s, (a1, "p2"), (a2, "p3"))
    assert decision(s).player == "p2"
    block(s, "p2")  # Bob doesn't block
    assert decision(s).player == "p3"
    block(s, "p3", (c, a2))
    st = s.state
    assert st.players["p2"].life == 38 and a2.id not in st.cards and c.id not in st.cards
    assert b.id in st.cards
    # next turn: Bob has a creature but doesn't attack → combat is skipped
    act(s, "p1", type="pass_priority")  # → Bob's turn, main 1
    act(s, "p2", type="pass_priority")  # → Bob's combat
    assert decision(s).kind == "declare_attackers" and decision(s).player == "p2"
    act(s, "p2", type="declare_attackers", attackers=[])
    assert s.state.turn.phase == "main2" and "doesn't attack" in json.dumps(s.view("p1")["log"])


# -- evasion keywords (702.14 landwalk, 702.28 shadow, 702.31 horsemanship, 702.36 fear,
#    702.13 intimidate, 702.120 skulk) -----------------------------------------------------------
def _evasion_table(cards, text, blocker_text="", blocker_pt="2/2", blocker_colors=(), attacker_colors=("B",)):
    s = table(cards)
    act(s, "p1", type="create_token", player="p1", token={"name": "Sneak", "type_line": "Token Creature — Test", "power": "2",
                                                         "toughness": "2", "text": text, "colors": list(attacker_colors)})
    act(s, "p2", type="create_token", player="p2", token={"name": "Guard", "type_line": "Token Creature — Test",
                                                         "power": blocker_pt.split("/")[0], "toughness": blocker_pt.split("/")[1],
                                                         "text": blocker_text, "colors": list(blocker_colors)})
    sneak = next(c for c in s.state.cards.values() if c.name == "Sneak")
    guard = next(c for c in s.state.cards.values() if c.name == "Guard")
    return s, sneak, guard


def _blocks(s, sneak, guard):
    automate(s)
    attack(s, (sneak, "p2"))
    d = decision(s)
    assert d.kind == "declare_blockers" and d.player == "p2"
    try:
        block(s, "p2", (guard, sneak))
    except ActionError:
        return False
    return True


def test_forestwalk_while_the_defender_controls_a_forest(cards):
    s, sneak, guard = _evasion_table(cards, "Forestwalk")
    forest = next(c for c in s.state.cards.values() if c.owner == "p2" and c.name == "Forest")
    act(s, "p2", type="move", card_ids=[forest.id], to={"zone": "battlefield"})
    assert not _blocks(s, sneak, guard)


def test_forestwalk_without_a_forest_can_be_blocked(cards):
    s, sneak, guard = _evasion_table(cards, "Forestwalk")
    assert _blocks(s, sneak, guard)


@pytest.mark.parametrize(("text", "blocker_text", "blocker_colors", "blocker_pt", "can_block"), [
    ("Shadow", "", (), "2/2", False),
    ("Shadow", "Shadow", (), "2/2", True),
    ("", "Shadow", (), "2/2", False),  # shadow creatures block only shadow creatures
    ("Horsemanship", "", (), "2/2", False),
    ("Horsemanship", "Horsemanship", (), "2/2", True),
    ("Fear", "", ("G",), "2/2", False),
    ("Fear", "", ("B",), "2/2", True),
    ("Intimidate", "", ("G",), "2/2", False),
    ("Intimidate", "", ("B",), "2/2", True),  # shares a color
    ("Skulk", "", (), "3/3", False),
    ("Skulk", "", (), "2/2", True),
])
def test_evasion(cards, text, blocker_text, blocker_colors, blocker_pt, can_block):
    s, sneak, guard = _evasion_table(cards, text, blocker_text, blocker_pt, blocker_colors)
    assert _blocks(s, sneak, guard) is can_block


@pytest.mark.parametrize(("attacker_text", "blocker_text", "can_block"), [
    ("", "This creature can't block.", False),
    ("", "This creature can't attack or block.", False),
    ("This creature can't be blocked.", "", False),
    ("", "This creature can block only creatures with flying.", False),
    ("Flying", "Reach\nThis creature can block only creatures with flying.", True),
])
def test_block_restrictions(cards, attacker_text, blocker_text, can_block):
    s, sneak, guard = _evasion_table(cards, attacker_text, blocker_text)
    assert _blocks(s, sneak, guard) is can_block


def test_attacks_each_combat_if_able(cards):
    s, sneak, _ = _evasion_table(cards, "This creature attacks each combat if able.")
    automate(s)
    with pytest.raises(ActionError, match="attacks each combat if able"):
        act(s, "p1", type="declare_attackers", attackers=[])
    attack(s, (sneak, "p2"))


def _end_turn_in_main1(s):
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → Alice's main 1
    assert s.state.turn.phase == "main1"
    act(s, "p1", type="pass_priority", until="next_turn")  # END TURN


def test_end_turn_skips_your_own_attack(cards):
    s = table(cards)
    creature(s, "p1", "Axe")
    _end_turn_in_main1(s)
    assert s.state.turn.number == 2 and (decision(s) is None or decision(s).player != "p1")
    assert "Alice doesn't attack" in json.dumps(s.view("p2")["log"])


def test_end_turn_still_asks_a_creature_that_must_attack(cards):
    s, sneak, _ = _evasion_table(cards, "This creature attacks each combat if able.")
    _end_turn_in_main1(s)
    assert decision(s).kind == "declare_attackers" and decision(s).player == "p1"  # 508.1d: Alice is asked
    attack(s, (sneak, "p2"))


def test_cant_attack(cards):
    s, sneak, _ = _evasion_table(cards, "This creature can't attack.")
    automate(s)
    with pytest.raises(ActionError):
        attack(s, (sneak, "p2"))
