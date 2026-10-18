"""Wave 30U: ability-word riders and event-player history (CR 2026-09-25), real Oracle text (tests/fixtures/wave30u_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load; three players play them, so "that player" / "you" / another
opponent are told apart.

* 207.2c / 608.2c: an ability word has no rules meaning - "Infusion - If you gained life this turn, that creature's controller loses 3 life." is
  the second sentence of the spell, carried out in order, so its "that creature" is the target of the line above (Foolish Fate).
* 603.4 / 608.2c: "if that player didn't cast a spell this turn" is the trigger event's player's own history (not the controller's), checked
  when the ability would trigger and again as it resolves (Impatience, Predatory Advantage); "a player other than you" is the controller's
  point of view (Ludevic, Necro-Alchemist).
* 608.2b / 400.7: a target that left the battlefield is gone - an object that comes back is a new one, and the spell does nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import counters, settle, until
from tests.wave9c_kit import card_named, check, life, mana, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30u_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t30u", number=f"U{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
PROBES = [("Probe Flash", "{U}", "Creature — Drake", "1", "1", "Flash", "U"), ("Probe Bear", "{1}{G}", "Creature — Bear", "2", "2", "", "G"), ("Probe Drake", "{U}", "Creature — Drake", "1", "1", "", "U"),
          ("Probe Cantrip", "{U}", "Instant", None, None, "Scry 1.", "U"), ("Probe Salve", "{W}", "Instant", None, None, "You gain 2 life.", "W"),
          ("Probe Trinket", "{1}", "Artifact", None, None, "", ""),
          ("Probe Sting", "{B}", "Instant", None, None, "Target player loses 1 life.", "B"),
          ("Probe Boast", "{B}", "Sorcery", None, None,
           "Destroy target creature.\nBoast — If you control an artifact, that creature's controller loses 3 life.", "B"),
          ("Probe Bare", "{B}", "Sorcery", None, None, "Destroy target creature.\nIf you control an artifact, that creature's controller loses 3 life.", "B")]
EXTRA += [card(n, set_code="t30u", number=f"P{i:02d}", mana_cost=mc, cmc=float(mc.count("{")), type_line=tl, colors=[c] if c else [],
               color_identity=[c] if c else [], oracle_text=text, power=p, toughness=t,
               keywords=["Flash"] if text == "Flash" else []) for i, (n, mc, tl, p, t, text, c) in enumerate(PROBES)]


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def three(cards, alice=(), bob=(), carol=()):
    decks = [deck(cards, "Krenko, Mob Boss", [*((1, n) for n in alice), (20, "Forest")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (20, "Island")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in carol), (20, "Island")])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # -> Alice's main phase
    return s


def bf(s, name, pid, controller=None):
    """Put ``name`` (owned by ``pid``) onto the battlefield under ``controller``'s control (its owner's, unless said)."""
    c = card_named(s, name, pid)
    act(s, controller or pid, type="move", card_ids=[c.id], to={"player": controller or pid, "zone": "battlefield"})
    return c


def level(name):
    c = next(c for c in [*EXTRA, *DATA] if c["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


def to_turn(s, n):
    until(s, lambda s: s.state.turn.number == n and s.state.turn.phase == "main1" and s.state.rules.decision is None, limit=500)


def to_end(s, n):
    """The end step of turn ``n``, its triggers on the stack and the active player holding priority (a player with ``stops`` set)."""
    until(s, lambda s: s.state.turn.number == n and s.state.turn.phase == "end", limit=500)


def cast(s, name, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, **kw)
    settle(s)


def play(s, name, pid, **m):
    """Put ``name`` into ``pid``'s hand, pay for it from the pool and cast it (a creature spell resolves)."""
    to_hand(s, name, pid)
    mana(s, pid, **m)
    cast(s, name, pid)


def stops(s, *pids):
    """These players stop at every priority (response ON), so they can act on another player's turn."""
    for pid in pids:
        act(s, pid, type="set_prefs", response="on")


