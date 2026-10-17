"""Wave 46A: commanders whose only blocker was one line (CR 2026-09-25), real Oracle text
(tests/fixtures/wave46a_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 101.2, 701.6 "Spells and abilities can't be countered" (Spider-Punk): neither a spell nor an ability is countered.
* 120.4b, 202.3e "a source you control with an odd mana value ... deals double that damage" (Obosh): a spell on the stack counts its X.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import pass_until_stack_empty
from tests.test_rules_permissions import cost_of
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave46a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w46a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
PUNK, OBOSH = "Spider-Punk", "Obosh, the Preypiercer"
FULL = [PUNK, OBOSH, "Karrthus, Tyrant of Jund", "Giott, King of the Dwarves", "Polukranos, Unchained", "Edgewalker", "Ragemonger", "Morophon, the Boundless", "Eluge, the Shoreless Sea", "Jared Carthalion, True Heir"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def cast(s, name, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=to_hand(s, name, pid).id, **kw)


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


# ---- 101.2, 701.6: Spider-Punk ---------------------------------------------------------------------------------------------------------------------
def counter_a_bolt(s, punk):
    if punk:
        put(s, PUNK)
    mana(s, R=1)
    bolt = to_hand(s, "Lightning Bolt")
    counter = to_hand(s, "Counterspell", "p2")
    mana(s, "p2", U=2)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[bolt.id])
    pass_until_stack_empty(s)


def test_spider_punk_keeps_a_spell_from_being_countered(cards):
    s = build(cards, [PUNK, "Lightning Bolt"], ["Counterspell"])
    counter_a_bolt(s, True)
    assert life(s, "p2") == 37 and zone_of(s, "Counterspell", "p2") == "p2:graveyard"
    check(s)


def test_without_spider_punk_the_spell_is_countered(cards):
    s = build(cards, [PUNK, "Lightning Bolt"], ["Counterspell"])
    counter_a_bolt(s, False)
    assert life(s, "p2") == 40 and zone_of(s, "Lightning Bolt") == "p1:graveyard"
    check(s)


def stifle_the_enters_trigger(s):
    mana(s, G=2)
    stifle = to_hand(s, "Stifle", "p2")
    mana(s, "p2", U=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Elvish Visionary").id)
    hand = len(s.state.zones["p1:hand"])
    for _ in range(8):  # until Bob has priority with the enters trigger on top of the stack
        top = s.state.zones.get("stack") and s.state.cards[s.state.zones["stack"][-1]]
        if top and top.ability is not None and s.state.rules.priority == "p2":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=stifle.id, targets=[top.id])
    pass_until_stack_empty(s)
    return len(s.state.zones["p1:hand"]) - hand


def test_spider_punk_keeps_an_ability_from_being_countered(cards):
    s = build(cards, [PUNK, "Elvish Visionary"], ["Stifle"])
    put(s, PUNK)
    assert stifle_the_enters_trigger(s) == 1  # the draw happened: Stifle did nothing
    check(s)


def test_without_spider_punk_stifle_counters_the_ability(cards):
    s = build(cards, [PUNK, "Elvish Visionary"], ["Stifle"])
    assert stifle_the_enters_trigger(s) == 0
    check(s)


# ---- 120.4b, 202.3e: Obosh -------------------------------------------------------------------------------------------------------------------------
def test_obosh_doubles_the_damage_of_sources_with_an_odd_mana_value_only(cards):
    s = build(cards, [OBOSH, "Lightning Bolt", "Stoke the Flames"], [])
    put(s, OBOSH)
    mana(s, R=5)
    cast(s, "Lightning Bolt", targets=["p2"])  # mana value 1: 3 doubled
    pass_until_stack_empty(s)
    assert life(s, "p2") == 40 - 6
    cast(s, "Stoke the Flames", targets=["p2"])  # mana value 4: 4 as printed
    pass_until_stack_empty(s)
    assert life(s, "p2") == 40 - 6 - 4
    check(s)


def test_obosh_counts_the_x_of_a_spell_on_the_stack(cards):
    s = build(cards, [OBOSH, "Blaze"], [])
    put(s, OBOSH)
    mana(s, R=8)
    cast(s, "Blaze", x_value=2, targets=["p2"])  # {X}{R} with X=2: mana value 3, odd: 2 doubled
    pass_until_stack_empty(s)
    assert life(s, "p2") == 40 - 4
    t = build(cards, [OBOSH, "Blaze"], [])
    put(t, OBOSH)
    mana(t, R=8)
    cast(t, "Blaze", x_value=3, targets=["p2"])  # X=3: mana value 4, even: 3 as printed
    pass_until_stack_empty(t)
    assert life(t, "p2") == 40 - 3
    check(s)
    check(t)


def test_obosh_does_not_double_an_opponents_sources(cards):
    s = build(cards, [OBOSH, "Elvish Visionary"], ["Lightning Bolt"])
    put(s, OBOSH)
    mana(s, G=2)
    mana(s, "p2", R=1)
    bolt = to_hand(s, "Lightning Bolt", "p2")  # (in hand first, so Bob gets priority)
    cast(s, "Elvish Visionary")
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])  # in response: a source Alice doesn't control
    pass_until_stack_empty(s)
    assert life(s, "p1") == 37
    check(s)


# ---- 608.2c, 611.2a: Karrthus ----------------------------------------------------------------------------------------------------------------------
KARRTHUS, GIOTT, POLUKRANOS = "Karrthus, Tyrant of Jund", "Giott, King of the Dwarves", "Polukranos, Unchained"


def on_table(s, name, pid):
    return s.state.cards[card_named(s, name, pid).id]


def test_karrthus_takes_every_dragon_and_untaps_them(cards):
    s = build(cards, [KARRTHUS], ["Shivan Dragon"])
    dragon = put(s, "Shivan Dragon", "p2")
    act(s, "p2", type="tap", card_ids=[dragon.id], tapped=True)
    mana(s, R=5, B=1, G=1)
    cast(s, KARRTHUS)
    pass_until_stack_empty(s)
    d = on_table(s, "Shivan Dragon", "p2")
    assert d.controller == "p1" and not d.tapped  # indefinitely Alice's, untapped
    check(s)


def test_karrthus_leaves_creatures_that_are_not_dragons_alone(cards):
    s = build(cards, [KARRTHUS, "Grizzly Bears"], [])
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="tap", card_ids=[bears.id], tapped=True)
    mana(s, R=5, B=1, G=1)
    cast(s, KARRTHUS)
    pass_until_stack_empty(s)
    assert on_table(s, "Grizzly Bears", "p1").tapped
    check(s)


# ---- 603.2c: Giott ---------------------------------------------------------------------------------------------------------------------------------
def choose(s, ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def cast_beside_giott(s, name, **m):
    put(s, GIOTT)
    forest = to_hand(s, "Forest")  # (the card to discard)
    mana(s, **m)
    cast(s, name)
    return forest


@pytest.mark.parametrize(("name", "cost"), [("Dwarven Trader", {"R": 1}), ("Bronze Sword", {"R": 1})])
def test_giott_triggers_for_another_dwarf_and_for_an_equipment(cards, name, cost):
    s = build(cards, [GIOTT, name], [])
    forest = cast_beside_giott(s, name, **cost)
    choose(s, ["pay"])  # the optional discard (the only card in hand), then the draw
    assert s.state.cards[forest.id].zone == "p1:graveyard" and len(s.state.zones["p1:hand"]) == 1
    check(s)


def test_giott_does_not_trigger_for_a_creature_that_is_neither(cards):
    s = build(cards, [GIOTT, "Grizzly Bears"], [])
    cast_beside_giott(s, "Grizzly Bears", G=2)
    assert s.state.rules.decision is None and not s.state.zones.get("stack")  # (no optional discard was offered)
    check(s)


# ---- 702.138b, 614.1c: Polukranos ------------------------------------------------------------------------------------------------------------------
def settle_decisions(s):
    for _ in range(40):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack") and not s.state.rules.pending_triggers:
            return
        if d is not None:
            choose(s, [o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")


def test_polukranos_enters_with_six_counters_cast_and_twelve_escaped(cards):
    s = build(cards, [POLUKRANOS, "Grizzly Bears", "Llanowar Elves", "Memnite", "Ornithopter", "Snapcaster Mage"], [])
    mana(s, B=3, G=3)
    cast(s, POLUKRANOS)
    settle_decisions(s)
    assert on_table(s, POLUKRANOS, "p1").counters.get("+1/+1") == 6  # cast from hand: 614.1c
    polu = card_named(s, POLUKRANOS)
    act(s, "p1", type="move", card_ids=[polu.id], to={"player": "p1", "zone": "graveyard"})
    for name in ("Grizzly Bears", "Llanowar Elves", "Memnite", "Ornithopter", "Snapcaster Mage"):
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[card_named(s, "Forest").id], to={"player": "p1", "zone": "graveyard"})
    mana(s, B=3, G=3)
    act(s, "p1", type="cast_spell", card_id=polu.id)  # escape {4}{B}{G}, exile six other cards: 702.138a
    settle_decisions(s)
    assert on_table(s, POLUKRANOS, "p1").zone == "p1:battlefield"
    assert on_table(s, POLUKRANOS, "p1").counters.get("+1/+1") == 12  # escaped: the larger amount instead
    check(s)


# ---- 118.7b, 118.7c: colored reductions that spill nowhere (Edgewalker, Ragemonger, Morophon) ---------------------------------------------------------
EDGEWALKER, RAGEMONGER, MOROPHON = "Edgewalker", "Ragemonger", "Morophon, the Boundless"


def cost(s, name, pid="p1"):
    return cost_of(s, on_table_or_hand(s, name, pid), s.cards)


def on_table_or_hand(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id]


def test_edgewalker_takes_only_the_white_and_black_symbols_off_cleric_spells(cards):
    s = build(cards, [EDGEWALKER, "Monk Idealist", "Skirsdag High Priest", "Dune Diviner", "Grizzly Bears"], [])
    put(s, EDGEWALKER)
    assert cost(s, "Monk Idealist") == "{2}"  # {2}{W}: the {W} goes, the generic part stays
    assert cost(s, "Skirsdag High Priest") == "{1}"  # {1}{B}
    assert cost(s, "Dune Diviner") == "{2}{G}"  # a Cleric with neither color: "only the amount of colored mana", nothing is taken from generic
    assert cost(s, "Grizzly Bears") == "{1}{G}"  # not a Cleric
    check(s)


def test_without_edgewalker_nothing_is_reduced(cards):
    s = build(cards, [EDGEWALKER, "Monk Idealist"], [])
    assert cost(s, "Monk Idealist") == "{2}{W}"
    check(s)


def test_morophon_reduces_every_color_of_the_chosen_type(cards):
    s = build(cards, [MOROPHON, "Elvish Visionary", "Grizzly Bears"], [])
    mana(s, R=7)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, MOROPHON).id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    choose(s, [next(o.id for o in d.options if o.label == "Elf" or o.id == "Elf")])
    pass_until_stack_empty(s)
    assert on_table_or_hand(s, MOROPHON).zone == "p1:battlefield"
    assert cost(s, "Elvish Visionary") == "{1}"  # an Elf, {1}{G}: the {G} goes
    assert cost(s, "Grizzly Bears") == "{1}{G}"  # a Bear
    check(s)


# ---- 118.7b, 601.2i: Eluge ---------------------------------------------------------------------------------------------------------------------------
ELUGE = "Eluge, the Shoreless Sea"


def flood(s, n):
    for _ in range(n):
        land = put(s, "Forest")
        act(s, "p1", type="set_counter", card_id=land.id, kind="flood", value=1)


def test_eluge_takes_a_blue_symbol_off_the_first_instant_or_sorcery_for_each_flooded_land(cards):
    s = build(cards, [ELUGE, "Counterspell", "Lightning Bolt", "Grizzly Bears"], [])
    put(s, ELUGE)
    assert cost(s, "Counterspell") == "{U}{U}"  # no land with a flood counter yet
    flood(s, 1)
    assert cost(s, "Counterspell") == "{U}"
    assert cost(s, "Grizzly Bears") == "{1}{G}"  # not an instant or sorcery
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=["p2"])  # {R}: no {U} in it and no generic, so nothing to take off (118.7b)
    pass_until_stack_empty(s)
    assert cost(s, "Counterspell") == "{U}{U}"  # only the first instant or sorcery each turn
    check(s)


# ---- 725.4: Jared Carthalion ---------------------------------------------------------------------------------------------------------------------------
JARED = "Jared Carthalion, True Heir"


def test_jared_makes_an_opponent_the_monarch_and_alice_cannot_take_it_back_this_turn(cards):
    s = build(cards, [JARED, "Palace Sentinels"], [])
    mana(s, R=5, G=1, W=1)
    cast(s, JARED)
    choose(s, ["p2"])  # the enters trigger's target opponent
    pass_until_stack_empty(s)
    assert s.state.table.monarch == "p2"
    mana(s, R=3, W=1)
    cast(s, "Palace Sentinels")  # "When this creature enters, you become the monarch."
    pass_until_stack_empty(s)
    assert s.state.table.monarch == "p2"  # Alice can't become the monarch this turn
    check(s)


def test_without_jared_the_same_creature_makes_alice_the_monarch(cards):
    s = build(cards, ["Palace Sentinels"], [])
    mana(s, R=3, W=1)
    cast(s, "Palace Sentinels")
    pass_until_stack_empty(s)
    assert s.state.table.monarch == "p1"
    check(s)
