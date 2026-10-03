"""Look at the top N cards and distribute them (wave 3L), read against CR 401.2 (a library is
hidden, its order too), 401.4 (several cards put into one library position are ordered by their
owner, privately), 701.20 (reveal: shown to everyone; look: only the looker sees), 608.2d (a choice
with no target is made on resolution) and 608.2c ("if you don't" follows what the instruction did).
The cards are real Commander cards, their Oracle text transcribed from the card database. Every
scenario also checks that Bob's serialized view never carries what only Alice may know, that a
reload and a replay of the recorded history reproduce the table exactly."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.language import parse_sentence
from app.rules.scripts import parse_effects
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_delayed import reloaded
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches

REAL = [
    card("Impulse", set_code="tst", number="L1", mana_cost="{1}{U}", cmc=2.0, type_line="Instant",
         oracle_text="Look at the top four cards of your library. Put one of them into your hand and the rest on the bottom "
                     "of your library in any order.", colors=["U"], color_identity=["U"]),
    card("Ancestral Memories", set_code="tst", number="L2", mana_cost="{2}{U}{U}{U}", cmc=5.0, type_line="Sorcery",
         oracle_text="Look at the top seven cards of your library. Put two of them into your hand and the rest into your graveyard.",
         colors=["U"], color_identity=["U"]),
    card("Commune with Nature", set_code="tst", number="L3", mana_cost="{G}", cmc=1.0, type_line="Sorcery",
         oracle_text="Look at the top five cards of your library. You may reveal a creature card from among them and put it into "
                     "your hand. Put the rest on the bottom of your library in any order.", colors=["G"], color_identity=["G"]),
    card("Adventurous Impulse", set_code="tst", number="L4", mana_cost="{G}", cmc=1.0, type_line="Sorcery",
         oracle_text="Look at the top three cards of your library. You may reveal a creature or land card from among them and put "
                     "it into your hand. Put the rest on the bottom of your library in any order.", colors=["G"], color_identity=["G"]),
    card("Satyr Wayfinder", set_code="tst", number="L5", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Satyr",
         oracle_text="When this creature enters, reveal the top four cards of your library. You may put a land card from among "
                     "them into your hand. Put the rest into your graveyard.", power="1", toughness="1", colors=["G"],
         color_identity=["G"]),
    card("Grisly Salvage", set_code="tst", number="L6", mana_cost="{B}{G}", cmc=2.0, type_line="Instant",
         oracle_text="Reveal the top five cards of your library. You may put a creature or land card from among them into your "
                     "hand. Put the rest into your graveyard.", colors=["B", "G"], color_identity=["B", "G"]),
    card("Risen Reef", set_code="tst", number="L7", mana_cost="{1}{G}{U}", cmc=3.0, type_line="Creature — Elemental",
         oracle_text="Whenever this creature or another Elemental you control enters, look at the top card of your library. If it's "
                     "a land card, you may put it onto the battlefield tapped. If you don't put the card onto the battlefield, "
                     "put it into your hand.", power="1", toughness="1", colors=["G", "U"], color_identity=["G", "U"]),
    card("Gathering Stone", set_code="tst", number="L8", mana_cost="{4}", cmc=4.0, type_line="Artifact",
         oracle_text="As this artifact enters, choose a creature type.\nSpells you cast of the chosen type cost {1} less to cast.\n"
                     "When this artifact enters and at the beginning of your upkeep, look at the top card of your library. If it's a "
                     "card of the chosen type, you may reveal it and put it into your hand. If you don't put the card into your "
                     "hand, you may put it into your graveyard."),
    card("Jace, the Mind Sculptor", set_code="tst", number="L9", mana_cost="{2}{U}{U}", cmc=4.0,
         type_line="Legendary Planeswalker — Jace", loyalty="3", colors=["U"], color_identity=["U"],
         oracle_text="+2: Look at the top card of target player's library. You may put that card on the bottom of that player's "
                     "library.\n0: Draw three cards, then put two cards from your hand on top of your library in any order."),
    card("Underrealm Lich", set_code="tst", number="L10", mana_cost="{3}{B}{G}", cmc=5.0, type_line="Creature — Zombie Elf Shaman",
         oracle_text="If you would draw a card, instead look at the top three cards of your library, then put one into your hand "
                     "and the rest into your graveyard.\nPay 4 life: This creature gains indestructible until end of turn. Tap it.",
         power="4", toughness="3", colors=["B", "G"], color_identity=["B", "G"]),
]


@pytest.fixture()
def cards(settings) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


SPELLS = ["Impulse", "Ancestral Memories", "Commune with Nature", "Adventurous Impulse", "Satyr Wayfinder", "Grisly Salvage",
          "Risen Reef", "Gathering Stone"]


def build(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, n) for n in SPELLS] + [(6, "Grizzly Bears"), (1, "Llanowar Elves"), (20, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(2, "Grizzly Bears"), (1, "Llanowar Elves"), (20, "Island")])
    state = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)
    s = GameSession(enable(state), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    return s


def put(s, name, where, pid="p1", nth=0):
    cs = [c for c in s.state.cards.values() if c.name == name and c.owner == pid]
    c = cs[nth]
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": where, "player": pid} if where != "battlefield" else {"zone": where})
    return s.state.cards[c.id]


def stack_library(s, names, pid="p1"):
    """Put these cards on top of the library, in this order (the first on top)."""
    ids = []
    for i, n in reversed(list(enumerate(names))):
        ids.insert(0, put(s, n, "library", pid, nth=sum(1 for m in names[:i] if m == n)).id)
    assert zone(s.state, pid, "library")[: len(names)] == ids
    return ids


def cast(s, name, mana_paid, targets=None, *, in_hand=False):
    c = next(x for x in s.state.cards.values() if x.name == name and x.owner == "p1") if in_hand else put(s, name, "hand")
    mana(s, **mana_paid)
    kw = {"targets": targets} if targets is not None else {}
    act(s, "p1", type="cast_spell", card_id=c.id, **kw)
    pass_until_stack_empty(s)
    return c


def decision(s, kind):
    d = s.state.rules.decision
    assert d is not None and d.kind == kind, d
    return d


def choose(s, ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    pass_until_stack_empty(s)


def secrets_of(s, ids):
    out = []
    for cid in ids:
        c = s.state.cards[cid]
        out += [cid, c.name]
        if c.card_id:
            out.append(c.card_id)
    return [x for x in out if x]


def assert_hidden_from_bob(s, ids):
    """Nothing identifying these cards is in Bob's view while Alice's decision is complete (a reload too)."""
    for session in (s, GameSession(s.history.rebuild(), cards=s.cards)):
        bob = json.dumps(session.view("p2"))
        for secret in secrets_of(s, ids):
            if secret not in ("Grizzly Bears", "Forest", "Llanowar Elves"):  # (a name Bob's own deck shares proves nothing)
                assert secret not in bob, secret
        for cid in ids:
            assert cid not in bob, cid
        d = session.view("p2")["rules"]["decision"]
        assert d["kind"] == "waiting" and "options" not in d
        assert session.view("p1")["rules"]["decision"]["options"] is not None


def assert_sound(s):
    replay_matches(s)
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


def zone_of(s, ids):
    return [s.state.cards[c].zone for c in ids]


# -- grammar (the wordings these cards use) ---------------------------------------------------------
@pytest.mark.parametrize(("text", "effects"), [
    ("put up to one of them on top of your library and the rest on the bottom of your library in a random order",
     [{"do": "pick_looked", "n": 1, "sel": None, "to": "top", "optional": True, "reveal": False},
      {"do": "rest_looked", "to": "bottom_random"}]),
    ("put any number of them into your graveyard and the rest back on top of your library in any order",
     [{"do": "pick_looked", "n": 99, "sel": None, "to": "graveyard", "optional": True, "reveal": False},
      {"do": "rest_looked", "to": "top_any"}]),
    ("you may put that card on the bottom of that player's library",
     [{"do": "pick_looked", "n": 1, "sel": None, "to": "bottom", "optional": True, "reveal": False, "which": "that"}]),
    ("exile one of them face down and put the other on the bottom of that library",
     [{"do": "pick_looked", "n": 1, "sel": None, "to": "exile", "optional": False, "reveal": False, "face_down": True},
      {"do": "rest_looked", "to": "bottom_any"}]),
    ("put one into your hand and the rest into their graveyard",
     [{"do": "pick_looked", "n": 1, "sel": None, "to": "hand", "optional": False, "reveal": False},
      {"do": "rest_looked", "to": "graveyard"}]),
])
def test_parse_distribution_wordings(text, effects):
    assert parse_sentence(text) == (effects, None)


def test_comma_chained_distribution_reads_each_step():
    effects, _ = parse_sentence("look at the top four cards of target opponent's library, exile one of them face down, then put "
                                "the rest on the bottom of that library in a random order")
    assert [e["do"] for e in effects] == ["look_top", "pick_looked", "rest_looked"]
    assert effects[1]["face_down"] is True and effects[2]["to"] == "bottom_random"
    effects, _ = parse_sentence("put one of them into your hand, put one of them on the bottom of your library, and exile one of them")
    assert [(e["do"], e["to"]) for e in effects] == [("pick_looked", "hand"), ("pick_looked", "bottom"), ("pick_looked", "exile")]


def test_if_you_dont_put_the_card_reads_what_the_pick_did():
    effects, _, _ = parse_effects("Look at the top card of your library. If it's a land card, you may put it onto the battlefield "
                                  "tapped. If you don't put the card onto the battlefield, put it into your hand.")
    pick = next(e for e in effects if e["do"] == "pick_looked" and e["to"] == "battlefield_tapped")
    gate = effects[effects.index(pick) + 1]
    assert gate["do"] == "only_if" and gate["cond"] == {"succeeded": pick["did"], "negate": True}


@pytest.mark.parametrize("text", [
    "put one of them on top of your library and the rest on the bottom of your library",  # ("one of them" is fine; two below isn't)
])
def test_single_pick_to_a_library_is_read(text):
    assert parse_sentence(text) is not None


@pytest.mark.parametrize("text", [
    "put two of them on top of your library",  # (their order would be a choice not read)
    "put them on the bottom of your library in any order",
])
def test_several_cards_into_a_library_stay_manual(text):
    assert parse_sentence(text) is None


# -- Impulse: a private pick, a private order --------------------------------------------------------
def test_impulse_picks_one_and_orders_the_rest_privately(cards):
    s = build(cards)
    top = stack_library(s, ["Grizzly Bears", "Forest", "Llanowar Elves", "Forest", "Grizzly Bears"])
    look = top[:4]
    cast(s, "Impulse", {"U": 1, "C": 1})
    d = decision(s, "choose_cards")
    assert (d.min_choices, d.max_choices) == (1, 1) and {o.id for o in d.options} == set(look)
    assert_hidden_from_bob(s, look)
    choose(s, [look[2]])
    d = decision(s, "order")  # 401.4: Alice orders the three, nobody else sees them
    assert {o.id for o in d.options} == {look[0], look[1], look[3]}
    assert_hidden_from_bob(s, [look[0], look[1], look[3]])
    choose(s, [look[3], look[0], look[1]])
    assert s.state.rules.decision is None
    assert s.state.cards[look[2]].zone == "p1:hand"
    assert zone(s.state, "p1", "library")[-3:] == [look[1], look[0], look[3]]  # (the first chosen at the very bottom)
    assert zone(s.state, "p1", "library")[0] == top[4]  # the card below the four is now on top
    assert_sound(s)


def test_impulse_with_fewer_cards_than_the_number_looked_at(cards):
    s = build(cards)
    put(s, "Impulse", "hand")
    for cid in zone(s.state, "p1", "library")[2:]:  # leave two cards
        act(s, "p1", type="move", card_ids=[cid], to={"zone": "exile"})
    two = list(zone(s.state, "p1", "library"))
    assert len(two) == 2
    cast(s, "Impulse", {"U": 1, "C": 1}, in_hand=True)
    d = decision(s, "choose_cards")
    assert {o.id for o in d.options} == set(two)  # only the two that are there
    assert (d.min_choices, d.max_choices) == (1, 1)
    choose(s, [two[1]])
    assert s.state.rules.decision is None  # one card left: nothing to order
    assert s.state.cards[two[1]].zone == "p1:hand" and zone(s.state, "p1", "library") == [two[0]]
    assert_sound(s)


def test_looking_at_an_empty_library_does_nothing(cards):
    s = build(cards)
    put(s, "Impulse", "hand")
    for cid in list(zone(s.state, "p1", "library")):
        act(s, "p1", type="move", card_ids=[cid], to={"zone": "exile"})
    cast(s, "Impulse", {"U": 1, "C": 1}, in_hand=True)
    assert s.state.rules.decision is None and not zone(s.state, "p1", "library")
    assert_sound(s)


# -- Ancestral Memories: two to hand, the rest to the (public) graveyard -------------------------------------
def test_ancestral_memories_two_to_hand_rest_to_graveyard(cards):
    s = build(cards)
    top = stack_library(s, ["Forest", "Grizzly Bears", "Forest", "Llanowar Elves", "Forest", "Grizzly Bears", "Forest", "Forest"])
    look = top[:7]
    cast(s, "Ancestral Memories", {"U": 3, "C": 2})
    d = decision(s, "choose_cards")
    assert (d.min_choices, d.max_choices) == (2, 2) and {o.id for o in d.options} == set(look)
    assert_hidden_from_bob(s, look)
    choose(s, [look[1], look[3]])
    assert s.state.rules.decision is None  # (no order: a graveyard is public and unordered here)
    assert zone_of(s, [look[1], look[3]]) == ["p1:hand", "p1:hand"]
    assert all(s.state.cards[c].zone == "p1:graveyard" for c in (look[0], look[2], look[4], look[5], look[6]))
    assert zone(s.state, "p1", "library")[0] == top[7]
    assert_sound(s)


# -- Commune with Nature / Adventurous Impulse: "you may reveal a ... card from among them" ----------------------------
def test_commune_with_nature_reveals_the_creature_and_bottoms_the_rest(cards):
    s = build(cards)
    top = stack_library(s, ["Forest", "Grizzly Bears", "Forest", "Forest", "Forest", "Llanowar Elves"])
    look = top[:5]
    cast(s, "Commune with Nature", {"G": 1})
    d = decision(s, "choose_cards")
    assert {o.id for o in d.options} == {look[1]} and (d.min_choices, d.max_choices) == (0, 1)  # only a creature card is offered
    assert_hidden_from_bob(s, look)
    choose(s, [look[1]])
    assert s.state.cards[look[1]].zone == "p1:hand"
    d = decision(s, "order")
    assert {o.id for o in d.options} == {look[0], look[2], look[3], look[4]}
    assert_hidden_from_bob(s, [look[0], look[2], look[3], look[4]])
    choose(s, [look[4], look[3], look[2], look[0]])
    assert zone(s.state, "p1", "library")[-4:] == [look[0], look[2], look[3], look[4]]
    assert zone(s.state, "p1", "library")[0] == top[5]
    assert_sound(s)


def test_commune_with_nature_may_decline_and_nothing_is_revealed(cards):
    s = build(cards)
    top = stack_library(s, ["Forest", "Grizzly Bears", "Forest", "Forest", "Forest"])
    cast(s, "Commune with Nature", {"G": 1})
    decision(s, "choose_cards")
    choose(s, [])
    d = decision(s, "order")
    assert len(d.options) == 5
    choose(s, list(reversed(top)))
    assert all(s.state.cards[c].zone == "p1:library" for c in top)
    assert zone(s.state, "p1", "library")[-5:] == top
    assert not any(c in json.dumps(s.view("p2")) for c in top)
    assert_sound(s)


def test_commune_with_nature_still_asks_when_no_creature_is_there(cards):
    """Whether a decision appears mustn't tell Bob that the looked-at cards held no creature."""
    s = build(cards)
    top = stack_library(s, ["Forest"] * 5)
    cast(s, "Commune with Nature", {"G": 1})
    d = decision(s, "choose_cards")
    assert d.options == [] and d.min_choices == 0
    choose(s, [])
    decision(s, "order")
    assert not any(c in json.dumps(s.view("p2")) for c in top)


