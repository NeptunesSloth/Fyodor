"""Wave 11D: "Each player chooses N <things> they control, then sacrifices the rest" and "Destroy the rest", researched against
CR 2026-09-25: every player chooses in APNAP order (101.4), each knowing the earlier choices (101.4b), and only after the last choice
is the rest sacrificed (701.21a) or destroyed (701.8) at once. A player with no more than N has no choice to make. "Up to" may
choose fewer. Every scenario replays the history and reloads a save mid-decision."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_effects import build, replay_matches, token
from tests.test_rules_player_choices import activate, assert_observer_sees_only_who, choose, reloaded
from tests.test_rules_scripts import ch

DIVINE_RECKONING = "Each player chooses a creature they control. Destroy the rest."
PURIFICATION = "Each player chooses three permanents they control, then sacrifices the rest."
ELEGY = ("Each player chooses up to two creatures they control, then sacrifices the rest. Then you create a tapped Treasure token "
         "for each creature your opponents control.")
ANNIHILATION = "Each player chooses six lands they control, then sacrifices the rest. ~ deals 6 damage to each creature."


def alive(s, *tokens):
    return [t.id in s.state.cards and s.state.cards[t.id].zone.endswith(":battlefield") for t in tokens]


def test_divine_reckoning_destroys_every_creature_that_was_not_chosen(cards):
    s = build(cards)
    a1, a2, b1, b2 = (token(s, p, n) for p, n in (("p1", "Alpha"), ("p1", "Beta"), ("p2", "Gamma"), ("p2", "Delta")))
    src = token(s, "p1", "Reckoner", "1/1", text=f"{{1}}: {DIVINE_RECKONING}")
    activate(s, src)
    d = s.state.rules.decision
    assert d.player == "p1" and {o.id for o in d.options} == {a1.id, a2.id, src.id}  # Alice first (APNAP, 101.4)
    assert_observer_sees_only_who(s, "p2", "Alice")
    choose(s, [a2.id])
    d = s.state.rules.decision
    assert d.player == "p2" and {o.id for o in d.options} == {b1.id, b2.id} and "Beta" in d.prompt  # 101.4b
    assert alive(s, a1, a2, b1, b2) == [True] * 4  # nothing is destroyed until everyone has chosen
    again = reloaded(s)
    choose(s, [b1.id])
    assert alive(s, a1, a2, b1, b2, src) == [False, True, True, False, False]
    assert s.state.rules.decision is None
    replay_matches(s)
    act(again, "p2", type="choose", decision_id=again.state.rules.decision.id, option_ids=[b2.id])
    assert alive(again, a2, b2, b1) == [True, True, False]


def test_a_player_with_nothing_but_the_chosen_has_no_choice(cards):
    s = build(cards)
    keep = token(s, "p2", "Solo")
    src = token(s, "p1", "Reckoner", "1/1", text=f"{{1}}: {DIVINE_RECKONING}")
    activate(s, src)
    assert s.state.rules.decision is None  # each has just one creature: it is chosen, nobody has a choice to make
    assert alive(s, keep, src) == [True, True]
    replay_matches(s)


def test_razias_purification_keeps_three_permanents_each(cards):
    s = build(cards)
    mine = [token(s, "p1", f"Mine{i}") for i in range(3)]
    theirs = [token(s, "p2", f"Their{i}") for i in range(5)]
    src = token(s, "p1", "Purifier", "1/1", text=f"{{1}}: {PURIFICATION}")
    activate(s, src)
    d = s.state.rules.decision
    assert d.player == "p1" and (d.min_choices, d.max_choices) == (3, 3)
    choose(s, [mine[0].id, mine[1].id, src.id])
    choose(s, [t.id for t in theirs[1:4]])
    assert alive(s, *mine, src) == [True, True, False, True]
    assert alive(s, *theirs) == [False, True, True, True, False]
    replay_matches(s)


def test_covetous_elegy_up_to_two_and_then_the_treasures(cards):
    s = build(cards)
    mine = [token(s, "p1", f"Mine{i}") for i in range(3)]
    theirs = [token(s, "p2", f"Their{i}") for i in range(3)]
    src = token(s, "p1", "Elegist", "1/1", text=f"{{1}}: {ELEGY}")
    activate(s, src)
    d = s.state.rules.decision
    assert (d.min_choices, d.max_choices) == (0, 2)  # "up to two"
    choose(s, [mine[0].id])
    d = s.state.rules.decision
    assert d.player == "p2" and (d.min_choices, d.max_choices) == (0, 2)
    choose(s, [theirs[0].id, theirs[2].id])
    assert alive(s, *mine, src) == [True, False, False, False]
    assert alive(s, *theirs) == [True, False, True]
    treasures = [c for c in s.state.cards.values() if c.name == "Treasure" and c.owner == "p1"]
    assert len(treasures) == 2 and all(t.tapped for t in treasures)  # one for each creature Bob still controls
    replay_matches(s)


def test_planetary_annihilation_keeps_six_lands_then_deals_damage(cards):
    s = build(cards)
    lands = []
    for _ in range(8):
        card = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone.endswith(":library")
                    and c.id not in [x.id for x in lands])
        act(s, "p1", type="move", card_ids=[card.id], to={"player": "p1", "zone": "battlefield"})
        lands.append(card)
    guard = token(s, "p2", "Guard", "2/2")
    src = token(s, "p1", "Annihilator", "1/1", text=f"{{1}}: {ANNIHILATION}")
    activate(s, src)
    d = s.state.rules.decision
    assert d.player == "p1" and (d.min_choices, d.max_choices) == (6, 6) and len(d.options) == 8
    choose(s, [c.id for c in lands[:6]])
    assert [s.state.cards[c.id].zone for c in lands] == ["p1:battlefield"] * 6 + ["p1:graveyard"] * 2
    assert guard.id not in s.state.cards  # 6 damage to each creature
    replay_matches(s)


@pytest.mark.parametrize(("name", "type_line", "text", "level"), [
    ("Divine Reckoning", "Sorcery", DIVINE_RECKONING, "FULL"),
    ("Razia's Purification", "Sorcery", PURIFICATION, "FULL"),
    ("Single Combat", "Sorcery", "Each player chooses a creature or planeswalker they control, then sacrifices the rest. Players can't "
                                  "cast creature or planeswalker spells until the end of your next turn.", "FULL"),  # (wave 32C)
    ("Duneblast", "Sorcery", "Choose up to one creature. Destroy the rest.", "FULL"),  # (automated and played in test_rules_nontarget_creature_choices.py)
])
def test_coverage_levels(name, type_line, text, level):
    assert coverage.of_characteristics(ch(name, type_line, text)).level == level
