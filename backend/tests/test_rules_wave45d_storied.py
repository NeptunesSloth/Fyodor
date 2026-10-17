"""Wave 45D: Storied and the enduring story designation (CR 702.195, 2026-09-25; rulings of 2026-06-29), real Oracle text
(tests/fixtures/wave45d_storied_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 702.195a/b: three permanents that are artifacts, Sagas and/or legendary and a permanent with storied give the player the designation for the rest of the game.
* The commanders Thorin, Fíli, Óin, Ori, Bombur, Dáin and Bifur read "as long as you have an enduring story".
* 702.195c: the designation is gained before triggers are checked (Bifur entering as the third permanent triggers his own ability twice).
* A state-based action is checked after a rules intent, not after a table move: a scenario casts the last permanent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import combat_rules, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand
from tests.wave9c_kit import cast as cast_card

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave45d_storied_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w45d", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
THORIN, FILI, OIN, BOMBUR, ORI = "Thorin Oakenshield", "Fíli the Pathfinder", "Óin the Brave", "Bombur, Gentle Dreamer", "Ori, Keeper of Songs"
DAIN, BIFUR = "Dáin, Lord of the Iron Hills", "Bifur, Melodic Rider"
FULL = [THORIN, FILI, OIN, BOMBUR, ORI, DAIN, BIFUR]


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


def cast(s, name, pid="p1"):
    to_hand(s, name, pid)
    cast_card(s, name, pid)


def story(s, pid="p1"):
    return pid in s.state.rules.enduring_story


def counters(s):
    return sum(c.counters.get("+1/+1", 0) for c in s.state.cards.values() if c.zone.endswith("battlefield"))


# ---- 702.195a: three artifacts / Sagas / legendaries and a storied permanent -----------------------------------------------------------------------------
def test_the_third_permanent_with_a_storied_one_gives_the_designation_and_the_anthem(cards):
    s = build(cards, [FILI, "Sol Ring", "Mind Stone", "Wall of Omens"], [])
    put(s, "Wall of Omens")
    put(s, FILI)
    put(s, "Sol Ring")
    (fp, ft), (wp, wt) = pt(s, FILI), pt(s, "Wall of Omens")
    mana(s, G=2)
    cast(s, "Mind Stone")  # Fíli is legendary: Fíli, Sol Ring and Mind Stone are three (the Wall isn't one)
    assert story(s) and not story(s, "p2")
    assert pt(s, FILI) == (fp + 1, ft + 1) and pt(s, "Wall of Omens") == (wp + 1, wt + 1)
    check(s)


def test_three_artifacts_without_a_storied_permanent_are_no_story_until_one_arrives(cards):
    s = build(cards, ["Sol Ring", "Mind Stone", "Arcane Signet", ORI], [])
    put(s, "Sol Ring")
    put(s, "Mind Stone")
    mana(s, G=1)
    cast(s, "Arcane Signet")
    assert not story(s)  # ruling 2026-06-29: three artifacts, but no permanent with storied
    mana(s, W=1, G=2)
    cast(s, ORI)
    assert story(s) and pt(s, ORI)[0] == 4  # Ori is 3/x: the +1/+0
    check(s)


def test_the_designation_stays_after_the_permanents_leave(cards):
    s = build(cards, [ORI, "Sol Ring", "Mind Stone"], [])
    put(s, "Sol Ring")
    put(s, "Mind Stone")
    mana(s, W=1, G=2)
    cast(s, ORI)
    assert story(s)
    for n in ("Sol Ring", "Mind Stone"):
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"zone": "graveyard"})
    assert story(s) and pt(s, ORI)[0] == 4  # "for the rest of the game" (702.195b): Ori keeps +1/+0
    check(s)


def test_two_qualifying_permanents_are_not_three(cards):
    s = build(cards, [ORI, "Sol Ring", "Wall of Omens"], [])
    put(s, "Sol Ring")
    put(s, "Wall of Omens")
    mana(s, W=1, G=2)
    cast(s, ORI)
    assert not story(s) and pt(s, ORI)[0] == 3  # Sol Ring and Ori (legendary): the Wall isn't an artifact, a Saga or legendary
    check(s)


def test_thorin_gives_ward_and_bombur_stops_untapping_only_without_the_story(cards):
    s = build(cards, [THORIN, BOMBUR, "Sol Ring", "Mind Stone"], [])
    put(s, BOMBUR)
    put(s, "Sol Ring")
    wards = lambda n: any(a.text == "Ward {1}" for a in Plan(s.state, "p1", s.cards, None).ch(card_named(s, n)).abilities)  # noqa: E731
    stuck = lambda: "doesnt_untap" in Plan(s.state, "p1", s.cards, None).ch(card_named(s, BOMBUR)).imposed  # noqa: E731
    assert stuck() and not wards("Sol Ring")
    mana(s, R=1, W=1)
    cast(s, THORIN)  # Bombur, Sol Ring, Thorin: three legendary or artifact permanents
    assert story(s) and wards("Sol Ring") and wards(BOMBUR) and not stuck()  # 702.195a, 614.9: "unless you have an enduring story"
    check(s)


# ---- 702.195c, 603.2d: the designation comes before the triggers are checked ---------------------------------------------------------------------------
def test_bifur_entering_as_the_third_permanent_triggers_his_own_ability_twice(cards):
    s = build(cards, [BIFUR, "Sol Ring", "Mind Stone", "Wall of Omens"], [])
    put(s, "Sol Ring")
    put(s, "Mind Stone")
    put(s, "Wall of Omens")
    mana(s, W=2, G=4)
    cast(s, BIFUR)
    assert story(s) and counters(s) == 2  # "If Bifur entering causes you to have an enduring story, his ability triggers an additional time"
    check(s)


def test_bifur_triggers_once_without_the_story(cards):
    s = build(cards, [BIFUR, "Wall of Omens"], [])
    put(s, "Wall of Omens")
    mana(s, W=2, G=4)
    cast(s, BIFUR)
    assert not story(s) and counters(s) == 1
    check(s)


# ---- Dáin: the attack tax only while the designation is there -------------------------------------------------------------------------------------------
def test_dain_taxes_attackers_once_its_controller_has_the_story(cards):
    s = build(cards, ["Llanowar Elves"], [DAIN, "Sol Ring", "Mind Stone"])
    put(s, DAIN, "p2")
    put(s, "Sol Ring", "p2")
    elves = to_hand(s, "Llanowar Elves")
    p = Plan(s.state, "p1", s.cards, None)
    assert combat_rules.attack_cost(p, [(elves.id, "p2")]) == ""  # Dáin and Sol Ring: two permanents of three
    put(s, "Mind Stone", "p2")
    mana(s, G=1)
    cast_card(s, "Llanowar Elves")  # any rules intent checks the state-based actions: Bob has the story now
    assert story(s, "p2") and not story(s)
    p = Plan(s.state, "p1", s.cards, None)
    assert combat_rules.attack_cost(p, [(elves.id, "p2")]) == "{1}"
    check(s)
