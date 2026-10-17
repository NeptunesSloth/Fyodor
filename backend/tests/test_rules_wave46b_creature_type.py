"""Wave 46B: "Creatures of the creature type of your choice get +N/+N until end of turn" (CR 2026-09-25, real Oracle text, tests/fixtures/wave46b_cards.json).
Every scenario checks the replay and a save and a load.

* 205.3m / 608.2d: the creature type is chosen as the spell resolves (Witch's Vengeance ruling 2019-10-04), by its controller; any creature type.
* 611.2c: the creatures are those on the battlefield as it resolves, on every side; one that enters or becomes the type later gets nothing.
* 702.73a: a changeling is every creature type, so it is of the chosen one.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules import scripts
from app.rules.characteristics import Characteristics
from app.rules.oracle import parse_abilities
from tests.game_helpers import act
from tests.test_rules_wave38a_trailing_ifs import table
from tests.test_rules_wave4j_leftovers import pick_type, typed
from tests.test_rules_wave5j_token_copies import drive
from tests.wave9c_kit import card_named, check, mana, put, pt, to_hand
from tests.wave46b_kit import make_repo, zone


@pytest.fixture()
def cards(settings):
    repo = make_repo(settings)
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Tribal Unity", "Witch's Vengeance", "Defensive Maneuvers", "Tribal Forcemage"])
def test_the_spells_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_witchs_vengeance_kills_every_creature_of_the_chosen_type_on_both_sides(cards):
    s = table(cards, ["Witch's Vengeance", "Soul Warden", "Grizzly Bears"], ["Young Pyromancer"])
    put(s, "Soul Warden")
    put(s, "Grizzly Bears")
    put(s, "Young Pyromancer", "p2")
    to_hand(s, "Witch's Vengeance")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Witch's Vengeance").id)
    prompts = []

    def pick(d):
        prompts.append(d.prompt)
        return pick_type("Human")(d)

    drive(s, pick)
    assert any("creature type" in p for p in prompts)  # (chosen as it resolves)
    assert zone(s, "Soul Warden") == "p1:graveyard" and zone(s, "Young Pyromancer", "p2") == "p2:graveyard"
    assert zone(s, "Grizzly Bears") == "p1:battlefield"
    check(s)


def test_defensive_maneuvers_pumps_only_the_chosen_type_until_end_of_turn(cards):
    s = table(cards, ["Defensive Maneuvers", "Soul Warden", "Grizzly Bears"])
    put(s, "Soul Warden")
    put(s, "Grizzly Bears")
    to_hand(s, "Defensive Maneuvers")
    mana(s, W=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Defensive Maneuvers").id)
    drive(s, pick_type("Bear"))
    assert pt(s, "Grizzly Bears") == (2, 6) and pt(s, "Soul Warden") == (1, 1)
    later = typed(s, "p1", "Late Bear", "Bear")  # (611.2c: it wasn't there as the spell resolved)
    assert pt(s, later.name) == (2, 2)
    check(s)


def test_tribal_unity_reads_x_and_a_changeling_is_of_every_type(cards):
    s = table(cards, ["Tribal Unity", "Soul Warden"])
    put(s, "Soul Warden")
    act(s, "p1", type="create_token", player="p1", token={"name": "Shifty", "type_line": "Token Creature — Shapeshifter", "power": "1",
                                                           "toughness": "1", "text": "Changeling"})
    to_hand(s, "Tribal Unity")
    mana(s, G=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Tribal Unity").id, x_value=2)
    drive(s, pick_type("Cleric"))
    assert pt(s, "Soul Warden") == (3, 3) and pt(s, "Shifty") == (3, 3)
    check(s)


def test_karonas_line_and_the_forcemage_trigger_read_the_choice():
    def defs(text, types):
        return scripts.definitions(Characteristics(name="Probe", types=frozenset(types), abilities=tuple(parse_abilities(text)), oracle_text=text))

    d = defs("Whenever Probe attacks, creatures of the creature type of your choice get +3/+3 until end of turn.", {"Creature"})
    assert d and [e["do"] for e in d[0]["effects"]][:2] == ["choose_value", "pump"]
    # not read: a creature type of someone else's choice, or a card type
    assert defs("Creatures of the creature type of an opponent's choice get +3/+3 until end of turn.", {"Sorcery"}) == {}
