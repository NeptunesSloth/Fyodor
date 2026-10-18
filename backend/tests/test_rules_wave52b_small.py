"""Wave 52B: triggered-ability wordings the grammar did not read yet (CR 2026-09-25), real Oracle text (tests/fixtures/wave52b_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 603.4: "Whenever a Mountain you control enters, if you control at least five other Mountains, …" (Valakut, the Molten Pinnacle; Roiling Canopy): "other" is other than
  the Mountain that entered (six in all), checked as it triggers and again as it resolves; Valakut's damage is optional ("you may have this land deal 3 damage").
* 603.2, 702.29d, 601.2i: "When you cast or cycle Drownyard Lurker, …" is two triggers, one for the cast and one for the cycling.
* 608.2c: "create a 2/2 Robot token and attach this Equipment to it" are two instructions in order; "When this Case enters" (719) is "this" and a type word.
* 706.3: a results table's "Create two of those tokens." (Swarming Goblins) is the token the row above made.
"""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import pick, token_of, until_asked
from tests.test_rules_wave12a_counters_keywords import answer, rolls  # noqa: I001
from tests.test_rules_wave33b_modal import cast as cast_choosing
from tests.test_rules_wave34b_activated import next_turn, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand, zone_of
from tests.wave52b_kit import open_repo, settle

LURKER, TUSKER, VALAKUT, CANOPY = "Drownyard Lurker", "Warped Tusker", "Valakut, the Molten Pinnacle", "Roiling Canopy"
PAN, BOOSTERS, GOBLINS, PULSE, GARDEN = "Field-Tested Frying Pan", "Auxiliary Boosters", "Swarming Goblins", "Case of the Crimson Pulse", "Case of the Trampled Garden"
SIEGE = "Frontier Siege"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [LURKER, TUSKER, VALAKUT, CANOPY, PAN, BOOSTERS, GOBLINS, PULSE, GARDEN, SIEGE])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def on_field(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:battlefield"]


def table(cards, spells=(), land="Mountain", lands=12):
    """Alice with ``spells`` (one each) and ``lands`` of one basic land type, Bob with islands, in her precombat main phase."""
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in spells), (lands, land)])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def lands_out(s, name, n, pid="p1"):
    """``n`` basic lands of that name already on the battlefield (put there by hand: no trigger)."""
    for c in [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:library"][:n]:
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})


def play_land(s, name, pid="p1"):
    """Play the next ``name`` from the library as the turn's land (it enters, so it triggers)."""
    c = next(c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:library")
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    act(s, pid, type="play_land", card_id=c.id)


# -- Valakut, the Molten Pinnacle / Roiling Canopy ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("others", "triggers"), [(4, False), (5, True)])
def test_valakut_needs_five_other_mountains_besides_the_one_that_entered(cards, others, triggers):
    s = table(cards, [VALAKUT])
    put(s, VALAKUT)
    lands_out(s, "Mountain", others)  # (Valakut is no Mountain)
    play_land(s, "Mountain")
    d = until_asked(s)
    assert (d is not None) is triggers
    if triggers:
        assert d.player == "p1"
        pick(s, "p2")
        settle(s, "yes")
        assert life(s, "p2") == 37
    check(s)


def test_valakut_may_decline_the_damage(cards):
    s = table(cards, [VALAKUT])
    put(s, VALAKUT)
    lands_out(s, "Mountain", 5)
    play_land(s, "Mountain")
    until_asked(s)
    pick(s, "p2")
    settle(s, "no")
    assert life(s, "p2") == 40
    check(s)


@pytest.mark.parametrize(("others", "boost"), [(4, (1, 1)), (5, (4, 4))])
def test_roiling_canopy_pumps_a_creature_at_six_forests(cards, others, boost):
    s = table(cards, [CANOPY, "Llanowar Elves"], land="Forest")
    put(s, CANOPY)
    put(s, "Llanowar Elves")
    lands_out(s, "Forest", others)
    play_land(s, "Forest")
    until_asked(s)
    if boost[0] > 1:
        pick(s, card_named(s, "Llanowar Elves").id)
    settle(s)
    assert pt(s, "Llanowar Elves") == boost  # +3/+3 until end of turn
    check(s)


# -- When you cast or cycle ~ ------------------------------------------------------------------------------------------------------------------
def spawns(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Eldrazi Spawn" and c.controller == pid and c.zone == f"{pid}:battlefield"]


@pytest.mark.parametrize("name", [LURKER, TUSKER])
def test_cast_trigger_of_cast_or_cycle(cards, name):
    s = build(cards, [name], [])
    c = to_hand(s, name)
    mana(s, C=7)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert zone_of(s, name) == "p1:battlefield" and len(spawns(s)) == 1
    check(s)


@pytest.mark.parametrize(("name", "cost"), [(LURKER, {"C": 2, "U": 1}), (TUSKER, {"C": 2, "G": 1})])
def test_cycle_trigger_of_cast_or_cycle(cards, name, cost):
    s = build(cards, [name], [])
    c = to_hand(s, name)
    mana(s, **cost)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=2)
    answer(s)
    assert zone_of(s, name) == "p1:graveyard" and len(spawns(s)) == 1
    check(s)


# -- Case of the Crimson Pulse / Case of the Trampled Garden -----------------------------------------------------------------------------------
def test_crimson_pulse_discards_then_draws_two(cards):
    s = build(cards, [PULSE, "Llanowar Elves"], [])
    case = to_hand(s, PULSE)
    elves = to_hand(s, "Llanowar Elves")
    hand = len(s.state.zones["p1:hand"])
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=case.id)
    answer(s, [elves.id])
    assert zone_of(s, "Llanowar Elves") == "p1:graveyard" and zone_of(s, PULSE) == "p1:battlefield"
    assert len(s.state.zones["p1:hand"]) == hand - 2 + 2  # the Case and the discarded card left, two drawn
    check(s)


