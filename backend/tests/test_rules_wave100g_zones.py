"""Wave 100G: graveyard returns, chapters and reveal lines read by exact Oracle wording (app/rules/zones100g.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

# Real Oracle data (tests/fixtures/wave100g_cards.json, copied from the card database) plus plain probe cards.
REAL = json.loads((Path(__file__).parent / "fixtures" / "wave100g_cards.json").read_text())
EXTRA = [
    real("Probe Pirate Vampire", "{1}{B}", 2, "Creature — Human Pirate Vampire", "", ("2", "2"), "B"),
    real("Probe Merfolk", "{U}", 1, "Creature — Merfolk", "", ("1", "1"), "U"),
    real("Probe Big", "{4}{G}", 5, "Creature — Beast", "", ("5", "5"), "G"),
    real("Probe Five", "{4}{G}", 5, "Creature — Beast", "", ("3", "3"), "G"),
    real("Probe Nightstalker", "{2}{B}", 3, "Creature — Nightstalker", "", ("2", "2"), "B"),
    real("Probe Doctor", "{2}{W}", 3, "Legendary Creature — Time Lord Doctor", "", ("2", "2"), "W"),
    real("Stone Rain", "{2}{R}", 3, "Sorcery", "Destroy target land.", None, "R"),
    real("Probe Companion", "{1}{W}", 2, "Creature — Human", "Doctor's companion", ("1", "1"), "W"),
    real("Probe Wall", "{1}{W}", 2, "Creature — Wall", "Defender", ("0", "4"), "W"),
    real("Probe Tall", "{1}{W}", 2, "Creature — Elf", "", ("1", "3"), "W"),
    real("Probe Lord", "{2}{U}", 3, "Creature — Time Lord", "", ("2", "2"), "U"),
    real("Probe WU", "{W}{U}", 2, "Creature — Human", "", ("2", "2"), "WU"),
    real("Probe Twin", "{4}{G}", 5, "Creature — Beast", "", ("5", "5"), "G"),
    real("Probe Huge", "{6}{G}", 7, "Creature — Beast", "", ("7", "7"), "G"),
    real("Probe Gate", "", 0, "Land — Gate", ""),
    real("Probe Snow Lair", "", 0, "Snow Land — Lair", ""),
    real("Probe Shatter", "{1}{R}", 2, "Instant", "Destroy target artifact.", None, "R"),
    real("Probe Phyrexian", "{1}{W}", 2, "Creature — Phyrexian Horror", "", ("2", "2"), "W"),
    real("Probe Relic", "{5}", 5, "Artifact", ""),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    real_cards = [card(c["name"], number=f"100G-{i}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(REAL)]
    build_database([*fixture_cards(), *EXTRA, *real_cards], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def run(s, pick=None, limit=40):
    """Resolve the stack; ``pick(decision)`` answers a decision (a list of option ids) or None for the first options."""
    seen = []
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers", "divide"):
            return seen
        if d is not None:
            seen.append(d)
            got = pick(d) if pick else None
            ids = got if got is not None else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return seen
    raise AssertionError("the stack never emptied")


def yes(d):
    ids = [o.id for o in d.options]
    return ["yes"] if "yes" in ids else None


def cast_it(s, name, pid="p1", targets=(), pick=None, face=None, counts=None, **m):
    mana(s, pid, **m)
    extra = ({} if face is None else {"face": face}) | ({} if counts is None else {"target_counts": counts})
    act(s, pid, type="cast_spell", card_id=to_hand(s, name, pid).id, targets=list(targets), **extra)
    return run(s, pick)


def gy(s, c, pid="p1"):
    act(s, pid, type="move", card_ids=[c.id], to={"player": c.owner, "zone": "graveyard"})
    return c


def where(s, c):
    return s.state.cards[c.id].zone


def lib(s, pid="p1"):
    return list(s.state.zones.get(f"{pid}:library", []))


def on_top(s, c, pid="p1"):
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")


def tokens(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:battlefield"]


PROMOTED = ["Genju of the Realm", "Return of the Nightstalkers", "Vengeful Regrowth", "Grim Captain's Call", "Ajani Fells the Godsire", "Defossilize",
            "Clear the Stage", "Perennation", "Crystal Dragon // Rob the Hoard", "Leonardo's Technique", "An Unearthly Child", "Lifeline",
            "Catapult Fodder // Catapult Captain", "Edgar, Charmed Groom // Edgar Markov's Coffin", "Garruk Relentless // Garruk, the Veil-Cursed",
            "Mutagen Connoisseur", "Jason Bright, Glowing Prophet", "Harvest Wurm", "The Curse of Fenric", "Nightmares and Daydreams",
            "Urza Assembles the Titans", "Write into Being", "Hide in Plain Sight",
            "Guardian Scalelord", "Olivia, Crimson Bride", "Reef Worm", "Rekindling Phoenix", "Ozox, the Clattering King",
            "Vault 12: The Necropolis", "Fall of the Impostor", "Braids's Frightful Return",
            "Zurgo and Ojutai", "Imperial Mask", "All Suns' Dawn", "Rogues' Gallery",
            "Woodcaller Automaton", "Time Lord Regeneration", "Waking the Trolls", "Moorland Rescuer", "Custodi Soulcaller",
            "Revealing Wind", "Trial of a Time Lord", "Vault 13: Dweller's Journey",
            "Summoner's Egg", "Esper Origins // Summon: Esper Maduin",
            "Nemesis Phoenix", "Tasigur, the Golden Fang", "The Three Seasons", "Veiled Ascension",
            "Baneblade Scoundrel // Baneclaw Marauder", "Giant Slug", "Illusionary Presence", "Barbarian Guides",
            "Getaway Barrel", "Death in Heaven", "Kang Dynasty", "Vulpine Harvester"]


@pytest.mark.parametrize("name", PROMOTED)
def test_wave100g_promoted_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def forests(s, n, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == pid and c.zone == f"{pid}:library"][:n]


def test_vengeful_regrowth_makes_a_plant_for_each_land_returned(cards):
    s = build(cards, ["Vengeful Regrowth"])
    a, b, c = (gy(s, f) for f in forests(s, 3))
    mana(s, G=2, C=4)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Vengeful Regrowth").id, targets=[a.id, b.id, c.id], target_counts=[3])
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "exile"})  # one target gone in response (the official ruling)
    run(s)
    assert where(s, a) == where(s, b) == "p1:battlefield" and s.state.cards[a.id].tapped and s.state.cards[b.id].tapped
    assert len(tokens(s, "Plant Warrior")) == 2  # not three
    check(s)


def test_grim_captains_call_returns_one_card_per_type_in_order(cards):
    s = build(cards, ["Grim Captain's Call", "Probe Pirate Vampire", "Probe Merfolk", "Grizzly Bears"])
    pv, mf, bears = (gy(s, card_named(s, n)) for n in ("Probe Pirate Vampire", "Probe Merfolk", "Grizzly Bears"))
    cast_it(s, "Grim Captain's Call", B=1, C=2)
    assert where(s, pv) == where(s, mf) == "p1:hand"  # the Pirate Vampire for "Pirate", nothing left for "Vampire" or "Dinosaur"
    assert where(s, bears) == "p1:graveyard"
    check(s)


def to_main(s, turn, limit=300):
    """Pass priority (no attackers, no blockers; first options) to the precombat main phase of turn ``turn`` (714.3b: a lore counter after the draw step)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.number == turn and s.state.turn.phase == "main1" and not s.state.zones.get("stack") and d is None:
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never reached that main phase")


