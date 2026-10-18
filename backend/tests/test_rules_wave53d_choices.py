"""Wave 53D: players choosing objects at once (CR 101.4), real Oracle text (tests/fixtures/wave53d_cards.json, from data/cards.sqlite). Every scenario checks the
replay and a save and a load.

* 101.4, 101.4b: the choices are made in APNAP order (or "starting with" a player), each player knowing the earlier choices; a player with no more than the
  number asked chooses all of them; what the choices do happens after all are made, to everything at once.
* Consuming Tide: the permanents nobody chose go back to their owners' hands. Eye of Doom: a doom counter on each chosen permanent. Planar Overlay: one land of each
  basic land type per player. Rejoin the Fight / Dredge the Mire: creature cards from graveyards, put onto the battlefield under your control. Watchers of the Dead:
  two cards stay in each opponent's graveyard. Grenzo's Rebuttal: from the permanents of the player to their left. Sculpted Sunburst: equal or lesser power.
"""

from __future__ import annotations

import json

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, until
from tests.wave9c_kit import card_named, mana, put
from tests.wave53d_kit import (  # noqa: F401
    answer,
    check,
    log,
    loyalty,
    names_on,
    open_repo,
    resolve,
    seen_by_others,
    table,
    to_hand,
)

TIDE, EYE, PLANAR, REJOIN, DREDGE = "Consuming Tide", "Eye of Doom", "Planar Overlay", "Rejoin the Fight", "Dredge the Mire"
WATCHERS, GRENZO, SUNBURST, VALEFOR = "Watchers of the Dead", "Grenzo's Rebuttal", "Sculpted Sunburst", "Summon: Valefor"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [TIDE, EYE, PLANAR, REJOIN, DREDGE, WATCHERS, GRENZO, SUNBURST, VALEFOR])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def cast(s, name, pid="p1", **pool):
    to_hand(s, name, pid)
    mana(s, pid, **pool)
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id)
    return len(s.state.zones[f"{pid}:hand"])  # (the cards left in hand once the spell is on the stack)


def pick(s, pid, *labels):
    """The decision is ``pid``'s: choose the options whose label starts with one of these."""
    d = s.state.rules.decision
    assert d is not None and d.player == pid, (d.player if d else None, pid)
    ids = [o.id for o in d.options if any(o.label.startswith(x) for x in labels)]
    assert len(ids) == len(labels), ([o.label for o in d.options], labels)
    act(s, pid, type="choose", decision_id=d.id, option_ids=ids)


def test_consuming_tide_returns_what_nobody_chose_and_draws_per_opponent_with_more_cards(cards):
    s = table(cards, [TIDE], ["Grizzly Bears"])
    _a1, _a2 = creature(s, "p1", "Alice One"), creature(s, "p1", "Alice Two")
    _b1, _b2 = creature(s, "p2", "Bob One"), creature(s, "p2", "Bob Two")
    creature(s, "p3", "Carol One")
    put(s, "Forest")
    act(s, "p2", type="draw", player="p2", count=3)  # Bob has more cards in hand than Alice will; Carol none
    hand = {p: len(s.state.zones[f"{p}:hand"]) for p in s.state.players}
    cast(s, TIDE, U=2, C=2)
    resolve(s)
    pick(s, "p1", "Alice One")  # the active player first (101.4); Carol controls one: no choice, it is chosen
    assert "Alice chooses" in s.state.rules.decision.prompt or "Alice One" in s.state.rules.decision.prompt
    pick(s, "p2", "Bob Two")
    resolve(s)
    assert names_on(s, "p1") == ["Alice One", "Forest"] and names_on(s, "p2") == ["Bob Two"] and names_on(s, "p3") == ["Carol One"]  # (a land isn't a nonland permanent)
    # the tokens returned to hand cease to exist (111.7); Alice then draws for the opponent with more cards than she has (Bob)
    assert len(s.state.zones["p1:hand"]) == hand["p1"] - 1 + 1  # (she had drawn Consuming Tide: it left her hand; then one card for Bob's bigger hand)
    check(s)


def test_eye_of_doom_a_doom_counter_on_each_chosen_permanent_at_once(cards):
    s = table(cards, [EYE], players=2)
    mine, theirs = creature(s, "p1", "Mine"), creature(s, "p2", "Theirs")
    cast(s, EYE, C=4)
    resolve(s)
    pick(s, "p1", "Theirs")  # any nonland permanent: even an opponent's
    assert "already chosen: Theirs" in s.state.rules.decision.prompt  # (101.4b: Bob knows)
    assert not s.state.cards[theirs.id].counters  # (nothing yet: the counters are put on all of them after the last choice)
    pick(s, "p2", "Theirs")
    resolve(s)
    assert s.state.cards[theirs.id].counters == {"doom": 1}  # chosen twice: one object, one counter
    assert not s.state.cards[mine.id].counters
    check(s)


def test_planar_overlay_one_land_of_each_basic_type_returns(cards):
    s = table(cards, [PLANAR], players=2)
    forest = put(s, "Forest")
    other = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.id != forest.id)
    act(s, "p1", type="move", card_ids=[other.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="create_token", player="p1", token={"name": "Taiga Token", "type_line": "Token Land — Forest Mountain", "text": ""})
    taiga = next(c for c in s.state.cards.values() if c.name == "Taiga Token")
    island = put(s, "Island", "p2")
    cast(s, PLANAR, U=1, C=2)
    resolve(s)
    d = s.state.rules.decision  # Alice: the Forest (three lands are Forests: both Forests and the Taiga token); the Mountain is the token, no choice
    assert d.player == "p1" and len(d.options) == 3
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])  # a Forest card
    resolve(s)
    assert s.state.cards[island.id].zone == "p2:hand"  # Bob's only land of a type: no choice
    assert sorted(s.state.cards[c.id].zone for c in (forest, other)) == ["p1:battlefield", "p1:hand"]
    assert taiga.id not in s.state.cards  # the token (the Mountain, no choice) returned too: a token ceases to exist (111.7)
    check(s)


