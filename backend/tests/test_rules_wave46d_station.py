"""Wave 46D: station and Spacecraft (CR 2026-09-25), real Oracle text (tests/fixtures/wave46d_station_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 702.184a: "Station" means "Tap another untapped creature you control: Put a number of charge counters on this permanent equal to the
  tapped creature's power. Activate only as a sorcery." The power is the creature's as the ability resolves (last known if it left).
* 721.2a-b: "{N+}[abilities][P/T]" means "As long as this permanent has N or more charge counters on it, it has [abilities] (and is a
  creature with base power and toughness [P/T] in addition to its other types)."
* 721.2c: a station card has no power or toughness off the battlefield; 721.4: its station ability works at any counter count.
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
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_conditionals import creature, pick, until_asked
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave46d_station_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t46d", number=f"S{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ch_of(s, name):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name).id])


def charge(s, name):
    return s.state.cards[card_named(s, name).id].counters.get("charge", 0)


def add_charge(s, name, n):
    act(s, "p1", type="counter", card_ids=[card_named(s, name).id], kind="charge", delta=n)


def station(s, name, tapped):
    """Activate the station ability of ``name``, tapping this creature; resolve it."""
    ch = ch_of(s, name)
    index = next(a.index for a in ch.abilities if a.text.startswith("Tap another untapped creature"))
    act(s, "p1", type="activate_ability", card_id=card_named(s, name).id, ability=index)
    if until_asked(s) is not None:  # (a single candidate is tapped without asking)
        pick(s, tapped.id)
    answer(s)


def ready(s, *names):
    for n in names:
        s.state.rules.controlled_since[card_named(s, n).id].turn = 0


@pytest.mark.parametrize("name", [c["name"] for c in DATA if c["name"] != "Doubling Season"])  # (wave 48D: Exploration Broodship is FULL: tests/test_rules_wave48d_broodship.py)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


@pytest.mark.parametrize("power,toughness,counters", [(1, 4, 4), (3, 3, 3), (4, 1, 4)])
def test_tapestry_warden_stations_with_toughness_only_where_it_is_greater_than_power(cards, power, toughness, counters):
    """702.184c: Tapestry Warden's static makes a creature with toughness greater than its power station using its toughness (power otherwise)."""
    s = build(cards, ["Galvanizing Sawship", "Tapestry Warden"])
    put(s, "Galvanizing Sawship")
    put(s, "Tapestry Warden")
    wall = creature(s, "p1", "Wall", pt=f"{power}/{toughness}")
    station(s, "Galvanizing Sawship", wall)
    assert charge(s, "Galvanizing Sawship") == counters
    check(s)


def test_without_tapestry_warden_the_power_counts(cards):
    s = build(cards, ["Galvanizing Sawship"])
    put(s, "Galvanizing Sawship")
    station(s, "Galvanizing Sawship", creature(s, "p1", "Wall", pt="1/4"))
    assert charge(s, "Galvanizing Sawship") == 1


def test_station_puts_counters_equal_to_the_tapped_creatures_power(cards):
    s = build(cards, ["Galvanizing Sawship"])
    put(s, "Galvanizing Sawship")
    bear = creature(s, "p1", "Bear", pt="2/2")
    station(s, "Galvanizing Sawship", bear)
    assert charge(s, "Galvanizing Sawship") == 2 and s.state.cards[bear.id].tapped
    ch = ch_of(s, "Galvanizing Sawship")
    assert not ch.is_creature and ch.power is None  # (721.2c, 721.2b: below 3 it is no creature and has no power or toughness)
    check(s)


def test_a_counter_doubler_doubles_the_station_counters(cards):
    s = build(cards, ["Galvanizing Sawship", "Doubling Season"])
    put(s, "Galvanizing Sawship")
    put(s, "Doubling Season")
    station(s, "Galvanizing Sawship", creature(s, "p1", "Bear", pt="2/2"))
    assert charge(s, "Galvanizing Sawship") == 4  # (614.1: Doubling Season puts twice that many)
    check(s)


