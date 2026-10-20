"""Sequential energy gains/payments, CR 107.3f, 118.12, 608.2c (2026-09-25)."""

from __future__ import annotations

import pytest

from app.rules import coverage, scripts
from tests.game_helpers import act
from tests.test_rules_designations import build, pick, put, res, roundtrip, settle
from tests.test_rules_energy_replacements import cards as cards
from tests.test_rules_wave34b_activated import stops
from tests.wave9c_kit import pt


@pytest.mark.parametrize("payment,expected", [("x:3", 3), ("decline", None)])
def test_refinery_gains_energy_before_optional_payment_and_sizes_the_token(cards, payment, expected):
    assert coverage.of_card_data(cards.resolve("Aether Refinery")).level == "FULL"
    s = build(cards, ["Aether Refinery"])
    refinery = put(s, "Aether Refinery", "battlefield")
    act(s, "p1", type="resource", player="p1", key="energy", delta=2)
    act(s, "p1", type="activate_ability", card_id=refinery.id, ability=1)
    settle(s)
    assert res(s) == 4  # The activation's energy is doubled before the payment choice.
    d = s.state.rules.decision
    assert d is not None and {"x:1", "x:4", "decline"} <= {o.id for o in d.options}
    assert "x:0" not in {o.id for o in d.options}
    roundtrip(s)
    pick(s, [payment])
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.name == "Aetherborn"]
    if expected is None:
        assert not tokens and res(s) == 4
    else:
        assert len(tokens) == 1 and res(s) == 1
        assert pt(s, "Aetherborn") == (expected, expected)
    roundtrip(s)


@pytest.mark.parametrize("payment", ["x:2", "decline"])
def test_localized_destruction_protects_matching_own_creatures_only_and_always_destroys(cards, payment):
    assert coverage.of_card_data(cards.resolve("Localized Destruction")).level == "FULL"
    s = build(cards, ["Localized Destruction", "Grizzly Bears", "Hill Giant"], bob=((1, "Grizzly Bears"), (10, "Island")))
    bear = put(s, "Grizzly Bears", "battlefield")
    giant = put(s, "Hill Giant", "battlefield")
    theirs = put(s, "Grizzly Bears", "battlefield", "p2")
    act(s, "p1", type="resource", player="p1", key="energy", delta=1)
    act(s, "p1", type="add_mana", player="p1", mana={"W": 2, "C": 3})
    act(s, "p1", type="cast_spell", card_id=put(s, "Localized Destruction", "hand").id)
    settle(s)
    assert res(s) == 2
    pick(s, [payment])
    settle(s)
    assert s.state.cards[bear.id].zone == ("p1:battlefield" if payment == "x:2" else "p1:graveyard")
    assert s.state.cards[giant.id].zone == "p1:graveyard"
    assert s.state.cards[theirs.id].zone == "p2:graveyard"
    roundtrip(s)


