"""Wave 110D: Master of Predicaments, real Oracle text (tests/fixtures/wave110d_cards.json).

* 608.2d: the controller picks the card in secret, the damaged player guesses whether its mana value is greater than 4 (202.3e).
* 118.9: a wrong guess lets the controller cast it without paying its mana cost; a right guess gives nothing.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave110d_kit import build, card_db, check, full, hand_new, life, now, put_new, to_phase  # noqa: F401

NAME = "Master of Predicaments"


def test_full():
    assert full(NAME)


def _hit(cards, hand, guess):
    """Attack unblocked; p1 picks the first card of ``hand``, p2 guesses ``guess``; later choices take the first option."""
    s = build(cards, [NAME, *hand], ["Grizzly Bears"])
    master = put_new(s, NAME)
    held = [hand_new(s, n) for n in hand]
    to_phase(s, "declare_attackers", turn=3)
    for c in [c for c in s.state.cards.values() if c.zone == "p1:hand" and c.id not in {h.id for h in held}]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "library"}, position="bottom")  # (nothing else in hand: only the cards under test)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": master.id, "target": "p2"}])
    seen = []
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            seen.append((d.player, d.prompt))
            if "target" in d.prompt:
                ids = ["p2"]
            elif d.kind == "choose_one" and d.player == "p2":
                ids = [guess]
            elif d.kind == "choose_one":  # (p1's yes/no: cast it)
                ids = ["yes"] if "yes" in [o.id for o in d.options] else [d.options[0].id]
            else:
                ids = [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.turn.phase in ("main2", "end") and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    return s, held, seen


def test_wrong_guess_lets_it_be_cast_free(cards):
    s, (bolt,), seen = _hit(cards, ["Lightning Bolt"], "yes")  # mana value 1: "greater than 4" is wrong
    assert now(s, bolt).zone == "p1:graveyard" and life(s, "p2") == 40 - 4 - 3  # (the Master's 4 combat damage, then the free Bolt at p2)
    check(s)


def test_right_guess_gives_nothing(cards):
    s, (bolt,), seen = _hit(cards, ["Lightning Bolt"], "no")
    assert now(s, bolt).zone == "p1:hand" and life(s, "p2") == 36
    check(s)


@pytest.mark.parametrize(("guess", "cast"), [("no", True), ("yes", False)])
def test_big_card(cards, guess, cast):
    s, (rise,), seen = _hit(cards, ["Rise of the Dark Realms"], guess)  # mana value 9
    assert (now(s, rise).zone == "p1:graveyard") is cast
    check(s)


def test_empty_hand_asks_nothing(cards):
    s, _, seen = _hit(cards, [], "yes")
    assert not [x for x in seen if "mana value" in x[1]] and life(s, "p2") == 36
    check(s)
