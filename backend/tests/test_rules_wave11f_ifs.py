"""Wave 11F: intervening-if conditions (603.4: checked as the ability triggers and again as it resolves) - a hand size, a
comparison with the player the event names, "if it was enchanted", counts of everything on the battlefield. Real Oracle
text; each scenario checks the replay and a save/load round trip."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import life, settle, to_turn
from tests.test_rules_wave11f_events import EXTRA as EVENT_CARDS
from tests.test_rules_wave11f_events import real, roundtrip
from tests.wave9c_kit import build, put, to_hand

EXTRA = [
    real("Imaginary Pet", "{3}{U}", 4, "Creature — Illusion",
         "At the beginning of your upkeep, if you have a card in hand, return this creature to its owner's hand.", ("4", "4"),
         "U"),
    real("Asylum Visitor", "{1}{B}", 2, "Creature — Vampire Wizard",
         "At the beginning of each player's upkeep, if that player has no cards in hand, you draw a card and you lose 1 life.",
         ("3", "1"), "B"),
    real("Keeper of the Accord", "{3}{W}", 4, "Creature — Human Monk",
         "At the beginning of each opponent's end step, if that player controls more creatures than you, create a 1/1 white "
         "Soldier creature token.\nAt the beginning of each opponent's end step, if that player controls more lands than you, "
         "you may search your library for a basic Plains card, put it onto the battlefield tapped, then shuffle.", ("3", "3"),
         "W"),
    real("Tephraderm", "{2}{R}{R}", 4, "Creature — Beast",
         "Whenever a creature deals damage to this creature, this creature deals that much damage to that creature.\n"
         "Whenever a spell deals damage to this creature, this creature deals that much damage to that spell's controller.",
         ("4", "5"), "R"),
    real("Gunner Conscript", "{1}{R}", 2, "Creature — Human Soldier",
         "Trample\nThis creature gets +1/+1 for each Aura and Equipment attached to it.\nWhen this creature dies, if it was "
         "enchanted, create a Junk token.\nWhen this creature dies, if it was equipped, create a Junk token.", ("1", "1"), "R"),
    real("Pacifism", "{1}{W}", 2, "Enchantment — Aura", "Enchant creature\nEnchanted creature can't attack or block.", None, "W"),
    real("Damia, Sage of Stone", "{4}{B}{G}{U}", 7, "Legendary Creature — Gorgon Wizard",
         "Deathtouch\nSkip your draw step.\nAt the beginning of your upkeep, if you have fewer than seven cards in hand, draw "
         "cards equal to the difference.", ("4", "4"), "BGU"),
    real("Mana Bloom", "{X}{G}", 1, "Enchantment",
         "This enchantment enters with X charge counters on it.\nRemove a charge counter from this enchantment: Add one mana of "
         "any color. Activate only once each turn.\nAt the beginning of your upkeep, if this enchantment has no charge counters on "
         "it, return it to its owner's hand.", None, "G"),
    real("Farsight Mask", "{3}", 3, "Artifact",
         "Whenever a source an opponent controls deals damage to you, if this artifact is untapped, you may draw a card.", None),
    real("Demonic Rising", "{3}{B}", 4, "Enchantment",
         "At the beginning of your end step, if you control exactly one creature, create a 5/5 black Demon creature token with "
         "flying.", None, "B"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EVENT_CARDS, *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Imaginary Pet", "Asylum Visitor", "Keeper of the Accord", "Tephraderm", "Gunner Conscript",
                                  "Farsight Mask", "Demonic Rising", "Damia, Sage of Stone", "Mana Bloom"])
def test_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def on(s, name, zone, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:{zone}"]


def tokens(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.zone == f"{pid}:battlefield" and c.is_token]


def hand_of(s, pid):
    return [c for c in s.state.cards.values() if c.zone == f"{pid}:hand"]


def empty_hand(s, pid="p1"):
    ids = [c.id for c in hand_of(s, pid)]
    if ids:
        act(s, pid, type="move", card_ids=ids, to={"zone": "graveyard"})


def cast_bolt(s, target, mana="R"):
    bolt = to_hand(s, "Lightning Bolt")
    act(s, "p1", type="add_mana", player="p1", mana={mana: 1})
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[target])


def test_a_hand_size_holds_when_the_step_begins(cards):
    s = build(cards, ("Imaginary Pet", "Forest"), forests=30, islands=30)
    put(s, "Imaginary Pet")
    empty_hand(s)
    to_hand(s, "Forest")
    to_turn(s, 3)  # a card in hand at Alice's upkeep: the Pet goes back to her hand (603.4: it held twice)
    assert on(s, "Imaginary Pet", "hand") and not on(s, "Imaginary Pet", "battlefield")
    roundtrip(s)


def test_no_card_in_hand_means_no_trigger(cards):
    s = build(cards, ("Imaginary Pet",), forests=30, islands=30)
    put(s, "Imaginary Pet")
    empty_hand(s)
    to_turn(s, 3)
    assert on(s, "Imaginary Pet", "battlefield")
    roundtrip(s)


def test_a_condition_about_the_player_whose_step_it_is(cards):
    s = build(cards, ("Asylum Visitor",), forests=30, islands=30)
    put(s, "Asylum Visitor")
    empty_hand(s)
    to_turn(s, 2)  # Bob's upkeep, and Bob has no cards in hand: Alice draws a card and loses 1 life
    assert life(s, "p1") == 39
    assert len(hand_of(s, "p1")) == 1
    roundtrip(s)


def test_that_players_hand_is_not_yours(cards):
    s = build(cards, ("Asylum Visitor",), forests=30, islands=30)
    put(s, "Asylum Visitor")
    empty_hand(s)
    act(s, "p2", type="draw", count=1)  # Bob holds a card at his upkeep; Alice's hand is empty: nothing happens
    to_turn(s, 2)
    assert life(s, "p1") == 40
    roundtrip(s)


def test_that_player_controls_more_creatures_than_you(cards):
    s = build(cards, ("Keeper of the Accord",), ("Grizzly Bears", "Grizzly Bears"), forests=30, islands=30)
    put(s, "Keeper of the Accord")
    for cid in [c.id for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"]:
        act(s, "p2", type="move", card_ids=[cid], to={"player": "p2", "zone": "battlefield"})
    to_turn(s, 3)  # Bob's end step: two creatures to Alice's one
    assert len(tokens(s)) == 1
    roundtrip(s)


def test_that_player_controlling_as_many_creatures_is_not_more(cards):
    s = build(cards, ("Keeper of the Accord",), ("Grizzly Bears",), forests=30, islands=30)
    put(s, "Keeper of the Accord")
    put(s, "Grizzly Bears", "p2")
    to_turn(s, 3)
    assert not tokens(s)
    roundtrip(s)


def test_exactly_one_creature(cards):
    s = build(cards, ("Demonic Rising", "Llanowar Elves"), forests=30, islands=30)
    put(s, "Demonic Rising")
    put(s, "Llanowar Elves")
    to_turn(s, 2)
    assert len(tokens(s)) == 1
    roundtrip(s)


def test_not_exactly_one_creature(cards):
    s = build(cards, ("Demonic Rising",), forests=30, islands=30)
    put(s, "Demonic Rising")  # no creature at all
    to_turn(s, 2)
    assert not tokens(s)
    roundtrip(s)


def test_the_condition_is_read_from_the_table_each_time_it_is_checked(cards):
    """603.4: the same condition is judged as the ability triggers and again as it resolves - from the table as it is then."""
    from app.rules import conditions
    from app.rules.plan import Plan

    s = build(cards, ("Imaginary Pet", "Forest"), forests=30, islands=30)
    empty_hand(s)
    to_hand(s, "Forest")
    ctx = {"controller": "p1", "event": {"players": ["p2"]}}
    mine = conditions.parse("you have a card in hand", objects=True)
    theirs = conditions.parse("that player has no cards in hand", objects=True)
    assert mine == {"value": {"hand": "you"}, "op": ">=", "n": 1} and theirs["as"] == "event"
    assert conditions.holds(Plan(s.state, "p1", s.cards, None), ctx, mine)
    assert conditions.holds(Plan(s.state, "p1", s.cards, None), ctx, theirs)
    empty_hand(s)
    act(s, "p2", type="draw", count=1)
    assert not conditions.holds(Plan(s.state, "p1", s.cards, None), ctx, mine)
    assert not conditions.holds(Plan(s.state, "p1", s.cards, None), ctx, theirs)  # (and "that player" is Bob, not Alice)


def test_it_does_something_when_it_still_holds(cards):
    s = build(cards, ("Lightning Bolt",), ("Farsight Mask",), forests=30, islands=30)
    put(s, "Farsight Mask", "p2")
    hand = len(hand_of(s, "p2"))
    cast_bolt(s, "p2")
    settle(s)  # (an optional draw: answered yes, the first option)
    assert len(hand_of(s, "p2")) == hand + 1
    roundtrip(s)


def test_it_is_checked_as_it_triggers(cards):
    s = build(cards, ("Lightning Bolt",), ("Farsight Mask",), forests=30, islands=30)
    mask = put(s, "Farsight Mask", "p2")
    act(s, "p2", type="tap", card_ids=[mask.id])
    hand = len(hand_of(s, "p2"))
    cast_bolt(s, "p2")
    settle(s)
    assert life(s, "p2") == 37 and len(hand_of(s, "p2")) == hand
    roundtrip(s)


def test_a_creature_that_died_enchanted_is_read_as_it_last_existed(cards):
    s = build(cards, ("Gunner Conscript", "Pacifism", "Lightning Bolt"), forests=30, islands=30)
    put(s, "Gunner Conscript")
    aura = to_hand(s, "Pacifism")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1, "C": 1})
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[on(s, "Gunner Conscript", "battlefield")[0].id])
    settle(s)
    cast_bolt(s, on(s, "Gunner Conscript", "battlefield")[0].id)
    settle(s)  # it died enchanted (603.10a), not equipped: one Junk token
    assert on(s, "Gunner Conscript", "graveyard")
    assert len([c for c in tokens(s) if c.name == "Junk"]) == 1
    roundtrip(s)


def test_a_spell_dealing_damage_to_this_creature(cards):
    s = build(cards, ("Tephraderm", "Lightning Bolt"), forests=30, islands=30)
    put(s, "Tephraderm")
    cast_bolt(s, on(s, "Tephraderm", "battlefield")[0].id)
    settle(s)
    assert life(s, "p1") == 37  # "that spell's controller" took that much
    roundtrip(s)


# -- "defending player …" (508.5): the player the attacking creature attacks ---------------------------------
REAPER = ("Whenever this creature attacks, if defending player has two or fewer cards in hand, it gains flying until end of "
          "turn.")
BEARS = "Whenever this creature attacks, if defending player controls no black nontoken permanents, it doesn't untap during your next untap step."


def attacker(s, text):
    from tests.test_rules_conditionals import token_of

    return token_of(s, "p1", "Specter", "Token Creature — Specter", "3/3", "Haste\n" + text)


def declare(s, creature):
    from tests.test_rules_wave6e_statics import attack_with

    attack_with(s, creature)
    d = s.state.rules.decision
    while d is not None and d.kind == "declare_blockers":  # (no blocks)
        act(s, d.player, type="declare_blockers", blocks=[])
        d = s.state.rules.decision
    settle(s)


def keywords(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).keywords


def test_defending_player_with_few_cards_in_hand(cards):
    s = build(cards, forests=30, islands=30)
    c = attacker(s, REAPER)
    declare(s, c)
    assert "flying" in {k.lower() for k in keywords(s, c)}  # Bob holds no cards
    roundtrip(s)


def test_defending_player_with_many_cards_in_hand(cards):
    s = build(cards, forests=30, islands=30)
    act(s, "p2", type="draw", count=3)
    c = attacker(s, REAPER)
    declare(s, c)
    assert "flying" not in {k.lower() for k in keywords(s, c)}
    roundtrip(s)


def test_defending_player_controls_no_black_nontoken_permanents(cards):
    s = build(cards, (), ("Phyrexian Obliterator",), forests=30, islands=30)
    c = attacker(s, BEARS)
    declare(s, c)
    to_turn(s, 3)
    assert s.state.cards[c.id].tapped  # it didn't untap during its controller's next untap step
    roundtrip(s)


def test_defending_player_controls_a_black_nontoken_permanent(cards):
    s = build(cards, (), ("Phyrexian Obliterator",), forests=30, islands=30)
    put(s, "Phyrexian Obliterator", "p2")
    c = attacker(s, BEARS)
    declare(s, c)
    to_turn(s, 3)
    assert not s.state.cards[c.id].tapped
    roundtrip(s)


def test_draw_cards_equal_to_the_difference(cards):
    s = build(cards, ("Damia, Sage of Stone",), forests=30, islands=30)
    put(s, "Damia, Sage of Stone")
    empty_hand(s)
    act(s, "p1", type="draw", count=2)
    to_turn(s, 3)  # Alice's upkeep: two cards in hand, so five more (the draw step is skipped)
    assert len(hand_of(s, "p1")) == 7
    roundtrip(s)


def test_it_is_the_source_when_nothing_else_is_named(cards):
    s = build(cards, ("Mana Bloom",), forests=30, islands=30)
    bloom = put(s, "Mana Bloom")
    act(s, "p1", type="counter", card_ids=[bloom.id], kind="charge", delta=1)
    to_turn(s, 3)  # a charge counter on it: the condition fails, it stays
    assert on(s, "Mana Bloom", "battlefield")
    act(s, "p1", type="counter", card_ids=[bloom.id], kind="charge", delta=-1)
    to_turn(s, 5)  # none left: "return it" is the Bloom itself
    assert on(s, "Mana Bloom", "hand")
    roundtrip(s)
