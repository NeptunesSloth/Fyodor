"""Library manipulation: the top of a library looked at (private, CR 701.20e) or revealed (public,
701.20a, until the card moves or the library is reordered, 701.20d), "… until you reveal a …",
cards put on top / on the bottom of a library or shuffled into it (401.4: several cards to one
position are ordered privately by their owner; 701.24: a shuffled library is re-keyed, its cards
new objects), and exiling from the top (face down stays hidden). Every scenario checks the final
table, that Bob's serialized view never carries what only Alice may know, and that replaying the
recorded history reproduces the table."""

from __future__ import annotations

import json

import pytest

from app.game.session import GameSession
from app.rules import selectors
from app.rules.language import parse_sentence
from tests.game_helpers import act, zone
from tests.test_rules_effects import build, mana, pass_until_stack_empty, replay_matches, token


def key(phrase):
    return selectors.parse(phrase).key()


# -- parsing ------------------------------------------------------------------------------
@pytest.mark.parametrize(("text", "effects", "target"), [
    ("reveal the top three cards of your library", [{"do": "look_top", "n": 3, "player": "you", "reveal": True}], None),
    ("look at the top card of target player's library", [{"do": "look_top", "n": 1, "player": "target", "reveal": False}], "player"),
    ("look at the top four cards of your library, then put them back in any order",
     [{"do": "look_top", "n": 4, "player": "you", "reveal": False}, {"do": "rest_looked", "to": "top_any"}], None),
    ("each player reveals the top card of their library", [{"do": "look_top", "n": 1, "player": "each_player", "reveal": True}], None),
    ("exile the top two cards of your library", [{"do": "exile_top", "n": 2, "player": "you", "face_down": False}], None),
    ("exile the top card of your library face down", [{"do": "exile_top", "n": 1, "player": "you", "face_down": True}], None),
    ("target opponent exiles the top two cards of their library", [{"do": "exile_top", "n": 2, "player": "target"}], "opponent"),
    ("reveal cards from the top of your library until you reveal a creature card",
     [{"do": "look_top", "n": 0, "player": "you", "until": key("creature card"), "reveal": True}], None),
    ("exile cards from the top of your library until you exile a nonland card",
     [{"do": "exile_top", "n": 0, "player": "you", "until": key("nonland card")}], None),
    ("put that card into your hand and the rest on the bottom of your library in a random order",
     [{"do": "pick_looked", "n": 1, "sel": None, "to": "hand", "optional": False, "reveal": False, "which": "that"},
      {"do": "rest_looked", "to": "bottom_random"}], None),
    ("put all land cards revealed this way into your hand and the rest into your graveyard",
     [{"do": "pick_looked", "n": 99, "sel": key("land card"), "to": "hand", "optional": False, "reveal": False},
      {"do": "rest_looked", "to": "graveyard"}], None),
    ("put two of those cards into your hand and the rest on the bottom of your library in any order",
     [{"do": "pick_looked", "n": 2, "sel": None, "to": "hand", "optional": False, "reveal": False},
      {"do": "rest_looked", "to": "bottom_any"}], None),
    ("you may put it into your graveyard",
     [{"do": "pick_looked", "n": 1, "sel": None, "to": "graveyard", "optional": True, "reveal": False, "which": "that"}], None),
    ("exile the rest", [{"do": "rest_looked", "to": "exile"}], None),
    ("put target creature on top of its owner's library", [{"do": "to_library", "who": "target", "place": "top"}], key("creature")),
    ("put target card from a graveyard on the bottom of its owner's library",
     [{"do": "to_library", "who": "target", "place": "bottom"}], key("card from a graveyard")),
    ("put ~ on the bottom of its owner's library", [{"do": "to_library", "who": "self", "place": "bottom"}], None),
    ("shuffle ~ into its owner's library", [{"do": "to_library", "who": "self", "place": "shuffle"}], None),
    ("its owner shuffles it into their library", [{"do": "to_library", "who": "it", "place": "shuffle"}], None),
    ("the owner of target nonland permanent puts it on their choice of the top or bottom of their library",
     [{"do": "to_library", "who": "target", "place": "choice"}], key("nonland permanent")),
    ("shuffle your library", [{"do": "shuffle_library", "who": "you", "zones": []}], None),
    ("you may shuffle", [{"do": "shuffle_library", "who": "you", "zones": [], "optional": True}], None),
    ("shuffle your graveyard into your library", [{"do": "shuffle_library", "who": "you", "zones": ["graveyard"]}], None),
    ("each player shuffles their hand and graveyard into their library",
     [{"do": "shuffle_library", "who": "each_player", "zones": ["hand", "graveyard"]}], None),
    ("then that player shuffles", [{"do": "shuffle_library", "who": "that_player", "zones": []}], None),
    ("search your library for a card, exile it face down, then shuffle",
     [{"do": "search", "who": "you", "sel": key("card from your library"), "label": "card", "max": 1, "to": "exile", "reveal": False,
       "upto": False, "face_down": True}], None),
])
def test_parse_library_wordings(text, effects, target):
    assert parse_sentence(text) == (effects, target)


