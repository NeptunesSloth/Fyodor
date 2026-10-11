"""Wave 35C: token-creation replacements that swap the tokens (CR 614.1a, 614.5, 616.1, 111.2), real Oracle text (tests/fixtures/wave35c_cards.json). Every
scenario checks the replay and a save and a load.

* "If one or more creature tokens would be created under your control, that many 4/4 white Angel creature tokens with flying and vigilance are created instead."
  (Divine Visitation; artifact tokens → 5/5 red Dragons: Draconic Visitor): the tokens' characteristics are replaced as they would be created (the Gatherer
  rulings), so a creature token made from an artifact one is replaced by both, in either order, with one result.
* "If you would create a Clue, Food, or Treasure token, instead create one of each." (Academy Manufactor): that many of each; two Manufactors make three times
  that many of each (each applies once to an event, 614.5, and to what the other made).
* "If you would create a Food token, instead create a Food token and a Treasure token." (Bilbo): that many Food and that many Treasure.
* 616.1: Divine Visitation with Chatterfang (or Bilbo with Academy Manufactor) give different results in different orders: the token's controller is asked.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import build, check, mana, put, reloaded, to_hand
from tests.wave35c_kit import cards, cast_from_hand  # noqa: F401

FULL = ["Divine Visitation", "Draconic Visitor", "Academy Manufactor", "Bilbo, Fellow Conspirator"]


@pytest.mark.parametrize("name", FULL)
def test_the_promoted_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def tokens(s, pid="p1"):
    out: dict[str, int] = {}
    for c in s.state.cards.values():
        if c.is_token and c.owner == pid and c.zone == f"{pid}:battlefield":
            out[c.name] = out.get(c.name, 0) + 1
    return out


def alarm(s):
    mana(s, "p1", W=2)
    cast_from_hand(s, "Raise the Alarm")


def goose(s):
    mana(s, "p1", G=2)
    cast_from_hand(s, "Gilded Goose")


def inspector(s):
    mana(s, "p1", W=2)
    cast_from_hand(s, "Thraben Inspector")


def decide(s, label):
    d = s.state.rules.decision
    assert d is not None and d.player == "p1", d
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if label in o.label)])
    settle(s)


# -- Divine Visitation / Draconic Visitor ----------------------------------------------------------------------------------------------------
def test_divine_visitation_makes_angels_instead_of_the_soldiers(cards):
    s = build(cards, ["Divine Visitation", "Raise the Alarm"], [])
    put(s, "Divine Visitation")
    alarm(s)
    assert tokens(s) == {"Angel": 2}
    angel = next(c for c in s.state.cards.values() if c.name == "Angel")
    assert (s.state.cards[angel.id].token.power, s.state.cards[angel.id].token.toughness) == ("4", "4")
    s = reloaded(s)
    check(s)


def test_draconic_visitor_swaps_artifact_tokens_only(cards):
    """A Clue is an artifact token: a Dragon instead; the Soldiers (creature tokens that aren't artifacts) are untouched."""
    s = build(cards, ["Draconic Visitor", "Thraben Inspector", "Raise the Alarm"], [])
    put(s, "Draconic Visitor")
    inspector(s)
    assert tokens(s) == {"Dragon": 1}
    alarm(s)
    assert tokens(s) == {"Dragon": 1, "Soldier": 2}
    s = reloaded(s)
    check(s)


def test_both_visitors_agree_on_an_artifact_creature_token_and_ask_nothing(cards):
    """616.1: a Servo is an artifact creature token. Visitation first: Angels. Visitor first: a Dragon is a creature token, so Visitation swaps it too:
    Angels. One result, no question."""
    s = build(cards, ["Divine Visitation", "Draconic Visitor", "Glint-Sleeve Artisan"], [])
    put(s, "Divine Visitation")
    put(s, "Draconic Visitor")
    mana(s, "p1", W=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Glint-Sleeve Artisan").id)
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:  # fabricate: the Servo rather than the counter
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if "Servo" in o.label or "token" in o.label.lower())])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.rules.decision is None and tokens(s) == {"Angel": 1}
    check(s)


