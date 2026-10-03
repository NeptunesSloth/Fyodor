"""Conditional static abilities (wave 4B): "as long as …" / "if you control …" (CR 604.2, 611.3a-b, 613.1d, 613.7,
113.6b, 700.5, 700.9, 701.37b, 702.112b, 903.7): app/rules/static_conditions.py, app/rules/statics.py and the layer
system (app/rules/layers.py).

Every scenario uses real Commander-legal cards with their current Oracle text (data/cards.sqlite), checks that
replaying the recorded history reproduces the table, and that a save/load round trip keeps it.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.state import GameState
from app.rules import coverage, statics
from app.rules.characteristics import Characteristics, parse_type_line
from app.rules.oracle import parse_abilities
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches
from tests.test_rules_permissions import build, hints, put

EXTRA = [
    card("Anger", set_code="tst", number="4B01", mana_cost="{3}{R}", cmc=4.0, type_line="Creature — Incarnation",
         oracle_text="Haste\nAs long as this card is in your graveyard and you control a Mountain, creatures you control have haste.",
         power="2", toughness="2", colors=["R"], color_identity=["R"], keywords=["Haste"]),
    card("Riftstone Portal", set_code="tst", number="4B02", type_line="Land",
         oracle_text='{T}: Add {C}.\nAs long as this card is in your graveyard, lands you control have "{T}: Add {G} or {W}."',
         color_identity=["G", "W"]),
    card("Purphoros, God of the Forge", set_code="tst", number="4B03", mana_cost="{3}{R}", cmc=4.0,
         type_line="Legendary Enchantment Creature — God",
         oracle_text="Indestructible\nAs long as your devotion to red is less than five, Purphoros isn't a creature.\nWhenever another "
                     "creature you control enters, Purphoros deals 2 damage to each opponent.\n{2}{R}: Creatures you control get +1/+0 "
                     "until end of turn.",
         power="6", toughness="5", colors=["R"], color_identity=["R"], keywords=["Indestructible"]),
    card("Iroas, God of Victory", set_code="tst", number="4B04", mana_cost="{2}{R}{W}", cmc=4.0,
         type_line="Legendary Enchantment Creature — God",
         oracle_text="Indestructible\nAs long as your devotion to red and white is less than seven, Iroas isn't a creature.\nCreatures "
                     "you control have menace.\nPrevent all damage that would be dealt to attacking creatures you control.",
         power="7", toughness="4", colors=["R", "W"], color_identity=["R", "W"], keywords=["Indestructible"]),
    card("Champion's Helm", set_code="tst", number="4B05", mana_cost="{3}", cmc=3.0, type_line="Artifact — Equipment",
         oracle_text="Equipped creature gets +2/+2.\nAs long as equipped creature is legendary, it has hexproof. (It can't be the target of "
                     "spells or abilities your opponents control.)\nEquip {1}", keywords=["Equip"]),
    card("Steel of the Godhead", set_code="tst", number="4B06", mana_cost="{2}{W/U}", cmc=3.0, type_line="Enchantment — Aura",
         oracle_text="Enchant creature\nAs long as enchanted creature is white, it gets +1/+1 and has lifelink. (Damage dealt by the "
                     "creature also causes its controller to gain that much life.)\nAs long as enchanted creature is blue, it gets +1/+1 "
                     "and can't be blocked.",
         colors=["U", "W"], color_identity=["U", "W"], keywords=["Enchant"]),
    card("Rune of Sustenance", set_code="tst", number="4B07", mana_cost="{1}{W}", cmc=2.0, type_line="Enchantment — Aura Rune",
         oracle_text='Enchant permanent\nWhen this Aura enters, draw a card.\nAs long as enchanted permanent is a creature, it has '
                     'lifelink.\nAs long as enchanted permanent is an Equipment, it has "Equipped creature has lifelink."',
         colors=["W"], color_identity=["W"], keywords=["Enchant"]),
    card("Beastmaster Ascension", set_code="tst", number="4B08", mana_cost="{2}{G}", cmc=3.0, type_line="Enchantment",
         oracle_text="Whenever a creature you control attacks, you may put a quest counter on this enchantment.\nAs long as this "
                     "enchantment has seven or more quest counters on it, creatures you control get +5/+5.",
         colors=["G"], color_identity=["G"]),
    card("Bloodghast", set_code="tst", number="4B09", mana_cost="{B}{B}", cmc=2.0, type_line="Creature — Vampire Spirit",
         oracle_text="This creature can't block.\nThis creature has haste as long as an opponent has 10 or less life.\nLandfall — "
                     "Whenever a land you control enters, you may return this card from your graveyard to the battlefield.",
         power="2", toughness="1", colors=["B"], color_identity=["B"], keywords=["Landfall"]),
    card("Righteous Valkyrie", set_code="tst", number="4B10", mana_cost="{2}{W}", cmc=3.0, type_line="Creature — Angel Cleric",
         oracle_text="Flying\nWhenever another Angel or Cleric you control enters, you gain life equal to that creature's toughness.\nAs "
                     "long as you have at least 7 life more than your starting life total, creatures you control get +2/+2.",
         power="2", toughness="4", colors=["W"], color_identity=["W"], keywords=["Flying"]),
    card("Bhaal, Lord of Murder", set_code="tst", number="4B11", mana_cost="{2}{B}{R}{G}", cmc=5.0, type_line="Legendary Creature — God",
         oracle_text="As long as your life total is less than or equal to half your starting life total, Bhaal has indestructible.\n"
                     "Whenever another nontoken creature you control dies, put a +1/+1 counter on target creature and goad it.",
         power="4", toughness="4", colors=["B", "G", "R"], color_identity=["B", "G", "R"], keywords=["Goad"]),
    card("Jetmir, Nexus of Revels", set_code="tst", number="4B12", mana_cost="{1}{R}{G}{W}", cmc=4.0,
         type_line="Legendary Creature — Cat Demon",
         oracle_text="Creatures you control get +1/+0 and have vigilance as long as you control three or more creatures.\nCreatures you "
                     "control also get +1/+0 and have trample as long as you control six or more creatures.\nCreatures you control also "
                     "get +1/+0 and have double strike as long as you control nine or more creatures.",
         power="5", toughness="4", colors=["G", "R", "W"], color_identity=["G", "R", "W"]),
    card("Voice of the Blessed", set_code="tst", number="4B13", mana_cost="{W}{W}", cmc=2.0, type_line="Creature — Spirit Cleric",
         oracle_text="Whenever you gain life, put a +1/+1 counter on this creature.\nAs long as this creature has four or more +1/+1 "
                     "counters on it, it has flying and vigilance.\nAs long as this creature has ten or more +1/+1 counters on it, it has "
                     "indestructible.",
         power="2", toughness="2", colors=["W"], color_identity=["W"]),
    card("Skyknight Squire", set_code="tst", number="4B14", mana_cost="{1}{W}", cmc=2.0, type_line="Creature — Cat Scout",
         oracle_text="Whenever another creature you control enters, put a +1/+1 counter on this creature.\nAs long as this creature has "
                     "three or more +1/+1 counters on it, it has flying and is a Knight in addition to its other types.",
         power="1", toughness="1", colors=["W"], color_identity=["W"]),
    card("Gravecrawler", set_code="tst", number="4B15", mana_cost="{B}", cmc=1.0, type_line="Creature — Zombie",
         oracle_text="This creature can't block.\nYou may cast this card from your graveyard as long as you control a Zombie.",
         power="2", toughness="1", colors=["B"], color_identity=["B"]),
    card("Den of the Bugbear", set_code="tst", number="4B16", type_line="Land",
         oracle_text='If you control two or more other lands, this land enters tapped.\n{T}: Add {R}.\n{3}{R}: Until end of turn, this '
                     'land becomes a 3/2 red Goblin creature with "Whenever this creature attacks, create a 1/1 red Goblin creature token '
                     'that\'s tapped and attacking." It\'s still a land.',
         color_identity=["R"]),
    card("Fleecemane Lion", set_code="tst", number="4B17", mana_cost="{G}{W}", cmc=2.0, type_line="Creature — Cat",
         oracle_text="{3}{G}{W}: Monstrosity 1. (If this creature isn't monstrous, put a +1/+1 counter on it and it becomes monstrous.)\n"
                     "As long as this creature is monstrous, it has hexproof and indestructible.",
         power="3", toughness="3", colors=["G", "W"], color_identity=["G", "W"], keywords=["Monstrosity"]),
    card("Caduceus, Staff of Hermes", set_code="tst", number="4B18", mana_cost="{2}{W}", cmc=3.0,
         type_line="Legendary Artifact — Equipment",
         oracle_text='Equipped creature has lifelink.\nAs long as you have 30 or more life, equipped creature gets +5/+5 and has '
                     'indestructible and "Prevent all damage that would be dealt to this creature."\nEquip {W}{W}',
         colors=["W"], color_identity=["W"], keywords=["Equip"]),
    card("Thieves' Guild Enforcer", set_code="tst", number="4B19", mana_cost="{B}", cmc=1.0, type_line="Creature — Human Rogue",
         oracle_text="Flash\nWhenever this creature or another Rogue you control enters, each opponent mills two cards.\nAs long as an "
                     "opponent has eight or more cards in their graveyard, this creature gets +2/+1 and has deathtouch.",
         power="1", toughness="1", colors=["B"], color_identity=["B"], keywords=["Flash", "Mill"]),
    card("Orochi Merge-Keeper", set_code="tst", number="4B20", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Snake Druid",
         oracle_text='{T}: Add {G}.\nAs long as this creature is modified, it has "{T}: Add {G}{G}." (Equipment, Auras you control, and '
                     'counters are modifications.)',
         power="1", toughness="1", colors=["G"], color_identity=["G"]),
    card("The World Tree", set_code="tst", number="4B21", type_line="Land",
         oracle_text='This land enters tapped.\n{T}: Add {G}.\nAs long as you control six or more lands, lands you control have "{T}: '
                     'Add one mana of any color."\n{W}{W}{U}{U}{B}{B}{R}{R}{G}{G}, {T}, Sacrifice this land: Search your library for any '
                     'number of God cards, put them onto the battlefield, then shuffle.',
         color_identity=["B", "G", "R", "U", "W"]),
    card("Silver-Inlaid Dagger", set_code="tst", number="4B22", mana_cost="{1}", cmc=1.0, type_line="Artifact — Equipment",
         oracle_text="Equipped creature gets +2/+0.\nAs long as equipped creature is a Human, it gets an additional +1/+0.\nEquip {2}",
         keywords=["Equip"]),
    card("Gate Hound", set_code="tst", number="4B23", mana_cost="{2}{W}", cmc=3.0, type_line="Creature — Dog",
         oracle_text="Creatures you control have vigilance as long as this creature is enchanted.",
         power="1", toughness="1", colors=["W"], color_identity=["W"]),
    card("Demon Wall", set_code="tst", number="4B25", mana_cost="{1}{B}", cmc=2.0, type_line="Artifact Creature — Demon Wall",
         oracle_text="Defender\nMenace (This creature can't be blocked except by two or more creatures.)\nAs long as this creature has a "
                     "counter on it, it can attack as though it didn't have defender.\n{5}{B}: Put two +1/+1 counters on this creature.",
         power="3", toughness="3", colors=["B"], color_identity=["B"], keywords=["Menace", "Defender"]),
    card("Path of Bravery", set_code="tst", number="4B24", mana_cost="{2}{W}", cmc=3.0, type_line="Enchantment",
         oracle_text="As long as your life total is greater than or equal to your starting life total, creatures you control get +1/+1.\n"
                     "Whenever one or more creatures you control attack, you gain life equal to the number of attacking creatures.",
         colors=["W"], color_identity=["W"]),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def tok(s, name, type_line="Token Creature — Test", pt="2/2", pid="p1", colors=(), text=""):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": type_line, "power": p, "toughness": t,
                                                         "text": text, "colors": list(colors)})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def roundtrip(s):
    """Replay rebuilds the same table, and a save/load round trip keeps it."""
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped


def ok(text, name="Card", type_line="Creature — Test"):
    """Is the line automated (coverage) on a card with that name and type?"""
    sup, types, sub = parse_type_line(type_line)
    abilities = tuple(parse_abilities(text))
    feats = coverage.features_of(Characteristics(name=name, supertypes=sup, types=types, subtypes=sub, oracle_text=text,
                                                 abilities=abilities))
    return all(f.supported for f in feats if f.id.startswith("text:"))


# -- the wording ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("text", "expected"), [
    ("As long as this card is in your graveyard and you control a Mountain, creatures you control have haste.",  # Anger
     {"keywords": ["haste"], "conditions": [{"static": "all", "conds": [
         {"static": "zone", "zone": "graveyard"},
         {"value": {"count": 'sel:{"controller":"you","subtypes":["Mountain"]}'}, "op": ">=", "n": 1}]}]}),
    ("As long as ~ has seven or more quest counters on it, creatures you control get +5/+5.",  # Beastmaster Ascension
     {"p": 5, "t": 5, "conditions": [{"static": "self_counter", "counter": "quest", "op": ">=", "n": 7}]}),
    ("As long as there are five or more growth counters on ~, creatures you control get +3/+3.",  # Comforting Counsel
     {"p": 3, "t": 3, "conditions": [{"static": "self_counter", "counter": "growth", "op": ">=", "n": 5}]}),
    ("As long as your devotion to red is less than five, ~ isn't a creature.",  # Purphoros
     {"who": "self", "remove_types": ["Creature"], "conditions": [{"value": {"devotion": ["R"]}, "op": "<=", "n": 4}]}),
    ("As long as equipped creature is legendary, it has hexproof.",  # Champion's Helm
     {"who": "attached", "keywords": ["hexproof"], "conditions": [
         {"static": "attached_is", "sel": 'sel:{"supertypes":["Legendary"]}', "noun": "creature", "who": "equipped"}]}),
    ("~ has haste as long as an opponent has 10 or less life.",  # Bloodghast
     {"keywords": ["haste"], "conditions": [{"static": "opp_life", "op": "<=", "n": 10}]}),
    ("As long as you have at least 7 life more than your starting life total, creatures you control get +2/+2.",  # Righteous Valkyrie
     {"p": 2, "t": 2, "conditions": [{"static": "life_vs_start", "op": ">=", "plus": 7, "half": False}]}),
    ("Creatures you control also get +1/+0 and have trample as long as you control six or more creatures.",  # Jetmir
     {"p": 1, "keywords": ["trample"]}),
    ("As long as ~ has three or more +1/+1 counters on it, it has flying and is a Knight in addition to its other types.",
     {"keywords": ["flying"], "add_subtypes": ["Knight"]}),  # Skyknight Squire
    ("As long as ~ is monstrous, it has hexproof and indestructible.",  # Fleecemane Lion
     {"keywords": ["hexproof", "indestructible"], "conditions": [{"static": "designation", "is": "monstrous"}]}),
    ("~ has flying as long as it's modified.", {"conditions": [{"static": "self", "test": "modified"}]}),  # Obstinate Gargoyle
    ("As long as equipped creature is a Human, it gets an additional +1/+0.", {"who": "attached", "p": 1}),  # Silver-Inlaid Dagger
    ("~ gets +1/+0 as long as any player controls a black permanent.",  # Knight of Grace
     {"p": 1, "conditions": [{"value": {"count": 'sel:{"colors":["B"]}'}, "op": ">=", "n": 1}]}),
    ("~ gets +3/+3 as long as an opponent has no cards in hand.",  # Guul Draz Specter
     {"p": 3, "conditions": [{"static": "opp_hand", "op": "==", "n": 0}]}),
    ("~ has infect as long as an opponent is poisoned.",  # Viridian Betrayers
     {"keywords": ["infect"], "conditions": [{"value": {"player_counters": "poison"}, "op": ">=", "n": 1, "per_opponent": True}]}),
    ("As long as you have 30 or more life and an opponent has 10 or less life, ~ gets +6/+6 and has flying.",  # Blood Baron
     {"p": 6, "conditions": [{"static": "all", "conds": [{"value": {"life": "you"}, "op": ">=", "n": 30},
                                                         {"static": "opp_life", "op": "<=", "n": 10}]}]}),
])
def test_wordings(text, expected):
    d = statics.parse(text)
    assert d is not None
    assert {k: d.get(k) for k in expected} == expected


@pytest.mark.parametrize("text", [
    "As long as ~ has a slumber counter on it, it's a land.",  # Arixmethes: a type-setting effect (not read)
    "As long as you control five or more enchantments, each other non-Aura enchantment you control is a creature in addition to "
    "its other types and has base power and base toughness each equal to its mana value.",  # Starfield of Nyx (613.8)
    "As long as ~ has eight or more +1/+1 counters on it, it's a 0/0 creature in addition to its other types and it has annihilator 2.",
    "As long as it's monstrous, creatures you control get +1/+1.",  # "it": not certainly the source
    "As long as you control six or more lands, ~ isn't a creature.",  # a layer-4 condition that reads types (613.8)
    "As long as this card is in your graveyard, ~ gets +1/+1.",  # a card in a graveyard is no permanent
    "As long as your life total is greater than your starting life total, ~ gets +1/+1 and has menace. ~ gets an additional "
    "+5/+5 as long as your life total is at least 10 greater than your starting life total.",  # Elenda: two sentences
    "As long as you control six or more lands, ~ and land creatures you control get +2/+2.",  # Sylvan Advocate
])
def test_refused_wordings(text):
    assert statics.parse(text) is None


def test_coverage_of_the_lines():
    assert ok("As long as your devotion to red is less than five, Purphoros isn't a creature.", "Purphoros, God of the Forge",
              "Legendary Enchantment Creature — God")
    assert ok("You may cast this card from your graveyard as long as you control a Zombie.", "Gravecrawler", "Creature — Zombie")
    assert ok("If you control two or more other lands, this land enters tapped.", "Den of the Bugbear", "Land")
    assert not ok("You may cast this card from your graveyard as long as you attacked this turn.")
    assert not ok("As long as Arixmethes has a slumber counter on it, it's a land.", "Arixmethes, Slumbering Isle")


# -- a static that functions from the graveyard (113.6b) --------------------------------------------------------
def test_anger_from_the_graveyard(cards):
    s = build(cards, [(1, "Anger"), (1, "Mountain"), (5, "Forest")], [(1, "Mountain"), (9, "Island")])
    bear = tok(s, "Bear")
    theirs = tok(s, "Theirs", pid="p2")
    anger = put(s, "Anger", "battlefield")
    put(s, "Mountain", "battlefield")
    assert "haste" not in ch(s, bear).keywords  # 113.6: on the battlefield the ability does nothing
    put(s, "Anger", "graveyard")
    assert "haste" in ch(s, bear).keywords and "haste" not in ch(s, theirs).keywords
    put(s, "Mountain", "hand")
    put(s, "Mountain", "battlefield", pid="p2")  # an opponent's Mountain isn't yours
    assert "haste" not in ch(s, bear).keywords
    put(s, "Mountain", "battlefield")
    assert "haste" in ch(s, bear).keywords
    late = tok(s, "Late")  # 611.3a: a creature that arrives later has it too
    assert "haste" in ch(s, late).keywords
    act(s, "p1", type="move", card_ids=[anger.id], to={"zone": "exile"})
    assert "haste" not in ch(s, bear).keywords
    roundtrip(s)


def test_anger_set_to_manual_in_the_graveyard_stops_granting(cards):
    """-- review (Codex) -- the static cache must notice a graveyard card's automation mode changing."""
    s = build(cards, [(1, "Anger"), (1, "Mountain"), (5, "Forest")], [(9, "Island")])
    bear = tok(s, "Bear")
    anger = put(s, "Anger", "graveyard")
    put(s, "Mountain", "battlefield")
    assert "haste" in ch(s, bear).keywords
    act(s, "p1", type="set_card_automation", card_id=anger.id, mode="manual")
    assert "haste" not in ch(s, bear).keywords
    act(s, "p1", type="set_card_automation", card_id=anger.id, mode="auto")
    assert "haste" in ch(s, bear).keywords
    roundtrip(s)


