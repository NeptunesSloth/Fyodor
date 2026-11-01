"""Wave 111C: Star Trek statics and "as long as" statics (CR 2026-09-25), real Oracle text (Scryfall, 2026-10-30). Every scenario checks
the replay and a save and a load.

* The Star Trek creature types (Klingon, Borg, Officer, Tribble, Vulcan …) as written on the sets' type lines (app/rules/creature_types.py, 205.3m).
* 721.2a station symbols that grant triggered abilities ("3+ | At the beginning of combat …", "6+ | Picard Maneuver — Whenever …": a flavor word
  first, 207.2d), 702.41a affinity for a creature type, 701.15b goaded by a static, the modal "choose one that hasn't been chosen" (700.2).
"""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act, deck, enable, mana_pool
from tests.test_rules_conditionals import creature, until
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand

EXTRA = [
    real("D-7 Battle Cruiser", "{1}{R}", 2, "Artifact \u2014 Spacecraft", "Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 8+.)\n3+ | At the beginning of combat on your turn, create a 2/1 red Klingon Warrior creature token with haste. Sacrifice it at the beginning of the next end step.\n8+ | Flying", ("3", "3"), "R"),
    real("Ensign Pavel Chekov", "{3}{U}", 4, "Legendary Creature \u2014 Human Pilot", "Strange new worlds \u2014 When Ensign Chekov enters, each opponent exiles the top X cards of their library, where X is the number of differently named lands you control. For each opponent, choose a land card that player owns exiled this way. You may play the chosen cards for as long as they remain exiled.", ("1", "5"), "U"),
    real("H.M.S. Bounty, Unlikely Timeship", "{4}{U}", 5, "Legendary Artifact \u2014 Spacecraft", "When H.M.S. Bounty enters, you may search your library for a Whale card, reveal it, put it into your hand, then shuffle.\nStation\n8+ | Flying\nWhenever H.M.S. Bounty deals combat damage to a player, draw a card. If you control a Whale and haven't begun an extra turn this game, take an extra turn after this one.", ("3", "4"), "U"),
    real("Kang, Suspicious Captain", "{3}{R}", 4, "Legendary Creature \u2014 Klingon Warrior Officer", "When Kang enters, choose target creature an opponent controls. Kang and that creature are goaded for as long as you control Kang. (They attack each combat if able and attack a player other than you if able.)\nWhenever one or more goaded creatures attack, put a +1/+1 counter on target creature you control.", ("4", "4"), "R"),
    real("Lwaxana Troi, Charming Guest", "{1}{R}", 2, "Legendary Creature \u2014 Betazoid Advisor", "You may choose not to untap Lwaxana Troi during your untap step.\n{2}, {T}: Choose another target creature you control. For as long as Lwaxana Troi remains tapped, if a triggered ability of that creature triggers, that ability triggers an additional time.", ("2", "2"), "R"),
    real("S.S. Botany Bay", "{3}", 3, "Legendary Artifact \u2014 Spacecraft", "{T}: Each opponent exiles a card from their graveyard. You may exile a card from your graveyard.\nStation\n8+ | Flying\nWhenever S.S. Botany Bay deals combat damage to a player, return each creature card you own exiled with it to the battlefield.", ("3", "5"), ""),
    real("Type-03 Borg Vessel", "{3}{W}", 4, "Artifact \u2014 Spacecraft", "Artifact spells you cast cost {1} less to cast.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 7+.)\n7+ | Flying\nWhenever you cast a spell, create a 1/1 colorless Borg artifact creature token.", ("5", "5"), "W"),
    real("U.S.S. Stargazer, Here and There", "{3}", 3, "Legendary Artifact \u2014 Spacecraft", "Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 6+.)\n6+ | Flying\nPicard Maneuver \u2014 Whenever U.S.S. Stargazer attacks, create a tapped and attacking 4/3 colorless Spacecraft Illusion artifact creature token with flying. Exile that token at end of combat.", ("4", "3"), ""),
    real("Vulcan Mind-Meld", "{U}", 1, "Sorcery", "Target opponent looks at the top card of your library, then exiles it face down. You look at the top two cards of their library, then exile them face down. For each card exiled this way, the player who exiled it may play it for as long as it remains exiled. Mana of any type can be spent to cast spells this way.", None, "U"),
    real("Academy Instructor", "{2}{R}", 3, "Creature \u2014 Bolian Officer", "This creature gets +1/+0 for each Officer token you control.\nWhenever you cast a noncreature spell, create a 1/1 red Officer creature token.", ("0", "3"), "R"),
    real("Amanda Grayson, Logic's Link", "{3}{G}", 4, "Legendary Creature \u2014 Human Advisor", "Affinity for Vulcans (This spell costs {1} less to cast for each Vulcan you control.)\nLandfall \u2014 Whenever a land you control enters, put two +1/+1 counters on target creature you control.", ("2", "3"), "G"),
    real("Commander Raffi Musiker", "{2}{B}", 3, "Legendary Creature \u2014 Human Officer", "When Commander Musiker enters, choose one \u2014\n\u2022 Exile up to one target card from a graveyard. You gain 2 life.\n\u2022 Investigate. You lose 2 life. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")", ("3", "2"), "B"),
    real("Extraction Integrant", "{1}{B}", 2, "Artifact Creature \u2014 Borg", "Artifact creatures you control have menace and \"Whenever a creature blocks this creature, that creature gets -1/-1 until end of turn.\"", ("1", "1"), "B"),
    real("First Contact", "{1}{G}", 2, "Instant", "Mill four cards. You may put a permanent card from among them into your hand. If this spell is the first spell you've cast this game, you gain 2 life. (To mill four cards, put the top four cards of your library into your graveyard.)", None, "G"),
    real("Genesis Effect", "{4}{R}", 5, "Instant", "Genesis Effect deals 6 damage to target creature. Destroy target land you control. Create a tapped Planet land token named New Planet with \"{T}: Add one mana of any color.\"", None, "R"),
    real("I.K.S. Negh'Var, Imperial Flagship", "{3}", 3, "Legendary Artifact \u2014 Spacecraft", "Klingons and Warriors you control have vigilance.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 10+.)\n10+ | Flying, vigilance", ("6", "6"), ""),
    real("Kirk, Man of Action", "{2}{G}{W}{U}", 5, "Legendary Creature \u2014 Human Officer", "Other Officers, Artificers, Doctors, Pilots, Scientists, and Spacecraft creatures you control get +2/+2.", ("3", "3"), "GUW"),
    real("Kobayashi Maru Scenario", "{1}{U}{U}", 3, "Enchantment", "At the beginning of your upkeep, choose one that hasn't been chosen \u2014\n\u2022 Hail \u2014 Return up to one target creature an opponent controls with mana value 3 or less to its owner's hand.\n\u2022 Sensors \u2014 Draw two cards.\n\u2022 Transport \u2014 Create two 1/1 red Officer creature tokens.\n\u2022 Abandon Ship \u2014 You lose the game.", None, "U"),
    real("Koloth, Tribble Hunter", "{3}{R}", 4, "Legendary Creature \u2014 Klingon Warrior Officer", "At the beginning of your end step, each player creates two 1/1 white Tribble creature tokens with \"This token can't block.\"\nAll Tribbles get +1/+0 and are goaded. (They attack each combat if able and attack a player other than you if able.)", ("3", "3"), "R"),
    real("Locutus of Borg", "{1}{W}{U}{B}", 4, "Legendary Artifact Creature \u2014 Borg", "Lifelink\nArtifact creatures you control have \"Whenever this creature deals combat damage to a player, create a 1/1 colorless Borg artifact creature token.\"", ("3", "3"), "BUW"),
    real("Make It So", "{3}{U}", 4, "Sorcery", "Choose one \u2014\n\u2022 Untap target permanent you control. Target player draws two cards.\n\u2022 Create a 1/1 red Officer creature token and draw two cards.", None, "U"),
    real("Merciful Mandate", "{1}{W}", 2, "Instant", "Untap all creatures you control. If it's a combat phase, you may end the combat phase. (Remove all attackers and blockers from combat. Exile all spells and abilities from the stack, including this spell.)", None, "W"),
    real("Quark, Humble Proprietor", "{2}{R}", 3, "Legendary Creature \u2014 Ferengi Rogue", "You can't sacrifice Treasure tokens.\nAt the beginning of each upkeep, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")", ("1", "2"), "R"),
    real("Right of Vengeance", "{3}{W}", 4, "Instant", "Until end of turn, whenever a creature deals combat damage to you, destroy that creature and create a 2/1 red Klingon Warrior creature token with haste.", None, "W"),
    real("Sulu, Heroic Helmsman", "{1}{W}", 2, "Legendary Creature \u2014 Human Pilot", "Sulu stations Spacecraft and crews Vehicles as though his power were tripled.", ("2", "2"), "W"),
    real("Worf, Son of Mogh", "{1}{R}{W}", 3, "Legendary Creature \u2014 Klingon Warrior Officer", "Menace\nOther Officers you control get +1/+1.\nSeek out \u2014 Whenever you draw your second card each turn, create a 1/1 red Officer creature token.", ("3", "3"), "RW"),
]
NAMES = ["Academy Instructor", "Amanda Grayson, Logic's Link", "Commander Raffi Musiker", "D-7 Battle Cruiser", "Ensign Pavel Chekov",
         "Extraction Integrant", "First Contact", "H.M.S. Bounty, Unlikely Timeship", "I.K.S. Negh'Var, Imperial Flagship",
         "Kang, Suspicious Captain", "Kirk, Man of Action", "Kobayashi Maru Scenario", "Koloth, Tribble Hunter", "Locutus of Borg",
         "Lwaxana Troi, Charming Guest", "Make It So", "Merciful Mandate", "Quark, Humble Proprietor", "Right of Vengeance", "S.S. Botany Bay",
         "Sulu, Heroic Helmsman", "Type-03 Borg Vessel", "U.S.S. Stargazer, Here and There", "Vulcan Mind-Meld", "Worf, Son of Mogh"]
