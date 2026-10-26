"""Wave 110C: Omnath, Locus of All: 614.1a unspent mana becomes black (500.4); the first-main-phase look/reveal (701.20a) adds three mana in the card's colors (106.1)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.wave110c_kit import build, check, make_db, mana, put, real

OMNATH = ("If you would lose unspent mana, that mana becomes black instead.\nAt the beginning of your first main phase, look at the top card of your library. You may "
          "reveal that card if it has three or more colored mana symbols in its mana cost. If you do, add three mana in any combination of its colors and put it into your "
          "hand. If you don't reveal it, put it into your hand.")
EXTRA = [real("Omnath, Locus of All", "{2}{G}{U}{R}", 5, "Legendary Creature — Elemental", OMNATH, ("4", "4"), "GUR"),
         real("Triple Mono", "{B}{B}{B}", 3, "Sorcery", "", None, "B"),
         real("Triple Hybrid", "{R/G}{R/G}{R/G}", 3, "Sorcery", "", None, "RG"),
         real("Two Pip", "{3}{G}{G}", 5, "Sorcery", "", None, "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Omnath, Locus of All")).level == "FULL"


def top_then_main(s, name):
    """During turn 2: ``name`` goes second from the top of Alice's library, so turn 3's draw takes a Forest and the trigger sees ``name``."""
    c = next(c for c in s.state.cards.values() if c.name == name)
    forest = next(f for f in s.state.cards.values() if f.name == "Forest" and f.zone == "p1:library")
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main2")
    for x in (c, forest):
        act(s, "p1", type="move", card_ids=[x.id], to={"player": "p1", "zone": "library"}, position="top")
    until(s, lambda s: s.state.rules.decision is not None and s.state.turn.number == 3 or s.state.turn.number == 4)
    return c


def test_lost_mana_becomes_black(cards):
    s = build(cards, ["Omnath, Locus of All"])
    put(s, "Omnath, Locus of All")
    mana(s, R=2)
    for _ in range(40):
        if s.state.turn.phase != "main1" or s.state.turn.number != 1:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.players["p1"].mana.get("B", 0) == 2 and not s.state.players["p1"].mana.get("R")
    check(s)


@pytest.mark.parametrize(("name", "reveal"), [("Triple Mono", True), ("Triple Hybrid", True), ("Triple Hybrid", False), ("Two Pip", True)])
def test_reveal_adds_three_mana(cards, name, reveal):
    s = build(cards, ["Omnath, Locus of All", name], forests=30, islands=30)
    put(s, "Omnath, Locus of All")
    c = top_then_main(s, name)
    d = s.state.rules.decision
    if name == "Two Pip":  # fewer than three colored symbols: no choice, straight to hand
        assert d is None or d.kind == "declare_attackers"
    else:
        assert d is not None and {o.id for o in d.options} == {"reveal", "hand"}
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["reveal" if reveal else "hand"])
        while (d := s.state.rules.decision) is not None:  # the colors of Triple Hybrid: choose red three times
            act(s, "p1", type="choose", decision_id=d.id, option_ids=["R"])
    assert s.state.cards[c.id].zone == "p1:hand"
    pool = {sym: sum(u.sym == sym for u in s.state.players["p1"].mana_units) + s.state.players["p1"].mana.get(sym, 0) for sym in "WUBRG"}
    if reveal and name != "Two Pip":
        assert (pool.get("B", 0) == 3) if name == "Triple Mono" else (pool.get("R", 0) == 3)
    else:
        assert not any(pool.values())
    check(s)
