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
from tests.test_rules_wave33b_modal import stops
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


def table(cards, spells=(), land="Mountain", lands=12, players=2):
    """Alice with ``spells`` (one each) and ``lands`` of one basic land type, Bob (and Carol) with islands, in her precombat main phase."""
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in spells), (lands, land)])
    others = [PlayerSetup(n, cards=deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])) for n in ("Bob", "Carol")[: players - 1]]
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), *others], shuffle=False)), cards=cards)
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


# -- Endurance / Deadbridge Chant -------------------------------------------------------------------------------------------------------------
ENDURANCE, CHANT = "Endurance", "Deadbridge Chant"


@pytest.mark.parametrize("name", [ENDURANCE, CHANT])
def test_the_third_batch_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


@pytest.mark.parametrize("target", ["p2", "p1"])
def test_endurance_puts_the_targets_graveyard_on_the_bottom_of_their_library(cards, target):
    s = build(cards, [ENDURANCE], [])
    c = to_hand(s, ENDURANCE)
    for pid in ("p1", "p2"):  # two cards in each graveyard
        act(s, pid, type="move", card_ids=s.state.zones[f"{pid}:library"][:2], to={"zone": "graveyard"})
    gy = list(s.state.zones[f"{target}:graveyard"])
    lib = len(s.state.zones[f"{target}:library"])
    other = "p1" if target == "p2" else "p2"
    other_gy = list(s.state.zones[f"{other}:graveyard"])
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s, [target])
    assert s.state.zones[f"{target}:graveyard"] == [] and len(s.state.zones[f"{target}:library"]) == lib + 2
    assert set(s.state.zones[f"{target}:library"][-2:]) == set(gy)  # (the last two: the bottom)
    assert s.state.zones[f"{other}:graveyard"] == other_gy
    check(s)


# -- Deadbridge Chant --------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("card", "where"), [("Llanowar Elves", "p1:battlefield"), ("Lightning Bolt", "p1:hand")])
def test_deadbridge_chant_returns_a_creature_to_the_battlefield_else_to_hand(cards, card, where):
    s = build(cards, [CHANT, card], [])
    put(s, CHANT)
    act(s, "p1", type="move", card_ids=[card_named(s, card).id], to={"zone": "graveyard"})
    stops(s, "upkeep")
    to_phase(s, "upkeep", turn=3)
    settle(s)
    assert zone_of(s, card) == where
    check(s)


# -- Keen Duelist / Parker Luck / Duskmantle Seer ----------------------------------------------------------------------------------------------
DUELIST, LUCK, SEER = "Keen Duelist", "Parker Luck", "Duskmantle Seer"


@pytest.mark.parametrize("name", [DUELIST, LUCK, SEER])
def test_the_reveal_trade_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def tops(s, mine, theirs, below=1):
    """Put these cards on top of Alice's library and ``below`` cards down in Bob's (he draws that many before turn 3's step)."""
    act(s, "p1", type="move", card_ids=[card_named(s, mine).id], to={"player": "p1", "zone": "library"}, position="top")
    act(s, "p2", type="move", card_ids=[card_named(s, theirs, "p2").id], to={"player": "p2", "zone": "library"}, index=below)


def upkeep_trade(cards, name, step="upkeep"):
    s = build(cards, [name, "Lightning Bolt"], ["Counterspell"])
    put(s, name)
    tops(s, "Lightning Bolt", "Counterspell", below=1 if step == "upkeep" else 2)  # mana values 1 and 2
    stops(s, step)
    to_phase(s, step, turn=3)
    return s


def test_keen_duelist_each_loses_life_equal_to_the_other_players_card_and_takes_their_own(cards):
    s = upkeep_trade(cards, DUELIST)
    answer(s, ["p2"])
    assert (life(s, "p1"), life(s, "p2")) == (38, 39)
    assert zone_of(s, "Lightning Bolt") == "p1:hand" and zone_of(s, "Counterspell", "p2") == "p2:hand"
    check(s)


def test_duskmantle_seer_each_player_loses_life_equal_to_their_own_card(cards):
    s = upkeep_trade(cards, SEER)
    answer(s)
    assert (life(s, "p1"), life(s, "p2")) == (39, 38)
    assert zone_of(s, "Lightning Bolt") == "p1:hand" and zone_of(s, "Counterspell", "p2") == "p2:hand"
    check(s)