def test_adventurous_impulse_takes_a_land(cards):
    s = build(cards)
    top = stack_library(s, ["Grizzly Bears", "Forest", "Llanowar Elves", "Forest"])
    cast(s, "Adventurous Impulse", {"G": 1})
    d = decision(s, "choose_cards")
    assert {o.id for o in d.options} == {top[0], top[1], top[2]}  # a creature or land card among the three
    choose(s, [top[1]])
    assert s.state.cards[top[1]].zone == "p1:hand"
    choose(s, [top[2], top[0]])
    assert zone(s.state, "p1", "library")[-2:] == [top[0], top[2]]
    assert_sound(s)


# -- reveal (public) variants -----------------------------------------------------------------------------
def test_satyr_wayfinder_reveals_four_publicly_and_mills_the_rest(cards):
    s = build(cards)
    top = stack_library(s, ["Grizzly Bears", "Forest", "Llanowar Elves", "Grizzly Bears", "Forest"])
    cast(s, "Satyr Wayfinder", {"G": 1, "C": 1})
    d = decision(s, "choose_cards")
    assert {o.id for o in d.options} == {top[1]}  # only a land card
    bob = json.dumps(s.view("p2"))
    assert all(c in bob for c in top[:4])  # 701.20a: revealed to everyone
    choose(s, [top[1]])
    assert s.state.cards[top[1]].zone == "p1:hand"
    assert all(s.state.cards[c].zone == "p1:graveyard" for c in (top[0], top[2], top[3]))
    assert zone(s.state, "p1", "library")[0] == top[4]
    assert_sound(s)


