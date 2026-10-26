"""Wave 110A session 14: real-Oracle scenario tests."""

# ruff: noqa: F403, F405
from __future__ import annotations

from tests.wave110a_kit import *

from app.rules import keyword_actions, scripts  # isort: skip

NAMES = ["Jon Irenicus, Shattered One", "Grothama, All-Devouring"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test(NAMES)


def _jon(cards, give=True):
    s = build(cards, ["Jon Irenicus, Shattered One", "Grizzly Bears"], ["Island"])
    put(s, "Jon Irenicus, Shattered One")
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: s.state.rules.decision is not None or (s.state.turn.phase == "end" and s.state.zones.get("stack")))
    answer(s, "p2", bears.id if give else [])
    return s, bears


def test_jon_gives_a_creature_counters_tap_goad_and_no_sacrifice(cards):  # 701.15a goad with no end, 611.2a no duration = rest of the game, 122.1
    s, bears = _jon(cards)
    c = s.state.cards[bears.id]
    assert (c.controller, c.counters.get("+1/+1"), c.tapped) == ("p2", 2, True)
    assert keyword_actions.goaded_by(ch(s, bears)) == {"p1"}
    assert "cant_be_sacrificed" in scripts.statics(ch(s, bears))
    assert [e.duration for e in s.state.rules.effects if "goaded:p1" in e.imposes] == ["permanent"]  # never expires (not at Jon's controller's next turn)
    check(s)


def test_jon_with_no_creature_chosen_changes_nothing(cards):  # "up to one": zero targets is legal (115.1b)
    s, bears = _jon(cards, give=False)
    assert s.state.cards[bears.id].controller == "p1" and s.state.cards[bears.id].counters.get("+1/+1") is None
    check(s)


def test_grothama_each_player_draws_the_damage_their_sources_dealt(cards):  # 120.3, 101.4: p1 dealt 2, p2 dealt 3, p3 none; Grothama then dies
    from tests.test_rules_wave30i_sneak import pod

    s = pod(cards, ["Grothama, All-Devouring", "Shock", "Murder"], ["Lightning Bolt"], players=3)
    groth = put(s, "Grothama, All-Devouring")
    stops(s)
    hand = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2", "p3")}
    cast(s, "Shock", [groth.id])
    cast(s, "Lightning Bolt", [groth.id], pid="p2")
    answer(s)
    assert s.state.cards[groth.id].zone == "p1:battlefield"  # 5 damage on a 10/8
    cast(s, "Murder", [groth.id])
    answer(s)
    assert s.state.cards[groth.id].zone == "p1:graveyard"
    drawn = {p: len(s.state.zones[f"{p}:hand"]) - hand[p] for p in hand}
    assert drawn == {"p1": 2, "p2": 3, "p3": 0}, drawn
    check(s)


@pytest.mark.parametrize("fight", [True, False])
def test_grothama_gives_other_creatures_an_optional_fight_with_it_when_they_attack(cards, fight):  # 603.2, 701.14: the attacker fights Grothama, which is no target
    from tests.test_rules_conditionals import until
    from tests.test_rules_wave30i_sneak import pod

    s = pod(cards, ["Grothama, All-Devouring", "Grizzly Bears"], players=3)
    groth = put(s, "Grothama, All-Devouring")
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "declare_blockers", "main2"])
    until(s, lambda s: s.state.turn.number >= 3 and s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers"
          and s.state.turn.active_player == "p1")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    answer(s, *([] if fight else ["no"]))
    assert (s.state.cards[bears.id].zone, s.state.cards[groth.id].damage) == (("p1:graveyard", 2) if fight else ("p1:battlefield", 0))
    check(s)


def test_aurora_shifter_pays_energy_becomes_a_copy_and_keeps_both_abilities(cards):  # 707.9a "except it has this ability", 117.12 reflexive, 702: energy
    s = build(cards, ["Aurora Shifter", "Grizzly Bears"], ["Island"])
    shifter = put(s, "Aurora Shifter")
    bears = put(s, "Grizzly Bears")
    next_turn(s)  # (past the first turn's combat, where nothing could be paid yet)
    act(s, "p1", type="set_resource", player="p1", key="energy", value=2)
    goto(s, "begin_combat")
    answer(s, "Pay {E}{E}", bears.id)
    assert ch(s, shifter).name == "Grizzly Bears" and s.state.players["p1"].resources.get("energy", 0) == 0
    texts = [a.text for a in ch(s, shifter).abilities]
    assert any("you may pay {E}{E}" in t for t in texts) and any(t.startswith("Whenever ~ deals combat damage to a player, you get that many") for t in texts)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": shifter.id, "target": "p2"}])
    until(s, lambda s: s.state.turn.phase == "end_combat")
    answer(s)
    assert s.state.players["p1"].resources.get("energy", 0) == 2  # the copy's granted trigger: 2 combat damage
    check(s)


def test_aurora_shifter_declined_payment_changes_nothing(cards):  # "you may pay": no payment, no reflexive trigger
    s = build(cards, ["Aurora Shifter", "Grizzly Bears"], ["Island"])
    shifter = put(s, "Aurora Shifter")
    put(s, "Grizzly Bears")
    next_turn(s)  # (past the first turn's combat, where nothing could be paid yet)
    act(s, "p1", type="set_resource", player="p1", key="energy", value=2)
    goto(s, "begin_combat")
    answer(s, "Don't pay")
    assert ch(s, shifter).name == "Aurora Shifter" and s.state.players["p1"].resources.get("energy", 0) == 2
    check(s)
