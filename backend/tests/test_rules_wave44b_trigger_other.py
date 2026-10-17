"""Wave 44B: commanders whose only gap was one trigger line (CR 2026-09-25, real Oracle text, tests/fixtures/wave44b_cards.json from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 120.1, 510.2: Zagras, "Whenever a creature you control deals combat damage to a planeswalker, destroy that planeswalker." - the planeswalker dealt damage.
* 508.1, 508.5, 118.12a: Merry ("you attack with Merry and another legendary creature"), Kazuul ("if you're the defending player" - you, a planeswalker you control or
  a battle you protect; the attacker's controller may pay {3} or you get the Ogre).
* 608.2c, 614: Selvala (the new creature's power against each other creature as the ability resolves, its controller draws) and Rayne (the "additional" draw is a
  second optional draw that happens only if Rayne is enchanted as the ability resolves, ruling of 2004-10-04).
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
from tests.test_rules_conditionals import settle
from tests.test_rules_wave38a_trailing_ifs import hand, table
from tests.wave9c_kit import card_named, check, mana, pt, put
from tests.wave36a_kit import attack_as, block, ready, to_turn_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave44b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w44b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
COMMANDERS = ["Zagras, Thief of Heartbeats", "Merry, Esquire of Rohan", "Kazuul, Tyrant of the Cliffs", "Selvala, Heart of the Wilds", "Rayne, Academy Chancellor",
              "Amalia Benavides Aguirre", "Jenson Carthalion, Druid Exile", "Michelangelo, Improviser", "Danitha, Sword of Hope", "Rose Noble",
              "Tameshi, Reality Architect", "The Beast, Deathless Prince", "Ultron the Annihilator", "Kolodin, Triumph Caster",
              "Mirko Vosk, Mind Drinker", "Gornog, the Red Reaper", "Whirlwind, Killer Cyclone", "Vraska, the Cutting Glare", "Splinter, Aging Champion",
              "April O'Neil, Hacktivist", "Daredevil, Man Without Fear", "Shizuko, Caller of Autumn", "Kassandra, Eagle Bearer", "Kynaios and Tiro of Meletis",
              "Namor the Sub-Mariner"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", COMMANDERS)
def test_the_commanders_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def zone(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].zone


# -- Zagras ------------------------------------------------------------------------------------------------------------------------------------
def zagras_table(cards, target):
    """Alice's hasty Zagras attacks ``target`` ("p2" or Bob's Gideon Jura, loyalty 6) on her first turn."""
    s = table(cards, ["Zagras, Thief of Heartbeats"], ["Gideon Jura"])
    zagras, gideon = put(s, "Zagras, Thief of Heartbeats"), put(s, "Gideon Jura", "p2")
    act(s, "p2", type="counter", card_ids=[gideon.id], kind="loyalty", delta=6)
    attack_as(s, "p1", [zagras], gideon.id if target == "gideon" else target)
    settle(s)
    return s


def test_zagras_destroys_the_planeswalker_it_dealt_combat_damage_to(cards):
    s = zagras_table(cards, "gideon")
    for _ in range(12):
        if zone(s, "Gideon Jura", "p2") != "p2:battlefield":
            break
        act(s, s.state.rules.priority, type="pass_priority")
        settle(s)
    assert zone(s, "Gideon Jura", "p2") == "p2:graveyard"  # (4 damage left it at 2 loyalty: only the trigger destroyed it)
    check(s)


def test_zagras_does_nothing_for_damage_to_a_player(cards):
    s = zagras_table(cards, "p2")
    for _ in range(12):
        act(s, s.state.rules.priority, type="pass_priority")
        settle(s)
        if s.state.turn.phase not in ("declare_attackers", "declare_blockers", "combat_damage", "first_strike_damage"):
            break
    assert s.state.players["p2"].life == 40 - 4
    assert zone(s, "Gideon Jura", "p2") == "p2:battlefield"
    check(s)


# -- Merry ---------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("attackers", "draws"), [(("Merry, Esquire of Rohan", "Isamaru, Hound of Konda"), 1), (("Merry, Esquire of Rohan", "Grizzly Bears"), 0),
                                                  (("Merry, Esquire of Rohan",), 0), (("Isamaru, Hound of Konda", "Grizzly Bears"), 0)])
def test_merry_draws_when_she_attacks_with_another_legendary_creature(cards, attackers, draws):
    s = table(cards, ["Merry, Esquire of Rohan", "Isamaru, Hound of Konda", "Grizzly Bears"])
    for n in ("Merry, Esquire of Rohan", "Isamaru, Hound of Konda", "Grizzly Bears"):
        put(s, n)
    ready(s, "Merry, Esquire of Rohan", "Isamaru, Hound of Konda", "Grizzly Bears")
    before = hand(s)
    attack_as(s, "p1", [card_named(s, n) for n in attackers], "p2")
    settle(s)
    assert hand(s) == before + draws
    check(s)


# -- Kazuul --------------------------------------------------------------------------------------------------------------------------------------
def ogres(s):
    return [c for c in s.state.cards.values() if c.name == "Ogre" and c.zone == "p1:battlefield"]


def kazuul_attack(cards, defender, players=2, lands=3):
    """Bob's Grizzly Bears (and ``lands`` Islands) attack ``defender`` ("p1" Alice, with Kazuul, or "p3" Carol); the table stops at the choice that comes up."""
    s = table(cards, ["Kazuul, Tyrant of the Cliffs"], ["Grizzly Bears"], players)
    put(s, "Kazuul, Tyrant of the Cliffs")
    put(s, "Grizzly Bears", "p2")
    ready(s, "Grizzly Bears", pid="p2")
    for _ in range(lands):
        act(s, "p2", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2" and c.zone == "p2:library")],
            to={"player": "p2", "zone": "battlefield"})
    to_turn_of(s, "p2")
    attack_as(s, "p2", [card_named(s, "Grizzly Bears", "p2")], defender)
    for _ in range(10):  # (the trigger resolves, then Bob is asked)
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    return s