def test_ajani_fells_the_godsire_chapter_two_token_then_vigilance_counter(cards):
    s = build(cards, ["Ajani Fells the Godsire", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    cast_it(s, "Ajani Fells the Godsire", W=2, C=3)  # chapter I: no creature an opponent controls with power 3 or greater
    to_main(s, 3)
    cats = tokens(s, "Cat Warrior")
    assert len(cats) == 1
    assert sum(s.state.cards[c.id].counters.get("vigilance", 0) for c in [bears, *cats]) == 1  # on one creature Alice controls
    check(s)


def test_defossilize_explores_twice(cards):
    s = build(cards, ["Defossilize", "Llanowar Elves", "Grizzly Bears"])
    elves = gy(s, card_named(s, "Llanowar Elves"))
    bears, forest = card_named(s, "Grizzly Bears"), forests(s, 1)[0]
    on_top(s, forest)
    on_top(s, bears)  # top: Grizzly Bears, then a Forest

    def pick(d):
        ids = [o.id for o in d.options]
        return ["graveyard"] if "graveyard" in ids else None

    cast_it(s, "Defossilize", pick=pick, B=1, C=4)
    assert where(s, elves) == "p1:battlefield" and s.state.cards[elves.id].counters.get("+1/+1") == 1  # the nonland card: a counter
    assert where(s, bears) == "p1:graveyard" and where(s, forest) == "p1:hand"  # the second explore reveals the Forest
    check(s)


@pytest.mark.parametrize("own", [False, True])
def test_clear_the_stage_checks_the_power_after_the_shrink(cards, own):
    s = build(cards, ["Clear the Stage", "Probe Big", "Grizzly Bears"], ["Llanowar Elves"])
    big, bears = put(s, "Probe Big"), gy(s, card_named(s, "Grizzly Bears"))
    victim = big if own else put(s, "Llanowar Elves", "p2")
    cast_it(s, "Clear the Stage", targets=[victim.id, bears.id], counts=[1, 1], pick=yes, B=1, C=4)
    assert where(s, bears) == ("p1:graveyard" if own else "p1:hand")  # a 5/5 shrunk to 2/2 leaves no creature with power 4
    check(s)


def test_perennation_returns_with_both_counters(cards):
    s = build(cards, ["Perennation", "Grizzly Bears"])
    bears = gy(s, card_named(s, "Grizzly Bears"))
    cast_it(s, "Perennation", targets=[bears.id], W=1, B=1, G=1, C=3)
    c = s.state.cards[bears.id]
    assert c.zone == "p1:battlefield" and c.counters.get("hexproof") == 1 and c.counters.get("indestructible") == 1
    check(s)


def test_rob_the_hoard_takes_a_legendary_card_not_a_plain_creature(cards):
    s = build(cards, ["Crystal Dragon // Rob the Hoard", "Test Legendary Sorcery", "Grizzly Bears"])
    legend, bears = gy(s, card_named(s, "Test Legendary Sorcery")), gy(s, card_named(s, "Grizzly Bears"))
    mana(s, W=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Crystal Dragon // Rob the Hoard").id, face=1, targets=[bears.id])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Crystal Dragon // Rob the Hoard").id, face=1, targets=[legend.id])
    run(s)
    assert where(s, legend) == "p1:hand" and where(s, bears) == "p1:graveyard"
    assert where(s, card_named(s, "Crystal Dragon // Rob the Hoard")) == "p1:exile"  # 715.4: on an adventure
    check(s)


def test_leonardos_technique_needs_one_target(cards):
    s = build(cards, ["Leonardo's Technique", "Grizzly Bears", "Llanowar Elves", "Probe Five"])
    bears, elves, five = (gy(s, card_named(s, n)) for n in ("Grizzly Bears", "Llanowar Elves", "Probe Five"))
    mana(s, W=1, C=3)
    tech = to_hand(s, "Leonardo's Technique")
    for bad in ([], [five.id]):  # none, or mana value 5
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=tech.id, targets=bad, target_counts=[len(bad)])
    act(s, "p1", type="cast_spell", card_id=tech.id, targets=[bears.id, elves.id], target_counts=[2])
    run(s)
    assert where(s, bears) == where(s, elves) == "p1:battlefield"
    check(s)


def test_return_of_the_nightstalkers_returns_them_then_destroys_your_swamps(cards):
    s = build(cards, ["Return of the Nightstalkers", "Probe Nightstalker", "Swamp"], ["Swamp"])
    night = gy(s, card_named(s, "Probe Nightstalker"))
    mine, theirs = put(s, "Swamp"), put(s, "Swamp", "p2")
    cast_it(s, "Return of the Nightstalkers", B=2, C=5)
    assert where(s, night) == "p1:battlefield"
    assert where(s, mine) == "p1:graveyard" and where(s, theirs) == "p2:battlefield"
    check(s)


def test_genju_of_the_realm_returns_to_hand_when_its_land_goes(cards):
    s = build(cards, ["Genju of the Realm", "Stone Rain"])
    land = put(s, "Forest")
    cast_it(s, "Genju of the Realm", targets=[land.id], W=1, U=1, B=1, R=1, G=1)
    genju = card_named(s, "Genju of the Realm")
    assert s.state.cards[genju.id].attached_to == land.id
    cast_it(s, "Stone Rain", targets=[land.id], pick=yes, R=1, C=2)  # 704.5m: the unattached Aura goes too; its trigger looks back (603.10a)
    assert where(s, genju) == "p1:hand"
    check(s)


@pytest.mark.parametrize("hit", ["Probe Doctor", "Probe Companion", "Sky-Skiff"])
def test_an_unearthly_child_reveals_until_a_doctor_companion_or_vehicle(cards, hit):
    s = build(cards, ["An Unearthly Child", "Grizzly Bears", hit])
    bears, found = card_named(s, "Grizzly Bears"), card_named(s, hit)
    on_top(s, found)
    on_top(s, bears)
    cast_it(s, "An Unearthly Child", U=2, C=1)
    assert where(s, found) == "p1:hand"
    assert lib(s)[-1] == bears.id  # the revealed miss goes to the bottom
    check(s)


# -- whole abilities ----------------------------------------------------------------------------------------------------------------------------
def to_step(s, phase, turn, limit=300, pick=None):
    """Pass priority (no attackers, no blockers; first options) until ``phase`` of turn ``turn`` is reached — or passed: a step nobody gets
    priority in is gone through within one action — with an empty stack and no decision."""
    from app.game.state import PHASES

    for _ in range(limit):
        d = s.state.rules.decision
        at = (s.state.turn.number, PHASES.index(s.state.turn.phase))
        if at >= (turn, PHASES.index(phase)) and not s.state.zones.get("stack") and d is None:
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            got = pick(d) if pick else None
            act(s, d.player, type="choose", decision_id=d.id, option_ids=got if got is not None else [o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase} of turn {turn}")


@pytest.mark.parametrize("alone", [False, True])
def test_lifeline_returns_a_dead_creature_at_the_next_end_step(cards, alone):
    s = build(cards, ["Lifeline", "Murder", "Grizzly Bears"], ["Llanowar Elves"])
    put(s, "Lifeline")
    elves = put(s, "Llanowar Elves", "p2")
    if not alone:
        put(s, "Grizzly Bears")
    cast_it(s, "Murder", targets=[elves.id], B=2, C=1)
    assert where(s, elves) == "p2:graveyard"
    to_step(s, "main2", 1)
    run(s)
    to_step(s, "upkeep", 2)
    assert where(s, elves) == ("p2:graveyard" if alone else "p2:battlefield")  # under its owner's control
    check(s)


@pytest.mark.parametrize("walls", [1, 2])
def test_catapult_fodder_needs_three_creatures_each_tougher_than_strong(cards, walls):
    s = build(cards, ["Catapult Fodder // Catapult Captain", "Probe Wall", "Probe Tall", "Grizzly Bears"])
    fodder = put(s, "Catapult Fodder // Catapult Captain")
    put(s, "Grizzly Bears")  # 2/2: not tougher than strong
    for name in ("Probe Wall", "Probe Tall")[:walls]:
        put(s, name)
    to_step(s, "declare_attackers", 1)
    assert s.state.cards[fodder.id].face == (1 if walls == 2 else 0)
    check(s)


def test_edgar_markovs_coffin_transforms_on_its_third_bloodline_counter(cards):
    s = build(cards, ["Edgar, Charmed Groom // Edgar Markov's Coffin", "Murder"])
    edgar = put(s, "Edgar, Charmed Groom // Edgar Markov's Coffin")
    cast_it(s, "Murder", targets=[edgar.id], B=2, C=1)
    assert where(s, edgar) == "p1:battlefield" and s.state.cards[edgar.id].face == 1  # returned transformed
    act(s, "p1", type="set_counter", card_id=edgar.id, kind="bloodline", value=1)
    to_step(s, "main1", 3)
    assert s.state.cards[edgar.id].counters.get("bloodline") == 2 and s.state.cards[edgar.id].face == 1
    to_step(s, "main1", 5)
    c = s.state.cards[edgar.id]
    assert c.face == 0 and not c.counters.get("bloodline")  # the third: removed, transformed back
    assert len(tokens(s, "Vampire")) == 2
    check(s)


@pytest.mark.parametrize("victim", ["Grizzly Bears", "Probe Wall"])
def test_garruk_relentless_transforms_at_two_or_fewer_loyalty(cards, victim):
    s = build(cards, ["Garruk Relentless // Garruk, the Veil-Cursed"], [victim])
    target = put(s, victim, "p2")
    cast_it(s, "Garruk Relentless // Garruk, the Veil-Cursed", G=1, C=3)
    garruk = card_named(s, "Garruk Relentless // Garruk, the Veil-Cursed")
    act(s, "p1", type="activate_ability", card_id=garruk.id, ability=1, targets=[target.id])
    run(s)
    c = s.state.cards[garruk.id]
    if victim == "Grizzly Bears":  # 2 damage back: one loyalty left
        assert c.counters.get("loyalty") == 1 and c.face == 1
    else:  # a 0-power creature deals nothing back
        assert c.counters.get("loyalty") == 3 and c.face == 0
    check(s)


def test_mutagen_connoisseur_counts_transformed_permanents(cards):
    from tests.wave9c_kit import pt

    s = build(cards, ["Mutagen Connoisseur", "Delver of Secrets // Insectile Aberration"], ["Delver of Secrets // Insectile Aberration"])
    put(s, "Mutagen Connoisseur")
    mine, theirs = put(s, "Delver of Secrets // Insectile Aberration"), put(s, "Delver of Secrets // Insectile Aberration", "p2")
    assert pt(s, "Mutagen Connoisseur") == (0, 5)
    act(s, "p2", type="set_face", card_id=theirs.id, face=1)
    assert pt(s, "Mutagen Connoisseur") == (0, 5)  # an opponent's transformed permanent doesn't count
    act(s, "p1", type="set_face", card_id=mine.id, face=1)
    assert pt(s, "Mutagen Connoisseur") == (1, 5)
    check(s)


@pytest.mark.parametrize("pumped", [False, True])
def test_jason_bright_draws_when_a_changed_zombie_dies(cards, pumped):
    s = build(cards, ["Jason Bright, Glowing Prophet", "Murder", "Dregscape Zombie"])
    put(s, "Jason Bright, Glowing Prophet")
    zombie = put(s, "Dregscape Zombie")
    if pumped:
        act(s, "p1", type="counter", card_ids=[zombie.id], kind="+1/+1", delta=1)
    hand = len(s.state.zones["p1:hand"])
    cast_it(s, "Murder", targets=[zombie.id], B=2, C=1)  # (Murder from the library to the hand, then cast: no net change)
    assert len(s.state.zones["p1:hand"]) == hand + (1 if pumped else 0)
    check(s)


@pytest.mark.parametrize("land", [False, True])
def test_harvest_wurm_is_sacrificed_unless_a_basic_land_card_returns(cards, land):
    s = build(cards, ["Harvest Wurm"])
    forest = forests(s, 1)[0]
    if land:
        gy(s, forest)
    cast_it(s, "Harvest Wurm", G=1, C=1)
    wurm = card_named(s, "Harvest Wurm")
    assert where(s, wurm) == ("p1:battlefield" if land else "p1:graveyard")
    assert where(s, forest) == ("p1:hand" if land else "p1:library")
    check(s)


def test_nightmares_and_daydreams_mills_the_cast_spells_mana_value(cards):
    s = build(cards, ["Nightmares and Daydreams", "Murder"], ["Llanowar Elves"])
    elves = put(s, "Llanowar Elves", "p2")
    cast_it(s, "Nightmares and Daydreams", U=1, C=2)  # chapter I: the watch, until Alice's next turn
    library = len(lib(s, "p2"))

    def pick(d):
        ids = [o.id for o in d.options]
        return ["p2"] if "p2" in ids else None

    cast_it(s, "Murder", targets=[elves.id], pick=pick, B=2, C=1)
    assert len(lib(s, "p2")) == library - 3  # Murder's mana value
    check(s)


def test_the_curse_of_fenric_chapter_two_makes_a_vanilla_legendary_fenric(cards):
    s = build(cards, ["The Curse of Fenric"], ["Kitchen Finks"])
    finks = put(s, "Kitchen Finks", "p2")
    saga = put(s, "The Curse of Fenric")
    act(s, "p1", type="set_counter", card_id=saga.id, kind="lore", value=1)  # (set by hand: no chapter I)
    to_step(s, "main1", 3)  # chapter II on Alice's next turn (714.3b); its only target the Finks
    c = s.state.cards[finks.id]
    ch = Plan(s.state, "p1", s.cards, None).ch(c)
    assert ch.name == "Fenric" and "Legendary" in ch.supertypes and ch.subtypes == {"Horror"} and ch.pt == (6, 6)
    assert not ch.keywords  # no abilities: no persist
    check(s)


def test_urza_assembles_the_titans_three_lets_loyalty_abilities_go_twice_this_turn(cards):
    s = build(cards, ["Urza Assembles the Titans", "Garruk Relentless // Garruk, the Veil-Cursed"])
    saga = put(s, "Urza Assembles the Titans")
    act(s, "p1", type="set_counter", card_id=saga.id, kind="lore", value=2)  # (set by hand: read ahead, no chapter I or II)
    cast_it(s, "Garruk Relentless // Garruk, the Veil-Cursed", G=1, C=3)
    garruk = card_named(s, "Garruk Relentless // Garruk, the Veil-Cursed")
    to_step(s, "main1", 3)  # chapter III
    for _ in range(2):  # "0: Create a 2/2 green Wolf creature token." twice
        act(s, "p1", type="activate_ability", card_id=garruk.id, ability=2)
        run(s)
    with pytest.raises(ActionError):  # never a third (the official ruling)
        act(s, "p1", type="activate_ability", card_id=garruk.id, ability=2)
    assert len(tokens(s, "Wolf")) == 2
    to_step(s, "main1", 5)  # a later turn: once again
    act(s, "p1", type="activate_ability", card_id=garruk.id, ability=2)
    run(s)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=garruk.id, ability=2)
    check(s)


@pytest.mark.parametrize("place", ["top", "bottom"])
def test_write_into_being_manifests_one_privately_and_places_the_other(cards, place):
    s = build(cards, ["Write into Being", "Grizzly Bears", "Llanowar Elves"])
    bears, elves = card_named(s, "Grizzly Bears"), card_named(s, "Llanowar Elves")
    on_top(s, elves)
    on_top(s, bears)
    hidden = []

    def pick(d):
        ids = [o.id for o in d.options]
        if bears.id in ids:
            hidden.append(json.dumps(s.view("p2")))
            return [bears.id]
        return [place] if place in ids else None

    cast_it(s, "Write into Being", pick=pick, U=1, C=2)
    assert hidden and "Grizzly Bears" not in hidden[0] and "Llanowar Elves" not in hidden[0]  # the looked-at cards, Alice's alone
    c = s.state.cards[bears.id]
    assert c.zone == "p1:battlefield" and c.face_down and c.face_down_kind == "manifest"
    assert (lib(s)[0] if place == "top" else lib(s)[-1]) == elves.id
    check(s)


def test_hide_in_plain_sight_cloaks_two_and_bottoms_the_rest(cards):
    s = build(cards, ["Hide in Plain Sight"])
    spell = to_hand(s, "Hide in Plain Sight")
    top = lib(s)[:5]
    picked = top[1:3]

    def pick(d):
        ids = [o.id for o in d.options]
        return picked if set(picked) <= set(ids) else None

    mana(s, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    run(s, pick)
    down = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.face_down]
    assert len(down) == 2 and all(c.face_down_kind == "cloak" for c in down)  # (face-down objects get fresh ids: 708, hidden identity)
    rest = [c for c in top if c in lib(s)]
    assert len(rest) == 3 and not set(picked) & set(rest) and set(lib(s)[-3:]) == set(rest)  # the chosen two left; the rest at the bottom
    check(s)


def attack(s, turn, attackers, pick=None, limit=300, target="p2"):
    """Pass priority to the declare attackers decision of turn ``turn``, attack Bob (``target``) with ``attackers`` and resolve the triggers."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers" and s.state.turn.number == turn:
            act(s, d.player, type="declare_attackers", attackers=[{"card_id": a.id, "target": target} for a in attackers])
            return run(s, pick)
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never reached the declare attackers step")


def test_guardian_scalelord_backup_grants_its_power_sized_return(cards):
    s = build(cards, ["Guardian Scalelord", "Grizzly Bears", "Probe Tall", "Probe Five"])
    bears = put(s, "Grizzly Bears")
    tall, five = gy(s, card_named(s, "Probe Tall")), gy(s, card_named(s, "Probe Five"))
    to_step(s, "main1", 3)

    def backup(d):
        ids = [o.id for o in d.options]
        return [bears.id] if bears.id in ids else None

    cast_it(s, "Guardian Scalelord", pick=backup, W=1, C=4)
    assert s.state.cards[bears.id].counters.get("+1/+1") == 1  # backup: a 3/3 with the attack trigger until end of turn
    offered = []

    def target(d):
        ids = [o.id for o in d.options]
        if tall.id in ids:
            offered.extend(ids)
            return [tall.id]
        return None

    attack(s, 3, [bears], pick=target)
    assert tall.id in offered and five.id not in offered  # mana value 2 ≤ its power 3; mana value 5 isn't
    assert where(s, tall) == "p1:battlefield"
    check(s)


def test_olivia_returns_an_attacker_that_leaves_with_the_last_legendary_vampire(cards):
    s = build(cards, ["Olivia, Crimson Bride", "Grizzly Bears", "Murder"])
    olivia = put(s, "Olivia, Crimson Bride")
    bears = gy(s, card_named(s, "Grizzly Bears"))
    bob = s.state.players["p2"].life
    attack(s, 1, [olivia], pick=lambda d: [bears.id] if bears.id in [o.id for o in d.options] else None)  # haste; Bob has no blockers
    c = s.state.cards[bears.id]
    assert c.zone == "p1:battlefield" and c.tapped and s.state.players["p2"].life == bob - 5  # it attacked too (3 + 2)
    to_step(s, "main2", 1)
    assert where(s, bears) == "p1:battlefield"  # Olivia is a legendary Vampire
    cast_it(s, "Murder", targets=[olivia.id], B=2, C=1)
    assert where(s, bears) == "p1:exile"  # the state trigger it gained (603.8)
    check(s)


def murder(s, target):
    to_hand(s, "Murder")  # (from wherever it is: the library, or the graveyard after an earlier cast)
    cast_it(s, "Murder", targets=[target.id], B=2, C=1)


def test_reef_worm_chain_fish_whale_kraken(cards):
    s = build(cards, ["Reef Worm", "Murder"])
    murder(s, put(s, "Reef Worm"))
    for name, nxt in (("Fish", "Whale"), ("Whale", "Kraken")):
        (made,) = tokens(s, name)
        murder(s, made)
        assert not tokens(s, name) and len(tokens(s, nxt)) == 1
    from tests.wave9c_kit import pt

    assert pt(s, "Kraken") == (9, 9)
    check(s)


@pytest.mark.parametrize("gone", [False, True])
def test_rekindling_phoenix_returns_at_the_next_upkeep(cards, gone):
    s = build(cards, ["Rekindling Phoenix", "Murder"])
    phoenix = put(s, "Rekindling Phoenix")
    murder(s, phoenix)
    assert len(tokens(s, "Elemental")) == 1
    if gone:
        act(s, "p1", type="move", card_ids=[phoenix.id], to={"player": "p1", "zone": "exile"})
    to_step(s, "main1", 3)
    if gone:  # no target: the ability is removed and the token stays (the official ruling)
        assert len(tokens(s, "Elemental")) == 1 and where(s, phoenix) == "p1:exile"
    else:
        assert not tokens(s, "Elemental") and where(s, phoenix) == "p1:battlefield"
        assert "haste" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[phoenix.id]).keywords
    check(s)


def test_ozox_makes_jumblebones_which_brings_it_back_to_hand(cards):
    s = build(cards, ["Ozox, the Clattering King", "Murder"])
    ozox = put(s, "Ozox, the Clattering King")
    murder(s, ozox)
    (bones,) = tokens(s, "Jumblebones")
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bones.id])
    assert "Legendary" in ch.supertypes and ch.pt == (2, 1)
    murder(s, bones)
    assert where(s, ozox) == "p1:hand"
    check(s)


def test_vault_12_counts_every_players_rad_counters(cards):
    s = build(cards, ["Vault 12: The Necropolis"])
    saga = put(s, "Vault 12: The Necropolis")
    act(s, "p1", type="set_counter", card_id=saga.id, kind="lore", value=1)  # (set by hand: no chapter I)
    to_step(s, "main2", 2)  # (after Bob's precombat main: his rad counters wait for his next turn)
    act(s, "p2", type="set_resource", player="p2", key="rad", value=3)
    to_step(s, "main1", 3)  # chapter II: Alice has none, Bob three
    assert len(tokens(s, "Zombie Mutant")) == 3
    check(s)


def test_fall_of_the_impostor_three_exiles_one_of_the_opponents_biggest(cards):
    s = build(cards, ["Fall of the Impostor", "Probe Huge"], ["Probe Big", "Probe Twin", "Probe Five"])
    huge = put(s, "Probe Huge")  # Alice's: never among the opponent's creatures
    big, twin, five = (put(s, n, "p2") for n in ("Probe Big", "Probe Twin", "Probe Five"))
    saga = put(s, "Fall of the Impostor")
    act(s, "p1", type="set_counter", card_id=saga.id, kind="lore", value=2)
    asked = []

    def pick(d):
        ids = [o.id for o in d.options]
        if twin.id in ids:
            asked.append((d.player, sorted(ids)))
            return [twin.id]
        return None

    to_step(s, "main1", 3, pick=pick)
    assert asked == [("p1", sorted([big.id, twin.id]))]  # the tie, Alice's choice
    assert where(s, twin) == "p2:exile" and where(s, big) == where(s, five) == "p2:battlefield" and where(s, huge) == "p1:battlefield"
    check(s)


@pytest.mark.parametrize("pays", [False, True])
def test_braids_frightful_return_three_sacrifice_or_lose_and_draw(cards, pays):
    s = build(cards, ["Braids's Frightful Return"], ["Grizzly Bears"])
    finks = put(s, "Grizzly Bears", "p2")
    saga = put(s, "Braids's Frightful Return")
    act(s, "p1", type="set_counter", card_id=saga.id, kind="lore", value=2)
    to_step(s, "main2", 2)  # (before Alice's draw step: one card more there)
    life, hand = s.state.players["p2"].life, len(s.state.zones["p1:hand"]) + 1

    def pick(d):
        ids = [o.id for o in d.options]
        if d.player == "p2" and "pay" in ids:
            return ["pay" if pays else "decline"]
        return [finks.id] if finks.id in ids else None

    to_step(s, "main1", 3, pick=pick)
    if pays:  # Bob sacrificed: nothing else
        assert where(s, finks) != "p2:battlefield" and s.state.players["p2"].life == life
    else:
        assert s.state.players["p2"].life == life - 2 and len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


@pytest.mark.parametrize("bounce", [False, True])
def test_zurgo_and_ojutai_may_return_one_of_the_dragons(cards, bounce):
    s = build(cards, ["Zurgo and Ojutai"])
    zurgo = put(s, "Zurgo and Ojutai")
    top = lib(s)[:3]
    hand = len(s.state.zones["p1:hand"])

    def pick(d):
        ids = [o.id for o in d.options]
        if ids == [zurgo.id]:
            return [zurgo.id] if bounce else []
        return None

    attack(s, 1, [zurgo], pick=pick)  # haste
    to_step(s, "main2", 1, pick=pick)
    assert len([c for c in top if where(s, s.state.cards[c]) == "p1:hand"]) == 1 and set(lib(s)[-2:]) <= set(top)
    assert where(s, zurgo) == ("p1:hand" if bounce else "p1:battlefield")
    assert len(s.state.zones["p1:hand"]) == hand + 1 + (1 if bounce else 0)
    check(s)


def test_imperial_mask_has_no_teammates_in_commander(cards):
    s = build(cards, ["Imperial Mask"])
    cast_it(s, "Imperial Mask", W=1, C=4)
    assert len([c for c in s.state.cards.values() if c.name == "Imperial Mask"]) == 1  # 903.2: Free-for-All, nobody gets a copy
    check(s)


def test_all_suns_dawn_one_card_per_color_each_chosen_once(cards):
    s = build(cards, ["All Suns' Dawn", "Probe WU", "Grizzly Bears"])
    wu, bears = gy(s, card_named(s, "Probe WU")), gy(s, card_named(s, "Grizzly Bears"))
    mana(s, G=1, C=4)
    dawn = to_hand(s, "All Suns' Dawn")
    with pytest.raises(ActionError):  # the white-and-blue card as both the white and the blue card
        act(s, "p1", type="cast_spell", card_id=dawn.id, targets=[wu.id, wu.id], target_counts=[1, 1, 0, 0, 0])
    with pytest.raises(ActionError):  # a green card isn't the white one
        act(s, "p1", type="cast_spell", card_id=dawn.id, targets=[bears.id], target_counts=[1, 0, 0, 0, 0])
    act(s, "p1", type="cast_spell", card_id=dawn.id, targets=[wu.id, bears.id], target_counts=[0, 1, 0, 0, 1])
    run(s)
    assert where(s, wu) == where(s, bears) == "p1:hand" and where(s, dawn) == "p1:exile"
    check(s)


def test_woodcaller_automaton_prototyped_makes_a_3_3_treefolk_land(cards):
    s = build(cards, ["Woodcaller Automaton"])
    land = put(s, "Forest")
    act(s, "p1", type="tap", card_ids=[land.id])
    mana(s, G=2, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Woodcaller Automaton").id, prototype=True)
    run(s)
    c = s.state.cards[land.id]
    ch = Plan(s.state, "p1", s.cards, None).ch(c)
    assert not c.tapped and ch.is_creature and ch.is_land and "Treefolk" in ch.subtypes and ch.pt == (3, 3) and "haste" in ch.keywords
    check(s)


def test_time_lord_regeneration_dies_into_the_next_time_lord(cards):
    s = build(cards, ["Time Lord Regeneration", "Murder", "Probe Doctor", "Probe Lord", "Grizzly Bears"])
    doctor, lord, bears = card_named(s, "Probe Doctor"), card_named(s, "Probe Lord"), card_named(s, "Grizzly Bears")
    put(s, "Probe Doctor")
    on_top(s, lord)
    on_top(s, bears)  # top: Grizzly Bears, then the Time Lord
    cast_it(s, "Time Lord Regeneration", targets=[doctor.id], U=1)
    murder(s, doctor)
    assert where(s, lord) == "p1:battlefield" and lib(s)[-1] == bears.id
    check(s)


@pytest.mark.parametrize("theirs", [1, 4])
def test_waking_the_trolls_three_makes_the_land_difference_in_trolls(cards, theirs):
    s = build(cards, ["Waking the Trolls"])
    for f in forests(s, 3):
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "battlefield"})
    islands = [c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2" and c.zone == "p2:library"][:theirs]
    act(s, "p2", type="move", card_ids=[c.id for c in islands], to={"player": "p2", "zone": "battlefield"})
    saga = put(s, "Waking the Trolls")
    act(s, "p1", type="set_counter", card_id=saga.id, kind="lore", value=2)
    to_step(s, "main1", 3)  # chapter III: Alice 3 lands
    assert len(tokens(s, "Troll Warrior")) == (2 if theirs == 1 else 0)
    check(s)


def test_moorland_rescuer_returns_power_up_to_its_last_power_then_exiles_itself(cards):
    s = build(cards, ["Moorland Rescuer", "Murder", "Probe Big", "Llanowar Elves"])
    rescuer = put(s, "Moorland Rescuer")
    act(s, "p1", type="counter", card_ids=[rescuer.id], kind="+1/+1", delta=1)  # 5/5 as it last existed (4/4 printed)
    big, elves = gy(s, card_named(s, "Probe Big")), gy(s, card_named(s, "Llanowar Elves"))
    to_hand(s, "Murder")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[rescuer.id])
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and big.id in [o.id for o in d.options]:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    with pytest.raises(ActionError):  # 5 + 1 is more than 5
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[big.id, elves.id])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[big.id])
    run(s)
    assert where(s, big) == "p1:battlefield" and where(s, elves) == "p1:graveyard" and where(s, rescuer) == "p1:exile"
    check(s)


def test_custodi_soulcaller_x_is_the_players_attacked(cards):
    s = build(cards, ["Custodi Soulcaller", "Llanowar Elves", "Grizzly Bears"])
    soul = put(s, "Custodi Soulcaller")
    elves, bears = gy(s, card_named(s, "Llanowar Elves")), gy(s, card_named(s, "Grizzly Bears"))
    to_step(s, "main1", 3)
    offered = []

    def pick(d):
        ids = [o.id for o in d.options]
        if elves.id in ids:
            offered.extend(ids)
            return [elves.id]
        return None

    attack(s, 3, [soul], pick=pick)
    assert elves.id in offered and bears.id not in offered  # one player attacked: mana value 1 or less
    assert where(s, elves) == "p1:battlefield"
    check(s)


def test_revealing_wind_prevents_combat_damage_and_shows_the_face_down_blocker(cards):
    s = build(cards, ["Revealing Wind", "Grizzly Bears"], ["Llanowar Elves"])
    bears = put(s, "Grizzly Bears")
    act(s, "p2", type="move", card_ids=[card_named(s, "Llanowar Elves", "p2").id], to={"player": "p2", "zone": "battlefield"}, face_down=True,
        face_down_kind="morph")
    (down,) = [c for c in s.state.cards.values() if c.zone == "p2:battlefield" and c.face_down]
    to_step(s, "main1", 3)
    attack(s, 3, [bears])
    act(s, "p1", type="set_stops", own=["declare_blockers"], smart_pass=False)  # (Alice acts in the declare blockers step)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": down.id, "attacker_id": bears.id}])
    assert "Llanowar Elves" not in json.dumps(s.view("p1"))
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Revealing Wind").id)
    seen = []

    def pick(d):
        seen.append((d.player, "Llanowar Elves" in json.dumps(s.view("p1")), "Llanowar Elves" in json.dumps(s.view("p2"))))
        return None

    run(s, pick)
    assert seen and seen[0][0] == "p1" and seen[0][1]  # Alice looks at it (Bob, its controller, always may: 708.5)
    to_step(s, "main2", 3)
    assert where(s, bears) == "p1:battlefield" and s.state.cards[down.id].zone == "p2:battlefield" and not s.state.cards[down.id].damage
    assert s.state.cards[down.id].face_down and not s.state.cards[down.id].revealed_to  # hidden again after the look
    check(s)


@pytest.mark.parametrize("bob", ["innocent", "guilty"])
def test_trial_of_a_time_lord_four_guilty_puts_the_exiled_on_the_bottom(cards, bob):
    s = build(cards, ["Trial of a Time Lord"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    cast_it(s, "Trial of a Time Lord", W=2, C=1)  # chapter I: the Bears exiled until the Saga leaves
    assert where(s, bears) == "p2:exile"
    saga = card_named(s, "Trial of a Time Lord")
    act(s, "p1", type="set_counter", card_id=saga.id, kind="lore", value=3)  # (by hand: no chapters)

    def pick(d):
        ids = [o.id for o in d.options]
        if "guilty" in ids:
            return ["guilty" if d.player == "p1" else bob]
        return None

    to_step(s, "main1", 3, pick=pick)  # chapter IV, then the Saga is sacrificed
    if bob == "guilty":  # two votes to none
        assert s.state.cards[lib(s, "p2")[-1]].name == "Grizzly Bears"  # (a card in a library: a fresh id, 401.? hidden)
    else:  # a tie: the Bears come back as the Saga leaves (the official ruling)
        assert where(s, card_named(s, "Grizzly Bears", "p2")) == "p2:battlefield"
    check(s)


def test_vault_13_three_returns_the_exiled_cards(cards):
    s = build(cards, ["Vault 13: Dweller's Journey", "Grizzly Bears"], ["Llanowar Elves"])
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Llanowar Elves", "p2")
    mana(s, W=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Vault 13: Dweller's Journey").id)
    run(s, lambda d: [o.id for o in d.options if o.id in (mine.id, theirs.id)] or None)  # chapter I: one of each player's
    assert where(s, mine) == "p1:exile" and where(s, theirs) == "p2:exile"
    saga = card_named(s, "Vault 13: Dweller's Journey")
    act(s, "p1", type="set_counter", card_id=saga.id, kind="lore", value=2)
    to_step(s, "main1", 3)  # chapter III: the two return under their owners' control
    assert where(s, card_named(s, "Grizzly Bears")) == "p1:battlefield" and where(s, card_named(s, "Llanowar Elves", "p2")) == "p2:battlefield"
    check(s)


def test_trial_of_a_time_lord_owner_orders_two_cards_on_the_bottom(cards):
    s = build(cards, ["Trial of a Time Lord"], ["Grizzly Bears", "Llanowar Elves"])
    bears, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    cast_it(s, "Trial of a Time Lord", pick=lambda d: [bears.id] if bears.id in [o.id for o in d.options] else None, W=2, C=1)
    to_step(s, "main1", 3)  # chapter II: the Elves
    assert where(s, bears) == where(s, elves) == "p2:exile"
    act(s, "p1", type="set_counter", card_id=card_named(s, "Trial of a Time Lord").id, kind="lore", value=3)
    asked = []

    def pick(d):
        ids = [o.id for o in d.options]
        if "guilty" in ids:
            return ["guilty"]
        if d.kind == "order":
            asked.append(d.player)
            return [elves.id, bears.id] if elves.id in ids else None
        return None

    to_step(s, "main1", 5, pick=pick)
    assert asked == ["p2"]  # Bob orders his own cards (the official ruling)
    assert sorted(s.state.cards[c].name for c in lib(s, "p2")[-2:]) == ["Grizzly Bears", "Llanowar Elves"]
    check(s)


@pytest.mark.parametrize("hidden", ["Grizzly Bears", "Swamp"])
def test_summoners_egg_turns_its_card_up_and_puts_a_creature_onto_the_battlefield(cards, hidden):
    s = build(cards, ["Summoner's Egg", "Murder", hidden])
    card = to_hand(s, hidden)
    cast_it(s, "Summoner's Egg", pick=lambda d: [card.id] if card.id in [o.id for o in d.options] else (["yes"] if "yes" in [o.id for o in d.options] else None), C=4)
    egg = card_named(s, "Summoner's Egg")
    (down,) = [c for c in s.state.cards.values() if c.zone == "p1:exile"]
    assert down.face_down and hidden not in json.dumps(s.view("p2"))  # imprinted face down: nobody else knows it
    murder(s, egg)
    now = s.state.cards[down.id]
    if hidden == "Grizzly Bears":
        assert now.zone == "p1:battlefield" and not now.face_down
    else:  # a noncreature card stays exiled, face up (the official ruling)
        assert now.zone == "p1:exile" and not now.face_down
    check(s)


@pytest.mark.parametrize("flashback", [False, True])
def test_esper_origins_from_a_graveyard_returns_transformed_with_finality(cards, flashback):
    s = build(cards, ["Esper Origins // Summon: Esper Maduin"])
    origins = card_named(s, "Esper Origins // Summon: Esper Maduin")
    if flashback:
        gy(s, origins)
        mana(s, G=1, C=3)
        act(s, "p1", type="cast_spell", card_id=origins.id)  # (flashback {3}{G}: the card in the graveyard)
    else:
        mana(s, G=1, C=1)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Esper Origins // Summon: Esper Maduin").id)
    life = s.state.players["p1"].life
    run(s)
    c = s.state.cards[origins.id]
    assert s.state.players["p1"].life == life + 2
    if flashback:  # 712.14a: the Saga face up, with a finality counter (and its first chapter)
        assert c.zone == "p1:battlefield" and c.face == 1 and c.counters.get("finality") == 1
    else:
        assert c.zone == "p1:graveyard"
    check(s)


def build3(cards, mine=(), theirs=()):
    """Alice, Bob and Carol (rules automation on), at Alice's precombat main phase."""
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (9, "Forest")])
    others = [deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in theirs), (10, "Island")]) for _ in range(2)]
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=others[0]), PlayerSetup("Carol", cards=others[1])],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


