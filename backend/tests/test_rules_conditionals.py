"""Conditional and "instead" clauses (CR 608.2c, 608.2h, 608.2i, 603.4, 614.1a): app/rules/conditions.py,
app/rules/history.py, the sentence forms of app/rules/scripts.py ("If C, X.", "X. If C, Y instead.",
"If C, X. Otherwise, Z.", "X if C.", "X unless C.", "X unless [you / they] discard / sacrifice / return …").

Every scenario uses real Commander-legal cards' current Oracle wording (the card named in the comment;
spells and creatures are added to the fixture database below, abilities that only need a permanent are
tokens with the card's exact text) and checks that replaying the recorded history reproduces the table.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import conditions, coverage, effects, history, scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, find, turn_on, zone
from tests.test_rules_attachments import ch, named, token
from tests.test_rules_delayed import reloaded
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches

# Real Oracle wording (Scryfall, current), one line per card: the test cards of this module.
EXTRA = [
    card("Life Goes On", set_code="tst", number="W919", mana_cost="{G}", cmc=1.0, type_line="Instant",
         oracle_text="You gain 4 life. If a creature died this turn, you gain 8 life instead.", colors=["G"], color_identity=["G"]),
    card("Lightning Dart", set_code="tst", number="W994", mana_cost="{1}{R}", cmc=2.0, type_line="Instant",
         oracle_text="Lightning Dart deals 1 damage to target creature. If that creature is white or blue, Lightning Dart deals 4 damage to it instead.",
         colors=["R"], color_identity=["R"]),
    card("Death's Caress", set_code="tst", number="W773", mana_cost="{3}{B}{B}", cmc=5.0, type_line="Sorcery",
         oracle_text="Destroy target creature. If that creature was a Human, you gain life equal to its toughness.", colors=["B"],
         color_identity=["B"]),
    card("Martial Coup", set_code="tst", number="W371", mana_cost="{X}{W}{W}", cmc=2.0, type_line="Sorcery",
         oracle_text="Create X 1/1 white Soldier creature tokens. If X is 5 or more, destroy all other creatures.", colors=["W"],
         color_identity=["W"]),
    card("Blot Out the Sky", set_code="tst", number="W471", mana_cost="{X}{W}{B}", cmc=2.0, type_line="Sorcery",
         oracle_text="Create X tapped 2/1 white and black Inkling creature tokens with flying. If X is 6 or more, destroy all noncreature, nonland permanents.",
         colors=["B", "W"], color_identity=["B", "W"]),
    card("Mardu Hordechief", set_code="tst", number="W885", mana_cost="{2}{W}", cmc=3.0, type_line="Creature — Human Warrior",
         oracle_text="Raid — When this creature enters, if you attacked this turn, create a 1/1 white Warrior creature token.",
         power="2", toughness="3", colors=["W"], color_identity=["W"], keywords=["Raid"]),
    card("Bone Picker", set_code="tst", number="W425", mana_cost="{3}{B}", cmc=4.0, type_line="Creature — Bird",
         oracle_text="This spell costs {3} less to cast if a creature died this turn.\nFlying, deathtouch", power="3", toughness="2",
         colors=["B"], color_identity=["B"], keywords=["Deathtouch", "Flying"]),
    card("Airdrop Aeronauts", set_code="tst", number="W866", mana_cost="{3}{W}{W}", cmc=5.0, type_line="Creature — Dwarf Scout",
         oracle_text="Flying\nRevolt — When this creature enters, if a permanent left the battlefield under your control this turn, you gain 5 life.",
         power="4", toughness="3", colors=["W"], color_identity=["W"], keywords=["Flying", "Revolt"]),
    card("Gravelighter", set_code="tst", number="W206", mana_cost="{2}{B}", cmc=3.0, type_line="Creature — Spirit",
         oracle_text="Flying\nWhen this creature enters, draw a card if a creature died this turn. Otherwise, each player sacrifices a creature of their choice.",
         power="2", toughness="2", colors=["B"], color_identity=["B"], keywords=["Flying"]),
    card("Fathom Fleet Boarder", set_code="tst", number="W115", mana_cost="{2}{B}", cmc=3.0, type_line="Creature — Orc Pirate",
         oracle_text="When this creature enters, you lose 2 life unless you control another Pirate.", power="3", toughness="3",
         colors=["B"], color_identity=["B"]),
    card("Coiling Oracle", set_code="tst", number="W830", mana_cost="{G}{U}", cmc=2.0, type_line="Creature — Snake Elf Druid",
         oracle_text="When this creature enters, reveal the top card of your library. If it's a land card, put it onto the battlefield. Otherwise, put that card into your hand.",
         power="1", toughness="1", colors=["G", "U"], color_identity=["G", "U"]),
    card("Scythe Tiger", set_code="tst", number="W186", mana_cost="{G}", cmc=1.0, type_line="Creature — Cat",
         oracle_text="Shroud (This creature can't be the target of spells or abilities.)\nWhen this creature enters, sacrifice it unless you sacrifice a land.",
         power="3", toughness="2", colors=["G"], color_identity=["G"], keywords=["Shroud"]),
    card("Masticore", set_code="tst", number="W638", mana_cost="{4}", cmc=4.0, type_line="Artifact Creature — Masticore",
         oracle_text="At the beginning of your upkeep, sacrifice this creature unless you discard a card.\n{2}: This creature deals 1 damage to target creature.\n{2}: Regenerate this creature.",
         power="4", toughness="4", colors=[], color_identity=[], keywords=["Regenerate"]),
    card("Stolen Vitality", set_code="tst", number="W639", mana_cost="{1}{R}", cmc=2.0, type_line="Instant",
         oracle_text="Target creature gets +3/+1 until end of turn. If it's your turn, that creature gains trample until end of turn. Otherwise, it gains first strike until end of turn.",
         colors=["R"], color_identity=["R"]),
    card("Linvala, the Preserver", set_code="tst", number="W839", mana_cost="{4}{W}{W}", cmc=6.0, type_line="Legendary Creature — Angel",
         oracle_text="Flying\nWhen Linvala enters, if an opponent has more life than you, you gain 5 life.\nWhen Linvala enters, if an opponent controls more creatures than you, create a 3/3 white Angel creature token with flying.",
         power="5", toughness="5", colors=["W"], color_identity=["W"], keywords=["Flying"]),
    card("Loyal Drake", set_code="tst", number="W188", mana_cost="{2}{U}", cmc=3.0, type_line="Creature — Drake",
         oracle_text="Flying\nLieutenant — At the beginning of combat on your turn, if you control your commander, draw a card.",
         power="2", toughness="2", colors=["U"], color_identity=["U"], keywords=["Flying", "Lieutenant"]),
    card("Sphinx Sovereign", set_code="tst", number="W908", mana_cost="{4}{W}{U}{U}{B}", cmc=8.0, type_line="Artifact Creature — Sphinx",
         oracle_text="Flying\nAt the beginning of your end step, you gain 3 life if this creature is untapped. Otherwise, each opponent loses 3 life.",
         power="6", toughness="6", colors=["B", "U", "W"], color_identity=["B", "U", "W"], keywords=["Flying"]),
    card("Scavenging Ooze", set_code="tst", number="W510", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Ooze",
         oracle_text="{G}: Exile target card from a graveyard. If it was a creature card, put a +1/+1 counter on this creature and you gain 1 life.",
         power="2", toughness="2", colors=["G"], color_identity=["G"]),
    card("Holy Justiciar", set_code="tst", number="W410", mana_cost="{3}{W}", cmc=4.0, type_line="Creature — Human Cleric",
         oracle_text="{2}{W}, {T}: Tap target creature. If that creature is a Zombie, exile it.", power="2", toughness="1",
         colors=["W"], color_identity=["W"]),
    card("Bontu the Glorified", set_code="tst", number="W771", mana_cost="{2}{B}", cmc=3.0, type_line="Legendary Creature — God",
         oracle_text="Menace, indestructible\nBontu can't attack or block unless a creature died under your control this turn.\n{1}{B}, Sacrifice another creature: Scry 1. Each opponent loses 1 life and you gain 1 life.",
         power="4", toughness="6", colors=["B"], color_identity=["B"], keywords=["Indestructible", "Menace", "Scry"]),
    card("Painful Quandary", set_code="tst", number="W610", mana_cost="{3}{B}{B}", cmc=5.0, type_line="Enchantment",
         oracle_text="Whenever an opponent casts a spell, that player loses 5 life unless they discard a card.", colors=["B"],
         color_identity=["B"]),
    card("Spelltithe Enforcer", set_code="tst", number="W656", mana_cost="{3}{W}{W}", cmc=5.0, type_line="Creature — Elephant Wizard",
         oracle_text="Whenever an opponent casts a spell, that player sacrifices a permanent of their choice unless they pay {1}.",
         power="3", toughness="3", colors=["W"], color_identity=["W"]),
    card("For the Family", set_code="tst", number="W768", mana_cost="{G}", cmc=1.0, type_line="Instant",
         oracle_text="Target creature gets +2/+2 until end of turn. If you control four or more creatures, that creature gets +4/+4 until end of turn instead.",
         colors=["G"], color_identity=["G"]),
    card("Cinderclasm", set_code="tst", number="W538", mana_cost="{1}{R}", cmc=2.0, type_line="Instant",
         oracle_text="Kicker {R} (You may pay an additional {R} as you cast this spell.)\nCinderclasm deals 1 damage to each creature. If it was kicked, it deals 2 damage to each creature instead.",
         colors=["R"], color_identity=["R"], keywords=["Kicker"]),
    card("Arrogant Outlaw", set_code="tst", number="W238", mana_cost="{2}{B}", cmc=3.0, type_line="Creature — Vampire Noble",
         oracle_text="When this creature enters, if an opponent lost life this turn, each opponent loses 2 life and you gain 2 life.",
         power="3", toughness="2", colors=["B"], color_identity=["B"]),
    card("Lava Coil", set_code="tst", number="W917", mana_cost="{1}{R}", cmc=2.0, type_line="Sorcery",
         oracle_text="Lava Coil deals 4 damage to target creature. If that creature would die this turn, exile it instead.", colors=["R"],
         color_identity=["R"]),
    card("Soul Swallower", set_code="tst", number="W148", mana_cost="{2}{G}{G}", cmc=4.0, type_line="Creature — Wurm",
         oracle_text="Trample\nDelirium — At the beginning of your upkeep, if there are four or more card types among cards in your graveyard, put three +1/+1 counters on this creature.",
         power="3", toughness="3", colors=["G"], color_identity=["G"], keywords=["Delirium", "Trample"]),
    card("Hidden Guerrillas", set_code="tst", number="W515", mana_cost="{G}", cmc=1.0, type_line="Enchantment",
         oracle_text="When an opponent casts an artifact spell, if this permanent is an enchantment, it becomes a 5/3 Soldier creature with trample.",
         colors=["G"], color_identity=["G"]),
    card("Overgrowth Elemental", set_code="tst", number="W340", mana_cost="{2}{G}", cmc=3.0, type_line="Creature — Elemental",
         oracle_text="When this creature enters, put a +1/+1 counter on another target Elemental you control.\nWhenever another creature you control dies, you gain 1 life. If that creature was an Elemental, put a +1/+1 counter on this creature.",
         power="3", toughness="2", colors=["G"], color_identity=["G"]),
    card("Elder Cathar", set_code="tst", number="W250", mana_cost="{2}{W}", cmc=3.0, type_line="Creature — Human Soldier",
         oracle_text="When this creature dies, put a +1/+1 counter on target creature you control. If that creature is a Human, put two +1/+1 counters on it instead.",
         power="2", toughness="2", colors=["W"], color_identity=["W"]),
    card("Tribute to the World Tree", set_code="tst", number="W354", mana_cost="{G}{G}{G}", cmc=3.0, type_line="Enchantment",
         oracle_text="Whenever a creature you control enters, draw a card if its power is 3 or greater. Otherwise, put two +1/+1 counters on it.",
         colors=["G"], color_identity=["G"]),
    card("Arch of Orazca", set_code="tst", number="W601", type_line="Land",
         oracle_text="Ascend (If you control ten or more permanents, you get the city's blessing for the rest of the game.)\n{T}: Add {C}.\n{5}, {T}: Draw a card. Activate only if you have the city's blessing.",
         keywords=["Ascend"]),
    card("Ghost Town", set_code="tst", number="W602", type_line="Land",
         oracle_text="{T}: Add {C}.\n{0}: Return this land to its owner's hand. Activate only if it's not your turn."),
    card("Desert", set_code="tst", number="W603", type_line="Land — Desert",
         oracle_text="{T}: Add {C}.\n{T}: This land deals 1 damage to target attacking creature. Activate only during the end of combat step."),
    card("Kami of Terrible Secrets", set_code="tst", number="W604", mana_cost="{3}{B}", cmc=4.0, type_line="Creature — Spirit",
         oracle_text="When this creature enters, if you control an artifact and an enchantment, you draw a card and you gain 1 life.",
         power="3", toughness="4", colors=["B"], color_identity=["B"]),
    card("Galvanize", set_code="tst", number="W605", mana_cost="{1}{R}", cmc=2.0, type_line="Instant",
         oracle_text="Galvanize deals 3 damage to target creature. If you've drawn two or more cards this turn, Galvanize deals 5 damage to that creature instead.",
         colors=["R"], color_identity=["R"]),
    card("Tragic Banshee", set_code="tst", number="W606", mana_cost="{4}{B}", cmc=5.0, type_line="Creature — Spirit",
         oracle_text="Morbid — When this creature enters, target creature an opponent controls gets -1/-1 until end of turn. If a creature died this turn, that creature gets -13/-13 until end of turn instead.",
         power="5", toughness="3", colors=["B"], color_identity=["B"], keywords=["Morbid"]),
    card("Gangrenous Zombies", set_code="tst", number="W607", mana_cost="{1}{B}{B}", cmc=3.0, type_line="Creature — Zombie",
         oracle_text="{T}, Sacrifice this creature: This creature deals 1 damage to each creature and each player. If you control a snow Swamp, this creature deals 2 damage to each creature and each player instead.",
         power="2", toughness="2", colors=["B"], color_identity=["B"]),
    card("Tawnos's Tinkering", set_code="tst", number="W608", mana_cost="{3}{G}", cmc=4.0, type_line="Instant",
         oracle_text="Put two +1/+1 counters on target artifact, creature, or land you control. Untap that permanent. If it isn't a creature, it becomes a 0/0 creature in addition to its other types.",
         colors=["G"], color_identity=["G"]),
    card("Extinguish the Light", set_code="tst", number="W609", mana_cost="{2}{B}{B}", cmc=4.0, type_line="Instant",
         oracle_text="Destroy target creature or planeswalker. If its mana value was 3 or less, you gain 3 life.", colors=["B"],
         color_identity=["B"]),
    card("Demoralize", set_code="tst", number="W610", mana_cost="{2}{R}", cmc=3.0, type_line="Instant",
         oracle_text="All creatures gain menace until end of turn. (They can't be blocked except by two or more creatures.)\nThreshold — If there are seven or more cards in your graveyard, creatures can't block this turn.",
         colors=["R"], color_identity=["R"], keywords=["Threshold"]),
    card("Carrion Imp", set_code="tst", number="W611", mana_cost="{3}{B}", cmc=4.0, type_line="Creature — Imp",
         oracle_text="Flying\nWhen this creature enters, you may exile target creature card from a graveyard. If you do, you gain 2 life.",
         power="2", toughness="3", colors=["B"], color_identity=["B"], keywords=["Flying"]),
    card("Niambi, Esteemed Speaker", set_code="tst", number="W612", mana_cost="{W}{U}", cmc=2.0, type_line="Legendary Creature — Human Cleric",
         oracle_text="Flash\nWhen Niambi enters, you may return another target creature you control to its owner's hand. If you do, you gain life equal to that creature's mana value.\n{1}{W}{U}, {T}, Discard a legendary card: Draw two cards.",
         power="2", toughness="1", colors=["U", "W"], color_identity=["U", "W"], keywords=["Flash"]),
    card("Turntimber Ranger", set_code="tst", number="W613", mana_cost="{3}{G}{G}", cmc=5.0, type_line="Creature — Elf Scout Ranger Ally",
         oracle_text="Whenever this creature or another Ally you control enters, you may create a 2/2 green Wolf creature token. If you do, put a +1/+1 counter on this creature.",
         power="2", toughness="2", colors=["G"], color_identity=["G"]),
    card("Academy Rector", set_code="tst", number="W614", mana_cost="{3}{W}", cmc=4.0, type_line="Creature — Human Cleric",
         oracle_text="When this creature dies, you may exile it. If you do, search your library for an enchantment card, put that card onto the battlefield, then shuffle.",
         power="1", toughness="2", colors=["W"], color_identity=["W"]),
]


@pytest.fixture()
def card_db(settings):
    """The fixture cards plus this module's real-Oracle cards."""
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build(cards, *names, p2=(), extra=()):
    """Alice (p1) and Bob (p2); ``names`` are in Alice's library, ``p2`` in Bob's (Islands fill both)."""
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in p2), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def to_hand(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return c


def on_field(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def life(s, pid="p1"):
    return s.state.players[pid].life


def counters(s, c, kind="+1/+1"):
    return s.state.cards[c.id].counters.get(kind, 0)


def settle(s, limit=30):
    """Let everything on the stack resolve; an order or a choice that comes up is answered with the first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("the stack never emptied")


def cast(s, c, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=c.id, **kw)
    settle(s)


def token_of(s, pid, name, type_line, pt="2/2", text="", colors=()):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid,
        token={"name": name, "type_line": type_line, "power": p, "toughness": t, "text": text, "colors": list(colors)})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def names_on_field(s, pid="p1"):
    return sorted(s.state.cards[c].name for c in zone(s.state, pid, "battlefield"))


# -- the wording (conditions.parse) ----------------------------------------------------------------
def key(phrase):
    from app.rules import selectors

    return selectors.parse(phrase).key()


@pytest.mark.parametrize(("text", "expected"), [
    ("you attacked this turn", {"history": "attacked"}),  # Mardu Hordechief (Raid)
    ("you attacked with a creature this turn", {"history": "attacked"}),
    ("you didn't attack with a creature this turn", {"not": {"history": "attacked"}}),  # Curious Obsession
    ("a creature died this turn", {"history": "died", "who": "any", "n": 1}),  # Bone Picker (Morbid)
    ("a creature died under your control this turn", {"history": "died", "who": "you", "n": 1}),  # Essenceknit Scholar
    ("three or more creatures died this turn", {"history": "died", "who": "any", "n": 3}),  # Inga Rune-Eyes
    ("a permanent left the battlefield under your control this turn", {"history": "left", "who": "you"}),  # Airdrop Aeronauts
    ("a permanent you controlled left the battlefield this turn", {"history": "left", "who": "you"}),  # Lulu, Loyal Hollyphant
    ("you gained life this turn", {"history": "gained", "n": 1}),  # Mortality Spear
    ("you've gained 3 or more life this turn", {"history": "gained", "n": 3}),  # Haliya, Guided by Light
    ("an opponent lost life this turn", {"history": "lost", "who": "opponent", "n": 1}),  # Arrogant Outlaw
    ("a player lost 4 or more life this turn", {"history": "lost", "who": "any", "n": 4}),  # Knight of the Ebon Legion
    ("you lost life last turn", {"history": "lost", "who": "you", "n": 1, "last": True}),  # First Response
    ("you've drawn two or more cards this turn", {"history": "drew", "n": 2}),  # Messenger Hawk
    ("you've cast two or more spells this turn", {"history": "spells", "n": 2}),  # Brightspear Zealot
    ("you didn't cast a spell this turn", {"not": {"history": "spells", "n": 1}}),  # Nightpack Ambusher
    ("a card left your graveyard this turn", {"history": "left_graveyard"}),  # Relic Retriever
    ("you descended this turn", {"history": "descended", "n": 1}),  # Deep Goblin Skulltaker (700.11)
    ("it's your turn", {"turn": "yours"}),  # Feed the Cauldron
    ("it's not your turn", {"not": {"turn": "yours"}}),  # Ghost Town
    ("you're the monarch", {"status": "monarch"}),  # Throne Warden
    ("you have the initiative", {"status": "initiative"}),  # Imoen, Mystic Trickster
    ("you have the city's blessing", {"status": "city_blessing"}),  # Mausoleum Harpy
    ("X is 6 or more", {"value": {"x": 1}, "op": ">=", "n": 6}),  # Blot Out the Sky
    ("an opponent has more life than you", {"versus": {"value": {"life": "you"}, "op": ">"}}),  # Linvala, the Preserver
])
def test_parse(text, expected):
    assert conditions.parse(text) == expected


def test_parse_counts_and_compounds():
    from app.rules import selectors

    mine = selectors.Selector(commander=True, controller="you", owner="you").key()  # Loyal Drake (Lieutenant)
    assert conditions.parse("you control your commander") == {"value": {"count": mine}, "op": ">=", "n": 1}
    assert conditions.parse("an opponent controls more lands than you") == {
        "versus": {"value": {"count": key("lands you control")}, "op": ">"}}  # Sunstar Expansionist
    assert conditions.parse("you control an artifact and an enchantment") == {"all": [  # Kami of Terrible Secrets
        {"value": {"count": key("artifact you control")}, "op": ">=", "n": 1},
        {"value": {"count": key("enchantment you control")}, "op": ">=", "n": 1}]}
    assert conditions.parse("you control a Desert or there is a Desert card in your graveyard") == {"any": [  # Solitary Camel
        {"value": {"count": key("Desert you control")}, "op": ">=", "n": 1},
        {"value": {"count": key("Desert card in your graveyard")}, "op": ">=", "n": 1}]}
    assert conditions.parse("there are four or more card types among cards in your graveyard") == {  # Soul Swallower (delirium)
        "value": {"distinct": "types", "among": key("cards in your graveyard")}, "op": ">=", "n": 4}
    assert conditions.parse("seven or more cards are in your graveyard") == {  # Far Wanderings (threshold)
        "value": {"count": key("cards in your graveyard")}, "op": ">=", "n": 7}
    assert conditions.parse("creatures you control have total power 8 or greater") == {  # Surrak, the Hunt Caller (formidable)
        "value": {"sum": "power", "of": key("creatures you control")}, "op": ">=", "n": 8}
    assert conditions.parse("you control three or more creatures with different powers") == {  # Candlelit Cavalry (coven)
        "value": {"distinct": "powers", "among": key("creatures you control")}, "op": ">=", "n": 3}
    assert conditions.parse("no creatures are on the battlefield") == {  # Pestilence
        "value": {"count": key("creatures")}, "op": "==", "n": 0}


@pytest.mark.parametrize("text", [
    "it's a land card",  # (an object the ability refers to: only where the ability has those objects)
    "~ is tapped",
    "you control a foo",
    "you cast it",  # (spell-cast information isn't modelled: stays manual)
    "there are four or more card types among cards in your library",
])
def test_object_and_unknown_wordings_are_not_read_without_objects(text):
    assert conditions.parse(text) is None


@pytest.mark.parametrize(("text", "expected"), [
    ("it's a land card", {"object": "it", "is": key("land card")}),  # Harsh Deceiver
    ("that creature is a Human", {"object": "it", "is": key("Human")}),  # Elder Cathar
    ("~ is an enchantment", {"object": "self", "is": key("enchantment")}),  # Hidden Guerrillas
    ("it isn't a creature", {"object": "it", "is": key("creature"), "negate": True}),  # Tawnos's Tinkering
    ("~ is tapped", {"object": "self", "test": "tapped"}),  # Eater of the Dead
    ("~ is untapped", {"object": "self", "test": "untapped"}),  # Nim Abomination
    ("its mana value was 3 or less", {"object": "it", "stat": "mana_value", "op": "<=", "n": 3}),  # Extinguish the Light
    ("it's blue", {"object": "it", "is": key("blue permanent")}),  # Pyroblast
])
def test_object_wordings(text, expected):
    assert conditions.parse(text, objects=True) == expected


@pytest.mark.parametrize("text", [
    "it's tapped",  # (physical state of an object other than the source: never read from last known information)
    "it's a creature you control",
    "it was kicked",
    "it's the second time",
])
def test_unread_object_wordings(text):
    assert conditions.parse(text, objects=True) is None


# -- tables -----------------------------------------------------------------------------------------
def sandbox(cards, *names, p2=(), players=2):
    """A sandbox table (things are set up by hand), then ``combat_step`` switches the rules on."""
    def cards_of(commander, spells):
        return deck(cards, commander, [*((1, n) for n in spells), (9, "Forest")])

    setups = [PlayerSetup("Alice", cards=cards_of("Krenko, Mob Boss", names)),
              PlayerSetup("Bob", cards=cards_of("Atraxa, Praetors' Voice", p2))]
    if players == 3:
        setups.append(PlayerSetup("Carol", cards=cards_of("Krenko, Mob Boss", ())))
    return GameSession(new_game(setups, shuffle=False), cards=cards)


def creature(s, pid, name, pt="2/2", type_line="Token Creature — Test", text=""):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": type_line, "power": p, "toughness": t, "text": text})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def combat_step(s):
    """Rules on; Alice's first main phase, then on to her declare attackers."""
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → main 1
    act(s, "p1", type="pass_priority")  # → combat: Alice declares attackers


def attack(s, *pairs):
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in pairs])


