"""Wave 53A: "that player" of a spell's target or of a trigger's event, and the cards of that player (CR 2026-09-25), real Oracle text (tests/fixtures/wave53a_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 608.2c, 608.2d: "Target opponent mills eight cards. You may put an artifact card from that player's graveyard onto the battlefield under your control." (Grasping Tentacles),
  "Put a land card from their graveyard onto the battlefield tapped under your control. It gains ..." (Realmbreaker, the Invasion Tree), "...then you may put any number of land cards
  that player owns from exile onto the battlefield under your control." (Oblivion Sower): the cards of the player the target is; chosen by the controller as the spell resolves.
* 603.2, 701.20e, 608.2g: "Whenever this creature deals combat damage to a player, look at that player's hand. You may cast a spell from among those cards without paying its mana
  cost." (Silent-Blade Oni) - the look is the controller's alone, the cast is made as the trigger resolves.
* 603.2, 406.3: "exile the top seven cards of that player's library, then put a creature card from among them onto the battlefield under your control." (Lord of the Void).
* 701.21a: "Choose target creature that player controls. The player sacrifices that creature." (Ashling, the Extinguisher).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.visibility import SPECTATOR
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave34b_activated import activate, attack, stops, to_phase
from tests.wave9c_kit import card_named, check, mana, put, to_hand
from tests.wave53a_kit import alice_next, open_repo, table, unseen_by, until_asked

BEARS, GIANT, ANGEL, GRAIL, BOLT = "Grizzly Bears", "Hill Giant", "Serra Angel", "Sol Grail", "Lightning Bolt"
NAMES = ["Grasping Tentacles", "Realmbreaker, the Invasion Tree", "Oblivion Sower", "Silent-Blade Oni", "Lord of the Void", "Ashling, the Extinguisher", "Myrkul's Edict",
         "Sail into the West", "Intellectual Offering", "Down for Repairs", "Windgrace's Judgment", "Dark Salvation", "The Black Gate", "Disciple of Perdition", "Siege Dragon", "The Fall of Kroog", "Tibalt, the Fiend-Blooded", "Elder Brain", "Mindleech Mass", "Doomsday Specter", "Leshrac's Sigil", "Painful Memories"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", NAMES)
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def to_gy(s, name, pid):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone.endswith((":library", ":hand")))
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


# -- Grasping Tentacles / Realmbreaker --------------------------------------------------------------------------------------------------
def test_grasping_tentacles_mills_the_opponent_then_you_may_take_an_artifact_of_theirs(cards):
    s = table(cards, ["Grasping Tentacles"], [GRAIL], [GRAIL])
    carols = to_gy(s, GRAIL, "p3")
    bobs = next(c for c in s.state.cards.values() if c.name == GRAIL and c.owner == "p2")  # top of Bob's library: milled with the seven after it
    to_hand(s, "Grasping Tentacles")
    mana(s, "p1", U=1, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Grasping Tentacles").id, targets=["p2"])
    d = until_asked(s)
    assert d.player == "p1" and {o.id for o in d.options} == {bobs.id}  # Bob's graveyard, not Carol's
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bobs.id])
    settle(s)
    assert s.state.cards[bobs.id].zone == "p1:battlefield" and s.state.cards[bobs.id].controller == "p1" and s.state.cards[bobs.id].owner == "p2"
    assert s.state.cards[carols.id].zone == "p3:graveyard" and len(s.state.zones["p2:graveyard"]) == 7
    check(s)


def test_realmbreaker_takes_a_land_card_tapped_and_exiles_it_if_it_would_leave(cards):
    s = table(cards, ["Realmbreaker, the Invasion Tree", "Stone Rain"], [], [])
    rb = put(s, "Realmbreaker, the Invasion Tree")
    mana(s, "p1", C=2)
    activate(s, "p1", rb, contains="Target opponent mills", targets=["p2"])
    d = until_asked(s)
    assert d.player == "p1" and {s.state.cards[o.id].name for o in d.options} == {"Island"} and {s.state.cards[o.id].owner for o in d.options} == {"p2"}
    land = d.options[0].id
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[land])
    settle(s)
    assert s.state.cards[land].zone == "p1:battlefield" and s.state.cards[land].controller == "p1" and s.state.cards[land].tapped
    to_hand(s, "Stone Rain")
    mana(s, "p1", R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Stone Rain").id, targets=[land])
    settle(s)
    assert s.state.cards[land].zone == "p2:exile"  # "If this land would leave the battlefield, exile it instead of putting it anywhere else"
    check(s)


# -- Oblivion Sower ---------------------------------------------------------------------------------------------------------------------
def test_oblivion_sower_puts_lands_the_opponent_owns_from_exile_onto_the_battlefield(cards):
    s = table(cards, ["Oblivion Sower"], [BEARS], [])
    to_hand(s, "Oblivion Sower")
    old = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[old.id], to={"zone": "exile"})  # a land of Bob's already in exile: "land cards that player owns from exile" is all of them
    mana(s, "p1", C=6)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Oblivion Sower").id)
    d = until_asked(s)  # the cast trigger's target: Bob (or Carol)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    d = until_asked(s)
    assert d.player == "p1" and d.min_choices == 0 and old.id in {o.id for o in d.options} and len(d.options) == 4  # the three Islands exiled now and the old one (the Bears are no land)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:3])
    settle(s)
    assert sum(1 for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2" and c.zone == "p1:battlefield") == 3
    assert sum(1 for c in s.state.cards.values() if c.owner == "p2" and c.zone == "p2:exile") == 2  # the Bears and the Island left
    check(s)


# -- Silent-Blade Oni --------------------------------------------------------------------------------------------------------------------
def test_silent_blade_oni_look_at_the_hand_and_cast_a_spell_from_it_for_free(cards):
    s = table(cards, ["Silent-Blade Oni"], [GIANT, BOLT], [BEARS])
    stops(s)
    oni = put(s, "Silent-Blade Oni")
    giant, bolt = to_hand(s, GIANT, "p2"), to_hand(s, BOLT, "p2")
    bears = to_hand(s, BEARS, "p3")
    alice_next(s)
    attack(s, oni)
    d = None
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.player == "p1" and d.kind == "confirm":
            break
        if d is not None:
            act(s, d.player, type="declare_blockers", blocks=[]) if d.kind == "declare_blockers" else act(
                s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p1" and "look at the hand" in d.prompt
    for viewer in ("p3", SPECTATOR):  # Alice sees Bob's hand: the others do not
        assert unseen_by(s, giant, viewer) and unseen_by(s, bolt, viewer)
    assert not unseen_by(s, giant, "p1") and not unseen_by(s, bolt, "p1")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["ok"])
    d = until_asked(s)
    assert d.player == "p1" and {o.id for o in d.options} == {giant.id, bolt.id}  # Bob's cards only (Carol's hand is not "that player's")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[giant.id])
    settle(s)
    assert s.state.cards[giant.id].zone == "p1:battlefield" and s.state.cards[giant.id].controller == "p1" and s.state.cards[bolt.id].zone == "p2:hand"
    assert s.state.cards[bears.id].zone == "p3:hand"
    check(s)


# -- Lord of the Void ----------------------------------------------------------------------------------------------------------------------
def test_lord_of_the_void_exiles_seven_and_puts_a_creature_among_them_onto_the_battlefield(cards):
    s = table(cards, ["Lord of the Void"], [GRAIL, BEARS, GIANT, ANGEL], [BEARS])
    stops(s)
    lord = put(s, "Lord of the Void")
    alice_next(s)
    top = list(s.state.zones["p2:library"])[:7]
    attack(s, lord)
    d = None
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards" and all(o.id in top for o in d.options):
            break
        if d is not None:
            act(s, d.player, type="declare_blockers", blocks=[]) if d.kind == "declare_blockers" else act(
                s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p1"
    names = sorted(s.state.cards[o.id].name for o in d.options)
    assert names and all(n in (BEARS, GIANT, ANGEL) for n in names)  # creature cards among the seven (Bob drew the first card of his library on his turn: it is not among them)
    pick = next(o.id for o in d.options if s.state.cards[o.id].name == ANGEL) if ANGEL in names else d.options[0].id
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[pick])
    settle(s)
    assert s.state.cards[pick].zone == "p1:battlefield" and s.state.cards[pick].controller == "p1"
    assert all(s.state.cards[c].zone == "p2:exile" for c in top if c != pick)  # the rest stay exiled
    check(s)


# -- Ashling, the Extinguisher ---------------------------------------------------------------------------------------------------------------
def test_ashling_the_target_creature_is_sacrificed_by_the_player_she_hit(cards):
    s = table(cards, ["Ashling, the Extinguisher"], [BEARS, GIANT], [BEARS])
    stops(s)
    ashling = put(s, "Ashling, the Extinguisher")
    bears, giant, carols = put(s, BEARS, "p2"), put(s, GIANT, "p2"), put(s, BEARS, "p3")
    alice_next(s)
    attack(s, ashling)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind in ("choose_cards", "choose_one") and d.player == "p1":
            break
        if d is not None:
            act(s, d.player, type="declare_blockers", blocks=[]) if d.kind == "declare_blockers" else act(
                s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and {o.id for o in d.options} == {bears.id, giant.id}  # the damaged player's creatures only
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[giant.id])
    settle(s)
    assert s.state.cards[giant.id].zone == "p2:graveyard" and s.state.cards[bears.id].zone == "p2:battlefield" and s.state.cards[carols.id].zone == "p3:battlefield"
    check(s)


# -- cards that became FULL with the same wording (a chosen or targeted player, "that player") -----------------------------------------------
def rolls(monkeypatch, *results):
    queue = list(results)
    monkeypatch.setattr("app.game.resolve._rng_int", lambda rng, lo, hi: queue.pop(0))


def edict(cards, monkeypatch, roll):
    s = table(cards, ["Myrkul's Edict"], [BEARS, ANGEL], [BEARS, GIANT])
    bears, angel, cb, cg = put(s, BEARS, "p2"), put(s, ANGEL, "p2"), put(s, BEARS, "p3"), put(s, GIANT, "p3")
    to_hand(s, "Myrkul's Edict")
    mana(s, "p1", B=1, C=1)
    rolls(monkeypatch, roll)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Myrkul's Edict").id)
    return s, bears, angel, cb, cg


def test_myrkuls_edict_low_roll_the_opponent_you_choose_sacrifices(cards, monkeypatch):
    s, bears, angel, cb, cg = edict(cards, monkeypatch, 5)
    d = until_asked(s)
    assert d.player == "p1" and {o.id for o in d.options} == {"p2", "p3"}  # "Choose an opponent"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    d = until_asked(s)
    assert d.player == "p2" and {o.id for o in d.options} == {bears.id, angel.id}  # that player's choice, of their own creatures
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard" and all(s.state.cards[c.id].zone.endswith(":battlefield") for c in (angel, cb, cg))
    check(s)


def test_myrkuls_edict_mid_roll_each_opponent_sacrifices(cards, monkeypatch):
    s, bears, angel, cb, cg = edict(cards, monkeypatch, 15)
    d = until_asked(s)
    assert d.player == "p2"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[angel.id])
    d = until_asked(s)
    assert d.player == "p3"
    act(s, "p3", type="choose", decision_id=d.id, option_ids=[cb.id])
    settle(s)
    assert s.state.cards[angel.id].zone == "p2:graveyard" and s.state.cards[cb.id].zone == "p3:graveyard" and s.state.cards[bears.id].zone == "p2:battlefield"
    check(s)


def test_myrkuls_edict_a_twenty_each_opponent_sacrifices_a_creature_with_the_greatest_power(cards, monkeypatch):
    s, bears, angel, cb, cg = edict(cards, monkeypatch, 20)
    settle(s)  # Bob's greatest power is the Angel's 4, Carol's the Giant's 3: one each, nothing to choose
    assert s.state.cards[angel.id].zone == "p2:graveyard" and s.state.cards[cg.id].zone == "p3:graveyard"
    assert s.state.cards[bears.id].zone == "p2:battlefield" and s.state.cards[cb.id].zone == "p3:battlefield"
    check(s)


def vote(s, pid, option):
    d = until_asked(s)
    assert d.player == pid and d.kind == "choose_one", (d.player, pid, d.kind)
    act(s, pid, type="choose", decision_id=d.id, option_ids=[option])


def test_sail_into_the_west_return_wins_every_player_gets_up_to_two_cards_and_it_is_exiled(cards):
    s = table(cards, ["Sail into the West", GIANT], [BEARS, ANGEL], [BEARS])
    mine, bears, angel, carols = to_gy(s, GIANT, "p1"), to_gy(s, BEARS, "p2"), to_gy(s, ANGEL, "p2"), to_gy(s, BEARS, "p3")
    to_hand(s, "Sail into the West")
    mana(s, "p1", G=1, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Sail into the West").id)
    vote(s, "p1", "return")
    vote(s, "p2", "return")
    vote(s, "p3", "embark")
    for who, most in (("p1", 1), ("p2", 2), ("p3", 1)):  # each player returns up to two cards, in turn order: "up to" always asks (nothing to be learned from a graveyard)
        d = until_asked(s)
        assert d.player == who and d.min_choices == 0 and d.max_choices == most
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:2])
    settle(s)
    assert s.state.cards[mine.id].zone == "p1:hand" and s.state.cards[bears.id].zone == "p2:hand" and s.state.cards[angel.id].zone == "p2:hand" and s.state.cards[carols.id].zone == "p3:hand"
    assert s.state.cards[card_named(s, "Sail into the West").id].zone == "p1:exile"
    check(s)


def test_sail_into_the_west_a_tie_goes_to_embark_each_player_may_discard_and_draw_seven(cards):
    s = table(cards, ["Sail into the West"], [BEARS], [BEARS])
    to_hand(s, "Sail into the West")
    mana(s, "p1", G=1, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Sail into the West").id)
    vote(s, "p1", "return")
    vote(s, "p2", "embark")
    vote(s, "p3", "embark")
    settle(s)
    assert card_named(s, "Sail into the West").zone == "p1:graveyard"  # not exiled: it resolved the other way
    check(s)


def test_intellectual_offering_the_chosen_opponent_draws_three_with_you_and_untaps(cards):
    s = table(cards, ["Intellectual Offering", BEARS], [BEARS], [BEARS])
    ob, oc = put(s, BEARS, "p2"), put(s, BEARS, "p3")
    mine = put(s, BEARS)
    for c in (ob, oc, mine):
        act(s, c.controller, type="tap", card_ids=[c.id], tapped=True)
    to_hand(s, "Intellectual Offering")
    mana(s, "p1", U=1, C=4)
    hands = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2", "p3")}
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Intellectual Offering").id)
    d = until_asked(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    d = until_asked(s)  # the second "Choose an opponent" is its own choice
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    settle(s)
    assert len(s.state.zones["p2:hand"]) == hands["p2"] + 3 and len(s.state.zones["p3:hand"]) == hands["p3"] and len(s.state.zones["p1:hand"]) == hands["p1"] - 1 + 3
    assert not s.state.cards[mine.id].tapped and not s.state.cards[oc.id].tapped and s.state.cards[ob.id].tapped  # the second opponent's permanents untap, the first's do not
    check(s)


def test_disciple_of_perdition_exile_target_opponents_graveyard_that_player_loses_1_life(cards):
    s = table(cards, ["Disciple of Perdition", "Murder"], [BEARS], [BEARS])
    disciple = put(s, "Disciple of Perdition")
    bears = to_gy(s, BEARS, "p2")
    carols = to_gy(s, BEARS, "p3")
    to_hand(s, "Murder")
    mana(s, "p1", B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[disciple.id])
    for _ in range(12):  # the trigger: choose one (mode), then its target
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        if d.kind == "choose_cards" and "mode" in d.prompt.lower():
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[1].id])
        elif {"p2", "p3"} <= {o.id for o in d.options}:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert s.state.cards[bears.id].zone == "p2:exile" and s.state.cards[carols.id].zone == "p3:graveyard"
    assert s.state.players["p2"].life == 39 and s.state.players["p3"].life == 40
    check(s)


def test_down_for_repairs_the_attraction_group_is_that_players_and_may_have_no_target(cards):
    """Commander decks have no Attractions (no Attraction deck, 717), so the second target group - "up to one target Attraction that player controls" - has no legal target and is
    skipped; the spell is the hand disruption (an Attraction destroyed would go to its owner's junkyard, which is not modelled)."""
    s = table(cards, ["Down for Repairs"], [BEARS, GIANT, GRAIL], [])
    for name in (BEARS, GRAIL):
        to_hand(s, name, "p2")
    to_hand(s, "Down for Repairs")
    mana(s, "p1", B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Down for Repairs").id, targets=["p2"], target_counts=[1, 0])
    d = until_asked(s)
    assert d.player == "p1" and {s.state.cards[o.id].name for o in d.options} == {BEARS, GRAIL}  # you choose a nonland card from the revealed hand
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[card_named(s, GRAIL, "p2").id])
    settle(s)
    assert s.state.cards[card_named(s, GRAIL, "p2").id].zone == "p2:graveyard" and s.state.cards[card_named(s, BEARS, "p2").id].zone == "p2:hand"
    check(s)


def test_windgraces_judgment_a_target_for_each_opponent_you_choose(cards):
    """601.2c: "For any number of opponents, destroy target nonland permanent that player controls" - a target for each opponent chosen, none for the others."""
    s = table(cards, ["Windgrace's Judgment"], [BEARS], [GIANT])
    bears, giant = put(s, BEARS, "p2"), put(s, GIANT, "p3")
    to_hand(s, "Windgrace's Judgment")
    mana(s, "p1", B=1, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Windgrace's Judgment").id, targets=[bears.id], target_counts=[1, 0])
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard" and s.state.cards[giant.id].zone == "p3:battlefield"  # Carol was not chosen
    check(s)


def test_windgraces_judgment_each_opponents_target_is_their_own_permanent(cards):
    s = table(cards, ["Windgrace's Judgment"], [BEARS], [GIANT])
    bears, giant = put(s, BEARS, "p2"), put(s, GIANT, "p3")
    to_hand(s, "Windgrace's Judgment")
    mana(s, "p1", B=1, G=1, C=3)
    with pytest.raises(ActionError):  # Carol's Giant isn't Bob's group's legal target
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Windgrace's Judgment").id, targets=[giant.id, bears.id], target_counts=[1, 1])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Windgrace's Judgment").id, targets=[bears.id, giant.id], target_counts=[1, 1])
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard" and s.state.cards[giant.id].zone == "p3:graveyard"
    check(s)


def test_dark_salvation_the_creature_gets_minus_one_for_each_zombie_that_target_player_controls(cards):
    """608.2c, 608.2b: the Zombies are made first; the count is the target player's own (the player chosen for the first target), whoever controls the creature."""
    from tests.wave9c_kit import pt

    s = table(cards, ["Dark Salvation"], [ANGEL], [])
    angel = put(s, ANGEL, "p2")
    to_hand(s, "Dark Salvation")
    mana(s, "p1", B=1, C=4)  # {X}{X}{B}
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Dark Salvation").id, targets=["p2", angel.id], target_counts=[1, 1], x_value=2)
    settle(s)
    zombies = [c for c in s.state.cards.values() if c.name == "Zombie" and c.zone == "p2:battlefield"]
    assert len(zombies) == 2 and pt(s, ANGEL, "p2") == (2, 2)  # Bob made them; Bob's two Zombies: -2/-2 until end of turn
    check(s)


def test_dark_salvation_counts_the_zombies_of_the_player_not_of_the_creatures_controller(cards):
    from tests.wave9c_kit import pt

    s = table(cards, ["Dark Salvation"], [ANGEL], [])
    angel = put(s, ANGEL, "p2")
    to_hand(s, "Dark Salvation")
    mana(s, "p1", B=1, C=6)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Dark Salvation").id, targets=["p1", angel.id], target_counts=[1, 1], x_value=3)
    settle(s)
    assert len([c for c in s.state.cards.values() if c.name == "Zombie" and c.zone == "p1:battlefield"]) == 3 and pt(s, ANGEL, "p2") == (1, 1)  # Alice's three Zombies, Bob's Angel
    check(s)


# -- The Black Gate ---------------------------------------------------------------------------------------------------------------------
def black_gate(cards, defender):
    """Bob has the most life and is the chosen player; ``defender`` is attacked by Alice's creature the Gate was used on."""
    from tests.test_rules_wave34b_activated import to_phase

    s = table(cards, ["The Black Gate", BEARS], [BEARS], [BEARS])
    stops(s)
    gate = put(s, "The Black Gate")
    mine = put(s, BEARS)
    bob_blocker, carol_blocker = put(s, BEARS, "p2"), put(s, BEARS, "p3")
    alice_next(s)
    act(s, "p1", type="set_life", player="p2", value=45)
    mana(s, "p1", B=1, C=1)
    activate(s, "p1", gate, contains="Choose a player", targets=[mine.id])
    d = until_asked(s)
    assert d.player == "p1" and {o.id for o in d.options} == {"p2"}  # 119.1: Bob alone has the most life (a public number)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    settle(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": mine.id, "target": defender}])
    to_phase(s, "declare_blockers")
    return s, mine, bob_blocker, carol_blocker


def test_the_black_gate_creatures_of_the_player_with_the_most_life_cannot_block_it(cards):
    s, mine, bob_blocker, _ = black_gate(cards, "p2")
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bob_blocker.id, "attacker_id": mine.id}])
    act(s, "p2", type="declare_blockers", blocks=[])
    check(s)