def test_riftstone_portal_grants_a_mana_ability_from_the_graveyard(cards):
    s = build(cards, [(1, "Riftstone Portal"), (5, "Forest")])
    forest = put(s, "Forest", "battlefield")
    assert not [a for a in ch(s, forest).abilities if a.index >= 100]
    put(s, "Riftstone Portal", "graveyard")
    assert [a.text for a in ch(s, forest).abilities if a.index >= 100] == ["{T}: Add {G} or {W}."]
    roundtrip(s)


# -- layer 4: devotion gods (700.5, 613.1d, 205.3d) -----------------------------------------------------------
def test_purphoros_is_a_creature_only_with_devotion_five(cards):
    s = build(cards, [(1, "Purphoros, God of the Forge"), (1, "Monastery Swiftspear"), (1, "Young Pyromancer"),
                      (1, "Stormblood Berserker"), (1, "Bloodbraid Elf"), (1, "Jetmir, Nexus of Revels"), (4, "Forest")])
    purphoros = put(s, "Purphoros, God of the Forge", "hand")
    assert ch(s, purphoros).is_creature  # 611.3b: only on the battlefield; a creature card elsewhere
    put(s, "Purphoros, God of the Forge", "battlefield")
    now = ch(s, purphoros)
    assert not now.is_creature and now.types == frozenset({"Enchantment"}) and "God" not in now.subtypes
    assert "Legendary" in now.supertypes and "indestructible" in now.keywords
    for name in ("Monastery Swiftspear", "Young Pyromancer", "Stormblood Berserker"):
        put(s, name, "battlefield")
    assert not ch(s, purphoros).is_creature  # devotion 4
    jetmir = put(s, "Jetmir, Nexus of Revels", "battlefield")  # {1}{R}{G}{W}: devotion to red 5
    assert ch(s, purphoros).is_creature and "God" in ch(s, purphoros).subtypes
    assert ch(s, purphoros).pt == (7, 5)  # Jetmir: three or more creatures, +1/+0
    put(s, "Jetmir, Nexus of Revels", "graveyard")
    put(s, "Monastery Swiftspear", "graveyard")
    put(s, "Young Pyromancer", "graveyard")
    assert not ch(s, purphoros).is_creature  # devotion 3
    put(s, "Jetmir, Nexus of Revels", "battlefield")  # devotion 4: Jetmir and the Berserker are the only creatures
    assert not ch(s, purphoros).is_creature and ch(s, jetmir).pt == (5, 4)  # (the God isn't counted: 2 creatures)
    roundtrip(s)


