"""Wave 51G: popular cards ranked 4,000 to 8,000 that were one clause short of FULL (CR 2026-09-25), real Oracle text (tests/fixtures/wave51g_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 102.2 / 101.4: Heartwood Storyteller / Standstill - "each of that player's opponents" is every player but the one the trigger names (the controller among them).
* 903.3 / 701.8: Slash the Ranks, Elspeth Tirel - "except for commanders" / "except for lands and tokens".
* 119.5: Sorin Markov - "Target opponent's life total becomes 10."
* 107.3 / 102.2: Rot Hulk - "up to X target … where X is the number of opponents you have".
* 402.3: Ensnaring Bridge - "power greater than the number of cards in your hand".
* 800.4: Rampant Frogantua - "+10/+10 for each player who has lost the game".
* 118.7 / 119.1: Shadow of Mortality - "this spell costs {X} less … where X is the difference" between the starting life total and yours.
* 603.2: Brood Sliver (its controller may create a token), Prophet of the Scarab ("whichever is greater"), Preacher of the Schism ("while you have the most life").
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, attack, next_turn, settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, reloaded, to_hand, zone_of
from tests.wave51g_kit import open_repo

NAMES = ["Heartwood Storyteller", "Standstill", "Rot Hulk", "Slash the Ranks", "Elspeth Tirel", "Engulf the Shore", "Sorin Markov", "Ensnaring Bridge",
         "Nightmare Unmaking", "Rampant Frogantua", "Shadow of Mortality", "Brood Sliver", "Prophet of the Scarab", "Preacher of the Schism"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", NAMES)
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def hand(s, pid="p1"):
    return len([c for c in s.state.cards.values() if c.zone == f"{pid}:hand"])


# ---- Heartwood Storyteller, Standstill -----------------------------------------------------------------------------------------------------------
def test_storyteller_lets_the_caster_s_opponent_draw_when_you_cast_a_noncreature_spell(cards):
    s = build(cards, ["Heartwood Storyteller", "Lightning Bolt"])
    put(s, "Heartwood Storyteller")
    mana(s, "p1", R=1)
    before = hand(s, "p2")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])
    settle(s)  # Bob answers "yes" to the may-draw
    assert hand(s, "p2") == before + 1 and life(s, "p2") == 37
    check(s)
    assert hand(reloaded(s), "p2") == before + 1


def test_storyteller_draws_for_you_when_an_opponent_casts_a_noncreature_spell(cards):
    s = build(cards, ["Heartwood Storyteller"], ["Lightning Bolt"])
    stops(s)
    put(s, "Heartwood Storyteller")
    act(s, "p1", type="pass_priority")  # Bob gets priority in Alice's main phase
    mana(s, "p2", R=1)
    before = (hand(s, "p1"), hand(s, "p2"))
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Lightning Bolt", "p2").id, targets=["p1"])
    settle(s)  # Alice (an opponent of the caster, though Bob is her opponent) may draw; Bob, the caster, does not
    assert (hand(s, "p1"), hand(s, "p2")) == (before[0] + 1, before[1])
    check(s)


def test_storyteller_ignores_a_creature_spell(cards):
    s = build(cards, ["Heartwood Storyteller", "Grizzly Bears"])
    put(s, "Heartwood Storyteller")
    mana(s, "p1", G=2)
    before = hand(s, "p2")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Grizzly Bears").id)
    settle(s)
    assert hand(s, "p2") == before
    check(s)


def test_standstill_draws_three_for_the_opponents_of_whoever_cast_the_spell(cards):
    s = build(cards, ["Standstill", "Lightning Bolt"])
    put(s, "Standstill")
    mana(s, "p1", R=1)
    before = hand(s, "p2")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])
    settle(s)
    assert zone_of(s, "Standstill") == "p1:graveyard" and hand(s, "p2") == before + 3
    check(s)


def test_standstill_gives_its_controller_the_cards_when_the_opponent_casts(cards):
    s = build(cards, ["Standstill"], ["Lightning Bolt"])
    stops(s)
    put(s, "Standstill")
    act(s, "p1", type="pass_priority")
    mana(s, "p2", R=1)
    before = (hand(s, "p1"), hand(s, "p2"))
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Lightning Bolt", "p2").id, targets=["p1"])
    settle(s)
    assert zone_of(s, "Standstill") == "p1:graveyard" and (hand(s, "p1"), hand(s, "p2")) == (before[0] + 3, before[1])
    check(s)


# ---- Slash the Ranks, Elspeth Tirel ----------------------------------------------------------------------------------------------------------------
def test_slash_the_ranks_destroys_everything_but_commanders(cards):
    s = build(cards, ["Slash the Ranks", "Grizzly Bears", "Elspeth Tirel"], ["Grizzly Bears"])
    put(s, "Grizzly Bears")
    put(s, "Elspeth Tirel")
    put(s, "Grizzly Bears", "p2")
    put(s, "Krenko, Mob Boss")  # Alice's commander
    put(s, "Atraxa, Praetors' Voice", "p2")  # Bob's commander: left out too
    mana(s, "p1", W=2, G=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Slash the Ranks").id)
    settle(s)
    assert [zone_of(s, "Grizzly Bears"), zone_of(s, "Elspeth Tirel"), zone_of(s, "Grizzly Bears", "p2")] == ["p1:graveyard", "p1:graveyard", "p2:graveyard"]
    assert zone_of(s, "Krenko, Mob Boss") == "p1:battlefield" and zone_of(s, "Atraxa, Praetors' Voice", "p2") == "p2:battlefield"
    check(s)


def test_elspeth_tirel_minus_five_keeps_lands_and_tokens(cards):
    s = build(cards, ["Elspeth Tirel", "Grizzly Bears", "Sol Ring"], ["Grizzly Bears"])
    put(s, "Grizzly Bears")
    put(s, "Sol Ring")
    put(s, "Grizzly Bears", "p2")
    elspeth = put(s, "Elspeth Tirel")
    act(s, "p1", type="counter", card_ids=[elspeth.id], kind="loyalty", delta=8)
    activate(s, "p1", elspeth, "Create three 1/1")  # the −2: three Soldier tokens, which the −5 leaves alone
    settle(s)
    next_turn(s)
    forest = next(c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    tokens = [c.id for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Soldier"]
    assert len(tokens) == 3
    activate(s, "p1", elspeth, "Destroy all other")
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard" and zone_of(s, "Sol Ring") == "p1:graveyard" and zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"
    assert s.state.cards[forest.id].zone == "p1:battlefield" and zone_of(s, "Elspeth Tirel") == "p1:battlefield"
    assert all(s.state.cards[t].zone == "p1:battlefield" for t in tokens)
    check(s)


def empty_hand(s, pid="p1"):
    ids = [c.id for c in s.state.cards.values() if c.zone == f"{pid}:hand"]
    if ids:
        act(s, pid, type="move", card_ids=ids, to={"player": pid, "zone": "exile"})


def forests_to_hand(s, n, pid="p1"):
    ids = [c.id for c in s.state.cards.values() if c.owner == pid and c.name == "Forest" and c.zone == f"{pid}:library"][:n]
    act(s, pid, type="move", card_ids=ids, to={"player": pid, "zone": "hand"})


# ---- Sorin Markov ----------------------------------------------------------------------------------------------------------------------------------
def test_sorin_markov_sets_an_opponent_s_life_total_to_ten(cards):
    s = build(cards, ["Sorin Markov"])
    sorin = put(s, "Sorin Markov")
    act(s, "p1", type="counter", card_ids=[sorin.id], kind="loyalty", delta=4)
    with pytest.raises(ActionError):  # an opponent, not you
        activate(s, "p1", sorin, "life total becomes 10", targets=["p1"])
    activate(s, "p1", sorin, "life total becomes 10", targets=["p2"])
    settle(s)
    assert (life(s, "p1"), life(s, "p2")) == (40, 10)
    check(s)
    assert life(reloaded(s), "p2") == 10


def test_sorin_markov_raises_a_lower_life_total_too(cards):
    s = build(cards, ["Sorin Markov"])
    sorin = put(s, "Sorin Markov")
    act(s, "p1", type="counter", card_ids=[sorin.id], kind="loyalty", delta=4)
    act(s, "p1", type="set_life", player="p2", value=4)
    activate(s, "p1", sorin, "life total becomes 10", targets=["p2"])
    settle(s)
    assert life(s, "p2") == 10
    check(s)


# ---- Rot Hulk --------------------------------------------------------------------------------------------------------------------------------------
def test_rot_hulk_returns_up_to_as_many_zombies_as_you_have_opponents(cards):
    s = build(cards, ["Rot Hulk", "Gravecrawler", "Prophet of the Scarab"])
    for name in ("Gravecrawler", "Prophet of the Scarab"):
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"player": "p1", "zone": "graveyard"})
    mana(s, "p1", B=2, G=5)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Rot Hulk").id)
    settle(s)  # one opponent: one of the two Zombie cards comes back
    back = [n for n in ("Gravecrawler", "Prophet of the Scarab") if zone_of(s, n) == "p1:battlefield"]
    assert len(back) == 1 and zone_of(s, "Rot Hulk") == "p1:battlefield"
    check(s)
    assert zone_of(reloaded(s), back[0]) == "p1:battlefield"


# ---- Engulf the Shore ------------------------------------------------------------------------------------------------------------------------------
def test_engulf_the_shore_returns_creatures_with_toughness_up_to_your_islands(cards):
    s = build(cards, ["Engulf the Shore", "Island", "Grizzly Bears", "Llanowar Elves"], ["Llanowar Elves"])
    put(s, "Island")
    put(s, "Grizzly Bears")
    put(s, "Llanowar Elves")
    put(s, "Llanowar Elves", "p2")
    mana(s, "p1", U=1, G=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Engulf the Shore").id)
    settle(s)  # one Island: toughness 1 or less goes home, both players' Elves; the Bears (toughness 2) stay
    assert zone_of(s, "Llanowar Elves") == "p1:hand" and zone_of(s, "Llanowar Elves", "p2") == "p2:hand"
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield"
    check(s)


# ---- Ensnaring Bridge, Nightmare Unmaking ----------------------------------------------------------------------------------------------------------
def test_ensnaring_bridge_keeps_creatures_with_more_power_than_your_hand_from_attacking(cards):
    from app.rules.combat import attack_problem
    from app.rules.plan import Plan

    s = build(cards, ["Ensnaring Bridge"], ["Grizzly Bears"])
    put(s, "Ensnaring Bridge")
    bears = put(s, "Grizzly Bears", "p2")
    empty_hand(s)
    forests_to_hand(s, 1)  # one card in Alice's hand: the 2-power Bears can't attack
    to_phase(s, "main1", turn=2)
    plan = Plan(s.state, "p2", s.cards, None)
    assert attack_problem(s.state, s.state.cards[bears.id], plan.ch(s.state.cards[bears.id])) is not None
    forests_to_hand(s, 1)  # two cards: power 2 is not greater than 2
    plan = Plan(s.state, "p2", s.cards, None)
    assert attack_problem(s.state, s.state.cards[bears.id], plan.ch(s.state.cards[bears.id])) is None
    check(s)


def test_nightmare_unmaking_exiles_creatures_with_more_power_than_your_hand(cards):
    s = build(cards, ["Nightmare Unmaking", "Grizzly Bears", "Llanowar Elves"])
    put(s, "Grizzly Bears")
    put(s, "Llanowar Elves")
    empty_hand(s)
    forests_to_hand(s, 1)
    mana(s, "p1", B=2, G=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Nightmare Unmaking").id, modes=[0])
    settle(s)  # one card left in hand after the cast: power 2 goes, power 1 stays
    assert zone_of(s, "Grizzly Bears") == "p1:exile" and zone_of(s, "Llanowar Elves") == "p1:battlefield"
    check(s)


# ---- Rampant Frogantua -----------------------------------------------------------------------------------------------------------------------------
def test_rampant_frogantua_grows_for_each_player_who_has_lost(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    def side(commander, names):
        return deck(cards, commander, [*((1, n) for n in names), (9, "Forest")])

    setups = [PlayerSetup("Alice", cards=side("Krenko, Mob Boss", ["Rampant Frogantua"])), PlayerSetup("Bob", cards=side("Atraxa, Praetors' Voice", [])),
              PlayerSetup("Carol", cards=side("Krenko, Mob Boss", []))]
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    put(s, "Rampant Frogantua")
    assert pt(s, "Rampant Frogantua") == (3, 3)
    act(s, "p3", type="concede")
    assert pt(s, "Rampant Frogantua") == (13, 13)
    check(s)
    assert pt(reloaded(s), "Rampant Frogantua") == (13, 13)


# ---- Shadow of Mortality ---------------------------------------------------------------------------------------------------------------------------
def test_shadow_of_mortality_costs_the_life_below_the_starting_total_less(cards):
    s = build(cards, ["Shadow of Mortality"])
    shadow = to_hand(s, "Shadow of Mortality")
    mana(s, "p1", B=2, G=6)  # {13}{B}{B} less 7 = {6}{B}{B}
    with pytest.raises(ActionError):  # at the starting life total nothing is taken off
        act(s, "p1", type="cast_spell", card_id=shadow.id)
    act(s, "p1", type="set_life", player="p1", value=33)
    act(s, "p1", type="cast_spell", card_id=shadow.id)
    settle(s)
    assert zone_of(s, "Shadow of Mortality") == "p1:battlefield"
    check(s)


# ---- Brood Sliver, Prophet of the Scarab, Preacher of the Schism -----------------------------------------------------------------------------------
def tokens(s, pid, name):
    return [c for c in s.state.cards.values() if c.zone == f"{pid}:battlefield" and c.name == name and c.is_token]


def test_brood_sliver_lets_its_controller_make_a_sliver_when_their_sliver_connects(cards):
    s = build(cards, ["Brood Sliver"], forests=30, islands=30)
    sliver = put(s, "Brood Sliver")
    next_turn(s)
    attack(s, sliver)
    to_phase(s, "main2")  # the may-create question is answered "yes"
    assert life(s, "p2") == 37 and len(tokens(s, "p1", "Sliver")) == 1
    check(s)
    assert len(tokens(reloaded(s), "p1", "Sliver")) == 1


def test_brood_sliver_gives_the_token_to_the_opponent_whose_sliver_dealt_the_damage(cards):
    s = build(cards, ["Brood Sliver"], forests=30, islands=30)
    put(s, "Brood Sliver")
    act(s, "p2", type="create_token", player="p2", token={"name": "Test Sliver", "type_line": "Token Creature — Sliver", "power": "2", "toughness": "2", "text": ""})
    to_phase(s, "declare_attackers", turn=2)
    mine = next(c for c in s.state.cards.values() if c.name == "Test Sliver")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": mine.id, "target": "p1"}])
    to_phase(s, "main2", turn=2)
    assert life(s, "p1") == 38 and len(tokens(s, "p2", "Sliver")) == 1 and not tokens(s, "p1", "Sliver")
    check(s)


def test_prophet_of_the_scarab_draws_for_the_greater_of_its_two_counts(cards):
    s = build(cards, ["Prophet of the Scarab", "Gravecrawler", "Rot Hulk"])
    mana(s, "p1", U=1, G=4)
    prophet = to_hand(s, "Prophet of the Scarab")
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=prophet.id)
    settle(s)  # only the Prophet itself is a Zombie you control, no Zombie card in the graveyard: one card
    assert hand(s) == before - 1 + 1
    check(s)
    s = build(cards, ["Prophet of the Scarab", "Gravecrawler", "Rot Hulk"])
    for name in ("Gravecrawler", "Rot Hulk"):
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"player": "p1", "zone": "graveyard"})
    mana(s, "p1", U=1, G=4)
    prophet = to_hand(s, "Prophet of the Scarab")
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=prophet.id)
    settle(s)  # two Zombie cards in the graveyard beat the one Zombie on the battlefield: two cards
    assert hand(s) == before - 1 + 2
    check(s)
    assert hand(reloaded(s)) == before + 1


def preacher_attack(cards, bob_life):
    s = build(cards, ["Preacher of the Schism"], forests=30, islands=30)
    preacher = put(s, "Preacher of the Schism")
    next_turn(s)
    act(s, "p1", type="set_life", player="p2", value=bob_life)
    before = (hand(s), life(s))
    attack(s, preacher)
    to_phase(s, "main2")
    return s, before


def test_preacher_of_the_schism_draws_while_you_have_the_most_life_or_are_tied(cards):
    s, before = preacher_attack(cards, 40)  # tied: both attack triggers happen
    assert (hand(s), life(s)) == (before[0] + 1, before[1] - 1) and len(tokens(s, "p1", "Vampire")) == 1
    check(s)
    assert hand(reloaded(s)) == before[0] + 1


def test_preacher_of_the_schism_draws_nothing_when_an_opponent_has_more_life(cards):
    s, before = preacher_attack(cards, 50)
    assert (hand(s), life(s)) == before and len(tokens(s, "p1", "Vampire")) == 1  # (the token trigger is the other one: the player attacked has the most life)
    check(s)


# ---- Well of Ideas, Smallpox / Death Cloud, Multiclass Baldric, Scion of Draco, Mind into Matter -------------------------------------------------------
def test_well_of_ideas_draws_an_extra_card_for_each_other_player_in_their_draw_step(cards):
    s = build(cards, ["Well of Ideas"], forests=30, islands=30)
    put(s, "Well of Ideas")
    to_phase(s, "main1", turn=2)
    assert hand(s, "p2") == 2  # the draw step's card and the extra one
    to_phase(s, "main1", turn=3)
    assert hand(s) == 3  # its own controller's draw step is not "another player's": the draw and the two additional cards of its own ability
    check(s)


def test_smallpox_makes_every_player_lose_life_discard_and_sacrifice_a_creature_and_a_land(cards):
    s = build(cards, ["Smallpox", "Grizzly Bears"], ["Grizzly Bears"])
    put(s, "Grizzly Bears")
    put(s, "Grizzly Bears", "p2")
    for pid, land in (("p1", "Forest"), ("p2", "Island")):
        spare = next(c for c in s.state.cards.values() if c.owner == pid and c.name == land and c.zone == f"{pid}:library")
        act(s, pid, type="move", card_ids=[spare.id], to={"player": pid, "zone": "battlefield"})
        forests = [c.id for c in s.state.cards.values() if c.owner == pid and c.name == land and c.zone == f"{pid}:library"][:2]
        act(s, pid, type="move", card_ids=forests, to={"player": pid, "zone": "hand"})
    mana(s, "p1", B=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Smallpox").id)
    settle(s)
    assert (life(s, "p1"), life(s, "p2")) == (39, 39)
    assert (hand(s), hand(s, "p2")) == (1, 1)  # each discarded one of two cards (Smallpox itself had left the hand)
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard" and zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"
    assert not [c for c in s.state.cards.values() if c.zone in ("p1:battlefield", "p2:battlefield") and c.name in ("Forest", "Island")]  # (the one land each had)
    check(s)


def keywords(s, name, pid="p1"):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id]).keywords


def test_multiclass_baldric_gives_a_keyword_for_each_kind_of_creature_you_control(cards):
    s = build(cards, ["Multiclass Baldric", "Grizzly Bears", "Preacher of the Schism"])
    bears = put(s, "Grizzly Bears")
    baldric = put(s, "Multiclass Baldric")
    act(s, "p1", type="attach", card_ids=[baldric.id], to=bears.id)
    assert "lifelink" not in keywords(s, "Grizzly Bears")  # no Cleric yet
    put(s, "Preacher of the Schism")  # a Vampire Cleric
    assert {"lifelink"} <= keywords(s, "Grizzly Bears") and not {"deathtouch", "haste", "flying"} & keywords(s, "Grizzly Bears")
    check(s)
    assert "lifelink" in keywords(reloaded(s), "Grizzly Bears")


def test_scion_of_draco_gives_each_creature_the_keyword_of_its_colors(cards):
    s = build(cards, ["Scion of Draco", "Soul Warden", "Merfolk Looter", "Young Pyromancer", "Grizzly Bears"])
    put(s, "Scion of Draco")
    for name in ("Soul Warden", "Merfolk Looter", "Young Pyromancer", "Grizzly Bears"):
        put(s, name)
    assert "vigilance" in keywords(s, "Soul Warden") and "hexproof" not in keywords(s, "Soul Warden")
    assert "hexproof" in keywords(s, "Merfolk Looter") and "first strike" in keywords(s, "Young Pyromancer") and "trample" in keywords(s, "Grizzly Bears")
    assert "trample" not in keywords(s, "Soul Warden")
    check(s)
    assert "trample" in keywords(reloaded(s), "Grizzly Bears")


def test_mind_into_matter_puts_a_permanent_with_mana_value_x_or_less_from_your_hand(cards):
    s = build(cards, ["Mind into Matter", "Grizzly Bears", "Twisted Abomination"], forests=30)
    empty_hand(s)
    bears, abomination = to_hand(s, "Grizzly Bears"), to_hand(s, "Twisted Abomination")
    mana(s, "p1", G=3, U=1)  # {X}{G}{U} with X = 2
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Mind into Matter").id, x_value=2)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and (d.resume or {}).get("step") == "put_from_hand":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    ids = {o.id for o in d.options}
    assert bears.id in ids and abomination.id not in ids  # mana value 2 fits X = 2, mana value 6 does not
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[bears.id])
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield" and zone_of(s, "Twisted Abomination") == "p1:hand" and s.state.cards[bears.id].tapped
    check(s)
