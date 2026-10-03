"""Type-setting statics, entering as a copy and entry forms (wave 5F), researched against CR 2026-09-25.

* Group statics that add types (613.1d, 205.1b, 205.3m, 305.6, 305.7, 613.8): app/rules/type_statics.py.

Every scenario uses real Commander-legal cards with their current Oracle text (data/cards.sqlite), checks that
replaying the recorded history reproduces the table, and that a save/load round trip keeps it.
"""

from __future__ import annotations

import pytest

from app.game.state import GameState
from app.rules import coverage
from app.rules.casting import castable, mana_sources
from app.rules.characteristics import Characteristics, parse_type_line
from app.rules.creature_types import CREATURE_TYPES
from app.rules.oracle import parse_abilities
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_permissions import build, hold, put

EXTRA = [
    card('Urborg, Tomb of Yawgmoth', set_code="tst", number="5F01", type_line='Legendary Land',
         oracle_text='Each land is a Swamp in addition to its other land types.'),
    card('Yavimaya, Cradle of Growth', set_code="tst", number="5F02", type_line='Legendary Land',
         oracle_text='Each land is a Forest in addition to its other land types.'),
    card('Dryad of the Ilysian Grove', set_code="tst", number="5F03", mana_cost='{2}{G}', cmc=3.0,
         type_line='Enchantment Creature — Nymph Dryad',
         oracle_text='You may play an additional land on each of your turns.\nLands you control are every basic land type in '
                     'addition to their other types.', power='2', toughness='4', colors=['G'], color_identity=['G']),
    card('Maskwood Nexus', set_code="tst", number="5F04", mana_cost='{4}', cmc=4.0, type_line='Artifact',
         oracle_text="Creatures you control are every creature type. The same is true for creature spells you control and creature "
                     "cards you own that aren't on the battlefield.\n{3}, {T}: Create a 2/2 blue Shapeshifter creature token with "
                     "changeling. (It is every creature type.)"),
    card('Ashaya, Soul of the Wild', set_code="tst", number="5F05", mana_cost='{3}{G}{G}', cmc=5.0,
         type_line='Legendary Creature — Elemental',
         oracle_text="Ashaya's power and toughness are each equal to the number of lands you control.\nNontoken creatures you control "
                     "are Forest lands in addition to their other types. (They're still affected by summoning sickness.)",
         power='*', toughness='*', colors=['G'], color_identity=['G']),
    card('Prismatic Omen', set_code="tst", number="5F06", mana_cost='{1}{G}', cmc=2.0, type_line='Enchantment',
         oracle_text='Lands you control are every basic land type in addition to their other types.', colors=['G'],
         color_identity=['G']),
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


def ok(text, name="Card", type_line="Creature — Test"):
    """Is every text line automated (coverage) on a card with that name and type?"""
    sup, types, sub = parse_type_line(type_line)
    feats = coverage.features_of(Characteristics(name=name, supertypes=sup, types=types, subtypes=sub, oracle_text=text,
                                                 abilities=tuple(parse_abilities(text))))
    return all(f.supported for f in feats if f.id.startswith("text:"))


def mana_texts(s, c):
    return sorted(a.text for a in ch(s, c).abilities if a.kind == "mana")


# -- type statics: the wording ------------------------------------------------------------------------------
def test_type_static_wordings_are_covered():
    assert ok("Each land is a Swamp in addition to its other land types.", "Urborg, Tomb of Yawgmoth", "Legendary Land")
    assert ok("Lands you control are every basic land type in addition to their other types.", "Prismatic Omen", "Enchantment")
    assert ok("Nontoken creatures you control are Forest lands in addition to their other types.", "Ashaya, Soul of the Wild")
    assert ok("Creatures you control are every creature type. The same is true for creature spells you control and creature "
              "cards you own that aren't on the battlefield.", "Maskwood Nexus", "Artifact")
    # a land type SET (305.7: the land loses its other land types and rules-text abilities) is not read
    assert not ok("Nonbasic lands are Mountains.", "Blood Moon", "Enchantment")
    assert not ok("Each land is a Swamp.", "Card", "Enchantment")
    assert not ok("Each land is a Desert in addition to its other land types.", "Card", "Enchantment")


# -- Urborg / Yavimaya (613.1d, 305.7) --------------------------------------------------------------------------
def test_urborg_makes_every_land_a_swamp_with_its_mana_ability(cards):
    s = build(cards, [(1, "Urborg, Tomb of Yawgmoth"), (1, "Forest"), (1, "Command Tower"), (1, "Murder")],
              [(1, "Island"), (9, "Island")])
    forest, tower = put(s, "Forest", "battlefield"), put(s, "Command Tower", "battlefield")
    island = put(s, "Island", "battlefield", pid="p2")
    assert "Swamp" not in ch(s, forest).subtypes
    urborg = put(s, "Urborg, Tomb of Yawgmoth", "battlefield")
    for land in (forest, tower, island, urborg):  # each land, any controller's, Urborg itself too
        assert "Swamp" in ch(s, land).subtypes
        assert "{T}: Add {B}." in mana_texts(s, land)  # 305.6: the intrinsic mana ability
    assert mana_texts(s, forest) == ["{T}: Add {B}.", "{T}: Add {G}."]  # it keeps its own (305.7: "in addition")
    assert any("commander's color identity" in t for t in mana_texts(s, tower))  # its rules text stays
    assert "Forest" in ch(s, forest).subtypes and "Land" in ch(s, forest).types
    # the auto-payer sees it: Murder ({1}{B}{B}) is castable from the Forest, Command Tower and Urborg
    murder = put(s, "Murder", "hand")
    assert castable(s.state, "p1", murder, cards)
    assert any("B" in "".join(o) for src in mana_sources(s.state, "p1", cards) for o in src.options if src.card_id == forest.id)
    # tapping the Forest for black mana
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=92)
    assert s.state.cards[forest.id].tapped
    roundtrip(s)
    put(s, "Urborg, Tomb of Yawgmoth", "graveyard")
    assert "Swamp" not in ch(s, forest).subtypes and mana_texts(s, forest) == ["{T}: Add {G}."]
    roundtrip(s)


