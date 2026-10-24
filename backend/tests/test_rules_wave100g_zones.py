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
    real("Probe Twin", "{4}{G}", 5, "Creature — Beast", "", ("5", "5"), "G"),
    real("Probe Huge", "{6}{G}", 7, "Creature — Beast", "", ("7", "7"), "G"),
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
            "Vault 12: The Necropolis", "Fall of the Impostor", "Braids's Frightful Return"]


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
    to_step(s, "cleanup", 1) if False else None
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


def attack(s, turn, attackers, pick=None, limit=300):
    """Pass priority to the declare attackers decision of turn ``turn``, attack Bob with ``attackers`` and resolve the triggers."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers" and s.state.turn.number == turn:
            act(s, d.player, type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2"} for a in attackers])
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
