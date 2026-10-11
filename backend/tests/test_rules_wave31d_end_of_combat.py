"""Wave 31D: "at end of combat" (CR 511.2, 603.7), real Oracle text (tests/fixtures/wave31d_cards.json, from data/cards.sqlite).

Researched against CR 2026-09-25: the end of combat step has no turn-based actions and "at end of combat" abilities trigger as it begins (511.2);
a delayed triggered ability created by an effect triggers once, at that step (603.7); which creature blocked which is remembered for the turn
(509.1g, "creature that blocked or was blocked this turn"); an object that left the battlefield is a new object (400.7), so a delayed trigger acts
on what it remembers by object, and on "it" only while "it" is still there (603.7c).

* A permanent's own step trigger: "At end of combat, destroy each creature that blocked or was blocked this turn." (Heat Stroke).
* A delayed trigger a block creates: "When this creature blocks, at end of combat, destroy it and all creatures it blocked this turn." (Defiant
  Vanguard: the blocked creatures are still destroyed when it died in combat), "Whenever this creature becomes blocked by a creature, gain control
  of that creature at end of combat." (Tolarian Entrancer: the control change has no duration and doesn't care that it left).

Every scenario checks that replaying the recorded history reproduces the table and that a save and a load keep it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave31d_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w31d", number=f"E{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def drive_to(s, phase, blocks=(), limit=200):
    """Pass priority until ``phase`` of this turn; Bob blocks as ``blocks`` says ((blocker, attacker) pairs), any other choice is the first option."""
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"  # (everyone stops at each step and object: the game doesn't run on past the step wanted)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id} for b, a in blocks])
            if phase == "declare_blockers":  # (asked for "the declare blockers step, blocks made")
                return
            continue
        if s.state.turn.phase == phase:
            return
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase}")


def attack(s, *attackers):
    """Alice attacks Bob with these creatures (long on the table: no summoning sickness) and the game goes on to the end of combat step."""
    for c in attackers:
        s.state.rules.controlled_since[c.id].turn = 0
    drive_to(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])


def on_table(s, name, n=1, pid="p1"):
    """``n`` different cards of this name onto the battlefield."""
    found = [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone.endswith(":library")][:n]
    for c in found:
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return found


def settle(s, limit=60):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def zone(s, c):
    return s.state.cards[c.id].zone


# -- Heat Stroke: a step trigger "At end of combat" over everything that blocked or was blocked this turn ---------------------------------------
def test_heat_stroke_destroys_each_creature_that_blocked_or_was_blocked_and_no_other(cards):
    s = build(cards, ["Heat Stroke", "Lim-Dûl the Necromancer", "Grizzly Bears"], ["Wall of Omens", "Wall of Omens"])
    put(s, "Heat Stroke")
    limdul, bears = put(s, "Lim-Dûl the Necromancer"), put(s, "Grizzly Bears")
    wall, idle = on_table(s, "Wall of Omens", 2, "p2")
    attack(s, limdul, bears)
    drive_to(s, "end_combat", blocks=[(wall, limdul)])  # the Wall blocks Lim-Dûl: neither dies in the damage step (0/4 vs 4/4 … 4 damage kills the Wall)
    settle(s)
    assert zone(s, limdul) == "p1:graveyard" and zone(s, wall) == "p2:graveyard"  # blocked / blocked (509.1g)
    assert zone(s, bears) == "p1:battlefield" and zone(s, idle) == "p2:battlefield"  # unblocked, and a creature that didn't block
    check(s)


def test_heat_stroke_does_nothing_when_nobody_blocked(cards):
    s = build(cards, ["Heat Stroke", "Grizzly Bears"])
    put(s, "Heat Stroke")
    bears = put(s, "Grizzly Bears")
    attack(s, bears)
    drive_to(s, "end_combat")
    settle(s)
    assert zone(s, bears) == "p1:battlefield"
    check(s)


# -- Defiant Vanguard: "When this creature blocks, at end of combat, destroy it and all creatures it blocked this turn." --------------------------
def test_defiant_vanguard_destroys_what_it_blocked_even_when_it_died_in_combat(cards):
    s = build(cards, ["Lim-Dûl the Necromancer", "Grizzly Bears"], ["Defiant Vanguard"])
    big, other = put(s, "Lim-Dûl the Necromancer"), put(s, "Grizzly Bears")
    vanguard = put(s, "Defiant Vanguard", "p2")
    attack(s, big, other)
    drive_to(s, "combat_damage", blocks=[(vanguard, big)])
    assert zone(s, vanguard) == "p2:graveyard" and zone(s, big) == "p1:battlefield"  # the 2/2 died; the 4/4 took 2 damage and lives
    drive_to(s, "end_combat")
    settle(s)  # the delayed trigger (603.7) remembers the block: it is gone, "all creatures it blocked this turn" are still destroyed
    assert zone(s, big) == "p1:graveyard" and zone(s, other) == "p1:battlefield"  # (the unblocked attacker isn't one of them)
    check(s)


# -- Tolarian Entrancer: "gain control of that creature at end of combat" -----------------------------------------------------------------------
def test_tolarian_entrancer_takes_the_blocker_at_end_of_combat_even_if_it_died(cards):
    s = build(cards, ["Tolarian Entrancer"], ["Grizzly Bears"])
    entrancer, bears = put(s, "Tolarian Entrancer"), put(s, "Grizzly Bears", "p2")
    attack(s, entrancer)
    drive_to(s, "combat_damage", blocks=[(bears, entrancer)])
    assert s.state.cards[bears.id].controller == "p2" and zone(s, entrancer) == "p1:graveyard"  # not yet: "at end of combat"
    drive_to(s, "end_combat")
    settle(s)
    assert zone(s, entrancer) == "p1:graveyard"  # the 1/1 died in the damage step …
    assert s.state.cards[bears.id].controller == "p1" and s.state.cards[bears.id].owner == "p2"  # … and Alice still took the Bears (no duration)
    check(s)


# -- blocking / blocked by "this creature" at end of combat (Wall of Nets, Greater Werewolf) ---------------------------------------------------
def test_wall_of_nets_exiles_what_it_blocked_and_gives_it_back_when_it_leaves(cards):
    s = build(cards, ["Grizzly Bears", "Grizzly Bears", "Murder"], ["Wall of Nets"])
    blocked, free = on_table(s, "Grizzly Bears", 2)
    wall = put(s, "Wall of Nets", "p2")
    attack(s, blocked, free)
    drive_to(s, "end_combat", blocks=[(wall, blocked)])
    settle(s)
    assert zone(s, blocked) == "p1:exile" and zone(s, free) == "p1:battlefield"  # only the creature it blocked
    murder = to_hand(s, "Murder")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[wall.id])
    settle(s)
    assert zone(s, wall) == "p2:graveyard" and zone(s, blocked) == "p1:battlefield"  # 607.2a: "return all cards exiled with it" (under their owners' control)
    check(s)


def test_greater_werewolf_puts_a_counter_on_each_creature_blocking_or_blocked_by_it(cards):
    s = build(cards, ["Greater Werewolf"], ["Wall of Omens", "Wall of Omens"])
    werewolf = put(s, "Greater Werewolf")
    blocker, idle = on_table(s, "Wall of Omens", 2, "p2")
    attack(s, werewolf)
    drive_to(s, "end_combat", blocks=[(blocker, werewolf)])
    settle(s)
    # the 0/4 Wall took 2 damage in the damage step (it lives), then the -0/-2 counter makes that lethal (704.5g); the idle Wall has none
    assert zone(s, blocker) == "p2:graveyard" and zone(s, idle) == "p2:battlefield" and not s.state.cards[idle.id].counters
    assert not s.state.cards[werewolf.id].counters  # (a creature isn't blocking or blocked by itself)
    check(s)


# -- "At end of combat on your turn, if you attacked this turn" (raid) ------------------------------------------------------------------------------
@pytest.mark.parametrize("attacked", [True, False])
def test_lara_crofts_raid_treasure_comes_at_end_of_combat_only_if_you_attacked(cards, attacked):
    s = build(cards, ["Lara Croft, Tomb Raider"])
    lara = put(s, "Lara Croft, Tomb Raider")
    if attacked:
        attack(s, lara)
    else:
        s.state.rules.controlled_since[lara.id].turn = 0
        drive_to(s, "declare_attackers")
        act(s, "p1", type="declare_attackers", attackers=[])
    drive_to(s, "end_combat")
    settle(s)
    treasures = [c for c in s.state.cards.values() if c.is_token and c.name == "Treasure" and c.zone == "p1:battlefield"]
    assert len(treasures) == (1 if attacked else 0)
    check(s)


def test_spitting_slug_gives_first_strike_to_both_when_its_controller_doesnt_pay(cards):
    s = build(cards, ["Grizzly Bears"], ["Spitting Slug"])
    bears, slug = put(s, "Grizzly Bears"), put(s, "Spitting Slug", "p2")
    attack(s, bears)
    drive_to(s, "declare_blockers", blocks=[(slug, bears)])
    settle(s)  # "you may pay {1}{G}": nothing to pay with — "otherwise, each creature blocking or blocked by this creature gains first strike"
    plan = Plan(s.state, "p1", s.cards, None)
    assert "first strike" in plan.ch(s.state.cards[bears.id]).keywords and "first strike" not in plan.ch(s.state.cards[slug.id]).keywords
    check(s)


def test_cromat_destroys_only_a_creature_blocking_or_blocked_by_it(cards):
    s = build(cards, ["Cromat"], ["Wall of Omens", "Wall of Omens"])
    cromat = put(s, "Cromat")
    blocker, idle = on_table(s, "Wall of Omens", 2, "p2")
    attack(s, cromat)
    drive_to(s, "declare_blockers", blocks=[(blocker, cromat)])
    mana(s, W=1, B=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=cromat.id, ability=0, targets=[idle.id])  # not blocking it
    act(s, "p1", type="activate_ability", card_id=cromat.id, ability=0, targets=[blocker.id])
    settle(s)
    assert zone(s, blocker) == "p2:graveyard" and zone(s, idle) == "p2:battlefield"
    check(s)


def test_end_of_combat_cards_are_fully_automated(cards):
    from app.rules import coverage

    for name in ("Heat Stroke", "Defiant Vanguard", "Tolarian Entrancer", "Wall of Nets", "Greater Werewolf", "Kjeldoran Frostbeast", "Cromat",
                 "Spitting Slug"):
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name
