"""Wave 110A: instants and sorceries whose last unread sentence is now read (CR 2026-09-25), real Oracle text (tests/fixtures/wave110a_cards.json).
Every scenario checks the replay and a save and a load.

* Berserk - "At the beginning of the next end step, destroy that creature if it attacked this turn." (508.1: declared as an attacker; 603.4 the
  condition is judged as the delayed trigger resolves).
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave110a_kit import *

BERSERK, MANDATE, BAIT, FLUX = "Berserk", "Mandate of Peace", "Take the Bait", "Thermal Flux"
EUREKA, HYPERGENESIS, MEDITATION = "Eureka", "Hypergenesis", "Cleansing Meditation"
AERITH, SUNDER, WMBD, ANOINT, SLIME = "Aerith Rescue Mission", "Sunder the Gateway", "What Must Be Done", "Anoint with Affliction", "Convert to Slime"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([BERSERK, MANDATE, BAIT, FLUX, AERITH, SUNDER, WMBD, ANOINT, SLIME, EUREKA, HYPERGENESIS, MEDITATION])


def attack(s, c, target="p2"):
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": target}])


@pytest.mark.parametrize("attacks", [True, False])
def test_berserk_destroys_the_creature_at_end_step_only_if_it_attacked(cards, attacks):
    s = build(cards, [BERSERK, "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    next_turn(s)
    stops(s)
    cast(s, BERSERK, [bears.id])
    answer(s)
    assert pt(s, "Grizzly Bears") == (4, 2) and "trample" in ch(s, bears).keywords  # (+X/+0, X its power: 2)
    if attacks:
        attack(s, bears)
    to_phase(s, "end")
    answer(s)
    assert zone_of(s, "Grizzly Bears") == ("p1:graveyard" if attacks else "p1:battlefield")
    check(s)


def test_berserk_cant_be_cast_after_combat_damage_begins(cards):
    s = build(cards, [BERSERK, "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    next_turn(s)
    stops(s)
    attack(s, bears)
    to_phase(s, "combat_damage")
    with pytest.raises(ActionError):
        cast(s, BERSERK, [bears.id])
    check(s)


def test_mandate_of_peace_ends_combat_and_stops_opponents_casting(cards):
    """724.2: no combat damage, combat left, on to the postcombat main; the opponents can't cast spells this turn."""
    s = build(cards, [MANDATE, "Grizzly Bears"], ["Counterspell"])
    bears = put(s, "Grizzly Bears")
    next_turn(s)
    stops(s)
    attack(s, bears)
    to_phase(s, "declare_blockers")
    cast(s, MANDATE)
    answer(s)
    assert s.state.turn.phase == "main2" and s.state.cards[bears.id].attacking is None
    assert life(s, "p2") == 40
    with pytest.raises(ActionError):
        cast(s, "Counterspell", [bears.id], pid="p2")
    assert zone_of(s, MANDATE) == "p1:exile"  # (724.2b: the resolving spell too)
    check(s)


def test_mandate_of_peace_cant_be_cast_outside_combat(cards):
    s = build(cards, [MANDATE])
    with pytest.raises(ActionError):
        cast(s, MANDATE)


def bob_attacks(s, c, target):
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": c.id, "target": target}])


@pytest.mark.parametrize("at", ["player", "planeswalker"])
def test_take_the_bait_prevents_combat_damage_to_you_and_your_planeswalkers_and_goads(cards, at):
    """Prevent (615), untap (701.26), goad (701.15), an added combat phase (500.8)."""
    s = build(cards, [BAIT, "Gideon Jura"], ["Grizzly Bears"])
    gideon = put(s, "Gideon Jura")
    act(s, "p1", type="counter", card_ids=[gideon.id], kind="loyalty", delta=6)
    bears = put(s, "Grizzly Bears", "p2")
    stops(s)
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1" if at == "player" else gideon.id}])
    act(s, "p2", type="pass_priority")
    cast(s, BAIT)
    answer(s)
    from app.rules.keyword_actions import goaded_by

    assert not s.state.cards[bears.id].tapped and s.state.rules.extra_phases and "p1" in goaded_by(ch(s, bears))
    to_phase(s, "end_combat")
    assert life(s, "p1") == 40 and s.state.cards[gideon.id].counters.get("loyalty", 0) == 6
    check(s)