@pytest.mark.parametrize("split", [False, True])
def test_nemesis_phoenix_needs_two_opponents_attacked(cards, split):
    s = build3(cards, ["Nemesis Phoenix", "Grizzly Bears", "Llanowar Elves"])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    phoenix = gy(s, card_named(s, "Nemesis Phoenix"))
    to_step(s, "main1", 4)
    act(s, "p1", type="set_stops", own=["declare_attackers"], smart_pass=False)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}, {"card_id": elves.id, "target": "p3" if split else "p2"}])
    mana(s, R=1, C=2)
    if not split:  # one opponent attacked: not allowed
        with pytest.raises(ActionError):
            act(s, "p1", type="activate_ability", card_id=phoenix.id, ability=1)
        return
    act(s, "p1", type="activate_ability", card_id=phoenix.id, ability=1)
    run(s, lambda d: ["p3"] if "p3" in [o.id for o in d.options] else None)
    c = s.state.cards[phoenix.id]
    assert c.zone == "p1:battlefield" and c.tapped and c.attacking is not None
    check(s)


def test_tasigur_an_opponent_of_your_choice_picks_the_nonland_card(cards):
    s = build3(cards, ["Tasigur, the Golden Fang", "Grizzly Bears", "Llanowar Elves"])
    tasigur = put(s, "Tasigur, the Golden Fang")
    bears, elves = gy(s, card_named(s, "Grizzly Bears")), gy(s, card_named(s, "Llanowar Elves"))
    mana(s, G=2, C=2)
    act(s, "p1", type="activate_ability", card_id=tasigur.id, ability=1)
    asked = []

    def pick(d):
        ids = [o.id for o in d.options]
        if "p3" in ids:
            asked.append((d.player, "opponent"))
            return ["p3"]
        if elves.id in ids:
            asked.append((d.player, "card"))
            assert not [o for o in d.options if s.state.cards[o.id].name == "Forest"]  # nonland cards only
            return [elves.id]
        return None

    run(s, pick)
    assert asked == [("p1", "opponent"), ("p3", "card")]
    assert where(s, elves) == "p1:hand" and where(s, bears) == "p1:graveyard"
    check(s)


