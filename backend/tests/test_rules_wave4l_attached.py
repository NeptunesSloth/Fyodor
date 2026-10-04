"""Wave 4L: what Auras and Equipment do to the permanent they're attached to, researched against CR 2026-09-25.

* Keyword abilities with a parameter granted by a static (layer 6, 613.1f): protection (702.16; "from A and from B"
  is two protection abilities, 702.16g), ward (702.21a: each instance triggers on its own), toxic (702.164).
* "loses flying" / "loses all abilities" (613.1f, 613.7: abilities gained later stay), type and color setting
  (205.1a: "is a green Elk creature" leaves only the creature card type; 205.1b: "in addition to its other types";
  layer 5), base power and toughness (613.4b). A permanent that lost its abilities has none of its static abilities
  either (Lignify ruling).
* "Whenever enchanted land is tapped for mana, its controller adds an additional {G}" (106.12a, 605.1b, 605.4a): a
  triggered mana ability, added with the land's own mana (and counted by the payment solver).
* "… and you untap all lands you control" / "you create a Treasure token": the imperative with "you" spelled out.

Every scenario checks the replay; the longer ones also reload the game from its saved history.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.session import GameSession
from app.rules import coverage, protection, statics, triggers
from app.rules.combat import block_problem
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import build, ch, mana, named, to_hand, token
from tests.test_rules_conditionals import attack, settle, through_combat, until
from tests.test_rules_effects import replay_matches

# Real Oracle wording (the local card database, current).
EXTRA = [
    card('Sword of Feast and Famine', set_code="tst", number="L01", mana_cost='{3}', cmc=3.0, type_line='Artifact — Equipment', oracle_text='Equipped creature gets +2/+2 and has protection from black and from green.\nWhenever equipped creature deals combat damage to a player, that player discards a card and you untap all lands you control.\nEquip {2}', colors=[], color_identity=[], keywords=['Equip']),  # noqa: E501
    card('Spirit Mantle', set_code="tst", number="L02", mana_cost='{1}{W}', cmc=2.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nEnchanted creature gets +1/+1 and has protection from creatures.', colors=['W'], color_identity=['W'], keywords=['Enchant']),  # noqa: E501
    card('Lavaspur Boots', set_code="tst", number="L03", mana_cost='{1}', cmc=1.0, type_line='Artifact — Equipment', oracle_text='Equipped creature gets +1/+0 and has haste and ward {1}. (Whenever it becomes the target of a spell or ability an opponent controls, counter it unless that player pays {1}.)\nEquip {1}', colors=[], color_identity=[], keywords=['Equip']),  # noqa: E501
    card("Kenrith's Transformation", set_code="tst", number="L04", mana_cost='{1}{G}', cmc=2.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nWhen this Aura enters, draw a card.\nEnchanted creature loses all abilities and is a green Elk creature with base power and toughness 3/3. (It loses all other card types and creature types.)', colors=['G'], color_identity=['G'], keywords=['Enchant']),  # noqa: E501
    card('Darksteel Mutation', set_code="tst", number="L05", mana_cost='{1}{W}', cmc=2.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nEnchanted creature is an Insect artifact creature with base power and toughness 0/1 and has indestructible, and it loses all other abilities, card types, and creature types.', colors=['W'], color_identity=['W'], keywords=['Enchant']),  # noqa: E501
    card('Lignify', set_code="tst", number="L06", mana_cost='{1}{G}', cmc=2.0, type_line='Kindred Enchantment — Treefolk Aura', oracle_text='Enchant creature\nEnchanted creature is a Treefolk with base power and toughness 0/4 and loses all abilities.', colors=['G'], color_identity=['G'], keywords=['Enchant']),  # noqa: E501
    card('Colossus Hammer', set_code="tst", number="L07", mana_cost='{1}', cmc=1.0, type_line='Artifact — Equipment', oracle_text='Equipped creature gets +10/+10 and loses flying.\nEquip {8} ({8}: Attach to target creature you control. Equip only as a sorcery.)', colors=[], color_identity=[], keywords=['Equip']),  # noqa: E501
    card('Wild Growth', set_code="tst", number="L08", mana_cost='{G}', cmc=1.0, type_line='Enchantment — Aura', oracle_text='Enchant land\nWhenever enchanted land is tapped for mana, its controller adds an additional {G}.', colors=['G'], color_identity=['G'], keywords=['Enchant']),  # noqa: E501
    card('Fertile Ground', set_code="tst", number="L09", mana_cost='{1}{G}', cmc=2.0, type_line='Enchantment — Aura', oracle_text='Enchant land\nWhenever enchanted land is tapped for mana, its controller adds an additional one mana of any color.', colors=['G'], color_identity=['G'], keywords=['Enchant']),  # noqa: E501
    card('Shiny Impetus', set_code="tst", number="L10", mana_cost='{2}{R}', cmc=3.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nEnchanted creature gets +2/+2 and is goaded. (It attacks each combat if able and attacks a player other than you if able.)\nWhenever enchanted creature attacks, you create a Treasure token. (It\'s an artifact with "{T}, Sacrifice this token: Add one mana of any color.")', colors=['R'], color_identity=['R'], keywords=['Goad', 'Treasure', 'Enchant']),  # noqa: E501
    card('Sword of Body and Mind', set_code="tst", number="L11", mana_cost='{3}', cmc=3.0, type_line='Artifact — Equipment', oracle_text='Equipped creature gets +2/+2 and has protection from green and from blue.\nWhenever equipped creature deals combat damage to a player, you create a 2/2 green Wolf creature token and that player mills ten cards.\nEquip {2}', colors=[], color_identity=[], keywords=['Equip', 'Mill']),  # noqa: E501
    card('Eldrazi Temple', set_code="tst", number="L12", mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}: Add {C}.\n{T}: Add {C}{C}. Spend this mana only to cast colorless Eldrazi spells or activate abilities of colorless Eldrazi.', colors=[], color_identity=[]),  # noqa: E501
    card('Tarmogoyf', set_code="tst", number="L13", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Lhurgoyf', oracle_text="Tarmogoyf's power is equal to the number of card types among cards in all graveyards and its toughness is equal to that number plus 1.", power='*', toughness='1+*', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Prosthetic Injector', set_code="tst", number="L15", mana_cost='{1}', cmc=1.0, type_line='Artifact — Equipment', oracle_text='Equipped creature gets +0/+2 and has toxic 1. (Players dealt combat damage by equipped creature also get a poison counter.)\nEquip {1}', colors=[], color_identity=[], keywords=['Equip']),  # noqa: E501
    card('Super-Soldier Serum', set_code="tst", number="L16", mana_cost='{1}{W}', cmc=2.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nEnchanted creature gets +2/+2, has first strike and vigilance, and is a legendary Soldier in addition to its other types.\nWhenever enchanted creature attacks or blocks, attach any number of target Equipment you control to it.', colors=['W'], color_identity=['W'], keywords=['Enchant']),  # noqa: E501
    card('Curse of Opulence', set_code="tst", number="M01", mana_cost='{R}', cmc=1.0, type_line='Enchantment — Aura Curse', oracle_text='Enchant player\nWhenever enchanted player is attacked, create a Gold token. Each opponent attacking that player does the same. (A Gold token is an artifact with "Sacrifice this token: Add one mana of any color.")', colors=['R'], color_identity=['R'], keywords=['Enchant']),  # noqa: E501
    card('Curse of Verbosity', set_code="tst", number="M02", mana_cost='{2}{U}', cmc=3.0, type_line='Enchantment — Aura Curse', oracle_text='Enchant player\nWhenever enchanted player is attacked, you draw a card. Each opponent attacking that player does the same.', colors=['U'], color_identity=['U'], keywords=['Enchant']),  # noqa: E501
    card('Vow of Duty', set_code="tst", number="N01", mana_cost='{2}{W}', cmc=3.0, type_line='Enchantment — Aura', oracle_text="Enchant creature\nEnchanted creature gets +2/+2, has vigilance, and can't attack you or planeswalkers you control.", colors=['W'], color_identity=['W'], keywords=['Enchant']),  # noqa: E501
    card('Carapace', set_code="tst", number="N02", mana_cost='{G}', cmc=1.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nEnchanted creature gets +0/+2.\nSacrifice this Aura: Regenerate enchanted creature.', colors=['G'], color_identity=['G'], keywords=['Regenerate', 'Enchant']),  # noqa: E501
    card('Sinister Possession', set_code="tst", number="N03", mana_cost='{B}', cmc=1.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nWhenever enchanted creature attacks or blocks, its controller loses 2 life.', colors=['B'], color_identity=['B'], keywords=['Enchant']),  # noqa: E501
    card('Amorphous Axe', set_code="tst", number="N04", mana_cost='{2}', cmc=2.0, type_line='Artifact — Equipment', oracle_text='Equipped creature gets +3/+0 and is every creature type.\nEquip {3} ({3}: Attach to target creature you control. Equip only as a sorcery.)', colors=[], color_identity=[], keywords=['Equip']),  # noqa: E501
    card('Ghoulflesh', set_code="tst", number="N05", mana_cost='{B}', cmc=1.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nEnchanted creature gets -1/-1 and is a black Zombie in addition to its other colors and types.', colors=['B'], color_identity=['B'], keywords=['Enchant']),  # noqa: E501
    card('Sinister Strength', set_code="tst", number="N06", mana_cost='{1}{B}', cmc=2.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nEnchanted creature gets +3/+1 and is black.', colors=['B'], color_identity=['B'], keywords=['Enchant']),  # noqa: E501
    card('Viridian Longbow', set_code="tst", number="P01", mana_cost='{1}', cmc=1.0, type_line='Artifact — Equipment', oracle_text='Equipped creature has "{T}: This creature deals 1 damage to any target."\nEquip {3} ({3}: Attach to target creature you control. Equip only as a sorcery.)', colors=[], color_identity=[], keywords=['Equip']),  # noqa: E501
    card('Paradise Mantle', set_code="tst", number="P02", mana_cost='{0}', cmc=0.0, type_line='Artifact — Equipment', oracle_text='Equipped creature has "{T}: Add one mana of any color."\nEquip {1}', colors=[], color_identity=[], keywords=['Equip']),  # noqa: E501
    # (still manual)
    card('Curse of Bounty', set_code="tst", number="M03", mana_cost='{1}{G}', cmc=2.0, type_line='Enchantment — Aura Curse', oracle_text='Enchant player\nWhenever enchanted player is attacked, untap all nonland permanents you control. Each opponent attacking that player untaps all nonland permanents they control.', colors=['G'], color_identity=['G'], keywords=['Enchant']),  # noqa: E501
    card('Elvish Guidance', set_code="tst", number="L20", mana_cost='{2}{G}', cmc=3.0, type_line='Enchantment — Aura', oracle_text='Enchant land\nWhenever enchanted land is tapped for mana, its controller adds an additional {G} for each Elf on the battlefield.', colors=['G'], color_identity=['G'], keywords=['Enchant']),  # noqa: E501
    card('Song of the Dryads', set_code="tst", number="L21", mana_cost='{2}{G}', cmc=3.0, type_line='Enchantment — Aura', oracle_text='Enchant permanent\nEnchanted permanent is a colorless Forest land.', colors=['G'], color_identity=['G'], keywords=['Enchant']),  # noqa: E501
    card('Flickering Ward', set_code="tst", number="L22", mana_cost='{W}', cmc=1.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nAs this Aura enters, choose a color.\nEnchanted creature has protection from the chosen color. This effect doesn\'t remove this Aura.\n{W}: Return this Aura to its owner\'s hand.', colors=['W'], color_identity=['W'], keywords=['Enchant']),  # noqa: E501
    card('Witness Protection', set_code="tst", number="L23", mana_cost='{U}', cmc=1.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nEnchanted creature loses all abilities and is a green and white Citizen creature with base power and toughness 1/1 named Legitimate Businessperson. (It loses all other colors, card types, creature types, and names.)', colors=['U'], color_identity=['U'], keywords=['Enchant']),  # noqa: E501
]
FULL = ["Sword of Feast and Famine", "Spirit Mantle", "Lavaspur Boots", "Kenrith's Transformation", "Darksteel Mutation",
        "Lignify", "Colossus Hammer", "Wild Growth", "Fertile Ground", "Shiny Impetus", "Sword of Body and Mind",
        "Prosthetic Injector", "Curse of Opulence", "Curse of Verbosity", "Vow of Duty", "Carapace", "Sinister Possession",
        "Amorphous Axe", "Ghoulflesh", "Sinister Strength", "Viridian Longbow", "Paradise Mantle"]
STILL_MANUAL = {
    "Elvish Guidance": "for each Elf",  # a counted extra
    "Song of the Dryads": "Forest land",  # a basic land type (305.7: rules-text abilities go)
    "Flickering Ward": "the chosen color",  # the color chosen as it entered
    "Witness Protection": "named",  # a name change, two colors
    "Super-Soldier Serum": "attach any number of target Equipment",
    "Curse of Bounty": "untaps all nonland permanents they control",  # (not "does the same")
}


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def reloaded(s):
    """The table as a fresh session rebuilt from the saved history (a save and a load)."""
    return GameSession(s.history.rebuild(), cards=s.cards)


def cast(s, name, targets=None, **m):
    c = to_hand(s, name)
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=c.id, **({"targets": targets} if targets else {}))
    return c


def put(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def equip(s, name, creature):
    gear = put(s, name)
    act(s, "p1", type="attach", card_ids=[gear.id], to=creature.id)
    return gear


def to_attack(s, number=3):
    until(s, lambda s: s.state.turn.number == number and s.state.rules.decision is not None
          and s.state.rules.decision.kind == "declare_attackers")


def plan(s):
    return Plan(s.state, "p1", s.cards, None)


# -- coverage ----------------------------------------------------------------------------------------------------
def test_still_manual_lines():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] not in STILL_MANUAL:
            continue
        chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
        level = coverage.of_characteristics(chs)
        assert level.level != "FULL", c["name"]
        manual = " ".join(level.manual_parts)
        assert STILL_MANUAL[c["name"]] in manual, (c["name"], manual)


def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
            assert coverage.of_characteristics(chs).level == "FULL", (c["name"], coverage.of_characteristics(chs).manual_parts)


@pytest.mark.parametrize("text", [
    "Enchanted creature has protection from the chosen color.",  # (a choice made as it entered)
    "Enchanted permanent is a colorless Forest land.",  # 305.7
    "Enchanted creature is an Island.",  # (an Island land type on a non-land: wave 12D reads only "Enchanted land")
    "Enchanted creature loses all abilities and is a green and white Citizen creature with base power and toughness 1/1 "
    "named Legitimate Businessperson.",
    "Enchanted permanent is a Treasure artifact with \"{T}, Sacrifice this artifact: Add one mana of any color,\" and it "
    "loses all other abilities.",
    "Creatures you control lose all abilities.",  # (only an Aura's or Equipment's)
    "As long as you control an Elf, enchanted creature loses all abilities.",  # (conditional: not read)
    "Enchanted creature gets +2/+2 and has ripple 4.",
])
def test_refused_wordings(text):
    assert statics.parse(text) is None


# -- protection, ward, toxic -------------------------------------------------------------------------------------
def test_sword_of_feast_and_famine_protection_and_its_trigger(cards):
    """Protection from black and from green (702.16g): green and black creatures can't block it (702.16f), a red one
    can. Combat damage to Bob: he discards a card and Alice untaps all her lands."""
    s = build(cards, "Sword of Feast and Famine", "Llanowar Elves", "Lightning Bolt")
    bear = token(s, "p1", "Bear")
    equip(s, "Sword of Feast and Famine", bear)
    elves = put(s, "Llanowar Elves", "p1")
    p = plan(s)
    bch = p.ch(s.state.cards[bear.id])
    assert bch.pt == (4, 4) and "protection" in bch.keywords
    assert protection.protected_from(bch, p.ch(s.state.cards[elves.id]))
    assert not protection.protected_from(bch, p.ch(named(s, "Lightning Bolt")))
    act(s, "p2", type="create_token", player="p2", token={"name": "Ogre", "type_line": "Token Creature — Ogre",
                                                         "power": "3", "toughness": "3", "colors": ["R"], "text": ""})
    ogre = named(s, "Ogre")
    assert "protection" in block_problem(s.state, s.state.cards[elves.id], p.ch(s.state.cards[elves.id]),
                                         s.state.cards[bear.id], bch, s.cards)
    assert block_problem(s.state, s.state.cards[ogre.id], p.ch(s.state.cards[ogre.id]), s.state.cards[bear.id], bch,
                         s.cards) is None
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    to_attack(s)
    act(s, "p1", type="tap", card_ids=[forest.id], tapped=True)
    hand = len(s.state.zones["p2:hand"])
    attack(s, (bear, "p2"))
    through_combat(s)
    assert len(s.state.zones["p2:hand"]) == hand - 1  # "that player discards a card"
    assert not s.state.cards[forest.id].tapped  # "and you untap all lands you control"
    replay_matches(s)
    replay_matches(reloaded(s))


def test_protection_from_creatures_and_ward_and_toxic(cards):
    s = build(cards, "Spirit Mantle", "Lavaspur Boots", "Prosthetic Injector")
    bear = token(s, "p1", "Bear")
    cast(s, "Spirit Mantle", targets=[bear.id], W=1, C=1)
    settle(s)
    wolf = token(s, "p2", "Wolf")
    p = plan(s)
    bch = p.ch(s.state.cards[bear.id])
    assert bch.pt == (3, 3)
    assert "protection" in block_problem(s.state, s.state.cards[wolf.id], p.ch(s.state.cards[wolf.id]),
                                         s.state.cards[bear.id], bch, s.cards)
    # ward {1} granted, next to a printed ward {2}: each instance triggers (702.21a)
    warded = token(s, "p1", "Warded", text="Ward {2}")
    equip(s, "Lavaspur Boots", warded)
    wch = plan(s).ch(s.state.cards[warded.id])
    assert sorted(triggers.ward_costs(wch)) == ["{1}", "{2}"] and "haste" in wch.keywords and wch.pt == (3, 2)
    # toxic 1 (702.164): combat damage to a player also gives a poison counter
    equip(s, "Prosthetic Injector", bear)
    to_attack(s)
    attack(s, (bear, "p2"))
    through_combat(s)
    assert s.state.players["p2"].resources.get("poison", 0) == 1
    replay_matches(s)


def test_sword_of_body_and_mind_you_create_and_that_player_mills(cards):
    s = build(cards, "Sword of Body and Mind")
    bear = token(s, "p1", "Bear")
    equip(s, "Sword of Body and Mind", bear)
    to_attack(s)
    library = len(s.state.zones["p2:library"])
    graveyard = len(s.state.zones.get("p2:graveyard", []))
    attack(s, (bear, "p2"))
    through_combat(s)
    assert len(s.state.zones["p2:library"]) == max(0, library - 10)  # (Bob's library is short: all of it)
    assert len(s.state.zones["p2:graveyard"]) == graveyard + min(10, library)
    assert any(c.name == "Wolf" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    replay_matches(s)


# -- layers 4-7b -------------------------------------------------------------------------------------------------
def test_kenriths_transformation_on_a_lord(cards):
    """The lord loses all abilities (its anthem stops: Lignify ruling), is only a green Elk creature (Frogify/Kenrith
    rulings: no other card types; supertypes stay), base 3/3; a +1/+1 counter still counts (613.4c)."""
    s = build(cards, "Kenrith's Transformation")
    act(s, "p1", type="create_token", player="p1", token={"name": "Lord", "type_line": "Legendary Artifact Creature — Goblin",
                                                         "power": "2", "toughness": "2", "colors": ["R"],
                                                         "text": "Flying\nOther Goblins you control get +1/+1."})
    lord = named(s, "Lord")
    act(s, "p1", type="create_token", player="p1", token={"name": "Grunt", "type_line": "Token Creature — Goblin",
                                                         "power": "1", "toughness": "1", "text": ""})
    grunt = named(s, "Grunt")
    assert ch(s, grunt).pt == (2, 2)
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Kenrith's Transformation", targets=[lord.id], G=1, C=1)
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1  # (put in hand, cast, then a card drawn)
    now = ch(s, lord)
    assert now.pt == (3, 3) and now.abilities == () and "flying" not in now.keywords
    assert now.types == frozenset({"Creature"}) and now.subtypes == frozenset({"Elk"}) and now.colors == frozenset({"G"})
    assert "Legendary" in now.supertypes
    assert ch(s, grunt).pt == (1, 1)  # the anthem is gone with the lord's abilities
    act(s, "p1", type="counter", card_ids=[lord.id], kind="+1/+1", delta=1)
    assert ch(s, lord).pt == (4, 4)
    s = reloaded(s)
    assert ch(s, lord).pt == (4, 4) and ch(s, grunt).pt == (1, 1)
    aura = named(s, "Kenrith's Transformation")
    act(s, "p1", type="move", card_ids=[aura.id], to={"zone": "graveyard"})
    back = ch(s, lord)
    assert "flying" in back.keywords and back.pt == (3, 3) and ch(s, grunt).pt == (2, 2)
    replay_matches(s)


def test_moving_a_loses_all_abilities_aura_updates_both_hosts(cards):
    """-- review (Codex) -- the static cache must notice an Aura moving: the old host's anthem works again, the new
    host's statics are gone."""
    s = build(cards, "Kenrith's Transformation")
    for name in ("Lord", "Other Lord"):
        act(s, "p1", type="create_token", player="p1", token={"name": name, "type_line": "Token Creature — Goblin",
                                                             "power": "2", "toughness": "2",
                                                             "text": "Other Goblins you control get +1/+1."})
    act(s, "p1", type="create_token", player="p1", token={"name": "Grunt", "type_line": "Token Creature — Goblin",
                                                         "power": "1", "toughness": "1", "text": ""})
    lord, other, grunt = named(s, "Lord"), named(s, "Other Lord"), named(s, "Grunt")
    assert ch(s, grunt).pt == (3, 3)
    cast(s, "Kenrith's Transformation", targets=[lord.id], G=1, C=1)
    settle(s)
    assert ch(s, grunt).pt == (2, 2)  # only Other Lord's anthem
    aura = named(s, "Kenrith's Transformation")
    act(s, "p1", type="attach", card_ids=[aura.id], to=other.id)
    assert ch(s, grunt).pt == (2, 2) and ch(s, lord).pt == (2, 2)  # now only Lord's anthem; Lord is a Goblin again
    assert ch(s, other).subtypes == frozenset({"Elk"})
    replay_matches(s)