EXTRA += [  # (helpers)
    real("Consulate Dreadnought", "{1}", 1, "Artifact — Vehicle", "Crew 6 (Tap any number of creatures you control with total power 6 or more: This Vehicle becomes an artifact creature until end of turn.)", ("7", "11"), ""),
    real("Unswerving Sloth", "{3}{W}{W}", 5, "Creature — Sloth Mount", "Whenever this creature attacks while saddled, it gains indestructible until end of turn. Untap all creatures you control.\nSaddle 4 (Tap any number of other creatures you control with total power 4 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)", ("5", "5"), "W"),
    real("Adagia, Windswept Bastion", "", 0, "Land — Planet", "This land enters tapped.\n{T}: Add {W}.\nStation (Tap another creature you control: Put charge counters equal to its power on this Planet. Station only as a sorcery.)\n12+ | {3}{W}, {T}: Create a token that's a copy of target artifact or enchantment you control, except it's legendary. Activate only as a sorcery.", None, ""),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


# -- helpers ------------------------------------------------------------------------------------------------------------------------------
def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn (a list: several options), else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, targets=(), pid="p1", **kw):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    return c


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def add_charge(s, name, n, pid="p1"):
    act(s, pid, type="counter", card_ids=[card_named(s, name, pid).id], kind="charge", delta=n)


def ready(s, *objs):
    for c in objs:
        s.state.rules.controlled_since[c.id].turn = 0


def on_field(s, name, pid="p1"):
    return [s.state.cards[c] for c in s.state.zones[f"{pid}:battlefield"] if s.state.cards[c].name == name]


