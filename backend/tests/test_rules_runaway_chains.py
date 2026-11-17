"""-- runaway chains -- Shabraz, the Skyshark and Marina Vendrell's Grimoire (real Oracle text): each card drawn puts a counter on Shabraz
and gains 1 life (one trigger per card, 603.2c), each life gain draws that many cards (one trigger per event): a mandatory loop that ends
only when the library is empty. The bug: one press of RESOLVE resolved the whole chain in one server step (77 cards drawn, a loss to the
empty library) although the player drew an instant they could have answered with.

* RESOLVE (the HUD's big button and P: ``pass_priority`` until ``stack_changes``) resolves the top object and gives priority back while
  anything is on the stack (117.3b, 117.4, 608.2); with the stack empty the usual stops decide (a lone spell: one press, as before).
* Every PASS UNTIL … (RESOLVE ALL) stops when a card arrives in hand that could be cast at instant speed (engine.new_response).
* No action resolves more than ``LOOP_RESOLUTIONS`` objects on automatic passes once the stack keeps refilling (engine.loop_pause).
Each scenario checks the replay and a save and a load, at a target-dummy table (Sandbox solo) and at a table of two players."""

from __future__ import annotations

import json

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameSettings
from app.rules import coverage
from app.rules.engine import LOOP_RESOLUTIONS
from tests.game_helpers import act, deck, enable, engine_pays
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check

SHABRAZ, GRIMOIRE = "Shabraz, the Skyshark", "Marina Vendrell's Grimoire"
EXTRA = [
    real(SHABRAZ, "{3}{W}{U}", 5, "Legendary Creature — Shark Bird",
         "Partner with Brallin, Skyshark Rider\nFlying\nWhenever you draw a card, put a +1/+1 counter on Shabraz and you gain 1 life.\n"
         "{W/U}: Target Human gains flying until end of turn.", ("3", "3"), "WU"),
    real(GRIMOIRE, "{5}{U}", 6, "Legendary Artifact — Book",
         "When Marina Vendrell's Grimoire enters, if you cast it, draw five cards.\nYou have no maximum hand size and don't lose the game "
         "for having 0 or less life.\nWhenever you gain life, draw that many cards.\nWhenever you lose life, discard that many cards. "
         "Then if you have no cards in hand, you lose the game.", None, "U"),
]
RESOLVE = {"type": "pass_priority", "until": "stack_changes"}  # what the HUD's RESOLVE button (and P) sends with a stack
RESOLVE_ALL = {"type": "pass_priority", "until": "stack_empty"}


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def table(cards, kind: str) -> GameSession:
    """Alice at her first main phase with Shabraz on the battlefield, the Grimoire in hand and {5}{U} floating. ``kind``: "dummy" (Sandbox
    solo against a target dummy, the bug's table) or "two" (Alice and Bob, both players)."""
    mine = [(1, SHABRAZ), (1, GRIMOIRE), (1, "Lightning Bolt"), (1, "Swords to Plowshares"), (2, "Mountain"), (40, "Island")]
    alice = deck(cards, "Krenko, Mob Boss", mine)
    if kind == "dummy":
        state = new_game([PlayerSetup("Alice", cards=alice)], name="Deck test", format="sandbox", shuffle=False, first_player=0,
                         settings=GameSettings(starting_life=40, allow_test_objects=True))
    else:
        bob = deck(cards, "Atraxa, Praetors' Voice", [(20, "Island")])
        state = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False, first_player=0)
    enable(state, "full")
    s = GameSession(state, cards=cards)
    if kind == "dummy":
        act(s, "p1", type="add_dummy")
        engine_pays(s.state)
    for _ in range(10):
        if s.state.turn.phase == "main1" and s.state.rules.priority == "p1" and not s.state.zones.get("stack"):
            break
        act(s, "p1", type="pass_priority")
    assert (s.state.turn.phase, s.state.rules.priority) == ("main1", "p1")
    act(s, "p1", type="move", card_ids=[named(s, SHABRAZ).id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[named(s, GRIMOIRE).id], to={"zone": "hand"})
    for name in ("Lightning Bolt", "Swords to Plowshares"):  # (out of the way: a test puts the one it wants where it's drawn)
        act(s, "p1", type="move", card_ids=[named(s, name).id], to={"zone": "library"}, position="bottom")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 6})
    return s


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def stack_names(s) -> list[str]:
    return [s.state.cards[cid].name for cid in s.state.zones.get("stack", [])]


