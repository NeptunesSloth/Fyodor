"""613.6 / 613.8 across characteristics, and 613.7m: what a static ability applies to is read from the object as the earlier layers (and,
within a layer, the effects it depends on) left it — a type a layer-4 effect gave (Opalescence, Arcane Adaptation, Conspiracy, Karn's Touch,
Life and Limb, Kormus Bell + Urborg, March of the Machines + Mycosynth Lattice), a color a layer-5 effect gave (Painter's Servant), abilities
layer 6 took away (Humility + Muraganda Petroglyphs) or gave (Levitation + Favorable Winds), the power 7a / 7b / the 7c effects it depends on
left (613.8a-c; no printed card's subject asks about power in layer 7c, so two plainly labelled test cards stand in), and a rule static's
"as long as you control a creature with power 4 or greater" read from the creatures as every layer leaves them (Bristlepack Sentry).
613.7m: cards entering together, and tokens made for several players, are timestamped in APNAP order.
Real Oracle text (Scryfall) except the two "Test" cards; each scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from app.rules import layers
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand

EXTRA = [
    real("Opalescence", "{2}{W}{W}", 4, "Enchantment", "Each other non-Aura enchantment is a creature in addition to its other types and has base "
         "power and base toughness each equal to its mana value.", None, "W"),
    real("Glorious Anthem", "{1}{W}{W}", 3, "Enchantment", "Creatures you control get +1/+1.", None, "W"),
    real("Arcane Adaptation", "{2}{U}", 3, "Enchantment", "As this enchantment enters, choose a creature type.\nCreatures you control are the chosen "
         "type in addition to their other types. The same is true for creature spells you control and creature cards you own that aren't on the "
         "battlefield.", None, "U"),
    real("Conspiracy", "{3}{B}{B}", 5, "Enchantment", "As this enchantment enters, choose a creature type.\nCreatures you control are the chosen "
         "type. The same is true for creature spells you control and creature cards you own that aren't on the battlefield.", None, "B"),
    real("Goblin King", "{1}{R}{R}", 3, "Creature — Goblin", "Other Goblins get +1/+1 and have mountainwalk.", ("2", "2"), "R"),
    real("Painter's Servant", "{2}", 2, "Artifact Creature — Scarecrow", "As this creature enters, choose a color.\nAll cards that aren't on the "
         "battlefield, spells, and permanents are the chosen color in addition to their other colors.", ("1", "3"), ""),
    real("Ascendant Evincar", "{4}{B}{B}", 6, "Legendary Creature — Phyrexian Vampire Noble", "Flying (This creature can't be blocked except by "
         "creatures with flying or reach.)\nOther black creatures get +1/+1.\nNonblack creatures get -1/-1.", ("3", "3"), "B"),
    real("Blood Moon", "{2}{R}", 3, "Enchantment", "Nonbasic lands are Mountains.", None, "R"),
    real("Urborg, Tomb of Yawgmoth", "", 0, "Legendary Land", "Each land is a Swamp in addition to its other land types.", None, ""),
    real("March of the Machines", "{3}{U}", 4, "Enchantment", "Each noncreature artifact is an artifact creature with power and toughness each "
         "equal to its mana value. (Equipment that's a creature can't equip a creature.)", None, "U"),
    real("Mycosynth Lattice", "{6}", 6, "Artifact", "All permanents are artifacts in addition to their other types.\nAll cards that aren't on the "
         "battlefield, spells, and permanents are colorless.\nPlayers may spend mana as though it were mana of any color.", None, ""),
    real("Humility", "{2}{W}{W}", 4, "Enchantment", "All creatures lose all abilities and have base power and toughness 1/1.", None, "W"),
    real("Life and Limb", "{3}{G}", 4, "Enchantment", "All Forests and all Saprolings are 1/1 green Saproling creatures and Forest lands in addition "
         "to their other types. (They're affected by summoning sickness.)", None, "G"),
    real("Kormus Bell", "{4}", 4, "Artifact", "All Swamps are 1/1 black creatures that are still lands.", None, ""),
    real("Wild Nacatl", "{G}", 1, "Creature — Cat Warrior", "This creature gets +1/+1 as long as you control a Mountain.\nThis creature gets +1/+1 "
         "as long as you control a Plains.", ("1", "1"), "G"),
    real("Prismatic Omen", "{1}{G}", 2, "Enchantment", "Lands you control are every basic land type in addition to their other types.", None, "G"),
    real("Sliver Legion", "{W}{U}{B}{R}{G}", 5, "Legendary Creature — Sliver", "All Sliver creatures get +1/+1 for each other Sliver on the "
         "battlefield.", ("7", "7"), "WUBRG"),
    real("Muraganda Petroglyphs", "{3}{G}", 4, "Enchantment", "Creatures with no abilities get +2/+2.", None, "G"),
    real("Levitation", "{2}{U}{U}", 4, "Enchantment", "Creatures you control have flying.", None, "U"),
    real("Favorable Winds", "{1}{U}", 2, "Enchantment", "Creatures you control with flying get +1/+1.", None, "U"),
    real("Bad Moon", "{1}{B}", 2, "Enchantment", "Black creatures get +1/+1.", None, "B"),
    real("Bristlepack Sentry", "{1}{G}", 2, "Creature — Plant Wolf", "Defender\nAs long as you control a creature with power 4 or greater, this "
         "creature can attack as though it didn't have defender.", ("3", "3"), "G"),
    real("Twilight's Call", "{4}{B}{B}", 6, "Sorcery", "You may cast this spell as though it had flash if you pay {2} more to cast it. (You may cast "
         "it any time you could cast an instant.)\nEach player returns all creature cards from their graveyard to the battlefield.", None, "B"),
    real("Kibo, Uktabi Prince", "{2}{G}", 3, "Legendary Creature — Monkey Noble", "{T}: Each player creates a colorless artifact token named Banana "
         "with \"{T}, Sacrifice this token: Add {R} or {G}. You gain 2 life.\"\nWhenever an artifact an opponent controls is put into a graveyard "
         "from the battlefield, put a +1/+1 counter on each creature you control that's an Ape or a Monkey.\nWhenever Kibo attacks, defending player "
         "sacrifices an artifact of their choice.", ("2", "2"), "G"),
    # No printed static's subject asks about power in layer 7c (only rule statics do: Tetsuko Umezawa, Reverence): two test cards stand in.
    real("Test Small Anthem", "{1}{W}", 2, "Enchantment", "Creatures with power 2 or less get +1/+1.", None, "W"),
    real("Test Big Tax", "{1}{B}", 2, "Enchantment", "Creatures with power 3 or greater get -2/-0.", None, "B"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def resolve(s, label=""):
    """Let the stack resolve; a choice is answered with the option labelled ``label`` (else the first)."""
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            pick = next((o for o in d.options if (o.label or "").lower() == label.lower()), d.options[0])
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick.id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("the stack never emptied")


def cast_choosing(s, name, choice, **m):
    to_hand(s, name)
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=card_named(s, name).id)
    resolve(s, choice)
    assert card_named(s, name).zone == "p1:battlefield"


# -- layer 4 → layers 6 / 7 (613.1d, 613.4c): the subject is read from the type an earlier layer gave --


def test_opalescence_creature_gets_the_anthem_it_is(cards):
    s = build(cards, ["Opalescence", "Glorious Anthem"])
    put(s, "Opalescence")
    anthem = put(s, "Glorious Anthem")
    assert ch(s, anthem).is_creature and pt(s, "Glorious Anthem") == (4, 4)  # 3/3 (its mana value, 7b) +1/+1 from itself (7c)
    check(s)


def test_arcane_adaptation_makes_goblin_king_pump_a_bear(cards):
    s = build(cards, ["Arcane Adaptation", "Goblin King", "Grizzly Bears"])
    put(s, "Goblin King")
    bears = put(s, "Grizzly Bears")
    assert pt(s, "Grizzly Bears") == (2, 2)
    cast_choosing(s, "Arcane Adaptation", "Goblin", U=1, C=2)
    assert "Goblin" in ch(s, bears).subtypes and pt(s, "Grizzly Bears") == (3, 3)
    check(s)


def test_type_grant_waits_for_the_later_animation_it_depends_on(cards):
    """613.8a: Arcane Adaptation (earlier) applies to what Opalescence (later) makes a creature: the animated anthem is a Goblin, so
    Goblin King and its own +1/+1 pump it: 3/3 + 1 + 1."""
    s = build(cards, ["Arcane Adaptation", "Opalescence", "Goblin King", "Glorious Anthem"])
    cast_choosing(s, "Arcane Adaptation", "Goblin", U=1, C=2)
    put(s, "Goblin King")
    put(s, "Opalescence")
    anthem = put(s, "Glorious Anthem")
    assert "Goblin" in ch(s, anthem).subtypes and pt(s, "Glorious Anthem") == (5, 5)
    check(s)


def test_conspiracy_sets_the_type_of_opalescence_creatures(cards):
    s = build(cards, ["Opalescence", "Goblin King", "Glorious Anthem", "Conspiracy"])
    anthem = put(s, "Glorious Anthem")
    put(s, "Goblin King")
    cast_choosing(s, "Conspiracy", "Goblin", B=2, C=3)
    put(s, "Opalescence")
    conspiracy = card_named(s, "Conspiracy")
    assert ch(s, anthem).subtypes == {"Goblin"} and ch(s, conspiracy).subtypes == {"Goblin"}
    assert pt(s, "Glorious Anthem") == (5, 5) and pt(s, "Conspiracy") == (7, 7)  # 3/3 and 5/5, +1/+1 anthem, +1/+1 Goblin King
    check(s)


def test_karns_touch_animation_then_static_type_grant(cards):
    """A resolved layer-4 effect (Karn's Touch, later) makes Sol Ring a creature; the static type grant reads it (613.8a), the lord follows."""
    s = build(cards, ["Arcane Adaptation", "Goblin King", "Sol Ring", "Karn's Touch"])
    cast_choosing(s, "Arcane Adaptation", "Goblin", U=1, C=2)
    put(s, "Goblin King")
    ring = put(s, "Sol Ring")
    to_hand(s, "Karn's Touch")
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Karn's Touch").id, targets=[ring.id])
    resolve(s)
    assert "Goblin" in ch(s, ring).subtypes and pt(s, "Sol Ring") == (2, 2)
    check(s)


def test_life_and_limb_saproling_is_adapted_and_lorded(cards):
    s = build(cards, ["Arcane Adaptation", "Goblin King", "Life and Limb"])
    cast_choosing(s, "Arcane Adaptation", "Goblin", U=1, C=2)
    put(s, "Goblin King")
    forest = put(s, "Forest")
    put(s, "Life and Limb")
    assert {"Saproling", "Goblin", "Forest"} <= ch(s, forest).subtypes and pt(s, "Forest") == (2, 2)
    check(s)


@pytest.mark.parametrize("moon_first", [True, False])
def test_blood_moon_and_urborg_either_order(cards, moon_first):
    """613.8a's own example: Urborg's effect depends on Blood Moon's (it would remove Urborg's ability), so Blood Moon applies first
    whatever the timestamps: Urborg is a Mountain with no ability and no land is a Swamp."""
    s = build(cards, ["Blood Moon", "Urborg, Tomb of Yawgmoth", "Breeding Pool"])
    pool = put(s, "Breeding Pool")
    forest = put(s, "Forest")
    for name in (["Blood Moon", "Urborg, Tomb of Yawgmoth"] if moon_first else ["Urborg, Tomb of Yawgmoth", "Blood Moon"]):
        put(s, name)
    urborg = ch(s, card_named(s, "Urborg, Tomb of Yawgmoth"))
    assert urborg.subtypes == {"Mountain"} and [a.text for a in urborg.abilities] == ["{T}: Add {R}."]
    assert ch(s, pool).subtypes == {"Mountain"} and ch(s, forest).subtypes == {"Forest"}
    check(s)


@pytest.mark.parametrize("bell_first", [True, False])
def test_kormus_bell_animates_what_urborg_makes_a_swamp(cards, bell_first):
    s = build(cards, ["Kormus Bell", "Urborg, Tomb of Yawgmoth"])
    forest = put(s, "Forest")
    for name in (["Kormus Bell", "Urborg, Tomb of Yawgmoth"] if bell_first else ["Urborg, Tomb of Yawgmoth", "Kormus Bell"]):
        put(s, name)
    got = ch(s, forest)
    assert got.is_creature and {"Swamp", "Forest"} <= got.subtypes and got.colors == {"B"} and pt(s, "Forest") == (1, 1)
    check(s)


@pytest.mark.parametrize("march_first", [True, False])
def test_march_of_the_machines_animates_what_mycosynth_lattice_makes_an_artifact(cards, march_first):
    s = build(cards, ["March of the Machines", "Mycosynth Lattice"])
    forest = put(s, "Forest")
    for name in (["March of the Machines", "Mycosynth Lattice"] if march_first else ["Mycosynth Lattice", "March of the Machines"]):
        put(s, name)
    assert {"Artifact", "Creature", "Land"} <= ch(s, forest).types and pt(s, "Forest") == (0, 0)
    assert pt(s, "Mycosynth Lattice") == (6, 6)
    check(s)


def test_wild_nacatl_reads_land_types_layer_4_gave(cards):
    s = build(cards, ["Wild Nacatl", "Blood Moon", "Breeding Pool", "Prismatic Omen"])
    put(s, "Wild Nacatl")
    put(s, "Breeding Pool")
    assert pt(s, "Wild Nacatl") == (1, 1)
    put(s, "Blood Moon")
    assert pt(s, "Wild Nacatl") == (2, 2)  # the Breeding Pool is a Mountain
    put(s, "Prismatic Omen")
    assert pt(s, "Wild Nacatl") == (3, 3)  # … and a Plains
    check(s)


def test_sliver_legion_counts_what_arcane_adaptation_made_slivers(cards):
    s = build(cards, ["Sliver Legion", "Arcane Adaptation", "Grizzly Bears"])
    cast_choosing(s, "Arcane Adaptation", "Sliver", U=1, C=2)
    put(s, "Sliver Legion")
    put(s, "Grizzly Bears")
    assert pt(s, "Sliver Legion") == (8, 8) and pt(s, "Grizzly Bears") == (3, 3)
    check(s)


# -- layer 5 → layer 7c: the color Painter's Servant gives --


def test_painters_servant_color_changes_what_ascendant_evincar_applies_to(cards):
    s = build(cards, ["Painter's Servant", "Ascendant Evincar", "Grizzly Bears"])
    put(s, "Ascendant Evincar")
    bears = put(s, "Grizzly Bears")
    assert pt(s, "Grizzly Bears") == (1, 1)  # nonblack: -1/-1
    to_hand(s, "Painter's Servant")
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Painter's Servant").id)
    resolve(s, "Black")
    assert "B" in ch(s, bears).colors and pt(s, "Grizzly Bears") == (3, 3) and pt(s, "Painter's Servant") == (2, 4)
    check(s)


# -- layer 6 → layer 7 (613.1f, 613.4) --


@pytest.mark.parametrize("humility_first", [True, False])
def test_humility_and_opalescence_by_timestamp(cards, humility_first):
    """The rulings: with Opalescence later, Humility is a 4/4 and an animated Glorious Anthem a 3/3 that pumps nothing (its ability is gone
    in layer 6, before 7c); with Humility later, every creature is a 1/1."""
    s = build(cards, ["Humility", "Opalescence", "Grizzly Bears", "Glorious Anthem"])
    put(s, "Grizzly Bears")
    put(s, "Glorious Anthem")
    for name in (["Humility", "Opalescence"] if humility_first else ["Opalescence", "Humility"]):
        put(s, name)
    got = {n: pt(s, n) for n in ("Humility", "Glorious Anthem", "Grizzly Bears")}
    assert got == ({"Humility": (4, 4), "Glorious Anthem": (3, 3), "Grizzly Bears": (1, 1)} if humility_first
                   else {"Humility": (1, 1), "Glorious Anthem": (1, 1), "Grizzly Bears": (1, 1)})
    check(s)


@pytest.mark.parametrize("humility_first", [True, False])
def test_petroglyphs_sees_the_abilities_humility_removed(cards, humility_first):
    s = build(cards, ["Humility", "Muraganda Petroglyphs", "Goblin King"])
    put(s, "Goblin King")
    for name in (["Humility", "Muraganda Petroglyphs"] if humility_first else ["Muraganda Petroglyphs", "Humility"]):
        put(s, name)
    assert pt(s, "Goblin King") == (3, 3)  # 1/1 with no abilities, +2/+2
    check(s)


def test_favorable_winds_sees_the_flying_levitation_gives(cards):
    s = build(cards, ["Levitation", "Favorable Winds", "Grizzly Bears"])
    put(s, "Grizzly Bears")
    put(s, "Favorable Winds")
    assert pt(s, "Grizzly Bears") == (2, 2)
    put(s, "Levitation")
    assert pt(s, "Grizzly Bears") == (3, 3)
    check(s)


# -- layer 7c: a subject that asks about power (613.6, 613.8a-c) --


def test_power_keyed_subject_reads_7b_and_waits_for_what_it_depends_on(cards):
    s = build(cards, ["Test Small Anthem", "Humility", "Garruk's Horde", "Grizzly Bears", "Glorious Anthem", "Test Big Tax"])
    put(s, "Garruk's Horde")
    put(s, "Grizzly Bears")
    put(s, "Test Small Anthem")
    assert pt(s, "Garruk's Horde") == (7, 7) and pt(s, "Grizzly Bears") == (3, 3)
    put(s, "Humility")  # 7b: 1/1, so "power 2 or less" (the printed 7 no longer counts)
    assert pt(s, "Garruk's Horde") == (2, 2) and pt(s, "Grizzly Bears") == (2, 2)
    put(s, "Glorious Anthem")  # 1/1 +1/+1 = 2/2, still "power 2 or less": 3/3
    assert pt(s, "Garruk's Horde") == (3, 3)
    # Test Big Tax (later) depends on Test Small Anthem (applying it makes the 2/2 a 3/3: 613.8a), not the other way round: the anthem
    # first, then the tax applies (613.8b, 613.8c): 2/2 → 3/3 → 1/3
    put(s, "Test Big Tax")
    assert pt(s, "Garruk's Horde") == (1, 3) and pt(s, "Grizzly Bears") == (1, 3)
    check(s)


def test_power_keyed_subject_waits_for_an_independent_pump(cards):
    """Grizzly Bears 2/2 with Glorious Anthem (later): "power 2 or less" depends on the anthem (applying it makes the Bears a 3/3), so
    the anthem applies first and the small anthem no longer does — 3/3, not 4/4, whatever the timestamps."""
    s = build(cards, ["Test Small Anthem", "Grizzly Bears", "Glorious Anthem"])
    put(s, "Grizzly Bears")
    put(s, "Test Small Anthem")
    put(s, "Glorious Anthem")
    assert pt(s, "Grizzly Bears") == (3, 3)
    check(s)


# -- 611.3a: a rule static's condition reads the other creatures as every layer leaves them --


def test_bristlepack_sentry_sees_power_an_anthem_gives(cards):
    s = build(cards, ["Bristlepack Sentry", "Glorious Anthem"])
    sentry = put(s, "Bristlepack Sentry")
    assert "attack_despite_defender" not in ch(s, sentry).imposed
    put(s, "Glorious Anthem")
    assert pt(s, "Bristlepack Sentry") == (4, 4) and "attack_despite_defender" in ch(s, sentry).imposed
    check(s)


def test_bristlepack_sentry_sees_another_creature_a_lord_pumps(cards):
    s = build(cards, ["Bristlepack Sentry", "Ascendant Evincar", "Bad Moon"])
    sentry = put(s, "Bristlepack Sentry")
    put(s, "Ascendant Evincar")
    assert pt(s, "Ascendant Evincar") == (3, 3) and "attack_despite_defender" not in ch(s, sentry).imposed
    put(s, "Bad Moon")
    assert pt(s, "Ascendant Evincar") == (4, 4) and pt(s, "Bristlepack Sentry") == (2, 2)
    assert "attack_despite_defender" in ch(s, sentry).imposed
    check(s)


# -- 613.7m: simultaneous timestamps in APNAP order --


def _opponents_main(s):
    stops(s, "main1")
    to_phase(s, "main1", turn=4)  # Bob's turn
    if s.state.rules.priority == "p2":
        act(s, "p2", type="pass_priority")
    assert s.state.turn.active_player == "p2" and s.state.rules.priority == "p1"


def test_cards_entering_together_on_an_opponents_turn_are_timestamped_apnap(cards):
    s = build(cards, ["Twilight's Call", "Grizzly Bears"], ["Grizzly Bears", "Goblin King"])
    for pid, name in (("p1", "Grizzly Bears"), ("p2", "Grizzly Bears"), ("p2", "Goblin King")):
        act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"zone": "graveyard"})
    _opponents_main(s)
    to_hand(s, "Twilight's Call")
    mana(s, B=2, C=6)  # (flash: {2} more)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Twilight's Call").id)
    resolve(s)
    mine, bears, king = (card_named(s, n, pid) for pid, n in (("p1", "Grizzly Bears"), ("p2", "Grizzly Bears"), ("p2", "Goblin King")))
    assert all(s.state.cards[c.id].zone.endswith(":battlefield") for c in (mine, bears, king))
    stamp = {c.id: layers.timestamp(s.state, c.id) for c in (mine, bears, king)}
    assert max(stamp[bears.id], stamp[king.id]) < stamp[mine.id]  # the active player's (Bob's) first
    check(s)


def test_tokens_each_player_creates_on_an_opponents_turn_are_timestamped_apnap(cards):
    s = build(cards, ["Kibo, Uktabi Prince"])
    kibo = put(s, "Kibo, Uktabi Prince")
    _opponents_main(s)
    act(s, "p1", type="activate_ability", card_id=kibo.id, ability=0)
    resolve(s)
    bananas = {c.controller: c for c in s.state.cards.values() if c.is_token and c.name == "Banana"}
    assert set(bananas) == {"p1", "p2"}
    assert layers.timestamp(s.state, bananas["p2"].id) < layers.timestamp(s.state, bananas["p1"].id)
    check(s)
