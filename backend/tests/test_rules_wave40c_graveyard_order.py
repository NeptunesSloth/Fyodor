"""Wave 40C: the order of a graveyard (CR 2026-09-25), real Oracle text (tests/fixtures/wave40c_graveyard_order_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 404.3: "If an effect or rule puts two or more cards into the same graveyard at the same time, the owner of those cards may arrange them
  in any order." The owner is asked only when a card on the table reads a graveyard's order (Barrow Ghoul: "the top creature card of your
  graveyard") or they set "always ask me" (a reader in their hand: Shallow Grave); otherwise the engine keeps its order and asks nothing.
* The question names the cards to its owner only (the others see that a player is choosing).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.visibility import SPECTATOR
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, mana, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave40c_graveyard_order_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w40c", number=f"G{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def run(s, limit=40):
    """Pass priority until a decision is pending or the stack is empty; the decision (or None)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            return d
        if not s.state.zones.get("stack"):
            return None
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never settled")


def pyroclasm(cards, board, hand=(), pref=False, theirs=()):
    """Alice has ``board`` on the battlefield (and Bob ``theirs``) and ``hand`` in her hand, and casts Pyroclasm: the question it leaves."""
    names = ["Pyroclasm", "Grizzly Bears", "Llanowar Elves", "Barrow Ghoul", "Shallow Grave", "Necratog", "Perpetual Timepiece"]
    s = build(cards, mine=names, theirs=["Grizzly Bears", "Llanowar Elves", "Rest in Peace"])
    if pref:
        act(s, "p1", type="set_prefs", ask_graveyard_order=True)
    for name in board:
        put(s, name)
    for name in theirs:
        put(s, name, "p2")
    for name in hand:
        to_hand(s, name)
    to_hand(s, "Pyroclasm")
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Pyroclasm").id)
    return s, run(s)


def yard(s, pid="p1"):
    """The graveyard, bottom to top, by name."""
    return [s.state.cards[c].name for c in s.state.zones[f"{pid}:graveyard"]]


def answer(s, *names, pid="p1"):
    """Answer the open question: these cards (of ``pid``), the first ends up on top."""
    d = s.state.rules.decision
    assert d is not None and d.kind == "order" and d.player == pid
    ids = [card_named(s, n, pid).id for n in names]
    act(s, pid, type="choose", decision_id=d.id, option_ids=ids)


def test_a_reader_on_the_battlefield_asks_the_owner_and_the_order_holds(cards):
    # Barrow Ghoul survives (4/4) and reads "the top creature card of your graveyard": Bears and Elves die together (404.3)
    s, d = pyroclasm(cards, ["Grizzly Bears", "Llanowar Elves", "Barrow Ghoul"])
    assert d is not None and d.kind == "order" and d.player == "p1" and d.min_choices == d.max_choices == 2
    assert {o.label for o in d.options} == {"Grizzly Bears", "Llanowar Elves"}
    assert s.state.rules.priority is None  # (before anyone may act)
    check(s)
    answer(s, "Llanowar Elves", "Grizzly Bears")  # the first chosen ends up on top
    assert yard(s) == ["Pyroclasm", "Grizzly Bears", "Llanowar Elves"] and s.state.rules.decision is None
    assert s.state.rules.pending_gy_order == []
    check(s)


def test_the_other_order_holds_too(cards):
    s, _ = pyroclasm(cards, ["Grizzly Bears", "Llanowar Elves", "Barrow Ghoul"])
    answer(s, "Grizzly Bears", "Llanowar Elves")
    assert yard(s) == ["Pyroclasm", "Llanowar Elves", "Grizzly Bears"]
    check(s)


def test_a_save_while_the_question_is_open(cards):
    s, d = pyroclasm(cards, ["Grizzly Bears", "Llanowar Elves", "Barrow Ghoul"])
    again = reloaded(s)
    assert again.state.rules.decision is not None and again.state.rules.decision.id == d.id
    assert again.state.rules.pending_gy_order == s.state.rules.pending_gy_order == []  # (asked: no longer waiting to be asked)
    answer(again, "Llanowar Elves", "Grizzly Bears")
    assert yard(again) == ["Pyroclasm", "Grizzly Bears", "Llanowar Elves"]
    check(again)


