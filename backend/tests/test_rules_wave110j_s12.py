"""Wave 110J session 12, real Oracle text (tests/fixtures/wave110j_cards.json). Every scenario ends with replay + save/load.

* Paliano, the High City: 905.2 / 103.6 and the 2014-05-29 ruling: without a draft no color was chosen, so its mana ability taps for no mana (not even colorless).
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build, life
from tests.wave110j_kit import EXTRA, card_db, cast_on, check, now, put_new, settle, to_phase  # noqa: F401

PALIANO = "Paliano, the High City"


def test_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(PALIANO)).level == "FULL"


def test_paliano_taps_for_no_mana(cards):
    s = build(cards, [PALIANO])
    p = put_new(s, PALIANO)
    act(s, "p1", type="activate_ability", card_id=p.id, ability=1)
    settle(s)
    assert now(s, p).tapped and s.state.players["p1"].mana == {} and not s.state.players["p1"].mana_units
    check(s)


TAKKLE = "Takklemaggot"


def _takkle_setup(cards, second_bear):
    s = build(cards, [TAKKLE, "Murder"], ["Grizzly Bears", "Grizzly Bears"], forests=30, islands=30)
    b1 = put_new(s, "Grizzly Bears", "p2")
    b2 = put_new(s, "Grizzly Bears", "p2") if second_bear else None
    t = cast_on(s, TAKKLE, b1)
    assert t.attached_to == b1.id if hasattr(t, "attached_to") else True
    cast_on(s, "Murder", b1)
    return s, t, b1, b2


def test_takklemaggot_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(TAKKLE)).level == "FULL"


def test_takklemaggot_returns_attached_to_the_creature_its_controller_picks(cards):
    s, t, b1, b2 = _takkle_setup(cards, True)
    settle(s, answers=[b2.id])
    t = now(s, t)
    assert t.zone == "p1:battlefield" and t.controller == "p1" and t.attached_to == b2.id
    check(s)


def test_takklemaggot_without_a_creature_returns_as_non_aura_that_pings(cards):
    s, t, b1, _ = _takkle_setup(cards, False)
    settle(s)
    t = now(s, t)
    assert t.zone == "p1:battlefield" and t.controller == "p1" and t.attached_to is None
    from tests.wave110j_kit import ch

    c = ch(s, t)
    assert "Aura" not in c.subtypes and not any(a.text.startswith("Enchant") for a in c.abilities)
    to_phase(s, "upkeep", turn=3)  # p2's turn-2 upkeep has passed: 1 damage each of its upkeeps, none on p1's
    settle(s)
    assert life(s, "p2") == 39 and life(s, "p1") == 40
    check(s)