@pytest.mark.parametrize("mode, start_snow", [(0, False), (1, True)])
def test_thermal_flux_makes_a_permanent_snow_or_not_until_end_of_turn_and_draws_next_upkeep(cards, mode, start_snow):
    """205.4 (supertype), 613.1d (layer 4), 611.2a (until end of turn), 603.7 (the delayed draw at the next turn's upkeep)."""
    s = build(cards, [FLUX, "Snow-Covered Forest"])
    land = put(s, "Snow-Covered Forest") if start_snow else put(s, "Forest")
    stops(s)
    hand = len(s.state.zones["p1:hand"])
    cast(s, FLUX, [land.id], modes=[mode])
    answer(s)
    assert ("Snow" in ch(s, land).supertypes) == (not start_snow)
    to_phase(s, "upkeep", turn=2)
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1  # (the delayed draw at the next turn's upkeep; the spell itself left the hand)
    assert ("Snow" in ch(s, land).supertypes) == start_snow  # (back at the cleanup step)
    check(s)


def test_aerith_rescue_mission_elevator_three_heroes(cards):
    s = build(cards, [AERITH])
    cast(s, AERITH, modes=[0])
    answer(s)
    heroes = [c for c in s.state.cards.values() if c.name == "Hero" and c.zone == "p1:battlefield"]
    assert len(heroes) == 3 and pt(s, "Hero") == (1, 1)
    check(s)


def test_aerith_rescue_mission_stairs_taps_up_to_three_and_stuns_one(cards):
    """122.1g: a stun counter on one of the tapped creatures (chosen as it resolves, 608.2d)."""
    s = build(cards, [AERITH], ["Grizzly Bears", "Hill Giant"])
    bears, giant = put(s, "Grizzly Bears", "p2"), put(s, "Hill Giant", "p2")
    cast(s, AERITH, [bears.id, giant.id], modes=[1], target_counts=[2])
    answer(s, giant.id)
    assert s.state.cards[bears.id].tapped and s.state.cards[giant.id].tapped
    assert s.state.cards[giant.id].counters.get("stun", 0) == 1 and s.state.cards[bears.id].counters.get("stun", 0) == 0
    check(s)


@pytest.mark.parametrize("mode", [0, 1])
def test_sunder_the_gateway_modes(cards, mode):
    """701.53a incubate; mode 2 then transforms an Incubator token you control (701.28)."""
    s = build(cards, [SUNDER], ["Sol Ring"])
    ring = put(s, "Sol Ring", "p2")
    cast(s, SUNDER, [ring.id] if mode == 0 else [], modes=[mode])
    answer(s)
    assert (zone_of(s, "Sol Ring", "p2") == "p2:graveyard") == (mode == 0)
    made = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert len(made) == 1 and made[0].counters.get("+1/+1", 0) == 2
    assert ("Creature" in ch(s, made[0]).types) == (mode == 1)  # (transformed: a 0/0 Phyrexian artifact creature with the counters)
    check(s)


def test_what_must_be_done_destroys_all_artifacts_and_creatures(cards):
    s = build(cards, [WMBD, "Sol Ring", "Grizzly Bears"], ["Hill Giant"])
    put(s, "Sol Ring"), put(s, "Grizzly Bears"), put(s, "Hill Giant", "p2")
    cast(s, WMBD, modes=[0])
    answer(s)
    assert all(zone_of(s, n, p) == f"{p}:graveyard" for n, p in (("Sol Ring", "p1"), ("Grizzly Bears", "p1"), ("Hill Giant", "p2")))
    check(s)


@pytest.mark.parametrize("name, counters", [("Perilous Myr", 2), ("Sol Ring", 0)])
def test_what_must_be_done_returns_a_historic_permanent_a_creature_with_two_more_counters(cards, name, counters):
    """122.6: the creature enters with the counters; a noncreature or a nonhistoric card isn't a legal target."""
    s = build(cards, [WMBD, "Sol Ring", "Perilous Myr", "Grizzly Bears"])
    card = put(s, name)
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[card.id, bears.id], to={"player": "p1", "zone": "graveyard"})
    with pytest.raises(ActionError):
        cast(s, WMBD, [bears.id], modes=[1])  # (not historic)
    cast(s, WMBD, [card.id], modes=[1])
    answer(s)
    assert zone_of(s, name) == "p1:battlefield" and s.state.cards[card.id].counters.get("+1/+1", 0) == counters
    check(s)