def test_the_black_gate_other_players_creatures_still_block_it(cards):
    s, mine, _, carol_blocker = black_gate(cards, "p3")
    act(s, "p3", type="declare_blockers", blocks=[{"blocker_id": carol_blocker.id, "attacker_id": mine.id}])
    settle(s)
    check(s)


def test_the_black_gate_tied_players_are_all_offered(cards):
    s = table(cards, ["The Black Gate", BEARS], [BEARS], [BEARS])
    gate = put(s, "The Black Gate")
    mine = put(s, BEARS)
    mana(s, "p1", B=1, C=1)
    activate(s, "p1", gate, contains="Choose a player", targets=[mine.id])
    d = until_asked(s)
    assert {o.id for o in d.options} == {"p1", "p2", "p3"}  # all at 40
    check(s)


# -- Siege Dragon -----------------------------------------------------------------------------------------------------------------------
def test_siege_dragon_damages_the_creatures_without_flying_of_the_defending_player_only(cards):
    """508.5: "defending player" and the "that player" after it are the one player the Dragon attacks: Bob's creatures without flying take 2, Carol's do not."""
    s = table(cards, ["Siege Dragon"], [BEARS, ANGEL], [BEARS])
    stops(s)
    dragon = put(s, "Siege Dragon")
    bears, angel, carols = put(s, BEARS, "p2"), put(s, ANGEL, "p2"), put(s, BEARS, "p3")
    alice_next(s)
    attack(s, dragon)
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard" and s.state.cards[angel.id].zone == "p2:battlefield"  # (flying: not damaged)
    assert s.state.cards[carols.id].zone == "p3:battlefield" and not s.state.cards[angel.id].damage
    check(s)


