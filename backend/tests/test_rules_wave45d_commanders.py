"""Wave 45D: commanders with two blocking lines (CR 2026-09-25), real Oracle text (tests/fixtures/wave45d_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 601.3b/601.3d: "You may cast legendary spells and artifact spells as though they had flash." (Gandalf the White, Liberator): a spell of either kind.
* 603.4: Liberator's intervening "if the amount of mana spent to cast that spell is greater than Liberator's power" (the amount actually spent: ruling 2022-10-14).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.casting import cast_problem
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import pass_until_stack_empty
from tests.test_rules_wave34b_activated import to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave45d_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w45d", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
GANDALF, LIBERATOR, RESHAPER = "Gandalf the White", "Liberator, Urza's Battlethopter", "Matter Reshaper"
FULL = [GANDALF, LIBERATOR]


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


def problem(s, name):
    """Why Alice can't cast this card from her hand right now, or None."""
    c = to_hand(s, name)
    plan = Plan(s.state, "p1", s.cards, None)
    return cast_problem(s.state, "p1", c, plan.ch(c), info=plan.info, check_priority=False)


# ---- 601.3b: a spell of either kind may be cast as though it had flash ---------------------------------------------------------------------------------
def test_gandalf_lets_legendary_and_artifact_spells_but_no_others_be_cast_at_instant_speed(cards):
    s = build(cards, [GANDALF, "Thorin Oakenshield", "Sol Ring", "Grizzly Bears", "Mind Stone"], [])
    to_phase(s, "main1", turn=2)  # Bob's turn: Alice can cast only what has flash
    assert problem(s, "Sol Ring")  # (without Gandalf: not now)
    put(s, GANDALF)
    assert problem(s, "Sol Ring") is None  # an artifact
    assert problem(s, "Thorin Oakenshield") is None  # a legendary creature
    assert problem(s, "Grizzly Bears")  # neither
    check(s)


def test_liberator_lets_colorless_and_artifact_spells_but_no_others_be_cast_at_instant_speed(cards):
    s = build(cards, [LIBERATOR, RESHAPER, "Sol Ring", "Grizzly Bears", "Mind Stone"], [])
    to_phase(s, "main1", turn=2)
    assert problem(s, "Sol Ring")
    put(s, LIBERATOR)
    assert problem(s, "Sol Ring") is None and problem(s, RESHAPER) is None  # an artifact; a colorless creature
    assert problem(s, "Grizzly Bears")  # a green creature
    check(s)


# ---- 603.4: Liberator's counter -------------------------------------------------------------------------------------------------------------------
def test_liberator_grows_when_more_mana_than_its_power_was_spent(cards):
    s = build(cards, [LIBERATOR, "Llanowar Elves", "Mind Stone"], [])
    lib = put(s, LIBERATOR)
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Llanowar Elves").id)  # one mana: not greater than its power 1
    pass_until_stack_empty(s)
    assert not s.state.cards[lib.id].counters.get("+1/+1")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Mind Stone").id)  # two mana spent
    pass_until_stack_empty(s)
    assert s.state.cards[lib.id].counters.get("+1/+1") == 1
    assert card_named(s, "Mind Stone").zone == "p1:battlefield"
    check(s)
