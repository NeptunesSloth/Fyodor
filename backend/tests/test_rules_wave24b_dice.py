"""Wave 24B: dice as events and many dice (CR 706), real Oracle text; every scenario checks the replay and a save and a load.

* 706.2: every die is a roll: "Whenever you roll a 1 or 2" triggers per die with that die's result ("that many", "If the roll was 4 or higher");
  "your third die each turn", "a die's highest natural result" read the turn's dice and the die's size.
* 706.1: an effect says how many dice ("Roll three six-sided dice", "Roll X six-sided dice"); "for each odd / even / different result" and
  "the total of those results" read them. The results are recorded on the step (a replay doesn't roll again).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer, real, rolls
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

EXTRA = [
    real("Atomwheel Acrobats", "{3}{G}", 4, "Creature — Elf Performer",
         "Whenever you roll a 1 or 2, put that many +1/+1 counters on this creature.\n{2}{G}: Roll a six-sided die.", ("3", "2"), "G"),
    real("Monoxa, Midway Manager", "{2}{B}{R}", 4, "Legendary Creature — Vampire Employee",
         "Whenever you roll a 3 or higher, Monoxa gains first strike until end of turn. If the roll was 4 or higher, it gains menace until "
         "end of turn. If the roll was 5 or higher, it gains lifelink until end of turn.\n{6}: Roll a six-sided die.", ("3", "3"), "BR"),
    real("Resolute Veggiesaur", "{2}{G}", 3, "Creature — Dinosaur Employee",
         "Trample\nWhenever you roll your third die each turn, put a +1/+1 counter on this creature.", ("3", "3"), "G"),
    real("The Space Family Goblinson", "{2}{R}{G}", 4, "Legendary Creature — Goblin Guest",
         "The Space Family Goblinson has trample as long as you've rolled three or more dice this turn.\n"
         "Whenever you roll a die, put a +1/+1 counter on The Space Family Goblinson.", ("1", "1"), "RG"),
    real("Netherese Puzzle-Ward", "{3}{U}", 4, "Enchantment",
         "Focus Beam — At the beginning of your upkeep, roll a d4. Scry X, where X is the result.\n"
         "Perfect Illumination — Whenever you roll a die's highest natural result, draw a card.", None, "U"),
    real("Circuits Act", "{2}{R}", 3, "Sorcery", "Roll three six-sided dice. For each different result, create a 1/1 white Clown Robot "
         "artifact creature token.", None, "R"),
    real("Clown Car", "{X}", 0, "Artifact — Vehicle",
         "When this Vehicle enters, roll X six-sided dice. For each odd result, create a 1/1 white Clown Robot artifact creature token. For "
         "each even result, put a +1/+1 counter on this Vehicle.\nCrew 2", ("1", "1")),
    real("Attempted Murder", "{X}{B}{B}", 2, "Sorcery",
         "Choose target creature. Roll X six-sided dice. For each even result, put two -1/-1 counters on that creature. For each odd result, "
         "create a 1/2 blue Bird creature token with flying named Storm Crow.", None, "B"),
    real("Diviner's Portent", "{X}{U}{U}{U}", 3, "Instant",
         "Roll a d20 and add the number of cards in your hand.\n1—14 | Draw X cards.\n15+ | Scry X, then draw X cards.", None, "U"),
    real("Boing!", "{1}{U}", 2, "Instant", "Return target creature to its owner's hand, then roll a six-sided die. If the result is 3 or less, "
         "scry a number of cards equal to the result.", None, "U"),
    real("Dice Bear", "{1}{G}", 2, "Creature — Bear", "", ("6", "6"), "G"),
    real("Wyll, Blade of Frontiers", "{1}{R}", 2, "Legendary Creature — Human Warlock",
         "If you would roll one or more dice, instead roll that many dice plus one and ignore the lowest roll.\nWhenever you roll one or more "
         "dice, put a +1/+1 counter on Wyll.\nChoose a Background (You can have a Background as a second commander.)", ("1", "1"), "R"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA if c["name"] != "Dice Bear"])
def test_the_dice_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def roll_ability(s, name):
    act(s, "p1", type="activate_ability", card_id=card_named(s, name).id, ability=1)
    answer(s)


def counters(s, name, kind="+1/+1"):
    return s.state.cards[card_named(s, name).id].counters.get(kind, 0)


@pytest.mark.parametrize("die,expected", [(2, 2), (1, 1), (5, 0)])
def test_whenever_you_roll_a_1_or_2_puts_that_many_counters(cards, monkeypatch, die, expected):
    rolls(monkeypatch, die)
    s = build(cards, ["Atomwheel Acrobats"], [])
    put(s, "Atomwheel Acrobats")
    mana(s, G=3)
    roll_ability(s, "Atomwheel Acrobats")
    assert counters(s, "Atomwheel Acrobats") == expected
    check(s)


@pytest.mark.parametrize("die,keywords", [(2, set()), (3, {"first strike"}), (4, {"first strike", "menace"}),
                                          (6, {"first strike", "menace", "lifelink"})])
def test_the_roll_was_n_or_higher_reads_the_die(cards, monkeypatch, die, keywords):
    rolls(monkeypatch, die)
    s = build(cards, ["Monoxa, Midway Manager"], [])
    put(s, "Monoxa, Midway Manager")
    mana(s, C=6)
    roll_ability(s, "Monoxa, Midway Manager")
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, "Monoxa, Midway Manager").id])
    assert {"first strike", "menace", "lifelink"} & set(ch.keywords) == keywords
    check(s)


def test_each_die_triggers_on_its_own_and_the_third_die_of_the_turn(cards, monkeypatch):
    rolls(monkeypatch, 1, 2, 3)
    s = build(cards, ["Resolute Veggiesaur", "The Space Family Goblinson", "Circuits Act"], [])
    put(s, "Resolute Veggiesaur")
    put(s, "The Space Family Goblinson")
    spell = to_hand(s, "Circuits Act")
    mana(s, R=1, G=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s)
    assert counters(s, "Resolute Veggiesaur") == 1  # the third die of the turn (706.2: three rolls)
    assert counters(s, "The Space Family Goblinson") == 3  # one trigger for each die
    from app.rules.plan import Plan

    assert "trample" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, "The Space Family Goblinson").id]).keywords
    assert len([c for c in s.state.cards.values() if c.is_token and c.name == "Clown Robot"]) == 3  # three different results
    check(s)


def test_for_each_different_result(cards, monkeypatch):
    rolls(monkeypatch, 4, 4, 6)
    s = build(cards, ["Circuits Act"], [])
    spell = to_hand(s, "Circuits Act")
    mana(s, R=1, G=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s)
    assert len([c for c in s.state.cards.values() if c.is_token and c.name == "Clown Robot"]) == 2
    check(s)


def test_roll_x_dice_odd_and_even_results(cards, monkeypatch):
    rolls(monkeypatch, 1, 2, 3, 4, 6)  # (X = 5: three odd... 1 and 3 are odd, 2, 4, 6 even)
    s = build(cards, ["Clown Car"], [])
    car = to_hand(s, "Clown Car")
    mana(s, G=5)
    act(s, "p1", type="cast_spell", card_id=car.id, x_value=5)
    answer(s)
    assert len([c for c in s.state.cards.values() if c.is_token and c.name == "Clown Robot"]) == 2
    assert counters(s, "Clown Car") == 3
    check(s)


def test_attempted_murder_even_results_shrink_and_odd_results_make_birds(cards, monkeypatch):
    rolls(monkeypatch, 2, 3, 6)
    s = build(cards, ["Attempted Murder", "Dice Bear"], [])
    bear = put(s, "Dice Bear")
    spell = to_hand(s, "Attempted Murder")
    mana(s, B=2, G=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=3, targets=[bear.id])
    answer(s)
    assert counters(s, "Dice Bear", "-1/-1") == 4  # two even results: two counters each
    assert len([c for c in s.state.cards.values() if c.is_token and c.name == "Storm Crow"]) == 1
    check(s)


def test_a_dice_roll_of_zero_dice_rolls_nothing(cards, monkeypatch):
    rolls(monkeypatch)
    s = build(cards, ["Clown Car"], [])
    car = to_hand(s, "Clown Car")
    act(s, "p1", type="cast_spell", card_id=car.id, x_value=0)
    answer(s)
    assert not [c for c in s.state.cards.values() if c.is_token]
    check(s)


@pytest.mark.parametrize("die,drawn", [(6, 1), (5, 0)])
def test_a_dies_highest_natural_result_draws(cards, monkeypatch, die, drawn):
    rolls(monkeypatch, die)
    s = build(cards, ["Atomwheel Acrobats", "Netherese Puzzle-Ward"], [])
    put(s, "Atomwheel Acrobats")
    put(s, "Netherese Puzzle-Ward")
    hand = len(s.state.zones["p1:hand"])
    mana(s, G=3)
    roll_ability(s, "Atomwheel Acrobats")
    assert len(s.state.zones["p1:hand"]) == hand + drawn  # (a d6 showing 6: its highest natural result)
    check(s)


@pytest.mark.parametrize("dice,counters_on_acrobats", [((2, 5), 0), ((5, 2), 0), ((1, 1), 1)])
def test_roll_one_more_die_and_ignore_the_lowest_roll(cards, monkeypatch, dice, counters_on_acrobats):
    rolls(monkeypatch, *dice)  # Wyll: one die asked for, two rolled; the lowest roll never happened (706.6): no trigger for it
    s = build(cards, ["Atomwheel Acrobats", "Wyll, Blade of Frontiers"], [])
    put(s, "Atomwheel Acrobats")
    put(s, "Wyll, Blade of Frontiers")
    mana(s, G=3)
    roll_ability(s, "Atomwheel Acrobats")
    assert counters(s, "Atomwheel Acrobats") == counters_on_acrobats  # (the 5 or the 1 is the roll that counts; a 2 that was ignored isn't)
    assert counters(s, "Wyll, Blade of Frontiers") == 1  # "Whenever you roll one or more dice": once for the roll
    check(s)


@pytest.mark.parametrize("die,drawn", [(3, 2), (20, 2)])
def test_roll_and_add_the_number_of_cards_in_your_hand(cards, monkeypatch, die, drawn):
    """706.2: the natural result plus the modifier is the result the table is read with: 3 + (cards in hand) stays under 15, 20 + … is over."""
    rolls(monkeypatch, die)
    s = build(cards, ["Diviner's Portent"], [])
    spell = to_hand(s, "Diviner's Portent")
    mana(s, U=3, G=2)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=2)
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + drawn  # the spell left the hand; X = 2 cards drawn either way (15+ scries first)
    check(s)


@pytest.mark.parametrize("die,scried", [(2, True), (5, False)])
def test_scry_a_number_of_cards_equal_to_the_result(cards, monkeypatch, die, scried):
    rolls(monkeypatch, die)
    s = build(cards, ["Boing!", "Dice Bear"], [])
    bear = put(s, "Dice Bear")
    spell = to_hand(s, "Boing!")
    mana(s, U=1, G=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id])
    answer(s)
    scries = [e for e in s.state.rules.events if e.kind == "designation" and e.counter == "scry"]
    assert [e.looked for e in scries] == ([die] if scried else [])  # 701.22: as many cards as the result, only for a result of 3 or less
    check(s)
