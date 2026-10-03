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
    card('Mystic Sanctuary', set_code="tst", number="5F101", type_line='Land — Island',
         oracle_text='({T}: Add {U}.)\nThis land enters tapped unless you control three or more other Islands.\nWhen this land enters '
                     'untapped, you may put target instant or sorcery card from your graveyard on top of your library.',
         color_identity=['U']),
    card('Dwarven Mine', set_code="tst", number="5F103", type_line='Land — Mountain',
         oracle_text='({T}: Add {R}.)\nThis land enters tapped unless you control three or more other Mountains.\nWhen this land '
                     'enters untapped, create a 1/1 red Dwarf creature token.', color_identity=['R']),
    card('Amulet of Vigor', set_code="tst", number="5F105", mana_cost='{1}', cmc=1.0, type_line='Artifact',
         oracle_text='Whenever a permanent you control enters tapped, untap it.'),
    card('Thriving Isle', set_code="tst", number="5F106", type_line='Land',
         oracle_text='This land enters tapped. As it enters, choose a color other than blue.\n{T}: Add {U} or one mana of the chosen '
                     'color.', color_identity=['U']),
    card("Valgavoth's Lair", set_code="tst", number="5F107", type_line='Enchantment Land',
         oracle_text='Hexproof\nThis land enters tapped. As it enters, choose a color.\n{T}: Add one mana of the chosen color.',
         keywords=['Hexproof']),
    card('Cursed Mirror', set_code="tst", number="5F201", mana_cost='{2}{R}', cmc=3.0, type_line='Artifact',
         oracle_text='{T}: Add {R}.\nAs this artifact enters, you may have it become a copy of any creature on the battlefield until '
                     'end of turn, except it has haste.', colors=['R'], color_identity=['R']),
    card('Vesuva', set_code="tst", number="5F202", type_line='Land',
         oracle_text='You may have this land enter tapped as a copy of any land on the battlefield.'),
    card('Mirrormade', set_code="tst", number="5F203", mana_cost='{1}{U}{U}', cmc=3.0, type_line='Enchantment',
         oracle_text='You may have this enchantment enter as a copy of any artifact or enchantment on the battlefield.', colors=['U'],
         color_identity=['U']),
    card('Clever Impersonator', set_code="tst", number="5F204", mana_cost='{2}{U}{U}', cmc=4.0, type_line='Creature — Shapeshifter',
         oracle_text='You may have this creature enter as a copy of any nonland permanent on the battlefield.', power='0',
         toughness='0', colors=['U'], color_identity=['U']),
    card('Masterwork of Ingenuity', set_code="tst", number="5F205", mana_cost='{1}', cmc=1.0, type_line='Artifact — Equipment',
         oracle_text='You may have this Equipment enter as a copy of any Equipment on the battlefield.'),
    card('Synth Infiltrator', set_code="tst", number="5F206", mana_cost='{3}{U}{U}', cmc=5.0, type_line='Artifact Creature — Synth',
         oracle_text="Improvise (Your artifacts can help cast this spell. Each artifact you tap after you're done activating mana "
                     "abilities pays for {1}.)\nYou may have this creature enter as a copy of any creature on the battlefield, except "
                     "it's a Synth artifact creature in addition to its other types.", power='0', toughness='0', colors=['U'],
         color_identity=['U'], keywords=['Improvise']),
    card('Enduring Curiosity', set_code="tst", number="5F401", mana_cost='{2}{U}{U}', cmc=4.0,
         type_line='Enchantment Creature — Cat Glimmer',
         oracle_text="Flash\nWhenever a creature you control deals combat damage to a player, draw a card.\nWhen Enduring Curiosity "
                     "dies, if it was a creature, return it to the battlefield under its owner's control. It's an enchantment. (It's "
                     "not a creature.)", power='4', toughness='3', colors=['U'], color_identity=['U'], keywords=['Flash']),
    card('Disenchant', set_code="tst", number="5F501", mana_cost='{1}{W}', cmc=2.0, type_line='Instant',
         oracle_text='Destroy target artifact or enchantment.', colors=['W'], color_identity=['W']),
    card('Reanimate', set_code="tst", number="5F301", mana_cost='{B}', cmc=1.0, type_line='Sorcery',
         oracle_text="Put target creature card from a graveyard onto the battlefield under your control. You lose life equal to that "
                     "card's mana value.", colors=['B'], color_identity=['B']),
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