def in_library_at(s, name: str, index: int) -> None:
    act(s, "p1", type="move", card_ids=[named(s, name).id], to={"zone": "library"}, index=index)


def hand(s) -> list[str]:
    return [s.state.cards[cid].name for cid in s.state.zones["p1:hand"]]


def counters(s) -> int:
    return s.state.cards[named(s, SHABRAZ).id].counters.get("+1/+1", 0)


def hold_and_cast_grimoire(s) -> None:
    act(s, "p1", type="set_prefs", hold_priority=True)  # (the Grimoire stays on the stack: each test presses what it tests)
    act(s, "p1", type="cast_spell", card_id=named(s, GRIMOIRE).id)
    act(s, "p1", type="set_prefs", hold_priority=False)
    assert stack_names(s) == [GRIMOIRE] and s.state.rules.priority == "p1"


def test_both_cards_are_full(cards):
    assert coverage.of_card_data(cards.resolve(SHABRAZ)).level == "FULL"
    assert coverage.of_card_data(cards.resolve(GRIMOIRE)).level == "FULL"


@pytest.mark.parametrize("kind", ["dummy", "two"])
def test_resolve_resolves_one_object_at_a_time_and_each_draw_is_its_own_trigger(cards, kind):
    s = table(cards, kind)
    hold_and_cast_grimoire(s)
    library, life = len(s.state.zones["p1:library"]), s.state.players["p1"].life
    act(s, "p1", **RESOLVE)  # the Grimoire resolves; its enters trigger goes on the stack and Alice gets priority (117.3b)
    assert stack_names(s) == [GRIMOIRE] and s.state.cards[named(s, GRIMOIRE).id].zone == "p1:battlefield"
    assert s.state.rules.priority == "p1"
    act(s, "p1", **RESOLVE)  # draw five cards: five separate Shabraz triggers (603.2c), each one Alice could respond to
    assert stack_names(s) == [SHABRAZ] * 5 and len(s.state.zones["p1:library"]) == library - 5
    assert s.state.rules.priority == "p1"
    act(s, "p1", **RESOLVE)  # one Shabraz trigger: a counter and 1 life, which triggers the Grimoire (one trigger for the event)
    assert counters(s) == 1 and s.state.players["p1"].life == life + 1
    assert stack_names(s) == [SHABRAZ] * 4 + [GRIMOIRE] and s.state.rules.priority == "p1"
    act(s, "p1", **RESOLVE)  # the Grimoire's trigger draws 1: a new Shabraz trigger on top
    assert stack_names(s) == [SHABRAZ] * 5 and len(s.state.zones["p1:library"]) == library - 6
    assert s.state.rules.winner is None
    check(s)


@pytest.mark.parametrize("kind", ["dummy", "two"])
def test_resolve_all_stops_when_a_drawn_instant_could_answer_and_the_instant_ends_the_loop(cards, kind):
    s = table(cards, kind)
    mountain = next(c for c in s.state.cards.values() if c.name == "Mountain" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[mountain.id], to={"player": "p1", "zone": "battlefield"})  # {R} open
    in_library_at(s, "Lightning Bolt", 3)  # drawn by the enters trigger (Shabraz is still a 3/3: its triggers wait on the stack)
    hold_and_cast_grimoire(s)
    act(s, "p1", **RESOLVE_ALL)  # RESOLVE ALL: it would pass straight through the loop…
    # …but the Bolt arrived in Alice's hand with {R} open: the passing stops and she has priority with the chain still going
    assert "Lightning Bolt" in hand(s) and s.state.rules.priority == "p1" and s.state.zones.get("stack")
    assert s.state.rules.prefs["p1"].pass_until is None and s.state.rules.winner is None
    drawn = len(s.state.zones["p1:hand"])
    assert drawn == 5 and len(s.state.zones["stack"]) == 5  # (it stopped where the Bolt was drawn: the five Shabraz triggers wait)
    act(s, "p1", type="cast_spell", card_id=named(s, "Lightning Bolt").id, targets=[named(s, SHABRAZ).id])
    for _ in range(40):  # the Bolt resolves first; then the triggers already waiting, which no longer draw anything that triggers
        if not s.state.zones.get("stack"):
            break
        act(s, "p1", **RESOLVE)
    assert not s.state.zones.get("stack") and s.state.cards[named(s, SHABRAZ).id].zone == "p1:graveyard"
    assert s.state.rules.winner is None and s.state.zones["p1:library"]  # the loop is over: no loss to an empty library
    view = json.dumps(s.view("p1"))
    assert "pass_hand" not in view  # (the hand when a pass began is never in a view)
    check(s)


