"""Wave 45A: "the player or planeswalker it's attacking" and "non-outlaw" (CR 2026-09-25), real Oracle text (tests/fixtures/wave45a_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 508.5, 120.3, 306.8: "Whenever a creature you control attacks, this creature deals 1 damage to the player or planeswalker it's attacking." (Hellrider [5773]),
  Scorch Spitter [13741], Raid Bombardment [3544], Cavalcade of Calamity [9794], Mage Slayer [4403], Fathom Fleet Swordjack [8883], Rakdos Roustabout [26391] -
  one creature at a time, each damages what it attacks: the player, or the planeswalker (loyalty); a creature that left the battlefield before the ability
  resolved still damages what it attacked (Raid Bombardment ruling 2018-12-07, Cavalcade of Calamity 2019-01-25); a creature that is still on the battlefield but
  was removed from combat damages nothing (Fathom Fleet Swordjack ruling 2020-11-10); a battle, or a planeswalker that has left, is nothing (Raid Bombardment 2023-09-01).
* 700.12a: "Destroy target non-outlaw creature." (Shoot the Sheriff [4184]), "2 damage to each non-outlaw creature" (Caught in the Crossfire) - none of
  Assassin, Mercenary, Pirate, Rogue, Warlock.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave5j_token_copies import drive
from tests.test_rules_wave34b_activated import activate, next_turn, stops
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of
from tests.wave45a_kit import FULL, cast, life, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def walker(s, pid="p2", loyalty=5):
    act(s, pid, type="create_token", player=pid, token={"name": "Walker", "type_line": "Token Legendary Planeswalker — Test"})
    w = card_named(s, "Walker", pid)
    act(s, pid, type="counter", card_ids=[w.id], kind="loyalty", delta=loyalty)
    return w


def loyalty(s, w):
    return s.state.cards[w.id].counters.get("loyalty", 0)


def declare(s, *pairs):
    """Alice's declare attackers step, these (creature, target) pairs declared; the stack is left as the attack put it (her triggers on it)."""
    stops(s)
    next_turn(s)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in pairs])


def test_hellrider_damages_what_each_attacker_attacks_a_player_or_a_planeswalker(cards):
    s = build(cards, ["Hellrider", "Grizzly Bears"], [])
    hell, bears = put(s, "Hellrider"), put(s, "Grizzly Bears")
    w = walker(s)
    declare(s, (hell, w.id), (bears, "p2"))
    assert len(s.state.zones["stack"]) == 2  # 603.2: one trigger for each attacking creature (the Bears and Hellrider itself)
    drive(s)
    # 508.5: Hellrider's own attack at the planeswalker costs it 1 loyalty; the Bears' attack at Bob costs him 1 life (the damage is not combat damage)
    assert (loyalty(s, w), life(s, "p2")) == (4, 39)
    check(s)


def test_scorch_spitter_damages_the_player_it_attacks(cards):
    s = build(cards, ["Scorch Spitter"], [])
    spitter = put(s, "Scorch Spitter")
    declare(s, (spitter, "p2"))
    drive(s)
    assert life(s, "p2") == 39
    check(s)


def test_a_creature_that_left_the_battlefield_still_damages_the_planeswalker_it_was_attacking(cards):
    # Raid Bombardment's ruling 2018-12-07: the attacker left before the ability resolved - it damages what that creature was attacking before it left
    s = build(cards, ["Raid Bombardment", "Grizzly Bears"], [])
    put(s, "Raid Bombardment")
    bears = put(s, "Grizzly Bears")
    w = walker(s)
    declare(s, (bears, w.id))
    assert len(s.state.zones["stack"]) == 1
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "graveyard"})
    drive(s)
    assert loyalty(s, w) == 4 and life(s, "p2") == 40
    check(s)


def test_a_creature_that_is_attacking_a_player_with_power_over_two_does_not_trigger_raid_bombardment(cards):
    s = build(cards, ["Raid Bombardment", "Shivan Dragon"], [])
    put(s, "Raid Bombardment")
    dragon = put(s, "Shivan Dragon")
    declare(s, (dragon, "p2"))
    assert not s.state.zones.get("stack")  # power 5: more than 2
    check(s)


def test_a_creature_removed_from_combat_but_still_on_the_battlefield_damages_nothing(cards):
    # Fathom Fleet Swordjack's ruling 2020-11-10: it remains on the battlefield but leaves combat before the ability resolves - no player or planeswalker is dealt damage
    s = build(cards, ["Scorch Spitter", "Reconnaissance"], [])
    spitter = put(s, "Scorch Spitter")
    put(s, "Reconnaissance")
    declare(s, (spitter, "p2"))
    activate(s, "p1", card_named(s, "Reconnaissance"), "Remove target attacking creature", targets=[spitter.id])
    drive(s)
    assert zone_of(s, "Scorch Spitter") == "p1:battlefield" and s.state.cards[spitter.id].attacking is None
    assert life(s, "p2") == 40
    check(s)


