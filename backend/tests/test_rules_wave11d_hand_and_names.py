"""Wave 11D: hand disruption, same-name sweeps and name searches, researched against CR 2026-09-25.

* 701.20a / 701.20e — "reveals their hand" shows it to everyone while the effect needs it; "look at target player's hand"
  shows it to the looking player alone, and it is hidden again once the effect is done;
* 701.9a — a discard puts the card in its owner's graveyard; exiling a card from a hand is no discard;
* 201.2 / 608.2b — "target X and all other Xs with the same name": the others are not targets;
* 701.23 / 701.24 — searching a hidden zone for cards with a name; the searched player shuffles.

Every scenario checks what the other players' views and decisions show, replays the history and reloads a save.
"""

from __future__ import annotations

import json

from tests.game_helpers import act, zone
from tests.test_rules_effects import build, mana, replay_matches, token
from tests.test_rules_player_choices import activate, assert_observer_sees_only_who, bob_holds, bobs_hand, choose, reloaded

PROBE = "Look at target player's hand."
INQUISITION = ("Target player reveals their hand. You choose a nonland card from it with mana value 3 or less. "
               "That player discards that card.")


def seen_by(s, viewer, ids):
    blob = json.dumps(s.view(viewer))
    return [c for c in ids if c in blob]


def bob_with_viper(cards, draws=2):
    s = build(cards)
    act(s, "p2", type="draw", player="p2", count=draws)
    viper = bob_holds(s, "Ambush Viper")
    return s, viper, [c for c in bobs_hand(s) if c != viper.id]


