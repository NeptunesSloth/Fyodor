"""Wave 17A (damage prevention with riders). Real Oracle text, replay and save/load for each.

* 615.5: a prevention effect's additional effect, which may refer to the damage prevented, takes place immediately after the
  damage event: source-of-your-choice shields (Reverse Damage, Deflecting Palm), "prevent the next N damage" shields (Healing
  Salve style, Safe Passage style), "prevent all combat damage" records (Inkshield) and statics (Phantom Nishoba, Vigor, Polukranos).
* 615.12: unpreventable damage — a static's additional effect still takes place.
"""

from __future__ import annotations

import pytest

from app.rules import coverage, scripts
from app.rules.characteristics import Characteristics, parse_abilities
from tests.game_helpers import act
from tests.test_rules_attachments import build, token
from tests.test_rules_effects import replay_matches
from tests.test_rules_refused_grants import _choose, life, supported
from tests.test_rules_replacements2 import activate, decision, permanent, red_creature, reload, rules

PINGER = "{1}: Pinger deals 3 damage to any target."
REVERSE = ("{1}: The next time a source of your choice would deal damage to you this turn, prevent that damage. You gain life "
           "equal to the damage prevented this way.")  # Reverse Damage
PALM = ("{1}: The next time a source of your choice would deal damage to you this turn, prevent that damage. If damage is "
        "prevented this way, Palm deals that much damage to that source's controller.")  # Deflecting Palm
SAFE = ("{1}: Prevent the next 3 damage that would be dealt to target creature this turn. For each 1 damage prevented this way, "
        "put a +1/+1 counter on that creature.")  # (Ajani's Presence-style)
HEAL = ("{1}: Prevent the next 3 damage that would be dealt to any target this turn. You gain life equal to the damage prevented "
        "this way.")  # Healing Salve style
INKSHIELD = ("{1}: Prevent all combat damage that would be dealt to you this turn. For each 1 damage prevented this way, create a "
             "2/1 white and black Inkling creature token with flying.")  # Inkshield
PHANTOM = "If damage would be dealt to this creature, prevent that damage. Remove a +1/+1 counter from this creature."
VIGOR = ("If damage would be dealt to another creature you control, prevent that damage. Put a +1/+1 counter on that creature "
         "for each 1 damage prevented this way.")


@pytest.mark.parametrize("text", [
    REVERSE, PALM, SAFE, HEAL, INKSHIELD, PHANTOM, VIGOR,
    "If damage would be dealt to this creature while it has a +1/+1 counter on it, prevent that damage and remove that many "
    "+1/+1 counters from it.",
    "If damage would be dealt to ~ while you're the monarch, prevent that damage and put that many +1/+1 counters on it.",
    "If equipped creature would be dealt damage, prevent that damage and put that many +1/+1 counters on it.",
    "If a creature would deal combat damage to this creature, prevent that damage and put a +1/+1 counter on this creature.",
    "If a source you control would deal damage to an opponent, prevent that damage and each opponent mills that many cards.",
])
def test_read(text):
    assert all(supported(text, name="Palm")), text


@pytest.mark.parametrize("text", [
    # a reflexive trigger (603.12), not an additional effect of the prevention
    "{1}: The next time a source of your choice would deal damage to you this turn, prevent that damage. When damage is "
    "prevented this way, Palm deals that much damage to that source's controller and you draw that many cards.",
    # the rider names a target / an unbound pronoun
    "{1}: Prevent the next 3 damage that would be dealt to any target this turn. If damage is prevented this way, Palm deals "
    "that much damage to any target.",
    # "that creature" is the source of the damage here, not what was dealt it
    "{1}: The next time a source of your choice would deal damage to you this turn, prevent that damage. If damage is prevented "
    "this way, Palm deals that much damage to that creature.",
])
def test_refused(text):
    assert not all(supported(text, name="Palm")), text