def test_planar_overlay_a_land_chosen_for_two_types_returns_once(cards):
    s = table(cards, [PLANAR], players=2)
    act(s, "p1", type="create_token", player="p1", token={"name": "Taiga Token", "type_line": "Token Land — Forest Mountain", "text": ""})
    taiga = next(c for c in s.state.cards.values() if c.name == "Taiga Token")
    forest = put(s, "Forest")
    cast(s, PLANAR, U=1, C=2)
    resolve(s)
    pick(s, "p1", "Taiga Token")  # for Forest (the Forest is the other candidate); the Mountain is the token again: both types, one land
    resolve(s)
    assert taiga.id not in s.state.cards and s.state.cards[forest.id].zone == "p1:battlefield"
    check(s)


def test_rejoin_the_fight_the_opponents_each_choose_a_different_creature_card(cards):
    names = ["Llanowar Elves", "Grizzly Bears", "Young Wolf"]
    s = table(cards, [REJOIN, *names])
    dead = [card_named(s, n) for n in names]
    for c in dead:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    cast(s, REJOIN, B=1, C=5)
    resolve(s)
    # Mill three (more cards for the graveyard); then the next opponent in turn order, Bob, chooses, then Carol: a different card
    d = s.state.rules.decision
    assert d.player == "p2" and {o.label.split(" — ")[0] for o in d.options} >= {"Llanowar Elves", "Grizzly Bears", "Young Wolf"}
    first = next(o for o in d.options if o.label.startswith("Grizzly Bears"))
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[first.id])
    d = s.state.rules.decision
    assert d.player == "p3" and first.id not in {o.id for o in d.options}  # "that hasn't been chosen"
    second = next(o for o in d.options if o.label.startswith("Young Wolf"))
    act(s, "p3", type="choose", decision_id=d.id, option_ids=[second.id])
    resolve(s)
    assert s.state.cards[first.id].zone == "p1:battlefield" and s.state.cards[second.id].zone == "p1:battlefield"
    assert s.state.cards[dead[0].id].zone == "p1:graveyard"  # (Llanowar Elves stayed)
    check(s)


def test_dredge_the_mire_each_opponent_chooses_a_creature_card_in_their_own_graveyard(cards):
    s = table(cards, [DREDGE], ["Llanowar Elves", "Grizzly Bears"], ["Young Wolf", "Dregscape Zombie"])
    bob = [card_named(s, n, "p2") for n in ("Llanowar Elves", "Grizzly Bears")]
    carol = [card_named(s, n, "p3") for n in ("Young Wolf", "Dregscape Zombie")]
    for c in bob + carol:
        act(s, c.owner, type="move", card_ids=[c.id], to={"player": c.owner, "zone": "graveyard"})
    cast(s, DREDGE, B=1, C=3)
    resolve(s)
    assert s.state.rules.decision.player == "p2" and {o.label for o in s.state.rules.decision.options} == {"Llanowar Elves", "Grizzly Bears"}
    pick(s, "p2", "Grizzly Bears")
    assert {o.label for o in s.state.rules.decision.options} == {"Young Wolf", "Dregscape Zombie"}  # their own graveyard, not Bob's
    pick(s, "p3", "Dregscape Zombie")
    resolve(s)
    assert s.state.cards[bob[1].id].zone == "p1:battlefield" and s.state.cards[carol[1].id].zone == "p1:battlefield"
    assert s.state.cards[bob[1].id].controller == "p1" and s.state.cards[bob[1].id].owner == "p2"
    assert s.state.cards[bob[0].id].zone == "p2:graveyard" and s.state.cards[carol[0].id].zone == "p3:graveyard"
    check(s)


def test_watchers_of_the_dead_exiles_all_but_two_cards_of_each_opponents_graveyard(cards):
    s = table(cards, [WATCHERS], ["Llanowar Elves", "Grizzly Bears", "Young Wolf", "Dregscape Zombie"], ["Mulldrifter"])
    bob = [card_named(s, n, "p2") for n in ("Llanowar Elves", "Grizzly Bears", "Young Wolf", "Dregscape Zombie")]
    carol = card_named(s, "Mulldrifter", "p3")
    for c in [*bob, carol]:
        act(s, c.owner, type="move", card_ids=[c.id], to={"player": c.owner, "zone": "graveyard"})
    w = put(s, WATCHERS)
    act(s, "p1", type="activate_ability", card_id=w.id, ability=0)
    resolve(s)
    assert s.state.rules.decision.player == "p2" and s.state.rules.decision.max_choices == 2  # Carol has one card: nothing to choose
    pick(s, "p2", "Llanowar Elves", "Young Wolf")
    resolve(s)
    assert [s.state.cards[c.id].zone for c in bob] == ["p2:graveyard", "p2:exile", "p2:graveyard", "p2:exile"]
    assert s.state.cards[carol.id].zone == "p3:graveyard"
    check(s)


def test_grenzo_s_rebuttal_each_player_chooses_from_the_player_to_their_left(cards):
    s = table(cards, [GRENZO])
    a = [creature(s, "p1", n) for n in ("Alice One", "Alice Two")]
    b = [creature(s, "p2", n) for n in ("Bob One", "Bob Two")]
    c = [creature(s, "p3", n) for n in ("Carol One", "Carol Two")]
    cast(s, GRENZO, R=2, C=4)
    resolve(s)
    # "Starting with you": Alice chooses among Bob's permanents (the player to her left), Bob among Carol's, Carol among Alice's (the Ogre token too)
    d = s.state.rules.decision
    assert d.player == "p1" and "among Bob's permanents" in d.prompt and {o.label.split(" — ")[0] for o in d.options} == {"Bob One", "Bob Two"}
    pick(s, "p1", "Bob One")
    d = s.state.rules.decision
    assert d.player == "p2" and "among Carol's permanents" in d.prompt
    pick(s, "p2", "Carol Two")
    d = s.state.rules.decision
    assert d.player == "p3" and {o.label.split(" — ")[0] for o in d.options} == {"Alice One", "Alice Two", "Ogre"}  # the token Grenzo's Rebuttal made counts
    pick(s, "p3", "Ogre")
    resolve(s)
    assert b[0].id not in s.state.cards and c[1].id not in s.state.cards and not any(x.name == "Ogre" for x in s.state.cards.values())
    assert a[0].id in s.state.zones["p1:battlefield"] and a[1].id in s.state.zones["p1:battlefield"]
    assert b[1].id in s.state.zones["p2:battlefield"] and c[0].id in s.state.zones["p3:battlefield"]
    check(s)