# -- "enters untapped" / "enters tapped" triggers (603.2, 614.1d) ------------------------------------------------------
def rules(s):
    return s.state.rules


def drive(s, choose=None):
    """Resolve the stack; ``choose(decision)`` answers each decision (option ids), the first option otherwise."""
    for _ in range(30):
        d = rules(s).decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=(choose(d) if choose else [d.options[0].id]))
            continue
        if not s.state.zones.get("stack"):
            return
        act(s, rules(s).priority, type="pass_priority")


def put_all(s, name, where, pid="p1"):
    ids = [c.id for c in s.state.cards.values() if c.name == name and c.owner == pid]
    act(s, pid, type="move", card_ids=ids, to={"player": pid, "zone": where})


def play(s, name, pid="p1"):
    land = put(s, name, "hand", pid=pid)
    act(s, pid, type="play_land", card_id=land.id)
    return s.state.cards[land.id]


def test_entry_trigger_wordings_are_covered():
    assert ok("When this land enters untapped, create a 1/1 red Dwarf creature token.", "Dwarven Mine", "Land — Mountain")
    assert ok("Whenever a permanent you control enters tapped, untap it.", "Amulet of Vigor", "Artifact")
    assert not ok("Whenever one or more lands you control enter tapped, draw a card.", "Card", "Artifact")


def test_mystic_sanctuary_enters_tapped_nothing_triggers(cards):
    s = build(cards, [(1, "Mystic Sanctuary"), (1, "Opt")])
    put(s, "Opt", "graveyard")
    land = play(s, "Mystic Sanctuary")  # no other Islands: it enters tapped
    assert land.tapped and not s.state.zones.get("stack") and rules(s).decision is None
    roundtrip(s)


def test_mystic_sanctuary_enters_untapped_puts_a_spell_on_top(cards):
    s = build(cards, [(1, "Mystic Sanctuary"), (3, "Island"), (1, "Opt")])
    opt = put(s, "Opt", "graveyard")
    put_all(s, "Island", "battlefield")
    land = play(s, "Mystic Sanctuary")
    assert not land.tapped
    drive(s, lambda d: [opt.id] if any(o.id == opt.id for o in d.options) else ["yes"])
    assert s.state.zones["p1:library"][0] == opt.id  # on top of the library
    roundtrip(s)


def test_dwarven_mine_untapped_makes_a_dwarf(cards):
    s = build(cards, [(1, "Dwarven Mine"), (3, "Mountain")])
    put_all(s, "Mountain", "battlefield")
    play(s, "Dwarven Mine")
    drive(s)
    assert [c.name for c in s.state.cards.values() if c.is_token] == ["Dwarf"]
    roundtrip(s)


def test_amulet_of_vigor_untaps_what_enters_tapped(cards):
    s = build(cards, [(1, "Amulet of Vigor"), (1, "Mystic Sanctuary"), (1, "Opt")])
    put(s, "Opt", "graveyard")
    put(s, "Amulet of Vigor", "battlefield")
    sanctuary = play(s, "Mystic Sanctuary")  # enters tapped (no other Islands)
    assert [e.tapped for e in rules(s).turn_log.entered if e.card == sanctuary.id] == [True]
    drive(s)
    assert not s.state.cards[sanctuary.id].tapped  # Amulet untapped it …
    # … but it entered tapped: its "enters untapped" ability never triggered (its target was never asked for)
    assert "Opt" in [s.state.cards[c].name for c in s.state.zones["p1:graveyard"]]
    roundtrip(s)


