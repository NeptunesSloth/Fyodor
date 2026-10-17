"""Wave 43B (triggers): the most-played triggered abilities one line short of FULL (CR 2026-09-25), real Oracle text (tests/fixtures/wave43b_cards.json).
Every scenario checks the replay and a save and a load.

* 608.2h: "Whenever another creature enters, its controller may draw a card if its power is greater than each other creature's power." (Selvala, Heart of the Wilds [411]) - strictly
  greater than every other creature's, anyone's; the creature's controller decides, not Selvala's.
* 122.6, 603.8: "When the twelfth hour counter is put on this artifact, shuffle your hand and graveyard into your library, then draw seven cards. Exile this artifact." (Midnight Clock [648]).
* 205.3m: "Whenever a creature you control attacks, it gets +1/+0 until end of turn for each other attacking creature that shares a creature type with it." (Shared Animosity [686]).
* 701.23: "Whenever an opponent searches their library, you gain 1 life and draw a card." (Archivist of Oghma [696]), "…put a +1/+1 counter on Wan Shi Tong and draw a card." (Wan Shi Tong,
  Librarian [1240]) - a search of their OWN library, nothing found or not; "If an opponent would search a library, that player searches the top four cards of that library instead."
  (Aven Mindcensor [1255]).
* 701.20a, 110.2: "Whenever this creature attacks, defending player reveals the top card of their library. If it's a land card, that player puts it into their hand." (Goblin Guide).
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, ask, attack, next_turn, settle
from tests.test_rules_wave43b_mana import to_bobs_main
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand, zone_of
from tests.wave43b_kit import library, life, names_in, on_top, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


def hand(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


def cast(s, name, pid="p1", **kw):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:hand")
    act(s, pid, type="cast_spell", card_id=c.id, **kw)


# ---- Selvala, Heart of the Wilds [411] ------------------------------------------------------------------------------------------------------------------
def test_selvala_lets_the_controller_of_a_creature_with_the_greatest_power_draw(cards):
    s = build(cards, ["Selvala, Heart of the Wilds", "Hill Giant", "Grizzly Bears"], ["Shivan Dragon"], forests=8)
    put(s, "Selvala, Heart of the Wilds")  # 2/3
    to_hand(s, "Hill Giant")
    to_hand(s, "Grizzly Bears")
    h = hand(s)
    mana(s, R=1, C=3)
    cast(s, "Hill Giant")
    d = ask(s)
    assert d.player == "p1"  # its controller (here also Selvala's): 3 power is more than Selvala's 2
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    settle(s)
    assert hand(s) == h - 1 + 1  # Hill Giant left the hand, one card drawn
    mana(s, G=1, C=1)
    cast(s, "Grizzly Bears")
    settle(s)
    assert hand(s) == h - 1 + 1 - 1 and zone_of(s, "Grizzly Bears") == "p1:battlefield"  # 2 power does not beat the Giant's 3: no question, no card
    check(s)


def test_selvala_gives_the_card_to_the_opponent_whose_creature_is_bigger(cards):
    s = build(cards, ["Selvala, Heart of the Wilds", "Hill Giant"], ["Shivan Dragon"], forests=8, islands=8)
    put(s, "Selvala, Heart of the Wilds")
    put(s, "Hill Giant")
    to_bobs_main(s)
    to_hand(s, "Shivan Dragon", "p2")
    bob = hand(s, "p2")
    mana(s, "p2", R=2, C=4)
    cast(s, "Shivan Dragon", "p2")
    d = ask(s)
    assert d.player == "p2"  # its controller decides (608.2d), not Selvala's: Bob
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["yes"])
    settle(s)
    assert hand(s, "p2") == bob - 1 + 1 and hand(s) == hand(s)  # 5 power beats the Giant's 3
    check(s)


# ---- Midnight Clock [648] --------------------------------------------------------------------------------------------------------------------------------
def test_midnight_clock_shuffles_hand_and_graveyard_in_draws_seven_and_exiles_itself_on_the_twelfth_counter(cards):
    s = build(cards, ["Midnight Clock", "Shock", "Hill Giant", "Elvish Mystic", "Wall of Omens"], forests=12)
    clock = put(s, "Midnight Clock")
    act(s, "p1", type="set_counter", card_id=clock.id, kind="hour", value=10)
    for n in ("Shock", "Hill Giant"):
        to_hand(s, n)
    act(s, "p1", type="move", card_ids=[card_named(s, "Elvish Mystic").id], to={"player": "p1", "zone": "graveyard"})
    mana(s, U=1, C=2)
    activate(s, "p1", clock, "hour counter")
    settle(s)
    assert s.state.cards[clock.id].counters.get("hour") == 11 and zone_of(s, "Midnight Clock") == "p1:battlefield"  # the eleventh: nothing yet
    assert names_in(s, "hand") == ["Hill Giant", "Shock"]
    mana(s, U=1, C=2)
    activate(s, "p1", clock, "hour counter")
    settle(s)
    assert zone_of(s, "Midnight Clock") == "p1:exile"  # "Exile this artifact."
    assert names_in(s, "graveyard") == [] and len(names_in(s, "hand")) == 7  # hand and graveyard shuffled into the library, seven new cards drawn
    check(s)


def test_midnight_clock_does_not_trigger_again_for_a_later_counter(cards):
    s = build(cards, ["Midnight Clock", "Shock"], forests=12)
    clock = put(s, "Midnight Clock")
    act(s, "p1", type="set_counter", card_id=clock.id, kind="hour", value=12)  # (already twelve: not "the twelfth hour counter" being put on)
    to_hand(s, "Shock")
    mana(s, U=1, C=2)
    activate(s, "p1", clock, "hour counter")
    settle(s)
    assert s.state.cards[clock.id].counters.get("hour") == 13 and zone_of(s, "Midnight Clock") == "p1:battlefield" and names_in(s, "hand") == ["Shock"]
    check(s)


# ---- Shared Animosity [686] ------------------------------------------------------------------------------------------------------------------------------
def test_shared_animosity_counts_the_other_attackers_that_share_a_creature_type(cards):
    s = build(cards, ["Shared Animosity", "Goblin Piker", "Goblin Guide", "Elvish Mystic"], ["Wall of Omens"])
    put(s, "Shared Animosity")
    piker, guide, mystic = put(s, "Goblin Piker"), put(s, "Goblin Guide"), put(s, "Elvish Mystic")
    next_turn(s)
    attack(s, piker, guide, mystic)
    settle(s)
    assert pt(s, "Goblin Piker") == (3, 1) and pt(s, "Goblin Guide") == (3, 2)  # each Goblin: +1/+0 for the OTHER attacking Goblin
    assert pt(s, "Elvish Mystic") == (1, 1)  # no other Elf attacks
    check(s)


def test_shared_animosity_gives_nothing_to_a_lone_attacker(cards):
    s = build(cards, ["Shared Animosity", "Goblin Piker", "Goblin Guide"], ["Wall of Omens"])
    put(s, "Shared Animosity")
    piker = put(s, "Goblin Piker")
    put(s, "Goblin Guide")
    next_turn(s)
    attack(s, piker)
    settle(s)
    assert pt(s, "Goblin Piker") == (2, 1)  # the other Goblin isn't attacking
    check(s)


# ---- Archivist of Oghma [696], Wan Shi Tong, Librarian [1240] --------------------------------------------------------------------------------------------
def search_table(cards, mine):
    s = build(cards, [*mine, "Rampant Growth"], ["Rampant Growth"], forests=8, islands=8)
    for n in mine:
        put(s, n)
    return s


def bob_searches(s):
    to_bobs_main(s)
    to_hand(s, "Rampant Growth", "p2")
    mana(s, "p2", G=1, C=1)
    cast(s, "Rampant Growth", "p2")
    d = ask(s)
    assert d.player == "p2"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)


def test_archivist_of_oghma_gains_life_and_draws_when_an_opponent_searches_their_library(cards):
    s = search_table(cards, ["Archivist of Oghma"])
    life0, hand0 = life(s), hand(s)
    bob_searches(s)
    assert life(s) == life0 + 1 and hand(s) == hand0 + 1
    check(s)


def test_archivist_of_oghma_ignores_its_controllers_own_search(cards):
    s = search_table(cards, ["Archivist of Oghma"])
    to_hand(s, "Rampant Growth")
    life0, hand0 = life(s), hand(s)
    mana(s, G=1, C=1)
    cast(s, "Rampant Growth")
    d = ask(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    assert life(s) == life0 and hand(s) == hand0 - 1  # only the Rampant Growth left her hand
    check(s)


def test_wan_shi_tong_grows_and_draws_when_an_opponent_searches(cards):
    s = search_table(cards, ["Wan Shi Tong, Librarian"])
    hand0 = hand(s)
    bob_searches(s)
    assert s.state.cards[card_named(s, "Wan Shi Tong, Librarian").id].counters.get("+1/+1") == 1 and hand(s) == hand0 + 1
    check(s)


# ---- Aven Mindcensor [1255] ------------------------------------------------------------------------------------------------------------------------------
def test_aven_mindcensor_limits_an_opponents_search_to_the_top_four_cards(cards):
    s = build(cards, ["Aven Mindcensor"], ["Rampant Growth", "Mountain"], forests=8, islands=8)
    put(s, "Aven Mindcensor")
    mountain = on_top(s, "Mountain", "p2")
    for c in [c for c in library(s, "p2") if s.state.cards[c].name == "Island"][:5]:  # five Islands above the Mountain; Bob draws one, so it is the fifth card
        act(s, "p2", type="move", card_ids=[c], to={"player": "p2", "zone": "library"}, position="top")
    to_bobs_main(s)
    to_hand(s, "Rampant Growth", "p2")
    mana(s, "p2", G=1, C=1)
    cast(s, "Rampant Growth", "p2")
    d = ask(s)
    assert d.player == "p2" and len(d.options) == 4 and all(o.label == "Island" for o in d.options)  # the Mountain, fifth from the top, isn't in the search
    assert mountain.id not in [o.id for o in d.options]
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    assert names_in(s, "battlefield", "p2") == ["Island"]
    check(s)


def test_without_aven_mindcensor_the_whole_library_is_searched(cards):
    s = build(cards, [], ["Rampant Growth", "Mountain"], forests=8, islands=8)
    on_top(s, "Mountain", "p2")
    for c in [c for c in library(s, "p2") if s.state.cards[c].name == "Island"][:5]:
        act(s, "p2", type="move", card_ids=[c], to={"player": "p2", "zone": "library"}, position="top")
    to_bobs_main(s)
    to_hand(s, "Rampant Growth", "p2")
    mana(s, "p2", G=1, C=1)
    cast(s, "Rampant Growth", "p2")
    d = ask(s)
    assert len(d.options) == 8  # seven Islands (Bob drew the eighth) and the Mountain
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    check(s)


# ---- Goblin Guide: "defending player reveals the top card of their library. If it's a land card, that player puts it into their hand." -----------------
def test_goblin_guide_gives_the_defending_player_a_revealed_land_and_leaves_other_cards(cards):
    s = build(cards, ["Goblin Guide"], ["Lightning Bolt"], islands=8)
    guide = put(s, "Goblin Guide")
    on_top(s, "Lightning Bolt", "p2")
    attack(s, guide)
    settle(s)
    assert hand(s, "p2") == 0 and s.state.cards[library(s, "p2")[0]].name == "Lightning Bolt"  # not a land card: it stays on top
    check(s)


def test_goblin_guide_puts_a_revealed_land_into_the_defenders_hand_not_the_attackers(cards):
    s = build(cards, ["Goblin Guide"], [], islands=8)
    guide = put(s, "Goblin Guide")
    attack(s, guide)
    settle(s)
    assert hand(s, "p2") == 1 and names_in(s, "hand", "p2") == ["Island"] and hand(s) == 0
    check(s)