def build3(cards, mine=(), theirs=(), third=()):
    """Alice, Bob and Carol; Alice's first main phase."""
    def cards_of(commander, spells):
        return deck(cards, commander, [*((1, n) for n in spells), (9, "Forest")])

    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=cards_of("Krenko, Mob Boss", mine)),
                                     PlayerSetup("Bob", cards=cards_of("Atraxa, Praetors' Voice", theirs)),
                                     PlayerSetup("Carol", cards=cards_of("Krenko, Mob Boss", third))], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def to_combat_damage_done(s):
    """Nobody blocks; play on to the end of combat damage (main 2)."""
    until(s, lambda s: s.state.turn.phase == "main2" and not s.state.zones.get("stack") and s.state.rules.decision is None)


# -- station symbols that grant triggered abilities (721.2a) ------------------------------------------------------------------------------
@pytest.mark.parametrize("charge", [2, 3])
def test_d7_makes_a_hasty_klingon_each_combat_from_three_counters_and_sacrifices_it(cards, charge):
    s = build(cards, ["D-7 Battle Cruiser"])
    put(s, "D-7 Battle Cruiser")
    add_charge(s, "D-7 Battle Cruiser", charge)
    act(s, "p1", type="pass_priority")  # -> beginning of combat: the trigger resolves, then declare attackers
    tokens = on_field(s, "Klingon Warrior")
    assert len(tokens) == (1 if charge == 3 else 0)
    assert not ch(s, card_named(s, "D-7 Battle Cruiser")).is_creature  # (an artifact creature only at 8+)
    if tokens:
        token = ch(s, tokens[0])
        assert (token.pt, set(token.colors), "haste" in token.keywords) == ((2, 1), {"R"}, True)
        assert {"Klingon", "Warrior"} <= set(token.subtypes)
        until(s, lambda s: s.state.turn.number == 2)  # (sacrificed at the beginning of the next end step)
        assert not on_field(s, "Klingon Warrior")
    check(s)


@pytest.mark.parametrize("charge", [6, 7])
def test_type03_borg_vessel_makes_a_borg_for_each_spell_from_seven_counters(cards, charge):
    s = build(cards, ["Type-03 Borg Vessel", "Sol Ring", "Opt"])
    put(s, "Type-03 Borg Vessel")
    add_charge(s, "Type-03 Borg Vessel", charge)
    cast(s, "Sol Ring")  # (artifact spells cost {1} less: Sol Ring for nothing)
    answer(s)
    mana(s, U=1)
    cast(s, "Opt")
    answer(s)
    borgs = on_field(s, "Borg")
    assert len(borgs) == (2 if charge == 7 else 0)
    if borgs:
        token = ch(s, borgs[0])
        assert token.pt == (1, 1) and not token.colors and {"Artifact", "Creature"} <= set(token.types) and "Borg" in token.subtypes
    check(s)


def test_stargazer_picard_maneuver_makes_an_attacking_illusion_at_six_counters_that_leaves_at_end_of_combat(cards):
    s = build(cards, ["U.S.S. Stargazer, Here and There"])
    ship = put(s, "U.S.S. Stargazer, Here and There")
    add_charge(s, "U.S.S. Stargazer, Here and There", 5)
    assert not any(a.text.startswith("Picard Maneuver") for a in ch(s, ship).abilities) and not ch(s, ship).is_creature
    add_charge(s, "U.S.S. Stargazer, Here and There", 1)
    assert ch(s, ship).is_creature and ch(s, ship).pt == (4, 3)
    ready(s, ship)
    act(s, "p1", type="set_prefs", full_control=True)  # (stop at each priority, to look at the combat)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ship.id, "target": "p2"}])
    answer(s)
    illusion = on_field(s, "Spacecraft Illusion")
    assert len(illusion) == 1
    token = ch(s, illusion[0])
    assert illusion[0].tapped and token.pt == (4, 3) and "flying" in token.keywords and {"Spacecraft", "Illusion"} <= set(token.subtypes)
    assert illusion[0].attacking
    to_combat_damage_done(s)
    assert life(s, "p2") == 40 - 8  # (both attacked Bob)
    assert not on_field(s, "Spacecraft Illusion")  # (exiled at end of combat)
    check(s)


# -- Star Trek creature types -------------------------------------------------------------------------------------------------------------
def test_academy_instructor_counts_only_your_officer_tokens_and_makes_them_for_noncreature_spells(cards):
    s = build(cards, ["Academy Instructor", "Opt", "Grizzly Bears"])
    teacher = put(s, "Academy Instructor")
    creature(s, "p2", "Their Officer", pt="1/1", type_line="Token Creature — Officer")
    assert pt(s, "Academy Instructor") == (0, 3)
    mana(s, U=1)
    cast(s, "Opt")
    answer(s)
    mana(s, G=2)
    cast(s, "Grizzly Bears")  # (a creature spell: no Officer)
    answer(s)
    officers = on_field(s, "Officer")
    assert len(officers) == 1 and ch(s, officers[0]).colors == {"R"} and ch(s, officers[0]).pt == (1, 1)
    assert pt(s, "Academy Instructor") == (1, 3) and teacher.id in s.state.zones["p1:battlefield"]
    check(s)


@pytest.mark.parametrize("vulcans", [1, 2])
def test_amanda_grayson_costs_one_less_for_each_vulcan_you_control(cards, vulcans):
    s = build(cards, ["Amanda Grayson, Logic's Link"])
    for i in range(vulcans):
        creature(s, "p1", f"Vulcan {i}", pt="1/1", type_line="Token Creature — Vulcan")
    creature(s, "p2", "Their Vulcan", pt="1/1", type_line="Token Creature — Vulcan")  # (only Vulcans you control)
    mana(s, G=1, C=2)
    amanda = cast(s, "Amanda Grayson, Logic's Link")
    answer(s)
    assert amanda.id in s.state.zones["p1:battlefield"]
    assert sum(mana_pool(s).values()) == vulcans - 1  # ({3}{G} less {1} per Vulcan)
    check(s)