def test_parker_luck_two_target_players(cards):
    s = upkeep_trade(cards, LUCK, "end")  # (at the beginning of your end step)
    answer(s, ["p1", "p2"])
    assert (life(s, "p1"), life(s, "p2")) == (38, 39)
    assert zone_of(s, "Lightning Bolt") == "p1:hand" and zone_of(s, "Counterspell", "p2") == "p2:hand"
    check(s)


def test_a_player_with_an_empty_library_reveals_nothing_and_costs_the_other_nothing(cards):
    s = build(cards, [DUELIST, "Lightning Bolt"], [])
    put(s, DUELIST)
    act(s, "p2", type="move", card_ids=list(s.state.zones["p2:library"])[1:], to={"zone": "graveyard"})  # one card left: his draw on turn 2 empties the library
    act(s, "p1", type="move", card_ids=[card_named(s, "Lightning Bolt").id], to={"player": "p1", "zone": "library"}, position="top")
    stops(s, "upkeep")
    to_phase(s, "upkeep", turn=3)
    answer(s, ["p2"])
    assert (life(s, "p1"), life(s, "p2")) == (40, 39)  # Alice lost nothing (Bob revealed no card); Bob lost Alice's card's 1
    check(s)


# -- Trouble in Pairs ---------------------------------------------------------------------------------------------------------------------------
TROUBLE = "Trouble in Pairs"


def test_trouble_in_pairs_is_full(cards):
    assert coverage.of_card_data(cards.resolve(TROUBLE)).level == "FULL"


def bobs_turn(s, step):
    """Pass priority to this step of Bob's turn 2, answering nothing."""
    stops(s, step)
    to_phase(s, step, turn=2)


def alice_cards(s):
    return len(s.state.zones["p1:hand"])


def test_trouble_in_pairs_when_an_opponent_attacks_with_two_creatures(cards):
    s = build(cards, [TROUBLE], [])
    put(s, TROUBLE)
    a = token_of(s, "p2", "Raider A", "Creature — Goblin", "1/1")
    b = token_of(s, "p2", "Raider B", "Creature — Goblin", "1/1")
    stops(s, "main1")
    to_phase(s, "main1", turn=2)
    to_phase(s, "declare_attackers", turn=2) if False else None
    for _ in range(10):  # on to Bob's declare attackers
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    mine = alice_cards(s)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p1"}, {"card_id": b.id, "target": "p1"}])
    answer(s)
    assert alice_cards(s) == mine + 1
    check(s)


def test_trouble_in_pairs_one_attacker_is_not_enough(cards):
    s = build(cards, [TROUBLE], [])
    put(s, TROUBLE)
    a = token_of(s, "p2", "Raider A", "Creature — Goblin", "1/1")
    stops(s, "main1")
    to_phase(s, "main1", turn=2)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    mine = alice_cards(s)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p1"}])
    answer(s)
    assert alice_cards(s) == mine
    check(s)


def test_trouble_in_pairs_on_the_opponents_second_draw_of_a_turn(cards):
    s = build(cards, [TROUBLE], [])
    put(s, TROUBLE)
    sage = token_of(s, "p2", "Sage", "Creature — Test", "1/1", text="{1}: Draw a card.")
    stops(s, "main1")
    to_phase(s, "main1", turn=2)  # Bob drew for the turn (his first card)
    mine = alice_cards(s)
    for expected in (mine + 1, mine + 1):  # the second draw triggers it, the third doesn't
        mana(s, "p2", C=1)
        act(s, "p2", type="activate_ability", card_id=sage.id, ability=0)
        answer(s)
        assert alice_cards(s) == expected
    check(s)


def test_trouble_in_pairs_on_the_opponents_second_spell_of_a_turn(cards):
    s = build(cards, [TROUBLE], ["Sol Ring", "Llanowar Elves"])
    put(s, TROUBLE)
    stops(s, "main1")
    to_phase(s, "main1", turn=2)
    mine = alice_cards(s)
    for name, cost, expected in (("Sol Ring", {"C": 1}, mine), ("Llanowar Elves", {"G": 1}, mine + 1)):
        card = to_hand(s, name, "p2")
        mana(s, "p2", **cost)
        act(s, "p2", type="cast_spell", card_id=card.id)
        answer(s)
        assert alice_cards(s) == expected
    check(s)


