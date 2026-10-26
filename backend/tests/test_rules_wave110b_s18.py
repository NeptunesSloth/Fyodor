"""Wave 110B session 18: single cards (real Oracle text in tests/fixtures/wave110b_cards.json).

* Marchesa, Resolute Monarch (Invasion of Fiora's back face): 603.4 upkeep draw and 1 life only if its controller was not dealt combat damage since their
  last turn ended (kept across the opponents' turns; damage in the turn before that does not count).
* Tombstone Stairwell: 603.2, 608.2h each upkeep every player makes a Tombspawn per creature card in their own graveyard (all counted first); those tokens die at
  the end step, or when the Stairwell leaves the battlefield, and nothing else does.
* Firkraag, Cunning Instigator: 508.1d a creature declared as an attacker with a requirement on it (goaded) "had to attack this combat"; one that was free to stay home did not.
* Behemoth of Vault 0: 107.14, 118.12 the energy paid equals the target's mana value; paid in full (or not at all), the target is destroyed.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110b_kit import (
    attack,
    build,
    card_named,
    cast,
    ch,
    check,
    drive,
    life,
    mana,
    pt,
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


def tombspawns(s):
    return sorted(c.owner for c in s.state.cards.values() if c.name == "Tombspawn" and c.zone.endswith(":battlefield"))


def stairwell_upkeep(cards):
    """Bob's upkeep (no cumulative upkeep for Alice): Alice has 1 creature card in her graveyard, Bob 2; a Kami waits to destroy the Stairwell."""
    s = build(cards, ["Tombstone Stairwell", "Grizzly Bears"], ["Llanowar Elves", "Grizzly Bears", "Kami of Ancient Law"], forests=30)
    put(s, "Tombstone Stairwell")
    for pid, name in (("p1", "Grizzly Bears"), ("p2", "Llanowar Elves"), ("p2", "Grizzly Bears")):
        act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"player": pid, "zone": "graveyard"})
    kami = put(s, "Kami of Ancient Law", "p2")
    to_phase(s, "main1", turn=2)
    return s, kami


def test_tombstone_stairwell_makes_a_zombie_per_creature_card_in_each_graveyard_and_destroys_them_at_end_step(cards):
    s, kami = stairwell_upkeep(cards)
    assert tombspawns(s) == ["p1", "p2", "p2"]
    assert all(ch(s, c).pt == (2, 2) for c in s.state.cards.values() if c.name == "Tombspawn")
    assert zone_of(s, "Kami of Ancient Law", "p2") == "p2:battlefield"  # (a real creature stays)
    to_phase(s, "end", turn=2)
    assert tombspawns(s) == ["p1", "p2", "p2"] and s.state.zones["stack"]  # (the end step trigger is waiting)
    act(s, s.state.rules.priority, type="pass_priority")  # (the trigger resolves; the new turn's upkeep triggers wait before any new token)
    assert tombspawns(s) == []
    assert zone_of(s, "Kami of Ancient Law", "p2") == "p2:battlefield"
    check(s)


def test_tombstone_stairwell_destroys_its_tokens_when_it_leaves(cards):
    s, kami = stairwell_upkeep(cards)
    act(s, "p2", type="activate_ability", card_id=kami.id, ability=0, targets=[card_named(s, "Tombstone Stairwell").id])
    drive(s)
    assert zone_of(s, "Tombstone Stairwell") == "p1:graveyard" and tombspawns(s) == []
    check(s)


@pytest.mark.parametrize(("goaded", "counters"), [(True, 2), (False, 0)])
def test_firkraag_counts_creatures_that_had_to_attack(cards, goaded, counters):
    s = build(cards, ["Firkraag, Cunning Instigator", "Grizzly Bears"], ["Disrupt Decorum"], forests=30)
    firkraag = put(s, "Firkraag, Cunning Instigator")
    bears = put(s, "Grizzly Bears")
    if goaded:  # Bob goads all of Alice's creatures on his turn: they attack Bob on hers
        to_phase(s, "main1", turn=2)
        mana(s, "p2", R=2, C=2)
        cast(s, "Disrupt Decorum", pid="p2")
        drive(s)
    to_phase(s, "main1", turn=3)
    base = pt(s, "Firkraag, Cunning Instigator")
    attack(s, firkraag, bears)
    through_combat(s)
    drive(s)
    assert pt(s, "Firkraag, Cunning Instigator")[0] - base[0] == counters
    check(s)