def test_iroas_counts_both_colors_and_a_hybrid_symbol_once(cards):
    s = build(cards, [(1, "Iroas, God of Victory"), (1, "Steel of the Godhead"), (1, "Bloodbraid Elf"), (1, "Young Pyromancer"),
                      (5, "Forest")])
    iroas = put(s, "Iroas, God of Victory", "battlefield")  # {R}{W}: 2
    for name in ("Steel of the Godhead", "Bloodbraid Elf", "Young Pyromancer"):  # {W/U}: 1, {R}: 1, {R}: 1 → 5
        put(s, name, "battlefield")
    assert not ch(s, iroas).is_creature
    tok(s, "Copy", "Token Creature — Test")  # (a token has no mana cost)
    assert not ch(s, iroas).is_creature
    roundtrip(s)


# -- the attached object (301.5a, 303.4b) ---------------------------------------------------------------------
def test_champions_helm_on_a_legendary_creature(cards):
    s = build(cards, [(1, "Champion's Helm"), (5, "Forest")])
    helm = put(s, "Champion's Helm", "battlefield")
    plain = tok(s, "Plain")
    legend = tok(s, "Legend", "Legendary Token Creature — Test")
    act(s, "p1", type="attach", card_ids=[helm.id], to=plain.id)
    assert ch(s, plain).pt == (4, 4) and "hexproof" not in ch(s, plain).keywords
    act(s, "p1", type="attach", card_ids=[helm.id], to=legend.id)
    assert ch(s, legend).pt == (4, 4) and "hexproof" in ch(s, legend).keywords
    assert "hexproof" not in ch(s, plain).keywords and ch(s, plain).pt == (2, 2)
    roundtrip(s)