def through_combat(s):
    """Play on to the second main phase (nobody blocks)."""
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
            continue
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
            continue
        if s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


def until(s, done, limit=300):
    """Pass priority (and answer whatever is asked the plain way) until ``done``."""
    for _ in range(limit):
        if done(s):
            return
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:  # (discard to hand size, the order of triggers, a choice: the first options offered)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    raise AssertionError("never got there")


def the_end_step(s, limit=80):
    """Play on through this turn's end step (its triggers resolve on the way) to the next turn's first main phase."""
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn and s.state.turn.phase == "main1", limit=limit)
    pass_until_stack_empty(s)


def to_turn(s, number, phase="main1", limit=120):
    until(s, lambda s: s.state.turn.number == number and s.state.turn.phase == phase, limit=limit)
    pass_until_stack_empty(s)


# -- history: attacked (Raid) -----------------------------------------------------------------------
def test_raid_after_attacking_makes_the_token(cards):
    """Mardu Hordechief: "Raid — When this creature enters, if you attacked this turn, create a 1/1 white Warrior creature token." (508.1)"""
    s = sandbox(cards, "Mardu Hordechief")
    bear = creature(s, "p1", "Bear")
    chief = to_hand(s, "Mardu Hordechief")
    combat_step(s)
    attack(s, (bear, "p2"))
    through_combat(s)
    mana(s, W=3)
    cast(s, chief)
    assert names_on_field(s).count("Warrior") == 1 and s.state.cards[chief.id].zone == "p1:battlefield"
    assert s.state.rules.turn_log.attacked == ["p1"]
    replay_matches(s)


def test_no_raid_without_an_attack(cards):
    s = sandbox(cards, "Mardu Hordechief")
    creature(s, "p1", "Bear")
    chief = to_hand(s, "Mardu Hordechief")
    combat_step(s)
    attack(s)  # (declares nobody: "doesn't attack")
    through_combat(s)
    mana(s, W=3)
    cast(s, chief)
    assert "Warrior" not in names_on_field(s) and not s.state.rules.pending_triggers
    assert s.state.rules.turn_log.attacked == []
    replay_matches(s)


# -- history: creatures that died (Morbid), permanents that left (Revolt) -------------------------------
def test_life_goes_on_gains_four_then_eight_instead_after_a_creature_died(cards):
    """Life Goes On: "You gain 4 life. If a creature died this turn, you gain 8 life instead." (608.2c, 700.4)"""
    s = build(cards, "Life Goes On", "Life Goes On")
    first, second = [c for c in s.state.cards.values() if c.name == "Life Goes On"]
    for c in (first, second):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, G=2)
    cast(s, first)
    assert life(s) == 44  # nothing died: the first instruction as written
    bear = creature(s, "p1", "Bear")
    act(s, "p2", type="create_token", player="p2", token={"name": "Goat", "type_line": "Token Artifact — Test"})
    act(s, "p2", type="move", card_ids=[find(s.state, "Goat", "p2").id], to={"zone": "graveyard"})  # an artifact isn't a creature
    cast(s, second)
    assert life(s) == 48  # (mana for the second was in the pool all along)
    replay_matches(s)
    assert bear.id in s.state.cards


def test_life_goes_on_after_a_creature_died(cards):
    s = build(cards, "Life Goes On")
    spell = to_hand(s, "Life Goes On")
    bear = creature(s, "p2", "Bear")  # (any player's creature: "a creature died this turn")
    act(s, "p2", type="move", card_ids=[bear.id], to={"zone": "graveyard"})
    mana(s, G=1)
    cast(s, spell)
    assert life(s) == 48
    assert [d.to for d in s.state.rules.turn_log.left] == ["graveyard"]
    replay_matches(s)
    assert reloaded(s).state.rules.turn_log == s.state.rules.turn_log


def test_the_condition_is_judged_as_the_spell_resolves_not_as_it_is_cast(cards):
    """608.2c / 608.2h: a creature dies while Life Goes On waits on the stack: it gains 8."""
    s = build(cards, "Life Goes On")
    spell = to_hand(s, "Life Goes On")
    bear = creature(s, "p1", "Bear")
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    assert life(s) == 40 and s.state.cards[spell.id].zone == "stack"
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "graveyard"})
    pass_until_stack_empty(s)
    assert life(s) == 48
    replay_matches(s)


def test_an_animated_land_that_died_was_a_creature(cards):
    """700.4 / 608.2i: what died is read as it last existed — a land that was a creature counts
    (the engine records the card types the layers gave it as it moves the permanent)."""
    s = build(cards, "Life Goes On", "Mutavault", "Murder")
    spell = to_hand(s, "Life Goes On")
    vault = on_field(s, "Mutavault")
    murder = to_hand(s, "Murder")
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=vault.id, ability=1)  # "{1}: becomes a 2/2 creature until end of turn"
    pass_until_stack_empty(s)
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[vault.id])
    pass_until_stack_empty(s)
    assert s.state.cards[vault.id].zone == "p1:graveyard"
    mana(s, G=1)
    cast(s, spell)
    assert life(s) == 48
    replay_matches(s)


def test_revolt_counts_only_your_permanents_and_tokens(cards):
    """Airdrop Aeronauts: "Revolt — When this creature enters, if a permanent left the battlefield under your control this turn, you gain 5 life." (700.4)"""
    s = build(cards, "Airdrop Aeronauts", "Airdrop Aeronauts")
    one, two = [c for c in s.state.cards.values() if c.name == "Airdrop Aeronauts"]
    for c in (one, two):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    theirs = creature(s, "p2", "Theirs")
    act(s, "p2", type="move", card_ids=[theirs.id], to={"zone": "graveyard"})
    mana(s, W=10)
    cast(s, one)
    assert life(s) == 40  # an opponent's permanent left: not "under your control"
    mine = creature(s, "p1", "Mine")
    act(s, "p1", type="move", card_ids=[mine.id], to={"zone": "exile"})  # (a token leaves, then ceases to exist)
    cast(s, two)
    assert life(s) == 45
    replay_matches(s)


