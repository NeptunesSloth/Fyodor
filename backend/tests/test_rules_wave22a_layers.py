"""Group layers (wave 22A), researched against CR 2026-09-25: type setting (305.7), "lose all abilities" for a group (613.1f),
group animation with per-object power and toughness (613.1d, 613.4b), colors / legendary / chosen-color statics in every zone
(613.1e, 611.3), and the order of all of them: timestamps (613.7), dependencies (613.8), an effect that began keeps its objects
in every layer (613.6). app/rules/group_layers.py solves the table; app/rules/layers.py applies it.

Every scenario uses real Commander-legal cards with their current Oracle text, checks that replaying the recorded history
reproduces the table, and that a save/load round trip keeps it.
"""

from __future__ import annotations

import pytest

from app.game.state import GameState
from app.rules import coverage
from app.rules.characteristics import Characteristics, parse_type_line
from app.rules.oracle import parse_abilities
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches, rules
from tests.test_rules_permissions import build, hold, put

EXTRA = [
    card('Urborg, Tomb of Yawgmoth', set_code="tst", number="22A01", type_line='Legendary Land',
         oracle_text='Each land is a Swamp in addition to its other land types.'),
    card('Blood Moon', set_code="tst", number="22A02", mana_cost='{2}{R}', cmc=3.0, type_line='Enchantment',
         oracle_text='Nonbasic lands are Mountains.', colors=['R'], color_identity=['R']),
    card('Harbinger of the Seas', set_code="tst", number="22A03", mana_cost='{1}{U}{U}', cmc=3.0, type_line='Creature — Merfolk Wizard',
         oracle_text='Nonbasic lands are Islands.', power='2', toughness='2', colors=['U'], color_identity=['U']),
    card('Humility', set_code="tst", number="22A04", mana_cost='{2}{W}{W}', cmc=4.0, type_line='Enchantment',
         oracle_text='All creatures lose all abilities and have base power and toughness 1/1.', colors=['W'], color_identity=['W']),
    card('Dress Down', set_code="tst", number="22A05", mana_cost='{1}{U}', cmc=2.0, type_line='Enchantment',
         oracle_text='Flash\nWhen this enchantment enters, draw a card.\nCreatures lose all abilities.\n'
                     'At the beginning of the end step, sacrifice this enchantment.', colors=['U'], color_identity=['U'], keywords=['Flash']),
    card('Opalescence', set_code="tst", number="22A06", mana_cost='{2}{W}{W}', cmc=4.0, type_line='Enchantment',
         oracle_text='Each other non-Aura enchantment is a creature in addition to its other types and has base power and base '
                     'toughness each equal to its mana value.', colors=['W'], color_identity=['W']),
    card('March of the Machines', set_code="tst", number="22A07", mana_cost='{3}{U}', cmc=4.0, type_line='Enchantment',
         oracle_text="Each noncreature artifact is an artifact creature with power and toughness each equal to its mana value. "
                     "(Equipment that's a creature can't equip a creature.)", colors=['U'], color_identity=['U']),
    card('Mycosynth Lattice', set_code="tst", number="22A08", mana_cost='{6}', cmc=6.0, type_line='Artifact',
         oracle_text="All permanents are artifacts in addition to their other types.\nAll cards that aren't on the battlefield, spells, "
                     "and permanents are colorless.\nPlayers may spend mana as though it were mana of any color."),
    card("Painter's Servant", set_code="tst", number="22A09", mana_cost='{2}', cmc=2.0, type_line='Artifact Creature — Scarecrow',
         oracle_text="As this creature enters, choose a color.\nAll cards that aren't on the battlefield, spells, and permanents are "
                     "the chosen color in addition to their other colors.", power='1', toughness='3'),
    card('Thran Lens', set_code="tst", number="22A10", mana_cost='{2}', cmc=2.0, type_line='Artifact',
         oracle_text='All permanents are colorless.'),
    card('Leyline of Singularity', set_code="tst", number="22A11", mana_cost='{2}{U}{U}', cmc=4.0, type_line='Enchantment',
         oracle_text="If this card is in your opening hand, you may begin the game with it on the battlefield.\n"
                     "All nonland permanents are legendary.", colors=['U'], color_identity=['U']),
    card('Encroaching Mycosynth', set_code="tst", number="22A12", mana_cost='{3}{U}', cmc=4.0, type_line='Artifact',
         oracle_text="Nonland permanents you control are artifacts in addition to their other types. The same is true for permanent "
                     "spells you control and nonland permanent cards you own that aren't on the battlefield.", colors=['U'],
         color_identity=['U']),
    card('Kormus Bell', set_code="tst", number="22A13", mana_cost='{4}', cmc=4.0, type_line='Artifact',
         oracle_text='All Swamps are 1/1 black creatures that are still lands.'),
    card('Ambush Commander', set_code="tst", number="22A14", mana_cost='{3}{G}{G}', cmc=5.0, type_line='Creature — Elf',
         oracle_text="Forests you control are 1/1 green Elf creatures that are still lands.\n{1}{G}, Sacrifice an Elf: Target creature "
                     "gets +3/+3 until end of turn.", power='2', toughness='2', colors=['G'], color_identity=['G']),
    card('Dryad of the Ilysian Grove', set_code="tst", number="22A15", mana_cost='{2}{G}', cmc=3.0,
         type_line='Enchantment Creature — Nymph Dryad',
         oracle_text='You may play an additional land on each of your turns.\nLands you control are every basic land type in '
                     'addition to their other types.', power='2', toughness='4', colors=['G'], color_identity=['G']),
    card('Ashaya, Soul of the Wild', set_code="tst", number="22A16", mana_cost='{3}{G}{G}', cmc=5.0,
         type_line='Legendary Creature — Elemental',
         oracle_text="Ashaya's power and toughness are each equal to the number of lands you control.\nNontoken creatures you control "
                     "are Forest lands in addition to their other types. (They're still affected by summoning sickness.)",
         power='*', toughness='*', colors=['G'], color_identity=['G']),
    card('Glorious Anthem', set_code="tst", number="22A17", mana_cost='{1}{W}{W}', cmc=3.0, type_line='Enchantment',
         oracle_text='Creatures you control get +1/+1.', colors=['W'], color_identity=['W']),
    card('Lord of Atlantis', set_code="tst", number="22A18", mana_cost='{U}{U}', cmc=2.0, type_line='Creature — Merfolk',
         oracle_text='Other Merfolk get +1/+1 and have islandwalk.', power='2', toughness='2', colors=['U'], color_identity=['U']),
    card('Mind Stone', set_code="tst", number="22A19", mana_cost='{2}', cmc=2.0, type_line='Artifact',
         oracle_text='{T}: Add {C}.\n{1}, {T}, Sacrifice this artifact: Draw a card.'),
    card('Darksteel Citadel', set_code="tst", number="22A20", type_line='Artifact Land',
         oracle_text='Indestructible\n{T}: Add {C}.', keywords=['Indestructible']),
    card('Kher Keep', set_code="tst", number="22A21", type_line='Land',
         oracle_text='{T}: Add {C}.\n{1}{R}, {T}: Create a 0/1 red Kobold creature token named Kobolds of Kher Keep.'),
    card('Fires of Yavimaya', set_code="tst", number="22A22", mana_cost='{1}{R}{G}', cmc=3.0, type_line='Enchantment',
         oracle_text='Creatures you control have haste.\nSacrifice this enchantment: Target creature gets +2/+2 until end of turn.',
         colors=['R', 'G'], color_identity=['R', 'G']),
    card('Blood Sun', set_code="tst", number="22A23", mana_cost='{2}{R}', cmc=3.0, type_line='Enchantment',
         oracle_text='When this enchantment enters, draw a card.\nAll lands lose all abilities except mana abilities.', colors=['R'],
         color_identity=['R']),
    card('Toxicrene', set_code="tst", number="22A24", mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Tyranid',
         oracle_text='Reach, deathtouch\nHypertoxic Miasma — All lands have "{T}: Add one mana of any color" and lose all other '
                     'abilities.', power='2', toughness='4', colors=['G'], color_identity=['G'], keywords=['Reach', 'Deathtouch']),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def roundtrip(s):
    """Replay rebuilds the same table, and a save/load round trip keeps it."""
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped


def ok(text, name="Card", type_line="Enchantment"):
    sup, types, sub = parse_type_line(type_line)
    feats = coverage.features_of(Characteristics(name=name, supertypes=sup, types=types, subtypes=sub, oracle_text=text,
                                                 abilities=tuple(parse_abilities(text))))
    return all(f.supported for f in feats if f.id.startswith("text:"))


def mana_texts(s, c):
    return sorted(a.text for a in ch(s, c).abilities if a.kind == "mana")


# -- Blood Moon: a land type SET (305.7) ------------------------------------------------------------------------
def test_wordings_are_covered():
    assert ok("Nonbasic lands are Mountains.", "Blood Moon")
    assert ok("Nonbasic lands are Islands.", "Harbinger of the Seas", "Creature — Merfolk Wizard")
    assert ok("All Mountains are Plains.", "Conversion")
    assert ok("All creatures lose all abilities and have base power and toughness 1/1.", "Humility")
    assert ok("Creatures lose all abilities.", "Dress Down")
    assert ok("Each other non-Aura enchantment is a creature in addition to its other types and has base power and base toughness "
              "each equal to its mana value.", "Opalescence")
    assert ok("Each noncreature artifact is an artifact creature with power and toughness each equal to its mana value.",
              "March of the Machines")
    assert ok("All permanents are colorless.", "Thran Lens", "Artifact")
    assert ok("All nonland permanents are legendary.", "Leyline of Singularity")
    # a text this reads only in part is not read at all
    assert not ok("Nonbasic lands are Mountains and have flying.", "Card")
    assert not ok("Creatures lose all abilities until end of turn.", "Card")


def test_blood_moon_sets_land_types_and_takes_the_rules_text(cards):
    s = build(cards, [(1, "Blood Moon"), (1, "Command Tower"), (1, "Forest"), (1, "Kher Keep")])
    tower, forest, keep = (put(s, n, "battlefield") for n in ("Command Tower", "Forest", "Kher Keep"))
    assert mana_texts(s, keep) == ["{T}: Add {C}."]
    put(s, "Blood Moon", "battlefield")
    for land in (tower, keep):  # 305.7: nonbasic: the land types are Mountain only, the rules-text abilities are gone
        assert ch(s, land).subtypes == {"Mountain"} and ch(s, land).types == {"Land"}
        assert mana_texts(s, land) == ["{T}: Add {R}."]  # 305.6: the new type's mana ability
    assert ch(s, forest).subtypes == {"Forest"} and mana_texts(s, forest) == ["{T}: Add {G}."]  # a basic land is not affected
    roundtrip(s)
    put(s, "Blood Moon", "graveyard")  # it leaves: everything is as printed again (611.3b)
    assert mana_texts(s, keep) == ["{T}: Add {C}."] and ch(s, keep).subtypes == set()
    roundtrip(s)


@pytest.mark.parametrize("urborg_first", [True, False])
def test_blood_moon_and_urborg_in_either_order(cards, urborg_first):
    """613.8a: Urborg's ability exists only if Blood Moon doesn't take it away (305.7), so Blood Moon applies first whatever the
    timestamps: every nonbasic land is only a Mountain, and the basic Forest is not a Swamp."""
    s = build(cards, [(1, "Blood Moon"), (1, "Urborg, Tomb of Yawgmoth"), (1, "Forest"), (1, "Command Tower")])
    forest, tower = put(s, "Forest", "battlefield"), put(s, "Command Tower", "battlefield")
    for name in (["Urborg, Tomb of Yawgmoth", "Blood Moon"] if urborg_first else ["Blood Moon", "Urborg, Tomb of Yawgmoth"]):
        put(s, name, "battlefield")
    urborg = next(c for c in s.state.cards.values() if c.name.startswith("Urborg"))
    assert ch(s, urborg).subtypes == {"Mountain"} and ch(s, tower).subtypes == {"Mountain"}
    assert ch(s, forest).subtypes == {"Forest"} and mana_texts(s, forest) == ["{T}: Add {G}."]
    roundtrip(s)
    put(s, "Blood Moon", "graveyard")  # Blood Moon gone: Urborg works again
    assert ch(s, forest).subtypes == {"Forest", "Swamp"} and ch(s, urborg).subtypes == {"Swamp"}
    roundtrip(s)


def test_the_later_land_type_setter_wins(cards):
    """613.7: two effects that set the land types of the same lands apply in timestamp order."""
    s = build(cards, [(1, "Blood Moon"), (1, "Harbinger of the Seas"), (1, "Command Tower")])
    tower = put(s, "Command Tower", "battlefield")
    put(s, "Blood Moon", "battlefield")
    put(s, "Harbinger of the Seas", "battlefield")
    assert ch(s, tower).subtypes == {"Island"} and mana_texts(s, tower) == ["{T}: Add {U}."]
    put(s, "Blood Moon", "graveyard")
    put(s, "Blood Moon", "battlefield")  # a new object: the newest timestamp
    assert ch(s, tower).subtypes == {"Mountain"}
    roundtrip(s)


# -- Humility, Dress Down: a group loses all abilities (613.1f) ---------------------------------------------------------
def test_humility_takes_all_abilities_and_sets_the_base_power_and_toughness(cards):
    s = build(cards, [(1, "Humility"), (1, "Glorious Anthem"), (1, "Lord of Atlantis"), (1, "Harbinger of the Seas"),
                      (1, "Grizzly Bears"), (1, "Command Tower")])
    bears, lord, harb, tower = (put(s, n, "battlefield") for n in ("Grizzly Bears", "Lord of Atlantis", "Harbinger of the Seas",
                                                                  "Command Tower"))
    put(s, "Glorious Anthem", "battlefield")
    assert ch(s, harb).pt == (4, 4) and "islandwalk" in ch(s, harb).keywords  # the Anthem and the lord
    assert ch(s, tower).subtypes == {"Island"}  # (Harbinger's static)
    put(s, "Humility", "battlefield")
    for c in (bears, lord, harb):
        assert ch(s, c).abilities == () and not ch(s, c).keywords
        assert ch(s, c).pt == (2, 2)  # 7b: base 1/1, then the Anthem's +1/+1 in 7c (an Enchantment's static: it keeps its ability)
    # 613.6: Harbinger's effect began in layer 4, before Humility took its ability in layer 6: it keeps applying to the same lands
    assert ch(s, tower).subtypes == {"Island"}
    roundtrip(s)
    put(s, "Humility", "graveyard")
    assert ch(s, harb).pt == (4, 4) and ch(s, tower).subtypes == {"Island"}
    roundtrip(s)


def test_dress_down_takes_abilities_only(cards):
    s = build(cards, [(1, "Dress Down"), (1, "Lord of Atlantis"), (1, "Harbinger of the Seas")])
    lord, harb = put(s, "Lord of Atlantis", "battlefield"), put(s, "Harbinger of the Seas", "battlefield")
    assert ch(s, harb).pt == (3, 3)
    put(s, "Dress Down", "battlefield")
    assert ch(s, harb).pt == (2, 2) and ch(s, harb).abilities == () and ch(s, lord).abilities == ()  # base 2/2, nothing else changes
    roundtrip(s)


# -- Opalescence: a group animated, each with its own base power and toughness (613.1d, 613.4b) -----------------------
def test_opalescence_makes_each_other_non_aura_enchantment_a_creature_with_its_mana_value(cards):
    s = build(cards, [(1, "Opalescence"), (1, "Glorious Anthem"), (1, "Fires of Yavimaya"), (1, "Grizzly Bears")])
    anthem, fires = put(s, "Glorious Anthem", "battlefield"), put(s, "Fires of Yavimaya", "battlefield")
    bears = put(s, "Grizzly Bears", "battlefield")
    opal = put(s, "Opalescence", "battlefield")
    assert not ch(s, opal).is_creature  # "other"
    for enchantment, mv in ((anthem, 3), (fires, 3)):
        assert ch(s, enchantment).is_creature and "Enchantment" in ch(s, enchantment).types
    assert ch(s, fires).pt == (4, 4) and ch(s, bears).pt == (3, 3)  # 3/3, and the Anthem's +1/+1 for every creature (itself too)
    assert ch(s, anthem).pt == (4, 4)
    roundtrip(s)
    put(s, "Opalescence", "graveyard")
    assert not ch(s, anthem).is_creature and ch(s, bears).pt == (3, 3)  # (the Anthem: +1/+1 for the creatures you control)
    roundtrip(s)


@pytest.mark.parametrize("humility_first", [True, False])
def test_humility_and_opalescence_in_either_order(cards, humility_first):
    """The Gatherer ruling of Opalescence / Humility, from 613.7 and 613.6: Opalescence makes the other enchantments creatures in
    layer 4; Humility's effect begins in layer 6 and applies to every creature, itself included (it keeps applying to the same
    objects in layer 7b even though it lost its own ability, 613.6); in layer 7b the later timestamp wins: Humility newer: every
    one of these creatures is 1/1; Opalescence newer: the enchantments are as big as their mana value."""
    s = build(cards, [(1, "Humility"), (1, "Opalescence"), (1, "Glorious Anthem"), (1, "Grizzly Bears")])
    bears = put(s, "Grizzly Bears", "battlefield")
    anthem = put(s, "Glorious Anthem", "battlefield")
    for name in (["Humility", "Opalescence"] if humility_first else ["Opalescence", "Humility"]):
        put(s, name, "battlefield")
    humility = next(c for c in s.state.cards.values() if c.name == "Humility")
    opal = next(c for c in s.state.cards.values() if c.name == "Opalescence")
    assert not ch(s, opal).is_creature and ch(s, opal).abilities and ch(s, bears).abilities == ()
    assert ch(s, humility).is_creature and ch(s, humility).abilities == () and ch(s, anthem).abilities == ()
    # the Anthem has no abilities (Humility): its bonus is gone
    if humility_first:
        assert (ch(s, humility).pt, ch(s, anthem).pt, ch(s, bears).pt) == ((4, 4), (3, 3), (1, 1))
    else:
        assert (ch(s, humility).pt, ch(s, anthem).pt, ch(s, bears).pt) == ((1, 1), (1, 1), (1, 1))
    roundtrip(s)
    put(s, "Humility", "graveyard")  # Humility gone: the creatures have their abilities again
    assert ch(s, anthem).abilities and ch(s, anthem).pt == (4, 4) and ch(s, bears).pt == (3, 3)
    roundtrip(s)


@pytest.mark.parametrize("dress_down_first", [True, False])
def test_two_effects_that_take_abilities_away_apply_in_timestamp_order(cards, dress_down_first):
    """613.8b: Dress Down's and Humility's effects each remove the other's ability (both are creatures under Opalescence), a
    dependency loop, so they apply in timestamp order (613.7): the older takes the other's ability away before it begins to apply
    (613.6), so only its effect is there."""
    s = build(cards, [(1, "Opalescence"), (1, "Dress Down"), (1, "Humility"), (1, "Grizzly Bears")])
    bears = put(s, "Grizzly Bears", "battlefield")
    put(s, "Opalescence", "battlefield")
    for name in (["Dress Down", "Humility"] if dress_down_first else ["Humility", "Dress Down"]):
        put(s, name, "battlefield")
    assert ch(s, bears).abilities == ()
    assert ch(s, bears).pt == ((2, 2) if dress_down_first else (1, 1))  # (only Humility sets a base power and toughness)
    roundtrip(s)


# -- March of the Machines: the group is not what the subject says any more by layer 7b (613.6) ----------------------------
@pytest.mark.parametrize("humility_first", [True, False])
def test_march_of_the_machines_and_humility(cards, humility_first):
    s = build(cards, [(1, "March of the Machines"), (1, "Humility"), (1, "Mind Stone"), (1, "Sol Ring"), (1, "Painter's Servant")])
    stone, ring, servant = (put(s, n, "battlefield") for n in ("Mind Stone", "Sol Ring", "Painter's Servant"))
    put(s, "March of the Machines", "battlefield")
    assert ch(s, stone).is_creature and ch(s, stone).types == {"Artifact", "Creature"}
    assert ch(s, stone).pt == (2, 2) and ch(s, ring).pt == (1, 1)  # 613.6: still "each noncreature artifact" in layer 7b
    assert ch(s, servant).pt == (1, 3)  # an artifact creature already: not affected
    assert mana_texts(s, stone) == ["{T}: Add {C}."]
    put(s, "Humility", "battlefield")  # (newest: its 1/1 beats the mana value)
    assert ch(s, stone).abilities == () and ch(s, stone).pt == (1, 1)
    roundtrip(s)
    if not humility_first:
        put(s, "March of the Machines", "graveyard")
        put(s, "March of the Machines", "battlefield")  # March is newest now: its mana values come after Humility's 1/1
        assert ch(s, stone).pt == (2, 2) and ch(s, stone).abilities == ()
        roundtrip(s)


# -- colors, supertypes and added types of groups, in every zone (613.1d-e, 611.3) ----------------------------------------
def test_thran_lens_makes_permanents_colorless(cards):
    s = build(cards, [(1, "Thran Lens"), (1, "Grizzly Bears"), (1, "Lightning Bolt")])
    bears, bolt = put(s, "Grizzly Bears", "battlefield"), put(s, "Lightning Bolt", "hand")
    assert ch(s, bears).colors == {"G"}
    put(s, "Thran Lens", "battlefield")
    assert ch(s, bears).colors == set() and ch(s, bolt).colors == {"R"}  # (permanents only)
    roundtrip(s)
    put(s, "Thran Lens", "graveyard")
    assert ch(s, bears).colors == {"G"}


def test_mycosynth_lattice_colors_every_object_in_every_zone(cards):
    s = build(cards, [(1, "Mycosynth Lattice"), (1, "Grizzly Bears"), (1, "Lightning Bolt"), (1, "Murder")],
              [(1, "Forest"), (9, "Island")])
    bears, bolt, murder = (put(s, n, "hand") for n in ("Grizzly Bears", "Lightning Bolt", "Murder"))
    gy = put(s, "Murder", "graveyard")
    theirs = put(s, "Forest", "battlefield", pid="p2")
    assert ch(s, bolt).colors == {"R"} and ch(s, gy).colors == {"B"}
    put(s, "Mycosynth Lattice", "battlefield")
    for c in (bolt, gy, bears, murder):  # hand, graveyard (any owner's, any zone: 205.? "cards that aren't on the battlefield")
        assert ch(s, c).colors == set()
    assert "Artifact" in ch(s, theirs).types  # (the first line: all permanents are artifacts)
    mana(s, G=1, C=1)
    hold(s)
    act(s, "p1", type="cast_spell", card_id=bears.id)  # a spell (on the stack): colorless too
    assert s.state.cards[bears.id].zone == "stack" and ch(s, bears).colors == set()
    roundtrip(s)
    put(s, "Mycosynth Lattice", "graveyard")
    assert ch(s, bolt).colors == {"R"} and ch(s, bears).colors == {"G"}


def cast_servant(s, color):
    spell = put(s, "Painter's Servant", "hand")
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    pass_until_stack_empty(s)
    d = rules(s).decision
    assert [o.id for o in d.options] == ["White", "Blue", "Black", "Red", "Green"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[color])
    pass_until_stack_empty(s)
    return s.state.cards[spell.id]


def test_painters_servant_adds_the_chosen_color_in_every_zone(cards):
    s = build(cards, [(1, "Painter's Servant"), (1, "Grizzly Bears"), (1, "Lightning Bolt")])
    bolt, bears = put(s, "Lightning Bolt", "hand"), put(s, "Grizzly Bears", "battlefield")
    servant = cast_servant(s, "Blue")
    assert servant.zone.endswith(":battlefield") and servant.choices == {"Chosen color": "Blue"}
    assert ch(s, bolt).colors == {"R", "U"} and ch(s, bears).colors == {"G", "U"}  # "in addition to their other colors"
    assert ch(s, servant).colors == {"U"}  # (colorless, now blue)
    roundtrip(s)


@pytest.mark.parametrize("lattice_first", [True, False])
def test_mycosynth_lattice_and_painters_servant_in_timestamp_order(cards, lattice_first):
    """613.7: both effects are in layer 5 and neither depends on the other: the later one wins (Lattice: colorless; the Servant:
    its color in addition to the others)."""
    s = build(cards, [(1, "Painter's Servant"), (1, "Mycosynth Lattice"), (1, "Lightning Bolt")])
    bolt = put(s, "Lightning Bolt", "hand")
    if lattice_first:
        put(s, "Mycosynth Lattice", "battlefield")
        servant = cast_servant(s, "Green")
        assert ch(s, bolt).colors == {"G"} and ch(s, servant).colors == {"G"}
    else:
        servant = cast_servant(s, "Green")
        put(s, "Mycosynth Lattice", "battlefield")
        assert ch(s, bolt).colors == set() and ch(s, servant).colors == set()
    roundtrip(s)


def test_leyline_of_singularity_makes_nonland_permanents_legendary(cards):
    s = build(cards, [(1, "Leyline of Singularity"), (1, "Grizzly Bears"), (1, "Forest")])
    bears, forest = put(s, "Grizzly Bears", "battlefield"), put(s, "Forest", "battlefield")
    put(s, "Leyline of Singularity", "battlefield")
    assert "Legendary" in ch(s, bears).supertypes and "Legendary" not in ch(s, forest).supertypes
    roundtrip(s)
    put(s, "Leyline of Singularity", "graveyard")
    assert "Legendary" not in ch(s, bears).supertypes


def test_encroaching_mycosynth_adds_artifact_to_your_nonland_permanents_spells_and_cards(cards):
    s = build(cards, [(1, "Encroaching Mycosynth"), (1, "Grizzly Bears"), (1, "Lightning Bolt"), (1, "Forest"), (1, "Mind Stone")],
              [(1, "Grizzly Bears"), (9, "Island")])
    mine, bolt, forest = put(s, "Grizzly Bears", "battlefield"), put(s, "Lightning Bolt", "hand"), put(s, "Forest", "battlefield")
    stone = put(s, "Mind Stone", "graveyard")
    theirs = put(s, "Grizzly Bears", "battlefield", pid="p2")
    put(s, "Encroaching Mycosynth", "battlefield")
    assert ch(s, mine).types == {"Creature", "Artifact"} and ch(s, theirs).types == {"Creature"}  # "you control"
    assert ch(s, forest).types == {"Land"} and ch(s, bolt).types == {"Instant"}  # nonland permanent cards only
    assert ch(s, stone).types == {"Artifact"}
    in_hand = put(s, "Grizzly Bears", "hand")
    assert ch(s, in_hand).types == {"Creature", "Artifact"}  # a permanent card you own, not on the battlefield
    assert ch(s, put(s, "Grizzly Bears", "hand", pid="p2")).types == {"Creature"}
    roundtrip(s)


# -- animated lands: a group that stays what it was (613.1d, 613.6) -------------------------------------------------
def test_kormus_bell_animates_swamps_and_urborg_makes_every_land_one(cards):
    s = build(cards, [(1, "Kormus Bell"), (1, "Urborg, Tomb of Yawgmoth"), (1, "Forest")])
    forest = put(s, "Forest", "battlefield")
    put(s, "Kormus Bell", "battlefield")
    assert not ch(s, forest).is_creature
    put(s, "Urborg, Tomb of Yawgmoth", "battlefield")  # 613.8: the Bell's "Swamps" depends on Urborg: it waits for it
    urborg = next(c for c in s.state.cards.values() if c.name.startswith("Urborg"))
    for land in (forest, urborg):
        assert ch(s, land).types == {"Land", "Creature"} and ch(s, land).pt == (1, 1) and ch(s, land).colors == {"B"}
    roundtrip(s)


def test_ambush_commander_makes_your_forests_green_elves(cards):
    s = build(cards, [(1, "Ambush Commander"), (1, "Forest"), (1, "Command Tower")], [(1, "Forest"), (9, "Island")])
    mine, tower, theirs = put(s, "Forest", "battlefield"), put(s, "Command Tower", "battlefield"), put(s, "Forest", "battlefield", pid="p2")
    put(s, "Ambush Commander", "battlefield")
    assert ch(s, mine).types == {"Land", "Creature"} and "Elf" in ch(s, mine).subtypes and "Forest" in ch(s, mine).subtypes
    assert ch(s, mine).pt == (1, 1) and ch(s, mine).colors == {"G"}
    assert not ch(s, tower).is_creature and not ch(s, theirs).is_creature
    roundtrip(s)


# -- Blood Sun and Toxicrene: all abilities but mana abilities (613.1f) -------------------------------------------------------
def test_blood_sun_lands_keep_only_mana_abilities(cards):
    s = build(cards, [(1, "Blood Sun"), (1, "Kher Keep"), (1, "Command Tower")])
    keep, tower = put(s, "Kher Keep", "battlefield"), put(s, "Command Tower", "battlefield")
    assert any(a.kind != "mana" for a in ch(s, keep).abilities)
    put(s, "Blood Sun", "battlefield")
    assert [a.kind for a in ch(s, keep).abilities] == ["mana"] and mana_texts(s, tower) == mana_texts(s, tower)
    assert [a.text for a in ch(s, keep).abilities] == ["{T}: Add {C}."]
    roundtrip(s)
    put(s, "Blood Sun", "graveyard")
    assert any(a.kind != "mana" for a in ch(s, keep).abilities)


def test_toxicrene_lands_have_one_mana_ability_and_lose_the_rest(cards):
    s = build(cards, [(1, "Toxicrene"), (1, "Kher Keep"), (1, "Forest")])
    keep, forest = put(s, "Kher Keep", "battlefield"), put(s, "Forest", "battlefield")
    put(s, "Toxicrene", "battlefield")
    assert [a.text for a in ch(s, keep).abilities] == ["{T}: Add one mana of any color."]
    assert [a.text for a in ch(s, forest).abilities] == ["{T}: Add one mana of any color."]  # (the intrinsic one is lost too)
    roundtrip(s)