def test_thriving_land_enters_tapped_with_a_color_other_than_its_own(cards):
    s = build(cards, [(1, "Thriving Isle"), (1, "Amulet of Vigor")])
    isle = put(s, "Thriving Isle", "hand")
    act(s, "p1", type="play_land", card_id=isle.id)
    d = rules(s).decision  # 614.12a: chosen before it enters
    assert d is not None and [o.id for o in d.options] == ["White", "Black", "Red", "Green"]  # not blue
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["Red"])
    isle = s.state.cards[isle.id]
    assert isle.zone == "p1:battlefield" and isle.tapped and isle.choices == {"Chosen color": "Red"}
    roundtrip(s)


def test_thriving_land_untapped_by_amulet_taps_for_either_color(cards):
    s = build(cards, [(1, "Thriving Isle"), (1, "Amulet of Vigor")])
    put(s, "Amulet of Vigor", "battlefield")
    isle = put(s, "Thriving Isle", "hand")
    act(s, "p1", type="play_land", card_id=isle.id)
    act(s, "p1", type="choose", decision_id=rules(s).decision.id, option_ids=["Black"])
    drive(s)
    assert not s.state.cards[isle.id].tapped  # Amulet of Vigor untapped it
    options = {o for src in mana_sources(s.state, "p1", cards) if src.card_id == isle.id for o in src.options}
    assert options == {("U",), ("B",)}
    roundtrip(s)


def test_valgavoths_lair_any_color(cards):
    s = build(cards, [(1, "Valgavoth's Lair")])
    lair = put(s, "Valgavoth's Lair", "hand")
    act(s, "p1", type="play_land", card_id=lair.id)
    d = rules(s).decision
    assert [o.id for o in d.options] == ["White", "Blue", "Black", "Red", "Green"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["Green"])
    assert s.state.cards[lair.id].tapped and s.state.cards[lair.id].choices == {"Chosen color": "Green"}
    roundtrip(s)


def test_amulet_ignores_what_enters_untapped(cards):
    s = build(cards, [(1, "Amulet of Vigor"), (1, "Forest")])
    put(s, "Amulet of Vigor", "battlefield")
    play(s, "Forest")
    assert not s.state.zones.get("stack") and rules(s).decision is None
    roundtrip(s)


# -- entering as a copy (707.5, 614.1c, 614.12a, 707.9) -----------------------------------------------------------------
def copy_pick(target_id):
    """Answer the "… to copy" choice with ``target_id`` ("none": copy nothing); anything else: the first option."""
    def choose(d):
        if d.prompt.endswith("to copy"):
            return [target_id]
        return [d.options[0].id]
    return choose


def cast(s, name, pick, **pool):
    spell = put(s, name, "hand")
    act(s, "p1", type="add_mana", player="p1", mana=pool)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    drive(s, copy_pick(pick))
    return s.state.cards[spell.id]


def test_clone_variant_wordings_are_covered():
    assert ok("You may have this land enter tapped as a copy of any land on the battlefield.", "Vesuva", "Land")
    assert ok("You may have this creature enter as a copy of any nonland permanent on the battlefield.", "Clever Impersonator")
    assert ok("You may have this enchantment enter as a copy of any artifact or enchantment on the battlefield.", "Mirrormade",
              "Enchantment")
    assert ok("As this artifact enters, you may have it become a copy of any creature on the battlefield until end of turn, "
              "except it has haste.", "Cursed Mirror", "Artifact")
    assert ok("You may have this creature enter as a copy of any creature on the battlefield, except it's a Synth artifact "
              "creature in addition to its other types.", "Synth Infiltrator", "Artifact Creature — Synth")
    # still refused: a mana value sized by the mana spent (Mockingbird), a card in a graveyard (Body Double)
    assert not ok("You may have this creature enter as a copy of any creature on the battlefield with mana value less than or "
                  "equal to the amount of mana spent to cast this creature, except it's a Bird in addition to its other types "
                  "and it has flying.", "Mockingbird")
    assert not ok("You may have this creature enter as a copy of any creature card in a graveyard.", "Body Double")


