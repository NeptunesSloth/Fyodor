"""CR 122.1b, 613.7c, 702.83, 702.147: keyword counters grant each complete ability."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import combat, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import build, put, roundtrip, settle
from tests.test_rules_wave34b_activated import attack, next_turn, stops, to_phase
from tests.wave9c_kit import pt


@pytest.fixture()
def cards(settings):
    base = {c["name"]:c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures" / "triggered_keyword_counters_cards.json").read_text())):
        base[c["name"]] = card(c["name"], set_code="tkc", number=str(i), **{k:v for k,v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("alone", [True, False])
def test_emissary_counters_stack_with_printed_exalted_and_trigger_only_for_a_lone_attacker(cards, alone):
    assert coverage.of_card_data(cards.resolve("Emissary of Soulfire")).level == "FULL"
    s = build(cards, ["Emissary of Soulfire", "Akrasan Squire", "Grizzly Bears"])
    emissary = put(s, "Emissary of Soulfire", "battlefield")
    squire = put(s, "Akrasan Squire", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    next_turn(s)
    stops(s)
    act(s, "p1", type="resource", player="p1", key="energy", delta=4)
    for _ in range(2):
        act(s, "p1", type="activate_ability", card_id=emissary.id, ability=1, targets=[squire.id])
        settle(s)
    assert s.state.cards[squire.id].counters.get("exalted") == 2
    roundtrip(s)
    attack(s, bear, *([] if alone else [squire]))
    settle(s)
    assert pt(s, "Grizzly Bears") == ((5, 5) if alone else (2, 2))
    roundtrip(s)


def test_renew_decayed_counters_prevent_blocking_and_create_independent_sacrifice_triggers(cards):
    assert coverage.of_card_data(cards.resolve("Rot-Curse Rakshasa")).level == "FULL"
    s = build(cards, ["Rot-Curse Rakshasa", "Grizzly Bears", "Akrasan Squire"])
    source = put(s, "Rot-Curse Rakshasa", "graveyard")
    bear = put(s, "Grizzly Bears", "battlefield")
    squire = put(s, "Akrasan Squire", "battlefield")
    next_turn(s)
    stops(s)
    act(s, "p1", type="add_mana", player="p1", mana={"B": 2, "C": 2})
    act(s, "p1", type="activate_ability", card_id=source.id, ability=2, x_value=2, targets=[bear.id, squire.id], target_counts=[2])
    settle(s)
    assert s.state.cards[source.id].zone == "p1:exile"
    plan = Plan(s.state, "p1", cards, None)
    bch = plan.ch(s.state.cards[bear.id])
    assert "decayed" in bch.keywords
    assert "decayed" in (combat.block_problem(s.state, s.state.cards[bear.id], bch, s.state.cards[squire.id], plan.ch(s.state.cards[squire.id])) or "")
    roundtrip(s)
    attack(s, bear)
    settle(s)
    assert s.state.rules.delayed
    act(s, "p1", type="counter", card_ids=[bear.id], kind="decayed", delta=-1)
    to_phase(s, "end_combat")
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    assert s.state.cards[squire.id].zone == "p1:battlefield"
    roundtrip(s)


def test_new_exalted_counter_restamps_all_counters_after_ability_loss_but_not_the_printed_instance(cards):
    s = build(cards, ["Akrasan Squire", "Grizzly Bears", "Dress Down"])
    squire = put(s, "Akrasan Squire", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    next_turn(s)
    stops(s)
    act(s, "p1", type="counter", card_ids=[squire.id], kind="exalted", delta=2)
    act(s, "p1", type="add_mana", player="p1", mana={"U": 1, "C": 1})
    act(s, "p1", type="cast_spell", card_id=put(s, "Dress Down", "hand").id)
    settle(s)
    assert "exalted" not in Plan(s.state, "p1", cards, None).ch(s.state.cards[squire.id]).keywords
    act(s, "p1", type="counter", card_ids=[squire.id], kind="exalted", delta=1)
    roundtrip(s)
    attack(s, bear)
    settle(s)
    assert pt(s, "Grizzly Bears") == (5, 5)  # Three counters, no printed instance through Dress Down.
    roundtrip(s)
