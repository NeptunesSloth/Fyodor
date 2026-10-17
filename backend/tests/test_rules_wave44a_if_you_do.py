"""Wave 44A: commanders whose only blocker was one "if you do" / "this way" line (CR 2026-09-25), real Oracle text
(tests/fixtures/wave44a_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 701.? exile-until in every library: "each player exiles cards from the top of their library until they exile a nonland card. You may cast any number of spells
  from among the nonland cards exiled this way without paying their mana costs." (Etali, Primal Conqueror; Fevered Suspicion): each library is read on its own
  (no single "found" card), every card exiled (lands too, which are never cast, 305.1) is among the cards exiled this way (608.2g: each cast is made as this resolves).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_effects import pass_until_stack_empty
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave44a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w44a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
ETALI, SUSPICION = "Etali, Primal Conqueror // Etali, Primal Sickness", "Fevered Suspicion"
FULL = [ETALI, SUSPICION]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def stack_top(s, names, pid="p1"):
    """Put these cards on top of the library, the first named on top."""
    ids = []
    for name in reversed(names):
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library" and c.id not in ids)
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")
        ids.insert(0, c.id)
    assert zone(s.state, pid, "library")[: len(names)] == ids
    return ids


def decision(s, step=None):
    d = s.state.rules.decision
    assert d is not None, "no decision"
    if step is not None:
        assert (d.resume or {}).get("step") == step, (d.resume or {}).get("step")
    return d


def choose(s, ids, *, resolve=False):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    if resolve:
        pass_until_stack_empty(s)


def cast_etali(s):
    to_hand(s, ETALI)
    mana(s, R=2, C=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, ETALI).id)
    pass_until_stack_empty(s)  # (Etali resolves, its enters trigger goes on the stack and resolves up to the first choice)


# ---- exile until, every library (Etali, Primal Conqueror; Fevered Suspicion) -------------------------------------------------------------------------
def test_etali_exiles_until_a_nonland_in_each_library_and_casts_any_number_of_them_free(cards):
    s = build(cards, [ETALI, "Grizzly Bears", "Lightning Bolt"], ["Grizzly Bears", "Lightning Bolt"])
    mine = stack_top(s, ["Forest", "Grizzly Bears", "Forest"])
    theirs = stack_top(s, ["Island", "Island", "Lightning Bolt", "Island"], pid="p2")
    cast_etali(s)
    d = decision(s, "free_cast_pick")
    assert {o.id for o in d.options} == {mine[1], theirs[2]}  # (the lands exiled with them are never offered)
    assert all(s.state.cards[c].zone.endswith(":exile") for c in (*mine[:2], *theirs[:3]))
    assert s.state.cards[mine[2]].zone == "p1:library" and s.state.cards[theirs[3]].zone == "p2:library"
    choose(s, [theirs[2]])
    choose(s, ["p1"])  # (Lightning Bolt: Alice hits herself or Bob, either way it is the free cast)
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")
    assert [o.id for o in d.options] == [mine[1]]
    choose(s, [mine[1]], resolve=True)
    assert s.state.cards[mine[1]].zone == "p1:battlefield" and s.state.cards[theirs[2]].zone == "p2:graveyard"
    assert all(s.state.cards[c].zone.endswith(":exile") for c in (mine[0], theirs[0], theirs[1]))
    check(s)


def test_etali_casts_nothing_when_she_declines(cards):
    s = build(cards, [ETALI, "Grizzly Bears"], ["Grizzly Bears"])
    mine = stack_top(s, ["Grizzly Bears", "Forest"])
    theirs = stack_top(s, ["Grizzly Bears", "Island"], pid="p2")
    cast_etali(s)
    decision(s, "free_cast_pick")
    choose(s, [])
    pass_until_stack_empty(s)
    assert s.state.rules.decision is None
    assert s.state.cards[mine[0]].zone.endswith(":exile") and s.state.cards[theirs[0]].zone.endswith(":exile")
    check(s)


def test_etali_exiles_a_whole_library_that_has_no_nonland_card_and_casts_from_the_other(cards):
    s = build(cards, [ETALI, "Grizzly Bears"], [])
    mine = stack_top(s, ["Forest", "Grizzly Bears"])
    cast_etali(s)
    d = decision(s, "free_cast_pick")
    assert [o.id for o in d.options] == [mine[1]]
    assert zone(s.state, "p2", "library") == []  # (ten Islands: no nonland card to stop at)
    choose(s, [mine[1]], resolve=True)
    assert s.state.cards[mine[1]].zone == "p1:battlefield"
    check(s)


def test_fevered_suspicion_exiles_from_each_opponent_and_casts_their_nonlands(cards):
    s = build(cards, [SUSPICION], ["Island", "Grizzly Bears"])
    theirs = stack_top(s, ["Island", "Grizzly Bears", "Island"], pid="p2")
    to_hand(s, SUSPICION)
    mana(s, B=1, R=1, C=6)
    act(s, "p1", type="cast_spell", card_id=card_named(s, SUSPICION).id)
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")
    assert [o.id for o in d.options] == [theirs[1]]
    choose(s, [theirs[1]], resolve=True)
    assert s.state.cards[theirs[1]].zone == "p1:battlefield" and s.state.cards[theirs[1]].controller == "p1"
    assert s.state.cards[theirs[0]].zone.endswith(":exile") and s.state.cards[theirs[2]].zone == "p2:library"
    check(s)