def test_amanda_grayson_landfall_puts_two_counters_on_target_creature_you_control(cards):
    s = build(cards, ["Amanda Grayson, Logic's Link"])
    amanda = put(s, "Amanda Grayson, Logic's Link")
    forest = to_hand(s, "Forest")
    act(s, "p1", type="play_land", card_id=forest.id)
    answer(s, amanda.id)
    assert s.state.cards[amanda.id].counters.get("+1/+1") == 2
    check(s)


def test_negh_var_gives_vigilance_to_your_klingons_and_warriors_only(cards):
    s = build(cards, ["I.K.S. Negh'Var, Imperial Flagship"])
    put(s, "I.K.S. Negh'Var, Imperial Flagship")
    klingon = creature(s, "p1", "K", type_line="Token Creature — Klingon Scientist")
    warrior = creature(s, "p1", "W", type_line="Token Creature — Human Warrior")
    human = creature(s, "p1", "H", type_line="Token Creature — Human")
    theirs = creature(s, "p2", "TK", type_line="Token Creature — Klingon")
    assert ["vigilance" in ch(s, c).keywords for c in (klingon, warrior, human, theirs)] == [True, True, False, False]
    check(s)


def test_kobayashi_maru_offers_only_the_modes_not_chosen_yet(cards):
    s = build(cards, ["Kobayashi Maru Scenario"])
    put(s, "Kobayashi Maru Scenario")
    hand = len(s.state.zones["p1:hand"])
    until(s, lambda s: s.state.turn.number == 3 and s.state.rules.decision is not None)
    d = s.state.rules.decision
    labels = [o.label for o in d.options]
    assert len(labels) == 4
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if "Sensors" in o.label)])
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + 2 + 1  # (two, then the draw step's card)
    until(s, lambda s: s.state.turn.number == 5 and s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert len(d.options) == 3 and not any("Sensors" in o.label for o in d.options)
    check(s)


def test_koloth_gives_each_player_two_tribbles_that_get_plus_one_and_are_goaded_by_you(cards):
    s = build3(cards, ["Koloth, Tribble Hunter"])
    put(s, "Koloth, Tribble Hunter")
    until(s, lambda s: s.state.turn.number == 2)
    for pid in ("p1", "p2", "p3"):
        tribbles = on_field(s, "Tribble", pid)
        assert len(tribbles) == 2, pid
        for t in tribbles:
            got = ch(s, t)
            assert got.pt == (2, 1) and "goaded:p1" in got.imposed and got.colors == {"W"}
    check(s)


def test_locutus_gives_your_artifact_creatures_a_borg_making_combat_damage_trigger(cards):
    s = build(cards, ["Locutus of Borg", "Frogmite"])
    locutus = put(s, "Locutus of Borg")
    frog = put(s, "Frogmite")
    bear = creature(s, "p1", "Bear", pt="2/2")
    ready(s, locutus, frog, bear)
    act(s, "p1", type="pass_priority")  # -> declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in (locutus, frog, bear)])
    to_combat_damage_done(s)
    assert len(on_field(s, "Borg")) == 2  # (Locutus and Frogmite; not the Bear)
    assert life(s, "p1") == 40 + 3 and life(s, "p2") == 40 - 3 - 2 - 2  # (lifelink)
    check(s)


@pytest.mark.parametrize("mode", [0, 1])
def test_make_it_so(cards, mode):
    s = build(cards, ["Make It So"])
    forest = card_named(s, "Forest")
    put(s, "Forest")
    act(s, "p1", type="tap", card_ids=[forest.id])
    hands = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2")}
    mana(s, U=1, C=3)
    if mode == 0:
        cast(s, "Make It So", [forest.id, "p2"], modes=[0], target_counts=[1, 1])
    else:
        cast(s, "Make It So", modes=[1])
    answer(s)
    if mode == 0:
        assert not s.state.cards[forest.id].tapped
        assert len(s.state.zones["p2:hand"]) == hands["p2"] + 2 and len(s.state.zones["p1:hand"]) == hands["p1"]
    else:
        officers = on_field(s, "Officer")
        assert len(officers) == 1 and ch(s, officers[0]).colors == {"R"}
        assert len(s.state.zones["p1:hand"]) == hands["p1"] + 2
    check(s)


def test_right_of_vengeance_destroys_each_creature_that_deals_you_combat_damage_and_makes_a_klingon(cards):
    s = build(cards, ["Right of Vengeance"])
    ogre = creature(s, "p2", "Ogre", pt="3/3")
    imp = creature(s, "p2", "Imp", pt="1/1")
    act(s, "p1", type="set_prefs", full_control=True)  # (Alice stops in Bob's declare attackers step)
    until(s, lambda s: s.state.turn.number == 2 and s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p1"} for c in (ogre, imp)])
    until(s, lambda s: s.state.rules.priority == "p1" and s.state.rules.decision is None)
    mana(s, W=1, C=3)
    cast(s, "Right of Vengeance")
    answer(s)
    until(s, lambda s: s.state.turn.phase == "main2")
    answer(s)
    assert life(s, "p1") == 40 - 4
    assert ogre.id not in s.state.zones["p2:battlefield"] and imp.id not in s.state.zones["p2:battlefield"]
    klingons = on_field(s, "Klingon Warrior")
    assert len(klingons) == 2 and "haste" in ch(s, klingons[0]).keywords
    check(s)


def test_worf_pumps_other_officers_and_makes_one_on_your_second_draw_each_turn(cards):
    s = build(cards, ["Worf, Son of Mogh", "Opt"])
    worf = put(s, "Worf, Son of Mogh")
    mana(s, U=1)
    cast(s, "Opt")  # (the turn's first draw: Alice skipped her first draw step)
    answer(s)
    assert not on_field(s, "Officer")
    mana(s, U=1)
    cast(s, "Opt")  # (the second)
    answer(s)
    officers = on_field(s, "Officer")
    assert len(officers) == 1
    assert ch(s, officers[0]).pt == (2, 2) and pt(s, "Worf, Son of Mogh") == (3, 3)  # (other Officers; Worf himself is one)
    assert worf.id in s.state.zones["p1:battlefield"]
    check(s)


@pytest.mark.parametrize("mode", [0, 1])
def test_commander_musiker_exiles_a_graveyard_card_and_gains_or_investigates_and_loses(cards, mode):
    """201.5c: "Commander Musiker" is the card's own short name (the shared rank-and-surname reading, wave 111G)."""
    s = build(cards, ["Commander Raffi Musiker"])
    island = card_named(s, "Island", "p2")
    act(s, "p2", type="move", card_ids=[island.id], to={"player": "p2", "zone": "graveyard"})
    mana(s, B=1, C=2)
    cast(s, "Commander Raffi Musiker")
    answer(s, f"{mode}:0", island.id)
    if mode == 0:
        assert s.state.cards[island.id].zone == "p2:exile" and life(s) == 42
    else:
        assert s.state.cards[island.id].zone == "p2:graveyard" and life(s) == 38 and len(on_field(s, "Clue")) == 1
    check(s)


def attack_with(s, *attackers):
    """Alice declares ``attackers`` at Bob in this turn's combat; nobody blocks; on to her second main phase."""
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers" and s.state.rules.decision.player == "p1")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])
    to_combat_damage_done(s)


@pytest.mark.parametrize("whale", [False, True])
def test_hms_bounty_takes_one_extra_turn_a_game_while_you_control_a_whale(cards, whale):
    """500.7: "haven't begun an extra turn this game" — the extra turn the first hit gave has begun when the ship hits again in it."""
    s = build(cards, ["H.M.S. Bounty, Unlikely Timeship"])
    ship = put(s, "H.M.S. Bounty, Unlikely Timeship")
    if whale:
        creature(s, "p1", "Whale", pt="4/4", type_line="Token Creature — Whale")
    add_charge(s, "H.M.S. Bounty, Unlikely Timeship", 8)
    ready(s, ship)
    hand = len(s.state.zones["p1:hand"])
    attack_with(s, ship)
    assert len(s.state.zones["p1:hand"]) == hand + 1 and life(s, "p2") == 37
    assert [t["player"] for t in s.state.rules.extra_turns] == (["p1"] if whale else [])
    until(s, lambda s: s.state.turn.number == 2)
    assert s.state.turn.active_player == ("p1" if whale else "p2")
    if whale:
        assert s.state.rules.extra_turn_begun111c == ["p1"]
        attack_with(s, ship)
        assert life(s, "p2") == 34 and not s.state.rules.extra_turns  # (a card, but no second extra turn)
        until(s, lambda s: s.state.turn.number == 3)
        assert s.state.turn.active_player == "p2"
    check(s)


def test_hms_bounty_has_no_combat_damage_trigger_below_eight_counters(cards):
    s = build(cards, ["H.M.S. Bounty, Unlikely Timeship"])
    ship = put(s, "H.M.S. Bounty, Unlikely Timeship")
    add_charge(s, "H.M.S. Bounty, Unlikely Timeship", 7)
    assert not ch(s, ship).is_creature and not any(a.text.startswith("Whenever") for a in ch(s, ship).abilities)
    add_charge(s, "H.M.S. Bounty, Unlikely Timeship", 1)
    assert ch(s, ship).is_creature and ch(s, ship).pt == (3, 4) and "flying" in ch(s, ship).keywords  # (no reminder text: the box of its only symbol)
    assert any(a.index >= 100 and a.text.startswith("Whenever") for a in ch(s, ship).abilities)
    check(s)


def decide(s, *wants, limit=60):
    """Resolve everything; each decision takes the options named in ``wants`` (ids or labels) that it offers, else its first option(s)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options if o.id in wants or o.label in wants][: max(1, d.max_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids or [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def test_botany_bay_returns_the_creature_cards_you_own_exiled_with_it_when_it_deals_combat_damage(cards):
    """607.1a, 607.2a: the 8+ ability refers to the cards the {T} ability exiled (both printed on the card), whatever its counters were then."""
    s = build3(cards, ["S.S. Botany Bay", "Grizzly Bears", "Llanowar Elves"], ["Ambush Viper"])
    bay = put(s, "S.S. Botany Bay")
    bears, elves, viper = card_named(s, "Grizzly Bears"), card_named(s, "Llanowar Elves"), card_named(s, "Ambush Viper", "p2")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[viper.id], to={"player": "p2", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[elves.id], to={"player": "p1", "zone": "exile"})  # (exiled some other way: not with it)
    forest = card_named(s, "Forest", "p3")
    act(s, "p3", type="move", card_ids=[forest.id], to={"player": "p3", "zone": "graveyard"})
    act(s, "p1", type="activate_ability", card_id=bay.id, ability=0)
    decide(s, "yes", "Yes", bears.id, viper.id, forest.id)
    assert {s.state.cards[c.id].zone for c in (bears, viper)} == {"p1:exile", "p2:exile"} and s.state.cards[forest.id].zone == "p3:exile"
    add_charge(s, "S.S. Botany Bay", 8)
    act(s, "p1", type="tap", card_ids=[bay.id], tapped=False)
    ready(s, bay)
    attack_with(s, bay)
    assert life(s, "p2") == 37
    assert bears.id in s.state.zones["p1:battlefield"] and s.state.cards[bears.id].controller == "p1"
    assert s.state.cards[viper.id].zone == "p2:exile" and s.state.cards[elves.id].zone == "p1:exile"  # (not yours; not exiled with it)
    check(s)


def test_kirk_pumps_your_other_officers_artificers_doctors_pilots_scientists_and_spacecraft_creatures(cards):
    s = build(cards, ["Kirk, Man of Action", "U.S.S. Stargazer, Here and There"])
    put(s, "Kirk, Man of Action")
    ship = put(s, "U.S.S. Stargazer, Here and There")
    add_charge(s, "U.S.S. Stargazer, Here and There", 6)
    crew = [creature(s, "p1", n, pt="1/1", type_line=f"Token Creature — {t}")
            for n, t in (("O", "Officer"), ("A", "Human Artificer"), ("D", "Doctor"), ("P", "Pilot"), ("S", "Vulcan Scientist"))]
    bear = creature(s, "p1", "Bear", pt="2/2", type_line="Token Creature — Bear")
    theirs = creature(s, "p2", "Their Officer", pt="1/1", type_line="Token Creature — Officer")
    assert [ch(s, c).pt for c in crew] == [(3, 3)] * 5
    assert (ch(s, ship).pt, ch(s, bear).pt, ch(s, theirs).pt, pt(s, "Kirk, Man of Action")) == ((6, 5), (2, 2), (1, 1), (3, 3))
    check(s)


def test_quark_you_cant_sacrifice_your_treasures_while_you_control_it(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Quark, Humble Proprietor"])
    quark = put(s, "Quark, Humble Proprietor")
    act(s, "p1", type="create_token", player="p1", token={"name": "Treasure", "type_line": "Token Artifact — Treasure",
                                                          "text": "{T}, Sacrifice this token: Add one mana of any color."})
    gold = on_field(s, "Treasure")[0]
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=gold.id, ability=0)
    act(s, "p1", type="move", card_ids=[quark.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="activate_ability", card_id=gold.id, ability=0)
    decide(s)
    assert not on_field(s, "Treasure") and sum(mana_pool(s).values()) == 1
    check(s)


def test_quark_makes_a_treasure_at_the_beginning_of_each_upkeep(cards):
    s = build(cards, ["Quark, Humble Proprietor"])
    put(s, "Quark, Humble Proprietor")
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    assert len(on_field(s, "Treasure")) == 1 and not on_field(s, "Treasure", "p2")  # (Bob's upkeep: Quark's controller creates it)
    check(s)


@pytest.mark.parametrize("before", [False, True])
def test_first_contact_gains_two_life_only_as_your_first_spell_of_the_game(cards, before):
    s = build(cards, ["First Contact", "Opt"])
    if before:
        mana(s, U=1)
        cast(s, "Opt")
        answer(s)
    hand = len(s.state.zones["p1:hand"])
    mana(s, G=1, C=1)
    cast(s, "First Contact")
    decide(s)
    assert len(s.state.zones["p1:graveyard"]) == (4 - 1) + 1 + (1 if before else 0)  # (three milled cards stay, First Contact, Opt)
    assert len(s.state.zones["p1:hand"]) == hand + 1  # (a permanent card from among them)
    assert life(s) == (40 if before else 42)
    check(s)


def test_first_contact_cast_first_stays_the_first_spell_after_another_is_cast_in_response(cards):
    """(review) "this spell is the first spell you've cast this game" is a fact about the order of the casts (601.2i): a spell cast after it,
    in response, doesn't make First Contact any less the first one, so it still gains the life as it resolves."""
    s = build(cards, ["First Contact", "Opt"])
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, G=1, C=1)
    cast(s, "First Contact")
    assert s.state.zones["stack"]
    mana(s, U=1)
    cast(s, "Opt")  # (in response: Opt resolves first)
    decide(s)
    assert life(s) == 42
    check(s)


@pytest.mark.parametrize("end", [False, True])
def test_merciful_mandate_untaps_your_attackers_and_may_end_the_combat_phase(cards, end):
    """724.2: yes exiles the stack with the spell, and the game goes on to the postcombat main phase without combat damage."""
    s = build(cards, ["Merciful Mandate"])
    ogre = creature(s, "p1", "Ogre", pt="3/3")
    ready(s, ogre)
    act(s, "p1", type="set_prefs", full_control=True)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ogre.id, "target": "p2"}])
    answer(s)
    assert s.state.cards[ogre.id].tapped
    mana(s, W=1, C=1)
    spell = cast(s, "Merciful Mandate")
    decide(s, "yes" if end else "no")
    assert not s.state.cards[ogre.id].tapped
    assert s.state.cards[spell.id].zone == ("p1:exile" if end else "p1:graveyard")
    if end:
        assert s.state.turn.phase == "main2" and not s.state.cards[ogre.id].attacking
    until(s, lambda s: s.state.turn.phase == "main2" and not s.state.zones.get("stack"))
    assert life(s, "p2") == (40 if end else 37)
    check(s)