# -- Malcolm, Keen-Eyed Navigator / Hordewing Skaab -------------------------------------------------------------------------------------------
MALCOLM, SKAAB = "Malcolm, Keen-Eyed Navigator", "Hordewing Skaab"


@pytest.mark.parametrize("name", [MALCOLM, SKAAB])
def test_the_opponents_dealt_damage_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def treasures(s):
    return len([c for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield"])


def unblocked_attack(s, *pairs):
    """Alice's turn 4 (three players): these creatures attack these players, nobody blocks, combat damage is dealt and the triggers settle."""
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in pairs])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack") or s.state.turn.phase in ("declare_attackers", "declare_blockers", "combat_damage", "first_strike_damage"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("combat never ended")


@pytest.mark.parametrize(("targets", "made"), [(("p2", "p3"), 2), (("p2", "p2"), 1)])
def test_malcolm_makes_a_treasure_for_each_opponent_dealt_damage(cards, targets, made):
    s = table(cards, [MALCOLM], players=3)
    put(s, MALCOLM)
    pirates = [token_of(s, "p1", f"Pirate {i}", "Token Creature — Pirate", "1/1") for i in range(2)]
    to_phase(s, "main1", turn=4)
    unblocked_attack(s, *zip(pirates, targets, strict=True))
    assert treasures(s) == made
    check(s)


@pytest.mark.parametrize(("targets", "drawn"), [(("p2", "p3"), 2), (("p3", "p3"), 1)])
def test_hordewing_skaab_draws_then_discards_the_number_of_opponents_dealt_damage(cards, targets, drawn):
    s = table(cards, [SKAAB], players=3)
    put(s, SKAAB)
    zombies = [token_of(s, "p1", f"Zombie {i}", "Token Creature — Zombie", "1/1") for i in range(2)]
    to_phase(s, "main1", turn=4)
    library, graveyard = len(s.state.zones["p1:library"]), len(s.state.zones["p1:graveyard"])
    unblocked_attack(s, *zip(zombies, targets, strict=True))
    assert len(s.state.zones["p1:library"]) == library - drawn and len(s.state.zones["p1:graveyard"]) == graveyard + drawn
    check(s)


# -- Colossal Grave-Reaver / Undead Alchemist / Polluted Cistern ------------------------------------------------------------------------------
REAVER, ALCHEMIST, CISTERN = "Colossal Grave-Reaver", "Undead Alchemist", "Polluted Cistern // Dim Oubliette"


@pytest.mark.parametrize("name", [REAVER, ALCHEMIST, CISTERN])
def test_the_library_to_graveyard_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def to_top(s, names, pid="p1"):
    """These cards on top of the library, first name on top."""
    for name in reversed(names):
        act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"player": pid, "zone": "library"}, position="top")


def test_colossal_grave_reaver_puts_one_of_the_milled_creature_cards_onto_the_battlefield(cards):
    s = build(cards, [REAVER, "Llanowar Elves", "Grizzly Bears", "Lightning Bolt"], [])
    reaver = to_hand(s, REAVER)
    to_top(s, ["Llanowar Elves", "Grizzly Bears", "Lightning Bolt"])
    mana(s, B=1, G=1, C=6)
    act(s, "p1", type="cast_spell", card_id=reaver.id)
    d = until_asked(s)  # "mill three cards" is its own ability; then the other triggers on the batch
    assert d is not None and {s.state.cards[o.id].name for o in d.options} == {"Llanowar Elves", "Grizzly Bears"}  # (the creature cards among the three)
    pick(s, card_named(s, "Grizzly Bears").id)
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield" and zone_of(s, "Llanowar Elves") == "p1:graveyard" and zone_of(s, "Lightning Bolt") == "p1:graveyard"
    check(s)


