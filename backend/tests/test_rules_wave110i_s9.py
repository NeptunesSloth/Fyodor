"""Wave 110I s9.

* 509.1d, 509.1f: Hipparion ({1} to block power 3 or greater) blocking a creature enchanted by Awesome Presence ({3} per blocker): both costs apply, {4} total, asked once.
"""
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act, mana_pool
from tests.test_rules_designations import build as designations_build
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave34b_activated import attack, next_turn, stops, to_phase
from tests.wave110c_kit import make_db

EXTRA = [real("Awesome Presence", "{U}", 1, "Enchantment \u2014 Aura", "Enchant creature\nEnchanted creature can't be blocked unless defending player pays {3} for each creature they control that's blocking it.", None, "U"),
         real("Hill Giant", "{3}{R}", 4, "Creature \u2014 Giant", "", ("3", "3"), "R"),
         real("Providence", "{5}{W}{W}", 7, "Sorcery", "You may reveal this card from your opening hand. If you do, at the beginning of the first upkeep, your life total becomes 26.\nYour life total becomes 26.", None, "W"),
         real("Hipparion", "{1}{G}", 2, "Creature \u2014 Horse", "This creature can't block creatures with power 3 or greater unless you pay {1}.", ("1", "3"), "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("aura", [True, False])
def test_hipparion_plus_awesome_presence(cards, aura):
    s = designations_build(cards, ["Awesome Presence", "Hill Giant"], bob=[(1, "Hipparion"), (10, "Island")])
    bear = put(s, "Hill Giant", "battlefield")
    pres = put(s, "Awesome Presence", "battlefield")
    if aura:
        act(s, "p1", type="attach", card_ids=[pres.id], to=bear.id)
    hip = put(s, "Hipparion", "battlefield", "p2")
    stops(s)
    next_turn(s)
    attack(s, bear)
    to_phase(s, "declare_blockers")
    blk = [{"blocker_id": hip.id, "attacker_id": bear.id}]
    act(s, "p2", type="add_mana", player="p2", mana={"C": 3})
    if aura:  # {1} (power 3) + {3} (Aura) = {4}, asked once
        with pytest.raises(ActionError, match="Blocking costs"):
            act(s, "p2", type="declare_blockers", blocks=blk)
        act(s, "p2", type="add_mana", player="p2", mana={"C": 1})
    act(s, "p2", type="declare_blockers", blocks=blk)
    assert s.state.cards[hip.id].blocking == bear.id
    assert mana_pool(s, "p2") == ({} if aura else {"C": 2})  # without the Aura only Hipparion's {1}
    roundtrip(s)


def test_providence(cards):
    """103.6b/603.7a: revealed from the opening hand, at the first upkeep the revealer's life total becomes 26 (119.5); declined: nothing; cast: 26 too."""
    import tests.test_rules_wave18c_pregame_vote as pv

    for reveal in (True, False):
        s = pv.table(cards, [], ["Providence"])
        pv.keep_all(s)
        pv.answer(s, "p1")
        pv.answer(s, "p2", ["Providence"] if reveal else [])
        assert [s.state.players[p].life for p in ("p1", "p2")] == [40, 26 if reveal else 40]
        pv.roundtrip(s)


def test_providence_cast(cards):
    from tests.wave9c_kit import build, cast, check, life, mana, to_hand
    from tests.wave110a_kit import answer

    s = build(cards, ["Providence"])
    to_hand(s, "Providence")
    mana(s, W=2, C=5)
    cast(s, "Providence")
    answer(s)
    assert life(s, "p1") == 26 and life(s, "p2") == 40
    check(s)
