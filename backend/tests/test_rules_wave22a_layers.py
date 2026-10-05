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
from tests.test_rules_effects import replay_matches
from tests.test_rules_permissions import build, put

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
    card('Knight of Glory', set_code="tst", number="22A18", mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Human Knight',
         oracle_text='Other creatures you control get +1/+1 and have flying.', power='2', toughness='2', colors=['W'],
         color_identity=['W']),
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