def test_merciful_mandate_outside_combat_only_untaps(cards):
    s = build(cards, ["Merciful Mandate"])
    ogre = creature(s, "p1", "Ogre", pt="3/3")
    act(s, "p1", type="tap", card_ids=[ogre.id], tapped=True)
    mana(s, W=1, C=1)
    spell = cast(s, "Merciful Mandate")
    assert s.state.rules.decision is None or s.state.rules.decision.kind != "choose"  # (no question: 724.2g)
    answer(s)
    assert not s.state.cards[ogre.id].tapped and s.state.cards[spell.id].zone == "p1:graveyard" and s.state.turn.phase == "main1"
    check(s)


def test_kang_goads_itself_and_the_target_for_as_long_as_you_control_it(cards):
    """701.15b: goaded by Kang's controller; 611.2b: the designation ends as Alice stops controlling Kang. A goaded creature's attack (Bob's, at
    Carol: not at Alice if able) triggers Kang's counter."""
    from app.game.errors import ActionError

    s = build3(cards, ["Kang, Suspicious Captain"])
    ogre = creature(s, "p2", "Ogre", pt="3/3")
    bear = creature(s, "p2", "Bear", pt="2/2")
    mana(s, R=1, C=3)
    kang = cast(s, "Kang, Suspicious Captain")
    answer(s, ogre.id)
    assert "goaded:p1" in ch(s, kang).imposed and "goaded:p1" in ch(s, ogre).imposed and "goaded:p1" not in ch(s, bear).imposed
    until(s, lambda s: s.state.turn.number == 2 and s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": ogre.id, "target": "p1"}])
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": ogre.id, "target": "p3"}])
    answer(s, kang.id)
    assert s.state.cards[kang.id].counters.get("+1/+1") == 1
    act(s, "p1", type="move", card_ids=[kang.id], to={"player": "p1", "zone": "graveyard"})
    act(s, s.state.rules.priority, type="pass_priority")  # (the rules look at the table again)
    assert "goaded:p1" not in ch(s, ogre).imposed and not any(o.duration == "source_controlled" for o in s.state.rules.effects)
    check(s)


def test_kang_gone_before_its_trigger_resolves_goads_nothing(cards):
    s = build3(cards, ["Kang, Suspicious Captain"])
    ogre = creature(s, "p2", "Ogre", pt="3/3")
    act(s, "p1", type="set_prefs", full_control=True)
    mana(s, R=1, C=3)
    kang = cast(s, "Kang, Suspicious Captain")
    until(s, lambda s: s.state.rules.decision is not None)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[ogre.id])
    assert s.state.zones.get("stack") and s.state.rules.priority == "p1"
    act(s, "p1", type="move", card_ids=[kang.id], to={"player": "p1", "zone": "graveyard"})  # (gone with its trigger on the stack)
    answer(s)
    assert "goaded:p1" not in ch(s, ogre).imposed and not s.state.zones.get("stack")
    check(s)


