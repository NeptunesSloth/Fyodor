"""Wave 18F: a quoted grant that names the object granting it (CR 2026-09-25, real Oracle text; replay and save/load for each).

* 607.1a / 613.1f / 113.10a: "Equipped creature has "{T}, Sacrifice Blazing Torch: Blazing Torch deals 2 damage to any target."" - the
  granted ability is the creature's, but "Blazing Torch" is the Equipment that granted it: it is sacrificed to pay (701.21a) and is the
  damage source (as it last existed once gone, 608.2h). "Unattach Heartseeker" (701.3d) leaves the Equipment on the battlefield.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card("Test Small", set_code="tst", number="C01", mana_cost="{G}", cmc=1.0, type_line="Creature — Elf", power="2", toughness="2",
         colors=["G"], color_identity=["G"], keywords=["Haste"], oracle_text="Haste"),
    card("Blazing Torch", set_code="tst", number="18F1", mana_cost="{1}", cmc=1.0, type_line="Artifact — Equipment",
         oracle_text='Equipped creature can\'t be blocked by Vampires or Zombies.\nEquipped creature has "{T}, Sacrifice Blazing Torch: '
         'Blazing Torch deals 2 damage to any target."\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)'),
    card("Heartseeker", set_code="tst", number="18F2", mana_cost="{4}", cmc=4.0, type_line="Artifact — Equipment",
         oracle_text='Equipped creature gets +2/+1 and has "{T}, Unattach Heartseeker: Destroy target creature."\n'
         'Equip {5} ({5}: Attach to target creature you control. Equip only as a sorcery.)'),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Blazing Torch", "Heartseeker"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _derived(s, name, pid="p1"):
    from app.rules import characteristics as chars
    from app.rules.layers import derive

    c = find(s, name, pid)
    return derive(s.state, c, chars.of(c, s.cards), s.cards)


def _equipped(cards, equipment, p2=()):
    s = build(cards, p1=(equipment, "Test Small"), p2=p2)
    gear = put(s, equipment, "battlefield")
    bear = put(s, "Test Small", "battlefield")
    return s, gear, bear


def _attach(s, gear, bear):
    equip = next(a for a in _derived(s, gear.name).abilities if "equip" in a.keywords)
    mana(s, C=5)
    act(s, "p1", type="activate_ability", card_id=gear.id, ability=equip.index, targets=[bear.id])
    answer(s)
    assert s.state.cards[gear.id].attached_to == bear.id


def test_blazing_torch_sacrifices_itself_and_deals_the_damage(cards):
    s, torch, bear = _equipped(cards, "Blazing Torch")
    _attach(s, torch, bear)
    ability = next(a for a in _derived(s, "Test Small").abilities if a.index >= 100 and a.kind == "activated")
    assert "Sacrifice" in ability.text and f"‹granter#{s.state.rules.object_id(torch.id)}›" in ability.text
    from app.game import ops

    assert "Sacrifice Blazing Torch: Blazing Torch deals 2 damage" in ops.shown(s.state, ability.text)  # (what people read)
    act(s, "p1", type="activate_ability", card_id=bear.id, ability=ability.index, targets=["p2"])
    assert s.state.cards[torch.id].zone.endswith(":graveyard")  # 701.21a: the Equipment paid, not the creature
    assert s.state.cards[bear.id].zone.endswith(":battlefield") and s.state.cards[bear.id].tapped
    answer(s)
    assert s.state.players["p2"].life == 38  # 608.2h: dealt by the Torch as it last existed
    assert not [a for a in _derived(s, "Test Small").abilities if a.index >= 100]  # the grant went with the Torch
    roundtrip(s)


def test_heartseeker_unattaches_and_destroys(cards):
    s, gear, bear = _equipped(cards, "Heartseeker", p2=("Test Small",))
    victim = put(s, "Test Small", "battlefield", "p2")
    _attach(s, gear, bear)
    ability = next(a for a in _derived(s, "Test Small").abilities if a.index >= 100 and a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=bear.id, ability=ability.index, targets=[victim.id])
    assert s.state.cards[gear.id].zone.endswith(":battlefield") and s.state.cards[gear.id].attached_to is None  # 701.3d
    answer(s)
    assert s.state.cards[victim.id].zone.endswith(":graveyard")
    assert not any(a.index >= 100 for a in _derived(s, "Test Small").abilities)
    roundtrip(s)


def test_a_tapped_creature_cannot_pay(cards):
    s, torch, bear = _equipped(cards, "Blazing Torch")
    _attach(s, torch, bear)
    ability = next(a for a in _derived(s, "Test Small").abilities if a.index >= 100 and a.kind == "activated")
    s.state.cards[bear.id].tapped = True
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=bear.id, ability=ability.index, targets=["p2"])
