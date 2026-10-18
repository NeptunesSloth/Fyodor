"""Wave 53D: piles (CR 700.3), real Oracle text (tests/fixtures/wave53d_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 700.3a-d: each object goes into exactly one pile, a pile may be empty, a pile is no object and nothing moves while objects are grouped.
* Liliana of the Veil -6 / Do or Die: the caster separates the target player's permanents (creatures), that player chooses a pile (the empty one if they like).
* Make an Example: each opponent separates their creatures, the caster chooses a pile for each, all sacrificed at once.
* Death or Glory: the caster separates their graveyard's creature cards; an opponent (named by the caster) chooses: exile that pile, the other returns.
* Whims of the Fates: every player separates into three piles (starting with the caster) and one pile of each, at random, is sacrificed.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import creature
from tests.wave9c_kit import card_named, mana, put
from tests.wave53d_kit import (
    check,
    log,
    loyalty,
    names_on,
    open_repo,
    pin_random,
    resolve,
    table,
    to_hand,
)

LILIANA, DIE, EXAMPLE, GLORY, WHIMS = "Liliana of the Veil", "Do or Die", "Make an Example", "Death or Glory", "Whims of the Fates"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [LILIANA, DIE, EXAMPLE, GLORY, WHIMS])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def cast(s, name, pid="p1", targets=None, **pool):
    to_hand(s, name, pid)
    mana(s, pid, **pool)
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, **({"targets": targets} if targets else {}))


def split(s, pid, first):
    """The separator picks the cards (by name prefix) of the first pile; the rest form the other."""
    d = s.state.rules.decision
    assert d is not None and d.player == pid, (d.player if d else None, pid)
    act(s, pid, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if any(o.label.startswith(f) for f in first)])


def pile(s, pid, number):
    d = s.state.rules.decision
    assert d is not None and d.player == pid and d.kind == "choose_one", (d.player if d else None, pid)
    act(s, pid, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label.startswith(f"Pile {number}"))])


def test_liliana_separates_the_permanents_and_the_player_sacrifices_the_pile_of_their_choice(cards):
    s = table(cards, [LILIANA], players=2)
    walker = loyalty(s, LILIANA, 6)
    bears = [creature(s, "p2", n) for n in ("Bear One", "Bear Two", "Bear Three")]
    land = card_named(s, "Island", "p2")
    act(s, "p2", type="move", card_ids=[land.id], to={"player": "p2", "zone": "battlefield"})
    act(s, "p1", type="activate_ability", card_id=walker.id, ability=2, targets=["p2"])
    resolve(s)
    d = s.state.rules.decision  # Alice separates (700.3): the player's four permanents, one pile chosen by her
    assert d.player == "p1" and d.max_choices == 4
    split(s, "p1", ["Bear One", "Bear Two"])
    assert "Alice separates Bob's permanents into piles: Bear One, Bear Two / Bear Three, Island" in log(s, "p2")
    assert all(c in s.state.zones["p2:battlefield"] for c in [b.id for b in bears] + [land.id])  # (nothing moved: 700.3c)
    pile(s, "p2", 2)  # Bob chooses
    resolve(s)
    assert names_on(s, "p2") == ["Bear One", "Bear Two"] and land.id not in s.state.zones["p2:battlefield"]  # (Bear Three, Island: sacrificed)
    check(s)


def test_an_empty_pile_may_be_chosen_and_nothing_is_sacrificed(cards):
    s = table(cards, [LILIANA], players=2)
    walker = loyalty(s, LILIANA, 6)
    bear = creature(s, "p2", "Bear One")
    act(s, "p1", type="activate_ability", card_id=walker.id, ability=2, targets=["p2"])
    resolve(s)
    split(s, "p1", ["Bear One"])  # all in one pile
    d = s.state.rules.decision
    assert [o.label for o in d.options] == ["Pile 1: Bear One", "Pile 2: no cards"]
    pile(s, "p2", 2)
    resolve(s)
    assert bear.id in s.state.zones["p2:battlefield"]
    check(s)


def test_a_player_with_no_permanents_has_nothing_to_separate(cards):
    s = table(cards, [LILIANA], players=2)
    walker = loyalty(s, LILIANA, 6)
    act(s, "p1", type="activate_ability", card_id=walker.id, ability=2, targets=["p2"])
    resolve(s)
    assert s.state.rules.decision is None
    check(s)


def test_do_or_die_destroys_the_creatures_of_the_chosen_pile(cards):
    s = table(cards, [DIE], players=2)
    ogre, wolf, bear = creature(s, "p2", "Ogre"), creature(s, "p2", "Wolf"), creature(s, "p2", "Bear")
    mine = creature(s, "p1", "Mine")
    cast(s, DIE, targets=["p2"], B=1, C=1)
    resolve(s)
    split(s, "p1", ["Ogre", "Wolf"])
    pile(s, "p2", 1)
    resolve(s)
    assert ogre.id not in s.state.cards and wolf.id not in s.state.cards and bear.id in s.state.zones["p2:battlefield"]
    assert mine.id in s.state.zones["p1:battlefield"]
    check(s)


def test_make_an_example_each_opponent_separates_and_the_caster_chooses(cards):
    s = table(cards, [EXAMPLE])
    b1, b2, b3 = (creature(s, "p2", n) for n in ("B1", "B2", "B3"))
    c1, c2 = creature(s, "p3", "C1"), creature(s, "p3", "C2")
    mine = creature(s, "p1", "Mine")
    cast(s, EXAMPLE, B=1, C=3)
    resolve(s)
    split(s, "p2", ["B1"])  # each opponent separates their own creatures, in APNAP order
    split(s, "p3", ["C1", "C2"])
    assert s.state.rules.decision.player == "p1" and "Bob's" in s.state.rules.decision.prompt  # then Alice chooses for each opponent
    pile(s, "p1", 2)
    assert "Carol's" in s.state.rules.decision.prompt
    pile(s, "p1", 1)
    resolve(s)
    assert [s.state.cards[c].name for c in s.state.zones["p2:battlefield"]].count("B1") == 1 and b2.id not in s.state.cards and b3.id not in s.state.cards
    assert c1.id not in s.state.cards and c2.id not in s.state.cards and mine.id in s.state.zones["p1:battlefield"]
    check(s)


def test_death_or_glory_an_opponent_chooses_a_pile_to_exile_and_the_other_returns(cards):
    s = table(cards, [GLORY, "Llanowar Elves", "Grizzly Bears", "Young Wolf"])
    dead = [card_named(s, n) for n in ("Llanowar Elves", "Grizzly Bears", "Young Wolf")]
    for c in dead:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    cast(s, GLORY, W=1, C=4)
    resolve(s)
    split(s, "p1", ["Llanowar Elves"])
    d = s.state.rules.decision  # which opponent chooses is Alice's call (608.2d)
    assert d.player == "p1" and {o.label for o in d.options} == {"Bob", "Carol"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    assert s.state.rules.decision.player == "p3"
    pile(s, "p3", 1)  # Carol: exile Llanowar Elves; the other pile returns to the battlefield under its owner's control
    resolve(s)
    assert s.state.cards[dead[0].id].zone == "p1:exile"
    assert s.state.cards[dead[1].id].zone == "p1:battlefield" and s.state.cards[dead[2].id].zone == "p1:battlefield"
    check(s)


def test_whims_of_the_fates_sacrifices_one_random_pile_of_each_player(cards, monkeypatch):
    s = table(cards, [WHIMS])
    a1, a2 = creature(s, "p1", "A1"), creature(s, "p1", "A2")
    b1, b2 = creature(s, "p2", "B1"), creature(s, "p2", "B2")
    pin_random(monkeypatch, 1)  # the second pile of each
    cast(s, WHIMS, R=1, C=5)
    resolve(s)
    split(s, "p1", ["A1"])  # three piles: the first, then the second among the rest, then what is left
    split(s, "p1", ["A2"])
    assert s.state.rules.decision.player == "p2"  # starting with Alice, then turn order
    split(s, "p2", [])
    split(s, "p2", ["B1", "B2"])
    resolve(s)
    assert a2.id not in s.state.cards and a1.id in s.state.zones["p1:battlefield"]
    assert b1.id not in s.state.cards and b2.id not in s.state.cards
    check(s)


def test_do_or_die_the_creatures_cant_be_regenerated(cards):
    s = table(cards, [DIE], ["Twisted Abomination"], players=2)
    abom = put(s, "Twisted Abomination", "p2")
    act(s, "p2", type="set_prefs", response="on")  # (Bob stops at each object on the stack)
    cast(s, DIE, targets=["p2"], B=1, C=1)
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    mana(s, "p2", B=1)  # Bob answers with a regeneration shield ("{B}: Regenerate Twisted Abomination.")
    act(s, "p2", type="activate_ability", card_id=abom.id, ability=0)
    resolve(s)  # the shield, then Do or Die resolves
    split(s, "p1", ["Twisted"])
    pile(s, "p2", 1)
    resolve(s)
    assert s.state.cards[abom.id].zone == "p2:graveyard"  # destroyed in spite of the shield (701.19c)
    check(s)


# -- piles of cards revealed or exiled ----------------------------------------------------------------------------------
INTRUDE, TRUTH, SPOILS, PARLEY = "Intrude on the Mind", "Truth or Tale", "Split the Spoils", "Boneyard Parley"
FIVE = ["Llanowar Elves", "Grizzly Bears", "Young Wolf", "Dregscape Zombie", "Mulldrifter"]


def stack_top(s, names, pid="p1"):
    """The library of ``pid`` with these cards on top, in this order (first = top)."""
    for n in reversed(names):
        c = card_named(s, n, pid)
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")
    return [card_named(s, n, pid) for n in names]


def test_intrude_on_the_mind_hand_and_graveyard_and_a_thopter_with_a_counter_for_each_card_in_the_graveyard(cards):
    s = table(cards, [INTRUDE, *FIVE], players=2)
    top = stack_top(s, FIVE)
    to_hand(s, INTRUDE)
    mana(s, "p1", U=2, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, INTRUDE).id)
    resolve(s)
    d = s.state.rules.decision
    assert d.player == "p1" and {o.label for o in d.options} == set(FIVE)  # the five revealed cards (701.20a: public), Alice separates
    split(s, "p1", ["Llanowar Elves", "Grizzly Bears"])
    assert "Alice separates cards into piles: Llanowar Elves, Grizzly Bears / Young Wolf, Dregscape Zombie, Mulldrifter" in log(s, "p2")
    pile(s, "p2", 1)  # Bob: the first pile goes to Alice's hand, the other to her graveyard
    resolve(s)
    assert names_on(s, "p1", "hand")[:0] == [] and {s.state.cards[c.id].zone for c in top[:2]} == {"p1:hand"}
    assert {s.state.cards[c.id].zone for c in top[2:]} == {"p1:graveyard"}
    thopter = next(c for c in s.state.cards.values() if c.name == "Thopter")
    assert s.state.cards[thopter.id].counters == {"+1/+1": 3}  # one counter for each of the three cards put into the graveyard
    check(s)


@pytest.mark.parametrize(("take", "counters"), [(1, 0), (2, 5)])
def test_intrude_on_the_mind_everything_in_one_pile(cards, take, counters):
    s = table(cards, [INTRUDE, *FIVE], players=2)
    stack_top(s, FIVE)
    to_hand(s, INTRUDE)
    mana(s, "p1", U=2, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, INTRUDE).id)
    resolve(s)
    split(s, "p1", FIVE)  # everything in one pile, the other empty (ruling 2024-02-02)
    assert "Pile 2: no cards" in [o.label for o in s.state.rules.decision.options]
    pile(s, "p2", take)  # the full pile to the hand (no card in the graveyard: a 0/0 Thopter dies), or the empty one (all five in the graveyard)
    resolve(s)
    zone = "p1:hand" if take == 1 else "p1:graveyard"
    assert all(s.state.cards[card_named(s, n).id].zone == zone for n in FIVE)
    thopters = [c for c in s.state.cards.values() if c.name == "Thopter" and c.zone == "p1:battlefield"]
    assert (len(thopters) == 1 and thopters[0].counters == {"+1/+1": counters}) if counters else not thopters
    check(s)


def test_truth_or_tale_one_card_of_the_chosen_pile_and_the_rest_on_the_bottom(cards):
    s = table(cards, [TRUTH, *FIVE], players=2)
    top = stack_top(s, FIVE)
    to_hand(s, TRUTH)
    mana(s, "p1", U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, TRUTH).id)
    resolve(s)
    split(s, "p1", ["Llanowar Elves", "Grizzly Bears"])
    pile(s, "p2", 1)  # Bob: the first pile
    d = s.state.rules.decision
    assert d.player == "p1" and {o.label for o in d.options} == {"Llanowar Elves", "Grizzly Bears"}  # Alice picks a card from the chosen pile
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "Grizzly Bears")])
    d = s.state.rules.decision  # the other four go on the bottom in the order Alice picks (401.4)
    assert d.kind == "order" and d.player == "p1" and len(d.options) == 4
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    resolve(s)
    assert s.state.cards[top[1].id].zone == "p1:hand"
    library = s.state.zones["p1:library"]
    assert [library.index(c.id) for c in top if c is not top[1]] and all(library.index(c.id) >= len(library) - 4 for c in top if c is not top[1])
    check(s)


def test_split_the_spoils_exiles_the_targets_and_the_piles_go_to_hand_and_graveyard(cards):
    s = table(cards, [SPOILS, "Llanowar Elves", "Grizzly Bears", "Young Wolf"], players=2)
    dead = [card_named(s, n) for n in ("Llanowar Elves", "Grizzly Bears", "Young Wolf")]
    for c in dead:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    to_hand(s, SPOILS)
    mana(s, "p1", G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, SPOILS).id, targets=[c.id for c in dead], target_counts=[3])
    resolve(s)
    split(s, "p1", ["Young Wolf"])
    pile(s, "p2", 2)  # Bob: the pile of Elves and Bears to Alice's hand
    resolve(s)
    assert s.state.cards[dead[0].id].zone == "p1:hand" and s.state.cards[dead[1].id].zone == "p1:hand"
    assert s.state.cards[dead[2].id].zone == "p1:graveyard"
    check(s)


def test_boneyard_parley_an_opponent_separates_and_you_choose_the_pile_you_take(cards):
    s = table(cards, [PARLEY, "Llanowar Elves", "Grizzly Bears"], ["Young Wolf", "Dregscape Zombie"], players=2)
    mine = [card_named(s, n) for n in ("Llanowar Elves", "Grizzly Bears")]
    theirs = [card_named(s, n, "p2") for n in ("Young Wolf", "Dregscape Zombie")]
    for c in mine + theirs:
        act(s, c.owner, type="move", card_ids=[c.id], to={"player": c.owner, "zone": "graveyard"})
    to_hand(s, PARLEY)
    mana(s, "p1", B=2, C=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, PARLEY).id, targets=[c.id for c in mine + theirs], target_counts=[4])
    resolve(s)
    assert s.state.rules.decision.player == "p2"  # the opponent separates the cards (they may come from different graveyards)
    split(s, "p2", ["Llanowar Elves", "Young Wolf"])
    pile(s, "p1", 1)  # Alice takes the first pile: onto the battlefield under her control; the rest to their owners' graveyards
    resolve(s)
    assert s.state.cards[mine[0].id].zone == "p1:battlefield" and s.state.cards[theirs[0].id].zone == "p1:battlefield"
    assert s.state.cards[theirs[0].id].controller == "p1" and s.state.cards[theirs[0].id].owner == "p2"
    assert s.state.cards[mine[1].id].zone == "p1:graveyard" and s.state.cards[theirs[1].id].zone == "p2:graveyard"
    check(s)
