"""Wave 111 (Star Trek), lead: the two cards whose only missing line was wave 111D's Planet land token, tested once the
groups were merged (Stable Wormhole from group G, Genesis Effect from group C; David and Carol Marcus is in 111A's tests).

`Create a tapped Planet land token named New Planet with "{T}: Add one mana of any color."`: 111.4 (the token's name),
205.3i (Planet is a land type), 111.5 (no color given: colorless), 305.6/106.1 (the quoted mana ability).
Oracle text: Scryfall, 2026-10-30 (pre-release, sets trk/trc); re-checked at release.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_wave111a_trek import answer, attack, cast, ch, own_turn_3, tokens
from tests.wave9c_kit import build, card_named, check, mana, put

PLANET = 'Create a tapped Planet land token named New Planet with "{T}: Add one mana of any color."'


def trek(i, name, cost, cmc, types, text, pt=None, colors=""):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="w111l", number=f"L{i:02d}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), keywords=[], **extra)


EXTRA = [
    trek(1, "Stable Wormhole", "{2}{G}", 3, "Enchantment", "Whenever you attack, " + PLANET[0].lower() + PLANET[1:], None, "G"),
    trek(2, "Genesis Effect", "{4}{R}", 5, "Instant",
         "Genesis Effect deals 6 damage to target creature. Destroy target land you control. " + PLANET, None, "R"),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _is_new_planet(s, token):
    now = ch(s, token)
    return (now.types, now.subtypes, now.colors, s.state.cards[token.id].tapped) == (
        frozenset({"Land"}), frozenset({"Planet"}), frozenset(), True)


# -- Stable Wormhole ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("attacks", [True, False])
def test_stable_wormhole_makes_a_new_planet_only_when_you_attack(cards, attacks):
    s = build(cards, ["Stable Wormhole", "Grizzly Bears"])
    put(s, "Stable Wormhole")
    bears = put(s, "Grizzly Bears")
    own_turn_3(s)
    attack(s, *([(bears, "p2")] if attacks else []))
    planets = tokens(s, "New Planet")
    assert len(planets) == (1 if attacks else 0)
    if attacks:
        assert _is_new_planet(s, planets[0])
    check(s)


def test_stable_wormhole_planet_taps_for_any_color(cards):
    s = build(cards, ["Stable Wormhole", "Grizzly Bears"])
    put(s, "Stable Wormhole")
    bears = put(s, "Grizzly Bears")
    own_turn_3(s)
    attack(s, (bears, "p2"))
    [planet] = tokens(s, "New Planet")
    act(s, "p1", type="tap", card_ids=[planet.id], tapped=False)  # it entered tapped; untapped by hand to use it this turn
    act(s, "p1", type="activate_ability", card_id=planet.id, ability=0)
    answer(s, ["3"])  # the color choice: {R}
    assert mana_pool(s) == {"R": 1}
    check(s)


# -- Genesis Effect ----------------------------------------------------------------------------------------------------------------------
def test_genesis_effect_kills_the_creature_destroys_your_land_and_makes_a_new_planet(cards):
    s = build(cards, ["Genesis Effect"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    forest = card_named(s, "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    mana(s, R=1, C=4)
    cast(s, "Genesis Effect", [bears.id, forest.id], target_counts=[1, 1])
    answer(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    assert s.state.cards[forest.id].zone == "p1:graveyard"
    [planet] = tokens(s, "New Planet")
    assert _is_new_planet(s, planet)
    check(s)


def test_genesis_effect_can_only_destroy_a_land_you_control(cards):
    s = build(cards, ["Genesis Effect", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    island = card_named(s, "Island", "p2")
    act(s, "p2", type="move", card_ids=[island.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, R=1, C=4)
    with pytest.raises(ActionError):  # "target land you control" (115.1): an opponent's land isn't a legal target
        cast(s, "Genesis Effect", [bears.id, island.id], target_counts=[1, 1])
    assert s.state.cards[island.id].zone == "p2:battlefield" and s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


# -- creature types with an apostrophe ---------------------------------------------------------------------------------------------------
def test_creature_types_are_spelled_as_the_cards_spell_them():
    """205.3m prints C’tan, Shi’ar, Jem’Hadar…; card type lines write a straight apostrophe. The list keeps one spelling, the cards'."""
    from app.rules.creature_types import CREATURE_TYPES

    assert not [t for t in CREATURE_TYPES if "’" in t]
    assert {"C'tan", "Shi'ar", "Jem'Hadar", "Na'kuhl", "Vau-N'Akat"} <= CREATURE_TYPES
    assert len({t.replace("'", "’") for t in CREATURE_TYPES}) == len(CREATURE_TYPES)  # no type twice (702.73a: each once)


@pytest.mark.parametrize(("type_line", "creature_types"), [
    ("Creature — Jem'Hadar Soldier", {"Jem'Hadar", "Soldier"}),
    ("Creature — C'tan", {"C'tan"}),
    ("Legendary Creature — Vau-N'Akat Scout", {"Vau-N'Akat", "Scout"}),
])
def test_a_cards_apostrophe_creature_types_are_creature_types(type_line, creature_types):
    from app.rules.characteristics import printed_from_data
    from app.rules.creature_types import CREATURE_TYPES

    data = card("Someone", set_code="w111l", number="L99", mana_cost="{2}", cmc=2.0, type_line=type_line, oracle_text="",
                colors=[], color_identity=[], keywords=[], power="2", toughness="2")
    assert printed_from_data(data).subtypes & CREATURE_TYPES == creature_types