def test_siege_dragon_with_a_wall_the_defending_player_is_not_damaged(cards):
    """603.4: the intervening "if defending player controls no Walls" is checked as it triggers: a Wall of Bob's stops the whole ability."""
    s = table(cards, ["Siege Dragon"], [BEARS, "Wall of Stone"], [])
    stops(s)
    dragon = put(s, "Siege Dragon")
    bears = put(s, BEARS, "p2")
    put(s, "Wall of Stone", "p2")
    alice_next(s)
    attack(s, dragon)
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:battlefield" and not s.state.cards[bears.id].damage
    check(s)


# -- The Fall of Kroog ------------------------------------------------------------------------------------------------------------------
def test_the_fall_of_kroog_the_land_and_the_damage_belong_to_the_opponent_chosen_first(cards):
    """115.1, 601.2c: "Choose target opponent" is the first target; "target land that player controls" is a second one, legal only for that player's lands; the damage goes to that
    player and to the creatures they control (608.2c), and to nobody else."""
    s = table(cards, ["The Fall of Kroog"], [BEARS], [BEARS])
    bbears, cbears = put(s, BEARS, "p2"), put(s, BEARS, "p3")
    bisland, cisland = put(s, "Island", "p2"), put(s, "Island", "p3")
    to_hand(s, "The Fall of Kroog")
    mana(s, "p1", R=2, C=4)
    with pytest.raises(ActionError):  # Carol's land is not Bob's
        act(s, "p1", type="cast_spell", card_id=card_named(s, "The Fall of Kroog").id, targets=["p2", cisland.id], target_counts=[1, 1])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "The Fall of Kroog").id, targets=["p2", bisland.id], target_counts=[1, 1])
    settle(s)
    assert s.state.cards[bisland.id].zone == "p2:graveyard" and s.state.cards[cisland.id].zone == "p3:battlefield"
    assert s.state.players["p2"].life == 37 and s.state.players["p3"].life == 40
    assert s.state.cards[bbears.id].zone == "p2:battlefield" and s.state.cards[bbears.id].damage == 1  # (a 2/2 takes 1)
    assert s.state.cards[cbears.id].zone == "p3:battlefield" and not s.state.cards[cbears.id].damage
    check(s)