def test_grisly_salvage_creature_or_land_the_rest_to_the_graveyard(cards):
    s = build(cards)
    top = stack_library(s, ["Grizzly Bears", "Forest", "Llanowar Elves", "Grizzly Bears", "Forest", "Forest"])
    cast(s, "Grisly Salvage", {"B": 1, "G": 1})
    d = decision(s, "choose_cards")
    assert {o.id for o in d.options} == set(top[:5]) and (d.min_choices, d.max_choices) == (0, 1)
    choose(s, [top[2]])
    assert s.state.cards[top[2]].zone == "p1:hand"
    assert all(s.state.cards[c].zone == "p1:graveyard" for c in (top[0], top[1], top[3], top[4]))
    assert_sound(s)


# -- "If you don't put the card onto the battlefield, put it into your hand" ------------------------------------------
def test_risen_reef_land_may_enter_tapped(cards):
    s = build(cards)
    top = stack_library(s, ["Forest", "Grizzly Bears"])
    cast(s, "Risen Reef", {"G": 1, "U": 1, "C": 1})
    d = decision(s, "choose_cards")
    assert [o.id for o in d.options] == [top[0]] and (d.min_choices, d.max_choices) == (0, 1)
    assert_hidden_from_bob(s, [top[0]])
    choose(s, [top[0]])
    forest = s.state.cards[top[0]]
    assert forest.zone == "p1:battlefield" and forest.tapped
    assert s.state.rules.decision is None
    assert_sound(s)


