"""Wave 110C: "any opponent may [cost]. If they do, ..." (118.12, 101.4, 603.4).

* Reservoir Kraken: an opponent may tap an untapped creature they control; if one does, the Kraken becomes tapped and its controller gets a Fish (unblockable token).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30p_combat import to_phase
from tests.wave110c_kit import build, check, make_db, put, real

KRAKEN = ("Trample, ward {2}\nAt the beginning of each combat, if this creature is untapped, any opponent may tap an untapped creature they control. If they do, tap this "
          "creature and create a 1/1 blue Fish creature token with \"This token can't be blocked.\"")
EXTRA = [real("Reservoir Kraken", "{3}{U}{U}", 5, "Creature — Kraken", KRAKEN, ("5", "5"), "U")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Reservoir Kraken")).level == "FULL"


def _fish(s):
    return [c for c in s.state.cards.values() if c.name == "Fish" and c.zone == "p1:battlefield"]


@pytest.mark.parametrize("pays", [False, True])
def test_reservoir_kraken_opponent_may_tap_a_creature_to_tap_it_and_give_a_fish(cards, pays):
    s = build(cards, ["Reservoir Kraken"], ["Grizzly Bears"])
    kraken, bears = put(s, "Reservoir Kraken"), put(s, "Grizzly Bears", "p2")
    to_phase(s, "begin_combat")
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            pick = ["pay" if pays else "decline"] if "decline" in ids else [bears.id] if bears.id in ids else ids[:1]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[bears.id].tapped == pays and s.state.cards[kraken.id].tapped == pays and len(_fish(s)) == int(pays)
    check(s)
