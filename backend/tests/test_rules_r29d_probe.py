"""Temporary review probes (wave 29D head review)."""

from __future__ import annotations

from tests.game_helpers import act
from tests.test_rules_conditionals import attack, through_combat, to_turn
from tests.test_rules_wave29d_life_lock import cards, cast, check, lock, table  # noqa: F401
from tests.wave9c_kit import card_named, life, mana, put, to_hand


def test_probe_teferi_protection(cards):  # noqa: F811
    s = table(cards)
    hawk = put(s, "Vampire Nighthawk", "p2")
    tp = cast(s, "Teferi's Protection", mana={"W": 1, "C": 2})
    print("tp zone", s.state.cards[tp.id].zone if tp.id in s.state.cards else "gone")
    to_turn(s, 2)
    bolt = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    try:
        act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
        print("bolt cast at p1 ALLOWED")
    except Exception as e:  # noqa: BLE001
        print("bolt refused:", e)
    s.state.rules.controlled_since[hawk.id].turn = 0
    act(s, "p2", type="pass_priority")
    d = s.state.rules.decision
    print("decision", d.kind if d else None, [o.id for o in d.options] if d else None)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": hawk.id, "target": "p1"}])
    through_combat(s)
    print("life", life(s, "p1"), life(s, "p2"))
    print([e for e in s.view("p1")["log"][-6:]])
    check(s)