def test_risen_reef_declining_the_land_puts_it_into_your_hand(cards):
    s = build(cards)
    top = stack_library(s, ["Forest", "Grizzly Bears"])
    cast(s, "Risen Reef", {"G": 1, "U": 1, "C": 1})
    decision(s, "choose_cards")
    choose(s, [])
    assert s.state.cards[top[0]].zone == "p1:hand" and s.state.rules.decision is None
    assert_sound(s)


def test_risen_reef_nonland_goes_to_hand_without_a_choice(cards):
    s = build(cards)
    top = stack_library(s, ["Grizzly Bears", "Forest"])
    cast(s, "Risen Reef", {"G": 1, "U": 1, "C": 1})
    # (wave 5I, 701.20e) the question is asked whatever the hidden card is — with nothing to choose for a nonland card —
    # so whether it appears doesn't tell the table what the card was (a declined land goes to the hand too)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.options == [] and d.min_choices == 0
    choose(s, [])
    assert s.state.rules.decision is None
    assert s.state.cards[top[0]].zone == "p1:hand"
    assert not any(s.state.cards[c].zone == "p1:battlefield" for c in top)
    assert_sound(s)


# -- activated abilities (tokens carrying the real cards' text) ---------------------------------------------------
def _activate(s, src, **kw):
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0, **kw)
    pass_until_stack_empty(s)