def test_crossing_the_threshold_gives_the_abilities_and_the_creature(cards):
    s = build(cards, ["Galvanizing Sawship"])
    put(s, "Galvanizing Sawship")
    ready(s, "Galvanizing Sawship")
    giant = creature(s, "p1", "Giant", pt="3/3")
    before = ch_of(s, "Galvanizing Sawship")
    assert not before.is_creature and not {"flying", "haste"} & before.keywords
    station(s, "Galvanizing Sawship", giant)
    after = ch_of(s, "Galvanizing Sawship")
    assert after.is_creature and "Artifact" in after.types and after.pt == (6, 5) and {"flying", "haste"} <= after.keywords
    act(s, "p1", type="pass_priority")  # -> declare attackers: the Spacecraft (a creature now, there since the turn began) attacks
    assert s.state.rules.decision.kind == "declare_attackers"
    ship = card_named(s, "Galvanizing Sawship")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ship.id, "target": "p2"}])
    assert s.state.cards[ship.id].tapped
    check(s)


def test_dropping_below_the_threshold_takes_them_away(cards):
    s = build(cards, ["Galvanizing Sawship"])
    put(s, "Galvanizing Sawship")
    add_charge(s, "Galvanizing Sawship", 4)
    assert ch_of(s, "Galvanizing Sawship").is_creature
    add_charge(s, "Galvanizing Sawship", -2)  # (the abilities follow the counters, 721.2a)
    now = ch_of(s, "Galvanizing Sawship")
    assert charge(s, "Galvanizing Sawship") == 2 and not now.is_creature and not {"flying", "haste"} & now.keywords
    add_charge(s, "Galvanizing Sawship", 1)
    assert ch_of(s, "Galvanizing Sawship").is_creature  # (exactly 3 is enough: "N or more")
    check(s)


def test_station_is_a_sorcery_speed_ability(cards):
    s = build(cards, ["Galvanizing Sawship"])
    ship = put(s, "Galvanizing Sawship")
    bear = creature(s, "p1", "Bear", pt="2/2")
    cub = creature(s, "p1", "Cub", pt="1/1")
    ready(s, "Bear")
    index = next(a.index for a in ch_of(s, "Galvanizing Sawship").abilities if a.text.startswith("Tap another"))
    act(s, "p1", type="set_stops", own=["main1", "declare_attackers", "main2"], others=["main1"])
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="activate_ability", card_id=ship.id, ability=index)
    pick(s, cub.id)
    assert s.state.zones["stack"] and s.state.rules.priority == "p1"
    with pytest.raises(ActionError, match="as a sorcery"):  # (a station ability on the stack: 307.5, 602.5d)
        act(s, "p1", type="activate_ability", card_id=ship.id, ability=index)
    act(s, "p1", type="set_prefs", hold_priority=False)
    answer(s)
    assert charge(s, "Galvanizing Sawship") == 1
    act(s, "p1", type="pass_priority")  # -> combat
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    assert s.state.turn.phase == "declare_attackers" and s.state.rules.priority == "p1"
    with pytest.raises(ActionError, match="as a sorcery"):  # (combat is no main phase)
        act(s, "p1", type="activate_ability", card_id=ship.id, ability=index)
    assert charge(s, "Galvanizing Sawship") == 1
    check(s)


def test_station_needs_another_untapped_creature(cards):
    s = build(cards, ["Galvanizing Sawship"])
    ship = put(s, "Galvanizing Sawship")
    add_charge(s, "Galvanizing Sawship", 3)  # (a creature itself now, and the only one: it can't tap itself, "another")
    index = next(a.index for a in ch_of(s, "Galvanizing Sawship").abilities if a.text.startswith("Tap another"))
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=ship.id, ability=index)
    bear = creature(s, "p1", "Bear", pt="2/2")
    act(s, "p1", type="tap", card_ids=[bear.id])
    with pytest.raises(ActionError):  # (an untapped one, 702.184a)
        act(s, "p1", type="activate_ability", card_id=ship.id, ability=index)
    assert charge(s, "Galvanizing Sawship") == 3
    check(s)


def held_station(s, name, tapped):
    """Activate the station ability of ``name`` tapping this creature and keep priority: the ability stays on the stack."""
    index = next(a.index for a in ch_of(s, name).abilities if a.text.startswith("Tap another untapped creature"))
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="activate_ability", card_id=card_named(s, name).id, ability=index)
    if s.state.rules.decision is not None:
        pick(s, tapped.id)
    act(s, "p1", type="set_prefs", hold_priority=False)
    assert s.state.zones["stack"]


def ch_of_id(s, cid):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[cid])