def test_a_planeswalker_that_left_is_nothing_to_damage(cards):
    s = build(cards, ["Scorch Spitter"], [])
    spitter = put(s, "Scorch Spitter")
    w = walker(s)
    declare(s, (spitter, w.id))
    act(s, "p2", type="move", card_ids=[w.id], to={"player": "p2", "zone": "graveyard"})
    drive(s)
    assert life(s, "p2") == 40  # (a token planeswalker ceased to exist; the Spitter is "attacking" nothing)
    check(s)


def test_mage_slayer_has_the_equipped_creature_deal_damage_equal_to_its_power_to_what_it_attacks(cards):
    s = build(cards, ["Mage Slayer", "Hill Giant"], [])
    giant, slayer = put(s, "Hill Giant"), put(s, "Mage Slayer")
    act(s, "p1", type="attach", card_ids=[slayer.id], to=giant.id)
    w = walker(s)
    declare(s, (giant, w.id))
    drive(s)
    assert loyalty(s, w) == 5 - 3  # Hill Giant's power 3: damage dealt by the creature (120.3), to the planeswalker it attacks (306.8: loyalty counters removed)
    assert life(s, "p2") == 40
    check(s)


def test_fathom_fleet_swordjack_damages_by_the_number_of_artifacts_you_control(cards):
    s = build(cards, ["Fathom Fleet Swordjack"], [])
    swordjack = put(s, "Fathom Fleet Swordjack")
    act(s, "p1", type="create_token", player="p1", token={"name": "Rock", "type_line": "Token Artifact — Test"})
    declare(s, (swordjack, "p2"))
    drive(s)
    assert life(s, "p2") == 40 - 1  # one artifact (the Rock; Swordjack itself is a creature, not an artifact)
    check(s)


def test_cavalcade_of_calamity_checks_power_one_or_less(cards):
    s = build(cards, ["Cavalcade of Calamity", "Goblin Piker"], [])
    put(s, "Cavalcade of Calamity")
    piker = put(s, "Goblin Piker")
    declare(s, (piker, "p2"))
    assert not s.state.zones.get("stack")  # a 2/1: power 2 isn't 1 or less
    check(s)


def test_rakdos_roustabout_damages_the_player_it_attacks_when_it_becomes_blocked(cards):
    s = build(cards, ["Rakdos Roustabout"], ["Grizzly Bears"])
    roustabout, bears = put(s, "Rakdos Roustabout"), put(s, "Grizzly Bears", "p2")
    declare(s, (roustabout, "p2"))
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": roustabout.id}])
    drive(s)
    assert life(s, "p2") == 39  # 508.5: it's still attacking Bob, though blocked - one damage to him (not combat damage)
    check(s)


# ---- Shoot the Sheriff [4184], Caught in the Crossfire ---------------------------------------------------------------------------------------------------
def outlaw_table(cards):
    s = build(cards, ["Shoot the Sheriff"], ["Grizzly Bears"], islands=6)
    for name, types in (("Pirate", "Token Creature — Pirate"), ("Human Warlock", "Token Creature — Human Warlock"), ("Bear", "Token Creature — Bear")):
        act(s, "p2", type="create_token", player="p2", token={"name": name, "power": "2", "toughness": "2", "type_line": types})
    to_hand(s, "Shoot the Sheriff")
    mana(s, B=1, C=1)
    return s


def test_shoot_the_sheriff_destroys_a_creature_with_none_of_the_outlaw_types(cards):
    s = outlaw_table(cards)
    cast(s, "Shoot the Sheriff", targets=[card_named(s, "Bear", "p2").id])
    assert zone_of(s, "Shoot the Sheriff") == "p1:graveyard" and "Bear" not in {c.name for c in s.state.cards.values()}  # (a token that died ceased to exist)
    assert {"Pirate", "Human Warlock"} <= {c.name for c in s.state.cards.values()}
    check(s)


@pytest.mark.parametrize("name", ["Pirate", "Human Warlock"])
def test_shoot_the_sheriff_cannot_target_an_outlaw(cards, name):
    s = outlaw_table(cards)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Shoot the Sheriff").id, targets=[card_named(s, name, "p2").id])  # 700.12a: Pirate, Warlock
    check(s)