def test_kazuul_makes_an_ogre_unless_the_attackers_controller_pays(cards):
    s = kazuul_attack(cards, "p1")
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and sorted(o.id for o in d.options) == ["decline", "pay"], d
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["decline"])
    settle(s)
    assert len(ogres(s)) == 1
    check(s)


def test_kazuul_makes_nothing_when_the_attacker_pays(cards):
    s = kazuul_attack(cards, "p1")
    d = s.state.rules.decision
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["pay"])
    settle(s)
    assert ogres(s) == []
    assert sum(1 for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:battlefield" and c.tapped) == 3
    check(s)


def test_kazuul_does_not_trigger_for_creatures_attacking_another_player(cards):
    s = kazuul_attack(cards, "p3", players=3)
    assert not s.state.zones.get("stack") and (s.state.rules.decision is None or s.state.rules.decision.kind != "optional_payment")
    settle(s)
    assert ogres(s) == []
    check(s)


# -- Selvala -------------------------------------------------------------------------------------------------------------------------------------
def library(s, pid):
    return len(s.state.zones[f"{pid}:library"])


def cast_creature(s, pid, name):
    """``pid`` casts the creature in their own first main phase (a card put onto the battlefield by hand triggers nothing); the cards each player drew."""
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    before = {p: library(s, p) for p in ("p1", "p2")}
    mana(s, pid, R=1, G=1, C=3)
    act(s, pid, type="cast_spell", card_id=c.id)
    settle(s)
    return {p: before[p] - library(s, p) for p in ("p1", "p2")}


@pytest.mark.parametrize(("who", "creature", "draws"), [("p1", "Hill Giant", "p1"), ("p2", "Hill Giant", "p2"), ("p1", "Grizzly Bears", None), ("p2", "Grizzly Bears", None)])
def test_selvala_lets_the_controller_of_a_creature_with_the_greatest_power_draw(cards, who, creature, draws):
    """Selvala is a 2/3: a 3/3 is strictly greater than every other creature's power, so its controller (not Selvala's) may draw; a 2/2 ties with her
    (ruling of 2016-08-23: the same or higher power, no one draws)."""
    s = table(cards, ["Selvala, Heart of the Wilds", "Hill Giant", "Grizzly Bears"], ["Hill Giant", "Grizzly Bears"])
    put(s, "Selvala, Heart of the Wilds")
    if who == "p2":
        to_turn_of(s, "p2")
    assert cast_creature(s, who, creature) == {p: int(p == draws) for p in ("p1", "p2")}
    check(s)


def test_selvala_compares_with_a_bigger_creature_on_the_battlefield(cards):
    s = table(cards, ["Selvala, Heart of the Wilds", "Hill Giant"], ["Hill Giant"])
    put(s, "Selvala, Heart of the Wilds")
    put(s, "Hill Giant", "p2")
    assert cast_creature(s, "p1", "Hill Giant") == {"p1": 0, "p2": 0}  # (a 3/3 ties with Bob's 3/3)
    check(s)


# -- Rayne ---------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("enchanted", "bolter", "draws"), [(False, "p2", 1), (True, "p2", 2), (True, "p1", 0)])
def test_rayne_draws_a_card_and_another_one_when_enchanted(cards, enchanted, bolter, draws):
    """Rayne: Bob's Lightning Bolt targets Alice's Grizzly Bears: she may draw a card, and (ruling of 2004-10-04: checked as the ability resolves) one more if
    Rayne is enchanted. Her own Bolt on her own creature is no opponent's spell."""
    s = table(cards, ["Rayne, Academy Chancellor", "Grizzly Bears", "Pacifism", "Lightning Bolt"], ["Lightning Bolt"])
    put(s, "Rayne, Academy Chancellor")
    bears = put(s, "Grizzly Bears")
    if enchanted:
        pacifism = card_named(s, "Pacifism")
        act(s, "p1", type="move", card_ids=[pacifism.id], to={"zone": "hand"})
        mana(s, "p1", W=1, C=1)
        act(s, "p1", type="cast_spell", card_id=pacifism.id, targets=[card_named(s, "Rayne, Academy Chancellor").id])
        settle(s)
    if bolter == "p2":
        to_turn_of(s, "p2")
    bolt = card_named(s, "Lightning Bolt", bolter)
    act(s, bolter, type="move", card_ids=[bolt.id], to={"zone": "hand"})
    before = library(s, "p1")
    mana(s, bolter, R=1)
    act(s, bolter, type="cast_spell", card_id=bolt.id, targets=[bears.id])
    settle(s)
    assert before - library(s, "p1") == draws
    check(s)


# -- Amalia Benavides Aguirre ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("start", "destroyed"), [(19, True), (17, False)])
def test_amalia_destroys_the_other_creatures_when_her_power_is_exactly_20_after_the_explore(cards, start, destroyed):
    """Amalia: "Whenever you gain life, ~ explores. Then destroy all other creatures if its power is exactly 20." The explore's +1/+1 counter (a nonland card on top)
    comes first (608.2c): 19 + 1 = 20 destroys, 17 + 1 = 18 doesn't."""
    s = table(cards, ["Hill Giant", "Heroes' Reunion", "Amalia Benavides Aguirre", "Grizzly Bears"], ["Grizzly Bears"])
    amalia = put(s, "Amalia Benavides Aguirre")
    put(s, "Grizzly Bears")
    base = pt(s, "Amalia Benavides Aguirre")[0]
    act(s, "p1", type="counter", card_ids=[amalia.id], kind="+1/+1", delta=start - base)
    assert pt(s, "Amalia Benavides Aguirre")[0] == start
    reunion = card_named(s, "Heroes' Reunion")
    act(s, "p1", type="move", card_ids=[reunion.id], to={"zone": "hand"})
    mana(s, "p1", G=1, W=1)
    act(s, "p1", type="cast_spell", card_id=reunion.id, targets=["p1"])
    settle(s)
    assert pt(s, "Amalia Benavides Aguirre")[0] == start + 1
    assert zone(s, "Grizzly Bears") == ("p1:graveyard" if destroyed else "p1:battlefield")
    assert zone(s, "Amalia Benavides Aguirre") == "p1:battlefield"
    check(s)


# -- Jenson Carthalion, Druid Exile ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("spell", "angels"), [("Transguild Courier", 1), ("Zhur-Taa Swine", 0)])
def test_jenson_makes_an_angel_for_an_all_colors_spell(cards, spell, angels):
    s = table(cards, ["Jenson Carthalion, Druid Exile", "Transguild Courier", "Zhur-Taa Swine"])
    put(s, "Jenson Carthalion, Druid Exile")
    c = card_named(s, spell)
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, "p1", R=1, G=1, C=4)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert sum(1 for x in s.state.cards.values() if x.name == "Angel" and x.zone == "p1:battlefield") == angels
    check(s)