# -- history: life, cards, spells, graveyard --------------------------------------------------------------
SAVAGE_GORGER = "At the beginning of your end step, if an opponent lost life this turn, put a +1/+1 counter on this creature."  # Savage Gorger


def test_an_opponent_lost_life_ignores_your_own_loss(cards):
    s = sandbox(cards, players=3)
    gorger = creature(s, "p1", "Gorger", text=SAVAGE_GORGER)
    turn_on(s)
    act(s, "p1", type="life", delta=-3)  # (you losing life isn't "an opponent")
    the_end_step(s)
    assert counters(s, gorger) == 0
    replay_matches(s)


def test_an_opponent_lost_life_is_any_one_of_your_opponents(cards):
    s = sandbox(cards, players=3)
    gorger = creature(s, "p1", "Gorger", text=SAVAGE_GORGER)
    turn_on(s)
    act(s, "p3", type="life", delta=-1)  # the third player, not the second
    assert s.state.rules.turn_log.lost == {"p3": 1}
    the_end_step(s)
    assert counters(s, gorger) == 1
    replay_matches(s)


GRIFFIN_AERIE = "At the beginning of your end step, if you gained 3 or more life this turn, create a 2/2 white Griffin creature token with flying."  # Griffin Aerie


@pytest.mark.parametrize(("changes", "griffins"), [
    ([("p1", 2), ("p1", -5), ("p2", 10)], 0),  # (a loss doesn't undo a gain; another player's gain isn't yours)
    ([("p1", 2), ("p1", 1)], 1),  # two and one: three gained this turn in all
])
def test_gained_three_or_more_life_this_turn_sums_the_gains(cards, changes, griffins):
    s = sandbox(cards)
    creature(s, "p1", "Aerie", text=GRIFFIN_AERIE)
    turn_on(s)
    for pid, delta in changes:
        act(s, pid, type="life", delta=delta)
    plan = Plan.view(s.state, "p1", s.cards)
    assert conditions.holds(plan, {"controller": "p1"}, conditions.parse("you gained 3 or more life this turn")) == bool(griffins)
    the_end_step(s)
    assert names_on_field(s).count("Griffin") == griffins
    replay_matches(s)


DEEP_GOBLIN_SKULLTAKER = "At the beginning of your end step, if you descended this turn, put a +1/+1 counter on this creature."


@pytest.mark.parametrize(("name", "pid", "exile_after", "counter"), [
    ("Grizzly Bears", "p1", False, 1),  # a permanent card put into your graveyard from anywhere (700.11)
    ("Forest", "p1", False, 1),  # (a land card)
    ("Sol Ring", "p1", False, 1),  # (an artifact card)
    ("Giant Growth", "p1", False, 0),  # an instant isn't a permanent card
    ("Grizzly Bears", "p2", False, 0),  # "your graveyard": not an opponent's
    ("Grizzly Bears", "p1", True, 1),  # it needn't still be there afterwards
])
def test_you_descended_this_turn(cards, name, pid, exile_after, counter):
    """Deep Goblin Skulltaker (and the other "descended" cards)."""
    s = sandbox(cards, name, p2=(name,))
    skulltaker = creature(s, "p1", "Deep Goblin Skulltaker", "1/1", "Token Creature — Goblin Warrior", text=DEEP_GOBLIN_SKULLTAKER)
    target = find(s.state, name, pid)
    turn_on(s)
    act(s, pid, type="move", card_ids=[target.id], to={"zone": "graveyard"})
    if exile_after:
        act(s, pid, type="move", card_ids=[target.id], to={"zone": "exile"})
    the_end_step(s)
    assert counters(s, skulltaker) == counter
    replay_matches(s)


def test_a_token_is_no_card_so_it_doesnt_descend_but_a_card_that_died_does(cards):
    s = sandbox(cards, "Grizzly Bears")
    skulltaker = creature(s, "p1", "Deep Goblin Skulltaker", "1/1", "Token Creature — Goblin Warrior", text=DEEP_GOBLIN_SKULLTAKER)
    bears = on_field(s, "Grizzly Bears")
    goblin = creature(s, "p1", "Goblin")
    turn_on(s)
    act(s, "p1", type="move", card_ids=[goblin.id], to={"zone": "graveyard"})  # a token dies: no card
    assert s.state.rules.turn_log.entered_graveyard == []
    plan = Plan.view(s.state, "p1", s.cards)
    assert not conditions.holds(plan, {"controller": "p1"}, conditions.parse("you descended this turn"))
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "graveyard"})  # a creature card dies
    assert [a.card for a in s.state.rules.turn_log.entered_graveyard] == [bears.id]
    assert reloaded(s).state.rules.turn_log == s.state.rules.turn_log
    the_end_step(s)
    assert counters(s, skulltaker) == 1
    replay_matches(s)


def test_the_turn_log_starts_over_each_turn_and_keeps_the_turn_before(cards):
    """First Response: "At the beginning of each upkeep, if you lost life last turn, create a 1/1 white Soldier creature token." """
    s = sandbox(cards)
    creature(s, "p1", "First Response", text="At the beginning of each upkeep, if you lost life last turn, create a 1/1 white Soldier creature token.")
    turn_on(s)
    act(s, "p1", type="life", delta=-1)  # on Alice's turn (turn 1)
    to_turn(s, 2)
    assert names_on_field(s).count("Soldier") == 1  # Bob's upkeep: Alice lost life last turn
    to_turn(s, 3)
    assert names_on_field(s).count("Soldier") == 1  # Alice's next upkeep: she lost none during Bob's turn
    replay_matches(s)


def test_a_turn_nothing_was_recorded_in_is_not_last_turn(cards):
    """The previous turn is the turn before — an older log never stands in for a quiet one."""
    s = sandbox(cards)
    turn_on(s)
    act(s, "p1", type="life", delta=-1)
    to_turn(s, 3)
    plan = Plan.view(s.state, "p1", s.cards)
    assert not conditions.holds(plan, {"controller": "p1"}, conditions.parse("you lost life last turn"))
    assert history.log_for(plan, last=True).lost == {}


def test_drawn_two_or_more_cards_this_turn_turns_a_static_on(cards):
    """Messenger Hawk: "This creature gets +2/+0 as long as you've drawn two or more cards this turn." (611.3a)"""
    s = build(cards)
    hawk = token(s, "p1", "Hawk", "1/1", text="This creature gets +2/+0 as long as you've drawn two or more cards this turn.")
    assert ch(s, hawk).pt == (1, 1)
    act(s, "p1", type="draw", count=1)
    assert ch(s, hawk).pt == (1, 1)
    act(s, "p1", type="draw", count=1)
    assert ch(s, hawk).pt == (3, 1)
    replay_matches(s)


def test_cast_two_or_more_spells_this_turn(cards):
    """Brightspear Zealot: "This creature gets +2/+0 as long as you've cast two or more spells this turn." """
    s = build(cards, "Giant Growth", "Giant Growth")
    zealot = token(s, "p1", "Zealot", "2/2", text="This creature gets +2/+0 as long as you've cast two or more spells this turn.")
    first, second = [c for c in s.state.cards.values() if c.name == "Giant Growth"]
    for c in (first, second):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, G=2)
    cast(s, first, targets=[zealot.id])
    assert ch(s, zealot).pt == (5, 5)  # (+3/+3 from the first, no bonus yet)
    cast(s, second, targets=[zealot.id])
    assert ch(s, zealot).pt == (10, 8)
    replay_matches(s)


def test_a_card_left_your_graveyard_this_turn(cards):
    """Relic Retriever: "At the beginning of each end step, if a card left your graveyard this turn, create a Treasure token." """
    s = sandbox(cards, "Lightning Bolt")
    creature(s, "p1", "Retriever", text="At the beginning of each end step, if a card left your graveyard this turn, create a Treasure token.")
    bolt = to_hand(s, "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "graveyard"})
    turn_on(s)
    the_end_step(s)  # (it entered the graveyard before the rules were on, and hasn't left it)
    assert "Treasure" not in names_on_field(s)
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "exile"})  # Bob's turn: it leaves, and "each end step" is his too
    the_end_step(s)
    assert names_on_field(s).count("Treasure") == 1
    replay_matches(s)


# -- the table: monarch, whose turn, your commander, graveyard, counts, totals ------------------------------
THRONE_WARDEN = "At the beginning of your end step, if you're the monarch, put a +1/+1 counter on this creature."  # Throne Warden


@pytest.mark.parametrize(("monarch", "counter"), [("p1", 1), ("p2", 0), (None, 0)])
def test_monarch_gates_an_intervening_if(cards, monarch, counter):
    s = build(cards)
    warden = token(s, "p1", "Warden", text=THRONE_WARDEN)
    if monarch:
        act(s, "p1", type="set_monarch", player=monarch)
    the_end_step(s)
    assert counters(s, warden) == counter
    replay_matches(s)


def test_the_intervening_if_is_checked_again_as_it_resolves(cards):
    """603.4 / 608.2a: it triggers as the monarch; by the time it resolves someone else is."""
    s = build(cards)
    warden = token(s, "p1", "Warden", text=THRONE_WARDEN)
    act(s, "p1", type="set_monarch", player="p1")
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack)
    until(s, lambda s: any(e.name == "Warden" for e in s.state.rules.stack.values()))
    act(s, "p2", type="set_monarch", player="p2")  # Bob takes the crown in response
    pass_until_stack_empty(s)
    assert counters(s, warden) == 0
    assert s.state.players["p2"].life == 40 and s.state.table.monarch == "p2"
    replay_matches(s)


def test_a_court_of_two_tokens_when_the_monarch(cards):
    """Court of Grace: "At the beginning of your upkeep, create a 1/1 white Spirit creature token with flying. If you're the
    monarch, create a 4/4 white Angel creature token with flying instead." (608.2c: the second replaces the first)"""
    text = ("At the beginning of your upkeep, create a 1/1 white Spirit creature token with flying. "
            "If you're the monarch, create a 4/4 white Angel creature token with flying instead.")
    for monarch, expected in (("p1", ["Angel"]), ("p2", ["Spirit"])):
        s = sandbox(cards)
        creature(s, "p1", "Court", text=text)
        act(s, "p1", type="set_monarch", player=monarch)
        turn_on(s)
        to_turn(s, 2)  # (through Alice's upkeep, the turn the rules came on)
        assert [n for n in names_on_field(s) if n in ("Angel", "Spirit")] == expected
        replay_matches(s)


def test_it_is_your_turn_or_otherwise(cards):
    """Stolen Vitality: "… If it's your turn, that creature gains trample until end of turn. Otherwise, it gains first strike
    until end of turn." (the verdict is judged once, as the instruction is reached)"""
    s = sandbox(cards, "Stolen Vitality", "Stolen Vitality")
    bear = creature(s, "p1", "Bear")
    first, second = [c for c in s.state.cards.values() if c.name == "Stolen Vitality"]
    for c in (first, second):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    mana(s, R=4)
    cast(s, first, targets=[bear.id])
    assert {"trample"} <= ch(s, bear).keywords and "first strike" not in ch(s, bear).keywords
    replay_matches(s)
    to_turn(s, 2)
    act(s, "p1", type="set_prefs", response="on")
    # Bob's turn: Alice has an instant-speed window when she gets priority after Bob
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.rules.priority == "p1", limit=30)
    mana(s, R=2)
    cast(s, second, targets=[bear.id])
    assert "first strike" in ch(s, bear).keywords
    replay_matches(s)


def test_lieutenant_needs_your_commander_on_the_battlefield(cards):
    """Loyal Drake: "Lieutenant — At the beginning of combat on your turn, if you control your commander, draw a card." (903.3)"""
    for commander_out in (False, True):
        s = sandbox(cards, "Loyal Drake")
        on_field(s, "Loyal Drake")
        if commander_out:
            on_field(s, "Krenko, Mob Boss")
        hand = len(zone(s.state, "p1", "hand"))
        turn_on(s)
        act(s, "p1", type="pass_priority")
        until(s, lambda s: s.state.turn.phase in ("declare_attackers", "main2"), limit=20)
        pass_until_stack_empty(s)
        assert len(zone(s.state, "p1", "hand")) == hand + (1 if commander_out else 0), commander_out
        replay_matches(s)


def test_delirium_counts_card_types_among_graveyard_cards(cards):
    """Soul Swallower: "Delirium — At the beginning of your upkeep, if there are four or more card types among cards in your
    graveyard, put three +1/+1 counters on this creature." (205.2a, 603.4)"""
    s = sandbox(cards, "Sol Ring", "Lightning Bolt", "Llanowar Elves", "Soul Swallower")
    swallower = on_field(s, "Soul Swallower")
    for name in ("Sol Ring", "Lightning Bolt", "Llanowar Elves"):
        act(s, "p1", type="move", card_ids=[find(s.state, name, "p1").id], to={"zone": "graveyard"})
    turn_on(s)
    to_turn(s, 3)
    assert counters(s, swallower) == 0  # artifact, instant, creature: three types
    act(s, "p1", type="move", card_ids=[named(s, "Forest").id], to={"zone": "graveyard"})  # land: four
    to_turn(s, 5)
    assert counters(s, swallower) == 3
    replay_matches(s)


def test_delirium_static(cards):
    """Grim Flayer: "Delirium — This creature gets +2/+2 as long as there are four or more card types among cards in your graveyard." """
    s = build(cards, "Sol Ring", "Lightning Bolt", "Llanowar Elves")
    flayer = token(s, "p1", "Flayer", "2/2", text="Delirium — This creature gets +2/+2 as long as there are four or more card types among cards in your graveyard.")
    for name in ("Sol Ring", "Lightning Bolt", "Llanowar Elves", "Forest"):
        assert ch(s, flayer).pt == (2, 2)
        act(s, "p1", type="move", card_ids=[named(s, name).id], to={"zone": "graveyard"})
    assert ch(s, flayer).pt == (4, 4)
    replay_matches(s)


@pytest.mark.parametrize(("x", "destroyed"), [(2, False), (6, True)])
def test_x_is_six_or_more(cards, x, destroyed):
    """Blot Out the Sky: "Create X tapped 2/1 white and black Inkling creature tokens with flying. If X is 6 or more, destroy
    all noncreature, nonland permanents." (107.3: the X the spell was cast with)"""
    s = build(cards, "Blot Out the Sky")
    sky = to_hand(s, "Blot Out the Sky")
    trinket = token_of(s, "p2", "Trinket", "Token Artifact — Trinket", pt="0/0")
    mana(s, W=1, B=1, C=x)
    cast(s, sky, x_value=x)
    assert names_on_field(s).count("Inkling") == x
    assert (trinket.id not in s.state.cards) == destroyed
    replay_matches(s)


def test_destroy_all_other_creatures_after_making_tokens_stays_manual(cards):
    """Martial Coup: "Create X 1/1 white Soldier creature tokens. If X is 5 or more, destroy all other creatures." — "other"
    means other than those tokens (its rulings), which the engine's "other than the source" isn't: never guessed."""
    text = "Create X 1/1 white Soldier creature tokens. If X is 5 or more, destroy all other creatures."
    assert scripts.parse_effects(text) is None
    assert coverage.of_card_data(cards.resolve("Martial Coup")).level == "PARTIAL"
    assert scripts.parse_effects("Create a 1/1 white Soldier creature token. If you control four or more creatures, destroy all creatures.")