def test_the_three_seasons_three_shuffles_three_cards_of_each_graveyard(cards):
    s = build3(cards, ["The Three Seasons", "Grizzly Bears", "Llanowar Elves"])
    bears, elves = gy(s, card_named(s, "Grizzly Bears")), gy(s, card_named(s, "Llanowar Elves"))
    kept, *_ = [gy(s, c) for c in forests(s, 2)]
    for c in [c for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library"][:2]:
        gy(s, c, "p2")
    saga = put(s, "The Three Seasons")
    act(s, "p1", type="set_counter", card_id=saga.id, kind="lore", value=2)  # (set by hand: no chapter I or II)
    to_step(s, "main2", 3)
    carol = lib(s, "p3")
    asked = []

    def pick(d):
        ids = [o.id for o in d.options]
        if bears.id in ids:
            asked.append((d.player, len(ids)))
            return [bears.id, elves.id, *(i for i in ids if i not in (bears.id, elves.id, kept.id))]
        return None

    to_step(s, "main1", 4, pick=pick)
    assert asked == [("p1", 4)]  # only Alice's graveyard holds more than three cards
    assert [s.state.cards[c].name for c in s.state.zones["p1:graveyard"]] == ["Forest", "The Three Seasons"] and where(s, kept) == "p1:graveyard"
    assert not s.state.zones["p2:graveyard"] and len(lib(s, "p2")) == 9  # fewer than three: all of them (one card drawn)
    assert lib(s, "p3") == carol  # nothing chosen in Carol's graveyard: no shuffle
    check(s)


def test_veiled_ascension_face_down_creatures_enter_with_a_flying_counter(cards):
    s = build(cards, ["Veiled Ascension", "Grizzly Bears"])
    put(s, "Veiled Ascension")
    to_step(s, "draw", 3, pick=yes)  # Alice's upkeep: cloak the top card
    cloaked = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.face_down]
    assert len(cloaked) == 1 and cloaked[0].counters.get("flying") == 1
    to_main(s, 3)
    cast_it(s, "Grizzly Bears", G=1, C=1)
    assert not s.state.cards[card_named(s, "Grizzly Bears").id].counters.get("flying")  # face up: none
    check(s)