def _token(s, name, text, pid="p1"):
    from tests.test_rules_effects import token

    return token(s, pid, name, text=text)


def test_monumental_henge_historic_card_from_among_them(cards):
    s = build(cards)
    top = stack_library(s, ["Grizzly Bears", "Gathering Stone", "Forest", "Llanowar Elves", "Forest", "Forest"])
    src = _token(s, "Henge", "{1}: Look at the top five cards of your library. You may reveal a historic card from among them and "
                             "put it into your hand. Put the rest on the bottom of your library in a random order.")
    _activate(s, src)
    d = decision(s, "choose_cards")
    assert [o.id for o in d.options] == [top[1]] and (d.min_choices, d.max_choices) == (0, 1)  # an artifact is historic (700.6)
    choose(s, [top[1]])
    assert s.state.cards[top[1]].zone == "p1:hand" and s.state.rules.decision is None
    library = zone(s.state, "p1", "library")
    assert library[0] == top[5] and set(library[-4:]) == {top[0], top[2], top[3], top[4]}  # (random order: recorded as moves)
    assert_sound(s)


def test_jace_plus_two_bottoms_the_opponents_top_card_privately(cards):
    s = build(cards)
    src = _token(s, "Jace", "{1}: Look at the top card of target player's library. You may put that card on the bottom of that "
                            "player's library.")
    bob_top = zone(s.state, "p2", "library")[0]
    below = zone(s.state, "p2", "library")[1]
    _activate(s, src, targets=["p2"])
    d = decision(s, "choose_cards")
    assert [o.id for o in d.options] == [bob_top] and (d.min_choices, d.max_choices) == (0, 1)
    assert d.player == "p1"
    assert bob_top not in json.dumps(s.view("p2"))
    choose(s, [bob_top])
    assert zone(s.state, "p2", "library")[0] == below and zone(s.state, "p2", "library")[-1] == bob_top  # Bob's own library
    assert s.state.cards[bob_top].zone == "p2:library"
    assert_sound(s)


