"""Wave 51E: Kodama of the East Tree (CR 2026-09-25), real Oracle text (tests/fixtures/wave51e_kodama_cards.json, from data/cards.sqlite). Every scenario
checks the replay and a save and a load.

* 603.4 / 608.2h: "Whenever another permanent you control enters, if it wasn't put onto the battlefield with this ability, you may put a permanent card with
  equal or lesser mana value from your hand onto the battlefield." - the limit is the mana value of the permanent that entered; what Kodama's own ability put
  there doesn't trigger it again (``Entry.via``), what anything else put there does.
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
from tests.test_rules_wave34b_activated import ask, settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave51e_kodama_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w51k", number=f"K{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
KODAMA = "Kodama of the East Tree"


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_kodama_is_full(cards):
    assert coverage.of_card_data(cards.resolve(KODAMA)).level == "FULL"


def choose(s, *ids):
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards", d
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))


def cast(s, name):
    to_hand(s, name)
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, name).id)


def test_kodama_puts_a_card_of_equal_or_lesser_mana_value_and_not_again_for_that_card(cards):
    s = build(cards, [KODAMA, "Grizzly Bears", "Albino Troll", "Young Wolf", "Phantasmal Forces"], [])
    put(s, KODAMA)
    for n in ("Albino Troll", "Young Wolf", "Phantasmal Forces"):
        to_hand(s, n)
    cast(s, "Grizzly Bears")  # mana value 2 enters
    d = ask(s)
    if d.min_choices == 0 and {o.id for o in d.options} == {"yes", "no"}:  # (the "you may" first)
        choose(s, "yes")
        d = ask(s)
    assert d.player == "p1" and d.min_choices == 0
    assert {o.id for o in d.options} == {card_named(s, "Albino Troll").id, card_named(s, "Young Wolf").id}  # mana value 2 or less; the 4 stays out
    choose(s, card_named(s, "Albino Troll").id)
    settle(s, answer="no")
    assert zone_of(s, "Albino Troll") == "p1:battlefield"
    assert zone_of(s, "Young Wolf") == "p1:hand" and s.state.rules.decision is None  # put by Kodama's ability: it doesn't trigger Kodama again
    check(s)


def test_kodama_triggers_again_for_a_permanent_something_else_put_there(cards):
    s = build(cards, [KODAMA, "Grizzly Bears", "Young Wolf", "Albino Troll"], [])
    put(s, KODAMA)
    to_hand(s, "Young Wolf")
    cast(s, "Grizzly Bears")
    d = ask(s)
    if {o.id for o in d.options} == {"yes", "no"}:
        choose(s, "yes")
        d = ask(s)
    choose(s)  # put nothing: Young Wolf stays in hand
    settle(s, answer="no")
    assert zone_of(s, "Young Wolf") == "p1:hand" and zone_of(s, "Grizzly Bears") == "p1:battlefield"
    cast(s, "Albino Troll")  # a permanent Kodama's ability didn't put there: it triggers
    d = ask(s)
    assert d is not None and d.player == "p1"
    check(s)
