"""Wave 12C: amounts the text defines ("where X is …"), what a spell's additional cost sacrificed, and one target group per opponent.

* 107.3c: "where X is …" defines X for the whole instruction (every X in the sentence); 608.2h: read as the instruction is carried out.
* 608.2h: the sacrificed creature's power / toughness / mana value is read as it last existed (Momentous Fall, Sacrifice, Morbid Curiosity).
* 201.2: "cards named ~" counts the cards with the spell's own name; 903.3: a commander is a card (the command zone counts).
* 115.1, 601.2c, 603.3d: "for each opponent, … up to one target creature that player controls" is one target group per opponent in the game.

Real Oracle wording; every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage, per_opponent, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana, pass_until_stack_empty
from tests.test_rules_multitarget import choose, decision
from tests.test_rules_wave9b_exile_permission import build, find, put, roundtrip
from tests.test_rules_wave9b_excess import cast

EXTRA = [
    card('Kindle', set_code='tst', number='W01', mana_cost='{1}{R}', cmc=2.0, type_line='Instant', oracle_text='Kindle deals X damage to any target, where X is 2 plus the number of cards named Kindle in all graveyards.', power=None, toughness=None, colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Feast of Flesh', set_code='tst', number='W02', mana_cost='{B}', cmc=1.0, type_line='Sorcery', oracle_text='Feast of Flesh deals X damage to target creature and you gain X life, where X is 1 plus the number of cards named Feast of Flesh in all graveyards.', power=None, toughness=None, colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Cloudkill', set_code='tst', number='W03', mana_cost='{4}{B}{B}', cmc=6.0, type_line='Sorcery', oracle_text='All creatures get -X/-X until end of turn, where X is the greatest mana value of a commander you own on the battlefield or in the command zone.', power=None, toughness=None, colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Momentous Fall', set_code='tst', number='W04', mana_cost='{2}{G}{G}', cmc=4.0, type_line='Instant', oracle_text="As an additional cost to cast this spell, sacrifice a creature.\nYou draw cards equal to the sacrificed creature's power, then you gain life equal to its toughness.", power=None, toughness=None, colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Sacrifice', set_code='tst', number='W05', mana_cost='{B}', cmc=1.0, type_line='Instant', oracle_text="As an additional cost to cast this spell, sacrifice a creature.\nAdd an amount of {B} equal to the sacrificed creature's mana value.", power=None, toughness=None, colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Morbid Curiosity', set_code='tst', number='W06', mana_cost='{1}{B}{B}', cmc=3.0, type_line='Sorcery', oracle_text='As an additional cost to cast this spell, sacrifice an artifact or creature.\nDraw cards equal to the mana value of the sacrificed permanent.', power=None, toughness=None, colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Haytham Kenway', set_code='tst', number='W07', mana_cost='{2}{W}{U}', cmc=4.0, type_line='Legendary Creature — Human Knight', oracle_text='Protection from Assassins\nOther Knights you control get +2/+2 and have protection from Assassins.\nWhen Haytham Kenway enters, for each opponent, exile up to one target creature that player controls until Haytham Kenway leaves the battlefield.', power='3', toughness='3', colors=['U', 'W'], color_identity=['U', 'W'], keywords=['Protection']),  # noqa: E501
    card('Intelligence Bobblehead', set_code='tst', number='W08', mana_cost='{3}', cmc=3.0, type_line='Artifact — Bobblehead', oracle_text='{T}: Add one mana of any color.\n{5}, {T}: Draw X cards, where X is the number of Bobbleheads you control.', power=None, toughness=None, colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Thunder of Hooves', set_code='tst', number='W09', mana_cost='{3}{R}', cmc=4.0, type_line='Sorcery', oracle_text='Thunder of Hooves deals X damage to each creature without flying and each player, where X is the number of Beasts on the battlefield.', power=None, toughness=None, colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Frenzied Gorespawn', set_code='tst', number='W10', mana_cost='{3}{B}{R}', cmc=5.0, type_line='Creature — Horror', oracle_text='When this creature enters, for each opponent, goad target creature that player controls. (Until your next turn, those creatures attack each combat if able and attack a player other than you if able.)\nWhenever one or more creatures attack one of your opponents, those creatures gain menace until end of turn.', power='4', toughness='4', colors=['B', 'R'], color_identity=['B', 'R'], keywords=['Goad']),  # noqa: E501
    card('Molten Primordial', set_code='tst', number='W11', mana_cost='{5}{R}{R}', cmc=7.0, type_line='Creature — Avatar', oracle_text='Haste\nWhen this creature enters, for each opponent, gain control of up to one target creature that player controls until end of turn. Untap those creatures. They gain haste until end of turn.', power='6', toughness='4', colors=['R'], color_identity=['R'], keywords=['Haste']),  # noqa: E501

]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def life(s, pid="p1"):
    return s.state.players[pid].life


def hand(s, pid="p1"):
    return sum(1 for c in s.state.cards.values() if c.zone == f"{pid}:hand")


def test_the_wording_is_exact():
    # X is the one the text defines: every X of the sentence (not a cast X), the whole ability or nothing
    e = scripts.parse_effects("Each opponent loses X life and you scry X, where X is the number of Zombies you control.")[0]
    assert e[0]["n"] == e[1]["n"] and "x" not in e[0]["n"]
    # a target count or a selector bound is not an amount field: stays manual
    assert scripts.parse_effects("Destroy up to X target artifacts, where X is the number of Vampires you control.") is None
    assert scripts.parse_effects("Draw X cards, where X is the number of Plains you control. Then discard X cards.") is None


# -- 107.3c: the text defines X ---------------------------------------------------------------------
def test_kindle_counts_the_cards_with_its_own_name_in_all_graveyards(cards):
    s = build(cards, p1=("Kindle",), p2=("Kindle",))
    put(s, "Kindle", "graveyard", pid="p1", owner="p2")
    cast(s, "Kindle", ["p2"], R=2)
    assert life(s, "p2") == 37  # 2 plus the one in Bob's graveyard
    roundtrip(s)
    alone = build(cards, p1=("Kindle",))
    cast(alone, "Kindle", ["p2"], R=2)
    assert life(alone, "p2") == 38
    roundtrip(alone)


def test_feast_of_flesh_uses_the_same_x_twice(cards):
    s = build(cards, p1=("Feast of Flesh", "Feast of Flesh"), p2=("Grizzly Bears",))
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    first, second = [c for c in s.state.cards.values() if c.name == "Feast of Flesh"]
    act(s, "p1", type="move", card_ids=[second.id], to={"player": "p1", "zone": "graveyard"})
    cast(s, "Feast of Flesh", [bears.id], B=1)
    assert s.state.cards[bears.id].zone == "p2:graveyard" and life(s, "p1") == 42  # X = 1 plus one: damage and life
    roundtrip(s)


def test_cloudkill_reads_the_commander_in_the_command_zone(cards):
    s = build(cards, p1=("Cloudkill",), p2=("Grizzly Bears",))
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    c = find(s, "Cloudkill")
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    mana(s, B=2, C=4)
    act(s, "p1", type="cast_spell", card_id=c.id)
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard"  # -4/-4: Krenko, Mob Boss is 4
    roundtrip(s)


def test_bobblehead_counts_bobbleheads_you_control(cards):
    s = build(cards, p1=("Intelligence Bobblehead",))
    bob = put(s, "Intelligence Bobblehead", "battlefield")
    before = hand(s)
    mana(s, C=5)
    act(s, "p1", type="activate_ability", card_id=bob.id, ability=1)
    pass_until_stack_empty(s)
    assert hand(s) == before + 1
    roundtrip(s)


# -- 608.2h: what the additional cost sacrificed ------------------------------------------------------
def test_momentous_fall_reads_the_sacrificed_creature_as_it_was(cards):
    from tests.test_rules_attachments import token

    s = build(cards, p1=("Momentous Fall",))
    token(s, "p1", "Brute", "3/2")
    fall = find(s, "Momentous Fall")
    act(s, "p1", type="move", card_ids=[fall.id], to={"player": "p1", "zone": "hand"})
    mana(s, G=2, C=2)
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=fall.id)
    pass_until_stack_empty(s)
    assert hand(s) == before - 1 + 3 and life(s, "p1") == 42  # power 3 cards, toughness 2 life
    roundtrip(s)


def test_sacrifice_adds_mana_equal_to_the_sacrificed_mana_value(cards):
    s = build(cards, p1=("Sacrifice", "Grizzly Bears"))
    put(s, "Grizzly Bears", "battlefield")
    spell = find(s, "Sacrifice")
    act(s, "p1", type="move", card_ids=[spell.id], to={"player": "p1", "zone": "hand"})
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    pass_until_stack_empty(s)
    assert s.state.players["p1"].mana.get("B") == 2  # Grizzly Bears: mana value 2
    roundtrip(s)


def test_morbid_curiosity_draws_for_the_sacrificed_permanents_mana_value(cards):
    s = build(cards, p1=("Morbid Curiosity", "Grizzly Bears"))
    put(s, "Grizzly Bears", "battlefield")
    spell = find(s, "Morbid Curiosity")
    act(s, "p1", type="move", card_ids=[spell.id], to={"player": "p1", "zone": "hand"})
    mana(s, B=2, C=1)
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    pass_until_stack_empty(s)
    assert hand(s) == before - 1 + 2
    roundtrip(s)


# -- 115.1, 601.2c: one target group per opponent ----------------------------------------------------
def three(cards, p1):
    decks = [deck(cards, "Krenko, Mob Boss", [*((1, n) for n in p1), (9, "Forest")]),
             deck(cards, "Atraxa, Praetors' Voice", [(1, "Grizzly Bears"), (10, "Island")]),
             deck(cards, "Atraxa, Praetors' Voice", [(1, "Grizzly Bears"), (10, "Island")])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Cara"), decks, strict=True)],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def test_haytham_kenway_exiles_one_creature_of_each_opponent(cards):
    s = three(cards, ("Haytham Kenway",))
    bob, cara = put(s, "Grizzly Bears", "battlefield", pid="p2"), put(s, "Grizzly Bears", "battlefield", pid="p3")
    taker = put(s, "Haytham Kenway", "hand")
    mana(s, W=1, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=taker.id)
    pass_until_stack_empty(s)
    d = decision(s)
    assert d.resume["step"] == "trigger_group" and d.player == "p1"
    assert {o.id for o in d.options} == {bob.id}  # the first group is Bob's permanents only
    choose(s, [bob.id])
    assert {o.id for o in decision(s).options} == {cara.id}
    choose(s, [cara.id])
    pass_until_stack_empty(s)
    assert s.state.cards[bob.id].zone == "p2:exile" and s.state.cards[cara.id].zone == "p3:exile"
    roundtrip(s)


def test_an_opponent_without_a_creature_gets_no_target_and_up_to_one_may_be_skipped(cards):
    s = three(cards, ("Haytham Kenway",))
    bob = put(s, "Grizzly Bears", "battlefield", pid="p2")
    taker = put(s, "Haytham Kenway", "hand")
    mana(s, W=1, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=taker.id)
    pass_until_stack_empty(s)
    choose(s, [bob.id])
    d = decision(s)
    if d is not None:
        choose(s, [])
    pass_until_stack_empty(s)
    assert s.state.cards[bob.id].zone == "p2:exile"
    roundtrip(s)


def test_per_opponent_is_read_only_for_a_triggered_ability_own_clause():
    ok = scripts.parse_effects("For each opponent, tap up to one target creature that player controls. Put a stun counter on each of those creatures.")
    assert ok is not None and ok[1][0][per_opponent.FLAG] is True
    # another reference to the opponent, or a second target, is not read
    for text in ("For each opponent, exile up to one target creature that player controls and that player gains life equal to its power.",
                 "For each opponent, exile up to one target creature that player controls and up to one target artifact.",
                 "For each opponent, exile up to two target creatures that player controls."):
        assert scripts.parse_effects(text) is None, text
