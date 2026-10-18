"""Wave 53D: group choices (CR 101.4, 701.? none: a choice is no keyword action), real Oracle text (tests/fixtures/wave53d_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 101.4: simultaneous choices are made in APNAP order, each player knowing the earlier public choices; what they do happens afterwards, all at once.
* "Each player chooses a creature type" (Harsh Mercy, Patriarch's Bidding): the types chosen by anyone are the "types chosen this way"; a type chosen twice is
  one type (Patriarch's Bidding rulings).
* "Each opponent chooses fame or fortune" (Seize the Spotlight), "chooses money, friends, or secrets" (Master of Ceremonies): "for each player who chose X" is
  done once for each such player.
* Secret choices (Wheel of Misfortune, Menacing Ogre, Prisoner's Dilemma): the choice is the chooser's alone until every choice is in; then all are revealed at once.
"""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, until
from tests.wave9c_kit import card_named, mana, put
from tests.wave53d_kit import answer, check, log, open_repo, resolve, seen_by_others, table, to_hand

BIDDING, MERCY, SPOTLIGHT, CEREMONIES = "Patriarch's Bidding", "Harsh Mercy", "Seize the Spotlight", "Master of Ceremonies"
WHEEL, OGRE, DILEMMA = "Wheel of Misfortune", "Menacing Ogre", "Prisoner's Dilemma"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [BIDDING, MERCY, SPOTLIGHT, CEREMONIES, WHEEL, OGRE, DILEMMA])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def cast(s, name, pid="p1", **pool):
    to_hand(s, name, pid)
    mana(s, pid, **pool)
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id)
    return len(s.state.zones[f"{pid}:hand"])  # (the cards left in hand once the spell is on the stack)


def gy(s, pid, name, types="Creature — Elf", text=""):
    """A creature card of that type in the graveyard of ``pid`` (a token can't be one: a real card is made by moving a deck card)."""
    c = card_named(s, "Forest", pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})
    return c


def test_harsh_mercy_destroys_what_isnt_of_a_chosen_type(cards):
    s = table(cards, [MERCY], players=2)
    elf = creature(s, "p1", "Elf A", type_line="Token Creature — Elf Warrior")
    goblin = creature(s, "p2", "Goblin A", type_line="Token Creature — Goblin Shaman")
    shaman = creature(s, "p2", "Shaman A", type_line="Token Creature — Human Shaman")
    ogre = creature(s, "p1", "Ogre A", type_line="Token Creature — Ogre")
    cast(s, MERCY, W=2, C=3)
    resolve(s)
    assert s.state.rules.decision.player == "p1"  # the active player chooses first (101.4)
    answer(s, "p1", "Elf")
    assert s.state.rules.decision.player == "p2" and "Alice Elf" in s.state.rules.decision.prompt
    answer(s, "p2", "Shaman")
    resolve(s)
    assert elf.id in s.state.zones["p1:battlefield"] and shaman.id in s.state.zones["p2:battlefield"]
    assert goblin.id in s.state.zones["p2:battlefield"]  # (a Goblin Shaman is a Shaman too)
    assert ogre.id not in s.state.cards  # (neither an Elf nor a Shaman)
    assert "Bob chooses Shaman" in log(s)
    check(s)


def test_patriarchs_bidding_returns_every_creature_card_of_any_chosen_type(cards):
    s = table(cards, [BIDDING, "Llanowar Elves", "Grizzly Bears"], ["Elvish Visionary", "Dregscape Zombie"], ["Twisted Abomination", "Young Wolf"])
    dead = {n: card_named(s, n, p) for n, p in [("Llanowar Elves", "p1"), ("Grizzly Bears", "p1"), ("Elvish Visionary", "p2"), ("Dregscape Zombie", "p2"),
                                                ("Twisted Abomination", "p3"), ("Young Wolf", "p3")]}
    for c in dead.values():
        act(s, c.owner, type="move", card_ids=[c.id], to={"player": c.owner, "zone": "graveyard"})
    cast(s, BIDDING, B=2, C=3)
    resolve(s)
    answer(s, "p1", "Elf")  # the active player first, then turn order (101.4); a type chosen twice is one type
    answer(s, "p2", "Elf")
    assert "already" not in s.state.rules.decision.prompt and "Alice Elf, Bob Elf" in s.state.rules.decision.prompt  # (101.4b: Carol knows)
    answer(s, "p3", "Zombie")
    resolve(s)
    back = {n for n, c in dead.items() if s.state.cards[c.id].zone.endswith(":battlefield")}
    assert back == {"Llanowar Elves", "Elvish Visionary", "Dregscape Zombie", "Twisted Abomination"}  # under their owners' control
    assert s.state.cards[dead["Dregscape Zombie"].id].controller == "p2" and s.state.cards[dead["Twisted Abomination"].id].controller == "p3"
    assert s.state.cards[dead["Grizzly Bears"].id].zone == "p1:graveyard" and s.state.cards[dead["Young Wolf"].id].zone == "p3:graveyard"
    check(s)


