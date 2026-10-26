"""Wave 110D: Brutal Hordechief, real Oracle text.

* 509.1c: "block this turn if able" binds every creature the opponents control (no characteristic changes: not locked, 611.2c).
* 509.1a: "you choose how those creatures block": the Hordechief's controller declares the blocks (decider), blind to the defender's secrets.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, check, mana, put
from tests.wave110d_kit import activate, next_turn, to_phase
from tests.wave110d_kit import card_db as _kit_db  # noqa: F401

EXTRA = [real("Brutal Hordechief", "{3}{B}", 4, "Creature — Human Warrior",
              "Whenever a creature you control attacks, defending player loses 1 life and you gain 1 life.\n"
              "{3}{R/W}{R/W}: Creatures your opponents control block this turn if able, and you choose how those creatures block.",
              ("3", "3"), "B")]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Brutal Hordechief")).level == "FULL"


def table(cards, on):
    s = build(cards, ["Brutal Hordechief", "Grizzly Bears"], ["Llanowar Elves", "Grizzly Bears"])
    horde = put(s, "Brutal Hordechief")
    bears = put(s, "Grizzly Bears")
    giant, wall = put(s, "Llanowar Elves", "p2"), put(s, "Grizzly Bears", "p2")
    next_turn(s)
    next_turn(s)
    if on:
        mana(s, "p1", R=2, C=3)
        activate(s, horde, "{3}{R/W}{R/W}")
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    to_phase(s, "declare_blockers")
    return s, bears, giant, wall


def test_controller_declares_and_every_creature_must_block(cards):
    s, bears, giant, wall = table(cards, True)
    d = s.state.rules.decision
    assert d.kind == "declare_blockers" and d.player == "p2" and d.decider == "p1" and d.blind
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[])  # not the defender's choice
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": giant.id, "attacker_id": bears.id}])  # the other creature must block too (509.1c)
    act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": giant.id, "attacker_id": bears.id}, {"blocker_id": wall.id, "attacker_id": bears.id}])
    assert s.state.cards[giant.id].is_blocking and s.state.cards[wall.id].is_blocking
    check(s)


def test_without_the_ability_the_defender_declares(cards):
    s, bears, giant, wall = table(cards, False)
    d = s.state.rules.decision
    assert d.kind == "declare_blockers" and d.decider is None
    act(s, "p2", type="declare_blockers", blocks=[])
    check(s)
