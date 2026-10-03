"""Wave 6C: token creation and pump wordings, researched against CR 2026-09-25.

* Temporary grants of the evasion and damage keywords the engine reads from a creature's keywords (613.1f): fear
  (702.36), shadow (702.28), horsemanship (702.31), intimidate (702.13), skulk (702.118), landwalk (702.14), wither
  (702.80), infect (702.90): Tainted Strike, Shadow Rift.
* Role tokens (303.7, 111.10j-r): created attached (303.4f), not created with nothing to enchant (303.4i), one Role per
  player per permanent (704.5z): Monstrous Rage, Royal Treatment, Shatter the Oath.
* Decayed (702.147): Rotten Reunion, Jadar.
* Token wordings (111.4 names, 105.1 "all colors"): Tolsimir Wolfblood, Army of the Damned, Moogles' Valor, Godsire,
  Crib Swap, The Hive; Field of the Dead ("lands with different names", 201.2).
* Anthems over type lists and invariant plurals; counts of attached Auras / Equipment and of creatures sharing a creature
  type with the object modified (613.4c, 611.3a): Vodalian Hexcatcher, Nightpack Ambusher, Kor Spiritdancer, Champion of
  the Flame, Coat of Arms; a pump with the source's damage (Firedrinker Satyr).

Every scenario checks the replay; the longer ones also reload the game from its saved history.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage, roles, sba, statics, token_grammar
from app.rules.combat import block_problem
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_attachments import token
from tests.test_rules_conditionals import settle, through_combat, token_of, until
from tests.test_rules_effects import replay_matches

# Real Oracle wording (the local card database, current).
EXTRA = [
    card('Tainted Strike', set_code='tst', number='W01', mana_cost='{B}', cmc=1.0, type_line='Instant', oracle_text='Target creature gets +1/+0 and gains infect until end of turn. (It deals damage to creatures in the form of -1/-1 counters and to players in the form of poison counters.)', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Shadow Rift', set_code='tst', number='W02', mana_cost='{U}', cmc=1.0, type_line='Instant', oracle_text='Target creature gains shadow until end of turn. (It can block or be blocked by only creatures with shadow.)\nDraw a card.', colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Monstrous Rage', set_code='tst', number='W03', mana_cost='{R}', cmc=1.0, type_line='Instant', oracle_text='Target creature gets +2/+0 until end of turn. Create a Monster Role token attached to it. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has trample.)', colors=['R'], color_identity=['R'], keywords=['Role token']),  # noqa: E501
    card('Royal Treatment', set_code='tst', number='W04', mana_cost='{G}', cmc=1.0, type_line='Instant', oracle_text='Target creature you control gains hexproof until end of turn. Create a Royal Role token attached to that creature. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has ward {1}.)', colors=['G'], color_identity=['G'], keywords=['Role token']),  # noqa: E501
    card('Shatter the Oath', set_code='tst', number='W05', mana_cost='{3}{B}{B}', cmc=5.0, type_line='Sorcery', oracle_text='Destroy target creature or enchantment. Create a Wicked Role token attached to up to one target creature you control. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1. When this token is put into a graveyard, each opponent loses 1 life.)', colors=['B'], color_identity=['B'], keywords=['Role token']),  # noqa: E501
    card('Rotten Reunion', set_code='tst', number='W06', mana_cost='{B}', cmc=1.0, type_line='Instant', oracle_text="Exile up to one target card from a graveyard. Create a 2/2 black Zombie creature token with decayed. (It can't block. When it attacks, sacrifice it at end of combat.)\nFlashback {1}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.)", colors=['B'], color_identity=['B'], keywords=['Flashback']),  # noqa: E501
    card('Jadar, Ghoulcaller of Nephalia', set_code='tst', number='W07', mana_cost='{1}{B}', cmc=2.0, type_line='Legendary Creature — Human Wizard', oracle_text="At the beginning of your end step, if you control no creatures with decayed, create a 2/2 black Zombie creature token with decayed. (It can't block. When it attacks, sacrifice it at end of combat.)", power='1', toughness='1', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Tolsimir Wolfblood', set_code='tst', number='W08', mana_cost='{4}{G}{W}', cmc=6.0, type_line='Legendary Creature — Elf Warrior', oracle_text='Other green creatures you control get +1/+1.\nOther white creatures you control get +1/+1.\n{T}: Create Voja, a legendary 2/2 green and white Wolf creature token.', power='3', toughness='4', colors=['G', 'W'], color_identity=['G', 'W'], keywords=[]),  # noqa: E501
    card('Army of the Damned', set_code='tst', number='W09', mana_cost='{5}{B}{B}{B}', cmc=8.0, type_line='Sorcery', oracle_text='Create thirteen tapped 2/2 black Zombie creature tokens.\nFlashback {7}{B}{B}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.)', colors=['B'], color_identity=['B'], keywords=['Flashback']),  # noqa: E501
    card("Moogles' Valor", set_code='tst', number='W10', mana_cost='{3}{W}{W}', cmc=5.0, type_line='Instant', oracle_text='For each creature you control, create a 1/2 white Moogle creature token with lifelink. Then creatures you control gain indestructible until end of turn.', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card('Godsire', set_code='tst', number='W11', mana_cost='{4}{R}{G}{G}{W}', cmc=8.0, type_line='Creature — Beast', oracle_text="Vigilance\n{T}: Create an 8/8 Beast creature token that's red, green, and white.", power='8', toughness='8', colors=['G', 'R', 'W'], color_identity=['G', 'R', 'W'], keywords=['Vigilance']),  # noqa: E501
    card('Crib Swap', set_code='tst', number='W12', mana_cost='{2}{W}', cmc=3.0, type_line='Kindred Instant — Shapeshifter', oracle_text='Changeling (This card is every creature type.)\nExile target creature. Its controller creates a 1/1 colorless Shapeshifter creature token with changeling.', colors=['W'], color_identity=['W'], keywords=['Changeling']),  # noqa: E501
    card('The Hive', set_code='tst', number='W13', mana_cost='{5}', cmc=5.0, type_line='Artifact', oracle_text="{5}, {T}: Create a 1/1 colorless Insect artifact creature token with flying named Wasp. (It can't be blocked except by creatures with flying or reach.)", colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Field of the Dead', set_code='tst', number='W14', mana_cost='', cmc=0.0, type_line='Land', oracle_text='This land enters tapped.\n{T}: Add {C}.\nWhenever this land or another land you control enters, if you control seven or more lands with different names, create a 2/2 black Zombie creature token.', colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Vodalian Hexcatcher', set_code='tst', number='W15', mana_cost='{1}{U}', cmc=2.0, type_line='Creature — Merfolk Wizard', oracle_text='Flash\nOther Merfolk you control get +1/+1.\nSacrifice a Merfolk: Counter target noncreature spell unless its controller pays {1}.', power='1', toughness='1', colors=['U'], color_identity=['U'], keywords=['Flash']),  # noqa: E501
    card('Nightpack Ambusher', set_code='tst', number='W16', mana_cost='{2}{G}{G}', cmc=4.0, type_line='Creature — Wolf', oracle_text="Flash\nOther Wolves and Werewolves you control get +1/+1.\nAt the beginning of your end step, if you didn't cast a spell this turn, create a 2/2 green Wolf creature token.", power='4', toughness='4', colors=['G'], color_identity=['G'], keywords=['Flash']),  # noqa: E501
    card('Kor Spiritdancer', set_code='tst', number='W17', mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Kor Wizard', oracle_text='This creature gets +2/+2 for each Aura attached to it.\nWhenever you cast an Aura spell, you may draw a card.', power='0', toughness='2', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card('Coat of Arms', set_code='tst', number='W18', mana_cost='{5}', cmc=5.0, type_line='Artifact', oracle_text='Each creature gets +1/+1 for each other creature on the battlefield that shares at least one creature type with it. (For example, if two Goblin Warriors and a Goblin Shaman are on the battlefield, each gets +2/+2.)', colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Firedrinker Satyr', set_code='tst', number='W19', mana_cost='{R}', cmc=1.0, type_line='Creature — Satyr Shaman', oracle_text='Whenever this creature is dealt damage, it deals that much damage to you.\n{1}{R}: This creature gets +1/+0 until end of turn and deals 1 damage to you.', power='2', toughness='1', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Champion of the Flame', set_code='tst', number='W20', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Human Warrior', oracle_text='Trample\nThis creature gets +2/+2 for each Aura and Equipment attached to it.', power='1', toughness='1', colors=['R'], color_identity=['R'], keywords=['Trample']),  # noqa: E501
    card('Kher Keep', set_code='tst', number='W21', mana_cost='', cmc=0.0, type_line='Legendary Land', oracle_text='{T}: Add {C}.\n{1}{R}, {T}: Create a 0/1 red Kobold creature token named Kobolds of Kher Keep.', colors=[], color_identity=['R'], keywords=[]),  # noqa: E501
    card("Ezuri's Predation", set_code='tst', number='W22', mana_cost='{5}{G}{G}{G}', cmc=8.0, type_line='Sorcery', oracle_text='For each creature your opponents control, create a 4/4 green Phyrexian Beast creature token. Each of those tokens fights a different one of those creatures.', colors=['G'], color_identity=['G'], keywords=['Fight']),  # noqa: E501
    card('Become Brutes', set_code='tst', number='W23', mana_cost='{1}{R}', cmc=2.0, type_line='Sorcery', oracle_text='One or two target creatures each gain haste until end of turn. For each of those creatures, create a Monster Role token attached to it. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has trample.)', colors=['R'], color_identity=['R'], keywords=['Role token']),  # noqa: E501
    card('The Great Mound', set_code='tst', number='W31', mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}: Add {C}.\n{3}, {T}: Create a tapped Vibranium token. (It\'s an artifact with indestructible and "{T}: Add {C}. This mana can\'t be spent to cast a nonartifact spell.")\n{6}, {T}: Draw a card.', colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Hansk, Slayer Zealot', set_code='tst', number='W32', mana_cost='{2}{R}{G}', cmc=4.0, type_line='Legendary Creature — Human Archer', oracle_text="At the beginning of your upkeep, target opponent creates three Walker tokens. (They're 2/2 black Zombie creatures.)\n{T}: Hansk, Slayer Zealot deals 2 damage to target creature.\nWhenever a Zombie an opponent controls dies, draw a card.", power='4', toughness='4', colors=['G', 'R'], color_identity=['G', 'R'], keywords=[]),  # noqa: E501
    card('Mobile Fort', set_code='tst', number='W33', mana_cost='{4}', cmc=4.0, type_line='Artifact Creature — Wall', oracle_text="Defender (This creature can't attack.)\n{3}: This creature gets +3/-1 until end of turn and can attack this turn as though it didn't have defender. Activate only once each turn.", power='0', toughness='6', colors=[], color_identity=[], keywords=['Defender']),  # noqa: E501
    card('Sporecrown Thallid', set_code='tst', number='W34', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Fungus', oracle_text="Each other creature you control that's a Fungus or Saproling gets +1/+1.", power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Lovisa Coldeyes', set_code='tst', number='W35', mana_cost='{3}{R}{R}', cmc=5.0, type_line='Legendary Creature — Human', oracle_text="Each creature that's a Barbarian, a Warrior, or a Berserker gets +2/+2 and has haste.", power='3', toughness='3', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Painsmith', set_code='tst', number='W41', mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Human Artificer', oracle_text='Whenever you cast an artifact spell, you may have target creature get +2/+0 and gain deathtouch until end of turn.', power='2', toughness='1', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
]
FULL = ["Tainted Strike", "Shadow Rift", "Monstrous Rage", "Royal Treatment", "Shatter the Oath", "Rotten Reunion",
        "Jadar, Ghoulcaller of Nephalia", "Tolsimir Wolfblood", "Army of the Damned", "Moogles' Valor", "Godsire",
        "Crib Swap", "The Hive", "Field of the Dead", "Vodalian Hexcatcher", "Nightpack Ambusher", "Kor Spiritdancer",
        "Coat of Arms", "Firedrinker Satyr", "Champion of the Flame", "The Great Mound", "Hansk, Slayer Zealot",
        "Mobile Fort", "Sporecrown Thallid", "Lovisa Coldeyes", "Painsmith"]
STILL_MANUAL = {
    "Kher Keep": "Kobolds of",  # (the token's name holds the card's own name: not read)
    "Ezuri's Predation": "fights a different one",  # (pairing each token with a different creature: refused)
    "Become Brutes": "For each of those creatures",  # (a Role for each of several objects: refused)
}


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def reloaded(s):
    """The table as a fresh session rebuilt from the saved history (a save and a load)."""
    return GameSession(s.history.rebuild(), cards=s.cards)


def build(cards, *names, forests=9):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (forests, "Forest")])
    seats = [PlayerSetup("Alice", cards=alice),
             PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")]))]
    state = enable(new_game(seats, shuffle=False))
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def card_named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def to_hand(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return c


def put(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def mana(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def pt(s, c):
    card = s.state.cards[c.id]
    ch = Plan(s.state, "p1", s.cards, None).ch(card)
    return sba.power(card, ch), sba.toughness(card, ch)


def chars(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def on_field(s, pid="p1"):
    return [s.state.cards[i] for i in s.state.zones[f"{pid}:battlefield"]]


def tokens(s, pid="p1"):
    return [c for c in on_field(s, pid) if c.is_token]


def to_attack(s):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")


# -- coverage ----------------------------------------------------------------------------------------------------
def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
            assert coverage.of_characteristics(chs).level == "FULL", (c["name"], coverage.of_characteristics(chs).manual_parts)


def test_still_manual_lines():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] not in STILL_MANUAL:
            continue
        chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
        level = coverage.of_characteristics(chs)
        assert level.level != "FULL", c["name"]
        assert STILL_MANUAL[c["name"]] in " ".join(level.manual_parts), (c["name"], level.manual_parts)


@pytest.mark.parametrize("text", [
    "create a 2/2 Zombie creature token.",  # (no color said at all)
    "create a 2/2 black Zombie creature token that's red.",  # (the colors said twice)
    "create a 1/1 red Goblin creature token named Kobolds of ~.",  # (the card's own name in the token's)
    "create Voja, a legendary 2/2 green Wolf creature token for each Forest you control.",  # (one named legend)
    "create a 1/1 Fish creature token that's all colors with flying.",
])
def test_refused_token_wordings(text):
    assert token_grammar.parse(text) is None


def test_token_wordings_read():
    voja = token_grammar.parse("create Voja, Friend to Elves, a legendary 3/3 green and white Wolf creature token")
    assert voja is not None and voja[0]["token"]["name"] == "Voja, Friend to Elves"
    assert voja[0]["token"]["type_line"] == "Legendary Token Creature — Wolf" and voja[0]["n"] == 1
    wasp = token_grammar.parse("create a 1/1 colorless Insect artifact creature token with flying named Wasp")
    assert wasp is not None and wasp[0]["token"]["name"] == "Wasp" and wasp[0]["token"]["text"] == "Flying"
    every = token_grammar.parse("create a 4/4 Dragon creature token named Reliquary Dragon that's all colors")
    assert every is not None and every[0]["token"]["colors"] == list("WUBRG")
    each = token_grammar.parse("for each creature your opponents control, create a 4/4 green Phyrexian Beast creature token")
    assert each is not None and each[0]["n"] == {"count": 'sel:{"controller":"opponent","types":["Creature"]}'}


def test_anthem_subjects():
    merfolk = statics.parse("Other Merfolk you control get +1/+1.")
    assert merfolk is not None and merfolk["who"] == 'sel:{"controller":"you","other":true,"subtypes":["Merfolk"]}'
    wolves = statics.parse("Other Wolves and Werewolves you control get +1/+1.")
    assert wolves is not None and sorted(json.loads(wolves["who"][4:])["subtypes"]) == ["Werewolf", "Wolf"]
    assert statics.parse("Other Merfolk you control gets +1/+1.") is None  # (a singular verb: not a group)
    assert statics.parse("Skeletons you control and other Zombies you control get +1/+1.") is None


# -- temporary grants of the evasion and damage keywords ---------------------------------------------------------
def test_tainted_strike_gives_infect_until_end_of_turn(cards):
    """702.90: the creature deals combat damage to a player as poison counters; the grant ends with the turn (514.2)."""
    s = build(cards, "Tainted Strike")
    bear = token(s, "p1", "Bear", "2/2", "Haste")
    to_hand(s, "Tainted Strike")
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Tainted Strike").id, targets=[bear.id])
    settle(s)
    assert "infect" in chars(s, bear).keywords and pt(s, bear) == (3, 2)
    to_attack(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    through_combat(s)
    assert s.state.players["p2"].resources.get("poison") == 3 and s.state.players["p2"].life == 40
    replay_matches(s)
    replay_matches(reloaded(s))
    until(s, lambda s: s.state.turn.number == 2)
    assert "infect" not in chars(s, bear).keywords


def test_shadow_rift_attacker_cant_be_blocked_by_a_creature_without_shadow(cards):
    s = build(cards, "Shadow Rift")
    bear = token(s, "p1", "Bear", "2/2", "Haste")
    wall = token(s, "p2", "Wall", "0/4", "Defender")
    to_hand(s, "Shadow Rift")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Shadow Rift").id, targets=[bear.id])
    settle(s)
    plan = Plan(s.state, "p1", s.cards, None)
    problem = block_problem(s.state, s.state.cards[wall.id], plan.ch(s.state.cards[wall.id]), s.state.cards[bear.id],
                            plan.ch(s.state.cards[bear.id]), s.cards)
    assert problem is not None and "shadow" in problem
    replay_matches(s)


# -- Role tokens (303.7, 111.10j-r, 704.5z) ------------------------------------------------------------------------
def roles_on(s, c):
    return [x for x in s.state.cards.values() if x.attached_to == c.id and x.zone.endswith(":battlefield")]


def test_monstrous_rage_creates_a_monster_role_attached(cards):
    s = build(cards, "Monstrous Rage")
    bear = token(s, "p1", "Bear", "2/2")
    to_hand(s, "Monstrous Rage")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Monstrous Rage").id, targets=[bear.id])
    settle(s)
    [role] = roles_on(s, bear)
    assert role.is_token and role.name == "Monster" and role.controller == "p1"
    rch = chars(s, role)
    assert {"Aura", "Role"} <= rch.subtypes and "Enchantment" in rch.types and not rch.colors
    assert pt(s, bear) == (5, 3) and "trample" in chars(s, bear).keywords  # +2/+0 until end of turn, +1/+1 from the Role
    replay_matches(s)
    s = reloaded(s)
    until(s, lambda s: s.state.turn.number == 2)
    assert pt(s, bear) == (3, 3) and roles_on(s, bear)  # (the Role stays)
    replay_matches(s)


def test_a_newer_role_replaces_the_older_one_and_the_wicked_role_drains(cards):
    """704.5z: a second Role of the same player on the creature puts the older one into its owner's graveyard (a token:
    it then ceases to exist); the Wicked Role's "put into a graveyard from the battlefield" trigger (111.10q)."""
    s = build(cards, "Shatter the Oath", "Royal Treatment")
    bear = token(s, "p1", "Bear", "2/2")
    victim = token(s, "p2", "Victim", "1/1")
    to_hand(s, "Shatter the Oath")
    mana(s, B=2, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Shatter the Oath").id, targets=[victim.id, bear.id],
        target_counts=[1, 1])
    settle(s)
    assert victim.id not in s.state.cards or not s.state.cards[victim.id].zone.endswith(":battlefield")
    [wicked] = roles_on(s, bear)
    assert wicked.name == "Wicked" and pt(s, bear) == (3, 3)
    to_hand(s, "Royal Treatment")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Royal Treatment").id, targets=[bear.id])
    settle(s)
    [royal] = roles_on(s, bear)
    assert royal.name == "Royal" and "hexproof" in chars(s, bear).keywords
    assert s.state.players["p2"].life == 39 and s.state.players["p1"].life == 40  # (each opponent loses 1)
    replay_matches(s)
    replay_matches(reloaded(s))