def test_a_player_who_left_the_game_chooses_nothing(cards):
    s = table(cards, [MERCY], players=3)
    elf = creature(s, "p1", "Elf A", type_line="Token Creature — Elf")
    ogre = creature(s, "p3", "Ogre A", type_line="Token Creature — Ogre")
    cast(s, MERCY, W=2, C=3)
    resolve(s)
    answer(s, "p1", "Elf")
    act(s, "p2", type="concede")  # Bob leaves while it is his turn to choose (800.4a)
    answer(s, "p3", "Ogre")
    resolve(s)
    assert elf.id in s.state.zones["p1:battlefield"] and ogre.id in s.state.zones["p3:battlefield"]
    check(s)


def names_on(s, pid, zone="battlefield"):
    return sorted(s.state.cards[c].name for c in s.state.zones[f"{pid}:{zone}"])


def test_seize_the_spotlight_takes_a_creature_per_fame_and_draws_per_fortune(cards):
    s = table(cards, [SPOTLIGHT])
    creature(s, "p1", "Mine")
    b1, b2 = creature(s, "p2", "Bob One"), creature(s, "p2", "Bob Two")
    c1 = creature(s, "p3", "Carol One")
    act(s, "p2", type="tap", card_ids=[b1.id], tapped=True)
    hand = cast(s, SPOTLIGHT, R=1, C=2)
    resolve(s)
    assert s.state.rules.decision.player == "p2"  # APNAP among the opponents: Alice is active, so Bob, then Carol
    answer(s, "p2", "fame")
    assert s.state.rules.decision.player == "p3" and "Bob fame" in s.state.rules.decision.prompt
    answer(s, "p3", "fortune")
    d = s.state.rules.decision  # Alice chooses which creature of Bob's (a choice, not a target: 608.2d)
    assert d.player == "p1" and {o.label for o in d.options} == {"Bob One — Bob", "Bob Two — Bob"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label.startswith("Bob One"))])
    resolve(s)
    got = s.state.cards[b1.id]
    assert got.controller == "p1" and not got.tapped  # untapped, and hasty until end of turn
    assert "haste" in Plan.view(s.state, "p1", s.cards).ch(got).keywords
    assert s.state.cards[b2.id].controller == "p2" and s.state.cards[c1.id].controller == "p3"
    assert len(s.state.zones["p1:hand"]) == hand + 1 and "Treasure" in names_on(s, "p1")  # one fortune: a card and a Treasure
    check(s)


def test_each_player_who_chose_fortune_is_one_draw_and_one_treasure(cards):
    s = table(cards, [SPOTLIGHT])
    hand = cast(s, SPOTLIGHT, R=1, C=2)
    resolve(s)
    answer(s, "p2", "fortune")
    answer(s, "p3", "fortune")
    resolve(s)
    assert len(s.state.zones["p1:hand"]) == hand + 2 and names_on(s, "p1").count("Treasure") == 2
    check(s)


def test_master_of_ceremonies_gives_both_players_what_one_chose(cards):
    s = table(cards, [CEREMONIES])
    put(s, CEREMONIES)
    until(s, lambda s: s.state.rules.decision is not None and "friends" in s.state.rules.decision.prompt, limit=200)
    d = s.state.rules.decision
    assert d.player == "p2" and s.state.turn.active_player == "p1" and s.state.turn.phase == "upkeep"
    hand = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2", "p3")}
    answer(s, "p2", "money")
    answer(s, "p3", "secrets")
    resolve(s)
    assert names_on(s, "p1").count("Treasure") == 1 and names_on(s, "p2").count("Treasure") == 1 and "Treasure" not in names_on(s, "p3")
    drawn = 1 + (s.state.turn.phase != "upkeep")  # (secrets: one card; and once the upkeep is over, her draw step's)
    assert len(s.state.zones["p1:hand"]) == hand["p1"] + drawn and len(s.state.zones["p3:hand"]) == hand["p3"] + 1 and len(s.state.zones["p2:hand"]) == hand["p2"]
    check(s)


def hands(s):
    return {p: len(s.state.zones[f"{p}:hand"]) for p in s.state.players}