def pass_to(s, pid):
    """Everyone passes (an empty stack) until ``pid`` holds priority."""
    for _ in range(6):
        if s.state.rules.priority == pid and not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"{pid} never got priority")


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def tokens(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.is_token and c.zone.endswith(":battlefield")]


NAMES = [c["name"] for c in DATA]


@pytest.mark.parametrize("name", NAMES)
def test_the_cards_are_full(name):
    assert level(name) == "FULL", name


# -- Infusion: "that creature's controller loses 3 life" (Foolish Fate) -----------------------------------------------------------
def fate(cards, gain=True, steal=False):
    s = three(cards, alice=["Foolish Fate", "Probe Salve"], bob=["Probe Bear"], carol=["Probe Drake"])
    bear = bf(s, "Probe Bear", "p2", controller="p3" if steal else None)
    if gain:
        play(s, "Probe Salve", "p1", W=1)
        assert life(s, "p1") == 42
    to_hand(s, "Foolish Fate")
    mana(s, "p1", B=3)
    return s, bear


def test_foolish_fate_after_lifegain_the_destroyed_creatures_controller_loses_life(cards):
    s, bear = fate(cards)
    cast(s, "Foolish Fate", targets=[bear.id])
    assert s.state.cards[bear.id].zone == "p2:graveyard"
    assert (life(s, "p2"), life(s, "p3"), life(s, "p1")) == (37, 40, 42)  # Bob's creature: Bob pays; Carol and Alice don't
    check(s)