def test_visitation_and_chatterfang_ask_which_applies_first(cards):
    """616.1: Chatterfang adds a Squirrel for each token. Chatterfang first: 2 Soldiers + 2 Squirrels, all creature tokens: 4 Angels. Visitation first: 2 Angels
    and then 2 Squirrels (Chatterfang's addition is not swapped again, 614.5 / the Angels' event is the one Visitation changed)."""
    for first, expected in (("Divine Visitation first", {"Angel": 2, "Squirrel": 2}), ("Chatterfang, Squirrel General first", {"Angel": 4})):
        s = build(cards, ["Divine Visitation", "Chatterfang, Squirrel General", "Raise the Alarm"], [])
        put(s, "Divine Visitation")
        put(s, "Chatterfang, Squirrel General")
        mana(s, "p1", W=2)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Raise the Alarm").id)
        for _ in range(8):
            if s.state.rules.decision is not None:
                break
            act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
        assert d is not None and d.player == "p1"
        assert any("Divine Visitation first" in o.label for o in d.options) and any("Chatterfang, Squirrel General first" in o.label for o in d.options)
        s = reloaded(s)  # the question survives a save and a load
        decide(s, first)
        assert {k: v for k, v in tokens(s).items() if k in ("Angel", "Squirrel", "Soldier")} == expected
        check(s)


# -- Academy Manufactor -----------------------------------------------------------------------------------------------------------------------
def test_academy_manufactor_makes_one_of_each(cards):
    s = build(cards, ["Academy Manufactor", "Thraben Inspector", "Gilded Goose"], [])
    put(s, "Academy Manufactor")
    inspector(s)
    assert {k: v for k, v in tokens(s).items() if k in ("Clue", "Food", "Treasure")} == {"Clue": 1, "Food": 1, "Treasure": 1}
    goose(s)
    assert {k: v for k, v in tokens(s).items() if k in ("Clue", "Food", "Treasure")} == {"Clue": 2, "Food": 2, "Treasure": 2}
    s = reloaded(s)
    check(s)


def test_two_manufactors_make_three_times_that_many_of_each(cards):
    """The Gatherer ruling of Academy Manufactor: two of them make three times that many of each — each applies once to an event (614.5) and again to
    what the other one made."""
    s = build(cards, ["Academy Manufactor", "Academy Manufactor", "Thraben Inspector"], [])
    for c in [c for c in s.state.cards.values() if c.name == "Academy Manufactor" and c.owner == "p1"]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    inspector(s)
    assert s.state.rules.decision is None
    assert {k: v for k, v in tokens(s).items() if k in ("Clue", "Food", "Treasure")} == {"Clue": 3, "Food": 3, "Treasure": 3}
    s = reloaded(s)
    check(s)


# -- Bilbo ------------------------------------------------------------------------------------------------------------------------------------
def test_bilbo_adds_a_treasure_for_each_food(cards):
    s = build(cards, ["Bilbo, Fellow Conspirator", "Gilded Goose", "Thraben Inspector"], [])
    put(s, "Bilbo, Fellow Conspirator")
    goose(s)
    assert {k: v for k, v in tokens(s).items() if k in ("Clue", "Food", "Treasure")} == {"Food": 1, "Treasure": 1}
    inspector(s)  # a Clue is not a Food
    assert {k: v for k, v in tokens(s).items() if k in ("Clue", "Food", "Treasure")} == {"Food": 1, "Treasure": 1, "Clue": 1}
    s = reloaded(s)
    check(s)


@pytest.mark.parametrize("first, expected", [("Bilbo, Fellow Conspirator first", {"Clue": 2, "Food": 2, "Treasure": 2}),
                                              ("Academy Manufactor first", {"Clue": 1, "Food": 1, "Treasure": 2})])
def test_bilbo_and_the_manufactor_ask_which_applies_first(cards, first, expected):
    """616.1: a Food token. Bilbo first: a Food and a Treasure, and each of those is swapped by the Manufactor (2 of each). The Manufactor first: a Clue, a Food and
    a Treasure, then Bilbo adds a Treasure for the Food."""
    s = build(cards, ["Bilbo, Fellow Conspirator", "Academy Manufactor", "Gilded Goose"], [])
    put(s, "Bilbo, Fellow Conspirator")
    put(s, "Academy Manufactor")
    mana(s, "p1", G=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Gilded Goose").id)
    for _ in range(8):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"
    s = reloaded(s)
    decide(s, first)
    assert {k: v for k, v in tokens(s).items() if k in ("Clue", "Food", "Treasure")} == expected
    check(s)