def test_wheel_of_misfortune_hurts_the_highest_and_wheels_everyone_but_the_lowest(cards):
    s = table(cards, [WHEEL])
    for p in ("p1", "p2", "p3"):
        act(s, p, type="draw", player=p, count=2)
    cast(s, WHEEL, R=1, C=2)
    resolve(s)
    life0 = {p: s.state.players[p].life for p in s.state.players}
    d = s.state.rules.decision
    assert d.player == "p1" and d.options[0].id == "__number__"  # a typed number, Alice first (101.4)
    answer(s, "p1", name="1")
    # Bob decides without any sign of what Alice chose, and nobody else sees the pending choice
    for viewer, seen in seen_by_others(s, "p1"):
        assert "chose" not in seen and "ballot" not in seen and '"gc"' not in seen, viewer
    assert s.state.rules.decision.player == "p2" and "chose" not in json.dumps(s.view("p3")["log"])
    assert s.view("p3")["rules"]["decision"]["kind"] == "waiting"
    answer(s, "p2", name="4")
    answer(s, "p3", name="4")
    resolve(s)
    assert "The choices are revealed: Alice chose 1; Bob chose 4; Carol chose 4" in log(s)
    assert s.state.players["p1"].life == life0["p1"] and s.state.players["p2"].life == life0["p2"] - 4 and s.state.players["p3"].life == life0["p3"] - 4
    assert len(s.state.zones["p2:hand"]) == 7 and len(s.state.zones["p3:hand"]) == 7  # Bob and Carol discarded their hands and drew seven
    assert len(s.state.zones["p1:hand"]) == 2  # Alice chose the lowest number: her two cards stay (the Wheel itself left her hand when it was cast)
    check(s)


def test_wheel_of_misfortune_when_everyone_chose_the_same_number_nobody_wheels(cards):
    s = table(cards, [WHEEL], players=2)
    act(s, "p2", type="draw", player="p2", count=2)
    before = hands(s)
    cast(s, WHEEL, R=1, C=2)
    resolve(s)
    answer(s, "p1", name="2")
    answer(s, "p2", name="2")
    resolve(s)
    assert s.state.players["p1"].life == 38 and s.state.players["p2"].life == 38  # (the highest is also the lowest: damage, no wheel)
    assert hands(s)["p2"] == before["p2"]
    check(s)


@pytest.mark.parametrize("typed", ["", "abc", "-1", "1.5", "1" * 10, " "])
def test_a_number_must_be_a_whole_number(cards, typed):
    s = table(cards, [WHEEL], players=2)
    cast(s, WHEEL, R=1, C=2)
    resolve(s)
    d = s.state.rules.decision
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[], name=typed)
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["__number__"])  # (the number is typed, not picked)
    assert s.state.rules.decision.id == d.id


def test_menacing_ogre_grows_if_you_are_among_the_highest(cards):
    s = table(cards, [OGRE])
    cast(s, OGRE, R=2, C=3)
    resolve(s)  # the creature spell resolves; its enters trigger waits for the choices
    until_asked = s.state.rules.decision
    while until_asked is None:
        act(s, s.state.rules.priority, type="pass_priority")
        until_asked = s.state.rules.decision
    life0 = {p: s.state.players[p].life for p in s.state.players}
    answer(s, "p1", name="5")
    answer(s, "p2", name="2")
    answer(s, "p3", name="5")
    resolve(s)
    assert s.state.players["p1"].life == life0["p1"] - 5 and s.state.players["p3"].life == life0["p3"] - 5 and s.state.players["p2"].life == life0["p2"]
    assert s.state.cards[card_named(s, OGRE).id].counters == {"+1/+1": 2}  # Alice is one of the highest players
    check(s)


def test_menacing_ogre_without_you_among_the_highest_gets_nothing(cards):
    s = table(cards, [OGRE], players=2)
    cast(s, OGRE, R=2, C=3)
    resolve(s)
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    answer(s, "p1", name="0")
    answer(s, "p2", name="3")
    resolve(s)
    assert s.state.players["p2"].life == 37 and s.state.players["p1"].life == 40
    assert not s.state.cards[card_named(s, OGRE).id].counters
    check(s)


def test_prisoners_dilemma_is_secret_until_all_have_chosen(cards):
    s = table(cards, [DILEMMA])
    cast(s, DILEMMA, R=2, C=3)
    resolve(s)
    life0 = {p: s.state.players[p].life for p in s.state.players}
    assert s.state.rules.decision.player == "p2"  # each opponent, in APNAP order
    answer(s, "p2", "snitch")
    for viewer, seen in seen_by_others(s, "p2"):
        assert "chose" not in seen and "ballot" not in seen, viewer
    answer(s, "p3", "silence")
    resolve(s)
    assert "The choices are revealed: Bob chose snitch; Carol chose silence" in log(s)
    # not all silent, not all snitching: 12 damage to each opponent who chose silence
    assert s.state.players["p3"].life == life0["p3"] - 12 and s.state.players["p2"].life == life0["p2"]
    check(s)


@pytest.mark.parametrize(("bob", "carol", "hit"), [("silence", "silence", 4), ("snitch", "snitch", 8)])
def test_prisoners_dilemma_when_all_chose_alike(cards, bob, carol, hit):
    s = table(cards, [DILEMMA])
    cast(s, DILEMMA, R=2, C=3)
    resolve(s)
    life0 = {p: s.state.players[p].life for p in s.state.players}
    answer(s, "p2", bob)
    answer(s, "p3", carol)
    resolve(s)
    assert s.state.players["p2"].life == life0["p2"] - hit and s.state.players["p3"].life == life0["p3"] - hit and s.state.players["p1"].life == life0["p1"]
    check(s)
