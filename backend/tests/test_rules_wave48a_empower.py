"""Wave 48A: "Empower Jace N" (CR 2026-09-25, 701.71a), real Oracle text (tests/fixtures/wave48a_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 701.71a: if you don't control a Jace planeswalker token, create a blue Jace planeswalker token with 0 loyalty, "[−1]: Surveil 1" and "[−3]: Draw a card."; choose a
  Jace planeswalker token you control; put N loyalty counters on it. A later empower puts its counters on the token you already have.
* 704.5i: a Jace token that got 0 counters (Empower Jace X with X = 0) has 0 loyalty and is put into the graveyard (a token then ceases to exist, 111.7).
* 606.3: the token's loyalty abilities are the ordinary ones of a planeswalker.
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
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, settle
from tests.wave9c_kit import build, check, mana, put, to_hand
from tests.wave43b_kit import cast, ch, move

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave48a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w48a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
EMPOWER = ["Way of the Necromancer", "Way of the Paradox", "Overwrite the Multiverse", "Plan for All Outcomes", "Way of the Mentor", "Theorist's Proxy",
           "Repurposed Enforcer", "Mindseeker Oculus", "Keeper of the Quiet Hour", "Hexhaven Battalion", "Arcane Amphisbaena", "Inspired Tethermage",
           "Campus Crier"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def jaces(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == "Jace" and c.token is not None and c.controller == pid and c.zone.endswith(":battlefield")]


def loyalty(c):
    return c.counters.get("loyalty", 0)


def test_empower_creates_a_jace_with_the_counters_and_a_second_empower_adds_to_it(cards):
    s = build(cards, ["Way of the Necromancer", "Way of the Paradox"], [])
    to_hand(s, "Way of the Necromancer")
    mana(s, B=1, C=1)
    cast(s, "Way of the Necromancer")
    (jace,) = jaces(s)
    assert loyalty(jace) == 2 and "Planeswalker" in ch(s, jace).types and "Jace" in ch(s, jace).subtypes and set(ch(s, jace).colors) == {"U"}
    to_hand(s, "Way of the Paradox")
    mana(s, G=1, C=2)
    cast(s, "Way of the Paradox")
    (same,) = jaces(s)
    assert same.id == jace.id and loyalty(same) == 7  # 2 + 5: the token you control, not a second one
    check(s)


def test_the_jace_token_loyalty_abilities_work(cards):
    s = build(cards, ["Way of the Necromancer"], [])
    to_hand(s, "Way of the Necromancer")
    mana(s, B=1, C=1)
    cast(s, "Way of the Necromancer")
    (jace,) = jaces(s)
    activate(s, "p1", jace, "Surveil 1")  # -1: Surveil 1.
    settle(s)
    assert loyalty(s.state.cards[jace.id]) == 1
    check(s)


def test_empower_x_counts_what_was_exiled_this_way(cards):
    s = build(cards, ["Overwrite the Multiverse", "Elvish Visionary", "Grizzly Bears"], ["Grizzly Bears"])
    put(s, "Elvish Visionary")
    put(s, "Grizzly Bears")
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Overwrite the Multiverse")
    mana(s, B=2, C=4)
    cast(s, "Overwrite the Multiverse")
    (jace,) = jaces(s)
    assert loyalty(jace) == 3  # three creatures were exiled
    check(s)


def test_empower_x_with_nothing_exiled_makes_a_jace_that_dies_with_0_loyalty(cards):
    s = build(cards, ["Overwrite the Multiverse"], [])
    to_hand(s, "Overwrite the Multiverse")
    mana(s, B=2, C=4)
    cast(s, "Overwrite the Multiverse")
    assert jaces(s) == []  # 704.5i
    check(s)


def test_a_second_empower_chooses_among_several_jace_tokens(cards):
    s = build(cards, ["Way of the Necromancer"], [])
    for _ in range(2):
        act(s, "p1", type="create_token", player="p1", token={"name": "Jace", "colors": ["U"], "type_line": "Token Planeswalker — Jace"})
    first, second = jaces(s)
    for j in (first, second):
        act(s, "p1", type="counter", card_ids=[j.id], kind="loyalty", delta=1)  # (a 0-loyalty planeswalker would be put into the graveyard)
    to_hand(s, "Way of the Necromancer")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Way of the Necromancer"))
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards":
            assert {o.id for o in d.options} == {first.id, second.id}
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[second.id])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    settle(s)
    assert loyalty(s.state.cards[first.id]) == 1 and loyalty(s.state.cards[second.id]) == 3
    check(s)


def test_the_activated_ability_of_campus_crier_empowers_from_the_graveyard(cards):
    s = build(cards, ["Campus Crier"], [])
    move(s, "Campus Crier")
    crier = next(c for c in s.state.cards.values() if c.name == "Campus Crier")
    mana(s, C=1)
    activate(s, "p1", crier, "Empower")
    settle(s)
    (jace,) = jaces(s)
    assert loyalty(jace) == 2
    check(s)
