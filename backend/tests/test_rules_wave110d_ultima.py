"""Wave 110D: Ultima, Origin of Oblivion, real Oracle text.

* 305.7, 613.1d, 613.1f: while the land has a blight counter it has no land types and loses its abilities, and has "{T}: Add {C}."; 611.2b the effect ends with the counter.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave110d_kit import build, card_db, ch, check, full, next_turn, now, put_new, settle, to_phase  # noqa: F401

NAME = "Ultima, Origin of Oblivion"


def test_full():
    assert full(NAME)


def test_attack_blights_a_land_which_loses_types_and_abilities_while_it_has_the_counter(cards):
    s = build(cards, [NAME], [])
    ultima, island = put_new(s, NAME), put_new(s, "Island", "p2")
    assert "Island" in ch(s, island).subtypes
    next_turn(s)
    next_turn(s)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="set_stops", own=["declare_attackers"], smart_pass=False)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ultima.id, "target": "p2"}])
    settle(s, answers=[island.id])
    assert now(s, island).counters.get("blight") == 1
    got = ch(s, island)
    assert "Island" not in got.subtypes and "Land" in got.types and [a.text for a in got.abilities if "Add" in a.text] == ["{T}: Add {C}."]
    check(s)
    act(s, "p1", type="counter", card_ids=[island.id], kind="blight", delta=-1)
    act(s, s.state.rules.priority, type="pass_priority")  # (the duration check runs on the next sync)
    got = ch(s, island)
    assert "Island" in got.subtypes and not any(a.text == "{T}: Add {C}." for a in got.abilities)