def test_darksteel_mutation_and_lignify_on_tarmogoyf(cards):
    """Darksteel Mutation: an indestructible 0/1 Insect artifact creature (its characteristic-defining P/T is gone);
    Lightning Bolt doesn't destroy it. Lignify on another: a 0/4 Treefolk (still a creature)."""
    s = build(cards, "Darksteel Mutation", "Lignify", "Tarmogoyf", "Lightning Bolt")
    goyf = put(s, "Tarmogoyf", "p1")
    cast(s, "Darksteel Mutation", targets=[goyf.id], W=1, C=1)
    settle(s)
    now = ch(s, goyf)
    assert now.pt == (0, 1) and "indestructible" in now.keywords
    assert now.types == frozenset({"Artifact", "Creature"}) and now.subtypes == frozenset({"Insect"})
    assert now.colors == frozenset({"G"})  # (Darksteel Mutation doesn't change colors: ruling)
    cast(s, "Lightning Bolt", targets=[goyf.id], R=1)
    settle(s)
    assert s.state.cards[goyf.id].zone == "p1:battlefield"
    bear = token(s, "p1", "Bear", text="Flying")
    cast(s, "Lignify", targets=[bear.id], G=1, C=1)
    settle(s)
    tree = ch(s, bear)
    assert tree.pt == (0, 4) and tree.subtypes == frozenset({"Treefolk"}) and tree.is_creature
    assert "flying" not in tree.keywords
    replay_matches(s)
    replay_matches(reloaded(s))


