"""Wave 100E: damage equal to a creature's power and "that much" (app/rules/xdamage100e.py; CR 2026-09-25). Real Oracle text
(tests/fixtures/wave100e_xdamage_cards.json); every scenario checks the replay and a save and a load.

* 120.3: the creature named is the source; its power as the instruction is carried out, or as it last existed (608.2h): Pain for All's
  enchanted creature, Alpha Brawl's two steps (no state-based actions in between), Waltz of Rage's bite and its delayed trigger (603.7c).
* 603.12 + 608.2h: Surtland Flinger's sacrificed creature, twice its power for a Giant; Imminent Doom's counters as it triggered.
* 114.4 / 613.1f: Arlinn's emblem grants an ability; Iron Fist gains one until end of turn.
"""

from __future__ import annotations

import pytest

from tests import wave100e_kit as kit
from tests.game_helpers import act
from tests.test_rules_wave7b_activation import ability_index
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand
from tests.wave100e_kit import answer, can_cast, chars, full_control, loyal, pick, zone_of


@pytest.fixture()
def cards(settings):
    yield from kit.repo(settings)


def ready(s, *cs):
    """Creatures that have been under their controller's control since the turn began (302.6)."""
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0


def exiled(s, pid):
    return list(s.state.zones.get(f"{pid}:exile", []))


# -- Pain for All ---------------------------------------------------------------------------------------------------------------------------------
def pain_for_all(cards):
    s = build(cards, ["Pain for All", "Grizzly Bears", "Murder"], ["Probe Wall"])
    bears = put(s, "Grizzly Bears")
    wall = put(s, "Probe Wall", "p2")
    aura = to_hand(s, "Pain for All")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[bears.id])
    return s, bears, wall, aura


def test_pain_for_all_the_enchanted_creature_bites_any_other_target(cards):
    s, bears, wall, aura = pain_for_all(cards)
    d = pick(s, "choose_one", wall.id)  # (the enters trigger's target)
    options = [o.id for o in d.options]
    assert bears.id not in options and "p2" in options and "p1" in options  # (any target but the enchanted creature)
    answer(s)
    assert s.state.cards[wall.id].damage == 2 and s.state.cards[aura.id].attached_to == bears.id
    check(s)


def test_pain_for_all_a_creature_gone_before_it_resolves_deals_its_last_known_power(cards):
    """The 2025-07-25 ruling: the enchanted creature left (a +1/+1 counter: 3 power) before the ability resolved: 3 damage all the same."""
    s, bears, wall, aura = pain_for_all(cards)
    full_control(s)
    pick(s, "choose_one", "p2")
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=1)
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Murder").id, targets=[bears.id])  # (in response)
    answer(s)
    assert zone_of(s, bears) == "p1:graveyard"
    assert zone_of(s, aura) == "p1:graveyard" and life(s, "p2") == 37
    check(s)


# -- Alpha Brawl ----------------------------------------------------------------------------------------------------------------------------------
def test_alpha_brawl_both_steps_with_no_state_based_actions_between(cards):
    """The 2011-01-22 rulings: the 5/3 deals 5 to each other creature Bob controls (Bears dies, the Wall survives with 5), then each of those
    (the dying Bears too) deals its power back: 2 + 0 — the 5/3 survives with 2 damage. Alice's Bears are untouched."""
    s = build(cards, ["Alpha Brawl", "Grizzly Bears"], ["Twisted Abomination", "Grizzly Bears", "Probe Wall"])
    mine = put(s, "Grizzly Bears")
    big, theirs, wall = put(s, "Twisted Abomination", "p2"), put(s, "Grizzly Bears", "p2"), put(s, "Probe Wall", "p2")
    spell = to_hand(s, "Alpha Brawl")
    mana(s, R=2, C=6)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[big.id])
    answer(s)
    assert zone_of(s, theirs) == "p2:graveyard" and s.state.cards[wall.id].damage == 5
    assert zone_of(s, big) == "p2:battlefield" and s.state.cards[big.id].damage == 2
    assert zone_of(s, mine) == "p1:battlefield" and s.state.cards[mine.id].damage == 0
    check(s)


# -- Waltz of Rage --------------------------------------------------------------------------------------------------------------------------------
def test_waltz_of_rage_bites_everything_and_each_of_your_dying_creatures_exiles_a_card(cards):
    """The 5/3 deals 5 to each other creature: Alice's two Bears die (two cards exiled, playable until the end of her next turn), Bob's Bears die
    (not hers: nothing)."""
    s = build(cards, ["Waltz of Rage", "Twisted Abomination", "Grizzly Bears", "Llanowar Elves", "Lightning Bolt", "Murder"], ["Grizzly Bears"])
    big = put(s, "Twisted Abomination")
    a, b = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    theirs = put(s, "Grizzly Bears", "p2")
    for name in ("Murder", "Lightning Bolt"):  # (Lightning Bolt on top, then Murder)
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"player": "p1", "zone": "library"}, position="top")
    spell = to_hand(s, "Waltz of Rage")
    mana(s, R=2, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[big.id])
    answer(s)
    assert {zone_of(s, a), zone_of(s, b), zone_of(s, theirs)} == {"p1:graveyard", "p2:graveyard"}
    assert {s.state.cards[c].name for c in exiled(s, "p1")} == {"Lightning Bolt", "Murder"}
    mana(s, R=1)
    assert can_cast(s, "p1", card_named(s, "Lightning Bolt"))
    check(s)


