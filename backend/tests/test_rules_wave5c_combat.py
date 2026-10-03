"""Wave 5C: combat, researched against CR 2026-09-25.

* Attack costs (508.1d, 508.1h-j): Propaganda / Ghostly Prison / Windborn Muse / Elephant Grass. The total is locked in
  after the declaration, mana abilities may be activated, everything is paid at once; without the payment the
  declaration is made again. Requirements never force a paid attack (508.1d).
* "No more than two creatures can attack you each combat." (Crawlspace, 508.1c), with requirements weighed over the
  whole declaration (508.1d).
* Block restrictions about the attacker's controller (509.1b): Champion of Lambholt, Bower Passage.
* Requirements from effects (508.1d, 611.2c): Bident of Thassa, Rage Nimbus, Goblin Diplomats, Kardur, The Akroan War.
* Additional combat phases (500.8): Seize the Day, Aggravated Assault, Aurelia.
* Tokens put onto the battlefield attacking (508.4): Adeline, Soaring Lightbringer.

Every scenario checks the replay; the longer ones also reload the game from its saved history.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.handlers.turn import PHASE_LABELS
from app.game.session import GameSession
from app.rules import combat_rules, coverage, statics
from app.rules.combat import block_problem
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_attachments import ch, named, token
from tests.test_rules_conditionals import settle, through_combat, until, until_asked
from tests.test_rules_effects import replay_matches

# Real Oracle wording (the local card database, current).
EXTRA = [
    card('Propaganda', set_code="tst", number="C01", mana_cost='{2}{U}', cmc=3.0, type_line='Enchantment', oracle_text="Creatures can't attack you unless their controller pays {2} for each creature they control that's attacking you.", colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Ghostly Prison', set_code="tst", number="C02", mana_cost='{2}{W}', cmc=3.0, type_line='Enchantment', oracle_text="Creatures can't attack you unless their controller pays {2} for each creature they control that's attacking you.", colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card('Windborn Muse', set_code="tst", number="C03", mana_cost='{3}{W}', cmc=4.0, type_line='Creature — Spirit', oracle_text="Flying\nCreatures can't attack you unless their controller pays {2} for each creature they control that's attacking you.", power='2', toughness='3', colors=['W'], color_identity=['W'], keywords=['Flying']),  # noqa: E501
    card('Elephant Grass', set_code="tst", number="C04", mana_cost='{G}', cmc=1.0, type_line='Enchantment', oracle_text="Cumulative upkeep {1} (At the beginning of your upkeep, put an age counter on this permanent, then sacrifice it unless you pay its upkeep cost for each age counter on it.)\nBlack creatures can't attack you.\nNonblack creatures can't attack you unless their controller pays {2} for each creature they control that's attacking you.", colors=['G'], color_identity=['G'], keywords=['Cumulative upkeep']),  # noqa: E501
    card('Crawlspace', set_code="tst", number="C05", mana_cost='{3}', cmc=3.0, type_line='Artifact', oracle_text='No more than two creatures can attack you each combat.', colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Champion of Lambholt', set_code="tst", number="C06", mana_cost='{1}{G}{G}', cmc=3.0, type_line='Creature — Human Warrior', oracle_text="Creatures with power less than this creature's power can't block creatures you control.\nWhenever another creature you control enters, put a +1/+1 counter on this creature.", power='1', toughness='1', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Bower Passage', set_code="tst", number="C07", mana_cost='{1}{G}', cmc=2.0, type_line='Enchantment', oracle_text="Creatures with flying can't block creatures you control.", colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Bident of Thassa', set_code="tst", number="C08", mana_cost='{2}{U}{U}', cmc=4.0, type_line='Legendary Enchantment Artifact', oracle_text='Whenever a creature you control deals combat damage to a player, you may draw a card.\n{1}{U}, {T}: Creatures your opponents control attack this turn if able.', colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Kardur, Doomscourge', set_code="tst", number="C09", mana_cost='{2}{B}{R}', cmc=4.0, type_line='Legendary Creature — Demon Berserker', oracle_text='When Kardur enters, until your next turn, creatures your opponents control attack each combat if able and attack a player other than you if able.\nWhenever an attacking creature dies, each opponent loses 1 life and you gain 1 life.', power='4', toughness='3', colors=['B', 'R'], color_identity=['B', 'R'], keywords=[]),  # noqa: E501
    card('The Akroan War', set_code="tst", number="C10", mana_cost='{3}{R}', cmc=4.0, type_line='Enchantment — Saga', oracle_text='(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Gain control of target creature for as long as this Saga remains on the battlefield.\nII — Until your next turn, creatures your opponents control attack each combat if able.\nIII — Each tapped creature deals damage to itself equal to its power.', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Rage Nimbus', set_code="tst", number="C11", mana_cost='{2}{R}', cmc=3.0, type_line='Creature — Elemental', oracle_text='Defender, flying\n{1}{R}: Target creature attacks this turn if able.', power='5', toughness='3', colors=['R'], color_identity=['R'], keywords=['Flying', 'Defender']),  # noqa: E501
    card('Goblin Diplomats', set_code="tst", number="C12", mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Goblin', oracle_text='{T}: Each creature attacks this turn if able.', power='2', toughness='1', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Aggravated Assault', set_code="tst", number="C13", mana_cost='{2}{R}', cmc=3.0, type_line='Enchantment', oracle_text='{3}{R}{R}: Untap all creatures you control. After this main phase, there is an additional combat phase followed by an additional main phase. Activate only as a sorcery.', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Seize the Day', set_code="tst", number="C14", mana_cost='{3}{R}', cmc=4.0, type_line='Sorcery', oracle_text='Untap target creature. After this main phase, there is an additional combat phase followed by an additional main phase.\nFlashback {2}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)', colors=['R'], color_identity=['R'], keywords=['Flashback']),  # noqa: E501
    card('Aurelia, the Warleader', set_code="tst", number="C15", mana_cost='{2}{R}{R}{W}{W}', cmc=6.0, type_line='Legendary Creature — Angel', oracle_text='Flying, vigilance, haste\nWhenever Aurelia attacks for the first time each turn, untap all creatures you control. After this phase, there is an additional combat phase.', power='3', toughness='4', colors=['R', 'W'], color_identity=['R', 'W'], keywords=['Flying', 'Vigilance', 'Haste']),  # noqa: E501
    card('Adeline, Resplendent Cathar', set_code="tst", number="C16", mana_cost='{1}{W}{W}', cmc=3.0, type_line='Legendary Creature — Human Knight', oracle_text="Vigilance\nAdeline's power is equal to the number of creatures you control.\nWhenever you attack, for each opponent, create a 1/1 white Human creature token that's tapped and attacking that player or a planeswalker they control.", power='*', toughness='4', colors=['W'], color_identity=['W'], keywords=['Vigilance']),  # noqa: E501
    card('Soaring Lightbringer', set_code="tst", number="C17", mana_cost='{4}{W}', cmc=5.0, type_line='Enchantment Creature — Bird Glimmer', oracle_text="Flying\nOther enchantment creatures you control have flying.\nWhenever you attack a player, create a 1/1 white Glimmer enchantment creature token that's tapped and attacking that player.", power='4', toughness='5', colors=['W'], color_identity=['W'], keywords=['Flying']),  # noqa: E501
    card('Maze of Ith', set_code="tst", number="C18", mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}: Untap target attacking creature. Prevent all combat damage that would be dealt to and dealt by that creature this turn.', colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Reconnaissance', set_code="tst", number="C19", mana_cost='{W}', cmc=1.0, type_line='Enchantment', oracle_text='{0}: Remove target attacking creature you control from combat and untap it. (If you activate during end of combat, the creature will untap after it deals combat damage.)', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card('Unnatural Growth', set_code="tst", number="C20", mana_cost='{1}{G}{G}{G}{G}', cmc=5.0, type_line='Enchantment', oracle_text='At the beginning of each combat, double the power and toughness of each creature you control until end of turn.', colors=['G'], color_identity=['G'], keywords=['Double']),  # noqa: E501
    card('Bulk Up', set_code="tst", number="C21", mana_cost='{1}{R}', cmc=2.0, type_line='Instant', oracle_text="Double target creature's power until end of turn.\nFlashback {4}{R}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)", colors=['R'], color_identity=['R'], keywords=['Flashback', 'Double']),  # noqa: E501
    card('Relentless Assault', set_code="tst", number="C22", mana_cost='{2}{R}{R}', cmc=4.0, type_line='Sorcery', oracle_text='Untap all creatures that attacked this turn. After this main phase, there is an additional combat phase followed by an additional main phase.', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Hellkite Charger', set_code="tst", number="C23", mana_cost='{4}{R}{R}', cmc=6.0, type_line='Creature — Dragon', oracle_text='Flying, haste\nWhenever this creature attacks, you may pay {5}{R}{R}. If you do, untap all attacking creatures and after this phase, there is an additional combat phase.', power='5', toughness='5', colors=['R'], color_identity=['R'], keywords=['Flying', 'Haste']),  # noqa: E501
    card('Finest Hour', set_code="tst", number="C24", mana_cost='{2}{G}{W}{U}', cmc=5.0, type_line='Enchantment', oracle_text="Exalted (Whenever a creature you control attacks alone, that creature gets +1/+1 until end of turn.)\nWhenever a creature you control attacks alone, if it's the first combat phase of the turn, untap that creature. After this phase, there is an additional combat phase.", colors=['G', 'U', 'W'], color_identity=['G', 'U', 'W'], keywords=['Exalted']),  # noqa: E501
    # (still manual)
    card('Karlach, Fury of Avernus', set_code="tst", number="C30", mana_cost='{4}{R}', cmc=5.0, type_line='Legendary Creature — Tiefling Barbarian', oracle_text="Whenever you attack, if it's the first combat phase of the turn, untap all attacking creatures. They gain first strike until end of turn. After this phase, there is an additional combat phase.\nChoose a Background (You can have a Background as a second commander.)", power='5', toughness='4', colors=['R'], color_identity=['R'], keywords=['Choose a background']),  # noqa: E501
    card('Sphere of Safety', set_code="tst", number="C31", mana_cost='{4}{W}', cmc=5.0, type_line='Enchantment', oracle_text="Creatures can't attack you or planeswalkers you control unless their controller pays {X} for each of those creatures, where X is the number of enchantments you control.", colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card('Nahiri, the Unforgiving', set_code="tst", number="C32", mana_cost='{1}{R}{W/P}{W}', cmc=4.0, type_line='Legendary Planeswalker — Nahiri', oracle_text="Compleated\n+1: Until your next turn, up to one target creature attacks a player each combat if able.\n−2: Discard a card, then draw a card.", colors=['R', 'W'], color_identity=['R', 'W'], keywords=['Compleated']),  # noqa: E501
]
FULL = ["Propaganda", "Ghostly Prison", "Windborn Muse", "Elephant Grass", "Crawlspace", "Champion of Lambholt",
        "Bower Passage", "Bident of Thassa", "Kardur, Doomscourge", "The Akroan War", "Rage Nimbus", "Goblin Diplomats",
        "Aggravated Assault", "Seize the Day", "Aurelia, the Warleader", "Adeline, Resplendent Cathar",
        "Soaring Lightbringer", "Karlach, Fury of Avernus", "Maze of Ith", "Reconnaissance", "Unnatural Growth", "Bulk Up",
        "Relentless Assault", "Hellkite Charger", "Finest Hour"]
STILL_MANUAL = {
    "Sphere of Safety": "{X}",  # (a cost sized by a count, and planeswalkers too)
    "Nahiri, the Unforgiving": "attacks a player each combat",
}


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def reloaded(s):
    """The table as a fresh session rebuilt from the saved history (a save and a load)."""
    return GameSession(s.history.rebuild(), cards=s.cards)


def build(cards, *names, players=2, forests=9, payment="auto", bob=()):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (forests, "Forest")])
    seats = [PlayerSetup("Alice", cards=alice),
             PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (10, "Island")])),
             PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(1, "Gideon Jura"), (10, "Mountain")]))][:players]
    state = enable(new_game(seats, shuffle=False))
    for prefs in state.rules.prefs.values():
        prefs.payment = payment
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    for pid in list(s.state.players)[1:]:  # (a wall each, so that combat waits for blockers)
        token(s, pid, f"Wall {pid}", "0/4", "Defender")
    return s


def put(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def lands(s, n, pid="p1", name="Forest"):
    ids = [c.id for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"][:n]
    act(s, pid, type="move", card_ids=ids, to={"player": pid, "zone": "battlefield"})
    return ids


def old(s, pid, name, pt="2/2", text=""):
    """A creature that can attack this turn (haste: 302.6)."""
    return token(s, pid, name, pt, "\n".join(x for x in ("Haste", text) if x))


def to_attack(s, number=1):
    until(s, lambda s: s.state.turn.number == number and s.state.rules.decision is not None
          and s.state.rules.decision.kind == "declare_attackers")


def declare(s, *pairs, pid="p1"):
    act(s, pid, type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in pairs])


def plan(s):
    return Plan(s.state, "p1", s.cards, None)


def attacking(s, c):
    a = s.state.cards[c.id].attacking
    return a.id if a is not None else None


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
    "Creatures can't attack you unless their controller pays {X} for each creature they control that's attacking you.",
    "~ can't attack you unless its controller pays {2}.",
    "No more than two creatures can block each combat.",
    "Creatures with power less than ~'s power can't block it.",  # (Wandering Wolf: its own grammar, not this)
])
def test_refused_or_other_wordings(text):
    assert combat_rules.static_definition(text) is None


def test_attacks_each_combat_needs_a_duration():
    from app.rules import scripts

    assert scripts.parse_effects("Creatures your opponents control attack each combat if able.") is not None  # (parsed …)
    from tests.test_rules_scripts import ch as characteristics

    chs = characteristics("Test", "Sorcery", "Creatures your opponents control attack each combat if able.")
    assert coverage.of_characteristics(chs).level != "FULL"  # … but without a duration it isn't a definition


# -- attack costs (508.1h) --------------------------------------------------------------------------------------
def test_propaganda_cost_is_paid_with_the_attack(cards):
    """Two creatures attack Bob, who has Propaganda: {4}, paid (the engine pays: AUTO) after the declaration; the
    attackers aren't tapped to pay it (508.1f)."""
    s = build(cards, bob=["Propaganda"])
    put(s, "Propaganda", "p2")
    forests = lands(s, 4)
    a, b = old(s, "p1", "Ogre"), old(s, "p1", "Wolf")
    to_attack(s)
    declare(s, (a, "p2"), (b, "p2"))
    assert attacking(s, a) == "p2" and attacking(s, b) == "p2"
    assert all(s.state.cards[f].tapped for f in forests)
    through_combat(s)
    assert s.state.players["p2"].life == 36
    replay_matches(s)
    replay_matches(reloaded(s))