def test_look_at_an_opponents_top_three_exile_one_face_down_rest_to_their_graveyard(cards):
    s = build(cards)
    src = _token(s, "Thief", "{1}: Look at the top three cards of target player's library, exile one of them face down, then put "
                             "the rest into their graveyard.")
    a, b, c = zone(s.state, "p2", "library")[:3]
    _activate(s, src, targets=["p2"])
    d = decision(s, "choose_cards")
    assert d.player == "p1" and {o.id for o in d.options} == {a, b, c} and (d.min_choices, d.max_choices) == (1, 1)
    assert not any(x in json.dumps(s.view("p2")) for x in (a, b, c))
    choose(s, [b])
    assert s.state.cards[b].zone == "p2:exile"  # (an owner's exile)
    assert s.state.cards[a].zone == "p2:graveyard" and s.state.cards[c].zone == "p2:graveyard"
    assert_sound(s)


def test_underrealm_lich_wording_one_to_hand_the_rest_to_the_graveyard(cards):
    s = build(cards)
    src = _token(s, "Lich", "{1}: Look at the top three cards of your library, then put one into your hand and the rest into "
                            "your graveyard.")
    a, b, c = zone(s.state, "p1", "library")[:3]
    _activate(s, src)
    decision(s, "choose_cards")
    choose(s, [c])
    assert s.state.cards[c].zone == "p1:hand" and s.state.cards[a].zone == "p1:graveyard" and s.state.cards[b].zone == "p1:graveyard"
    assert_sound(s)