def test_sculpted_sunburst_only_creatures_not_chosen_by_anyone_are_exiled(cards):
    s = table(cards, [SUNBURST])
    mine_small, mine_big = creature(s, "p1", "Mine Small", "1/1"), creature(s, "p1", "Mine Big", "3/3")
    bob_small, bob_mid, bob_big = creature(s, "p2", "Bob Small", "2/2"), creature(s, "p2", "Bob Mid", "3/3"), creature(s, "p2", "Bob Big", "4/4")
    carol = creature(s, "p3", "Carol Only", "5/5")
    cast(s, SUNBURST, W=2, C=3)
    resolve(s)
    pick(s, "p1", "Mine Big")  # power 3
    d = s.state.rules.decision
    assert d.player == "p2" and {o.label for o in d.options} == {"Bob Small", "Bob Mid"}  # equal or lesser power than the creature chosen first: the 4/4 isn't allowed
    pick(s, "p2", "Bob Mid")
    resolve(s)  # Carol controls only a 5/5: nothing she can choose
    assert [s.state.cards[c.id].zone for c in (mine_big, bob_mid)] == ["p1:battlefield", "p2:battlefield"]
    assert all(c.id not in s.state.cards for c in (mine_small, bob_small, bob_big, carol))  # (tokens exiled cease to exist)
    check(s)


def test_sculpted_sunburst_with_no_creature_of_your_own_nothing_is_exiled(cards):
    s = table(cards, [SUNBURST], players=2)
    bob = creature(s, "p2", "Bob One", "2/2")
    cast(s, SUNBURST, W=2, C=3)
    resolve(s)
    assert s.state.rules.decision is None and s.state.cards[bob.id].zone == "p2:battlefield"
    check(s)


def test_summon_valefor_each_opponent_returns_a_creature_with_the_greatest_mana_value(cards):
    s = table(cards, [VALEFOR], ["Llanowar Elves", "Grizzly Bears", "Elvish Visionary"], ["Young Wolf", "Mulldrifter"])
    elves, bears, vis = (put(s, n, "p2") for n in ("Llanowar Elves", "Grizzly Bears", "Elvish Visionary"))
    wolf, drifter = put(s, "Young Wolf", "p3"), put(s, "Mulldrifter", "p3")
    cast(s, VALEFOR, U=1, C=4)
    resolve(s)  # the Saga creature enters with a lore counter: chapter I triggers
    d = s.state.rules.decision
    assert d.player == "p2" and {o.label.split(" — ")[0] for o in d.options} == {"Grizzly Bears", "Elvish Visionary"}  # the tie for mana value 2
    pick(s, "p2", "Grizzly Bears")
    resolve(s)  # Carol controls Mulldrifter (mana value 5) alone at that value: no choice
    assert [s.state.cards[c.id].zone for c in (elves, bears, vis)] == ["p2:battlefield", "p2:hand", "p2:battlefield"]
    assert [s.state.cards[c.id].zone for c in (wolf, drifter)] == ["p3:battlefield", "p3:hand"]
    check(s)


# -- parties, balance, a shared type, the revealed cards -------------------------------------------------------------------
STICK, RESTORE, MAGUS, ACT, GRUDGE, INSIGHTS = "Stick Together", "Restore Balance", "Magus of the Balance", "Balancing Act", "Fatal Grudge", "Manifold Insights"


@pytest.mark.parametrize("name", [STICK, RESTORE, MAGUS, ACT, GRUDGE, INSIGHTS])
def test_the_cards_are_full_too(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_stick_together_each_player_keeps_a_party_and_sacrifices_the_rest(cards):
    s = table(cards, [STICK], players=2)
    clerics = [creature(s, "p2", n, type_line="Token Creature — Cleric") for n in ("Cleric One", "Cleric Two")]
    rogue = creature(s, "p2", "Rogue One", type_line="Token Creature — Rogue")
    both = creature(s, "p2", "Wizard Cleric", type_line="Token Creature — Wizard Cleric")
    goblin = creature(s, "p2", "Goblin", type_line="Token Creature — Goblin")
    mine = creature(s, "p1", "Warrior One", type_line="Token Creature — Warrior")
    cast(s, STICK, W=2, C=3)
    resolve(s)
    d = s.state.rules.decision
    assert d.player == "p1" and d.min_choices == 0 and {o.label for o in d.options} == {"Warrior One"}  # only party-type creatures can be chosen
    pick(s, "p1", "Warrior One")
    d = s.state.rules.decision
    assert d.player == "p2" and {o.label for o in d.options} == {"Cleric One", "Cleric Two", "Rogue One", "Wizard Cleric"}  # the Goblin has no party type
    with pytest.raises(Exception, match="party"):  # two Clerics: one party member for a type only (700.8)
        act(s, "p2", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.label in ("Cleric One", "Cleric Two")])
    pick(s, "p2", "Cleric One", "Rogue One", "Wizard Cleric")  # Cleric, Rogue and Wizard (the Wizard Cleric counts for one type)
    resolve(s)
    assert clerics[0].id in s.state.zones["p2:battlefield"] and rogue.id in s.state.zones["p2:battlefield"] and both.id in s.state.zones["p2:battlefield"]
    assert clerics[1].id not in s.state.cards and goblin.id not in s.state.cards and mine.id in s.state.zones["p1:battlefield"]
    check(s)


def test_stick_together_two_creatures_for_the_same_member_are_no_party(cards):
    s = table(cards, [STICK], players=2)
    both = creature(s, "p2", "Wizard Cleric", type_line="Token Creature — Wizard Cleric")
    cleric = creature(s, "p2", "Cleric One", type_line="Token Creature — Cleric")
    cast(s, STICK, W=2, C=3)
    resolve(s)
    d = s.state.rules.decision
    assert d.player == "p2"
    pick(s, "p2", "Wizard Cleric", "Cleric One")  # a Cleric (the Wizard) and a Cleric: the Wizard Cleric can stand for the Wizard
    resolve(s)
    assert both.id in s.state.zones["p2:battlefield"] and cleric.id in s.state.zones["p2:battlefield"]
    check(s)


