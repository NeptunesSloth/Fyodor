"""Mystery Booster Commander (wave MBC-A, app/rules/mbc_a.py): Rulebreaker lines (deck construction only), named tokens, The Everforger, Whtz,
The Unluckiest Planeswalker, Tsagan's max speed and Werewolf Pack Leader. Real Oracle text (Scryfall); each scenario checks the replay and a
save and a load."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, scripts
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import can_cast, to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

EXTRA = [
    real("Seluma, Light of Aysen", "{4}{W}", 5, "Legendary Creature — Angel Warrior",
         "Rulebreaker — A deck with this commander can have Angel cards of any color identity and any basic land cards.\nFlying\nWhenever Seluma "
         "deals combat damage to a player, return target Angel creature card from your graveyard to the battlefield.", ("4", "4"), "W"),
    real("Valko Indorian", "{3}{B}", 4, "Legendary Creature — Human Wizard",
         "Rulebreaker — A deck with this commander can have Phyrexian cards of any color identity and any basic land cards.\nPhyrexian creatures "
         "you control have menace and lifelink.", ("2", "4"), "B"),
    real("Grizzlegom, Hurloon Hero", "{5}{R}{G}", 7, "Legendary Creature — Minotaur Warrior",
         "Rulebreaker — A deck with this commander can have any land cards.\nWhenever Grizzlegom attacks, create a 1/1 white Soldier creature token "
         "for each Plains you control. Draw a card for each Island you control. Each opponent loses 1 life for each Swamp you control. Put a +1/+1 "
         "counter on Grizzlegom for each Mountain you control. You gain 1 life for each Forest you control.", ("4", "4"), "RG"),
    real("Maular, the Next Evolution", "{5}{G}{G}", 7, "Legendary Creature — Dinosaur Mutant",
         "Rulebreaker — A deck with this commander can have creature cards with mana value 7 or greater of any color identity and any basic land "
         "cards.\nWhenever a creature you control with mana value 7 or greater attacks, double its power and toughness until end of turn.",
         ("10", "10"), "G"),
    real("Tolabow, Loch Rascal", "{2}{U}{U}", 4, "Legendary Creature — Otter",
         "Rulebreaker — If Tolabow, Loch Rascal is your commander, the color identity of instant and sorcery cards in your deck can include one "
         "color of your choice not in your commander's color identity, and your deck can have any basic land cards.\nWhenever you cast an instant "
         "or sorcery spell, create a 1/1 blue and red Otter creature token with prowess. (Whenever you cast a noncreature spell, it gets +1/+1 until "
         "end of turn.)", ("3", "2"), "U"),
    real("Whtz, the Bibliophile", "{1}{W}{U}", 3, "Legendary Creature — Homunculus",
         "Rulebreaker — A deck with this commander has no maximum deck size.\n{3}, {T}: You draw a card and gain 1 life. This ability costs {3} "
         "less to activate if you had 200 or more cards in your starting deck.", ("1", "3"), "WU"),
    real("The Everforger", "{6}", 6, "Legendary Artifact Creature — Construct",
         "Rulebreaker — A deck with this commander can have artifact creature and Equipment cards of any color identity and any basic land "
         "cards.\nWhenever you cast an artifact creature or Equipment spell, you may copy that spell. Do this only once each turn. (The copy "
         "becomes a token.)", ("4", "5"), ""),
    {**real("The Unluckiest Planeswalker", "{2}{R}", 3, "Legendary Planeswalker",
            "Rulebreaker — A deck with this commander can have Aura cards of any color identity and any basic land cards.\n+1: Add one mana of any "
            "color. When you spend this mana to cast an Aura spell this turn, create a 1/1 red Gremlin creature token.\n−3: Discard your hand, then "
            "draw cards equal to twice the number of Auras you control. For each Aura attached to you, attach it to an opponent of your choice.\n"
            "The Unluckiest Planeswalker can be your commander.", None, "R"), "loyalty": "4"},
    {**real("Greensleeves", "{4}{G}{G}", 6, "Legendary Planeswalker — Greensleeves",
            "+2: Create a Giant Badger token. (It's a {1}{G}{G} 2/2 Badger creature with \"Whenever this token blocks, it gets +2/+2 until end of "
            "turn.\")\n−3: Mill three cards. Put all permanent cards from among them into your hand.\n−8: Until end of turn, creatures you control "
            "have base power and toughness 8/8 and gain trample.\nGreensleeves can be your commander.", None, "G"), "loyalty": "5"},
    {**real("Worzel, the Protector", "{1}{W}{W}{W}", 4, "Legendary Planeswalker — Worzel",
            "0: Create a 1/1 white Cat creature token with \"{T}: Put a loyalty counter on each planeswalker you control.\"\n−1: Look at the top "
            "six cards of your library. You may reveal a planeswalker or basic Plains card from among them and put it into your hand. Put the rest "
            "on the bottom of your library in a random order.\n−8: Create ten Scryb Sprites tokens. (They're {G} 1/1 Faerie creatures with "
            "flying.)\nWorzel, the Protector can be your commander.", None, "W"), "loyalty": "4"},
    {**real("Thomil, the Destroyer", "{3}{B}{B}", 5, "Legendary Planeswalker — Thomil",
            "+2: Create a 2/2 black Zombie creature token.\n0: You may sacrifice a creature. If you do, add {B}{B}{B}.\n−5: Create a Lord of the "
            "Pit token. (It's a {4}{B}{B}{B} 7/7 Demon creature with flying, trample, and \"At the beginning of your upkeep, sacrifice another "
            "creature. If you can't, this token deals 7 damage to you.\")\nThomil, the Destroyer can be your commander.", None, "B"),
     "loyalty": "4"},
    {**real("Arzakon", "{W}{U}{B}{R}{G}", 5, "Legendary Planeswalker — Arzakon",
            "+2: Arzakon deals 3 damage to any other target.\n−3: Create a Black Lotus token. (It's a {0} artifact with \"{T}, Sacrifice this "
            "token: Add three mana of any one color.\")\n−7: Each player shuffles their hand and graveyard into their library, then draws seven "
            "cards.\nArzakon can be your commander.", None, "WUBRG"), "loyalty": "4"},
    {**real("Feroz, Ulgrotha's Warden", "{3}{G}{W}{U}", 6, "Legendary Planeswalker — Feroz",
            "+2: Create two 1/1 blue Bird creature tokens with flying.\n0: Draw a card. You may put a permanent card with mana value 4 or less "
            "from your hand onto the battlefield.\n−7: Create a Feroz's Ban token. (It's a {6} artifact with \"Creature spells cost {2} more to "
            "cast.\")\nFeroz, Ulgrotha's Warden can be your commander.", None, "GWU"), "loyalty": "5"},
    real("Nivea, Beloved Battlemage", "{2}{W}", 3, "Legendary Creature — Human Wizard Warrior",
         "Whenever a creature you control becomes blocked, you may untap it and remove it from combat.\n{5}{W}{W}{W}, Sacrifice Nivea: Create an "
         "Akroma, Angel of Wrath token. (She's a {5}{W}{W}{W} legendary 6/6 Angel creature with flying, first strike, vigilance, trample, haste, "
         "and protection from black and from red.)", ("3", "1"), "W"),
    # (the 2026-11 card data prints its ability word with a hyphen; Oracle has an em dash)
    real("Werewolf Pack Leader", "{G}{G}", 2, "Creature — Human Werewolf",
         "Pack tactics - Whenever this creature attacks, if you attacked with creatures with total power 6 or greater this combat, draw a card.\n"
         "{3}{G}: Until end of turn, this creature has base power and toughness 5/3, gains trample, and is a Werewolf.", ("3", "3"), "G"),
    real("Tsagan, Raider Warlord", "{R}{W}{B}", 3, "Legendary Creature — Dinosaur Berserker",
         "Double strike\nStart your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent "
         "loses life. Max speed is 4.)\nWhenever Tsagan attacks, creatures you control get +1/+0 until end of turn for each creature you control "
         "with first strike or double strike.\nMax speed — Tsagan has deathtouch and other creatures you control have first strike.", ("1", "4"),
         "RWB"),
]
NAMES = [c["name"] for c in EXTRA]
HELPERS = [
    real("Ornithopter", "{0}", 0, "Artifact Creature — Thopter", "Flying", ("0", "2"), ""),
    real("Curse of the Pierced Heart", "{1}{R}", 2, "Enchantment — Aura Curse",
         "Enchant player\nAt the beginning of enchanted player's upkeep, Curse of the Pierced Heart deals 1 damage to that player or a planeswalker "
         "that player controls.", None, "R"),
    real("Hill Giant", "{3}{R}", 4, "Creature — Giant", "", ("3", "3"), "R"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *HELPERS], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", coverage.of_card_data(cards.resolve(name)).manual_parts


def ch_of(s, c):
    return Plan(s.state, c.controller, s.cards, None).ch(s.state.cards[c.id])


def walker(s, name, loyalty=10):
    c = put(s, name)
    act(s, "p1", type="set_counter", card_id=c.id, kind="loyalty", value=loyalty)
    return c


def tokens(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.controller == pid and c.zone.endswith(":battlefield")]


# -- Rulebreaker: deck construction only ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["Seluma, Light of Aysen", "Valko Indorian", "Grizzlegom, Hurloon Hero", "Maular, the Next Evolution",
                                  "Tolabow, Loch Rascal", "Whtz, the Bibliophile", "The Everforger", "The Unluckiest Planeswalker"])
def test_rulebreaker_is_a_deckbuilding_static(cards, name):
    s = build(cards, [name])
    c = put(s, name)
    ch = ch_of(s, c)
    line = next(a for a in ch.abilities if a.text.startswith("Rulebreaker — "))
    assert scripts.definitions(ch)[line.index] == {"kind": "static", "static": "deckbuilding", "effects": []}
    check(s)


def test_a_rulebreaker_wording_outside_deck_construction_is_not_read(cards):
    from app.rules import mbc_a

    assert mbc_a._RULEBREAKER.fullmatch("Rulebreaker — Creatures you control get +1/+1.") is None


# -- named tokens ----------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name,ability,token,count,expect", [
    ("Greensleeves", 0, "Giant Badger", 1, {"mana_cost": "{1}{G}{G}", "pt": ("2", "2"), "types": {"Creature"}, "subtypes": {"Badger"}}),
    ("Worzel, the Protector", 2, "Scryb Sprites", 10, {"mana_cost": "{G}", "pt": ("1", "1"), "types": {"Creature"}, "keywords": {"flying"}}),
    ("Thomil, the Destroyer", 2, "Lord of the Pit", 1, {"mana_cost": "{4}{B}{B}{B}", "pt": ("7", "7"), "keywords": {"flying", "trample"}}),
    ("Arzakon", 1, "Black Lotus", 1, {"mana_cost": "{0}", "types": {"Artifact"}}),
    ("Feroz, Ulgrotha's Warden", 2, "Feroz's Ban", 1, {"mana_cost": "{6}", "types": {"Artifact"}}),
])
def test_planeswalker_named_tokens_have_the_cards_values(cards, name, ability, token, count, expect):
    s = build(cards, [name])
    pw = walker(s, name)
    act(s, "p1", type="activate_ability", card_id=pw.id, ability=ability)
    settle(s)
    made = tokens(s, token)
    assert sum(c.quantity for c in made) == count
    ch = ch_of(s, made[0])
    assert ch.name == token
    assert ch.mana_value == {"{1}{G}{G}": 3, "{G}": 1, "{4}{B}{B}{B}": 7, "{0}": 0, "{6}": 6}[expect["mana_cost"]]  # (111.3: the card's mana cost)
    if "pt" in expect:
        assert (ch.power, ch.toughness) == expect["pt"]
    for t in expect.get("types", ()):
        assert t in ch.types
    for t in expect.get("subtypes", ()):
        assert t in ch.subtypes
    for k in expect.get("keywords", ()):
        assert k in ch.keywords
    check(s)


def test_black_lotus_token_taps_and_sacrifices_for_three_mana(cards):
    s = build(cards, ["Arzakon"])
    pw = walker(s, "Arzakon")
    act(s, "p1", type="activate_ability", card_id=pw.id, ability=1)
    settle(s)
    lotus = tokens(s, "Black Lotus")[0]
    act(s, "p1", type="activate_ability", card_id=lotus.id, ability=0)
    settle(s)
    assert lotus.id not in s.state.cards or not s.state.cards[lotus.id].zone.endswith(":battlefield")
    pool = s.state.players["p1"].mana
    units = s.state.players["p1"].mana_units
    assert sum(pool.values()) + len(units) == 3
    check(s)


def test_ferozs_ban_token_makes_creature_spells_cost_two_more(cards):
    s = build(cards, ["Feroz, Ulgrotha's Warden", "Grizzly Bears"])
    pw = walker(s, "Feroz, Ulgrotha's Warden")
    bears = to_hand(s, "Grizzly Bears")
    mana(s, G=2)
    assert can_cast(s, "p1", bears)
    act(s, "p1", type="activate_ability", card_id=pw.id, ability=2)
    settle(s)
    assert tokens(s, "Feroz's Ban")
    assert not can_cast(s, "p1", bears)  # ({1}{G} + {2}: four mana)
    mana(s, G=2)
    assert can_cast(s, "p1", bears)
    check(s)


def test_nivea_sacrifices_for_an_akroma_token(cards):
    s = build(cards, ["Nivea, Beloved Battlemage"])
    nivea = put(s, "Nivea, Beloved Battlemage")
    mana(s, W=3, G=5)
    act(s, "p1", type="activate_ability", card_id=nivea.id, ability=1)
    settle(s)
    assert s.state.cards[nivea.id].zone == "p1:graveyard"
    akroma = tokens(s, "Akroma, Angel of Wrath")
    assert len(akroma) == 1
    ch = ch_of(s, akroma[0])
    assert "Legendary" in ch.supertypes and (ch.power, ch.toughness) == ("6", "6") and ch.mana_value == 8
    assert {"flying", "first strike", "vigilance", "trample", "haste"} <= set(ch.keywords)
    check(s)


# -- The Everforger -------------------------------------------------------------------------------------------------------------------------------
def _cast_copying(s, name, pid="p1"):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            labels = [o.label.lower() for o in d.options]
            pick = next((o.id for o, label in zip(d.options, labels, strict=True) if label in ("yes", "copy") or label.startswith("yes")), d.options[0].id)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


@pytest.mark.parametrize("name,copied", [("Ornithopter", True), ("Bonesplitter", True), ("Grizzly Bears", False)])
def test_everforger_copies_an_artifact_creature_or_equipment_spell(cards, name, copied):
    s = build(cards, ["The Everforger", name])
    put(s, "The Everforger")
    to_hand(s, name)
    mana(s, G=3)
    _cast_copying(s, name)
    same = [c for c in s.state.cards.values() if c.name == name and c.zone == "p1:battlefield"]
    assert len(same) == (2 if copied else 1)
    assert any(c.is_token for c in same) == copied
    check(s)


def test_everforger_copies_only_once_each_turn(cards):
    s = build(cards, ["The Everforger", "Ornithopter", "Bonesplitter"])
    put(s, "The Everforger")
    to_hand(s, "Ornithopter")
    to_hand(s, "Bonesplitter")
    mana(s, G=3)
    _cast_copying(s, "Ornithopter")
    _cast_copying(s, "Bonesplitter")
    assert len([c for c in s.state.cards.values() if c.name == "Ornithopter" and c.zone == "p1:battlefield"]) == 2
    assert len([c for c in s.state.cards.values() if c.name == "Bonesplitter" and c.zone == "p1:battlefield"]) == 1
    check(s)


# -- Whtz, the Bibliophile ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("forests,free", [(9, False), (200, True)])
def test_whtz_costs_three_less_with_a_200_card_starting_deck(cards, forests, free):
    s = build(cards, ["Whtz, the Bibliophile"], forests=forests)
    whtz = put(s, "Whtz, the Bibliophile")
    to_phase(s, "main1", turn=3)
    hand, life = len(s.state.zones["p1:hand"]), s.state.players["p1"].life
    if not free:
        with pytest.raises(ActionError):
            act(s, "p1", type="activate_ability", card_id=whtz.id, ability=1)
        mana(s, G=3)
    act(s, "p1", type="activate_ability", card_id=whtz.id, ability=1)
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1 and s.state.players["p1"].life == life + 1
    assert sum(s.state.players["p1"].mana.values()) == 0
    check(s)


# -- The Unluckiest Planeswalker --------------------------------------------------------------------------------------------------------------------
def _plus_one(s, pw, color="W"):
    act(s, "p1", type="activate_ability", card_id=pw.id, ability=1)
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((o.id for o in d.options if o.id == color or o.label == color),
                                                                             d.options[0].id)])
    settle(s)


@pytest.mark.parametrize("aura", [True, False])
def test_unluckiest_mana_spent_on_an_aura_makes_a_gremlin(cards, aura):
    s = build(cards, ["The Unluckiest Planeswalker", "Pacifism", "Grizzly Bears"], ["Grizzly Bears"])
    pw = walker(s, "The Unluckiest Planeswalker")
    put(s, "Grizzly Bears", "p2")
    _plus_one(s, pw, "W" if aura else "G")
    mana(s, G=1)
    if aura:
        target = card_named(s, "Grizzly Bears", "p2")
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Pacifism").id, targets=[target.id])
    else:
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Grizzly Bears").id)
    settle(s)
    assert len(tokens(s, "Gremlin")) == (1 if aura else 0)
    if aura:
        ch = ch_of(s, tokens(s, "Gremlin")[0])
        assert (ch.power, ch.toughness) == ("1", "1") and ch.colors == frozenset({"R"})
    check(s)


def _cursed(s, pid="p2"):
    curse = put(s, "Curse of the Pierced Heart", pid)
    settle(s)
    if s.state.cards[curse.id].attached_player != "p1":
        act(s, pid, type="attach", card_ids=[curse.id], to="p1")
    assert s.state.cards[curse.id].attached_player == "p1"
    return curse


def test_unluckiest_minus_three_discards_draws_and_passes_curses_on(cards):
    s = build(cards, ["The Unluckiest Planeswalker", "Pacifism", "Lightning Bolt"], ["Curse of the Pierced Heart", "Grizzly Bears"])
    pw = walker(s, "The Unluckiest Planeswalker")
    bears = put(s, "Grizzly Bears", "p2")
    pacifism = put(s, "Pacifism")
    act(s, "p1", type="attach", card_ids=[pacifism.id], to=bears.id)
    assert s.state.cards[pacifism.id].attached_to == bears.id
    curse = _cursed(s)
    to_hand(s, "Lightning Bolt")
    hand_before = list(s.state.zones["p1:hand"])
    act(s, "p1", type="activate_ability", card_id=pw.id, ability=2)
    settle(s)
    assert all(s.state.cards[c].zone == "p1:graveyard" for c in hand_before)
    assert len(s.state.zones["p1:hand"]) == 2  # (twice the one Aura Alice controls; Bob's curse is his)
    assert s.state.cards[curse.id].attached_player == "p2"
    check(s)


def test_unluckiest_minus_three_lets_alice_choose_which_opponent(cards):
    from tests.test_rules_wave30m_durations import three

    s = three(cards, a=["The Unluckiest Planeswalker"], b=["Curse of the Pierced Heart"])
    pw = walker(s, "The Unluckiest Planeswalker")
    curse = _cursed(s)
    act(s, "p1", type="activate_ability", card_id=pw.id, ability=2)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            assert d.player == "p1" and {o.id for o in d.options} == {"p2", "p3"}
            act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[curse.id].attached_player == "p3"
    check(s)


# -- Tsagan, Raider Warlord: max speed ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("speed", [3, 4])
def test_tsagan_at_max_speed(cards, speed):
    s = build(cards, ["Tsagan, Raider Warlord", "Grizzly Bears"])
    tsagan = put(s, "Tsagan, Raider Warlord")
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="set_resource", player="p1", key="speed", value=speed)
    assert ("deathtouch" in ch_of(s, tsagan).keywords) == (speed == 4)
    assert ("first strike" in ch_of(s, bears).keywords) == (speed == 4)
    assert "first strike" not in ch_of(s, tsagan).keywords  # ("other creatures")
    check(s)


# -- Werewolf Pack Leader -----------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("giant,draws", [(False, False), (True, True)])
def test_pack_tactics_draws_with_six_power_attacking(cards, giant, draws):
    s = build(cards, ["Werewolf Pack Leader", "Grizzly Bears", "Hill Giant"])
    leader = put(s, "Werewolf Pack Leader")
    bears = put(s, "Grizzly Bears")
    hill = put(s, "Hill Giant")
    to_phase(s, "declare_attackers", turn=3)
    hand = len(s.state.zones["p1:hand"])
    attackers = [leader, bears, *([hill] if giant else [])]  # (3 + 2 = 5; 3 + 2 + 3 = 8)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand + (1 if draws else 0)
    check(s)


def test_werewolf_pack_leader_becomes_a_5_3_trampling_werewolf_until_end_of_turn(cards):
    s = build(cards, ["Werewolf Pack Leader"])
    leader = put(s, "Werewolf Pack Leader")
    mana(s, G=4)
    act(s, "p1", type="activate_ability", card_id=leader.id, ability=1)
    settle(s)
    ch = ch_of(s, leader)
    assert ch.pt == (5, 3)
    assert "trample" in ch.keywords
    assert ch.subtypes == frozenset({"Werewolf"})
    check(s)
    to_phase(s, "main1", turn=2)  # (Bob's turn: "until end of turn" ended in Alice's cleanup, 514.2)
    ch = ch_of(s, leader)
    assert "trample" not in ch.keywords and "Human" in ch.subtypes
    check(s)
