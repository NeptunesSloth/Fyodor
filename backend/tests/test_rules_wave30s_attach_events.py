"""Wave 30S: "becomes attached" / "becomes unattached" triggers (CR 2026-09-25), real Oracle text (tests/fixtures/wave30s_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 603.2e: "becomes attached" triggers only at the time it happens — not when the state already exists, so equipping the creature an
  Equipment already equips (701.3b) triggers nothing.
* 701.3d, 603.10c: an Aura / Equipment that stops being attached to something — it moves, the permanent leaves, it leaves the battlefield,
  or it stops being an Equipment — "becomes unattached", looking back in time.
* Rulings: an Aura that enters attached to a creature "becomes attached" to it (Brood Keeper, Siona); "you won't be able to sacrifice it"
  when you don't control the permanent an Equipment let go of.
"""

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
from tests.test_rules_attachments import token
from tests.test_rules_copy import pay
from tests.test_rules_effects import pass_until_stack_empty
from tests.wave9c_kit import build, check, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30s_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t30s", number=f"B{i:02d}", **{k: v for k, v in c.items() if k not in ("name", "layout", "card_faces")})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
EXTRA.append(card("Probe Shatter", set_code="t30s", number="B90", mana_cost="{R}", cmc=1.0, type_line="Instant",
                  oracle_text="Destroy target artifact.", colors=["R"], color_identity=["R"]))


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def equip(s, equipment, creature, ability, **mana):
    """Activate the Equipment's equip ability (702.6a; its Oracle line ``ability``) on ``creature`` and let it resolve."""
    pay(s, **mana)
    act(s, "p1", type="activate_ability", card_id=equipment.id, ability=ability, targets=[creature.id])
    pass_until_stack_empty(s)


def cast_on(s, name, target, **mana):
    c = to_hand(s, name)
    pay(s, **mana)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[target.id])
    pass_until_stack_empty(s)
    return c


def on_table(s, name):
    return [c for c in s.state.cards.values() if c.name == name and c.zone.endswith(":battlefield")]


# (Captain's Hook stays PARTIAL: "is a Pirate in addition to its other creature types" is another line's business; its trigger is tested below)
@pytest.mark.parametrize("name", [c["name"] for c in DATA if c["name"] != "Captain's Hook"])
def test_the_cards_are_full(name):
    data = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or []}).level == "FULL"


def test_energy_blade_taps_what_it_becomes_attached_to_once(cards):
    """Enormous Energy Blade: equipping the creature it already equips does nothing (701.3b), so nothing triggers (603.2e)."""
    s = build(cards, ["Enormous Energy Blade"])
    bear, goat = token(s, "p1", "Bear"), token(s, "p1", "Goat")
    blade = put(s, "Enormous Energy Blade")
    equip(s, blade, bear, 2, C=2)
    assert s.state.cards[blade.id].attached_to == bear.id and s.state.cards[bear.id].tapped
    act(s, "p1", type="tap", card_ids=[bear.id], tapped=False)
    equip(s, blade, bear, 2, C=2)
    assert not s.state.cards[bear.id].tapped
    equip(s, blade, goat, 2, C=2)
    assert s.state.cards[goat.id].tapped and not s.state.cards[bear.id].tapped and s.state.cards[blade.id].attached_to == goat.id
    act(s, "p1", type="tap", card_ids=[goat.id], tapped=False)
    act(s, "p1", type="set_controller", card_ids=[blade.id], player="p2")  # 301.5d: a new controller of the Equipment doesn't move it
    pass_until_stack_empty(s)
    assert s.state.cards[blade.id].attached_to == goat.id and not s.state.cards[goat.id].tapped
    check(s)


@pytest.mark.parametrize(("name", "made", "count"), [("Brood Keeper", "Dragon", 1), ("Bramble Elemental", "Saproling", 2)])
def test_an_aura_becoming_attached_to_this_creature_triggers_it(cards, name, made, count):
    """An Aura entering attached to it counts as becoming attached (rulings 2014-07-18); one attached to another creature doesn't."""
    s = build(cards, [name, "Holy Strength"])
    keeper, bear = put(s, name), token(s, "p1", "Bear")
    cast_on(s, "Holy Strength", bear, W=1)
    assert not on_table(s, made)
    cast_on(s, "Holy Strength", keeper, W=1)
    assert len(on_table(s, made)) == count
    check(s)


