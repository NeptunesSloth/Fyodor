"""Wave 35C: "instead" riders on the object a trigger is about (CR 608.2c, 614.15, 608.2h, 603.10a), real Oracle text (tests/fixtures/wave35c_cards.json). Every
scenario checks the replay and a save and a load.

* "If the creature had power 4 or greater, create two of those tokens instead." (Anax, Hardened in the Forge): the power the dying creature had immediately
  before it died (the Gatherer ruling; last known information, 608.2h) — nothing is targeted, so "the creature" is the trigger's.
* "If it entered from your library or was cast from your library, draw two cards instead." (Fblthp, the Lost): where it came from (400.7: a permanent spell
  enters from the stack, so a cast from the library is the other half).
* "Whenever one or more opponents lose life, you may cast target instant or sorcery card from your graveyard. If that spell would be put into your graveyard,
  exile it instead. Do this only once each turn." (Emet-Selch of the Third Seat): the trigger is once per batch of life lost at the same time (603.2c).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import build, card_named, check, life, mana, put, reloaded, to_hand
from tests.wave35c_kit import cast_from_hand, repository

FULL = ["Anax, Hardened in the Forge", "Fblthp, the Lost"]


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", FULL)
def test_the_promoted_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def satyrs(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == "Satyr" and c.owner == pid and c.zone == f"{pid}:battlefield"]


@pytest.mark.parametrize("counters, made", [(0, 1), (1, 1), (2, 2)])
def test_anax_makes_two_tokens_for_a_creature_that_had_power_four_or_more(cards, counters, made):
    """Grizzly Bears (2/2) with 0, 1 or 2 +1/+1 counters dies: power 2, 3 or 4 immediately before it died."""
    s = build(cards, ["Anax, Hardened in the Forge", "Grizzly Bears", "Murder"], [])
    put(s, "Anax, Hardened in the Forge")
    bears = put(s, "Grizzly Bears")
    if counters:
        act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=counters)
    mana(s, "p1", B=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Murder").id, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard" and len(satyrs(s)) == made
    s = reloaded(s)
    check(s)


def test_anax_does_nothing_for_a_token_or_an_opponents_creature(cards):
    s = build(cards, ["Anax, Hardened in the Forge", "Murder"], ["Grizzly Bears"])
    put(s, "Anax, Hardened in the Forge")
    theirs = put(s, "Grizzly Bears", "p2")
    mana(s, "p1", B=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Murder").id, targets=[theirs.id])
    settle(s)
    assert s.state.cards[theirs.id].zone == "p2:graveyard" and not satyrs(s)
    check(s)


def hand(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


def test_fblthp_draws_one_when_it_is_cast_from_the_hand(cards):
    s = build(cards, ["Fblthp, the Lost"], [])
    mana(s, "p1", U=2)
    before = hand(s)
    cast_from_hand(s, "Fblthp, the Lost")  # to hand and back out: the hand is as it was, plus the one card it draws
    assert hand(s) == before + 1
    s = reloaded(s)
    check(s)


def test_fblthp_draws_two_when_it_entered_from_the_library(cards):
    s = build(cards, ["Fblthp, the Lost", "Genesis Wave"], [])
    mana(s, "p1", G=5)
    before = hand(s)
    cast_from_hand(s, "Genesis Wave", x_value=2)  # reveals the top two cards: Fblthp (MV 2) enters from the library
    assert card_named(s, "Fblthp, the Lost").zone == "p1:battlefield" and hand(s) == before + 2
    s = reloaded(s)
    check(s)


def test_fblthp_cast_from_the_library_draws_two(cards):
    """601.2a: cast from the top of the library (Future Sight): "was cast from your library"."""
    s = build(cards, ["Fblthp, the Lost", "Future Sight"], [])
    put(s, "Future Sight")
    fblthp = card_named(s, "Fblthp, the Lost")
    act(s, "p1", type="move", card_ids=[fblthp.id], to={"player": "p1", "zone": "library"}, position="top")
    mana(s, "p1", U=2)
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=fblthp.id)
    settle(s)
    assert s.state.cards[fblthp.id].zone == "p1:battlefield" and hand(s) == before + 2
    s = reloaded(s)
    check(s)


def test_emet_selch_casts_a_spell_from_the_graveyard_and_it_is_exiled_after(cards):
    """603.2c: "Whenever one or more opponents lose life" — Bob loses 2 to Sign in Blood: the trigger lets Alice cast Lightning Bolt from her graveyard, and
    614.1a: "If that spell would be put into your graveyard, exile it instead". "Do this only once each turn": a second loss that turn casts nothing."""
    s = build(cards, ["Emet-Selch of the Third Seat", "Lightning Bolt", "Sign in Blood", "Sign in Blood"], [])  # (the first Sign in Blood is also a target)
    put(s, "Emet-Selch of the Third Seat")
    gy_bolt = card_named(s, "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[gy_bolt.id], to={"zone": "graveyard"})
    mana(s, "p1", B=2, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Sign in Blood").id, targets=["p2"])

    def play_out():
        asked = []
        for _ in range(30):
            d = s.state.rules.decision
            if d is not None:
                asked.append(d.prompt)
                pick = next((o.id for o in d.options if o.label in ("Lightning Bolt", "Bob")), None) or d.options[0].id
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
            elif s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
            else:
                return asked
        raise AssertionError("never settled")

    assert any("Choose a spell to cast" in p for p in play_out())
    assert life(s, "p2") == 40 - 2 - 3 and s.state.cards[gy_bolt.id].zone == "p1:exile"
    s = reloaded(s)
    mana(s, "p1", B=2)  # a second loss of life this turn: the trigger is on the stack, and the instruction is not done again
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Sign in Blood").id, targets=["p2"])
    assert not any("Choose a spell to cast" in p for p in play_out())
    assert life(s, "p2") == 40 - 2 - 3 - 2
    check(s)