def test_wrath_of_the_skies_uses_energy_paid_instead_of_cast_x(cards):
    assert coverage.of_card_data(cards.resolve("Wrath of the Skies")).level == "FULL"
    s = build(cards, ["Wrath of the Skies", "Sol Ring", "Grizzly Bears"])
    ring = put(s, "Sol Ring", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    for kind in ("Artifact", "Creature", "Enchantment"):
        act(s, "p1", type="create_token", player="p1", token={"name": f"Zero {kind}", "type_line": f"Token {kind}", "power": "1", "toughness": "1"})
    act(s, "p1", type="resource", player="p1", key="energy", delta=3)
    act(s, "p1", type="add_mana", player="p1", mana={"W": 2, "C": 2})
    act(s, "p1", type="cast_spell", card_id=put(s, "Wrath of the Skies", "hand").id, x_value=2)
    settle(s)
    assert res(s) == 5
    pick(s, ["1"])
    settle(s)
    assert res(s) == 4
    assert s.state.cards[ring.id].zone == "p1:graveyard"
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    assert not any(c.zone.endswith(":battlefield") and c.name.startswith("Zero ") for c in s.state.cards.values())
    roundtrip(s)


@pytest.mark.parametrize("payment,power", [("0", 2), ("1", 1), ("2", None)])
def test_die_young_binds_the_creature_and_scales_the_reduction(cards, payment, power):
    assert coverage.of_card_data(cards.resolve("Die Young")).level == "FULL"
    s = build(cards, ["Die Young", "Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "battlefield")
    act(s, "p1", type="add_mana", player="p1", mana={"B": 1, "C": 1})
    act(s, "p1", type="cast_spell", card_id=put(s, "Die Young", "hand").id, targets=[bear.id])
    settle(s)
    pick(s, [payment])
    settle(s)
    assert res(s) == 2 - int(payment)
    if power is None:
        assert s.state.cards[bear.id].zone == "p1:graveyard"
    else:
        assert pt(s, "Grizzly Bears") == (power, power)
    roundtrip(s)


def test_resolution_energy_cannot_restrict_targets_or_refer_to_an_unmade_payment():
    assert scripts.parse_effects("Destroy target creature with power equal to the amount of {E} paid this way.", "self") is None
    assert scripts.parse_effects("Destroy each creature with power equal to the amount of {E} paid this way.", "self") is None
    assert scripts.parse_effects("Counter target spell unless its controller pays {1} for each {E} paid this way.", "self") is None
    assert scripts.parse_effects("Choose target creature. Create a 1/1 white Soldier creature token. The creature gets -1/-1 until end of turn.", "self") is None


@pytest.mark.parametrize("pay", ["pay", "decline"])
@pytest.mark.parametrize("energy", ["0", "2"])
def test_aether_spike_uses_energy_paid_to_set_the_targets_controllers_payment(cards, pay, energy):
    assert coverage.of_card_data(cards.resolve("Aether Spike")).level == "FULL"
    s = build(cards, ["Grizzly Bears"], bob=((1, "Aether Spike"), (10, "Island")))
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1, "C": 3})
    act(s, "p2", type="add_mana", player="p2", mana={"U": 1, "C": 1})
    spike = put(s, "Aether Spike", "hand", "p2")
    bear = put(s, "Grizzly Bears", "hand")
    act(s, "p1", type="cast_spell", card_id=bear.id)
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=spike.id, targets=[bear.id])
    settle(s)
    assert s.state.rules.decision.player == "p2"
    pick(s, [energy])
    settle(s)
    assert s.state.rules.decision.player == "p1"
    roundtrip(s)
    pick(s, [pay])
    settle(s)
    assert s.state.cards[bear.id].zone == ("p1:battlefield" if pay == "pay" else "p1:graveyard")
    assert res(s, "p2") == 2 - int(energy)
    assert s.state.players["p1"].mana.get("C", 0) == (2 - int(energy) if pay == "pay" else 2)
    roundtrip(s)


@pytest.mark.parametrize("pay", ["x:2", "decline"])
def test_aetherkite_payment_creates_a_separate_reflexive_damage_trigger(cards, pay):
    assert coverage.of_card_data(cards.resolve("Territorial Aetherkite")).level == "FULL"
    s = build(cards, ["Territorial Aetherkite", "Grizzly Bears"], bob=((1, "Grizzly Bears"), (10, "Island")))
    mine = put(s, "Grizzly Bears", "battlefield")
    theirs = put(s, "Grizzly Bears", "battlefield", "p2")
    act(s, "p1", type="add_mana", player="p1", mana={"R": 2, "C": 4})
    stops(s)
    kite = put(s, "Territorial Aetherkite", "hand")
    act(s, "p1", type="cast_spell", card_id=kite.id)
    settle(s)
    assert res(s) == 2
    pick(s, [pay])
    if pay == "x:2":
        assert s.state.zones["stack"]  # CR 603.12: this damage can be responded to.
        assert s.state.cards[mine.id].zone == "p1:battlefield"
        assert s.state.cards[theirs.id].zone == "p2:battlefield"
    roundtrip(s)
    settle(s)
    assert s.state.cards[mine.id].zone == ("p1:graveyard" if pay == "x:2" else "p1:battlefield")
    assert s.state.cards[theirs.id].zone == ("p2:graveyard" if pay == "x:2" else "p2:battlefield")
    assert s.state.cards[kite.id].zone == "p1:battlefield" and s.state.cards[kite.id].damage == 0
    roundtrip(s)