def test_a_later_grant_survives_and_an_earlier_one_does_not(cards):
    """613.7: an ability granted after the Aura's timestamp stays (Kenrith ruling); one granted before is gone."""
    s = build(cards, "Lignify", "Colossus Hammer")
    bear = token(s, "p1", "Bear")
    act(s, "p1", type="create_token", player="p1", token={"name": "Banner", "type_line": "Token Enchantment",
                                                         "text": "Creatures you control have vigilance."})
    cast(s, "Lignify", targets=[bear.id], G=1, C=1)
    settle(s)
    assert "vigilance" not in ch(s, bear).keywords  # (the Banner's grant has the earlier timestamp)
    act(s, "p1", type="create_token", player="p1", token={"name": "Flag", "type_line": "Token Enchantment",
                                                         "text": "Creatures you control have trample."})
    assert "trample" in ch(s, bear).keywords
    replay_matches(s)


def test_colossus_hammer_loses_flying_and_angelic_types(cards):
    s = build(cards, "Colossus Hammer", "Super-Soldier Serum")
    bird = token(s, "p1", "Bird", "1/1", text="Flying")
    equip(s, "Colossus Hammer", bird)
    now = ch(s, bird)
    assert now.pt == (11, 11) and "flying" not in now.keywords
    cast(s, "Super-Soldier Serum", targets=[bird.id], W=1, C=1)
    settle(s)
    now = ch(s, bird)
    assert "Legendary" in now.supertypes and "Soldier" in now.subtypes and "Test" in now.subtypes
    assert now.pt == (13, 13) and {"first strike", "vigilance"} <= now.keywords
    replay_matches(s)


