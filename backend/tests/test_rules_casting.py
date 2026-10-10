"""Milestone 15a: mana abilities, paying costs and casting spells through the rules engine."""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, enable, find, zone


def build(cards, p1: list[tuple[int, str]], p2: list[tuple[int, str]], *, c1="Krenko, Mob Boss", c2="Atraxa, Praetors' Voice"):
    def deck(commander, entries):
        cmd = cards.resolve(commander)
        out = [DeckCard("commander", 1, cmd["name"], cmd["id"])]
        for qty, name in entries:
            card = cards.resolve(name)
            out.append(DeckCard("main", qty, card["name"], card["id"]))
        return out

    state = new_game([PlayerSetup("Alice", cards=deck(c1, p1)), PlayerSetup("Bob", cards=deck(c2, p2))], shuffle=False)
    enable(state)
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    return s


def put(s, pid, name, where):
    card = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith(where))
    act(s, pid, type="move", card_ids=[card.id], to={"zone": where})
    return s.state.cards[card.id]


def rules(s):
    return s.state.rules


def log_text(s, viewer="p2"):
    return json.dumps(s.view(viewer)["log"], ensure_ascii=False)


def test_cast_a_creature_paying_with_a_land(cards):
    s = build(cards, [(1, "Llanowar Elves"), (3, "Forest")], [(5, "Island")])
    put(s, "p1", "Forest", "battlefield")
    elves = put(s, "p1", "Llanowar Elves", "hand")
    seq = s.state.seq
    act(s, "p1", type="cast_spell", card_id=elves.id)
    st = s.state
    assert st.cards[elves.id].zone == "p1:battlefield"  # nobody could respond: it resolved right away
    assert find(st, "Forest", "p1").tapped
    assert st.seq == seq + 1  # cast, payment, passes and resolution: one history entry
    log = log_text(s)
    assert "cast" in log and "paid {G} for Llanowar Elves" in log
    assert rules(s).priority == "p1" and st.turn.phase == "main1"


def test_can_not_cast_what_you_can_not_pay_and_nothing_happens(cards):
    s = build(cards, [(1, "Llanowar Elves"), (3, "Mountain")], [(5, "Island")])
    put(s, "p1", "Mountain", "battlefield")
    elves = put(s, "p1", "Llanowar Elves", "hand")
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError, match=r"Not enough mana to pay \{G\}"):
        act(s, "p1", type="cast_spell", card_id=elves.id)
    assert s.state.model_dump(mode="json") == before


def test_sorcery_speed_timing(cards):
    s = build(cards, [(1, "Llanowar Elves"), (3, "Forest")], [(5, "Island")])
    put(s, "p1", "Forest", "battlefield")
    elves = put(s, "p1", "Llanowar Elves", "hand")
    act(s, "p1", type="phase", to="end")  # manual jump to the end step
    with pytest.raises(ActionError, match="main phase"):
        act(s, "p1", type="cast_spell", card_id=elves.id)


def test_counterspell_response_counters_the_spell(cards):
    s = build(cards, [(1, "Llanowar Elves"), (3, "Forest")], [(1, "Counterspell"), (4, "Island")])
    put(s, "p1", "Forest", "battlefield")
    elves = put(s, "p1", "Llanowar Elves", "hand")
    put(s, "p2", "Island", "battlefield")
    put(s, "p2", "Island", "battlefield")
    counter = put(s, "p2", "Counterspell", "hand")
    act(s, "p1", type="cast_spell", card_id=elves.id)
    # Bob can respond (Counterspell, two Islands), so he gets priority
    assert rules(s).priority == "p2" and s.state.zones["stack"] == [elves.id]
    assert s.view("p2")["rules"]["hints"]["castable"] == [counter.id]
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[elves.id])
    # Alice can't respond: passed for her; Counterspell resolves and counters the Elves by itself
    assert rules(s).decision is None and not s.state.zones.get("stack")
    assert s.state.cards[elves.id].zone == "p1:graveyard" and s.state.cards[counter.id].zone == "p2:graveyard"
    assert rules(s).priority == "p1"


def test_summoning_sick_creatures_cannot_tap_for_mana(cards):
    s = build(cards, [(1, "Llanowar Elves"), (3, "Forest")], [(5, "Island")])
    put(s, "p1", "Forest", "battlefield")
    elves = put(s, "p1", "Llanowar Elves", "hand")
    act(s, "p1", type="cast_spell", card_id=elves.id)
    with pytest.raises(ActionError, match="summoning sickness"):
        act(s, "p1", type="activate_ability", card_id=elves.id, ability=0)
    act(s, "p1", type="pass_priority")  # → main 2
    act(s, "p1", type="pass_priority")  # → Bob's turn
    act(s, "p2", type="pass_priority")
    act(s, "p2", type="pass_priority")  # → Alice's turn 3
    assert (s.state.turn.number, s.state.turn.active_player) == (3, "p1")
    act(s, "p1", type="activate_ability", card_id=elves.id, ability=0)
    assert s.state.players["p1"].mana == {"G": 1}