def test_propaganda_unpayable_declaration_is_illegal(cards):
    s = build(cards, bob=["Propaganda"])
    put(s, "Propaganda", "p2")
    lands(s, 3)
    a, b = old(s, "p1", "Ogre"), old(s, "p1", "Wolf")
    to_attack(s)
    with pytest.raises(ActionError, match=r"Attacking costs \{4\}"):
        declare(s, (a, "p2"), (b, "p2"))
    declare(s, (a, "p2"))  # {2}: payable
    assert attacking(s, a) == "p2" and attacking(s, b) is None
    replay_matches(s)


def test_two_attack_cost_statics_add_up_and_planeswalkers_are_free(cards):
    """Propaganda and Ghostly Prison each cost {2} per creature (508.1h: the total)."""
    s = build(cards, bob=["Propaganda", "Ghostly Prison"])
    put(s, "Propaganda", "p2")
    put(s, "Ghostly Prison", "p2")
    lands(s, 4)
    a = old(s, "p1", "Ogre")
    p = plan(s)
    assert combat_rules.attack_cost(p, [(a.id, "p2")]) == 4
    to_attack(s)
    declare(s, (a, "p2"))
    assert attacking(s, a) == "p2"
    replay_matches(s)


def test_tap_your_own_mana_then_cancel_or_pay(cards):
    """With players tapping their own mana, the declaration opens the "tap your mana" prompt (508.1i: mana abilities
    while it's open); cancelling asks for attackers again; paying finishes the declaration."""
    s = build(cards, payment="self", bob=["Propaganda"])
    put(s, "Propaganda", "p2")
    forests = lands(s, 2)
    a = old(s, "p1", "Ogre")
    to_attack(s)
    declare(s, (a, "p2"))
    d = s.state.rules.decision
    assert d is not None and d.display["kind"] == "tap_mana" and d.display["cost"] == "{2}"
    assert attacking(s, a) is None and not s.state.cards[a.id].tapped
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["cancel"])
    assert s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers"
    declare(s, (a, "p2"))
    act(s, "p1", type="activate_ability", card_id=forests[0], ability=0)
    assert attacking(s, a) is None
    act(s, "p1", type="activate_ability", card_id=forests[1], ability=0)  # the pool covers it: the attack is made
    assert attacking(s, a) == "p2" and s.state.cards[a.id].tapped
    assert s.state.players["p1"].mana == {}
    through_combat(s)
    assert s.state.players["p2"].life == 38
    replay_matches(s)
    replay_matches(reloaded(s))