# -- Michelangelo, Improviser ----------------------------------------------------------------------------------------------------------------------
def test_michelangelo_puts_a_creature_and_a_land_from_hand_onto_the_battlefield(cards):
    """"You may put a creature card and/or a land card from your hand onto the battlefield" is up to one of each (a land put this way isn't played, ruling of
    2026-01-27)."""
    s = table(cards, ["Michelangelo, Improviser", "Grizzly Bears"])
    mike = put(s, "Michelangelo, Improviser")
    bears, forest = card_named(s, "Grizzly Bears"), next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    for c in (bears, forest):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    ready(s, "Michelangelo, Improviser")
    attack_as(s, "p1", [mike], "p2")
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack") or s.state.turn.phase in ("declare_attackers", "declare_blockers", "combat_damage", "first_strike_damage"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[forest.id].zone == "p1:battlefield"
    check(s)


# -- Danitha, Sword of Hope / Rose Noble -------------------------------------------------------------------------------------------------------------
def cast_from_hand(s, name, pid="p1", targets=None, **m):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, pid, **m)
    before = library(s, "p1")
    act(s, pid, type="cast_spell", card_id=c.id, **({"targets": targets} if targets else {}))
    settle(s)
    return before - library(s, "p1")


def test_danitha_draws_for_an_equipment_spell_once_each_turn(cards):
    s = table(cards, ["Danitha, Sword of Hope", "Bonesplitter", "Short Sword"])
    put(s, "Danitha, Sword of Hope")
    assert cast_from_hand(s, "Bonesplitter", C=1) == 1
    assert cast_from_hand(s, "Short Sword", C=1) == 0  # (this ability triggers only once each turn)
    check(s)


