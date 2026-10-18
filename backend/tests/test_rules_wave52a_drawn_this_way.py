"""Wave 52A: "drawn this way" (CR 2026-09-25), real Oracle text (tests/fixtures/wave52a_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 121.2 / 608.2c: the cards a draw instruction made players draw, counted when a later instruction of the same ability reads them: Cut a Deal - "Each opponent draws a card, then
  you draw a card for each opponent who drew a card this way." (an opponent who couldn't draw, 121.2a / 101.2: Narset, Parter of Veils, drew none this way); Struggle for Project
  Purity (Brotherhood) - "each opponent draws a card. You draw a card for each card drawn this way."; Communal Brewing - an ingredient counter for each card drawn this way;
  Ancient Excavation - "Draw cards equal to the number of cards in your hand, then discard a card for each card drawn this way."
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, to_hand
from tests.wave52a_kit import build_n, open_repo

DEAL, STRUGGLE, BREWING, EXCAVATION, NARSET = "Cut a Deal", "Struggle for Project Purity", "Communal Brewing", "Ancient Excavation", "Narset, Parter of Veils"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [DEAL, STRUGGLE, BREWING, EXCAVATION])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def hand(s, pid):
    return sum(1 for c in s.state.cards.values() if c.zone == f"{pid}:hand")


def cast(s, name, **kw):
    act(s, "p1", type="cast_spell", card_id=card_named(s, name).id, **kw)
    settle(s)


# -- Cut a Deal --------------------------------------------------------------------------------------------------------------------------
def test_cut_a_deal_you_draw_for_each_opponent_who_drew(cards):
    s = build(cards, [DEAL])
    to_hand(s, DEAL)
    mana(s, "p1", W=1, C=2)
    mine, theirs = hand(s, "p1") - 1, hand(s, "p2")
    cast(s, DEAL)
    assert hand(s, "p2") == theirs + 1 and hand(s, "p1") == mine + 1  # one opponent drew, so she draws one
    check(s)


def test_cut_a_deal_an_opponent_who_could_not_draw_gives_no_card(cards):
    s = build_n(cards, [(2, DEAL), NARSET])
    to_hand(s, NARSET)
    mana(s, "p1", U=2, C=1)
    cast(s, NARSET)  # (cast, so it enters with its loyalty counters)
    for c in [x for x in s.state.cards.values() if x.name == DEAL]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, "p1", W=2, C=4)
    mine, theirs = hand(s, "p1") - 1, hand(s, "p2")
    first, second = [x for x in s.state.cards.values() if x.name == DEAL]
    act(s, "p1", type="cast_spell", card_id=first.id)
    settle(s)
    assert hand(s, "p2") == theirs + 1 and hand(s, "p1") == mine + 1
    act(s, "p1", type="cast_spell", card_id=second.id)  # Bob has drawn his one card this turn: Narset stops the second draw
    settle(s)
    assert hand(s, "p2") == theirs + 1 and hand(s, "p1") == mine + 1 - 1  # (the second spell left her hand, and nobody drew this way)
    check(s)


# -- Struggle for Project Purity ---------------------------------------------------------------------------------------------------------
def test_struggle_for_project_purity_brotherhood_you_draw_as_many_as_the_opponents_did(cards):
    s = build(cards, [STRUGGLE])
    to_hand(s, STRUGGLE)
    mana(s, "p1", U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, STRUGGLE).id)
    for _ in range(10):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((o.id for o in d.options if "Brotherhood" in o.label), d.options[0].id)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    stops(s)  # (both players get priority at every step, so the upkeep is a stop)
    to_phase(s, "upkeep", turn=3)
    mine, theirs = hand(s, "p1"), hand(s, "p2")
    settle(s)
    assert hand(s, "p2") == theirs + 1 and hand(s, "p1") == mine + 1
    check(s)


# -- Communal Brewing --------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("opponents,counters", [(["p2"], 2), ([], 1)])
def test_communal_brewing_an_ingredient_counter_for_each_card_drawn(cards, opponents, counters):
    s = build(cards, [BREWING])
    c = to_hand(s, BREWING)
    mana(s, "p1", G=1, C=2)
    theirs = hand(s, "p2")
    act(s, "p1", type="cast_spell", card_id=c.id)
    for _ in range(10):  # the enters trigger asks for its targets
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=opponents if d.min_choices == 0 else [d.options[0].id])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[c.id].counters.get("ingredient", 0) == counters
    assert hand(s, "p2") == theirs + len(opponents)
    check(s)


# -- Ancient Excavation ------------------------------------------------------------------------------------------------------------------
def test_ancient_excavation_discards_a_card_for_each_card_drawn(cards):
    s = build(cards, [EXCAVATION, "Grizzly Bears", "Hill Giant", "Soul Warden"])
    for name in ("Grizzly Bears", "Hill Giant", "Soul Warden"):
        to_hand(s, name)
    c = to_hand(s, EXCAVATION)
    mana(s, "p1", U=1, B=1, C=2)
    h = hand(s, "p1") - 1  # (the spell is on the stack)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert hand(s, "p1") == h  # drew h cards, discarded h cards
    assert sum(1 for x in s.state.cards.values() if x.zone == "p1:graveyard") == h + 1  # (the h discards and the spell)
    check(s)