def test_up_to_one_target_with_none_chosen_creates_no_role(cards):
    """303.4i: an Aura that would enter attached to nothing isn't created."""
    s = build(cards, "Shatter the Oath")
    victim = token(s, "p2", "Victim", "1/1")
    to_hand(s, "Shatter the Oath")
    mana(s, B=2, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Shatter the Oath").id, targets=[victim.id],
        target_counts=[1, 0])
    settle(s)
    assert not [c for c in s.state.cards.values() if c.name == "Wicked"]
    replay_matches(s)


def test_role_target_gone_means_the_spell_does_nothing(cards):
    s = build(cards, "Monstrous Rage")
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    bear = token(s, "p1", "Bear", "2/2")
    to_hand(s, "Monstrous Rage")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Monstrous Rage").id, targets=[bear.id])
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "graveyard"})  # (gone before it resolves)
    settle(s)
    assert not [c for c in s.state.cards.values() if c.name == "Monster"]
    replay_matches(s)


def test_role_stale_roles_per_controller():
    """704.5z counts only Roles of the same controller: Roles of two players on one creature both stay."""
    assert roles.ROLES["Monster"] == "Enchanted creature gets +1/+1 and has trample."
    assert roles.clause("create a Monster Role token attached to each creature you control") is None
    assert roles.clause("create a Monster Role token attached to one or two target creatures") is None


