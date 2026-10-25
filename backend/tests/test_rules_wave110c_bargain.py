"""Wave 110C: Back for Seconds (702.166b bargain read as kicked; 608.2d the controller picks the one target put onto the battlefield instead)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, check, make_db, mana, put, real, to_hand

EXTRA = [real("Back for Seconds", "{2}{B}", 3, "Sorcery",
              "Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\n"
              "Return up to two target creature cards from your graveyard to your hand. If this spell was bargained, you may put one of those cards with "
              "mana value 4 or less onto the battlefield instead of putting it into your hand.", None, "B"),
         real("Small Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
         real("Huge Bear", "{5}{G}", 6, "Creature — Bear", "", ("6", "6"), "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Back for Seconds")).level == "FULL"


def grave(s, *names):
    out = [put(s, n) for n in names]
    act(s, "p1", type="move", card_ids=[c.id for c in out], to={"player": "p1", "zone": "graveyard"})
    return out


@pytest.mark.parametrize("bargain,where", [(False, ("p1:hand", "p1:hand")), (True, ("p1:battlefield", "p1:hand"))])
def test_bargained_puts_a_cheap_target_onto_the_battlefield(cards, bargain, where):
    """702.166b + 608.2d: bargained, the controller picks a target with mana value 4 or less; the other still goes to hand."""
    s = build(cards, ["Back for Seconds", "Small Bear", "Huge Bear", "Sol Ring"])
    small, huge = grave(s, "Small Bear", "Huge Bear")
    ring = put(s, "Sol Ring")
    src = to_hand(s, "Back for Seconds")
    mana(s, B=1, C=2)
    from app.rules.view import hints

    kw = {"optional_costs": [hints(s.state, "p1", s.cards)["optional_costs"][src.id][0]["id"]]} if bargain else {}
    act(s, "p1", type="cast_spell", card_id=src.id, targets=[small.id, huge.id], target_counts=[2], **kw)
    if bargain:
        d = s.state.rules.decision
        while d is not None and d.resume.get("step") != "choose_branch110c":
            answer(s, [ring.id]) if "sacrifice" in d.prompt.lower() else act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
            d = s.state.rules.decision
        assert [o.label for o in d.options] == ["Return them to your hand", "Battlefield: Small Bear"]
        answer(s, [d.options[1].id])
    else:
        answer(s)
    assert (s.state.cards[small.id].zone, s.state.cards[huge.id].zone) == where
    check(s)