@pytest.mark.parametrize(("victim", "caster_draws"), [("p1", 1), ("p2", 0)])
def test_danitha_draws_for_a_spell_that_targets_a_creature_you_control(cards, victim, caster_draws):
    s = table(cards, ["Danitha, Sword of Hope", "Giant Growth", "Grizzly Bears"], ["Grizzly Bears"])
    put(s, "Danitha, Sword of Hope")
    bears = put(s, "Grizzly Bears", victim)
    assert cast_from_hand(s, "Giant Growth", targets=[bears.id], G=1) == caster_draws
    check(s)


@pytest.mark.parametrize(("spell", "draws"), [("Night Nurse, Healer of Heroes", 1), ("K-9, Mark I", 1), ("Grizzly Bears", 0)])
def test_rose_noble_draws_for_a_doctor_spell_or_a_creature_spell_with_doctors_companion(cards, spell, draws):
    s = table(cards, ["Rose Noble", "Night Nurse, Healer of Heroes", "K-9, Mark I", "Grizzly Bears"])
    put(s, "Rose Noble")
    assert cast_from_hand(s, spell, W=2, U=1, G=2) == draws
    check(s)


# -- Tameshi, Reality Architect -----------------------------------------------------------------------------------------------------------------------
def test_tameshi_draws_once_each_turn_for_noncreature_permanents_returned_to_hand(cards):
    """Tameshi: "Whenever one or more noncreature permanents are returned to hand, draw a card. This ability triggers only once each turn." A creature bounced
    doesn't count, and nothing returned from a graveyard does (ruling of 2022-02-18: from the battlefield)."""
    s = table(cards, ["Tameshi, Reality Architect", "Bonesplitter", "Short Sword", "Grizzly Bears", "Boomerang"])
    put(s, "Tameshi, Reality Architect")
    ring, sword, bears = put(s, "Bonesplitter"), put(s, "Short Sword"), put(s, "Grizzly Bears")
    assert cast_from_hand(s, "Boomerang", targets=[bears.id], U=2) == 0  # (a creature)
    assert cast_from_hand(s, "Boomerang", targets=[ring.id], U=2) == 1  # (the Boomerang itself is a spell, not a permanent)
    assert zone(s, "Bonesplitter") == "p1:hand"
    assert cast_from_hand(s, "Boomerang", targets=[sword.id], U=2) == 0  # (only once each turn)
    check(s)


