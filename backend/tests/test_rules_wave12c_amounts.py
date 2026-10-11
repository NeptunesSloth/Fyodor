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
from tests.test_rules_wave9b_excess import cast
from tests.test_rules_wave9b_exile_permission import build, find, put, roundtrip

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

    card('Plague Rats', set_code='tst', number='V01', mana_cost='{2}{B}', cmc=3.0, type_line='Creature — Rat', oracle_text="Plague Rats's power and toughness are each equal to the number of creatures named Plague Rats on the battlefield.", power='*', toughness='*', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Timberpack Wolf', set_code='tst', number='V02', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Wolf', oracle_text='This creature gets +1/+1 for each other creature you control named Timberpack Wolf.', power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Pack Mastiff', set_code='tst', number='V03', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Dog', oracle_text='{1}{R}: Each creature you control named Pack Mastiff gets +1/+0 until end of turn.', power='2', toughness='2', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Faerie Miscreant', set_code='tst', number='V04', mana_cost='{U}', cmc=1.0, type_line='Creature — Faerie Rogue', oracle_text='Flying\nWhen this creature enters, if you control another creature named Faerie Miscreant, draw a card.', power='1', toughness='1', colors=['U'], color_identity=['U'], keywords=['Flying']),  # noqa: E501
    card('Cleric of the Forward Order', set_code='tst', number='V05', mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Human Cleric', oracle_text='When this creature enters, you gain 2 life for each creature you control named Cleric of the Forward Order.', power='2', toughness='2', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card('Demigod of Revenge', set_code='tst', number='V06', mana_cost='{B/R}{B/R}{B/R}{B/R}{B/R}', cmc=5.0, type_line='Creature — Spirit Avatar', oracle_text='When you cast this spell, return all cards named Demigod of Revenge from your graveyard to the battlefield.\nFlying, haste', power='5', toughness='4', colors=['B', 'R'], color_identity=['B', 'R'], keywords=['Flying', 'Haste']),  # noqa: E501
    card('Battlefield Medic', set_code='tst', number='U01', mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Human Cleric', oracle_text='{T}: Prevent the next X damage that would be dealt to target creature this turn, where X is the number of Clerics on the battlefield.', power='1', toughness='1', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card('Burnt Offering', set_code='tst', number='U02', mana_cost='{B}', cmc=1.0, type_line='Instant', oracle_text="As an additional cost to cast this spell, sacrifice a creature.\nAdd X mana in any combination of {B} and/or {R}, where X is the sacrificed creature's mana value.", power=None, toughness=None, colors=['B'], color_identity=['B', 'R'], keywords=[]),  # noqa: E501
    card('Judgment Bolt', set_code='tst', number='U04', mana_cost='{3}{R}', cmc=4.0, type_line='Instant', oracle_text="Judgment Bolt deals 5 damage to target creature and X damage to that creature's controller, where X is the number of Equipment you control.", power=None, toughness=None, colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
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
    # (wave 28D: a bound is read as the trigger is put on the stack, 603.3d: the wording parses to a marker (app/rules/where_bound.py), but only a
    # triggered ability keeps it: a spell's stays manual)
    got = scripts.parse_effects("Destroy target creature with toughness X or less, where X is the number of Vampires you control.")
    assert got is not None and "wx:" in got[1]
    from app.rules import coverage
    from tests.fixtures.cards import card

    spell = card("Vampire Bane", set_code="tst", number="X999", mana_cost="{B}", cmc=1.0, type_line="Sorcery", colors=["B"], color_identity=["B"],
                 oracle_text="Destroy target creature with toughness X or less, where X is the number of Vampires you control.")
    assert coverage.of_card_data(spell).level != "FULL"
    # (27C: "up to X target" is no amount field either: it becomes the group's x_value, read as the targets are chosen, 601.2c)
    got = scripts.parse_effects("Destroy up to X target artifacts, where X is the number of Vampires you control.")
    assert got is not None and "n" not in got[0][0] and got[1][0]["x_value"] == {"count": 'sel:{"controller":"you","subtypes":["Vampire"]}'}


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


# -- 201.2: "named ~" is the source's own name, as the rules text writes it ---------------------------------
def test_named_self_in_a_cda_a_static_and_a_group_ability(cards):
    from tests.wave9c_kit import build as kbuild
    from tests.wave9c_kit import mana as kmana
    from tests.wave9c_kit import pt as kpt
    from tests.wave9c_kit import put as kput

    s = kbuild(cards, mine=("Plague Rats", "Plague Rats", "Timberpack Wolf", "Timberpack Wolf", "Pack Mastiff"))
    first, second = [c for c in s.state.cards.values() if c.name == "Plague Rats"]
    for c in (first, second):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    assert kpt(s, "Plague Rats") == (2, 2)  # the number of creatures named Plague Rats on the battlefield
    wolf1, wolf2 = [c for c in s.state.cards.values() if c.name == "Timberpack Wolf"]
    act(s, "p1", type="move", card_ids=[wolf1.id], to={"player": "p1", "zone": "battlefield"})
    assert kpt(s, "Timberpack Wolf") == (2, 2)
    act(s, "p1", type="move", card_ids=[wolf2.id], to={"player": "p1", "zone": "battlefield"})
    assert kpt(s, "Timberpack Wolf") == (3, 3)  # +1/+1 for each OTHER creature named Timberpack Wolf
    kput(s, "Pack Mastiff")
    kmana(s, R=2)
    act(s, "p1", type="activate_ability", card_id=next(c.id for c in s.state.cards.values() if c.name == "Pack Mastiff"), ability=0)
    pass_until_stack_empty(s)
    assert kpt(s, "Pack Mastiff") == (3, 2) and kpt(s, "Timberpack Wolf") == (3, 3)  # only the creatures named Pack Mastiff
    roundtrip(s)


def test_named_self_in_enters_triggers(cards):
    from tests.wave9c_kit import build as kbuild
    from tests.wave9c_kit import mana as kmana

    s = kbuild(cards, mine=("Faerie Miscreant", "Faerie Miscreant", "Cleric of the Forward Order", "Cleric of the Forward Order"))
    one, two = [c for c in s.state.cards.values() if c.name == "Faerie Miscreant"]
    c1, c2 = [c for c in s.state.cards.values() if c.name == "Cleric of the Forward Order"]
    before = hand(s)
    act(s, "p1", type="move", card_ids=[one.id], to={"player": "p1", "zone": "hand"})
    kmana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=one.id)
    pass_until_stack_empty(s)
    assert hand(s) == before  # no other Faerie Miscreant: nothing drawn
    act(s, "p1", type="move", card_ids=[two.id], to={"player": "p1", "zone": "hand"})
    kmana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=two.id)
    pass_until_stack_empty(s)
    assert hand(s) == before + 1  # another one: draw a card
    for c in (c1, c2):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    life0 = life(s)
    kmana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c1.id)
    pass_until_stack_empty(s)
    assert life(s) == life0 + 2
    kmana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c2.id)
    pass_until_stack_empty(s)
    assert life(s) == life0 + 2 + 4  # 2 life for each creature named Cleric of the Forward Order (itself included)
    roundtrip(s)