def test_reverse_damage_gains_the_damage_prevented(cards):
    s = build(cards)
    reverse = permanent(s, "p1", "Reverse Damage", "Enchantment", REVERSE)
    pinger = red_creature(s, "p1", "Pinger", "1/1", PINGER)
    s2 = reload(s, cards)
    activate(s, reverse)
    _choose(s, "Pinger")
    activate(s, pinger, targets=["p1"])
    assert life(s, "p1") == 43  # 615.5: the 3 damage never happened; the life is gained right after it
    activate(s, pinger, targets=["p1"])  # (a "next time" shield: used up)
    assert life(s, "p1") == 40
    replay_matches(s)
    activate(s2, s2.state.cards[reverse.id])
    _choose(s2, "Pinger")
    activate(s2, s2.state.cards[pinger.id], targets=["p1"])
    assert life(s2, "p1") == 43
    replay_matches(s2)


def test_deflecting_palm_deals_the_prevented_damage_to_the_sources_controller(cards):
    s = build(cards)
    palm = permanent(s, "p1", "Palm", "Enchantment", PALM)
    pinger = red_creature(s, "p1", "Pinger", "1/1", PINGER)
    activate(s, palm)
    _choose(s, "Pinger")
    activate(s, pinger, targets=["p1"])
    assert life(s, "p1") == 37  # the 3 damage to me was prevented; Palm dealt 3 to Pinger's controller (me)
    replay_matches(s)


def test_a_shield_with_a_rider_counts_only_what_it_prevented(cards):
    s = build(cards)
    safe = permanent(s, "p1", "Safe", "Enchantment", SAFE)
    pinger = red_creature(s, "p1", "Pinger", "1/1", "{1}: Pinger deals 2 damage to any target.")
    bear = token(s, "p1", "Bear", "4/4")
    activate(s, safe, targets=[bear.id])
    activate(s, pinger, targets=[bear.id])
    assert s.state.cards[bear.id].damage == 0 and s.state.cards[bear.id].counters.get("+1/+1") == 2
    activate(s, pinger, targets=[bear.id])  # 1 more is prevented (the shield is used up), 1 is dealt
    assert s.state.cards[bear.id].damage == 1 and s.state.cards[bear.id].counters.get("+1/+1") == 3
    assert not rules(s).prevention and not rules(s).prevention_riders
    replay_matches(s)
    s2 = reload(s, cards)
    assert s2.state.cards[bear.id].counters.get("+1/+1") == 3
    replay_matches(s2)


def test_healing_shield_gains_life_for_the_prevented_damage(cards):
    s = build(cards)
    heal = permanent(s, "p1", "Heal", "Enchantment", HEAL)
    pinger = red_creature(s, "p1", "Pinger", "1/1", "{1}: Pinger deals 2 damage to any target.")
    activate(s, heal, targets=["p1"])
    activate(s, pinger, targets=["p1"])
    assert life(s, "p1") == 42  # 2 prevented, 2 gained
    activate(s, pinger, targets=["p1"])  # 1 prevented (+1), 1 dealt (-1)
    assert life(s, "p1") == 42
    replay_matches(s)


def test_phantom_prevents_and_loses_a_counter_even_when_the_damage_cant_be_prevented(cards):
    s = build(cards)
    phantom = token(s, "p1", "Phantom", "0/0", PHANTOM)
    act(s, "p1", type="counter", card_ids=[phantom.id], kind="+1/+1", delta=4)
    pinger = red_creature(s, "p1", "Pinger", "1/1", PINGER)
    activate(s, pinger, targets=[phantom.id])
    assert s.state.cards[phantom.id].damage == 0 and s.state.cards[phantom.id].counters.get("+1/+1") == 3
    unprev = red_creature(s, "p1", "Burner", "1/1", "{1}: Burner deals 1 damage to target creature. The damage can't be prevented.")
    activate(s, unprev, targets=[phantom.id])  # 615.12: the effect applies, prevents none of it, and its additional effect happens
    assert s.state.cards[phantom.id].damage == 1 and s.state.cards[phantom.id].counters.get("+1/+1") == 2
    replay_matches(s)
    s2 = reload(s, cards)
    assert s2.state.cards[phantom.id].counters.get("+1/+1") == 2
    replay_matches(s2)