def test_multiplayer_only_the_player_with_propaganda_costs(cards):
    s = build(cards, players=3, bob=["Windborn Muse"])
    put(s, "Windborn Muse", "p2")
    forests = lands(s, 2)
    a, b = old(s, "p1", "Ogre"), old(s, "p1", "Wolf")
    to_attack(s)
    declare(s, (a, "p3"), (b, "p2"))
    assert attacking(s, a) == "p3" and attacking(s, b) == "p2"
    assert all(s.state.cards[f].tapped for f in forests)
    replay_matches(s)


def test_requirements_never_force_a_paid_attack(cards):
    """508.1d: Rage Nimbus makes the Ogre attack if able, but Bob's Propaganda is a cost: attacking with nothing is
    legal. Without the cost the requirement holds."""
    s = build(cards, "Rage Nimbus", bob=["Propaganda"])
    nimbus = put(s, "Rage Nimbus")
    put(s, "Propaganda", "p2")
    lands(s, 4)
    a = old(s, "p1", "Ogre")
    act(s, "p1", type="add_mana", player="p1", mana={"R": 2})
    act(s, "p1", type="activate_ability", card_id=nimbus.id, ability=1, targets=[a.id])
    settle(s)
    assert "must_attack" in ch(s, a).imposed
    to_attack(s)
    declare(s)
    assert s.state.players["p2"].life == 40 and s.state.turn.phase in ("end_combat", "main2")
    replay_matches(s)


