"""Wave 110C: Tevesh Szat, Doom of Fools (701.21a sacrifice, 608.2h last-known commander status, 903.3, 408/-10 loyalty ability)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, check, make_db, put, real

TEXT = ("+2: Create two 0/1 black Thrull creature tokens.\n"
        "+1: You may sacrifice another creature or planeswalker. If you do, draw two cards, then draw another card if the sacrificed permanent was a commander.\n"
        "−10: Gain control of all commanders. Put all commanders from the command zone onto the battlefield under your control.\n"
        "Tevesh Szat, Doom of Fools can be your commander.\nPartner")
EXTRA = [card("Tevesh Szat, Doom of Fools", set_code="tst", number="110C-TE", mana_cost="{4}{B}", cmc=5.0, type_line="Legendary Planeswalker — Szat",
              oracle_text=TEXT, loyalty="4", colors=["B"], color_identity=["B"]),
         real("Small Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Tevesh Szat, Doom of Fools")).level == "FULL"


def _hand(s):
    return len(s.state.zones.get("p1:hand", []))


@pytest.mark.parametrize("victim,draws,picks", [("Small Bear", 2, ["pay"]), ("Krenko, Mob Boss", 3, ["pay", "yes"]), (None, 0, ["decline"])])
def test_plus_one_sacrifices_and_draws(cards, victim, draws, picks):
    s = build(cards, ["Tevesh Szat, Doom of Fools", "Small Bear"])
    w = put(s, "Tevesh Szat, Doom of Fools")
    if victim:
        put(s, victim)
    before = _hand(s)
    act(s, "p1", type="activate_ability", card_id=w.id, ability=1)
    answer(s, *picks)  # (the one other creature is the only choice; a commander may then go to the command zone, 903.9a)
    assert _hand(s) - before == draws
    check(s)


def test_minus_ten_takes_every_commander_from_the_command_zone(cards):
    s = build(cards, ["Tevesh Szat, Doom of Fools"])
    w = put(s, "Tevesh Szat, Doom of Fools")
    act(s, "p1", type="set_counter", card_id=w.id, kind="loyalty", value=10)
    act(s, "p1", type="activate_ability", card_id=w.id, ability=2)
    answer(s)
    cmds = [c for c in s.state.cards.values() if c.commander_key is not None]
    assert len(cmds) == 2 and all(c.zone.endswith(":battlefield") and c.controller == "p1" for c in cmds)
    check(s)

