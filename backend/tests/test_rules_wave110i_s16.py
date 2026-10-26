"""Wave 110I session 16 (final pass).

* Turtles Forever: 701.23b a hidden zone is searched without having to find (all four, or none); 903.11 nothing comes from outside the game, so only the library is searched;
  four legendary creature cards with different names are revealed (701.20a), an opponent chooses two (they go to hand), the rest stay in the library, shuffled (701.24).
* Battlefield Scrounger: the cost puts three cards from your graveyard on the bottom of your library, in the order chosen (401.4); the Threshold gate is checked before activating, so
  paying down to six cards still resolves (ruling 2022-12-08); only once each turn (602.5b).
* Homura, Human Ascendant: "return it to the battlefield flipped" (710.2, 110.5): the new object enters already flipped (a legendary enchantment, not a creature: "whenever a creature enters"
  does not see it) and its alternative static ability applies.
* Ranar the Ever-Watchful: the first foretell special action each turn costs {0} (702.143a, ruling 2021-06-18: the first card exiled from your hand as part of foretelling), the next ones {2}.
"""
from __future__ import annotations

import pytest

import tests.test_rules_wave110e_cards as base
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import answer, card_db  # noqa: F401  (the fixture)
from tests.test_rules_wave110e_cards import cast as cast_card
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

TURTLES = real("Turtles Forever", "{3}{W}", 4, "Instant",
               "Search your library and/or outside the game for exactly four legendary creature cards you own with different names, then reveal those cards. "
               "An opponent chooses two of them. Put the chosen cards into your hand and shuffle the rest into your library.", None, "W")
LEGENDS = [real(f"Legend{n}", "{1}{W}", 2, "Legendary Creature — Human", "", ("2", "2"), "W") for n in "ABCDE"]
base.EXTRA.extend([TURTLES, *LEGENDS])


def test_turtles_full(cards):
    assert coverage.of_card_data(cards.resolve("Turtles Forever")).level == "FULL"


def _cast(cards, legends):
    s = build(cards, ["Turtles Forever", *(f"Legend{n}" for n in legends)])
    mana(s, W=1, C=3)
    cast_card(s, "Turtles Forever")
    return s


def _find(s, ids):
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None:
            return d
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no decision")


def _lib(s, n):
    return next(c for c in s.state.cards.values() if c.name == f"Legend{n}" and c.owner == "p1")


def test_turtles_opponent_splits_four_found_cards(cards):
    s = _cast(cards, "ABCDE")
    d = _find(s, None)
    assert d.player == "p1" and d.min_choices == 0 and d.max_choices == 4
    found = [_lib(s, n).id for n in "ABCD"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=found)
    d = s.state.rules.decision
    assert d.player == "p2" and d.min_choices == d.max_choices == 2 and {o.id for o in d.options} == set(found)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=found[:2])
    answer(s)
    assert [_lib(s, n).zone for n in "ABCD"] == ["p1:hand", "p1:hand", "p1:library", "p1:library"]
    assert _lib(s, "E").zone == "p1:library"
    check(s)


def test_turtles_wrong_count_is_refused_and_none_is_allowed(cards):
    s = _cast(cards, "ABCDE")
    d = _find(s, None)
    with pytest.raises(ActionError, match="exactly 4"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[_lib(s, n).id for n in "AB"])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    answer(s)
    assert all(_lib(s, n).zone == "p1:library" for n in "ABCDE")
    check(s)


def test_turtles_with_only_three_different_names_finds_those_three(cards):
    s = _cast(cards, "ABC")
    d = _find(s, None)
    assert d.max_choices == 3
    found = [_lib(s, n).id for n in "ABC"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=found)
    d = s.state.rules.decision
    assert d.player == "p2"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=found[1:])
    answer(s)
    assert [_lib(s, n).zone for n in "ABC"] == ["p1:library", "p1:hand", "p1:hand"]
    check(s)


