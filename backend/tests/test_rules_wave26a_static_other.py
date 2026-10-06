"""Wave 26A (static_other): "[each|all] <group> target player/opponent controls" (CR 115.1, 608.2c).

* "Simoon deals 1 damage to each creature target opponent controls." (the player is the one target; the creatures are not targeted and are
  read as the spell resolves), "Destroy all enchantments target player controls." (Primeval Light), "Return all nonland permanents target
  player controls to their owner's hand." (River's Rebuke).
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
from tests.test_rules_combat import _blocks, _evasion_table
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card('Simoon', set_code='tst', number='N01', mana_cost='{R}{G}', cmc=2.0, type_line='Instant', oracle_text='Simoon deals 1 damage to each creature target opponent controls.', colors=['R', 'G'], color_identity=['R', 'G'], keywords=[], layout='normal'),  # noqa: E501
    card('Primeval Light', set_code='tst', number='N02', mana_cost='{1}{G}{G}', cmc=3.0, type_line='Sorcery', oracle_text='Destroy all enchantments target player controls.', colors=['G'], color_identity=['G'], keywords=[], layout='normal'),  # noqa: E501
    card("River's Rebuke", set_code='tst', number='N03', mana_cost='{4}{U}{U}', cmc=6.0, type_line='Sorcery', oracle_text="Return all nonland permanents target player controls to their owner's hand.", colors=['U'], color_identity=['U'], keywords=[], layout='normal'),  # noqa: E501
    card('Evaporate', set_code='tst', number='N04', mana_cost='{1}{R}', cmc=2.0, type_line='Sorcery', oracle_text='Evaporate deals 1 damage to each white and/or blue creature.', colors=['R'], color_identity=['R'], keywords=[], layout='normal'),  # noqa: E501
    card('Test Knight', set_code='tst', number='N97', mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Knight', power='2', toughness='2', colors=['W'], color_identity=['W'], oracle_text=''),  # noqa: E501
    card('Ghastly Demise', set_code='tst', number='N05', mana_cost='{B}', cmc=1.0, type_line='Instant', oracle_text='Destroy target nonblack creature if its toughness is less than or equal to the number of cards in your graveyard.', colors=['B'], color_identity=['B'], keywords=[], layout='normal'),  # noqa: E501
    card('Touch of Darkness', set_code='tst', number='N06', mana_cost='{B}', cmc=1.0, type_line='Instant', oracle_text='One or more target creatures become black until end of turn.', colors=['B'], color_identity=['B'], keywords=[], layout='normal'),  # noqa: E501
    card('Viridescent Wisps', set_code='tst', number='N07', mana_cost='{G}', cmc=1.0, type_line='Instant', oracle_text='Target creature becomes green and gets +1/+0 until end of turn.\nDraw a card.', colors=['G'], color_identity=['G'], keywords=[], layout='normal'),  # noqa: E501
    card('Soul Search', set_code='tst', number='N08', mana_cost='{2}{B}', cmc=3.0, type_line='Sorcery', oracle_text="Target opponent reveals their hand. You choose a nonland card from it. Exile that card. If the card's mana value is 1 or less, create a 1/1 white and black Spirit creature token with flying.", colors=['B'], color_identity=['B'], keywords=[], layout='normal'),  # noqa: E501
    card('Perish the Thought', set_code='tst', number='N09', mana_cost='{2}{B}', cmc=3.0, type_line='Sorcery', oracle_text='Target opponent reveals their hand. You choose a card from it. That player shuffles that card into their library.', colors=['B'], color_identity=['B'], keywords=[], layout='normal'),  # noqa: E501
    card('Lost Hours', set_code='tst', number='N10', mana_cost='{2}{B}', cmc=3.0, type_line='Sorcery', oracle_text='Target player reveals their hand. You choose a nonland card from it. That player puts that card into their library third from the top.', colors=['B'], color_identity=['B'], keywords=[], layout='normal'),  # noqa: E501
    card("Talara's Bane", set_code='tst', number='N11', mana_cost='{1}{B}', cmc=2.0, type_line='Sorcery', oracle_text="Target opponent reveals their hand. You choose a green or white creature card from it. You gain life equal to that creature card's toughness, then that player discards that card.", colors=['B'], color_identity=['B'], keywords=[], layout='normal'),  # noqa: E501
    card('Break Under Pressure', set_code='tst', number='N12', mana_cost='{2}{B}', cmc=3.0, type_line='Sorcery', oracle_text='Target opponent sacrifices a creature or planeswalker with the greatest mana value among creatures and planeswalkers they control.', colors=['B'], color_identity=['B'], keywords=[], layout='normal'),  # noqa: E501
    card('End of the Hunt', set_code='tst', number='N13', mana_cost='{1}{B}', cmc=2.0, type_line='Sorcery', oracle_text='Target opponent exiles a creature or planeswalker they control with the greatest mana value among creatures and planeswalkers they control.', colors=['B'], color_identity=['B'], keywords=[], layout='normal'),  # noqa: E501
    card('Test Bear', set_code='tst', number='N99', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Bear', power='2', toughness='2', colors=['G'], color_identity=['G'], oracle_text=''),  # noqa: E501
    card('Test Glass', set_code='tst', number='N98', mana_cost='{W}', cmc=1.0, type_line='Enchantment', oracle_text='', colors=['W'], color_identity=['W']),  # noqa: E501
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Simoon", "Primeval Light", "River's Rebuke", "Evaporate", "Ghastly Demise", "Touch of Darkness", "Viridescent Wisps", "Soul Search", "Perish the Thought", "Lost Hours", "Talara's Bane", "Break Under Pressure", "End of the Hunt"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def cast(s, name, target):
    put(s, name, "hand")
    mana(s, W=3, U=6, R=3, G=3, B=3)
    act(s, "p1", type="cast_spell", card_id=find(s, name).id, targets=[target])
    answer(s)


def test_simoon_hits_only_the_targeted_opponents_creatures(cards):
    s = build(cards, p1=("Simoon", "Test Bear"), p2=("Test Bear",))
    mine, theirs = put(s, "Test Bear", "battlefield"), put(s, "Test Bear", "battlefield", pid="p2")
    cast(s, "Simoon", "p2")
    assert s.state.cards[theirs.id].damage == 1 and s.state.cards[mine.id].damage == 0
    roundtrip(s)


def test_primeval_light_destroys_only_their_enchantments(cards):
    s = build(cards, p1=("Primeval Light", "Test Glass"), p2=("Test Glass",))
    mine, theirs = put(s, "Test Glass", "battlefield"), put(s, "Test Glass", "battlefield", pid="p2")
    cast(s, "Primeval Light", "p2")
    assert s.state.cards[theirs.id].zone == "p2:graveyard" and s.state.cards[mine.id].zone == "p1:battlefield"
    roundtrip(s)


def test_rivers_rebuke_returns_their_nonland_permanents_to_their_owners(cards):
    s = build(cards, p1=("River's Rebuke", "Test Bear"), p2=("Test Bear",))
    mine, theirs = put(s, "Test Bear", "battlefield"), put(s, "Test Bear", "battlefield", pid="p2")
    cast(s, "River's Rebuke", "p2")
    assert s.state.cards[theirs.id].zone == "p2:hand" and s.state.cards[mine.id].zone == "p1:battlefield"
    roundtrip(s)


def test_evaporate_hits_white_and_or_blue_creatures_only(cards):
    s = build(cards, p1=("Evaporate", "Test Bear"), p2=("Test Knight",))
    bear, knight = put(s, "Test Bear", "battlefield"), put(s, "Test Knight", "battlefield", pid="p2")
    put(s, "Evaporate", "hand")
    mana(s, R=3)
    act(s, "p1", type="cast_spell", card_id=find(s, "Evaporate").id)
    answer(s)
    assert s.state.cards[knight.id].damage == 1 and s.state.cards[bear.id].damage == 0
    roundtrip(s)


@pytest.mark.parametrize(("graveyard", "dies"), [(1, False), (2, True)])
def test_ghastly_demise_compares_toughness_with_my_graveyard(cards, graveyard, dies):
    s = build(cards, p1=("Ghastly Demise", "Evaporate", "Simoon"), p2=("Test Bear",))
    bear = put(s, "Test Bear", "battlefield", pid="p2")
    for name in ("Evaporate", "Simoon")[:graveyard]:
        put(s, name, "graveyard")
    cast(s, "Ghastly Demise", bear.id)
    assert (s.state.cards[bear.id].zone == "p2:graveyard") is dies
    roundtrip(s)


@pytest.mark.parametrize(("wall", "blockable"), [("Creatures with forestwalk can be blocked as though they didn't have forestwalk.", True),
                                                 ("Creatures with plainswalk can be blocked as though they didn't have plainswalk.", False)])
def test_great_wall_style_static_ignores_only_its_landwalk(cards, wall, blockable):
    s, sneak, guard = _evasion_table(cards, "Forestwalk")
    forest = next(c for c in s.state.cards.values() if c.owner == "p2" and c.name == "Forest")
    act(s, "p2", type="move", card_ids=[forest.id], to={"zone": "battlefield"})
    act(s, "p2", type="create_token", player="p2", token={"name": "Wall", "type_line": "Token Artifact", "text": wall})
    assert _blocks(s, sneak, guard) is blockable


def test_one_or_more_target_creatures_become_black(cards):
    s = build(cards, p1=("Touch of Darkness", "Test Bear"), p2=("Test Knight",))
    bear, knight = put(s, "Test Bear", "battlefield"), put(s, "Test Knight", "battlefield", pid="p2")
    put(s, "Touch of Darkness", "hand")
    mana(s, B=2)
    act(s, "p1", type="cast_spell", card_id=find(s, "Touch of Darkness").id, targets=[bear.id, knight.id], target_counts=[2])
    answer(s)
    assert ch(s, s.state.cards[bear.id]).colors == {"B"} and ch(s, s.state.cards[knight.id]).colors == {"B"}
    roundtrip(s)


def test_becomes_green_and_gets_plus_one_zero(cards):
    s = build(cards, p1=("Viridescent Wisps", "Test Knight"))
    knight = put(s, "Test Knight", "battlefield")
    put(s, "Viridescent Wisps", "hand")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=find(s, "Viridescent Wisps").id, targets=[knight.id])
    answer(s)
    assert ch(s, s.state.cards[knight.id]).colors == {"G"} and ch(s, s.state.cards[knight.id]).pt == (3, 2)
    roundtrip(s)


@pytest.mark.parametrize(("victim", "spirit"), [("Test Glass", True), ("Test Bear", False)])
def test_soul_search_reads_the_exiled_cards_mana_value(cards, victim, spirit):
    s = build(cards, p1=("Soul Search",), p2=(victim,))
    put(s, victim, "hand", pid="p2")
    cast(s, "Soul Search", "p2")
    assert find(s, victim, "p2").zone == "p2:exile"
    assert any(c.name == "Spirit" and c.zone == "p1:battlefield" for c in s.state.cards.values()) is spirit
    roundtrip(s)


def test_chosen_card_goes_back_to_the_library_shuffled(cards):
    s = build(cards, p1=("Perish the Thought",), p2=("Test Bear",))
    put(s, "Test Bear", "hand", pid="p2")
    cast(s, "Perish the Thought", "p2")
    assert find(s, "Test Bear", "p2").zone == "p2:library"
    roundtrip(s)


def test_chosen_card_goes_third_from_the_top(cards):
    s = build(cards, p1=("Lost Hours",), p2=("Test Bear",))
    put(s, "Test Bear", "hand", pid="p2")
    cast(s, "Lost Hours", "p2")
    bear = find(s, "Test Bear", "p2")
    assert s.state.zones["p2:library"].index(bear.id) == 2
    roundtrip(s)


def test_talaras_bane_gains_the_chosen_cards_toughness_then_discards_it(cards):
    s = build(cards, p1=("Talara's Bane",), p2=("Test Knight",))
    put(s, "Test Knight", "hand", pid="p2")
    life = s.state.players["p1"].life
    cast(s, "Talara's Bane", "p2")
    assert s.state.players["p1"].life == life + 2 and find(s, "Test Knight", "p2").zone == "p2:graveyard"
    roundtrip(s)


@pytest.mark.parametrize(("spell", "zone"), [("Break Under Pressure", "p2:graveyard"), ("End of the Hunt", "p2:exile")])
def test_greatest_mana_value_among_their_creatures(cards, spell, zone):
    s = build(cards, p1=(spell,), p2=("Test Bear", "Test Knight"))
    bear, knight = put(s, "Test Bear", "battlefield", pid="p2"), put(s, "Test Knight", "battlefield", pid="p2")
    cast(s, spell, "p2")
    assert s.state.cards[bear.id].zone == zone and s.state.cards[knight.id].zone == "p2:battlefield"
    roundtrip(s)