# -- triggered mana abilities on the enchanted land --------------------------------------------------------------
def forest_of(s):
    return next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")


def test_wild_growth_adds_an_additional_green(cards):
    s = build(cards, "Wild Growth", "Grizzly Bears")
    forest = forest_of(s)
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    cast(s, "Wild Growth", targets=[forest.id], G=1)
    settle(s)
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=0)
    assert s.state.players["p1"].mana == {"G": 2}
    act(s, "p1", type="add_mana", player="p1", mana={"G": -2})
    act(s, "p1", type="tap", card_ids=[forest.id], tapped=False)
    bears = to_hand(s, "Grizzly Bears")
    act(s, "p1", type="cast_spell", card_id=bears.id)  # {1}{G}: the one enchanted Forest pays it all
    assert s.state.cards[forest.id].tapped and s.state.cards[bears.id].zone in ("stack", "p1:battlefield")
    assert s.state.players["p1"].mana == {}
    replay_matches(s)
    replay_matches(reloaded(s))


def test_fertile_ground_any_color_and_a_restricted_ability(cards):
    s = build(cards, "Fertile Ground", "Wild Growth", "Eldrazi Temple")
    forest = forest_of(s)
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    cast(s, "Fertile Ground", targets=[forest.id], G=1, C=1)
    settle(s)
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=0)
    d = s.state.rules.decision
    assert d is not None and len(d.options) == 5  # {G} plus one of the five colors
    red = next(o for o in d.options if "R" in o.label)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[red.id])
    assert s.state.players["p1"].mana == {"G": 1, "R": 1}
    # Wild Growth on Eldrazi Temple: its plain {C} carries the extra {G}; the restricted {C}{C} is left to the player
    temple = put(s, "Eldrazi Temple")
    cast(s, "Wild Growth", targets=[temple.id], G=1)
    settle(s)
    from app.rules.casting import mana_abilities

    found = dict(mana_abilities(s.state, s.state.cards[temple.id], s.cards))
    assert list(found) == [0] and found[0].options == (("C", "G"),)
    replay_matches(s)


