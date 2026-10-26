"""Wave 110D: Huntmaster of the Fells // Ravager of the Fells, real Oracle text (tests/fixtures/wave110d_cards.json), three players.

* 701.28, 603.2: transforming into Ravager of the Fells triggers; 115.1: two target groups, "target opponent or planeswalker", then "up to one target
  creature that player or that planeswalker's controller controls" (the creature must belong to the player chosen first; 115.7d).
* 120.3: 2 damage to each.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.test_rules_wave110d_three import three
from tests.wave9c_kit import put
from tests.wave110d_kit import card_db, check, full, life, now, put_new, settle  # noqa: F401

NAME = "Huntmaster of the Fells // Ravager of the Fells"


def test_full():
    assert full(NAME)


def test_ravager_hits_the_opponent_and_a_creature_of_that_opponent(cards):
    s = three(cards, [NAME], ["Grizzly Bears"], ["Llanowar Elves"])
    put(s, NAME)
    bears, elves = put_new(s, "Grizzly Bears", "p2"), put_new(s, "Llanowar Elves", "p3")
    for _ in range(40):  # to the upkeep trigger: no spells were cast last turn, so it transforms, then the Ravager trigger asks for targets
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d.player == "p1" and {o.id for o in d.options} == {"p2", "p3"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    d = s.state.rules.decision
    assert {o.id for o in d.options} >= {elves.id} and bears.id not in {o.id for o in d.options}  # 115.7d: only creatures of the player chosen
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[elves.id])
    settle(s)
    assert life(s, "p3") == 38 and life(s, "p2") == 40 and now(s, elves).zone == "p3:graveyard" and now(s, bears).zone == "p2:battlefield"
    check(s)


def test_ravager_planeswalker_target_names_its_controller(cards):
    s = three(cards, [NAME], ["Grizzly Bears", "Gideon Jura"], ["Llanowar Elves"])
    put(s, NAME)
    bears, elves, gideon = put_new(s, "Grizzly Bears", "p2"), put_new(s, "Llanowar Elves", "p3"), put_new(s, "Gideon Jura", "p2")
    act(s, "p1", type="counter", card_ids=[gideon.id], kind="loyalty", delta=6)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[gideon.id])
    d = s.state.rules.decision
    assert bears.id in {o.id for o in d.options} and elves.id not in {o.id for o in d.options}  # (the planeswalker's controller, 115.7d)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])
    settle(s)
    assert now(s, bears).zone == "p2:graveyard" and now(s, gideon).counters.get("loyalty") == 4 and life(s, "p2") == 40
    check(s)