@pytest.mark.parametrize("blocker", ["Grizzly Bears", "Probe Big"])
def test_baneclaw_marauder_a_dying_blocker_costs_its_controller_one_life(cards, blocker):
    s = build(cards, ["Baneblade Scoundrel // Baneclaw Marauder", "Grizzly Bears"], [blocker, "Llanowar Elves"])
    wolf = put(s, "Baneblade Scoundrel // Baneclaw Marauder")
    act(s, "p1", type="set_day_night", value="night")
    act(s, "p1", type="set_face", card_id=wolf.id, face=1)  # (by hand: nightbound, 702.145)
    bears, guard, other = put(s, "Grizzly Bears"), put(s, blocker, "p2"), put(s, "Llanowar Elves", "p2")
    to_step(s, "main1", 3)
    life = s.state.players["p2"].life
    attack(s, 3, [wolf, bears])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": guard.id, "attacker_id": wolf.id}, {"blocker_id": other.id, "attacker_id": bears.id}])
    to_step(s, "main2", 3)
    assert where(s, guard) == where(s, other) == "p2:graveyard"
    assert s.state.players["p2"].life == life - 1  # the Elves blocked another attacker: nothing for it
    if blocker == "Probe Big":
        assert where(s, wolf) == "p1:graveyard"  # (the two died at once: the trigger looks back in time, 603.10a)
    check(s)


