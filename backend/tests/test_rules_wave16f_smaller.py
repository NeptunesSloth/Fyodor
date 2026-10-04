"""Wave 16F: the smaller non-keyword families. Real Oracle text; every scenario checks the replay and a save and a load.

* 604.1 / 603.1: a ", where X is …" that sits inside a quoted granted ability belongs to that ability, not to the Aura's sentence.
"""

from __future__ import annotations

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import check

IDOLIZED = ("Enchant creature\nEnchanted creature has \"Whenever this creature attacks alone, it gets +X/+X until end of turn, "
            "where X is the number of nonland permanents you control.\"")


def test_a_where_x_inside_a_granted_ability_is_that_abilitys(cards):
    from tests.test_rules_combat import attack, automate, creature, table

    s = table(cards)
    bear = creature(s, "p1", "Bear", "2/2")
    creature(s, "p1", "Ox", "1/1")
    act(s, "p1", type="create_token", player="p1", token={
        "name": "Idolized", "type_line": "Token Enchantment — Aura", "power": None, "toughness": None, "colors": [],
        "text": IDOLIZED})
    aura = next(c for c in s.state.cards.values() if c.name == "Idolized")
    act(s, "p1", type="attach", card_ids=[aura.id], to=bear.id)
    automate(s)
    attack(s, (bear, "p2"))
    answer(s)
    from app.rules import sba
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bear.id])
    assert (sba.power(s.state.cards[bear.id], ch), sba.toughness(s.state.cards[bear.id], ch)) == (5, 5)  # Bear, Ox, the Aura: X = 3
    check(s)


def test_idolized_is_full():
    from app.rules.characteristics import Characteristics, parse_type_line
    from app.rules.oracle import parse_abilities

    sup, types, subs = parse_type_line("Enchantment — Aura")
    ch = Characteristics(name="Idolized", supertypes=sup, types=types, subtypes=subs, oracle_text=IDOLIZED,
                         abilities=tuple(parse_abilities(IDOLIZED, spell=False)), mana_cost="{1}{W}")
    assert coverage.of_characteristics(ch).level == "FULL"
