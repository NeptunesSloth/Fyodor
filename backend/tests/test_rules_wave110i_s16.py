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