def test_sol_ring_commander_tax_and_mana_pools_empty(cards):
    s = build(cards, [(1, "Sol Ring"), (6, "Mountain")], [(5, "Island")])
    for _ in range(3):
        put(s, "p1", "Mountain", "battlefield")
    sol = put(s, "p1", "Sol Ring", "battlefield")
    act(s, "p1", type="activate_ability", card_id=sol.id, ability=0)
    assert s.state.players["p1"].mana == {"C": 2} and s.state.cards[sol.id].tapped
    krenko = find(s.state, "Krenko, Mob Boss", "p1")
    act(s, "p1", type="cast_spell", card_id=krenko.id)  # {2}{R}{R}: {C}{C} from the pool + 2 Mountains
    assert s.state.cards[krenko.id].zone == "p1:battlefield"
    assert s.state.players["p1"].commander_tax[krenko.commander_key] == 2
    assert s.state.players["p1"].mana == {}
    # back to the command zone by hand: now it costs {4}{R}{R} and Alice can't pay
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "command"})
    act(s, "p1", type="tap", card_ids=[c for c in zone(s.state, "p1", "battlefield")], tapped=False)
    with pytest.raises(ActionError, match=r"\{6\}\{R\}\{R\}|Not enough mana to pay \{4\}\{R\}\{R\}"):
        act(s, "p1", type="cast_spell", card_id=krenko.id)
    # mana empties when the step ends
    act(s, "p1", type="activate_ability", card_id=sol.id, ability=0)
    act(s, "p1", type="pass_priority")
    assert s.state.players["p1"].mana == {} and s.state.turn.phase == "main2"


def test_any_color_sources_ask_which_color(cards):
    s = build(cards, [(5, "Mountain")], [(1, "Command Tower"), (4, "Island")])
    tower = put(s, "p2", "Command Tower", "battlefield")
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="pass_priority")  # → Bob's turn, main 1
    act(s, "p2", type="activate_ability", card_id=tower.id, ability=0)
    d = rules(s).decision
    assert d and d.kind == "choose_one" and sorted(o.label for o in d.options) == ["{B}", "{G}", "{U}", "{W}"]
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "{U}")])
    assert s.state.players["p2"].mana == {"U": 1} and rules(s).priority == "p2"
    with pytest.raises(ActionError, match="tapped"):
        act(s, "p2", type="activate_ability", card_id=tower.id, ability=0, mana_choice="G")


def test_hints_list_castable_spells_and_undo_takes_back_a_cast(cards):
    s = build(cards, [(1, "Llanowar Elves"), (1, "Lightning Bolt"), (3, "Forest")], [(5, "Island")])
    put(s, "p1", "Forest", "battlefield")
    elves = put(s, "p1", "Llanowar Elves", "hand")
    bolt = put(s, "p1", "Lightning Bolt", "hand")
    hints = s.view("p1")["rules"]["hints"]
    assert elves.id in hints["castable"] and bolt.id not in hints["castable"]  # no red mana
    act(s, "p1", type="cast_spell", card_id=elves.id)
    s.undo("p1")
    assert s.state.cards[elves.id].zone == "p1:hand" and not find(s.state, "Forest", "p1").tapped
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def test_mana_costs_abilities_and_payment_solver():
    from app.rules.mana import ManaError, Source, parse_cost, parse_mana_ability, solve

    assert parse_cost("{X}{2}{G}{G}").x == 1 and parse_cost("{X}{2}{G}{G}").with_x(3).text() == "{5}{G}{G}"
    assert parse_cost("{2/B}{G/W}{U/P}").text() == "{2/B}{G/W}{U/P}"
    assert parse_mana_ability("{T}: Add {R} or {G}.").options == (("R",), ("G",))
    assert parse_mana_ability("{T}, Sacrifice this token: Add one mana of any color.").sacrifice_self
    assert parse_mana_ability("{1}, {T}: Add {W}{U}.").extra_cost == "{1}"  # filters: paid with other mana
    assert parse_mana_ability("{T}, Tap an untapped creature you control: Add one mana of any color.").chooses  # (wave 3R3: by hand)
    assert parse_mana_ability("{T}: Add {G} for each Elf you control.").count == "control:Elf"  # counted at use
    forest, mountain = Source("f", (("G",),)), Source("m", (("R",),))
    sol = Source("s", (("C", "C"),))
    dual = Source("d", (("R",), ("G",)))
    # the dual land is kept for last: the Forest pays {G}, the dual pays {R}
    pay = solve(parse_cost("{R}{G}"), {}, [dual, forest])
    assert sorted(pay.tapped) == ["d", "f"] and pay.spent == {"R": 1, "G": 1}
    # generic prefers the biggest source (Sol Ring) and the pool comes first
    assert solve(parse_cost("{2}"), {}, [forest, sol]).tapped == ["s"]
    assert solve(parse_cost("{1}{G}"), {"G": 1}, [mountain]).tapped == ["m"]
    # twobrid {2/B} paid with two generic; phyrexian with life when there's no mana for it
    assert solve(parse_cost("{2/B}"), {}, [sol]).tapped == ["s"]
    assert solve(parse_cost("{G/P}"), {}, [mountain], life=10).life == 2
    assert solve(parse_cost("{G/P}"), {}, [mountain], life=2).life == 2  # 119.4 (wave 29C): exactly the life it costs is enough
    with pytest.raises(ManaError):
        solve(parse_cost("{G/P}"), {}, [mountain], life=1)  # not enough life either
    with pytest.raises(ManaError, match=r"\{G\}\{G\}"):
        solve(parse_cost("{G}{G}"), {}, [forest, mountain])