# -- Tibalt, the Fiend-Blooded ----------------------------------------------------------------------------------------------------------
def test_tibalt_minus_four_damage_equal_to_the_cards_in_the_target_players_hand(cards):
    """120.3, 608.2h: the amount is the target player's own hand as the ability resolves; the damage goes to that player."""
    s = table(cards, ["Tibalt, the Fiend-Blooded"], [BEARS, GIANT, ANGEL], [BEARS])
    tibalt = put(s, "Tibalt, the Fiend-Blooded")
    act(s, "p1", type="counter", card_ids=[tibalt.id], kind="loyalty", delta=5)
    for name in (BEARS, GIANT, ANGEL):
        to_hand(s, name, "p2")
    to_hand(s, BEARS, "p3")
    size = len(s.state.zones["p2:hand"])
    assert size == 3
    activate(s, "p1", tibalt, contains="−4", targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 40 - size and s.state.players["p3"].life == 40
    check(s)


# -- Elder Brain ------------------------------------------------------------------------------------------------------------------------
def test_elder_brain_exiles_the_defending_players_hand_they_draw_that_many_and_you_play_the_exiled_cards(cards):
    """508.5, 406.3, 608.2c: the hand of the player the Brain attacks (not Carol's) is exiled face up, that player draws as many cards, and the Brain's controller may play lands and cast
    spells from among the exiled cards, spending mana as though it were mana of any color."""
    s = table(cards, ["Elder Brain"], [GIANT, BOLT, BEARS], [BEARS])
    stops(s)
    brain = put(s, "Elder Brain")
    giant, bolt = to_hand(s, GIANT, "p2"), to_hand(s, BOLT, "p2")
    carols = to_hand(s, BEARS, "p3")
    alice_next(s)
    hand = len(s.state.zones["p2:hand"])  # (Bob drew for his turn)
    drawn_from = list(s.state.zones["p2:library"])[:hand]
    attack(s, brain)
    settle(s)
    assert s.state.cards[giant.id].zone == "p2:exile" and s.state.cards[bolt.id].zone == "p2:exile"  # face up, public: 406.3
    assert s.state.cards[carols.id].zone == "p3:hand"
    assert len(s.state.zones["p2:hand"]) == hand and all(c in s.state.zones["p2:hand"] for c in drawn_from)  # as many as were exiled
    check(s)
    to_phase(s, "main2")
    mana(s, "p1", G=4)  # {3}{R}: the red from Forests' green
    act(s, "p1", type="cast_spell", card_id=giant.id)
    settle(s)
    assert s.state.cards[giant.id].zone == "p1:battlefield" and s.state.cards[giant.id].controller == "p1"
    check(s)


# -- Mindleech Mass ---------------------------------------------------------------------------------------------------------------------
def mass_prompt(s):
    """Alice's first question (may she use the ability): answered; the hand is looked at only if she did."""
    d = None
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.player == "p1" and d.kind not in ("declare_attackers", "declare_blockers"):
            break
        if d is not None:
            act(s, d.player, type="declare_blockers", blocks=[]) if d.kind == "declare_blockers" else act(
                s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p1"
    return d


def test_mindleech_mass_look_at_their_hand_then_cast_a_spell_from_it_without_paying(cards):
    """701.20e (look), 608.2g, 601.2: two choices of the controller, each its own "may": use the ability (see the hand), then cast one of the cards seen."""
    s = table(cards, ["Mindleech Mass"], [GIANT, BOLT], [BEARS])
    stops(s)
    mass = put(s, "Mindleech Mass")
    giant, bolt = to_hand(s, GIANT, "p2"), to_hand(s, BOLT, "p2")
    bears = to_hand(s, BEARS, "p3")
    alice_next(s)
    attack(s, mass)
    d = mass_prompt(s)
    while "look at the hand" not in d.prompt and d.kind == "confirm":
        assert unseen_by(s, giant, "p1")  # not seen before she says so
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
        d = mass_prompt(s)
    assert "look at the hand" in d.prompt
    for viewer in ("p3", SPECTATOR):
        assert unseen_by(s, giant, viewer) and unseen_by(s, bolt, viewer)
    assert not unseen_by(s, giant, "p1") and not unseen_by(s, bolt, "p1")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["ok"])
    d = until_asked(s)
    assert d.player == "p1" and {o.id for o in d.options} == {giant.id, bolt.id}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[giant.id])
    settle(s)
    assert s.state.cards[giant.id].zone == "p1:battlefield" and s.state.cards[bolt.id].zone == "p2:hand" and s.state.cards[bears.id].zone == "p3:hand"
    check(s)