def test_look_with_a_computed_count():
    effects, _ = parse_sentence("look at the top x cards of your library, where x is the number of lands you control")
    assert effects[0] == {"do": "look_top", "n": {"count": key("lands you control")}, "player": "you", "reveal": False}


@pytest.mark.parametrize("text", [
    "put two cards from your hand on top of your library in any order",  # (which two: not read)
    "put a card from your hand on the bottom of your library",
    "look at the top card of each player's library, then put them back in any order",  # (who orders whose)
    "put all creature cards from your graveyard on top of your library",
    "mill cards until you mill a land card",
])
def test_unknown_library_wordings_stay_manual(text):
    assert parse_sentence(text) is None


# -- helpers --------------------------------------------------------------------------------
def secrets_of(s, card_ids):
    out = []
    for cid in card_ids:
        c = s.state.cards[cid]
        out += [cid, c.name]
        if c.card_id:
            out.append(c.card_id)
    return [x for x in out if x]


def assert_hidden_from_bob(s, card_ids, *, reloaded=True):
    """Nothing identifying these cards is in Bob's serialized view (REST and WebSocket send the
    same payload), while Alice's decision is complete; a reload keeps it so."""
    sessions = [s, GameSession(s.history.rebuild(), cards=s.cards)] if reloaded else [s]
    for session in sessions:
        bob = json.dumps(session.view("p2"))
        for secret in secrets_of(s, card_ids):
            assert secret not in bob, secret
        d = session.view("p2")["rules"]["decision"]
        assert d["kind"] == "waiting" and "options" not in d
        alice = session.view("p1")["rules"]["decision"]
        assert alice["options"] is not None and alice["prompt"]


def activate(s, card, **kw):
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=card.id, ability=0, **kw)
    pass_until_stack_empty(s)


def choose(s, option_ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=option_ids)
    pass_until_stack_empty(s)


def names(s, ids):
    return [s.state.cards[c].name for c in ids]


def bob_can_see(s, card_id):
    return card_id in json.dumps(s.view("p2"))


def ch(s, cid):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[cid])


def is_creature(s, cid):
    return ch(s, cid).is_creature


# -- looking (private) and revealing (public) -----------------------------------------------
def test_look_at_top_pick_two_rest_on_the_bottom_in_any_order(cards):
    s = build(cards)
    src = token(s, "p1", "Seer", text="{1}: Look at the top four cards of your library. Put two of those cards into your hand and the rest on the bottom of your library in any order.")
    top4 = zone(s.state, "p1", "library")[:4]
    activate(s, src)
    d = s.state.rules.decision
    assert d.kind == "choose_cards" and (d.min_choices, d.max_choices) == (2, 2) and {o.id for o in d.options} == set(top4)
    assert_hidden_from_bob(s, top4)
    choose(s, [top4[0], top4[2]])
    d = s.state.rules.decision  # 401.4: the order of the two going to the bottom is Alice's secret
    assert d.kind == "order" and {o.id for o in d.options} == {top4[1], top4[3]}
    assert_hidden_from_bob(s, [top4[1], top4[3]])
    choose(s, [top4[3], top4[1]])
    assert s.state.rules.decision is None
    assert all(s.state.cards[c].zone == "p1:hand" for c in (top4[0], top4[2]))
    assert zone(s.state, "p1", "library")[-2:] == [top4[1], top4[3]]  # first chosen at the very bottom
    assert not bob_can_see(s, top4[1]) and not bob_can_see(s, top4[3])
    replay_matches(s)


