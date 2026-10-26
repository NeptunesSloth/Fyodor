"""Wave 110C: Chancellor of the Annex's opening-hand reveal (103.6, 603.7, 118.12).

"You may reveal this card from your opening hand. If you do, when each opponent casts their first spell of the game, counter that spell unless that player pays {1}."
One delayed trigger per opponent, used up by that player's first spell (nothing is cast before the game begins); their second spell is not affected."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave18c_pregame_vote import answer, keep_all, real, roundtrip, table, zone_names

ANNEX = ("You may reveal this card from your opening hand. If you do, when each opponent casts their first spell of the game, counter that spell unless that player pays {1}.\n"
         "Flying\nWhenever an opponent casts a spell, counter it unless that player pays {1}.")
EXTRA = [real("Chancellor of the Annex", "{4}{W}{W}{W}", 7, "Creature — Phyrexian Angel", ANNEX, ("5", "6"), "W"),
         real("Opt", "{U}", 1, "Instant", "Scry 1.\nDraw a card.", colors="U"),
         real("Consider", "{U}", 1, "Instant", "Surveil 1. (Mill a card, then you may put it back.)\nDraw a card.", colors="U")]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Chancellor of the Annex")).level == "FULL"


def _alice_casts(s, name):
    """Alice's own spell on the stack gives Bob priority to respond (it is no matter of the reveal)."""
    mine = next(c for c in s.state.cards.values() if c.name == name and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[mine.id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"U": 1})
    act(s, "p1", type="cast_spell", card_id=mine.id)
    assert s.state.rules.priority == "p2"


def _start(cards, bob_mana):
    s = table(cards, ["Chancellor of the Annex", "Consider", "Opt"], ["Opt", "Consider"])
    keep_all(s)
    answer(s, "p1", ["Chancellor of the Annex"])
    answer(s, "p2")
    for n in ("Opt", "Consider"):
        c = next(c for c in s.state.cards.values() if c.name == n and c.owner == "p2")
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "hand"})
    act(s, "p2", type="add_mana", player="p2", mana=bob_mana)  # (so that Bob is not passed over)
    _alice_casts(s, "Consider")
    return s


def _settle(s, pay=None):
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[("pay" if pay else "decline") if "decline" in ids else ids[0]])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def _cast(s, name):
    act(s, "p2", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == name and c.owner == "p2" and c.zone == "p2:hand"))


def test_first_spell_is_countered_unless_it_pays_and_the_second_is_not(cards):
    s = _start(cards, {"U": 1})
    _cast(s, "Opt")  # no mana for the {1}: countered
    _settle(s)
    assert s.state.players["p1"].life == 40  # (Alice's spells are no matter of the reveal)
    assert "Opt" in zone_names(s, "p2:graveyard")
    hand = len(s.state.zones["p2:hand"])
    act(s, "p2", type="add_mana", player="p2", mana={"U": 1})
    _alice_casts(s, "Opt")
    _cast(s, "Consider")  # the second spell of the game: the reveal no longer applies
    _settle(s)
    assert len(s.state.zones["p2:hand"]) == hand  # cast (-1) and its draw (+1)
    assert zone_names(s, "p2:graveyard").count("Consider") == 1
    roundtrip(s)


def test_paying_one_lets_the_first_spell_resolve(cards):
    s = _start(cards, {"U": 2})
    hand = len(s.state.zones["p2:hand"])
    _cast(s, "Opt")
    _settle(s, pay=True)
    assert len(s.state.zones["p2:hand"]) == hand  # Opt left the hand and drew a card: it resolved
    roundtrip(s)