def test_steel_of_the_godhead_reads_the_enchanted_creatures_colors(cards):
    s = build(cards, [(1, "Steel of the Godhead"), (5, "Forest")])
    steel = put(s, "Steel of the Godhead", "battlefield")
    white = tok(s, "White", colors=["W"])
    both = tok(s, "Both", colors=["W", "U"])
    green = tok(s, "Green", colors=["G"])
    act(s, "p1", type="attach", card_ids=[steel.id], to=white.id)
    assert ch(s, white).pt == (3, 3) and "lifelink" in ch(s, white).keywords and "cant_be_blocked" not in ch(s, white).imposed
    act(s, "p1", type="attach", card_ids=[steel.id], to=both.id)
    now = ch(s, both)
    assert now.pt == (4, 4) and "lifelink" in now.keywords and "cant_be_blocked" in now.imposed
    act(s, "p1", type="attach", card_ids=[steel.id], to=green.id)
    assert ch(s, green).pt == (2, 2) and not ch(s, green).imposed
    roundtrip(s)


def test_rune_on_a_creature_and_on_an_equipment(cards):
    s = build(cards, [(1, "Rune of Sustenance"), (1, "Bonesplitter"), (5, "Forest")])
    rune = put(s, "Rune of Sustenance", "battlefield")
    splitter = put(s, "Bonesplitter", "battlefield")
    bear = tok(s, "Bear")
    act(s, "p1", type="attach", card_ids=[rune.id], to=bear.id)
    assert "lifelink" in ch(s, bear).keywords
    act(s, "p1", type="attach", card_ids=[rune.id], to=splitter.id)
    assert "lifelink" not in ch(s, bear).keywords
    act(s, "p1", type="attach", card_ids=[splitter.id], to=bear.id)
    assert "lifelink" in ch(s, bear).keywords and ch(s, bear).pt == (4, 2)  # "Equipped creature has lifelink." (the Rune's grant)
    assert "lifelink" not in ch(s, splitter).keywords
    roundtrip(s)