OWLBEAR_SHEPHERD = "At the beginning of your end step, if creatures you control have total power 8 or greater, draw a card."
CANDLEGROVE_WITCH = ("Coven — At the beginning of combat on your turn, if you control three or more creatures with different powers, "
                     "this creature gains flying until end of turn.")


@pytest.mark.parametrize(("other_power", "draws"), [(3, 0), (4, 1)])
def test_total_power_eight_or_greater(cards, other_power, draws):
    """Owlbear Shepherd (formidable wording): a 4/4 and a 3/3 have total power 7, a 4/4 and a 4/4 have exactly 8."""
    s = sandbox(cards)
    creature(s, "p1", "Shepherd", "4/4", text=OWLBEAR_SHEPHERD)
    creature(s, "p1", "Other", f"{other_power}/3")
    hand = len(zone(s.state, "p1", "hand"))
    turn_on(s)
    the_end_step(s)
    assert len(zone(s.state, "p1", "hand")) == hand + draws
    replay_matches(s)


@pytest.mark.parametrize(("others", "flies"), [(("2/2", "2/3"), False), (("2/2", "3/3"), True)])
def test_three_or_more_creatures_with_different_powers(cards, others, flies):
    """Candlegrove Witch (coven): a 1/1 Witch with a 2/2 and a 2/3 has two different powers, with a 2/2 and a 3/3 three."""
    s = sandbox(cards)
    witch = creature(s, "p1", "Witch", "1/1", text=CANDLEGROVE_WITCH)
    for i, pt in enumerate(others):
        creature(s, "p1", f"Other {i}", pt)
    turn_on(s)
    until(s, lambda s: s.state.turn.phase in ("declare_attackers", "main2"), limit=30)
    pass_until_stack_empty(s)
    assert ("flying" in ch(s, witch).keywords) == flies
    replay_matches(s)


@pytest.mark.parametrize(("bob_life", "bob_creatures", "gains", "angels"), [
    (41, 2, 5, 1),  # more life and more creatures (2 against Linvala alone)
    (40, 1, 0, 0),  # equal on both: "more" is strictly more
    (41, 1, 5, 0),  # only life
    (30, 3, 0, 1),  # only creatures
])
def test_an_opponent_has_more_life_or_more_creatures(cards, bob_life, bob_creatures, gains, angels):
    """Linvala, the Preserver: "When Linvala enters, if an opponent has more life than you, you gain 5 life. When Linvala
    enters, if an opponent controls more creatures than you, create a 3/3 white Angel creature token with flying." """
    s = build(cards, "Linvala, the Preserver")
    linvala = to_hand(s, "Linvala, the Preserver")
    act(s, "p2", type="life", delta=bob_life - 40)
    for i in range(bob_creatures):
        creature(s, "p2", f"Theirs {i}")
    mana(s, W=6)
    cast(s, linvala)
    assert life(s) == 40 + gains and names_on_field(s).count("Angel") == angels
    replay_matches(s)


# -- "Otherwise", trailing "if" / "unless", the verdict judged once ---------------------------------------
def until_asked(s, limit=40):
    """Pass priority until a decision is asked (returned) or everything has resolved (None)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            return d
        if not s.state.zones.get("stack"):
            return None
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("still resolving")


def pick(s, *ids, pid=None):
    d = s.state.rules.decision
    act(s, pid or d.player, type="choose", decision_id=d.id, option_ids=list(ids))


def test_otherwise_draw_a_card_or_each_player_sacrifices(cards):
    """Gravelighter: "When this creature enters, draw a card if a creature died this turn. Otherwise, each player sacrifices a
    creature of their choice." (608.2c: the second sentence is the else of the first, on the same verdict)"""
    for died in (True, False):
        s = build(cards, "Gravelighter")
        ghost = to_hand(s, "Gravelighter")
        mine = creature(s, "p1", "Mine")
        theirs = creature(s, "p2", "Theirs")
        fodder = creature(s, "p2", "Fodder")
        if died:
            act(s, "p2", type="move", card_ids=[fodder.id], to={"zone": "graveyard"})
            act(s, "p2", type="move", card_ids=[theirs.id], to={"zone": "graveyard"})
            theirs = creature(s, "p2", "Theirs again")
        hand = len(zone(s.state, "p1", "hand"))
        mana(s, B=3)
        act(s, "p1", type="cast_spell", card_id=ghost.id)
        asked = []
        for _ in range(10):  # (each player picks what they sacrifice, in turn order, when there is a choice to make)
            d = until_asked(s)
            if d is None:
                break
            assert d.kind == "choose_cards"
            asked.append(d.player)
            ids = [o.id for o in d.options]
            pick(s, mine.id if mine.id in ids else ids[0])
        if died:
            assert asked == [] and len(zone(s.state, "p1", "hand")) == hand - 1 + 1  # drew a card, nobody sacrificed
            assert mine.id in s.state.cards and theirs.id in s.state.cards
        else:
            assert asked == ["p1", "p2"] and mine.id not in s.state.cards  # each player sacrificed a creature
            assert sum(1 for c in (theirs, fodder) if c.id in s.state.cards) == 1
            assert s.state.cards[ghost.id].zone == "p1:battlefield"
        replay_matches(s)


@pytest.mark.parametrize(("tapped", "p1_life", "p2_life"), [(False, 43, 40), (True, 40, 37)])
def test_trailing_if_with_otherwise_on_the_source(cards, tapped, p1_life, p2_life):
    """Sphinx Sovereign: "At the beginning of your end step, you gain 3 life if this creature is untapped. Otherwise, each
    opponent loses 3 life." """
    s = build(cards)
    token(s, "p1", "Sovereign", "6/6", text="At the beginning of your end step, you gain 3 life if this creature is untapped. "
                                            "Otherwise, each opponent loses 3 life.")
    if tapped:
        act(s, "p1", type="tap", card_ids=[named(s, "Sovereign").id], tapped=True)
    the_end_step(s)
    assert (life(s, "p1"), life(s, "p2")) == (p1_life, p2_life)
    replay_matches(s)


@pytest.mark.parametrize(("pirates", "lost"), [(0, 2), (1, 0)])
def test_unless_you_control_another_pirate(cards, pirates, lost):
    """Fathom Fleet Boarder: "When this creature enters, you lose 2 life unless you control another Pirate." ("another": not itself)"""
    s = build(cards, "Fathom Fleet Boarder")
    boarder = to_hand(s, "Fathom Fleet Boarder")
    for i in range(pirates):
        token_of(s, "p1", f"Pirate {i}", "Token Creature — Pirate")
    mana(s, B=3)
    cast(s, boarder)
    assert life(s) == 40 - lost
    replay_matches(s)


def test_the_top_card_is_a_land_or_otherwise_goes_to_hand(cards):
    """Coiling Oracle: "When this creature enters, reveal the top card of your library. If it's a land card, put it onto the
    battlefield. Otherwise, put that card into your hand." (608.2h: "it" is the card revealed)"""
    for top in ("Forest", "Giant Growth"):
        s = build(cards, "Coiling Oracle", "Giant Growth")
        oracle = to_hand(s, "Coiling Oracle")
        card_on_top = next(c for c in s.state.cards.values() if c.name == top and c.owner == "p1" and c.zone == "p1:library")
        act(s, "p1", type="move", card_ids=[card_on_top.id], to={"zone": "library"}, position="top")
        hand = len(zone(s.state, "p1", "hand"))
        mana(s, G=1, U=1)
        cast(s, oracle)
        now = s.state.cards[card_on_top.id].zone
        if top == "Forest":
            assert now == "p1:battlefield" and len(zone(s.state, "p1", "hand")) == hand - 1
        else:
            assert now == "p1:hand" and len(zone(s.state, "p1", "hand")) == hand - 1 + 1
        replay_matches(s)


def test_the_verdict_is_judged_once_for_the_otherwise_clause(cards):
    """608.2c: "If you control a Forest, sacrifice a Forest you control. Otherwise, you gain 5 life." — sacrificing the only
    Forest makes the condition false, but the Otherwise clause reads the verdict the condition was given."""
    s = build(cards)
    sage = token(s, "p1", "Sage", text="{1}: If you control a Forest, sacrifice a Forest you control. Otherwise, you gain 5 life.")
    forest = on_field(s, "Forest")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=sage.id, ability=0)
    settle(s)
    assert s.state.cards[forest.id].zone == "p1:graveyard" and life(s) == 40  # no life: the verdict was "true"
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=sage.id, ability=0)
    settle(s)
    assert life(s) == 45  # now there's no Forest: the else clause
    replay_matches(s)


def test_the_otherwise_verdict_survives_a_decision_and_a_reload(cards):
    """The recorded verdict lives in the resolution's context: a pause for a choice in between doesn't lose it."""
    s = build(cards)
    sage = token(s, "p1", "Sage", text="{1}: If you control a Forest, sacrifice a Forest you control. Otherwise, you gain 5 life.")
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:2]
    for c in forests:  # (two lands: Alice chooses which to sacrifice)
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=sage.id, ability=0)
    d = until_asked(s)
    assert d is not None and d.kind == "choose_cards"
    again = reloaded(s)
    pick(again, forests[0].id)
    settle(again)
    pick(s, forests[0].id)
    settle(s)
    assert s.state.players["p1"].life == 40 and again.state.players["p1"].life == 40
    assert len([c for c in zone(s.state, "p1", "battlefield") if s.state.cards[c].name == "Forest"]) == 1
    replay_matches(s)


# -- "X unless [a player] discards / sacrifices / pays …" (118.12a) -------------------------------------
def test_unless_you_sacrifice_a_land_pay_or_lose_it(cards):
    """Scythe Tiger: "When this creature enters, sacrifice it unless you sacrifice a land." (118.12a: "You may sacrifice a land.
    If you don't, sacrifice it.")"""
    for answer in ("pay", "decline"):
        s = build(cards, "Scythe Tiger")
        lands = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:2]
        for c in lands:
            act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
        tiger = to_hand(s, "Scythe Tiger")
        mana(s, G=1)
        act(s, "p1", type="cast_spell", card_id=tiger.id)
        d = until_asked(s)
        assert d.player == "p1" and d.kind == "choose_one" and [o.id for o in d.options] == ["pay", "decline"]
        assert "options" not in s.view("p2")["rules"]["decision"]  # (the payer's own decision)
        pick(s, answer)
        if answer == "pay":
            d = until_asked(s)  # which land
            assert d.kind == "choose_cards" and {o.id for o in d.options} == {c.id for c in lands}
            pick(s, lands[1].id)
        settle(s)
        if answer == "pay":
            assert s.state.cards[tiger.id].zone == "p1:battlefield" and s.state.cards[lands[1].id].zone == "p1:graveyard"
        else:
            assert s.state.cards[tiger.id].zone == "p1:graveyard" and all(s.state.cards[c.id].zone == "p1:battlefield" for c in lands)
        replay_matches(s)


def test_a_payment_that_cant_be_made_isnt_offered(cards):
    """608.2d / 118.3: with no land to sacrifice the option isn't there: the Tiger is sacrificed."""
    s = build(cards, "Scythe Tiger")
    tiger = to_hand(s, "Scythe Tiger")
    mana(s, G=1)
    cast(s, tiger)
    assert s.state.cards[tiger.id].zone == "p1:graveyard" and s.state.rules.decision is None
    replay_matches(s)


def test_unless_you_discard_a_card_at_upkeep(cards):
    """Masticore: "At the beginning of your upkeep, sacrifice this creature unless you discard a card." """
    s = build(cards, "Masticore", "Lightning Bolt", "Giant Growth")
    masticore = on_field(s, "Masticore")
    bolt = to_hand(s, "Lightning Bolt")
    growth = to_hand(s, "Giant Growth")
    d = None
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_one":
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
    assert d is not None and d.player == "p1" and s.state.turn.number == 3  # (Alice's next upkeep)
    pick(s, "pay")
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and {bolt.id, growth.id} <= {o.id for o in d.options}
    assert "options" not in s.view("p2")["rules"]["decision"]  # (what is in Alice's hand is hers to see)
    pick(s, bolt.id)
    settle(s)
    assert s.state.cards[masticore.id].zone == "p1:battlefield" and s.state.cards[bolt.id].zone == "p1:graveyard"
    assert s.state.cards[growth.id].zone == "p1:hand"
    replay_matches(s)


def test_the_payer_is_the_player_whose_spell_it_was(cards):
    """Painful Quandary: "Whenever an opponent casts a spell, that player loses 5 life unless they discard a card." — the
    decision is Bob's (the player who cast it), not Alice's."""
    for answer, bob_life in (("pay", 40), ("decline", 35)):
        s = build(cards, "Painful Quandary", p2=("Giant Growth", "Giant Growth"))
        on_field(s, "Painful Quandary")
        to_turn(s, 2)
        growths = [c for c in s.state.cards.values() if c.name == "Giant Growth" and c.owner == "p2"]
        for c in growths:
            act(s, "p2", type="move", card_ids=[c.id], to={"zone": "hand"})
        bear = creature(s, "p2", "Bear")
        mana(s, "p2", G=1)
        hand = len(zone(s.state, "p2", "hand"))
        act(s, "p2", type="cast_spell", card_id=growths[0].id, targets=[bear.id])
        d = until_asked(s)
        assert d.player == "p2" and [o.id for o in d.options] == ["pay", "decline"]
        assert "options" not in s.view("p1")["rules"]["decision"]
        pick(s, answer)
        if answer == "pay":  # (their hand: the other Giant Growth and whatever they drew: a choice only they see)
            d = until_asked(s)
            if d is not None:
                assert d.kind == "choose_cards" and d.player == "p2" and len(d.options) == hand - 1
                pick(s, growths[1].id)
        settle(s)
        assert life(s, "p2") == bob_life and life(s, "p1") == 40
        assert len(zone(s.state, "p2", "hand")) == hand - 1 - (1 if answer == "pay" else 0)
        replay_matches(s)


def test_nothing_to_discard_means_the_loss_happens(cards):
    """118.3: Bob has no card to discard, so he can't pay it: he loses the 5 life (and nothing is asked)."""
    s = build(cards, "Painful Quandary", p2=("Giant Growth",))
    on_field(s, "Painful Quandary")
    to_turn(s, 2)  # (his one draw is the Giant Growth he casts)
    growth = to_hand(s, "Giant Growth", "p2")
    bear = creature(s, "p2", "Bear")
    mana(s, "p2", G=1)
    act(s, "p2", type="cast_spell", card_id=growth.id, targets=[bear.id])
    assert until_asked(s) is None and life(s, "p2") == 35
    replay_matches(s)