# -- decayed (702.147) ---------------------------------------------------------------------------------------------
def test_rotten_reunion_decayed_zombie_cant_block_and_is_sacrificed_after_attacking(cards):
    s = build(cards, "Rotten Reunion")
    to_hand(s, "Rotten Reunion")
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Rotten Reunion").id, targets=[])
    settle(s)
    [zombie] = tokens(s)
    assert zombie.name == "Zombie" and "decayed" in chars(s, zombie).keywords
    attacker = token(s, "p2", "Raider", "1/1")
    plan = Plan(s.state, "p1", s.cards, None)
    problem = block_problem(s.state, s.state.cards[zombie.id], plan.ch(s.state.cards[zombie.id]),
                            s.state.cards[attacker.id], plan.ch(s.state.cards[attacker.id]), s.cards)
    assert problem is not None and "decayed" in problem
    replay_matches(s)
    s = reloaded(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.rules.decision is not None
          and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": zombie.id, "target": "p2"}])
    through_combat(s)
    assert s.state.players["p2"].life == 38  # (it dealt its damage, then was sacrificed at end of combat)
    assert zombie.id not in s.state.cards or not s.state.cards[zombie.id].zone.endswith(":battlefield")
    replay_matches(s)


def test_jadar_makes_a_decayed_zombie_only_without_one(cards):
    s = build(cards, "Jadar, Ghoulcaller of Nephalia")
    put(s, "Jadar, Ghoulcaller of Nephalia")
    until(s, lambda s: s.state.turn.number == 2)
    assert [c.name for c in tokens(s)] == ["Zombie"]
    until(s, lambda s: s.state.turn.number == 4)
    assert [c.name for c in tokens(s)] == ["Zombie"]  # (it had one with decayed: no second)
    replay_matches(s)


# -- token wordings ------------------------------------------------------------------------------------------------
def test_tolsimir_creates_voja_a_legendary_token(cards):
    s = build(cards, "Tolsimir Wolfblood")
    tol = put(s, "Tolsimir Wolfblood")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and not s.state.zones.get("stack"))
    act(s, "p1", type="activate_ability", card_id=tol.id, ability=2)
    settle(s)
    [voja] = tokens(s)
    assert voja.name == "Voja" and "Legendary" in chars(s, voja).supertypes
    assert pt(s, voja) == (4, 4) and chars(s, voja).colors == frozenset({"G", "W"})  # (Tolsimir: green, white +1/+1)
    replay_matches(s)
    replay_matches(reloaded(s))


