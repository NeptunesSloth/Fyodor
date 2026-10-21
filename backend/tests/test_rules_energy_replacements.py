"""Energy-specific replacements: CR 107.14, 614.5, 616.1 (2026-09-25).

Real Oracle text is retained, including the abilities that remain unsupported.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.rules_state import TurnLog
from app.rules import coverage, replace_grammar
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import REAL, build, put, res, roundtrip, settle

DATA = json.loads((Path(__file__).parent / "fixtures/energy_replacements_cards.json").read_text())


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in [*fixture_cards(), *REAL]}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(c["name"], set_code="erg", number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name,expected", [("Izzet Generatorium", 2), ("Aether Refinery", 2)])
def test_energy_replacement_affects_its_controller(cards, name, expected):
    s = build(cards, [name, "Aether Hub"], bob=((1, "Aether Hub"), (10, "Island")))
    put(s, name, "battlefield")
    act(s, "p1", type="play_land", card_id=put(s, "Aether Hub", "hand").id)
    settle(s)
    assert res(s) == expected
    roundtrip(s)


@pytest.mark.parametrize("name", ["Izzet Generatorium", "Aether Refinery"])
def test_opponents_energy_replacement_does_not_apply(cards, name):
    s = build(cards, ["Aether Hub"], bob=((1, name), (10, "Island")))
    put(s, name, "battlefield", "p2")
    act(s, "p1", type="play_land", card_id=put(s, "Aether Hub", "hand").id)
    settle(s)
    assert res(s) == 1 and res(s, "p2") == 0
    roundtrip(s)


@pytest.mark.parametrize("name", ["Izzet Generatorium", "Aether Refinery"])
def test_energy_replacement_does_not_change_poison(cards, name):
    s = build(cards, ["Prologue to Phyresis"], bob=((1, name), (10, "Island")))
    put(s, name, "battlefield", "p2")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 2})
    act(s, "p1", type="cast_spell", card_id=put(s, "Prologue to Phyresis", "hand").id)
    settle(s)
    assert res(s, "p2", "poison") == 1
    roundtrip(s)


@pytest.mark.parametrize("answer,expected", [("yes", 3), ("no", 4)])
@pytest.mark.parametrize("adder", ["Izzet Generatorium", "Winding Constrictor"])
def test_affected_player_orders_energy_replacements_and_choice_survives_reload(cards, answer, expected, adder):
    s = build(cards, ["Aether Refinery", adder, "Aether Hub"])
    put(s, "Aether Refinery", "battlefield")
    put(s, adder, "battlefield")
    act(s, "p1", type="play_land", card_id=put(s, "Aether Hub", "hand").id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"
    assert res(s) == 0
    roundtrip(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[answer])
    settle(s)
    assert res(s) == expected
    roundtrip(s)


def test_unknown_energy_replacement_wording_stays_unsupported():
    assert replace_grammar.parse("If you would get one or more {E}, you get three times that many {E} instead.") is None


def test_generatorium_tracks_energy_removed_not_energy_gained(cards):
    s = build(cards, ["Izzet Generatorium"])
    generator = put(s, "Izzet Generatorium", "battlefield")
    assert coverage.of_card_data(cards.resolve("Izzet Generatorium")).level == "FULL"
    act(s, "p1", type="resource", player="p1", key="energy", delta=10)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=generator.id, ability=1)
    act(s, "p1", type="resource", player="p2", key="energy", delta=4)
    act(s, "p1", type="resource", player="p2", key="energy", delta=-4)
    act(s, "p1", type="resource", player="p1", key="energy", delta=-3)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=generator.id, ability=1)
    act(s, "p1", type="resource", player="p1", key="energy", delta=-1)
    roundtrip(s)
    before = len(s.state.zones["p1:hand"])
    act(s, "p1", type="activate_ability", card_id=generator.id, ability=1)
    settle(s)
    assert len(s.state.zones["p1:hand"]) == before + 1
    roundtrip(s)


def test_energy_payment_counts_and_history_resets_at_turn_boundary(cards):
    from app.rules import history

    s = build(cards, ["Izzet Generatorium", "Aether Hub"])
    put(s, "Izzet Generatorium", "battlefield")
    hub = put(s, "Aether Hub", "battlefield")
    act(s, "p1", type="resource", player="p1", key="energy", delta=4)
    act(s, "p1", type="activate_ability", card_id=hub.id, ability=2, mana_choice="G")
    assert history.amount(Plan(s.state, "p1", cards, None), {"controller": "p1"}, {"turn_history": "energy_lost"}) == 1
    roundtrip(s)
    act(s, "p1", type="next_turn")
    assert history.amount(Plan(s.state, "p1", cards, None), {"controller": "p1"}, {"turn_history": "energy_lost"}) == 0
    roundtrip(s)


def test_old_turn_log_without_energy_history_loads():
    assert TurnLog.model_validate({"turn": 3}).energy_lost == {}
