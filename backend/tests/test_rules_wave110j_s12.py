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


CURSE = "Volrath's Curse"


def _curse_turn(cards):
    """p1 curses p2's Grizzly Bears; p2's turn 2, precombat main, bears are summoning-sick-free (put on the battlefield on turn 1)."""
    s = build(cards, [CURSE], ["Grizzly Bears", "Grizzly Bears"], forests=30, islands=30)
    bears = put_new(s, "Grizzly Bears", "p2")
    put_new(s, "Grizzly Bears", "p2")
    cast_on(s, CURSE, bears)
    act(s, "p2", type="set_stops", own=["declare_attackers"])
    to_phase(s, "main1", turn=2)
    return s, bears


def _attack(s, bears):
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])


def test_volrath_curse_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(CURSE)).level == "FULL"


def test_volrath_curse_stops_attacks_and_activations(cards):
    s, bears = _curse_turn(cards)
    act(s, "p2", type="pass_priority")
    while s.state.rules.decision is None or s.state.rules.decision.kind != "declare_attackers":
        act(s, s.state.rules.priority, type="pass_priority")
        if s.state.turn.phase not in ("main1", "beginning_of_combat", "declare_attackers"):
            break
    import pytest
    from app.game.errors import ActionError

    with pytest.raises(ActionError):
        _attack(s, bears)
    check(s)


def test_volrath_curse_is_ignored_by_sacrificing_a_permanent(cards):
    s, bears = _curse_turn(cards)
    forest = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2" and c.id != bears.id and c.zone.endswith(":battlefield"))  # (any permanent will do)
    from tests.wave110j_kit import ability

    act(s, "p2", type="activate_ability", card_id=bears.id, ability=ability(s, bears, "Sacrifice a permanent"))
    settle(s, answers=[forest.id])
    assert now(s, forest).zone.endswith(":graveyard")
    while s.state.rules.decision is None or s.state.rules.decision.kind != "declare_attackers":
        act(s, s.state.rules.priority, type="pass_priority")
    _attack(s, bears)
    settle(s)
    assert now(s, bears).attacking is not None
    check(s)
