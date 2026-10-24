"""Wave 100D: rule-modifying statics and loyalty abilities of permanents (app/rules/static_perm100d.py), real Oracle text,
CR 2026-09-25. Every scenario checks the replay and a save/load round trip.

* Attachment legality: "can be attached only to a creature with power / toughness N or greater" and "can't be equipped" (301.5c,
  701.3b, 704.5n); "You control enchanted artifact creature." (613.1b); "Enchanted Mountain is a 7/7 … It's still a land." (205.1b).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, token_of
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand

EXTRA = [
    real('O-Naginata', '{1}', 1, 'Artifact — Equipment', 'This Equipment can be attached only to a creature with power 3 or greater.\nEquipped creature gets +3/+0 and has trample.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)', None, ''),
    real('Gate Smasher', '{3}', 3, 'Artifact — Equipment', 'This Equipment can be attached only to a creature with toughness 4 or greater.\nEquipped creature gets +3/+0 and has trample.\nEquip {3}', None, ''),
    real('Goblin Brawler', '{2}{R}', 3, 'Creature — Goblin Warrior', "First strike\nThis creature can't be equipped.", ("2", "2"), 'R'),
    real('Bonesplitter', '{1}', 1, 'Artifact — Equipment', 'Equipped creature gets +2/+0.\nEquip {1}', None, ''),
    real('Domineer', '{1}{U}{U}', 3, 'Enchantment — Aura', 'Enchant artifact creature\nYou control enchanted artifact creature.', None, 'U'),
    real('Awaken the Ancient', '{1}{R}{R}{R}', 4, 'Enchantment — Aura', "Enchant Mountain\nEnchanted Mountain is a 7/7 red Giant creature with haste. It's still a land.", None, 'R'),
]


def pw(name, cost, cmc, types, text, colors, loyalty):
    return {**real(name, cost, cmc, types, text, None, colors), "loyalty": loyalty}


EXTRA += [
    pw('Gideon, the Oathsworn', '{4}{W}{W}', 6, 'Legendary Planeswalker — Gideon', "Whenever you attack with two or more non-Gideon creatures, put a +1/+1 counter on each of those creatures.\n+2: Until end of turn, Gideon becomes a 5/5 white Soldier creature that's still a planeswalker. Prevent all damage that would be dealt to him this turn. (He can't attack if he was cast this turn.)\n−9: Exile Gideon and each creature your opponents control.", 'W', "4"),
    pw('Dovin, Architect of Law', '{4}{W}{U}', 6, 'Legendary Planeswalker — Dovin', "+1: You gain 2 life and draw a card.\n−1: Tap target creature. It doesn't untap during its controller's next untap step.\n−9: Tap all permanents target opponent controls. That player skips their next untap step.", 'UW', "5"),
    pw('Ajani Unrelenting', '{4}{R}{R}', 6, 'Legendary Planeswalker — Ajani', 'Whenever you activate a loyalty ability, create a 2/2 colorless Wizard Soldier creature token named Cadet.\n+1: Creatures you control get +1/+0 and gain haste until end of turn.\n−2: Discard your hand, then draw a card for each creature you control.\n−3: Ajani deals 4 damage to each creature except for tokens you control.', 'R', "5"),
    pw('Nicol Bolas, Planeswalker', '{4}{U}{B}{B}{R}', 8, 'Legendary Planeswalker — Bolas', "+3: Destroy target noncreature permanent.\n−2: Gain control of target creature.\n−9: Nicol Bolas deals 7 damage to target player or planeswalker. That player or that planeswalker's controller discards seven cards, then sacrifices seven permanents of their choice.", 'BRU', "5"),
    pw('Liliana, the Necromancer', '{3}{B}{B}', 5, 'Legendary Planeswalker — Liliana', '+1: Target player loses 2 life.\n−1: Return target creature card from your graveyard to your hand.\n−7: Destroy up to two target creatures. Put up to two creature cards from graveyards onto the battlefield under your control.', 'B', "4"),
]
EXTRA += [
    real('Replenish', '{3}{W}', 4, 'Sorcery', 'Return all enchantment cards from your graveyard to the battlefield. (Auras with nothing to enchant remain in your graveyard.)', None, 'W'),
    real('Heightened Awareness', '{3}{U}{U}', 5, 'Enchantment', 'As this enchantment enters, discard your hand.\nAt the beginning of your draw step, draw an additional card.', None, 'U'),
    real('Overlaid Terrain', '{2}{G}{G}', 4, 'Enchantment', 'As this enchantment enters, sacrifice all lands you control.\nLands you control have "{T}: Add two mana of any one color."', None, 'G'),
    real("Full Moon's Rise", '{1}{G}', 2, 'Enchantment', 'Werewolf creatures you control get +1/+0 and have trample.\nSacrifice this enchantment: Regenerate all Werewolf creatures you control.', None, 'G'),
]
EXTRA += [
    real('Scourge of the Skyclaves', '{1}{B}', 2, 'Creature — Demon', "Kicker {4}{B}\nWhen you cast this spell, if it was kicked, each player loses half their life, rounded up.\nScourge of the Skyclaves's power and toughness are each equal to 20 minus the highest life total among players.", ("*", "*"), 'B'),
    real('Roiling Horror', '{3}{B}{B}', 5, 'Creature — Horror', "Roiling Horror's power and toughness are each equal to your life total minus the life total of an opponent with the most life.\nSuspend X—{X}{B}{B}{B}. X can't be 0. (Rather than cast this card from your hand, you may pay {X}{B}{B}{B} and exile it with X time counters on it. At the beginning of your upkeep, remove a time counter. When the last is removed, you may cast it without paying its mana cost. It has haste.)\nWhenever a time counter is removed from this card while it's exiled, target player loses 1 life and you gain 1 life.", ("*", "*"), 'B'),
    real('Angry Mob', '{2}{W}{W}', 4, 'Creature — Human', "Trample\nDuring your turn, Angry Mob's power and toughness are each equal to 2 plus the number of Swamps your opponents control. During turns other than yours, Angry Mob's power and toughness are each 2.", ("2+*", "2+*"), 'W'),
    real('Swamp', '', 0, 'Basic Land — Swamp', '({T}: Add {B}.)', None, ''),
    card("Alrund, God of the Cosmos // Hakka, Whispering Raven", set_code="tst", number="100D-alrund", layout="modal_dfc", mana_cost=None, cmc=5.0,
         type_line="Legendary Creature — God // Legendary Creature — Bird", colors=["U"], color_identity=["U"], image_uris=None, card_faces=[
             {"object": "card_face", "name": "Alrund, God of the Cosmos", "mana_cost": "{3}{U}{U}", "type_line": "Legendary Creature — God",
              "oracle_text": "Alrund gets +1/+1 for each card in your hand and each foretold card you own in exile.\nAt the beginning of your end step, choose a card type, then reveal the top two cards of your library. Put all cards of the chosen type revealed this way into your hand and the rest on the bottom of your library in any order.",
              "power": "1", "toughness": "1", "colors": ["U"]},
             {"object": "card_face", "name": "Hakka, Whispering Raven", "mana_cost": "{1}{U}", "type_line": "Legendary Creature — Bird",
              "oracle_text": "Flying\nWhenever Hakka deals combat damage to a player, return it to its owner's hand, then scry 2.", "power": "2", "toughness": "3", "colors": ["U"]},
         ]),
]
EXTRA += [
    real('Case of the Stashed Skeleton', '{1}{B}', 2, 'Enchantment — Case', "When this Case enters, create a 2/1 black Skeleton creature token and suspect it. (It has menace and can't block.)\nTo solve — You control no suspected Skeletons. (If unsolved, solve at the beginning of your end step.)\nSolved — {1}{B}, Sacrifice this Case: Search your library for a card, put it into your hand, then shuffle. Activate only as a sorcery.", None, 'B'),
    real('Case of the Gateway Express', '{1}{W}', 2, 'Enchantment — Case', "When this Case enters, choose target creature you don't control. Each creature you control deals 1 damage to that creature.\nTo solve — Three or more creatures attacked this turn. (If unsolved, solve at the beginning of your end step.)\nSolved — Creatures you control get +1/+0.", None, 'W'),
    real("Case of the Gorgon's Kiss", '{B}', 1, 'Enchantment — Case', 'When this Case enters, destroy up to one target creature that was dealt damage this turn.\nTo solve — Three or more creature cards were put into graveyards from anywhere this turn. (If unsolved, solve at the beginning of your end step.)\nSolved — This Case is a 4/4 Gorgon creature with deathtouch and lifelink in addition to its other types.', None, 'B'),
    real('Case of the Burning Masks', '{1}{R}{R}', 3, 'Enchantment — Case', 'When this Case enters, it deals 3 damage to target creature an opponent controls.\nTo solve — Three or more sources you controlled dealt damage this turn. (If unsolved, solve at the beginning of your end step.)\nSolved — Sacrifice this Case: Exile the top three cards of your library. Choose one of them. You may play that card this turn.', None, 'R'),
]
EXTRA += [
    real('Mistform Sliver', '{1}{U}', 2, 'Creature — Illusion Sliver', 'All Slivers have "{1}: This permanent becomes the creature type of your choice in addition to its other types until end of turn."', ("1", "1"), 'U'),
    real('Mesmeric Sliver', '{3}{U}', 4, 'Creature — Sliver', 'All Slivers have "When this permanent enters, you may fateseal 1." (To fateseal 1, its controller looks at the top card of an opponent\'s library, then they may put that card on the bottom of that library.)', ("2", "2"), 'U'),
    real('Enduring Sliver', '{1}{W}', 2, 'Creature — Sliver', 'Outlast {2} ({2}, {T}: Put a +1/+1 counter on this creature. Outlast only as a sorcery.)\nOther Sliver creatures you control have outlast {2}.', ("2", "2"), 'W'),
]
EXTRA += [
    real('Gruul Spellbreaker', '{1}{R}{G}', 3, 'Creature — Ogre Warrior', 'Riot (This creature enters with your choice of a +1/+1 counter or haste.)\nTrample\nDuring your turn, you and this creature have hexproof.', ('3', '3'), 'GR'),
    real('Experimental Frenzy', '{3}{R}', 4, 'Enchantment', "You may look at the top card of your library any time.\nYou may play lands and cast spells from the top of your library.\nYou can't play lands or cast spells from your hand.\n{3}{R}: Destroy this enchantment.", None, 'R'),
    real('City of Solitude', '{2}{G}', 3, 'Enchantment', 'Players can cast spells and activate abilities only during their own turns.', None, 'G'),
    real('Melting', '{3}{R}', 4, 'Enchantment', 'All lands are no longer snow.', None, 'R'),
    real('Dream Leash', '{3}{U}{U}', 5, 'Enchantment — Aura', "Enchant permanent\nYou can't choose an untapped permanent as this spell's target as you cast it.\nYou control enchanted permanent.", None, 'U'),
    real('Enthralling Hold', '{3}{U}{U}', 5, 'Enchantment — Aura', "Enchant creature\nYou can't choose an untapped creature as this spell's target as you cast it.\nYou control enchanted creature.", None, 'U'),
    real('Snow-Covered Forest', '', 0, 'Basic Snow Land — Forest', '({T}: Add {G}.)', None, ''),
]
EXTRA += [
    real('Pardic Firecat', '{3}{R}', 4, 'Creature — Elemental Cat', 'Haste\nIf this card is in a graveyard, effects from spells named Flame Burst count it as a card named Flame Burst.', ('2', '3'), 'R'),
    real('Diligent Farmhand', '{G}', 1, 'Creature — Human Druid', '{1}{G}, Sacrifice this creature: Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.\nIf this card is in a graveyard, effects from spells named Muscle Burst count it as a card named Muscle Burst.', ('1', '1'), 'G'),
    real('Flame Burst', '{1}{R}', 2, 'Instant', 'Flame Burst deals X damage to any target, where X is 2 plus the number of cards named Flame Burst in all graveyards.', None, 'R'),
    real('Muscle Burst', '{1}{G}', 2, 'Instant', 'Target creature gets +X/+X until end of turn, where X is 3 plus the number of cards named Muscle Burst in all graveyards.', None, 'G'),
    real("Garza's Assassin", '{B}{B}{B}', 3, 'Creature — Human Assassin', 'Sacrifice this creature: Destroy target nonblack creature.\nRecover—Pay half your life, rounded up. (When another creature is put into your graveyard from the battlefield, you may pay half your life, rounded up. If you do, return this card from your graveyard to your hand. Otherwise, exile this card.)', ('2', '2'), 'B'),
    real('Robe of the Archmagi', '{2}{U}', 3, 'Artifact — Equipment', 'Whenever equipped creature deals combat damage to a player, you draw that many cards.\nEquip {4}\nEquip Shaman, Warlock, or Wizard {1}', None, 'U'),
    card("My Precious // Allure of Power", set_code="tst", number="100D-precious", layout="adventure", mana_cost="{3} // {1}{B}", cmc=3.0,
         type_line="Legendary Artifact — Equipment // Instant — Adventure", colors=[], color_identity=["B"], image_uris=None, card_faces=[
             {"object": "card_face", "name": "My Precious", "mana_cost": "{3}", "type_line": "Legendary Artifact — Equipment",
              "oracle_text": "Equipped creature has hexproof and can't be blocked.\nEquip—{2}, Pay 2 life."},
             {"object": "card_face", "name": "Allure of Power", "mana_cost": "{1}{B}", "type_line": "Instant — Adventure",
              "oracle_text": "As an additional cost to cast this spell, sacrifice a creature.\nDraw two cards."},
         ]),
]
EXTRA += [
    pw('Ajani Goldmane', '{2}{W}{W}', 4, 'Legendary Planeswalker — Ajani', '+1: You gain 2 life.\n−1: Put a +1/+1 counter on each creature you control. Those creatures gain vigilance until end of turn.\n−6: Create a white Avatar creature token. It has "This token\'s power and toughness are each equal to your life total."', 'W', '4'),
    real('Elsewhere Flask', '{2}', 2, 'Artifact', 'When this artifact enters, draw a card.\nSacrifice this artifact: Choose a basic land type. Each land you control becomes that type until end of turn.', None, ''),
    real('Dragon Turtle', '{1}{U}{U}', 3, 'Creature — Dragon Turtle', "Flash\nDrag Below — When this creature enters, tap it and up to one target creature an opponent controls. They don't untap during their controllers' next untap steps.", ('3', '5'), 'U'),
    real('Blue Dragon', '{5}{U}{U}', 7, 'Creature — Dragon', 'Flying\nLightning Breath — When this creature enters, until your next turn, target creature an opponent controls gets -3/-0, up to one other target creature gets -2/-0, and up to one other target creature gets -1/-0.', ('5', '5'), 'U'),
    real("Legate Lanius, Caesar's Ace", '{2}{B}{R}', 4, 'Legendary Creature — Human Soldier', 'Decimate — When Legate Lanius enters, each opponent sacrifices a tenth of the creatures they control of their choice, rounded up.\nWhenever an opponent sacrifices a creature, put a +1/+1 counter on Legate Lanius.', ('2', '2'), 'BR'),
]
EXTRA += [
    real('Serra Avenger', '{W}{W}', 2, 'Creature — Angel', "You can't cast Serra Avenger during your first, second, or third turns of the game.\nFlying, vigilance", ('3', '3'), 'W'),
    real('Karlov Watchdog', '{3}{W}', 4, 'Creature — Dog', "Vigilance\nPermanents your opponents control can't be turned face up during your turn.\nWhenever you attack with three or more creatures, creatures you control get +1/+1 until end of turn.", ('3', '2'), 'W'),
    real('Everlasting Torment', '{2}{B/R}', 3, 'Enchantment', "Players can't gain life.\nDamage can't be prevented.\nAll damage is dealt as though its source had wither. (A source with wither deals damage to creatures in the form of -1/-1 counters.)", None, 'BR'),
    real('Exalted Angel', '{4}{W}{W}', 6, 'Creature — Angel', 'Flying\nWhenever this creature deals damage, you gain that much life.\nMorph {2}{W}{W} (You may cast this card face down as a 2/2 creature for {3}. Turn it face up any time for its morph cost.)', ('4', '5'), 'W'),
]
EXTRA += [
    real('Archon of the Wild Rose', '{2}{W}{W}', 4, 'Creature — Archon', 'Flying\nOther creatures you control that are enchanted by Auras you control have base power and toughness 4/4 and have flying.', ('4', '4'), 'W'),
    pw('Urza, Planeswalker', '', 8, 'Legendary Planeswalker — Urza', 'You may activate the loyalty abilities of Urza twice each turn rather than only once.\n+2: Artifact, instant, and sorcery spells you cast this turn cost {2} less to cast. You gain 2 life.\n+1: Draw two cards, then discard a card.\n0: Create two 1/1 colorless Soldier artifact creature tokens.\n−3: Exile target nonland permanent.\n−10: Artifacts and planeswalkers you control gain indestructible until end of turn. Destroy all nonland permanents.', 'UW', '7'),
    card("Invert // Invent", set_code="tst", number="100D-invert", layout="split", mana_cost="{U/R} // {4}{U}{R}", cmc=7.0, type_line="Instant // Instant",
         colors=["R", "U"], color_identity=["R", "U"], image_uris=None, card_faces=[
             {"object": "card_face", "name": "Invert", "mana_cost": "{U/R}", "type_line": "Instant",
              "oracle_text": "Switch the power and toughness of each of up to two target creatures until end of turn."},
             {"object": "card_face", "name": "Invent", "mana_cost": "{4}{U}{R}", "type_line": "Instant",
              "oracle_text": "Search your library for an instant card and/or a sorcery card, reveal them, put them into your hand, then shuffle."}]),
]
EXTRA += [
    real('Enhanced Surveillance', '{1}{U}', 2, 'Enchantment', 'You may look at an additional two cards each time you surveil.\nExile this enchantment: Shuffle your graveyard into your library.', None, 'U'),
    real('Cosmos Charger', '{3}{U}', 4, 'Creature — Horse Spirit', "Flash\nFlying\nForetelling cards from your hand costs {1} less and can be done on any player's turn.\nForetell {2}{U} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)", ('3', '3'), 'U'),
    real('Doomskar Oracle', '{2}{W}', 3, 'Creature — Human Cleric', 'Whenever you cast your second spell each turn, you gain 2 life.\nForetell {W} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)', ('3', '2'), 'W'),
    real('Consider', '{U}', 1, 'Instant', 'Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\nDraw a card.', None, 'U'),
]
EXTRA += [
    real('Carth the Lion', '{2}{B}{G}', 4, 'Legendary Creature — Human Warrior', "Whenever Carth enters or a planeswalker you control dies, look at the top seven cards of your library. You may reveal a planeswalker card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.\nPlaneswalkers' loyalty abilities you activate cost an additional [+1] to activate.", ('3', '5'), 'BG'),
]
EXTRA += [
    real('Dusk Mangler', '{5}{B}{B}', 7, 'Creature — Horror', 'As an additional cost to cast this spell, sacrifice a creature, discard a card, or pay 4 life.\nWhen this creature enters, each opponent sacrifices a creature of their choice, discards a card, and loses 4 life.', ('5', '4'), 'B'),
    real('Urborg Lhurgoyf', '{1}{G}', 2, 'Creature — Lhurgoyf', "Kicker {U} and/or {B} (You may pay an additional {U} and/or {B} as you cast this spell.)\nAs this creature enters, mill three cards for each time it was kicked.\nUrborg Lhurgoyf's power is equal to the number of creature cards in your graveyard and its toughness is equal to that number plus 1.", ('*', '1+*'), 'G'),
]
EXTRA += [
    real('Hogaak, Arisen Necropolis', '{5}{B/G}{B/G}', 7, 'Legendary Creature — Avatar', "You can't spend mana to cast this spell.\nConvoke, delve (Each creature you tap while casting this spell pays for {1} or one mana of that creature's color. Each card you exile from your graveyard pays for {1}.)\nYou may cast this card from your graveyard.\nTrample", ('8', '8'), 'BG'),
]
EXTRA += [
    real('Sanctum Lurker', '{2}{B}', 3, 'Creature — Horror', 'When this creature enters, empower Jace 1.\nPlaneswalkers you control aren\'t put into their owners\' graveyards for having 0 loyalty.\nPlaneswalkers you control have "[+2]: This planeswalker deals 1 damage to each opponent and you gain 1 life."', ('3', '2'), 'B'),
]
EXTRA += [
    real('Minion of the Wastes', '{3}{B}{B}{B}', 6, 'Creature — Minion', "Trample\nAs this creature enters, pay any amount of life.\nMinion of the Wastes's power and toughness are each equal to the life paid as it entered.", ('*', '*'), 'B'),
    real('Nameless Race', '{3}{B}', 4, 'Creature', "Trample\nAs this creature enters, pay any amount of life. The amount you pay can't be more than the total number of white nontoken permanents your opponents control plus the total number of white cards in their graveyards.\nNameless Race's power and toughness are each equal to the life paid as it entered.", ('*', '*'), 'B'),
]
SINGLES = ["Minion of the Wastes", "Nameless Race", "Sanctum Lurker", "Hogaak, Arisen Necropolis", "Dusk Mangler", "Urborg Lhurgoyf", "Carth the Lion", "Enhanced Surveillance", "Cosmos Charger", "Archon of the Wild Rose", "Urza, Planeswalker", "Invert // Invent", "Serra Avenger", "Karlov Watchdog", "Everlasting Torment", "Ajani Goldmane", "Elsewhere Flask", "Dragon Turtle", "Blue Dragon", "Legate Lanius, Caesar's Ace", "Pardic Firecat", "Diligent Farmhand", "Garza's Assassin", "Robe of the Archmagi", "My Precious // Allure of Power"]
RULES = ["Gruul Spellbreaker", "Experimental Frenzy", "City of Solitude", "Melting", "Dream Leash", "Enthralling Hold"]
FULL = [*SINGLES, *RULES, "Mistform Sliver", "Mesmeric Sliver", "Enduring Sliver", "Case of the Stashed Skeleton", "Case of the Gateway Express", "Case of the Gorgon's Kiss", "Case of the Burning Masks", "Scourge of the Skyclaves", "Roiling Horror", "Angry Mob", "Alrund, God of the Cosmos // Hakka, Whispering Raven", "Heightened Awareness", "Overlaid Terrain", "Full Moon's Rise", "O-Naginata", "Gate Smasher", "Goblin Brawler", "Domineer", "Awaken the Ancient", "Gideon, the Oathsworn", "Dovin, Architect of Law",
        "Ajani Unrelenting", "Nicol Bolas, Planeswalker", "Liliana, the Necromancer"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def equip(s, gear, ability, host, **m):
    mana(s, **m)
    act(s, "p1", type="activate_ability", card_id=gear.id, ability=ability, targets=[host.id])
    settle(s)


def sba_check(s):
    """704.3: state-based actions are checked as a player would receive priority (Alice passes; Bob gets it)."""
    act(s, "p1", type="pass_priority")


def attached(s, gear):
    return s.state.cards[gear.id].attached_to


# -- attachment legality (301.5c, 701.3b, 704.5n) -------------------------------------------------------------------------
def test_o_naginata_moves_only_onto_power_three_and_falls_off_below(cards):
    s = build(cards, ["O-Naginata"])
    blade = put(s, "O-Naginata")
    small = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    big = token_of(s, "p1", "Ogre", "Token Creature — Ogre", "3/5")
    equip(s, blade, 2, small, C=2)  # the equip ability may target it (ruling 2020-08-07), but nothing moves (701.3b)
    assert attached(s, blade) is None
    equip(s, blade, 2, big, C=2)
    assert attached(s, blade) == big.id and pt(s, "Ogre") == (6, 5)
    act(s, "p1", type="counter", card_ids=[big.id], kind="-1/-1", delta=3)
    sba_check(s)
    assert attached(s, blade) == big.id  # 3 power with its own +3/+0 (0 + 3): still legal
    act(s, "p1", type="counter", card_ids=[big.id], kind="-1/-1", delta=1)
    sba_check(s)
    assert attached(s, blade) is None  # 704.5n: 2 power, the +3/+0 included, makes it unattached
    assert s.state.cards[blade.id].zone == "p1:battlefield"
    check(s)


def test_gate_smasher_needs_toughness_four(cards):
    s = build(cards, ["Gate Smasher"])
    smasher = put(s, "Gate Smasher")
    low = token_of(s, "p1", "Bear", "Token Creature — Bear", "5/3")
    wall = token_of(s, "p1", "Wall", "Token Creature — Wall", "0/4")
    equip(s, smasher, 2, low, C=3)
    assert attached(s, smasher) is None
    equip(s, smasher, 2, wall, C=3)
    assert attached(s, smasher) == wall.id and pt(s, "Wall") == (3, 4)
    act(s, "p1", type="counter", card_ids=[wall.id], kind="-1/-1", delta=1)
    sba_check(s)
    assert attached(s, smasher) is None  # 704.5n (ruling 2015-02-25)
    check(s)


def test_goblin_brawler_cannot_be_equipped(cards):
    s = build(cards, ["Goblin Brawler", "Bonesplitter"])
    brawler = put(s, "Goblin Brawler")
    splitter = put(s, "Bonesplitter")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    equip(s, splitter, 1, brawler, C=1)  # ruling 2004-12-01: the ability can target it, the Equipment fails to move
    assert attached(s, splitter) is None and pt(s, "Goblin Brawler") == (2, 2)
    equip(s, splitter, 1, bear, C=1)
    assert attached(s, splitter) == bear.id
    check(s)


def test_domineer_steals_an_artifact_creature_only(cards):
    s = build(cards, ["Domineer"])
    golem = token_of(s, "p2", "Golem", "Token Artifact Creature — Golem", "3/3")
    bear = token_of(s, "p2", "Bear", "Token Creature — Bear", "2/2")
    aura = to_hand(s, "Domineer")
    mana(s, U=2, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=aura.id, targets=[bear.id])  # 303.4a: enchant artifact creature
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[golem.id])
    settle(s)
    assert s.state.cards[aura.id].attached_to == golem.id
    assert s.state.cards[golem.id].controller == "p1" and s.state.cards[bear.id].controller == "p2"  # 613.1b
    check(s)


def test_awaken_the_ancient_animates_a_mountain(cards):
    s = build(cards, ["Awaken the Ancient", "Mountain"])
    mountain = put(s, "Mountain")
    forest = card_named(s, "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    aura = to_hand(s, "Awaken the Ancient")
    mana(s, R=3, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=aura.id, targets=[forest.id])  # Enchant Mountain
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[mountain.id])
    settle(s)
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[mountain.id])
    assert ch.is_creature and ch.is_land and "Mountain" in ch.subtypes and "Giant" in ch.subtypes  # 205.1b: still a land
    assert "haste" in ch.keywords and set(ch.colors) == {"R"}
    assert pt(s, "Mountain") == (7, 7)
    check(s)


# -- loyalty abilities (606) ------------------------------------------------------------------------------------------------
def walker(s, name, loyalty):
    c = put(s, name)
    act(s, "p1", type="set_counter", card_id=c.id, kind="loyalty", value=loyalty)
    return c


def loyal(s, c, ability, targets=()):
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability, targets=list(targets))
    settle(s)


def zone(s, c):
    return s.state.cards[c.id].zone if c.id in s.state.cards else None


@pytest.mark.parametrize("start", [10, 9])
def test_gideon_exiles_himself_and_each_opposing_creature(cards, start):
    s = build(cards, ["Gideon, the Oathsworn"], ["Grizzly Bears", "Sol Ring"])
    gideon = walker(s, "Gideon, the Oathsworn", start)
    mine = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    bears = put(s, "Grizzly Bears", "p2")
    ring = put(s, "Sol Ring", "p2")
    loyal(s, gideon, 2)
    assert zone(s, bears) == "p2:exile" and zone(s, ring) == "p2:battlefield" and zone(s, mine) == "p1:battlefield"
    # 9 loyalty: the cost leaves him with none, so he's put into the graveyard before the ability resolves (704.5i, ruling 2019-05-03)
    assert zone(s, gideon) == ("p1:exile" if start == 10 else "p1:graveyard")
    check(s)


def test_dovin_taps_everything_and_the_opponent_skips_the_untap_step(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, ["Dovin, Architect of Law"], ["Grizzly Bears", "Sol Ring"])
    dovin = walker(s, "Dovin, Architect of Law", 9)
    bears, ring = put(s, "Grizzly Bears", "p2"), put(s, "Sol Ring", "p2")
    forest = card_named(s, "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    loyal(s, dovin, 2, ["p2"])
    assert s.state.cards[bears.id].tapped and s.state.cards[ring.id].tapped and not s.state.cards[forest.id].tapped
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    assert s.state.cards[bears.id].tapped and s.state.cards[ring.id].tapped  # 502.1 skipped (614.10)
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1" and s.state.turn.number >= 4)
    assert not s.state.cards[bears.id].tapped  # only the next one
    check(s)


def test_ajani_unrelenting_spares_only_your_tokens(cards):
    s = build(cards, ["Ajani Unrelenting", "Grizzly Bears"])
    ajani = walker(s, "Ajani Unrelenting", 5)
    my_token = token_of(s, "p1", "Ox", "Token Creature — Ox", "5/5")
    my_card = put(s, "Grizzly Bears")
    their_token = token_of(s, "p2", "Elk", "Token Creature — Elk", "5/5")
    loyal(s, ajani, 3)
    cadet = next(c for c in s.state.cards.values() if c.name == "Cadet")  # the trigger resolved first (ruling 2026-08-21): a token of yours
    assert s.state.cards[my_token.id].damage == 0 and s.state.cards[cadet.id].damage == 0
    assert s.state.cards[their_token.id].damage == 4 and zone(s, my_card) == "p1:graveyard"
    check(s)


def test_nicol_bolas_ultimate_discards_then_sacrifices(cards):
    s = build(cards, ["Nicol Bolas, Planeswalker"], ["Grizzly Bears", "Sol Ring"])
    bolas = walker(s, "Nicol Bolas, Planeswalker", 9)
    for name in ("Grizzly Bears", "Sol Ring"):
        put(s, name, "p2")
    for i in range(7):
        token_of(s, "p2", f"Spirit {i}", "Token Creature — Spirit", "1/1")
    act(s, "p2", type="draw", count=9 - len(s.state.zones.get("p2:hand", [])))
    before = s.state.players["p2"].life
    loyal(s, bolas, 2, ["p2"])
    assert s.state.players["p2"].life == before - 7
    assert len(s.state.zones["p2:hand"]) == 2  # seven of the nine cards discarded
    assert len(s.state.zones["p2:battlefield"]) == 2  # seven of the nine permanents sacrificed
    assert zone(s, bolas) == "p1:graveyard"  # (0 loyalty)
    check(s)


def test_liliana_returns_cards_chosen_after_the_destruction(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, ["Liliana, the Necromancer"], ["Grizzly Bears"])
    liliana = walker(s, "Liliana, the Necromancer", 8)
    bears = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="activate_ability", card_id=liliana.id, ability=2, targets=[bears.id], target_counts=[1])
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.player == "p1" and bears.id in {o.id for o in d.options}  # the destroyed card is offered (ruling 2018-07-13)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])
    settle(s)
    back = s.state.cards[bears.id]
    assert back.zone == "p1:battlefield" and back.controller == "p1" and back.owner == "p2"
    check(s)


# -- "As ~ enters, …" (614.1c, 614.12) ----------------------------------------------------------------------------------------
def hand(s, pid="p1"):
    return list(s.state.zones.get(f"{pid}:hand", []))


def test_heightened_awareness_discards_the_hand_as_it_enters(cards):
    s = build(cards, ["Heightened Awareness", "Grizzly Bears", "Sol Ring"], ["Grizzly Bears"])
    aura = to_hand(s, "Heightened Awareness")
    others = [to_hand(s, "Grizzly Bears"), to_hand(s, "Sol Ring")]
    theirs = to_hand(s, "Grizzly Bears", "p2")
    mana(s, U=2, C=3)
    act(s, "p1", type="cast_spell", card_id=aura.id)
    settle(s)
    assert zone(s, aura) == "p1:battlefield"
    assert all(zone(s, c) == "p1:graveyard" for c in others) and not hand(s)
    assert zone(s, theirs) == "p2:hand"
    check(s)


def test_overlaid_terrain_sacrifices_the_lands_before_it_enters(cards):
    s = build(cards, ["Overlaid Terrain"], ["Grizzly Bears"])
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:3]
    act(s, "p1", type="move", card_ids=[f.id for f in forests], to={"player": "p1", "zone": "battlefield"})
    island = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[island.id], to={"player": "p2", "zone": "battlefield"})
    terrain = to_hand(s, "Overlaid Terrain")
    mana(s, G=2, C=2)
    act(s, "p1", type="cast_spell", card_id=terrain.id)
    settle(s)
    assert zone(s, terrain) == "p1:battlefield"
    assert all(zone(s, f) == "p1:graveyard" for f in forests) and zone(s, island) == "p2:battlefield"  # (only yours)
    check(s)


def test_entering_from_the_graveyard_does_it_too(cards):
    s = build(cards, ["Replenish", "Heightened Awareness", "Overlaid Terrain", "Sol Ring"])
    for name in ("Heightened Awareness", "Overlaid Terrain"):
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"zone": "graveyard"})
    forest = card_named(s, "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    ring = to_hand(s, "Sol Ring")
    spell = to_hand(s, "Replenish")
    mana(s, W=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    settle(s)
    assert zone(s, card_named(s, "Heightened Awareness")) == "p1:battlefield" and zone(s, card_named(s, "Overlaid Terrain")) == "p1:battlefield"
    assert zone(s, ring) == "p1:graveyard" and zone(s, forest) == "p1:graveyard"  # (Wood Elemental's ruling: however it enters)
    check(s)


def test_full_moons_rise_regenerates_every_werewolf(cards):
    s = build(cards, ["Full Moon's Rise", "Murder"])
    rise = put(s, "Full Moon's Rise")
    wolf = token_of(s, "p1", "Wolfman", "Token Creature — Human Werewolf", "2/2")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    assert pt(s, "Wolfman") == (3, 2) and pt(s, "Bear") == (2, 2)
    act(s, "p1", type="activate_ability", card_id=rise.id, ability=1)
    settle(s)
    assert zone(s, rise) == "p1:graveyard" and pt(s, "Wolfman") == (2, 2)  # (the bonus left with it: ruling 2011-09-22)
    murder = to_hand(s, "Murder")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[wolf.id])
    settle(s)
    assert zone(s, wolf) == "p1:battlefield" and s.state.cards[wolf.id].tapped  # 701.19a: regenerated
    act(s, "p1", type="move", card_ids=[murder.id], to={"zone": "hand"})
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[bear.id])
    settle(s)
    assert bear.id not in s.state.cards or zone(s, bear) != "p1:battlefield"  # no shield on a non-Werewolf
    check(s)


# -- characteristic-defining power and toughness (604.3, 613.4a) ----------------------------------------------------------------
def set_life(s, pid, n):
    act(s, "p1", type="set_life", player=pid, value=n)


def test_scourge_of_the_skyclaves_is_twenty_minus_the_highest_life(cards):
    s = build(cards, ["Scourge of the Skyclaves"])
    set_life(s, "p1", 10)
    set_life(s, "p2", 15)
    assert pt(s, "Scourge of the Skyclaves") == (5, 5)  # (in the hand too: 604.3, ruling 2020-09-25)
    scourge = put(s, "Scourge of the Skyclaves")
    assert pt(s, "Scourge of the Skyclaves") == (5, 5)
    set_life(s, "p2", 30)
    assert pt(s, "Scourge of the Skyclaves") == (-10, -10)  # set below 0 (107.1b)
    sba_check(s)
    assert zone(s, scourge) == "p1:graveyard"  # 704.5f
    check(s)


def test_roiling_horror_is_your_life_minus_the_top_opponent(cards):
    s = build(cards, ["Roiling Horror"])
    set_life(s, "p1", 30)
    set_life(s, "p2", 20)
    horror = put(s, "Roiling Horror")
    assert pt(s, "Roiling Horror") == (10, 10)
    set_life(s, "p2", 35)
    sba_check(s)
    assert zone(s, horror) == "p1:graveyard"  # -5/-5
    check(s)


def test_angry_mob_counts_swamps_only_during_your_turn(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, ["Angry Mob"], ["Swamp"])
    mob = put(s, "Angry Mob")
    put(s, "Swamp", "p2")
    token_of(s, "p2", "Swampy", "Token Land — Swamp", "0/0")  # (any land with the subtype, 205.3i)
    assert pt(s, "Angry Mob") == (4, 4)
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    assert pt(s, "Angry Mob") == (2, 2)
    assert zone(s, mob) == "p1:battlefield"
    check(s)


def test_alrund_counts_the_hand_and_foretold_cards(cards):
    s = build(cards, ["Alrund, God of the Cosmos // Hakka, Whispering Raven", "Grizzly Bears", "Sol Ring", "Swamp"], ["Grizzly Bears"])
    put(s, "Alrund, God of the Cosmos // Hakka, Whispering Raven")
    to_hand(s, "Grizzly Bears")
    to_hand(s, "Sol Ring")
    to_hand(s, "Grizzly Bears", "p2")  # (an opponent's hand doesn't count)
    swamp = card_named(s, "Swamp")
    act(s, "p1", type="move", card_ids=[swamp.id], to={"player": "p1", "zone": "foretell"})
    n = len(s.state.zones.get("p1:hand", [])) + 1
    assert pt(s, "Alrund, God of the Cosmos // Hakka, Whispering Raven") == (1 + n, 1 + n)
    check(s)


# -- Cases: "To solve — …" (719.3a) ---------------------------------------------------------------------------------------------
def to_end(s, turn=1):
    from tests.test_rules_wave30m_durations import stops, to_phase

    stops(s, "end")
    to_phase(s, "end", turn=turn)
    settle(s)


def solved(s, case):
    return "Solved" in s.state.cards[case.id].choices


@pytest.mark.parametrize("gone", [False, True])
def test_stashed_skeleton_solves_once_no_suspected_skeleton_is_left(cards, gone):
    s = build(cards, ["Case of the Stashed Skeleton"])
    case = to_hand(s, "Case of the Stashed Skeleton")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=case.id)
    settle(s)
    skeleton = next(c for c in s.state.cards.values() if c.name == "Skeleton")
    assert s.state.rules.object_id(skeleton.id) in s.state.rules.suspected
    if gone:
        act(s, "p1", type="move", card_ids=[skeleton.id], to={"zone": "graveyard"})
    token_of(s, "p1", "Bones", "Token Creature — Skeleton", "1/1")  # (a Skeleton that isn't suspected doesn't stop it)
    to_end(s)
    assert solved(s, case) == gone
    check(s)


@pytest.mark.parametrize("n", [2, 3])
def test_gateway_express_counts_the_creatures_that_attacked(cards, n):
    from tests.test_rules_wave6e_statics import attack_with

    s = build(cards, ["Case of the Gateway Express"])
    case = put(s, "Case of the Gateway Express")
    settle(s)
    raiders = [token_of(s, "p1", f"Raider {i}", "Token Creature — Soldier", "1/1", "Haste") for i in range(n)]
    attack_with(s, *raiders)
    to_end(s)
    assert solved(s, case) == (n == 3)
    if n == 3:
        assert pt(s, "Raider 0") == (2, 1)  # Solved — Creatures you control get +1/+0.
    check(s)


@pytest.mark.parametrize("n", [2, 3])
def test_gorgons_kiss_counts_creature_cards_put_into_graveyards(cards, n):
    s = build(cards, ["Case of the Gorgon's Kiss", "Grizzly Bears", "Sol Ring"], ["Grizzly Bears", "Grizzly Bears"])
    case = put(s, "Case of the Gorgon's Kiss")
    settle(s)
    mine = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1"][:1]
    theirs = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"][: n - 1]
    ring = card_named(s, "Sol Ring")
    act(s, "p1", type="move", card_ids=[c.id for c in mine] + [ring.id], to={"zone": "graveyard"})  # (a noncreature card doesn't count)
    for c in theirs:
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    wolf = token_of(s, "p1", "Wolf", "Token Creature — Wolf", "2/2")
    act(s, "p1", type="move", card_ids=[wolf.id], to={"zone": "graveyard"})  # (a token is no card: ruling 2024-02-02)
    to_end(s)
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[case.id])
    if n == 3:
        assert solved(s, case) and ch.is_creature and "Enchantment" in ch.types and "Gorgon" in ch.subtypes
        assert {"deathtouch", "lifelink"} <= set(ch.keywords) and pt(s, "Case of the Gorgon's Kiss") == (4, 4)
    else:
        assert not solved(s, case) and not ch.is_creature
    check(s)


@pytest.mark.parametrize("n", [1, 2])
def test_burning_masks_counts_each_source_once(cards, n):
    from tests.test_rules_wave6e_statics import attack_with

    s = build(cards, ["Case of the Burning Masks"])
    victim = token_of(s, "p2", "Ogre", "Token Creature — Ogre", "5/5")
    case = to_hand(s, "Case of the Burning Masks")
    mana(s, R=2, C=1)
    act(s, "p1", type="cast_spell", card_id=case.id)
    settle(s)
    assert s.state.cards[victim.id].damage == 3  # the Case is one source you controlled
    raiders = [token_of(s, "p1", f"Raider {i}", "Token Creature — Soldier", "1/1", "Double strike\nHaste") for i in range(n)]
    attack_with(s, *raiders)  # (a double striker deals damage twice: one source)
    to_end(s)
    assert solved(s, case) == (n == 2)
    check(s)


# -- Sliver grants (613.1f) ------------------------------------------------------------------------------------------------------
def derived(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def granted_index(s, c, needle):
    return next((a.index for a in derived(s, c).abilities if needle in a.text and a.kind != "static"), None)


def test_enduring_sliver_gives_other_slivers_you_control_outlast(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Enduring Sliver"])
    put(s, "Enduring Sliver")
    mine = token_of(s, "p1", "Sliver", "Token Creature — Sliver", "1/1")
    theirs = token_of(s, "p2", "Their Sliver", "Token Creature — Sliver", "1/1")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    assert granted_index(s, theirs, "+1/+1 counter") is None and granted_index(s, bear, "+1/+1 counter") is None
    to_phase(s, "main1", turn=3)
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=mine.id, ability=granted_index(s, mine, "+1/+1 counter"))
    settle(s)
    assert s.state.cards[mine.id].counters.get("+1/+1") == 1 and s.state.cards[mine.id].tapped  # 702.107a
    check(s)


def test_mistform_sliver_adds_the_chosen_type(cards):
    s = build(cards, ["Mistform Sliver"])
    sliver = put(s, "Mistform Sliver")
    theirs = token_of(s, "p2", "Their Sliver", "Token Creature — Sliver", "1/1")
    assert granted_index(s, theirs, "creature type of your choice") is not None  # "All Slivers": whoever controls them
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=sliver.id, ability=granted_index(s, sliver, "creature type of your choice"))
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["Elf"])
    settle(s)
    assert {"Illusion", "Sliver", "Elf"} <= set(derived(s, sliver).subtypes)  # in addition to its other types (ruling 2004-10-04)
    check(s)


@pytest.mark.parametrize("bottom", [True, False])
def test_mesmeric_sliver_fateseals_one_as_a_sliver_enters(cards, bottom):
    from tests.test_rules_conditionals import until

    s = build(cards, ["Mesmeric Sliver", "Mistform Sliver"])
    put(s, "Mesmeric Sliver")
    library = list(s.state.zones["p2:library"])
    other = to_hand(s, "Mistform Sliver")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=other.id)  # another Sliver: it has the ability as it enters (613.1f)
    seen = []
    for _ in range(12):
        until(s, lambda s: s.state.rules.decision is not None or not s.state.zones.get("stack"))
        d = s.state.rules.decision
        if d is None:
            break
        assert d.player == "p1"  # only the fatesealing player is asked (and sees the card)
        seen.append(d.kind)
        ids = [o.id for o in d.options]
        if d.kind == "confirm":
            pick = ["yes"]
        elif library[0] in ids:
            pick = [library[0]] if bottom else []
        else:
            pick = ids[: max(1, d.min_choices)]
        act(s, "p1", type="choose", decision_id=d.id, option_ids=pick)
    assert s.state.zones["p2:library"] == (library[1:] + library[:1] if bottom else library)  # 701.29a
    check(s)


# -- rule-modifying statics -------------------------------------------------------------------------------------------------
def p2_priority(s):
    act(s, "p2", type="set_prefs", full_control=True)
    act(s, "p1", type="pass_priority")  # (Alice passes in her main phase: Bob has priority, 117.3d)
    assert s.state.rules.priority == "p2"


def test_gruul_spellbreaker_shields_you_and_itself_during_your_turn_only(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, ["Gruul Spellbreaker"], ["Lightning Bolt"])
    breaker = put(s, "Gruul Spellbreaker")
    bolt = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    p2_priority(s)
    for target in ("p1", breaker.id):  # 702.11c / 702.11b: not by an opponent's spell during your turn
        with pytest.raises(ActionError):
            act(s, "p2", type="cast_spell", card_id=bolt.id, targets=[target])
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    life = s.state.players["p1"].life
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
    settle(s)
    assert s.state.players["p1"].life == life - 3  # (Bob's turn: no hexproof)
    check(s)


def test_experimental_frenzy_bars_the_hand_but_not_the_library_top(cards):
    s = build(cards, ["Experimental Frenzy", "Grizzly Bears"])
    put(s, "Experimental Frenzy")
    bears = to_hand(s, "Grizzly Bears")
    in_hand = to_hand(s, "Forest")
    mana(s, G=2)
    with pytest.raises(ActionError, match="Experimental Frenzy"):
        act(s, "p1", type="cast_spell", card_id=bears.id)  # 601.3
    with pytest.raises(ActionError, match="Experimental Frenzy"):
        act(s, "p1", type="play_land", card_id=in_hand.id)  # 305.1
    top = s.state.zones["p1:library"][0]
    assert s.state.cards[top].name == "Forest"
    act(s, "p1", type="play_land", card_id=top)  # (the top of the library: its own permission)
    assert zone(s, s.state.cards[top]) == "p1:battlefield" and zone(s, bears) == "p1:hand"
    check(s)


def test_city_of_solitude_stops_spells_and_mana_abilities_on_other_turns(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, ["City of Solitude", "Llanowar Elves"], ["Lightning Bolt"])
    put(s, "City of Solitude")
    elves = put(s, "Llanowar Elves")
    island = card_named(s, "Island", "p2")
    act(s, "p2", type="move", card_ids=[island.id], to={"player": "p2", "zone": "battlefield"})
    bolt = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    p2_priority(s)
    with pytest.raises(ActionError, match="City of Solitude"):
        act(s, "p2", type="cast_spell", card_id=bolt.id, targets=[elves.id])  # 601.3: not Bob's turn
    with pytest.raises(ActionError, match="City of Solitude"):
        act(s, "p2", type="activate_ability", card_id=island.id, ability=0)  # a mana ability too (ruling 2009-10-01)
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    act(s, "p2", type="activate_ability", card_id=island.id, ability=0)  # his own turn
    assert s.state.cards[island.id].tapped
    mana(s, "p2", R=1)
    act(s, "p1", type="set_prefs", full_control=True)
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=[elves.id])
    from tests.test_rules_wave34b_activated import priority_to

    priority_to(s, "p1")
    assert s.state.zones.get("stack")  # (the Bolt is still on the stack, with Alice holding priority)
    with pytest.raises(ActionError, match="City of Solitude"):
        act(s, "p1", type="activate_ability", card_id=elves.id, ability=0)  # (Alice's elf, on Bob's turn)
    settle(s)
    assert zone(s, elves) == "p1:graveyard"
    check(s)


def test_melting_takes_snow_away_from_every_land(cards):
    s = build(cards, ["Melting", "Snow-Covered Forest"], ["Snow-Covered Forest"])
    mine, theirs = put(s, "Snow-Covered Forest"), put(s, "Snow-Covered Forest", "p2")
    assert "Snow" in derived(s, mine).supertypes
    put(s, "Melting")
    for land in (mine, theirs):
        ch = derived(s, land)
        assert "Snow" not in ch.supertypes and "Basic" in ch.supertypes and "Forest" in ch.subtypes  # 205.4: only snow goes
    check(s)


def test_dream_leash_targets_only_a_tapped_permanent_as_it_is_cast(cards):
    s = build(cards, ["Dream Leash"], ["Sol Ring"])
    ring = put(s, "Sol Ring", "p2")
    leash = to_hand(s, "Dream Leash")
    mana(s, U=2, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=leash.id, targets=[ring.id])  # 601.2c: untapped
    act(s, "p2", type="tap", card_ids=[ring.id], tapped=True)
    act(s, "p1", type="cast_spell", card_id=leash.id, targets=[ring.id])
    settle(s)
    assert s.state.cards[leash.id].attached_to == ring.id and s.state.cards[ring.id].controller == "p1"
    check(s)


def test_enthralling_hold_still_resolves_if_its_target_untaps(cards):
    s = build(cards, ["Enthralling Hold"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    act(s, "p2", type="tap", card_ids=[bears.id], tapped=True)
    hold = to_hand(s, "Enthralling Hold")
    mana(s, U=2, C=3)
    act(s, "p1", type="cast_spell", card_id=hold.id, targets=[bears.id])
    act(s, "p2", type="tap", card_ids=[bears.id], tapped=False)  # (ruling 2020-06-23: only the choice as it is cast)
    settle(s)
    assert s.state.cards[hold.id].attached_to == bears.id and s.state.cards[bears.id].controller == "p1"
    check(s)


# -- single cards: named counts, recover, equip costs --------------------------------------------------------------------------
@pytest.mark.parametrize("where", ["graveyard", "battlefield"])
def test_pardic_firecat_counts_as_flame_burst_only_in_a_graveyard(cards, where):
    s = build(cards, ["Pardic Firecat", "Flame Burst"])
    cat = card_named(s, "Pardic Firecat")
    act(s, "p1", type="move", card_ids=[cat.id], to={"player": "p1", "zone": where})
    ogre = token_of(s, "p2", "Ogre", "Token Creature — Ogre", "5/5")
    burst = to_hand(s, "Flame Burst")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=burst.id, targets=[ogre.id])
    settle(s)
    assert s.state.cards[ogre.id].damage == (3 if where == "graveyard" else 2)  # 2 plus the cards named Flame Burst in all graveyards
    check(s)


def test_diligent_farmhand_counts_for_muscle_burst_and_not_for_flame_burst(cards):
    s = build(cards, ["Diligent Farmhand", "Muscle Burst", "Flame Burst"])
    act(s, "p1", type="move", card_ids=[card_named(s, "Diligent Farmhand").id], to={"zone": "graveyard"})
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    muscle = to_hand(s, "Muscle Burst")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=muscle.id, targets=[bear.id])
    settle(s)
    assert pt(s, "Bear") == (6, 6)  # 3 plus the Farmhand (the Muscle Burst itself is still on the stack)
    ogre = token_of(s, "p2", "Ogre", "Token Creature — Ogre", "5/5")
    flame = to_hand(s, "Flame Burst")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=flame.id, targets=[ogre.id])
    settle(s)
    assert s.state.cards[ogre.id].damage == 2  # (it counts only for spells named Muscle Burst)
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_garzas_assassin_recovers_for_half_your_life(cards, pay):
    from tests.test_rules_conditionals import until

    s = build(cards, ["Garza's Assassin", "Murder", "Grizzly Bears"])
    assassin = card_named(s, "Garza's Assassin")
    act(s, "p1", type="move", card_ids=[assassin.id], to={"zone": "graveyard"})
    bears = put(s, "Grizzly Bears")
    set_life(s, "p1", 25)
    murder = to_hand(s, "Murder")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[bears.id])
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.player == "p1"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay" if pay else next(o.id for o in d.options if o.id != "pay")])
    settle(s)
    if pay:  # 119.4: half of 25, rounded up
        assert s.state.players["p1"].life == 12 and zone(s, assassin) == "p1:hand"
    else:  # 702.59a: otherwise, exile this card
        assert s.state.players["p1"].life == 25 and zone(s, assassin) == "p1:exile"
    check(s)


def test_robe_of_the_archmagi_cheap_equip_needs_a_shaman_warlock_or_wizard(cards):
    s = build(cards, ["Robe of the Archmagi"])
    robe = put(s, "Robe of the Archmagi")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    warlock = token_of(s, "p1", "Warlock", "Token Creature — Human Warlock", "1/1")
    mana(s, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=robe.id, ability=2, targets=[bear.id])  # 702.6b: only that quality
    act(s, "p1", type="activate_ability", card_id=robe.id, ability=2, targets=[warlock.id])
    settle(s)
    assert attached(s, robe) == warlock.id
    equip(s, robe, 1, bear, C=4)  # Equip {4}: any creature you control
    assert attached(s, robe) == bear.id
    check(s)


def test_my_precious_equip_costs_two_and_two_life(cards):
    s = build(cards, ["My Precious // Allure of Power"])
    precious = put(s, "My Precious // Allure of Power")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    life = s.state.players["p1"].life
    equip(s, precious, 1, bear, C=2)
    assert attached(s, precious) == bear.id and s.state.players["p1"].life == life - 2  # 702.6a: both parts paid
    ch = derived(s, bear)
    assert "hexproof" in ch.keywords
    check(s)


def test_ajani_goldmane_avatar_is_your_life_total(cards):
    s = build(cards, ["Ajani Goldmane"])
    ajani = walker(s, "Ajani Goldmane", 6)
    set_life(s, "p1", 23)
    loyal(s, ajani, 2)
    assert pt(s, "Avatar") == (23, 23)  # 604.3: its own characteristic-defining ability
    set_life(s, "p1", 9)
    assert pt(s, "Avatar") == (9, 9)  # (ruling 2007-10-01: it changes as your life total does)
    check(s)


def test_elsewhere_flask_sets_the_type_of_each_land_you_control(cards):
    s = build(cards, ["Elsewhere Flask"])
    flask = put(s, "Elsewhere Flask")
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:2]
    act(s, "p1", type="move", card_ids=[f.id for f in forests], to={"player": "p1", "zone": "battlefield"})
    island = card_named(s, "Island", "p2")
    act(s, "p2", type="move", card_ids=[island.id], to={"player": "p2", "zone": "battlefield"})
    act(s, "p1", type="activate_ability", card_id=flask.id, ability=1)
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.rules.decision is not None)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["Swamp"])
    settle(s)
    for f in forests:  # 305.7: the land type set (rulings 2008-05-01: still basic, still named Forest)
        ch = derived(s, f)
        assert set(ch.subtypes) == {"Swamp"} and "Basic" in ch.supertypes and ch.name == "Forest"
    assert set(derived(s, island).subtypes) == {"Island"}  # (only yours)
    check(s)


def test_dragon_turtle_keeps_both_tapped_through_their_controllers_next_untap_steps(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, ["Dragon Turtle"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    turtle = to_hand(s, "Dragon Turtle")
    mana(s, U=2, C=1)
    act(s, "p1", type="cast_spell", card_id=turtle.id)
    settle(s)
    assert s.state.cards[turtle.id].tapped and s.state.cards[bears.id].tapped
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    assert s.state.cards[bears.id].tapped  # 502.3: Bob's next untap step skipped for it
    until(s, lambda s: s.state.turn.active_player == "p1" and s.state.turn.phase == "main1")
    assert s.state.cards[turtle.id].tapped  # Alice's own next untap step
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    assert not s.state.cards[bears.id].tapped
    check(s)


def test_blue_dragon_three_different_targets_until_your_next_turn(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, ["Blue Dragon"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    ogre = token_of(s, "p2", "Ogre", "Token Creature — Ogre", "5/5")
    mine = token_of(s, "p1", "Elk", "Token Creature — Elk", "3/3")
    dragon = to_hand(s, "Blue Dragon")
    mana(s, U=2, C=5)
    act(s, "p1", type="cast_spell", card_id=dragon.id)
    for pick in (bears, ogre, mine):
        until(s, lambda s: s.state.rules.decision is not None)
        d = s.state.rules.decision
        if pick is not bears:
            assert bears.id not in {o.id for o in d.options}  # "other": not the same creature again (ruling 2021-07-23)
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[pick.id])
    settle(s)
    assert (pt(s, "Grizzly Bears", "p2"), pt(s, "Ogre", "p2"), pt(s, "Elk")) == ((-1, 2), (3, 5), (2, 3))
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    assert pt(s, "Ogre", "p2") == (3, 5)  # (through Bob's turn)
    until(s, lambda s: s.state.turn.active_player == "p1" and s.state.turn.phase == "main1")
    assert pt(s, "Ogre", "p2") == (5, 5)
    check(s)


@pytest.mark.parametrize("n", [10, 11])
def test_legate_lanius_decimates_rounded_up(cards, n):
    s = build(cards, ["Legate Lanius, Caesar's Ace"])
    for i in range(n):
        token_of(s, "p2", f"Soldier {i}", "Token Creature — Soldier", "1/1")
    lanius = to_hand(s, "Legate Lanius, Caesar's Ace")
    mana(s, B=1, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=lanius.id)
    for _ in range(10):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: d.min_choices or 1])
    left = sum(1 for c in s.state.cards.values() if c.zone == "p2:battlefield" and c.name.startswith("Soldier"))
    assert left == n - (1 if n == 10 else 2)  # one to ten: 1; eleven to twenty: 2 (ruling 2024-03-08)
    assert s.state.cards[lanius.id].counters.get("+1/+1") == (1 if n == 10 else 2)
    check(s)


def test_serra_avenger_waits_for_your_fourth_turn(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, ["Serra Avenger"])
    angel = to_hand(s, "Serra Avenger")
    mana(s, W=2)
    with pytest.raises(ActionError, match="first, second, or third"):
        act(s, "p1", type="cast_spell", card_id=angel.id)  # 601.3: Alice's first turn
    until(s, lambda s: s.state.turn.active_player == "p1" and s.state.turn.phase == "main1" and s.state.turn.number == 7)
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=angel.id)  # her fourth turn
    settle(s)
    assert zone(s, angel) == "p1:battlefield"
    check(s)


def test_karlov_watchdog_keeps_their_morphs_down_during_your_turn(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, ["Karlov Watchdog"], ["Exalted Angel"])
    put(s, "Karlov Watchdog")
    angel = card_named(s, "Exalted Angel", "p2")
    act(s, "p2", type="move", card_ids=[angel.id], to={"player": "p2", "zone": "battlefield"}, face_down=True, face_down_kind="morph")
    mana(s, "p2", W=2, C=2)
    p2_priority(s)
    with pytest.raises(ActionError, match="Karlov Watchdog"):
        act(s, "p2", type="turn_face_up", card_id=angel.id)  # 702.37e (ruling 2024-02-02)
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    mana(s, "p2", W=2, C=2)
    act(s, "p2", type="turn_face_up", card_id=angel.id)  # (Bob's own turn)
    assert not s.state.cards[angel.id].face_down
    check(s)


def test_everlasting_torment_turns_damage_into_minus_counters(cards):
    s = build(cards, ["Everlasting Torment", "Lightning Bolt"])
    put(s, "Everlasting Torment")
    ogre = token_of(s, "p2", "Ogre", "Token Creature — Ogre", "5/5")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[ogre.id])
    settle(s)
    o = s.state.cards[ogre.id]
    assert o.damage == 0 and o.counters.get("-1/-1") == 3 and pt(s, "Ogre", "p2") == (2, 2)  # 702.80a, 120.3d
    check(s)


def test_archon_of_the_wild_rose_sets_your_enchanted_creatures(cards):
    s = build(cards, ["Archon of the Wild Rose", "Pacifism"], ["Pacifism"])
    put(s, "Archon of the Wild Rose")
    mine = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    theirs = token_of(s, "p1", "Elk", "Token Creature — Elk", "1/1")
    token_of(s, "p1", "Ox", "Token Creature — Ox", "3/3")
    for aura, host, pid in ((card_named(s, "Pacifism"), mine, "p1"), (card_named(s, "Pacifism", "p2"), theirs, "p2")):
        act(s, pid, type="move", card_ids=[aura.id], to={"player": pid, "zone": "battlefield"})
        act(s, pid, type="attach", card_ids=[aura.id], to=host.id)
    assert pt(s, "Bear") == (4, 4) and "flying" in derived(s, mine).keywords  # 613.4b, 613.1f
    assert pt(s, "Elk") == (1, 1) and pt(s, "Ox") == (3, 3)  # (an opponent's Aura, no Aura: unchanged)
    check(s)


def test_urza_activates_loyalty_abilities_twice_each_turn(cards):
    s = build(cards, ["Urza, Planeswalker"])
    urza = walker(s, "Urza, Planeswalker", 7)
    loyal(s, urza, 3)  # 0: two Soldiers
    loyal(s, urza, 2)  # +1 (606.3, changed)
    d = s.state.rules.decision
    if d is not None:  # (the discard)
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: d.min_choices or 1])
        settle(s)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=urza.id, ability=3)  # (only twice)
    assert sum(1 for c in s.state.cards.values() if c.name == "Soldier") == 2 and s.state.cards[urza.id].counters.get("loyalty") == 8
    check(s)


def test_invert_switches_each_of_two_targets(cards):
    s = build(cards, ["Invert // Invent"])
    ogre = token_of(s, "p2", "Ogre", "Token Creature — Ogre", "1/4")
    elk = token_of(s, "p1", "Elk", "Token Creature — Elk", "3/2")
    invert = to_hand(s, "Invert // Invent")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=invert.id, face=0, targets=[ogre.id, elk.id], target_counts=[2])
    settle(s)
    assert pt(s, "Ogre", "p2") == (4, 1) and pt(s, "Elk") == (2, 3)  # 613.4d, each its own (ruling 2018-10-05)
    check(s)


def test_enhanced_surveillance_looks_at_two_more(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, ["Enhanced Surveillance", "Consider"])
    put(s, "Enhanced Surveillance")
    spell = to_hand(s, "Consider")
    top = list(s.state.zones["p1:library"][:3])
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.player == "p1" and [o.id for o in d.options] == top  # surveil 1 plus two (701.25a)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=top[:2])
    settle(s)
    assert all(zone(s, s.state.cards[c]) == "p1:graveyard" for c in top[:2])
    check(s)


def test_cosmos_charger_foretells_for_one_on_another_turn(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, ["Cosmos Charger", "Doomskar Oracle"])
    put(s, "Cosmos Charger")
    oracle = to_hand(s, "Doomskar Oracle")
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    act(s, "p1", type="set_prefs", full_control=True)
    act(s, "p2", type="pass_priority")
    assert s.state.rules.priority == "p1"
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=oracle.id, ability=1)  # 702.143a: {2} less {1}, on Bob's turn
    settle(s)
    assert zone(s, oracle) == "p1:foretell"  # (one mana was enough)
    check(s)


def test_carth_adds_one_to_each_loyalty_cost(cards):
    s = build(cards, ["Carth the Lion", "Ajani Goldmane", "Ajani Unrelenting"])
    put(s, "Carth the Lion")
    for _ in range(5):  # (its enters trigger: take nothing)
        settle(s)
        if (d := s.state.rules.decision) is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: d.min_choices])
    goldmane, unrelenting = walker(s, "Ajani Goldmane", 4), walker(s, "Ajani Unrelenting", 5)
    loyal(s, goldmane, 1)  # [-1] becomes [0] (ruling 2021-06-18)
    loyal(s, unrelenting, 1)  # [+1] becomes [+2]
    assert s.state.cards[goldmane.id].counters.get("loyalty") == 4 and s.state.cards[unrelenting.id].counters.get("loyalty") == 7
    check(s)


def test_dusk_mangler_one_of_three_additional_costs(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, ["Dusk Mangler"], ["Grizzly Bears"])
    put(s, "Grizzly Bears", "p2")
    token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    to_hand(s, "Forest")  # (each way payable)
    mangler = to_hand(s, "Dusk Mangler")
    mana(s, B=2, C=5)
    life = s.state.players["p1"].life
    act(s, "p1", type="cast_spell", card_id=mangler.id)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.player == "p1" and len(d.options) == 3  # 601.2b: the three ways, one chosen (118.8)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if "life" in o.label.lower())])
    for _ in range(10):
        settle(s)
        if (d := s.state.rules.decision) is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: d.min_choices or 1])
    assert s.state.players["p1"].life == life - 4 and zone(s, mangler) == "p1:battlefield"
    check(s)


def test_urborg_lhurgoyf_mills_three_for_each_kick_as_it_enters(cards):
    s = build(cards, ["Urborg Lhurgoyf"])
    goyf = to_hand(s, "Urborg Lhurgoyf")
    before = len(s.state.zones["p1:library"])
    mana(s, G=1, C=1, U=1, B=1)
    act(s, "p1", type="cast_spell", card_id=goyf.id, kicker=3)  # 702.33b: both kicker costs
    settle(s)
    assert zone(s, goyf) == "p1:battlefield" and len(s.state.zones["p1:library"]) == before - 6  # 614.12, 701.17a
    check(s)


def test_hogaak_is_paid_only_by_convoke_and_delve(cards):
    s = build(cards, ["Hogaak, Arisen Necropolis"])
    hogaak = to_hand(s, "Hogaak, Arisen Necropolis")
    elves = [token_of(s, "p1", f"Elf {i}", "Token Creature — Elf", "1/1", colors=["G"]) for i in range(5)]
    mana(s, G=2)
    with pytest.raises(ActionError, match="spend mana"):
        act(s, "p1", type="cast_spell", card_id=hogaak.id, contributions=[{"kind": "convoke", "card": e.id} for e in elves[:5]])  # (two mana left to pay)
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:2]
    act(s, "p1", type="move", card_ids=[f.id for f in forests], to={"zone": "graveyard"})
    paid = [{"kind": "convoke", "card": e.id} for e in elves[:5]] + [{"kind": "delve", "card": f.id} for f in forests]
    act(s, "p1", type="cast_spell", card_id=hogaak.id, contributions=paid)
    settle(s)
    assert zone(s, hogaak) == "p1:battlefield"
    check(s)


def test_sanctum_lurker_keeps_planeswalkers_with_no_loyalty(cards):
    s = build(cards, ["Sanctum Lurker", "Ajani Goldmane"], ["Ajani Goldmane"])
    lurker = put(s, "Sanctum Lurker")
    settle(s)
    mine = walker(s, "Ajani Goldmane", 0)
    theirs = put(s, "Ajani Goldmane", "p2")
    act(s, "p2", type="set_counter", card_id=theirs.id, kind="loyalty", value=0)
    sba_check(s)
    assert zone(s, mine) == "p1:battlefield" and zone(s, theirs) == "p2:graveyard"  # 704.5i (only yours)
    act(s, "p1", type="move", card_ids=[lurker.id], to={"zone": "graveyard"})
    sba_check(s)
    assert zone(s, mine) == "p1:graveyard"
    check(s)


@pytest.mark.parametrize("name,most,pay", [("Minion of the Wastes", 40, 7), ("Nameless Race", 2, 2)])
def test_life_paid_as_it_enters_sets_power_and_toughness(cards, name, most, pay):
    from tests.test_rules_conditionals import until

    s = build(cards, [name], ["Pacifism", "Archon of the Wild Rose"])
    put(s, "Archon of the Wild Rose", "p2")
    token_of(s, "p2", "Knight", "Token Creature — Knight", "2/2", colors=["W"])  # (a token isn't counted)
    act(s, "p2", type="move", card_ids=[card_named(s, "Pacifism", "p2").id], to={"zone": "graveyard"})  # (a white card in their graveyard)
    creature = to_hand(s, name)
    mana(s, B=3, C=3)
    act(s, "p1", type="cast_spell", card_id=creature.id)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.player == "p1" and [o.id for o in d.options] == [str(n) for n in range(most + 1)]  # 119.4 (Nameless Race: the Archon and the Pacifism)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[str(pay)])
    settle(s)
    assert s.state.players["p1"].life == 40 - pay and pt(s, name) == (pay, pay)  # 604.3
    check(s)