def test_army_of_the_damned_thirteen_tapped_zombies(cards):
    s = build(cards, "Army of the Damned")
    to_hand(s, "Army of the Damned")
    mana(s, B=3, C=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Army of the Damned").id)
    settle(s)
    made = tokens(s)
    assert len(made) == 13 and all(c.tapped and c.name == "Zombie" for c in made)
    replay_matches(s)


def test_moogles_valor_one_token_for_each_creature(cards):
    s = build(cards, "Moogles' Valor")
    for i in range(3):
        token(s, "p1", f"Bear{i}", "2/2")
    to_hand(s, "Moogles' Valor")
    mana(s, W=2, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Moogles' Valor").id)
    settle(s)
    moogles = [c for c in tokens(s) if c.name == "Moogle"]
    assert len(moogles) == 3 and all("indestructible" in chars(s, c).keywords for c in on_field(s) if chars(s, c).is_creature)
    replay_matches(s)
    replay_matches(reloaded(s))


def test_godsire_beast_is_red_green_and_white(cards):
    s = build(cards, "Godsire")
    god = put(s, "Godsire")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and not s.state.zones.get("stack"))
    act(s, "p1", type="activate_ability", card_id=god.id, ability=1)
    settle(s)
    [beast] = tokens(s)
    assert chars(s, beast).colors == frozenset({"R", "G", "W"}) and pt(s, beast) == (8, 8)
    replay_matches(s)


def test_crib_swap_its_controller_gets_a_changeling(cards):
    s = build(cards, "Crib Swap")
    victim = token(s, "p2", "Victim", "5/5")
    to_hand(s, "Crib Swap")
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Crib Swap").id, targets=[victim.id])
    settle(s)
    [shape] = tokens(s, "p2")
    assert shape.name == "Shapeshifter" and pt(s, shape) == (1, 1) and "Elf" in chars(s, shape).subtypes  # (702.73a)
    assert not tokens(s, "p1")
    replay_matches(s)
    replay_matches(reloaded(s))


def test_the_hive_wasp_is_named_so(cards):
    s = build(cards, "The Hive")
    hive = put(s, "The Hive")
    mana(s, C=5)
    act(s, "p1", type="activate_ability", card_id=hive.id, ability=0)
    settle(s)
    [wasp] = tokens(s)
    assert wasp.name == "Wasp" and "flying" in chars(s, wasp).keywords and "Insect" in chars(s, wasp).subtypes
    replay_matches(s)


def test_field_of_the_dead_counts_different_names(cards):
    """Six Forests and the Field: two names, no Zombie; seven different names: a Zombie (201.2)."""
    s = build(cards, "Field of the Dead", "Command Tower", "Island", "Mountain", "Swamp", "Kher Keep", forests=9)
    forests = [c.id for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"][:6]
    act(s, "p1", type="move", card_ids=forests, to={"player": "p1", "zone": "battlefield"})
    put(s, "Field of the Dead")
    settle(s)
    for name in ("Command Tower", "Island", "Mountain"):
        put(s, name)
    act(s, "p1", type="play_land", card_id=to_hand(s, "Swamp").id)  # (played: its trigger, with six names)
    settle(s)
    assert not tokens(s)
    keep = to_hand(s, "Kher Keep")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and not s.state.zones.get("stack"))
    act(s, "p1", type="play_land", card_id=keep.id)  # the seventh name
    settle(s)
    assert [c.name for c in tokens(s)] == ["Zombie"]
    replay_matches(s)
    replay_matches(reloaded(s))


# -- anthems and counts ------------------------------------------------------------------------------------------
def test_anthems_with_type_lists_and_invariant_plurals(cards):
    s = build(cards, "Vodalian Hexcatcher", "Nightpack Ambusher")
    put(s, "Vodalian Hexcatcher")
    put(s, "Nightpack Ambusher")
    merfolk = token_of(s, "p1", "Fish", "Token Creature — Merfolk", "1/1")
    were = token_of(s, "p1", "Were", "Token Creature — Werewolf", "1/1")
    wolf = token_of(s, "p1", "Pup", "Token Creature — Wolf", "1/1")
    elf = token_of(s, "p1", "Elfy", "Token Creature — Elf", "1/1")
    enemy = token_of(s, "p2", "Enemy Wolf", "Token Creature — Wolf", "1/1")
    assert pt(s, merfolk) == (2, 2) and pt(s, were) == (2, 2) and pt(s, wolf) == (2, 2)
    assert pt(s, elf) == (1, 1) and pt(s, enemy) == (1, 1)
    replay_matches(s)


def test_kor_spiritdancer_and_champion_count_attachments(cards):
    s = build(cards, "Kor Spiritdancer", "Champion of the Flame", "Monstrous Rage")
    kor = put(s, "Kor Spiritdancer")
    champ = put(s, "Champion of the Flame")
    assert pt(s, kor) == (0, 2) and pt(s, champ) == (1, 1)
    to_hand(s, "Monstrous Rage")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Monstrous Rage").id, targets=[kor.id])
    settle(s)
    assert pt(s, kor) == (5, 5)  # 0/2 +2/+0 (until end of turn) +1/+1 (the Role) +2/+2 (one Aura)
    sword = token_of(s, "p1", "Sword", "Token Artifact — Equipment", "0/0")
    act(s, "p1", type="attach", card_ids=[sword.id], to=champ.id)
    assert pt(s, champ) == (3, 3)
    replay_matches(s)
    replay_matches(reloaded(s))


def test_coat_of_arms_counts_shared_creature_types_per_creature(cards):
    s = build(cards, "Coat of Arms")
    put(s, "Coat of Arms")
    e1 = token_of(s, "p1", "Elf A", "Token Creature — Elf Warrior", "1/1")
    e2 = token_of(s, "p1", "Elf B", "Token Creature — Elf", "1/1")
    w = token_of(s, "p2", "Warrior", "Token Creature — Human Warrior", "1/1")
    goat = token_of(s, "p2", "Goat", "Token Creature — Goat", "1/1")
    assert pt(s, e1) == (3, 3)  # shares Elf with e2, Warrior with w
    assert pt(s, e2) == (2, 2) and pt(s, w) == (2, 2) and pt(s, goat) == (1, 1)
    replay_matches(s)


def test_firedrinker_satyr_pumps_and_deals_damage_to_you(cards):
    s = build(cards, "Firedrinker Satyr")
    satyr = put(s, "Firedrinker Satyr")
    mana(s, R=1, C=1)
    act(s, "p1", type="activate_ability", card_id=satyr.id, ability=1)
    settle(s)
    assert pt(s, satyr) == (3, 1)
    # 1 damage to Alice; the Satyr wasn't dealt damage (no trigger)
    assert s.state.players["p1"].life == 39
    replay_matches(s)


def test_the_great_mound_vibranium_token(cards):
    """111.10w: a colorless Vibranium artifact token with indestructible and a restricted {C} mana ability."""
    s = build(cards, "The Great Mound")
    mound = put(s, "The Great Mound")
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=mound.id, ability=1)
    settle(s)
    [vib] = tokens(s)
    vch = chars(s, vib)
    assert vib.name == "Vibranium" and vib.tapped and "Artifact" in vch.types and "indestructible" in vch.keywords
    replay_matches(s)


