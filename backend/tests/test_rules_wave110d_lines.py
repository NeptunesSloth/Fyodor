"""Wave 110D: one-line rewrites, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 702.181a, 107.3c: "Equipped creature has menace and mobilize X, where X is its power." (Infantry Shield) — X tokens as the attack trigger resolves.
* 205.1b, 613.4b, 613.1f: "Enchanted creature loses all abilities and is a Toy artifact creature with base power and toughness 0/2 in addition
  to its other types." (Unable to Scream) — Toy and artifact are added, the creature stays an Elf; "can't be turned face up" (708.2).
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import (  # noqa: F401
    activate,
    card_db,
    cast_on,
    ch,
    check,
    full,
    mana,
    next_turn,
    now,
    put,
    settle,
    to_phase,
)


def test_infantry_shield_is_full():
    assert full("Infantry Shield")


def test_infantry_shield_mobilizes_its_power(cards):
    s = build(cards, ["Infantry Shield", "Grizzly Bears"])
    shield, bears = put(s, "Infantry Shield"), put(s, "Grizzly Bears")
    s.state.rules.controlled_since[bears.id].turn = 0
    mana(s, C=2)
    activate(s, shield, "Equip {2}")
    settle(s)
    assert "menace" in ch(s, bears).keywords
    next_turn(s)
    next_turn(s)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="set_stops", own=["declare_attackers"], smart_pass=False)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    settle(s)
    warriors = [c for c in s.state.cards.values() if c.name == "Warrior" and c.zone == "p1:battlefield"]
    assert len(warriors) == 2 and all(w.tapped for w in warriors)  # Grizzly Bears' power
    check(s)


def test_unable_to_scream_is_full():
    assert full("Unable to Scream")


def test_unable_to_scream_makes_a_toy(cards):
    s = build(cards, ["Unable to Scream", "Llanowar Elves"])
    elves = put(s, "Llanowar Elves")
    cast_on(s, "Unable to Scream", elves)
    c = ch(s, elves)
    assert c.pt == (0, 2)
    assert {"Artifact", "Creature"} <= set(c.types) and {"Toy", "Elf"} <= set(c.subtypes)
    assert not c.abilities
    check(s)
