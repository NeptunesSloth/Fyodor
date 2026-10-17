"""Wave 45A: "If you put a [kind] into your hand / onto the battlefield this way, ..." (CR 2026-09-25), real Oracle text
(tests/fixtures/wave45a_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 608.2c, 400.7: Spelunking [743] ("If you put a Cave onto the battlefield this way, you gain 4 life."), Town Greeter [7699] ("If you put a Town card into your hand
  this way, you gain 2 life."), Chrome Courier [16603] ("If you put an artifact card into your hand this way, you gain 3 life."), Sidequest: Catch a Fish [8045] ("If you
  put a card into your hand this way, create a Food token and transform this enchantment.") - the card the earlier instruction of the same ability moved, judged as
  the card it is where it went.
* 614.1d: Spelunking's "Lands you control enter untapped." also applies to the land its own ability puts onto the battlefield (the enchantment is already there).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, card_named, check, mana, to_hand, zone_of
from tests.wave43b_kit import on_top
from tests.wave45a_kit import FULL, life, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def cast_to_decision(s, name):
    """Cast it and let the stack resolve up to the first question (the pick), not past it."""
    act(s, "p1", type="cast_spell", card_id=card_named(s, name).id)
    for _ in range(20):
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")


def pick(s, name, pid="p1"):
    """Answer the open decision by choosing the option that is this card (a card of that name among the options)."""
    d = s.state.rules.decision
    wanted = [o.id for o in d.options if s.state.cards.get(o.id) is not None and s.state.cards[o.id].name == name]
    assert wanted, [o.label for o in d.options]
    act(s, pid, type="choose", decision_id=d.id, option_ids=wanted[:1])


@pytest.mark.parametrize("land, gained", [("Hidden Volcano", 4), ("Forest", 0)])
def test_spelunking_gains_4_life_for_a_cave_only_and_the_land_enters_untapped(cards, land, gained):
    s = build(cards, ["Spelunking", "Hidden Volcano"], [], forests=30)
    to_hand(s, "Spelunking")
    mana(s, G=1, C=2)
    in_hand = to_hand(s, land)
    cast_to_decision(s, "Spelunking")
    pick(s, land)
    settle(s)
    assert s.state.cards[in_hand.id].zone == "p1:battlefield" and not s.state.cards[in_hand.id].tapped  # (a Cave enters tapped by its own text: Spelunking's effect wins)
    assert life(s, "p1") == 40 + gained
    check(s)


@pytest.mark.parametrize("take, gained", [("Insomnia, Crown City", 2), ("Forest", 0)])
def test_town_greeter_gains_2_life_only_for_a_town_card(cards, take, gained):
    s = build(cards, ["Town Greeter", "Insomnia, Crown City"], [], forests=30)
    to_hand(s, "Town Greeter")
    on_top(s, "Insomnia, Crown City")
    mana(s, G=1, C=1)
    cast_to_decision(s, "Town Greeter")
    pick(s, take)
    settle(s)
    assert life(s, "p1") == 40 + gained
    assert zone_of(s, "Insomnia, Crown City") == ("p1:hand" if take != "Forest" else "p1:graveyard")
    check(s)


@pytest.mark.parametrize("take, gained", [("Sol Ring", 3), ("Forest", 0)])
def test_chrome_courier_gains_3_life_only_for_an_artifact_card_put_into_hand(cards, take, gained):
    s = build(cards, ["Chrome Courier", "Sol Ring"], [], forests=30)
    to_hand(s, "Chrome Courier")
    on_top(s, "Sol Ring")
    mana(s, W=1, U=1, C=1)
    cast_to_decision(s, "Chrome Courier")
    pick(s, take)
    settle(s)
    assert life(s, "p1") == 40 + gained
    check(s)