def test_waltz_of_rage_the_delayed_trigger_ends_with_the_turn(cards):
    s = build(cards, ["Waltz of Rage", "Twisted Abomination", "Grizzly Bears"])
    big = put(s, "Twisted Abomination")
    spell = to_hand(s, "Waltz of Rage")
    mana(s, R=2, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[big.id])
    answer(s)
    kit.to_phase(s, "main1", turn=1)
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "graveyard"})
    answer(s)
    assert not exiled(s, "p1")
    check(s)


# -- Surtland Flinger -----------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("fodder", "dealt"), [("Grizzly Bears", 2), ("Surtland Flinger", 8)])
def test_surtland_flinger_flings_the_sacrificed_creature_twice_as_hard_for_a_giant(cards, fodder, dealt):
    """The 2021-02-05 rulings: its power as it was sacrificed (a second Flinger is a 4-power Giant: 8)."""
    s = build(cards, ["Surtland Flinger", fodder] if fodder != "Surtland Flinger" else ["Surtland Flinger", "Surtland Flinger"])
    flingers = [c for c in s.state.cards.values() if c.name == "Surtland Flinger" and c.owner == "p1"]
    flinger = flingers[0]
    act(s, "p1", type="move", card_ids=[flinger.id], to={"player": "p1", "zone": "battlefield"})
    victim = flingers[1] if fodder == "Surtland Flinger" else card_named(s, fodder)
    act(s, "p1", type="move", card_ids=[victim.id], to={"player": "p1", "zone": "battlefield"})
    ready(s, flinger)
    act(s, "p1", type="pass_priority")  # -> declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": flinger.id, "target": "p2"}])
    answer(s, "yes", victim.id, "p2")
    assert zone_of(s, victim) == "p1:graveyard" and life(s, "p2") == 40 - dealt - 4  # (and the Flinger's own 4 combat damage)
    check(s)


# -- Imminent Doom --------------------------------------------------------------------------------------------------------------------------------
def test_imminent_doom_deals_the_counters_it_triggered_for(cards):
    """The 2017-07-14 ruling: a mana value 1 spell with one doom counter triggers it; a counter added in response doesn't change the 1 damage;
    then a counter is added (three), and a mana value 1 spell no longer triggers it."""
    s = build(cards, ["Imminent Doom", "Lightning Bolt", "Opt"])
    doom = to_hand(s, "Imminent Doom")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=doom.id)
    answer(s)
    assert s.state.cards[doom.id].counters.get("doom") == 1
    full_control(s)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])
    pick(s, "choose_one", "p2")  # (the doom trigger's target)
    act(s, "p1", type="counter", card_ids=[doom.id], kind="doom", delta=1)
    answer(s)
    assert life(s, "p2") == 40 - 1 - 3 and s.state.cards[doom.id].counters.get("doom") == 3
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Opt").id)
    answer(s)
    assert life(s, "p2") == 36 and s.state.cards[doom.id].counters.get("doom") == 3
    check(s)


# -- Arlinn, Embraced by the Moon: the emblem ------------------------------------------------------------------------------------------------------
def test_arlinn_emblem_gives_creatures_haste_and_a_power_sized_ping(cards):
    """114.4: the emblem's static ability grants each creature you control haste and "{T}: This creature deals damage equal to its power to any
    target" (613.1f) — a creature just put onto the battlefield can use it (haste)."""
    s = build(cards, ["Arlinn Kord // Arlinn, Embraced by the Moon", "Twisted Abomination"], ["Grizzly Bears"])
    arlinn = loyal(s, "Arlinn Kord // Arlinn, Embraced by the Moon", face=1)
    act(s, "p1", type="activate_ability", card_id=arlinn.id, ability=ability_index(s, arlinn, "emblem"))
    answer(s)
    big = put(s, "Twisted Abomination")
    theirs = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="activate_ability", card_id=big.id, ability=ability_index(s, big, "deals damage equal to its power"), targets=["p2"])
    answer(s)
    assert life(s, "p2") == 35 and s.state.cards[big.id].tapped
    assert "haste" in chars(s, big).keywords and "haste" not in chars(s, theirs).keywords
    check(s)


# -- Iron Fist, Living Weapon ---------------------------------------------------------------------------------------------------------------------
def test_iron_fist_gains_a_power_ping_when_a_spell_targets_your_creature(cards):
    """Giant Growth on Iron Fist: it gains "{T}: … damage equal to his power to any other target" until end of turn (5 with +3/+3); it can't
    target itself."""
    s = build(cards, ["Iron Fist, Living Weapon", "Giant Growth"])
    fist = put(s, "Iron Fist, Living Weapon")
    ready(s, fist)
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Giant Growth").id, targets=[fist.id])
    answer(s)
    assert pt(s, "Iron Fist, Living Weapon") == (5, 6)
    gained = next(a.index for a in chars(s, fist).abilities if a.kind == "activated" and "any other target" in a.text)
    act(s, "p1", type="activate_ability", card_id=fist.id, ability=gained, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 35
    check(s)


def test_iron_fist_has_no_ping_without_the_spell(cards):
    s = build(cards, ["Iron Fist, Living Weapon"])
    fist = put(s, "Iron Fist, Living Weapon")
    assert not any("any other target" in a.text for a in chars(s, fist).abilities if a.kind == "activated")
    check(s)