def test_undead_alchemist_exiles_a_creature_card_milled_from_an_opponents_library_and_makes_a_zombie(cards):
    # its own replacement (a Zombie's combat damage to a player is that many cards milled instead) mills Bob's top four
    s = build(cards, [ALCHEMIST], ["Grizzly Bears", "Lightning Bolt"])
    alchemist = put(s, ALCHEMIST)
    for at, name in enumerate(["Grizzly Bears", "Lightning Bolt"], 2):  # (Bob draws a card or two first, before turn 3)
        act(s, "p2", type="move", card_ids=[card_named(s, name, "p2").id], to={"player": "p2", "zone": "library"}, index=at)
    next_turn(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": alchemist.id, "target": "p2"}])
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack") or s.state.turn.phase in ("declare_attackers", "declare_blockers", "combat_damage", "first_strike_damage"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:exile" and zone_of(s, "Lightning Bolt", "p2") == "p2:graveyard"  # (a creature card only)
    assert len([c for c in s.state.cards.values() if c.name == "Zombie" and c.is_token and c.zone == "p1:battlefield"]) == 1
    assert life(s, "p2") == 40  # (milled instead of damage)
    check(s)


def test_polluted_cistern_costs_each_opponent_a_life_for_each_card_type_milled(cards):
    # the other door ("When you unlock this door, mill three cards, then return a creature card …") mills three: creature, instant, land
    s = build(cards, [CISTERN, "Grizzly Bears", "Lightning Bolt"], [])
    room = to_hand(s, CISTERN)
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=room.id, face=0)
    settle(s)
    to_top(s, ["Grizzly Bears", "Lightning Bolt", "Forest"])
    mana(s, B=1, C=4)
    act(s, "p1", type="unlock_door", card_id=room.id, door=2)
    settle(s)
    assert life(s, "p2") == 37  # three card types among the three cards
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield"
    check(s)


# -- Consuming Aberration -----------------------------------------------------------------------------------------------------------------
ABERRATION = "Consuming Aberration"


def test_consuming_aberration_is_full(cards):
    assert coverage.of_card_data(cards.resolve(ABERRATION)).level == "FULL"


def test_consuming_aberration_reveals_down_to_a_land_and_mills_those_cards(cards):
    s = build(cards, [ABERRATION, "Lightning Bolt"], ["Counterspell", "Arcane Signet"])
    act(s, "p2", type="move", card_ids=s.state.zones["p2:library"][-2:], to={"zone": "graveyard"})  # (its power and toughness are the cards in your opponents' graveyards: a 0/0 dies)
    put(s, ABERRATION)
    to_top(s, ["Counterspell", "Arcane Signet"], "p2")  # then Islands: the third card is a land
    bolt = to_hand(s, "Lightning Bolt")
    library = len(s.state.zones["p2:library"])
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    answer(s)
    assert {zone_of(s, "Counterspell", "p2"), zone_of(s, "Arcane Signet", "p2")} == {"p2:graveyard"}
    assert len(s.state.zones["p2:library"]) == library - 3 and len(s.state.zones["p2:graveyard"]) == 5  # (two before, three revealed: the first land stops it)
    check(s)


# -- The Skullspore Nexus / Temur War Shaman / Nessian Wilds Ravager -----------------------------------------------------------------------------
NEXUS, SHAMAN, RAVAGER = "The Skullspore Nexus", "Temur War Shaman", "Nessian Wilds Ravager"


@pytest.mark.parametrize("name", [NEXUS, SHAMAN, RAVAGER])
def test_the_last_batch_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name  # (the last two: "if …, you may have it fight target creature", a conditional "may have")


def test_skullspore_nexus_makes_one_token_as_big_as_the_total_power_of_the_nontoken_creatures_that_died(cards):
    s = build(cards, [NEXUS, "Llanowar Elves", "Grizzly Bears"], [])
    put(s, NEXUS)
    for name in ("Llanowar Elves", "Grizzly Bears"):
        put(s, name)
    token_of(s, "p1", "Fodder", "Token Creature — Test", "4/4")  # (a token's death counts for nothing)
    ids = [card_named(s, n).id for n in ("Llanowar Elves", "Grizzly Bears")] + [card_named(s, "Fodder").id]
    act(s, "p1", type="set_damage", card_ids=ids, value=20)  # all three die together (704.5g)
    act(s, s.state.rules.priority or "p1", type="pass_priority")
    answer(s)
    fungus = [c for c in s.state.cards.values() if c.name == "Fungus Dinosaur" and c.is_token and c.zone == "p1:battlefield"]
    assert len(fungus) == 1 and pt(s, "Fungus Dinosaur") == (3, 3)  # 1 + 2
    check(s)