def test_silver_inlaid_dagger_on_a_human(cards):
    s = build(cards, [(1, "Silver-Inlaid Dagger"), (5, "Forest")])
    dagger = put(s, "Silver-Inlaid Dagger", "battlefield")
    human = tok(s, "Hero", "Token Creature — Human Soldier")
    elf = tok(s, "Elf", "Token Creature — Elf")
    act(s, "p1", type="attach", card_ids=[dagger.id], to=elf.id)
    assert ch(s, elf).pt == (4, 2)
    act(s, "p1", type="attach", card_ids=[dagger.id], to=human.id)
    assert ch(s, human).pt == (5, 2) and ch(s, elf).pt == (2, 2)
    roundtrip(s)


def test_caduceus_while_you_have_thirty_life(cards):
    s = build(cards, [(1, "Caduceus, Staff of Hermes"), (1, "Lightning Bolt"), (5, "Forest")], [(1, "Lightning Bolt"), (9, "Island")])
    staff = put(s, "Caduceus, Staff of Hermes", "battlefield")
    bear = tok(s, "Bear")
    act(s, "p1", type="attach", card_ids=[staff.id], to=bear.id)
    now = ch(s, bear)
    assert now.pt == (7, 7) and {"lifelink", "indestructible"} <= now.keywords
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[bear.id])
    pass_until_stack_empty(s)
    assert s.state.cards[bear.id].damage == 0  # "Prevent all damage that would be dealt to this creature." (granted)
    act(s, "p1", type="set_life", player="p1", value=29)
    now = ch(s, bear)
    assert now.pt == (2, 2) and "lifelink" in now.keywords and "indestructible" not in now.keywords
    roundtrip(s)


