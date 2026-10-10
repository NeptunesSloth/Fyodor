"""Wave 25D: an additional cost sized by the X announced as the spell is cast (CR 107.3a, 601.2b, 601.2f-h): "As an additional cost to
cast this spell, discard X cards." (Firestorm, the Dreams), "sacrifice X lands / creatures", "exile X cards from your graveyard", "return X
Swamps you control to their owner's hand". Real Oracle text (tests/fixtures/wave25d_x_cards.json); each scenario replays and round-trips.

The announced X also sizes the spell (107.3: every X of the spell is the same number): "deals X damage to each of X targets", "Destroy X
target creatures"."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.game.errors import ActionError
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import build, ch, to_hand
from tests.test_rules_copy import choose, decision, on_battlefield, pay
from tests.test_rules_effects import pass_until_stack_empty, replay_matches

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave25d_x_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t25x", number=f"B{i:02d}", **{k: v for k, v in c.items() if k not in ("name", "layout", "card_faces")})
         for i, c in enumerate(DATA)]
FODDER = [
    card(f"Probe {name}", set_code="t25x", number=f"C{i:02d}", mana_cost="{1}", cmc=1.0, type_line=tl, oracle_text="", power=pt, toughness=pt,
         colors=[], color_identity=[])
    for i, (name, tl, pt) in enumerate([("Bear", "Creature — Bear", "2"), ("Bear Two", "Creature — Bear", "2"), ("Bear Three", "Creature — Bear", "2"),
                                        ("Spell Book", "Instant", None)])
]


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *FODDER], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped


def settle(s, limit=30):
    for _ in range(limit):
        d = decision(s)
        if d is not None:
            choose(s, d.options[0].id)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def zone(s, pid, z):
    return [s.state.cards[c].name for c in s.state.zones.get(f"{pid}:{z}", [])]


@pytest.mark.parametrize("name", [c["name"] for c in DATA if c["name"] != "Abandon Hope"])
def test_the_promoted_cards_are_full(name):
    data = next(c for c in DATA if c["name"] == name)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or [], "legalities": {"commander": "legal"}}).level == "FULL"


def test_harvest_pyre_exiles_x_cards_from_the_graveyard_and_deals_x(cards):
    s = build(cards, "Harvest Pyre", "Probe Bear", "Probe Bear Two", "Probe Bear Three")
    bear = on_battlefield(s, "Probe Bear")
    for n in ("Probe Bear Two", "Probe Bear Three"):
        act(s, "p1", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == n)], to={"zone": "graveyard"})
    pyre = to_hand(s, "Harvest Pyre")
    pay(s, R=1, C=1)
    with pytest.raises(ActionError, match="Choose a value for X"):
        act(s, "p1", type="cast_spell", card_id=pyre.id, targets=[bear.id])  # 601.2b: X is announced as it's cast
    with pytest.raises(ActionError, match="can't pay"):
        act(s, "p1", type="cast_spell", card_id=pyre.id, targets=[bear.id], x_value=3)  # 118.3: only two cards in the graveyard
    act(s, "p1", type="cast_spell", card_id=pyre.id, targets=[bear.id], x_value=2)
    settle(s)
    assert sorted(zone(s, "p1", "graveyard")) == ["Harvest Pyre", "Probe Bear"]  # 2 damage on a 2/2 killed it
    assert sorted(zone(s, "p1", "exile")) == ["Probe Bear Three", "Probe Bear Two"]
    roundtrip(s)


def test_firestorm_discards_x_and_has_x_targets(cards):
    s = build(cards, "Firestorm", "Probe Bear", "Probe Bear Two", "Probe Bear Three", "Probe Spell Book")
    bears = [on_battlefield(s, n) for n in ("Probe Bear", "Probe Bear Two")]
    junk = [to_hand(s, "Probe Spell Book"), to_hand(s, "Probe Bear Three")]
    storm = to_hand(s, "Firestorm")
    pay(s, R=1)
    with pytest.raises(ActionError, match="Choose 2 targets"):
        act(s, "p1", type="cast_spell", card_id=storm.id, targets=[bears[0].id], target_counts=[1], x_value=2)  # 601.2c: X targets, exactly
    act(s, "p1", type="cast_spell", card_id=storm.id, targets=[b.id for b in bears], target_counts=[2], x_value=2,
        cost_choices=[{"component": 0, "cards": [j.id for j in junk]}])
    pass_until_stack_empty(s)
    assert {"Probe Spell Book", "Probe Bear Three"} <= set(zone(s, "p1", "graveyard"))  # discarded as the cost
    assert all(b.id in s.state.zones["p1:graveyard"] for b in bears)  # X damage (2) to each of the two 2/2s
    roundtrip(s)


def test_devastating_summons_sacrifices_x_lands_for_x_x_tokens(cards):
    s = build(cards, "Devastating Summons")
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:2]
    for f in forests:
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "battlefield"})
    spell = to_hand(s, "Devastating Summons")
    pay(s, R=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=2, cost_choices=[{"component": 0, "cards": [f.id for f in forests]}])
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert len(tokens) == 2 and all(ch(s, t).pt == (2, 2) for t in tokens)  # "Create two X/X red Elemental creature tokens"
    assert all(f.id in s.state.zones["p1:graveyard"] for f in forests)
    roundtrip(s)


def test_aether_tide_the_mana_x_and_the_cost_x_are_one_number(cards):
    s = build(cards, "Aether Tide", "Probe Bear", "Probe Bear Two", "Probe Spell Book")
    bear = on_battlefield(s, "Probe Bear")
    fodder = to_hand(s, "Probe Bear Two")
    book = to_hand(s, "Probe Spell Book")
    tide = to_hand(s, "Aether Tide")
    pay(s, U=2)
    with pytest.raises(ActionError):  # "discard X creature cards": an instant isn't one
        act(s, "p1", type="cast_spell", card_id=tide.id, targets=[bear.id], target_counts=[1], x_value=1,
            cost_choices=[{"component": 0, "cards": [book.id]}])
    act(s, "p1", type="cast_spell", card_id=tide.id, targets=[bear.id], target_counts=[1], x_value=1,
        cost_choices=[{"component": 0, "cards": [fodder.id]}])
    settle(s)
    assert "Probe Bear Two" in zone(s, "p1", "graveyard") and "Probe Bear" in zone(s, "p1", "hand")  # discarded one, returned X = 1 target
    roundtrip(s)


def test_discarding_x_at_random_is_recorded_for_replay(cards):
    s = build(cards, "Devastating Dreams", "Probe Bear", "Probe Bear Two", "Probe Spell Book")
    hand = [to_hand(s, n) for n in ("Probe Bear", "Probe Bear Two", "Probe Spell Book")]
    dreams = to_hand(s, "Devastating Dreams")
    pay(s, R=2)
    act(s, "p1", type="cast_spell", card_id=dreams.id, x_value=2)
    settle(s)
    assert sum(1 for h in hand if s.state.cards[h.id].zone == "p1:graveyard") == 2  # two of the three, none of them chosen by the caster
    roundtrip(s)


def test_x_zero_costs_nothing(cards):
    s = build(cards, "Harvest Pyre", "Probe Bear")
    bear = on_battlefield(s, "Probe Bear")
    pyre = to_hand(s, "Harvest Pyre")
    pay(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=pyre.id, targets=[bear.id], x_value=0)  # 107.3a: X may be 0
    settle(s)
    assert bear.id in s.state.zones["p1:battlefield"] and zone(s, "p1", "exile") == []
    roundtrip(s)