def test_vesuva_enters_tapped_as_a_copy_of_a_land(cards):
    s = build(cards, [(1, "Vesuva"), (1, "Urborg, Tomb of Yawgmoth"), (1, "Forest")], [(1, "Island"), (9, "Island")])
    urborg = put(s, "Urborg, Tomb of Yawgmoth", "battlefield")
    island = put(s, "Island", "battlefield", pid="p2")  # any land: an opponent's too
    vesuva = put(s, "Vesuva", "hand")
    act(s, "p1", type="play_land", card_id=vesuva.id)
    d = rules(s).decision
    assert d.prompt.endswith("to copy") and {urborg.id, island.id, "none"} <= {o.id for o in d.options}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[urborg.id])
    drive(s)
    v = s.state.cards[vesuva.id]
    assert v.zone == "p1:battlefield" and v.tapped  # tapped because it entered as a copy
    assert ch(s, v).name == "Urborg, Tomb of Yawgmoth" and "Legendary" in ch(s, v).supertypes
    roundtrip(s)


def test_vesuva_copying_nothing_enters_untapped(cards):
    s = build(cards, [(1, "Vesuva"), (1, "Forest")])
    put(s, "Forest", "battlefield")
    vesuva = put(s, "Vesuva", "hand")
    act(s, "p1", type="play_land", card_id=vesuva.id)
    act(s, "p1", type="choose", decision_id=rules(s).decision.id, option_ids=["none"])
    v = s.state.cards[vesuva.id]
    assert v.zone == "p1:battlefield" and not v.tapped and ch(s, v).name == "Vesuva"
    roundtrip(s)


def test_cursed_mirror_is_a_hasty_copy_until_end_of_turn(cards):
    s = build(cards, [(1, "Cursed Mirror"), (1, "Grizzly Bears")])
    bears = put(s, "Grizzly Bears", "battlefield")
    mirror = cast(s, "Cursed Mirror", bears.id, R=1, C=2)
    got = ch(s, mirror)
    assert mirror.zone == "p1:battlefield" and got.name == "Grizzly Bears" and got.pt == (2, 2) and "haste" in got.keywords
    assert "{T}: Add {R}." not in [a.text for a in got.abilities]
    roundtrip(s)
    for _ in range(12):  # 514.2: "until end of turn" ends in the cleanup step
        if s.state.turn.active_player != "p1":
            break
        d = rules(s).decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        else:
            act(s, rules(s).priority, type="pass_priority")
    assert s.state.turn.active_player == "p2"
    got = ch(s, s.state.cards[mirror.id])
    assert got.name == "Cursed Mirror" and not got.is_creature and "{T}: Add {R}." in [a.text for a in got.abilities]
    roundtrip(s)


def test_mirrormade_copies_an_artifact(cards):
    s = build(cards, [(1, "Mirrormade"), (1, "Sol Ring")])
    ring = put(s, "Sol Ring", "battlefield")
    mirror = cast(s, "Mirrormade", ring.id, U=2, C=1)
    got = ch(s, mirror)
    assert got.name == "Sol Ring" and "Artifact" in got.types and "Enchantment" not in got.types
    roundtrip(s)


def test_masterwork_copies_an_equipment(cards):
    s = build(cards, [(1, "Masterwork of Ingenuity"), (1, "Bonesplitter")])
    splitter = put(s, "Bonesplitter", "battlefield")
    work = cast(s, "Masterwork of Ingenuity", splitter.id, C=1)
    assert ch(s, work).name == "Bonesplitter" and work.attached_to is None
    roundtrip(s)


def test_synth_infiltrator_is_a_synth_artifact_creature_copy(cards):
    s = build(cards, [(1, "Synth Infiltrator"), (1, "Grizzly Bears")])
    bears = put(s, "Grizzly Bears", "battlefield")
    synth = cast(s, "Synth Infiltrator", bears.id, U=2, C=3)
    got = ch(s, synth)
    assert got.name == "Grizzly Bears" and {"Artifact", "Creature"} <= got.types and {"Bear", "Synth"} <= got.subtypes
    roundtrip(s)