def test_rage_nimbus_requirement_without_a_cost(cards):
    s = build(cards, "Rage Nimbus")
    nimbus = put(s, "Rage Nimbus")
    a = old(s, "p1", "Ogre")
    act(s, "p1", type="add_mana", player="p1", mana={"R": 2})
    act(s, "p1", type="activate_ability", card_id=nimbus.id, ability=1, targets=[a.id])
    settle(s)
    to_attack(s)
    with pytest.raises(ActionError, match="attacks each combat if able"):
        declare(s)
    declare(s, (a, "p2"))
    through_combat(s)
    until(s, lambda s: s.state.turn.number == 2)
    assert "must_attack" not in ch(s, a).imposed  # this turn only (514.2)
    replay_matches(s)


def test_elephant_grass(cards):
    s = build(cards, bob=["Elephant Grass"])
    put(s, "Elephant Grass", "p2")
    lands(s, 2)
    a = old(s, "p1", "Ogre")
    act(s, "p1", type="create_token", player="p1", token={"name": "Shade", "type_line": "Token Creature — Shade",
                                                         "power": "1", "toughness": "1", "colors": ["B"], "text": ""})
    shade = named(s, "Shade")
    to_attack(s)
    with pytest.raises(ActionError, match="can't attack"):
        declare(s, (shade, "p2"))
    declare(s, (a, "p2"))
    assert attacking(s, a) == "p2"
    replay_matches(s)