def kws(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).keywords


def test_giant_slug_chooses_a_basic_landwalk_at_the_next_upkeep(cards):
    s = build(cards, ["Giant Slug"])
    slug = put(s, "Giant Slug")
    mana(s, C=5)
    act(s, "p1", type="activate_ability", card_id=slug.id, ability=0)
    run(s)
    asked = []

    def pick(d):
        ids = [o.id for o in d.options]
        if "Island" in ids:
            asked.append((s.state.turn.number, ids))
            return ["Island"]
        return None

    to_step(s, "main1", 3, pick=pick)
    assert asked == [(3, ["Plains", "Island", "Swamp", "Mountain", "Forest"])]  # Alice's next upkeep, not Bob's
    assert "islandwalk" in kws(s, slug)
    to_step(s, "main1", 4)
    assert "islandwalk" not in kws(s, slug)  # until the end of that turn
    check(s)


def test_illusionary_presence_any_land_type_landwalk(cards):
    s = build(cards, ["Illusionary Presence", "Island"], ["Probe Gate", "Llanowar Elves"])
    ip = put(s, "Illusionary Presence")
    put(s, "Island")
    put(s, "Probe Gate", "p2")
    elves = put(s, "Llanowar Elves", "p2")
    seen = []

    def pick(d):
        ids = [o.id for o in d.options]
        if "pay" in ids:  # (cumulative upkeep {U})
            return ["pay"]
        if "Gate" in ids:
            seen.append(ids)
            return ["Gate"]
        return None

    to_step(s, "main1", 3, pick=pick)
    assert len(seen) == 1 and len(seen[0]) == 17 and "Snow" not in seen[0]  # the land types (205.3i): no supertype
    assert "gatewalk" in kws(s, ip)
    attack(s, 3, [ip])
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": elves.id, "attacker_id": ip.id}])
    check(s)