# -- Curses that share ----------------------------------------------------------------------------------------------
def golds(s, pid):
    return sum(1 for c in s.state.cards.values() if c.name == "Gold" and c.controller == pid and c.zone.endswith("battlefield"))


def test_curse_of_opulence_and_verbosity_the_attacking_opponent_does_the_same(cards):
    """Alice enchants herself (ruling: "you'll get its effects whenever another player attacks you"). Bob attacks her:
    Alice creates a Gold token and draws a card, and Bob, an opponent attacking her, does the same."""
    s = build(cards, "Curse of Opulence", "Curse of Verbosity")
    cast(s, "Curse of Opulence", targets=["p1"], R=1)
    settle(s)
    cast(s, "Curse of Verbosity", targets=["p1"], U=1, C=2)
    settle(s)
    assert named(s, "Curse of Opulence").attached_player == "p1"
    ogre = token(s, "p2", "Ogre", "3/3")
    until(s, lambda s: s.state.turn.number == 2 and s.state.rules.decision is not None
          and s.state.rules.decision.kind == "declare_attackers")
    hands = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2")}
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": ogre.id, "target": "p1"}])
    settle(s)
    assert golds(s, "p1") == 1 and golds(s, "p2") == 1
    assert len(s.state.zones["p1:hand"]) == hands["p1"] + 1 and len(s.state.zones["p2:hand"]) == hands["p2"] + 1
    replay_matches(s)
    replay_matches(reloaded(s))


