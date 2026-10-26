"""Wave 35B: "when that creature dies / leaves the battlefield this turn" triggers bound to the objects a spell named or damaged,
researched against CR 2026-09-25, real Oracle text (tests/fixtures/wave35b_cards.json, from data/cards.sqlite). Every scenario checks the
replay and a save and a load.

* 603.7, 603.7a, 603.7c: a resolving spell creates the delayed triggered ability; it refers to the particular object (the target as chosen,
  or "the creature an opponent controls" of a later target, or every creature "dealt damage this way"); one that left before the
  ability existed is never watched, and one that left and came back is a new object (400.7) that does not trigger it.
* 603.7b: "this turn" is a stated duration: the ability triggers each time (once per creature dealt damage), and is gone at cleanup (514.2).
* 603.10a, 700.4: a dies trigger looks back in time: "its controller's graveyard", "lesser mana value" read the creature as it last existed.
* 603.4: an intervening "if" (Fight for the Throne's commander) is checked as the ability triggers and as it resolves.
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
from tests.game_helpers import act, mana_pool
from tests.test_rules_attachments import token
from tests.test_rules_conditionals import settle, until
from tests.wave9c_kit import build, card_named, cast, check, life, mana, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave35b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w35b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Rushed Rebirth", "Burn Away", "Fatal Fissure", "Adarkar Valkyrie", "Fight for the Throne", "Devouring Tendrils",
        "Skeletonize", "Reckless Blaze", "Ghired's Belligerence"]
# (wave 110D: the other five are FULL now - Touch of Moonglove 110G, Whippoorwill 110G, Heroic Sacrifice 110B, End-Blaze Epiphany and
# Runesword 110K - checked in test_rules_wave110d_dies_manual.py / test_rules_wave110d_runesword.py)
MANUAL = ["Kjeldoran Guard"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def delayed(s):
    return list(s.state.rules.delayed)


def kill(s, victim, value=9):
    """Lethal damage and the state-based action that follows (704.5g), then everything the death triggered."""
    act(s, "p1", type="set_damage", card_ids=[victim.id], value=value)
    act(s, s.state.rules.priority, type="pass_priority")
    settle(s)


def zone(s, c):
    return s.state.cards[c.id].zone


def named_zone(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].zone


# -- coverage ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", FULL)
def test_the_bound_dies_cards_are_full(name):
    from tests.test_rules_scripts import ch as characteristics

    c = next(c for c in DATA if c["name"] == name)
    chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
    assert coverage.of_characteristics(chs).level == "FULL", (name, coverage.of_characteristics(chs).manual_parts)


# -- Rushed Rebirth: "lesser mana value" than the creature as it last existed (603.10a) ----------------------------------
def rebirth(cards, *, blink=False):
    s = build(cards, ["Rushed Rebirth", "Grizzly Bears", "Llanowar Elves", "Young Wolf", "Kitchen Finks", "Cloudshift"], forests=20)
    finks = put(s, "Grizzly Bears", "p1")
    to_hand(s, "Rushed Rebirth")
    mana(s, B=1, G=1)
    cast(s, "Rushed Rebirth", targets=[finks.id], target_counts=[1])
    return s, finks


def test_rushed_rebirth_fetches_a_cheaper_creature_when_that_creature_dies(cards):
    """603.7c: "that creature" is the target as chosen; it dies this turn (Grizzly Bears, mana value 2 as it last existed): a creature card
    with lesser mana value (not Kitchen Finks, 3) goes onto the battlefield tapped, chosen as the trigger resolves."""
    s, finks = rebirth(cards)
    (t,) = delayed(s)
    assert t.when == {"kind": "event", "event": "die"} and t.refs["watch"]["objects"]
    s = reloaded(s)  # (the watch is pending across a save and a load)
    assert len(delayed(s)) == 1
    act(s, "p1", type="set_damage", card_ids=[card_named(s, "Grizzly Bears").id], value=9)
    act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and {o.label for o in d.options} == {"Llanowar Elves", "Young Wolf"}  # (mana value 1 < 2; not Kitchen Finks, 3)
    settle(s)
    fetched = [c for c in s.state.cards.values() if c.owner == "p1" and c.zone == "p1:battlefield" and c.name in ("Llanowar Elves", "Young Wolf")]
    assert len(fetched) == 1 and fetched[0].tapped
    check(s)


def test_rushed_rebirth_does_nothing_if_it_dies_next_turn(cards):
    s, finks = rebirth(cards)
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn, limit=80)
    assert delayed(s) == []  # 514.2: gone at cleanup
    kill(s, finks)
    assert zone(s, finks) == "p1:graveyard"
    assert not any(c.zone == "p1:battlefield" and c.name in ("Llanowar Elves", "Young Wolf") for c in s.state.cards.values())
    check(s)


def test_rushed_rebirth_is_not_about_a_creature_that_was_blinked(cards):
    """400.7: Cloudshift returns Grizzly Bears as a new object; the watch was bound to the old one."""
    s, finks = rebirth(cards)
    to_hand(s, "Cloudshift")
    mana(s, W=1)
    cast(s, "Cloudshift", targets=[finks.id], target_counts=[1])
    assert zone(s, finks) == "p1:battlefield"
    kill(s, finks)
    assert zone(s, finks) == "p1:graveyard"
    assert not any(c.zone == "p1:battlefield" and c.name in ("Llanowar Elves", "Young Wolf") for c in s.state.cards.values())
    check(s)


# -- Burn Away: "its controller's graveyard" (603.10a: the controller as it last was) -----------------------------------------
def test_burn_away_exiles_the_graveyard_of_its_controller_when_the_creature_dies(cards):
    s = build(cards, ["Burn Away"], theirs=["Grizzly Bears", "Llanowar Elves"], forests=10)
    bears = put(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[card_named(s, "Llanowar Elves", "p2").id], to={"zone": "graveyard"})
    to_hand(s, "Burn Away")
    mana(s, R=5)
    cast(s, "Burn Away", targets=[bears.id], target_counts=[1])
    assert zone(s, bears) == "p2:exile" and named_zone(s, "Llanowar Elves", "p2") == "p2:exile"  # (6 damage killed it; then its controller's graveyard)
    assert not [c for c in s.state.cards.values() if c.zone == "p2:graveyard"]
    check(s)


def bounce(s, c, pid="p1"):
    """Out of the battlefield and back (a new object, 400.7), by hand."""
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})


def into_next_turn(s):
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn, limit=80)


def on_battlefield(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:battlefield"]


# -- Fatal Fissure: the deferred ability has a target of its own, chosen as it triggers (603.3d) ---------------------------
def test_fatal_fissure_earthbends_a_land_chosen_as_the_creature_dies(cards):
    s = build(cards, ["Fatal Fissure", "Grizzly Bears"], forests=20)
    bears = put(s, "Grizzly Bears")
    forest = put(s, "Forest")
    to_hand(s, "Fatal Fissure")
    mana(s, B=2)
    cast(s, "Fatal Fissure", targets=[bears.id], target_counts=[1])
    (t,) = delayed(s)
    assert t.target is not None and t.when["event"] == "die"  # (the land is not chosen yet: nothing to earthbend until it dies)
    s = reloaded(s)
    kill(s, card_named(s, "Grizzly Bears"))
    assert s.state.cards[forest.id].counters == {"+1/+1": 4}  # 701.66a: earthbend 4
    assert zone(s, bears) == "p1:graveyard"
    check(s)


def test_fatal_fissure_with_no_land_to_earthbend_triggers_nothing(cards):
    s = build(cards, ["Fatal Fissure", "Grizzly Bears"], forests=20)
    bears = put(s, "Grizzly Bears")
    to_hand(s, "Fatal Fissure")
    mana(s, B=2)
    cast(s, "Fatal Fissure", targets=[bears.id], target_counts=[1])
    kill(s, bears)  # 603.3d: no legal target for the land: the ability is removed from the stack
    assert zone(s, bears) == "p1:graveyard" and not s.state.zones.get("stack") and s.state.rules.decision is None
    check(s)


def test_fatal_fissure_does_nothing_if_the_creature_dies_next_turn(cards):
    s = build(cards, ["Fatal Fissure", "Grizzly Bears"], forests=20)
    bears = put(s, "Grizzly Bears")
    forest = put(s, "Forest")
    to_hand(s, "Fatal Fissure")
    mana(s, B=2)
    cast(s, "Fatal Fissure", targets=[bears.id], target_counts=[1])
    into_next_turn(s)
    assert delayed(s) == []
    kill(s, bears)
    assert s.state.cards[forest.id].counters == {}
    check(s)


# -- Adarkar Valkyrie: another creature's death, returned under your control ---------------------------------------------------
def valkyrie(cards):
    s = build(cards, ["Adarkar Valkyrie"], theirs=["Llanowar Elves"], forests=20)
    valk = put(s, "Adarkar Valkyrie")
    elves = put(s, "Llanowar Elves", "p2")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")  # (no longer summoning sick)
    return s, valk, elves


def test_adarkar_valkyrie_returns_the_creature_that_dies_under_your_control(cards):
    s, valk, elves = valkyrie(cards)
    act(s, "p1", type="activate_ability", card_id=valk.id, ability=1, targets=[elves.id])
    settle(s)
    (t,) = delayed(s)
    assert t.when == {"kind": "event", "event": "die"} and t.until_turn == s.state.turn.number
    s = reloaded(s)
    before = s.state.rules.object_id(elves.id)
    kill(s, elves)
    back = s.state.cards[elves.id]
    assert back.zone == "p1:battlefield" and back.controller == "p1" and back.owner == "p2"  # 400.7: a new object, under Alice's control
    assert s.state.rules.object_id(elves.id) != before and delayed(s) == []
    check(s)


def test_adarkar_valkyrie_does_nothing_for_a_creature_that_was_blinked(cards):
    s, valk, elves = valkyrie(cards)
    act(s, "p1", type="activate_ability", card_id=valk.id, ability=1, targets=[elves.id])
    settle(s)
    bounce(s, elves, "p2")  # 400.7: the watch was bound to the old object
    kill(s, elves)
    assert zone(s, elves) == "p2:graveyard"
    check(s)


def test_adarkar_valkyrie_does_nothing_if_the_creature_dies_next_turn(cards):
    s, valk, elves = valkyrie(cards)
    act(s, "p1", type="activate_ability", card_id=valk.id, ability=1, targets=[elves.id])
    settle(s)
    into_next_turn(s)
    assert delayed(s) == []  # 514.2
    kill(s, elves)
    assert zone(s, elves) == "p2:graveyard"
    check(s)


def test_adarkar_valkyrie_cannot_return_a_token(cards):
    """A token ceases to exist in the graveyard (111.7): there is no card to return (the ability can still target it)."""
    s, valk, elves = valkyrie(cards)
    spirit = token(s, "p2", "Spirit Token", "1/1")
    act(s, "p1", type="activate_ability", card_id=valk.id, ability=1, targets=[spirit.id])
    settle(s)
    assert len(delayed(s)) == 1
    kill(s, spirit)
    assert spirit.id not in s.state.cards or s.state.cards[spirit.id].zone not in ("p1:battlefield", "p2:battlefield")
    assert delayed(s) == []
    check(s)


# -- Fight for the Throne: the target described again, with an intervening "if" (603.4) ---------------------------------------
def throne(cards, *, commander):
    s = build(cards, ["Fight for the Throne", "Grizzly Bears"], theirs=["Llanowar Elves"], forests=20)
    bears = put(s, "Grizzly Bears")
    elves = put(s, "Llanowar Elves", "p2")
    if commander:
        put(s, "Krenko, Mob Boss")
    to_hand(s, "Fight for the Throne")
    mana(s, G=2)
    cast(s, "Fight for the Throne", targets=[bears.id, elves.id], target_counts=[1, 1])
    return s, bears, elves


def test_fight_for_the_throne_makes_you_the_monarch_if_you_control_your_commander(cards):
    s, bears, elves = throne(cards, commander=True)
    assert zone(s, elves) == "p2:graveyard" and s.state.cards[bears.id].counters == {"+1/+1": 1}
    assert s.state.table.monarch == "p1"
    check(s)


def test_fight_for_the_throne_without_your_commander_the_ability_does_not_trigger(cards):
    s, bears, elves = throne(cards, commander=False)
    assert zone(s, elves) == "p2:graveyard" and s.state.table.monarch is None
    check(s)


def test_fight_for_the_throne_is_not_about_a_creature_that_left_before_it_resolved(cards):
    """603.7a: the opponent's creature is gone as the spell resolves: no fight, and nothing to watch — it can't "die this turn" afterwards."""
    s = build(cards, ["Fight for the Throne", "Grizzly Bears"], theirs=["Llanowar Elves"], forests=20)
    bears = put(s, "Grizzly Bears")
    elves = put(s, "Llanowar Elves", "p2")
    put(s, "Krenko, Mob Boss")
    to_hand(s, "Fight for the Throne")
    mana(s, G=2)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Fight for the Throne").id, targets=[bears.id, elves.id], target_counts=[1, 1])
    act(s, "p2", type="move", card_ids=[elves.id], to={"zone": "graveyard"})  # in response
    settle(s)
    assert delayed(s) == [] and s.state.table.monarch is None and s.state.cards[bears.id].damage == 0
    check(s)


def test_fight_for_the_throne_waits_for_the_creature_that_survives_the_fight(cards):
    """The fight (3 damage) doesn't kill a 7-toughness creature; it dies later this turn: "when the creature dies this turn" still
    triggers, after the commander came into play (the "if" is checked as it triggers)."""
    s = build(cards, ["Fight for the Throne", "Grizzly Bears"], theirs=["Garruk's Horde"], forests=20)
    bears = put(s, "Grizzly Bears")
    big = put(s, "Garruk's Horde", "p2")
    to_hand(s, "Fight for the Throne")
    mana(s, G=2)
    cast(s, "Fight for the Throne", targets=[bears.id, big.id], target_counts=[1, 1])
    assert zone(s, big) == "p2:battlefield" and len(delayed(s)) == 1
    put(s, "Krenko, Mob Boss")
    s = reloaded(s)
    kill(s, big)
    assert s.state.table.monarch == "p1"
    check(s)


# -- Devouring Tendrils: "even if it didn't die because of the damage" ------------------------------------------------------------
def tendrils(cards):
    s = build(cards, ["Devouring Tendrils", "Grizzly Bears"], theirs=["Garruk's Horde"], forests=20)
    bears = put(s, "Grizzly Bears")
    big = put(s, "Garruk's Horde", "p2")
    to_hand(s, "Devouring Tendrils")
    mana(s, G=2)
    cast(s, "Devouring Tendrils", targets=[bears.id, big.id], target_counts=[1, 1])
    return s, bears, big


def test_devouring_tendrils_gains_life_when_the_creature_later_dies_for_any_reason(cards):
    s, bears, big = tendrils(cards)
    assert zone(s, big) == "p2:battlefield" and life(s) == 40  # (2 damage; Garruk's Horde has 7 toughness)
    s = reloaded(s)
    kill(s, card_named(s, "Garruk's Horde", "p2"))
    assert life(s) == 42
    check(s)


def test_devouring_tendrils_ignores_a_creature_that_was_blinked(cards):
    s, bears, big = tendrils(cards)
    bounce(s, big, "p2")
    kill(s, big)
    assert life(s) == 40
    check(s)


def test_devouring_tendrils_ignores_a_creature_that_dies_next_turn(cards):
    s, bears, big = tendrils(cards)
    into_next_turn(s)
    kill(s, big)
    assert life(s) == 40 and delayed(s) == []
    check(s)


# -- Skeletonize: every creature dealt damage this way (several triggers, 603.7b) ---------------------------------------------------
def skeletons(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == "Skeleton" and c.zone == f"{pid}:battlefield"]


def skeletonize(cards, creature="Grizzly Bears"):
    s = build(cards, ["Skeletonize"], theirs=[creature], forests=10)
    victim = put(s, creature, "p2")
    to_hand(s, "Skeletonize")
    mana(s, R=5)
    cast(s, "Skeletonize", targets=[victim.id], target_counts=[1])
    return s, victim


def test_skeletonize_makes_a_skeleton_for_you_whoever_controlled_the_creature(cards):
    s, bears = skeletonize(cards)
    assert zone(s, bears) == "p2:graveyard" and len(skeletons(s)) == 1 and not skeletons(s, "p2")  # (the controller of the delayed ability gets it)
    check(s)


def test_skeletonize_a_survivor_that_dies_later_this_turn_still_counts(cards):
    s, big = skeletonize(cards, "Garruk's Horde")
    assert skeletons(s) == [] and len(delayed(s)) == 1 and delayed(s)[0].once is False
    s = reloaded(s)
    kill(s, card_named(s, "Garruk's Horde", "p2"))
    assert len(skeletons(s)) == 1
    check(s)


def test_skeletonize_not_if_blinked_first(cards):
    s, big = skeletonize(cards, "Garruk's Horde")
    bounce(s, big, "p2")
    kill(s, big)
    assert skeletons(s) == []
    check(s)


def test_skeletonize_not_if_it_dies_next_turn(cards):
    s, big = skeletonize(cards, "Garruk's Horde")
    into_next_turn(s)
    kill(s, big)
    assert skeletons(s) == [] and delayed(s) == []
    check(s)


def test_skeletonize_damage_that_was_prevented_was_not_dealt(cards):
    """120.3, 615: only a creature that was actually dealt damage (after prevention) is "dealt damage this way"."""
    s = build(cards, ["Skeletonize"], theirs=["Garruk's Horde", "Test Aegis"], forests=10)
    put(s, "Test Aegis", "p2")
    big = put(s, "Garruk's Horde", "p2")
    to_hand(s, "Skeletonize")
    mana(s, R=5)
    cast(s, "Skeletonize", targets=[big.id], target_counts=[1])
    assert delayed(s) == [] and s.state.cards[big.id].damage == 0
    kill(s, big)
    assert skeletons(s) == []
    check(s)


# -- Reckless Blaze: "a creature you control", as it last was (603.10a) -----------------------------------------------------------------
def test_reckless_blaze_adds_red_for_each_of_your_creatures_dealt_damage_this_way_that_dies(cards):
    s = build(cards, ["Reckless Blaze", "Grizzly Bears", "Llanowar Elves"], theirs=["Kitchen Finks"], forests=20)
    put(s, "Grizzly Bears")
    put(s, "Llanowar Elves")
    token(s, "p1", "Survivor", "2/6")
    put(s, "Kitchen Finks", "p2")
    to_hand(s, "Reckless Blaze")
    mana(s, R=5)
    cast(s, "Reckless Blaze")
    assert mana_pool(s) == {"R": 2}  # (Bears and Elves; the opponent's Finks gives nothing: not a creature you control)
    assert len(delayed(s)) == 1 and delayed(s)[0].once is False
    s = reloaded(s)
    kill(s, next(c for c in s.state.cards.values() if c.name == "Survivor"))
    assert mana_pool(s) == {"R": 3}  # the one that survived 5 damage died later this turn: it was dealt damage this way
    check(s)


def test_reckless_blaze_is_gone_next_turn(cards):
    s = build(cards, ["Reckless Blaze"], forests=20)
    survivor = token(s, "p1", "Survivor", "2/6")
    to_hand(s, "Reckless Blaze")
    mana(s, R=5)
    cast(s, "Reckless Blaze")
    into_next_turn(s)
    assert delayed(s) == []
    before = dict(s.state.players["p1"].mana)
    kill(s, survivor)
    assert s.state.players["p1"].mana == before
    check(s)


# -- Ghired's Belligerence: divided damage, populate for each creature dealt it that dies ---------------------------------------------
def test_ghireds_belligerence_populates_for_each_creature_dealt_damage_that_dies(cards):
    s = build(cards, ["Ghired's Belligerence"], theirs=["Grizzly Bears", "Garruk's Horde"], forests=20)
    token(s, "p1", "Goblin Token", "1/1")
    bears = put(s, "Grizzly Bears", "p2")
    big = put(s, "Garruk's Horde", "p2")
    to_hand(s, "Ghired's Belligerence")
    mana(s, R=5)
    cast(s, "Ghired's Belligerence", targets=[bears.id, big.id], target_counts=[2], division=[2, 1], x_value=3)
    assert zone(s, bears) == "p2:graveyard" and len(on_battlefield(s, "Goblin Token")) == 2  # (Bears died: one populate)
    assert zone(s, big) == "p2:battlefield" and len(delayed(s)) == 1
    s = reloaded(s)
    kill(s, card_named(s, "Garruk's Horde", "p2"))  # 603.7b: it was dealt damage this way too, and died this turn (for any reason)
    assert len(on_battlefield(s, "Goblin Token")) == 3
    check(s)


def test_ghireds_belligerence_two_creatures_dying_together_populate_twice(cards):
    s = build(cards, ["Ghired's Belligerence"], theirs=["Grizzly Bears", "Llanowar Elves"], forests=20)
    token(s, "p1", "Goblin Token", "1/1")
    bears = put(s, "Grizzly Bears", "p2")
    elves = put(s, "Llanowar Elves", "p2")
    to_hand(s, "Ghired's Belligerence")
    mana(s, R=5)
    cast(s, "Ghired's Belligerence", targets=[bears.id, elves.id], target_counts=[2], division=[2, 1], x_value=3)
    assert len(on_battlefield(s, "Goblin Token")) == 3
    check(s)


# -- the sentences that stay manual ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    # War Barge: the object that leaves is the artifact; "that creature" is the target of the first sentence, not the event's object
    "Target creature gains islandwalk until end of turn. When ~ leaves the battlefield this turn, destroy that creature.",
    # two damage instructions: which one is "this way"?
    "~ deals 2 damage to target creature. ~ deals 1 damage to each opponent. Whenever a creature dealt damage this way dies this turn, draw a card.",
    # no damage instruction before it
    "Whenever a creature dealt damage this way dies this turn, draw a card.",
    # a condition on the creature that died is not one the trigger can check yet
    "~ deals 3 damage to target creature. When that creature dies this turn, if it was a Dragon, draw a card.",
    # which of two creatures is "the creature you control"?
    "Target creature you control fights another target creature you control. When the creature you control dies this turn, draw a card.",
])
def test_unclear_shapes_are_not_read(text):
    from app.rules import scripts

    assert scripts.parse_effects(text) is None



@pytest.mark.parametrize("name", MANUAL)
def test_the_shapes_that_need_more_stay_manual(name):
    from tests.test_rules_scripts import ch as characteristics

    c = next(c for c in DATA if c["name"] == name)
    chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
    assert coverage.of_characteristics(chs).level != "FULL"


@pytest.mark.parametrize("name", ["Time to Feed", "Reincarnation"])
def test_exact_target_death_followthrough_now_native(name):
    # Canonical gameplay, original ownership and cold resume are verified in
    # test_rules_bound_delayed35.py; these old refusals are now supported.
    from tests.test_rules_scripts import ch as characteristics

    c = next(c for c in DATA if c["name"] == name)
    assert coverage.of_characteristics(characteristics(c["name"], c["type_line"], c["oracle_text"])).level == "FULL"