SCROUNGER = real("Battlefield Scrounger", "{3}{G}{G}", 5, "Creature — Centaur",
                 "Threshold — Put three cards from your graveyard on the bottom of your library: This creature gets +3/+3 until end of turn. "
                 "Activate only once each turn and only if there are seven or more cards in your graveyard.", ("3", "3"), "G")
base.EXTRA.append(SCROUNGER)


def test_scrounger_full(cards):
    assert coverage.of_card_data(cards.resolve("Battlefield Scrounger")).level == "FULL"


def _scrounger(cards, in_graveyard):
    s = build(cards, ["Battlefield Scrounger"], forests=12)
    scr = put(s, "Battlefield Scrounger")
    yard = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:in_graveyard]
    act(s, "p1", type="move", card_ids=[c.id for c in yard], to={"zone": "graveyard"})
    return s, scr, [c.id for c in yard]


def test_scrounger_needs_seven_cards_in_the_graveyard(cards):
    s, scr, yard = _scrounger(cards, 6)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=scr.id, ability=0, cost_choices=[{"component": 0, "cards": yard[:3]}])


def test_scrounger_puts_the_chosen_cards_on_the_bottom_in_order_and_pumps_once(cards):
    s, scr, yard = _scrounger(cards, 10)
    pick = [yard[2], yard[0], yard[1]]
    act(s, "p1", type="activate_ability", card_id=scr.id, ability=0, cost_choices=[{"component": 0, "cards": pick}])
    lib = s.state.zones["p1:library"]
    assert len(lib) >= 3 and all(s.state.cards[c].zone == "p1:library" for c in pick)
    assert lib[-3:] == pick  # the order chosen, the last one deepest
    answer(s)
    assert s.state.cards[scr.id].zone == "p1:battlefield"
    from tests.wave9c_kit import pt

    assert pt(s, "Battlefield Scrounger") == (6, 6)
    assert len([c for c in s.state.cards.values() if c.zone == "p1:graveyard"]) == 7
    with pytest.raises(ActionError):  # once each turn: seven cards are still there
        act(s, "p1", type="activate_ability", card_id=scr.id, ability=0, cost_choices=[{"component": 0, "cards": [c for c in s.state.zones["p1:graveyard"][:3]]}])
    check(s)


_HFRONT = "Homura can't block.\nWhen Homura dies, return it to the battlefield flipped."
_HBACK = 'Creatures you control get +2/+2 and have flying and "{R}: This creature gets +1/+0 until end of turn."'
HOMURA = card("Homura, Human Ascendant // Homura's Essence", set_code="t110i", number="H1", mana_cost="{4}{R}{R}", cmc=6.0, layout="flip",
              type_line="Legendary Creature — Human Monk // Legendary Enchantment", power="4", toughness="4", colors=["R"], color_identity=["R"],
              oracle_text=_HFRONT + "\n//\n" + _HBACK,
              card_faces=[{"name": "Homura, Human Ascendant", "mana_cost": "{4}{R}{R}", "type_line": "Legendary Creature — Human Monk", "power": "4", "toughness": "4", "oracle_text": _HFRONT},
                          {"name": "Homura's Essence", "mana_cost": "", "type_line": "Legendary Enchantment", "oracle_text": _HBACK}])
