"""Wave 25A: conditions of "as long as" statics: the source's own state and types, the object it is attached to (CR 604.2, 611.3a, 613.1d, 303.4).

* "~ gets +2/+0 as long as it isn't attacking or blocking." (Intrepid Ace), "As long as this creature is enchanted or equipped, it can attack as
  though it didn't have defender." (Novice Knight), "As long as this permanent is a creature, it has prowess." (Triton Wavebreaker), "~ has
  defender as long as it's a Wall." (Mistform Wall);
* "Enchanted creature gets +2/+2 as long as it's a Human. Otherwise, it can't attack or block." (Bonds of Faith), "As long as you control
  enchanted creature, it gets +2/+2. Otherwise, it can't block." (Mishra's Domination), "As long as enchanted creature isn't legendary, it
  doesn't untap during its controller's untap step." (Stunning Strike).
Every statement is a continuous effect that applies at any moment its condition is true (611.3a): it follows the object as it changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import ch
from tests.test_rules_effects import mana, token
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card('Intrepid Ace', set_code='tst', number='M01', mana_cost='{R}', cmc=1.0, type_line='Creature — Human Pilot', oracle_text="This creature gets +2/+0 as long as it isn't attacking or blocking.", power='2', toughness='1', colors=['R'], color_identity=['R'], keywords=[], layout='normal'),  # noqa: E501
    card('Bonds of Faith', set_code='tst', number='M02', mana_cost='{1}{W}', cmc=2.0, type_line='Enchantment — Aura', oracle_text="Enchant creature\nEnchanted creature gets +2/+2 as long as it's a Human. Otherwise, it can't attack or block.", colors=['W'], color_identity=['W'], keywords=['Enchant'], layout='normal'),  # noqa: E501
    card("Mishra's Domination", set_code='tst', number='M03', mana_cost='{1}{R}', cmc=2.0, type_line='Enchantment — Aura', oracle_text="Enchant creature\nAs long as you control enchanted creature, it gets +2/+2. Otherwise, it can't block.", colors=['R'], color_identity=['R'], keywords=['Enchant'], layout='normal'),  # noqa: E501
    card('Stunning Strike', set_code='tst', number='M04', mana_cost='{2}{U}', cmc=3.0, type_line='Enchantment — Aura', oracle_text="Flash\nEnchant creature\nWhen this Aura enters, tap enchanted creature and remove it from combat.\nAs long as enchanted creature isn't legendary, it doesn't untap during its controller's untap step.", colors=['U'], color_identity=['U'], keywords=['Enchant', 'Flash'], layout='normal'),  # noqa: E501
    card('Triton Wavebreaker', set_code='tst', number='M05', mana_cost='{U}', cmc=1.0, type_line='Enchantment Creature — Merfolk Wizard', oracle_text="Bestow {1}{U} (If you cast this card for its bestow cost, it's an Aura spell with enchant creature. It becomes a creature again if it's not attached.)\nAs long as this permanent is a creature, it has prowess. (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nEnchanted creature gets +1/+1 and has prowess.", power='1', toughness='1', colors=['U'], color_identity=['U'], keywords=['Bestow'], layout='normal'),  # noqa: E501
    card('Mistform Wall', set_code='tst', number='M06', mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Illusion Wall', oracle_text="This creature has defender as long as it's a Wall.\n{1}: This creature becomes the creature type of your choice until end of turn.", power='1', toughness='4', colors=['U'], color_identity=['U'], keywords=[], layout='normal'),  # noqa: E501
    card('Novice Knight', set_code='tst', number='M07', mana_cost='{W}', cmc=1.0, type_line='Creature — Human Knight', oracle_text="Defender (This creature can't attack.)\nAs long as this creature is enchanted or equipped, it can attack as though it didn't have defender.", power='2', toughness='3', colors=['W'], color_identity=['W'], keywords=['Defender'], layout='normal'),  # noqa: E501
    card('Elite Vanguard', set_code='tst', number='M08', mana_cost='{W}', cmc=1.0, type_line='Creature — Human Soldier', power='2', toughness='1', colors=['W'], color_identity=['W'], keywords=[], layout='normal'),  # noqa: E501
    card('Isamaru, Hound of Konda', set_code='tst', number='M09', mana_cost='{W}', cmc=1.0, type_line='Legendary Creature — Dog', power='2', toughness='2', colors=['W'], color_identity=['W'], keywords=[], layout='normal'),  # noqa: E501
    card('Test Bear', set_code='tst', number='M99', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Bear', power='2', toughness='2', colors=['G'], color_identity=['G'], oracle_text=''),
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Intrepid Ace", "Bonds of Faith", "Mishra's Domination", "Stunning Strike", "Triton Wavebreaker", "Mistform Wall",
                                  "Novice Knight"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def enchant(s, aura, target):
    put(s, aura, "hand")
    mana(s, W=2, U=3, R=2)
    act(s, "p1", type="cast_spell", card_id=find(s, aura).id, targets=[target.id])
    answer(s)
    assert find(s, aura).zone == "p1:battlefield" and find(s, aura).attached_to == target.id


def test_it_isnt_attacking_or_blocking_follows_the_combat_state(cards):
    s = build(cards, p1=("Intrepid Ace",))
    ace = put(s, "Intrepid Ace", "battlefield")
    assert ch(s, ace).pt == (4, 1)  # 2/1 and +2/+0
    s.state.cards[ace.id].attacking = "p2"
    assert ch(s, ace).pt == (2, 1)
    s.state.cards[ace.id].attacking = None
    s.state.cards[ace.id].blocking = "x"
    assert ch(s, ace).pt == (2, 1)
    s.state.cards[ace.id].blocking = None
    roundtrip(s)


def test_a_creature_with_defender_attacks_only_while_enchanted_or_equipped(cards):
    s = build(cards, p1=("Novice Knight", "Bonds of Faith"))
    knight = put(s, "Novice Knight", "battlefield")
    assert "attack_despite_defender" not in ch(s, knight).imposed
    enchant(s, "Bonds of Faith", find(s, "Novice Knight"))
    assert "attack_despite_defender" in ch(s, find(s, "Novice Knight")).imposed
    roundtrip(s)


def test_a_wall_has_defender(cards):
    s = build(cards, p1=("Mistform Wall",))
    wall = put(s, "Mistform Wall", "battlefield")
    assert "defender" in ch(s, wall).keywords  # (Illusion Wall)
    roundtrip(s)


def test_bonds_of_faith_gives_a_human_the_bonus_and_anyone_else_cant_attack_or_block(cards):
    s = build(cards, p1=("Bonds of Faith", "Elite Vanguard", "Test Bear"))
    human = put(s, "Elite Vanguard", "battlefield")
    bear = put(s, "Test Bear", "battlefield")
    enchant(s, "Bonds of Faith", human)
    assert ch(s, human).pt == (4, 3) and "cant_attack_or_block" not in ch(s, human).imposed
    act(s, "p1", type="move", card_ids=[find(s, "Bonds of Faith").id], to={"zone": "hand"})
    enchant(s, "Bonds of Faith", bear)
    assert ch(s, bear).pt == (2, 2) and "cant_attack_or_block" in ch(s, bear).imposed  # Otherwise: it can't attack or block (611.3a)
    roundtrip(s)


def test_mishras_domination_depends_on_who_controls_the_enchanted_creature(cards):
    s = build(cards, p1=("Mishra's Domination", "Test Bear"))
    mine = put(s, "Test Bear", "battlefield")
    theirs = token(s, "p2", "Theirs", "2/2")
    enchant(s, "Mishra's Domination", mine)
    assert ch(s, mine).pt == (4, 4) and "cant_block" not in ch(s, mine).imposed
    act(s, "p1", type="move", card_ids=[find(s, "Mishra's Domination").id], to={"zone": "hand"})
    enchant(s, "Mishra's Domination", theirs)
    assert ch(s, theirs).pt == (2, 2) and "cant_block" in ch(s, theirs).imposed  # Otherwise, it can't block
    roundtrip(s)


def test_stunning_strike_holds_down_only_a_nonlegendary_creature(cards):
    s = build(cards, p1=("Stunning Strike", "Test Bear"))
    bear = put(s, "Test Bear", "battlefield")
    enchant(s, "Stunning Strike", bear)
    assert "doesnt_untap" in ch(s, bear).imposed
    roundtrip(s)


def test_stunning_strike_does_not_hold_down_a_legendary_creature(cards):
    s = build(cards, p1=("Stunning Strike", "Isamaru, Hound of Konda"))
    isamaru = put(s, "Isamaru, Hound of Konda", "battlefield")
    enchant(s, "Stunning Strike", isamaru)
    assert "doesnt_untap" not in ch(s, isamaru).imposed  # 611.3a: it applies only while the creature isn't legendary
    roundtrip(s)


def test_a_bestowed_triton_wavebreaker_is_no_creature_so_it_has_no_prowess_but_gives_it(cards):
    s = build(cards, p1=("Triton Wavebreaker", "Test Bear"))
    wave = put(s, "Triton Wavebreaker", "battlefield")
    assert "prowess" in ch(s, wave).keywords  # as long as this permanent is a creature
    put(s, "Triton Wavebreaker", "exile")
    wave = put(s, "Triton Wavebreaker", "hand")
    bear = put(s, "Test Bear", "battlefield")
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=wave.id, alt_cost=f"{wave.id}:0", targets=[bear.id])  # bestow {1}{U}
    answer(s)
    assert find(s, "Triton Wavebreaker").attached_to == bear.id
    assert not ch(s, find(s, "Triton Wavebreaker")).is_creature and "prowess" not in ch(s, find(s, "Triton Wavebreaker")).keywords
    assert "prowess" in ch(s, bear).keywords and ch(s, bear).pt == (3, 3)  # "Enchanted creature gets +1/+1 and has prowess"
    roundtrip(s)