def test_unless_they_pay_the_edict_is_theirs_too(cards):
    """Spelltithe Enforcer: "Whenever an opponent casts a spell, that player sacrifices a permanent of their choice unless they
    pay {1}." """
    for answer in ("pay", "decline"):
        s = build(cards, "Spelltithe Enforcer", p2=("Giant Growth",))
        enforcer = on_field(s, "Spelltithe Enforcer")
        to_turn(s, 2)
        growth = to_hand(s, "Giant Growth", "p2")
        bear = creature(s, "p2", "Bear")
        other = creature(s, "p2", "Other")
        mana(s, "p2", G=2)
        act(s, "p2", type="cast_spell", card_id=growth.id, targets=[bear.id])
        d = until_asked(s)
        assert d.player == "p2" and d.kind == "choose_one"
        pick(s, answer)
        if answer == "decline":
            d = until_asked(s)
            assert d.kind == "choose_cards" and d.player == "p2"  # (Bob picks what he sacrifices)
            assert enforcer.id not in {o.id for o in d.options} and {bear.id, other.id} <= {o.id for o in d.options}
            pick(s, other.id)
        settle(s)
        assert (other.id in s.state.cards) == (answer == "pay")  # (the one Bob chose went; none when he paid)
        assert bear.id in s.state.cards and life(s, "p1") == 40 and s.state.cards[enforcer.id].zone == "p1:battlefield"
        replay_matches(s)


# -- "X. If C, Y instead." on a target, and objects that left (608.2h) -------------------------------------
@pytest.mark.parametrize(("colors", "damage_dead"), [(("W",), True), (("U",), True), (("R",), False)])
def test_lightning_dart_four_damage_instead_to_a_white_or_blue_creature(cards, colors, damage_dead):
    """Lightning Dart: "… deals 1 damage to target creature. If that creature is white or blue, Lightning Dart deals 4 damage to
    it instead." (608.2c; "it" is the target, read as it is now, 608.2h)"""
    s = build(cards, "Lightning Dart")
    dart = to_hand(s, "Lightning Dart")
    victim = token_of(s, "p2", "Victim", "Token Creature — Test", pt="3/3" if not damage_dead else "4/4", colors=colors)
    mana(s, R=1, C=1)
    cast(s, dart, targets=[victim.id])
    if damage_dead:
        assert victim.id not in s.state.cards  # (4 damage on a 4/4)
    else:
        assert s.state.cards[victim.id].damage == 1
    replay_matches(s)


@pytest.mark.parametrize(("one_leaves_in_response", "expected"), [(False, (5, 5)), (True, (3, 3))])
def test_for_the_family_needs_four_creatures_as_it_resolves(cards, one_leaves_in_response, expected):
    """For the Family: "Target creature gets +2/+2 until end of turn. If you control four or more creatures, that creature gets
    +4/+4 until end of turn instead." The count is taken as the spell resolves, not as it's cast (608.2h): four creatures when
    it's cast, and only three (so +2/+2) if one of them is gone by then."""
    s = build(cards, "For the Family")
    spell = to_hand(s, "For the Family")
    bear = creature(s, "p1", "Bear", "1/1")
    others = [creature(s, "p1", f"Other {i}") for i in range(3)]  # four creatures as it's cast
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id])
    if one_leaves_in_response:
        act(s, "p1", type="move", card_ids=[others[0].id], to={"zone": "graveyard"})
    pass_until_stack_empty(s)
    assert ch(s, bear).pt == expected
    replay_matches(s)


def test_death_s_caress_reads_the_creature_as_it_last_existed(cards):
    """Death's Caress: "Destroy target creature. If that creature was a Human, you gain life equal to its toughness." (608.2h:
    it's gone, so last known information: its toughness with the counter it had)"""
    for type_line, gain in (("Token Creature — Human", 4), ("Token Creature — Goblin", 0)):
        s = build(cards, "Death's Caress")
        caress = to_hand(s, "Death's Caress")
        victim = token_of(s, "p2", "Victim", type_line, pt="2/3")
        act(s, "p2", type="counter", card_ids=[victim.id], kind="+1/+1", delta=1)  # toughness 4 as it dies
        mana(s, B=2, C=3)
        cast(s, caress, targets=[victim.id])
        assert victim.id not in s.state.cards and life(s) == 40 + gain
        replay_matches(s)


@pytest.mark.parametrize(("kicked", "remaining"), [(0, {"Two": 1, "Three": 1}), (1, {"Two": None, "Three": 2})])
def test_kicked_it_deals_two_damage_instead(cards, kicked, remaining):
    """Cinderclasm: "Cinderclasm deals 1 damage to each creature. If it was kicked, it deals 2 damage to each creature
    instead." (702.33e: "it" is the spell)"""
    s = build(cards, "Cinderclasm")
    spell = to_hand(s, "Cinderclasm")
    two = creature(s, "p2", "Two", "2/2")
    three = creature(s, "p2", "Three", "3/3")
    mana(s, R=1 + kicked, C=1)
    cast(s, spell, **({"kicker": 1} if kicked else {}))
    for c, name in ((two, "Two"), (three, "Three")):
        if remaining[name] is None:
            assert c.id not in s.state.cards
        else:
            assert s.state.cards[c.id].damage == remaining[name]
    replay_matches(s)


# -- "that creature is a …", "it was a … card": the object an effect refers to (608.2h) --------------------------
@pytest.mark.parametrize(("name", "grows"), [("Grizzly Bears", True), ("Giant Growth", False)])
def test_scavenging_ooze_grows_only_on_a_creature_card(cards, name, grows):
    """Scavenging Ooze: "{G}: Exile target card from a graveyard. If it was a creature card, put a +1/+1 counter on this creature
    and you gain 1 life." (608.2c: read as the exiled card — a card is what it is wherever it is)"""
    s = build(cards, "Scavenging Ooze", name)
    ooze = on_field(s, "Scavenging Ooze")
    target = find(s.state, name, "p1")
    act(s, "p1", type="move", card_ids=[target.id], to={"zone": "graveyard"})
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=ooze.id, ability=0, targets=[target.id])
    pass_until_stack_empty(s)
    assert s.state.cards[target.id].zone == "p1:exile"
    assert counters(s, ooze) == int(grows) and life(s) == 40 + int(grows)
    replay_matches(s)


@pytest.mark.parametrize(("type_line", "exiled"), [("Token Creature — Zombie", True), ("Token Creature — Human", False)])
def test_holy_justiciar_exiles_only_a_zombie(cards, type_line, exiled):
    """Holy Justiciar: "{2}{W}, {T}: Tap target creature. If that creature is a Zombie, exile it." """
    s = sandbox(cards, "Holy Justiciar")
    justiciar = on_field(s, "Holy Justiciar")
    victim = creature(s, "p2", "Victim", type_line=type_line)
    turn_on(s)
    mana(s, W=1, C=2)
    act(s, "p1", type="activate_ability", card_id=justiciar.id, ability=0, targets=[victim.id])
    pass_until_stack_empty(s)
    assert s.state.cards[justiciar.id].tapped  # (the cost)
    if exiled:
        assert victim.id not in s.state.cards  # (a token that leaves the battlefield ceases to exist)
    else:
        assert s.state.cards[victim.id].tapped
    replay_matches(s)


@pytest.mark.parametrize(("type_line", "counters_on_it"), [("Token Creature — Elemental", 1), ("Token Creature — Goblin", 0)])
def test_overgrowth_elemental_looks_at_the_creature_that_died(cards, type_line, counters_on_it):
    """Overgrowth Elemental: "Whenever another creature you control dies, you gain 1 life. If that creature was an Elemental, put a
    +1/+1 counter on this creature." (700.4: it died; 608.2h: its types as it last existed on the battlefield)"""
    s = build(cards, "Overgrowth Elemental", "Murder")
    elemental = on_field(s, "Overgrowth Elemental")
    victim = creature(s, "p1", "Victim", type_line=type_line)
    murder = to_hand(s, "Murder")
    mana(s, B=3)
    cast(s, murder, targets=[victim.id])
    assert victim.id not in s.state.cards
    assert life(s) == 41 and counters(s, elemental) == counters_on_it
    replay_matches(s)


def test_overgrowth_elemental_ignores_other_creatures_and_itself(cards):
    s = build(cards, "Overgrowth Elemental", "Murder", "Murder")
    elemental = on_field(s, "Overgrowth Elemental")
    theirs = creature(s, "p2", "Theirs", type_line="Token Creature — Elemental")
    first, second = [c for c in s.state.cards.values() if c.name == "Murder"]
    for c in (first, second):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, B=6)
    cast(s, first, targets=[theirs.id])  # "another creature you control": not Bob's
    assert life(s) == 40 and counters(s, elemental) == 0
    cast(s, second, targets=[elemental.id])  # and not itself
    assert life(s) == 40 and s.state.cards[elemental.id].zone == "p1:graveyard"
    replay_matches(s)


@pytest.mark.parametrize(("type_line", "counters_on_it"), [("Token Creature — Human", 2), ("Token Creature — Goblin", 1)])
def test_elder_cathar_puts_two_counters_instead_on_a_human(cards, type_line, counters_on_it):
    """Elder Cathar: "When this creature dies, put a +1/+1 counter on target creature you control. If that creature is a Human, put
    two +1/+1 counters on it instead." (608.2c: "that creature" is the target, not the Cathar that died)"""
    s = build(cards, "Elder Cathar", "Murder")
    cathar = on_field(s, "Elder Cathar")
    friend = creature(s, "p1", "Friend", type_line=type_line)
    murder = to_hand(s, "Murder")
    mana(s, B=3)
    cast(s, murder, targets=[cathar.id])
    assert s.state.cards[cathar.id].zone == "p1:graveyard"
    assert counters(s, friend) == counters_on_it
    replay_matches(s)


@pytest.mark.parametrize(("type_line", "counters_on_it"), [
    ("Token Creature — Goblin", 2), ("Token Creature — Orc", 2), ("Token Creature — Goblin Orc", 2), ("Token Creature — Elf", 1)])
def test_ugluk_counts_two_for_a_goblin_or_an_orc(cards, type_line, counters_on_it):
    """Uglúk of the White Hand: "Whenever another creature you control dies, put a +1/+1 counter on Uglúk. If that creature was a
    Goblin or Orc, put two +1/+1 counters on Uglúk instead." (one type from a list)"""
    s = build(cards, "Murder")
    ugluk = creature(s, "p1", "Uglúk", "3/3", "Token Legendary Creature — Orc Soldier",
                     text="Whenever another creature you control dies, put a +1/+1 counter on Uglúk. If that creature was a Goblin or Orc, "
                          "put two +1/+1 counters on Uglúk instead.")
    victim = creature(s, "p1", "Victim", type_line=type_line)
    murder = to_hand(s, "Murder")
    mana(s, B=3)
    cast(s, murder, targets=[victim.id])
    assert counters(s, ugluk) == counters_on_it
    replay_matches(s)


ORAN_RIEF_HYDRA = ("Landfall — Whenever a land you control enters, put a +1/+1 counter on this creature. If that land is a Forest, "
                   "put two +1/+1 counters on this creature instead.")


@pytest.mark.parametrize(("land", "expected"), [("Forest", 2), ("Mountain", 1), ("Mutavault", 1)])
def test_landfall_puts_two_counters_instead_for_a_forest(cards, land, expected):
    """Oran-Rief Hydra: the land that entered (an event's object) is tested, not the Hydra."""
    s = build(cards, land)
    hydra = creature(s, "p1", "Hydra", "5/5", "Token Creature — Hydra", text=ORAN_RIEF_HYDRA)
    act(s, "p1", type="play_land", card_id=to_hand(s, land).id)
    pass_until_stack_empty(s)
    assert counters(s, hydra) == expected
    replay_matches(s)


TRIBUTE = "Whenever a creature you control enters, draw a card if its power is 3 or greater. Otherwise, put two +1/+1 counters on it."


def cast_holding(s, name, **mana_cost):
    """Alice casts a creature spell; everyone stops at each object on the stack, so this returns when the creature has resolved and
    its ability waits on the stack (Alice has priority)."""
    c = to_hand(s, name)
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    mana(s, **mana_cost)
    act(s, "p1", type="cast_spell", card_id=c.id)
    until(s, lambda s: s.state.cards[c.id].zone == "p1:battlefield")
    d = s.state.rules.decision
    if d is not None:  # (the target of its ability: the only one there is)
        assert d.kind == "choose_one" and len(d.options) == 1
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert s.state.zones["stack"] and s.state.rules.priority == "p1"
    return c


@pytest.mark.parametrize(("name", "cost", "draws", "counters_on_it"), [
    ("Grizzly Bears", {"G": 1, "C": 1}, 0, 2),  # 2/2: otherwise
    ("Airdrop Aeronauts", {"W": 2, "C": 3}, 1, 0),  # 4/3: draw
])
def test_tribute_to_the_world_tree_draws_or_else_grows_it(cards, name, cost, draws, counters_on_it):
    """Tribute to the World Tree: the entering creature's power decides (the trigger's event object)."""
    s = build(cards, "Tribute to the World Tree", name)
    on_field(s, "Tribute to the World Tree")
    hand = len(zone(s.state, "p1", "hand"))
    entered = cast_holding(s, name, **cost)
    pass_until_stack_empty(s)
    assert counters(s, entered) == counters_on_it
    assert len(zone(s.state, "p1", "hand")) == hand + draws  # (the creature card went from hand to the table: +1 -1)
    replay_matches(s)


def test_tribute_reads_the_power_as_the_trigger_resolves(cards):
    """608.2h: a Giant Growth in response makes the 2/2 a 5/5 before "its power is 3 or greater" is asked."""
    s = build(cards, "Tribute to the World Tree", "Grizzly Bears", "Giant Growth")
    on_field(s, "Tribute to the World Tree")
    hand = len(zone(s.state, "p1", "hand"))
    bears = cast_holding(s, "Grizzly Bears", G=1, C=1)
    growth = to_hand(s, "Giant Growth")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[bears.id])
    pass_until_stack_empty(s)
    assert counters(s, bears) == 0 and ch(s, bears).pt == (5, 5)
    assert len(zone(s.state, "p1", "hand")) == hand + 1  # drew a card (+1); the Bears and the Giant Growth left the hand (+1 each way)
    replay_matches(s)


@pytest.mark.parametrize(("name", "cost", "draws"), [("Grizzly Bears", {"G": 1, "C": 1}, 0), ("Airdrop Aeronauts", {"W": 2, "C": 3}, 1)])
def test_tribute_uses_last_known_power_if_the_creature_left(cards, name, cost, draws):
    """608.2h: the creature is gone when the ability resolves: its power as it last existed decides; the counters find nothing."""
    s = build(cards, "Tribute to the World Tree", name)
    on_field(s, "Tribute to the World Tree")
    hand = len(zone(s.state, "p1", "hand"))
    entered = cast_holding(s, name, **cost)
    act(s, "p1", type="move", card_ids=[entered.id], to={"zone": "graveyard"})
    pass_until_stack_empty(s)
    assert s.state.cards[entered.id].zone == "p1:graveyard" and not s.state.cards[entered.id].counters
    assert len(zone(s.state, "p1", "hand")) == hand + draws  # (the creature card: into the hand and cast again, no change)
    replay_matches(s)


# -- "instead" after history (Morbid, drawn cards), on targets, and with a source that is sacrificed ------------------
@pytest.mark.parametrize(("draws", "dead"), [(0, False), (1, False), (2, True)])
def test_galvanize_five_damage_instead_after_two_draws(cards, draws, dead):
    """Galvanize: "… deals 3 damage to target creature. If you've drawn two or more cards this turn, Galvanize deals 5 damage to that
    creature instead." (the cards drawn this turn, whenever: the turn's history is judged as it resolves)"""
    s = build(cards, "Galvanize", "Forest", "Forest")
    spell = to_hand(s, "Galvanize")
    victim = creature(s, "p2", "Victim", "5/5")
    if draws:
        act(s, "p1", type="draw", count=draws)
    mana(s, R=1, C=1)
    cast(s, spell, targets=[victim.id])
    if dead:
        assert victim.id not in s.state.cards
    else:
        assert s.state.cards[victim.id].damage == 3
    replay_matches(s)


