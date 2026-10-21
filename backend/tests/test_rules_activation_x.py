"""CR 107.3a, 601.2b/c/h, 602.2b: activation-cost X is known before targets and payment."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import costs, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import build, put, res, resolve, roundtrip, settle
from tests.test_rules_wave34b_activated import next_turn, stops


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures" / "activation_x_cards.json").read_text())):
        base[c["name"]] = card(c["name"], set_code="axx", number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ability(s, c):
    return next(a for a in Plan(s.state, "p1", s.cards, None).ch(c).abilities if "Pay X {E}" in (a.cost or ""))


@pytest.mark.parametrize("name,x", [("Grizzly Bears", 2), ("Ornithopter", 0)])
def test_helios_targets_the_announced_mana_value_and_keeps_x_after_sacrificing_itself(cards, name, x):
    assert coverage.of_card_data(cards.resolve("HELIOS One")).level == "FULL"
    s = build(cards, ["HELIOS One", name])
    helios = put(s, "HELIOS One", "battlefield")
    target = put(s, name, "battlefield")
    act(s, "p1", type="resource", player="p1", key="energy", delta=3)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3})
    act(s, "p1", type="activate_ability", card_id=helios.id, ability=ability(s, helios).index, x_value=x, targets=[target.id])
    assert res(s) == 3 - x and s.state.cards[helios.id].zone == "p1:graveyard"
    roundtrip(s)
    settle(s)
    assert s.state.cards[target.id].zone == "p1:graveyard"
    roundtrip(s)


def test_helios_rejects_wrong_mana_value_before_paying_any_cost(cards):
    s = build(cards, ["HELIOS One", "Grizzly Bears"])
    helios = put(s, "HELIOS One", "battlefield")
    target = put(s, "Grizzly Bears", "battlefield")
    act(s, "p1", type="resource", player="p1", key="energy", delta=3)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3})
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=helios.id, ability=ability(s, helios).index, x_value=1, targets=[target.id])
    assert res(s) == 3 and s.state.players["p1"].mana.get("C") == 3
    assert s.state.cards[helios.id].zone == "p1:battlefield" and not s.state.cards[helios.id].tapped
    roundtrip(s)


@pytest.mark.parametrize("name,x", [("Grizzly Bears", 2), ("Ornithopter", 0)])
def test_nightmare_pays_the_announced_energy_and_returns_its_target_after_returning_itself(cards, name, x):
    assert coverage.of_card_data(cards.resolve("Chthonian Nightmare")).level == "FULL"
    s = build(cards, ["Chthonian Nightmare", "Llanowar Elves", name])
    target = put(s, name, "graveyard")
    victim = put(s, "Llanowar Elves", "battlefield")
    nightmare = put(s, "Chthonian Nightmare", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"B": 1, "C": 1})
    act(s, "p1", type="cast_spell", card_id=nightmare.id)
    settle(s)
    assert res(s) == 3
    a = ability(s, s.state.cards[nightmare.id])
    cost = costs.parse_ability_cost(a.cost, card_name="Chthonian Nightmare")
    sacrifice = next(i for i, c in enumerate(cost.components) if c.kind == costs.SACRIFICE)
    act(s, "p1", type="activate_ability", card_id=nightmare.id, ability=a.index, x_value=x, targets=[target.id],
        cost_choices=[{"component": sacrifice, "cards": [victim.id]}])
    assert s.state.cards[nightmare.id].zone == "p1:hand" and s.state.cards[victim.id].zone == "p1:graveyard"
    assert res(s) == 3 - x
    roundtrip(s)
    settle(s)
    assert s.state.cards[target.id].zone == "p1:battlefield"
    roundtrip(s)


@pytest.mark.parametrize("x", [None, 4])
def test_helios_requires_an_announced_affordable_x_without_consuming_resources(cards, x):
    s = build(cards, ["HELIOS One", "Hill Giant"])
    helios = put(s, "HELIOS One", "battlefield")
    target = put(s, "Hill Giant", "battlefield")
    act(s, "p1", type="resource", player="p1", key="energy", delta=3)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3})
    extra = {} if x is None else {"x_value": x}
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=helios.id, ability=ability(s, helios).index, targets=[target.id], **extra)
    assert res(s) == 3 and s.state.players["p1"].mana.get("C") == 3
    assert s.state.cards[helios.id].zone == "p1:battlefield" and not s.state.cards[helios.id].tapped
    roundtrip(s)


@pytest.mark.parametrize("pay", [True, False])
def test_confiscation_coup_gains_energy_before_offering_the_exact_cost(cards, pay):
    assert coverage.of_card_data(cards.resolve("Confiscation Coup")).level == "FULL"
    s = build(cards, ["Confiscation Coup"], bob=((1, "Grizzly Bears"), (10, "Island")))
    target = put(s, "Grizzly Bears", "battlefield", "p2")
    spell = put(s, "Confiscation Coup", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 2, "C": 3})
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[target.id])
    resolve(s, "pay" if pay else "decline")
    assert res(s) == (2 if pay else 4)
    assert s.state.cards[target.id].controller == ("p1" if pay else "p2")
    roundtrip(s)


@pytest.mark.parametrize("name,x", [("Grizzly Bears", 2), ("Ornithopter", 0)])
def test_jolted_awake_returns_the_chosen_card_for_its_exact_energy_cost(cards, name, x):
    assert coverage.of_card_data(cards.resolve("Jolted Awake")).level == "FULL"
    s = build(cards, ["Jolted Awake", name])
    target = put(s, name, "graveyard")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
    act(s, "p1", type="cast_spell", card_id=put(s, "Jolted Awake", "hand").id, targets=[target.id], target_counts=[1])
    resolve(s, "pay")
    assert s.state.cards[target.id].zone == "p1:battlefield" and res(s) == 2 - x
    roundtrip(s)


def test_jolted_awake_cannot_partially_pay_for_an_expensive_card(cards):
    s = build(cards, ["Jolted Awake", "Hill Giant"])
    target = put(s, "Hill Giant", "graveyard")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
    act(s, "p1", type="cast_spell", card_id=put(s, "Jolted Awake", "hand").id, targets=[target.id], target_counts=[1])
    settle(s)
    assert s.state.cards[target.id].zone == "p1:graveyard" and res(s) == 2
    assert s.state.rules.decision is None
    roundtrip(s)


def test_jolted_awake_with_no_target_still_gains_energy(cards):
    s = build(cards, ["Jolted Awake"])
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
    act(s, "p1", type="cast_spell", card_id=put(s, "Jolted Awake", "hand").id, targets=[], target_counts=[0])
    settle(s)
    # A zero cost can be offered even when there is no card to return.
    if s.state.rules.decision is not None:
        resolve(s, "decline")
    assert res(s) == 2
    roundtrip(s)


def test_jolted_awake_with_an_illegal_target_does_not_gain_energy(cards):
    s = build(cards, ["Jolted Awake", "Grizzly Bears"])
    stops(s)
    target = put(s, "Grizzly Bears", "graveyard")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
    act(s, "p1", type="cast_spell", card_id=put(s, "Jolted Awake", "hand").id, targets=[target.id], target_counts=[1])
    act(s, "p1", type="move", card_ids=[target.id], to={"player": "p1", "zone": "exile"})
    settle(s)
    assert s.state.cards[target.id].zone == "p1:exile" and res(s) == 0
    roundtrip(s)


@pytest.mark.parametrize("x", [0, 2])
def test_hourglass_preserves_counter_cost_x_after_exiling_itself(cards, x):
    assert coverage.of_card_data(cards.resolve("Hourglass of the Lost")).level == "FULL"
    s = build(cards, ["Hourglass of the Lost", "Grizzly Bears", "Ornithopter", "Island"])
    source = put(s, "Hourglass of the Lost", "battlefield")
    bear = put(s, "Grizzly Bears", "graveyard")
    thopter = put(s, "Ornithopter", "graveyard")
    land = put(s, "Island", "graveyard")
    act(s, "p1", type="counter", card_ids=[source.id], kind="time", delta=2)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=1, x_value=x)
    settle(s)
    assert s.state.cards[source.id].zone == "p1:exile"
    assert s.state.cards[bear.id].zone == ("p1:battlefield" if x == 2 else "p1:graveyard")
    assert s.state.cards[thopter.id].zone == ("p1:battlefield" if x == 0 else "p1:graveyard")
    assert s.state.cards[land.id].zone == "p1:graveyard"
    roundtrip(s)


def test_resonance_technician_copies_a_spell_matching_the_number_of_artifacts_tapped(cards):
    from tests.test_rules_wave31d_spell_copies import hold
    from tests.test_rules_wave31d_spell_copies import settle as resolve_copies

    assert coverage.of_card_data(cards.resolve("Resonance Technician")).level == "FULL"
    s = build(cards, ["Resonance Technician", "Sol Ring", "Lightning Bolt"])
    source = put(s, "Resonance Technician", "battlefield")
    artifact = put(s, "Sol Ring", "battlefield")
    next_turn(s)
    hold(s)
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    bolt = put(s, "Lightning Bolt", "hand")
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    a = next(a for a in Plan(s.state, "p1", cards, None).ch(source).abilities if a.cost and "Tap X" in a.cost)
    cost = costs.parse_ability_cost(a.cost, card_name="Resonance Technician")
    tap = next(i for i, c in enumerate(cost.components) if c.kind == costs.TAP_OTHER)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=a.index, x_value=1, targets=[bolt.id],
        cost_choices=[{"component": tap, "cards": [artifact.id]}])
    assert s.state.cards[source.id].tapped and s.state.cards[artifact.id].tapped
    roundtrip(s)
    resolve_copies(s)
    assert s.state.players["p2"].life == 34
    roundtrip(s)


def test_hourglass_does_not_exile_itself_when_counter_cost_is_unaffordable(cards):
    s = build(cards, ["Hourglass of the Lost", "Grizzly Bears"])
    source = put(s, "Hourglass of the Lost", "battlefield")
    target = put(s, "Grizzly Bears", "graveyard")
    act(s, "p1", type="counter", card_ids=[source.id], kind="time", delta=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=source.id, ability=1, x_value=2)
    assert s.state.cards[source.id].zone == "p1:battlefield" and not s.state.cards[source.id].tapped
    assert s.state.cards[source.id].counters.get("time") == 1
    assert s.state.cards[target.id].zone == "p1:graveyard"
    roundtrip(s)