# -- The Beast, Deathless Prince ----------------------------------------------------------------------------------------------------------------------
def test_the_beast_untaps_and_draws_when_a_creature_deals_combat_damage_to_its_owner(cards):
    """Alice steals Bob's Grizzly Bears with Threaten and hits Bob (its owner): The Beast triggers; her own Bears dealing damage to Bob doesn't."""
    s = table(cards, ["The Beast, Deathless Prince", "Threaten", "Grizzly Bears"], ["Grizzly Bears"])
    put(s, "The Beast, Deathless Prince")
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    ready(s, "Grizzly Bears")
    cast_from_hand(s, "Threaten", targets=[theirs.id], R=1, C=2)
    assert s.state.cards[theirs.id].controller == "p1"
    before = library(s, "p1")
    attack_as(s, "p1", [s.state.cards[mine.id], s.state.cards[theirs.id]], "p2")
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack") or s.state.turn.phase in ("declare_attackers", "declare_blockers", "combat_damage", "first_strike_damage"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert before - library(s, "p1") == 1  # (one trigger: only Bob's Bears hit its owner)
    check(s)


# -- Ultron the Annihilator -------------------------------------------------------------------------------------------------------------------------
def ultron_table(cards):
    s = table(cards, ["Sol Ring", "Ultron the Annihilator", "Shatter", "Mental Note"], ["Sol Ring"])  # (Alice's Sol Ring is the top card of her library)
    put(s, "Ultron the Annihilator")
    return s


def test_ultron_drains_for_another_artifact_that_dies(cards):
    s = ultron_table(cards)
    ring = put(s, "Sol Ring")
    before = s.state.players["p2"].life
    cast_from_hand(s, "Shatter", targets=[ring.id], R=1, C=1)
    assert zone(s, "Sol Ring") == "p1:graveyard" and s.state.players["p2"].life == before - 1
    check(s)


def test_ultron_drains_for_an_artifact_card_milled(cards):
    s = ultron_table(cards)
    before = s.state.players["p2"].life
    cast_from_hand(s, "Mental Note", U=1)  # (mills Sol Ring and the card under it: an artifact card put into a graveyard from a library)
    assert zone(s, "Sol Ring") == "p1:graveyard" and s.state.players["p2"].life == before - 1
    check(s)


def test_ultron_ignores_an_opponents_artifact(cards):
    s = ultron_table(cards)
    ring = put(s, "Sol Ring", "p2")
    before = s.state.players["p2"].life
    cast_from_hand(s, "Shatter", targets=[ring.id], R=1, C=1)
    assert zone(s, "Sol Ring", "p2") == "p2:graveyard" and s.state.players["p2"].life == before
    check(s)


# -- Kolodin, Triumph Caster -------------------------------------------------------------------------------------------------------------------------
def test_kolodin_saddles_a_mount_as_it_enters(cards):
    """Kolodin: "Whenever a Mount you control enters, it becomes saddled until end of turn" (702.171b), and Mounts have haste, so Bulwark Ox attacks saddled
    the turn it is cast and its "attacks while saddled" trigger puts the counter. A creature that isn't a Mount is no such entry."""
    from app.rules import crew_saddle
    from app.rules.plan import Plan

    s = table(cards, ["Kolodin, Triumph Caster", "Bulwark Ox", "Grizzly Bears"])
    put(s, "Kolodin, Triumph Caster")
    cast_from_hand(s, "Grizzly Bears", W=1, G=2)
    ox = card_named(s, "Bulwark Ox")
    cast_from_hand(s, "Bulwark Ox", W=2)
    plan = Plan(s.state, "p1", s.cards, None)
    assert crew_saddle.is_saddled(plan, s.state.cards[ox.id]) and not crew_saddle.is_saddled(plan, s.state.cards[card_named(s, "Grizzly Bears").id])
    attack_as(s, "p1", [s.state.cards[ox.id]], "p2")
    settle(s)
    assert sum(c.counters.get("+1/+1", 0) for c in s.state.cards.values() if c.zone == "p1:battlefield") == 1
    check(s)


# -- Mirko Vosk, Mind Drinker ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("lands_left", "milled"), [(20, 6), (3, 5)])
def test_mirko_vosk_makes_the_player_reveal_until_four_lands_and_mill_them(cards, lands_left, milled):
    """Bob's library is a Bears and a Hill Giant over Islands: revealing until four land cards is six cards; with only three lands (ruling of 2013-04-15) all of
    his library is revealed and put into his graveyard."""
    s = table(cards, ["Mirko Vosk, Mind Drinker"], ["Grizzly Bears", "Hill Giant"])
    mirko = put(s, "Mirko Vosk, Mind Drinker")
    ready(s, "Mirko Vosk, Mind Drinker")
    islands = [c for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library"]
    for c in islands[: len(islands) - lands_left]:
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "exile"})
    in_library = len(s.state.zones["p2:library"])
    attack_as(s, "p1", [mirko], "p2")
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack") or s.state.turn.phase in ("declare_attackers", "declare_blockers", "combat_damage", "first_strike_damage"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert len(s.state.zones["p2:graveyard"]) == milled and len(s.state.zones["p2:library"]) == in_library - milled
    check(s)


