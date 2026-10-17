"""Wave 50C: modal triggered and activated abilities of commanders (CR 2026-09-25), real Oracle text (tests/fixtures/wave50c_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 700.2d / Shadrix's ruling (2021-04-16): "you may choose two. Each mode must target a different player." - zero modes or exactly two, never one.
* 608.2c / 700.2: a mode that opens with "If" (Venser, Corpse Puppet) is a condition of that mode, checked as the ability resolves, not an
  intervening "if" of the trigger; "If a source would deal damage … this turn, it deals that much damage plus 2 instead" (Rankle and Torbran)
  is a replacement effect for the rest of the turn (611.2a), not a condition.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave33b_modal import settle, stops, to_phase
from tests.wave9c_kit import build, check, put

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50c", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def board(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:battlefield"]


def counters(s, name, pid="p1"):
    return sum(c.counters.get("+1/+1", 0) for c in board(s, name, pid))


# --- Shadrix Silverquill: "you may choose two" ---------------------------------------------------------------------------------------------


def test_shadrix_two_modes_for_two_different_players(cards):
    s = build(cards, ["Shadrix Silverquill", "Grizzly Bears"], ["Grizzly Bears"])
    put(s, "Shadrix Silverquill")
    put(s, "Grizzly Bears", "p1")
    put(s, "Grizzly Bears", "p2")
    stops(s, "begin_combat")
    to_phase(s, "begin_combat", turn=1)
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and (d.min_choices, d.max_choices) == (0, 2)
    with pytest.raises(ActionError, match="no mode, or exactly two"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["0:0"])  # one mode is not allowed
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["0:0", "2:0"])  # an Inkling for one player, counters for the other
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p1"])
    d = s.state.rules.decision
    assert "p1" not in [o.id for o in d.options]  # the second mode: a player the first doesn't target
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    settle(s)
    assert [c.name for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"] == ["Inkling"]
    assert counters(s, "Grizzly Bears", "p2") == 1 and counters(s, "Grizzly Bears", "p1") == 0
    check(s)


def test_shadrix_may_choose_no_mode(cards):
    s = build(cards, ["Shadrix Silverquill"])
    put(s, "Shadrix Silverquill")
    stops(s, "begin_combat")
    to_phase(s, "begin_combat", turn=1)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert not [c for c in s.state.cards.values() if c.is_token]
    check(s)
