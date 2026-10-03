"""Wave 9C: replacement effects on the mana a permanent produces when tapped for mana (106.12b, 614.1a), researched
against CR 2026-09-25: Mana Reflection / Nyxbloom Ancient / Virtue of Strength (twice / three times as much),
Contamination / Infernal Darkness (only {B}), Ritual of Subdual (colorless), Damping Sphere ({C} for two or more mana),
Pulse of Llanowar (a color of your choice).

Only abilities with {T} in their cost are "tapped for mana" (106.12); two such statics on one ability, restricted mana
and counted mana are left to the player (616.1 ordering and 106.6a are not modelled); Reflecting Pool-style "could
produce" is left to the player while one is in play (106.7).
Every scenario uses real Oracle text and checks the replay and a save and a load.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_permissions import build, find, put
from tests.test_rules_wave5a_mana_riders import roundtrip

EXTRA = [
    card('Mana Reflection', set_code='wm', number='E01', mana_cost='{4}{G}{G}', cmc=6.0, type_line='Enchantment', oracle_text='If you tap a permanent for mana, it produces twice as much of that mana instead.', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Nyxbloom Ancient', set_code='wm', number='E02', mana_cost='{4}{G}{G}{G}', cmc=7.0, type_line='Enchantment Creature — Elemental', oracle_text='Trample\nIf you tap a permanent for mana, it produces three times as much of that mana instead.', colors=['G'], color_identity=['G'], keywords=['Trample'], power='5', toughness='5'),  # noqa: E501
    card('Virtue of Strength // Garenbrig Growth', set_code='wm', number='E03', layout='adventure', mana_cost='{5}{G}{G} // {G}', cmc=7.0, type_line='Enchantment // Sorcery — Adventure', oracle_text='If you tap a basic land for mana, it produces three times as much of that mana instead.\n//\nReturn target creature or land card from your graveyard to your hand. (Then exile this card. You may cast the enchantment later from exile.)', colors=['G'], color_identity=['G'], keywords=[],  # noqa: E501
         card_faces=[
             {"object": "card_face", "name": "Virtue of Strength", "mana_cost": "{5}{G}{G}", "type_line": "Enchantment", "oracle_text": "If you tap a basic land for mana, it produces three times as much of that mana instead."},
             {"object": "card_face", "name": "Garenbrig Growth", "mana_cost": "{G}", "type_line": "Sorcery — Adventure", "oracle_text": "Return target creature or land card from your graveyard to your hand. (Then exile this card. You may cast the enchantment later from exile.)"},
         ]),
    card('Contamination', set_code='wm', number='E04', mana_cost='{2}{B}', cmc=3.0, type_line='Enchantment', oracle_text='At the beginning of your upkeep, sacrifice this enchantment unless you sacrifice a creature.\nIf a land is tapped for mana, it produces {B} instead of any other type and amount.', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Ritual of Subdual', set_code='wm', number='E05', mana_cost='{4}{G}{G}', cmc=6.0, type_line='Enchantment', oracle_text='Cumulative upkeep {2} (At the beginning of your upkeep, put an age counter on this permanent, then sacrifice it unless you pay its upkeep cost for each age counter on it.)\nIf a land is tapped for mana, it produces colorless mana instead of any other type.', colors=['G'], color_identity=['G'], keywords=['Cumulative upkeep']),  # noqa: E501
    card('Pulse of Llanowar', set_code='wm', number='E06', mana_cost='{3}{G}', cmc=4.0, type_line='Enchantment', oracle_text='If a basic land you control is tapped for mana, it produces mana of a color of your choice instead of any other type.', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Damping Sphere', set_code='wm', number='E07', mana_cost='{2}', cmc=2.0, type_line='Artifact', oracle_text='If a land is tapped for two or more mana, it produces {C} instead of any other type and amount.\nEach spell a player casts costs {1} more to cast for each other spell that player has cast this turn.', colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Gauntlet of Might', set_code='wm', number='E20', mana_cost='{4}', cmc=4.0, type_line='Artifact', oracle_text='Red creatures get +1/+1.\nWhenever a Mountain is tapped for mana, its controller adds an additional {R}.', colors=[], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Vernal Bloom', set_code='wm', number='E21', mana_cost='{3}{G}', cmc=4.0, type_line='Enchantment', oracle_text='Whenever a Forest is tapped for mana, its controller adds an additional {G}.', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Dark Imp', set_code='wm', number='E10', mana_cost='{B}', cmc=1.0, type_line='Creature — Imp', oracle_text='', power='1', toughness='1', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Red Imp', set_code='wm', number='E11', mana_cost='{R}', cmc=1.0, type_line='Creature — Imp', oracle_text='', power='1', toughness='1', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Green Cub', set_code='wm', number='E12', mana_cost='{G}', cmc=1.0, type_line='Creature — Bear', oracle_text='', power='1', toughness='1', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Quiet Bear', set_code='wm', number='E13', mana_cost='{2}', cmc=2.0, type_line='Creature — Bear', oracle_text='', power='2', toughness='2', colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Triple Idol', set_code='wm', number='E14', mana_cost='{3}', cmc=3.0, type_line='Artifact', oracle_text='', colors=[], color_identity=[], keywords=[]),  # noqa: E501
]
VIRTUE = "Virtue of Strength // Garenbrig Growth"
FULL = ["Gauntlet of Might", "Vernal Bloom", "Mana Reflection", "Nyxbloom Ancient", "Contamination", "Ritual of Subdual", "Pulse of Llanowar"]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def table(cards, *names, lands=1):
    s = build(cards, [(1, n) for n in names] + [(9, "Forest")])
    for n in names:
        if n in ("Mana Reflection", "Nyxbloom Ancient", VIRTUE, "Contamination", "Ritual of Subdual",
                 "Pulse of Llanowar", "Damping Sphere"):
            put(s, n.split(" //")[0], "battlefield")
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"]
    for c in forests[:lands]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    return s


def forest(s):
    return next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:battlefield")


def cast_from_hand(s, name):
    c = put(s, name, "hand")
    act(s, "p1", type="cast_spell", card_id=c.id)
    return c


def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
            assert coverage.of_characteristics(chs).level == "FULL", c["name"]


@pytest.mark.parametrize("line", [
    "If you tap a permanent for mana, it produces four times as much of that mana instead.",
    "If an opponent taps a land for mana, it produces twice as much of that mana instead.",
    "If a land is tapped for mana, it produces {B}{B} instead of any other type.",
    "If you tap a land for mana, it produces {B} instead of any other type.",
    "If a nonbasic land is tapped for mana, it produces colorless mana instead of any other type."])
def test_other_wordings_stay_manual(line):
    from tests.test_rules_scripts import ch as characteristics

    assert coverage.of_characteristics(characteristics("Test", "Enchantment", line)).level != "FULL", line


def test_mana_reflection_doubles_what_a_tapped_land_makes(cards):
    s = table(cards, "Mana Reflection", "Quiet Bear")
    f = forest(s)
    act(s, "p1", type="activate_ability", card_id=f.id, ability=0)
    assert s.state.players["p1"].mana == {"G": 2}
    roundtrip(s)


def test_the_payer_uses_the_doubled_mana(cards):
    s = table(cards, "Mana Reflection", "Quiet Bear")
    cast_from_hand(s, "Quiet Bear")  # {2} from one Forest
    assert s.state.cards[find(s, "Quiet Bear").id].zone == "p1:battlefield" and s.state.cards[forest(s).id].tapped
    roundtrip(s)


def test_nyxbloom_ancient_triples_any_permanent_including_nonlands(cards):
    s = table(cards, "Nyxbloom Ancient", "Triple Idol", "Sol Ring", lands=0)
    sol = put(s, "Sol Ring", "battlefield")
    act(s, "p1", type="activate_ability", card_id=sol.id, ability=0)
    assert s.state.players["p1"].mana == {"C": 6}  # {C}{C} three times
    roundtrip(s)


def test_virtue_of_strength_triples_basic_lands_only(cards):
    s = table(cards, VIRTUE, "Triple Idol", "Sol Ring")
    sol = put(s, "Sol Ring", "battlefield")
    act(s, "p1", type="activate_ability", card_id=sol.id, ability=0)
    assert s.state.players["p1"].mana == {"C": 2}  # (not a basic land)
    act(s, "p1", type="activate_ability", card_id=forest(s).id, ability=0)
    assert s.state.players["p1"].mana == {"C": 2, "G": 3}
    roundtrip(s)


def test_contamination_makes_one_black_mana_whatever_the_land_made(cards):
    s = table(cards, "Contamination", "Dark Imp", "Green Cub")
    act(s, "p1", type="activate_ability", card_id=forest(s).id, ability=0)
    assert s.state.players["p1"].mana == {"B": 1}
    roundtrip(s)


def test_contamination_stops_a_forest_paying_for_green(cards):
    s = table(cards, "Contamination", "Dark Imp", "Green Cub")
    c = put(s, "Green Cub", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id)
    cast_from_hand(s, "Dark Imp")
    assert s.state.cards[find(s, "Dark Imp").id].zone == "p1:battlefield"
    roundtrip(s)


def test_ritual_of_subdual_makes_colorless_mana(cards):
    s = table(cards, "Ritual of Subdual", "Quiet Bear", "Green Cub")
    c = put(s, "Green Cub", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id)
    act(s, "p1", type="activate_ability", card_id=forest(s).id, ability=0)
    assert s.state.players["p1"].mana == {"C": 1}
    roundtrip(s)


def test_pulse_of_llanowar_lets_a_basic_land_make_any_color(cards):
    s = table(cards, "Pulse of Llanowar", "Red Imp")
    cast_from_hand(s, "Red Imp")  # {R} from a Forest
    assert s.state.cards[find(s, "Red Imp").id].zone == "p1:battlefield"
    roundtrip(s)


def test_two_replacements_on_one_land_are_left_to_the_player(cards):
    """616.1: the order of two applicable replacement effects is the affected player's choice; not modelled, so the
    engine does not tap the land by itself."""
    s = table(cards, "Mana Reflection", "Contamination", "Dark Imp")
    c = put(s, "Dark Imp", "hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id)
    roundtrip(s)


def test_gauntlet_of_might_adds_a_red_for_each_mountain_tapped(cards):
    """"Whenever a Mountain is tapped for mana, its controller adds an additional {R}": a triggered mana ability (605.1b)
    for that land type only, whoever controls the Gauntlet."""
    s = build(cards, [(1, "Gauntlet of Might"), (4, "Mountain"), (4, "Forest")])
    put(s, "Gauntlet of Might", "battlefield")
    mountain = put(s, "Mountain", "battlefield")
    act(s, "p1", type="activate_ability", card_id=mountain.id, ability=0)
    assert s.state.players["p1"].mana == {"R": 2}
    forest_card = put(s, "Forest", "battlefield")
    act(s, "p1", type="activate_ability", card_id=forest_card.id, ability=0)
    assert s.state.players["p1"].mana == {"R": 2, "G": 1}
    roundtrip(s)


def test_vernal_bloom_doubles_forests(cards):
    s = build(cards, [(1, "Vernal Bloom"), (8, "Forest")])
    put(s, "Vernal Bloom", "battlefield")
    act(s, "p1", type="activate_ability", card_id=put(s, "Forest", "battlefield").id, ability=0)
    assert s.state.players["p1"].mana == {"G": 2}
    roundtrip(s)