# -- Soul Charmer (shares Kazuul's "unless that creature's controller pays") -------------------------------------------------------------------------
@pytest.mark.parametrize(("answer", "gained"), [("decline", 2), ("pay", 0)])
def test_soul_charmer_gains_life_unless_the_blockers_controller_pays(cards, answer, gained):
    s = table(cards, ["Soul Charmer"], ["Grizzly Bears", "Island"])
    charmer, bears = put(s, "Soul Charmer"), put(s, "Grizzly Bears", "p2")
    ready(s, "Soul Charmer")
    for _ in range(2):
        act(s, "p2", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2" and c.zone == "p2:library")],
            to={"player": "p2", "zone": "battlefield"})
    life_before = s.state.players["p1"].life
    attack_as(s, "p1", [charmer], "p2")
    block(s, "p2", (bears, charmer))
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p2" and sorted(o.id for o in d.options) == ["decline", "pay"]
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[answer])
    settle(s)
    assert s.state.players["p1"].life == life_before + gained
    check(s)


# -- Gornog, the Red Reaper / Whirlwind, Killer Cyclone ------------------------------------------------------------------------------------------------
def subtypes(s, name, pid):
    from app.rules.plan import Plan

    return set(Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id]).subtypes)


def test_gornog_turns_a_creature_of_the_player_attacked_into_a_coward(cards):
    """Gornog: "Whenever one or more Warriors you control attack a player, target creature that player controls becomes a Coward." In a three-player game it
    triggers for Bob (the player attacked, 508.3e) and can only choose Bob's creature, not Carol's; the type change has no duration (ruling of 2024-11-08)."""
    s = table(cards, ["Gornog, the Red Reaper", "Grizzly Bears"], ["Grizzly Bears", "Hill Giant"], players=3)
    gornog = put(s, "Gornog, the Red Reaper")
    put(s, "Grizzly Bears", "p2")
    put(s, "Hill Giant", "p3")
    attack_as(s, "p1", [gornog], "p2")
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind != "declare_blockers":
            assert all(s.state.cards[o.card_id].controller == "p2" for o in d.options if getattr(o, "card_id", None) in s.state.cards), d
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert subtypes(s, "Grizzly Bears", "p2") == {"Coward"} and subtypes(s, "Hill Giant", "p3") == {"Giant"}
    check(s)


def test_gornog_does_nothing_when_no_warrior_attacks(cards):
    s = table(cards, ["Gornog, the Red Reaper", "Grizzly Bears"], ["Grizzly Bears"])
    put(s, "Gornog, the Red Reaper")
    bears, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    ready(s, "Grizzly Bears")
    attack_as(s, "p1", [s.state.cards[bears.id]], "p2")
    assert not s.state.zones.get("stack") and s.state.rules.decision is None or s.state.rules.decision.kind == "declare_blockers"
    assert subtypes(s, "Grizzly Bears", "p2") == {"Bear"} and s.state.cards[theirs.id].zone == "p2:battlefield"
    check(s)