def test_trampled_garden_distributes_two_counters(cards):
    s = build(cards, [GARDEN], [])
    a = token_of(s, "p1", "Mine A", "Creature — Bear", "2/2")
    b = token_of(s, "p1", "Mine B", "Creature — Bear", "2/2")
    case = to_hand(s, GARDEN)
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=case.id)
    answer(s, [a.id, b.id], ("divide", [1, 1]))
    assert (s.state.cards[a.id].counters.get("+1/+1", 0), s.state.cards[b.id].counters.get("+1/+1", 0)) == (1, 1)
    check(s)


# -- Field-Tested Frying Pan / Auxiliary Boosters ----------------------------------------------------------------------------------------------
def test_frying_pan_makes_a_food_and_a_halfling_and_attaches_to_the_halfling(cards):
    s = build(cards, [PAN], [])
    pan = to_hand(s, PAN)
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=pan.id)
    answer(s)
    halfling = next(c for c in s.state.cards.values() if c.name == "Halfling" and c.zone == "p1:battlefield")
    assert any(c.name == "Food" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    assert s.state.cards[pan.id].attached_to == halfling.id
    check(s)


def test_auxiliary_boosters_attaches_to_the_robot(cards):
    s = build(cards, [BOOSTERS], [])
    eq = to_hand(s, BOOSTERS)
    mana(s, W=1, C=4)
    act(s, "p1", type="cast_spell", card_id=eq.id)
    answer(s)
    robot = next(c for c in s.state.cards.values() if c.name == "Robot" and c.zone == "p1:battlefield")
    assert s.state.cards[eq.id].attached_to == robot.id
    check(s)


# -- Swarming Goblins -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("die", "made"), [(1, 1), (9, 1), (10, 2), (19, 2), (20, 3)])
def test_swarming_goblins_table_of_those_tokens(cards, monkeypatch, die, made):
    rolls(monkeypatch, die)
    s = build(cards, [GOBLINS], [])
    c = to_hand(s, GOBLINS)
    mana(s, R=1, C=4)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert len([x for x in s.state.cards.values() if x.name == "Goblin" and x.is_token and x.zone == "p1:battlefield"]) == made
    check(s)


# -- Frontier Siege ---------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("word", "mana_added"), [("Khans", 2), ("Dragons", 0)])
def test_frontier_siege_khans_adds_mana_at_each_of_your_main_phases(cards, word, mana_added):
    s = build(cards, [SIEGE], [])
    to_hand(s, SIEGE)
    mana(s, G=1, C=3)
    cast_choosing(s, SIEGE, prefer=(word,))
    assert zone_of(s, SIEGE) == "p1:battlefield"
    next_turn(s)  # the precombat main phase of Alice's next turn
    settle(s)
    assert s.state.players["p1"].mana.get("G", 0) == mana_added
    to_phase(s, "main2")
    settle(s)
    assert s.state.players["p1"].mana.get("G", 0) == mana_added  # (the first main phase's mana emptied with the phase, 500.5)
    check(s)


# -- Hammerhead Tyrant / Mana Echoes / Seasoned Dungeoneer / Sandstone Oracle, Slithermuse ------------------------------------------------------
TYRANT, ECHOES, DUNGEONEER, ORACLE, MUSE = "Hammerhead Tyrant", "Mana Echoes", "Seasoned Dungeoneer", "Sandstone Oracle", "Slithermuse"


@pytest.mark.parametrize("name", [TYRANT, ECHOES, DUNGEONEER, ORACLE, MUSE])
def test_the_second_batch_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_hammerhead_tyrant_bounces_only_a_permanent_not_costlier_than_the_spell(cards):
    # 202.3: "mana value less than or equal to that spell's mana value" (the spell on the stack, X counted: 202.3e)
    s = build(cards, [TYRANT, "Lightning Bolt"], ["Llanowar Elves", "Grizzly Bears"])
    put(s, TYRANT)
    put(s, "Llanowar Elves", "p2")  # mana value 1
    put(s, "Grizzly Bears", "p2")  # mana value 2
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    d = until_asked(s)
    assert d is not None and {o.id for o in d.options} == {card_named(s, "Llanowar Elves", "p2").id}  # (the Bears cost 2: more than the Bolt's 1)
    pick(s, card_named(s, "Llanowar Elves", "p2").id)
    settle(s)
    assert zone_of(s, "Llanowar Elves", "p2") == "p2:hand" and zone_of(s, "Grizzly Bears", "p2") == "p2:battlefield"
    check(s)


@pytest.mark.parametrize(("others", "amount"), [(0, 1), (2, 3)])
def test_mana_echoes_counts_the_creatures_sharing_a_type_with_the_one_that_entered(cards, others, amount):
    # the entering Elf Druid counts itself and every Elf you control; a Goblin doesn't
    s = build(cards, [ECHOES, "Llanowar Elves"], [])
    put(s, ECHOES)
    for i in range(others):
        token_of(s, "p1", f"Elf {i}", "Creature — Elf Warrior", "1/1")
    token_of(s, "p1", "Goblin", "Creature — Goblin", "1/1")
    elves = to_hand(s, "Llanowar Elves")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=elves.id)
    settle(s, "yes")
    assert s.state.players["p1"].mana.get("C", 0) == amount
    check(s)