def test_the_power_is_read_as_the_ability_resolves(cards):
    s = build(cards, ["Galvanizing Sawship"])
    put(s, "Galvanizing Sawship")
    bear = creature(s, "p1", "Bear", pt="2/2")
    held_station(s, "Galvanizing Sawship", bear)
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=2)  # (4/4 before it resolves)
    answer(s)
    assert charge(s, "Galvanizing Sawship") == 4  # (the tapped creature's power now, not when it was tapped)
    check(s)


def test_a_tapped_creature_that_left_counts_as_it_last_existed(cards):
    s = build(cards, ["Galvanizing Sawship"])
    put(s, "Galvanizing Sawship")
    bear = creature(s, "p1", "Bear", pt="3/3")
    held_station(s, "Galvanizing Sawship", bear)
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "graveyard"})
    answer(s)
    assert charge(s, "Galvanizing Sawship") == 3  # (608.2h: its power as it last existed on the battlefield)
    check(s)


def test_negative_power_puts_no_counters(cards):
    s = build(cards, ["Galvanizing Sawship"])
    put(s, "Galvanizing Sawship")
    add_charge(s, "Galvanizing Sawship", 2)
    station(s, "Galvanizing Sawship", creature(s, "p1", "Wilting", pt="-2/4"))
    assert charge(s, "Galvanizing Sawship") == 2  # (nothing is put on or removed from it)
    check(s)


def test_the_seriema_gives_a_tapped_legend_indestructible(cards):
    s = build(cards, ["The Seriema"])
    put(s, "The Seriema")
    legend = creature(s, "p1", "Hero", pt="7/7", type_line="Token Legendary Creature — Human")
    assert "indestructible" not in ch_of_id(s, legend.id).keywords
    station(s, "The Seriema", legend)
    seriema = ch_of(s, "The Seriema")
    assert charge(s, "The Seriema") == 7 and seriema.pt == (5, 5) and "flying" in seriema.keywords and seriema.is_creature
    assert s.state.cards[legend.id].tapped and "indestructible" in ch_of_id(s, legend.id).keywords  # (other tapped legendary creatures)
    check(s)


def test_lumen_class_frigate_has_a_conditional_anthem_and_then_becomes_a_creature(cards):
    s = build(cards, ["Lumen-Class Frigate"])
    put(s, "Lumen-Class Frigate")
    bear = creature(s, "p1", "Bear", pt="2/2")
    assert ch_of_id(s, bear.id).pt == (2, 2)
    add_charge(s, "Lumen-Class Frigate", 2)
    assert ch_of_id(s, bear.id).pt == (3, 3) and not ch_of(s, "Lumen-Class Frigate").is_creature
    add_charge(s, "Lumen-Class Frigate", 10)
    frigate = ch_of(s, "Lumen-Class Frigate")
    assert frigate.pt == (3, 5) and {"flying", "lifelink"} <= frigate.keywords  # (it is no "other" creature for its own anthem)
    check(s)


def test_uthros_research_craft_draws_for_artifact_spells_at_three(cards):
    s = build(cards, ["Uthros Research Craft", "Sol Ring", "Sol Ring"])
    put(s, "Uthros Research Craft")
    rings = [c for c in s.state.cards.values() if c.name == "Sol Ring" and c.owner == "p1"]
    for ring in rings:
        act(s, "p1", type="move", card_ids=[ring.id], to={"zone": "hand"})
    add_charge(s, "Uthros Research Craft", 2)
    hand = len(s.state.zones["p1:hand"])
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=rings[0].id)
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand - 1 and charge(s, "Uthros Research Craft") == 2  # (below 3 it has no such ability)
    add_charge(s, "Uthros Research Craft", 1)
    hand = len(s.state.zones["p1:hand"])
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=rings[1].id)
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand  # (the spell left the hand, a card was drawn)
    assert charge(s, "Uthros Research Craft") == 4  # (the granted trigger also puts a charge counter on it)
    check(s)


def test_a_planet_land_gains_its_mana_ability_at_twelve(cards):
    s = build(cards, ["Evendo, Waking Haven"])
    put(s, "Evendo, Waking Haven")
    creature(s, "p1", "Bear", pt="2/2")
    creature(s, "p1", "Cub", pt="1/1")
    add_charge(s, "Evendo, Waking Haven", 11)
    assert all(a.index < 100 for a in ch_of(s, "Evendo, Waking Haven").abilities)
    add_charge(s, "Evendo, Waking Haven", 1)
    index = next(a.index for a in ch_of(s, "Evendo, Waking Haven").abilities if a.index >= 100)
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Evendo, Waking Haven").id, ability=index)
    assert mana_pool(s) == {"G": 2}  # ({G} paid, {G} for each of the two creatures)
    check(s)


