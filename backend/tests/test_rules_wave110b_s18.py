"""Wave 110B session 18: single cards (real Oracle text in tests/fixtures/wave110b_cards.json).

* Marchesa, Resolute Monarch (Invasion of Fiora's back face): 603.4 upkeep draw and 1 life only if its controller was not dealt combat damage since their
  last turn ended (kept across the opponents' turns; damage in the turn before that does not count).
* Behemoth of Vault 0: 107.14, 118.12 the energy paid equals the target's mana value; paid in full (or not at all), the target is destroyed.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110b_kit import (
    build,
    card_named,
    cast,
    check,
    drive,
    life,
    mana,
    put,
    repository,
    through_combat,
    zone_of,
)


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["Behemoth of Vault 0", "Marchesa, Resolute Monarch"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def answer(target):
    """Pick the target by card; any other decision takes its first option (pay)."""
    return lambda d: [o.id for o in d.options if o.card_id == target] or None


@pytest.mark.parametrize(("victim", "destroyed", "energy"), [("Grizzly Bears", True, 2), ("Shivan Dragon", False, 4)])
def test_behemoth_pays_the_target_s_mana_value(cards, victim, destroyed, energy):
    s = build(cards, ["Behemoth of Vault 0", "Murder"], [victim])
    mana(s, C=6)
    cast(s, "Behemoth of Vault 0")
    drive(s)
    b = card_named(s, "Behemoth of Vault 0")
    v = put(s, victim, "p2")
    assert s.state.players["p1"].resources.get("energy") == 4
    mana(s, B=3)
    cast(s, "Murder", [b.id])
    drive(s, answer(v.id))
    assert (zone_of(s, victim, "p2") == "p2:graveyard") is destroyed
    assert s.state.players["p1"].resources.get("energy") == energy
    check(s)


@pytest.mark.parametrize(("hit", "life_after"), [(False, 39), (True, 38)])
def test_marchesa_draws_unless_dealt_combat_damage_since_its_controllers_last_turn(cards, hit, life_after):
    s = build(cards, ["Marchesa, Resolute Monarch"], ["Grizzly Bears"], forests=30)
    put(s, "Marchesa, Resolute Monarch")
    bears = put(s, "Grizzly Bears", "p2")
    to_phase(s, "main1", turn=2)
    if hit:
        s.state.rules.controlled_since[bears.id].turn = 0
        act(s, "p2", type="pass_priority")
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
        through_combat(s)
        assert life(s, "p1") == 38
    to_phase(s, "main1", turn=3)
    drive(s)
    assert life(s, "p1") == life_after
    if hit:  # the damage was before p1's turn 3 ended: turn 5's upkeep draws again
        to_phase(s, "main1", turn=5)
        assert life(s, "p1") == 37
    check(s)