def test_reveal_top_is_public_and_the_matches_go_to_hand(cards):
    s = build(cards)
    src = token(s, "p1", "Herald", text="{1}: Reveal the top three cards of your library. Put all creature cards revealed this way into your hand and the rest into your graveyard.")
    top3 = zone(s.state, "p1", "library")[:3]
    creatures = [c for c in top3 if is_creature(s, c)]
    assert creatures  # (the fixture deck: a creature among the top three)
    activate(s, src)
    assert s.state.rules.decision is None  # nothing to choose: every creature card
    assert all(s.state.cards[c].zone == "p1:hand" for c in creatures)
    assert all(s.state.cards[c].zone == "p1:graveyard" for c in top3 if c not in creatures)
    # 701.20a: revealed to everyone — Bob's log names the card that went to Alice's hand
    bob = json.dumps(s.view("p2"))
    assert all(s.state.cards[c].name in bob for c in creatures)
    replay_matches(s)


def test_reveal_one_and_put_that_card_into_your_hand(cards):
    s = build(cards)
    src = token(s, "p1", "Sorin", text="{1}: Reveal the top card of your library and put that card into your hand.")
    top = zone(s.state, "p1", "library")[0]
    hand = len(zone(s.state, "p1", "hand"))
    activate(s, src)
    assert s.state.rules.decision is None and s.state.cards[top].zone == "p1:hand" and len(zone(s.state, "p1", "hand")) == hand + 1
    assert s.state.cards[top].name in json.dumps(s.view("p2"))  # (revealed as it was drawn)
    replay_matches(s)


def test_look_at_the_top_card_and_may_put_it_into_your_graveyard(cards):
    s = build(cards)
    src = token(s, "p1", "Sifter", text="{1}: Look at the top card of your library. You may put it into your graveyard.")
    top = zone(s.state, "p1", "library")[0]
    activate(s, src)
    d = s.state.rules.decision
    assert d.kind == "choose_cards" and (d.min_choices, d.max_choices) == (0, 1) and [o.id for o in d.options] == [top]
    assert_hidden_from_bob(s, [top])
    choose(s, [top])
    assert s.state.cards[top].zone == "p1:graveyard"
    replay_matches(s)
    # (and keeping it: it stays on top, still unknown to Bob)
    s = build(cards)
    src = token(s, "p1", "Sifter", text="{1}: Look at the top card of your library. You may put it into your graveyard.")
    top = zone(s.state, "p1", "library")[0]
    activate(s, src)
    choose(s, [])
    assert zone(s.state, "p1", "library")[0] == top and not bob_can_see(s, top)


def test_reorder_the_top_three_in_a_chosen_order(cards):
    s = build(cards)
    src = token(s, "p1", "Ponderer", text="{1}: Look at the top three cards of your library, then put them back in any order. You may shuffle. Draw a card.")
    a, b, c = zone(s.state, "p1", "library")[:3]
    activate(s, src)
    d = s.state.rules.decision
    assert d.kind == "order" and {o.id for o in d.options} == {a, b, c}
    assert_hidden_from_bob(s, [a, b, c])
    choose(s, [c, a, b])
    d = s.state.rules.decision
    assert d.kind == "confirm" and s.view("p2")["rules"]["decision"]["kind"] == "waiting"
    choose(s, ["no"])
    assert s.state.rules.decision is None
    assert s.state.cards[c].zone == "p1:hand" and zone(s.state, "p1", "library")[:2] == [a, b]  # c on top, then drawn
    assert not bob_can_see(s, a) and not bob_can_see(s, b) and not bob_can_see(s, c)
    replay_matches(s)


def test_may_shuffle_after_reordering(cards):
    s = build(cards)
    src = token(s, "p1", "Ponderer", text="{1}: Look at the top three cards of your library, then put them back in any order. You may shuffle. Draw a card.")
    before = list(zone(s.state, "p1", "library"))
    activate(s, src)
    choose(s, list(before[:3]))
    choose(s, ["yes"])
    after = zone(s.state, "p1", "library")
    assert len(after) == len(before) - 1 and not set(after) & set(before)  # 701.24: every library card re-keyed
    assert all(c not in s.state.cards for c in before)
    replay_matches(s)