# -- counters, designations, modified (700.9, 701.37b) --------------------------------------------------------
def test_beastmaster_ascension_with_seven_counters(cards):
    s = build(cards, [(1, "Beastmaster Ascension"), (5, "Forest")])
    ascension = put(s, "Beastmaster Ascension", "battlefield")
    bear = tok(s, "Bear")
    theirs = tok(s, "Theirs", pid="p2")
    act(s, "p1", type="counter", card_ids=[ascension.id], kind="quest", delta=6)
    assert ch(s, bear).pt == (2, 2)
    act(s, "p1", type="counter", card_ids=[ascension.id], kind="quest", delta=1)
    assert ch(s, bear).pt == (7, 7) and ch(s, theirs).pt == (2, 2)
    roundtrip(s)


def test_voice_of_the_blessed_and_skyknight_squire(cards):
    s = build(cards, [(1, "Voice of the Blessed"), (1, "Skyknight Squire"), (5, "Forest")])
    voice = put(s, "Voice of the Blessed", "battlefield")
    squire = put(s, "Skyknight Squire", "battlefield")
    lord = tok(s, "Lord", text="Other Knights you control get +1/+1.")
    act(s, "p1", type="counter", card_ids=[voice.id, squire.id], kind="+1/+1", delta=3)
    assert "flying" not in ch(s, voice).keywords
    assert "flying" in ch(s, squire).keywords and "Knight" in ch(s, squire).subtypes
    assert ch(s, squire).pt == (5, 5)  # 613.8-style: the lord's subject sees the Knight type (layer 4 before 7c)
    act(s, "p1", type="counter", card_ids=[voice.id], kind="+1/+1", delta=1)
    assert {"flying", "vigilance"} <= ch(s, voice).keywords and "indestructible" not in ch(s, voice).keywords
    act(s, "p1", type="counter", card_ids=[voice.id], kind="+1/+1", delta=6)
    assert "indestructible" in ch(s, voice).keywords
    act(s, "p1", type="counter", card_ids=[squire.id], kind="+1/+1", delta=-1)
    assert "Knight" not in ch(s, squire).subtypes and ch(s, squire).pt == (3, 3)
    assert ch(s, lord).pt == (2, 2)
    roundtrip(s)


