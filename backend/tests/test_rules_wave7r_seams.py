"""Wave 7R (second part of the wave 7 review): regressions for the seams found in the shield-counter, power-up, coin-flip
and must-block code of wave 7. Researched against CR 2026-09-25; cards carry real Oracle text."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import mana as M
from tests.game_helpers import act
from tests.test_rules_combat import attack, automate, block, creature, table
from tests.test_rules_effects import replay_matches


# -- 509.1c: a block that obeys its own requirement isn't taken as disobeying another one ------------------------------
def test_a_blocker_obeying_its_own_requirement_is_not_taken_away_from_another(cards):
    s = table(cards)
    soldier = creature(s, "p1", "Soldier", "2/2", "This creature must be blocked if able.")
    other = creature(s, "p1", "Other", "2/2")
    screen = creature(s, "p2", "Screen", "1/3", "This creature blocks each combat if able.")
    automate(s)
    attack(s, (soldier, "p2"), (other, "p2"))
    with pytest.raises(ActionError, match="if able"):
        block(s, "p2")  # neither requirement obeyed
    block(s, "p2", (screen, other))  # "blocks each combat if able" obeyed; the one blocker can't also block the Soldier
    replay_matches(s)


# -- 118.7g: snow in a power-up cost is not read ---------------------------------------------------------------------
def test_power_up_with_snow_is_not_read():
    from app.rules import power_up
    from app.rules.characteristics import Characteristics

    def ch(cost):
        return Characteristics(name="X", mana_cost=cost)

    assert not power_up.readable(ch("{S}"), "{2}{G}")
    assert not power_up.readable(ch("{1}{G}"), "{S}{G}")
    assert power_up.readable(ch("{1}{G}"), "{2}{G}")
    assert M.parse_cost("{S}").colored == ("S",)


# -- 122.1c: shield counters in combat -----------------------------------------------------------------------------------
def _shield(s, c, n=1):
    act(s, c.controller, type="counter", card_ids=[c.id], kind="shield", delta=n)


def test_two_blockers_use_up_one_shield_counter_and_deathtouch_does_not_kill(cards):
    s = table(cards)
    rhino = creature(s, "p1", "Rhino", "6/3", "Trample")
    _shield(s, rhino)
    a = creature(s, "p2", "Viper", "1/1", "Deathtouch")
    b = creature(s, "p2", "Wall", "0/4")
    automate(s)
    attack(s, (rhino, "p2"))
    block(s, "p2", (a, rhino), (b, rhino))
    r = s.state.cards[rhino.id]
    assert r.zone == "p1:battlefield" and not r.counters.get("shield") and r.damage == 0  # all prevented, one counter
    replay_matches(s)


def test_a_shield_counter_protects_only_its_own_permanent(cards):
    s = table(cards)
    bear = creature(s, "p2", "Bear", "2/2")
    mine = creature(s, "p1", "Mine", "2/2")
    _shield(s, bear)
    automate(s)
    attack(s, (mine, "p2"))
    block(s, "p2", (bear, mine))
    assert mine.id not in s.state.cards  # (a token ceases to exist) the unshielded one took its 2 damage and died
    assert s.state.cards[bear.id].zone == "p2:battlefield" and not s.state.cards[bear.id].counters.get("shield")
    replay_matches(s)


# -- Event.group (wave 7C): old saves have none ---------------------------------------------------------------------------
def test_an_event_from_an_old_save_has_no_group_and_a_new_one_keeps_its_group():
    from app.game.rules_state import Event

    old = Event.model_validate({"batch": 3, "kind": "counters", "turn": 1, "counter": "reach", "amount": 1})
    assert old.group == 0
    new = Event(batch=4, kind="counters", turn=1, counter="reach", amount=1, group=7)
    assert Event.model_validate_json(new.model_dump_json()).group == 7