def test_mindleech_mass_she_may_decline_and_then_sees_nothing(cards):
    s = table(cards, ["Mindleech Mass"], [GIANT, BOLT], [BEARS])
    stops(s)
    mass = put(s, "Mindleech Mass")
    giant = to_hand(s, GIANT, "p2")
    alice_next(s)
    attack(s, mass)
    d = mass_prompt(s)
    assert d.kind == "confirm" and "look at the hand" not in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["no"])
    settle(s)
    assert unseen_by(s, giant, "p1") and s.state.cards[giant.id].zone == "p2:hand"
    check(s)


# -- Painful Memories / Doomsday Specter / Leshrac's Sigil ------------------------------------------------------------------------------
def test_painful_memories_the_card_you_choose_goes_on_top_of_their_library(cards):
    """701.20e (a private look), 108.3: Alice alone sees Bob's hand, picks a card and it goes on top of Bob's library (the owner's, not hers)."""
    s = table(cards, ["Painful Memories"], [GIANT, BOLT, BEARS], [BEARS])
    giant, bolt, bears = to_hand(s, GIANT, "p2"), to_hand(s, BOLT, "p2"), to_hand(s, BEARS, "p2")
    carols = to_hand(s, BEARS, "p3")
    to_hand(s, "Painful Memories")
    mana(s, "p1", B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Painful Memories").id, targets=["p2"])
    d = until_asked(s)
    assert d.player == "p1" and {o.id for o in d.options} == {giant.id, bolt.id, bears.id}  # Bob's hand only, seen by her alone
    for viewer in ("p3", SPECTATOR):
        assert all(unseen_by(s, c, viewer) for c in (giant, bolt, bears))
    assert not unseen_by(s, bolt, "p1")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bolt.id])
    settle(s)
    top = s.state.zones["p2:library"][0]
    assert s.state.cards[top].name == BOLT and s.state.cards[top].owner == "p2"
    assert s.state.cards[giant.id].zone == "p2:hand" and s.state.cards[carols.id].zone == "p3:hand"
    check(s)