# -- attack limits (508.1c) -------------------------------------------------------------------------------------
def test_crawlspace_limit(cards):
    s = build(cards, bob=["Crawlspace"])
    put(s, "Crawlspace", "p2")
    a, b, c = old(s, "p1", "Ogre"), old(s, "p1", "Wolf"), old(s, "p1", "Bear")
    to_attack(s)
    with pytest.raises(ActionError, match="No more than 2 creatures can attack Bob"):
        declare(s, (a, "p2"), (b, "p2"), (c, "p2"))
    declare(s, (a, "p2"), (b, "p2"))
    through_combat(s)
    assert s.state.players["p2"].life == 36
    replay_matches(s)


def test_crawlspace_with_requirements_weighs_the_whole_declaration(cards):
    """Goblin Diplomats: each creature attacks if able. Bob's Crawlspace lets two attack him; Carol can take the rest.
    Two at Bob and one at Carol obey all three requirements; two at Bob alone obey only two (508.1d)."""
    s = build(cards, "Goblin Diplomats", players=3, bob=["Crawlspace"])
    diplomats = put(s, "Goblin Diplomats")
    put(s, "Crawlspace", "p2")
    a, b, c = old(s, "p1", "Ogre"), old(s, "p1", "Wolf"), old(s, "p1", "Bear")
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1")  # (the Diplomats' {T}: 302.6)
    act(s, "p1", type="activate_ability", card_id=diplomats.id, ability=0)
    settle(s)
    to_attack(s, 4)
    with pytest.raises(ActionError, match="508.1d"):
        declare(s, (a, "p2"), (b, "p2"))
    declare(s, (a, "p2"), (b, "p2"), (c, "p3"))
    assert attacking(s, c) == "p3"
    replay_matches(s)


# -- blocks (509.1b) --------------------------------------------------------------------------------------------
def test_champion_of_lambholt_and_bower_passage(cards):
    s = build(cards, "Champion of Lambholt", "Bower Passage")
    champ = put(s, "Champion of Lambholt")
    act(s, "p1", type="counter", card_ids=[champ.id], kind="+1/+1", delta=2)  # 3/3
    bear = old(s, "p1", "Bear")
    small, big = old(s, "p2", "Small", "2/2"), old(s, "p2", "Big", "3/3")
    p = plan(s)

    def problem(blocker):
        return block_problem(s.state, s.state.cards[blocker.id], p.ch(s.state.cards[blocker.id]),
                             s.state.cards[bear.id], p.ch(s.state.cards[bear.id]), s.cards)

    assert "can't block creatures Alice controls" in problem(small)
    assert problem(big) is None
    flier = old(s, "p2", "Flier", "4/4", "Flying")
    assert problem(flier) is None
    put(s, "Bower Passage")
    p = plan(s)
    assert "can't block creatures Alice controls" in problem(flier)
    # Bob's own creatures aren't Alice's: his small creature may block a creature Carol … (here: his own rule applies
    # only to Alice's attackers)
    to_attack(s)
    declare(s, (bear, "p2"))
    d = s.state.rules.decision
    with pytest.raises(ActionError, match="can't block"):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": small.id, "attacker_id": bear.id}])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": big.id, "attacker_id": bear.id}])
    assert d is not None
    replay_matches(s)
    replay_matches(reloaded(s))


