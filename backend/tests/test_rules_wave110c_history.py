"""Wave 110C turn history: the Traps' alternative-cost conditions (118.9, 608.2i).

* Cobra Trap: a noncreature permanent under your control destroyed this turn by an opponent's spell or ability (701.8a: only a spell or ability's own
  "destroy" counts, not an ability you control, a creature or an exile).
* Summoning Trap: a creature spell you cast this turn was countered by a spell or ability an opponent controlled (701.6a).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import (
    answer,
    build,
    card_named,
    cast,
    check,
    make_db,
    mana,
    offers,
    put,
    real,
    to_hand,
    zone,
)

EXTRA = [
    real('Cobra Trap', '{4}{G}{G}', 6, 'Instant — Trap',
         "If a noncreature permanent under your control was destroyed this turn by a spell or ability an opponent controlled, you may pay {G} rather than pay this spell's mana cost.\nCreate four 1/1 green Snake creature tokens.", None, 'G'),
    real('Summoning Trap', '{4}{G}{G}', 6, 'Instant — Trap',
         "If a creature spell you cast this turn was countered by a spell or ability an opponent controlled, you may pay {0} rather than pay this spell's mana cost.\nLook at the top seven cards of your library. You may put a creature card from among them onto the battlefield. Put the rest on the bottom of your library in any order.", None, 'G'),
    real('Naturalize', '{1}{G}', 2, 'Instant', 'Destroy target artifact or enchantment.', None, 'G'),
    real('Ambush Viper', '{1}{G}', 2, 'Creature — Snake', 'Flash\nDeathtouch', ('2', '1'), 'G'),
]
NAMES = ["Cobra Trap", "Summoning Trap"]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _respond(s, spell, targets, pid, **m):
    """Bob (stops on) answers what is on the stack with ``spell``; it resolves; Alice has priority again with her own spell still there."""
    mana(s, pid, **m)
    cast(s, spell, targets, pid=pid)
    while any(c.name == spell and c.zone == "stack" for c in s.state.cards.values()):  # (Alice may already have passed: it resolved)
        act(s, s.state.rules.priority, type="pass_priority")


@pytest.mark.parametrize("scenario, expect", [
    ("bob_naturalizes_alices_ring", True),   # the one that counts
    ("alice_naturalizes_her_own_ring", False),  # a spell *you* controlled
    ("bob_murders_alices_bears", False),  # a creature
    ("bob_naturalizes_his_own_ring", False),  # not under your control
])
def test_cobra_trap_alternative_cost_needs_an_opponents_destroy_of_your_noncreature_permanent(cards, scenario, expect):
    """Cobra Trap: 701.8a destroy by a spell or ability an opponent controlled (608.2i, last known controller and card types)."""
    s = build(cards, ["Cobra Trap", "Sol Ring", "Lightning Bolt", "Grizzly Bears", "Naturalize"], ["Naturalize", "Murder", "Sol Ring"])
    ring = put(s, "Sol Ring")
    bears = put(s, "Grizzly Bears")
    theirs = put(s, "Sol Ring", "p2")
    for pid in ("p1", "p2"):
        act(s, pid, type="set_stops", own=["main1"], others=["main1"], smart_pass=False)
    if scenario.startswith("bob"):  # (a spell of Alice's on the stack for Bob to answer)
        mana(s, R=1)
        cast(s, "Lightning Bolt", ["p2"])
    trap = to_hand(s, "Cobra Trap")
    assert not offers(s, trap)
    if scenario == "bob_naturalizes_alices_ring":
        _respond(s, "Naturalize", [ring.id], "p2", G=1, C=1)
    elif scenario == "bob_murders_alices_bears":
        _respond(s, "Murder", [bears.id], "p2", B=2, C=1)
    elif scenario == "bob_naturalizes_his_own_ring":
        _respond(s, "Naturalize", [theirs.id], "p2", G=1, C=1)
    else:
        mana(s, G=1, C=1)
        cast(s, "Naturalize", [ring.id])
        answer(s)
    assert zone(s, ring) in ("p1:graveyard", "p1:battlefield")
    got = offers(s, trap)
    assert bool(got) == expect
    if expect:
        mana(s, G=1)
        act(s, "p1", type="cast_spell", card_id=trap.id, alt_cost=got[0].key)
        answer(s)
        assert sum(c.name == "Snake" and c.zone == "p1:battlefield" for c in s.state.cards.values()) == 4
    check(s)


@pytest.mark.parametrize("scenario, expect", [("creature_countered_by_bob", True), ("noncreature_countered", False), ("bobs_creature_countered_by_alice", False)])
def test_summoning_trap_alternative_cost_needs_your_creature_spell_countered_by_an_opponent(cards, scenario, expect):
    """Summoning Trap: 701.6a countered by a spell or ability an opponent controlled; only a spell you cast, and a creature spell."""
    s = build(cards, ["Summoning Trap", "Grizzly Bears", "Counterspell", "Lightning Bolt"], ["Counterspell", "Grizzly Bears", "Lightning Bolt", "Ambush Viper"])
    for pid in ("p1", "p2"):
        act(s, pid, type="set_stops", own=["main1"], others=["main1"], smart_pass=False)
    trap = to_hand(s, "Summoning Trap")
    if scenario == "bobs_creature_countered_by_alice":  # (Bob's flash creature, Alice's Counterspell: a creature spell *he* cast)
        mana(s, R=1)
        cast(s, "Lightning Bolt", ["p2"])
        mana(s, "p2", G=2)
        cast(s, "Ambush Viper", pid="p2")
        assert s.state.rules.priority == "p1"
        mana(s, U=2)
        cast(s, "Counterspell", [next(c.id for c in s.state.cards.values() if c.zone == "stack" and c.name == "Ambush Viper")])
        while any(c.name == "Counterspell" and c.zone == "stack" for c in s.state.cards.values()):
            act(s, s.state.rules.priority, type="pass_priority")
        assert not offers(s, trap) and zone(s, card_named(s, "Ambush Viper", "p2")) == "p2:graveyard"
        check(s)
        return
    if scenario == "creature_countered_by_bob":
        mana(s, G=2)
        cast(s, "Grizzly Bears")
    else:
        mana(s, R=1)
        cast(s, "Lightning Bolt", ["p2"])
    mana(s, "p2", U=2)
    cast(s, "Counterspell", [next(c.id for c in s.state.cards.values() if c.zone == "stack" and c.ability is None and c.name != "Counterspell")], pid="p2")
    while any(c.name == "Counterspell" and c.zone == "stack" for c in s.state.cards.values()):
        act(s, s.state.rules.priority, type="pass_priority")
    got = offers(s, trap)
    assert bool(got) == expect
    if expect:
        act(s, "p1", type="cast_spell", card_id=trap.id, alt_cost=got[0].key)
        answer(s)
    check(s)