def test_doomsday_specter_you_choose_a_card_of_the_hand_you_looked_at_and_the_player_discards_it(cards):
    s = table(cards, ["Doomsday Specter"], [GIANT, BOLT], [BEARS])
    stops(s)
    specter = put(s, "Doomsday Specter")  # (put onto the table: its enters trigger doesn't run)
    giant, bolt = to_hand(s, GIANT, "p2"), to_hand(s, BOLT, "p2")
    bears = to_hand(s, BEARS, "p3")
    alice_next(s)
    attack(s, specter)
    d = None
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.player == "p1" and d.kind not in ("declare_attackers", "declare_blockers"):
            break
        if d is not None:
            act(s, d.player, type="declare_blockers", blocks=[]) if d.kind == "declare_blockers" else act(
                s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p1" and {o.id for o in d.options} == set(s.state.zones["p2:hand"]) >= {giant.id, bolt.id}  # Bob's hand (with what he drew), not Carol's
    for viewer in ("p3", SPECTATOR):
        assert unseen_by(s, giant, viewer) and unseen_by(s, bolt, viewer)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bolt.id])
    settle(s)
    assert s.state.cards[bolt.id].zone == "p2:graveyard" and s.state.cards[giant.id].zone == "p2:hand" and s.state.cards[bears.id].zone == "p3:hand"
    check(s)