def test_barbarian_guides_snow_landwalk_of_the_chosen_type_then_back_to_hand(cards):
    s = build(cards, ["Barbarian Guides", "Grizzly Bears"], ["Probe Snow Lair", "Llanowar Elves"])
    guides, bears = put(s, "Barbarian Guides"), put(s, "Grizzly Bears")
    put(s, "Probe Snow Lair", "p2")
    elves = put(s, "Llanowar Elves", "p2")
    to_step(s, "main1", 3)
    mana(s, R=1, C=2)
    act(s, "p1", type="activate_ability", card_id=guides.id, ability=0, targets=[bears.id])
    run(s, lambda d: ["Lair"] if "Lair" in [o.id for o in d.options] else None)
    assert "snow lairwalk" in kws(s, bears)
    attack(s, 3, [bears])
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": elves.id, "attacker_id": bears.id}])
    act(s, "p2", type="declare_blockers", blocks=[])
    to_step(s, "cleanup", 3)
    assert where(s, bears) == "p1:hand"  # at the beginning of the next end step
    check(s)


def test_getaway_barrel_puts_a_random_revealed_creature_card_onto_the_battlefield(cards):
    s = build(cards, ["Getaway Barrel", "Probe Shatter", "Grizzly Bears", "Llanowar Elves"])
    barrel = put(s, "Getaway Barrel")
    bears, elves = card_named(s, "Grizzly Bears"), card_named(s, "Llanowar Elves")
    on_top(s, bears)
    on_top(s, elves)
    seen = cast_it(s, "Probe Shatter", targets=[barrel.id], R=1, C=1)
    assert not [d for d in seen if d.kind == "choose_cards"]  # nobody chooses
    up = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name in ("Grizzly Bears", "Llanowar Elves")]
    assert len(up) == 1
    assert [s.state.cards[c].name for c in lib(s)].count("Grizzly Bears" if up[0].name == "Llanowar Elves" else "Llanowar Elves") == 1
    check(s)