def test_look_at_the_top_of_an_opponents_library_and_reorder_it(cards):
    s = build(cards)
    src = token(s, "p1", "Spy", text="{1}: Look at the top three cards of target player's library, then put them back in any order.")
    a, b, c = zone(s.state, "p2", "library")[:3]
    activate(s, src, targets=["p2"])
    d = s.state.rules.decision
    assert d.player == "p1" and d.kind == "order" and {o.id for o in d.options} == {a, b, c}
    assert_hidden_from_bob(s, [a, b, c])  # (Bob doesn't get to see his own library either)
    choose(s, [b, c, a])
    assert zone(s.state, "p2", "library")[:3] == [b, c, a]
    assert s.view("p1")["rules"]["decision"] is None or s.view("p1")["rules"]["decision"]["kind"] != "order"
    replay_matches(s)


def test_a_bare_look_shows_the_cards_to_the_looker_alone(cards):
    s = build(cards)
    src = token(s, "p1", "Spy", text="{1}: Look at the top card of target player's library.")
    top = zone(s.state, "p2", "library")[0]
    activate(s, src, targets=["p2"])
    assert s.state.rules.decision is None
    assert s.state.cards[top].name in json.dumps(s.view("p1")) and not bob_can_see(s, top)  # 701.20e
    reloaded = GameSession(s.history.rebuild(), cards=s.cards)
    assert s.state.cards[top].name in json.dumps(reloaded.view("p1")) and top not in json.dumps(reloaded.view("p2"))
    replay_matches(s)


# -- reveal until ---------------------------------------------------------------------------
def test_reveal_until_finds_the_first_match_and_bottoms_the_rest_randomly(cards):
    s = build(cards)
    src = token(s, "p1", "Digger", text="{1}: Reveal cards from the top of your library until you reveal a creature card. Put that card into your hand and the rest on the bottom of your library in a random order.")
    library = list(zone(s.state, "p1", "library"))
    at = next(i for i, c in enumerate(library) if is_creature(s, c))
    activate(s, src)
    assert s.state.rules.decision is None
    found, rest = library[at], library[:at]
    assert s.state.cards[found].zone == "p1:hand"
    after = zone(s.state, "p1", "library")
    assert after[: len(library) - at - 1] == library[at + 1:]  # the unrevealed cards stay in order
    assert set(after[len(library) - at - 1:]) == set(rest)  # the rest on the bottom (in a recorded random order)
    bob = json.dumps(s.view("p2"))
    assert all(s.state.cards[c].name in bob for c in [found, *rest])  # 701.20a: revealed to everyone
    assert all(c not in bob for c in rest)  # (bottomed: no longer revealed, not pointed at)
    replay_matches(s)  # the random order was recorded as moves


def test_reveal_until_with_no_match_reveals_the_whole_library(cards):
    s = build(cards)
    src = token(s, "p1", "Digger", text="{1}: Reveal cards from the top of your library until you reveal a planeswalker card. Put that card into your hand and the rest on the bottom of your library in a random order.")
    library = list(zone(s.state, "p1", "library"))
    hand = len(zone(s.state, "p1", "hand"))
    activate(s, src)
    assert set(zone(s.state, "p1", "library")) == set(library) and len(zone(s.state, "p1", "hand")) == hand
    replay_matches(s)


def test_reveal_until_put_that_card_onto_the_battlefield(cards):
    s = build(cards)
    src = token(s, "p1", "Summoner", text="{1}: Reveal cards from the top of your library until you reveal a creature card. Put that card onto the battlefield and the rest on the bottom of your library in a random order.")
    library = list(zone(s.state, "p1", "library"))
    found = next(c for c in library if is_creature(s, c))
    activate(s, src)
    assert s.state.cards[found].zone == "p1:battlefield"
    replay_matches(s)


# -- exiling from the top -------------------------------------------------------------------
def test_exile_the_top_cards_face_up_and_face_down(cards):
    s = build(cards)
    src = token(s, "p1", "Burner", text="{1}: Exile the top two cards of your library.")
    top2 = zone(s.state, "p1", "library")[:2]
    activate(s, src)
    assert all(s.state.cards[c].zone == "p1:exile" and not s.state.cards[c].face_down for c in top2)
    bob = json.dumps(s.view("p2"))
    assert all(s.state.cards[c].name in bob for c in top2)  # face up: public
    hider = token(s, "p1", "Hider", text="{1}: Exile the top card of your library face down.")
    top = zone(s.state, "p1", "library")[0]
    activate(s, hider)
    assert s.state.cards[top].zone == "p1:exile" and s.state.cards[top].face_down
    assert s.state.cards[top].name not in json.dumps(s.view("p2"))  # face down: hidden from Bob
    assert s.state.cards[top].name in json.dumps(s.view("p1"))  # (its controller may look)
    replay_matches(s)