def test_siona_wants_your_aura_on_your_creature(cards):
    """"Whenever an Aura you control becomes attached to a creature you control": not onto an opponent's creature."""
    s = build(cards, ["Siona, Captain of the Pyleas", "Holy Strength"])
    put(s, "Siona, Captain of the Pyleas")
    theirs, mine = token(s, "p2", "Theirs"), token(s, "p1", "Mine")
    cast_on(s, "Holy Strength", theirs, W=1)
    assert not on_table(s, "Human Soldier")
    aura = cast_on(s, "Holy Strength", mine, W=1)
    assert len(on_table(s, "Human Soldier")) == 1
    act(s, "p1", type="set_damage", card_ids=[mine.id], value=9)  # the creature dies: the Aura is put into the graveyard (704.5m), nothing else happens
    act(s, "p1", type="pass_priority")
    pass_until_stack_empty(s)
    assert s.state.cards[aura.id].zone == "p1:graveyard" and len(on_table(s, "Human Soldier")) == 1
    check(s)


def test_wargear_makes_you_sacrifice_what_it_let_go_of(cards):
    """Grafted Wargear (701.3d): equipping another creature, or the Equipment leaving, unattaches it (603.10c: looking back in time)."""
    s = build(cards, ["Grafted Wargear", "Probe Shatter"])
    bear, goat, ox = token(s, "p1", "Bear"), token(s, "p1", "Goat"), token(s, "p1", "Ox")
    gear = put(s, "Grafted Wargear")
    equip(s, gear, bear, 2)
    equip(s, gear, bear, 2)  # 701.3b: nothing moves — it doesn't become unattached
    assert bear.id in s.state.cards
    equip(s, gear, goat, 2)
    assert bear.id not in s.state.cards and goat.id in s.state.cards  # sacrificed (a token ceases to exist)
    cast_on(s, "Probe Shatter", gear, R=1)  # it leaves the battlefield: unattached from the goat
    pass_until_stack_empty(s)
    assert goat.id not in s.state.cards and ox.id in s.state.cards
    check(s)


def test_a_creature_that_left_has_nothing_to_sacrifice(cards):
    """The equipped creature dies: the Equipment is unattached (704.5n) and its trigger finds nothing — no error, no other loss."""
    s = build(cards, ["Grafted Wargear"])
    bear, goat = token(s, "p1", "Bear"), token(s, "p1", "Goat")
    gear = put(s, "Grafted Wargear")
    equip(s, gear, bear, 2)
    act(s, "p1", type="set_damage", card_ids=[bear.id], value=9)
    act(s, "p1", type="pass_priority")
    pass_until_stack_empty(s)
    assert bear.id not in s.state.cards and goat.id in s.state.cards
    assert s.state.cards[gear.id].zone == "p1:battlefield" and s.state.cards[gear.id].attached_to is None
    check(s)


def test_you_cant_sacrifice_what_someone_else_controls(cards):
    """Rulings 2004-12-01: Wargear ends up on an opponent's creature; when it lets go you can't sacrifice that creature."""
    s = build(cards, ["Grafted Wargear"])
    bear, goat = token(s, "p1", "Bear"), token(s, "p1", "Goat")
    gear = put(s, "Grafted Wargear")
    equip(s, gear, bear, 2)
    act(s, "p1", type="set_controller", card_ids=[bear.id], player="p2")
    equip(s, gear, goat, 2)
    assert bear.id in s.state.cards and s.state.cards[bear.id].controller == "p2"
    check(s)


def test_captains_hook_destroys_it(cards):
    s = build(cards, ["Captain's Hook"])
    bear, goat = token(s, "p1", "Bear"), token(s, "p1", "Goat")
    hook = put(s, "Captain's Hook")
    equip(s, hook, bear, 2, C=1)
    equip(s, hook, goat, 2, C=1)
    assert bear.id not in s.state.cards and goat.id in s.state.cards
    check(s)
