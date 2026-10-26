"""Wave 110D: Firebender Ascension, real Oracle text.

* 603.2, 603.2d: a creature attacking causes its own triggered ability to trigger: quest counter; at four or more, the ability may be copied (707.10c new targets).
* A creature whose trigger another creature's attack caused does not count ("that creature").
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, check, life, put
from tests.wave110d_kit import card_db as _kit_db  # noqa: F401
from tests.wave110d_kit import next_turn, now, to_phase

EXTRA = [
    real("Firebender Ascension", "{1}{R}", 2, "Enchantment",
         "When this enchantment enters, create a 2/2 red Soldier creature token with firebending 1.\n"
         "Whenever a creature you control attacking causes a triggered ability of that creature to trigger, put a quest counter on this enchantment. "
         "Then if it has four or more quest counters on it, you may copy that ability. You may choose new targets for the copy.", None, "R"),
    real("Brutal Hordechief", "{3}{B}", 4, "Creature — Human Warrior",
         "Whenever a creature you control attacks, defending player loses 1 life and you gain 1 life.\n"
         "{3}{R/W}{R/W}: Creatures your opponents control block this turn if able, and you choose how those creatures block.", ("3", "3"), "B"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Firebender Ascension")).level == "FULL"


def attack(cards, counters, attackers=("Brutal Hordechief",), copy=True):
    s = build(cards, ["Firebender Ascension", "Brutal Hordechief", "Grizzly Bears"], ["Grizzly Bears"])
    asc = put(s, "Firebender Ascension")
    mine = {n: put(s, n) for n in dict.fromkeys(attackers)}
    next_turn(s)
    next_turn(s)
    if counters:
        act(s, "p1", type="set_counter", card_id=asc.id, kind="quest", value=counters)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": mine[n].id, "target": "p2"} for n in attackers])
    d = s.state.rules.decision
    for _ in range(12):
        d = s.state.rules.decision
        if d is None and s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        elif d is not None and d.kind != "declare_blockers":
            opts = [o.id for o in d.options]
            yes = next((o for o in opts if o in ("yes", "1")), opts[0])
            act(s, d.player, type="choose", decision_id=d.id, option_ids=opts if d.min_choices > 1 else [yes if copy else opts[-1]])
        else:
            break
    return s, asc


def test_fourth_counter_copies_the_attack_trigger(cards):
    s, asc = attack(cards, 3)
    assert now(s, asc).counters["quest"] == 4
    assert life(s, "p2") == 35  # 40 - 3 combat damage - 2 (the trigger and its copy)
    check(s)


def test_declining_the_copy(cards):
    s, asc = attack(cards, 3, copy=False)
    assert now(s, asc).counters["quest"] == 4 and life(s, "p2") == 36
    check(s)


def test_below_four_no_copy_and_only_its_own_triggers_count(cards):
    s, asc = attack(cards, 0, ("Brutal Hordechief", "Grizzly Bears"))
    assert now(s, asc).counters["quest"] == 1  # the Hordechief's own trigger (not the Bears', which have none)
    assert life(s, "p2") == 33  # 40 - 5 combat damage - 2 (two attackers, two triggers of the Hordechief)
    check(s)