def test_balancing_act_everyone_keeps_as_many_permanents_and_cards_as_the_player_with_the_fewest(cards):
    s = table(cards, [ACT])
    [creature(s, "p1", f"A{i}") for i in range(4)]
    [creature(s, "p2", f"B{i}") for i in range(2)]
    [creature(s, "p3", f"C{i}") for i in range(3)]
    for p, k in (("p1", 4), ("p2", 1), ("p3", 3)):
        act(s, p, type="draw", player=p, count=k)
    cast(s, ACT, W=2, C=2)
    before = {p: len(s.state.zones[f"{p}:hand"]) for p in s.state.players}  # (with Balancing Act on the stack)
    resolve(s)
    # permanents: Alice 4, Bob 2, Carol 3 (the fewest is 2): Alice keeps two, Carol keeps two; Bob keeps both
    d = s.state.rules.decision
    assert d.player == "p1" and d.max_choices == 2
    pick(s, "p1", "A0", "A1")
    d = s.state.rules.decision
    assert d.player == "p3" and d.max_choices == 2 and "already chosen: A0, A1" in d.prompt or d.player == "p3"
    pick(s, "p3", "C2", "C1")
    d = s.state.rules.decision  # then the hands: Alice has the most cards and discards down to the fewest
    assert d.player == "p1" and d.kind == "choose_cards" and "Discard" in d.prompt
    resolve_answers = 0
    while s.state.rules.decision is not None and resolve_answers < 6:
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: d.max_choices])
        resolve_answers += 1
    resolve(s)
    assert names_on(s, "p1") == ["A0", "A1"] and names_on(s, "p2") == ["B0", "B1"] and names_on(s, "p3") == ["C1", "C2"]
    assert {p: len(s.state.zones[f"{p}:hand"]) for p in s.state.players} == dict.fromkeys(s.state.players, min(before.values()))  # down to the fewest
    check(s)


def test_magus_of_the_balance_lands_then_cards_then_creatures(cards):
    s = table(cards, [MAGUS], players=2)
    magus = put(s, MAGUS)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None, limit=300)
    for p, k in (("p1", 5), ("p2", 1)):
        act(s, p, type="draw", player=p, count=k)
    lands = [put(s, "Forest") for _ in range(1)]
    for _ in range(2):
        c = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    bob_lands = []
    for _ in range(2):
        c = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2" and c.zone == "p2:library")
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
        bob_lands.append(c)
    mine = [creature(s, "p1", f"A{i}") for i in range(3)]
    theirs = [creature(s, "p2", f"B{i}") for i in range(2)]
    # Alice: 3 lands (+ the mana to pay), 4 creatures with the Magus; Bob: 2 lands, 2 creatures
    mana(s, "p1", W=1, C=4)
    act(s, "p1", type="activate_ability", card_id=magus.id, ability=0)
    resolve(s)
    d = s.state.rules.decision
    assert d.player == "p1" and d.max_choices == 2 and len(d.options) == 3 and "land" in d.prompt  # lands first: Alice keeps two (Bob has two)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:2])
    d = s.state.rules.decision
    assert d.player == "p1" and "Discard" in d.prompt  # then cards in hand, then creatures (Magus of the Balance's order)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: d.max_choices])
    d = s.state.rules.decision
    assert d.player == "p1" and d.max_choices == 2 and "creature" in d.prompt  # the Magus is sacrificed as a cost: three creatures against Bob's two
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:2])
    resolve(s)
    assert len([c for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name == "Forest"]) == 2
    assert len(s.state.zones["p1:hand"]) == len(s.state.zones["p2:hand"])
    assert sum(1 for c in mine if c.id in s.state.zones["p1:battlefield"]) == 2 and sum(1 for c in theirs if c.id in s.state.zones["p2:battlefield"]) == 2
    assert len(lands) == 1 and len(bob_lands) == 2
    check(s)


def test_fatal_grudge_each_opponent_sacrifices_a_permanent_sharing_a_card_type_with_the_one_sacrificed(cards):
    s = table(cards, [GRUDGE, "Frogmite"], ["Sol Ring"], ["Llanowar Elves"])
    frogmite = put(s, "Frogmite")  # an artifact creature: shares a type with both an artifact and a creature
    bob_ring = put(s, "Sol Ring", "p2")
    bob_bear = creature(s, "p2", "Bob Bear")
    bob_land = put(s, "Island", "p2")
    carol_elves = put(s, "Llanowar Elves", "p3")
    to_hand(s, GRUDGE)
    mana(s, "p1", B=1, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, GRUDGE).id)  # the additional cost: Frogmite, her only nonland permanent, is sacrificed
    resolve(s)
    d = s.state.rules.decision  # Bob: an artifact or a creature he controls (not the land); Carol: a creature only
    assert d.player == "p2" and {o.label for o in d.options} == {"Sol Ring", "Bob Bear"}
    pick(s, "p2", "Sol Ring")
    resolve(s)  # Carol's only matching permanent is the Elves: no choice
    assert s.state.cards[frogmite.id].zone == "p1:graveyard" and s.state.cards[bob_ring.id].zone == "p2:graveyard"
    assert carol_elves.id not in s.state.zones["p3:battlefield"] and bob_bear.id in s.state.zones["p2:battlefield"] and bob_land.id in s.state.zones["p2:battlefield"]
    check(s)


def test_manifold_insights_each_opponent_takes_a_different_nonland_card_the_rest_go_to_the_bottom(cards):
    names = ["Llanowar Elves", "Grizzly Bears", "Young Wolf", "Dregscape Zombie", "Mulldrifter", "Elvish Visionary", "Frogmite", "Soul Warden", "Merfolk Looter"]
    s = table(cards, [INSIGHTS, *names])
    lib = [card_named(s, n) for n in names]
    for c in reversed(lib):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "library"}, position="top")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "library"}, position="top")  # a land among the ten revealed
    to_hand(s, INSIGHTS)
    mana(s, "p1", U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, INSIGHTS).id)
    resolve(s)
    d = s.state.rules.decision
    assert d.player == "p2" and forest.id not in {o.id for o in d.options} and len(d.options) == 9  # the next opponent first; nonland cards only
    first = next(o.id for o in d.options if o.label == "Mulldrifter")
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[first])
    d = s.state.rules.decision
    assert d.player == "p3" and first not in {o.id for o in d.options} and len(d.options) == 8  # "a different nonland card"
    second = next(o.id for o in d.options if o.label == "Young Wolf")
    act(s, "p3", type="choose", decision_id=d.id, option_ids=[second])
    resolve(s)
    assert s.state.cards[first].zone == "p1:hand" and s.state.cards[second].zone == "p1:hand"
    library = s.state.zones["p1:library"]
    rest = [c.id for c in lib if c.id not in (first, second)] + [forest.id]
    assert all(c in library[-8:] for c in rest) and len(library) >= 8
    check(s)