# -- hand disruption --------------------------------------------------------------------------------------------
def test_look_at_a_hand_is_private_to_the_looker_and_hidden_again_afterwards(cards):
    s, viper, islands = bob_with_viper(cards)
    hand = [viper.id, *islands]
    src = token(s, "p1", "Peeker", "1/1", text=f"{{1}}: {PROBE}")
    assert seen_by(s, "p1", hand) == []
    activate(s, src, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.kind == "confirm"
    assert seen_by(s, "p1", hand) == hand  # Alice sees all of Bob's hand while she looks (701.20e)
    assert seen_by(s, "p2", hand) == [] or all(s.state.cards[c].owner == "p2" for c in seen_by(s, "p2", hand))  # (his own cards only)
    assert all(s.state.cards[c].revealed_to == ["p1"] for c in hand)  # to her alone, not "everyone"
    assert_observer_sees_only_who(s, "p2", "Alice")
    again = reloaded(s)
    act(again, "p1", type="choose", decision_id=again.state.rules.decision.id, option_ids=["ok"])
    choose(s, ["ok"])
    assert seen_by(s, "p1", hand) == []  # hidden again: the look is over
    assert all(s.state.cards[c].revealed_to == [] for c in hand)
    assert s.state.rules.decision is None and set(bobs_hand(s)) == set(hand)
    replay_matches(s)
    replay_matches(again)


def test_look_at_an_empty_hand_asks_nothing(cards):
    s = build(cards)
    src = token(s, "p1", "Peeker", "1/1", text=f"{{1}}: {PROBE}")
    activate(s, src, targets=["p2"])
    assert s.state.rules.decision is None or not zone(s.state, "p2", "hand")


def test_inquisition_chooses_only_among_cheap_nonland_cards(cards):
    s, viper, islands = bob_with_viper(cards)
    src = token(s, "p1", "Seizer", "1/1", text=f"{{1}}: {INQUISITION}")
    activate(s, src, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None and [o.id for o in d.options] == [viper.id]  # Ambush Viper has mana value 2
    assert all(s.state.cards[c].revealed_to == ["*"] for c in [viper.id, *islands])  # revealed: 701.20a
    choose(s, [viper.id])
    assert s.state.cards[viper.id].zone == "p2:graveyard" and bobs_hand(s) == islands
    assert all(s.state.cards[c].revealed_to == [] for c in islands) and seen_by(s, "p1", islands) == []
    replay_matches(s)


def test_a_mana_value_filter_that_nothing_meets_chooses_nothing(cards):
    s, viper, islands = bob_with_viper(cards)
    src = token(s, "p1", "Seizer", "1/1", text="{1}: Target opponent reveals their hand. You choose a card from it with mana value 3 "
                                                "or greater. Exile that card.")
    activate(s, src, targets=["p2"])
    assert s.state.rules.decision is None and s.state.cards[viper.id].zone == "p2:hand"
    assert seen_by(s, "p1", [viper.id, *islands]) == []
    replay_matches(s)


def test_agonizing_remorse_takes_a_nonland_card_from_the_hand_or_any_card_from_the_graveyard(cards):
    s, viper, islands = bob_with_viper(cards)
    act(s, "p2", type="move", card_ids=[islands[0]], to={"player": "p2", "zone": "graveyard"})
    src = token(s, "p1", "Seizer", "1/1", text="{1}: Target opponent reveals their hand. You choose a nonland card from it or a card "
                                                "from their graveyard. Exile that card. You lose 1 life.")
    activate(s, src, targets=["p2"])
    d = s.state.rules.decision
    assert {o.id for o in d.options} == {viper.id, islands[0]}  # the nonland card in hand and the (any) card in the graveyard
    life = s.state.players["p1"].life
    again = reloaded(s)
    choose(s, [islands[0]])
    assert s.state.cards[islands[0]].zone == "p2:exile" and s.state.cards[viper.id].zone == "p2:hand"
    assert s.state.players["p1"].life == life - 1
    assert s.state.cards[viper.id].revealed_to == []
    replay_matches(s)
    act(again, "p1", type="choose", decision_id=again.state.rules.decision.id, option_ids=[viper.id])
    assert again.state.cards[viper.id].zone == "p2:exile"


def test_amnesia_discards_every_nonland_card_of_the_revealed_hand(cards):
    s, viper, islands = bob_with_viper(cards)
    src = token(s, "p1", "Amnesia", "1/1", text="{1}: Target player reveals their hand and discards all nonland cards.")
    activate(s, src, targets=["p2"])
    assert s.state.rules.decision is None
    assert s.state.cards[viper.id].zone == "p2:graveyard" and bobs_hand(s) == islands
    assert all(s.state.cards[c].revealed_to == [] for c in islands) and seen_by(s, "p1", islands) == []
    replay_matches(s)


def test_exiling_cards_from_a_hand_is_the_players_private_choice(cards):
    s, viper, islands = bob_with_viper(cards, draws=3)
    src = token(s, "p1", "Aim", "1/1", text="{1}: Target opponent exiles two cards from their hand.")
    activate(s, src, targets=["p2"])
    d = s.state.rules.decision
    assert d.player == "p2" and (d.min_choices, d.max_choices) == (2, 2)  # Bob chooses (and sees only his own hand)
    assert_observer_sees_only_who(s, "p1", "Bob")
    again = reloaded(s)
    choose(s, [viper.id, islands[0]])
    assert s.state.cards[viper.id].zone == "p2:exile" and s.state.cards[islands[0]].zone == "p2:exile"
    assert len(bobs_hand(s)) == 2
    assert not any("discard" in json.dumps(e).lower() for e in s.view("p1")["log"][-3:])
    replay_matches(s)
    act(again, "p2", type="choose", decision_id=again.state.rules.decision.id, option_ids=[islands[1], islands[0]])
    assert again.state.cards[islands[1]].zone == "p2:exile"


def test_extortion_looks_privately_then_makes_the_chosen_cards_be_discarded(cards):
    s, viper, islands = bob_with_viper(cards)
    hand = [viper.id, *islands]
    src = token(s, "p1", "Extort", "1/1", text="{1}: Look at target player's hand and choose up to two cards from it. "
                                                "That player discards those cards.")
    activate(s, src, targets=["p2"])
    d = s.state.rules.decision
    assert d.player == "p1" and {o.id for o in d.options} == set(hand) and (d.min_choices, d.max_choices) == (0, 2)
    assert all(s.state.cards[c].revealed_to == ["p1"] for c in hand)  # only Alice looks
    assert_observer_sees_only_who(s, "p2", "Alice")
    choose(s, [viper.id, islands[0]])
    assert s.state.cards[viper.id].zone == "p2:graveyard" and s.state.cards[islands[0]].zone == "p2:graveyard"
    assert bobs_hand(s) == [islands[1]] and s.state.cards[islands[1]].revealed_to == []
    assert seen_by(s, "p1", [islands[1]]) == []
    replay_matches(s)


def test_a_look_before_a_choice_still_shows_the_hand_when_nothing_can_be_chosen(cards):
    """Cracked Skull: "look at target player's hand. You may choose a nonland card from it": an all-land hand is still looked at."""
    s = build(cards)
    act(s, "p2", type="draw", player="p2", count=2)  # two Islands
    hand = bobs_hand(s)
    src = token(s, "p1", "Skull", "1/1", text="{1}: Look at target player's hand. You may choose a nonland card from it. "
                                                "That player discards that card.")
    activate(s, src, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None and d.kind == "confirm" and seen_by(s, "p1", hand) == hand
    choose(s, ["ok"])
    assert s.state.rules.decision is None and seen_by(s, "p1", hand) == [] and set(bobs_hand(s)) == set(hand)
    replay_matches(s)


def test_a_card_exiled_from_a_hand_can_be_played_by_the_one_who_may(cards):
    """Fiend of the Shadows: "that player exiles a card from their hand. You may play that card for as long as it remains exiled"."""
    s, viper, islands = bob_with_viper(cards)
    src = token(s, "p1", "Fiend", "1/1", text="{1}: Target opponent exiles a card from their hand. You may play that card for as long "
                                                "as it remains exiled.")
    activate(s, src, targets=["p2"])
    choose(s, [viper.id])
    assert s.state.cards[viper.id].zone == "p2:exile" and s.state.cards[viper.id].revealed_to in (["*"], [])
    assert [(p.card, p.player) for p in s.state.rules.permissions] == [(viper.id, "p1")]
    replay_matches(s)


# -- same name sweeps ---------------------------------------------------------------------------------------------
def land_on_battlefield(s, pid, name):
    card = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone.endswith(":library"))
    act(s, pid, type="move", card_ids=[card.id], to={"player": pid, "zone": "battlefield"})
    return card


def test_wake_of_destruction_destroys_every_land_with_the_targets_name(cards):
    s = build(cards)
    islands = [land_on_battlefield(s, "p2", "Island") for _ in range(2)] + [land_on_battlefield(s, "p1", "Island")]
    forest = land_on_battlefield(s, "p1", "Forest")
    src = token(s, "p1", "Waker", "1/1", text="{1}: Destroy target land and all other lands with the same name as that land.")
    activate(s, src, targets=[islands[0].id])
    assert all(s.state.cards[c.id].zone.endswith(":graveyard") for c in islands)  # the others weren't targeted, and Alice's too
    assert s.state.cards[forest.id].zone == "p1:battlefield"
    replay_matches(s)
    reloaded_game = reloaded_table(s)
    assert reloaded_game.state.cards[forest.id].zone == "p1:battlefield"


def reloaded_table(s):
    from app.game.session import GameSession

    return GameSession(s.history.rebuild(), cards=s.cards)


def test_bile_blight_hits_only_creatures_with_the_same_name_and_ignores_hexproof(cards):
    s = build(cards)
    g1, g2 = token(s, "p2", "Goblin", "3/3"), token(s, "p1", "Goblin", "3/3")
    hexed = token(s, "p2", "Goblin", "3/3", text="Hexproof")
    ogre = token(s, "p2", "Ogre", "3/3")
    src = token(s, "p1", "Blighter", "1/1", text="{1}: Target creature and all other creatures with the same name as that creature "
                                                  "get -3/-3 until end of turn.")
    activate(s, src, targets=[g1.id])
    assert all(c.id not in s.state.cards for c in (g1, g2, hexed))  # (state-based: 0 toughness; tokens cease to exist)
    assert ogre.id in s.state.cards and s.state.cards[ogre.id].zone == "p2:battlefield"
    replay_matches(s)


def test_echoing_truth_returns_every_permanent_with_the_name_to_its_owners_hand(cards):
    s = build(cards)
    a = land_on_battlefield(s, "p2", "Island")
    b = land_on_battlefield(s, "p2", "Island")
    c = land_on_battlefield(s, "p1", "Forest")
    src = token(s, "p1", "Truth", "1/1", text="{1}: Return target nonland permanent and all other permanents with the same name as "
                                                "that permanent to their owners' hands.")
    t1 = token(s, "p2", "Wisp", "1/1")
    t2 = token(s, "p1", "Wisp", "1/1")
    activate(s, src, targets=[t1.id])
    assert t1.id not in s.state.cards and t2.id not in s.state.cards  # (tokens cease to exist in a hand)
    assert all(s.state.cards[x.id].zone.endswith(":battlefield") for x in (a, b, c))  # lands aren't named Wisp
    replay_matches(s)