@pytest.mark.parametrize("name, poison, exiled", [("Hill Giant", 2, False), ("Hill Giant", 3, True), ("Grizzly Bears", 0, True)])
def test_anoint_with_affliction_exiles_mana_value_3_or_less_or_any_if_corrupted(cards, name, poison, exiled):
    """Corrupted (its controller has three or more poison counters) is judged as the spell resolves: instead exile any creature (608.2c)."""
    s = build(cards, [ANOINT], [name])
    target = put(s, name, "p2")
    act(s, "p2", type="set_resource", player="p2", key="poison", value=poison)
    cast(s, ANOINT, [target.id])
    answer(s)
    assert (zone_of(s, name, "p2") == "p2:exile") == exiled
    check(s)


@pytest.mark.parametrize("delirium", [False, True])
def test_convert_to_slime_ooze_as_big_as_the_total_mana_value_destroyed_with_delirium(cards, delirium):
    """Destroys up to one of each; delirium (four card types in your graveyard, checked after the destruction) makes an X/X Ooze, X the total mana
    value of what was destroyed (Sol Ring 1 + Hill Giant 4)."""
    s = build(cards, [SLIME, "Sol Ring", "Grizzly Bears", "Lightning Bolt"], ["Sol Ring", "Hill Giant"])
    ring, giant = put(s, "Sol Ring", "p2"), put(s, "Hill Giant", "p2")
    mine = [card_named(s, n).id for n in (["Sol Ring", "Grizzly Bears"] + (["Lightning Bolt"] if delirium else []))]
    act(s, "p1", type="move", card_ids=mine, to={"player": "p1", "zone": "graveyard"})
    to_graveyard(s, 1)
    cast(s, SLIME, [ring.id, giant.id], target_counts=[1, 1, 0])
    answer(s)
    assert zone_of(s, "Sol Ring", "p2") == zone_of(s, "Hill Giant", "p2") == "p2:graveyard"
    oozes = [c for c in s.state.cards.values() if c.name == "Ooze" and c.zone == "p1:battlefield"]
    assert len(oozes) == (1 if delirium else 0)
    if delirium:
        assert pt(s, "Ooze") == (5, 5)
    check(s)


@pytest.mark.parametrize("name", [EUREKA, HYPERGENESIS])
def test_eureka_and_hypergenesis_repeat_the_round_until_a_whole_round_puts_nothing(cards, name):
    """Starting with you, each player in turn may put one card; the process is repeated until no one does (101.4, 608.2c). Eureka takes any permanent
    card, Hypergenesis (cast by its last suspend counter, 702.62a) an artifact, creature, enchantment or land card — never a planeswalker."""
    s = build(cards, [name, "Grizzly Bears", "Sol Ring", "Gideon Jura"], ["Hill Giant"])
    spell = to_hand(s, name)
    for n in ("Gideon Jura", "Grizzly Bears", "Sol Ring"):
        to_hand(s, n)
    to_hand(s, "Hill Giant", "p2")
    if name == EUREKA:
        cast(s, name)
    else:
        ab = next(a.index for a in ch(s, spell).abilities if "suspend" in a.keywords)
        fund(s, "{1}{G}{G}")
        act(s, "p1", type="activate_ability", card_id=spell.id, ability=ab, sources=[])
        act(s, "p1", type="counter", card_ids=[spell.id], kind="time", delta=-2)
        to_phase(s, "upkeep", turn=3)
    for _ in range(10):  # (to the first question: whose hand cards may be put)
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards":
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])  # ("Cast it")
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert ("Gideon Jura" in [o.label for o in d.options]) == (name == EUREKA)
    answer(s, "Grizzly Bears", "Hill Giant", "Sol Ring", [], [], [])
    assert zone_of(s, "Grizzly Bears") == zone_of(s, "Sol Ring") == "p1:battlefield" and zone_of(s, "Hill Giant", "p2") == "p2:battlefield"
    assert zone_of(s, "Gideon Jura") == "p1:hand"
    check(s)


@pytest.mark.parametrize("threshold", [False, True])
def test_cleansing_meditation_threshold_returns_your_destroyed_enchantments(cards, threshold):
    """Threshold is judged as it resolves; instead the destroyed enchantment cards in YOUR graveyard (your own, whoever controlled them) return."""
    s = build(cards, [MEDITATION, "Sylvan Library"], ["Sylvan Library", "Grizzly Bears"])
    mine, theirs = put(s, "Sylvan Library"), put(s, "Sylvan Library", "p2")
    to_graveyard(s, 7 if threshold else 5)
    cast(s, MEDITATION)
    answer(s)
    assert zone_of(s, "Sylvan Library") == ("p1:battlefield" if threshold else "p1:graveyard")
    assert zone_of(s, "Sylvan Library", "p2") == "p2:graveyard"
    check(s)