def test_foolish_fate_without_lifegain_only_destroys(cards):
    s, bear = fate(cards, gain=False)
    cast(s, "Foolish Fate", targets=[bear.id])
    assert s.state.cards[bear.id].zone == "p2:graveyard" and (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (40, 40, 40)
    check(s)


def test_foolish_fate_a_stolen_creature_costs_the_player_controlling_it(cards):
    s, bear = fate(cards, steal=True)
    cast(s, "Foolish Fate", targets=[bear.id])
    assert s.state.cards[bear.id].zone == "p2:graveyard"  # (Bob's card)
    assert (life(s, "p2"), life(s, "p3")) == (40, 37)  # "that creature's controller" is who controlled it when it died: Carol
    check(s)


def test_foolish_fate_a_target_that_left_and_came_back_is_a_new_object(cards):
    s, bear = fate(cards)
    act(s, "p1", type="set_prefs", hold_priority=True)  # (the spell waits on the stack)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Foolish Fate").id, targets=[bear.id])
    assert s.state.zones.get("stack")
    act(s, "p2", type="move", card_ids=[bear.id], to={"player": "p2", "zone": "exile"})
    act(s, "p2", type="move", card_ids=[bear.id], to={"player": "p2", "zone": "battlefield"})  # 400.7: not the creature that was targeted
    settle(s)
    assert s.state.cards[bear.id].zone == "p2:battlefield" and (life(s, "p2"), life(s, "p3")) == (40, 40)  # 608.2b: the spell does nothing
    check(s)


def test_only_your_own_lifegain_turns_the_rider_on(cards):
    s = three(cards, alice=["Foolish Fate"], bob=["Probe Bear", "Probe Salve"])
    bear = bf(s, "Probe Bear", "p2")
    to_hand(s, "Foolish Fate")
    stops(s, "p1")
    to_turn(s, 2)  # Bob's turn: he gains life, then Alice (who didn't) destroys his creature
    play(s, "Probe Salve", "p2", W=1)
    assert life(s, "p2") == 42
    pass_to(s, "p1")
    mana(s, "p1", B=3)
    cast(s, "Foolish Fate", targets=[bear.id])
    assert s.state.cards[bear.id].zone == "p2:graveyard" and life(s, "p2") == 42
    check(s)


# -- Infusion: "that creature also gains trample and indestructible" (Efflorescence) ---------------------------------------------------
@pytest.mark.parametrize("gain", [True, False])
def test_efflorescence_only_the_target_gets_the_rider(cards, gain):
    s = three(cards, alice=["Efflorescence", "Probe Salve", "Probe Bear"], bob=["Probe Bear"])
    mine, other = bf(s, "Probe Bear", "p1"), bf(s, "Probe Bear", "p2")
    if gain:
        play(s, "Probe Salve", "p1", W=1)
    to_hand(s, "Efflorescence")
    mana(s, "p1", G=3)
    cast(s, "Efflorescence", targets=[mine.id])
    assert counters(s, mine) == 2 and counters(s, other) == 0
    assert {"trample", "indestructible"} & set(ch(s, mine).keywords) == ({"trample", "indestructible"} if gain else set())
    assert not {"trample", "indestructible"} & set(ch(s, other).keywords)
    check(s)


# -- Metalcraft: "exile that creature" (Dispatch) ------------------------------------------------------------------------------------
@pytest.mark.parametrize(("mine", "theirs", "exiled"), [(3, 0, True), (2, 3, False)])  # only YOUR artifacts count
def test_dispatch_exiles_the_tapped_creature_with_three_of_your_artifacts(cards, mine, theirs, exiled):
    s = three(cards, alice=["Dispatch", *["Probe Trinket"] * 3], bob=["Probe Bear", *["Probe Trinket"] * 3])
    bear = bf(s, "Probe Bear", "p2")
    for pid, n in (("p1", mine), ("p2", theirs)):
        for c in [c for c in s.state.cards.values() if c.name == "Probe Trinket" and c.owner == pid][:n]:
            act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    to_hand(s, "Dispatch")
    mana(s, "p1", W=1)
    cast(s, "Dispatch", targets=[bear.id])
    got = s.state.cards[bear.id]
    assert (got.zone == "p2:exile") == exiled and (exiled or (got.zone == "p2:battlefield" and got.tapped))
    check(s)


# -- the ability-word deny list: only the printed ability words are read as riders, a lone "If" line is left to the player -------------
@pytest.mark.parametrize("name", ["Probe Boast", "Probe Bare"])
def test_a_line_without_an_ability_word_is_not_joined_to_the_one_above(name):
    assert level(name) == "PARTIAL"


# -- "if that player didn't cast a spell this turn" (Impatience: the player whose end step it is, 603.4) -------------------------------
def test_impatience_is_about_the_player_whose_end_step_it_is_not_its_controller(cards):
    s = three(cards, alice=["Impatience", "Probe Cantrip"], bob=["Probe Cantrip"], carol=["Probe Cantrip"])
    bf(s, "Impatience", "p1")
    stops(s, "p1")
    play(s, "Probe Cantrip", "p1", U=1)  # turn 1: Alice cast a spell
    to_turn(s, 2)
    assert life(s, "p1") == 40  # (her end step: she had cast one)
    pass_to(s, "p1")
    play(s, "Probe Cantrip", "p1", U=1)  # Bob's turn: ALICE casts a spell, Bob none
    to_turn(s, 3)
    assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (40, 38, 40)  # Bob's end step: he cast nothing, whatever Alice did
    play(s, "Probe Cantrip", "p3", U=1)  # Carol's turn: she casts one
    to_turn(s, 4)
    assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (40, 38, 40)
    check(s)


def test_impatience_is_checked_again_as_it_resolves(cards):
    s = three(cards, alice=["Impatience"], bob=["Probe Cantrip"])
    bf(s, "Impatience", "p1")
    stops(s, "p2")
    to_turn(s, 2)
    to_end(s, 2)
    assert s.state.zones.get("stack") and s.state.rules.priority == "p2"  # Bob, the active player, with the trigger waiting (nothing cast yet)
    play(s, "Probe Cantrip", "p2", U=1)  # 603.4: he casts one in response - the condition is false when it would resolve
    to_turn(s, 3)
    assert life(s, "p2") == 40
    check(s)


# -- "if that player didn't cast a creature spell this turn" (Predatory Advantage: each opponent's end step) ------------------------------
def test_predatory_advantage_reads_each_opponents_own_creature_spells(cards):
    s = three(cards, alice=["Predatory Advantage", "Probe Drake"], bob=["Probe Drake"], carol=["Probe Cantrip"])
    bf(s, "Predatory Advantage", "p1")
    to_turn(s, 2)
    play(s, "Probe Drake", "p2", U=1)  # Bob cast a creature spell
    to_turn(s, 3)
    assert not tokens(s, "Lizard")  # (and Alice's own end step on turn 1 never triggered it)
    play(s, "Probe Cantrip", "p3", U=1)  # Carol cast only an instant
    to_turn(s, 4)
    assert len(tokens(s, "Lizard")) == 1
    check(s)


def test_predatory_advantage_what_you_cast_on_their_turn_does_not_count_for_them(cards):
    s = three(cards, alice=["Predatory Advantage", "Probe Flash"], bob=["Probe Drake"])
    bf(s, "Predatory Advantage", "p1")
    stops(s, "p1")
    to_turn(s, 2)
    pass_to(s, "p1")
    play(s, "Probe Flash", "p1", U=1)  # Alice casts a creature spell on Bob's turn - Bob still didn't
    to_turn(s, 3)
    assert len(tokens(s, "Lizard")) == 1
    check(s)


# -- "that player may draw a card if a player other than you lost life this turn" (Ludevic: "you" is the controller) --------------------
def answer_asks(s, turn, yes=True):
    """Play to the main phase of ``turn``, answering the yes / no asks the same way; return who was asked."""
    asked = []

    def done(s):
        d = s.state.rules.decision
        if d is not None and {o.id for o in d.options} == {"pay", "decline"}:
            asked.append(d.player)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay" if yes else "decline"])
        return s.state.turn.number == turn and s.state.turn.phase == "main1" and s.state.rules.decision is None

    until(s, done, limit=500)
    return asked


def library(s, pid):
    return len(s.state.zones[f"{pid}:library"])


def ludevic(cards):
    s = three(cards, alice=["Ludevic, Necro-Alchemist", "Probe Sting"], bob=["Probe Cantrip"], carol=["Probe Cantrip"])
    bf(s, "Ludevic, Necro-Alchemist", "p1")
    stops(s, "p1")
    to_hand(s, "Probe Sting")
    mana(s, "p1", B=1)
    return s


def test_ludevic_another_player_lost_life_so_the_player_whose_end_step_it_is_draws(cards):
    s = ludevic(cards)
    cast(s, "Probe Sting", targets=["p2"])  # turn 1: Bob lost life
    before = [library(s, p) for p in ("p1", "p2", "p3")]
    assert answer_asks(s, 2) == ["p1"]  # Alice's end step: she is the player and is asked; a player other than Alice lost life: she draws
    assert [library(s, p) for p in ("p1", "p2", "p3")] == [before[0] - 1, before[1] - 1, before[2]]  # (Bob's -1 is his own draw step)
    check(s)


def test_ludevic_only_the_controller_losing_life_is_not_another_player(cards):
    s = ludevic(cards)
    cast(s, "Probe Sting", targets=["p1"])  # turn 1: only ALICE lost life - "a player other than you" is false
    assert life(s, "p1") == 39
    before = [library(s, p) for p in ("p1", "p2")]
    assert answer_asks(s, 2) == ["p1"]  # (asked, and said yes - the condition is what is false)
    assert [library(s, p) for p in ("p1", "p2")] == [before[0], before[1] - 1]
    check(s)


def test_ludevic_on_another_players_turn_that_player_draws_not_the_controller(cards):
    s = ludevic(cards)
    answer_asks(s, 2)  # (turn 1 passes: nobody lost life)
    pass_to(s, "p1")  # Bob's turn: Alice gets priority and makes Carol lose life
    mana(s, "p1", B=1)
    cast(s, "Probe Sting", targets=["p3"])
    before = [library(s, p) for p in ("p1", "p2", "p3")]
    assert answer_asks(s, 3) == ["p2"]  # Bob's end step: BOB is asked and draws; neither Alice nor Carol is
    assert [library(s, p) for p in ("p1", "p2", "p3")] == [before[0], before[1] - 1, before[2] - 1]  # (Carol's -1 is her own draw step)
    check(s)
