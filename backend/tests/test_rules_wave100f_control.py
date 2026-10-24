"""Wave 100F: control-changing spells and abilities and more attached-object triggers, real Oracle text (tests/fixtures/wave100f_cards.json). Every scenario
checks the replay and a save and a load (tests/wave9c_kit.check).

* 613.1b, 611.2c, 514.2: "You and target opponent each gain control of all creatures the other controls until end of turn." (Twist Allegiance, Reins of Power):
  both sets fixed at once; untapped (before or after, as written) and given haste.
* 603.7, 202.3: Angrath's delayed sacrifice reads the creature's mana value only as it resolves (the ruling).
* 603.4: "if you control each creature on the battlefield with the greatest power" (Might Makes Right), checked as it triggers and as it resolves.
* 608.2c: "If that creature's power is 2 or less or if you control another Lizard" (Reptilian Recruiter), checked as it resolves (the ruling).
* 603.7, 115.1: "At the beginning of the next end step, target land deals 3 damage to that creature." (Swooping Pteranodon): the land is chosen as the delayed
  ability triggers (the ruling), and is the source of the damage.
* 701.3a, 111.1: Grip of Phyresis: the Germ token, then the Equipment attached to it (the 0/0 dies when the Equipment gives no toughness: the ruling).
* 508.1: "Whenever equipped creature and at least one other creature attack" (Glimmer Lens); 701.21a "If the player can't" (Cruel Reality).
* 120.3: "this Aura deals 1 damage to that player or a planeswalker that player controls" (Curse of the Pierced Heart): its controller chooses as it resolves.
* 603.10a: Hateful Eidolon counts the Auras you controlled that were attached to the creature as it died (the rulings).
* 701.60: "can't become suspected" / "it's no longer suspected" (Airtight Alibi); 722.3b: "It becomes unprepared." (Infinite Coursework).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import pass_until_stack_empty
from tests.test_rules_wave100f_attached import next_turn, to_phase
from tests.wave9c_kit import build, check, life, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave100f_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w100f", number=f"F{i:03d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
CARDS = ["Angrath, the Flame-Chained", "Might Makes Right", "Twist Allegiance", "Reins of Power", "Grip of Phyresis", "Reptilian Recruiter",
         "Swooping Pteranodon", "Glimmer Lens", "Cruel Reality", "Curse of the Pierced Heart", "Hateful Eidolon", "Airtight Alibi", "Infinite Coursework"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, PREPARED], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", CARDS)
def test_the_cards_are_full(name):
    data = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or []}).level == "FULL"


def cost(name):
    out: dict[str, int] = {}
    for sym in re.findall(r"{([^}]+)}", next(c for c in DATA if c["name"] == name)["mana_cost"]):
        key = "C" if sym.isdigit() else sym
        out[key] = out.get(key, 0) + (int(sym) if sym.isdigit() else 1)
    return {k: v for k, v in out.items() if v}


def cast(s, name, targets=(), pid="p1", counts=None, pick=()):
    """Cast ``name`` paying its own cost, then resolve everything, answering decisions with ``pick`` ids where offered."""
    c = to_hand(s, name, pid)
    if cost(name):
        mana(s, pid, **cost(name))
    act(s, pid, type="cast_spell", card_id=c.id, **({"targets": list(targets)} if targets else {}), **({"target_counts": counts} if counts else {}))
    answer(s, pick)
    return s.state.cards[c.id]


def answer(s, pick=(), limit=40):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        if d is not None:
            ids = [o.id for o in d.options]
            want = [i for i in pick if i in ids] or ids[: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=want[: max(1, d.max_choices or 1)] if d.max_choices else want)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def ctl(s, c):
    return s.state.cards[c.id].controller


def zone(s, c):
    return s.state.cards[c.id].zone


# -- Twist Allegiance / Reins of Power ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["Twist Allegiance", "Reins of Power"])
def test_each_gains_control_of_the_others_creatures_until_end_of_turn(cards, name):
    s = build(cards, [name, "Grizzly Bears", "Llanowar Elves"], ["Hill Giant", "Walking Corpse"])
    bear, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    giant, corpse = put(s, "Hill Giant", "p2"), put(s, "Walking Corpse", "p2")
    act(s, "p1", type="tap", card_ids=[bear.id, giant.id], tapped=True)
    if name == "Twist Allegiance":
        to_phase(s, "main1", turn=1)
    cast(s, name, ["p2"])
    assert ctl(s, giant) == ctl(s, corpse) == "p1" and ctl(s, bear) == ctl(s, elves) == "p2"  # both sets at once (611.2c)
    for c in (bear, elves, giant, corpse):
        assert not s.state.cards[c.id].tapped and "haste" in ch(s, c).keywords
    next_turn(s)
    assert ctl(s, giant) == ctl(s, corpse) == "p2" and ctl(s, bear) == ctl(s, elves) == "p1"  # 514.2
    check(s)


def test_twist_allegiance_leaves_a_third_player_alone(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    players = [PlayerSetup(n, cards=deck(cards, "Krenko, Mob Boss", [(1, "Twist Allegiance"), (1, "Grizzly Bears"), (10, "Forest")])) for n in ("Alice", "Bob", "Carol")]
    s = GameSession(enable(new_game(players, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    bears = {p: next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == p) for p in ("p1", "p2", "p3")}
    for p, c in bears.items():
        act(s, "p1", type="move", card_ids=[c.id], to={"player": p, "zone": "battlefield"})
    cast(s, "Twist Allegiance", ["p3"])
    assert ctl(s, bears["p1"]) == "p3" and ctl(s, bears["p3"]) == "p1" and ctl(s, bears["p2"]) == "p2"
    check(s)


# -- Angrath, the Flame-Chained −3 ---------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("victim,sacrificed", [("Grizzly Bears", True), ("Hill Giant", False)])
def test_angrath_sacrifices_a_cheap_creature_at_the_next_end_step(cards, victim, sacrificed):
    s = build(cards, ["Angrath, the Flame-Chained"], [victim])
    angrath = put(s, "Angrath, the Flame-Chained")
    act(s, "p1", type="counter", card_ids=[angrath.id], kind="loyalty", delta=4)
    target = put(s, victim, "p2")
    act(s, "p1", type="activate_ability", card_id=angrath.id, ability=1, targets=[target.id])
    pass_until_stack_empty(s)
    assert ctl(s, target) == "p1" and "haste" in ch(s, target).keywords
    next_turn(s)
    assert zone(s, target) == ("p2:graveyard" if sacrificed else "p2:battlefield")  # mana value 2 (or 4) read as the delayed ability resolves
    check(s)


# -- Might Makes Right (603.4) ---------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("tied", [False, True])
def test_might_makes_right_needs_every_greatest_creature(cards, tied):
    s = build(cards, ["Might Makes Right", "Hill Giant"], ["Grizzly Bears", "Hill Giant"])
    put(s, "Might Makes Right")
    put(s, "Hill Giant")
    bear = put(s, "Grizzly Bears", "p2")
    if tied:
        put(s, "Hill Giant", "p2")  # (Bob's Giant ties for the greatest power: not every one of them is Alice's)
    to_phase(s, "begin_combat", turn=1)
    answer(s, [bear.id])
    assert ctl(s, bear) == ("p2" if tied else "p1")
    check(s)


# -- Reptilian Recruiter (608.2c) -------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lizard,taken", [(False, False), (True, True)])
def test_reptilian_recruiter_takes_a_big_creature_only_with_another_lizard(cards, lizard, taken):
    s = build(cards, ["Reptilian Recruiter", "Lizard Warrior"], ["Hill Giant"])
    if lizard:
        put(s, "Lizard Warrior")
    giant = put(s, "Hill Giant", "p2")
    cast(s, "Reptilian Recruiter", pick=[giant.id])
    assert ctl(s, giant) == ("p1" if taken else "p2")
    check(s)


def test_reptilian_recruiter_takes_a_small_creature(cards):
    s = build(cards, ["Reptilian Recruiter"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    act(s, "p2", type="tap", card_ids=[bear.id], tapped=True)
    cast(s, "Reptilian Recruiter", pick=[bear.id])
    assert ctl(s, bear) == "p1" and not s.state.cards[bear.id].tapped and "haste" in ch(s, bear).keywords
    check(s)


# -- Swooping Pteranodon (603.7: the delayed ability's own target) ------------------------------------------------------------------------------------------
def test_swooping_pteranodon_drops_the_creature_with_a_land_at_the_end_step(cards):
    s = build(cards, ["Swooping Pteranodon"], ["Hill Giant"])
    giant = put(s, "Hill Giant", "p2")
    land = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2")
    act(s, "p1", type="move", card_ids=[land.id], to={"player": "p2", "zone": "battlefield"})
    cast(s, "Swooping Pteranodon", pick=[giant.id])
    assert ctl(s, giant) == "p1" and {"flying", "haste"} <= set(ch(s, giant).keywords)
    to_phase(s, "end", turn=1)
    d = s.state.rules.decision
    assert d is not None and land.id in [o.id for o in d.options]  # (the land is chosen now, as the delayed ability triggers)
    answer(s, [land.id])
    assert zone(s, giant) == "p2:graveyard"  # 3 damage from the land, the damage's source (120.3), lethal for the 3/3 (704.5g)
    check(s)


# -- Grip of Phyresis (701.3a) --------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("equipment,germ_lives", [("Behemoth Sledge", True), ("Bonesplitter", False)])
def test_grip_of_phyresis_takes_the_equipment_onto_a_germ(cards, equipment, germ_lives):
    s = build(cards, ["Grip of Phyresis"], [equipment, "Grizzly Bears"])
    gear, bear = put(s, equipment, "p2"), put(s, "Grizzly Bears", "p2")
    act(s, "p2", type="attach", card_ids=[gear.id], to=bear.id)
    cast(s, "Grip of Phyresis", [gear.id])
    germ = [c for c in s.state.cards.values() if c.name == "Phyrexian Germ" and c.zone.endswith(":battlefield")]
    assert ctl(s, gear) == "p1"
    if germ_lives:
        assert len(germ) == 1 and s.state.cards[gear.id].attached_to == germ[0].id
    else:
        assert not germ and s.state.cards[gear.id].attached_to is None  # the 0/0 died (704.5f); Alice keeps the Equipment
    check(s)


# -- Glimmer Lens (508.1) -------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("alone", [True, False])
def test_glimmer_lens_draws_when_its_creature_attacks_with_another(cards, alone):
    s = build(cards, ["Glimmer Lens", "Grizzly Bears", "Llanowar Elves"])
    lens, bear, elves = put(s, "Glimmer Lens"), put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    act(s, "p1", type="attach", card_ids=[lens.id], to=bear.id)
    to_phase(s, "declare_attackers", turn=3)
    hand = len(s.state.zones.get("p1:hand", []))
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in ([bear] if alone else [bear, elves])])
    answer(s)
    assert len(s.state.zones.get("p1:hand", [])) == hand + (0 if alone else 1)
    check(s)


# -- Curses ---------------------------------------------------------------------------------------------------------------------------------------------------
def test_cruel_reality_makes_the_player_sacrifice_or_lose_five(cards):
    s = build(cards, ["Cruel Reality"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    cast(s, "Cruel Reality", ["p2"])
    to_phase(s, "draw", turn=2)
    assert zone(s, bear) == "p2:graveyard" and life(s, "p2") == 40  # a creature to sacrifice: no life lost
    to_phase(s, "draw", turn=4)
    assert life(s, "p2") == 35  # nothing left to sacrifice: 5 life (701.21a)
    check(s)


@pytest.mark.parametrize("walker", [False, True])
def test_curse_of_the_pierced_heart_hits_the_player_or_their_planeswalker(cards, walker):
    s = build(cards, ["Curse of the Pierced Heart"], ["Gideon Jura"])
    gideon = put(s, "Gideon Jura", "p2") if walker else None
    if gideon is not None:
        act(s, "p1", type="counter", card_ids=[gideon.id], kind="loyalty", delta=6)
    cast(s, "Curse of the Pierced Heart", ["p2"])
    to_phase(s, "upkeep", turn=2)
    if walker:
        d = s.state.rules.decision
        while d is None and s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
            d = s.state.rules.decision
        assert d is not None and d.player == "p1" and {o.id for o in d.options} == {"p2", gideon.id}  # Alice (the Aura's controller) chooses
        answer(s, [gideon.id])
        assert s.state.cards[gideon.id].counters.get("loyalty") == 5 and life(s, "p2") == 40
    else:
        answer(s)
        assert life(s, "p2") == 39
    check(s)


# -- Hateful Eidolon (603.10a) ------------------------------------------------------------------------------------------------------------------------------
def test_hateful_eidolon_draws_for_each_of_your_auras_on_the_creature_that_died(cards):
    s = build(cards, ["Hateful Eidolon", "Errantry", "Cunning"], ["Grizzly Bears", "Insubordination"])
    put(s, "Hateful Eidolon")
    bear = put(s, "Grizzly Bears", "p2")
    for name in ("Errantry", "Cunning"):
        aura = to_hand(s, name)
        act(s, "p1", type="move", card_ids=[aura.id], to={"player": "p1", "zone": "battlefield"})
        act(s, "p1", type="attach", card_ids=[aura.id], to=bear.id)
    theirs = to_hand(s, "Insubordination", "p2")
    act(s, "p2", type="move", card_ids=[theirs.id], to={"player": "p2", "zone": "battlefield"})
    act(s, "p2", type="attach", card_ids=[theirs.id], to=bear.id)
    hand = len(s.state.zones.get("p1:hand", []))
    act(s, "p1", type="set_damage", card_ids=[bear.id], value=9)
    act(s, "p1", type="pass_priority")
    answer(s)
    assert zone(s, bear) == "p2:graveyard" and len(s.state.zones.get("p1:hand", [])) == hand + 2  # Alice's two Auras, not Bob's
    check(s)


# -- Airtight Alibi (701.60), Infinite Coursework (722.3b) ----------------------------------------------------------------------------------------------------
def suspected(s, c):
    return s.state.rules.object_id(c.id) in s.state.rules.suspected


def test_airtight_alibi_clears_and_blocks_suspicion(cards):
    s = build(cards, ["Airtight Alibi", "Repeat Offender"])
    offender = put(s, "Repeat Offender")
    mana(s, B=1, C=2)
    act(s, "p1", type="activate_ability", card_id=offender.id, ability=0)  # "Otherwise, suspect it."
    pass_until_stack_empty(s)
    assert suspected(s, offender) and "menace" in ch(s, offender).keywords
    act(s, "p1", type="tap", card_ids=[offender.id], tapped=True)
    cast(s, "Airtight Alibi", [offender.id])
    assert not suspected(s, offender) and "menace" not in ch(s, offender).keywords  # "If it's suspected, it's no longer suspected."
    assert not s.state.cards[offender.id].tapped and "hexproof" in ch(s, offender).keywords and ch(s, offender).pt == (4, 3)
    mana(s, B=1, C=2)
    act(s, "p1", type="activate_ability", card_id=offender.id, ability=0)  # not suspected: "suspect it" — but it can't become suspected
    pass_until_stack_empty(s)
    assert not suspected(s, offender) and not s.state.cards[offender.id].counters.get("+1/+1")
    check(s)


PREPARED = card("Studious First-Year // Rampant Growth", set_code="w100f", number="P01", layout="prepare", mana_cost="{G} // {1}{G}", cmc=1.0,
                type_line="Creature — Bear Wizard // Sorcery", colors=["G"], color_identity=["G"], power="1", toughness="1",
                oracle_text="This creature enters prepared. (While it's prepared, you may cast a copy of its spell. Doing so unprepares "
                "it.)\n//\nSearch your library for a basic land card, put that card onto the battlefield tapped, then shuffle.",
                keywords=["Prepared"], card_faces=[
                    {"name": "Studious First-Year", "mana_cost": "{G}", "type_line": "Creature — Bear Wizard", "power": "1", "toughness": "1",
                     "oracle_text": "This creature enters prepared. (While it's prepared, you may cast a copy of its spell. Doing so unprepares it.)"},
                    {"name": "Rampant Growth", "mana_cost": "{1}{G}", "type_line": "Sorcery",
                     "oracle_text": "Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle."}])


def test_infinite_coursework_taps_and_unprepares(cards):
    s = build(cards, ["Infinite Coursework", "Studious First-Year // Rampant Growth"])
    first = to_hand(s, "Studious First-Year // Rampant Growth")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=first.id)
    pass_until_stack_empty(s)
    assert len(s.state.rules.prepared) == 1
    copy_id = next(iter(s.state.rules.prepared.values()))
    cast(s, "Infinite Coursework", [first.id])
    assert s.state.cards[first.id].tapped and s.state.rules.prepared == {}  # 722.3b
    act(s, "p1", type="pass_priority")  # 722.3c: the exiled copy no longer remains (704.5e)
    assert copy_id not in s.state.cards
    check(s)