def test_demigod_of_revenge_cast_trigger_returns_the_others_from_the_graveyard(cards):
    from tests.wave9c_kit import build as kbuild
    from tests.wave9c_kit import mana as kmana

    s = kbuild(cards, mine=("Demigod of Revenge", "Demigod of Revenge"))
    dead, live = [c for c in s.state.cards.values() if c.name == "Demigod of Revenge"]
    act(s, "p1", type="move", card_ids=[dead.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[live.id], to={"player": "p1", "zone": "hand"})
    kmana(s, B=5)
    act(s, "p1", type="cast_spell", card_id=live.id)
    pass_until_stack_empty(s)
    assert s.state.cards[dead.id].zone == "p1:battlefield" and s.state.cards[live.id].zone == "p1:battlefield"
    roundtrip(s)


# -- the amount lands in the right field: a shield, mana, counters, two recipients -------------------------
def test_battlefield_medic_prevents_as_many_as_there_are_clerics(cards):
    from tests.wave9c_kit import build as kbuild
    from tests.wave9c_kit import put as kput

    s = kbuild(cards, mine=("Battlefield Medic", "Grizzly Bears"))
    medic, bears = kput(s, "Battlefield Medic"), kput(s, "Grizzly Bears")
    s.state.rules.controlled_since[medic.id].turn = 0  # (it has been under its controller since before the turn)
    act(s, "p1", type="activate_ability", card_id=medic.id, ability=0, targets=[bears.id])
    pass_until_stack_empty(s)
    assert s.state.rules.prevention[next(iter(s.state.rules.prevention))] == 1  # one Cleric on the battlefield: the Medic
    roundtrip(s)


def test_burnt_offering_adds_mana_for_the_sacrificed_mana_value(cards):
    s = build(cards, p1=("Burnt Offering", "Grizzly Bears"))
    put(s, "Grizzly Bears", "battlefield")
    spell = find(s, "Burnt Offering")
    act(s, "p1", type="move", card_ids=[spell.id], to={"player": "p1", "zone": "hand"})
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    pass_until_stack_empty(s)
    d = decision(s)
    assert d is not None and d.kind == "choose_one"  # two mana, each {B} or {R}
    choose(s, ["B"])
    choose(s, ["R"])
    pass_until_stack_empty(s)
    assert s.state.players["p1"].mana.get("B") == 1 and s.state.players["p1"].mana.get("R") == 1
    roundtrip(s)



def test_judgment_bolt_hits_the_creature_and_its_controller(cards):
    s = build(cards, p1=("Judgment Bolt",), p2=("Grizzly Bears",))
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    cast(s, "Judgment Bolt", [bears.id], R=1, C=3)
    assert s.state.cards[bears.id].zone == "p2:graveyard" and life(s, "p2") == 40  # no Equipment: X is 0
    roundtrip(s)


# -- review (wave 12C) --
@pytest.mark.parametrize("text", [
    # an X a selector compares with (selectors.X_VALUE, the cast X) isn't the X the text defines: manual, not "mana value 0 or less"
    "Destroy each creature with mana value X or less and you gain X life, where X is the number of Zombies you control.",
])
def test_an_x_left_inside_a_selector_stays_manual(text):
    from tests.test_rules_scripts import ch

    assert coverage.of_characteristics(ch("Test", "Sorcery", text)).level != "FULL"


@pytest.mark.parametrize("text", [
    # wave 34C: the X the text defines, in the selector of an effect that has no target, is a live count read as the effect is carried
    # out (where_bound.tag_effects; 107.3c, 608.2h) — not the cast X
    "Draw X cards and each creature with mana value X or less gains flying until end of turn, where X is the number of Zombies you control.",
    "Destroy each creature with mana value X or less, where X is the number of Zombies you control.",
])
def test_the_x_the_text_defines_in_an_effects_own_selector_is_read_live(text):
    from tests.test_rules_scripts import ch

    assert coverage.of_characteristics(ch("Test", "Sorcery", text)).level == "FULL"