def test_death_in_heaven_exiles_graveyards_then_brings_the_creatures_back_as_cybermen(cards):
    s = build(cards, ["Death in Heaven"], ["Grizzly Bears", "Llanowar Elves"])
    gy(s, card_named(s, "Llanowar Elves", "p2"), "p2")
    on_top(s, card_named(s, "Grizzly Bears", "p2"), "p2")
    cast_it(s, "Death in Heaven", B=1, C=3, pick=lambda d: ["p2"] if "p2" in [o.id for o in d.options] else None)  # chapter I: Bob mills the Bears and an Island, then exiles his graveyard
    assert not s.state.zones.get("p2:graveyard")
    assert sorted(s.state.cards[c].name for c in s.state.zones["p2:exile"]) == ["Grizzly Bears", "Island", "Llanowar Elves"]
    act(s, "p1", type="set_counter", card_id=card_named(s, "Death in Heaven").id, kind="lore", value=2)  # (by hand: no chapter II)
    to_main(s, 3)
    down = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.face_down]
    assert len(down) == 2 and all(c.owner == "p2" for c in down)
    for c in down:
        ch = Plan(s.state, "p1", s.cards, None).ch(c)
        assert ch.types == {"Artifact", "Creature"} and ch.subtypes == {"Cyberman"} and ch.pt == (2, 2) and not ch.name
    assert [s.state.cards[c].name for c in s.state.zones["p2:exile"]] == ["Island"]  # not a creature card
    check(s)


def test_kang_dynasty_goads_one_creature_of_each_opponent_and_draws_on_their_hits(cards):
    s = build3(cards, ["Kang Dynasty"], ["Grizzly Bears"])
    bears, other = put(s, "Grizzly Bears", "p2"), put(s, "Grizzly Bears", "p3")
    cast_it(s, "Kang Dynasty", U=1, C=3, pick=lambda d: [c for c in (bears.id, other.id) if c in [o.id for o in d.options]] or None)
    assert s.state.cards[bears.id].tapped and s.state.cards[other.id].tapped
    from app.rules.keyword_actions import goaded_by

    assert all(goaded_by(Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])) == {"p1"} for c in (bears, other))
    hand = len(s.state.zones["p1:hand"])
    attack(s, 2, [bears], target="p3")  # (goaded: it attacks a player other than Alice, 701.15b; Carol's creature is tapped: no blocks)
    to_step(s, "main2", 2)
    assert len(s.state.zones["p1:hand"]) == hand + 1  # Bob's goaded Bears dealt combat damage to Carol: Alice draws
    check(s)


def test_kang_dynasty_three_pumps_by_hand_size_and_cant_be_blocked(cards):
    s = build(cards, ["Kang Dynasty", "Grizzly Bears"], ["Llanowar Elves"])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves", "p2")
    saga = put(s, "Kang Dynasty")
    act(s, "p1", type="set_counter", card_id=saga.id, kind="lore", value=2)  # (by hand: no chapter I or II)
    to_step(s, "main2", 2)

    def pick(d):
        return [bears.id] if bears.id in [o.id for o in d.options] else None

    to_step(s, "main1", 3, pick=pick)
    hand = len(s.state.zones["p1:hand"])
    from tests.wave9c_kit import pt

    assert pt(s, "Grizzly Bears") == (2 + hand, 2 + hand)
    attack(s, 3, [bears])
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": elves.id, "attacker_id": bears.id}])
    check(s)


@pytest.mark.parametrize("both", [False, True])
def test_vulpine_harvester_returns_the_artifact_only_within_the_attackers_total_power(cards, both):
    s = build(cards, ["Vulpine Harvester", "Probe Phyrexian", "Probe Relic"])
    fox, horror = put(s, "Vulpine Harvester"), put(s, "Probe Phyrexian")
    relic = gy(s, card_named(s, "Probe Relic"))
    to_step(s, "main1", 3)
    attack(s, 3, [fox, horror] if both else [fox], pick=lambda d: [relic.id] if relic.id in [o.id for o in d.options] else None)
    assert where(s, relic) == ("p1:battlefield" if both else "p1:graveyard")  # mana value 5: 3 + 2 attacking, not 3 alone
    check(s)