def test_a_token_copy_of_a_station_permanent_has_the_abilities_but_not_the_counters(cards):
    s = build(cards, ["Adagia, Windswept Bastion", "Galvanizing Sawship"])
    put(s, "Adagia, Windswept Bastion")
    put(s, "Galvanizing Sawship")
    add_charge(s, "Adagia, Windswept Bastion", 12)
    add_charge(s, "Galvanizing Sawship", 5)
    assert ch_of(s, "Galvanizing Sawship").is_creature
    index = next(a.index for a in ch_of(s, "Adagia, Windswept Bastion").abilities if a.index >= 100)
    mana(s, W=1, C=3)
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Adagia, Windswept Bastion").id, ability=index,
        targets=[card_named(s, "Galvanizing Sawship").id])
    answer(s)
    copies = [c for c in s.state.cards.values() if c.name == "Galvanizing Sawship" and c.is_token]
    assert len(copies) == 1 and copies[0].counters.get("charge", 0) == 0  # (721 ruling: the counters aren't copied)
    copy = ch_of_id(s, copies[0].id)
    assert "Legendary" in copy.supertypes and not copy.is_creature and not copy.keywords and copy.power is None
    assert any(a.text.startswith("Tap another untapped creature") for a in copy.abilities)  # (its station symbols and station ability are)
    act(s, "p1", type="counter", card_ids=[copies[0].id], kind="charge", delta=3)
    assert ch_of_id(s, copies[0].id).is_creature and ch_of_id(s, copies[0].id).pt == (6, 5)  # (the copy's abilities follow its own counters)
    check(s)


