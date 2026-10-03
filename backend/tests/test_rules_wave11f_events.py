"""Wave 11F: event triggers - "a source deals damage" (120.3, 603.2), "activates an ability" (602.2) - and intervening-if
conditions (603.4). Each scenario uses real Oracle text and checks the replay and a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import counters, life, settle, token_of
from tests.test_rules_effects import mana, replay_matches
from tests.wave9c_kit import build, card_named, put, to_hand


def real(name, cost, cmc, types, text, pt=None, colors=()):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=f"11F-{name[:6]}", mana_cost=cost, cmc=float(cmc), type_line=types,
                oracle_text=text, colors=list(colors), color_identity=list(colors), **extra)


EXTRA = [
    real("Niv-Mizzet, Visionary", "{4}{U}{R}", 6, "Legendary Creature — Dragon Wizard",
         "You have no maximum hand size.\nWhenever a source you control deals noncombat damage to an opponent, you draw that "
         "many cards.", ("6", "6"), "UR"),
    real("Phyrexian Obliterator", "{B}{B}{B}{B}", 4, "Creature — Phyrexian Horror",
         "Trample\nWhenever a source deals damage to this creature, that source's controller sacrifices that many permanents "
         "of their choice.", ("5", "5"), "B"),
    real("Retaliator Griffin", "{3}{W}", 4, "Creature — Griffin",
         "Flying\nWhenever a source an opponent controls deals damage to you, you may put that many +1/+1 counters on this "
         "creature.", ("3", "3"), "W"),
    real("Harsh Mentor", "{1}{R}", 2, "Creature — Goblin Rogue",
         "Whenever an opponent activates an ability of an artifact, creature, or land on the battlefield, if it isn't a mana "
         "ability, this creature deals 2 damage to that player.", ("2", "2"), "R"),
    real("Runic Armasaur", "{3}{G}", 4, "Creature — Dinosaur",
         "Whenever an opponent activates an ability of a creature or land that isn't a mana ability, you may draw a card.",
         ("3", "4"), "G"),
    real("Dragonborn Champion", "{2}{R}{G}", 4, "Creature — Dragon Warrior",
         "Trample\nWhenever a source you control deals 5 or more damage to a player, draw a card.", ("5", "3"), "RG"),
    real("Lava Axe", "{4}{R}", 5, "Sorcery", "Lava Axe deals 5 damage to target player or planeswalker.", None, "R"),
    real("Elrond, Moon-Reader", "{1}{G}{U}", 3, "Legendary Creature — Elf Noble",
         "Whenever you activate an ability of a creature, draw a card. This ability triggers only once each turn.", ("3", "3"),
         "GU"),
    real("Belltower Sphinx", "{4}{U}", 5, "Creature — Sphinx",
         "Flying\nWhenever a source deals damage to this creature, that source's controller mills that many cards.", ("4", "4"),
         "U"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def bolt(s, target, pid="p1"):
    c = to_hand(s, "Lightning Bolt", pid)
    mana(s, pid, R=1)
    act(s, pid, type="cast_spell", card_id=c.id, targets=[target])
    settle(s)


@pytest.mark.parametrize("name", ["Niv-Mizzet, Visionary", "Phyrexian Obliterator", "Retaliator Griffin", "Belltower Sphinx"])
def test_source_damage_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- a source deals damage (120.3, 603.2) ----------------------------------------------------------------
def test_a_source_you_control_deals_noncombat_damage_to_an_opponent_even_a_spell(cards):
    s = build(cards, ("Niv-Mizzet, Visionary", "Lightning Bolt"))
    put(s, "Niv-Mizzet, Visionary")
    hand = len(s.state.zones["p1:hand"])
    bolt(s, "p2")
    assert life(s, "p2") == 37
    assert len(s.state.zones["p1:hand"]) == hand + 3  # drew "that many" cards: the Bolt left the hand, three came in
    roundtrip(s)


def test_a_source_you_control_dealing_damage_to_yourself_does_not_trigger(cards):
    s = build(cards, ("Niv-Mizzet, Visionary", "Lightning Bolt"))
    put(s, "Niv-Mizzet, Visionary")
    hand = len(s.state.zones["p1:hand"])
    bolt(s, "p1")
    assert len(s.state.zones["p1:hand"]) == hand
    roundtrip(s)


def test_that_sources_controller_is_the_player_who_controlled_the_source(cards):
    s = build(cards, ("Lightning Bolt",), ("Phyrexian Obliterator",))
    put(s, "Phyrexian Obliterator", "p2")
    for cid in [c.id for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:4]:
        act(s, "p1", type="move", card_ids=[cid], to={"player": "p1", "zone": "battlefield"})
    bolt(s, card_named(s, "Phyrexian Obliterator", "p2").id)
    on_field = [c for c in s.state.cards.values() if c.zone == "p1:battlefield"]
    assert len(on_field) == 1  # it dealt 3 damage: Alice (the Bolt's controller) sacrifices that many permanents
    assert s.state.cards[card_named(s, "Phyrexian Obliterator", "p2").id].zone == "p2:battlefield"
    roundtrip(s)


def test_a_source_an_opponent_controls_deals_damage_to_you(cards):
    s = build(cards, ("Lightning Bolt",), ("Retaliator Griffin",))
    griffin = put(s, "Retaliator Griffin", "p2")
    bolt(s, "p2")
    assert counters(s, griffin) == 3
    roundtrip(s)


# -- activates an ability (602.2) --------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["Harsh Mentor", "Runic Armasaur"])
def test_activation_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def pump(s, pid="p1"):
    t = token_of(s, pid, "Pumper", "Token Creature — Test", "2/2", "{R}: This creature gets +1/+0 until end of turn.")
    mana(s, pid, R=1)
    act(s, pid, type="activate_ability", card_id=t.id, ability=0)
    settle(s)
    return t


def test_an_opponent_activating_a_non_mana_ability_triggers_it(cards):
    s = build(cards, (), ("Harsh Mentor",))
    put(s, "Harsh Mentor", "p2")
    pump(s)
    assert life(s, "p1") == 38  # "that player" is the player who activated it
    roundtrip(s)


def test_your_own_ability_and_a_spell_do_not_trigger_it(cards):
    s = build(cards, ("Harsh Mentor", "Lightning Bolt"))
    put(s, "Harsh Mentor")
    pump(s)
    bolt(s, "p2")  # casting a spell is not activating an ability
    assert life(s, "p1") == 40
    roundtrip(s)


def test_an_optional_reaction_to_an_opponents_activation(cards):
    s = build(cards, (), ("Runic Armasaur",))
    put(s, "Runic Armasaur", "p2")
    hand = len(s.state.zones["p2:hand"])
    pump(s)  # (settle answers the optional draw with its first option: yes)
    assert len(s.state.zones["p2:hand"]) == hand + 1
    roundtrip(s)


def test_a_damage_threshold_is_what_one_source_dealt_in_one_event(cards):
    s = build(cards, ("Dragonborn Champion", "Lightning Bolt", "Lava Axe"))
    put(s, "Dragonborn Champion")
    hand = len(s.state.zones["p1:hand"])
    bolt(s, "p2")  # 3 damage: under the threshold
    assert len(s.state.zones["p1:hand"]) == hand
    axe = to_hand(s, "Lava Axe")
    mana(s, "p1", R=1, C=4)
    act(s, "p1", type="cast_spell", card_id=axe.id, targets=["p2"])
    settle(s)
    assert life(s, "p2") == 32 and len(s.state.zones["p1:hand"]) == hand + 1  # 5 damage: drew a card
    roundtrip(s)


@pytest.mark.parametrize("text,plain", [
    ("a nontoken creature enters the battlefield under your control", "a nontoken creature you control enters"),
    ("another creature enters under your control", "another creature you control enters"),
    ("a land enters under an opponent's control", "a land an opponent controls enters"),
    ("one or more nontoken lands enter under your control", "one or more nontoken lands you control enter"),
])
def test_enters_under_a_players_control_is_that_players_permanent_entering(text, plain):
    from app.rules import events

    assert events.parse_condition(text) == events.parse_condition(plain) is not None


@pytest.mark.parametrize("text", [
    "a permanent an opponent owns enters the battlefield under your control",  # ownership is another thing
    "a source deals 4 or more damage",  # (a threshold needs a recipient: the damage one source dealt one recipient)
    "a creature has activated an ability",
])
def test_unread_wordings_stay_manual(text):
    from app.rules import events

    assert events.parse_condition(text) is None


def test_activating_a_mana_ability_would_trigger_it_too_so_the_wording_must_exclude_them(cards):
    """605.3b: mana abilities don't use the stack here, so "Whenever you activate an ability of a creature" (which a mana
    ability triggers, 602.2) is refused rather than read as the non-mana abilities only."""
    assert coverage.of_card_data(cards.resolve("Elrond, Moon-Reader")).level != "FULL"