def test_swords_to_plowshares_drawn_mid_chain_stops_resolve_all_too(cards):
    s = table(cards, "dummy")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
    in_library_at(s, "Swords to Plowshares", 6)
    hold_and_cast_grimoire(s)
    act(s, "p1", **RESOLVE_ALL)
    assert "Swords to Plowshares" in hand(s) and s.state.rules.priority == "p1" and s.state.zones.get("stack")
    act(s, "p1", type="cast_spell", card_id=named(s, "Swords to Plowshares").id, targets=[named(s, SHABRAZ).id])
    for _ in range(60):
        if not s.state.zones.get("stack"):
            break
        act(s, "p1", **RESOLVE)
    assert s.state.cards[named(s, SHABRAZ).id].zone.endswith("exile") and not s.state.zones.get("stack")
    assert s.state.rules.winner is None and s.state.zones["p1:library"]
    check(s)


@pytest.mark.parametrize("kind", ["dummy", "two"])
def test_a_runaway_chain_stops_after_a_bounded_number_of_resolutions(cards, kind):
    s = table(cards, kind)  # no mana open: nothing to respond with, so every automatic pass goes through
    library = len(s.state.zones["p1:library"])
    act(s, "p1", type="cast_spell", card_id=named(s, GRIMOIRE).id)  # (passes after the cast, Arena style: the chain begins)
    assert s.state.rules.winner is None and s.state.zones.get("stack") and s.state.rules.priority == "p1"
    first = library - len(s.state.zones["p1:library"])
    assert 0 < first <= LOOP_RESOLUTIONS
    assert any("This keeps repeating: " in json.dumps(e) for e in s.view("p1")["log"][-5:])
    act(s, "p1", **RESOLVE_ALL)  # RESOLVE ALL: another round, bounded the same way
    second = library - len(s.state.zones["p1:library"])
    assert s.state.rules.winner is None and s.state.zones.get("stack") and first < second <= first + LOOP_RESOLUTIONS
    act(s, "p1", type="pass_priority")  # a plain pass too
    assert s.state.rules.winner is None and s.state.zones.get("stack")
    assert library - len(s.state.zones["p1:library"]) <= second + LOOP_RESOLUTIONS
    check(s)


def test_a_lone_spell_still_resolves_with_one_press_and_play_goes_on(cards):
    s = table(cards, "two")
    act(s, "p1", type="move", card_ids=[named(s, "Lightning Bolt").id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=named(s, "Lightning Bolt").id, targets=["p2"])
    act(s, "p1", type="set_prefs", hold_priority=False)
    act(s, "p1", **RESOLVE)  # Bob has nothing: auto-passed; the Bolt resolves; the stack is empty: Alice's usual main-phase stop
    assert s.state.players["p2"].life == 37 and not s.state.zones.get("stack")
    assert (s.state.turn.phase, s.state.rules.priority) == ("main1", "p1") and s.state.rules.prefs["p1"].pass_until is None
    check(s)


def test_resolve_with_an_emptied_stack_follows_the_usual_stops_like_a_plain_pass(cards):
    """Bolt in the beginning of combat (no stop there): RESOLVE and a plain pass end up at the same place once the stack is empty."""
    from tests.test_rules_wave30m_durations import to_phase

    ends = []
    for press in (RESOLVE, {"type": "pass_priority"}):
        s = table(cards, "two")
        act(s, "p1", type="move", card_ids=[named(s, "Lightning Bolt").id], to={"zone": "hand"})
        act(s, "p1", type="set_prefs", hold_priority=True, stops_my_turn=["main1", "main2", "begin_combat"])
        to_phase(s, "begin_combat")
        act(s, "p1", type="set_prefs", stops_my_turn=["main1", "main2"])
        act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
        act(s, "p1", type="cast_spell", card_id=named(s, "Lightning Bolt").id, targets=["p2"])
        act(s, "p1", type="set_prefs", hold_priority=False)
        act(s, "p1", **press)
        assert s.state.players["p2"].life == 37
        ends.append((s.state.turn.number, s.state.turn.phase, s.state.rules.priority, (s.state.rules.decision or None) and s.state.rules.decision.kind))
    assert ends[0] == ends[1]
