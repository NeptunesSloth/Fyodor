"""Wave 16F: the smaller non-keyword families. Real Oracle text; every scenario checks the replay and a save and a load.

* 702.5d / 603.1: a Curse's triggers name "enchanted player": its draws and casts, the creatures and lands they control.
* 604.1 / 603.1: a ", where X is …" that sits inside a quoted granted ability belongs to that ability, not to the Aura's sentence.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_sagas import main_phase
from tests.test_rules_wave12a_counters_keywords import answer, real
from tests.wave9c_kit import build, check, life, mana, to_hand

EXTRA = [
    real("Trespasser's Curse", "{1}{B}", 2, "Enchantment — Aura Curse",
         "Enchant player\nWhenever a creature enchanted player controls enters, that player loses 1 life and you gain 1 life.",
         None, "B"),
    real("Curse of Fool's Wisdom", "{3}{B}", 4, "Enchantment — Aura Curse",
         "Enchant player\nWhenever enchanted player draws a card, they lose 2 life and you gain 2 life.\nMadness {3}{B} (If you "
         "discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your graveyard.)",
         None, "B"),
]

EXTRA.append(real("Jackdaw Savior", "{3}{W}", 4, "Creature — Bird Soldier",
                  "Flying\nWhenever this creature or another creature you control with flying dies, return another target creature "
                  "card with lesser mana value from your graveyard to the battlefield.", ("2", "2"), "W"))

EXTRA.append(real("Deepwood Legate", "{4}{G}{G}", 6, "Creature — Treefolk",
                  "If an opponent controls a Forest and you control a Swamp, you may cast this spell without paying its mana cost.\n"
                  "{B}: This creature gets +1/+1 until end of turn.", ("4", "4"), "G"))

EXTRA.append(real("Rona, Sheoldred's Faithful", "{2}{B}", 3, "Legendary Creature — Human Cleric",
                  "Whenever you cast an instant or sorcery spell, each opponent loses 1 life.\nYou may cast this card from your "
                  "graveyard by discarding two cards in addition to paying its other costs.", ("2", "2"), "B"))

EXTRA.append(real("Tabernacle at Pendrell Vale", "", 0, "Legendary Land",
                  "All creatures have \"At the beginning of your upkeep, destroy this creature unless you pay {1}.\"", None))

EXTRA.append(real("Search Party Captain", "{4}{B}", 5, "Creature — Human Scout",
                  "This spell costs {1} less to cast for each creature you attacked with this turn.", ("3", "3"), "B"))

EXTRA.append(real("Avatar of Will", "{6}{U}{U}", 8, "Creature — Avatar",
                  "If an opponent has no cards in hand, this spell costs {6} less to cast.\nFlying", ("5", "6"), "U"))

EXTRA.append(real("Avatar of Might", "{6}{G}{G}", 8, "Creature — Avatar",
                  "If an opponent controls at least four more creatures than you, this spell costs {6} less to cast.\nTrample",
                  ("8", "8"), "G"))
EXTRA.append(real("Paradox Surveyor", "{1}{G}", 2, "Creature — Elf Scout",
                  "Reach\nWhen this creature enters, look at the top five cards of your library. You may reveal a land card or a card "
                  "with {X} in its mana cost from among them and put it into your hand. Put the rest on the bottom of your library "
                  "in a random order.", ("2", "2"), "G"))

EXTRA.append(real("Entropic Specter", "{1}{B}{B}", 3, "Creature — Specter",
                  "Flying\nAs this creature enters, choose an opponent.\nEntropic Specter's power and toughness are each equal to the "
                  "number of cards in the chosen player's hand.\nWhenever this creature deals damage to a player, that player discards a "
                  "card.", ("*", "*"), "B"))
EXTRA.append(real("Haunting Apparition", "{1}{B}", 2, "Creature — Spirit",
                  "Flying\nAs this creature enters, choose an opponent.\nHaunting Apparition's power is equal to 1 plus the number of "
                  "green creature cards in the chosen player's graveyard.", ("*", "1"), "B"))

EXTRA.append(card(
    "Captive Weird // Compleated Conjurer", set_code="tst", number="16F-CW", layout="transform", mana_cost=None, cmc=3.0,
    type_line="Creature — Weird // Creature — Phyrexian Wizard", colors=["R"], color_identity=["R"], image_uris=None,
    card_faces=[
        {"object": "card_face", "name": "Captive Weird", "mana_cost": "{2}{R}", "type_line": "Creature — Weird", "power": "3",
         "toughness": "3", "colors": ["R"], "oracle_text": "Defender\n{3}{R/P}: Transform this creature. Activate only as a sorcery. "
                                                         "({R/P} can be paid with either {R} or 2 life.)"},
        {"object": "card_face", "name": "Compleated Conjurer", "mana_cost": "", "type_line": "Creature — Phyrexian Wizard", "power": "3",
         "toughness": "3", "colors": ["R"], "oracle_text": "When this creature transforms into Compleated Conjurer, exile the top card "
                                                         "of your library. Until the end of your next turn, you may play that card."},
    ]))

IDOLIZED = ("Enchant creature\nEnchanted creature has \"Whenever this creature attacks alone, it gets +X/+X until end of turn, "
            "where X is the number of nonland permanents you control.\"")


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_a_where_x_inside_a_granted_ability_is_that_abilitys(cards):
    from app.rules import sba
    from app.rules.plan import Plan
    from tests.test_rules_combat import attack, automate, creature, table

    s = table(cards)
    bear = creature(s, "p1", "Bear", "2/2")
    creature(s, "p1", "Ox", "1/1")
    act(s, "p1", type="create_token", player="p1", token={
        "name": "Idolized", "type_line": "Token Enchantment — Aura", "power": None, "toughness": None, "colors": [],
        "text": IDOLIZED})
    aura = next(c for c in s.state.cards.values() if c.name == "Idolized")
    act(s, "p1", type="attach", card_ids=[aura.id], to=bear.id)
    automate(s)
    attack(s, (bear, "p2"))
    answer(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bear.id])
    assert (sba.power(s.state.cards[bear.id], ch), sba.toughness(s.state.cards[bear.id], ch)) == (5, 5)  # Bear, Ox, the Aura: X = 3
    check(s)


def test_idolized_is_full():
    from app.rules.characteristics import Characteristics, parse_type_line
    from app.rules.oracle import parse_abilities

    sup, types, subs = parse_type_line("Enchantment — Aura")
    ch = Characteristics(name="Idolized", supertypes=sup, types=types, subtypes=subs, oracle_text=IDOLIZED,
                         abilities=tuple(parse_abilities(IDOLIZED, spell=False)), mana_cost="{1}{W}")
    assert coverage.of_characteristics(ch).level == "FULL"


def curse_on_bob(cards, name, **cost):
    s = build(cards, [name, "Llanowar Elves"], ["Llanowar Elves"])
    c = to_hand(s, name)
    mana(s, **cost)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    answer(s)
    assert s.state.cards[c.id].attached_player == "p2"
    return s


def test_a_curse_triggers_on_creatures_the_enchanted_player_controls(cards):
    s = curse_on_bob(cards, "Trespasser's Curse", B=1, C=1)
    elves = to_hand(s, "Llanowar Elves")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=elves.id)  # (Alice's own creature: not a trigger)
    answer(s)
    assert (life(s, "p1"), life(s, "p2")) == (40, 40)
    main_phase(s, 2)
    ox = to_hand(s, "Llanowar Elves", "p2")
    mana(s, "p2", G=1)
    act(s, "p2", type="cast_spell", card_id=ox.id)
    answer(s)
    assert (life(s, "p1"), life(s, "p2")) == (41, 39)
    check(s)


def test_a_curse_triggers_on_the_enchanted_players_draws(cards):
    s = curse_on_bob(cards, "Curse of Fool's Wisdom", B=1, C=3)
    assert (life(s, "p1"), life(s, "p2")) == (40, 40)  # (Alice drew nothing on turn 1)
    main_phase(s, 2)  # Bob draws in his draw step
    answer(s)
    assert (life(s, "p1"), life(s, "p2")) == (42, 38)
    check(s)


QUIVER = ("Equipped creature has \"{T}: This creature deals 1 damage to any target\" and \"{T}: This creature deals 3 damage to "
          "target Werewolf creature.\"\nEquip {1}")


def test_a_quoted_ability_that_ends_its_clause_without_a_period_is_granted(cards):
    # 604.1 / 113.3: Wolfhunter's Quiver's two quoted abilities are the creature's own; the first has no period inside its quote
    from tests.test_rules_combat import automate, creature, table

    s = table(cards)
    bear = creature(s, "p1", "Bear", "2/2")
    act(s, "p1", type="create_token", player="p1", token={
        "name": "Quiver", "type_line": "Token Artifact — Equipment", "power": None, "toughness": None, "colors": [], "text": QUIVER})
    quiver = next(c for c in s.state.cards.values() if c.name == "Quiver")
    act(s, "p1", type="attach", card_ids=[quiver.id], to=bear.id)
    automate(s)
    act(s, "p1", type="declare_attackers", attackers=[])
    act(s, "p1", type="activate_ability", card_id=bear.id, ability=100, targets=["p2"])
    answer(s)
    assert s.state.players["p2"].life == 39 and s.state.cards[bear.id].tapped
    check(s)


def test_an_aura_stops_activated_abilities_but_not_mana_abilities(cards):
    # 602.2 / 605.1a: Faith's Fetters on a creature with a mana ability and a pump ability; 702.122: Bound in Gold's crew rule
    from app.game.errors import ActionError
    from tests.test_rules_combat import automate, creature, table

    s = table(cards)
    elf = creature(s, "p1", "Elf", "1/1", "{T}: Add {G}.\n{1}: This creature gets +1/+0 until end of turn.")
    act(s, "p1", type="create_token", player="p1", token={
        "name": "Fetters", "type_line": "Token Enchantment — Aura", "power": None, "toughness": None, "colors": [],
        "text": "Enchant permanent\nEnchanted permanent can't attack or block, and its activated abilities can't be activated "
                "unless they're mana abilities."})
    aura = next(c for c in s.state.cards.values() if c.name == "Fetters")
    act(s, "p1", type="attach", card_ids=[aura.id], to=elf.id)
    automate(s)  # (the Elf can't attack: no attackers are asked for)
    mana(s, "p1", C=1)
    with pytest.raises(ActionError, match="unless they're mana abilities"):
        act(s, "p1", type="activate_ability", card_id=elf.id, ability=1)
    act(s, "p1", type="activate_ability", card_id=elf.id, ability=0, mana_choice="G")
    assert s.state.cards[elf.id].tapped
    check(s)


def test_plus_one_for_each_of_its_colors_counts_the_modified_creatures_colors(cards):
    # 105.1 / 613.4c / 611.3a: Blessing of the Nephilim, read for the creature it enchants whenever its characteristics are
    from app.rules import sba
    from app.rules.plan import Plan

    s = build(cards)
    for name, colors, expect in (("Mono", ["G"], (3, 3)), ("Duo", ["G", "W"], (4, 4)), ("Gray", [], (2, 2))):
        act(s, "p1", type="create_token", player="p1", token={
            "name": name, "type_line": "Token Creature — Test", "power": "2", "toughness": "2", "colors": colors, "text": ""})
        c = next(c for c in s.state.cards.values() if c.name == name)
        act(s, "p1", type="create_token", player="p1", token={
            "name": f"Blessing {name}", "type_line": "Token Enchantment — Aura", "power": None, "toughness": None, "colors": [],
            "text": "Enchant creature\nEnchanted creature gets +1/+1 for each of its colors."})
        aura = next(c for c in s.state.cards.values() if c.name == f"Blessing {name}")
        act(s, "p1", type="attach", card_ids=[aura.id], to=c.id)
        ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])
        assert (sba.power(s.state.cards[c.id], ch), sba.toughness(s.state.cards[c.id], ch)) == expect
    check(s)


def test_zendikon_makes_the_land_a_creature_that_is_still_a_land(cards):
    # 205.1b / 613.1d-e / 613.4b: Corrupted Zendikon: a 3/3 black Ooze creature, still a (Forest) land, with its mana ability
    from app.rules import sba
    from app.rules.plan import Plan

    s = build(cards)
    act(s, "p1", type="create_token", player="p1", token={
        "name": "Wood", "type_line": "Token Land — Forest", "power": None, "toughness": None, "colors": [], "text": "{T}: Add {G}."})
    land = next(c for c in s.state.cards.values() if c.name == "Wood")
    act(s, "p1", type="create_token", player="p1", token={
        "name": "Zendikon", "type_line": "Token Enchantment — Aura", "power": None, "toughness": None, "colors": [],
        "text": "Enchant land\nEnchanted land is a 3/3 black Ooze creature. It's still a land.\nWhen enchanted land dies, return that "
                "card to its owner's hand."})
    aura = next(c for c in s.state.cards.values() if c.name == "Zendikon")
    act(s, "p1", type="attach", card_ids=[aura.id], to=land.id)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[land.id])
    assert {"Land", "Creature"} <= ch.types and {"Forest", "Ooze"} <= ch.subtypes and ch.colors == frozenset({"B"})
    assert (sba.power(s.state.cards[land.id], ch), sba.toughness(s.state.cards[land.id], ch)) == (3, 3)
    assert any(a.kind == "mana" for a in ch.abilities)
    check(s)


def _pt(s, c):
    from app.rules import sba
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])
    return sba.power(s.state.cards[c.id], ch), sba.toughness(s.state.cards[c.id], ch)


def _token(s, pid, name, type_line, pt=("2", "2"), colors=(), text=""):
    act(s, pid, type="create_token", player=pid, token={
        "name": name, "type_line": type_line, "power": pt[0], "toughness": pt[1], "colors": list(colors), "text": text})
    return next(c for c in s.state.cards.values() if c.name == name)


def test_a_static_condition_about_the_enchanted_creature_and_its_controller(cards):
    # 611.3a / 613.4c: "as long as it's white" and "as long as its controller controls another creature" read the creature the
    # Aura is on, now (Aura on a white and a green creature; the second Aura needs a second creature of the same controller)
    s = build(cards)
    white, green = _token(s, "p1", "Pale", "Token Creature — Test", colors="W"), _token(s, "p1", "Leaf", "Token Creature — Test", colors="G")
    for who in (white, green):
        aura = _token(s, "p1", f"Glow {who.name}", "Token Enchantment — Aura", (None, None),
                      text="Enchant creature\nEnchanted creature gets +1/+2 as long as it's white.")
        act(s, "p1", type="attach", card_ids=[aura.id], to=who.id)
    assert (_pt(s, white), _pt(s, green)) == ((3, 4), (2, 2))
    ward = _token(s, "p1", "Ward", "Token Enchantment — Aura", (None, None),
                  text="Enchant creature\nEnchanted creature gets +2/+0 as long as its controller controls another creature.")
    act(s, "p1", type="attach", card_ids=[ward.id], to=green.id)
    assert _pt(s, green) == (4, 2)  # (the white creature is another creature)
    act(s, "p1", type="move", card_ids=[white.id], to={"zone": "graveyard"})
    assert _pt(s, green) == (2, 2)
    check(s)


def test_a_self_static_with_no_opponent_creature_and_graveyard_conditions(cards):
    s = build(cards)
    lone = _token(s, "p1", "Lone", "Token Creature — Test", text="~ gets +3/+3 as long as no opponent controls a creature.")
    assert _pt(s, lone) == (5, 5)
    _token(s, "p2", "Foe", "Token Creature — Test")
    assert _pt(s, lone) == (2, 2)
    check(s)


def test_a_host_condition_is_refused_for_a_subject_that_is_not_attached():
    from app.rules import statics

    # (Technodrome: its own power is read since wave 42A, as a condition of the source's own rule checked after layer 7)
    assert statics.parse("~ can't attack or block unless its power is 6 or greater.") is not None
    assert statics.parse("Equipped creature can't be blocked as long as its power is 3 or less.") is not None


def test_sentences_inside_a_granted_quote_are_the_quotes_own():
    from app.rules import statics

    assert statics.parse('Enchanted creature has "{T}: This creature deals 1 damage to target player or planeswalker. '
                         'You draw a card."') is not None
    assert statics.parse('Enchanted creature has "{T}: Add {G}." It is blue.') is None  # (a second sentence outside the quote)


def test_lesser_mana_value_is_than_the_creature_that_died(cards):
    # 608.2h / 700.4: Jackdaw Savior dying returns a creature card with mana value less than its own (4): Elves (1), not Twisted Abomination (6)
    from tests.test_rules_wave15b_triggers import kill
    from tests.wave9c_kit import card_named, put

    s = build(cards, ["Jackdaw Savior", "Llanowar Elves", "Twisted Abomination"])
    put(s, "Jackdaw Savior")
    for name in ("Llanowar Elves", "Twisted Abomination"):
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"zone": "graveyard"})
    kill(s, "Jackdaw Savior")
    assert card_named(s, "Llanowar Elves").zone == "p1:battlefield"
    assert card_named(s, "Twisted Abomination").zone == "p1:graveyard"
    check(s)


def test_legate_is_cast_for_free_only_while_the_condition_holds(cards):
    # 118.9: an alternative cost of {0}, announced as the spell is cast; the Swamp/Forest condition is checked then (601.2b)
    from app.game.errors import ActionError
    from tests.wave9c_kit import card_named

    s = build(cards, ["Deepwood Legate"], [])
    legate = to_hand(s, "Deepwood Legate")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=legate.id, alt_cost=f"{legate.id}:0")  # (no Forest or Swamp yet)
    for pid, land in (("p1", "Forest"), ("p2", "Forest")):
        act(s, pid, type="create_token", player=pid, token={
            "name": f"{land} {pid}", "type_line": f"Token Land — {'Swamp' if pid == 'p1' else 'Forest'}", "power": None,
            "toughness": None, "colors": [], "text": ""})
    act(s, "p1", type="cast_spell", card_id=legate.id, alt_cost=f"{legate.id}:0")
    answer(s)
    assert card_named(s, "Deepwood Legate").zone == "p1:battlefield"
    check(s)


def test_cast_from_the_graveyard_by_discarding_two_cards(cards):
    # 601.2b / 601.2f: Rona's permission names an additional cost, announced and paid with the mana cost; with fewer cards in hand
    # than it needs she can't be cast that way
    from app.game.errors import ActionError
    from tests.wave9c_kit import card_named

    s = build(cards, ["Rona, Sheoldred's Faithful"], [])
    rona = card_named(s, "Rona, Sheoldred's Faithful")
    act(s, "p1", type="move", card_ids=[rona.id], to={"zone": "graveyard"})
    act(s, "p1", type="draw", count=1)
    mana(s, B=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=rona.id)  # (one card in hand: it can't pay for two)
    act(s, "p1", type="draw", count=2)
    hand = [c.id for c in s.state.cards.values() if c.zone == "p1:hand"]
    act(s, "p1", type="cast_spell", card_id=rona.id)
    answer(s, hand[:2])
    assert s.state.cards[rona.id].zone == "p1:battlefield"
    gone = [c for c in hand if s.state.cards[c].zone == "p1:graveyard"]
    assert len(gone) == 2 and len([c for c in s.state.cards.values() if c.zone == "p1:hand"]) == len(hand) - 2
    check(s)


def test_a_static_grants_every_creature_an_upkeep_payment(cards):
    # 613.1f / 603.2: Tabernacle at Pendrell Vale: each creature has the ability, its own controller pays or it is destroyed
    pass
    from tests.wave9c_kit import put

    s = build(cards, ["Tabernacle at Pendrell Vale"], [], forests=30, islands=30)
    put(s, "Tabernacle at Pendrell Vale")
    bear = _token(s, "p1", "Bear", "Token Creature — Bear")
    foe = _token(s, "p2", "Foe", "Token Creature — Bear")
    main_phase(s, 2)
    assert (bear.id in s.state.cards and s.state.cards[bear.id].zone == "p1:battlefield")
    assert foe.id not in s.state.cards  # (a token that left the battlefield ceases to exist) Bob couldn't pay at his upkeep: destroyed (not Alice's)
    main_phase(s, 3)
    assert bear.id not in s.state.cards  # Alice couldn't pay either
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_sacrifice_unless_you_pay_its_mana_cost(cards, pay):
    # 701.21a / 118.12a: Pendrell Flux gives the creature "sacrifice this creature unless you pay its mana cost" ({1}{G})
    from tests.test_rules_conditionals import until
    from tests.wave9c_kit import put

    s = build(cards, ["Grizzly Bears"], [], forests=30, islands=30)
    bears = put(s, "Grizzly Bears")
    aura = _token(s, "p1", "Flux", "Token Enchantment — Aura", (None, None), text=(
        "Enchant creature\nEnchanted creature has \"At the beginning of your upkeep, sacrifice this creature unless you pay its "
        "mana cost.\""))
    act(s, "p1", type="attach", card_ids=[aura.id], to=bears.id)
    until(s, lambda s: s.state.turn.number == 3 and s.state.rules.decision is not None and s.state.rules.decision.player == "p1")
    d = s.state.rules.decision
    assert sorted(o.id for o in d.options) == ["pay", "sacrifice"]
    if pay:
        mana(s, G=1, C=1)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay" if pay else "sacrifice"])
    answer(s)
    assert (s.state.cards[bears.id].zone == "p1:battlefield") == pay
    check(s)


def test_cant_be_the_target_of_black_spells_or_abilities_from_black_sources(cards):
    # 115.2 / 702.11: Mercenary Informer's wording: a black spell can't target it (Murder), a green one can (Giant Growth); the
    # color is the source's, spell or ability
    from app.game.errors import ActionError

    s = build(cards, ["Murder", "Giant Growth"], [])
    inf = _token(s, "p1", "Informer", "Token Creature — Rogue", text="~ can't be the target of black spells or abilities from black "
                 "sources.")
    murder, growth = to_hand(s, "Murder"), to_hand(s, "Giant Growth")
    mana(s, B=2, C=1, G=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=murder.id, targets=[inf.id])
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[inf.id])
    answer(s)
    assert _pt(s, inf) == (5, 5)
    check(s)


def test_cost_reduction_counts_the_creatures_you_attacked_with(cards):
    # 601.2f / 508.1: Search Party Captain after attacking with two creatures (one of which died) costs {1} less for each of the two
    from app.game.factory import DeckCard, PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.test_rules_combat import automate, creature
    from tests.test_rules_conditionals import attack, through_combat
    from tests.wave9c_kit import card_named

    def deck(commander, *spells):
        cmd = cards.resolve(commander)
        return [DeckCard("commander", 1, cmd["name"], cmd["id"]),
                *(DeckCard("main", n, cards.resolve(name)["name"], cards.resolve(name)["id"]) for n, name in spells)]

    s = GameSession(new_game([PlayerSetup("Alice", cards=deck("Krenko, Mob Boss", (1, "Search Party Captain"), (9, "Forest"))),
                              PlayerSetup("Bob", cards=deck("Atraxa, Praetors' Voice", (10, "Island")))], shuffle=False), cards=cards)
    a, b = creature(s, "p1", "Ape", "2/2"), creature(s, "p1", "Bat", "1/1")
    act(s, "p1", type="create_token", player="p2", token={"name": "Wall", "type_line": "Token Creature — Wall", "power": "0",
                                                          "toughness": "9", "colors": [], "text": ""})
    automate(s)
    attack(s, (a, "p2"), (b, "p2"))
    through_combat(s)
    act(s, "p1", type="move", card_ids=[b.id], to={"zone": "graveyard"})  # (it left the battlefield: it still attacked)
    cap = card_named(s, "Search Party Captain")
    act(s, "p1", type="move", card_ids=[cap.id], to={"zone": "hand"})
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=cap.id)
    answer(s)
    assert s.state.cards[cap.id].zone == "p1:battlefield"
    check(s)


def test_an_opponent_with_no_cards_in_hand_reduces_the_cost(cards):
    # 601.2f: Avatar of Will costs {6} less while some opponent has no cards in hand (Bob has none; then he draws one)
    from app.game.errors import ActionError

    s = build(cards, ["Avatar of Will"], [])
    avatar = to_hand(s, "Avatar of Will")
    mana(s, U=2)
    act(s, "p2", type="draw", count=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=avatar.id)  # (Bob has a card in hand: the full {6}{U}{U})
    hand = [c.id for c in s.state.cards.values() if c.zone == "p2:hand"]
    act(s, "p2", type="move", card_ids=hand, to={"zone": "graveyard"})
    act(s, "p1", type="cast_spell", card_id=avatar.id)
    answer(s)
    assert s.state.cards[avatar.id].zone == "p1:battlefield"
    check(s)


def test_cost_reduction_by_a_creature_margin(cards):
    # 601.2f: Avatar of Might needs some opponent to control at least four more creatures than you (3 more: the full cost)
    from app.game.errors import ActionError

    s = build(cards, ["Avatar of Might"], [])
    might = to_hand(s, "Avatar of Might")
    mana(s, G=2)
    for i in range(3):
        _token(s, "p2", f"Foe{i}", "Token Creature — Bear")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=might.id)
    _token(s, "p2", "Foe3", "Token Creature — Bear")
    act(s, "p1", type="cast_spell", card_id=might.id)
    answer(s)
    assert s.state.cards[might.id].zone == "p1:battlefield"
    check(s)


def test_reveal_one_of_several_kinds_from_the_top_cards(cards):
    # 701.20 / 400.1: Paradox Surveyor: a land card or a card with {X} in its mana cost from among the top five; Llanowar Elves
    # on top isn't either, so it can't be taken; the rest go to the bottom
    from tests.wave9c_kit import card_named

    s = build(cards, ["Paradox Surveyor", "Llanowar Elves"], [])
    elves = card_named(s, "Llanowar Elves")
    act(s, "p1", type="move", card_ids=[elves.id], to={"zone": "library"}, position="top")
    surveyor = to_hand(s, "Paradox Surveyor")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=surveyor.id)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert elves.id not in [o.id for o in d.options] and len(d.options) == 4 and all(o.label == "Forest" for o in d.options)
    hand = len([c for c in s.state.cards.values() if c.zone == "p1:hand"])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    answer(s)
    assert len([c for c in s.state.cards.values() if c.zone == "p1:hand"]) == hand + 1
    assert s.state.cards[elves.id].zone == "p1:library"
    check(s)


def test_power_and_toughness_count_what_the_chosen_player_has(cards):
    # 604.3 / 611.3a: Entropic Specter and Haunting Apparition choose an opponent as they enter, then count Bob's hand and the green
    # creature cards in Bob's graveyard whenever their characteristics are read
    from tests.wave9c_kit import card_named

    s = build(cards, ["Entropic Specter", "Haunting Apparition"], ["Llanowar Elves"])
    spec, app = to_hand(s, "Entropic Specter"), to_hand(s, "Haunting Apparition")
    act(s, "p2", type="draw", count=3)  # (a 0/0 Specter would die as it enters)
    mana(s, B=5, C=1)
    for c in (spec, app):
        act(s, "p1", type="cast_spell", card_id=c.id)
        answer(s, "p2")  # (As it enters: choose Bob)
    assert _pt(s, spec) == (3, 3) and _pt(s, app)[0] == 1
    act(s, "p2", type="draw", count=2)
    assert _pt(s, spec) == (5, 5)
    hand = [c.id for c in s.state.cards.values() if c.zone == "p2:hand" and c.name == "Llanowar Elves"]
    act(s, "p2", type="move", card_ids=hand[:1] or [card_named(s, "Llanowar Elves", "p2").id], to={"zone": "graveyard"})
    assert _pt(s, app)[0] == 2
    check(s)


def test_transforms_into_triggers_when_the_object_turns_over(cards):
    # 701.28 / 712.18 / 603.2: Captive Weird transformed by its own ability: the new face's "transforms into" trigger exiles the top card
    from tests.wave9c_kit import put

    s = build(cards, ["Captive Weird // Compleated Conjurer"], [])
    weird = put(s, "Captive Weird // Compleated Conjurer")
    top = s.state.zones["p1:library"][0]
    mana(s, R=1, C=3)
    act(s, "p1", type="activate_ability", card_id=weird.id, ability=1)
    answer(s)
    assert s.state.cards[weird.id].face == 1
    assert s.state.cards[top].zone == "p1:exile"
    check(s)
