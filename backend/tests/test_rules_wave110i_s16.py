"""Wave 110I session 16 (final pass).

* Turtles Forever: 701.23b a hidden zone is searched without having to find (all four, or none); 903.11 nothing comes from outside the game, so only the library is searched;
  four legendary creature cards with different names are revealed (701.20a), an opponent chooses two (they go to hand), the rest stay in the library, shuffled (701.24).
* Battlefield Scrounger: the cost puts three cards from your graveyard on the bottom of your library, in the order chosen (401.4); the Threshold gate is checked before activating, so
  paying down to six cards still resolves (ruling 2022-12-08); only once each turn (602.5b).
* Homura, Human Ascendant: "return it to the battlefield flipped" (710.2, 110.5): the new object enters already flipped (a legendary enchantment, not a creature: "whenever a creature enters"
  does not see it) and its alternative static ability applies.
* Ranar the Ever-Watchful: the first foretell special action each turn costs {0} (702.143a, ruling 2021-06-18: the first card exiled from your hand as part of foretelling), the next ones {2}.
* Lich: 119.3/614.12 the life total is lost as it enters (and you don't lose at 0); 614.1a a life gain (spell, or lifelink damage 702.15) draws that many cards instead; damage dealt to you
  makes you sacrifice that many nontoken permanents, and you lose the game when you can't (rulings 2004-10-04, 2010-08-15).
* Saruman of Many Colors: ward "Discard an enchantment, instant, or sorcery card" is one cost (702.21a); the second spell each turn mills each opponent two, and only if a card was milled (603.12 reflexive
  trigger) exiles an enchantment, instant or sorcery card with mana value up to that spell's from an opponent's graveyard; its copy may be cast free (707.12, 608.2g, ruling 2023-06-16).
* Merseine: "Pay enchanted creature's mana cost" is the enchanted creature's own mana cost, colored symbols included (ruling 2004-10-04; 202.1), activatable only by that creature's controller (602.2),
  at instant speed, as often as they can pay (a net counter each time).
* Draugr Necromancer: an opponent's nontoken creature that would die is exiled with an ice counter, and its controller may cast spells from among cards in exile their opponents own with ice
  counters, spending mana from snow sources as though it were mana of any color (609.4b, ruling 2021-02-05: only snow-source mana, a spell still follows the normal rules).
* Haldan, Avid Arcanist (with Pako's fetch counters): lands and noncreature spells from cards you exiled with fetch counters, mana of any color (305.1, 601.3, rulings 2020-04-17).
* Jetfire, Ingenious Scientist: removing X +1/+1 counters from among your artifacts (118.3) makes the target player add X {C} that can't be spent on nonartifact spells (106.6a), then Jetfire converts (701.28-style, 712).
* Mavinda, Students' Advocate: the cast permission from the graveyard (this turn, only once each turn, exiled instead of going to the graveyard) costs {8} more unless the spell targets a creature
  you control (601.2f: counted after the targets are chosen, 601.2c).
* Leori, Sparktouched Hunter: the chosen planeswalker type (205.3j) makes the delayed trigger copy each ability its controller activates of a planeswalker of that type until end of turn (707.10, 603.7); the copy
  changes no loyalty (rulings 2023-07-28), planeswalkers of other types are not copied.
* Quicksilver Elemental: "gains all activated abilities of target creature until end of turn" (113.10, 611.2a: the abilities it has at resolution, written for "this permanent"), and its own abilities may
  be paid with blue mana as though it were mana of any color (609.4b).
* Grell Philosopher: each Horror you control gains all activated abilities of the target artifact an opponent controls; those abilities (only) may be paid with blue mana as though any color.
* Panglacial Wurm: while you search your own library you may cast it from there, paying its mana cost (601.3, 608.2g); the cast comes before any card is found, the search then goes on and the Wurm waits on the
  stack above the search (rulings 2006-07-15); declining or a search of someone else's library offers nothing.
* Shaman's Trance: the other players can't play lands or cast spells from their graveyards this turn (101.2); the caster may play lands and cast spells from other players' graveyards, and those cards count as in
  their own graveyard for what applies to it (rulings 2004-10-04: flashback works; abilities of those cards stay unusable).
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
from tests.test_rules_wave110e_s11 import _three
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


LICH = real("Lich", "{B}{B}{B}{B}", 4, "Enchantment",
            "As this enchantment enters, you lose life equal to your life total.\nYou don't lose the game for having 0 or less life.\nIf you would gain life, draw that many cards instead.\n"
            "Whenever you're dealt damage, sacrifice that many nontoken permanents. If you can't, you lose the game.\n"
            "When this enchantment is put into a graveyard from the battlefield, you lose the game.", None, "B")
KISS = real("Vampire's Kiss", "{1}{B}", 2, "Sorcery",
            "Target player loses 2 life and you gain 2 life. Create two Blood tokens. (They're artifacts with \"{1}, {T}, Discard a card, Sacrifice this token: Draw a card.\")", None, "B")
VAMP = real("Vampire of the Dire Moon", "{B}", 1, "Creature — Vampire",
            "Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\nLifelink (Damage dealt by this creature also causes you to gain that much life.)", ("1", "1"), "B")
PREY = real("Prey Upon", "{G}", 1, "Sorcery", "Target creature you control fights target creature you don't control. (Each deals damage equal to its power to the other.)", None, "G")
base.EXTRA.extend([LICH, KISS, VAMP, PREY])


def test_lich_full(cards):
    assert coverage.of_card_data(cards.resolve("Lich")).level == "FULL"


def _lich(cards, extra=()):
    s = _three(cards, ["Lich", "Vampire's Kiss", "Vampire of the Dire Moon", "Prey Upon", *extra])
    mana(s, B=4)
    cast_card(s, "Lich")
    answer(s)
    return s


def test_lich_sets_life_to_zero_and_survives(cards):
    from tests.wave9c_kit import life

    s = _lich(cards)
    assert life(s, "p1") == 0 and card_named(s, "Lich").zone == "p1:battlefield"
    check(s)


def test_lich_draws_instead_of_gaining_life(cards):
    from tests.wave9c_kit import life

    s = _lich(cards)
    hand = len(s.state.zones["p1:hand"])
    mana(s, B=2)
    cast_card(s, "Vampire's Kiss", ["p2"])  # you gain 2 life: draw 2 instead
    answer(s)
    assert life(s, "p1") == 0 and life(s, "p2") == 38
    assert len(s.state.zones["p1:hand"]) == hand + 2  # two cards came in (the Kiss itself went to hand and left again)
    check(s)


def test_lich_lifelink_damage_draws_instead(cards):
    from tests.wave9c_kit import life

    s = _lich(cards, ["Bear Cub110I"])
    mana(s, B=1)
    cast_card(s, "Vampire of the Dire Moon")
    answer(s)
    hand = len(s.state.zones["p1:hand"])
    mana(s, G=1)
    bear = next(c for c in s.state.cards.values() if c.owner == "p2" and c.name == "Test Giant")
    act(s, "p2", type="move", card_ids=[bear.id], to={"player": "p2", "zone": "battlefield"})
    cast_card(s, "Prey Upon", [card_named(s, "Vampire of the Dire Moon").id, bear.id], target_counts=[1, 1])
    answer(s)
    assert life(s, "p1") == 0 and len(s.state.zones["p1:hand"]) == hand + 1  # the 1 lifelink damage drew a card
    check(s)


def _forests(s, n):
    ids = [c.id for c in s.state.cards.values() if c.name == "Mountain" and c.owner == "p1" and c.zone == "p1:library"][:n]
    assert len(ids) == n
    act(s, "p1", type="move", card_ids=ids, to={"player": "p1", "zone": "battlefield"})
    return ids


def _bolt_alice(s):
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Bolt").id, targets=["p1"])  # Alice bolts herself: 3 damage dealt to her


def test_lich_damage_sacrifices_that_many_nontoken_permanents(cards):
    s = _lich(cards, ["Test Bolt"])
    lands = _forests(s, 4)
    _bolt_alice(s)
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:
            assert d.player == "p1" and d.min_choices == d.max_choices == 3  # 3 damage: 3 nontoken permanents
            act(s, "p1", type="choose", decision_id=d.id, option_ids=lands[:3])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert [s.state.cards[c].zone for c in lands] == ["p1:graveyard"] * 3 + ["p1:battlefield"]
    assert card_named(s, "Lich").zone == "p1:battlefield" and "p1" not in s.state.rules.lost
    check(s)


def test_lich_loses_the_game_when_it_cannot_sacrifice_that_many(cards):
    s = _lich(cards, ["Test Bolt"])
    _forests(s, 1)  # Lich and one land: two nontoken permanents for 3 damage
    _bolt_alice(s)
    answer(s)
    assert "p1" in s.state.rules.lost
    check(s)


SARUMAN = real("Saruman of Many Colors", "{3}{W}{U}{B}", 6, "Legendary Creature — Avatar Wizard",
               "Ward—Discard an enchantment, instant, or sorcery card.\nWhenever you cast your second spell each turn, each opponent mills two cards. When one or more cards are milled this way, exile target "
               "enchantment, instant, or sorcery card with equal or lesser mana value than that spell from an opponent's graveyard. Copy the exiled card. You may cast the copy without paying its mana cost.",
               ("5", "4"), "WUB")
base.EXTRA.append(SARUMAN)


def test_saruman_full(cards):
    assert coverage.of_card_data(cards.resolve("Saruman of Many Colors")).level == "FULL"


def test_saruman_ward_cost_is_one_discard_of_three_types(cards):
    from app.rules import triggers
    from app.rules.plan import Plan

    s = build(cards, ["Saruman of Many Colors"])
    ch = Plan(s.state, "p1", s.cards, None).ch(card_named(s, "Saruman of Many Colors"))
    assert triggers.ward_costs(ch) == ["Discard an enchantment or instant or sorcery card"]


def _saruman(cards, bob_library_islands=10):
    s = build(cards, ["Saruman of Many Colors", "Test Bolt", "Vampire of the Dire Moon"], ["Test Bolt", "Vampire's Kiss"], islands=bob_library_islands)
    put(s, "Saruman of Many Colors")
    for n in ("Test Bolt", "Vampire's Kiss"):
        act(s, "p2", type="move", card_ids=[card_named(s, n, "p2").id], to={"zone": "graveyard"})
    mana(s, R=1)
    cast_card(s, "Test Bolt", ["p2"])
    answer(s)
    s.before = len(s.state.zones["p2:library"])  # type: ignore[attr-defined]
    mana(s, B=1)
    cast_card(s, "Vampire of the Dire Moon")
    return s


def _drive(s, pick):
    """Resolve everything, answering each decision with ``pick(decision)`` (a list of option ids)."""
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick(d))
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def _label(d, name):
    return [o.id for o in d.options if o.label == name]


def test_saruman_second_spell_mills_and_exiles_a_cheap_enough_card_to_copy(cards):
    from tests.wave9c_kit import life

    s = _saruman(cards)
    seen = []

    def pick(d):
        seen.append((d.kind, [o.label for o in d.options]))
        if d.kind == "choose_cards":  # cast the copy: yes
            return [d.options[0].id]
        return _label(d, "Bob") or [d.options[0].id]

    _drive(s, pick)
    assert seen[0] == ("choose_one", ["Test Bolt"])  # Vampire's Kiss (mana value 2) is above the second spell's 1
    assert len(s.state.zones["p2:library"]) == s.before - 2
    assert card_named(s, "Test Bolt", "p2").zone == "p2:exile" and card_named(s, "Vampire's Kiss", "p2").zone == "p2:graveyard"
    assert life(s, "p2") == 40 - 3 - 3  # Alice's own Bolt, then the free copy
    check(s)


def test_saruman_nothing_milled_no_reflexive_trigger(cards):
    s = _saruman(cards, bob_library_islands=0)
    assert s.before == 0  # Bob has no library left to mill
    _drive(s, lambda d: [d.options[0].id])
    assert card_named(s, "Test Bolt", "p2").zone == "p2:graveyard"
    check(s)


MERSEINE = real("Merseine", "{2}{U}{U}", 4, "Enchantment — Aura",
                "Enchant creature\nThis Aura enters with three net counters on it.\nEnchanted creature doesn't untap during its controller's untap step if this Aura has a net counter on it.\n"
                "Pay enchanted creature's mana cost: Remove a net counter from this Aura. Only the controller of the enchanted creature may activate this ability.", None, "U")
base.EXTRA.append(MERSEINE)


def test_merseine_full(cards):
    assert coverage.of_card_data(cards.resolve("Merseine")).level == "FULL"


def _merseine(cards):
    s = build(cards, ["Merseine", "Test Bolt"], ["Test Giant"])
    giant = to_hand(s, "Test Giant", "p2")
    act(s, "p2", type="move", card_ids=[giant.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, U=2, C=2)
    cast_card(s, "Merseine", [giant.id])
    answer(s)
    return s, giant


def _bob_priority(s):
    """Alice puts a Test Bolt on the stack and passes: Bob has priority with the stack not empty."""
    act(s, "p2", type="set_prefs", full_control=True)  # Bob is stopped at every priority
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Bolt").id, targets=["p1"])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"


def _nets(s):
    return card_named(s, "Merseine").counters.get("net", 0)


def test_merseine_the_creatures_controller_pays_its_mana_cost_for_each_net_counter(cards):
    s, giant = _merseine(cards)
    assert _nets(s) == 3 and s.state.cards[card_named(s, "Merseine").id].attached_to == giant.id
    _bob_priority(s)
    ab = next(a.index for a in __import__("app.rules.plan", fromlist=["Plan"]).Plan(s.state, "p2", s.cards, None).ch(card_named(s, "Merseine")).abilities if a.kind == "activated")
    mana(s, "p2", G=1, C=3)  # {4}{G}: one generic short
    with pytest.raises(ActionError):
        act(s, "p2", type="activate_ability", card_id=card_named(s, "Merseine").id, ability=ab)
    mana(s, "p2", C=1)
    act(s, "p2", type="activate_ability", card_id=card_named(s, "Merseine").id, ability=ab)
    answer(s)
    assert _nets(s) == 2
    check(s)


def test_merseine_its_own_controller_may_not_activate_it(cards):
    s, giant = _merseine(cards)
    mana(s, G=1, C=4)
    ab = next(a.index for a in __import__("app.rules.plan", fromlist=["Plan"]).Plan(s.state, "p1", s.cards, None).ch(card_named(s, "Merseine")).abilities if a.kind == "activated")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=card_named(s, "Merseine").id, ability=ab)
    assert _nets(s) == 3


DRAUGR = real("Draugr Necromancer", "{3}{B}", 4, "Snow Creature — Zombie Cleric",
              "If a nontoken creature an opponent controls would die, exile that card with an ice counter on it instead.\nYou may cast spells from among cards in exile your opponents own with ice counters on them, "
              "and you may spend mana from snow sources as though it were mana of any color to cast those spells.", ("4", "4"), "B")
SNOWFOREST = real("Snow-Covered Forest", "", 0, "Basic Snow Land \u2014 Forest", "({T}: Add {G}.)")
base.EXTRA.extend([DRAUGR, SNOWFOREST])


def test_draugr_full(cards):
    assert coverage.of_card_data(cards.resolve("Draugr Necromancer")).level == "FULL"


def _draugr(cards):
    s = build(cards, ["Draugr Necromancer", "Test Bolt", "Snow-Covered Forest"], ["Vampire of the Dire Moon"])
    put(s, "Draugr Necromancer")
    vamp = put(s, "Vampire of the Dire Moon", "p2")
    mana(s, R=1)
    cast_card(s, "Test Bolt", [vamp.id])
    answer(s)
    return s, vamp


def test_draugr_exiles_the_dying_creature_with_an_ice_counter(cards):
    s, vamp = _draugr(cards)
    c = s.state.cards[vamp.id]
    assert c.zone == "p2:exile" and c.counters.get("ice") == 1
    check(s)


def test_draugr_snow_mana_pays_any_color_but_other_mana_does_not(cards):
    s, vamp = _draugr(cards)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    snow = put(s, "Snow-Covered Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    with pytest.raises(ActionError):  # a plain Forest's {G} can't pay {B}
        act(s, "p1", type="cast_spell", card_id=vamp.id, sources=[forest.id])
    act(s, "p1", type="cast_spell", card_id=vamp.id, sources=[snow.id])  # a Snow-Covered Forest's mana can
    answer(s)
    assert s.state.cards[vamp.id].zone == "p1:battlefield" or any(c.name == "Vampire of the Dire Moon" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    check(s)


HALDAN = real("Haldan, Avid Arcanist", "{2}{U}", 3, "Legendary Creature — Human Wizard",
              "Partner with Pako, Arcane Retriever (When this creature enters, target player may put Pako into their hand from their library, then shuffle.)\n"
              "You may play lands and cast noncreature spells from among cards you exiled that have fetch counters on them, and you may spend mana as though it were mana of any color to cast those spells.",
              ("1", "4"), "U")
PAKO = real("Pako, Arcane Retriever", "{3}{R}{G}", 5, "Legendary Creature — Elemental Dog",
            "Partner with Haldan, Avid Arcanist\nHaste\nWhenever Pako attacks, exile the top card of each player's library and put a fetch counter on each of them. "
            "Put a +1/+1 counter on Pako for each noncreature card exiled this way.", ("3", "3"), "RG")
base.EXTRA.extend([HALDAN, PAKO])


def test_haldan_and_pako_full(cards):
    for n in ("Haldan, Avid Arcanist", "Pako, Arcane Retriever"):
        assert coverage.of_card_data(cards.resolve(n)).level == "FULL"


def _pako_attack(cards, alice_top, bob_top):
    from tests.wave110b_kit import attack, through_combat

    s = build(cards, ["Haldan, Avid Arcanist", "Pako, Arcane Retriever", "Test Bolt"], ["Vampire of the Dire Moon"])
    put(s, "Haldan, Avid Arcanist")
    pako = put(s, "Pako, Arcane Retriever")
    for who, name in (("p1", alice_top), ("p2", bob_top)):
        c = next(x for x in s.state.cards.values() if x.name == name and x.owner == who)
        act(s, who, type="move", card_ids=[c.id], to={"player": who, "zone": "library"}, position="top")
    attack(s, pako)
    through_combat(s)
    return s


def test_haldan_casts_a_noncreature_card_and_plays_a_land_exiled_with_fetch_counters(cards):
    from tests.wave9c_kit import life

    s = _pako_attack(cards, "Test Bolt", "Island")
    bolt, island = card_named(s, "Test Bolt"), card_named(s, "Island", "p2")
    assert bolt.zone == "p1:exile" and bolt.counters.get("fetch") == 1 and island.zone == "p2:exile" and island.counters.get("fetch") == 1
    mana(s, G=1)  # {R}: mana of any color
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 40 - 5 - 3  # Pako (3/3 + two counters for the two noncreature cards it exiled) hit for 5, then the Bolt
    act(s, "p1", type="play_land", card_id=island.id)
    assert card_named(s, "Island", "p2").zone == "p1:battlefield"
    check(s)


def test_haldan_cannot_cast_the_exiled_creature(cards):
    s = _pako_attack(cards, "Test Bolt", "Vampire of the Dire Moon")
    vamp = card_named(s, "Vampire of the Dire Moon", "p2")
    assert vamp.zone == "p2:exile" and vamp.counters.get("fetch") == 1
    mana(s, B=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=vamp.id)


_JFRONT = ("More Than Meets the Eye {3}{U} (You may cast this card converted for {3}{U}.)\nFlying\nRemove one or more +1/+1 counters from among artifacts you control: Target player adds that much {C}. "
           "This mana can't be spent to cast nonartifact spells. Convert Jetfire.")
_JBACK = "Living metal (During your turn, this Vehicle is also a creature.)\nFlying\n{U}{U}{U}: Convert Jetfire, then adapt 3. (If it has no +1/+1 counters on it, put three +1/+1 counters on it.)"
JETFIRE = card("Jetfire, Ingenious Scientist // Jetfire, Air Guardian", set_code="t110i", number="J1", layout="transform", mana_cost="{4}{U} // ", cmc=5.0,
               type_line="Legendary Artifact Creature \u2014 Robot // Legendary Artifact \u2014 Vehicle", power="3", toughness="4", colors=["U"], color_identity=["U"],
               keywords=["Flying", "Convert", "More Than Meets the Eye", "Living metal"], oracle_text=_JFRONT + "\n//\n" + _JBACK,
               card_faces=[{"name": "Jetfire, Ingenious Scientist", "mana_cost": "{4}{U}", "type_line": "Legendary Artifact Creature \u2014 Robot", "oracle_text": _JFRONT, "power": "3", "toughness": "4", "colors": ["U"]},
                           {"name": "Jetfire, Air Guardian", "mana_cost": "", "type_line": "Legendary Artifact \u2014 Vehicle", "oracle_text": _JBACK, "power": "4", "toughness": "5", "colors": ["U"]}])
base.EXTRA.append(JETFIRE)
JNAME = JETFIRE["name"]


def test_jetfire_full(cards):
    assert coverage.of_card_data({**JETFIRE, "faces": JETFIRE["card_faces"]}).level == "FULL"


def test_jetfire_counters_become_restricted_colorless_mana_and_it_converts(cards):
    from app.rules.plan import Plan
    from tests.test_rules_contextual_mana_outcomes import pool

    s = build(cards, [JNAME, "Bear Cub110I"])
    jet = put(s, JNAME)
    act(s, "p1", type="counter", card_ids=[jet.id], kind="+1/+1", delta=3)
    ab = next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[jet.id]).abilities if a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=jet.id, ability=ab, x_value=2, targets=["p1"])
    for _ in range(8):
        d = s.state.rules.decision
        if d is not None:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:2])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[jet.id].counters.get("+1/+1") == 1 and s.state.cards[jet.id].face == 1  # two removed, converted
    assert pool(s, "C") == 2
    mana(s, G=1)
    bear = to_hand(s, "Bear Cub110I")
    with pytest.raises(ActionError):  # {1}{G}: the Jetfire {C} can't pay for a nonartifact spell
        act(s, "p1", type="cast_spell", card_id=bear.id)
    mana(s, C=1)  # an ordinary {C} can
    act(s, "p1", type="cast_spell", card_id=bear.id)
    answer(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield" and pool(s, "C") == 2  # the restricted mana is still there
    check(s)


MAVINDA = real("Mavinda, Students' Advocate", "{2}{W}", 3, "Legendary Creature \u2014 Bird Advisor",
               "Flying\n{0}: You may cast target instant or sorcery card from your graveyard this turn. If that spell doesn't target a creature you control, it costs {8} more to cast this way. "
               "If that spell would be put into your graveyard, exile it instead. Activate only once each turn. (You still pay the spell's costs. Timing rules for the spell still apply.)", ("2", "3"), "W")
base.EXTRA.append(MAVINDA)


def test_mavinda_full(cards):
    assert coverage.of_card_data(cards.resolve("Mavinda, Students' Advocate")).level == "FULL"


def _mavinda(cards, spell):
    from app.rules.plan import Plan

    s = build(cards, ["Mavinda, Students' Advocate", spell, "Vampire of the Dire Moon"], ["Test Giant"])
    mav = put(s, "Mavinda, Students' Advocate")
    put(s, "Vampire of the Dire Moon")
    giant = put(s, "Test Giant", "p2")
    target = card_named(s, spell)
    act(s, "p1", type="move", card_ids=[target.id], to={"zone": "graveyard"})
    ab = next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[mav.id]).abilities if a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=mav.id, ability=ab, targets=[target.id])
    answer(s)
    return s, target, giant


def test_mavinda_no_tax_when_the_spell_targets_a_creature_you_control(cards):
    s, prey, giant = _mavinda(cards, "Prey Upon")
    mana(s, G=1)
    vamp = card_named(s, "Vampire of the Dire Moon")
    act(s, "p1", type="cast_spell", card_id=prey.id, targets=[vamp.id, giant.id], target_counts=[1, 1])
    answer(s)
    assert s.state.cards[prey.id].zone.endswith(":exile")  # exiled instead of the graveyard
    check(s)


def test_mavinda_charges_8_more_when_it_does_not(cards):
    from tests.wave9c_kit import life

    s, bolt, _ = _mavinda(cards, "Test Bolt")
    mana(s, R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    mana(s, C=8)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 37 and s.state.cards[bolt.id].zone.endswith(":exile")
    check(s)


LEORI = real("Leori, Sparktouched Hunter", "{U}{R}{W}", 3, "Legendary Creature \u2014 Elemental Cat",
             "Flying, vigilance\nWhenever Leori deals combat damage to a player, choose a planeswalker type. Until end of turn, whenever you activate an ability of a planeswalker of that type, copy that ability. "
             "You may choose new targets for the copies.", ("3", "3"), "URW")
AJANI = card("Ajani Goldmane", set_code="t110i", number="A1", mana_cost="{2}{W}{W}", cmc=4.0, type_line="Legendary Planeswalker \u2014 Ajani", loyalty="4", colors=["W"], color_identity=["W"],
             oracle_text="+1: You gain 2 life.\n\u22121: Put a +1/+1 counter on each creature you control. Those creatures gain vigilance until end of turn.\n\u22126: Create a white Avatar creature token. "
                         "It has \"This token's power and toughness are each equal to your life total.\"")
base.EXTRA.extend([LEORI, AJANI])


def test_leori_full(cards):
    assert coverage.of_card_data(cards.resolve("Leori, Sparktouched Hunter")).level == "FULL"


def _leori(cards, pw_type):
    from tests.wave110b_kit import attack

    s = build(cards, ["Leori, Sparktouched Hunter", "Ajani Goldmane"])
    leori = put(s, "Leori, Sparktouched Hunter")
    mana(s, W=2, C=2)
    ajani = cast_card(s, "Ajani Goldmane")  # cast, so it enters with its loyalty counters
    answer(s)
    attack(s, leori)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_one" and "planeswalker type" in d.prompt:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[pw_type])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    return s, ajani


@pytest.mark.parametrize(("pw_type", "gained"), [("Ajani", 4), ("Jace", 2)])
def test_leori_copies_planeswalker_abilities_of_the_chosen_type_only(cards, pw_type, gained):
    from tests.wave9c_kit import life

    s, ajani = _leori(cards, pw_type)
    before = life(s, "p1")
    plus = next(a.index for a in __import__("app.rules.plan", fromlist=["Plan"]).Plan(s.state, "p1", s.cards, None).ch(s.state.cards[ajani.id]).abilities if a.kind == "loyalty")
    act(s, "p1", type="activate_ability", card_id=ajani.id, ability=plus)
    answer(s)
    assert life(s, "p1") == before + gained  # +1: gain 2 life, and its copy gains 2 more only for the chosen type
    assert s.state.cards[ajani.id].counters.get("loyalty") == 5  # 4 + 1: the copy doesn't add loyalty
    check(s)


QUICK = real("Quicksilver Elemental", "{3}{U}{U}", 5, "Creature \u2014 Elemental",
             "{U}: This creature gains all activated abilities of target creature until end of turn. (If any of the abilities use that creature's name, use this creature's name instead.)\n"
             "You may spend blue mana as though it were mana of any color to pay the activation costs of this creature's abilities.", ("3", "4"), "U")
SORC = real("Prodigal Sorcerer", "{2}{U}", 3, "Creature \u2014 Human Wizard Sorcerer", "{T}: This creature deals 1 damage to any target.", ("1", "1"), "U")
SHIVAN = real("Shivan Dragon", "{4}{R}{R}", 6, "Creature \u2014 Dragon", "Flying\n{R}: This creature gets +1/+0 until end of turn.", ("5", "5"), "R")
GRELL = real("Grell Philosopher", "{2}{U}", 3, "Creature \u2014 Horror Wizard",
             "Aberrant Tinkering \u2014 When this creature enters and at the beginning of your upkeep, each Horror you control gains all activated abilities of target artifact an opponent controls until end of turn. "
             "You may spend blue mana as though it were mana of any color to activate those abilities.", ("1", "4"), "U")
SPELLBOMB = real("Pyrite Spellbomb", "{0}", 0, "Artifact", "{R}, Sacrifice this artifact: This artifact deals 2 damage to any target.\n{1}, Sacrifice this artifact: Draw a card.", None)
base.EXTRA.extend([QUICK, SORC, SHIVAN, GRELL, SPELLBOMB])


def test_quicksilver_and_grell_full(cards):
    for n in ("Quicksilver Elemental", "Grell Philosopher"):
        assert coverage.of_card_data(cards.resolve(n)).level == "FULL"


def _activated(s, card, needle, pid="p1"):
    from app.rules.plan import Plan

    return next(a.index for a in Plan(s.state, pid, s.cards, None).ch(s.state.cards[card.id]).abilities if a.kind == "activated" and needle in a.text)


def test_quicksilver_gains_the_activated_abilities_of_the_target_and_pays_with_blue(cards):
    from app.rules.plan import Plan
    from tests.wave9c_kit import life, pt

    s = build(cards, ["Quicksilver Elemental"], ["Prodigal Sorcerer", "Shivan Dragon"])
    q = put(s, "Quicksilver Elemental")
    s.state.rules.controlled_since[q.id].turn = 0
    sorc, dragon = put(s, "Prodigal Sorcerer", "p2"), put(s, "Shivan Dragon", "p2")
    mana(s, U=1)
    act(s, "p1", type="activate_ability", card_id=q.id, ability=_activated(s, q, "gains all activated"), targets=[sorc.id])
    answer(s)
    ping = _activated(s, q, "deals 1 damage")  # "This creature" became Quicksilver Elemental
    act(s, "p1", type="activate_ability", card_id=q.id, ability=ping, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 39 and s.state.cards[q.id].tapped
    mana(s, U=1)
    act(s, "p1", type="activate_ability", card_id=q.id, ability=_activated(s, q, "gains all activated"), targets=[dragon.id])
    answer(s)
    pump = _activated(s, q, "gets +1/+0")
    mana(s, G=1)
    with pytest.raises(ActionError):  # green mana is not blue mana
        act(s, "p1", type="activate_ability", card_id=q.id, ability=pump)
    mana(s, U=1)  # blue mana pays {R}
    act(s, "p1", type="activate_ability", card_id=q.id, ability=pump)
    answer(s)
    assert pt(s, "Quicksilver Elemental")[0] == 4
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[q.id]).abilities
    check(s)


def test_grell_gives_horrors_the_abilities_of_an_opponents_artifact_payable_with_blue(cards):
    from tests.wave9c_kit import life

    s = build(cards, ["Grell Philosopher"], ["Pyrite Spellbomb"])
    bomb = put(s, "Pyrite Spellbomb", "p2")
    mana(s, U=1, C=2)
    grell = cast_card(s, "Grell Philosopher")
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((o.id for o in d.options if o.card_id == bomb.id), d.options[0].id)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    ab = _activated(s, grell, "deals 2 damage")
    mana(s, G=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=grell.id, ability=ab, targets=["p2"])
    mana(s, U=1)
    act(s, "p1", type="activate_ability", card_id=grell.id, ability=ab, targets=["p2"])  # {R} paid with blue mana
    answer(s)
    assert life(s, "p2") == 38 and s.state.cards[grell.id].zone.endswith(":graveyard")  # it sacrificed itself
    check(s)


WURM = real("Panglacial Wurm", "{5}{G}{G}", 7, "Creature \u2014 Wurm", "Trample\nWhile you're searching your library, you may cast this card from your library.", ("9", "5"), "G")
GROWTH = real("Rampant Growth", "{1}{G}", 2, "Sorcery", "Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.", None, "G")
base.EXTRA.extend([WURM, GROWTH])


def test_wurm_full(cards):
    assert coverage.of_card_data(cards.resolve("Panglacial Wurm")).level == "FULL"


def _wurm_search(cards, cast_it):
    from tests.test_rules_contextual_mana_outcomes import pool

    s = build(cards, ["Panglacial Wurm", "Rampant Growth"])
    mana(s, G=3, C=6)
    growth = to_hand(s, "Rampant Growth")
    act(s, "p1", type="cast_spell", card_id=growth.id)
    on_stack_while_searching = None
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and "Panglacial Wurm" in [o.label for o in d.options]:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options] if cast_it else [])
        elif d is not None:
            if d.prompt.startswith("Search your library"):
                on_stack_while_searching = card_named(s, "Panglacial Wurm").zone
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return s, on_stack_while_searching, pool(s, "G") + pool(s, "C")


def test_wurm_is_cast_from_the_library_during_a_search(cards):
    s, zone_during, left = _wurm_search(cards, True)
    assert zone_during == "stack"  # waiting above the search, which goes on after the cast
    assert card_named(s, "Panglacial Wurm").zone == "p1:battlefield" and left == 0  # {5}{G}{G} paid with the rest of the 9 mana
    assert sum(1 for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:battlefield") == 1  # the search still found its land
    check(s)


def test_wurm_stays_in_the_library_when_the_window_is_declined(cards):
    s, zone_during, left = _wurm_search(cards, False)
    assert zone_during == "p1:library" and card_named(s, "Panglacial Wurm").zone == "p1:library" and left == 7
    check(s)


GIFTS = real("Gifts Ungiven", "{3}{U}", 4, "Instant",
             "Search your library for up to four cards with different names and reveal them. Target opponent chooses two of those cards. Put the chosen cards into your graveyard and the rest into your hand. Then shuffle.",
             None, "U")
base.EXTRA.append(GIFTS)


def test_wurm_window_also_comes_before_a_gifts_ungiven_search(cards):
    s = build(cards, ["Panglacial Wurm", "Gifts Ungiven"])
    mana(s, U=1, G=2, C=8)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Gifts Ungiven").id, targets=["p2"])
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and "Panglacial Wurm" in [o.label for o in d.options] and d.prompt.startswith("Choose a spell"):
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert card_named(s, "Panglacial Wurm").zone == "p1:battlefield"
    check(s)


TRANCE = real("Shaman's Trance", "{2}{R}", 3, "Instant",
              "Other players can't play lands or cast spells from their graveyards this turn. You may play lands and cast spells from other players' graveyards this turn as though those cards were in your graveyard.",
              None, "R")
THINK = {**real("Think Twice", "{1}{U}", 2, "Instant", "Draw a card.\nFlashback {2}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)", None, "U"), "keywords": ["Flashback"]}
base.EXTRA.extend([TRANCE, THINK])


def test_trance_full(cards):
    assert coverage.of_card_data(cards.resolve("Shaman's Trance")).level == "FULL"


def _trance(cards):
    s = build(cards, ["Shaman's Trance", "Test Bolt"], ["Think Twice", "Test Bolt", "Island"])
    act(s, "p2", type="set_prefs", full_control=True)
    for name in ("Think Twice", "Test Bolt", "Island"):
        act(s, "p2", type="move", card_ids=[card_named(s, name, "p2").id], to={"zone": "graveyard"})
    mana(s, R=1, C=2)
    cast_card(s, "Shaman's Trance")
    answer(s)
    return s


def test_trance_lets_the_caster_cast_flashback_and_normal_spells_and_play_lands_from_another_graveyard(cards):
    from tests.wave9c_kit import life

    s = _trance(cards)
    think = card_named(s, "Think Twice", "p2")
    hand = len(s.state.zones["p1:hand"])
    mana(s, U=1, C=2)  # flashback {2}{U}
    act(s, "p1", type="cast_spell", card_id=think.id)
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1 and s.state.cards[think.id].zone.endswith(":exile")  # drew a card, exiled instead of the graveyard
    bolt = card_named(s, "Test Bolt", "p2")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 37
    island = card_named(s, "Island", "p2")
    act(s, "p1", type="play_land", card_id=island.id)
    assert s.state.cards[island.id].zone == "p1:battlefield" and s.state.cards[island.id].controller == "p1"
    check(s)


def test_trance_stops_the_other_players_from_using_their_own_graveyards(cards):
    s = _trance(cards)
    mana(s, "p2", U=1, C=2)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Bolt").id, targets=["p1"])  # Alice puts something on the stack: Bob has priority
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    with pytest.raises(ActionError):  # Bob's own flashback card
        act(s, "p2", type="cast_spell", card_id=card_named(s, "Think Twice", "p2").id)
