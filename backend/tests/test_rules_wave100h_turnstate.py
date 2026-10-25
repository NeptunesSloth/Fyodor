"""Wave 100H: "this turn" history conditions and ability-word abilities, real Oracle text (tests/fixtures/wave100h_cards.json). Every scenario
checks the replay and a save and a load (tests/wave9c_kit.check).

* 608.2h: Akoum Hellkite's "that land" is the land that entered, not the target. 508.1: "you attacked with two or more creatures / a Hero /
  three or more Merfolk this turn" (Wedding Announcement, Avengers Assemble!, Deepway Navigator) count declared attackers.
* 702.49c: Moon-Circuit Hacker entered this turn by ninjutsu: no discard. 608.2c: Motivated Pony's "those creatures", Composer of Spring's
  "instead", Kraul Harpooner's optional fight. 701.21a: Sawblade Skinripper's "that much".
* 603.2, 400.7: "This ability triggers only once." (Acrobatic Cheerleader). 614.10: Gibbering Descent skips the upkeep only with an empty hand.
* 614.1: The Rollercrusher Ride doubles noncombat damage only with delirium. 603.4: Fear of Burning Alive's delirium.
* 701.38: Magister of Worth's vote. 608.2b: Squirming Emergence counts the permanent cards in your graveyard again as it resolves.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave100f_attached import to_phase
from tests.test_rules_wave100f_control import answer, ch, zone
from tests.wave9c_kit import build, check, life, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave100h_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w100h", number=f"H{i:03d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
HELPERS = {"Amateur Hero", "Instant Ramen", "Coral Merfolk", "Merfolk of the Pearl Trident", "Wind Drake", "Soul Warden", "Lonely Sandbar", "Secluded Steppe", "Prowcatcher Specialist"}


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", sorted(c["name"] for c in DATA if c["name"] not in HELPERS))
def test_the_cards_are_full(name):
    data = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or []}).level == "FULL"


def cost(name):
    import re

    out: dict[str, int] = {}
    for sym in re.findall(r"{([^}]+)}", next(c for c in [*DATA, *fixture_cards()] if c["name"] == name)["mana_cost"].split(" // ")[0]):
        key = "C" if sym.isdigit() else sym[0]  # (a hybrid symbol: its first color)
        out[key] = out.get(key, 0) + (int(sym) if sym.isdigit() else 1)
    return {k: v for k, v in out.items() if v}


def cast(s, name, targets=(), pid="p1", pick=(), **kw):
    c = to_hand(s, name, pid)
    if cost(name):
        mana(s, pid, **cost(name))
    act(s, pid, type="cast_spell", card_id=c.id, **({"targets": list(targets)} if targets else {}), **kw)
    answer(s, pick)
    return s.state.cards[c.id]


def bolt(s, target, pid="p1"):
    c = to_hand(s, "Lightning Bolt", pid)
    mana(s, pid, R=1)
    act(s, pid, type="cast_spell", card_id=c.id, targets=[target])
    answer(s)


def attack(s, attackers, turn=3, pick=()):
    """Attack Bob with ``attackers`` (no blocks) in turn ``turn``, through to the second main phase."""
    to_phase(s, "declare_attackers", turn=turn)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])
    for _ in range(80):
        d = s.state.rules.decision
        if s.state.turn.phase == "main2" and d is None and not s.state.zones.get("stack"):
            return
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[i for i in pick if i in ids][:max(1, d.min_choices)] or ids[: d.min_choices])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


def gy(s, pid="p1"):
    return [s.state.cards[c].name for c in s.state.zones[f"{pid}:graveyard"]]


def bury(s, *names, pid="p1"):
    for n in names:
        c = next(x for x in s.state.cards.values() if x.name == n and x.owner == pid and not x.zone.endswith(("graveyard", "battlefield")))
        act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})


# -- Akoum Hellkite ------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("land,dealt", [("Mountain", 2), ("Forest", 1)])
def test_akoum_hellkite_deals_two_only_when_the_land_is_a_mountain(cards, land, dealt):
    s = build(cards, ["Akoum Hellkite", "Mountain"])
    put(s, "Akoum Hellkite")
    c = to_hand(s, land)
    act(s, "p1", type="play_land", card_id=c.id)
    answer(s, ["p2"])
    assert life(s, "p2") == 40 - dealt
    check(s)


# -- Moon-Circuit Hacker ----------------------------------------------------------------------------------------------------------------------------
def hand(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


def combat_rest(s, pick=()):
    for _ in range(80):
        d = s.state.rules.decision
        if s.state.turn.phase == "main2" and d is None and not s.state.zones.get("stack"):
            return
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[i for i in pick if i in ids][:max(1, d.min_choices)] or ids[: d.min_choices])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


def test_moon_circuit_hacker_discards_unless_it_entered_this_turn(cards):
    s = build(cards, ["Moon-Circuit Hacker", "Lightning Bolt"])
    hacker = put(s, "Moon-Circuit Hacker")
    to_phase(s, "main1", turn=3)
    before = hand(s)
    attack(s, [hacker], pick=["yes"])
    assert hand(s) == before and len(gy(s)) == 1  # drew a card, then discarded one
    check(s)


def test_moon_circuit_hacker_by_ninjutsu_keeps_the_card(cards):
    from app.rules import ninjutsu
    from app.rules.plan import Plan

    s = build(cards, ["Moon-Circuit Hacker", "Grizzly Bears"])
    bear = put(s, "Grizzly Bears")
    hacker = to_hand(s, "Moon-Circuit Hacker")
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "declare_blockers", "main2"])
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif s.state.turn.phase == "declare_blockers" and d is None and s.state.rules.priority == "p1" and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    c = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[hacker.id])
    mana(s, U=1)
    act(s, "p1", type="activate_ability", card_id=hacker.id, ability=next(a.index for a in c.abilities if ninjutsu.cost_of(c, a.index) is not None))
    answer(s, [bear.id])
    before = hand(s)
    combat_rest(s, pick=["yes"])
    assert zone(s, hacker) == "p1:battlefield" and hand(s) == before + 1 and gy(s) == []  # drew, no discard (it entered this turn)
    check(s)


# -- Motivated Pony ----------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("food", [True, False])
def test_motivated_pony_untaps_and_pumps_more_after_a_food_entered(cards, food):
    s = build(cards, ["Motivated Pony", "Grizzly Bears", "Instant Ramen"])
    pony, bear = put(s, "Motivated Pony"), put(s, "Grizzly Bears")
    to_phase(s, "main1", turn=3)
    if food:
        put(s, "Instant Ramen")
        answer(s)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": pony.id, "target": "p2"}, {"card_id": bear.id, "target": "p2"}])
    answer(s)
    assert ch(s, bear).pt == ((5, 5) if food else (3, 3)) and s.state.cards[bear.id].tapped != food
    check(s)


# -- Wedding Announcement ------------------------------------------------------------------------------------------------------------------------
def names(s, pid="p1", where="battlefield"):
    return sorted(s.state.cards[c].name for c in s.state.zones[f"{pid}:{where}"])


def test_wedding_announcement_draws_after_two_attackers_and_transforms_at_three(cards):
    s = build(cards, ["Wedding Announcement // Wedding Festivity", "Grizzly Bears", "Coral Merfolk"])
    w = put(s, "Wedding Announcement // Wedding Festivity")
    bear, merfolk = put(s, "Grizzly Bears"), put(s, "Coral Merfolk")
    to_phase(s, "cleanup", turn=1)
    assert names(s).count("Human") == 1 and s.state.cards[w.id].counters.get("invitation") == 1  # no attack: a Human
    attack(s, [bear, merfolk])
    before = hand(s)
    to_phase(s, "cleanup", turn=3)
    assert names(s).count("Human") == 1 and hand(s) == before + 1  # two attackers this turn: a card instead
    to_phase(s, "cleanup", turn=5)
    assert s.state.cards[w.id].counters.get("invitation") == 3 and ch(s, w).name == "Wedding Festivity" and ch(s, bear).pt == (3, 3)
    check(s)


# -- Composer of Spring --------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("six", [False, True])
def test_composer_of_spring_puts_a_creature_too_with_six_enchantments(cards, six):
    from tests.test_rules_conditionals import token_of

    s = build(cards, ["Composer of Spring", "Grizzly Bears", "Test Aegis"])
    put(s, "Composer of Spring")
    bear, forest = to_hand(s, "Grizzly Bears"), to_hand(s, "Forest")
    for i in range(5 if six else 0):
        token_of(s, "p1", f"Glyph {i}", "Token Enchantment")
        answer(s, ["no"])
    cast(s, "Test Aegis", pick=[bear.id, forest.id])
    assert zone(s, bear) == ("p1:battlefield" if six else "p1:hand") and s.state.cards[bear.id].tapped == six
    assert zone(s, forest) == ("p1:hand" if six else "p1:battlefield")
    check(s)


# -- Kraul Harpooner -------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("fight", [True, False])
def test_kraul_harpooner_gets_x_then_may_fight_the_flier(cards, fight):
    s = build(cards, ["Kraul Harpooner", "Grizzly Bears", "Coral Merfolk"], ["Wind Drake"])
    drake = put(s, "Wind Drake", "p2")
    bury(s, "Grizzly Bears", "Coral Merfolk")
    kraul = cast(s, "Kraul Harpooner", pick=[drake.id, "yes" if fight else "no"])
    if fight:  # (a 5/2 and a 2/2 flier fight: both die)
        assert zone(s, drake) == "p2:graveyard" and zone(s, kraul) == "p1:graveyard"
    else:
        assert zone(s, drake) == "p2:battlefield" and ch(s, kraul).pt == (5, 2)
    check(s)


# -- Oriss, Samite Guardian ------------------------------------------------------------------------------------------------------------------------
def test_oriss_grandeur_stops_spells_and_attacks_of_the_target_player(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Oriss, Samite Guardian", "Oriss, Samite Guardian"], ["Grizzly Bears", "Lightning Bolt"])
    first, second = [c for c in s.state.cards.values() if c.name == "Oriss, Samite Guardian"]
    act(s, "p1", type="move", card_ids=[first.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[second.id], to={"zone": "hand"})
    bear = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="set_prefs", stops_their_turn=["main1"])
    to_phase(s, "main1", turn=2)
    act(s, "p2", type="pass_priority")
    act(s, "p1", type="activate_ability", card_id=first.id, ability=1, targets=["p2"])
    answer(s, [second.id])
    assert zone(s, second) == "p1:graveyard"
    bolt_card = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=bolt_card.id, targets=["p1"])
    to_phase(s, "declare_attackers", turn=2)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p1"}])
    check(s)


# -- Stalked Researcher ----------------------------------------------------------------------------------------------------------------------------
def test_stalked_researcher_attacks_only_after_an_enchantment_entered(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Stalked Researcher", "Test Aegis"])
    researcher = put(s, "Stalked Researcher")
    to_phase(s, "declare_attackers", turn=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": researcher.id, "target": "p2"}])
    to_phase(s, "main1", turn=5)
    cast(s, "Test Aegis")
    attack(s, [researcher], turn=5)
    assert life(s, "p2") == 37
    check(s)


# -- Jagged Poppet ----------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("hellbent", [True, False])
def test_jagged_poppet_hellbent_makes_the_player_discard_the_damage(cards, hellbent):
    s = build(cards, ["Jagged Poppet"])
    poppet = put(s, "Jagged Poppet")
    to_phase(s, "main1", turn=3)
    for c in list(s.state.zones["p1:hand"])[: None if hellbent else -1]:
        act(s, "p1", type="move", card_ids=[c], to={"zone": "library"})
    for c in [c for c in s.state.zones["p2:library"] if s.state.cards[c].name == "Island"][:4]:
        act(s, "p2", type="move", card_ids=[c], to={"zone": "hand"})
    bob = hand(s, "p2")
    attack(s, [poppet])
    assert hand(s, "p2") == (bob - 3 if hellbent else bob)
    check(s)


# -- Vengevine ----------------------------------------------------------------------------------------------------------------------------------------
def test_vengevine_returns_on_the_second_creature_spell_only(cards):
    s = build(cards, ["Vengevine", "Grizzly Bears", "Llanowar Elves", "Coral Merfolk"])
    vine = next(c for c in s.state.cards.values() if c.name == "Vengevine")
    act(s, "p1", type="move", card_ids=[vine.id], to={"zone": "graveyard"})
    cast(s, "Llanowar Elves")
    assert zone(s, vine) == "p1:graveyard"
    cast(s, "Grizzly Bears", pick=["yes"])
    assert zone(s, vine) == "p1:battlefield"
    act(s, "p1", type="move", card_ids=[vine.id], to={"zone": "graveyard"})
    cast(s, "Coral Merfolk", pick=["yes"])
    assert zone(s, vine) == "p1:graveyard"  # (the third creature spell: no trigger)
    check(s)


# -- Sawblade Skinripper ----------------------------------------------------------------------------------------------------------------------------
def test_sawblade_skinripper_deals_damage_for_each_permanent_sacrificed(cards):
    s = build(cards, ["Sawblade Skinripper", "Grizzly Bears", "Test Aegis"])
    ripper = put(s, "Sawblade Skinripper")
    bear, aegis = put(s, "Grizzly Bears"), put(s, "Test Aegis")
    answer(s)
    for victim in (bear, aegis):
        mana(s, C=2)
        act(s, "p1", type="activate_ability", card_id=ripper.id, ability=1)
        answer(s, [victim.id])
    to_phase(s, "end", turn=1)
    answer(s, ["p2"])
    assert life(s, "p2") == 38 and s.state.cards[ripper.id].counters.get("+1/+1") == 2
    to_phase(s, "end", turn=3)
    answer(s, ["p2"])
    assert life(s, "p2") == 38  # (nothing sacrificed that turn: no trigger)
    check(s)


# -- delirium: The Rollercrusher Ride, Fear of Burning Alive ---------------------------------------------------------------------------------------
DELIRIUM = ("Forest", "Grizzly Bears", "Opt", "Sol Ring")  # (land, creature, instant, artifact: 700.4-style card types, 300.1)


@pytest.mark.parametrize("delirium", [True, False])
def test_the_rollercrusher_ride_doubles_noncombat_damage_with_delirium(cards, delirium):
    s = build(cards, ["The Rollercrusher Ride", "Grizzly Bears", "Opt", "Sol Ring", "Lightning Bolt"])
    put(s, "The Rollercrusher Ride")
    if delirium:
        bury(s, *DELIRIUM)
    bolt(s, "p2")
    assert life(s, "p2") == (34 if delirium else 37)
    check(s)


@pytest.mark.parametrize("delirium", [True, False])
def test_fear_of_burning_alive_hits_a_creature_of_the_damaged_opponent_with_delirium(cards, delirium):
    s = build(cards, ["Fear of Burning Alive", "Grizzly Bears", "Opt", "Sol Ring", "Lightning Bolt"], ["Coral Merfolk"])
    merfolk = put(s, "Coral Merfolk", "p2")
    if delirium:
        bury(s, *DELIRIUM)
    cast(s, "Fear of Burning Alive")  # (its enters trigger: 4 damage to Bob, noncombat — a trigger with delirium)
    assert life(s, "p2") == 36 and zone(s, merfolk) == ("p2:graveyard" if delirium else "p2:battlefield")
    check(s)


# -- Magister of Worth ---------------------------------------------------------------------------------------------------------------------------------
def ballot(s, pid, label):
    d = s.state.rules.decision
    assert d is not None and d.player == pid
    act(s, pid, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == label)])


@pytest.mark.parametrize("bob,grace", [("grace", True), ("condemnation", False)])
def test_magister_of_worth_returns_every_creature_card_or_destroys_the_others(cards, bob, grace):
    s = build(cards, ["Magister of Worth", "Grizzly Bears", "Coral Merfolk"], ["Wind Drake", "Merfolk of the Pearl Trident"])
    bury(s, "Grizzly Bears")
    bury(s, "Wind Drake", pid="p2")
    merfolk, pearl = put(s, "Coral Merfolk"), put(s, "Merfolk of the Pearl Trident", "p2")
    magister = to_hand(s, "Magister of Worth")
    mana(s, W=2, B=2, C=2)
    act(s, "p1", type="cast_spell", card_id=magister.id)
    for _ in range(4):
        if s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
    ballot(s, "p1", "grace")
    ballot(s, "p2", bob)  # (a tie goes to condemnation)
    answer(s)
    if grace:
        assert names(s) == ["Coral Merfolk", "Grizzly Bears", "Magister of Worth"] and names(s, "p2") == ["Merfolk of the Pearl Trident", "Wind Drake"]
    else:
        assert names(s) == ["Magister of Worth"] and zone(s, merfolk) == "p1:graveyard" and zone(s, pearl) == "p2:graveyard"
    check(s)


# -- Gibbering Descent -------------------------------------------------------------------------------------------------------------------------------
def test_gibbering_descent_skips_the_upkeep_of_an_empty_hand(cards):
    s = build(cards, ["Gibbering Descent"])
    put(s, "Gibbering Descent")
    for c in list(s.state.zones["p1:hand"]):
        act(s, "p1", type="move", card_ids=[c], to={"zone": "library"})
    to_phase(s, "draw", turn=3)
    assert life(s, "p1") == 40  # (Alice skipped her upkeep: its "each player's upkeep" trigger never happened, 614.10a)
    assert life(s, "p2") == 39  # (Bob had cards: he lost 1 and discarded in his upkeep)
    to_phase(s, "draw", turn=5)
    assert life(s, "p1") == 39  # (she had the card she drew on turn 3)
    check(s)


# -- Acrobatic Cheerleader -----------------------------------------------------------------------------------------------------------------------------
def test_acrobatic_cheerleader_triggers_only_once(cards):
    s = build(cards, ["Acrobatic Cheerleader"])
    cheer = put(s, "Acrobatic Cheerleader")
    to_phase(s, "main2", turn=1)
    assert not s.state.cards[cheer.id].counters  # (untapped: no trigger)
    attack(s, [cheer])
    answer(s)
    assert s.state.cards[cheer.id].counters.get("flying") == 1
    attack(s, [cheer], turn=5)
    answer(s)
    assert s.state.cards[cheer.id].counters.get("flying") == 1  # (it triggered once already)
    check(s)


# -- Squirming Emergence --------------------------------------------------------------------------------------------------------------------------------
def test_squirming_emergence_counts_the_permanent_cards_in_your_graveyard(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Squirming Emergence", "Mulldrifter", "Grizzly Bears", "Opt", "Sol Ring"])
    bury(s, "Mulldrifter", "Grizzly Bears", "Opt", "Sol Ring")  # (three permanent cards: Opt isn't one)
    spell = to_hand(s, "Squirming Emergence")
    mulldrifter = next(c for c in s.state.cards.values() if c.name == "Mulldrifter")
    bear = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears")
    mana(s, B=1, G=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[mulldrifter.id])  # (mana value 5 > 3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id])
    answer(s)
    assert zone(s, bear) == "p1:battlefield"
    check(s)


# -- Undercity Upheaval -----------------------------------------------------------------------------------------------------------------------------------
def test_undercity_upheaval_divides_the_creature_cards_counted_as_it_is_cast(cards):
    s = build(cards, ["Undercity Upheaval", "Mulldrifter", "Wind Drake", "Grizzly Bears", "Coral Merfolk"])
    bury(s, "Mulldrifter", "Wind Drake")
    bear, merfolk = put(s, "Grizzly Bears"), put(s, "Coral Merfolk")
    cast(s, "Undercity Upheaval", targets=[bear.id, merfolk.id], target_counts=[2], division=[1, 1])
    assert s.state.cards[bear.id].counters.get("+1/+1") == 1 and s.state.cards[merfolk.id].counters.get("+1/+1") == 1
    assert "vigilance" in ch(s, bear).keywords
    check(s)


# -- Avengers Assemble! / Deepway Navigator ------------------------------------------------------------------------------------------------------------
def test_avengers_assemble_draws_after_a_hero_entered_or_attacked(cards):
    s = build(cards, ["Avengers Assemble!", "Amateur Hero"])
    put(s, "Avengers Assemble!")
    before = hand(s)
    to_phase(s, "cleanup", turn=1)
    assert hand(s) == before  # (no Hero yet)
    to_phase(s, "main1", turn=3)
    hero = put(s, "Amateur Hero")
    before = hand(s)
    to_phase(s, "cleanup", turn=3)
    assert hand(s) == before + 1  # (a Hero entered under your control this turn)
    to_phase(s, "main1", turn=5)
    before = hand(s)
    attack(s, [hero], turn=5)
    to_phase(s, "cleanup", turn=5)
    assert hand(s) == before + 1  # (you attacked with a Hero this turn)
    act(s, "p1", type="set_prefs", stops_their_turn=["end"])
    to_phase(s, "end", turn=6)
    answer(s)
    assert s.state.turn.number == 6 and hand(s) == before + 1  # (Bob's end step: Alice did neither that turn)
    check(s)


@pytest.mark.parametrize("attacked", [True, False])
def test_thaumaton_torpedo_costs_three_less_after_a_spacecraft_attacked(cards, attacked):
    from app.game.errors import ActionError
    from tests.test_rules_conditionals import token_of

    s = build(cards, ["Thaumaton Torpedo"], ["Coral Merfolk"])
    torpedo, merfolk = put(s, "Thaumaton Torpedo"), put(s, "Coral Merfolk", "p2")
    ship = token_of(s, "p1", "Probe Ship", "Token Artifact Creature — Spacecraft", "1/1")
    if attacked:
        attack(s, [ship])
    else:
        to_phase(s, "main1", turn=3)
    mana(s, C=3)
    if not attacked:
        with pytest.raises(ActionError):
            act(s, "p1", type="activate_ability", card_id=torpedo.id, ability=0, targets=[merfolk.id])
        return
    act(s, "p1", type="activate_ability", card_id=torpedo.id, ability=0, targets=[merfolk.id])
    answer(s)
    assert zone(s, merfolk) == "p2:graveyard"
    check(s)


@pytest.mark.parametrize("n", [3, 2])
def test_deepway_navigator_pumps_merfolk_after_three_merfolk_attacked(cards, n):
    s = build(cards, ["Deepway Navigator", "Coral Merfolk", "Merfolk of the Pearl Trident", "Merfolk Looter"])
    nav = put(s, "Deepway Navigator")
    folk = [put(s, x) for x in ("Coral Merfolk", "Merfolk of the Pearl Trident", "Merfolk Looter")]
    attack(s, folk[:n])
    assert ch(s, nav).pt == ((3, 2) if n == 3 else (2, 2)) and ch(s, folk[0]).pt == ((3, 1) if n == 3 else (2, 1))
    check(s)


# -- Bloodcurdler ----------------------------------------------------------------------------------------------------------------------------------------
def test_bloodcurdler_threshold_exiles_two_graveyard_cards_at_the_end_step(cards):
    s = build(cards, ["Bloodcurdler"])
    curdler = put(s, "Bloodcurdler")
    base = ch(s, curdler).pt
    for c in [c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"][:7]:
        act(s, "p1", type="move", card_ids=[c], to={"zone": "graveyard"})
    assert ch(s, curdler).pt == (base[0] + 1, base[1] + 1)
    to_phase(s, "cleanup", turn=1)
    assert len(gy(s)) == 5 and len(s.state.zones["p1:exile"]) == 2 and ch(s, curdler).pt == base  # (two chosen and exiled: below threshold now)
    check(s)


# -- Linessa, Zephyr Mage -------------------------------------------------------------------------------------------------------------------------------
def test_linessa_grandeur_returns_a_creature_artifact_enchantment_and_land(cards):
    s = build(cards, ["Linessa, Zephyr Mage", "Linessa, Zephyr Mage"], ["Coral Merfolk", "Sol Ring", "Test Aegis"])
    first, second = [c for c in s.state.cards.values() if c.name == "Linessa, Zephyr Mage"]
    act(s, "p1", type="move", card_ids=[first.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[second.id], to={"zone": "hand"})
    gone = [put(s, n, "p2") for n in ("Coral Merfolk", "Sol Ring", "Test Aegis", "Island")]
    act(s, "p1", type="activate_ability", card_id=first.id, ability=1, targets=["p2"])
    answer(s, [second.id])
    assert all(zone(s, c) == "p2:hand" for c in gone) and zone(s, second) == "p1:graveyard"
    check(s)


# -- Sizzling Soloist / Rose Room Treasurer (alliance) ----------------------------------------------------------------------------------------------
def test_sizzling_soloist_second_resolution_makes_the_creature_attack(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Sizzling Soloist", "Grizzly Bears", "Llanowar Elves"], ["Coral Merfolk"])
    put(s, "Sizzling Soloist")
    merfolk = put(s, "Coral Merfolk", "p2")
    cast(s, "Llanowar Elves", pick=[merfolk.id])
    cast(s, "Grizzly Bears", pick=[merfolk.id])
    to_phase(s, "declare_attackers", turn=2)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[])  # (it attacks during its controller's next combat if able)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": merfolk.id, "target": "p1"}])
    check(s)


def test_rose_room_treasurer_makes_two_treasures_then_offers_x_damage(cards):
    s = build(cards, ["Rose Room Treasurer", "Grizzly Bears", "Llanowar Elves", "Coral Merfolk"])
    put(s, "Rose Room Treasurer")
    cast(s, "Llanowar Elves")
    cast(s, "Grizzly Bears")
    assert names(s).count("Treasure") == 2
    c = to_hand(s, "Coral Merfolk")
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((i for i in ("x:2", "p2") if i in ids), ids[0])])
    assert names(s).count("Treasure") == 2 and life(s, "p2") == 38  # (the third resolution: no Treasure, X = 2 paid)
    check(s)


# -- Ashling the Pilgrim ---------------------------------------------------------------------------------------------------------------------------------
def test_ashling_blows_up_on_the_third_resolution(cards):
    s = build(cards, ["Ashling the Pilgrim"], ["Coral Merfolk"])
    ash, merfolk = put(s, "Ashling the Pilgrim"), put(s, "Coral Merfolk", "p2")
    for i in range(3):
        mana(s, R=1, C=1)
        act(s, "p1", type="activate_ability", card_id=ash.id, ability=0)
        answer(s)
        if i < 2:
            assert s.state.cards[ash.id].counters.get("+1/+1") == i + 1
    assert life(s, "p1") == 37 and life(s, "p2") == 37 and zone(s, merfolk) == "p2:graveyard" and zone(s, ash) == "p1:graveyard"
    check(s)


# -- The Last Ronin --------------------------------------------------------------------------------------------------------------------------------------
def test_the_last_ronin_chapter_three_pumps_a_lone_attacker(cards):
    s = build(cards, ["The Last Ronin", "Grizzly Bears", "Coral Merfolk"])
    cast(s, "The Last Ronin")
    to_phase(s, "main1", turn=3)
    answer(s)
    bear, merfolk = put(s, "Grizzly Bears"), put(s, "Coral Merfolk")
    to_phase(s, "main1", turn=5)
    answer(s)
    attack(s, [bear], turn=5)
    assert s.state.cards[bear.id].counters.get("+1/+1") == 3 and {"trample", "lifelink", "indestructible"} <= set(ch(s, bear).keywords)
    assert life(s, "p2") == 35 and life(s, "p1") == 45 and not s.state.cards[merfolk.id].counters
    check(s)


# -- Council Guardian --------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bob", ["red", "green"])
def test_council_guardian_gains_protection_from_each_leading_color_for_good(cards, bob):
    from app.game.errors import ActionError

    s = build(cards, ["Council Guardian", "Lightning Bolt"])
    guardian = to_hand(s, "Council Guardian")
    mana(s, W=1, C=5)
    act(s, "p1", type="cast_spell", card_id=guardian.id)
    for _ in range(4):
        if s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
    ballot(s, "p1", "red")
    ballot(s, "p2", bob)  # (red alone, or red and green tied for most votes)
    answer(s)
    to_phase(s, "main1", turn=3)
    shield = {a.text for a in ch(s, guardian).abilities}
    assert "Protection from red." in shield and ("Protection from green." in shield) == (bob == "green") and "Protection from blue." not in shield
    with pytest.raises(ActionError):
        bolt(s, guardian.id)
    check(s)


# -- Taigam, Ojutai Master -----------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("attacked", [True, False])
def test_taigam_gives_rebound_after_it_attacked(cards, attacked):
    s = build(cards, ["Taigam, Ojutai Master", "Opt"])
    taigam = put(s, "Taigam, Ojutai Master")
    if attacked:
        attack(s, [taigam])
    else:
        to_phase(s, "main2", turn=3)
    opt = cast(s, "Opt")
    assert zone(s, opt) == ("p1:exile" if attacked else "p1:graveyard")
    check(s)


# -- Beck // Call --------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("draw", [True, False])
def test_beck_may_draw_whenever_a_creature_enters_this_turn(cards, draw):
    s = build(cards, ["Beck // Call", "Llanowar Elves"], ["Coral Merfolk"])
    beck = to_hand(s, "Beck // Call")
    mana(s, G=1, U=1)
    act(s, "p1", type="cast_spell", card_id=beck.id)
    answer(s)
    before = hand(s)
    cast(s, "Llanowar Elves", pick=["yes" if draw else "no"])
    assert hand(s) == before + draw  # (the Elves came from the library to the hand, then were cast)
    check(s)


# -- Frodo, Adventurous Hobbit ------------------------------------------------------------------------------------------------------------------------
def test_frodo_tempts_after_three_life_and_draws_from_the_second_temptation(cards):
    s = build(cards, ["Frodo, Adventurous Hobbit", "Soul Warden", "Amateur Hero", "Kitchen Finks"])
    frodo = put(s, "Frodo, Adventurous Hobbit")
    put(s, "Soul Warden")
    for turn, gainer in ((3, "Amateur Hero"), (5, "Kitchen Finks")):
        to_phase(s, "main1", turn=turn)
        cast(s, gainer)  # (Soul Warden's 1 and its own 2: three life this turn)
        before = hand(s)
        attack(s, [frodo], turn=turn, pick=[frodo.id])
        assert s.state.rules.ring_tempted.get("p1") == (1 if turn == 3 else 2)
        assert hand(s) == before + (turn == 5)  # (Frodo is the Ring-bearer; the second temptation draws)
    check(s)


# -- Riverchurn Monument ------------------------------------------------------------------------------------------------------------------------------
def test_riverchurn_monument_exhaust_mills_each_target_its_own_graveyard_size(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Riverchurn Monument", "Grizzly Bears", "Opt", "Sol Ring"])
    monument = put(s, "Riverchurn Monument")
    bury(s, "Grizzly Bears", "Opt", "Sol Ring")
    for c in [c for c in s.state.zones["p2:library"] if s.state.cards[c].name == "Island"][:2]:
        act(s, "p2", type="move", card_ids=[c], to={"zone": "graveyard"})
    alice, bob = len(s.state.zones["p1:library"]), len(s.state.zones["p2:library"])
    mana(s, U=2, C=2)
    act(s, "p1", type="activate_ability", card_id=monument.id, ability=1, targets=["p1", "p2"], target_counts=[2])
    answer(s)
    assert len(s.state.zones["p1:library"]) == alice - 3 and len(s.state.zones["p2:library"]) == bob - 2
    to_phase(s, "main1", turn=3)
    mana(s, U=2, C=2)
    with pytest.raises(ActionError):  # (exhaust: only once, 702.177a)
        act(s, "p1", type="activate_ability", card_id=monument.id, ability=1, targets=["p2"], target_counts=[1])
    check(s)


# -- Angel of Destiny --------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("attacked,start", [(True, 55), (True, 54), (False, 60)])
def test_angel_of_destiny_ends_the_game_for_the_players_it_attacked(cards, attacked, start):
    s = build(cards, ["Angel of Destiny"])
    angel = put(s, "Angel of Destiny")
    if attacked:
        attack(s, [angel])
    else:
        to_phase(s, "main2", turn=3)
    act(s, "p1", type="set_life", player="p1", value=start)
    to_phase(s, "end", turn=3)
    answer(s)
    assert ("p2" in s.state.rules.lost) == (attacked and start >= 55)
    check(s)


# -- The Lunar Whale ---------------------------------------------------------------------------------------------------------------------------------
def test_the_lunar_whale_plays_the_top_card_after_it_attacked(cards):
    from app.game.errors import ActionError

    s = build(cards, ["The Lunar Whale", "Grizzly Bears", "Coral Merfolk"])
    whale, merfolk = put(s, "The Lunar Whale"), put(s, "Coral Merfolk")
    bear = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears")
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "library"}, position="top")
    mana(s, G=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bear.id)
    act(s, "p1", type="activate_ability", card_id=whale.id, ability=next(a.index for a in ch(s, whale).abilities if a.text.startswith("Crew")))
    answer(s, [merfolk.id])
    attack(s, [whale])
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bear.id)
    answer(s)
    assert zone(s, bear) == "p1:battlefield"
    check(s)


# -- Glissa's Retriever ------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("poison,back", [(3, 1), (2, 0)])
def test_glissas_retriever_returns_up_to_one_card_per_corrupted_opponent(cards, poison, back):
    s = build(cards, ["Glissa's Retriever", "Grizzly Bears", "Opt", "Murder"])
    retriever = put(s, "Glissa's Retriever")
    bury(s, "Grizzly Bears", "Opt")
    act(s, "p2", type="set_resource", player="p2", key="poison", value=poison)
    c = to_hand(s, "Murder")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[retriever.id])
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None or not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert zone(s, retriever) == "p1:exile"
    bear = next(x for x in s.state.cards.values() if x.name == "Grizzly Bears")
    if back:
        assert d is not None and d.max_choices == 1  # (one opponent with three or more poison counters: up to one target)
        answer(s, [bear.id])
        assert zone(s, bear) == "p1:hand"
    else:
        answer(s)
        assert zone(s, bear) == "p1:graveyard"  # (X is 0: no target, nothing returns)
    check(s)


# -- Split Decision ---------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("alice,bob,draws", [("denial", "denial", 0), ("denial", "duplication", 2), ("duplication", "duplication", 2)])
def test_split_decision_counters_or_copies_the_spell_by_vote(cards, alice, bob, draws):
    s = build(cards, ["Split Decision", "Opt"])
    act(s, "p1", type="set_prefs", hold_priority=True)
    opt = to_hand(s, "Opt")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    split = to_hand(s, "Split Decision")
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=split.id, targets=[opt.id])
    act(s, "p1", type="set_prefs", hold_priority=False)
    for _ in range(4):
        if s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
    before = hand(s)
    ballot(s, "p1", alice)
    ballot(s, "p2", bob)  # (a tie: duplication)
    answer(s)
    assert hand(s) == before + draws and zone(s, opt) == "p1:graveyard"  # (countered, or the copy and then the spell each draw a card)
    check(s)


# -- Spellpyre Phoenix ------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cycles", [2, 1])
def test_spellpyre_phoenix_returns_after_two_cyclings(cards, cycles):
    s = build(cards, ["Spellpyre Phoenix", "Lonely Sandbar", "Secluded Steppe"])
    phoenix = next(c for c in s.state.cards.values() if c.name == "Spellpyre Phoenix")
    act(s, "p1", type="move", card_ids=[phoenix.id], to={"zone": "graveyard"})
    for name, sym in [("Lonely Sandbar", "U"), ("Secluded Steppe", "W")][:cycles]:
        c = to_hand(s, name)
        mana(s, **{sym: 1})
        act(s, "p1", type="activate_ability", card_id=c.id, ability=next(a.index for a in ch(s, c).abilities if a.text.startswith("Cycling")))
        answer(s)
    to_phase(s, "end", turn=1)
    answer(s)
    assert zone(s, phoenix) == ("p1:hand" if cycles == 2 else "p1:graveyard")
    check(s)


# -- Messenger Jays ----------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bob,counters,drawn", [("feather", 2, 0), ("quill", 1, 1)])
def test_messenger_jays_counts_and_loots_by_the_votes(cards, bob, counters, drawn):
    s = build(cards, ["Messenger Jays"])
    jays = to_hand(s, "Messenger Jays")
    mana(s, U=1, C=4)
    act(s, "p1", type="cast_spell", card_id=jays.id)
    for _ in range(4):
        if s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
    before, library = hand(s), len(s.state.zones["p1:library"])
    ballot(s, "p1", "feather")
    ballot(s, "p2", bob)
    answer(s)
    assert s.state.cards[jays.id].counters.get("+1/+1") == counters
    assert len(s.state.zones["p1:library"]) == library - drawn and hand(s) == before and len(gy(s)) == drawn  # (one discard per card drawn)
    check(s)


# -- Nesting Dragon ----------------------------------------------------------------------------------------------------------------------------------
def test_nesting_dragon_egg_hatches_a_firebreathing_dragon(cards):
    s = build(cards, ["Nesting Dragon", "Lightning Bolt"])
    put(s, "Nesting Dragon")
    act(s, "p1", type="play_land", card_id=to_hand(s, "Forest").id)
    answer(s)
    egg = next(c for c in s.state.cards.values() if c.name == "Dragon Egg")
    assert "defender" in ch(s, egg).keywords
    bolt(s, egg.id)
    dragon = next(c for c in s.state.cards.values() if c.name == "Dragon" and c.zone == "p1:battlefield")
    assert "flying" in ch(s, dragon).keywords
    mana(s, R=1)
    act(s, "p1", type="activate_ability", card_id=dragon.id, ability=next(a.index for a in ch(s, dragon).abilities if a.text.startswith("{R}")))
    answer(s)
    assert ch(s, dragon).pt == (3, 2)
    check(s)


# -- Demonfire ---------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("hellbent", [True, False])
def test_demonfire_hellbent_cant_be_countered_or_prevented(cards, hellbent):
    s = build(cards, ["Demonfire", "Opt"], ["Counterspell", "Test Ward"])
    put(s, "Test Ward", "p2")  # ("Prevent all damage that would be dealt to you.")
    fire = to_hand(s, "Demonfire")
    for c in list(s.state.zones["p1:hand"]):
        if c != fire.id:
            act(s, "p1", type="move", card_ids=[c], to={"zone": "library"})
    if not hellbent:
        to_hand(s, "Opt")
    act(s, "p2", type="set_prefs", response="on")
    counter = to_hand(s, "Counterspell", "p2")
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=fire.id, targets=["p2"], x_value=3)
    mana(s, "p2", U=2)
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[fire.id])
    answer(s)
    assert zone(s, fire) == "p1:graveyard" and life(s, "p2") == (37 if hellbent else 40)  # (countered, or dealt its unpreventable 3)
    check(s)


# -- The Wandering Emperor ---------------------------------------------------------------------------------------------------------------------------
def test_the_wandering_emperor_activates_at_instant_speed_the_turn_she_entered(cards):
    from app.game.errors import ActionError

    s = build(cards, ["The Wandering Emperor", "Opt"])
    emperor = cast(s, "The Wandering Emperor")

    def respond():  # (a loyalty ability with a spell on the stack: instant timing, 606.3)
        act(s, "p1", type="set_prefs", hold_priority=True)
        mana(s, U=1)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Opt").id)
        act(s, "p1", type="activate_ability", card_id=emperor.id, ability=3)

    respond()
    act(s, "p1", type="set_prefs", hold_priority=False)
    answer(s)
    assert names(s).count("Samurai") == 1
    to_phase(s, "main1", turn=3)
    with pytest.raises(ActionError):
        respond()
    check(s)


# -- Intermediate Chirography -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("modified", [True, False])
def test_intermediate_chirography_makes_an_inkling_after_a_modified_creature_died(cards, modified):
    s = build(cards, ["Intermediate Chirography", "Grizzly Bears", "Lightning Bolt"])
    chiro = put(s, "Intermediate Chirography")
    for ability, cost in ((1, {"B": 1, "C": 1}), (3, {"B": 1, "C": 2})):  # (the Class to level 2, then 3: 716.2)
        mana(s, **cost)
        act(s, "p1", type="activate_ability", card_id=chiro.id, ability=ability)
        answer(s)
    bear = put(s, "Grizzly Bears")
    if modified:
        act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    bolt(s, bear.id)
    assert zone(s, bear) == "p1:graveyard"
    to_phase(s, "cleanup", turn=1)
    assert names(s).count("Inkling") == (1 if modified else 0)
    check(s)


# -- Kiora of Salt and Sand ---------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("activated", [True, False])
def test_kiora_untaps_an_attacker_after_a_loyalty_activation(cards, activated):
    s = build(cards, ["Kiora of Salt and Sand", "Gideon Jura", "Grizzly Bears"])
    put(s, "Kiora of Salt and Sand")
    bear = put(s, "Grizzly Bears")
    to_phase(s, "main1", turn=3)
    gideon = cast(s, "Gideon Jura")
    if activated:
        act(s, "p1", type="activate_ability", card_id=gideon.id, ability=next(a.index for a in ch(s, gideon).abilities if a.text.startswith("0:")))
        answer(s)
    attack(s, [bear], pick=[bear.id])
    assert s.state.cards[bear.id].tapped != activated and life(s, "p2") == 38
    check(s)


# -- Laboratory Drudge --------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("how", ["flashback", "unearth", "none"])
def test_laboratory_drudge_draws_after_graveyard_play(cards, how):
    s = build(cards, ["Laboratory Drudge", "Firebolt", "Dregscape Zombie"])
    put(s, "Laboratory Drudge")
    bury(s, "Firebolt", "Dregscape Zombie")
    if how == "flashback":
        mana(s, R=1, C=4)
        act(s, "p1", type="cast_spell", card_id=next(c for c in s.state.cards.values() if c.name == "Firebolt").id, targets=["p2"])
    elif how == "unearth":
        zombie = next(c for c in s.state.cards.values() if c.name == "Dregscape Zombie")
        mana(s, B=1)
        act(s, "p1", type="activate_ability", card_id=zombie.id, ability=next(a.index for a in ch(s, zombie).abilities if a.text.startswith("Unearth")))
    answer(s)
    before = hand(s)
    to_phase(s, "cleanup", turn=1)
    assert hand(s) == before + (how != "none")
    check(s)



# -- Goliath Hatchery ---------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("poison,drawn", [(3, 3), (2, 0)])
def test_goliath_hatchery_draws_the_chosen_creatures_total_toxic_value(cards, poison, drawn):
    s = build(cards, ["Goliath Hatchery", "Glissa's Retriever"])
    put(s, "Goliath Hatchery")
    put(s, "Glissa's Retriever")  # (toxic 3)
    act(s, "p2", type="set_resource", player="p2", key="poison", value=poison)
    before = hand(s)
    to_phase(s, "main1", turn=3)
    assert hand(s) == before + 1 + drawn  # (the draw step's card, and the upkeep's)
    check(s)


# -- Warrior's Resolve -------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("counter", [True, False])
def test_warriors_resolve_draws_for_an_attacker_with_a_counter(cards, counter):
    s = build(cards, ["Warrior's Resolve", "Grizzly Bears", "Coral Merfolk"])
    put(s, "Warrior's Resolve")
    bear, merfolk = put(s, "Grizzly Bears"), put(s, "Coral Merfolk")
    act(s, "p1", type="counter", card_ids=[merfolk.id], kind="+1/+1", delta=1)  # (the Merfolk, with a counter, does not attack)
    if counter:
        act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    attack(s, [bear])
    before = hand(s)
    to_phase(s, "cleanup", turn=3)
    assert hand(s) == before + counter
    check(s)


# -- Protean Raider (raid) ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("attacked", [True, False])
def test_protean_raider_may_enter_as_a_copy_after_you_attacked(cards, attacked):
    s = build(cards, ["Protean Raider", "Grizzly Bears"], ["Wind Drake"])
    bear, drake = put(s, "Grizzly Bears"), put(s, "Wind Drake", "p2")
    if attacked:
        attack(s, [bear])
    else:
        to_phase(s, "main2", turn=3)
    raider = cast(s, "Protean Raider", pick=[drake.id])
    assert ch(s, raider).name == ("Wind Drake" if attacked else "Protean Raider")
    check(s)


# -- Sage of the Skies ---------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("another", [True, False])
def test_sage_of_the_skies_copies_itself_after_another_spell(cards, another):
    s = build(cards, ["Sage of the Skies", "Opt"])
    if another:
        cast(s, "Opt")
    cast(s, "Sage of the Skies")
    assert names(s).count("Sage of the Skies") == (2 if another else 1)  # (the copy became a token, 707.10f)
    check(s)


# -- Hatchery Spider ---------------------------------------------------------------------------------------------------------------------------------
def test_hatchery_spider_reveals_and_caps_by_the_creature_cards_in_your_graveyard(cards):
    s = build(cards, ["Hatchery Spider", "Grizzly Bears", "Coral Merfolk", "Llanowar Elves", "Kitchen Finks"])
    bury(s, "Grizzly Bears", "Coral Merfolk")  # (X = 2)
    elves, finks = [next(c for c in s.state.cards.values() if c.name == n) for n in ("Llanowar Elves", "Kitchen Finks")]
    for c in (elves, finks):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "library"}, position="top")
    spider = to_hand(s, "Hatchery Spider")
    mana(s, G=2, C=5)
    act(s, "p1", type="cast_spell", card_id=spider.id)
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None or not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and finks.id not in [o.id for o in d.options] and elves.id in [o.id for o in d.options]  # (Finks has mana value 3)
    answer(s, [elves.id])
    assert zone(s, elves) == "p1:battlefield" and zone(s, finks) == "p1:library" and s.state.zones["p1:library"][-1] == finks.id
    check(s)


# -- Skyclave Shade ----------------------------------------------------------------------------------------------------------------------------------
def test_skyclave_shade_may_be_cast_from_the_graveyard_after_landfall(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Skyclave Shade"])
    shade = next(c for c in s.state.cards.values() if c.name == "Skyclave Shade")
    act(s, "p1", type="move", card_ids=[shade.id], to={"zone": "graveyard"})
    mana(s, B=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=shade.id)
    act(s, "p1", type="play_land", card_id=to_hand(s, "Forest").id)
    answer(s)
    act(s, "p1", type="cast_spell", card_id=shade.id)
    answer(s)
    assert zone(s, shade) == "p1:battlefield"
    check(s)


# -- Basri Ket -----------------------------------------------------------------------------------------------------------------------------------
def test_basri_ket_makes_a_soldier_for_each_nontoken_attacker(cards):
    from tests.test_rules_conditionals import token_of

    s = build(cards, ["Basri Ket", "Grizzly Bears", "Coral Merfolk"])
    bear, merfolk = put(s, "Grizzly Bears"), put(s, "Coral Merfolk")
    spirit = token_of(s, "p1", "Spirit", "Token Creature — Spirit", "1/1")
    to_phase(s, "main1", turn=3)
    basri = cast(s, "Basri Ket")
    act(s, "p1", type="activate_ability", card_id=basri.id, ability=1)
    answer(s)
    attack(s, [bear, merfolk, spirit])
    soldiers = [c for c in s.state.cards.values() if c.name == "Soldier"]
    assert len(soldiers) == 2 and all(c.tapped for c in soldiers)  # (two nontoken attackers; the Spirit token doesn't count)
    assert life(s, "p2") == 40 - 2 - 2 - 1 - 2  # (the Soldiers entered attacking and dealt their damage)
    check(s)


# -- Spiny Starfish ----------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("times", [2, 0])
def test_spiny_starfish_makes_a_starfish_for_each_regeneration(cards, times):
    s = build(cards, ["Spiny Starfish", "Lightning Bolt"])
    starfish = put(s, "Spiny Starfish")
    for _ in range(times):
        mana(s, U=1)
        act(s, "p1", type="activate_ability", card_id=starfish.id, ability=0)
        answer(s)
        bolt(s, starfish.id)  # (lethal damage destroys it: the shield replaces that, 701.19a)
        assert zone(s, starfish) == "p1:battlefield"
    to_phase(s, "cleanup", turn=1)
    assert sum(1 for c in s.state.cards.values() if c.name == "Starfish" and c.zone == "p1:battlefield") == times
    check(s)


# -- Elvish Refueler ----------------------------------------------------------------------------------------------------------------------------
def test_elvish_refueler_reopens_one_exhaust_activation_each_of_your_turns(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Elvish Refueler", "Prowcatcher Specialist"])
    put(s, "Elvish Refueler")
    prow = put(s, "Prowcatcher Specialist")
    exhaust = next(a.index for a in ch(s, prow).abilities if a.text.startswith("Exhaust"))

    def go():
        mana(s, R=1, C=3)
        act(s, "p1", type="activate_ability", card_id=prow.id, ability=exhaust)
        answer(s)

    go()
    with pytest.raises(ActionError):
        go()  # (Alice activated an exhaust ability this turn: 702.177b)
    to_phase(s, "main1", turn=3)
    go()  # (her turn, none activated yet this turn: as though it hadn't been activated)
    with pytest.raises(ActionError):
        go()
    assert s.state.cards[prow.id].counters.get("+1/+1") == 4
    check(s)


# -- Bloodbraid Marauder -----------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("delirium", [True, False])
def test_bloodbraid_marauder_cascades_with_delirium(cards, delirium):
    s = build(cards, ["Bloodbraid Marauder", "Llanowar Elves", "Grizzly Bears", "Opt", "Sol Ring"])
    if delirium:
        bury(s, *DELIRIUM)
    elves = next(c for c in s.state.cards.values() if c.name == "Llanowar Elves")
    act(s, "p1", type="move", card_ids=[elves.id], to={"zone": "library"}, position="top")
    marauder = cast(s, "Bloodbraid Marauder", pick=["yes", elves.id])
    assert zone(s, marauder) == "p1:battlefield" and zone(s, elves) == ("p1:battlefield" if delirium else "p1:library")
    check(s)


# -- Sita Varma, Masked Racer -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("choose", [True, False])
def test_sita_varma_counters_then_sets_the_others_base_power(cards, choose):
    from app.game.errors import ActionError

    s = build(cards, ["Sita Varma, Masked Racer", "Grizzly Bears"])
    sita, bear = put(s, "Sita Varma, Masked Racer"), put(s, "Grizzly Bears")
    power = ch(s, sita).pt[0]
    mana(s, G=2, U=1, C=2)
    act(s, "p1", type="activate_ability", card_id=sita.id, ability=0, x_value=2)
    answer(s, ["yes" if choose else "no"])
    assert ch(s, sita).pt[0] == power + 2 and ch(s, bear).pt == ((power + 2, power + 2) if choose else (2, 2))
    mana(s, G=2, U=1)
    with pytest.raises(ActionError):  # (exhaust: only once, 702.177a)
        act(s, "p1", type="activate_ability", card_id=sita.id, ability=0, x_value=0)
    check(s)


# -- Magnigoth Treefolk -----------------------------------------------------------------------------------------------------------------------------
def test_magnigoth_treefolk_has_the_landwalk_of_each_basic_type_you_control(cards):
    s = build(cards, ["Magnigoth Treefolk", "Island", "Forest"])
    tree = put(s, "Magnigoth Treefolk")
    assert not {k for k in ch(s, tree).keywords if k.endswith("walk")}
    put(s, "Island")
    assert {k for k in ch(s, tree).keywords if k.endswith("walk")} == {"islandwalk"}
    put(s, "Forest")
    assert {k for k in ch(s, tree).keywords if k.endswith("walk")} == {"islandwalk", "forestwalk"}
    check(s)


# -- Goddric, Cloaked Reveler -----------------------------------------------------------------------------------------------------------------------
def test_goddric_is_a_dragon_after_two_nonland_permanents_entered(cards):
    s = build(cards, ["Goddric, Cloaked Reveler", "Grizzly Bears", "Forest"])
    god = put(s, "Goddric, Cloaked Reveler")  # (one nonland permanent entered)
    put(s, "Forest")
    assert "Dragon" not in ch(s, god).subtypes and "flying" not in ch(s, god).keywords and ch(s, god).pt != (4, 4)
    cast(s, "Grizzly Bears")
    got = ch(s, god)
    assert got.subtypes == {"Dragon"} and got.pt == (4, 4) and "flying" in got.keywords and "haste" in got.keywords
    pump = next(a.index for a in got.abilities if a.text.startswith("{R}: Dragons"))
    mana(s, R=1)
    act(s, "p1", type="activate_ability", card_id=god.id, ability=pump)
    answer(s)
    assert ch(s, god).pt == (5, 4)  # (it is a Dragon itself)
    check(s)


# -- Zimone, Mystery Unraveler ----------------------------------------------------------------------------------------------------------------------
def test_zimone_manifests_dread_first_then_turns_a_permanent_face_up(cards):
    s = build(cards, ["Zimone, Mystery Unraveler", "Forest", "Rampant Growth", "Grizzly Bears", "Llanowar Elves"])
    put(s, "Zimone, Mystery Unraveler")
    for name in ("Grizzly Bears", "Llanowar Elves"):
        c = next(c for c in s.state.cards.values() if c.name == name)
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "library"}, position="top")
    act(s, "p1", type="play_land", card_id=to_hand(s, "Forest").id)
    answer(s)
    down = [c for c in s.state.cards.values() if c.face_down and c.zone == "p1:battlefield"]
    assert len(down) == 1
    cast(s, "Rampant Growth")
    answer(s)
    assert not s.state.cards[down[0].id].face_down
    assert not [c for c in s.state.cards.values() if c.face_down and c.zone == "p1:battlefield"]  # (no second manifest)
    check(s)
