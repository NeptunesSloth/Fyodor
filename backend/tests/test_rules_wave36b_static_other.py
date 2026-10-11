"""Wave 36B: the `static_other` gaps that were one grammar piece each, researched against CR 2026-09-25, real Oracle text
(tests/fixtures/wave36b_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 613.1f, 611.3a: a static ability that grants to several groups ("Dion and other Knights you control", "Other snow and Zombie creatures you control",
  "Artifact creatures and Heroes you control") affects an object in any of them, once; under "During your turn" it is on during that turn only (500.1), under
  "During turns other than yours" during every other turn (Mesa Lynx, Glory of Warfare).
* "for each noncreature, nonland card in your graveyard", "for each creature and planeswalker card in your graveyard", "the number of untapped artifacts,
  creatures, and lands you control": one count of a list of kinds, each object counted once (the cards are read as they are now, 611.3a).
* 118.3, 602.2: "Tap two other untapped Halflings you control" taps two creatures other than the source and cannot be paid without them; "Tap three untapped
  Advisors, Artificers, and/or Monks you control" counts the source if it is one (it says no "other").
* 601.3: "You can't cast Rakdos unless an opponent lost life this turn." is a restriction on casting it (and 119.3: life lost by any means counts).
* 115.7d-e: "You may choose new targets for target spell or ability." (Deflecting Swat): each target is kept or changed to a legal one, the final set judged.
* "thirty or more artifacts" (number words), a pronoun for the card itself ("as he attacks", 701.43d exert), a shortened name that is also a creature type
  ("a green Lizard creature" on Lizard, Connors's Curse: 205.3m), "creatures without flying or reach" (neither).
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
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, ask, next_turn, priority_to, settle, stops, to_phase
from tests.wave9c_kit import build, card_named, cast, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave36b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w36b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
DION = "Dion, Bahamut's Dominant // Bahamut, Warden of Light"
FULL = [DION, "Yuna, Hope of Spira", "Miriam, Herd Whisperer", "Narfi, Betrayer King", "Cid, Timeless Artificer", "Xande, Dark Mage",
        "Winter, Tormented Loner", "Maraxus of Keld", "Saradoc, Master of Buckland", "The Archimandrite", "Rakdos, Lord of Riots",
        "Knuckles the Echidna", "Themberchaud", "Lizard, Connors's Curse", "Sidar Kondo of Jamuraa", "Mesa Lynx", "Glory of Warfare",
        "Blasphemous Edict", "Maha, Its Feathers Night", "Frodo, Determined Hero", "Sylvan Advocate", "Proft, Sinister Mastermind",
        "Stormtide Leviathan", "Deflecting Swat"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ch(s, name, pid="p1"):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id])


def keywords(s, name, pid="p1"):
    return ch(s, name, pid).keywords


def copies(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid]


def put_all(s, name, n, pid="p1"):
    """``n`` copies of a card onto the battlefield (the helper ``put`` always takes the first)."""
    cs = [c for c in copies(s, name, pid) if not c.zone.endswith(":battlefield")][:n]
    assert len(cs) == n
    act(s, pid, type="move", card_ids=[c.id for c in cs], to={"player": pid, "zone": "battlefield"})
    return cs


def to_gy(s, name, pid="p1", n=1):
    cs = [c for c in copies(s, name, pid) if not c.zone.endswith(":graveyard")][:n]
    assert len(cs) == n
    act(s, pid, type="move", card_ids=[c.id for c in cs], to={"zone": "graveyard"})
    return cs


def power_toughness(s, name, pid="p1"):
    return ch(s, name, pid).pt


# -- coverage ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", FULL)
def test_the_cards_are_full(cards, name):
    cov = coverage.of_card_data(cards.resolve(name))
    assert cov.level == "FULL", (name, [f.label for f in cov.features if not f.supported])


# -- Dion, Bahamut's Dominant: "During your turn, Dion and other Knights you control have flying." -------------------------------------
def test_dion_and_other_knights_you_control_fly_during_your_turn_only(cards):
    s = build(cards, [DION, "Youthful Knight", "Walking Corpse"], ["Youthful Knight"])
    put(s, DION)
    put(s, "Youthful Knight")
    put(s, "Walking Corpse")
    put(s, "Youthful Knight", "p2")
    assert "flying" in keywords(s, DION) and "flying" in keywords(s, "Youthful Knight")  # the source itself and another Knight
    assert "flying" not in keywords(s, "Walking Corpse") and "flying" not in keywords(s, "Youthful Knight", "p2")  # not a Knight; not "you control"
    to_phase(s, "main1", turn=2)
    assert "flying" not in keywords(s, DION) and "flying" not in keywords(s, "Youthful Knight")  # their turn (500.1): off
    to_phase(s, "main1", turn=3)
    assert "flying" in keywords(s, DION) and "flying" in keywords(s, "Youthful Knight")  # on again
    act(s, "p1", type="move", card_ids=[card_named(s, DION).id], to={"zone": "graveyard"})
    assert "flying" not in keywords(s, "Youthful Knight")  # the source left: the static is gone (611.3b)
    check(s)


# -- Yuna, Hope of Spira: "During your turn, Yuna and enchantment creatures you control have trample, lifelink, and ward {2}." ----------
def test_yuna_and_enchantment_creatures_get_trample_lifelink_and_ward_on_your_turn(cards):
    s = build(cards, ["Yuna, Hope of Spira", "Nyxborn Courser", "Walking Corpse"])
    put(s, "Yuna, Hope of Spira")
    put(s, "Nyxborn Courser")
    put(s, "Walking Corpse")
    for name in ("Yuna, Hope of Spira", "Nyxborn Courser"):
        assert {"trample", "lifelink"} <= keywords(s, name) and any("Ward {2}" in a.text for a in ch(s, name).abilities), name
    assert "trample" not in keywords(s, "Walking Corpse")
    to_phase(s, "main1", turn=2)
    assert "trample" not in keywords(s, "Nyxborn Courser") and not any("Ward" in a.text for a in ch(s, "Nyxborn Courser").abilities)
    check(s)


# -- Miriam, Herd Whisperer: "During your turn, Mounts and Vehicles you control have hexproof." ---------------------------------------
def test_miriam_gives_vehicles_hexproof_during_your_turn(cards):
    s = build(cards, ["Miriam, Herd Whisperer", "Honeymoon Hearse", "Walking Corpse"])
    put(s, "Miriam, Herd Whisperer")
    put(s, "Honeymoon Hearse")
    put(s, "Walking Corpse")
    assert "hexproof" in keywords(s, "Honeymoon Hearse") and "hexproof" not in keywords(s, "Walking Corpse")
    to_phase(s, "main1", turn=2)
    assert "hexproof" not in keywords(s, "Honeymoon Hearse")
    to_phase(s, "main1", turn=3)
    assert "hexproof" in keywords(s, "Honeymoon Hearse")
    check(s)


# -- Narfi, Betrayer King: "Other snow and Zombie creatures you control get +1/+1." ----------------------------------------------------
def test_narfi_pumps_other_snow_and_other_zombie_creatures_once(cards):
    s = build(cards, ["Narfi, Betrayer King", "Boreal Druid", "Walking Corpse", "Gutless Ghoul", "Elvish Mystic"], ["Walking Corpse"])
    put(s, "Boreal Druid")
    put(s, "Walking Corpse")
    put(s, "Gutless Ghoul")
    put(s, "Elvish Mystic")
    put(s, "Walking Corpse", "p2")
    base = {n: power_toughness(s, n) for n in ("Boreal Druid", "Walking Corpse", "Gutless Ghoul", "Elvish Mystic")}
    put(s, "Narfi, Betrayer King")
    assert power_toughness(s, "Boreal Druid") == (base["Boreal Druid"][0] + 1, base["Boreal Druid"][1] + 1)  # a snow creature
    assert power_toughness(s, "Walking Corpse") == (base["Walking Corpse"][0] + 1, base["Walking Corpse"][1] + 1)  # a Zombie
    assert power_toughness(s, "Gutless Ghoul") == (base["Gutless Ghoul"][0] + 1, base["Gutless Ghoul"][1] + 1)  # both: once
    assert power_toughness(s, "Elvish Mystic") == base["Elvish Mystic"]  # neither
    assert power_toughness(s, "Walking Corpse", "p2") == base["Walking Corpse"]  # not "you control"
    assert power_toughness(s, "Narfi, Betrayer King") == (4, 3)  # "other"
    act(s, "p1", type="move", card_ids=[card_named(s, "Narfi, Betrayer King").id], to={"zone": "graveyard"})
    assert {n: power_toughness(s, n) for n in base} == base
    check(s)


# -- Cid, Timeless Artificer: "Artifact creatures and Heroes you control get +1/+1 for each Artificer you control and each Artificer card in your graveyard." ---
def test_cid_pumps_artifact_creatures_and_heroes_for_each_artificer(cards):
    s = build(cards, ["Cid, Timeless Artificer", "Ornithopter", "Ant-Man, Scott Lang", "Grizzly Bears", "Sage of Lat-Nam", "Daring Mechanic"])
    put(s, "Ornithopter")
    put(s, "Ant-Man, Scott Lang")
    put(s, "Grizzly Bears")
    put(s, "Cid, Timeless Artificer")
    assert power_toughness(s, "Ornithopter") == (1, 3) and power_toughness(s, "Ant-Man, Scott Lang") == (3, 3)  # Cid is the one Artificer
    assert power_toughness(s, "Grizzly Bears") == (2, 2)  # neither an artifact creature nor a Hero
    to_gy(s, "Sage of Lat-Nam")
    assert power_toughness(s, "Ornithopter") == (2, 4)  # an Artificer card in your graveyard
    put(s, "Daring Mechanic")
    assert power_toughness(s, "Ornithopter") == (3, 5) and power_toughness(s, "Daring Mechanic") == (3, 3)  # an Artificer you control; not itself pumped
    act(s, "p1", type="move", card_ids=[card_named(s, "Cid, Timeless Artificer").id], to={"zone": "graveyard"})
    assert power_toughness(s, "Ornithopter") == (0, 2)
    check(s)


# -- Sylvan-style union with a condition: "As long as you control six or more lands, ~ and land creatures you control get +2/+2." (parse only) --
def test_a_union_of_the_source_and_a_group_under_a_condition_is_read():
    from app.rules import statics

    d = statics.parse("As long as you control six or more lands, ~ and land creatures you control get +2/+2.")
    assert d is not None and d["who"].startswith(statics.UNION) and d["p"] == 2 and d["conditions"]
    assert statics.parse("Skeletons you control and other Zombies you control can't block.") is None  # (a rule on a union: still not read)


# -- Xande, Dark Mage: "Xande gets +1/+1 for each noncreature, nonland card in your graveyard." ------------------------------------------
def test_xande_counts_noncreature_nonland_cards_in_your_graveyard(cards):
    s = build(cards, ["Xande, Dark Mage", "Lightning Bolt", "Sol Ring", "Counterspell", "Grizzly Bears", "Jace Beleren"])
    put(s, "Xande, Dark Mage")
    assert power_toughness(s, "Xande, Dark Mage") == (3, 3)
    for name in ("Lightning Bolt", "Sol Ring", "Jace Beleren"):
        to_gy(s, name)
    to_gy(s, "Grizzly Bears")  # a creature card
    to_gy(s, "Forest")  # a land card
    assert power_toughness(s, "Xande, Dark Mage") == (6, 6)  # an instant, an artifact, a planeswalker
    act(s, "p1", type="move", card_ids=[card_named(s, "Lightning Bolt").id], to={"zone": "exile"})
    assert power_toughness(s, "Xande, Dark Mage") == (5, 5)  # read as it is now (611.3a)
    check(s)


# -- Winter, Tormented Loner: "Winter gets +1/+0 for each creature and planeswalker card in your graveyard." ----------------------------
def test_winter_counts_creature_and_planeswalker_cards_in_your_graveyard(cards):
    s = build(cards, ["Winter, Tormented Loner", "Grizzly Bears", "Jace Beleren", "Lightning Bolt"])
    put(s, "Winter, Tormented Loner")
    settle(s)
    assert power_toughness(s, "Winter, Tormented Loner") == (0, 3)
    for name in ("Grizzly Bears", "Jace Beleren", "Lightning Bolt"):
        to_gy(s, name)
    to_gy(s, "Forest")
    assert power_toughness(s, "Winter, Tormented Loner") == (2, 3)
    act(s, "p1", type="move", card_ids=[card_named(s, "Grizzly Bears").id], to={"zone": "exile"})
    assert power_toughness(s, "Winter, Tormented Loner") == (1, 3)
    check(s)


# -- Maraxus of Keld: "Maraxus's power and toughness are each equal to the number of untapped artifacts, creatures, and lands you control." --
def test_maraxus_counts_each_untapped_artifact_creature_and_land_once(cards):
    s = build(cards, ["Maraxus of Keld", "Sol Ring", "Ornithopter"], forests=12)
    maraxus = put(s, "Maraxus of Keld")
    put(s, "Sol Ring")
    orni = put(s, "Ornithopter")
    forests = put_all(s, "Forest", 2)
    assert power_toughness(s, "Maraxus of Keld") == (5, 5)  # Maraxus, Sol Ring, Ornithopter (artifact creature: once), two Forests
    act(s, "p1", type="tap", card_ids=[forests[0].id], tapped=True)
    assert power_toughness(s, "Maraxus of Keld") == (4, 4)
    act(s, "p1", type="tap", card_ids=[orni.id], tapped=True)
    assert power_toughness(s, "Maraxus of Keld") == (3, 3)  # one fewer, not two
    act(s, "p1", type="tap", card_ids=[maraxus.id], tapped=True)
    assert power_toughness(s, "Maraxus of Keld") == (2, 2)
    check(s)


# -- Saradoc, Master of Buckland: "Tap two other untapped Halflings you control: Saradoc gets +2/+0 and gains lifelink until end of turn." ----
def test_saradoc_taps_two_other_halflings_and_not_himself(cards):
    s = build(cards, ["Saradoc, Master of Buckland", "Took Reaper", "Took Reaper"])
    to_hand(s, "Saradoc, Master of Buckland")
    mana(s, W=1, C=3)
    cast(s, "Saradoc, Master of Buckland")
    settle(s)  # his own trigger: one 1/1 Halfling token
    saradoc = card_named(s, "Saradoc, Master of Buckland")

    def others():
        return [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.id != saradoc.id and "Halfling" in ch(s, c.name, c.owner).subtypes]

    assert len(others()) == 1
    with pytest.raises(ActionError):
        activate(s, "p1", saradoc, "Tap two other")  # 118.3: only one other Halfling; Saradoc is no "other"
    assert not s.state.cards[saradoc.id].tapped
    to_hand(s, "Took Reaper")
    mana(s, W=2)
    cast(s, "Took Reaper")
    settle(s)  # a nontoken creature with power 2 or less entered: another token
    assert len(others()) == 3
    activate(s, "p1", saradoc, "Tap two other")
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and sorted(o.id for o in d.options) == sorted(c.id for c in others())  # Saradoc himself is no option
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:2])
    settle(s)
    assert not s.state.cards[saradoc.id].tapped and sum(1 for c in others() if s.state.cards[c.id].tapped) == 2
    assert power_toughness(s, "Saradoc, Master of Buckland") == (4, 4) and "lifelink" in keywords(s, "Saradoc, Master of Buckland")
    check(s)


# -- The Archimandrite: "Tap three untapped Advisors, Artificers, and/or Monks you control: Draw a card." ------------------------------
def test_the_archimandrite_taps_three_advisors_artificers_or_monks_itself_included(cards):
    s = build(cards, ["The Archimandrite", "Sage of Lat-Nam", "Daring Mechanic", "Grizzly Bears"])
    archimandrite = put(s, "The Archimandrite")
    put(s, "Sage of Lat-Nam")
    put(s, "Grizzly Bears")
    with pytest.raises(ActionError):
        activate(s, "p1", archimandrite, "Tap three")  # two of them: a bear is neither
    put(s, "Daring Mechanic")
    hand = len(s.state.zones["p1:hand"])
    activate(s, "p1", archimandrite, "Tap three")
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1
    assert all(s.state.cards[card_named(s, n).id].tapped for n in ("The Archimandrite", "Sage of Lat-Nam", "Daring Mechanic"))
    assert not s.state.cards[card_named(s, "Grizzly Bears").id].tapped
    check(s)


# -- Rakdos, Lord of Riots: "You can't cast Rakdos unless an opponent lost life this turn." ------------------------------------------
def test_rakdos_cannot_be_cast_until_an_opponent_lost_life_this_turn(cards):
    s = build(cards, ["Rakdos, Lord of Riots"])
    rakdos = to_hand(s, "Rakdos, Lord of Riots")
    mana(s, B=2, R=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=rakdos.id)
    assert s.state.cards[rakdos.id].zone == "p1:hand"
    act(s, "p1", type="life", player="p1", delta=-3)  # you losing life is not "an opponent"
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=rakdos.id)
    act(s, "p1", type="life", player="p2", delta=-1)
    cast(s, "Rakdos, Lord of Riots")
    assert s.state.cards[rakdos.id].zone == "p1:battlefield"
    check(s)


def test_rakdos_as_a_commander_is_held_to_the_same_restriction(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Rakdos, Lord of Riots", [(20, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(20, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    rakdos = card_named(s, "Rakdos, Lord of Riots")
    assert rakdos.zone == "p1:command"
    mana(s, B=2, R=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=rakdos.id)
    act(s, "p1", type="life", player="p2", delta=-2)
    act(s, "p1", type="cast_spell", card_id=rakdos.id)
    settle(s)
    assert s.state.cards[rakdos.id].zone == "p1:battlefield"
    check(s)


# -- Knuckles the Echidna: "At the beginning of your upkeep, if you control thirty or more artifacts, you win the game." -----------------
def test_knuckles_wins_the_game_with_thirty_artifacts(cards):
    s = build(cards, ["Knuckles the Echidna", *["Sol Ring"] * 30], forests=5)
    put(s, "Knuckles the Echidna")
    put_all(s, "Sol Ring", 29)
    to_phase(s, "main1", turn=3)
    assert s.state.rules.winner is None  # twenty-nine
    put_all(s, "Sol Ring", 1)  # the thirtieth
    for _ in range(300):  # play on to the next upkeep
        if s.state.rules.winner is not None:
            break
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.winner == "p1" and s.state.turn.number == 5 and s.state.turn.phase == "upkeep"
    check(s)


# -- Themberchaud: "You may exert Themberchaud as he attacks. When you do, he gains flying until end of turn." ---------------------------
def test_themberchaud_exerted_as_he_attacks_gains_flying(cards):
    s = build(cards, ["Themberchaud"], ["Walking Corpse"])
    them = put(s, "Themberchaud")
    settle(s)
    next_turn(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": them.id, "target": "p2"}])
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and [o.id for o in d.options] == [them.id]
    assert "flying" not in keywords(s, "Themberchaud")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[them.id])
    settle(s)
    assert "flying" in keywords(s, "Themberchaud")
    to_phase(s, "main1", turn=5)
    assert s.state.cards[them.id].tapped  # 701.43a: exerted, it did not untap during the next untap step
    check(s)


# -- Lizard, Connors's Curse: "… up to one other target creature loses all abilities and becomes a green Lizard creature with base power and toughness 4/4." --
def test_lizard_makes_another_creature_a_green_lizard_44_without_abilities(cards):
    s = build(cards, ["Lizard, Connors's Curse"], ["Leonin Skyhunter"])
    put(s, "Leonin Skyhunter", "p2")
    mana(s, G=2, C=2)
    to_hand(s, "Lizard, Connors's Curse")
    cast(s, "Lizard, Connors's Curse")
    settle(s)
    sky = ch(s, "Leonin Skyhunter", "p2")
    assert sky.pt == (4, 4) and "Lizard" in sky.subtypes and "G" in sky.colors and "flying" not in sky.keywords
    assert power_toughness(s, "Lizard, Connors's Curse") == (5, 5)
    check(s)


# -- Sidar Kondo of Jamuraa: "Creatures your opponents control without flying or reach can't block creatures with power 2 or less." -----------
def attacked_by_a_small_knight(cards, kondo=True):
    s = build(cards, ["Sidar Kondo of Jamuraa", "Youthful Knight"], ["Walking Corpse", "Leonin Skyhunter"])
    kondo_card = put(s, "Sidar Kondo of Jamuraa")
    knight = put(s, "Youthful Knight")
    corpse = put(s, "Walking Corpse", "p2")
    sky = put(s, "Leonin Skyhunter", "p2")
    if not kondo:
        act(s, "p1", type="move", card_ids=[kondo_card.id], to={"zone": "graveyard"})
    next_turn(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": knight.id, "target": "p2"}])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    return s, knight, corpse, sky


def test_sidar_kondo_stops_creatures_with_neither_flying_nor_reach_blocking_small_creatures(cards):
    s, knight, corpse, sky = attacked_by_a_small_knight(cards)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": corpse.id, "attacker_id": knight.id}])  # neither flying nor reach, power 2
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": sky.id, "attacker_id": knight.id}])  # flying: may
    check(s)


def test_without_sidar_kondo_the_same_creature_may_block(cards):
    s, knight, corpse, sky = attacked_by_a_small_knight(cards, kondo=False)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": corpse.id, "attacker_id": knight.id}])
    check(s)


# -- Sylvan Advocate: "As long as you control six or more lands, this creature and land creatures you control get +2/+2." (the source and a group, under a condition) --
def test_sylvan_advocate_and_land_creatures_get_the_bonus_with_six_lands(cards):
    s = build(cards, ["Sylvan Advocate", "Dryad Arbor", "Walking Corpse"], forests=14)
    put(s, "Sylvan Advocate")
    put(s, "Dryad Arbor")  # a land creature: it is one of the lands
    put(s, "Walking Corpse")
    put_all(s, "Forest", 4)  # five lands
    assert power_toughness(s, "Sylvan Advocate") == (2, 3) and power_toughness(s, "Dryad Arbor") == (1, 1)
    put_all(s, "Forest", 5)  # nine
    assert power_toughness(s, "Sylvan Advocate") == (4, 5) and power_toughness(s, "Dryad Arbor") == (3, 3)  # both
    assert power_toughness(s, "Walking Corpse") == (2, 2)  # neither itself nor a land
    check(s)


# -- Maha, Its Feathers Night: "Creatures your opponents control have base toughness 1." (613.4b: only the toughness is set) --------------------
def test_maha_sets_the_base_toughness_of_opposing_creatures_only(cards):
    s = build(cards, ["Maha, Its Feathers Night", "Walking Corpse"], ["Walking Corpse", "Grizzly Bears"])
    put(s, "Walking Corpse")
    bears = put(s, "Grizzly Bears", "p2")
    put(s, "Walking Corpse", "p2")
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=2)  # (4/4)
    put(s, "Maha, Its Feathers Night")
    assert power_toughness(s, "Walking Corpse", "p2") == (2, 1)  # power stays, toughness 1
    assert power_toughness(s, "Grizzly Bears", "p2") == (4, 3)  # counters modify the base (7c): 1 + 2
    assert power_toughness(s, "Walking Corpse") == (2, 2) and power_toughness(s, "Maha, Its Feathers Night") == (6, 5)
    act(s, "p1", type="move", card_ids=[card_named(s, "Maha, Its Feathers Night").id], to={"zone": "graveyard"})
    assert power_toughness(s, "Walking Corpse", "p2") == (2, 2) and power_toughness(s, "Grizzly Bears", "p2") == (4, 4)
    check(s)


# -- Frodo, Determined Hero: "During your turn, prevent all damage that would be dealt to Frodo." -----------------------------------------
def test_frodo_takes_no_damage_during_your_turn_only(cards):
    s = build(cards, ["Frodo, Determined Hero", "Lightning Bolt"], ["Lightning Bolt"])
    frodo = put(s, "Frodo, Determined Hero")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[frodo.id])  # on Alice's own turn: prevented (615.1)
    settle(s)
    assert s.state.cards[frodo.id].zone == "p1:battlefield" and s.state.cards[frodo.id].damage == 0
    to_phase(s, "main1", turn=2)
    theirs = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=theirs.id, targets=[frodo.id])  # on Bob's turn: the damage is dealt, a 2/2 dies
    settle(s)
    assert s.state.cards[frodo.id].zone == "p1:graveyard"
    check(s)


# -- Proft, Sinister Mastermind: "Threshold — You can't cast this spell unless there are seven or more cards in your graveyard." ----------------
def test_proft_needs_seven_cards_in_your_graveyard_to_be_cast(cards):
    s = build(cards, ["Proft, Sinister Mastermind"], forests=20)
    proft = to_hand(s, "Proft, Sinister Mastermind")
    mana(s, B=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=proft.id)
    to_gy(s, "Forest", n=6)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=proft.id)  # six
    to_gy(s, "Forest", n=1)
    cast(s, "Proft, Sinister Mastermind")
    assert s.state.cards[proft.id].zone == "p1:battlefield"
    check(s)


# -- Stormtide Leviathan: "Creatures without flying or islandwalk can't attack." ------------------------------------------------------------
def test_stormtide_leviathan_lets_only_flying_or_islandwalk_creatures_attack(cards):
    s = build(cards, ["Stormtide Leviathan", "Walking Corpse", "Leonin Skyhunter"])
    put(s, "Stormtide Leviathan")
    corpse = put(s, "Walking Corpse")
    sky = put(s, "Leonin Skyhunter")
    next_turn(s)
    to_phase(s, "declare_attackers")
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": corpse.id, "target": "p2"}])  # neither flying nor islandwalk
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": sky.id, "target": "p2"}])  # flying
    check(s)


# -- Mesa Lynx: "During turns other than yours, this creature gets +0/+2." / Glory of Warfare -----------------------------------------
def test_mesa_lynx_is_bigger_on_other_players_turns(cards):
    s = build(cards, ["Mesa Lynx", "Glory of Warfare", "Walking Corpse"])
    put(s, "Mesa Lynx")
    put(s, "Walking Corpse")
    assert power_toughness(s, "Mesa Lynx") == (2, 1)
    to_phase(s, "main1", turn=2)
    assert power_toughness(s, "Mesa Lynx") == (2, 3)  # the opponent's turn
    put(s, "Glory of Warfare")
    assert power_toughness(s, "Mesa Lynx") == (2, 5) and power_toughness(s, "Walking Corpse") == (2, 4)  # +0/+2 twice; (+2/+0 is for my turn)
    to_phase(s, "main1", turn=3)
    assert power_toughness(s, "Mesa Lynx") == (4, 1) and power_toughness(s, "Walking Corpse") == (4, 2)
    check(s)


# -- Deflecting Swat: "You may choose new targets for target spell or ability." (115.7d) -------------------------------------------------------
def swat_table(cards):
    s = build(cards, ["Deflecting Swat", "Grizzly Bears"], ["Lightning Bolt", "Walking Corpse"])
    stops(s)
    bears = put(s, "Grizzly Bears")
    corpse = put(s, "Walking Corpse", "p2")
    to_phase(s, "main1", turn=2)  # Bob's turn
    bolt = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=[bears.id])
    priority_to(s, "p1")
    swat = to_hand(s, "Deflecting Swat")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=swat.id, targets=[bolt.id])
    d = ask(s)
    assert d.player == "p1" and d.kind == "choose_one" and "keep" in [o.id for o in d.options]
    return s, bears, corpse, bolt, d


def test_deflecting_swat_sends_a_bolt_to_another_legal_target(cards):
    s, bears, corpse, bolt, d = swat_table(cards)
    assert corpse.id in [o.id for o in d.options] and bolt.id not in [o.id for o in d.options]  # 115.5: not the spell itself
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[corpse.id])
    settle(s)
    assert s.state.cards[corpse.id].zone == "p2:graveyard" and s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[bears.id].damage == 0
    check(s)


def test_deflecting_swat_may_keep_the_target(cards):
    s, bears, corpse, bolt, d = swat_table(cards)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["keep"])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard" and s.state.cards[corpse.id].zone == "p2:battlefield"
    check(s)