def test_leshracs_sigil_pay_and_the_caster_discards_the_card_you_choose(cards):
    """603.2: the caster is "that player" (the event's); you pay {B}{B} as the ability resolves (118.12), then look at their hand and choose."""
    s = table(cards, ["Leshrac's Sigil"], [BEARS, GIANT, BOLT], [])
    stops(s)
    put(s, "Leshrac's Sigil")
    giant, bolt = to_hand(s, GIANT, "p2"), to_hand(s, BOLT, "p2")
    bears = to_hand(s, BEARS, "p2")
    to_phase(s, "main1", turn=2)  # Bob's turn: his first main phase
    assert s.state.rules.priority == "p2"
    mana(s, "p2", G=1, C=1)
    act(s, "p2", type="cast_spell", card_id=bears.id)
    mana(s, "p1", B=2)
    d = until_asked(s)
    assert d.player == "p1" and {o.id for o in d.options} == {"pay", "decline"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    d = until_asked(s)
    assert d.player == "p1" and {o.id for o in d.options} == set(s.state.zones["p2:hand"]) >= {giant.id, bolt.id}  # Bob's hand; the Bears are on the stack
    assert unseen_by(s, giant, "p3", SPECTATOR) and not unseen_by(s, giant, "p1")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bolt.id])
    settle(s)
    assert s.state.cards[bolt.id].zone == "p2:graveyard" and s.state.cards[giant.id].zone == "p2:hand"
    check(s)
