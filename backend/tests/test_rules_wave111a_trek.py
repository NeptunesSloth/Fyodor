"""Wave 111A: Star Trek cards (trk/trc, pre-release Oracle text of 2026-10-30), family trigger_other, first half.

* The Star Trek creature types (Officer, Klingon, Borg …: the lead's shared block in creature_types.py, 205.3m pending its update) let the
  token lines and type selectors read: "a 1/1 colorless Borg artifact creature token", "Klingons and Warriors you control", "one or more Officers you
  control deal combat damage to a player", "attacking Klingons you control".
* "Search your library for a Spacecraft card, put it onto the battlefield with seven charge counters on it, then shuffle." (122.6: entry counters, so
  the station symbols apply as it enters, 721.2a-b).
* "create a tapped Planet land token named New Planet with "{T}: Add one mana of any color."" (David and Carol Marcus): wave 111D's grammar; those
  tests skip until it is merged.
* "Whenever you attack while creatures you control have total power 8 or greater, …" (wave 111G's events.py line, byte-identical here; judged as
  the attack happens).
* Rank and surname short names (201.5c, wave 111G's block): "Captain Archer", "Captain Janeway".
* "Whenever ~ or another creature you control enters, that creature explores." (701.44a: the entering creature explores).

Every scenario uses the real Oracle text and ends with ``check`` (replay and a save/load round trip).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, sba
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_conditionals import token_of, until
from tests.test_rules_wave15e_keywords import build3
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand


def trek(i, name, cost, cmc, types, text, pt=None, colors=""):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="w111a", number=f"A{i:02d}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), keywords=[], **extra)


RAW = [
    ("Assembly Specialist", "{1}{W}", 2, "Artifact Creature — Borg", "When this creature enters, create a 1/1 colorless Borg artifact creature token.", ("1", "1"), "W"),
    ("Captain Janeway, Endgame", "{1}{U}{R}{W}", 4, "Legendary Creature — Human Officer", "Whenever one or more Officers you control deal combat damage to a player, you draw a card and create a 1/1 red Officer creature token.\n{2}, Tap an untapped creature you control: Captain Janeway can't be blocked this turn.", ("3", "3"), "RUW"),
    ("Captain Jean-Luc Picard", "{2}{W}", 3, "Legendary Creature — Human Officer", "Other creatures you control get +1/+1.\nWhenever you cast a creature or Spacecraft spell, create a 1/1 red Officer creature token.\nTap seven untapped Officers you control: Search your library for a Spacecraft card, put it onto the battlefield with seven charge counters on it, then shuffle.", ("2", "3"), "W"),
    ("Captain Jonathan Archer", "{2}{G}", 3, "Legendary Creature — Human Officer", "When Captain Archer enters, create Porthos, a legendary 1/1 green Dog creature token.\nFederation — {G}, {T}: Target creature you control gets +X/+X until end of turn, where X is the number of creature types among non-Borg creatures you control. Activate only as a sorcery.", ("3", "3"), "G"),
    ("Captain Kathryn Janeway", "{3}{G}", 4, "Legendary Creature — Human Officer", "You may play an additional land on each of your turns.\nWhenever Captain Janeway or another creature you control enters, that creature explores. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on the creature, then put the card back or put it into your graveyard.)", ("2", "3"), "G"),
    ("Cha'DIch Investigator", "{4}{B}", 5, "Creature — Klingon Warrior", "When this creature enters, create a 2/1 red Klingon Warrior creature token with haste.", ("4", "4"), "B"),
    ("Class-4 Tactical Cube", "{4}", 4, "Artifact — Spacecraft", "When this Spacecraft enters, create two 1/1 colorless Borg artifact creature tokens.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 7+.)\n7+ | Flying\nArtifact creatures you control get +1/+1.", ("4", "4"), ""),
    ("David and Carol Marcus, Creators", "{2}{G}", 3, "Legendary Creature — Human Scientist", "When David and Carol Marcus enter, create a tapped Planet land token named New Planet with \"{T}: Add one mana of any color.\"", ("1", "3"), "G"),
    ("Georgiou, Terran Emperor", "{4}{B}{B}", 6, "Legendary Creature — Human Rogue Noble", "You don't lose the game for having 0 or less life.\nAt the beginning of your end step, you lose 3 life and draw a card. Then if your life total is 0 or less, create ten 1/1 red Officer creature tokens.", ("4", "6"), "B"),
    ("Glory to the Empire!", "{5}{R}", 6, "Enchantment", "When this enchantment enters, create a number of 2/1 red Klingon Warrior creature tokens with haste equal to the number of opponents you have.\nCreatures you control have melee. (Whenever a creature with melee attacks, it gets +1/+1 until end of turn for each opponent you attacked this combat.)", None, "R"),
    ("Gnarling Targ", "{4}{R}", 5, "Creature — Boar", "Trample\nWhenever you attack, Klingons and Warriors you control get +2/+0 and gain trample until end of turn.", ("4", "5"), "R"),
    ("Indelicate Healer", "{2}{W}", 3, "Creature — Klingon Warrior Doctor", "Whenever this creature or another Klingon or Warrior you control enters, creatures you control gain lifelink until end of turn.", ("3", "3"), "W"),
    ("K't'inga-Class Battle Cruiser", "{3}", 3, "Artifact — Spacecraft", "Whenever this Spacecraft enters or attacks, one or two target Klingons and/or Warriors you control gain flying until end of turn.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 4+.)\n4+ | Flying", ("5", "5"), ""),
    ("Kirk, Commanding Officer", "{1}{R}{W}", 3, "Legendary Creature — Human Officer", "Whenever you attack while creatures you control have total power 8 or greater, exile the top card of your library. You may play that card this turn.\n{2}, Sacrifice Kirk: Destroy target artifact or enchantment.", ("3", "3"), "RW"),
    ("Kruge, Genesis Seeker", "{2}{R}", 3, "Legendary Creature — Klingon Officer", "Whenever Kruge attacks, attacking Klingons you control get +1/+1 until end of turn.", ("2", "2"), "R"),
    ("L'Rell, Fierce Visionary", "{1}{B}{R}", 3, "Legendary Creature — Klingon Warrior", "At the beginning of combat on your turn, create a 2/1 red Klingon Warrior creature token with haste. Sacrifice it at the beginning of the next end step.\n{2}, Sacrifice another creature or artifact: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)", ("1", "4"), "BR"),
]
EXTRA = [trek(i, *row) for i, row in enumerate(RAW)]
EXTRA.append(trek(len(RAW), "Centaur Courser", "{2}{G}", 3, "Creature — Centaur Warrior", "", ("3", "3"), "G"))  # (a Warrior, no Klingon)
PROMOTED = ["Assembly Specialist", "Captain Janeway, Endgame", "Captain Jean-Luc Picard", "Captain Jonathan Archer", "Captain Kathryn Janeway",
            "Cha'DIch Investigator", "Class-4 Tactical Cube",
            "Georgiou, Terran Emperor", "Glory to the Empire!", "Gnarling Targ", "Indelicate Healer",
            "K't'inga-Class Battle Cruiser", "Kirk, Commanding Officer", "Kruge, Genesis Seeker", "L'Rell, Fierce Visionary"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", PROMOTED)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


STEPS = ["main1", "begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_combat", "main2", "end"]


# -- helpers ---------------------------------------------------------------------------------------------------------------------------
def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn (a list: several options), else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, targets=(), pid="p1", **kw):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    return c


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def pt(s, c):
    obj = s.state.cards[c.id]
    now = Plan(s.state, "p1", s.cards, None).ch(obj)
    return sba.power(obj, now), sba.toughness(obj, now)


def tok(s, name, type_line, power_toughness="1/1", pid="p1", text=""):
    return token_of(s, pid, name, type_line, power_toughness, text)


def tokens(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.token and c.name == name and c.zone == f"{pid}:battlefield"]


def ability(s, c, start):
    return next(a.index for a in ch(s, c).abilities if a.text.startswith(start))


def to_bottom(s, c, pid="p1"):
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "library"}, position="bottom")


def own_turn_3(s):
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)


def attack(s, *pairs):
    """Declare ``(creature, defender)`` attackers at the next declare attackers decision, then resolve the attack triggers."""
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in pairs])
    answer(s)


def library(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:library", []))


# -- tokens with the new creature types ------------------------------------------------------------------------------------------------
def test_assembly_specialist_makes_a_colorless_borg_artifact_creature(cards):
    s = build(cards, ["Assembly Specialist"])
    mana(s, W=1, C=1)
    cast(s, "Assembly Specialist")
    answer(s)
    [borg] = tokens(s, "Borg")
    now = ch(s, borg)
    assert (now.types, now.subtypes, now.colors, pt(s, borg)) == (frozenset({"Artifact", "Creature"}), frozenset({"Borg"}), frozenset(), (1, 1))
    check(s)


def test_chadich_investigator_makes_a_hasty_klingon_warrior(cards):
    s = build(cards, ["Cha'DIch Investigator"])
    mana(s, B=1, C=4)
    cast(s, "Cha'DIch Investigator")
    answer(s)
    [warrior] = tokens(s, "Klingon Warrior")
    now = ch(s, warrior)
    assert (now.subtypes, now.colors, pt(s, warrior), "haste" in now.keywords) == (frozenset({"Klingon", "Warrior"}), frozenset({"R"}), (2, 1), True)
    check(s)


def test_class4_tactical_cube_makes_two_borg_and_pumps_artifact_creatures_at_seven(cards):
    s = build(cards, ["Class-4 Tactical Cube"])
    mana(s, C=4)
    cube = cast(s, "Class-4 Tactical Cube")
    answer(s)
    borgs = tokens(s, "Borg")
    assert len(borgs) == 2 and all(pt(s, b) == (1, 1) for b in borgs)
    assert "Creature" not in ch(s, cube).types  # (no charge counters: 721.2b)
    big = tok(s, "Big Seven", "Token Creature — Giant", "7/7")
    act(s, "p1", type="activate_ability", card_id=cube.id, ability=ability(s, cube, "Tap another untapped creature"))
    answer(s, [big.id])
    assert s.state.cards[cube.id].counters.get("charge") == 7 and s.state.cards[big.id].tapped
    assert pt(s, cube) == (5, 5) and "flying" in ch(s, cube).keywords  # 4/4 artifact creature, +1/+1 from its own static (721.2a-b)
    assert all(pt(s, b) == (2, 2) for b in borgs) and pt(s, big) == (7, 7)  # (the Giant is no artifact)
    check(s)


# -- Captain Jean-Luc Picard -----------------------------------------------------------------------------------------------------------
def test_picard_makes_an_officer_for_creature_and_spacecraft_spells_only(cards):
    s = build(cards, ["Captain Jean-Luc Picard", "Grizzly Bears", "Class-4 Tactical Cube", "Glory to the Empire!"])
    picard = put(s, "Captain Jean-Luc Picard")
    mana(s, G=1, C=1)
    bears = cast(s, "Grizzly Bears")
    answer(s)
    assert len(tokens(s, "Officer")) == 1
    assert pt(s, bears) == (3, 3) and pt(s, picard) == (2, 3)  # "Other creatures you control get +1/+1."
    mana(s, C=4)
    cast(s, "Class-4 Tactical Cube")  # a Spacecraft spell (an artifact, no creature off the battlefield: 721.2c)
    answer(s)
    assert len(tokens(s, "Officer")) == 2
    mana(s, R=1, C=5)
    cast(s, "Glory to the Empire!")  # neither a creature nor a Spacecraft spell
    answer(s)
    assert len(tokens(s, "Officer")) == 2 and all(pt(s, o) == (2, 2) for o in tokens(s, "Officer"))
    check(s)


def _picard_crew(cards, officers):
    s = build(cards, ["Captain Jean-Luc Picard", "Class-4 Tactical Cube"])
    picard = put(s, "Captain Jean-Luc Picard")
    cube = card_named(s, "Class-4 Tactical Cube")
    to_bottom(s, cube)
    crew = [tok(s, f"Ensign {i}", "Token Creature — Human Officer") for i in range(officers)]
    return s, picard, cube, crew


def test_picard_fetches_a_spacecraft_with_seven_charge_counters(cards):
    s, picard, cube, crew = _picard_crew(cards, 6)
    before = library(s)
    act(s, "p1", type="activate_ability", card_id=picard.id, ability=ability(s, picard, "Tap seven untapped Officers"))
    answer(s, [cube.id])  # (exactly seven untapped Officers: all of them pay)
    assert s.state.cards[picard.id].tapped and all(s.state.cards[c.id].tapped for c in crew)
    assert s.state.cards[cube.id].zone == "p1:battlefield" and s.state.cards[cube.id].counters.get("charge") == 7  # 122.6
    assert library(s) == before - 1
    now = ch(s, cube)
    assert "Creature" in now.types and "flying" in now.keywords and pt(s, cube) == (6, 6)  # 4/4 (7+), +1/+1 Picard, +1/+1 its own static
    borgs = tokens(s, "Borg")  # its enters trigger
    assert len(borgs) == 2 and all(pt(s, b) == (3, 3) for b in borgs)
    check(s)


def test_picard_needs_seven_officers(cards):
    s, picard, _cube, _crew = _picard_crew(cards, 5)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=picard.id, ability=ability(s, picard, "Tap seven untapped Officers"))
    assert s.state.model_dump(mode="json") == before
    check(s)


# -- David and Carol Marcus --------------------------------------------------------------------------------------------------------------
# The token wording is wave 111D's (token_grammar.py); these run once that grammar is merged.
def _planet_grammar():
    from app.rules import token_grammar

    return token_grammar.parse('create a tapped Planet land token named New Planet with "{T}: Add one mana of any color."') is not None


NEEDS_D = pytest.mark.skipif(not _planet_grammar(), reason="waits for wave 111D's Planet land token grammar")


@NEEDS_D
def test_full_david_and_carol(cards):
    assert coverage.of_card_data(cards.resolve("David and Carol Marcus, Creators")).level == "FULL"


@NEEDS_D
def test_david_and_carol_make_a_tapped_new_planet_that_taps_for_any_color(cards):
    s = build(cards, ["David and Carol Marcus, Creators"])
    mana(s, G=1, C=2)
    cast(s, "David and Carol Marcus, Creators")
    answer(s)
    [planet] = tokens(s, "New Planet")
    now = ch(s, planet)
    assert (now.types, now.subtypes, now.colors, s.state.cards[planet.id].tapped) == (frozenset({"Land"}), frozenset({"Planet"}), frozenset(), True)
    own_turn_3(s)
    act(s, "p1", type="activate_ability", card_id=planet.id, ability=0)
    answer(s, ["3"])  # ({R})
    assert mana_pool(s) == {"R": 1}
    check(s)


# -- Georgiou, Terran Emperor ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("start", "officers"), [(40, 0), (4, 0), (3, 10)])
def test_georgiou_end_step(cards, start, officers):
    s = build(cards, ["Georgiou, Terran Emperor"])
    put(s, "Georgiou, Terran Emperor")
    act(s, "p1", type="set_life", player="p1", value=start)
    before = library(s)
    until(s, lambda s: s.state.turn.number == 2)
    assert life(s) == start - 3 and library(s) == before - 1
    assert len(tokens(s, "Officer")) == officers
    assert "p1" not in s.state.rules.lost  # "You don't lose the game for having 0 or less life." (704.5a)
    check(s)


# -- Glory to the Empire! ----------------------------------------------------------------------------------------------------------------
def test_glory_to_the_empire_one_klingon_per_opponent_and_melee(cards):
    s = build3(cards, "Glory to the Empire!")
    mana(s, R=1, C=5)
    cast(s, "Glory to the Empire!")
    answer(s)
    warriors = tokens(s, "Klingon Warrior")
    assert len(warriors) == 2 and all("haste" in ch(s, w).keywords and "melee" in ch(s, w).keywords for w in warriors)
    attack(s, (warriors[0], "p2"), (warriors[1], "p3"))
    assert all(pt(s, w) == (4, 3) for w in warriors)  # melee: two opponents attacked this combat (702.121a)
    check(s)


# -- Gnarling Targ -----------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("attacks", [True, False])
def test_gnarling_targ_pumps_klingons_and_warriors_when_you_attack(cards, attacks):
    s = build(cards, ["Gnarling Targ", "Grizzly Bears"])
    targ = put(s, "Gnarling Targ")
    bears = put(s, "Grizzly Bears")
    klingon = tok(s, "Kor'ak", "Token Creature — Klingon")
    warrior = tok(s, "Brute", "Token Creature — Human Warrior")
    own_turn_3(s)
    attack(s, *([(bears, "p2")] if attacks else []))
    bonus = 2 if attacks else 0
    assert (pt(s, klingon), pt(s, warrior)) == ((1 + bonus, 1), (1 + bonus, 1))
    assert ("trample" in ch(s, klingon).keywords, "trample" in ch(s, warrior).keywords) == (attacks, attacks)
    assert pt(s, bears) == (2, 2) and "trample" not in ch(s, bears).keywords and pt(s, targ) == (4, 5)
    check(s)


# -- Indelicate Healer -------------------------------------------------------------------------------------------------------------------
ENTERING = {"klingon": ("Kruge, Genesis Seeker", {"R": 1, "C": 2}), "warrior": ("Centaur Courser", {"G": 1, "C": 2}),
            "bear": ("Grizzly Bears", {"G": 1, "C": 1})}


@pytest.mark.parametrize(("who", "lifelink"), [("self", True), ("klingon", True), ("warrior", True), ("bear", False), ("their_klingon", False)])
def test_indelicate_healer(cards, who, lifelink):
    s = build(cards, ["Indelicate Healer", "Kruge, Genesis Seeker", "Centaur Courser", "Grizzly Bears"], ["Kruge, Genesis Seeker"])
    if who == "self":
        mana(s, W=1, C=2)
        healer = cast(s, "Indelicate Healer")
    else:
        healer = put(s, "Indelicate Healer")
        if who == "their_klingon":  # (an opponent's Klingon: not one "you control")
            until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
            mana(s, "p2", R=1, C=2)
            cast(s, "Kruge, Genesis Seeker", pid="p2")
        else:
            name, pool = ENTERING[who]
            mana(s, **pool)
            cast(s, name)
    answer(s)
    assert ("lifelink" in ch(s, healer).keywords) is lifelink
    check(s)


# -- K't'inga-Class Battle Cruiser -------------------------------------------------------------------------------------------------------
def test_ktinga_gives_flying_to_one_or_two_klingons_or_warriors(cards):
    s = build(cards, ["K't'inga-Class Battle Cruiser", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    klingon = tok(s, "Kor'ak", "Token Creature — Klingon")
    warrior = tok(s, "Brute", "Token Creature — Human Warrior")
    mana(s, C=3)
    cast(s, "K't'inga-Class Battle Cruiser")
    until(s, lambda s: s.state.rules.decision is not None)  # (its enters trigger: targets as it is put on the stack, 603.3d)
    d = s.state.rules.decision
    assert d is not None and {klingon.id, warrior.id} <= {o.id for o in d.options} and bears.id not in {o.id for o in d.options}
    answer(s, [klingon.id, warrior.id])
    assert "flying" in ch(s, klingon).keywords and "flying" in ch(s, warrior).keywords and "flying" not in ch(s, bears).keywords
    check(s)


def test_ktinga_attack_trigger_once_stationed(cards):
    s = build(cards, ["K't'inga-Class Battle Cruiser"])
    cruiser = put(s, "K't'inga-Class Battle Cruiser")
    hauler = tok(s, "Hauler", "Token Creature \u2014 Human Soldier", "4/4")
    klingon = tok(s, "Kor'ak", "Token Creature \u2014 Klingon")
    act(s, "p1", type="activate_ability", card_id=cruiser.id, ability=ability(s, cruiser, "Tap another untapped creature"))
    answer(s, [hauler.id])
    assert s.state.cards[cruiser.id].counters.get("charge") == 4 and pt(s, cruiser) == (5, 5)  # an artifact creature at 4+
    own_turn_3(s)
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": cruiser.id, "target": "p2"}])
    answer(s, [klingon.id])
    assert "flying" in ch(s, klingon).keywords
    check(s)


# -- Kirk, Commanding Officer ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("other", "fires"), [("5/5", True), ("4/4", False)])
def test_kirk_impulse_draws_when_you_attack_with_total_power_8(cards, other, fires):
    s = build(cards, ["Kirk, Commanding Officer"])
    kirk = put(s, "Kirk, Commanding Officer")
    tok(s, "Muscle", "Token Creature — Human Soldier", other)  # Kirk's 3 power plus this one's: 8 or 7
    own_turn_3(s)
    before = len(s.state.zones.get("p1:exile", []))
    attack(s, (kirk, "p2"))
    exiled = s.state.zones.get("p1:exile", [])
    assert len(exiled) == before + (1 if fires else 0)
    if fires:
        land = s.state.cards[exiled[-1]]
        assert land.name == "Forest"
        until(s, lambda s: s.state.turn.phase == "main2")
        act(s, "p1", type="play_land", card_id=land.id)  # "You may play that card this turn."
        assert s.state.cards[land.id].zone == "p1:battlefield"
    check(s)


# -- Kruge, Genesis Seeker ---------------------------------------------------------------------------------------------------------------
def test_kruge_pumps_attacking_klingons(cards):
    s = build(cards, ["Kruge, Genesis Seeker", "Grizzly Bears"])
    kruge = put(s, "Kruge, Genesis Seeker")
    bears = put(s, "Grizzly Bears")
    raider = tok(s, "Raider", "Token Creature — Klingon")
    home = tok(s, "Homeguard", "Token Creature — Klingon")
    own_turn_3(s)
    attack(s, (kruge, "p2"), (raider, "p2"), (bears, "p2"))
    assert (pt(s, kruge), pt(s, raider), pt(s, home), pt(s, bears)) == ((3, 3), (2, 2), (1, 1), (2, 2))
    check(s)


# -- L'Rell, Fierce Visionary ------------------------------------------------------------------------------------------------------------
def test_lrell_makes_a_klingon_each_combat_and_sacrifices_it_at_the_end_step(cards):
    s = build(cards, ["L'Rell, Fierce Visionary"])
    put(s, "L'Rell, Fierce Visionary")
    until(s, lambda s: s.state.turn.phase == "declare_attackers" or (s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers"))
    [warrior] = tokens(s, "Klingon Warrior")
    assert "haste" in ch(s, warrior).keywords and pt(s, warrior) == (2, 1)
    until(s, lambda s: s.state.turn.number == 2)
    assert tokens(s, "Klingon Warrior") == []  # sacrificed at the beginning of the next end step
    check(s)


def test_lrell_surveils_for_a_sacrificed_creature(cards):
    s = build(cards, ["L'Rell, Fierce Visionary", "Grizzly Bears"])
    lrell = put(s, "L'Rell, Fierce Visionary")
    bears = put(s, "Grizzly Bears")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=lrell.id, ability=ability(s, lrell, "{2}, Sacrifice another"))  # (the Bears: the only other one)
    assert s.state.cards[bears.id].zone == "p1:graveyard" and s.state.cards[lrell.id].zone == "p1:battlefield"
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.kind == "choose_cards" and len(d.options) == 1  # surveil 1: the top card (701.25a)
    seen = d.options[0].id
    answer(s, [seen])
    assert s.state.cards[seen].zone == "p1:graveyard"
    check(s)


# -- Captain Janeway, Endgame ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("officers", [True, False])
def test_janeway_endgame_draws_and_makes_an_officer_once(cards, officers):
    s = build(cards, ["Captain Janeway, Endgame", "Grizzly Bears"])
    janeway = put(s, "Captain Janeway, Endgame")
    bears = put(s, "Grizzly Bears")
    ensign = tok(s, "Ensign", "Token Creature — Human Officer")
    own_turn_3(s)
    hand = len(s.state.zones["p1:hand"])
    attack(s, *([(janeway, "p2"), (ensign, "p2")] if officers else [(bears, "p2")]))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert life(s, "p2") == 40 - (4 if officers else 2)
    assert len(s.state.zones["p1:hand"]) == hand + (1 if officers else 0)  # one trigger for the batch (603.2c)
    assert len(tokens(s, "Officer")) == (1 if officers else 0)
    check(s)


def test_janeway_endgame_triggers_once_per_player_dealt_damage(cards):
    s = build3(cards, "Captain Janeway, Endgame")
    janeway = put(s, "Captain Janeway, Endgame")
    ensign = tok(s, "Ensign", "Token Creature \u2014 Human Officer")
    tok(s, "Lieutenant", "Token Creature \u2014 Human Officer")
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)  # (Alice's next turn)
    hand = len(s.state.zones["p1:hand"])
    attack(s, (janeway, "p2"), (ensign, "p3"))  # (the Lieutenant stays home)
    until(s, lambda s: s.state.turn.phase == "main2")
    assert (life(s, "p2"), life(s, "p3")) == (37, 39)
    assert len(s.state.zones["p1:hand"]) == hand + 2 and len(tokens(s, "Officer")) == 2  # one batch per player dealt the damage
    check(s)


def test_janeway_endgame_cant_be_blocked_after_tapping_a_creature(cards):
    s = build(cards, ["Captain Janeway, Endgame", "Grizzly Bears"])
    janeway = put(s, "Captain Janeway, Endgame")
    bears = put(s, "Grizzly Bears")
    guard = tok(s, "Guard", "Token Creature — Human Soldier", "2/2", pid="p2")
    own_turn_3(s)
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=janeway.id, ability=ability(s, janeway, "{2}, Tap an untapped"))
    answer(s, [bears.id])
    assert s.state.cards[bears.id].tapped
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": janeway.id, "target": "p2"}])
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": guard.id, "attacker_id": janeway.id}])
    act(s, "p2", type="declare_blockers", blocks=[])
    until(s, lambda s: s.state.turn.phase == "main2")
    assert life(s, "p2") == 37
    check(s)


# -- Captain Jonathan Archer (201.5c: "Captain Archer" is the card itself) -------------------------------------------------------------------
def test_archer_makes_porthos(cards):
    s = build(cards, ["Captain Jonathan Archer"])
    mana(s, G=1, C=2)
    cast(s, "Captain Jonathan Archer")
    answer(s)
    [porthos] = tokens(s, "Porthos")
    now = ch(s, porthos)
    assert (now.supertypes, now.subtypes, now.colors, pt(s, porthos)) == (frozenset({"Legendary"}), frozenset({"Dog"}), frozenset({"G"}), (1, 1))
    check(s)


@pytest.mark.parametrize(("borg", "x"), [(False, 4), (True, 3)])
def test_archer_federation_counts_creature_types_of_non_borg_creatures(cards, borg, x):
    s = build(cards, ["Captain Jonathan Archer", "Grizzly Bears"])
    archer = put(s, "Captain Jonathan Archer")  # Human Officer
    bears = put(s, "Grizzly Bears")  # Bear
    tok(s, "Unit", "Token Artifact Creature \u2014 Borg Drone" if borg else "Token Creature \u2014 Drone")  # (a Borg's types don't count, not even Drone)
    own_turn_3(s)
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=archer.id, ability=ability(s, archer, "Federation"), targets=[bears.id])
    answer(s)
    assert pt(s, bears) == (2 + x, 2 + x) and s.state.cards[archer.id].tapped
    check(s)


def test_archer_federation_only_as_a_sorcery(cards):
    s = build(cards, ["Captain Jonathan Archer"])
    archer = put(s, "Captain Jonathan Archer")
    own_turn_3(s)
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: s.state.turn.phase == "begin_combat" and s.state.rules.priority == "p1")
    mana(s, G=1)
    with pytest.raises(ActionError, match="(?i)sorcery"):  # (602.5d: a main phase of its controller's turn, with an empty stack)
        act(s, "p1", type="activate_ability", card_id=archer.id, ability=ability(s, archer, "Federation"), targets=[archer.id])
    check(s)


# -- Captain Kathryn Janeway -------------------------------------------------------------------------------------------------------------
def on_top(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library")
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")
    return c


@pytest.mark.parametrize("top", ["Forest", "Centaur Courser"])
def test_kathryn_janeway_explores_as_she_enters(cards, top):
    s = build(cards, ["Captain Kathryn Janeway", "Centaur Courser"])
    revealed = on_top(s, top)
    mana(s, G=1, C=3)
    janeway = cast(s, "Captain Kathryn Janeway")
    answer(s, ["graveyard"])  # (a nonland card: put into the graveyard)
    if top == "Forest":
        assert s.state.cards[revealed.id].zone == "p1:hand" and not s.state.cards[janeway.id].counters.get("+1/+1")
    else:
        assert s.state.cards[revealed.id].zone == "p1:graveyard" and s.state.cards[janeway.id].counters.get("+1/+1") == 1
    check(s)


@pytest.mark.parametrize("whose", ["p1", "p2"])
def test_kathryn_janeway_another_creature_explores(cards, whose):
    s = build(cards, ["Captain Kathryn Janeway", "Grizzly Bears", "Centaur Courser"], ["Grizzly Bears"])
    janeway = put(s, "Captain Kathryn Janeway")
    revealed = on_top(s, "Centaur Courser")
    if whose == "p2":
        until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    mana(s, whose, G=1, C=1)
    bears = cast(s, "Grizzly Bears", pid=whose)
    answer(s)  # (the revealed card stays on top: the first option, none to the graveyard)
    assert s.state.cards[bears.id].counters.get("+1/+1", 0) == (1 if whose == "p1" else 0)  # the entering creature explores, not Janeway
    assert not s.state.cards[janeway.id].counters.get("+1/+1") and s.state.cards[revealed.id].zone == "p1:library"
    check(s)


def test_kathryn_janeway_plays_an_additional_land(cards):
    s = build(cards, ["Captain Kathryn Janeway"])
    put(s, "Captain Kathryn Janeway")
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:3]
    act(s, "p1", type="move", card_ids=[f.id for f in forests], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=forests[0].id)
    act(s, "p1", type="play_land", card_id=forests[1].id)
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=forests[2].id)
    assert [s.state.cards[f.id].zone for f in forests] == ["p1:battlefield", "p1:battlefield", "p1:hand"]
    check(s)