@pytest.mark.parametrize(("someone_died", "survives"), [(False, True), (True, False)])
def test_morbid_minus_thirteen_instead(cards, someone_died, survives):
    """Tragic Banshee: "Morbid — When this creature enters, target creature an opponent controls gets -1/-1 until end of turn. If a
    creature died this turn, that creature gets -13/-13 until end of turn instead." (Bob's 3/3: a 2/2, or dead)"""
    s = build(cards, "Tragic Banshee")
    banshee = to_hand(s, "Tragic Banshee")
    target = creature(s, "p2", "Target", "3/3")
    if someone_died:
        fodder = creature(s, "p1", "Fodder")
        act(s, "p1", type="move", card_ids=[fodder.id], to={"zone": "graveyard"})
    mana(s, B=1, C=4)
    cast(s, banshee)
    assert (target.id in s.state.cards) == survives
    if survives:
        assert ch(s, target).pt == (2, 2)
    replay_matches(s)


def test_morbid_counts_a_creature_that_dies_while_the_ability_waits(cards):
    """608.2c: "If a creature died this turn" is asked as the instruction is carried out, not as the ability triggers."""
    s = build(cards, "Tragic Banshee")
    target = creature(s, "p2", "Target", "3/3")
    fodder = creature(s, "p1", "Fodder")
    banshee = cast_holding(s, "Tragic Banshee", B=1, C=4)
    assert ch(s, target).pt == (3, 3)
    act(s, "p1", type="move", card_ids=[fodder.id], to={"zone": "graveyard"})
    pass_until_stack_empty(s)
    assert target.id not in s.state.cards and s.state.cards[banshee.id].zone == "p1:battlefield"
    replay_matches(s)


@pytest.mark.parametrize(("lands", "damage"), [
    ((), 1),  # no snow Swamp
    (("Token Land — Swamp",), 1),  # a Swamp that isn't snow
    (("Token Snow Land — Forest",), 1),  # snow, but not a Swamp
    (("Token Snow Land — Swamp",), 2),
])
def test_gangrenous_zombies_two_damage_instead_with_a_snow_swamp(cards, lands, damage):
    """Gangrenous Zombies: "{T}, Sacrifice this creature: This creature deals 1 damage to each creature and each player. If you
    control a snow Swamp, this creature deals 2 damage to each creature and each player instead." (the source is gone: 608.2h)"""
    s = sandbox(cards, "Gangrenous Zombies")
    zombies = on_field(s, "Gangrenous Zombies")
    for i, line in enumerate(lands):
        act(s, "p1", type="create_token", player="p1", token={"name": f"Land {i}", "type_line": line})
    hard = creature(s, "p2", "Hard", "3/3")
    soft = creature(s, "p2", "Soft", "2/2")
    turn_on(s)
    act(s, "p1", type="activate_ability", card_id=zombies.id, ability=0)
    pass_until_stack_empty(s)
    assert zombies.id not in s.state.cards or s.state.cards[zombies.id].zone == "p1:graveyard"
    assert life(s, "p1") == 40 - damage and life(s, "p2") == 40 - damage
    assert s.state.cards[hard.id].damage == damage
    assert (soft.id in s.state.cards) == (damage == 1)
    replay_matches(s)


# -- designations the players keep by hand: the city's blessing and the initiative (702.131, 725) -----------------
MAUSOLEUM_HARPY = "Whenever another creature you control dies, if you have the city's blessing, put a +1/+1 counter on this creature."
DUSK_CHARGER = "This creature gets +2/+2 as long as you have the city's blessing."
PASSAGEWAY_SEER = "At the beginning of your end step, if you have the initiative, put a +1/+1 counter on this creature."


def city_blessing(s, pid, value=True):
    act(s, pid, type="city_blessing", player=pid, value=value)


@pytest.mark.parametrize(("holder", "counter"), [("p1", 1), ("p2", 0), (None, 0)])
def test_the_city_s_blessing_gates_a_dies_trigger(cards, holder, counter):
    """Mausoleum Harpy: "you have" means the controller: Bob's blessing is nothing to Alice."""
    s = build(cards, "Murder")
    harpy = creature(s, "p1", "Harpy", "3/3", "Token Creature — Harpy", text=MAUSOLEUM_HARPY)
    victim = creature(s, "p1", "Victim")
    if holder:
        city_blessing(s, holder)
    murder = to_hand(s, "Murder")
    mana(s, B=3)
    cast(s, murder, targets=[victim.id])
    assert counters(s, harpy) == counter
    replay_matches(s)


def test_the_blessing_is_checked_again_as_the_trigger_resolves(cards):
    """603.4: it triggered with the blessing; lost by the time it resolves, nothing happens (it is a designation kept by hand)."""
    s = build(cards, "Murder")
    harpy = creature(s, "p1", "Harpy", "3/3", "Token Creature — Harpy", text=MAUSOLEUM_HARPY)
    victim = creature(s, "p1", "Victim")
    city_blessing(s, "p1")
    murder = to_hand(s, "Murder")
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[victim.id])
    until(s, lambda s: any(e.name == "Harpy" for e in s.state.rules.stack.values()))
    city_blessing(s, "p1", False)
    pass_until_stack_empty(s)
    assert counters(s, harpy) == 0
    replay_matches(s)


def test_the_city_s_blessing_turns_a_static_on_and_off(cards):
    """Dusk Charger (611.3a)."""
    s = build(cards)
    charger = creature(s, "p1", "Charger", "3/3", "Token Creature — Horse", text=DUSK_CHARGER)
    city_blessing(s, "p2")
    assert ch(s, charger).pt == (3, 3)
    city_blessing(s, "p1")
    assert ch(s, charger).pt == (5, 5)
    city_blessing(s, "p1", False)
    assert ch(s, charger).pt == (3, 3)
    replay_matches(s)


def test_activate_only_if_you_have_the_city_s_blessing(cards):
    """Arch of Orazca: "{5}, {T}: Draw a card. Activate only if you have the city's blessing." (602.5b)"""
    s = build(cards, "Arch of Orazca")
    arch = on_field(s, "Arch of Orazca")
    mana(s, C=5)
    with pytest.raises(ActionError, match="only be activated if you have the city's blessing"):
        act(s, "p1", type="activate_ability", card_id=arch.id, ability=2)
    city_blessing(s, "p1")
    hand = len(zone(s.state, "p1", "hand"))
    act(s, "p1", type="activate_ability", card_id=arch.id, ability=2)
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p1", "hand")) == hand + 1
    replay_matches(s)


@pytest.mark.parametrize(("holder", "counter"), [("p1", 1), ("p2", 0), (None, 0)])
def test_the_initiative_gates_an_end_step_trigger(cards, holder, counter):
    """Passageway Seer: "At the beginning of your end step, if you have the initiative, put a +1/+1 counter on this creature." """
    s = sandbox(cards)
    seer = creature(s, "p1", "Seer", text=PASSAGEWAY_SEER)
    act(s, "p1", type="set_initiative", player=holder)
    turn_on(s)
    the_end_step(s)
    assert counters(s, seer) == counter
    replay_matches(s)


# -- whose turn, which permanents, what died or was cast this turn (more forms) ------------------------------------
def test_activate_only_if_it_is_not_your_turn(cards):
    """Ghost Town: "{0}: Return this land to its owner's hand. Activate only if it's not your turn." (602.5b)"""
    s = sandbox(cards, "Ghost Town")
    town = on_field(s, "Ghost Town")
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    with pytest.raises(ActionError, match="only be activated if it's not your turn"):
        act(s, "p1", type="activate_ability", card_id=town.id, ability=1)
    act(s, "p1", type="set_prefs", response="on")
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.rules.priority == "p1", limit=60)
    act(s, "p1", type="activate_ability", card_id=town.id, ability=1)
    pass_until_stack_empty(s)
    assert s.state.cards[town.id].zone == "p1:hand"
    replay_matches(s)


PESTILENCE = "At the beginning of the end step, if no creatures are on the battlefield, sacrifice this enchantment."


@pytest.mark.parametrize(("theirs", "stays"), [(0, False), (1, True)])
def test_no_creatures_on_the_battlefield(cards, theirs, stays):
    """Pestilence: "… if no creatures are on the battlefield" — any player's creature counts (603.4)."""
    s = sandbox(cards)
    pestilence = token_of(s, "p1", "Pestilence", "Token Enchantment — Test", pt="0/0", text=PESTILENCE)
    for i in range(theirs):
        creature(s, "p2", f"Theirs {i}")
    turn_on(s)
    the_end_step(s)
    assert (pestilence.id in s.state.cards) == stays
    replay_matches(s)


DENETHOR = "At the beginning of your end step, if a creature died under your control this turn, create a 1/1 white Human Soldier creature token."


@pytest.mark.parametrize(("owner", "soldiers"), [("p1", 1), ("p2", 0)])
def test_a_creature_died_under_your_control(cards, owner, soldiers):
    """Denethor, Ruling Steward: your creature dying counts, an opponent's doesn't (700.4)."""
    s = sandbox(cards)
    creature(s, "p1", "Denethor", "2/4", "Token Legendary Creature — Human Noble", text=DENETHOR)
    turn_on(s)
    victim = creature(s, owner, "Victim")
    act(s, owner, type="move", card_ids=[victim.id], to={"zone": "graveyard"})
    the_end_step(s)
    assert names_on_field(s).count("Human Soldier") == soldiers
    replay_matches(s)


INGA ="When Inga Rune-Eyes dies, draw three cards if three or more creatures died this turn."


@pytest.mark.parametrize(("others", "draws"), [(1, 0), (2, 3)])
def test_three_or_more_creatures_died_this_turn(cards, others, draws):
    """Inga Rune-Eyes: she counts herself; three die at once to Day of Judgment, or only two."""
    s = build(cards, "Day of Judgment", "Forest", "Forest", "Forest", "Forest")
    creature(s, "p1", "Inga Rune-Eyes", "3/3", "Token Legendary Creature — Human Wizard", text=INGA)
    for i in range(others):
        creature(s, "p2", f"Theirs {i}")
    wrath = to_hand(s, "Day of Judgment")
    hand = len(zone(s.state, "p1", "hand"))
    mana(s, W=2, C=2)
    cast(s, wrath)
    assert len(zone(s.state, "p1", "hand")) == hand - 1 + draws  # (the Day of Judgment left it)
    replay_matches(s)


EDGAR = "At the beginning of your end step, if you didn't cast a spell this turn, put two +1/+1 counters on Edgar."


@pytest.mark.parametrize(("casts", "expected"), [(False, 2), (True, 0)])
def test_you_didnt_cast_a_spell_this_turn(cards, casts, expected):
    """Edgar, Moonlit Sovereign."""
    s = build(cards, "Giant Growth")
    edgar = creature(s, "p1", "Edgar", "4/4", "Token Legendary Creature — Werewolf Noble", text=EDGAR)
    if casts:
        growth = to_hand(s, "Giant Growth")
        mana(s, G=1)
        cast(s, growth, targets=[edgar.id])
    the_end_step(s)
    assert counters(s, edgar) == expected
    replay_matches(s)


def test_a_spell_an_opponent_cast_isnt_yours(cards):
    """Bob's Edgar: Alice casts a spell during Bob's turn — Bob himself cast none."""
    s = build(cards, "Giant Growth")
    edgar = creature(s, "p2", "Edgar", "4/4", "Token Legendary Creature — Werewolf Noble", text=EDGAR)
    growth = to_hand(s, "Giant Growth")
    act(s, "p1", type="set_prefs", response="on")
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.rules.priority == "p1", limit=60)
    mana(s, G=1)
    cast(s, growth, targets=[edgar.id])
    assert s.state.turn.active_player == "p2" and s.state.rules.turn_log.drew == {}
    the_end_step(s)
    assert counters(s, edgar) == 2
    replay_matches(s)


SEE_RED = "At the beginning of your end step, if you didn't attack with a creature this turn, sacrifice this Aura."


@pytest.mark.parametrize("attacks", [True, False])
def test_you_didnt_attack_with_a_creature(cards, attacks):
    """See Red / Curious Obsession (508.1: declaring attackers is what counts). (The token is no Aura, which would fall off at
    once for want of a creature: only its wording matters here.)"""
    s = sandbox(cards)
    aura = token_of(s, "p1", "See Red", "Token Enchantment — Test", pt="0/0", text=SEE_RED)
    bear = creature(s, "p1", "Bear")
    combat_step(s)
    attack(s, *([(bear, "p2")] if attacks else []))
    through_combat(s)
    the_end_step(s)
    assert (aura.id in s.state.cards) == attacks
    replay_matches(s)


def test_the_cost_is_less_if_a_creature_died_this_turn(cards):
    """Bone Picker: "This spell costs {3} less to cast if a creature died this turn." (601.2f)"""
    s = build(cards, "Bone Picker")
    picker = to_hand(s, "Bone Picker")
    mana(s, B=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=picker.id)
    victim = creature(s, "p2", "Victim")
    act(s, "p2", type="move", card_ids=[victim.id], to={"zone": "graveyard"})
    cast(s, picker)
    assert s.state.cards[picker.id].zone == "p1:battlefield"
    replay_matches(s)


@pytest.mark.parametrize("died", [False, True])
def test_bontu_cant_attack_unless_a_creature_died_under_your_control(cards, died):
    """Bontu the Glorified: "Bontu can't attack or block unless a creature died under your control this turn." (508.1c: checked
    as attackers are declared, so the creature dies in the first main phase)"""
    s = sandbox(cards, "Bontu the Glorified")
    bontu = on_field(s, "Bontu the Glorified")
    fodder = creature(s, "p1", "Fodder")
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → main 1
    if died:
        act(s, "p1", type="move", card_ids=[fodder.id], to={"zone": "graveyard"})
    act(s, "p1", type="pass_priority")  # → combat: Alice declares attackers
    eligible = {o.id[2:] for o in s.state.rules.decision.options if o.id.startswith("a:")}
    assert (bontu.id in eligible) == died
    if died:
        attack(s, (bontu, "p2"))
        assert s.state.rules.turn_log.attacked == ["p1"] and s.state.cards[bontu.id].tapped
    else:
        with pytest.raises(ActionError, match="can't attack"):
            attack(s, (bontu, "p2"))
    replay_matches(s)


# -- compound conditions, thresholds, an object that is itself, several opponents -----------------------------------
@pytest.mark.parametrize(("artifact", "enchantment", "drew"), [
    ("p1", "p1", True),
    ("p1", None, False),
    (None, "p1", False),
    ("p2", "p1", False),  # (an opponent's artifact isn't one you control)
    ("p1", "p2", False),
])
def test_you_control_an_artifact_and_an_enchantment(cards, artifact, enchantment, drew):
    """Kami of Terrible Secrets: "When this creature enters, if you control an artifact and an enchantment, you draw a card and you
    gain 1 life." (603.4: both halves)"""
    s = build(cards, "Kami of Terrible Secrets")
    kami = to_hand(s, "Kami of Terrible Secrets")
    if artifact:
        token_of(s, artifact, "Trinket", "Token Artifact — Trinket", pt="0/0")
    if enchantment:
        token_of(s, enchantment, "Charm", "Token Enchantment — Test", pt="0/0")
    hand = len(zone(s.state, "p1", "hand"))
    mana(s, B=1, C=3)
    cast(s, kami)
    assert len(zone(s.state, "p1", "hand")) == hand - 1 + int(drew) and life(s) == 40 + int(drew)
    replay_matches(s)