def test_seasoned_dungeoneer_explores_the_attacking_rogue(cards):
    s = build(cards, [DUNGEONEER], [])
    rogue = token_of(s, "p1", "Pickpocket", "Token Creature — Human Rogue", "2/2")
    put(s, DUNGEONEER)
    next_turn(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": rogue.id, "target": "p2"}])
    hand = len(s.state.zones["p1:hand"])
    top = s.state.zones["p1:library"][0]
    answer(s)
    assert s.state.cards[top].zone == "p1:hand" and len(s.state.zones["p1:hand"]) == hand + 1  # (a Forest on top: a land card goes to the hand, 701.44a)
    assert s.state.cards[rogue.id].counters.get("+1/+1", 0) == 0
    check(s)


# -- Sandstone Oracle / Slithermuse -----------------------------------------------------------------------------------------------------------
def test_sandstone_oracle_draws_the_difference_when_the_opponent_has_more_cards(cards):
    s = build(cards, [ORACLE], [])
    oracle = to_hand(s, ORACLE)
    for _ in range(3):  # Bob: 7 cards in hand + 3
        act(s, "p2", type="move", card_ids=[s.state.zones["p2:library"][0]], to={"zone": "hand"})
    mana(s, C=7)
    act(s, "p1", type="cast_spell", card_id=oracle.id)
    mine_before, theirs = len(s.state.zones["p1:hand"]) - 1, len(s.state.zones["p2:hand"])
    answer(s)
    assert len(s.state.zones["p1:hand"]) == mine_before + (theirs - mine_before)  # equal now
    assert len(s.state.zones["p1:hand"]) == len(s.state.zones["p2:hand"])
    check(s)


def test_sandstone_oracle_draws_nothing_when_the_opponent_has_no_more(cards):
    s = build(cards, [ORACLE], [])
    oracle = to_hand(s, ORACLE)
    mana(s, C=7)
    act(s, "p1", type="cast_spell", card_id=oracle.id)
    mine = len(s.state.zones["p1:hand"])
    answer(s)
    assert len(s.state.zones["p1:hand"]) == mine
    check(s)


def test_slithermuse_draws_the_difference_as_it_leaves(cards):
    s = build(cards, [MUSE], [])
    put(s, MUSE)
    for _ in range(4):
        act(s, "p2", type="move", card_ids=[s.state.zones["p2:library"][0]], to={"zone": "hand"})
    act(s, "p1", type="set_damage", card_ids=[card_named(s, MUSE).id], value=20)  # lethal damage: it dies (704.5g)
    act(s, s.state.rules.priority or "p1", type="pass_priority")
    answer(s)
    assert zone_of(s, MUSE) == "p1:graveyard"
    assert len(s.state.zones["p1:hand"]) == len(s.state.zones["p2:hand"])
    check(s)