# -- bids ---------------------------------------------------------------------------------------------------------------
CONTEST, AUCTION, REWARD = "Mages' Contest", "Illicit Auction", "Pain's Reward"


@pytest.mark.parametrize("name", [CONTEST, AUCTION, REWARD])
def test_the_bidding_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def bid(s, pid, number):
    d = s.state.rules.decision
    assert d is not None and d.player == pid, (d.player if d else None, pid)
    act(s, pid, type="choose", decision_id=d.id, option_ids=[], name=str(number))


def test_pain_s_reward_the_bidding_goes_round_until_the_high_bid_stands(cards):
    s = table(cards, [REWARD])
    hand = cast(s, REWARD, B=1, C=2)
    life0 = {p: s.state.players[p].life for p in s.state.players}
    resolve(s)
    d = s.state.rules.decision
    assert d.player == "p1" and d.options[0].id == "__number__"  # "a bid of any number": Alice types her opening bid
    bid(s, "p1", 2)
    assert s.state.rules.decision.player == "p2" and "high bid is 2 (Alice)" in s.state.rules.decision.prompt
    bid(s, "p2", 5)  # Bob tops it
    assert s.state.rules.decision.player == "p3"  # in turn order after the new high bidder
    bid(s, "p3", "pass")
    assert s.state.rules.decision.player == "p1" and "high bid is 5 (Bob)" in s.state.rules.decision.prompt  # Alice may top the new bid
    bid(s, "p1", 9)
    bid(s, "p2", "pass")
    bid(s, "p3", "pass")  # everybody but Alice has declined to top 9: the bidding ends
    resolve(s)
    assert s.state.players["p1"].life == life0["p1"] - 9 and s.state.players["p2"].life == life0["p2"] and s.state.players["p3"].life == life0["p3"]
    assert len(s.state.zones["p1:hand"]) == hand + 4
    assert "Alice wins the bidding with a bid of 9" in log(s, "p2")
    check(s)


def test_a_bid_must_top_the_high_bid_and_may_exceed_your_life(cards):
    s = table(cards, [REWARD], players=2)
    cast(s, REWARD, B=1, C=2)
    resolve(s)
    bid(s, "p1", 3)
    d = s.state.rules.decision
    for bad in ("3", "2", "x", "-1"):
        with pytest.raises(Exception, match="number|more"):
            act(s, "p2", type="choose", decision_id=d.id, option_ids=[], name=bad)
    bid(s, "p2", 50)  # more life than Bob has (40): allowed, the rulings say it is life loss and not a payment
    bid(s, "p1", "pass")
    resolve(s)
    assert s.state.players["p2"].life == -10
    check(s)


def test_illicit_auction_the_high_bidder_loses_the_life_and_gains_control(cards):
    s = table(cards, [AUCTION], players=2)
    bear = creature(s, "p2", "Bob Bear")
    to_hand(s, AUCTION)
    mana(s, "p1", R=2, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, AUCTION).id, targets=[bear.id])
    resolve(s)  # Alice starts with a bid of 0 (no choice to make); Bob may top it
    assert s.state.rules.decision.player == "p2" and "high bid is 0 (Alice)" in s.state.rules.decision.prompt
    bid(s, "p2", 4)
    bid(s, "p1", 6)
    bid(s, "p2", "pass")
    resolve(s)
    assert s.state.cards[bear.id].controller == "p1" and s.state.players["p1"].life == 34 and s.state.players["p2"].life == 40
    check(s)


def test_illicit_auction_with_no_other_bid_the_creature_costs_nothing(cards):
    s = table(cards, [AUCTION], players=2)
    bear = creature(s, "p2", "Bob Bear")
    to_hand(s, AUCTION)
    mana(s, "p1", R=2, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, AUCTION).id, targets=[bear.id])
    resolve(s)
    bid(s, "p2", "pass")
    resolve(s)
    assert s.state.cards[bear.id].controller == "p1" and s.state.players["p1"].life == 40
    check(s)


def test_mages_contest_counters_the_spell_if_you_win_the_bidding(cards):
    s = table(cards, [CONTEST, "Grizzly Bears"], ["Lightning Bolt"], players=2)
    for p in ("p1", "p2"):
        act(s, p, type="set_prefs", response="on")
    bears = card_named(s, "Grizzly Bears")
    to_hand(s, "Grizzly Bears")
    mana(s, "p1", G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    assert s.state.rules.priority == "p2"  # Bob answers with a Lightning Bolt (on the Bears)...
    bolt = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
    to_hand(s, CONTEST)  # ...which Alice answers with Mages' Contest on the Bolt
    mana(s, "p1", R=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, CONTEST).id, targets=[bolt.id])
    while not (s.state.rules.decision and s.state.rules.decision.player == "p2"):
        act(s, s.state.rules.priority, type="pass_priority")
    life0 = {p: s.state.players[p].life for p in s.state.players}
    assert "high bid is 1 (Alice)" in s.state.rules.decision.prompt  # "You start the bidding with a bid of 1"
    bid(s, "p2", "pass")
    resolve(s)
    assert s.state.players["p1"].life == life0["p1"] - 1  # Alice, the high bidder, loses 1 life (and the Bolt, countered, deals no damage)
    assert s.state.cards[bolt.id].zone == "p2:graveyard"
    check(s)


def test_mages_contest_the_other_player_wins_the_bidding_and_the_spell_stays(cards):
    s = table(cards, [CONTEST, "Grizzly Bears"], ["Lightning Bolt"], players=2)
    for p in ("p1", "p2"):
        act(s, p, type="set_prefs", response="on")
    bears = card_named(s, "Grizzly Bears")
    to_hand(s, "Grizzly Bears")
    mana(s, "p1", G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    bolt = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
    to_hand(s, CONTEST)
    mana(s, "p1", R=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, CONTEST).id, targets=[bolt.id])
    while not (s.state.rules.decision and s.state.rules.decision.player == "p2"):
        act(s, s.state.rules.priority, type="pass_priority")
    life0 = {p: s.state.players[p].life for p in s.state.players}
    bid(s, "p2", 2)
    bid(s, "p1", "pass")
    resolve(s)
    assert s.state.players["p2"].life == life0["p2"] - 2 and s.state.players["p1"].life == life0["p1"] - 3  # (Bob lost the 2 he bid; the Bolt was not countered)
    check(s)


