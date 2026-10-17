"""Wave 47A: commanders with two blocking lines (CR 2026-09-25), real Oracle text (tests/fixtures/wave47a_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 119.1, 903.7: "less than half their starting life total" (Anya): strictly less, an opponent's own life total against the game's starting life.
* 601.2f: cost changers read as the total cost is determined (Doran: toughness greater than power; Heliod: the cards your opponents drew this turn).
* 603.2: "Whenever a creature you control attacks or blocks, it gets +X/+X" (Doran) is one trigger for each of the two events.
* 702.112: renown granted to attackers; "renowned" is the designation of 702.112b (Aragorn, Hornburg Hero).
* 509.1b: "can't be blocked unless all creatures defending player controls block it" (Tromokratis, ruling 2014-02-01).
* 120.3: "dealt damage to another creature this turn", doubled by a replacement of its own damage (Wolverine).
* 509.1b, 611.2c: "can't be blocked by creatures with greater power this combat" ends with the combat (Tadeas).
* 613.1b: "that player untaps Karona and gains control of it" at each player's upkeep.
* 122.6, 603.2: "When the tenth +1/+1 counter is put on Shang-Chi" (ruling 2019-10-04 for the same wording): the event that takes it from nine to ten.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_permissions import cost_of
from tests.test_rules_wave34b_activated import activate, ask, attack, next_turn, settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand
from tests.wave44c_kit import ch, life

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave47a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w47a", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
ANYA, DORAN, HELIOD = "Anya, Merciless Angel", "Doran, Besieged by Time", "Heliod, the Radiant Dawn // Heliod, the Warped Eclipse"
ARAGORN, TROM, WOLVERINE = "Aragorn, Hornburg Hero", "Tromokratis", "Wolverine, Best There Is"
TADEAS, KARONA, SHANG = "Tadeas, Juniper Ascendant", "Karona, False God", "Shang-Chi and the Ten Rings"
NAMES = [ANYA, DORAN, HELIOD, ARAGORN, TROM, WOLVERINE, TADEAS, KARONA, SHANG]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", NAMES)
def test_every_commander_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def set_life(s, pid, value):
    act(s, pid, type="set_life", player=pid, value=value)


def has(s, c, keyword):
    return keyword in ch(s, c).keywords


# ---- 119.1, 903.7: Anya ----------------------------------------------------------------------------------------------------------------------------
def test_anya_grows_and_is_indestructible_while_an_opponent_is_below_half_the_starting_life(cards):
    s = build(cards, [ANYA], [])
    anya = put(s, ANYA)
    assert pt(s, ANYA) == (4, 4) and not has(s, anya, "indestructible")
    set_life(s, "p2", 20)  # exactly half of 40: not less than half
    assert pt(s, ANYA) == (4, 4) and not has(s, anya, "indestructible")
    set_life(s, "p2", 19)
    assert pt(s, ANYA) == (7, 7) and has(s, anya, "indestructible")
    set_life(s, "p2", 25)  # (it is not locked in: 611.3a)
    assert pt(s, ANYA) == (4, 4) and not has(s, anya, "indestructible")
    check(s)


def test_anya_looks_at_the_opponents_not_at_its_own_controller(cards):
    s = build(cards, [ANYA], [])
    anya = put(s, ANYA)
    set_life(s, "p1", 5)
    assert pt(s, ANYA) == (4, 4) and not has(s, anya, "indestructible")
    check(s)


# ---- 601.2f: Doran ---------------------------------------------------------------------------------------------------------------------------------
def test_doran_reduces_only_creature_spells_whose_toughness_is_greater_than_their_power(cards):
    s = build(cards, [DORAN, "Wall of Omens", "Hill Giant", "Lightning Bolt"], [])
    wall, giant, bolt = to_hand(s, "Wall of Omens"), to_hand(s, "Hill Giant"), to_hand(s, "Lightning Bolt")
    assert cost_of(s, wall, cards) == "{1}{W}" and cost_of(s, giant, cards) == "{3}{R}"
    put(s, DORAN)
    assert cost_of(s, wall, cards) == "{W}"  # 0/4
    assert cost_of(s, giant, cards) == "{3}{R}"  # 3/3: not greater
    assert cost_of(s, bolt, cards) == "{R}"  # not a creature spell
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=wall.id)
    settle(s)
    assert s.state.cards[wall.id].zone == "p1:battlefield"
    check(s)


def test_doran_pumps_an_attacker_by_the_difference_between_its_power_and_toughness(cards):
    s = build(cards, [DORAN, "Kitchen Finks"], [])
    doran, finks = put(s, DORAN), put(s, "Kitchen Finks")
    settle(s)
    next_turn(s)
    attack(s, doran, finks)
    settle(s)
    assert pt(s, DORAN) == (5, 10)  # 0/5: +5/+5
    assert pt(s, "Kitchen Finks") == (4, 3)  # 3/2: +1/+1
    check(s)


def test_doran_pumps_a_blocker_but_not_a_creature_of_the_other_player(cards):
    s = build(cards, [DORAN, "Kitchen Finks"], ["Grizzly Bears"])
    finks, bears = put(s, "Kitchen Finks"), put(s, "Grizzly Bears", "p2")
    put(s, DORAN)
    settle(s)
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
    d = ask(s)
    assert d.kind == "declare_blockers" and d.player == "p1"
    act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": finks.id, "attacker_id": bears.id}])
    settle(s)
    assert pt(s, "Kitchen Finks") == (4, 3)  # blocking: +1/+1
    assert pt(s, "Grizzly Bears", "p2") == (2, 2)  # (Bob's attacker: not a creature Alice controls)
    check(s)


# ---- Heliod ----------------------------------------------------------------------------------------------------------------------------------------
def test_heliod_returns_an_enchantment_that_is_not_a_god_and_cheapens_spells_for_cards_the_opponents_drew(cards):
    s = build(cards, [HELIOD, "Arrest", "Purphoros, God of the Forge", "Grizzly Bears"], [])
    for name in ("Arrest", "Purphoros, God of the Forge"):
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"player": "p1", "zone": "graveyard"})
    heliod = to_hand(s, HELIOD)
    mana(s, W=4)
    act(s, "p1", type="cast_spell", card_id=heliod.id)
    settle(s)
    assert card_named(s, "Arrest").zone == "p1:hand"  # the God stays where it was
    assert card_named(s, "Purphoros, God of the Forge").zone == "p1:graveyard"
    bears = to_hand(s, "Grizzly Bears")
    assert cost_of(s, bears, cards) == "{1}{G}"
    act(s, "p2", type="draw", player="p2", count=2)
    assert cost_of(s, bears, cards) == "{1}{G}"  # (the front face has no such line: Heliod, the Warped Eclipse does)
    mana(s, W=3, U=1)
    activate(s, "p1", card_named(s, HELIOD), "Transform")
    settle(s)
    assert cost_of(s, bears, cards) == "{G}"  # two cards the opponent drew this turn
    act(s, "p1", type="draw", player="p1", count=3)
    assert cost_of(s, bears, cards) == "{G}"  # (your own draws don't count)
    act(s, "p2", type="draw", player="p2", count=1)
    assert cost_of(s, bears, cards) == "{G}"  # ({1} less for each: the generic part is gone)
    check(s)


def test_heliod_finds_nothing_when_only_a_god_is_in_the_graveyard(cards):
    s = build(cards, [HELIOD, "Purphoros, God of the Forge"], [])
    act(s, "p1", type="move", card_ids=[card_named(s, "Purphoros, God of the Forge").id], to={"player": "p1", "zone": "graveyard"})
    heliod = to_hand(s, HELIOD)
    mana(s, W=4)
    act(s, "p1", type="cast_spell", card_id=heliod.id)
    settle(s)
    assert card_named(s, "Purphoros, God of the Forge").zone == "p1:graveyard"
    check(s)


# ---- 702.112: Aragorn, Hornburg Hero ---------------------------------------------------------------------------------------------------------------
def counters(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].counters.get("+1/+1", 0)


def test_attackers_gain_renown_and_a_renowned_one_doubles_its_counters_the_next_time(cards):
    s = build(cards, [ARAGORN, "Grizzly Bears"], [])
    put(s, ARAGORN)
    bears = put(s, "Grizzly Bears")
    settle(s)
    next_turn(s)
    attack(s, bears)
    settle(s)
    assert counters(s, "Grizzly Bears") == 1 and life(s, "p2") == 38  # renown 1: a counter, and it became renowned (it was not renowned as it hit)
    to_phase(s, "main1", turn=5)
    attack(s, bears)
    settle(s)
    assert counters(s, "Grizzly Bears") == 2  # now renowned: Aragorn doubles the one counter
    assert life(s, "p2") == 38 - 3
    to_phase(s, "main1", turn=7)
    attack(s, bears)
    settle(s)
    assert counters(s, "Grizzly Bears") == 4  # (and again, 122.1)
    check(s)


def test_a_creature_that_does_not_attack_gets_no_renown(cards):
    s = build(cards, [ARAGORN, "Grizzly Bears"], [])
    attacker = put(s, ARAGORN)
    put(s, "Grizzly Bears")
    settle(s)
    next_turn(s)
    stops(s)
    attack(s, attacker)  # (Aragorn alone: the Bears stay home, so they're no attacking creature)
    assert has(s, card_named(s, ARAGORN), "first strike") and not has(s, card_named(s, "Grizzly Bears"), "first strike")
    to_phase(s, "main2")
    assert counters(s, "Grizzly Bears") == 0
    check(s)


# ---- 509.1b: Tromokratis ---------------------------------------------------------------------------------------------------------------------------
def trom_table(cards, bob):
    s = build(cards, [TROM], bob)
    trom = put(s, TROM)
    for name in bob:
        put(s, name, "p2")
    settle(s)
    next_turn(s)
    return s, trom


def blocks(s, *pairs):
    d = ask(s)
    assert d.kind == "declare_blockers" and d.player == "p2"
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id} for b, a in pairs])


def test_tromokratis_is_blocked_only_by_all_of_the_defenders_creatures_or_none(cards):
    s, trom = trom_table(cards, ["Hill Giant", "Grizzly Bears"])
    attack(s, trom)
    giant, bears = card_named(s, "Hill Giant", "p2"), card_named(s, "Grizzly Bears", "p2")
    with pytest.raises(ActionError, match="can't be blocked unless all creatures"):
        blocks(s, (giant, trom))
    blocks(s, (giant, trom), (bears, trom))
    assert all(s.state.cards[c.id].blocks(trom.id) for c in (giant, bears))
    check(s)


def test_tromokratis_is_unblocked_when_one_creature_of_the_defender_is_tapped(cards):
    s, trom = trom_table(cards, ["Hill Giant", "Grizzly Bears"])
    act(s, "p2", type="tap", card_ids=[card_named(s, "Grizzly Bears", "p2").id])  # (it can't block, so they can't all)
    attack(s, trom)
    giant = card_named(s, "Hill Giant", "p2")
    with pytest.raises(ActionError, match="can't be blocked unless all creatures"):
        blocks(s, (giant, trom))
    blocks(s)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - 8
    check(s)


def test_tromokratis_has_hexproof_only_while_it_is_not_attacking_or_blocking(cards):
    s, trom = trom_table(cards, ["Grizzly Bears"])
    assert has(s, trom, "hexproof")
    stops(s)
    attack(s, trom)
    assert not has(s, trom, "hexproof")  # attacking: Bob may target it now
    to_phase(s, "main2")
    assert has(s, trom, "hexproof")  # (combat is over)
    check(s)


# ---- 120.3, 120.4: Wolverine -----------------------------------------------------------------------------------------------------------------------
def test_wolverine_doubles_its_damage_and_grows_at_the_end_step_after_damaging_a_creature(cards):
    s = build(cards, [WOLVERINE], ["Wall of Omens"])
    wolverine = put(s, WOLVERINE)
    wall = put(s, "Wall of Omens", "p2")
    settle(s)
    next_turn(s)
    stops(s)
    attack(s, wolverine)
    blocks(s, (wall, wolverine))
    to_phase(s, "main2")
    assert s.state.cards[wall.id].zone == "p2:graveyard"  # 2 doubled is 4: the 0/4 Wall dies
    to_phase(s, "end")
    settle(s)
    assert counters(s, WOLVERINE) == 1 and pt(s, WOLVERINE) == (3, 3)
    check(s)


def test_wolverine_doubles_its_damage_to_a_player_but_grows_only_for_a_creature(cards):
    s = build(cards, [WOLVERINE], [])
    wolverine = put(s, WOLVERINE)
    settle(s)
    next_turn(s)
    stops(s)
    attack(s, wolverine)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - 4
    to_phase(s, "end")
    settle(s)
    assert counters(s, WOLVERINE) == 0  # (damage to a player is not damage to another creature)
    check(s)


# ---- 509.1b, 611.2c: Tadeas --------------------------------------------------------------------------------------------------------------------------
def test_tadeas_untaps_and_cannot_be_blocked_by_greater_power_while_attacking_with_reach(cards):
    s = build(cards, [TADEAS], ["Hill Giant"])
    tadeas = put(s, TADEAS)
    giant = put(s, "Hill Giant", "p2")
    settle(s)
    next_turn(s)
    assert has(s, tadeas, "hexproof")
    stops(s)
    attack(s, tadeas)
    settle(s)
    assert not s.state.cards[tadeas.id].tapped and not has(s, tadeas, "hexproof")  # untapped by its trigger (it has reach)
    with pytest.raises(ActionError, match="greater power"):
        to_phase(s, "declare_blockers")
        blocks(s, (giant, tadeas))
    blocks(s)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - 1
    check(s)


def test_tadeas_gives_nothing_to_an_attacker_without_reach(cards):
    s = build(cards, [TADEAS, "Grizzly Bears"], ["Hill Giant"])
    put(s, TADEAS)
    bears = put(s, "Grizzly Bears")
    giant = put(s, "Hill Giant", "p2")
    settle(s)
    next_turn(s)
    attack(s, bears)
    blocks(s, (giant, bears))  # the Giant (power 3) may block the Bears (power 2): no reach, no trigger
    to_phase(s, "main2")
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    check(s)


# ---- 613.1b: Karona --------------------------------------------------------------------------------------------------------------------------------
def test_karona_changes_hands_at_every_players_upkeep_and_untaps(cards):
    s = build(cards, [KARONA], [])
    karona = put(s, KARONA)
    act(s, "p1", type="tap", card_ids=[karona.id])
    settle(s)
    stops(s)
    to_phase(s, "upkeep", turn=2)
    settle(s)  # Bob's upkeep: Bob untaps it and gains control
    assert s.state.cards[karona.id].controller == "p2" and not s.state.cards[karona.id].tapped
    act(s, "p2", type="tap", card_ids=[karona.id])
    to_phase(s, "upkeep", turn=3)
    settle(s)  # Alice's upkeep: the trigger is Bob's now, and it is Alice who takes it back
    assert s.state.cards[karona.id].controller == "p1" and not s.state.cards[karona.id].tapped
    to_phase(s, "upkeep", turn=5)
    settle(s)  # (a turn later, at Alice's own upkeep it stays hers and is untapped)
    assert s.state.cards[karona.id].controller == "p1"
    check(s)


# ---- 122.6, 603.2: Shang-Chi ---------------------------------------------------------------------------------------------------------------------------
def test_shang_chi_draws_five_and_gains_five_for_the_tenth_counter_only_once(cards):
    s = build(cards, [SHANG, "Opt", "Opt"], [])
    shang = put(s, SHANG)
    act(s, "p1", type="counter", card_ids=[shang.id], kind="+1/+1", delta=8)
    for opt in range(2):  # Opt draws a card: the first draw puts the ninth counter on it, the second the tenth
        opt_card = next(c for c in s.state.cards.values() if c.name == "Opt" and c.owner == "p1" and c.zone != "p1:graveyard")
        act(s, "p1", type="move", card_ids=[opt_card.id], to={"zone": "hand"})
        mana(s, U=1)
        act(s, "p1", type="cast_spell", card_id=opt_card.id)
        settle(s)
        if opt == 0:
            assert counters(s, SHANG) == 9 and life(s, "p1") == 40  # the ninth: nothing yet
    assert life(s, "p1") == 45 and len(s.state.zones["p1:hand"]) >= 6  # the tenth counter: draw five and gain 5 life
    assert counters(s, SHANG) == 15  # (each of the five draws put another counter on it; none of them is the tenth)
    check(s)
