"""Wave 16F: the smaller non-keyword families. Real Oracle text; every scenario checks the replay and a save and a load.

* 702.5d / 603.1: a Curse's triggers name "enchanted player": its draws and casts, the creatures and lands they control.
* 604.1 / 603.1: a ", where X is …" that sits inside a quoted granted ability belongs to that ability, not to the Aura's sentence.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer, real
from tests.test_rules_sagas import main_phase
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
