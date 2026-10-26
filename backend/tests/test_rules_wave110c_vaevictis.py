"""Wave 110C: Vaevictis Asmadi, the Dire (115.1, 701.21a, 701.20a, 614.12a): one target per player, all sacrificed together; each player who sacrificed reveals their top card
and puts it onto the battlefield if it is a permanent card (otherwise it stays on top)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named
from tests.wave110c_kit import check, make_db, put, real
from tests.wave110d_kit import to_phase

TEXT = ("Flying\nWhenever Vaevictis Asmadi attacks, for each player, choose target permanent that player controls. Those players sacrifice those permanents. Each player who "
        "sacrificed a permanent this way reveals the top card of their library, then puts it onto the battlefield if it's a permanent card.")
EXTRA = [real("Vaevictis Asmadi, the Dire", "{2}{B}{R}{G}", 5, "Legendary Creature — Elder Dragon", TEXT, ("6", "6"), "BRG")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Vaevictis Asmadi, the Dire")).level == "FULL"


def top(s, pid, name):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")
    return c


def pick(wanted):
    """Answer each target decision with the wanted card, else the first option."""
    def go(s):
        d = s.state.rules.decision
        ids = [o.id for o in d.options]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((w for w in wanted if w in ids), ids[0])])
    return go


def attack(s, vaev, wanted):
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": vaev.id, "target": "p2"}])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            pick(wanted)(s)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


@pytest.mark.parametrize("p2_top,enters", [("Forest", True), ("Lightning Bolt", False)])
def test_each_player_sacrifices_and_reveals(cards, p2_top, enters):
    s = build(cards, ["Vaevictis Asmadi, the Dire", "Grizzly Bears", "Forest"], ["Grizzly Bears", "Forest", "Lightning Bolt"])
    vaev = put(s, "Vaevictis Asmadi, the Dire")
    s.state.rules.controlled_since[vaev.id].turn = 0
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    to_phase(s, "declare_attackers", turn=3)  # (after the draw step)
    mine_top, their_top = top(s, "p1", "Forest"), top(s, "p2", p2_top)
    attack(s, vaev, [mine.id, theirs.id])
    assert s.state.cards[mine.id].zone == "p1:graveyard" and s.state.cards[theirs.id].zone == "p2:graveyard"
    assert s.state.cards[mine_top.id].zone == "p1:battlefield"  # (p1's top card was a land)
    assert (s.state.cards[their_top.id].zone == "p2:battlefield") is enters
    check(s)


def test_a_player_who_sacrificed_nothing_reveals_nothing(cards):
    """p2 has no permanent to target: only p1 sacrifices (their own choice) and reveals."""
    s = build(cards, ["Vaevictis Asmadi, the Dire", "Grizzly Bears", "Forest"], ["Forest"])
    vaev = put(s, "Vaevictis Asmadi, the Dire")
    s.state.rules.controlled_since[vaev.id].turn = 0
    mine = put(s, "Grizzly Bears")
    to_phase(s, "declare_attackers", turn=3)
    mine_top, their_top = top(s, "p1", "Forest"), top(s, "p2", "Forest")
    attack(s, vaev, [mine.id])
    assert s.state.cards[mine.id].zone == "p1:graveyard"
    assert s.state.cards[mine_top.id].zone == "p1:battlefield" and s.state.cards[their_top.id].zone == "p2:library"
    check(s)