def station_with(s, name, tapped):
    """Activate the station ability of ``name``, tapping ``tapped``; resolve it."""
    perm = card_named(s, name)
    index = next(a.index for a in ch(s, perm).abilities if a.text.startswith("Tap another untapped creature"))
    act(s, "p1", type="activate_ability", card_id=perm.id, ability=index)
    decide(s, tapped.id)


@pytest.mark.parametrize("sulu, ship, counters", [(True, "U.S.S. Stargazer, Here and There", 6), (False, "U.S.S. Stargazer, Here and There", 2),
                                                  (True, "Adagia, Windswept Bastion", 2)])
def test_sulu_stations_spacecraft_as_though_his_power_were_tripled(cards, sulu, ship, counters):
    """702.184c: a Spacecraft's station ability counts Sulu's power three times; a Planet's (not a Spacecraft) counts it once."""
    s = build(cards, ["Sulu, Heroic Helmsman", ship])
    put(s, ship)
    pilot = put(s, "Sulu, Heroic Helmsman") if sulu else creature(s, "p1", "Pilot", pt="2/2", type_line="Token Creature — Human Pilot")
    station_with(s, ship, pilot)
    assert s.state.cards[card_named(s, ship).id].counters.get("charge") == counters and s.state.cards[pilot.id].tapped
    check(s)