def test_curse_only_its_controller_when_nobody_attacks_that_player_any_more(cards):
    """Ruling: no creature attacking the enchanted player as the ability resolves → only the Curse's controller."""
    s = build(cards, "Curse of Opulence", "Lightning Bolt")
    cast(s, "Curse of Opulence", targets=["p1"], R=1)
    settle(s)
    ogre = token(s, "p2", "Ogre", "3/3")
    until(s, lambda s: s.state.turn.number == 2 and s.state.rules.decision is not None
          and s.state.rules.decision.kind == "declare_attackers")
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": ogre.id, "target": "p1"}])
    assert s.state.zones.get("stack")  # (the Curse's trigger)
    act(s, "p1", type="move", card_ids=[ogre.id], to={"zone": "graveyard"})  # (gone before it resolves)
    settle(s)
    assert golds(s, "p1") == 1 and golds(s, "p2") == 0
    replay_matches(s)


# -- restrictions, regeneration, attack-or-block triggers, more types and colors -------------------------------------
def to_bobs_attack(s):
    until(s, lambda s: s.state.turn.number == 2 and s.state.rules.decision is not None
          and s.state.rules.decision.kind == "declare_attackers")


def test_vow_of_duty_the_creature_cant_attack_the_auras_controller(cards):
    """508.1c: Bob's creature can't attack Alice. Goaded by Alice too (Shiny Impetus: it must attack a player other
    than her if able, 701.15b), it has nowhere to attack: declaring no attackers is legal (508.1d)."""
    from app.game.errors import ActionError

    s = build(cards, "Vow of Duty", "Shiny Impetus")
    ogre = token(s, "p2", "Ogre", "3/3")
    cast(s, "Vow of Duty", targets=[ogre.id], W=1, C=2)
    settle(s)
    cast(s, "Shiny Impetus", targets=[ogre.id], R=1, C=2)
    settle(s)
    assert ch(s, ogre).pt == (7, 7) and "vigilance" in ch(s, ogre).keywords
    to_bobs_attack(s)
    with pytest.raises(ActionError, match="can't attack"):
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": ogre.id, "target": "p1"}])
    act(s, "p2", type="declare_attackers", attackers=[])
    replay_matches(s)
    replay_matches(reloaded(s))