# -- requirements from effects (508.1d) -------------------------------------------------------------------------
def test_bident_of_thassa_applies_to_opponents_creatures_this_turn(cards):
    s = build(cards, "Bident of Thassa")
    bident = put(s, "Bident of Thassa")
    mine, theirs = old(s, "p1", "Mine"), old(s, "p2", "Theirs")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 2})
    act(s, "p1", type="activate_ability", card_id=bident.id, ability=1)
    settle(s)
    later = old(s, "p2", "Later")  # 611.2c: not locked in
    assert "must_attack" in ch(s, theirs).imposed and "must_attack" in ch(s, later).imposed
    assert "must_attack" not in ch(s, mine).imposed
    until(s, lambda s: s.state.turn.number == 2)
    assert "must_attack" not in ch(s, theirs).imposed
    replay_matches(s)


def test_kardur_until_your_next_turn(cards):
    """Bob's creature must attack, and attack someone other than Alice, until Alice's next turn (3 players)."""
    s = build(cards, "Kardur, Doomscourge", players=3)
    theirs = old(s, "p2", "Theirs")
    kardur = named(s, "Kardur, Doomscourge")
    act(s, "p1", type="move", card_ids=[kardur.id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"B": 1, "R": 1, "C": 2})
    act(s, "p1", type="cast_spell", card_id=kardur.id)
    settle(s)
    assert {"must_attack", "attack_other_than:p1"} <= ch(s, theirs).imposed
    assert not {"must_attack", "attack_other_than:p1"} & ch(s, kardur).imposed
    until(s, lambda s: s.state.turn.number == 2 and s.state.rules.decision is not None
          and s.state.rules.decision.kind == "declare_attackers")
    with pytest.raises(ActionError, match="attacks each combat if able"):
        declare(s, pid="p2")
    with pytest.raises(ActionError, match="a player other than Alice"):
        declare(s, (theirs, "p1"), pid="p2")
    declare(s, (theirs, "p3"), pid="p2")
    assert attacking(s, theirs) == "p3"
    s = reloaded(s)
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1")
    assert "must_attack" not in ch(s, theirs).imposed  # until Alice's next turn
    replay_matches(s)


# -- additional combat phases (500.8) ---------------------------------------------------------------------------
_KEYS = {f"— {label} —": key for key, label in PHASE_LABELS.items()}


def phases_logged(s, since=0, turn=1):
    """The phases and steps the turn went through, from the table log (after entry ``since``)."""
    return [_KEYS[e.parts[0].t] for e in s.state.log[since:] if e.kind == "phase" and e.turn == turn and e.parts
            and e.parts[0].t in _KEYS]


def to_blocks(s, limit=30):
    """Let the attack triggers resolve, up to the declare blockers step (or the end of combat)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_blockers", "declare_attackers"):
            return
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never got to blockers")


def test_seize_the_day_in_the_first_main_phase(cards):
    """After this main phase: an additional combat phase and main phase, then the turn's own combat (500.8)."""
    s = build(cards, "Seize the Day")
    bear = old(s, "p1", "Bear")
    seize = next(c for c in s.state.cards.values() if c.name == "Seize the Day")
    act(s, "p1", type="move", card_ids=[seize.id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"R": 4})
    act(s, "p1", type="cast_spell", card_id=seize.id, targets=[bear.id])
    settle(s)
    assert s.state.rules.extra_phases == ["begin_combat", "main2", "begin_combat"]
    mark = len(s.state.log)
    until(s, lambda s: s.state.turn.number == 2)
    assert phases_logged(s, mark) == ["begin_combat", "declare_attackers", "end_combat", "main2", "begin_combat",
                                      "declare_attackers", "end_combat", "main2", "end", "cleanup"]
    assert s.state.rules.extra_phases == []
    replay_matches(s)


def test_aggravated_assault_after_combat(cards):
    """Attack, then in the second main phase untap everything: one more combat and one more main phase."""
    s = build(cards, "Aggravated Assault")
    assault = put(s, "Aggravated Assault")
    bear = old(s, "p1", "Bear")
    to_attack(s)
    declare(s, (bear, "p2"))
    through_combat(s)
    assert s.state.cards[bear.id].tapped and s.state.players["p2"].life == 38
    act(s, "p1", type="add_mana", player="p1", mana={"R": 5})
    act(s, "p1", type="activate_ability", card_id=assault.id, ability=0)
    settle(s)
    assert not s.state.cards[bear.id].tapped
    assert s.state.rules.extra_phases == ["begin_combat", "main2", "end"]
    s = reloaded(s)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    assert s.state.turn.number == 1 and s.state.rules.combats == 2
    declare(s, (bear, "p2"))
    through_combat(s)
    assert s.state.players["p2"].life == 36 and s.state.turn.phase == "main2" and s.state.turn.number == 1
    mark = len(s.state.log)
    until(s, lambda s: s.state.turn.number == 2)
    assert phases_logged(s, mark) == ["end", "cleanup"]
    replay_matches(s)