# -- secret choices of objects and numbers; secret council ---------------------------------------------------------------
VOID, SAFE, TRAP = "Call to the Void", "Expert-Level Safe", "Trap the Trespassers"


@pytest.mark.parametrize("name", [VOID, SAFE, TRAP])
def test_the_secret_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_call_to_the_void_secret_choices_revealed_together_each_creature_destroyed_once(cards):
    s = table(cards, [VOID])
    a1, a2 = creature(s, "p1", "Alice One"), creature(s, "p1", "Alice Two")
    b1, b2 = creature(s, "p2", "Bob One"), creature(s, "p2", "Bob Two")
    c1 = creature(s, "p3", "Carol One")
    cast(s, VOID, B=2, C=3)
    resolve(s)
    d = s.state.rules.decision
    assert d.player == "p1" and "a creature you control" in d.prompt and "(secret)" in d.prompt
    pick(s, "p1", "Alice One")
    d = s.state.rules.decision  # a creature she doesn't control: Bob's or Carol's (Carol has only one: but she isn't the question yet)
    assert d.player == "p1" and "a creature you don't control" in d.prompt and {o.label for o in d.options} == {"Bob One — Bob", "Bob Two — Bob", "Carol One — Carol"}
    pick(s, "p1", "Bob One")
    for viewer, seen in seen_by_others(s, "p1"):  # nothing of Alice's two choices is shown
        assert "chooses" not in json.dumps(s.view(viewer)["log"]) and "revealed" not in json.dumps(s.view(viewer)["log"]) and "chose" not in seen, viewer
    assert s.state.rules.decision.player == "p2"
    pick(s, "p2", "Bob Two")  # his own creature
    pick(s, "p2", "Carol One")
    pick(s, "p3", "Bob One")  # Carol's one creature is chosen without a question (it is her only one); then one she doesn't control: Bob One again
    resolve(s)
    assert "The choices are revealed: Alice chose Alice One" in log(s, "p2") and "Bob chose Bob Two" in log(s, "p2")
    assert [c.id in s.state.cards for c in (a1, a2, b1, b2, c1)] == [False, True, False, False, False]  # (Bob One was chosen twice and is destroyed once; Alice Two nobody chose)
    check(s)


def test_expert_level_safe_matching_numbers_open_it_and_a_mismatch_hides_another_card(cards):
    s = table(cards, [SAFE], players=2)
    safe = put(s, SAFE)  # (it did not enter by being cast: its enters trigger is not what is under test)
    top = [c for c in s.state.zones["p1:library"][:3]]
    act(s, "p1", type="move", card_ids=[top[0]], to={"player": "p1", "zone": "exile"})
    mana(s, "p1", C=1)
    act(s, "p1", type="activate_ability", card_id=safe.id, ability=1, targets=["p2"])
    resolve(s)
    d = s.state.rules.decision
    assert d.player == "p1" and {o.label for o in d.options} == {"1", "2", "3"} and "(secret)" in d.prompt
    answer(s, "p1", "2")
    for viewer, seen in seen_by_others(s, "p1"):
        assert "chose" not in seen and "ballot" not in seen, viewer
    assert s.state.rules.decision.player == "p2"
    answer(s, "p2", "3")
    resolve(s)
    assert "The choices are revealed: Alice chose 2; Bob chose 3" in log(s, "p2")
    # they differ: the top card of Alice's library is exiled face down, linked to the Safe
    exiled = [c for c in s.state.zones["p1:exile"] if c != top[0]]
    assert len(exiled) == 1 and s.state.cards[exiled[0]].face_down
    assert safe.id in s.state.zones["p1:battlefield"]
    check(s)


def test_expert_level_safe_matching_choices_return_the_exiled_cards_and_sacrifice_it(cards):
    s = table(cards, [SAFE], players=2)
    cast(s, SAFE, C=2)
    resolve(s)  # it enters: the top two cards of Alice's library are exiled face down
    safe = card_named(s, SAFE)
    exiled = list(s.state.zones["p1:exile"])
    assert len(exiled) == 2 and all(s.state.cards[c].face_down for c in exiled)
    mana(s, "p1", C=1)
    act(s, "p1", type="activate_ability", card_id=safe.id, ability=1, targets=["p2"])
    resolve(s)
    answer(s, "p1", "3")
    answer(s, "p2", "3")
    resolve(s)
    assert s.state.cards[safe.id].zone == "p1:graveyard"
    assert all(s.state.cards[c].zone == "p1:hand" for c in exiled)  # into their owners' hands
    check(s)


def test_trap_the_trespassers_secret_votes_stun_counters_for_each_vote_and_tap(cards):
    s = table(cards, [TRAP])
    mine = creature(s, "p1", "Alice One")
    b1, b2 = creature(s, "p2", "Bob One"), creature(s, "p2", "Bob Two")
    c1 = creature(s, "p3", "Carol One")
    cast(s, TRAP, U=1, C=2)
    resolve(s)
    d = s.state.rules.decision
    assert d.player == "p1" and {o.label for o in d.options} == {"Bob One", "Bob Two", "Carol One"} and "secret" in d.prompt  # creatures Alice doesn't control
    pick(s, "p1", "Bob One")
    for viewer, seen in seen_by_others(s, "p1"):
        assert "voted for" not in seen and "ballots" not in seen, viewer
    pick(s, "p2", "Carol One")
    pick(s, "p3", "Bob One")
    resolve(s)
    assert "The votes are revealed" in log(s, "p2")
    assert s.state.cards[b1.id].counters == {"stun": 2} and s.state.cards[b1.id].tapped
    assert s.state.cards[c1.id].counters == {"stun": 1} and s.state.cards[c1.id].tapped
    assert not s.state.cards[b2.id].counters and not s.state.cards[b2.id].tapped and not s.state.cards[mine.id].counters
    check(s)