def test_fleecemane_lion_once_monstrous(cards):
    s = build(cards, [(1, "Fleecemane Lion"), (5, "Forest")])
    lion = put(s, "Fleecemane Lion", "battlefield")
    act(s, "p1", type="counter", card_ids=[lion.id], kind="+1/+1", delta=1)
    assert not {"hexproof", "indestructible"} & ch(s, lion).keywords  # a counter alone doesn't make it monstrous
    mana(s, G=2, W=1, C=2)
    act(s, "p1", type="activate_ability", card_id=lion.id, ability=0)
    pass_until_stack_empty(s)
    assert {"hexproof", "indestructible"} <= ch(s, lion).keywords
    put(s, "Fleecemane Lion", "hand")
    put(s, "Fleecemane Lion", "battlefield")  # 400.7: a new object, not monstrous
    assert not {"hexproof", "indestructible"} & ch(s, lion).keywords
    roundtrip(s)


def test_orochi_merge_keeper_and_gate_hound(cards):
    s = build(cards, [(1, "Orochi Merge-Keeper"), (1, "Gate Hound"), (1, "Holy Strength"), (5, "Forest")],
              [(1, "Holy Strength"), (9, "Island")])
    keeper = put(s, "Orochi Merge-Keeper", "battlefield")
    hound = put(s, "Gate Hound", "battlefield")
    assert not [a for a in ch(s, keeper).abilities if a.index >= 100]
    act(s, "p1", type="counter", card_ids=[keeper.id], kind="+1/+1", delta=1)
    assert [a.text for a in ch(s, keeper).abilities if a.index >= 100] == ["{T}: Add {G}{G}."]
    theirs = put(s, "Holy Strength", "battlefield", pid="p2")
    act(s, "p2", type="attach", card_ids=[theirs.id], to=hound.id)  # 700.9 doesn't matter here: "enchanted" is any Aura
    assert "vigilance" in ch(s, keeper).keywords
    act(s, "p2", type="attach", card_ids=[theirs.id], to=keeper.id)  # an opponent's Aura: not a modification (700.9)
    act(s, "p1", type="counter", card_ids=[keeper.id], kind="+1/+1", delta=-1)
    assert not [a for a in ch(s, keeper).abilities if a.index >= 100] and "vigilance" not in ch(s, keeper).keywords
    roundtrip(s)


# -- life totals and opponents (119.1, 903.7) ------------------------------------------------------------------
def test_life_against_the_starting_life_total(cards):
    s = build(cards, [(1, "Righteous Valkyrie"), (1, "Path of Bravery"), (1, "Bhaal, Lord of Murder"), (5, "Forest")])
    valkyrie = put(s, "Righteous Valkyrie", "battlefield")
    put(s, "Path of Bravery", "battlefield")
    bhaal = put(s, "Bhaal, Lord of Murder", "battlefield")
    assert s.state.settings.starting_life == 40
    assert ch(s, valkyrie).pt == (3, 5) and "indestructible" not in ch(s, bhaal).keywords  # 40: Path only
    act(s, "p1", type="set_life", player="p1", value=47)
    assert ch(s, valkyrie).pt == (5, 7)
    act(s, "p1", type="set_life", player="p1", value=46)
    assert ch(s, valkyrie).pt == (3, 5)
    act(s, "p1", type="set_life", player="p1", value=39)
    assert ch(s, valkyrie).pt == (2, 4)
    act(s, "p1", type="set_life", player="p1", value=21)
    assert "indestructible" not in ch(s, bhaal).keywords
    act(s, "p1", type="set_life", player="p1", value=20)  # half of 40
    assert "indestructible" in ch(s, bhaal).keywords
    roundtrip(s)


