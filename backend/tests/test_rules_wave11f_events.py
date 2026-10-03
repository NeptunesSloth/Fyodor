"""Wave 11F: event triggers - "a source deals damage" (120.3, 603.2), "activates an ability" (602.2) - and intervening-if
conditions (603.4). Each scenario uses real Oracle text and checks the replay and a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.state import GameState
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import counters, life, settle
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