def test_carapace_sacrificed_regenerates_the_creature_it_enchanted(cards):
    """"Sacrifice this Aura: Regenerate enchanted creature." — the Aura is gone as the ability resolves: the creature
    it enchanted as it last existed (608.2h) gets the shield (701.19a)."""
    s = build(cards, "Carapace", "Lightning Bolt")
    bear = token(s, "p1", "Bear")
    aura = cast(s, "Carapace", targets=[bear.id], G=1)
    settle(s)
    assert ch(s, bear).pt == (2, 4)
    act(s, "p1", type="activate_ability", card_id=aura.id, ability=2)
    settle(s)
    assert s.state.cards[aura.id].zone == "p1:graveyard"
    cast(s, "Lightning Bolt", targets=[bear.id], R=1)
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.cards[bear.id].tapped  # regenerated
    replay_matches(s)


def test_sinister_possession_attacks_or_blocks(cards):
    """"Whenever enchanted creature attacks or blocks, its controller loses 2 life" (603.2: each event)."""
    s = build(cards, "Sinister Possession")
    bear = token(s, "p1", "Bear")
    cast(s, "Sinister Possession", targets=[bear.id], B=1)
    settle(s)
    to_attack(s)
    life = s.state.players["p1"].life
    attack(s, (bear, "p2"))
    settle(s)
    assert s.state.players["p1"].life == life - 2
    replay_matches(s)