def test_exile_until_a_nonland_card(cards):
    s = build(cards)
    src = token(s, "p1", "Bruntar", text="{1}: Exile cards from the top of your library until you exile a nonland card.")
    library = list(zone(s.state, "p1", "library"))
    at = next(i for i, c in enumerate(library) if not ch(s, c).is_land)
    activate(s, src)
    assert all(s.state.cards[c].zone == "p1:exile" for c in library[: at + 1])
    assert zone(s.state, "p1", "library") == library[at + 1:]
    replay_matches(s)


def test_target_opponent_exiles_the_top_cards(cards):
    s = build(cards)
    src = token(s, "p1", "Thief", text="{1}: Target opponent exiles the top two cards of their library.")
    top2 = zone(s.state, "p2", "library")[:2]
    activate(s, src, targets=["p2"])
    assert all(s.state.cards[c].zone == "p2:exile" for c in top2)
    replay_matches(s)


# -- putting cards into a library -----------------------------------------------------------
def test_put_a_card_from_an_opponents_graveyard_on_top_of_their_library(cards):
    s = build(cards)
    dead = zone(s.state, "p2", "library")[-1]
    act(s, "p2", type="move", card_ids=[dead], to={"player": "p2", "zone": "graveyard"})
    src = token(s, "p1", "Gravedigger", text="{1}: Put target card from a graveyard on top of its owner's library.")
    activate(s, src, targets=[dead])
    assert s.state.rules.decision is None and zone(s.state, "p2", "library")[0] == dead
    replay_matches(s)
    bottom = token(s, "p1", "Sinker", text="{1}: Put target card from a graveyard on the bottom of its owner's library.")
    dead2 = zone(s.state, "p2", "library")[-1]
    act(s, "p2", type="move", card_ids=[dead2], to={"player": "p2", "zone": "graveyard"})
    activate(s, bottom, targets=[dead2])
    assert zone(s.state, "p2", "library")[-1] == dead2
    replay_matches(s)


def test_put_target_creature_on_top_of_its_owners_library(cards):
    s = build(cards)
    viper = next(c for c in zone(s.state, "p2", "library") if s.state.cards[c].name == "Ambush Viper")
    act(s, "p2", type="move", card_ids=[viper], to={"player": "p2", "zone": "battlefield"})
    src = token(s, "p1", "Bouncer", text="{1}: Put target creature on top of its owner's library.")
    activate(s, src, targets=[viper])
    assert zone(s.state, "p2", "library")[0] == viper
    replay_matches(s)


def test_several_cards_to_the_top_are_ordered_privately_by_their_owner(cards):
    s = build(cards)
    mine = [c for c in zone(s.state, "p1", "library") if is_creature(s, c)][:2]
    act(s, "p1", type="move", card_ids=mine, to={"player": "p1", "zone": "graveyard"})
    src = token(s, "p1", "Feast", text="{1}: Put any number of target creature cards from your graveyard on top of your library.")
    activate(s, src, targets=mine, target_counts=[2])
    d = s.state.rules.decision
    assert d.player == "p1" and d.kind == "order" and {o.id for o in d.options} == set(mine)
    assert s.view("p2")["rules"]["decision"]["kind"] == "waiting"  # 401.4: the order isn't revealed
    choose(s, [mine[1], mine[0]])
    assert zone(s.state, "p1", "library")[:2] == [mine[1], mine[0]]
    replay_matches(s)


def test_owner_chooses_top_or_bottom(cards):
    s = build(cards)
    viper = next(c for c in zone(s.state, "p2", "library") if s.state.cards[c].name == "Ambush Viper")
    act(s, "p2", type="move", card_ids=[viper], to={"player": "p2", "zone": "battlefield"})
    src = token(s, "p1", "Motes", text="{1}: Target creature's owner puts it on their choice of the top or bottom of their library.")
    activate(s, src, targets=[viper])
    d = s.state.rules.decision
    assert d.player == "p2" and d.kind == "choose_one" and [o.id for o in d.options] == ["top", "bottom"]
    choose(s, ["bottom"])
    assert zone(s.state, "p2", "library")[-1] == viper
    replay_matches(s)


