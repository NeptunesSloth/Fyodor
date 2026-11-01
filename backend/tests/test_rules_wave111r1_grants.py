"""Wave 111R1: abilities a resolved effect grants with quoted static and activated abilities (113.10, 611.2, 613.1f). Real Oracle text
(Scryfall, 2026-10-30); every scenario checks the replay and a save and a load.

* Nog, Ambitious Cadet: "If Nog is a Rogue, he becomes a Ferengi Scout with base power and toughness 3/4 and gains "Whenever Nog becomes
  tapped, surveil 2."" (608.2c: the condition is read as it resolves; 205.1a: the creature types are replaced; 611.2a: for the rest of the
  game) and "If Nog is a Scout, he becomes a Ferengi Officer and gains "You may play lands from your graveyard" and "You may play an
  additional land on each of your turns."" (the granted statics work while he has them: 305.1, 305.2; a new object has none, 400.7).
* Q, Stacking the Deck: the card the exile stops at gains an activated ability that works only while it is exiled (113.6b), activated by its
  owner (602.2) during their turn, whose copy (707.12) is cast while it resolves, paying its costs (608.2g).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put

NOG = ('Menace\n{1}: If Nog is a Rogue, he becomes a Ferengi Scout with base power and toughness 3/4 and gains "Whenever Nog becomes tapped, '
       'surveil 2."\n{3}: If Nog is a Scout, he becomes a Ferengi Officer and gains "You may play lands from your graveyard" and "You may play an '
       'additional land on each of your turns."')
Q = ('When Q enters, shuffle your library, then exile cards from the top of your library until you exile a nonland card. That nonland card gains '
     '"Exile a card from your hand: Create a copy of this card. You may cast the copy. Activate only during your turn and only if this card is exiled."')
Q_ABILITY = ("Exile a card from your hand: Create a copy of this card. You may cast the copy. Activate only during your turn and only if this card "
             "is exiled.")
EXTRA = [
    card("Nog, Ambitious Cadet", set_code="tst", number="111R1-1", mana_cost="{B}{G}", cmc=2.0, type_line="Legendary Creature — Ferengi Rogue",
         oracle_text=NOG, colors=["B", "G"], color_identity=["B", "G"], keywords=["Menace"], power="2", toughness="2"),
    real("Q, Stacking the Deck", "{2}{R}{R}", 4, "Legendary Creature — Q", Q, ("4", "4"), "R"),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [real("Exile", "{2}{W}", 3, "Instant", "Exile target nonwhite attacking creature. You gain life equal to its toughness.", None, "W")]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def step(s, pick=None):
    """One decision (answered with ``pick``, else its first options) or one priority pass."""
    d = s.state.rules.decision
    if d is not None:
        ids = pick if pick is not None else [o.id for o in d.options][: max(1, d.min_choices)]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    else:
        act(s, s.state.rules.priority, type="pass_priority")


def settle(s, limit=60, **on):
    """Resolve everything. ``on``: a word of a decision's prompt → the option ids to answer it with."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            return
        step(s, next((ids for word, ids in on.items() if d is not None and word in d.prompt), None))
    raise AssertionError("never settled")


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def granted(s, c):
    return [a for a in ch(s, c).abilities if a.index >= 10_000]


