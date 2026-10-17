"""Wave 50D: an Aura / Equipment trigger about its host dealing or being dealt damage, real Oracle text (tests/fixtures/wave50d_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load (tests/wave9c_kit.check).

* 603.2: an ability triggers when its event happens. The damage is dealt before any state-based action is checked (704.3), so the Aura was still attached to the
  creature that is dealt lethal damage and its "whenever enchanted creature is dealt damage" ability triggers (Druid's Call, Binding Agony, Ragged Veins, Spiteful
  Shadows, Soul Link), and an Equipment was still attached to a creature that dies in the combat damage step it dealt its damage in (Umezawa's Jitte, Goldvein
  Pick, Fiendlash). By the time the trigger is looked at the creature is gone and the Aura / Equipment let go of it (704.5g, 704.5m, 704.5n): the creature's last
  known information lists what was attached to it (603.10a).
* 608.2h: "its controller", "its power" read the creature as it last existed.
* An Aura / Equipment that was no longer attached to that creature when the event happened triggers nothing (301.5).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import ch, token
from tests.test_rules_conditionals import through_combat
from tests.test_rules_copy import choose, pay
from tests.test_rules_wave39b_trigger_damage import attack, block, to_main1
from tests.test_rules_wave40b_attached import cast_on, equip, settle
from tests.wave9c_kit import build, check, life, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50d_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t50d", number=f"D{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def squirrels(s):
    return [c for c in s.state.cards.values() if c.name == "Squirrel" and c.zone.endswith(":battlefield")]


def enchant(s, name, creature, **m):
    """The Aura cast on ``creature`` and resolved."""
    aura = to_hand(s, name)
    pay(s, **m)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[creature.id])
    settle(s)
    assert s.state.cards[aura.id].attached_to == creature.id
    return aura


def dead(s, c):
    return c.id not in s.state.cards or s.state.cards[c.id].zone.endswith(":graveyard")


def combat(s):
    """The table saved and loaded in the middle of combat, then played on to the second main phase."""
    s = reloaded(s)
    through_combat(s)
    return s


# -- the Aura goes to the graveyard with the creature it enchants ---------------------------------------------------------------------
def test_druids_call_makes_squirrels_when_the_creature_dies_to_that_damage(cards):
    s = build(cards, ["Druid's Call", "Lightning Bolt"])
    bear = token(s, "p1", "Bear", "2/2")
    aura = enchant(s, "Druid's Call", bear, G=2)
    cast_on(s, "Lightning Bolt", bear, R=1)
    assert dead(s, bear)  # 704.5g
    assert s.state.cards[aura.id].zone.endswith(":graveyard")  # 704.5m
    assert len(squirrels(s)) == 3  # 603.2: the Aura was attached as the damage was dealt
    check(s)


def test_druids_call_makes_squirrels_for_survivable_damage(cards):
    s = build(cards, ["Druid's Call", "Lightning Bolt"])
    bear = token(s, "p1", "Bear", "4/4")
    aura = enchant(s, "Druid's Call", bear, G=2)
    cast_on(s, "Lightning Bolt", bear, R=1)
    assert s.state.cards[bear.id].zone.endswith(":battlefield") and s.state.cards[aura.id].attached_to == bear.id
    assert len(squirrels(s)) == 3
    check(s)


def test_the_enchanted_creatures_controller_gets_the_squirrels(cards):
    """"its controller creates": Bob, whose 2/2 Alice's Druid's Call enchants, gets them (as it last existed, 608.2h)."""
    s = build(cards, ["Druid's Call", "Lightning Bolt"])
    bear = token(s, "p2", "Bear", "2/2")
    enchant(s, "Druid's Call", bear, G=2)
    cast_on(s, "Lightning Bolt", bear, R=1)
    assert dead(s, bear)
    assert [c.controller for c in squirrels(s)] == ["p2"] * 3
    check(s)


def test_an_aura_on_another_creature_triggers_nothing(cards):
    s = build(cards, ["Druid's Call", "Lightning Bolt"])
    bear, other = token(s, "p1", "Bear", "2/2"), token(s, "p1", "Goat", "2/2")
    enchant(s, "Druid's Call", other, G=2)
    cast_on(s, "Lightning Bolt", bear, R=1)
    assert dead(s, bear) and not squirrels(s)
    check(s)


@pytest.mark.parametrize(("aura", "mana"), [
    ("Binding Agony", {"R": 1, "B": 1, "C": 1}),  # "this Aura deals that much damage to that creature's controller"
    ("Ragged Veins", {"B": 1, "C": 1}),  # "its controller loses that much life"
    ("Spiteful Shadows", {"B": 2}),  # "it deals that much damage to its controller"
])
def test_the_controller_of_the_dead_creature_is_hurt(cards, aura, mana):
    s = build(cards, [aura, "Lightning Bolt"])
    bear = token(s, "p2", "Bear", "2/2")
    enchant(s, aura, bear, **mana)
    cast_on(s, "Lightning Bolt", bear, R=1)
    assert dead(s, bear) and life(s, "p2") == 37
    check(s)


def test_sleep_magic_has_nothing_left_to_sacrifice(cards):
    """"When enchanted creature is dealt damage, sacrifice this Aura": it triggers (the Aura was attached), and finds the Aura already gone."""
    s = build(cards, ["Sleep Magic", "Lightning Bolt"])
    bear = token(s, "p1", "Bear", "2/2")
    aura = enchant(s, "Sleep Magic", bear, U=3)
    cast_on(s, "Lightning Bolt", bear, R=1)
    assert dead(s, bear) and s.state.cards[aura.id].zone == "p1:graveyard" and not s.state.zones.get("stack")
    check(s)


# -- combat: the host deals and is dealt its damage and dies in the same combat damage step (510.2, 704.3) ----------------------------
def test_jitte_gets_its_counters_when_the_equipped_creature_dies_in_the_combat_damage(cards):
    """The Ape deals 2 combat damage to the blocker and is dealt 3 at the same time (510.2): it dies, but its damage was dealt, so Jitte triggers."""
    s = build(cards, ["Umezawa's Jitte"], forests=20)
    jitte, ape, big = put(s, "Umezawa's Jitte"), token(s, "p1", "Ape", "2/2"), token(s, "p2", "Big", "3/3")
    equip(s, jitte, ape, 5, C=2)
    to_main1(s, 3)
    attack(s, (ape, "p2"))
    block(s, (big, ape))
    s = combat(s)
    assert dead(s, ape) and s.state.cards[big.id].damage == 2
    assert s.state.cards[jitte.id].counters == {"charge": 2} and s.state.cards[jitte.id].attached_to is None  # (704.5n)
    check(s)


def test_a_trampling_equipped_creature_dies_to_deathtouch_but_still_made_its_treasure(cards):
    """702.19b, 702.2: the 4/4 trampler assigns 1 to the deathtouch Viper and 3 to Bob; the Viper's damage kills it as Goldvein Pick triggers."""
    s = build(cards, ["Goldvein Pick"], forests=20)
    pick, rhino = put(s, "Goldvein Pick"), token(s, "p1", "Rhino", "3/3", "Trample")
    viper = token(s, "p2", "Viper", "1/1", "Deathtouch")
    equip(s, pick, rhino, 2, C=1)
    to_main1(s, 3)
    attack(s, (rhino, "p2"))
    block(s, (viper, rhino))
    d = s.state.rules.decision
    assert d is not None and d.kind == "divide"
    act(s, "p1", type="choose", decision_id=d.id, amounts=[1, 3])
    s = combat(s)
    assert dead(s, rhino) and life(s, "p2") == 37
    assert [c.name for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Treasure"] == ["Treasure"]
    check(s)


def test_soul_link_gains_life_for_the_damage_dealt_and_the_damage_taken_by_a_creature_that_dies(cards):
    """Both abilities: the 2/2 deals 2 and is dealt 3 at once and dies (the Aura follows it, 704.5m): 5 life."""
    s = build(cards, ["Soul Link"], forests=20)
    ape, big = token(s, "p1", "Ape", "2/2"), token(s, "p2", "Big", "3/3")
    enchant(s, "Soul Link", ape, W=1, B=1, C=1)
    to_main1(s, 3)
    before = life(s, "p1")
    attack(s, (ape, "p2"))
    block(s, (big, ape))
    s = combat(s)
    assert dead(s, ape) and life(s, "p1") == before + 5
    check(s)


def test_an_ability_the_aura_gave_the_dying_creature_triggers_too(cards):
    """Combat Research gives the Rhino "Whenever this creature deals combat damage to a player, draw a card." The Rhino is the trigger's source and has left
    the battlefield (with its Aura) by the time the trigger is looked at: its last known information has the ability (603.10a)."""
    s = build(cards, ["Combat Research"], forests=20)
    rhino, viper = token(s, "p1", "Rhino", "3/3", "Trample"), token(s, "p2", "Viper", "1/1", "Deathtouch")
    enchant(s, "Combat Research", rhino, U=1)
    to_main1(s, 3)
    attack(s, (rhino, "p2"))
    block(s, (viper, rhino))
    d = s.state.rules.decision
    assert d is not None and d.kind == "divide"
    start = len(s.state.zones["p1:library"])
    act(s, "p1", type="choose", decision_id=d.id, amounts=[1, 2])
    s = combat(s)
    assert dead(s, rhino) and life(s, "p2") == 38 and len(s.state.zones["p1:library"]) == start - 1
    check(s)


def test_komainu_battle_armor_goads_when_the_creature_it_equips_dies_dealing_combat_damage_to_a_player(cards):
    """"Whenever this creature or equipped creature deals combat damage to a player, goad each creature that player controls" (701.15): the 5/5 menace trampler
    assigns 1 to each deathtouch Viper and 3 to Bob, and dies; Bob's Wall that did not block is goaded."""
    s = build(cards, ["Komainu Battle Armor"], forests=20)
    armor, rhino = put(s, "Komainu Battle Armor"), token(s, "p1", "Rhino", "3/3", "Trample")
    vipers, wall = [token(s, "p2", f"Viper{i}", "1/1", "Deathtouch") for i in (1, 2)], token(s, "p2", "Wall", "0/4")
    equip(s, armor, rhino, 4, C=4)  # (reconfigure {4}: attach to target creature you control, 702.151a)
    assert s.state.cards[armor.id].attached_to == rhino.id
    to_main1(s, 3)
    attack(s, (rhino, "p2"))
    block(s, *[(v, rhino) for v in vipers])
    d = s.state.rules.decision
    assert d is not None and d.kind == "divide"
    act(s, "p1", type="choose", decision_id=d.id, amounts=[1, 1, 3])
    s = combat(s)
    assert dead(s, rhino) and life(s, "p2") == 37
    assert "goaded:p1" in ch(s, wall).imposed
    check(s)


# -- Fiendlash: "it deals damage equal to its power to target player or planeswalker" -------------------------------------------
def fiendlash_kill(s, moved, pick="p2"):
    """Fiendlash (4/2 reach on a 2/2) equips the Ape, then the Boar if ``moved``; Alice bolts the Ape (the first option of every decision, but ``pick``)."""
    lash = put(s, "Fiendlash")
    ape, boar = token(s, "p1", "Ape", "2/2"), token(s, "p1", "Boar", "2/2")
    equip(s, lash, ape, 2, R=1, C=2)
    if moved:
        equip(s, lash, boar, 2, R=1, C=2)
    c = to_hand(s, "Lightning Bolt")
    pay(s, R=1)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[ape.id])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            choose(s, pick if pick in ids else ids[0])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return ape
    raise AssertionError("never settled")


def test_fiendlash_deals_the_power_the_dead_creature_last_had(cards):
    """608.2h: the Ape as it last existed had 4 power with the Equipment: Bob goes to 36."""
    s = build(cards, ["Fiendlash", "Lightning Bolt"], forests=20)
    ape = fiendlash_kill(s, False)
    assert dead(s, ape) and life(s, "p2") == 36 and life(s, "p1") == 40
    check(s)


def test_an_equipment_that_moved_on_triggers_nothing_for_the_first_creature(cards):
    """301.5: Fiendlash equips the Boar when the Ape is bolted."""
    s = build(cards, ["Fiendlash", "Lightning Bolt"], forests=20)
    ape = fiendlash_kill(s, True)
    assert dead(s, ape) and life(s, "p2") == 40 and life(s, "p1") == 40
    check(s)