@pytest.mark.parametrize("sulu", [False, True])
def test_sulu_crews_vehicles_as_though_his_power_were_tripled_but_saddles_as_he_is(cards, sulu):
    from app.rules.casting import activatable

    s = build(cards, ["Sulu, Heroic Helmsman", "Consulate Dreadnought", "Unswerving Sloth"])
    wagon = put(s, "Consulate Dreadnought")
    sloth = put(s, "Unswerving Sloth")
    act(s, "p1", type="tap", card_ids=[sloth.id], tapped=True)  # (it can't help crew)
    pilot = put(s, "Sulu, Heroic Helmsman") if sulu else creature(s, "p1", "Pilot", pt="2/2", type_line="Token Creature — Human Pilot")
    usable = {a["card_id"] for a in activatable(s.state, "p1", cards)}
    assert (wagon.id in usable, sloth.id in usable) == (sulu, False)  # (Crew 6: 2 × 3; Saddle 4: still 2)
    if sulu:
        crew = next(a.index for a in ch(s, wagon).abilities if a.text.startswith("Crew"))
        act(s, "p1", type="activate_ability", card_id=wagon.id, ability=crew)
        decide(s, pilot.id)
        assert s.state.cards[pilot.id].tapped and ch(s, wagon).is_creature
    check(s)


def test_lwaxana_makes_the_creatures_triggers_trigger_twice_while_she_stays_tapped(cards):
    """603.2d: an additional instance of each of that creature's triggered abilities; 611.2b: over once Lwaxana untaps."""
    s = build(cards, ["Lwaxana Troi, Charming Guest", "Prosperous Innkeeper", "Llanowar Elves", "Grizzly Bears"])
    lwaxana = put(s, "Lwaxana Troi, Charming Guest")
    inn = put(s, "Prosperous Innkeeper")
    ready(s, lwaxana)
    mana(s, C=2)
    index = next(a.index for a in ch(s, lwaxana).abilities if a.text.startswith("{2}"))
    act(s, "p1", type="activate_ability", card_id=lwaxana.id, ability=index, targets=[inn.id])
    decide(s)
    assert any(r.startswith("trigger_again_111c:") for r in ch(s, inn).imposed) and s.state.cards[lwaxana.id].tapped
    mana(s, G=1)
    cast(s, "Llanowar Elves")
    decide(s)
    assert life(s) == 42  # ("Whenever another creature you control enters": twice)
    act(s, "p1", type="tap", card_ids=[lwaxana.id], tapped=False)
    mana(s, G=2)
    cast(s, "Grizzly Bears")  # (the rules look at the table again: she is untapped, the effect is over)
    decide(s)
    assert life(s) == 43 and not any(r.startswith("trigger_again_111c:") for r in ch(s, inn).imposed)
    check(s)