def test_without_a_reader_nothing_is_asked(cards):
    s, d = pyroclasm(cards, ["Grizzly Bears", "Llanowar Elves"])
    assert d is None and sorted(yard(s)[1:]) == ["Grizzly Bears", "Llanowar Elves"] and yard(s)[0] == "Pyroclasm"
    assert yard(s) == yard(pyroclasm(cards, ["Grizzly Bears", "Llanowar Elves"])[0])  # (deterministic)
    assert s.state.rules.pending_gy_order == []
    check(s)


def test_one_card_has_no_order_to_arrange(cards):
    s, d = pyroclasm(cards, ["Grizzly Bears", "Barrow Ghoul"], pref=True)
    assert d is None and yard(s) == ["Pyroclasm", "Grizzly Bears"]
    check(s)


def test_a_reader_that_dies_with_them_still_counts(cards):
    # Necratog (1/2) is a reader on the battlefield as the damage is dealt: it is in the batch
    s, d = pyroclasm(cards, ["Grizzly Bears", "Necratog"])
    assert d is not None and {o.label for o in d.options} == {"Grizzly Bears", "Necratog"}
    answer(s, "Necratog", "Grizzly Bears")
    assert yard(s) == ["Pyroclasm", "Grizzly Bears", "Necratog"]
    check(s)


def test_a_reader_in_hand_asks_only_if_the_owner_said_so(cards):
    s, d = pyroclasm(cards, ["Grizzly Bears", "Llanowar Elves"], hand=["Shallow Grave"])  # preference off
    assert d is None and s.state.rules.decision is None
    check(s)
    s, d = pyroclasm(cards, ["Grizzly Bears", "Llanowar Elves"], hand=["Shallow Grave"], pref=True)
    assert d is not None and d.player == "p1"
    answer(s, "Grizzly Bears", "Llanowar Elves")
    assert yard(s) == ["Pyroclasm", "Llanowar Elves", "Grizzly Bears"]
    check(s)


def test_others_see_a_question_but_never_its_options(cards):
    s, d = pyroclasm(cards, ["Grizzly Bears", "Llanowar Elves"], hand=["Shallow Grave"], pref=True)
    mine = s.view("p1")["rules"]["decision"]
    assert mine["kind"] == "order" and {o["label"] for o in mine["options"]} == {"Grizzly Bears", "Llanowar Elves"}
    for viewer in ("p2", SPECTATOR):
        seen = s.view(viewer)["rules"]["decision"]
        assert seen["kind"] == "waiting" and "options" not in seen and seen["prompt"] == "Alice is making a choice"
        shown = json.dumps(s.view(viewer)["rules"])  # (nor Alice's preference, the batch waiting to be asked, or what her hand holds)
        assert '"ask_graveyard_order": true' not in shown and "pending_gy_order" not in shown and "Shallow Grave" not in shown
    # a player who didn't ask for it is not asked, so nothing tells the table what a hand holds
    quiet, none = pyroclasm(cards, ["Grizzly Bears", "Llanowar Elves"], hand=["Shallow Grave"])
    assert none is None and quiet.view("p2")["rules"]["decision"] is None


def test_each_owner_arranges_their_own_cards_active_player_first(cards):
    s, d = pyroclasm(cards, ["Grizzly Bears", "Llanowar Elves", "Barrow Ghoul"], theirs=["Grizzly Bears", "Llanowar Elves"])
    assert d is not None and d.player == "p1"
    answer(s, "Grizzly Bears", "Llanowar Elves")
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and {o.label for o in d.options} == {"Grizzly Bears", "Llanowar Elves"}
    again = reloaded(s)  # (a save between the two questions)
    answer(again, "Llanowar Elves", "Grizzly Bears", pid="p2")
    assert yard(again) == ["Pyroclasm", "Llanowar Elves", "Grizzly Bears"] and yard(again, "p2") == ["Grizzly Bears", "Llanowar Elves"]
    check(again)