def test_vigor_puts_a_counter_for_each_damage_prevented_on_the_other_creature(cards):
    s = build(cards)
    vigor = token(s, "p1", "Vigor", "6/6", VIGOR)
    bear = token(s, "p1", "Bear", "2/2")
    pinger = red_creature(s, "p1", "Pinger", "1/1", PINGER)
    activate(s, pinger, targets=[bear.id])
    assert s.state.cards[bear.id].damage == 0 and s.state.cards[bear.id].counters.get("+1/+1") == 3
    activate(s, pinger, targets=[vigor.id])  # (another creature only)
    assert s.state.cards[vigor.id].damage == 3
    replay_matches(s)


def test_a_fog_with_a_rider_gains_life_for_the_combat_damage_it_prevented(cards):
    from tests.test_rules_combat import attack, table, turn_on
    from tests.test_rules_suspend import until

    s = table(cards)
    krenko = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    fog = permanent(s, "p1", "Fog", "Enchantment", "{1}: Prevent all combat damage that would be dealt this turn. You gain life equal to the "
                    "damage prevented this way.")
    assert all(supported("{1}: Prevent all combat damage that would be dealt this turn. You gain life equal to the damage prevented "
                         "this way."))
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → Alice's main 1
    activate(s, fog)
    act(s, "p1", type="pass_priority")  # → combat: Alice declares attackers
    attack(s, (krenko, "p2"))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert life(s, "p2") == 40 and life(s, "p1") == 43  # Krenko is 3/3
    replay_matches(s)
    s2 = reload(s, cards)
    assert life(s2, "p1") == 43
    replay_matches(s2)


def test_combat_damage_to_a_hydra_is_prevented_and_it_grows(cards):
    from tests.test_rules_combat import attack, automate, block, table
    from tests.test_rules_suspend import until

    s = table(cards)
    krenko = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    hydra = token(s, "p2", "Hydra", "2/6", "If a creature would deal combat damage to this creature, prevent that damage and put a "
                  "+1/+1 counter on this creature.")
    automate(s)
    attack(s, (krenko, "p2"))
    block(s, "p2", (hydra, krenko))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.cards[hydra.id].damage == 0 and s.state.cards[hydra.id].counters.get("+1/+1") == 1
    assert s.state.cards[krenko.id].damage == 2
    replay_matches(s)


# -- sources named by property, recipients named by the effect (609.7c, 615.7, 615.8) ------------------------------------------------
LUMINESCE = "{1}: Prevent all damage that black sources and red sources would deal this turn."  # Luminesce
ENERGY_FIELD = "Prevent all damage that would be dealt to you by sources you don't control."  # Energy Field (last line)
HONORABLE = ("{1}: The next time a source of your choice would deal damage to any target this turn, prevent that damage. If damage "
             "from a red source is prevented this way, Passage deals that much damage to the source's controller.")
REMEDY = "{1}: Prevent the next 5 damage that would be dealt this turn to any number of targets, divided as you choose."  # Remedy
KITSUNE = "{1}: Prevent the next 1 damage that would be dealt to each creature you control this turn."  # (Samite Censer-Bearer)


@pytest.mark.parametrize("text", [
    LUMINESCE, ENERGY_FIELD, HONORABLE, REMEDY, KITSUNE,
    "Prevent all damage that would be dealt by instant and sorcery spells.",  # Energy Storm
    "Prevent all damage that would be dealt to this creature by artifact sources.",  # Argothian Treefolk
    "{1}: Prevent all combat damage blue creatures and black creatures would deal this turn.",  # Radiant Kavu
    "{1}: Prevent all damage that would be dealt this turn by non-Human sources.",  # Repel the Abominable
    "{1}: Prevent all combat damage target creature would deal this turn.",  # Azorius Ploy
    "{1}: Prevent all damage one or two target creatures would deal this turn.",  # Soul Parry
    "Sacrifice this Aura: The next time a source of your choice would deal damage to enchanted creature this turn, prevent that "
    "damage.",  # Kithkin Armor
    "Remove a healing counter from this Aura: Prevent the next 1 damage that would be dealt to enchanted creature this turn.",  # Fylgja
    "{1}: Prevent the next 1 damage that would be dealt to each creature and each player this turn.",  # Kitsune Palliator
])
def test_read_sources_and_recipients(text):
    assert all(supported(text, name="Passage")), text


