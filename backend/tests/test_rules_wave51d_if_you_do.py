"""Wave 51D: "if you do" / "this way" lines that blocked commanders (CR 2026-09-25), real Oracle text (tests/fixtures/wave51d_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 118.12 / 115.3 / 702.151a: Stiltzkin - "Target opponent gains control of another target permanent you control. If they do, you draw a card." The first target is a
  player, so "another" is than the source itself (as reconfigure's "another target creature you control"), never Stiltzkin.
* 608.2c / 205.2: Szarekh - "You may put an artifact creature card or Vehicle card from among the cards milled this way into your hand." (an artifact creature, or a
  Vehicle, which is an artifact that is not necessarily a creature).
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
from tests.test_rules_wave34b_activated import activate, attack, next_turn, settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, put, reloaded, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave51d_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w51d", number=f"X{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
STILTZKIN, SZAREKH = "Stiltzkin, Moogle Merchant", "Szarekh, the Silent King"


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", [STILTZKIN, SZAREKH])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- Stiltzkin ---------------------------------------------------------------------------------------------------------------------------
def stiltzkin(cards, others):
    s = build(cards, [STILTZKIN, "Grizzly Bears"], forests=30)
    stilt = put(s, STILTZKIN)
    bears = put(s, "Grizzly Bears")
    next_turn(s)
    mana(s, "p1", G=2)
    return s, stilt, bears


def test_stiltzkin_gives_another_permanent_to_the_opponent_and_draws(cards):
    s, stilt, bears = stiltzkin(cards, [])
    hand = len([c for c in s.state.cards.values() if c.zone == "p1:hand"])
    activate(s, "p1", stilt, targets=["p2", bears.id], target_counts=[1, 1])
    settle(s)
    assert s.state.cards[bears.id].controller == "p2" and s.state.cards[bears.id].owner == "p1"
    assert len([c for c in s.state.cards.values() if c.zone == "p1:hand"]) == hand + 1  # "If they do, you draw a card."
    check(s)


def test_stiltzkin_cannot_give_itself_away(cards):
    """"another": Stiltzkin is not a legal second target of its own ability (the source is not "another" permanent)."""
    s, stilt, bears = stiltzkin(cards, [])
    with pytest.raises(Exception):
        activate(s, "p1", stilt, targets=["p2", stilt.id], target_counts=[1, 1])
    assert s.state.cards[stilt.id].controller == "p1" and not s.state.zones.get("stack")
    check(s)


# -- Szarekh -----------------------------------------------------------------------------------------------------------------------------
def szarekh(cards, top):
    s = build(cards, [SZAREKH, "Ornithopter", "Smuggler's Copter", "Grizzly Bears", "Hill Giant"], forests=30)
    sz = put(s, SZAREKH)
    for name in [*top, "Grizzly Bears"]:  # (the last one on top is drawn in the draw step; the three below it are milled)
        c = card_named(s, name)
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "library"}, position="top")
    stops(s)
    next_turn(s)
    attack(s, sz)
    return s


def drive(s, pick):
    for _ in range(60):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack") and s.state.turn.phase in ("end_combat", "main2", "end"):
                return
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            names = {o.id: s.state.cards[o.id].name for o in d.options if o.id in s.state.cards}
            ids = [i for i, n in names.items() if n in pick]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids[: max(1, d.min_choices)] if ids else [])
    raise AssertionError("never settled")


@pytest.mark.parametrize("take", ["Ornithopter", "Smuggler's Copter"])
def test_szarekh_takes_an_artifact_creature_or_a_vehicle_from_the_milled_cards(cards, take):
    s = szarekh(cards, ["Hill Giant", "Ornithopter", "Smuggler's Copter"])
    drive(s, {take})
    assert zone_of(s, take) == "p1:hand" and zone_of(s, "Grizzly Bears") == "p1:hand"
    assert zone_of(s, "Hill Giant") == "p1:graveyard"  # a plain creature is not one of the cards it may take
    check(s)


def test_szarekh_declined_takes_nothing(cards):
    s = szarekh(cards, ["Hill Giant", "Ornithopter", "Smuggler's Copter"])
    drive(s, set())
    assert zone_of(s, "Ornithopter") == "p1:graveyard" and zone_of(s, "Smuggler's Copter") == "p1:graveyard"
    check(s)