def test_arranging_a_graveyard_is_no_zone_change(cards):
    # Rest in Peace arrives (by hand) while the question is open: arranging the cards already in the graveyard doesn't exile them
    s, d = pyroclasm(cards, ["Grizzly Bears", "Llanowar Elves", "Barrow Ghoul"])
    assert d is not None
    put(s, "Rest in Peace", "p2")
    answer(s, "Grizzly Bears", "Llanowar Elves")
    assert yard(s) == ["Pyroclasm", "Llanowar Elves", "Grizzly Bears"] and not s.state.zones.get("p1:exile")
    check(s)


def test_a_mill_is_arranged_too(cards):
    s = build(cards, mine=["Perpetual Timepiece", "Grizzly Bears", "Llanowar Elves"])
    act(s, "p1", type="set_prefs", ask_graveyard_order=True)
    put(s, "Perpetual Timepiece")
    for name in ("Llanowar Elves", "Grizzly Bears"):  # the Bears on top
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"player": "p1", "zone": "library"}, position="top")
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Perpetual Timepiece").id, ability=0)
    d = run(s)
    assert d is not None and d.kind == "order" and yard(s) == ["Grizzly Bears", "Llanowar Elves"]
    answer(s, "Grizzly Bears", "Llanowar Elves")  # the first chosen ends up on top
    assert yard(s) == ["Llanowar Elves", "Grizzly Bears"]
    check(s)


def test_blockers_that_die_in_combat_are_arranged_by_their_owner(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, turn_on

    mine = deck(cards, "Krenko, Mob Boss", [(1, "Barrow Ghoul"), (1, "Llanowar Elves"), (9, "Forest")])
    theirs = deck(cards, "Atraxa, Praetors' Voice", [(1, "Grizzly Bears"), (1, "Llanowar Elves"), (9, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=mine), PlayerSetup("Bob", cards=theirs)], shuffle=False), cards=cards)
    for name, pid in (("Barrow Ghoul", "p1"), ("Grizzly Bears", "p2"), ("Llanowar Elves", "p2")):
        act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"player": pid, "zone": "battlefield"})
    fodder = card_named(s, "Llanowar Elves", "p1")  # (for the Ghoul's upkeep: "sacrifice it unless you exile the top creature card of your graveyard")
    act(s, "p1", type="move", card_ids=[fodder.id], to={"player": "p1", "zone": "graveyard"})
    turn_on(s)  # (the creatures were there before)
    for _ in range(12):  # Alice's upkeep (the Ghoul exiles her Elves and stays), then on to combat: Alice declares attackers
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.card_id == fodder.id])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[fodder.id].zone == "p1:exile"
    ghoul = card_named(s, "Barrow Ghoul")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ghoul.id, "target": "p2"}])
    blocks = [{"blocker_id": card_named(s, n, "p2").id, "attacker_id": ghoul.id} for n in ("Grizzly Bears", "Llanowar Elves")]
    act(s, "p2", type="declare_blockers", blocks=blocks)
    d = s.state.rules.decision
    assert d is not None and d.kind == "divide"  # (510.1c: Alice divides the Ghoul's 4 damage; 2 + 1 are lethal, it survives 3)
    act(s, "p1", type="choose", decision_id=d.id, amounts=[3, 1] if d.options[0].label == "Grizzly Bears" else [1, 3])
    d = run(s)
    assert d is not None and d.kind == "order" and d.player == "p2" and {o.label for o in d.options} == {"Grizzly Bears", "Llanowar Elves"}
    check(s)
    answer(s, "Grizzly Bears", "Llanowar Elves", pid="p2")
    assert yard(s, "p2") == ["Llanowar Elves", "Grizzly Bears"] and s.state.zones["p1:battlefield"] == [ghoul.id]
    check(s)
