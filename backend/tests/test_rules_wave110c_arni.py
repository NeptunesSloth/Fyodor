"""Wave 110C: "enters attacking" as a trigger event (508.4, 603.2).

* Arni Metalbrow: whenever a creature you control attacks or enters attacking, its controller may pay {1}{R} and put a creature card with lesser mana value from
  their hand onto the battlefield tapped and attacking. A creature put there never "attacks" (508.4), so only the "enters attacking" half sees it: the chain
  Arni (3) -> Grizzly Bears (2) -> Llanowar Elves (1) runs, a card of mana value 4 (or equal) is never offered.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30p_combat import to_phase
from tests.wave110c_kit import build, check, life, make_db, mana, put, real, to_hand

ARNI = ("Whenever a creature you control attacks or enters attacking, you may pay {1}{R}. If you do, you may put a creature card with mana value less than that creature's "
        "mana value from your hand onto the battlefield tapped and attacking.")
EXTRA = [real("Arni Metalbrow", "{2}{R}", 3, "Legendary Creature — Human Berserker", ARNI, ("3", "3"), "R"),
         real("Hill Giant", "{3}{R}", 4, "Creature — Giant", "", ("3", "3"), "R"),
         real("Llanowar Elves", "{G}", 1, "Creature — Elf Druid", "{T}: Add {G}.", ("1", "1"), "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Arni Metalbrow")).level == "FULL"


def _attack(cards, pays):
    s = build(cards, ["Arni Metalbrow", "Grizzly Bears", "Llanowar Elves", "Hill Giant"])
    arni = put(s, "Arni Metalbrow")
    hand = {n: to_hand(s, n) for n in ("Grizzly Bears", "Llanowar Elves", "Hill Giant")}
    to_phase(s, "declare_attackers", 3)
    mana(s, R=2, C=2)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": arni.id, "target": "p2"}])
    offered: list[list[str]] = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            if d.kind == "choose_cards":
                offered.append([s.state.cards[i].name for i in ids])
            pick = (["pay" if pays else "decline"] if "decline" in ids else ids[:1])
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return s, arni, hand, offered


def test_attack_chain_puts_lesser_creatures_in_attacking(cards):
    s, arni, hand, offered = _attack(cards, True)
    bears, elves, giant = (s.state.cards[hand[n].id] for n in ("Grizzly Bears", "Llanowar Elves", "Hill Giant"))
    assert offered[0] == ["Grizzly Bears", "Llanowar Elves"]  # mana value less than Arni's 3: not the 4
    assert offered[1] == ["Llanowar Elves"]  # Bears entered attacking and triggered Arni: less than 2
    assert bears.zone == elves.zone == "p1:battlefield" and bears.tapped and elves.tapped
    assert life(s, "p2") == 40 - 3 - 2 - 1  # all three dealt combat damage: they were attacking creatures (508.4)
    assert giant.zone == "p1:hand"
    check(s)


def test_declined_payment_puts_nothing(cards):
    s, arni, hand, offered = _attack(cards, False)
    assert offered == [] and s.state.cards[hand["Grizzly Bears"].id].zone == "p1:hand" and life(s, "p2") == 37
    check(s)