def test_selective_obliteration_each_player_keeps_only_their_own_chosen_color_and_colorless(cards):
    s = table(cards, ["Selective Obliteration", "Llanowar Elves", "Frogmite", "Kitchen Finks"], ["Dregscape Zombie", "Grizzly Bears"], players=2)
    elves, frog, finks = (put(s, n) for n in ("Llanowar Elves", "Frogmite", "Kitchen Finks"))
    zombie, bears = (put(s, n, "p2") for n in ("Dregscape Zombie", "Grizzly Bears"))
    forest = put(s, "Forest")
    cast(s, "Selective Obliteration", C=5)
    resolve(s)
    assert s.state.rules.decision.player == "p1"
    answer(s, "p1", "Green")  # public: Bob knows (101.4b)
    assert "Alice chooses Green" in log(s, "p2")
    answer(s, "p2", "Black")
    resolve(s)
    # Alice: green Elves and the colorless Frogmite and Forest stay, the multicolored Kitchen Finks goes; Bob chose black: the Zombie stays, his green Bears go
    assert elves.id in s.state.zones["p1:battlefield"] and frog.id in s.state.zones["p1:battlefield"] and forest.id in s.state.zones["p1:battlefield"]
    assert s.state.cards[finks.id].zone == "p1:exile"
    assert zombie.id in s.state.zones["p2:battlefield"] and s.state.cards[bears.id].zone == "p2:exile"
    check(s)


# -- hands, graveyards, names, directions ----------------------------------------------------------------------------------
WORLDPURGE, GAMBIT, SIFTER, SPHINX, SUCCESSION = "Worldpurge", "Stronghold Gambit", "Grave Sifter", "Conundrum Sphinx", "Order of Succession"
HAND = ["Llanowar Elves", "Grizzly Bears", "Young Wolf", "Dregscape Zombie", "Mulldrifter", "Elvish Visionary", "Soul Warden", "Merfolk Looter", "Albino Troll"]


@pytest.mark.parametrize("name", [WORLDPURGE, GAMBIT, SIFTER, SPHINX, SUCCESSION])
def test_the_hand_and_name_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_worldpurge_each_player_keeps_up_to_seven_cards_and_shuffles_the_rest_in_unseen(cards):
    s = table(cards, [WORLDPURGE, *HAND], ["Mulldrifter", "Soul Warden", "Merfolk Looter"], players=2)
    for n in HAND:
        to_hand(s, n)
    [to_hand(s, n, "p2") for n in ("Mulldrifter", "Soul Warden", "Merfolk Looter")]
    creature(s, "p1", "Alice Token")
    creature(s, "p2", "Bob Token")
    mana(s, "p2", R=3)
    to_hand(s, WORLDPURGE)
    mana(s, "p1", W=4, C=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, WORLDPURGE).id)
    resolve(s)
    d = s.state.rules.decision
    assert d.player == "p1" and d.min_choices == 0 and d.max_choices == 7 and len(d.options) >= 9  # up to seven of the hand (the Elves-to-Troll cards and the rest)
    keep = [o.id for o in d.options][:7]
    kept_names = {s.state.cards[c].name for c in keep}
    lost_names = {s.state.cards[o.id].name for o in d.options} - kept_names
    act(s, "p1", type="choose", decision_id=d.id, option_ids=keep)
    for viewer, seen in seen_by_others(s, "p1"):  # Bob sees neither which cards Alice kept nor which she shuffled away (101.4a: how many only)
        assert not any(n in seen for n in lost_names - {"Mulldrifter", "Soul Warden", "Merfolk Looter"}), viewer
    d = s.state.rules.decision
    assert d.player == "p2" and d.max_choices == 3 and d.min_choices == 0
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:2])  # "up to seven": fewer is allowed
    resolve(s)
    assert len(s.state.zones["p1:hand"]) == 7 and len(s.state.zones["p2:hand"]) == 2
    assert "Alice chooses 7 cards in their hand" in log(s, "p2") and "Bob shuffles 1 card from their hand into their library" in log(s, "p1")
    assert not s.state.players["p2"].mana  # each player loses all unspent mana
    check(s)


def gambit(cards, picks):
    """Alice casts Stronghold Gambit; each player chooses the card named in ``picks`` (a hand of Llanowar Elves, Sol Ring / Grizzly Bears / Young Wolf, Sol Ring)."""
    s = table(cards, [GAMBIT, "Llanowar Elves", "Sol Ring"], ["Grizzly Bears", "Sol Ring"], ["Young Wolf", "Sol Ring"])
    held = {"p1": [to_hand(s, n) for n in ("Llanowar Elves", "Sol Ring")], "p2": [to_hand(s, n, "p2") for n in ("Grizzly Bears", "Sol Ring")],
            "p3": [to_hand(s, n, "p3") for n in ("Young Wolf", "Sol Ring")]}
    to_hand(s, GAMBIT)
    mana(s, "p1", R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, GAMBIT).id)
    resolve(s)
    for pid in ("p1", "p2", "p3"):
        d = s.state.rules.decision
        assert d.player == pid and "(secret)" in d.prompt
        act(s, pid, type="choose", decision_id=d.id, option_ids=[next(c.id for c in held[pid] if c.name == picks[pid])])
        if picks[pid] != "Sol Ring" and s.state.rules.decision is not None:  # the chosen card is not shown to the others while the others choose
            for viewer, seen in seen_by_others(s, pid):
                assert picks[pid] not in seen, (viewer, picks[pid])
    resolve(s)
    return s, held


def test_stronghold_gambit_only_the_lowest_creature_card_enters(cards):
    s, held = gambit(cards, {"p1": "Llanowar Elves", "p2": "Grizzly Bears", "p3": "Sol Ring"})
    assert s.state.cards[held["p1"][0].id].zone == "p1:battlefield"  # the Elves (1) are the lowest creature card; the Sol Ring (also 1) is no creature
    assert s.state.cards[held["p2"][0].id].zone == "p2:hand" and s.state.cards[held["p3"][1].id].zone == "p3:hand"
    assert "The choices are revealed: Alice chose Llanowar Elves; Bob chose Grizzly Bears; Carol chose Sol Ring" in log(s, "p2")
    check(s)


