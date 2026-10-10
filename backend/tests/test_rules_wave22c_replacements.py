"""Wave 22C: counter putters (Vorinclex, Lae'zel, Pir), zone-change "instead", shields (CR 614, 615, 616.1, 122.6a).

Real Oracle text (card database snapshot 2026-10-03) as custom permanents. Every scenario checks the final table and
that replaying the history reproduces it; choices are tried in both orders (a wrong order is silent).
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.test_rules_attachments import build, token
from tests.test_rules_combat import attack, automate, creature, table
from tests.test_rules_effects import replay_matches
from tests.test_rules_replacements2 import HARDENED_SCALES, activate, answer, decision, permanent, reload
from tests.test_rules_suspend import until

VORINCLEX = ("Trample, haste\nIf you would put one or more counters on a permanent or player, put twice that many of each of "
             "those kinds of counters on that permanent or player instead.\nIf an opponent would put one or more counters "
             "on a permanent or player, they put half that many of each of those kinds of counters on that permanent or "
             "player instead, rounded down.")
LAEZEL = ("If you would put one or more counters on a creature or planeswalker you control or on yourself, put that many "
          "plus one of each of those kinds of counters on that permanent or player instead.")
PIR = ("If one or more counters would be put on a permanent your team controls, that many plus one of each of those kinds "
       "of counters are put on that permanent instead.")
FEED = "{1}: Put a +1/+1 counter on target creature."


def feeder(s, pid, text=FEED):
    return token(s, pid, f"Feeder {pid}", text=text)


def test_vorinclex_and_hardened_scales_ask_the_affected_player_and_both_orders_differ(cards):
    s = build(cards)
    permanent(s, "p1", "Vorinclex", "Creature", VORINCLEX)
    permanent(s, "p1", "Hardened Scales", "Enchantment", HARDENED_SCALES)
    bear = token(s, "p1", "Bear")
    activate(s, feeder(s, "p1"), targets=[bear.id])
    d = decision(s)
    assert d is not None and d.player == "p1" and d.kind == "confirm" and "616.1" in d.prompt
    labels = {o.id: o.label for o in d.options}
    assert sorted(labels) == ["no", "yes"]
    answers = {k: v for k, v in labels.items()}
    # Hardened Scales first: (1 + 1) x 2 = 4; Vorinclex first: 1 x 2 + 1 = 3
    first_scales = next(k for k, v in answers.items() if v.startswith("Hardened Scales"))
    other = "no" if first_scales == "yes" else "yes"
    assert "4 +1/+1" in answers[first_scales] and "3 +1/+1" in answers[other], answers
    assert not s.state.cards[bear.id].counters
    s2 = reload(s, cards)
    act(s2, "p1", type="choose", decision_id=d.id, option_ids=[other])
    assert s2.state.cards[bear.id].counters == {"+1/+1": 3}
    answer(s, first_scales)
    assert s.state.cards[bear.id].counters == {"+1/+1": 4} and decision(s) is None
    replay_matches(s)


def test_vorinclex_doubles_what_you_put_on_any_permanent(cards):
    s = build(cards)
    permanent(s, "p1", "Vorinclex", "Creature", VORINCLEX)
    mine, theirs = token(s, "p1", "Bear"), token(s, "p2", "Wolf")
    activate(s, feeder(s, "p1"), targets=[mine.id])
    activate(s, feeder(s, "p1"), targets=[theirs.id])  # you put them on an opponent's creature: doubled too
    assert s.state.cards[mine.id].counters == {"+1/+1": 2} and s.state.cards[theirs.id].counters == {"+1/+1": 2}
    replay_matches(s)


def test_vorinclex_halves_three_to_one_for_an_opponent_and_energy_is_put_by_the_player(cards):
    s = build(cards)
    permanent(s, "p2", "Vorinclex", "Creature", VORINCLEX)
    bear = token(s, "p2", "Bear")
    three = token(s, "p1", "Triple", text="{1}: Put three +1/+1 counters on target creature.")
    battery = token(s, "p1", "Battery", text="{1}: You get {E}{E}{E}.")
    activate(s, three, targets=[bear.id])
    assert s.state.cards[bear.id].counters == {"+1/+1": 1}  # p1 is Vorinclex's opponent: half of 3, rounded down
    activate(s, feeder(s, "p1"), targets=[bear.id])
    assert s.state.cards[bear.id].counters == {"+1/+1": 1}  # half of 1: none
    activate(s, battery)
    assert s.state.players["p1"].resources.get("energy") == 1
    replay_matches(s)


def test_vorinclex_doubles_energy_you_get(cards):
    s = build(cards)
    permanent(s, "p1", "Vorinclex", "Creature", VORINCLEX)
    activate(s, token(s, "p1", "Battery", text="{1}: You get {E}{E}."))
    assert s.state.players["p1"].resources.get("energy") == 4
    replay_matches(s)


def test_laezel_adds_one_for_your_creatures_and_yourself_only(cards):
    s = build(cards)
    permanent(s, "p1", "Laezel", "Creature", LAEZEL)
    mine, theirs = token(s, "p1", "Bear"), token(s, "p2", "Wolf")
    activate(s, feeder(s, "p1"), targets=[mine.id])
    activate(s, feeder(s, "p1"), targets=[theirs.id])
    assert s.state.cards[mine.id].counters == {"+1/+1": 2} and s.state.cards[theirs.id].counters == {"+1/+1": 1}
    activate(s, token(s, "p1", "Battery", text="{1}: You get {E}{E}."))
    assert s.state.players["p1"].resources.get("energy") == 3
    replay_matches(s)


def test_pir_gives_one_more_counter_on_your_permanents(cards):
    s = build(cards)
    permanent(s, "p1", "Pir", "Creature", PIR)
    mine, theirs = token(s, "p1", "Bear"), token(s, "p2", "Wolf")
    activate(s, feeder(s, "p1"), targets=[mine.id])
    activate(s, feeder(s, "p1"), targets=[theirs.id])
    assert s.state.cards[mine.id].counters == {"+1/+1": 2} and s.state.cards[theirs.id].counters == {"+1/+1": 1}
    replay_matches(s)


def test_vorinclex_counts_counters_you_give_another_player_as_put(cards):
    """Review 22C: "gets" / "gives" counters are put (122.6, 701.34a), by the effect's controller (608.2c)."""
    s = build(cards)
    permanent(s, "p1", "Vorinclex", "Creature", VORINCLEX)
    activate(s, token(s, "p1", "Poisoner", text="{1}: Target opponent gets two poison counters."), targets=["p2"])
    assert s.state.players["p2"].resources.get("poison") == 4
    assert reload(s, cards).state.players["p2"].resources.get("poison") == 4
    replay_matches(s)
    s2 = build(cards)
    permanent(s2, "p2", "Vorinclex", "Creature", VORINCLEX)
    activate(s2, token(s2, "p1", "Poisoner", text="{1}: Target opponent gets three poison counters."), targets=["p2"])
    assert s2.state.players["p2"].resources.get("poison") == 1  # p1 is Vorinclex's opponent: half of 3, rounded down
    replay_matches(s2)


def test_vorinclex_doubles_infect_poison_its_controller_gives(cards):
    """120.3b: the infect source's controller gives (puts) the poison counters, so Vorinclex doubles them."""
    s = table(cards)
    permanent(s, "p1", "Vorinclex", "Creature", VORINCLEX)
    elf = creature(s, "p1", "Elf", "2/2", "Infect")
    automate(s)
    attack(s, (elf, "p2"))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.players["p2"].resources.get("poison") == 4
    replay_matches(s)
    assert reload(s, cards).state.players["p2"].resources.get("poison") == 4