WATCHER = real("Entry Watcher", "{1}{W}", 2, "Enchantment", "Whenever a creature enters, you gain 1 life.", None, "W")
BEAR = real("Bear Cub110I", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G")
KILL = real("Doom Blade110I", "{1}{B}", 2, "Instant", "Destroy target nonblack creature.", None, "B")
base.EXTRA.extend([HOMURA, WATCHER, BEAR, KILL])


def test_homura_full(cards):
    assert coverage.of_card_data({**HOMURA, "faces": HOMURA["card_faces"]}).level == "FULL"


def test_homura_returns_flipped_and_pumps_the_team(cards):
    from app.rules import characteristics as chars
    from app.rules.plan import Plan
    from tests.wave9c_kit import life, pt

    s = build(cards, [HOMURA["name"], "Entry Watcher", "Bear Cub110I", "Doom Blade110I"])
    put(s, "Entry Watcher")
    homura = put(s, HOMURA["name"])
    mana(s, G=1, C=1)
    bear = cast_card(s, "Bear Cub110I")
    answer(s)
    before = life(s, "p1")
    assert before == 41  # control: the Watcher sees a creature enter
    mana(s, B=1, C=1)
    cast_card(s, "Doom Blade110I", [homura.id])
    answer(s)
    new = card_named(s, HOMURA["name"])
    assert new.zone == "p1:battlefield" and new.flipped
    ch = Plan(s.state, "p1", s.cards, None).ch(new)
    assert ch.name == "Homura's Essence" and "Creature" not in ch.types and "Enchantment" in ch.types
    assert life(s, "p1") == before  # it never entered as a creature
    assert pt(s, "Bear Cub110I") == (4, 4) and chars.of(s.state.cards[bear.id], s.cards)
    check(s)


RANAR = real("Ranar the Ever-Watchful", "{2}{W}{U}", 4, "Legendary Creature — Spirit Warrior",
             "Flying, vigilance\nThe first card you foretell each turn costs {0} to foretell.\n"
             "Whenever one or more cards are put into exile from your hand or a spell or ability you control exiles one or more permanents from the battlefield, create a 1/1 white Spirit creature token with flying.",
             ("2", "3"), "UW")
FORE_A = real("Doomskar Oracle", "{2}{W}", 3, "Creature — Human Cleric",
              "Whenever you cast your second spell each turn, you gain 2 life.\nForetell {W} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)",
              ("3", "2"), "W")
FORE_B = real("Cosmos Charger", "{3}{U}", 4, "Creature — Horse Spirit",
              "Flash\nFlying\nForetelling cards from your hand costs {1} less and can be done on any player's turn.\nForetell {2}{U} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)",
              ("3", "3"), "U")
base.EXTRA.extend([RANAR, FORE_A, FORE_B])


def _foretell_ability(s, card):
    from app.rules.plan import Plan

    return next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card.id]).abilities if "foretell" in a.keywords)


def test_ranar_full(cards):
    assert coverage.of_card_data(cards.resolve("Ranar the Ever-Watchful")).level == "FULL"


def test_ranar_only_the_first_foretell_each_turn_is_free(cards):
    from tests.wave9c_kit import zone_of

    s = build(cards, ["Ranar the Ever-Watchful", "Doomskar Oracle", "Cosmos Charger"])
    put(s, "Ranar the Ever-Watchful")
    first, second = to_hand(s, "Doomskar Oracle"), to_hand(s, "Cosmos Charger")
    act(s, "p1", type="activate_ability", card_id=first.id, ability=1)  # no mana at all
    answer(s)
    assert zone_of(s, "Doomskar Oracle") == "p1:foretell"
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=second.id, ability=_foretell_ability(s, second))
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=second.id, ability=_foretell_ability(s, second))
    answer(s)
    assert zone_of(s, "Cosmos Charger") == "p1:foretell"
    check(s)


def test_ranar_resets_each_turn(cards):
    from tests.test_rules_conditionals import until
    from tests.wave9c_kit import zone_of

    s = build(cards, ["Ranar the Ever-Watchful", "Doomskar Oracle", "Cosmos Charger"])
    put(s, "Ranar the Ever-Watchful")
    first = to_hand(s, "Doomskar Oracle")
    act(s, "p1", type="activate_ability", card_id=first.id, ability=1)
    answer(s)
    until(s, lambda s: s.state.turn.number >= 3 and s.state.turn.active_player == "p1" and s.state.turn.phase == "main1")
    second = to_hand(s, "Cosmos Charger")
    act(s, "p1", type="activate_ability", card_id=second.id, ability=_foretell_ability(s, second))  # a new turn: free again
    answer(s)
    assert zone_of(s, "Cosmos Charger") == "p1:foretell"
    check(s)