@pytest.mark.parametrize("entered_this_turn", [True, False])
def test_whirlwind_stops_a_creature_blocking_only_for_creatures_that_entered_this_turn(cards, entered_this_turn):
    """Whirlwind: "Whenever one or more creatures you control that entered this turn attack a player, target creature that player controls can't block this turn."
    Cast this turn (haste) it triggers and Bob's Bears can't block; one that entered earlier doesn't."""
    from app.game.errors import ActionError
    from tests.wave36a_kit import next_own_turn

    s = table(cards, ["Whirlwind, Killer Cyclone"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    if entered_this_turn:
        cast_from_hand(s, "Whirlwind, Killer Cyclone", R=1, C=2)
    else:
        put(s, "Whirlwind, Killer Cyclone")
        next_own_turn(s)
    whirlwind = s.state.cards[card_named(s, "Whirlwind, Killer Cyclone").id]
    attack_as(s, "p1", [whirlwind], "p2")
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind != "declare_blockers":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    if entered_this_turn:
        with pytest.raises(ActionError, match="can't block"):
            block(s, "p2", (bears, whirlwind))
    else:
        block(s, "p2", (bears, whirlwind))
    check(s)


# -- Vraska, the Cutting Glare / Splinter, Aging Champion ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("lands", "destroyed"), [(6, True), (5, False)])
def test_vraska_destroys_a_permanent_and_its_controller_creates_a_treasure(cards, lands, destroyed):
    """Vraska: "if you control six or more lands, destroy target permanent an opponent controls. They create a Treasure token." - "they" are the player who
    controlled it (Bob), not Alice; with five lands it doesn't trigger (603.4)."""
    s = table(cards, ["Vraska, the Cutting Glare"], ["Grizzly Bears"])
    put(s, "Grizzly Bears", "p2")
    for _ in range(lands):
        act(s, "p1", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")],
            to={"player": "p1", "zone": "battlefield"})
    cast_from_hand(s, "Vraska, the Cutting Glare", B=2, G=1)
    treasures = {p: sum(1 for c in s.state.cards.values() if c.name == "Treasure" and c.controller == p and c.zone.endswith(":battlefield")) for p in ("p1", "p2")}
    assert zone(s, "Grizzly Bears", "p2") == ("p2:graveyard" if destroyed else "p2:battlefield")
    assert treasures == {"p1": 0, "p2": int(destroyed)}
    check(s)


def test_splinter_lets_you_and_another_player_draw_when_it_leaves(cards):
    s = table(cards, ["Splinter, Aging Champion", "Lightning Bolt"], ["Grizzly Bears"])
    splinter = put(s, "Splinter, Aging Champion")
    bolt = card_named(s, "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "hand"})
    before = {p: library(s, p) for p in ("p1", "p2")}
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[splinter.id])
    settle(s)
    assert zone(s, "Splinter, Aging Champion") == "p1:graveyard"
    assert {p: before[p] - library(s, p) for p in ("p1", "p2")} == {"p1": 1, "p2": 1}
    check(s)


# -- April O'Neil, Hacktivist --------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("spells", "draws"), [((), 0), (("Grizzly Bears",), 1), (("Grizzly Bears", "Lightning Bolt", "Giant Growth"), 2)])
def test_april_draws_for_each_card_type_among_the_spells_cast_this_turn(cards, spells, draws):
    """April: "At the beginning of your end step, draw a card for each card type among spells you've cast this turn": a creature and two instants are two types."""
    from tests.wave36a_kit import finish_turn

    s = table(cards, ["April O'Neil, Hacktivist", "Grizzly Bears", "Lightning Bolt", "Giant Growth"])
    put(s, "April O'Neil, Hacktivist")
    for name in spells:
        c = card_named(s, name)
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
        mana(s, "p1", R=1, G=1, C=1)
        targets = ["p2"] if name == "Lightning Bolt" else [card_named(s, "Grizzly Bears").id] if name == "Giant Growth" else None
        act(s, "p1", type="cast_spell", card_id=c.id, **({"targets": targets} if targets else {}))
        settle(s)
    before = library(s, "p1")
    finish_turn(s)
    assert before - library(s, "p1") == draws
    check(s)


# -- Daredevil, Man Without Fear ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("top", "bonus"), [("Night Nurse, Healer of Heroes", (2, 1)), ("Grizzly Bears", (0, 0))])
def test_daredevil_exiles_the_top_card_and_gets_a_bonus_for_a_hero(cards, top, bonus):
    """Daredevil: "Whenever you attack, you may exile the top card of your library. If that card is a Hero card, Daredevil gets +2/+1 until end of turn. You may play
    that card this turn." The exiled card is the top one either way."""
    s = table(cards, [top, "Daredevil, Man Without Fear"])
    daredevil = put(s, "Daredevil, Man Without Fear")
    ready(s, "Daredevil, Man Without Fear")
    power, toughness = pt(s, "Daredevil, Man Without Fear")
    attack_as(s, "p1", [daredevil], "p2")
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind != "declare_blockers":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert zone(s, top) == "p1:exile"
    assert pt(s, "Daredevil, Man Without Fear") == (power + bonus[0], toughness + bonus[1])
    check(s)


# -- Shizuko, Caller of Autumn -----------------------------------------------------------------------------------------------------------------------
def test_shizuko_gives_each_player_mana_that_they_keep_through_the_turn(cards):
    """Shizuko: "At the beginning of each player's upkeep, that player adds {G}{G}{G}. Until end of turn, they don't lose this mana as steps and phases end." Bob's
    upkeep: the mana is Bob's, and he still has it in his main phase (not Alice's pool, not emptied)."""
    s = table(cards, ["Shizuko, Caller of Autumn"])
    put(s, "Shizuko, Caller of Autumn")
    to_turn_of(s, "p2")
    assert s.state.players["p2"].mana.get("G", 0) == 3 and s.state.players["p1"].mana.get("G", 0) == 0
    check(s)


# -- Kassandra, Eagle Bearer -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("equipment", "draws"), [("Shadowspear", 1), ("Bonesplitter", 0), (None, 0)])
def test_kassandra_draws_when_a_creature_with_a_legendary_equipment_deals_combat_damage_to_a_player(cards, equipment, draws):
    from app.rules.plan import Plan

    s = table(cards, ["Kassandra, Eagle Bearer", "Shadowspear", "Bonesplitter"])
    kassandra = put(s, "Kassandra, Eagle Bearer")
    if equipment:
        gear = put(s, equipment)
        ability = next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[gear.id]).abilities if a.text.startswith("Equip "))
        mana(s, "p1", C=2)
        act(s, "p1", type="activate_ability", card_id=gear.id, ability=ability, targets=[kassandra.id])
        settle(s)
        assert s.state.cards[gear.id].attached_to == kassandra.id
    before = library(s, "p1")
    attack_as(s, "p1", [s.state.cards[kassandra.id]], "p2")
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack") or s.state.turn.phase in ("declare_attackers", "declare_blockers", "combat_damage", "first_strike_damage"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert before - library(s, "p1") == draws
    check(s)