def test_every_creature_type_and_colors(cards):
    s = build(cards, "Amorphous Axe", "Ghoulflesh", "Sinister Strength")
    bear = token(s, "p1", "Bear", "3/3")
    equip(s, "Amorphous Axe", bear)
    now = ch(s, bear)
    assert {"Elf", "Goblin", "Sliver", "Test"} <= now.subtypes and now.pt == (6, 3)
    wolf = token(s, "p1", "Wolf", "3/3")
    act(s, "p1", type="create_token", player="p1", token={"name": "Pixie", "type_line": "Token Creature — Faerie",
                                                         "power": "2", "toughness": "2", "colors": ["U"], "text": ""})
    pixie = named(s, "Pixie")
    cast(s, "Ghoulflesh", targets=[pixie.id], B=1)
    settle(s)
    now = ch(s, pixie)
    assert now.colors == frozenset({"U", "B"}) and now.subtypes == frozenset({"Faerie", "Zombie"}) and now.pt == (1, 1)
    cast(s, "Sinister Strength", targets=[pixie.id], B=1, C=1)
    settle(s)
    now = ch(s, pixie)
    assert now.colors == frozenset({"B"}) and now.pt == (4, 2)  # (the later timestamp sets it: 613.7)
    assert ch(s, wolf).colors == frozenset()
    replay_matches(s)


def test_equipment_granting_a_quoted_tap_ability(cards):
    """"Equipped creature has "{T}: …"" is a static (not an Equip cost): the creature has the ability (layer 6) and
    uses it as its own ("This creature" deals the damage); summoning sickness applies to {T} (302.6)."""
    from app.game.errors import ActionError
    from app.rules.casting import mana_abilities

    s = build(cards, "Viridian Longbow", "Paradise Mantle")
    bear = token(s, "p1", "Bear")
    equip(s, "Viridian Longbow", bear)
    granted = [a for a in ch(s, bear).abilities if a.index >= 100]
    assert [a.text for a in granted] == ["{T}: ~ deals 1 damage to any target."]  # ("This creature": the creature)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=bear.id, ability=granted[0].index, targets=["p2"])
    elf = token(s, "p1", "Elf", "1/1")
    equip(s, "Paradise Mantle", elf)
    to_attack(s)
    act(s, "p1", type="declare_attackers", attackers=[])
    until(s, lambda s: s.state.turn.phase == "main2")
    life = s.state.players["p2"].life
    act(s, "p1", type="activate_ability", card_id=bear.id, ability=granted[0].index, targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == life - 1 and s.state.cards[bear.id].tapped
    found = mana_abilities(s.state, s.state.cards[elf.id], s.cards)
    assert len(found) == 1 and len(found[0][1].options) == 5
    replay_matches(s)
