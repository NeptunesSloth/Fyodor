"""Wave 110I session 14.

* Guardian Archon: "Reveal the player you chose" (the entry secret choice, 614.12a) gives you and a permanent you control protection from that player (702.16k) until end of turn; once only.
"""
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import answer, card_db  # noqa: F401  (the fixture)
from tests.test_rules_wave110e_cards import cast as cast_card
from tests.test_rules_wave110e_s11 import _three
from tests.test_rules_wave110e_s12 import SHAMAN
from tests.wave9c_kit import card_named, check, mana, put, to_hand
import tests.test_rules_wave110e_cards as base

ARCHON = real("Guardian Archon", "{4}{W}{W}", 6, "Creature — Archon",
              "Flying\nAs this creature enters, secretly choose an opponent.\nReveal the player you chose: You and target permanent you control each gain protection from the chosen player "
              "until end of turn. Activate only once.", ("5", "5"), "W")
base.EXTRA.append(ARCHON)


def test_archon_full(cards):
    assert coverage.of_card_data(cards.resolve("Guardian Archon")).level == "FULL"


def _table(cards, choose):
    s = _three(cards, ["Guardian Archon", "Test Shaman"])
    shaman = put(s, "Test Shaman")
    mana(s, W=2, C=4)
    cast_card(s, "Guardian Archon")
    for _ in range(3):
        d = s.state.rules.decision
        if d is not None and d.player == "p1" and "secretly" in d.prompt:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label.startswith(choose))])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    return s, shaman


def _bolt(s, pid, target):
    mana(s, pid, R=1)
    act(s, pid, type="cast_spell", card_id=to_hand(s, "Test Bolt", pid).id, targets=[target])


@pytest.mark.parametrize("who", ["p2", "p3"])
def test_archon_protects_you_and_the_target_from_the_chosen_player_only(cards, who):
    """Bob was chosen: afterwards Bob can target neither Alice nor her Shaman; Carol still can. The ability is once only (Activate only once)."""
    s, shaman = _table(cards, "Bob")
    archon = card_named(s, "Guardian Archon")
    assert archon.zone == "p1:battlefield"
    act(s, "p1", type="activate_ability", card_id=archon.id, ability=2, targets=[shaman.id])
    answer(s)
    for pid in ("p2", "p3"):
        act(s, pid, type="set_stops", own=[], others=["main1"], smart_pass=False)
    act(s, "p1", type="pass_priority")
    while s.state.rules.priority != who:
        act(s, s.state.rules.priority, type="pass_priority")
    for target in ("p1", shaman.id):
        if who == "p2":
            with pytest.raises(ActionError, match="(?i)target"):
                _bolt(s, who, target)
        else:
            _bolt(s, who, target)
            answer(s)
            assert s.state.players["p1"].life == 37
            break
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=archon.id, ability=2, targets=[shaman.id])
    check(s)