def test_urborg_and_yavimaya_together(cards):
    s = build(cards, [(1, "Urborg, Tomb of Yawgmoth"), (1, "Yavimaya, Cradle of Growth"), (1, "Island")])
    island = put(s, "Island", "battlefield")
    put(s, "Urborg, Tomb of Yawgmoth", "battlefield")
    yav = put(s, "Yavimaya, Cradle of Growth", "battlefield")
    assert {"Island", "Swamp", "Forest"} <= ch(s, island).subtypes
    assert mana_texts(s, island) == ["{T}: Add {B}.", "{T}: Add {G}.", "{T}: Add {U}."]
    assert {"Swamp", "Forest"} <= ch(s, yav).subtypes
    roundtrip(s)


# -- Dryad / Prismatic Omen: "lands you control" ----------------------------------------------------------------
def test_dryad_gives_only_your_lands_every_basic_land_type(cards):
    s = build(cards, [(1, "Dryad of the Ilysian Grove"), (1, "Command Tower")], [(1, "Island"), (9, "Island")])
    tower = put(s, "Command Tower", "battlefield")
    theirs = put(s, "Island", "battlefield", pid="p2")
    put(s, "Dryad of the Ilysian Grove", "battlefield")
    assert {"Plains", "Island", "Swamp", "Mountain", "Forest"} <= ch(s, tower).subtypes
    assert len([t for t in mana_texts(s, tower) if t.startswith("{T}: Add {") and len(t) == 13]) == 5
    assert ch(s, theirs).subtypes == frozenset({"Island"})
    roundtrip(s)


# -- Ashaya: creatures become Forest lands (and Dryad then sees them: 613.8) --------------------------------------
def test_ashaya_makes_nontoken_creatures_forest_lands(cards):
    s = build(cards, [(1, "Ashaya, Soul of the Wild"), (1, "Grizzly Bears"), (2, "Forest"), (1, "Prismatic Omen")])
    bears = put(s, "Grizzly Bears", "battlefield")
    act(s, "p1", type="create_token", player="p1", token={"name": "Spirit", "type_line": "Token Creature — Spirit",
                                                          "power": "1", "toughness": "1", "text": "", "colors": []})
    spirit = next(c for c in s.state.cards.values() if c.name == "Spirit")
    put(s, "Forest", "battlefield")
    ashaya = put(s, "Ashaya, Soul of the Wild", "battlefield")
    for c in (bears, ashaya):
        got = ch(s, c)
        assert "Land" in got.types and "Creature" in got.types and {"Forest", "Bear" if c is bears else "Elemental"} <= got.subtypes
        assert "{T}: Add {G}." in mana_texts(s, c)
    assert "Land" not in ch(s, spirit).types  # a token isn't
    assert ch(s, ashaya).pt == (3, 3)  # its own CDA counts the lands it made: Forest, Bears, Ashaya
    # Prismatic Omen's "lands you control" applies to the creature lands too (613.8: it depends on Ashaya)
    put(s, "Prismatic Omen", "battlefield")
    assert {"Plains", "Island", "Swamp", "Mountain", "Forest"} <= ch(s, bears).subtypes
    roundtrip(s)
    put(s, "Ashaya, Soul of the Wild", "graveyard")
    assert "Land" not in ch(s, bears).types and "Forest" not in ch(s, bears).subtypes
    roundtrip(s)


# -- Maskwood Nexus (205.3m) ----------------------------------------------------------------------------------
def test_maskwood_nexus_every_creature_type_everywhere(cards):
    s = build(cards, [(1, "Maskwood Nexus"), (2, "Grizzly Bears"), (1, "Llanowar Elves")], [(1, "Grizzly Bears"), (9, "Island")])
    bears = put(s, "Grizzly Bears", "battlefield")
    theirs = put(s, "Grizzly Bears", "battlefield", pid="p2")
    elves = put(s, "Llanowar Elves", "hand")
    put(s, "Maskwood Nexus", "battlefield")
    assert ch(s, bears).subtypes >= CREATURE_TYPES
    assert ch(s, elves).subtypes >= CREATURE_TYPES  # a creature card you own in your hand
    assert "Goblin" not in ch(s, theirs).subtypes  # not an opponent's creature
    grave = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1" and c.id != bears.id)
    act(s, "p1", type="move", card_ids=[grave.id], to={"player": "p1", "zone": "graveyard"})
    assert ch(s, grave).subtypes >= CREATURE_TYPES  # a creature card in your graveyard
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1})
    hold(s)
    act(s, "p1", type="cast_spell", card_id=elves.id)
    assert s.state.cards[elves.id].zone == "stack"
    assert ch(s, elves).subtypes >= CREATURE_TYPES  # a creature spell you control
    pass_until_stack_empty(s)
    roundtrip(s)