def test_luminesce_prevents_only_black_and_red_sources(cards):
    s = build(cards)
    lum = permanent(s, "p1", "Luminesce", "Enchantment", LUMINESCE)
    red = red_creature(s, "p1", "Pinger", "1/1", PINGER)
    green = token(s, "p1", "Grower", "1/1", "{1}: Grower deals 3 damage to any target.")
    activate(s, lum)
    activate(s, red, targets=["p1"])
    assert life(s, "p1") == 40
    activate(s, green, targets=["p1"])
    assert life(s, "p1") == 37
    replay_matches(s)
    assert life(reload(s, cards), "p1") == 37


def test_energy_field_prevents_damage_from_sources_you_dont_control(cards):
    s = build(cards)
    permanent(s, "p2", "Energy Field", "Enchantment", ENERGY_FIELD)
    pinger = red_creature(s, "p1", "Pinger", "1/1", PINGER)
    activate(s, pinger, targets=["p2"])  # p1's source, p2's field
    assert life(s, "p2") == 40
    activate(s, pinger, targets=["p1"])  # (it protects only its controller)
    assert life(s, "p1") == 37
    replay_matches(s)


def test_a_source_of_your_choice_to_any_target_with_a_color_rider(cards):
    s = build(cards)
    passage = permanent(s, "p1", "Passage", "Enchantment", HONORABLE)
    red = red_creature(s, "p1", "Pinger", "1/1", PINGER)
    bear = token(s, "p1", "Bear", "2/2")
    green = token(s, "p1", "Grower", "1/1", "{1}: Grower deals 3 damage to any target.")
    activate(s, passage, targets=[bear.id])
    assert [o.label for o in decision(s).options if "Pinger" in o.label or "Grower" in o.label]
    _choose(s, "Grower")
    activate(s, green, targets=["p1"])  # not the bear: the shield stays
    assert life(s, "p1") == 37
    activate(s, green, targets=[bear.id])  # prevented, but not a red source: no rider
    assert s.state.cards[bear.id].damage == 0 and life(s, "p1") == 37
    replay_matches(s)
    s2 = reload(s, cards)
    assert life(s2, "p1") == 37
    replay_matches(s2)
    # the red source: the rider hits its controller
    s3 = build(cards)
    passage = permanent(s3, "p1", "Passage", "Enchantment", HONORABLE)
    red = red_creature(s3, "p1", "Pinger", "1/1", PINGER)
    bear = token(s3, "p1", "Bear", "2/2")
    activate(s3, passage, targets=[bear.id])
    _choose(s3, "Pinger")
    activate(s3, red, targets=[bear.id])
    assert s3.state.cards[bear.id].damage == 0 and life(s3, "p1") == 37
    replay_matches(s3)


def test_a_divided_shield_protects_each_target_by_its_share(cards):
    s = build(cards)
    remedy = permanent(s, "p1", "Remedy", "Enchantment", REMEDY)
    pinger = red_creature(s, "p1", "Pinger", "1/1", PINGER)
    bear = token(s, "p1", "Bear", "2/2")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="activate_ability", card_id=remedy.id, ability=0, targets=[bear.id, "p1"], target_counts=[2], division=[2, 3])
    from tests.test_rules_effects import pass_until_stack_empty

    pass_until_stack_empty(s)
    assert rules(s).prevention == {rules(s).object_id(bear.id): 2, "p1": 3}
    activate(s, pinger, targets=[bear.id])  # 3 damage, 2 prevented
    assert s.state.cards[bear.id].damage == 1
    activate(s, pinger, targets=["p1"])  # 3 damage, all prevented
    assert life(s, "p1") == 40
    replay_matches(s)


def test_each_creature_you_control_gets_its_own_shield(cards):
    s = build(cards)
    shield = permanent(s, "p1", "Censer", "Enchantment", KITSUNE)
    pinger = red_creature(s, "p1", "Pinger", "1/1", PINGER)
    bear = token(s, "p1", "Bear", "4/4")
    activate(s, shield)
    late = token(s, "p1", "Late", "4/4")  # (a creature that comes later isn't shielded: 615.11)
    activate(s, pinger, targets=[bear.id])
    activate(s, pinger, targets=[late.id])
    assert s.state.cards[bear.id].damage == 2 and s.state.cards[late.id].damage == 3