# -- Kynaios and Tiro of Meletis ---------------------------------------------------------------------------------------------------------------------
def test_kynaios_and_tiro_opponents_who_put_no_land_draw_a_card(cards):
    """Kynaios and Tiro: "At the beginning of your end step, draw a card. Each player may put a land card from their hand onto the battlefield, then each
    opponent who didn't draws a card." Alice and Bob put a land, Carol (none in hand) doesn't: only Carol draws (and Alice's own draw)."""
    s = table(cards, ["Kynaios and Tiro of Meletis"], [], players=3)
    put(s, "Kynaios and Tiro of Meletis")
    for pid, land in (("p1", "Forest"), ("p2", "Island")):
        act(s, pid, type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == land and c.owner == pid and c.zone == f"{pid}:library")],
            to={"zone": "hand"})
    before = {p: library(s, p) for p in ("p1", "p2", "p3")}
    asked = []
    for _ in range(60):
        d = s.state.rules.decision
        if s.state.turn.number > 1:
            break
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None and d.kind == "choose_cards":
            asked.append(d.player)
            hand_lands = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=hand_lands[:1] if d.player in ("p1", "p2") else [])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert sorted(asked) == ["p1", "p2", "p3"]
    assert {p: before[p] - library(s, p) for p in ("p1", "p2", "p3")} == {"p1": 1, "p2": 0, "p3": 1}
    on_field = {p: sum(1 for c in s.state.cards.values() if c.zone == f"{p}:battlefield" and c.name in ("Forest", "Island", "Swamp")) for p in ("p1", "p2", "p3")}
    assert on_field == {"p1": 1, "p2": 1, "p3": 0}
    check(s)


# -- Namor the Sub-Mariner ---------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("spell", "extra", "tokens"), [("Mental Note", {}, 1), ("Mind Spring", {"x_value": 1}, 2), ("Lightning Bolt", {"targets": ["p2"]}, 0)])
def test_namor_makes_a_merfolk_for_each_blue_mana_symbol_in_the_cost_of_a_noncreature_spell(cards, spell, extra, tokens):
    """Namor: "Whenever you cast a noncreature spell with one or more blue mana symbols in its mana cost, create that many 1/1 blue Merfolk creature tokens."
    {U} is one, {X}{U}{U} two, and a red spell with none doesn't trigger."""
    s = table(cards, ["Namor the Sub-Mariner", "Mental Note", "Mind Spring", "Lightning Bolt"])
    put(s, "Namor the Sub-Mariner")
    c = card_named(s, spell)
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, "p1", U=3, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id, **extra)
    settle(s)
    assert sum(1 for x in s.state.cards.values() if x.name == "Merfolk" and x.is_token and x.zone == "p1:battlefield") == tokens
    check(s)
