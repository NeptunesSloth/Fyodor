"""CR 118.12, 603.12, 608.2c: ordered costs and separately targeted reflexive abilities."""
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
from tests.test_rules_designations import build, pick, put, res, roundtrip, settle
from tests.test_rules_wave34b_activated import attack, next_turn, stops


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures" / "ordered_payments_cards.json").read_text())):
        base[c["name"]] = card(c["name"], set_code="ord", number=str(i), **{k:v for k,v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("initial,payment", [(6, "pay"), (6, "decline"), (5, None)])
def test_lightning_runner_gains_energy_before_optional_payment_and_adds_combat_only_if_paid(cards, initial, payment):
    assert coverage.of_card_data(cards.resolve("Lightning Runner")).level == "FULL"
    s = build(cards, ["Lightning Runner", "Grizzly Bears"])
    runner = put(s, "Lightning Runner", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    next_turn(s)
    stops(s)
    act(s, "p1", type="tap", card_ids=[bear.id], tapped=True)
    act(s, "p1", type="resource", player="p1", key="energy", delta=initial)
    attack(s, runner)
    settle(s)
    assert res(s) == initial + 2
    if payment is not None:
        assert s.state.rules.decision is not None
        roundtrip(s)
        pick(s, [payment])
        settle(s)
    assert res(s) == initial + 2 - (8 if payment == "pay" else 0)
    assert s.state.cards[runner.id].tapped is (payment != "pay")
    assert s.state.cards[bear.id].tapped is (payment != "pay")
    assert s.state.rules.extra_phases == (["begin_combat", "main2"] if payment == "pay" else [])
    roundtrip(s)


@pytest.mark.parametrize("pay", [True, False])
def test_blaster_hulk_selects_targets_and_divides_damage_only_after_payment(cards, pay):
    assert coverage.of_card_data(cards.resolve("Blaster Hulk")).level == "FULL"
    s = build(cards, ["Blaster Hulk"], bob=((1, "Grizzly Bears"), (10, "Island")))
    hulk = put(s, "Blaster Hulk", "battlefield")
    victim = put(s, "Grizzly Bears", "battlefield", "p2")
    next_turn(s)
    stops(s)
    act(s, "p1", type="resource", player="p1", key="energy", delta=6)
    attack(s, hulk)
    settle(s)
    decision = s.state.rules.decision
    assert decision is not None and {o.id for o in decision.options} == {"pay", "decline"}
    assert res(s) == 8  # No target was announced for the original attack trigger.
    roundtrip(s)
    pick(s, ["pay" if pay else "decline"])
    settle(s)
    if pay:
        decision = s.state.rules.decision
        assert decision is not None and "target" in decision.prompt.lower()
        pick(s, [victim.id, "p2"])
        decision = s.state.rules.decision
        assert decision is not None and decision.kind == "divide" and decision.display["total"] == 8
        act(s, "p1", type="choose", decision_id=decision.id, amounts=[5, 3])
        assert s.state.zones.get("stack")  # Opponents get a response window for the reflexive trigger.
        roundtrip(s)
        settle(s)
        assert s.state.cards[victim.id].zone == "p2:graveyard"
        assert s.state.players["p2"].life == 37
    else:
        assert s.state.cards[victim.id].zone == "p2:battlefield"
        assert s.state.players["p2"].life == 40
    assert res(s) == (0 if pay else 8)
    roundtrip(s)


def test_ugin_draws_before_choosing_permanent_cards_from_hand(cards):
    assert coverage.of_card_data(cards.resolve("Ugin, the Spirit Dragon")).level == "FULL"
    s = build(cards, ["Ugin, the Spirit Dragon", "Grizzly Bears", "Sol Ring", "Lightning Bolt"])
    ugin = put(s, "Ugin, the Spirit Dragon", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 8})
    act(s, "p1", type="cast_spell", card_id=ugin.id)
    settle(s)
    bear = put(s, "Grizzly Bears", "hand")
    ring = put(s, "Sol Ring", "hand")
    bolt = put(s, "Lightning Bolt", "hand")
    before = len(s.state.zones.get("p1:hand", []))
    act(s, "p1", type="counter", card_ids=[ugin.id], kind="loyalty", delta=3)
    act(s, "p1", type="activate_ability", card_id=ugin.id, ability=2)
    settle(s)
    assert s.state.players["p1"].life == 47
    assert len(s.state.zones["p1:hand"]) == before + 7
    decision = s.state.rules.decision
    assert decision is not None and decision.max_choices == 7 and decision.min_choices == 0
    assert bolt.id not in {o.id for o in decision.options}
    roundtrip(s)
    pick(s, [bear.id, ring.id])
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.cards[ring.id].zone == "p1:battlefield"
    assert s.state.cards[ugin.id].zone == "p1:graveyard"
    roundtrip(s)


def test_blaster_hulk_reduction_uses_energy_lost_before_casting(cards):
    s = build(cards, ["Blaster Hulk"])
    hulk = put(s, "Blaster Hulk", "hand")
    act(s, "p1", type="resource", player="p1", key="energy", delta=4)
    act(s, "p1", type="resource", player="p1", key="energy", delta=-4)
    act(s, "p1", type="add_mana", player="p1", mana={"R": 2, "C": 2})
    act(s, "p1", type="cast_spell", card_id=hulk.id)
    settle(s)
    assert s.state.cards[hulk.id].zone == "p1:battlefield"
    assert sum(s.state.players["p1"].mana.values()) == 0
    roundtrip(s)


def test_ugin_may_put_zero_cards_after_drawing(cards):
    s = build(cards, ["Ugin, the Spirit Dragon"])
    ugin = put(s, "Ugin, the Spirit Dragon", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 8})
    act(s, "p1", type="cast_spell", card_id=ugin.id)
    settle(s)
    act(s, "p1", type="counter", card_ids=[ugin.id], kind="loyalty", delta=3)
    act(s, "p1", type="activate_ability", card_id=ugin.id, ability=2)
    settle(s)
    assert s.state.rules.decision is not None
    pick(s, [])
    settle(s)
    assert s.state.players["p1"].life == 47 and len(s.state.zones["p1:hand"]) == 7
    assert not [c for c in s.state.cards.values() if c.zone == "p1:battlefield"]
    roundtrip(s)