SIDEWINDER_NAGA = "As long as you control a Desert or there is a Desert card in your graveyard, this creature gets +1/+0 and has trample."


def test_a_desert_or_a_desert_card_in_your_graveyard(cards):
    """Sidewinder Naga: either half is enough; an opponent's graveyard isn't yours."""
    s = build(cards, "Desert", "Desert", p2=("Desert",))
    naga = creature(s, "p1", "Naga", "3/2", "Token Creature — Snake Warrior", text=SIDEWINDER_NAGA)

    def shape():
        return ch(s, naga).pt, "trample" in ch(s, naga).keywords

    assert shape() == ((3, 2), False)
    act(s, "p2", type="move", card_ids=[find(s.state, "Desert", "p2").id], to={"zone": "graveyard"})
    assert shape() == ((3, 2), False)
    first, second = [c for c in s.state.cards.values() if c.name == "Desert" and c.owner == "p1"]
    act(s, "p1", type="move", card_ids=[first.id], to={"zone": "graveyard"})
    assert shape() == ((4, 2), True)
    act(s, "p1", type="move", card_ids=[first.id], to={"zone": "exile"})
    assert shape() == ((3, 2), False)
    act(s, "p1", type="move", card_ids=[second.id], to={"player": "p1", "zone": "battlefield"})
    assert shape() == ((4, 2), True)
    replay_matches(s)


NIMBLE_MONGOOSE = "Threshold — This creature gets +2/+2 as long as there are seven or more cards in your graveyard."


def test_threshold_is_seven_cards_in_your_graveyard(cards):
    """Nimble Mongoose."""
    s = build(cards, p2=("Island",) * 3)
    mongoose = creature(s, "p1", "Mongoose", "1/1", "Token Creature — Mongoose", text=NIMBLE_MONGOOSE)
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"]
    for n, forest in enumerate(forests[:7], start=1):
        act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "graveyard"})
        assert ch(s, mongoose).pt == ((3, 3) if n >= 7 else (1, 1)), n
    for island in [c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2"][:3]:
        act(s, "p2", type="move", card_ids=[island.id], to={"zone": "graveyard"})  # (Bob's cards don't change Alice's count)
    act(s, "p1", type="move", card_ids=[forests[0].id], to={"zone": "exile"})
    assert ch(s, mongoose).pt == (1, 1)
    replay_matches(s)


HIDDEN_GUERRILLAS = "When an opponent casts an artifact spell, if this permanent is an enchantment, it becomes a 5/3 Soldier creature with trample."


def bob_casts_sol_ring(s):
    to_turn(s, 2)  # Bob's first main phase
    ring = to_hand(s, "Sol Ring", "p2")
    mana(s, "p2", C=1)
    act(s, "p2", type="cast_spell", card_id=ring.id)
    settle(s)


@pytest.mark.parametrize(("type_line", "becomes"), [("Token Enchantment — Test", True), ("Token Artifact — Test", False)])
def test_hidden_guerrillas_turns_into_a_creature_only_if_it_is_an_enchantment(cards, type_line, becomes):
    """603.4: "if this permanent is an enchantment" — the source itself is the object tested."""
    s = build(cards, p2=("Sol Ring",))
    guerrillas = token_of(s, "p1", "Hidden Guerrillas", type_line, pt="0/0", text=HIDDEN_GUERRILLAS)
    bob_casts_sol_ring(s)
    assert ("Creature" in ch(s, guerrillas).types) == becomes
    assert (ch(s, guerrillas).pt == (5, 3)) == becomes and ("trample" in ch(s, guerrillas).keywords) == becomes
    replay_matches(s)


def test_hidden_guerrillas_ignores_its_controllers_own_artifact(cards):
    s = build(cards, "Sol Ring")
    guerrillas = token_of(s, "p1", "Hidden Guerrillas", "Token Enchantment — Test", pt="0/0", text=HIDDEN_GUERRILLAS)
    ring = to_hand(s, "Sol Ring")
    mana(s, C=1)
    cast(s, ring)
    assert "Creature" not in ch(s, guerrillas).types
    replay_matches(s)


@pytest.mark.parametrize(("who_lost", "drained"), [("p3", True), ("p2", True), ("p1", False), (None, False)])
def test_each_opponent_loses_two_life_if_one_of_them_lost_life(cards, who_lost, drained):
    """Arrogant Outlaw (three players): "if an opponent lost life this turn" is any one of them; "each opponent" is all."""
    s = sandbox(cards, "Arrogant Outlaw", players=3)
    outlaw = to_hand(s, "Arrogant Outlaw")
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    if who_lost:
        act(s, who_lost, type="life", delta=-1)
    mana(s, B=1, C=2)
    cast(s, outlaw)
    expected = {"p1": 40, "p2": 40, "p3": 40}
    if who_lost:
        expected[who_lost] -= 1
    if drained:
        expected = {"p1": expected["p1"] + 2, "p2": expected["p2"] - 2, "p3": expected["p3"] - 2}
    assert {pid: life(s, pid) for pid in ("p1", "p2", "p3")} == expected
    replay_matches(s)


PURIFYING_DRAGON = ("Whenever this creature attacks, it deals 1 damage to target creature defending player controls. If that creature is a "
                    "Zombie, this creature deals 2 damage to it instead.")


@pytest.mark.parametrize(("type_line", "dead"), [("Token Creature — Zombie", True), ("Token Creature — Human", False)])
def test_an_attack_trigger_deals_two_instead_to_a_zombie(cards, type_line, dead):
    """Purifying Dragon: the target is chosen as it triggers, "that creature" is judged as it resolves."""
    s = sandbox(cards)
    dragon = creature(s, "p1", "Purifying Dragon", "4/3", "Token Creature — Dragon", text="Flying\n" + PURIFYING_DRAGON)
    victim = creature(s, "p2", "Victim", "2/2", type_line)
    combat_step(s)
    attack(s, (dragon, "p2"))
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_one"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    pass_until_stack_empty(s)
    if dead:
        assert victim.id not in s.state.cards
    else:
        assert s.state.cards[victim.id].damage == 1
    replay_matches(s)


# -- rules about combat that read the turn's history or the graveyard as they are applied (611.3a, 508.1c, 509.1b) ---
def to_declare_blockers(s, attacker, *, before_combat=lambda: None):
    """Alice's main phase (``before_combat`` runs there), then her attack at Bob; returns when Bob has to declare blockers."""
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → main 1
    before_combat()
    act(s, "p1", type="pass_priority")  # → combat
    attack(s, (attacker, "p2"))
    d = s.state.rules.decision
    assert d is not None and d.kind == "declare_blockers" and d.player == "p2"


@pytest.mark.parametrize(("draws", "blockable"), [(1, True), (2, False)])
def test_cant_be_blocked_as_long_as_you_have_drawn_two_cards(cards, draws, blockable):
    """Tome Anima: "This creature can't be blocked as long as you've drawn two or more cards this turn." """
    s = sandbox(cards)
    anima = creature(s, "p1", "Tome Anima", "2/3", "Token Creature — Spirit",
                     text="This creature can't be blocked as long as you've drawn two or more cards this turn.")
    wall = creature(s, "p2", "Wall", "0/5")
    to_declare_blockers(s, anima, before_combat=lambda: act(s, "p1", type="draw", count=draws))
    block = [{"blocker_id": wall.id, "attacker_id": anima.id}]
    if blockable:
        act(s, "p2", type="declare_blockers", blocks=block)
        assert s.state.cards[wall.id].damage == 2
    else:
        with pytest.raises(ActionError, match="can't be blocked"):
            act(s, "p2", type="declare_blockers", blocks=block)
    replay_matches(s)


@pytest.mark.parametrize(("spells", "blockable"), [(1, True), (2, False)])
def test_cant_be_blocked_if_you_have_cast_two_spells(cards, spells, blockable):
    """Illvoi Infiltrator: "This creature can't be blocked if you've cast two or more spells this turn." """
    s = sandbox(cards, "Giant Growth", "Giant Growth")
    infiltrator = creature(s, "p1", "Illvoi Infiltrator", "1/3", "Token Creature — Jellyfish Rogue",
                           text="This creature can't be blocked if you've cast two or more spells this turn.")
    wall = creature(s, "p2", "Wall", "0/5")
    growths = [c for c in s.state.cards.values() if c.name == "Giant Growth"]
    for c in growths:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})

    def cast_spells():
        mana(s, G=2)
        for c in growths[:spells]:
            cast(s, c, targets=[infiltrator.id])

    to_declare_blockers(s, infiltrator, before_combat=cast_spells)
    block = [{"blocker_id": wall.id, "attacker_id": infiltrator.id}]
    if blockable:
        act(s, "p2", type="declare_blockers", blocks=block)
    else:
        with pytest.raises(ActionError, match="can't be blocked"):
            act(s, "p2", type="declare_blockers", blocks=block)
    replay_matches(s)


@pytest.mark.parametrize(("cards_in_graveyard", "attacks"), [(6, False), (7, True)])
def test_cant_attack_unless_seven_cards_are_in_your_graveyard(cards, cards_in_graveyard, attacks):
    """Deep-Sea Terror: "This creature can't attack unless there are seven or more cards in your graveyard." (508.1c)"""
    s = sandbox(cards)
    terror = creature(s, "p1", "Deep-Sea Terror", "6/6", "Token Creature — Serpent",
                      text="This creature can't attack unless there are seven or more cards in your graveyard.")
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"]
    for c in forests[:cards_in_graveyard]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → main 1
    act(s, "p1", type="pass_priority")  # → combat (no one is asked to attack if no creature can)
    d = s.state.rules.decision
    eligible = {o.id[2:] for o in d.options if o.id.startswith("a:")} if d is not None and d.kind == "declare_attackers" else set()
    assert (terror.id in eligible) == attacks
    replay_matches(s)


@pytest.mark.parametrize(("in_graveyard", "can_block"), [(6, True), (7, False)])
def test_threshold_creatures_cant_block_this_turn(cards, in_graveyard, can_block):
    """Demoralize: "All creatures gain menace until end of turn. Threshold — If there are seven or more cards in your graveyard,
    creatures can't block this turn." (Demoralize itself is still on the stack as it's read: it isn't one of the seven.)"""
    s = sandbox(cards, "Demoralize")
    spell = to_hand(s, "Demoralize")
    bear = creature(s, "p1", "Bear", "2/6")
    blockers = [creature(s, "p2", f"Blocker {i}") for i in range(2)]
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"]
    for c in forests[:in_graveyard]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})

    def cast_it():
        mana(s, R=1, C=2)
        cast(s, spell)

    to_declare_blockers(s, bear, before_combat=cast_it)
    block = [{"blocker_id": b.id, "attacker_id": bear.id} for b in blockers]  # (two together: menace is met)
    if can_block:
        act(s, "p2", type="declare_blockers", blocks=block)
        assert s.state.cards[bear.id].damage == 4
    else:
        with pytest.raises(ActionError, match="can't block"):
            act(s, "p2", type="declare_blockers", blocks=block)
    replay_matches(s)


ANSWERED_PRAYERS = ("Whenever a creature you control enters, you gain 1 life. If this enchantment isn't a creature, it becomes a 3/3 "
                    "Angel creature with flying in addition to its other types until end of turn.")


@pytest.mark.parametrize(("type_line", "pt", "angel"), [
    ("Token Enchantment — Test", "0/0", True),
    ("Token Enchantment Creature — Test", "1/1", False),  # already a creature: nothing more happens to it
])
def test_answered_prayers_becomes_an_angel_only_if_it_isnt_a_creature(cards, type_line, pt, angel):
    """Answered Prayers: the source is the object tested ("isn't"), and "it" after the condition is the source too — not the creature
    that entered."""
    s = build(cards, "Grizzly Bears")
    prayers = token_of(s, "p1", "Answered Prayers", type_line, pt=pt, text=ANSWERED_PRAYERS)
    bears = to_hand(s, "Grizzly Bears")
    mana(s, G=1, C=1)
    cast(s, bears)
    assert life(s) == 41
    assert (ch(s, prayers).pt == (3, 3)) == angel and ("flying" in ch(s, prayers).keywords) == angel
    assert ch(s, find(s.state, "Grizzly Bears", "p1")).pt == (2, 2)  # (the Bears are not the "it")
    replay_matches(s)


@pytest.mark.parametrize(("type_line", "pt"), [
    ("Token Land — Test", (2, 2)),  # a 0/0 creature with two counters
    ("Token Artifact — Test", (2, 2)),
    ("Token Creature — Test", (4, 4)),  # a 2/2 creature already: two counters, and no 0/0 base
])
def test_tawnos_s_tinkering_animates_what_isnt_a_creature(cards, type_line, pt):
    """Tawnos's Tinkering: "If it isn't a creature, it becomes a 0/0 creature in addition to its other types." ("it": the target)"""
    s = build(cards, "Tawnos's Tinkering")
    target = token_of(s, "p1", "Target", type_line, pt="2/2" if "Creature" in type_line else "0/0")
    spell = to_hand(s, "Tawnos's Tinkering")
    mana(s, G=1, C=3)
    cast(s, spell, targets=[target.id])
    assert ch(s, target).pt == pt and "Creature" in ch(s, target).types
    replay_matches(s)


@pytest.mark.parametrize(("name", "gain"), [("Grizzly Bears", 3), ("Linvala, the Preserver", 0)])
def test_extinguish_the_light_reads_the_mana_value_it_had(cards, name, gain):
    """Extinguish the Light: "Destroy target creature or planeswalker. If its mana value was 3 or less, you gain 3 life." (608.2h:
    as it last existed on the battlefield — a Grizzly Bears is 2, Linvala 6)"""
    s = build(cards, "Extinguish the Light", name)
    victim = on_field(s, name)
    spell = to_hand(s, "Extinguish the Light")
    mana(s, B=2, C=2)
    cast(s, spell, targets=[victim.id])
    assert s.state.cards[victim.id].zone == "p1:graveyard" and life(s) == 40 + gain
    replay_matches(s)


@pytest.mark.parametrize(("power", "trample"), [(9, False), (10, True)])
def test_trample_if_its_power_is_ten_or_greater(cards, power, trample):
    """Witch-Maw Nephilim: "Whenever this creature attacks, it gains trample until end of turn if its power is 10 or greater." """
    s = sandbox(cards)
    nephilim = creature(s, "p1", "Witch-Maw Nephilim", f"{power}/{power}", "Token Creature — Nephilim",
                        text="Whenever this creature attacks, it gains trample until end of turn if its power is 10 or greater.")
    combat_step(s)
    attack(s, (nephilim, "p2"))
    pass_until_stack_empty(s)
    assert ("trample" in ch(s, nephilim).keywords) == trample
    replay_matches(s)


@pytest.mark.parametrize("died", [False, True])
def test_bontu_cant_block_unless_a_creature_died_under_your_control(cards, died):
    """Bontu the Glorified, on Bob's side: the same restriction as he declares blockers (509.1b)."""
    s = sandbox(cards, p2=("Bontu the Glorified",))
    bontu = on_field(s, "Bontu the Glorified", "p2")
    fodder = creature(s, "p2", "Fodder")
    bear = creature(s, "p1", "Bear")
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    if died:
        act(s, "p2", type="move", card_ids=[fodder.id], to={"zone": "graveyard"})
    act(s, "p1", type="pass_priority")  # → combat
    attack(s, (bear, "p2"))
    d = s.state.rules.decision
    assert d is not None and d.kind == "declare_blockers" and d.player == "p2"
    block = [{"blocker_id": bontu.id, "attacker_id": bear.id}]
    if died:
        act(s, "p2", type="declare_blockers", blocks=block)
        assert s.state.cards[bontu.id].damage == 2  # (it blocked the 2/2: combat damage went on)
    else:
        with pytest.raises(ActionError, match="can't block"):
            act(s, "p2", type="declare_blockers", blocks=block)
    replay_matches(s)