def test_aurelia_second_combat(cards):
    s = build(cards, "Aurelia, the Warleader")
    aurelia = put(s, "Aurelia, the Warleader")
    bear = old(s, "p1", "Bear")
    to_attack(s)
    declare(s, (aurelia, "p2"), (bear, "p2"))
    to_blocks(s)
    assert not s.state.cards[bear.id].tapped  # untap all creatures you control
    assert s.state.rules.extra_phases == ["begin_combat", "main2"]
    mark = len(s.state.log)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    assert "main2" not in phases_logged(s, mark) and s.state.players["p2"].life == 35
    declare(s, (aurelia, "p2"), (bear, "p2"))
    to_blocks(s)
    assert s.state.rules.extra_phases == ["main2"]  # (not the first time this turn: no trigger)
    through_combat(s)
    assert s.state.players["p2"].life == 30 and s.state.turn.number == 1
    replay_matches(s)
    replay_matches(reloaded(s))


# -- tokens entering attacking (508.4) --------------------------------------------------------------------------
def test_adeline_one_token_attacking_each_opponent(cards):
    s = build(cards, "Adeline, Resplendent Cathar", players=3)
    adeline = put(s, "Adeline, Resplendent Cathar")
    to_attack(s, 4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": adeline.id, "target": "p2"}])
    to_blocks(s)
    humans = [c for c in s.state.cards.values() if c.name == "Human" and c.zone == "p1:battlefield"]
    assert sorted(attacking(s, h) for h in humans) == ["p2", "p3"]
    assert all(h.tapped for h in humans)
    replay_matches(s)
    replay_matches(reloaded(s))


def test_soaring_lightbringer_token_attacks_that_player(cards):
    s = build(cards, "Soaring Lightbringer", players=3)
    put(s, "Soaring Lightbringer")
    a, b = old(s, "p1", "Ogre"), old(s, "p1", "Wolf")
    to_attack(s)
    declare(s, (a, "p2"), (b, "p3"))
    to_blocks(s)
    glimmers = [c for c in s.state.cards.values() if c.name == "Glimmer" and c.zone == "p1:battlefield"]
    assert sorted(attacking(s, g) for g in glimmers) == ["p2", "p3"]
    replay_matches(s)


def test_statics_parse_for_the_combat_rules():
    d = combat_rules.static_definition("Creatures can't attack you unless their controller pays {2} for each creature "
                                       "they control that's attacking you.")
    assert d is not None and d["rules"] == ["attack_tax:@you:2:@src"]
    assert statics.parse("Creatures with flying can't block creatures you control.") is None  # (read here, not there)


# -- more combat wordings ----------------------------------------------------------------------------------------
def respond_on(s):
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"


def test_maze_of_ith(cards):
    """Untap the attacker; combat damage to it and by it this turn is prevented (615)."""
    s = build(cards, bob=["Maze of Ith"])
    maze = put(s, "Maze of Ith", "p2")
    ogre = old(s, "p1", "Ogre", "3/3")
    to_attack(s)
    respond_on(s)
    declare(s, (ogre, "p2"))
    act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    act(s, "p2", type="activate_ability", card_id=maze.id, ability=0, targets=[ogre.id])
    settle(s)
    assert not s.state.cards[ogre.id].tapped and attacking(s, ogre) == "p2"
    through_combat(s)
    assert s.state.players["p2"].life == 40
    replay_matches(s)
    replay_matches(reloaded(s))


def test_reconnaissance_removes_from_combat(cards):
    s = build(cards, "Reconnaissance")
    recon = put(s, "Reconnaissance")
    ogre, wolf = old(s, "p1", "Ogre", "3/3"), old(s, "p1", "Wolf")
    to_attack(s)
    respond_on(s)
    declare(s, (ogre, "p2"), (wolf, "p2"))
    assert s.state.rules.priority == "p1"
    act(s, "p1", type="activate_ability", card_id=recon.id, ability=0, targets=[ogre.id])
    settle(s)
    assert attacking(s, ogre) is None and not s.state.cards[ogre.id].tapped  # 506.4
    assert attacking(s, wolf) == "p2"
    through_combat(s)
    assert s.state.players["p2"].life == 38
    replay_matches(s)


def test_unnatural_growth_and_bulk_up(cards):
    """701.10b: +X/+Y with X and Y the creature's power and toughness as the effect begins (layer 7c)."""
    s = build(cards, "Unnatural Growth", "Bulk Up")
    put(s, "Unnatural Growth")
    ogre = old(s, "p1", "Ogre", "3/2")
    act(s, "p1", type="counter", card_ids=[ogre.id], kind="+1/+1", delta=1)  # 4/3
    bulk = named(s, "Bulk Up")
    act(s, "p1", type="move", card_ids=[bulk.id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"R": 2})
    act(s, "p1", type="cast_spell", card_id=bulk.id, targets=[ogre.id])
    settle(s)
    assert ch(s, ogre).pt == (8, 3)
    to_attack(s)
    assert ch(s, ogre).pt == (16, 6)  # "At the beginning of each combat": both doubled
    act(s, "p1", type="counter", card_ids=[ogre.id], kind="+1/+1", delta=1)
    assert ch(s, ogre).pt == (17, 7)  # (a fixed modification: the counter isn't doubled after the fact)
    s = reloaded(s)
    until(s, lambda s: s.state.turn.number == 2)
    assert ch(s, ogre).pt == (5, 4)
    replay_matches(s)


def test_relentless_assault_untaps_the_creatures_that_attacked(cards):
    s = build(cards, "Relentless Assault")
    ogre, tapped = old(s, "p1", "Ogre", "3/3"), old(s, "p1", "Tapped")
    act(s, "p1", type="tap", card_ids=[tapped.id], tapped=True)
    to_attack(s)
    declare(s, (ogre, "p2"))
    through_combat(s)
    assault = named(s, "Relentless Assault")
    act(s, "p1", type="move", card_ids=[assault.id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"R": 4})
    act(s, "p1", type="cast_spell", card_id=assault.id)
    settle(s)
    assert not s.state.cards[ogre.id].tapped and s.state.cards[tapped.id].tapped
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    declare(s, (ogre, "p2"))
    through_combat(s)
    assert s.state.players["p2"].life == 34 and s.state.turn.number == 1
    replay_matches(s)


def test_hellkite_charger_pays_for_another_combat(cards):
    s = build(cards, "Hellkite Charger")
    charger = put(s, "Hellkite Charger")
    to_attack(s)
    respond_on(s)
    declare(s, (charger, "p2"))
    act(s, "p1", type="add_mana", player="p1", mana={"R": 7})  # (mana empties between steps: 500.4)
    d = until_asked(s)
    assert d is not None and {o.id for o in d.options} == {"pay", "decline"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    to_blocks(s)
    assert not s.state.cards[charger.id].tapped and s.state.rules.extra_phases == ["begin_combat", "main2"]
    replay_matches(s)


def test_finest_hour_only_in_the_first_combat(cards):
    s = build(cards, "Finest Hour")
    put(s, "Finest Hour")
    ogre = old(s, "p1", "Ogre", "3/3")
    to_attack(s)
    declare(s, (ogre, "p2"))
    to_blocks(s)
    assert not s.state.cards[ogre.id].tapped and s.state.rules.extra_phases == ["begin_combat", "main2"]
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    declare(s, (ogre, "p2"))
    to_blocks(s)
    assert s.state.cards[ogre.id].tapped and s.state.rules.extra_phases == ["main2"]  # (603.4: not the first combat)
    through_combat(s)
    assert s.state.players["p2"].life == 31  # (exalted each time, until end of turn: 4, then 5)
    replay_matches(s)
    replay_matches(reloaded(s))


def test_karlach_first_strike_for_the_untapped_attackers(cards):
    s = build(cards, "Karlach, Fury of Avernus")
    ogre, wolf = old(s, "p1", "Ogre", "3/3"), old(s, "p1", "Wolf")
    put(s, "Karlach, Fury of Avernus")
    to_attack(s)
    declare(s, (ogre, "p2"))
    to_blocks(s)
    assert not s.state.cards[ogre.id].tapped and "first strike" in ch(s, ogre).keywords
    assert "first strike" not in ch(s, wolf).keywords
    assert s.state.rules.extra_phases == ["begin_combat", "main2"]
    replay_matches(s)


def test_adeline_token_may_attack_a_planeswalker(cards):
    s = build(cards, "Adeline, Resplendent Cathar", players=3)
    gideon = next(c for c in s.state.cards.values() if c.name == "Gideon Jura")
    act(s, "p3", type="move", card_ids=[gideon.id], to={"player": "p3", "zone": "battlefield"})
    act(s, "p3", type="counter", card_ids=[gideon.id], kind="loyalty", delta=6)
    adeline = put(s, "Adeline, Resplendent Cathar")
    to_attack(s, 4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": adeline.id, "target": "p2"}])
    d = until_asked(s)
    while d is not None and d.kind != "choose_one":
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        d = until_asked(s)
    assert d is not None and {o.id for o in d.options} == {"p3", gideon.id}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[gideon.id])
    to_blocks(s)
    humans = [c for c in s.state.cards.values() if c.name == "Human" and c.zone == "p1:battlefield"]
    assert sorted(attacking(s, h) for h in humans) == sorted(["p2", gideon.id])
    replay_matches(s)