def test_bloodghast_and_thieves_guild_enforcer_read_one_opponent(cards):
    s = build(cards, [(1, "Bloodghast"), (1, "Thieves' Guild Enforcer"), (5, "Forest")])
    ghast = put(s, "Bloodghast", "battlefield")
    enforcer = put(s, "Thieves' Guild Enforcer", "battlefield")
    assert "haste" not in ch(s, ghast).keywords and ch(s, enforcer).pt == (1, 1)
    act(s, "p1", type="set_life", player="p2", value=10)
    assert "haste" in ch(s, ghast).keywords
    act(s, "p1", type="set_life", player="p1", value=5)  # your own life doesn't count
    act(s, "p1", type="set_life", player="p2", value=11)
    assert "haste" not in ch(s, ghast).keywords
    library = list(s.state.zones["p2:library"])[:8]
    act(s, "p2", type="move", card_ids=library[:7], to={"zone": "graveyard"})
    assert ch(s, enforcer).pt == (1, 1)
    act(s, "p2", type="move", card_ids=library[7:], to={"zone": "graveyard"})
    assert ch(s, enforcer).pt == (3, 2) and "deathtouch" in ch(s, enforcer).keywords
    roundtrip(s)


def test_blood_baron_needs_both_halves(cards):
    s = build(cards, [(5, "Forest")])
    baron = tok(s, "Blood Baron of Vizkopa", pt="4/4", text="As long as you have 30 or more life and an opponent has 10 or less "
                                                             "life, this creature gets +6/+6 and has flying.")
    assert ch(s, baron).pt == (4, 4)
    act(s, "p1", type="set_life", player="p2", value=10)
    assert ch(s, baron).pt == (10, 10) and "flying" in ch(s, baron).keywords
    act(s, "p1", type="set_life", player="p1", value=29)
    assert ch(s, baron).pt == (4, 4)
    roundtrip(s)


def test_jetmir_counts_its_creatures(cards):
    s = build(cards, [(1, "Jetmir, Nexus of Revels"), (5, "Forest")])
    jetmir = put(s, "Jetmir, Nexus of Revels", "battlefield")
    tok(s, "One")
    assert ch(s, jetmir).pt == (5, 4)
    for i in range(4):
        tok(s, f"T{i}")
    now = ch(s, jetmir)  # six creatures: +1/+0 vigilance, also +1/+0 trample
    assert now.pt == (7, 4) and {"vigilance", "trample"} <= now.keywords and "double strike" not in now.keywords
    for i in range(3):
        tok(s, f"U{i}")
    assert ch(s, jetmir).pt == (8, 4) and "double strike" in ch(s, jetmir).keywords
    roundtrip(s)


# -- other wordings: a conditional cast permission, a conditional enters-tapped ---------------------------------
def test_gravecrawler_casts_from_the_graveyard_while_you_control_a_zombie(cards):
    s = build(cards, [(1, "Gravecrawler"), (5, "Forest")])
    crawler = put(s, "Gravecrawler", "graveyard")
    mana(s, B=1)
    assert crawler.id not in hints(s)["castable"]
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=crawler.id)
    tok(s, "Zombie", "Token Creature — Zombie")
    assert crawler.id in hints(s)["castable"]
    act(s, "p1", type="cast_spell", card_id=crawler.id)
    pass_until_stack_empty(s)
    assert s.state.cards[crawler.id].zone == "p1:battlefield"
    roundtrip(s)


@pytest.mark.parametrize(("others", "tapped"), [(1, False), (2, True)])
def test_den_of_the_bugbear_enters_tapped_with_two_other_lands(cards, others, tapped):
    s = build(cards, [(1, "Den of the Bugbear"), (5, "Forest")])
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:others]
    act(s, "p1", type="move", card_ids=[f.id for f in forests], to={"player": "p1", "zone": "battlefield"})
    den = put(s, "Den of the Bugbear", "hand")
    act(s, "p1", type="play_land", card_id=den.id)
    assert s.state.cards[den.id].zone == "p1:battlefield" and s.state.cards[den.id].tapped is tapped
    roundtrip(s)


def test_demon_wall_attacks_despite_defender_with_a_counter(cards):
    """702.3b: defender stops an attack unless an effect says it can attack as though it didn't have it."""
    from app.rules.combat import attack_problem

    s = build(cards, [(1, "Demon Wall"), (5, "Forest")])
    wall = put(s, "Demon Wall", "battlefield")
    assert "defender" in (attack_problem(s.state, s.state.cards[wall.id], ch(s, wall)) or "")
    act(s, "p1", type="counter", card_ids=[wall.id], kind="+1/+1", delta=1)
    assert "attack_despite_defender" in ch(s, wall).imposed and "defender" in ch(s, wall).keywords
    problem = attack_problem(s.state, s.state.cards[wall.id], ch(s, wall))
    assert problem is not None and "defender" not in problem  # (it arrived this turn: summoning sickness instead)
    act(s, "p1", type="counter", card_ids=[wall.id], kind="+1/+1", delta=-1)
    assert "defender" in (attack_problem(s.state, s.state.cards[wall.id], ch(s, wall)) or "")
    roundtrip(s)