def build3(cards, p1=()):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    seats = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [*((1, n) for n in p1), (9, "Forest")])),
             PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])),
             PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(10, "Mountain")]))]
    s = GameSession(enable(new_game(seats, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def library(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:library"]


def move(s, cards_, zone, pid="p1"):
    act(s, pid, type="move", card_ids=[c.id for c in cards_], to={"player": pid, "zone": zone})


def hints(s, pid="p1"):
    return s.view(pid)["rules"]["hints"]


# -- Nog, Ambitious Cadet ----------------------------------------------------------------------------------------------------------------
def nog_table(cards, *, scout=False, officer=False, build_=build):
    s = build_(cards, ["Nog, Ambitious Cadet"])
    nog = put(s, "Nog, Ambitious Cadet")
    if scout or officer:
        mana(s, C=1)
        act(s, "p1", type="activate_ability", card_id=nog.id, ability=1)
        settle(s)
    if officer:
        mana(s, C=3)
        act(s, "p1", type="activate_ability", card_id=nog.id, ability=2)
        settle(s)
    return s, nog


def test_nog_becomes_a_scout_with_the_surveil_trigger(cards):
    from tests.test_rules_wave5c_combat import declare, to_attack

    s, nog = nog_table(cards)
    assert ch(s, nog).subtypes == {"Ferengi", "Rogue"} and pt(s, "Nog, Ambitious Cadet") == (2, 2) and not granted(s, nog)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=nog.id, ability=1)
    settle(s)
    assert ch(s, nog).subtypes == {"Ferengi", "Scout"} and pt(s, "Nog, Ambitious Cadet") == (3, 4)  # 205.1a, 613.4b
    assert [a.text for a in granted(s, nog)] == ["Whenever this permanent becomes tapped, surveil 2."]
    to_attack(s, 3)  # (his controller's next turn: no longer summoning sick)
    declare(s, (nog, "p2"))  # tapped by attacking: the granted trigger (603.2)
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and d.prompt.startswith("Surveil 2") and len(d.options) == 2
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert [s.state.cards[c].name for c in s.state.zones["p1:graveyard"]] == ["Forest"]
    check(s)


@pytest.mark.parametrize("ability", [1, 2])
def test_nog_does_nothing_when_he_is_not_the_named_type(cards, ability):
    """{1} as a Scout (already became one: not a Rogue) and {3} as a Rogue (not a Scout): the condition is false as it resolves (608.2c)."""
    s, nog = nog_table(cards, scout=ability == 1)
    before = (ch(s, nog).subtypes, pt(s, "Nog, Ambitious Cadet"), [a.text for a in granted(s, nog)])
    mana(s, C=3 if ability == 2 else 1)
    act(s, "p1", type="activate_ability", card_id=nog.id, ability=ability)
    settle(s)
    assert (ch(s, nog).subtypes, pt(s, "Nog, Ambitious Cadet"), [a.text for a in granted(s, nog)]) == before
    assert ch(s, nog).subtypes == ({"Ferengi", "Scout"} if ability == 1 else {"Ferengi", "Rogue"})
    check(s)


@pytest.mark.parametrize("officer", [False, True])
def test_nog_the_officer_plays_lands_from_his_graveyard_and_an_extra_land(cards, officer):
    s, nog = nog_table(cards, scout=True, officer=officer)
    if officer:  # a Ferengi Officer now (no longer a Scout), still 3/4 with the surveil trigger: each effect stays (613.7)
        assert ch(s, nog).subtypes == {"Ferengi", "Officer"} and pt(s, "Nog, Ambitious Cadet") == (3, 4)
        assert [a.text for a in granted(s, nog)] == ["Whenever this permanent becomes tapped, surveil 2.", "You may play lands from your graveyard.",
                                                     "You may play an additional land on each of your turns."]
    buried, first, second = library(s, "Forest")[:3]
    move(s, [buried], "graveyard")
    move(s, [first, second], "hand")
    assert (buried.id in hints(s)["playable_lands"]) is officer
    if officer:
        act(s, "p1", type="play_land", card_id=buried.id)  # 305.1: the granted permission
        assert s.state.cards[buried.id].zone == "p1:battlefield"
    else:
        with pytest.raises(ActionError):
            act(s, "p1", type="play_land", card_id=buried.id)
    act(s, "p1", type="play_land", card_id=first.id)  # the land for the turn (Scout) / the additional one (Officer, 305.2)
    with pytest.raises(ActionError):  # one land (Scout) / two lands (Officer) this turn: no more
        act(s, "p1", type="play_land", card_id=second.id)
    assert s.state.cards[first.id].zone == "p1:battlefield" and s.state.cards[second.id].zone == "p1:hand"
    check(s)


def test_nog_loses_the_granted_abilities_when_he_leaves(cards):
    """400.7: the Officer bounced and cast again is a new object, a 2/2 Ferengi Rogue without the grants (they were locked to the old one, 611.2c)."""
    s, nog = nog_table(cards, officer=True)
    move(s, [nog], "hand")
    mana(s, B=1, G=1)
    act(s, "p1", type="cast_spell", card_id=nog.id)
    settle(s)
    assert s.state.cards[nog.id].zone == "p1:battlefield" and not granted(s, nog)
    assert ch(s, nog).subtypes == {"Ferengi", "Rogue"} and pt(s, "Nog, Ambitious Cadet") == (2, 2)
    buried = library(s, "Forest")[0]
    move(s, [buried], "graveyard")
    assert buried.id not in hints(s)["playable_lands"]
    check(s)


def test_nogs_statics_are_his_controllers_only(cards):
    """Three players: "you" is Nog's controller (on Bob's turn Bob can't play a land from his graveyard); "on each of your turns": on Alice's
    next turn she has two land plays again."""
    s, nog = nog_table(cards, officer=True, build_=build3)
    to_phase(s, "main1", turn=2)
    island = library(s, "Island", "p2")[0]
    move(s, [island], "graveyard", "p2")
    assert island.id not in hints(s, "p2")["playable_lands"]
    with pytest.raises(ActionError):
        act(s, "p2", type="play_land", card_id=island.id)
    to_phase(s, "main1", turn=4)
    first, second = library(s, "Forest")[-2:]
    move(s, [first, second], "hand")
    act(s, "p1", type="play_land", card_id=first.id)
    act(s, "p1", type="play_land", card_id=second.id)
    assert s.state.cards[second.id].zone == "p1:battlefield"
    check(s)


# -- Q, Stacking the Deck -------------------------------------------------------------------------------------------------------------------
def q_table(cards, found="Lightning Bolt", build_=build, hand=1):
    """Alice casts Q; her library holds Forests and one nonland card (``found``), so the exile stops at it whatever the shuffle."""
    s = build_(cards, ["Q, Stacking the Deck", *([found] if found else [])])
    q = card_named(s, "Q, Stacking the Deck")
    move(s, [q], "hand")
    if hand:
        move(s, library(s, "Forest")[-hand:], "hand")
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=q.id)
    settle(s)
    return s, (card_named(s, found) if found else None)


def activate(s, c, pid="p1"):
    act(s, pid, type="activate_ability", card_id=c.id, ability=granted(s, c)[0].index)


def test_q_grants_the_exiled_card_a_copy_ability(cards):
    s, bolt = q_table(cards, hand=2)
    assert s.state.cards[bolt.id].zone == "p1:exile"
    assert [a.text for a in granted(s, bolt)] == [Q_ABILITY]
    exiled_forests = [c for c in s.state.zones["p1:exile"] if s.state.cards[c].name == "Forest"]
    assert len(exiled_forests) + len(library(s, "Forest")) == 7  # the lands above it were exiled too
    for pid in ("p1", "p2"):  # exile is public: everyone sees the granted ability
        assert [a["text"] for a in s.view(pid)["rules"]["stats"][bolt.id]["abilities"]] == [Q_ABILITY]
    assert {"card_id": bolt.id, "ability": granted(s, bolt)[0].index} in hints(s).get("activatable", [])
    for n in (1, 2):  # the card stays exiled with the ability: each activation makes another copy
        if n == 2:  # Q leaving changes nothing: no "for as long as" (611.2a)
            move(s, [card_named(s, "Q, Stacking the Deck")], "graveyard")
        paid = s.state.zones["p1:hand"][0]
        activate(s, bolt)
        mana(s, R=1)
        settle(s, exile=[paid], target=["p2"])  # the cost: a card exiled from the hand; the copy (707.12) is cast from exile, its {R} paid (608.2g)
        assert s.state.cards[paid].zone == "p1:exile" and paid not in s.state.zones.get("p1:hand", [])
        assert life(s, "p2") == 40 - 3 * n and not s.state.players["p1"].mana.get("R")
        assert s.state.cards[bolt.id].zone == "p1:exile" and [a.text for a in granted(s, bolt)] == [Q_ABILITY]
    assert [c.name for c in s.state.cards.values() if c.name == "Lightning Bolt"] == ["Lightning Bolt"]  # the copies ceased to exist (704.5e)
    check(s)


@pytest.mark.parametrize("cast", [False, True])
def test_q_copy_of_a_creature_card_becomes_a_token(cards, cast):
    """The copy of Grizzly Bears, cast, resolves as a token (608.3f, 111.13) without the granted ability (707.2); not cast, it ceases to exist."""
    s, bears = q_table(cards, found="Grizzly Bears")
    activate(s, bears)
    mana(s, G=1, C=1)
    d = s.state.rules.decision
    while d is None or "cast" not in d.prompt.lower():
        step(s)
        d = s.state.rules.decision
    step(s, [d.options[0].id] if cast else [])
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:battlefield"]
    assert len(tokens) == int(cast) and all(c.is_token for c in tokens)
    if cast:
        assert not granted(s, tokens[0]) and s.state.players["p1"].mana.get("G", 0) == 0
    assert s.state.cards[bears.id].zone == "p1:exile" and not s.state.zones.get("p1:hand")
    assert [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and not c.is_token] == [s.state.cards[bears.id]]
    check(s)


def test_q_ability_only_during_its_owners_turn(cards):
    """Three players: not on Bob's or Carol's turn (602.5); only its owner may activate it (602.2: no controller in exile, 108.4a)."""
    s, bolt = q_table(cards, build_=build3, hand=2)
    with pytest.raises(ActionError):
        activate(s, bolt, pid="p2")
    act(s, "p1", type="set_prefs", stops_my_turn=["end"])
    to_phase(s, "end", turn=1)  # any time during her turn, not only in a main phase
    activate(s, bolt)
    mana(s, R=1)
    settle(s, exile=[s.state.zones["p1:hand"][0]], target=["p3"])
    assert life(s, "p3") == 37 and len(s.state.zones["p1:hand"]) == 1
    for turn in (2, 3):
        to_phase(s, "main1", turn=turn)
        assert not any(a["card_id"] == bolt.id for a in hints(s).get("activatable", []))
        with pytest.raises(ActionError):
            activate(s, bolt)
    check(s)


def test_q_ability_needs_a_card_in_hand(cards):
    s, bolt = q_table(cards, hand=0)
    assert not s.state.zones.get("p1:hand") and not any(a["card_id"] == bolt.id for a in hints(s).get("activatable", []))
    with pytest.raises(ActionError):
        activate(s, bolt)
    check(s)


@pytest.mark.parametrize("back_to_exile", [False, True])
def test_q_ability_ends_when_the_card_leaves_exile(cards, back_to_exile):
    """400.7: in the graveyard (113.6b: it works only in exile) and back in exile it is a new object that never gained it."""
    s, bolt = q_table(cards)
    move(s, [bolt], "graveyard")
    if back_to_exile:
        move(s, [bolt], "exile")
    assert not granted(s, bolt) and not any(a["card_id"] == bolt.id for a in hints(s).get("activatable", []))
    check(s)


def test_q_card_that_left_before_the_copy_is_made_by_hand(cards):
    """The card leaves exile with the ability on the stack: the copy would be of its last known information (113.7a), left to the players."""
    s, bolt = q_table(cards)
    act(s, "p1", type="set_prefs", hold_priority=True)
    activate(s, bolt)
    assert s.state.zones.get("stack") and s.state.rules.priority == "p1"
    move(s, [bolt], "graveyard")  # (as an opponent's Pull from Eternity would, in response)
    while s.state.rules.decision is None:
        step(s)
    d = s.state.rules.decision
    assert d.kind == "manual_resolution" and "last known information" in d.prompt
    settle(s)
    assert life(s, "p2") == 40 and s.state.cards[bolt.id].zone == "p1:graveyard" and not s.state.zones.get("stack")
    check(s)


def test_q_finds_no_nonland_card(cards):
    """Only lands in the library: every card is exiled and nothing gains the ability."""
    s, _ = q_table(cards, found=None)
    assert not library(s, "Forest") and not any(granted(s, s.state.cards[c]) for c in s.state.zones["p1:exile"])
    check(s)


def test_q_ability_on_a_card_named_exile(cards):
    """The granted ability names no holder: on a card named "Exile" its cost is still "Exile a card from your hand"."""
    s, exile = q_table(cards, found="Exile")
    assert [a.text for a in granted(s, exile)] == [Q_ABILITY]
    assert {"card_id": exile.id, "ability": granted(s, exile)[0].index} in hints(s).get("activatable", [])
    activate(s, exile)
    settle(s)
    assert not s.state.zones.get("p1:hand") and s.state.cards[exile.id].zone == "p1:exile"
    check(s)