def test_lwaxana_untapped_before_her_ability_resolves_does_nothing(cards):
    s = build(cards, ["Lwaxana Troi, Charming Guest", "Prosperous Innkeeper"])
    lwaxana = put(s, "Lwaxana Troi, Charming Guest")
    inn = put(s, "Prosperous Innkeeper")
    ready(s, lwaxana)
    act(s, "p1", type="set_prefs", full_control=True, hold_priority=True)  # (Alice keeps priority with the ability on the stack)
    mana(s, C=2)
    index = next(a.index for a in ch(s, lwaxana).abilities if a.text.startswith("{2}"))
    act(s, "p1", type="activate_ability", card_id=lwaxana.id, ability=index, targets=[inn.id])
    act(s, "p1", type="tap", card_ids=[lwaxana.id], tapped=False)  # (untapped in response)
    decide(s)
    assert not any(r.startswith("trigger_again_111c:") for r in ch(s, inn).imposed)
    check(s)


def test_vulcan_mind_meld_each_player_may_play_the_cards_they_exiled_face_down(cards):
    """406.3: whoever looked at a card and exiled it face down may go on looking at it; nobody else may (its owner neither). Each may play the
    cards they exiled, with mana of any type."""
    from app.game.visibility import SPECTATOR, can_see

    s = build3(cards, ["Vulcan Mind-Meld", "Grizzly Bears"], ["Opt", "Llanowar Elves"])
    to_hand(s, "Vulcan Mind-Meld")
    names = {s.state.cards[s.state.zones["p1:library"][0]].name}, {s.state.cards[c].name for c in s.state.zones["p2:library"][:2]}
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Vulcan Mind-Meld").id, targets=["p2"])
    decide(s)
    (mine,), theirs = s.state.zones["p1:exile"], s.state.zones["p2:exile"]  # (face down: new hidden identities)
    assert ({s.state.cards[mine].name}, {s.state.cards[c].name for c in theirs}) == names and len(theirs) == 2
    assert all(s.state.cards[c].face_down for c in (mine, *theirs))
    seen = {cid: [p for p in ("p1", "p2", "p3", SPECTATOR) if can_see(s.state, s.state.cards[cid], p)] for cid in (mine, *theirs)}
    assert seen == {mine: ["p2"], theirs[0]: ["p1"], theirs[1]: ["p1"]}
    allowed = {(p.player, p.card) for p in s.state.rules.permissions}
    assert ("p2", mine) in allowed and {("p1", c) for c in theirs} <= allowed and ("p1", mine) not in allowed
    opt = next(c for c in theirs if s.state.cards[c].name == "Opt")
    hand = len(s.state.zones["p1:hand"])
    mana(s, G=1)  # (mana of any type)
    act(s, "p1", type="cast_spell", card_id=opt)
    decide(s)
    assert s.state.cards[opt].zone == "p2:graveyard" and len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def test_ensign_chekov_lets_you_play_one_chosen_land_card_of_each_opponent_exiled_this_way(cards):
    """X = 2 (Forest, Command Tower: differently named, 201.2); Bob's two cards hold one land (chosen without a question), Carol's two Forests
    are a choice; only the chosen cards may be played (305.2: one as Alice's land play)."""
    s = build3(cards, ["Ensign Pavel Chekov", "Command Tower"], ["Opt"])
    for name in ("Forest", "Command Tower"):
        put(s, name)
    act(s, "p1", type="move", card_ids=[c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"][:1],
        to={"player": "p1", "zone": "battlefield"})  # (a second Forest: still two names)
    bob, carol = s.state.zones["p2:library"][:2], s.state.zones["p3:library"][:2]
    assert sorted(s.state.cards[c].name for c in bob) == ["Forest", "Opt"] and [s.state.cards[c].name for c in carol] == ["Forest", "Forest"]
    mana(s, U=1, C=3)
    cast(s, "Ensign Pavel Chekov")
    d = None
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards":
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p1" and sorted(o.id for o in d.options) == sorted(carol)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[carol[1]])
    decide(s)
    assert all(s.state.cards[c].zone == "p2:exile" for c in bob) and all(s.state.cards[c].zone == "p3:exile" for c in carol)
    island = next(c for c in bob if s.state.cards[c].name == "Forest")  # (Bob's land)
    allowed = {(p.player, p.card) for p in s.state.rules.permissions}
    assert ("p1", island) in allowed and ("p1", carol[1]) in allowed
    assert ("p1", carol[0]) not in allowed and not any(c != island and (p, c) in allowed for p in ("p1", "p2", "p3") for c in bob)
    act(s, "p1", type="play_land", card_id=island)
    assert s.state.cards[island].zone == "p1:battlefield" and s.state.cards[island].owner == "p2"
    check(s)


def test_extraction_integrant_gives_your_artifact_creatures_menace_and_shrinks_each_blocker(cards):
    """509.3b: one trigger for each creature that blocks an artifact creature of Alice's; a nonartifact attacker's blocker is untouched."""
    s = build(cards, ["Extraction Integrant", "Frogmite"])
    integrant = put(s, "Extraction Integrant")
    frog = put(s, "Frogmite")
    bear = creature(s, "p1", "Bear", pt="2/2")
    walls = [creature(s, "p2", f"Wall {i}", pt=pt_) for i, pt_ in enumerate(("1/1", "2/5", "0/4"))]
    ready(s, frog, bear)
    assert [("menace" in ch(s, c).keywords) for c in (integrant, frog, bear)] == [True, True, False]
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in (frog, bear)])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": walls[0].id, "attacker_id": frog.id}, {"blocker_id": walls[1].id, "attacker_id": frog.id},
                                                  {"blocker_id": walls[2].id, "attacker_id": bear.id}])
    decide(s)
    assert walls[0].id not in s.state.zones["p2:battlefield"]  # (0/0: 704.5f)
    assert ch(s, walls[1]).pt == (1, 4) and ch(s, walls[2]).pt == (0, 4)  # (until end of turn; and Frogmite's 2 damage)
    check(s)
