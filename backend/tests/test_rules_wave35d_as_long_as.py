"""Wave 35D: conditions of "as long as" statics that read the table and the source (CR 604.1-604.3, 611.3a, 613, 613.5), real Oracle text
(tests/fixtures/wave35d_cards.json, from data/cards.sqlite). Every scenario shows the condition becoming true and then false in the same game, with
the effect applied and removed (611.3a: a static ability applies at any moment its condition is true, never locked in), and checks the replay and
a save and a load.

* 701.54e: "As long as ~ is your Ring-bearer" (Frodo Baggins); 301.5, 303.4: the Equipment or Auras attached to it or to the creature it is
  attached to ("two or more Equipment are attached to it": Balan, Brass Knuckles; "enchanted by exactly one Aura": Timber Paladin; "another Aura is
  attached to enchanted creature": Face of Divinity); 120.3: "hasn't dealt (combat) damage yet" (Palladia-Mors, Ruric Thar, Karakyk Guardian: since
  it became this object, 400.7); 608.3: "as long as it was cast" (The Tarrasque).
* 201.2 / 205.3h: "a permanent named A or a permanent named B" (Liu Bei), "an artifact creature or a Plan" (Doctor Doom), "a commander that's a
  creature or planeswalker" (Gray Harbor Merfolk); 404.1, 406.1, 701.27g, 709.5, 509.1: counts of cards and states (Swimmer in Nightmares, Warden of
  the Beyond, Howling Galefang, Oculus Whelp, Rampaging Cyclops, Tenacious Hunter).
* The object the Aura is attached to (Security Bypass, Snow Devil, Goblin Caves), a group that is only the ones not attacking (Arcades Sabboth), the
  one creature you control (Homicidal Seclusion), the top of the library (Verge Rangers, The Reality Chip) and a spell's own flash (Crashing Tide).
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
from tests.test_rules_attachments import ch
from tests.test_rules_conditionals import settle, until
from tests.wave9c_kit import build, card_named, cast, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave35d_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w35d", number=f"D{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Sting, the Glinting Dagger", "Frodo Baggins", "Balan, Wandering Knight", "Brass Knuckles", "Timber Paladin", "Face of Divinity", "Palladia-Mors, the Ruiner",
        "Ruric Thar, Magecrusher", "Karakyk Guardian", "The Tarrasque", "Doctor Doom", "Liu Bei, Lord of Shu", "Gray Harbor Merfolk",
        "Swimmer in Nightmares", "Warden of the Beyond", "Howling Galefang", "Oculus Whelp", "Rampaging Cyclops", "Tenacious Hunter",
        "Rampaging Soulrager", "Security Bypass", "Snow Devil", "Goblin Caves", "Arcades Sabboth", "Homicidal Seclusion", "Verge Rangers",
        "The Reality Chip", "Crashing Tide", "Supernatural Rescue", "The Wondrous Wasp", "Hobble", "Augur of Autumn",
        "Summoning Materia", "Scarring Memories", "Captain America, Super-Soldier", "Conqueror's Flail", "Thunderstaff", "Hedron-Field Purists",
        "Spirit of Resistance", "Aether Revolt", "Anthem of Rakdos", "Vampire Socialite", "Merfolk Trickster", "Gutter Skulker // Gutter Shortcut", "Goblin Shrine", "Deadly Wanderings", "Bronze Horse"]


# Refused, not guessed: each stays manual until its rule is modelled.
# * Croakid Amphibonaut: "a stickered permanent" (stickers are not modelled: no permanent is ever stickered, so the line can't be read);
# * Manor Gargoyle, Warmonger's Chariot: a condition on the keywords of the very object it modifies (613.8: dependencies between layer-6 effects);
# * Grond: a layer-4 type change whose condition reads other permanents' creature types (613.8, app/rules/statics.py ``_layer4_safe``);
# * (Cloud, Midgar Mercenary - a trigger multiplier read with last known information (603.10) under a condition - is read since wave 43A: test_rules_wave43a_trigger_multipliers.py)
# * (Archelos - "enter tapped" and "enter untapped" replacements whose order the affected permanent's controller chooses (616.1) - is read since wave 49B, as Horizon Explorer's
#   "enter untapped" is (wave 45A): the permanent's controller takes untapped: test_rules_wave49b_commanders.py)
# * (Sting - "blocking or blocked by a Goblin or Orc", a relation between the equipped creature and the creature it fights - is read since wave 45A: test_rules_wave45a_attacked.py)
# Bronze Horse now has canonical spell-target/other-creature gameplay in test_rules_conditional_prevention.py.
MANUAL = ["Croakid Amphibonaut", "Manor Gargoyle", "Warmonger's Chariot", "Grond, the Gatebreaker"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def token(s, pid, name, pt="2/2", type_line="Token Creature — Test", colors=()):
    before = set(s.state.cards)
    p, t = pt.split("/") if pt else (None, None)
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": type_line, "power": p, "toughness": t, "text": "", "colors": list(colors)})
    return next(c for cid, c in s.state.cards.items() if cid not in before)


def of(s, c):
    return ch(s, c)


def kw(s, c):
    return of(s, c).keywords


def pt(s, c):
    return of(s, c).pt


def attach(s, aura, host):
    act(s, "p1", type="attach", card_ids=[aura.id], to=host.id)


def detach(s, *things):
    act(s, "p1", type="detach", card_ids=[t.id for t in things])


def unready(s, c):
    s.state.rules.controlled_since[c.id].turn = 0  # (there since before the turn: no summoning sickness)


def to_attack(s):
    until(s, lambda s: s.state.turn.number == 1 and s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers",
          limit=60)


def through_combat(s):
    """Play on to the second main phase (nobody blocks)."""
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


def attack_and_hit(s, c):
    to_attack(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"}])
    through_combat(s)


# -- coverage ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", FULL)
def test_the_conditional_statics_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


@pytest.mark.parametrize("name", MANUAL)
def test_the_refused_conditional_statics_stay_manual(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level != "FULL", name


# -- 701.54e: the Ring-bearer ---------------------------------------------------------------------------------------
def test_frodo_must_be_blocked_only_while_he_is_the_ring_bearer(cards):
    s = build(cards, mine=("Frodo Baggins", "Isamaru, Hound of Konda"))
    to_hand(s, "Frodo Baggins")
    mana(s, G=1, W=1)
    cast(s, "Frodo Baggins")  # "Whenever Frodo Baggins … enters, the Ring tempts you": he is the only creature, so he is the Ring-bearer (701.54a)
    frodo = card_named(s, "Frodo Baggins")
    assert s.state.rules.ring_bearers["p1"] == s.state.rules.object_id(frodo.id)
    assert "must_be_blocked" in of(s, frodo).imposed
    isamaru = to_hand(s, "Isamaru, Hound of Konda")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=isamaru.id)  # another legendary creature: the Ring tempts you again, and you choose the Ring-bearer
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.card_id == isamaru.id])
    settle(s)
    assert s.state.rules.ring_bearers["p1"] == s.state.rules.object_id(isamaru.id)
    assert "must_be_blocked" not in of(s, frodo).imposed  # 611.3a: it ended with the condition
    check(s)


# -- 301.5, 303.4: what is attached ---------------------------------------------------------------------------------
def test_balan_and_brass_knuckles_have_double_strike_while_two_equipment_are_attached(cards):
    s = build(cards, mine=("Balan, Wandering Knight", "Brass Knuckles", "Bonesplitter"))
    balan, knuckles, splitter = put(s, "Balan, Wandering Knight"), put(s, "Brass Knuckles"), put(s, "Bonesplitter")
    assert kw(s, balan) == {"first strike"}
    attach(s, splitter, balan)
    assert "double strike" not in kw(s, balan)  # one Equipment
    attach(s, knuckles, balan)
    assert "double strike" in kw(s, balan) and pt(s, balan) == (5, 3)  # Balan's own, and Brass Knuckles' (the equipped creature has it too)
    detach(s, splitter)
    assert "double strike" not in kw(s, balan)  # 611.3a: one Equipment again, so neither grant applies
    attach(s, splitter, balan)
    assert "double strike" in kw(s, balan)
    check(s)


def test_brass_knuckles_gives_its_double_strike_to_the_equipped_creature_only_with_a_second_equipment(cards):
    s = build(cards, mine=("Brass Knuckles", "Bonesplitter", "Balan, Wandering Knight"))
    knuckles, splitter = put(s, "Brass Knuckles"), put(s, "Bonesplitter")
    bear = token(s, "p1", "Bear")
    attach(s, knuckles, bear)
    assert "double strike" not in kw(s, bear)
    attach(s, splitter, bear)
    assert "double strike" in kw(s, bear) and pt(s, bear) == (4, 2)
    other = token(s, "p1", "Other")
    attach(s, splitter, other)  # the second Equipment moves to another creature
    assert "double strike" not in kw(s, bear) and "double strike" not in kw(s, other)
    check(s)


def test_timber_paladin_grows_with_the_number_of_auras_enchanting_it(cards):
    s = build(cards, mine=("Timber Paladin", "Holy Strength", "Pacifism", "Face of Divinity"))
    paladin = put(s, "Timber Paladin")
    strength, pacifism, face = put(s, "Holy Strength"), put(s, "Pacifism"), put(s, "Face of Divinity")
    assert pt(s, paladin) == (1, 1) and "vigilance" not in kw(s, paladin)
    attach(s, strength, paladin)
    assert pt(s, paladin) == (4, 5)  # base 3/3 (exactly one Aura) and Holy Strength's +1/+2
    attach(s, pacifism, paladin)
    assert pt(s, paladin) == (6, 7) and "vigilance" in kw(s, paladin)  # base 5/5 (exactly two)
    attach(s, face, paladin)
    assert pt(s, paladin) == (13, 14) and {"vigilance", "trample"} <= kw(s, paladin)  # base 10/10 (three or more), +1/+2 and +2/+2
    assert {"first strike", "lifelink"} <= kw(s, paladin)  # Face of Divinity: another Aura is attached to enchanted creature
    detach(s, strength, pacifism, face)
    assert pt(s, paladin) == (1, 1) and not kw(s, paladin)
    check(s)


def test_face_of_divinity_needs_another_aura_on_the_creature(cards):
    s = build(cards, mine=("Face of Divinity", "Holy Strength"))
    face, strength = put(s, "Face of Divinity"), put(s, "Holy Strength")
    bear = token(s, "p1", "Bear")
    attach(s, face, bear)
    assert pt(s, bear) == (4, 4) and not kw(s, bear)  # +2/+2 alone
    attach(s, strength, bear)
    assert pt(s, bear) == (5, 6) and {"first strike", "lifelink"} <= kw(s, bear)
    other = token(s, "p1", "Other")
    attach(s, strength, other)  # the other Aura is on another creature now
    assert not kw(s, bear) and not kw(s, other)
    check(s)


# -- 120.3: "hasn't dealt damage yet" ---------------------------------------------------------------------------------------
def test_palladia_mors_loses_hexproof_for_good_once_it_has_dealt_damage(cards):
    s = build(cards, mine=("Palladia-Mors, the Ruiner",))
    pal = put(s, "Palladia-Mors, the Ruiner")
    unready(s, pal)
    assert "hexproof" in kw(s, pal)
    attack_and_hit(s, pal)
    assert s.state.players["p2"].life == 40 - 6
    assert "hexproof" not in kw(s, pal)  # it has dealt damage (to a player)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1", limit=200)
    assert "hexproof" not in kw(s, pal)  # and it isn't "yet" any more, whatever turn it is
    check(s)
    to_hand(s, "Palladia-Mors, the Ruiner")
    again = put(s, "Palladia-Mors, the Ruiner")
    assert "hexproof" in kw(s, again)  # 400.7: a new object that hasn't dealt damage
    check(s)


def test_karakyk_guardian_counts_damage_to_a_creature_and_ruric_thar_only_combat_damage(cards):
    s = build(cards, mine=("Karakyk Guardian", "Ruric Thar, Magecrusher", "Prey Upon"))
    karakyk, ruric = put(s, "Karakyk Guardian"), put(s, "Ruric Thar, Magecrusher")
    victim = token(s, "p2", "Victim", "1/99")
    assert "hexproof" in kw(s, karakyk) and "hexproof" in kw(s, ruric)
    to_hand(s, "Prey Upon")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Prey Upon").id, targets=[ruric.id, victim.id], target_counts=[1, 1])
    settle(s)  # Ruric Thar fights: noncombat damage
    assert "hexproof" in kw(s, ruric)  # "combat damage" only
    to_hand(s, "Prey Upon")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Prey Upon").id, targets=[karakyk.id, victim.id], target_counts=[1, 1])
    settle(s)
    assert "hexproof" not in kw(s, karakyk)  # damage of any kind
    unready(s, ruric)
    attack_and_hit(s, ruric)
    assert "hexproof" not in kw(s, ruric)
    check(s)


# -- 608.3: "as long as it was cast" ------------------------------------------------------------------------------------------
def test_the_tarrasque_has_haste_and_ward_only_if_it_was_cast(cards):
    s = build(cards, mine=("The Tarrasque",))
    tarrasque = to_hand(s, "The Tarrasque")
    mana(s, G=9)
    act(s, "p1", type="cast_spell", card_id=tarrasque.id)
    settle(s)
    here = card_named(s, "The Tarrasque")
    assert here.zone == "p1:battlefield" and "haste" in kw(s, here) and "ward" in kw(s, here)
    to_hand(s, "The Tarrasque")
    again = put(s, "The Tarrasque")  # not cast: put onto the battlefield from the hand by hand
    assert "haste" not in kw(s, again) and "ward" not in kw(s, again)
    check(s)


# -- 201.2, 205.3h: "you control X or Y" --------------------------------------------------------------------------------------
def test_doctor_doom_is_indestructible_with_an_artifact_creature_or_a_plan(cards):
    s = build(cards, mine=("Doctor Doom", "Rewrite History"))
    doom = put(s, "Doctor Doom")
    assert "indestructible" not in kw(s, doom)
    robot = token(s, "p1", "Doombot", "3/3", "Token Artifact Creature — Robot Villain")
    assert "indestructible" in kw(s, doom)  # an artifact creature
    act(s, "p1", type="move", card_ids=[robot.id], to={"player": "p1", "zone": "graveyard"})
    assert "indestructible" not in kw(s, doom)  # 611.3a: it ended with the condition
    plan = put(s, "Rewrite History")
    assert "indestructible" in kw(s, doom)  # a Plan (an enchantment type, 205.3h)
    token(s, "p2", "Their Robot", "3/3", "Token Artifact Creature — Robot")
    act(s, "p1", type="move", card_ids=[plan.id], to={"player": "p1", "zone": "graveyard"})
    assert "indestructible" not in kw(s, doom)  # their artifact creature is not one "you control"
    check(s)


def test_liu_bei_grows_with_either_named_sworn_brother(cards):
    s = build(cards, mine=("Liu Bei, Lord of Shu", "Guan Yu, Sainted Warrior", "Zhang Fei, Fierce Warrior"), theirs=("Guan Yu, Sainted Warrior",))
    liu = put(s, "Liu Bei, Lord of Shu")
    assert pt(s, liu) == (2, 4)
    put(s, "Guan Yu, Sainted Warrior", "p2")
    assert pt(s, liu) == (2, 4)  # "a permanent" you control: not theirs
    guan = put(s, "Guan Yu, Sainted Warrior")
    assert pt(s, liu) == (4, 6)
    zhang = put(s, "Zhang Fei, Fierce Warrior")
    assert pt(s, liu) == (4, 6)  # one "+2/+2 as long as", not one for each
    act(s, "p1", type="move", card_ids=[guan.id], to={"player": "p1", "zone": "graveyard"})
    assert pt(s, liu) == (4, 6)  # Zhang Fei is enough
    act(s, "p1", type="move", card_ids=[zhang.id], to={"player": "p1", "zone": "graveyard"})
    assert pt(s, liu) == (2, 4)
    check(s)


def test_gray_harbor_merfolk_counts_your_commander_while_it_is_a_creature_on_the_battlefield(cards):
    s = build(cards, mine=("Gray Harbor Merfolk", "Grizzly Bears"))
    merfolk = put(s, "Gray Harbor Merfolk")
    assert pt(s, merfolk) == (0, 3)
    put(s, "Grizzly Bears")
    assert pt(s, merfolk) == (0, 3)  # a creature, but not a commander
    krenko = put(s, "Krenko, Mob Boss")  # the commander (Alice's)
    assert pt(s, merfolk) == (2, 3)
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "command"})
    assert pt(s, merfolk) == (0, 3)  # back in the command zone
    check(s)


# -- 404.1, 406.1, 701.27g, 709.5, 509.1: counts -----------------------------------------------------------------------------
def test_swimmer_in_nightmares_wants_ten_cards_in_one_graveyard(cards):
    s = build(cards, mine=("Swimmer in Nightmares",))
    swimmer = put(s, "Swimmer in Nightmares")
    islands = [c for c in s.state.cards.values() if c.owner == "p2" and c.name == "Island"]
    assert len(islands) == 10
    act(s, "p2", type="move", card_ids=[c.id for c in islands[:9]], to={"player": "p2", "zone": "graveyard"})
    assert pt(s, swimmer) == (1, 4)
    act(s, "p2", type="move", card_ids=[islands[9].id], to={"player": "p2", "zone": "graveyard"})
    assert pt(s, swimmer) == (4, 4)  # ten in Bob's graveyard
    act(s, "p2", type="move", card_ids=[islands[0].id], to={"player": "p2", "zone": "hand"})
    assert pt(s, swimmer) == (1, 4)
    forests = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest"][:5]
    act(s, "p1", type="move", card_ids=[c.id for c in forests], to={"player": "p1", "zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[islands[0].id], to={"player": "p2", "zone": "graveyard"})
    assert pt(s, swimmer) == (4, 4)  # (the count is of one graveyard, not of all together: Bob's again)
    check(s)


def test_warden_of_the_beyond_wants_a_card_an_opponent_owns_in_exile(cards):
    s = build(cards, mine=("Warden of the Beyond",))
    warden = put(s, "Warden of the Beyond")
    mine = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest"][0]
    act(s, "p1", type="move", card_ids=[mine.id], to={"player": "p1", "zone": "exile"})
    assert pt(s, warden) == (2, 2)  # their card, not mine
    theirs = [c for c in s.state.cards.values() if c.owner == "p2" and c.name == "Island"][0]
    act(s, "p2", type="move", card_ids=[theirs.id], to={"player": "p2", "zone": "exile"})
    assert pt(s, warden) == (4, 4)
    act(s, "p2", type="move", card_ids=[theirs.id], to={"player": "p2", "zone": "graveyard"})
    assert pt(s, warden) == (2, 2)
    check(s)


def test_howling_galefang_wants_an_adventure_card_you_own_in_exile(cards):
    s = build(cards, mine=("Howling Galefang", "Bonecrusher Giant // Stomp"), theirs=("Bonecrusher Giant // Stomp",))
    fang = put(s, "Howling Galefang")
    assert "haste" not in kw(s, fang)
    theirs = card_named(s, "Bonecrusher Giant // Stomp", "p2")
    act(s, "p2", type="move", card_ids=[theirs.id], to={"player": "p2", "zone": "exile"})
    assert "haste" not in kw(s, fang)  # not yours
    plain = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest"][0]
    act(s, "p1", type="move", card_ids=[plain.id], to={"player": "p1", "zone": "exile"})
    assert "haste" not in kw(s, fang)  # yours, but no Adventure
    giant = card_named(s, "Bonecrusher Giant // Stomp")
    act(s, "p1", type="move", card_ids=[giant.id], to={"player": "p1", "zone": "exile"})
    assert "haste" in kw(s, fang)
    act(s, "p1", type="move", card_ids=[giant.id], to={"player": "p1", "zone": "graveyard"})
    assert "haste" not in kw(s, fang)
    check(s)


def test_oculus_whelp_grants_itself_a_death_draw_while_you_control_a_transformed_permanent(cards):
    s = build(cards, mine=("Oculus Whelp", "Delver of Secrets // Insectile Aberration"))
    whelp = put(s, "Oculus Whelp")
    delver = put(s, "Delver of Secrets // Insectile Aberration")

    def draws(c):
        return any(a.kind == "triggered" and "draw a card" in a.text for a in of(s, c).abilities)

    assert not draws(whelp)  # the front face is not a transformed permanent (701.27g)
    act(s, "p1", type="set_face", card_id=delver.id, face=1)
    assert draws(whelp)
    act(s, "p1", type="set_face", card_id=delver.id, face=0)
    assert not draws(whelp)
    check(s)


def test_rampaging_cyclops_shrinks_while_two_creatures_block_it(cards):
    s = build(cards, mine=("Rampaging Cyclops",))
    cyclops = put(s, "Rampaging Cyclops")
    one, two = token(s, "p2", "One"), token(s, "p2", "Two")
    s.state.cards[one.id].blocking = cyclops.id
    assert pt(s, cyclops) == (4, 4)
    s.state.cards[two.id].blocking = cyclops.id
    assert pt(s, cyclops) == (2, 4)  # 509.1: two creatures block it
    s.state.cards[two.id].blocking = None
    assert pt(s, cyclops) == (4, 4)
    s.state.cards[one.id].blocking = None
    check(s)


def test_tenacious_hunter_watches_every_creatures_counters(cards):
    s = build(cards, mine=("Tenacious Hunter",))
    hunter = put(s, "Tenacious Hunter")
    mine, theirs = token(s, "p1", "Mine"), token(s, "p2", "Theirs")
    assert not {"vigilance", "deathtouch"} & kw(s, hunter)
    act(s, "p1", type="counter", card_ids=[theirs.id], kind="-1/-1", delta=1)  # any creature, whoever controls it
    assert {"vigilance", "deathtouch"} <= kw(s, hunter)
    act(s, "p1", type="counter", card_ids=[theirs.id], kind="-1/-1", delta=-1)
    assert not {"vigilance", "deathtouch"} & kw(s, hunter)
    act(s, "p1", type="counter", card_ids=[mine.id], kind="+1/+1", delta=1)  # (another kind of counter)
    assert not {"vigilance", "deathtouch"} & kw(s, hunter)
    check(s)


def test_rampaging_soulrager_counts_the_unlocked_doors_of_your_rooms(cards):
    s = build(cards, mine=("Rampaging Soulrager", "Dazzling Theater // Prop Room"))
    soulrager = put(s, "Rampaging Soulrager")
    assert pt(s, soulrager) == (1, 4)
    room = to_hand(s, "Dazzling Theater // Prop Room")
    mana(s, W=6)
    act(s, "p1", type="cast_spell", card_id=room.id, face=0)  # the left door
    settle(s)
    assert pt(s, soulrager) == (1, 4)  # one unlocked door
    mana(s, W=3)
    act(s, "p1", type="unlock_door", card_id=card_named(s, "Dazzling Theater // Prop Room").id, door=2)
    settle(s)
    assert pt(s, soulrager) == (4, 4)  # two
    check(s)


# -- 301.5, 303.4: the object an Aura is attached to ----------------------------------------------------------------------
def test_security_bypass_makes_the_creature_unblockable_only_while_it_attacks_alone(cards):
    s = build(cards, mine=("Security Bypass",))
    aura = put(s, "Security Bypass")
    bear, other = token(s, "p1", "Bear"), token(s, "p1", "Other")
    attach(s, aura, bear)
    assert "cant_be_blocked" not in of(s, bear).imposed
    s.state.cards[bear.id].attacking = "p2"
    assert "cant_be_blocked" in of(s, bear).imposed  # 506.5: the only attacking creature
    s.state.cards[other.id].attacking = "p2"
    assert "cant_be_blocked" not in of(s, bear).imposed
    s.state.cards[other.id].attacking = None
    assert "cant_be_blocked" in of(s, bear).imposed
    s.state.cards[bear.id].attacking = None
    check(s)


def test_snow_devil_gives_first_strike_while_the_creature_blocks_and_you_control_a_snow_land(cards):
    s = build(cards, mine=("Snow Devil", "Snow-Covered Island"))
    aura = put(s, "Snow Devil")
    bear = token(s, "p1", "Bear")
    attach(s, aura, bear)
    assert "flying" in kw(s, bear) and "first strike" not in kw(s, bear)
    s.state.cards[bear.id].blocking = "x"
    assert "first strike" not in kw(s, bear)  # blocking, but no snow land
    put(s, "Snow-Covered Island")
    assert "first strike" in kw(s, bear)
    s.state.cards[bear.id].blocking = None
    assert "first strike" not in kw(s, bear)  # a snow land, but not blocking
    check(s)


def test_goblin_caves_helps_goblins_while_the_enchanted_land_is_a_basic_mountain(cards):
    s = build(cards, mine=("Goblin Caves", "Mountain"))
    caves = put(s, "Goblin Caves")
    mountain = put(s, "Mountain")
    forest = next(c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest")
    put(s, "Forest")
    goblin = token(s, "p2", "Goblin Raider", "2/2", "Token Creature — Goblin")  # (every Goblin, whoever controls it)
    attach(s, caves, forest)
    assert pt(s, goblin) == (2, 2)
    attach(s, caves, mountain)
    assert pt(s, goblin) == (2, 4)
    attach(s, caves, forest)
    assert pt(s, goblin) == (2, 2)
    check(s)


# -- 611.3a: a group, each member read at that moment -------------------------------------------------------------------------
def test_arcades_sabboth_toughens_the_untapped_creatures_that_are_not_attacking(cards):
    s = build(cards, mine=("Arcades Sabboth",))
    arcades = put(s, "Arcades Sabboth")
    bear = token(s, "p1", "Bear")
    assert pt(s, arcades) == (7, 9) and pt(s, bear) == (2, 4)
    s.state.cards[bear.id].attacking = "p2"
    assert pt(s, bear) == (2, 2)  # attacking: it ended for this one
    s.state.cards[bear.id].attacking = None
    act(s, "p1", type="tap", card_ids=[bear.id], tapped=True)
    assert pt(s, bear) == (2, 2)  # tapped: it isn't "each untapped creature"
    act(s, "p1", type="tap", card_ids=[bear.id], tapped=False)
    assert pt(s, bear) == (2, 4)
    check(s)


def test_homicidal_seclusion_helps_the_one_creature_you_control(cards):
    s = build(cards, mine=("Homicidal Seclusion",))
    put(s, "Homicidal Seclusion")
    assert pt(s, token(s, "p2", "Theirs")) == (2, 2)
    bear = token(s, "p1", "Bear")
    assert pt(s, bear) == (5, 3) and "lifelink" in kw(s, bear)
    other = token(s, "p1", "Other")
    assert pt(s, bear) == (2, 2) and pt(s, other) == (2, 2) and "lifelink" not in kw(s, bear)  # two creatures: none is "the" creature
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "graveyard"})
    assert pt(s, other) == (5, 3) and "lifelink" in kw(s, other)  # exactly one again: whichever it is now
    check(s)


# -- 305.2, 401.5: the top of the library ----------------------------------------------------------------------------------
def top_forest(s):
    land = next(c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[land.id], to={"player": "p1", "zone": "library"}, position="top")
    return land


def grants(s, c, verb):
    """The permissions that let Alice ``verb`` ("play" a land / "cast") this card from where it is now."""
    from app.rules import permissions
    from app.rules.plan import Plan

    plan = Plan(s.state, "p1", s.cards, None)
    here = s.state.cards[c.id]
    return permissions.grants(s.state, "p1", here, plan.ch(here), plan.info, verb=verb)


def test_verge_rangers_play_lands_from_the_top_only_while_an_opponent_controls_more_lands(cards):
    s = build(cards, mine=("Verge Rangers",))
    put(s, "Verge Rangers")
    land = top_forest(s)
    assert not grants(s, land, "play")  # nobody controls more lands
    theirs = [token(s, "p2", f"Island {n}", None, "Token Land — Island") for n in "AB"]
    assert grants(s, land, "play")  # they control two, you control none
    act(s, "p1", type="play_land", card_id=land.id)
    assert s.state.cards[land.id].zone == "p1:battlefield"
    land2 = top_forest(s)
    assert grants(s, land2, "play")  # one against two
    act(s, "p2", type="move", card_ids=[theirs[0].id], to={"player": "p2", "zone": "graveyard"})
    assert not grants(s, land2, "play")  # one each: no more than you
    check(s)


def test_the_reality_chip_lets_you_play_from_the_top_only_while_attached_to_a_creature(cards):
    s = build(cards, mine=("The Reality Chip",))
    chip = put(s, "The Reality Chip")
    land = top_forest(s)
    assert not grants(s, land, "play")
    bear = token(s, "p1", "Bear")
    attach(s, chip, bear)
    assert grants(s, land, "play")
    detach(s, chip)
    assert not grants(s, land, "play")  # 611.3a
    attach(s, chip, bear)
    act(s, "p1", type="play_land", card_id=land.id)
    assert s.state.cards[land.id].zone == "p1:battlefield"
    check(s)


# -- 601.3b-d: a spell with flash while a condition holds ---------------------------------------------------------------------
def test_crashing_tide_has_flash_only_while_you_control_a_merfolk(cards):
    s = build(cards, mine=("Crashing Tide", "Gray Harbor Merfolk"))
    tide = to_hand(s, "Crashing Tide")
    assert not any(g.flash for g in grants(s, tide, "cast"))
    merfolk = put(s, "Gray Harbor Merfolk")
    assert any(g.flash for g in grants(s, tide, "cast"))  # a Merfolk: "This spell has flash"
    act(s, "p1", type="move", card_ids=[merfolk.id], to={"player": "p1", "zone": "graveyard"})
    assert not any(g.flash for g in grants(s, tide, "cast"))
    check(s)


# -- 611.2b, 613.1f: "it loses all abilities for as long as ~ remains on the battlefield" ----------------------------------------
def test_the_wondrous_wasp_takes_every_ability_of_the_creature_only_while_it_stays(cards):
    s = build(cards, mine=("The Wondrous Wasp",), theirs=("Serra Angel",))
    angel = put(s, "Serra Angel", "p2")
    assert {"flying", "vigilance"} <= kw(s, angel)
    wasp = to_hand(s, "The Wondrous Wasp")
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=wasp.id)
    for _ in range(30):  # the enters trigger: choose its target (up to one), then resolve
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.card_id == angel.id][:1] or [d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[angel.id].tapped and not kw(s, angel)  # tapped, and it has no abilities (flying and vigilance gone)
    check(s)
    act(s, "p1", type="set_damage", card_ids=[card_named(s, "The Wondrous Wasp").id], value=9)  # lethal damage: it dies (704.5g)
    act(s, s.state.rules.priority, type="pass_priority")
    settle(s)
    assert card_named(s, "The Wondrous Wasp").zone == "p1:graveyard"
    assert {"flying", "vigilance"} <= kw(s, angel)  # 611.2b: it ended when the Wasp left the battlefield
    check(s)


# -- the same grammar, other cards ------------------------------------------------------------------------------------------
def test_hobble_stops_only_a_black_creature_from_blocking(cards):
    s = build(cards, mine=("Hobble", "Walking Corpse", "Grizzly Bears"))
    aura = put(s, "Hobble")
    corpse, bears = put(s, "Walking Corpse"), put(s, "Grizzly Bears")
    attach(s, aura, corpse)
    assert "cant_block" in of(s, corpse).imposed and "cant_attack" in of(s, corpse).imposed  # black
    attach(s, aura, bears)
    assert "cant_block" not in of(s, bears).imposed and "cant_attack" in of(s, bears).imposed  # green: it can block (611.3a)
    assert "cant_block" not in of(s, corpse).imposed
    check(s)


def test_augur_of_autumn_casts_creatures_from_the_top_with_three_different_powers(cards):
    s = build(cards, mine=("Augur of Autumn", "Grizzly Bears"))
    put(s, "Augur of Autumn")  # 2/3
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "library"}, position="top")
    token(s, "p1", "One", "1/1")
    assert not grants(s, bears, "cast")  # two different powers (Augur's 2 and 1)
    big = token(s, "p1", "Three", "3/3")
    assert grants(s, bears, "cast")  # coven: three or more creatures with different powers
    act(s, "p1", type="move", card_ids=[big.id], to={"player": "p1", "zone": "graveyard"})
    assert not grants(s, bears, "cast")
    check(s)


def test_summoning_materia_casts_creatures_from_the_top_only_while_attached(cards):
    s = build(cards, mine=("Summoning Materia", "Grizzly Bears"))
    materia = put(s, "Summoning Materia")
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "library"}, position="top")
    assert not grants(s, bears, "cast")
    host = token(s, "p1", "Host")
    attach(s, materia, host)
    assert grants(s, bears, "cast")
    detach(s, materia)
    assert not grants(s, bears, "cast")
    check(s)


def test_scarring_memories_has_flash_only_with_an_attacking_legendary_creature(cards):
    s = build(cards, mine=("Scarring Memories",))
    spell = to_hand(s, "Scarring Memories")
    krenko = put(s, "Krenko, Mob Boss")  # legendary
    assert not any(g.flash for g in grants(s, spell, "cast"))
    s.state.cards[krenko.id].attacking = "p2"
    assert any(g.flash for g in grants(s, spell, "cast"))  # a sorcery's own flash condition (601.3d)
    s.state.cards[krenko.id].attacking = None
    assert not any(g.flash for g in grants(s, spell, "cast"))
    check(s)


# -- 611.3a: a replacement, a prevention, a limit or a player's hexproof that applies only while a condition holds ------------------
def damage_candidates(s, pid="p1"):
    """The replacement statics of permanents in force for damage right now (app/rules/replace.py)."""
    from app.rules import replace
    from app.rules.plan import Plan

    return [c.label for c in replace.static_candidates(Plan(s.state, pid, s.cards, None), "damage")]


def test_thunderstaff_prevents_combat_damage_only_while_it_is_untapped(cards):
    s = build(cards, mine=("Lightning Bolt",), theirs=("Thunderstaff",))
    staff = put(s, "Thunderstaff", "p2")
    assert "Thunderstaff" in damage_candidates(s)
    act(s, "p2", type="tap", card_ids=[staff.id], tapped=True)
    assert "Thunderstaff" not in damage_candidates(s)  # tapped: it isn't there to prevent (611.3a)
    act(s, "p2", type="tap", card_ids=[staff.id], tapped=False)
    assert "Thunderstaff" in damage_candidates(s)
    bear = token(s, "p1", "Bear", "3/3")
    unready(s, bear)
    attack_and_hit(s, bear)
    assert s.state.players["p2"].life == 40 - 2  # "prevent 1 of that damage"
    check(s)


def test_hedron_field_purists_prevent_one_then_two_with_its_level_counters(cards):
    s = build(cards, mine=("Hedron-Field Purists",))
    purists = put(s, "Hedron-Field Purists")

    def prevented():
        from app.rules import replace
        from app.rules.plan import Plan

        return [c.op["n"] for c in replace.static_candidates(Plan(s.state, "p1", s.cards, None), "damage") if c.label == "Hedron-Field Purists"]

    assert prevented() == []  # no level counter yet
    act(s, "p1", type="counter", card_ids=[purists.id], kind="level", delta=1)
    assert prevented() == [1]  # LEVEL 1-4
    act(s, "p1", type="counter", card_ids=[purists.id], kind="level", delta=4)
    assert prevented() == [2]  # LEVEL 5+ (and not the 1-4 line any more)
    act(s, "p1", type="counter", card_ids=[purists.id], kind="level", delta=-5)
    assert prevented() == []
    check(s)


def test_spirit_of_resistance_prevents_all_damage_to_you_while_you_control_every_color(cards):
    s = build(cards, mine=("Spirit of Resistance", "Lightning Bolt"))
    put(s, "Spirit of Resistance")  # white
    made = [token(s, "p1", f"Color {c}", "1/1", colors=(c,)) for c in "UBRG"]
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p1"])
    settle(s)
    assert s.state.players["p1"].life == 40  # a permanent of each color: all damage to you is prevented
    act(s, "p1", type="move", card_ids=[made[0].id], to={"player": "p1", "zone": "graveyard"})  # no blue permanent now
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p1"])
    settle(s)
    assert s.state.players["p1"].life == 37
    check(s)


def test_conquerors_flail_stops_their_spells_in_your_turn_only_while_attached(cards):
    s = build(cards, mine=("Conqueror's Flail", "Lightning Bolt"), theirs=("Lightning Bolt",))
    flail = put(s, "Conqueror's Flail")
    bear = token(s, "p1", "Bear")
    theirs = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)

    def my_bolt():
        mine = to_hand(s, "Lightning Bolt")
        mana(s, R=1)
        act(s, "p1", type="cast_spell", card_id=mine.id, targets=["p2"])

    my_bolt()
    assert s.state.zones.get("stack") and s.state.rules.priority == "p2"  # not attached: they may respond in my turn
    settle(s)
    assert s.state.players["p2"].life == 37
    attach(s, flail, bear)
    my_bolt()
    assert not s.state.zones.get("stack") and s.state.players["p2"].life == 34  # "can't cast spells during your turn": no one to respond
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=theirs.id, targets=["p1"])
    detach(s, flail)
    my_bolt()
    assert s.state.rules.priority == "p2"  # 611.3a: they may respond again
    act(s, "p2", type="cast_spell", card_id=theirs.id, targets=["p1"])
    settle(s)
    assert s.state.players["p1"].life == 37 and s.state.players["p2"].life == 31
    check(s)


def test_captain_america_gives_you_and_the_other_heroes_hexproof_while_he_has_a_shield_counter(cards):
    from app.rules import player_shields
    from app.rules.plan import Plan

    s = build(cards, mine=("Captain America, Super-Soldier",))
    cap = put(s, "Captain America, Super-Soldier")
    hero = token(s, "p1", "Hero", "2/2", "Token Creature — Human Hero")

    def targetable():
        plan = Plan(s.state, "p1", s.cards, None)
        return player_shields.can_target(plan, "p2", "p1", None)

    assert targetable() and "hexproof" not in kw(s, hero)  # no shield counter yet
    act(s, "p1", type="counter", card_ids=[cap.id], kind="shield", delta=1)
    assert not targetable() and "hexproof" in kw(s, hero) and "hexproof" not in kw(s, cap)  # you, and the others (not Captain America himself)
    act(s, "p1", type="counter", card_ids=[cap.id], kind="shield", delta=-1)
    assert targetable() and "hexproof" not in kw(s, hero)
    check(s)


# -- 611.3a: "As long as C, <replacement effect>" read by the replacement machinery ----------------------------------------------
def bolt_player(s, target="p2", pid="p1"):
    bolt = to_hand(s, "Lightning Bolt", pid)
    mana(s, pid, R=1)
    act(s, pid, type="cast_spell", card_id=bolt.id, targets=[target])
    settle(s)


def empty_hand(s, pid="p1"):
    ids = list(s.state.zones[f"{pid}:hand"])
    if ids:
        act(s, pid, type="move", card_ids=ids, to={"player": pid, "zone": "graveyard"})


def test_anthem_of_rakdos_doubles_your_damage_only_while_you_have_no_cards_in_hand(cards):
    s = build(cards, mine=("Anthem of Rakdos", "Lightning Bolt"))
    put(s, "Anthem of Rakdos")
    empty_hand(s)
    spare = next(c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[spare.id], to={"player": "p1", "zone": "hand"})
    bolt_player(s)
    assert s.state.players["p2"].life == 37  # a Forest in hand: Hellbent is off, 3 damage
    act(s, "p1", type="move", card_ids=[spare.id], to={"player": "p1", "zone": "graveyard"})
    bolt_player(s)
    assert s.state.players["p2"].life == 31  # no cards in hand (the Bolt is on the stack): double (6)
    check(s)


def test_aether_revolt_adds_two_noncombat_damage_only_after_a_permanent_left(cards):
    s = build(cards, mine=("Aether Revolt", "Lightning Bolt"))
    put(s, "Aether Revolt")
    bolt_player(s)
    assert s.state.players["p2"].life == 37  # no permanent has left the battlefield under your control this turn
    gone = token(s, "p1", "Gone")
    act(s, "p1", type="move", card_ids=[gone.id], to={"player": "p1", "zone": "graveyard"})  # (a token leaves, then ceases to exist)
    bolt_player(s)
    assert s.state.players["p2"].life == 32  # revolt: that much plus 2
    check(s)


def test_vampire_socialite_adds_a_counter_to_vampires_entering_after_an_opponent_lost_life(cards):
    s = build(cards, mine=("Vampire Socialite", "Bloodthrone Vampire", "Lightning Bolt"))
    put(s, "Vampire Socialite")
    first = to_hand(s, "Bloodthrone Vampire")
    mana(s, B=2)
    act(s, "p1", type="cast_spell", card_id=first.id)
    settle(s)
    assert s.state.cards[first.id].zone == "p1:battlefield" and not s.state.cards[first.id].counters  # nobody has lost life yet
    bolt_player(s)
    act(s, "p1", type="move", card_ids=[first.id], to={"player": "p1", "zone": "hand"})
    mana(s, B=2)
    act(s, "p1", type="cast_spell", card_id=first.id)
    settle(s)
    assert s.state.cards[first.id].counters.get("+1/+1") == 1  # an opponent lost life this turn
    check(s)


def test_merfolk_trickster_taps_the_creature_and_it_loses_its_abilities_for_the_turn(cards):
    s = build(cards, mine=("Merfolk Trickster",), theirs=("Serra Angel",))
    angel = put(s, "Serra Angel", "p2")
    trickster = to_hand(s, "Merfolk Trickster")
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=trickster.id)
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.card_id == angel.id][:1] or [d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[angel.id].tapped and not kw(s, angel)  # "It loses all abilities until end of turn" (613.1f)
    check(s)