def test_hansk_gives_the_opponent_walkers(cards):
    """111.10d: "A Walker token is a 2/2 black Zombie creature token named Walker."; the target opponent creates them."""
    s = build(cards, "Hansk, Slayer Zealot")
    put(s, "Hansk, Slayer Zealot")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and not s.state.zones.get("stack"))
    walkers = tokens(s, "p2")
    assert [w.name for w in walkers] == ["Walker"] * 3 and not tokens(s)
    assert all(pt(s, w) == (2, 2) and "Zombie" in chars(s, w).subtypes and chars(s, w).colors == frozenset({"B"})
               for w in walkers)
    replay_matches(s)
    replay_matches(reloaded(s))


def test_mobile_fort_attacks_despite_defender_this_turn(cards):
    """702.3b: "can attack this turn as though it didn't have defender" (a rule on it until end of turn)."""
    from app.rules.combat import attack_problem

    s = build(cards, "Mobile Fort")
    fort = put(s, "Mobile Fort")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and not s.state.zones.get("stack"))
    assert "defender" in (attack_problem(s.state, s.state.cards[fort.id], chars(s, fort)) or "")
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=fort.id, ability=1)
    settle(s)
    assert pt(s, fort) == (3, 5) and attack_problem(s.state, s.state.cards[fort.id], chars(s, fort)) is None
    to_attack(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": fort.id, "target": "p2"}])
    through_combat(s)
    assert s.state.players["p2"].life == 37
    replay_matches(s)
    until(s, lambda s: s.state.turn.number == 5 and s.state.turn.phase == "main1")
    assert "defender" in (attack_problem(s.state, s.state.cards[fort.id], chars(s, fort)) or "")


def test_thats_a_type_or_type_anthems(cards):
    s = build(cards, "Sporecrown Thallid", "Lovisa Coldeyes")
    put(s, "Sporecrown Thallid")
    put(s, "Lovisa Coldeyes")
    fungus = token_of(s, "p1", "Spore", "Token Creature — Fungus", "1/1")
    sap = token_of(s, "p1", "Sap", "Token Creature — Saproling", "1/1")
    warrior = token_of(s, "p2", "Brute", "Token Creature — Human Warrior", "1/1")
    goat = token_of(s, "p1", "Goat", "Token Creature — Goat", "1/1")
    assert pt(s, fungus) == (2, 2) and pt(s, sap) == (2, 2) and pt(s, goat) == (1, 1)
    assert pt(s, warrior) == (3, 3) and "haste" in chars(s, warrior).keywords  # (Lovisa: each creature, any controller)
    assert pt(s, card_named(s, "Sporecrown Thallid")) == (2, 2)  # ("each other")
    replay_matches(s)


def test_you_may_have_target_creature_get():
    """"you may have target creature get +2/+0 and gain deathtouch until end of turn": an optional targeted pump."""
    from app.rules import scripts
    from tests.test_rules_scripts import ch as characteristics

    c = next(c for c in EXTRA if c["name"] == "Painsmith")
    chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
    [d] = scripts.definitions(chs).values()
    assert d["optional"] and d["target"] == {"what": "creature"}
    assert d["effects"] == [{"do": "pump", "who": "target", "p": 2, "t": 0},
                            {"do": "grant", "who": "target", "keywords": ["deathtouch"]}]