def test_stronghold_gambit_tied_creature_cards_all_enter_and_the_rest_stop_being_revealed(cards):
    s, held = gambit(cards, {"p1": "Llanowar Elves", "p2": "Grizzly Bears", "p3": "Young Wolf"})
    assert s.state.cards[held["p1"][0].id].zone == "p1:battlefield" and s.state.cards[held["p3"][0].id].zone == "p3:battlefield"  # both of mana value 1
    bears = held["p2"][0]
    assert s.state.cards[bears.id].zone == "p2:hand" and not s.state.cards[bears.id].revealed_to  # no longer revealed
    check(s)


def test_stronghold_gambit_without_a_creature_card_nothing_enters(cards):
    s, held = gambit(cards, {"p1": "Sol Ring", "p2": "Sol Ring", "p3": "Sol Ring"})
    assert all(s.state.cards[c.id].zone.endswith(":hand") for cs in held.values() for c in cs)
    check(s)


def test_grave_sifter_each_player_returns_cards_of_their_own_chosen_type(cards):
    s = table(cards, [SIFTER, "Llanowar Elves", "Elvish Visionary", "Grizzly Bears"], ["Elvish Visionary", "Dregscape Zombie", "Young Wolf"], players=2)
    elves, vis, bears = (card_named(s, n) for n in ("Llanowar Elves", "Elvish Visionary", "Grizzly Bears"))
    b_vis, zombie, wolf = (card_named(s, n, "p2") for n in ("Elvish Visionary", "Dregscape Zombie", "Young Wolf"))
    for c in (elves, vis, bears, b_vis, zombie, wolf):
        act(s, c.owner, type="move", card_ids=[c.id], to={"player": c.owner, "zone": "graveyard"})
    cast(s, SIFTER, G=1, C=5)
    resolve(s)
    answer(s, "p1", "Elf")
    answer(s, "p2", "Zombie")  # each player's type is their own
    d = s.state.rules.decision
    assert d.player == "p1" and {o.label for o in d.options} == {"Llanowar Elves", "Elvish Visionary"}  # the Elves in her graveyard: any number of them
    pick(s, "p1", "Llanowar Elves")
    d = s.state.rules.decision
    assert d.player == "p2" and {o.label for o in d.options} == {"Dregscape Zombie"}
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    resolve(s)
    assert s.state.cards[elves.id].zone == "p1:hand" and s.state.cards[vis.id].zone == "p1:graveyard" and s.state.cards[zombie.id].zone == "p2:hand"
    assert s.state.cards[b_vis.id].zone == "p2:graveyard"  # (Bob chose Zombie, not Elf)
    check(s)


def test_conundrum_sphinx_a_player_keeps_the_card_they_named(cards):
    s = table(cards, [SPHINX, "Llanowar Elves", "Grizzly Bears"], ["Young Wolf", "Mulldrifter"], players=2)
    sphinx = put(s, SPHINX)
    top_a = card_named(s, "Llanowar Elves")
    top_b = card_named(s, "Young Wolf", "p2")
    act(s, "p1", type="move", card_ids=[top_a.id], to={"player": "p1", "zone": "library"}, position="top")
    act(s, "p2", type="move", card_ids=[top_b.id], to={"player": "p2", "zone": "library"}, position="top")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1", limit=300)
    act(s, "p1", type="move", card_ids=[top_a.id], to={"player": "p1", "zone": "library"}, position="top")
    act(s, "p2", type="move", card_ids=[top_b.id], to={"player": "p2", "zone": "library"}, position="top")
    act(s, "p1", type="pass_priority")  # to combat
    d = None
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": sphinx.id, "target": "p2"}])
    d = s.state.rules.decision
    assert d.player == "p1" and d.options[0].id == "__name__"  # a card name is typed (201.4)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[], name="Llanowar Elves")  # right: the top card of her library
    d = s.state.rules.decision
    assert d.player == "p2" and "Llanowar Elves" in d.prompt  # Bob knows what she named (101.4b)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[], name="Grizzly Bears")  # wrong: his top card is Young Wolf
    resolve(s)
    assert s.state.cards[top_a.id].zone == "p1:hand"  # named correctly: into the hand
    assert s.state.zones["p2:library"][-1] == top_b.id  # not the name he chose: to the bottom of his library
    assert "revealed Llanowar Elves" in log(s, "p2") and "revealed Young Wolf" in log(s, "p1")
    check(s)


def test_order_of_succession_each_player_takes_a_creature_from_the_next_player_in_the_chosen_direction(cards):
    s = table(cards, [SUCCESSION])
    a = [creature(s, "p1", n) for n in ("A1", "A2")]
    b = [creature(s, "p2", n) for n in ("B1", "B2")]
    c = [creature(s, "p3", n) for n in ("C1", "C2")]
    cast(s, SUCCESSION, U=1, C=3)
    resolve(s)
    answer(s, "p1", "left")  # left: the next player in turn order
    d = s.state.rules.decision
    assert d.player == "p1" and {o.label for o in d.options} == {"B1", "B2"} and "Bob" in d.prompt
    pick(s, "p1", "B2")
    d = s.state.rules.decision
    assert d.player == "p2" and {o.label for o in d.options} == {"C1", "C2"} and "Alice B2" in d.prompt
    pick(s, "p2", "C1")
    pick(s, "p3", "A2")
    resolve(s)
    assert [s.state.cards[x.id].controller for x in (b[1], c[0], a[1])] == ["p1", "p2", "p3"]
    assert [s.state.cards[x.id].controller for x in (a[0], b[0], c[1])] == ["p1", "p2", "p3"]
    check(s)


def test_order_of_succession_right_goes_the_other_way_round(cards):
    s = table(cards, [SUCCESSION])
    a = [creature(s, "p1", n) for n in ("A1", "A2")]
    c = [creature(s, "p3", n) for n in ("C1", "C2")]
    b = [creature(s, "p2", n) for n in ("B1", "B2")]
    cast(s, SUCCESSION, U=1, C=3)
    resolve(s)
    answer(s, "p1", "right")
    d = s.state.rules.decision
    assert d.player == "p1" and {o.label for o in d.options} == {"C1", "C2"}  # the player before her: Carol
    pick(s, "p1", "C1")
    d = s.state.rules.decision
    assert d.player == "p3" and {o.label for o in d.options} == {"B1", "B2"}  # then Carol takes from Bob
    pick(s, "p3", "B2")
    pick(s, "p2", "A1")
    resolve(s)
    assert [s.state.cards[x.id].controller for x in (c[0], b[1], a[0])] == ["p1", "p3", "p2"]
    check(s)
