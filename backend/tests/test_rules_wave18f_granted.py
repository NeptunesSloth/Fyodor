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
    card("Spare Dagger", set_code="tst", number="18F3", mana_cost="{1}", cmc=1.0, type_line="Artifact — Equipment",
         oracle_text='Equipped creature gets +1/+0 and has "Whenever this creature attacks, you may sacrifice Spare Dagger. When you do, '
         'this creature deals 1 damage to any target."\nEquip {1}'),
    card("Trusty Boomerang", set_code="tst", number="18F4", mana_cost="{1}", cmc=1.0, type_line="Artifact — Equipment",
         oracle_text='Equipped creature has "{1}, {T}: Tap target creature. Return Trusty Boomerang to its owner\'s hand."\nEquip {1}'),
    card("Fishing Pole", set_code="tst", number="18F5", mana_cost="{1}", cmc=1.0, type_line="Artifact — Equipment",
         oracle_text='Equipped creature has "{1}, {T}, Tap Fishing Pole: Put a bait counter on Fishing Pole."\nEquip {1}'),
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


def test_spare_dagger_is_sacrificed_by_the_granted_attack_trigger(cards):
    from tests.test_rules_wave5c_combat import declare, to_attack, to_blocks

    s, gear, bear = _equipped(cards, "Spare Dagger")
    _attach(s, gear, bear)
    to_attack(s)
    declare(s, (bear, "p2"))
    to_blocks(s)  # the granted trigger: "you may sacrifice Spare Dagger" - paid with the Dagger, not the creature
    answer(s)
    assert s.state.cards[gear.id].zone.endswith(":graveyard") and s.state.cards[bear.id].zone.endswith(":battlefield")
    assert s.state.players["p2"].life < 40
    roundtrip(s)


def test_trusty_boomerang_returns_itself_not_the_creature(cards):
    s, gear, bear = _equipped(cards, "Trusty Boomerang", p2=("Test Small",))
    victim = put(s, "Test Small", "battlefield", "p2")
    _attach(s, gear, bear)
    ability = next(a for a in _derived(s, "Test Small").abilities if a.index >= 100 and a.kind == "activated")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=bear.id, ability=ability.index, targets=[victim.id])
    answer(s)
    assert s.state.cards[victim.id].tapped  # (a creature's {T} ability)
    assert s.state.cards[gear.id].zone.endswith(":hand")  # 607.1a: the Boomerang, not the creature
    assert s.state.cards[bear.id].zone.endswith(":battlefield")
    roundtrip(s)


def test_fishing_pole_taps_itself_and_gets_the_counter(cards):
    s, gear, bear = _equipped(cards, "Fishing Pole")
    _attach(s, gear, bear)
    ability = next(a for a in _derived(s, "Test Small").abilities if a.index >= 100 and a.kind == "activated")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=bear.id, ability=ability.index)
    assert s.state.cards[gear.id].tapped and s.state.cards[bear.id].tapped  # both tapped to pay
    answer(s)
    assert s.state.cards[gear.id].counters.get("bait") == 1 and not s.state.cards[bear.id].counters
    roundtrip(s)


# -- copied abilities: Kurkesh (707.10) -----------------------------------------------------------------------------------
EXTRA += [
    card("Kurkesh, Onakke Ancient", set_code="tst", number="18F6", mana_cost="{2}{R}{R}", cmc=4.0, colors=["R"], color_identity=["R"],
         type_line="Legendary Creature — Ogre Spirit", power="4", toughness="3",
         oracle_text="Whenever you activate an ability of an artifact, if it isn't a mana ability, you may pay {R}. If you do, copy that "
         "ability. You may choose new targets for the copy."),
    card("Rod of Ruin", set_code="tst", number="18F7", mana_cost="{4}", cmc=4.0, type_line="Artifact",
         oracle_text="{3}, {T}: Rod of Ruin deals 1 damage to any target."),
]


def _settle(s):
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


# -- copied for each (707.10d): Zada, Mirrorwing Dragon ----------------------------------------------------------------------
EXTRA += [
    card("Zada, Hedron Grinder", set_code="tst", number="18F8", mana_cost="{3}{R}", cmc=4.0, colors=["R"], color_identity=["R"],
         type_line="Legendary Creature — Goblin Ninja", power="3", toughness="3",
         oracle_text="Whenever you cast an instant or sorcery spell that targets only Zada, copy that spell for each other creature you "
         "control that the spell could target. Each copy targets a different one of those creatures."),
    card("Mirrorwing Dragon", set_code="tst", number="18F9", mana_cost="{3}{R}{R}", cmc=5.0, colors=["R"], color_identity=["R"],
         type_line="Creature — Dragon", power="4", toughness="5", keywords=["Flying"],
         oracle_text="Flying\nWhenever a player casts an instant or sorcery spell that targets only this creature, that player copies "
         "that spell for each other creature they control that the spell could target. Each copy targets a different one of those "
         "creatures."),
]


def test_zada_copies_the_bolt_for_each_other_creature_you_control(cards):
    s = build(cards, p1=("Zada, Hedron Grinder", "Test Small", "Llanowar Elves", "Lightning Bolt"), p2=("Test Small",))
    zada = put(s, "Zada, Hedron Grinder", "battlefield")
    small = put(s, "Test Small", "battlefield")
    elves = put(s, "Llanowar Elves", "battlefield")
    theirs = put(s, "Test Small", "battlefield", "p2")
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[zada.id])
    _settle(s)  # 707.10d: a copy for each of the two other creatures (ordered by you); the opponent's isn't one you control
    assert all(s.state.cards[c.id].zone.endswith(":graveyard") for c in (zada, small, elves))  # each hit by a Bolt
    assert s.state.cards[theirs.id].zone.endswith(":battlefield")
    roundtrip(s)


def test_mirrorwing_dragon_copies_for_the_caster(cards):
    s = build(cards, p1=("Test Small", "Lightning Bolt"), p2=("Mirrorwing Dragon", "Llanowar Elves"))
    dragon = put(s, "Mirrorwing Dragon", "battlefield", "p2")
    elves = put(s, "Llanowar Elves", "battlefield", "p2")
    mine = put(s, "Test Small", "battlefield")
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[dragon.id])
    _settle(s)  # that player (Alice) copies it for each other creature *they* control that it could target: her Test Small
    assert s.state.cards[mine.id].zone.endswith(":graveyard") and s.state.cards[elves.id].zone.endswith(":battlefield")
    roundtrip(s)


def test_kurkesh_copies_the_activated_artifact_ability(cards):
    s = build(cards, p1=("Kurkesh, Onakke Ancient", "Rod of Ruin"))
    put(s, "Kurkesh, Onakke Ancient", "battlefield")
    rod = put(s, "Rod of Ruin", "battlefield")
    mana(s, C=3, R=1)
    act(s, "p1", type="activate_ability", card_id=rod.id, ability=0, targets=["p2"])
    _settle(s)  # Kurkesh triggers (603.2): pay {R} (118.12), copy the ability (707.10)
    assert s.state.players["p2"].life == 38  # the ability and its copy
    roundtrip(s)