def test_clever_impersonator_reanimated_as_an_aura_chooses_what_it_enchants(cards):
    """303.4f: an Aura put onto the battlefield without being cast chooses what it enchants (no targeting)."""
    s = build(cards, [(1, "Clever Impersonator"), (1, "Reanimate"), (1, "Pacifism")], [(1, "Grizzly Bears"), (9, "Island")])
    ox = put(s, "Grizzly Bears", "battlefield", pid="p2")
    pacifism = put(s, "Pacifism", "battlefield")
    act(s, "p1", type="attach", card_ids=[pacifism.id], to=ox.id)
    imp = put(s, "Clever Impersonator", "graveyard")
    reanimate = put(s, "Reanimate", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"B": 1})
    act(s, "p1", type="cast_spell", card_id=reanimate.id, targets=[imp.id])
    drive(s, lambda d: [pacifism.id] if d.prompt.endswith("to copy") else [ox.id] if any(o.id == ox.id for o in d.options)
          else [d.options[0].id])
    got = s.state.cards[imp.id]
    assert got.zone == "p1:battlefield" and ch(s, got).name == "Pacifism" and got.attached_to == ox.id
    roundtrip(s)


def test_clever_impersonator_cast_as_an_aura_copy_is_attached_by_hand(cards):
    """Cast, it wasn't an Aura spell (no target): the engine asks for the attaching to be done by hand."""
    s = build(cards, [(1, "Clever Impersonator"), (1, "Pacifism")], [(1, "Grizzly Bears"), (9, "Island")])
    ox = put(s, "Grizzly Bears", "battlefield", pid="p2")
    pacifism = put(s, "Pacifism", "battlefield")
    act(s, "p1", type="attach", card_ids=[pacifism.id], to=ox.id)
    imp = put(s, "Clever Impersonator", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 2, "C": 2})
    act(s, "p1", type="cast_spell", card_id=imp.id)
    for _ in range(10):
        d = rules(s).decision
        if d is not None and d.prompt.endswith("to copy"):
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[pacifism.id])
        elif d is None and s.state.zones.get("stack"):
            act(s, rules(s).priority, type="pass_priority")
        else:
            break
    d = rules(s).decision
    assert d is not None and d.kind == "manual_resolution"
    assert ch(s, s.state.cards[imp.id]).name == "Pacifism"
    roundtrip(s)


# -- the Enduring cycle: "It's an enchantment." (611.2e, 603.4, 608.2h) ----------------------------------------------------
def test_enduring_wording_is_covered_only_after_a_return():
    text = ("When Enduring Curiosity dies, if it was a creature, return it to the battlefield under its owner's control. "
            "It's an enchantment. (It's not a creature.)")
    assert ok(text, "Enduring Curiosity", "Enchantment Creature — Cat Glimmer")
    assert not ok("When this creature dies, draw a card. It's an enchantment.")


def test_enduring_curiosity_returns_as_an_enchantment_then_stays_dead(cards):
    s = build(cards, [(1, "Enduring Curiosity"), (1, "Soul Warden"), (1, "Disenchant")])
    put(s, "Soul Warden", "battlefield")
    curiosity = put(s, "Enduring Curiosity", "battlefield")
    life = s.state.players["p1"].life
    act(s, "p1", type="set_damage", card_ids=[curiosity.id], delta=3)  # lethal: it dies (704.5g)
    act(s, "p1", type="pass_priority")
    drive(s)
    c = s.state.cards[curiosity.id]
    got = ch(s, c)
    assert c.zone == "p1:battlefield" and got.types == frozenset({"Enchantment"}) and not got.is_creature
    assert "Glimmer" not in got.subtypes and "Cat" not in got.subtypes  # (205.1a: no creature types without the type)
    # 611.2e: it was never a creature on the battlefield — Soul Warden's "another creature enters" didn't trigger
    assert s.state.players["p1"].life == life
    entry = [e for e in rules(s).turn_log.entered if e.card == c.id][-1]
    assert entry.types == ["Enchantment"]
    roundtrip(s)
    # destroyed as an enchantment, it wasn't a creature as it last existed: it stays in the graveyard (603.4)
    disenchant = put(s, "Disenchant", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1, "C": 1})
    act(s, "p1", type="cast_spell", card_id=disenchant.id, targets=[c.id])
    drive(s)
    assert s.state.cards[c.id].zone == "p1:graveyard"
    roundtrip(s)