# -- what is never guessed (the ability stays manual: "wrong automation is worse than manual") --------------------
REFUSED = [
    # (why, the wording, the same wording with only a condition the engine reads: it is automated)
    # (how the spell was cast: read since wave 3R1, tests/test_rules_refused_r1.py)
    # (what keyword abilities the creature has: read since wave 3R1, tests/test_rules_refused_r1.py)
    ("an 'instead' that might replace only part of the sentence before it",
     "You draw two cards and you lose 2 life. If you control a Forest, you draw three cards instead.",
     "You draw two cards and you lose 2 life. If you control a Forest, you draw three cards and you lose 3 life instead."),
    ("a chain of 'instead' clauses",
     "Draw a card. If you control a Forest, draw two cards instead. If you control a Swamp, draw three cards instead.",
     "Draw a card. If you control a Forest, draw two cards instead."),
    ("an 'instead' with a target of its own (115.3: chosen whether or not it applies)",
     "Destroy target creature. If you control a Forest, exile target artifact instead.",
     "Destroy target creature. If you control a Forest, destroy all creatures instead."),
    ("'Otherwise' with no 'If' sentence before it to belong to",
     "Draw a card. Otherwise, discard a card.",
     "If you control a Forest, draw a card. Otherwise, discard a card."),
    ("a lead of several instructions: which of them is the condition about?",
     "Draw a card and you gain 1 life if you control a Forest.",
     "Draw a card if you control a Forest."),
    ("an 'instead' pronoun naming what the instruction it replaces would have moved — Consign to Dream",
     "Destroy target creature. If you control a Forest, exile it instead.",
     "Destroy target creature. If you control a Forest, destroy all creatures instead."),
    ("'other' than what? (the tokens the spell made, not the source) — Martial Coup",
     "Create X 1/1 white Soldier creature tokens. If X is 5 or more, destroy all other creatures.",
     "Create X 1/1 white Soldier creature tokens. If X is 5 or more, destroy all creatures."),
]


@pytest.mark.parametrize(("why", "text", "control"), REFUSED, ids=[r[0][:40] for r in REFUSED])
def test_forms_that_are_not_guessed(why, text, control):
    assert scripts.parse_effects(control) is not None, "the control wording should be read"
    assert scripts.parse_effects(text) is None, why


@pytest.mark.parametrize(("text", "piece"), [
    ("This creature gets +1/+1 until end of turn. If mana from a Treasure was spent to activate this ability, put a +1/+1 counter on "
     "this creature instead.", "mana"),  # Jetmir's Fixer
    ("Target creature gets -2/-2 until end of turn. If it's night, that creature gets -13/-13 until end of turn instead.", "day/night"),  # Olivia's Midnight Ambush
])
def test_refused_wordings_are_registered_with_their_reason(text, piece):
    reason = coverage.refusal(text)
    assert reason is not None and piece in reason, text
    assert scripts.parse_effects(text) is None


@pytest.mark.parametrize("name", ["Martial Coup"])
def test_the_cards_with_those_forms_stay_partial(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "PARTIAL"


def test_a_static_with_a_history_condition_is_still_read_by_its_own_grammar():
    """The same wording in a static ability ("as long as …") reads through conditions.parse too (611.3a)."""
    assert scripts.parse_anthem("~ gets +2/+0 as long as you've drawn two or more cards this turn.") is not None
    assert scripts.parse_anthem("~ gets +2/+0 as long as it's a land card.") is None  # (object wording: a static has no object "it")


COVERED = [  # every one of these has its scenarios above (both branches of each condition)
    "Life Goes On", "Lightning Dart", "Death's Caress", "Blot Out the Sky", "Mardu Hordechief", "Bone Picker", "Airdrop Aeronauts",
    "Gravelighter", "Fathom Fleet Boarder", "Coiling Oracle", "Scythe Tiger", "Masticore", "Stolen Vitality", "Linvala, the Preserver",
    "Loyal Drake", "Sphinx Sovereign", "Scavenging Ooze", "Holy Justiciar", "Bontu the Glorified", "Painful Quandary",
    "Spelltithe Enforcer", "For the Family", "Cinderclasm", "Arrogant Outlaw", "Soul Swallower", "Hidden Guerrillas",
    "Overgrowth Elemental", "Elder Cathar", "Tribute to the World Tree", "Ghost Town", "Kami of Terrible Secrets", "Galvanize",
    "Tragic Banshee", "Gangrenous Zombies",
]


@pytest.mark.parametrize("name", COVERED)
def test_coverage_says_full_only_for_the_cards_tested_here(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- "You may [do A]. If you do, [B]." : one choice, as a whole-ability "you may" (608.2d) ------------------------
def answer_may(s, answer="yes", limit=30):
    """Resolve the stack, answering a "you may" with ``answer`` (any other choice: the first option offered)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [answer] if d.kind == "confirm" else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


RIDDLESMITH = "Whenever you cast an artifact spell, you may draw a card. If you do, discard a card."


@pytest.mark.parametrize("answer", ["yes", "no"])
def test_you_may_draw_and_if_you_do_discard(cards, answer):
    """Riddlesmith: yes — draw a card, then discard a card; no — neither (one choice covers both)."""
    s = build(cards, "Sol Ring", "Forest", "Forest")
    creature(s, "p1", "Riddlesmith", "2/1", "Token Creature — Human Artificer", text=RIDDLESMITH)
    ring = to_hand(s, "Sol Ring")
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=ring.id)
    hand, library, graveyard = (len(zone(s.state, "p1", z)) for z in ("hand", "library", "graveyard"))
    answer_may(s, answer)
    assert len(zone(s.state, "p1", "hand")) == hand  # drew one and discarded one, or did neither
    assert len(zone(s.state, "p1", "library")) == library - (answer == "yes")
    assert len(zone(s.state, "p1", "graveyard")) == graveyard + (answer == "yes")
    replay_matches(s)


@pytest.mark.parametrize(("answer", "gain"), [("yes", 2), ("no", 0)])
def test_you_may_exile_a_creature_card_and_if_you_do_gain_life(cards, answer, gain):
    """Carrion Imp."""
    s = build(cards, "Carrion Imp", "Grizzly Bears")
    bears = find(s.state, "Grizzly Bears", "p1")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    imp = to_hand(s, "Carrion Imp")
    mana(s, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=imp.id)
    answer_may(s, answer)
    assert (s.state.cards[bears.id].zone == "p1:exile") == (answer == "yes") and life(s) == 40 + gain
    replay_matches(s)


def test_no_creature_card_in_any_graveyard_means_nothing_to_choose(cards):
    s = build(cards, "Carrion Imp", "Giant Growth")
    act(s, "p1", type="move", card_ids=[find(s.state, "Giant Growth", "p1").id], to={"zone": "graveyard"})  # (not a creature card)
    imp = to_hand(s, "Carrion Imp")
    mana(s, B=1, C=3)
    cast(s, imp)
    assert s.state.rules.decision is None and life(s) == 40 and s.state.cards[imp.id].zone == "p1:battlefield"
    replay_matches(s)


@pytest.mark.parametrize(("name", "answer", "gain"), [
    ("Linvala, the Preserver", "yes", 6), ("Grizzly Bears", "yes", 2), ("Linvala, the Preserver", "no", 0)])
def test_you_may_return_another_creature_and_if_you_do_gain_life_equal_to_its_mana_value(cards, name, answer, gain):
    """Niambi, Esteemed Speaker: the returned creature's mana value, read as it last existed (608.2h)."""
    s = build(cards, "Niambi, Esteemed Speaker", name)
    friend = on_field(s, name)
    niambi = to_hand(s, "Niambi, Esteemed Speaker")
    mana(s, W=1, U=1)
    act(s, "p1", type="cast_spell", card_id=niambi.id)
    answer_may(s, answer)
    assert (s.state.cards[friend.id].zone == "p1:hand") == (answer == "yes") and life(s) == 40 + gain
    replay_matches(s)


def test_the_prompt_of_an_optional_ability_names_an_amount_worked_out_later_as_x():
    assert effects.describe([{"do": "bounce", "who": "target"}, {"do": "gain_life", "who": "you", "n": {"mana_value": "ref:e0"}}]) \
        == "Bounce, gain x life"
    assert effects.describe([{"do": "draw", "who": "you", "n": 1}, {"do": "discard", "who": "you", "n": 1}]) == "Draw 1 card(s), discard 1"


@pytest.mark.parametrize(("answer", "wolves"), [("yes", 1), ("no", 0)])
def test_you_may_create_a_token_and_if_you_do_put_a_counter_on_this_creature(cards, answer, wolves):
    """Turntimber Ranger."""
    s = build(cards, "Turntimber Ranger")
    ranger = to_hand(s, "Turntimber Ranger")
    mana(s, G=2, C=3)
    act(s, "p1", type="cast_spell", card_id=ranger.id)
    answer_may(s, answer)
    assert names_on_field(s).count("Wolf") == wolves and counters(s, ranger) == wolves
    replay_matches(s)


ASTRAL_SLIDE = ("Whenever a player cycles a card, you may exile target creature. If you do, return that card to the battlefield under "
                "its owner's control at the beginning of the next end step.")


@pytest.mark.parametrize("answer", ["yes", "no"])
def test_you_may_exile_a_creature_and_if_you_do_it_returns_at_the_next_end_step(cards, answer):
    """Astral Slide: the delayed return belongs to the choice (603.7): only the exiled card comes back."""
    s = build(cards, "Barren Moor", p2=("Grizzly Bears",))
    token_of(s, "p1", "Astral Slide", "Token Enchantment — Test", pt="0/0", text=ASTRAL_SLIDE)
    bears = on_field(s, "Grizzly Bears", "p2")
    moor = to_hand(s, "Barren Moor")
    mana(s, B=1)
    act(s, "p1", type="activate_ability", card_id=moor.id, ability=2)  # Cycling {B}
    answer_may(s, answer)
    assert s.state.cards[bears.id].zone == ("p2:exile" if answer == "yes" else "p2:battlefield")
    the_end_step(s)
    assert s.state.cards[bears.id].zone == "p2:battlefield"
    replay_matches(s)


@pytest.mark.parametrize(("text", "it"), [
    ("You may draw a card. If you don't, discard a card.", None),  # (no such "If you don't" without a payment)
    ("You may draw a card. If you do, you may discard a card.", None),  # (a second choice)
    ("You may draw a card. If you do, discard a card. You gain 1 life.", None),  # (a third sentence would be optional too)
    ("You gain 1 life. You may draw a card. If you do, discard a card.", None),  # (a "you may" that isn't the whole ability)
    ("You may draw X cards. If you do, discard a card.", None),  # (a count that could be zero)
    ("You may draw a card. If you do, target creature gets +1/+1 until end of turn.", None),  # (B's target)
    ("You may exile it. If you do, draw a card.", "self_gone"),  # Academy Rector: "it" may have left the graveyard
])
def test_optional_then_if_you_do_forms_that_are_not_read(text, it):
    assert scripts.parse_effects(text, it=it) is None


def test_academy_rector_stays_manual(cards):
    assert coverage.of_card_data(cards.resolve("Academy Rector")).level == "PARTIAL"


# -- saved games, undo and redo ---------------------------------------------------------------------------
def test_undo_and_redo_take_the_turn_log_with_them(cards):
    """The history of the turn is part of the recorded state: taking a move back takes its record back."""
    s = build(cards, "Life Goes On")
    spell = to_hand(s, "Life Goes On")
    bear = creature(s, "p1", "Bear")
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "graveyard"})
    assert len(s.state.rules.turn_log.left) == 1
    s.undo("p1")
    assert s.state.rules.turn_log.left == [] and bear.id in s.state.cards
    s.redo("p1")
    assert len(s.state.rules.turn_log.left) == 1 and bear.id not in s.state.cards
    mana(s, G=1)
    cast(s, spell)
    assert life(s) == 48
    replay_matches(s)


def test_a_game_saved_before_the_turn_log_still_loads(cards):
    from app.game.state import GameState

    s = build(cards)
    dumped = s.state.model_dump(mode="json")
    del dumped["rules"]["turn_log"], dumped["rules"]["last_turn_log"]
    loaded = GameState.model_validate(dumped)
    assert loaded.rules.turn_log.lost == {} and loaded.rules.last_turn_log is None


def test_the_turn_log_survives_a_reload_in_the_middle_of_the_turn(cards):
    s = build(cards, "Life Goes On", "Forest")
    spell = to_hand(s, "Life Goes On")
    bear = creature(s, "p2", "Bear")
    act(s, "p2", type="move", card_ids=[bear.id], to={"zone": "graveyard"})
    act(s, "p1", type="life", delta=-2)
    act(s, "p1", type="draw", count=2)
    t = reloaded(s)
    assert t.state.rules.turn_log == s.state.rules.turn_log
    assert t.state.rules.turn_log.lost == {"p1": 2} and t.state.rules.turn_log.drew == {"p1": 2}
    mana(t, G=1)
    cast(t, spell)
    assert life(t) == 46  # 40 - 2 + 8 (a creature died this turn, as the reloaded game remembers)
    replay_matches(t)

# -- "If you do" reads what the optional action actually did (608.2c; 903.9b; 121.2) ---------------------------
def test_if_you_do_after_a_bounced_commander_goes_to_the_command_zone_does_nothing(cards):
    """Niambi: the commander went to the command zone instead of the hand (903.9b): nothing was returned, so no life."""
    s = build(cards, "Niambi, Esteemed Speaker")
    krenko = find(s.state, "Krenko, Mob Boss", "p1")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "battlefield"})
    bouncer = token_of(s, "p1", "Bouncer", "Token Artifact — Test", pt="0/0", text="{1}: Return target creature to its owner's hand.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=bouncer.id, ability=0, targets=[krenko.id])
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"], remember="yes_this_turn")  # (903.9b, from now on this turn)
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "battlefield"})
    niambi = to_hand(s, "Niambi, Esteemed Speaker")
    mana(s, W=1, U=1)
    act(s, "p1", type="cast_spell", card_id=niambi.id)
    answer_may(s, "yes")
    assert s.state.cards[krenko.id].zone == "p1:command" and life(s) == 40
    replay_matches(s)


def test_if_you_do_after_a_draw_from_an_empty_library_discards_nothing(cards):
    """Riddlesmith with an empty library: no card was drawn, so nothing is discarded."""
    s = build(cards, "Sol Ring")
    creature(s, "p1", "Riddlesmith", "2/1", "Token Creature — Human Artificer", text=RIDDLESMITH)
    ring = to_hand(s, "Sol Ring")
    to_hand(s, "Forest")  # (a card to discard, were one drawn)
    for c in list(zone(s.state, "p1", "library")):
        act(s, "p1", type="move", card_ids=[c], to={"zone": "exile"})
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=ring.id)
    answer_may(s, "yes")
    text = " ".join((part.t or "") for entry in s.state.log for part in entry.parts).lower()
    assert "loses the game (drew from an empty library)" in text and "discard" not in text  # (no card drawn, none discarded)
    replay_matches(s)
