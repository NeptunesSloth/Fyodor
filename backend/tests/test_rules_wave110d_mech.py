"""Wave 110D: Mechtitan Core, real Oracle text.

* 602.2, 118.3: the cost exiles the Vehicle and four OTHER artifact creatures and/or Vehicles (a Vehicle that is not crewed counts), all or nothing.
* 607.2a: the cards exiled for the cost are the ones "exiled with" the Core, except the Core itself; 603.7: when the token leaves, they return tapped under their owners' control.
"""

from __future__ import annotations

from tests.wave9c_kit import build
from tests.wave110d_kit import EXTRA, activate, card_db, check, full, mana, now, put, refused  # noqa: F401

COST = "{5}, Exile this Vehicle and four other artifact creatures and/or Vehicles you control"
OTHERS = ["Frogmite", "Shimmer Myr", "Foundry Inspector", "Sky-Skiff"]


def test_full():
    assert full("Mechtitan Core")


def setup(cards, others=OTHERS):
    s = build(cards, ["Mechtitan Core", *others, "Grizzly Bears"])
    core = put(s, "Mechtitan Core")
    return s, core, [put(s, n) for n in others]


def run(s, core, paid):
    mana(s, C=5)
    activate(s, core, COST, cost_choices=[{"component": 2, "cards": [c.id for c in paid]}])


def kill(s, tok):
    from tests.game_helpers import act

    act(s, "p1", type="set_damage", card_ids=[tok.id], value=99)
    from tests.wave110d_kit import settle

    act(s, s.state.rules.priority, type="pass_priority")
    settle(s)


def test_exiled_cards_return_tapped_when_the_token_leaves_and_the_core_stays(cards):
    s, core, paid = setup(cards)
    run(s, core, paid)
    tok = next(c for c in s.state.cards.values() if c.name == "Mechtitan")
    assert all(now(s, c).zone == "p1:exile" for c in [core, *paid]) and tok.zone == "p1:battlefield"
    ch = s.state.cards[tok.id]
    assert (ch.token.power, ch.token.toughness) == ("10", "10") and len(ch.token.colors) == 5
    kill(s, tok)
    assert all(now(s, c).zone == "p1:battlefield" and now(s, c).tapped for c in paid)
    assert now(s, core).zone == "p1:exile"  # "except this card"
    check(s)


def test_three_others_is_not_enough(cards):
    s, core, paid = setup(cards)
    mana(s, C=5)
    refused(s, "Choose|pay|enough|isn.t|aren.t", core, COST, cost_choices=[{"component": 2, "cards": [c.id for c in paid[:3]]}])
    assert now(s, core).zone == "p1:battlefield" and all(now(s, c).zone == "p1:battlefield" for c in paid)


def test_a_plain_creature_does_not_count(cards):
    s, core, paid = setup(cards, OTHERS[:3] + ["Grizzly Bears"])
    mana(s, C=5)
    refused(s, "Choose|pay|enough|isn.t|aren.t|legal", core, COST, cost_choices=[{"component": 2, "cards": [c.id for c in paid]}])