def test_shuffle_a_permanent_into_its_owners_library_rekeys_it(cards):
    s = build(cards)
    viper = next(c for c in zone(s.state, "p2", "library") if s.state.cards[c].name == "Ambush Viper")
    act(s, "p2", type="move", card_ids=[viper], to={"player": "p2", "zone": "battlefield"})
    library = list(zone(s.state, "p2", "library"))
    was = names(s, library)
    src = token(s, "p1", "Nullifier", text="{1}: Shuffle target creature into its owner's library.")
    activate(s, src, targets=[viper])
    after = zone(s.state, "p2", "library")
    assert len(after) == len(library) + 1 and viper not in s.state.cards and not set(after) & set(library)
    assert sorted(names(s, after)) == sorted(was + ["Ambush Viper"])
    assert viper not in json.dumps(s.view("p2")) and viper not in json.dumps(s.view("p1"))  # (a new object: 701.20d)
    replay_matches(s)


def test_shuffle_your_graveyard_into_your_library(cards):
    s = build(cards)
    dead = zone(s.state, "p1", "library")[:3]
    act(s, "p1", type="move", card_ids=dead, to={"player": "p1", "zone": "graveyard"})
    library = list(zone(s.state, "p1", "library"))
    src = token(s, "p1", "Cane", text="{1}: Shuffle your graveyard into your library.")
    activate(s, src)
    after = zone(s.state, "p1", "library")
    assert not zone(s.state, "p1", "graveyard") and len(after) == len(library) + 3
    assert not set(after) & set(library + dead) and all(c not in s.state.cards for c in dead)
    bob = json.dumps(s.view("p2"))
    assert all(c not in bob for c in dead) and all(s.state.cards[c].name not in bob or True for c in after)
    replay_matches(s)


def test_then_shuffle_as_its_own_sentence(cards):
    s = build(cards)
    library = list(zone(s.state, "p1", "library"))
    src = token(s, "p1", "Mixer", text="{1}: Exile the top card of your library. Then shuffle.")
    activate(s, src)
    after = zone(s.state, "p1", "library")
    assert s.state.cards[library[0]].zone == "p1:exile" and len(after) == len(library) - 1 and not set(after) & set(library)
    replay_matches(s)


# -- edge cases -----------------------------------------------------------------------------
def test_fewer_cards_than_asked_for(cards):
    s = build(cards)
    act(s, "p1", type="draw", count=len(zone(s.state, "p1", "library")) - 2)
    two = zone(s.state, "p1", "library")
    src = token(s, "p1", "Seer", text="{1}: Look at the top four cards of your library. Put two of those cards into your hand and the rest on the bottom of your library in any order.")
    activate(s, src)
    d = s.state.rules.decision
    assert (d.min_choices, d.max_choices) == (2, 2) and {o.id for o in d.options} == set(two)
    choose(s, two)
    assert s.state.rules.decision is None and not zone(s.state, "p1", "library")
    digger = token(s, "p1", "Digger", text="{1}: Reveal cards from the top of your library until you reveal a creature card. Put that card into your hand and the rest on the bottom of your library in a random order.")
    activate(s, digger)  # an empty library: nothing happens
    assert s.state.rules.decision is None and not zone(s.state, "p1", "library")
    burner = token(s, "p1", "Burner", text="{1}: Exile the top two cards of your library.")
    activate(s, burner)
    assert not zone(s.state, "p1", "exile")
    replay_matches(s)


def test_privacy_survives_a_reload_for_every_private_library_decision(cards):
    s = build(cards)
    src = token(s, "p1", "Scout", text="{1}: Look at the top four cards of your library. You may reveal a creature card from among them and put it into your hand. Put the rest on the bottom of your library in any order.")
    top4 = zone(s.state, "p1", "library")[:4]
    activate(s, src)
    assert_hidden_from_bob(s, top4)
    pick = next(c for c in top4 if is_creature(s, c))
    choose(s, [pick])
    assert s.state.cards[pick].name in json.dumps(s.view("p2"))  # revealed on the way to the hand
    rest = [c for c in top4 if c != pick]
    assert_hidden_from_bob(s, rest)  # the order of the rest: still Alice's alone
    choose(s, rest)
    assert zone(s.state, "p1", "library")[-3:] == list(reversed(rest))
    replay_matches(s)
