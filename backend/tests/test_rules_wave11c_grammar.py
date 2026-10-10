"""Wave 11C: small grammar words and trigger qualifiers, researched against CR 2026-09-25.

* A named character's "he / she / him / her / his" is the card itself, and a legendary "Elanor Gardner" is "Elanor" in its
  own text (201.5c); "modified" (700.9: a counter, an Equipment, or an Aura its controller controls) and "historic" (700.6)
  as selector words; "Put a +1/+1 counter on ~ and a +1/+1 counter on …" / "… and add {R}" (two instructions, 608.2c);
  "you may have Ally creatures you control gain …"; "that player loses the game" (104.3e).
* Trigger qualifiers (603.2): "… during your / an opponent's / their turn", "you gain life for the first time each turn" (kept
  per player per turn, whoever watches), "~ and at least one other Warrior attack".

Every scenario checks the replay; the longer ones also reload the game from its saved history.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage, events, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import token_of, until
from tests.test_rules_wave9a_x_value import (
    cast,
    check,
    counters,
    life,
    mana,
    named,
    put,
    run,
    to_gy,
    to_hand,
    zone,
)

# Real Oracle wording (the local card database, current).
EXTRA = [
    card('Elanor Gardner', set_code='tst', number='W01', mana_cost='{3}{G}', cmc=4.0, type_line='Legendary Creature — Halfling Scout', oracle_text='When Elanor enters, create a Food token.\nAt the beginning of your end step, if you sacrificed a Food this turn, you may search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.', power='2', toughness='4', colors=['G'], color_identity=['G'], keywords=['Food']),  # noqa: E501
    card('Hercules, Prince of Power', set_code='tst', number='W02', mana_cost='{2}{G}', cmc=3.0, type_line='Legendary Creature — Demigod Warrior Hero', oracle_text='Power-up — {4}{G}: Put a +1/+1 counter on Hercules. He gains vigilance, indestructible, and haste until end of turn. (Activate each power-up ability only once. Reduce the cost by his mana cost if he entered this turn.)', power='3', toughness='3', colors=['G'], color_identity=['G'], keywords=['Power-up']),  # noqa: E501
    card('Revitalize', set_code='tst', number='W03', mana_cost='{1}{W}', cmc=2.0, type_line='Instant', oracle_text='You gain 3 life.\nDraw a card.', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card("Whitesun's Passage", set_code='tst', number='W04', mana_cost='{1}{W}', cmc=2.0, type_line='Instant', oracle_text='You gain 5 life.', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card('Divination', set_code='tst', number='W05', mana_cost='{2}{U}', cmc=3.0, type_line='Sorcery', oracle_text='Draw two cards.', colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Attended Healer', set_code='tst', number='W06', mana_cost='{3}{W}', cmc=4.0, type_line='Creature — Kor Cleric', oracle_text='Whenever you gain life for the first time each turn, create a 1/1 white Cat creature token.\n{2}{W}: Another target Cleric gains lifelink until end of turn.', power='2', toughness='3', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card('Deathless Knight', set_code='tst', number='W07', mana_cost='{B/G}{B/G}{B/G}{B/G}', cmc=4.0, type_line='Creature — Skeleton Knight', oracle_text='Haste\nWhen you gain life for the first time each turn, return this card from your graveyard to your hand.', power='4', toughness='2', colors=['B', 'G'], color_identity=['B', 'G'], keywords=['Haste']),  # noqa: E501
    card('The Council of Four', set_code='tst', number='W08', mana_cost='{3}{W}{U}', cmc=5.0, type_line='Legendary Creature — Human Noble', oracle_text='Whenever a player draws their second card during their turn, you draw a card.\nWhenever a player casts their second spell during their turn, you create a 2/2 white Knight creature token.', power='0', toughness='8', colors=['U', 'W'], color_identity=['U', 'W'], keywords=[]),  # noqa: E501
    card('Foe-liage', set_code='tst', number='W09', mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Plant Mutant', oracle_text='Whenever a land enters during your turn, put a +1/+1 counter on this creature.', power='3', toughness='3', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Door to Nothingness', set_code='tst', number='W10', mana_cost='{5}', cmc=5.0, type_line='Artifact', oracle_text='This artifact enters tapped.\n{W}{W}{U}{U}{B}{B}{R}{R}{G}{G}, {T}, Sacrifice this artifact: Target player loses the game.', colors=[], color_identity=['B', 'G', 'R', 'U', 'W'], keywords=[]),  # noqa: E501
    card('Kodama of the West Tree', set_code='tst', number='W11', mana_cost='{2}{G}', cmc=3.0, type_line='Legendary Creature — Spirit', oracle_text='Reach\nModified creatures you control have trample. (Equipment, Auras you control, and counters are modifications.)\nWhenever a modified creature you control deals combat damage to a player, search your library for a basic land card, put it onto the battlefield tapped, then shuffle.', power='3', toughness='3', colors=['G'], color_identity=['G'], keywords=['Reach']),  # noqa: E501
    card('Upriser Renegade', set_code='tst', number='W12', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Human Samurai', oracle_text='This creature gets +2/+0 for each other modified creature you control. (Equipment, Auras you control, and counters are modifications.)', power='1', toughness='3', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Juniper Order Ranger', set_code='tst', number='W13', mana_cost='{3}{G}{W}', cmc=5.0, type_line='Creature — Human Knight Ranger', oracle_text='Whenever another creature you control enters, put a +1/+1 counter on that creature and a +1/+1 counter on this creature.', power='2', toughness='4', colors=['G', 'W'], color_identity=['G', 'W'], keywords=[]),  # noqa: E501
    card('Joraga Bard', set_code='tst', number='W14', mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Elf Rogue Bard Ally', oracle_text='Whenever this creature or another Ally you control enters, you may have Ally creatures you control gain vigilance until end of turn.', power='1', toughness='4', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Platinum Angel', set_code='tst', number='W16', mana_cost='{7}', cmc=7.0, type_line='Artifact Creature — Angel', oracle_text="Flying\nYou can't lose the game and your opponents can't win the game.", power='4', toughness='4', colors=[], color_identity=[], keywords=['Flying']),  # noqa: E501
    card('Demonic Pact', set_code='tst', number='W17', mana_cost='{2}{B}{B}', cmc=4.0, type_line='Enchantment', oracle_text="At the beginning of your upkeep, choose one that hasn't been chosen —\n• This enchantment deals 4 damage to any target and you gain 4 life.\n• Target opponent discards two cards.\n• Draw two cards.\n• You lose the game.", colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Paired Tactician', set_code='tst', number='W15', mana_cost='{2}{W}', cmc=3.0, type_line='Creature — Human Warrior', oracle_text='Whenever this creature and at least one other Warrior attack, put a +1/+1 counter on this creature.', power='3', toughness='2', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
]
FULL = [c["name"] for c in EXTRA if c["name"] not in ("Revitalize", "Whitesun's Passage", "Divination")]
FULL += ["Revitalize", "Whitesun's Passage", "Divination"]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build(cards, *names, bob=(), forests=9):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    seats = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (forests, "Forest")])),
             PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (10, "Island")]))]
    s = GameSession(enable(new_game(seats, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def keywords(s, name):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[named(s, name).id]).keywords


def power(s, name):
    from app.rules import sba
    from app.rules.plan import Plan

    c = s.state.cards[named(s, name).id]
    return sba.power(c, Plan(s.state, "p1", s.cards, None).ch(c))


def on_field(s, name, pid="p1"):
    return sum(1 for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:battlefield")


# -- coverage ----------------------------------------------------------------------------------------------------
def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
            assert coverage.of_characteristics(chs).level == "FULL", (c["name"], coverage.of_characteristics(chs).manual_parts)


@pytest.mark.parametrize("text", [
    "Whenever one or more modified creatures you control die, draw a card.",  # (wave 25B: a single dying creature is read as it last existed; a batch is not)
    "Whenever you discard one or more nonland cards for the first time each turn, draw a card.",  # (a filter on the count)
    "Whenever a player gains life for the first time each turn, draw a card.",  # (each player's, or the table's first?)
    "Whenever you gain life for the first time this turn, draw a card.",
    "Whenever ~ attacks, he or she draws a card.",
    "Whenever ~ attacks, destroy target creature. Its controller loses 1 life and her controller draws a card.",
])
def test_wordings_that_stay_manual(text):
    from tests.test_rules_scripts import ch as characteristics

    assert coverage.of_characteristics(characteristics("Test", "Legendary Creature — Human", text)).level != "FULL", text


def test_pronouns_and_short_names_are_read_only_where_they_mean_the_card():
    assert scripts.self_text("Whenever Zuko deals combat damage to a player, put a +1/+1 counter on him.", "Zuko, Seeking Honor") == \
        "Whenever ~ deals combat damage to a player, put a +1/+1 counter on ~."
    assert scripts.self_text("Elanor deals 1 damage to him or her.", "Elanor Gardner") == "~ deals 1 damage to him or her."
    assert scripts.self_text("His or her controller draws.", "Test") == "His or her controller draws."
    assert scripts.self_text("When Black enters, draw.", "Black Lotus").startswith("When ~ enters")  # a subject: accepted
    assert scripts.self_text("Black creatures get +1/+1.", "Black Lotus") == "Black creatures get +1/+1."  # a color word: not
    assert scripts.self_text("Sliver creatures get +1/+1.", "Sliver Queen") == "Sliver creatures get +1/+1."  # a creature type


def test_the_qualifiers_are_part_of_the_condition():
    assert events.parse_condition("a land enters during your turn")["during"] == "you"
    assert events.parse_condition("you draw a card during an opponent's turn")["during"] == "opponent"
    assert events.parse_condition("a player draws their second card during their turn") == {
        "event": "draw", "subject": "player", "player": "any", "nth": 2, "during": "their"}
    first = events.parse_condition("you gain life for the first time each turn")
    assert first["first_each_turn"] and first["event"] == "gain_life" and "during" not in first
    assert events.parse_condition("you lose life for the first time during each of your turns")["during"] == "you"
    assert events.parse_condition("~ and at least one other Warrior attack")["others_only"]
    # (wave 25B: the creature as it last existed - its counters and what was attached to it, 603.10a - tests/test_rules_wave25b_triggers.py)
    assert events.parse_condition("a modified creature you control dies")["sel"].count("modified") == 1
    assert events.parse_condition("one or more modified creatures you control die") is None


# -- shortened names, pronouns ----------------------------------------------------------------------------------------
def test_elanor_is_the_card_that_enters(cards):
    s = build(cards, "Elanor Gardner")
    to_hand(s, "Elanor Gardner")
    mana(s, G=4)
    cast(s, "Elanor Gardner")
    run(s)
    assert on_field(s, "Food") == 1 and on_field(s, "Elanor Gardner") == 1
    check(s)


def test_hercules_puts_the_counter_on_himself_and_he_gains_keywords(cards):
    s = build(cards, "Hercules, Prince of Power")
    put(s, "Hercules, Prince of Power")
    mana(s, G=5)
    act(s, "p1", type="activate_ability", card_id=named(s, "Hercules, Prince of Power").id, ability=0)
    run(s)
    assert counters(s, "Hercules, Prince of Power") == 1
    assert {"vigilance", "indestructible", "haste"} <= set(keywords(s, "Hercules, Prince of Power"))
    check(s)


# -- twin instructions, "you may have" -----------------------------------------------------------------------------------
def test_juniper_order_ranger_puts_a_counter_on_each(cards):
    s = build(cards, "Juniper Order Ranger", "Upriser Renegade")
    put(s, "Juniper Order Ranger")
    to_hand(s, "Upriser Renegade")
    mana(s, R=2)
    cast(s, "Upriser Renegade")
    run(s)
    assert counters(s, "Juniper Order Ranger") == 1 and counters(s, "Upriser Renegade") == 1
    check(s)


def test_joraga_bard_gives_the_allies_vigilance_when_you_say_yes(cards):
    s = build(cards, "Joraga Bard")
    to_hand(s, "Joraga Bard")
    mana(s, G=4)
    cast(s, "Joraga Bard")
    for _ in range(6):  # (the creature resolves, its ability goes on the stack and resolves: "Grant?")
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and "yes" in [o.id for o in d.options], d
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
    run(s)
    assert "vigilance" in keywords(s, "Joraga Bard")
    check(s)


# -- modified ----------------------------------------------------------------------------------------------------------
def test_modified_creatures_are_those_with_a_counter(cards):
    """700.9: Kodama gives modified creatures trample; Upriser Renegade gets +2/+0 for each other one."""
    s = build(cards, "Kodama of the West Tree", "Upriser Renegade")
    put(s, "Kodama of the West Tree")
    put(s, "Upriser Renegade")
    bear = token_of(s, "p1", "Bear", "Creature — Bear", "2/2")
    assert "trample" not in keywords(s, "Bear") and power(s, "Upriser Renegade") == 1
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    assert "trample" in keywords(s, "Bear") and power(s, "Upriser Renegade") == 3
    check(s)


# -- first time each turn, during turns ----------------------------------------------------------------------------------
def test_the_first_life_gain_each_turn_triggers_once_and_returns_the_knight(cards):
    s = build(cards, "Attended Healer", "Deathless Knight", "Revitalize", "Whitesun's Passage")
    put(s, "Attended Healer")
    to_gy(s, "Deathless Knight")
    for n in ("Revitalize", "Whitesun's Passage"):
        to_hand(s, n)
        mana(s, W=2)
        cast(s, n)
        run(s)
    assert on_field(s, "Cat") == 1 and "Deathless Knight" in zone(s, "p1", "hand")  # (the second gain is not the first)
    assert life(s, "p1") == 40 + 3 + 5
    check(s)


def test_an_earlier_gain_this_turn_counts_for_a_creature_that_arrived_later(cards):
    """603.2: it is "the first time" this turn that the event happened, not the first one the ability saw."""
    s = build(cards, "Attended Healer", "Revitalize", "Whitesun's Passage")
    to_hand(s, "Revitalize")
    mana(s, W=2)
    cast(s, "Revitalize")
    run(s)
    put(s, "Attended Healer")
    to_hand(s, "Whitesun's Passage")
    mana(s, W=2)
    cast(s, "Whitesun's Passage")
    run(s)
    assert on_field(s, "Cat") == 0
    check(s)


def test_the_council_of_four_draws_for_the_second_card_a_player_draws_in_their_turn(cards):
    s = build(cards, "The Council of Four", "Divination")
    put(s, "The Council of Four")
    to_hand(s, "Divination")
    hand = len(zone(s, "p1", "hand"))
    mana(s, U=3)
    cast(s, "Divination")
    run(s)
    assert len(zone(s, "p1", "hand")) == hand - 1 + 2 + 1
    check(s)


def test_during_your_turn_means_the_controllers_turn(cards):
    """Foe-liage: a land entering in Alice's turn grows hers, and not Bob's (it isn't Bob's turn)."""
    s = build(cards, "Foe-liage", bob=("Foe-liage",))
    put(s, "Foe-liage")
    put(s, "Foe-liage", "p2")
    to_hand(s, "Forest")
    act(s, "p1", type="play_land", card_id=named(s, "Forest").id)
    run(s)
    assert counters(s, "Foe-liage") == 1
    assert s.state.cards[named(s, "Foe-liage", "p2").id].counters.get("+1/+1", 0) == 0
    check(s)


# -- lose the game -----------------------------------------------------------------------------------------------------
def test_door_to_nothingness_makes_the_target_player_lose_the_game(cards):
    s = build(cards, "Door to Nothingness")
    door = put(s, "Door to Nothingness")
    mana(s, W=2, U=2, B=2, R=2, G=2)
    act(s, "p1", type="activate_ability", card_id=door.id, ability=1, targets=["p2"])
    run(s, target="p2")
    assert "p2" in s.state.rules.lost and s.state.rules.winner == "p1"
    assert not [c for c in s.state.cards.values() if c.owner == "p2" and c.zone.endswith(":battlefield")]
    check(s)


def test_a_player_who_cant_lose_stays_when_an_effect_says_they_lose(cards):
    """-- review (wave 11C) -- 104.3 as read by app/rules/game_result.py (wave 10B): Bob's Platinum Angel keeps him in the
    game when Door to Nothingness says he loses it; the same check as for a state-based loss."""
    s = build(cards, "Door to Nothingness", bob=("Platinum Angel",))
    door = put(s, "Door to Nothingness")
    put(s, "Platinum Angel", "p2")
    mana(s, W=2, U=2, B=2, R=2, G=2)
    act(s, "p1", type="activate_ability", card_id=door.id, ability=1, targets=["p2"])
    run(s, target="p2")
    assert s.state.rules.lost == {} and s.state.rules.winner is None
    check(s)


def test_you_lose_the_game_in_a_three_player_game_goes_on_without_you(cards):
    """104.3e, 800.4a: Alice picks Demonic Pact's last mode in her upkeep; she leaves, Bob and Cy play on (no winner yet)."""
    from tests.test_rules_wave9a_x_value import build as build3

    s = build3(cards, "Demonic Pact", players=3)
    put(s, "Demonic Pact")
    until(s, lambda s: s.state.turn.number == 4 and s.state.rules.decision is not None
          and s.state.rules.decision.kind != "declare_attackers")
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if "lose the game" in o.label])
    until(s, lambda s: not s.state.zones.get("stack") and s.state.rules.decision is None, limit=50)
    assert "p1" in s.state.rules.lost and s.state.rules.winner is None and s.state.rules.priority == "p2"
    until(s, lambda s: s.state.turn.number == 6, limit=400)  # (Bob's and Cy's turns go round)
    check(s)


# -- combat ------------------------------------------------------------------------------------------------------------
def test_paired_tactician_needs_another_warrior_attacking_with_it(cards):
    """"~ and at least one other Warrior attack": the other attacker is a Warrior (a Bear doesn't do), not ~ itself."""
    from tests.test_rules_wave5c_combat import declare, to_attack

    s = build(cards, "Paired Tactician")
    tactician = put(s, "Paired Tactician")
    warrior = token_of(s, "p1", "Fighter", "Creature — Human Warrior", "2/2")
    bear = token_of(s, "p1", "Bear", "Creature — Bear", "2/2")
    to_attack(s, 3)
    declare(s, (tactician, "p2"), (bear, "p2"))
    run(s)
    assert counters(s, "Paired Tactician") == 0
    check(s)
    s = build(cards, "Paired Tactician")
    tactician = put(s, "Paired Tactician")
    warrior = token_of(s, "p1", "Fighter", "Creature — Human Warrior", "2/2")
    to_attack(s, 3)
    declare(s, (tactician, "p2"), (warrior, "p2"))
    run(s)
    assert counters(s, "Paired Tactician") == 1
    check(s)