def decide_all(s, picks=(), limit=40):
    """Resolve everything; each decision takes the next of ``picks`` (an option id or a label) when it is offered, else its first option."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        if d is not None:
            ids = [o.id for o in d.options]
            want = next((o.id for o in d.options for p in picks if p in (o.id, o.label)), None)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[want] if want else ids[: d.max_choices if d.kind == "choose_cards" else max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


@pytest.mark.parametrize("kind, plus, charge_after", [("+1/+1 counter", 1, 0), ("charge counter", 0, 2)])
def test_inspirit_puts_your_choice_of_counters_on_another_artifact(cards, kind, plus, charge_after):
    s = build(cards, ["Inspirit, Flagship Vessel", "Sol Ring"])
    put(s, "Inspirit, Flagship Vessel")
    ring = put(s, "Sol Ring")
    add_charge(s, "Inspirit, Flagship Vessel", 1)  # (1+: At the beginning of combat on your turn, put your choice of …)
    act(s, "p1", type="pass_priority")  # -> beginning of combat: the trigger
    decide_all(s, [ring.id, kind])
    now = s.state.cards[ring.id].counters
    assert (now.get("+1/+1", 0), now.get("charge", 0)) == (plus, charge_after)
    check(s)


def test_inspirit_has_nothing_to_trigger_without_a_charge_counter(cards):
    s = build(cards, ["Inspirit, Flagship Vessel", "Sol Ring"])
    put(s, "Inspirit, Flagship Vessel")
    ring = put(s, "Sol Ring")
    act(s, "p1", type="pass_priority")
    decide_all(s)
    assert not s.state.cards[ring.id].counters
    check(s)


def test_synthesizer_labship_animates_another_artifact_at_the_beginning_of_combat(cards):
    s = build(cards, ["Synthesizer Labship", "Sol Ring"])
    put(s, "Synthesizer Labship")
    ring = put(s, "Sol Ring")
    add_charge(s, "Synthesizer Labship", 2)
    act(s, "p1", type="pass_priority")  # -> beginning of combat
    decide_all(s, [ring.id])
    ch = ch_of_id(s, ring.id)
    assert ch.is_creature and ch.pt == (2, 2) and "flying" in ch.keywords
    assert not ch_of(s, "Synthesizer Labship").is_creature  # (2 charge counters is below 9)
    check(s)


def test_owen_grady_puts_your_choice_of_a_keyword_counter_on_a_target_dinosaur(cards):
    """The target form of "put your choice of": the Dinosaur is chosen as the ability is put on the stack, the kind as it resolves (608.2d)."""
    s = build(cards, ["Owen Grady, Raptor Trainer"])
    owen = put(s, "Owen Grady, Raptor Trainer")
    ready(s, "Owen Grady, Raptor Trainer")
    raptor = creature(s, "p1", "Raptor", pt="3/3", type_line="Token Creature — Dinosaur")
    index = next(a.index for a in ch_of(s, "Owen Grady, Raptor Trainer").abilities if a.text.startswith("{T}: Put your choice"))
    act(s, "p1", type="activate_ability", card_id=owen.id, ability=index, targets=[raptor.id])
    d = s.state.rules.decision
    assert [o.id for o in d.options] == ["reach", "menace", "trample", "haste"]
    pick(s, "trample")
    answer(s)
    assert s.state.cards[raptor.id].counters == {"trample": 1} and "trample" in ch_of_id(s, raptor.id).keywords
    check(s)


def test_larval_scoutlander_sacrifices_a_lander_for_two_basic_lands(cards):
    s = build(cards, ["Larval Scoutlander"])
    lander = creature(s, "p1", "Lander", pt="0/0", type_line="Token Artifact — Lander")
    lands = len([c for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name == "Forest"])
    scout = to_hand(s, "Larval Scoutlander")
    mana(s, G=3, C=3)
    act(s, "p1", type="cast_spell", card_id=scout.id)
    decide_all(s, ["pay", lander.id])
    assert lander.id not in s.state.zones["p1:battlefield"]  # (sacrificed to the "you may sacrifice a land or Lander")
    assert len([c for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name == "Forest"]) == lands + 2
    check(s)


def test_dawnsire_deals_100_damage_when_you_attack_at_ten_counters(cards):
    s = build(cards, ["Dawnsire, Sunstar Dreadnought"])
    put(s, "Dawnsire, Sunstar Dreadnought")
    bear = creature(s, "p1", "Bear", pt="2/2")
    wall = creature(s, "p2", "Wall", pt="0/4")
    ready(s, "Bear")
    add_charge(s, "Dawnsire, Sunstar Dreadnought", 9)
    act(s, "p1", type="pass_priority")  # -> declare attackers: 9 counters, nothing granted yet
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    decide_all(s)
    assert wall.id in s.state.zones["p2:battlefield"] and not s.state.zones.get("stack")  # (no trigger below ten)
    s2 = build(cards, ["Dawnsire, Sunstar Dreadnought"])
    put(s2, "Dawnsire, Sunstar Dreadnought")
    bear2 = creature(s2, "p1", "Bear", pt="2/2")
    wall2 = creature(s2, "p2", "Wall", pt="0/4")
    ready(s2, "Bear")
    add_charge(s2, "Dawnsire, Sunstar Dreadnought", 10)
    act(s2, "p1", type="pass_priority")
    act(s2, "p1", type="declare_attackers", attackers=[{"card_id": bear2.id, "target": "p2"}])
    decide_all(s2, [wall2.id])
    assert wall2.id not in s2.state.zones["p2:battlefield"]  # (100 damage to up to one target creature or planeswalker)
    check(s2)


def test_debris_field_crusher_pumps_itself_once_it_is_a_creature(cards):
    s = build(cards, ["Debris Field Crusher"])
    put(s, "Debris Field Crusher")
    add_charge(s, "Debris Field Crusher", 8)
    index = next(a.index for a in ch_of(s, "Debris Field Crusher").abilities if a.index >= 100 and a.text.startswith("{1}{R}"))
    mana(s, R=1, C=1)
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Debris Field Crusher").id, ability=index)
    answer(s)
    assert ch_of(s, "Debris Field Crusher").pt == (3, 5) and "flying" in ch_of(s, "Debris Field Crusher").keywords
    check(s)


def test_the_eternity_elevator_adds_mana_equal_to_its_counters_at_twenty(cards):
    s = build(cards, ["The Eternity Elevator"])
    put(s, "The Eternity Elevator")
    add_charge(s, "The Eternity Elevator", 21)
    index = next(a.index for a in ch_of(s, "The Eternity Elevator").abilities if a.index >= 100)
    act(s, "p1", type="activate_ability", card_id=card_named(s, "The Eternity Elevator").id, ability=index)
    d = s.state.rules.decision
    if d is not None:  # (the color: one choice for all of it, 605.3a)
        pick(s, d.options[0].id)
    pool = mana_pool(s)
    assert sum(pool.values()) == 21 and len([k for k, v in pool.items() if v]) == 1
    check(s)
