"""Wave 23A: faces a villainous choice (CR 701.55a-d, 101.4b).

The Dalek Emperor: "At the beginning of combat on your turn, each opponent faces a villainous choice — That player sacrifices a creature of
their choice, or you create a 3/3 black Dalek artifact creature token with menace." Each opponent in APNAP order, one at a time: the
chosen option is carried out before the next opponent chooses (701.55d). Real Oracle text; replay and save/load round trips."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_conditionals import creature, on_field, pick, until_asked
from tests.test_rules_effects import replay_matches

EXTRA = [
    card("The Dalek Emperor", set_code="tst", number="23A-DE", mana_cost="{5}{B}{R}", cmc=7.0, type_line="Legendary Artifact Creature — Dalek",
         oracle_text="Affinity for Daleks (This spell costs {1} less to cast for each Dalek you control.)\nOther Daleks you control have haste.\nAt the beginning of combat on your turn, each opponent faces a villainous choice — That player sacrifices a creature of their choice, or you create a 3/3 black Dalek artifact creature token with menace.",
         power="6", toughness="6", colors=["B", "R"], color_identity=["B", "R"], keywords=["Affinity"]),
    card("Damocles Base, Sword of Kang", set_code="tst", number="23A-DB", mana_cost="{4}{B}", cmc=5.0, type_line="Legendary Artifact — Vehicle",
         oracle_text="Flying, deathtouch\nWhenever Damocles Base deals combat damage to a player, that player faces a villainous choice — They sacrifice a nontoken creature of their choice, or they lose 2 life and you draw two cards.\nCrew 3",
         power="5", toughness="5", colors=["B"], color_identity=["B"], keywords=["Deathtouch", "Flying", "Crew"]),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build3(cards, *mine):
    a = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (12, "Forest")])
    b = deck(cards, "Atraxa, Praetors' Voice", [(13, "Island")])
    c = deck(cards, "Krenko, Mob Boss", [(13, "Mountain")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b), PlayerSetup("Carol", cards=c)],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def names(s, pid):
    return sorted(s.state.cards[c].name for c in zone(s.state, pid, "battlefield"))


@pytest.mark.parametrize("name", [e["name"] for e in EXTRA])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_wording_is_two_options_for_the_one_who_faces_them():
    found = scripts.parse_effects("Each opponent faces a villainous choice — That player sacrifices a creature of their choice, or you create a 3/3 black Dalek artifact creature token with menace.")
    assert found is not None and found[0][0]["do"] == "villain" and found[0][0]["who"] == "each_opponent"
    # an option naming a target or a chaos effect isn't read; "you may <one instruction>" is that instruction made optional (wave 110B, Dr. Eggman)
    optional = scripts.parse_effects("Each opponent faces a villainous choice — That player discards a card, or you may draw a card.")
    assert optional is not None and optional[0][0]["b"][0]["optional"] is True
    assert scripts.parse_effects("Each opponent faces a villainous choice — That player discards a card, or you may draw a card and gain 1 life.") is None
    assert scripts.parse_effects("Each opponent faces a villainous choice — That player discards a card, or you draw a card and chaos ensues.") is None


def test_each_opponent_chooses_in_turn_order_one_at_a_time(cards):
    s = build3(cards, "The Dalek Emperor")
    on_field(s, "The Dalek Emperor")
    bear = creature(s, "p2", "Bear")
    wolf = creature(s, "p3", "Wolf")
    act(s, "p1", type="pass_priority")  # → beginning of combat: the trigger
    d = until_asked(s)
    assert d is not None and d.player == "p2" and [o.id for o in d.options] == ["a", "b"]
    assert "options" not in s.view("p1")["rules"]["decision"]  # (only the chooser is asked)
    roundtrip(s)  # a save with the choice pending
    pick(s, "a")  # Bob sacrifices (the Bear token: it ceases to exist) …
    assert bear.id not in s.state.cards or s.state.cards[bear.id].zone != "p2:battlefield"
    d = s.state.rules.decision
    assert d is not None and d.player == "p3"  # … before Carol chooses
    pick(s, "b")  # Carol lets Alice have a Dalek instead
    assert s.state.rules.decision is None or s.state.rules.decision.kind == "declare_attackers"
    assert names(s, "p1").count("Dalek") == 1 and names(s, "p3") == ["Wolf"]
    assert s.state.cards[wolf.id].zone == "p3:battlefield"
    roundtrip(s)


def test_an_impossible_option_does_as_much_as_possible(cards):
    # 701.55b: Bob has no creature but may still choose to sacrifice one: nothing happens
    s = build3(cards, "The Dalek Emperor")
    on_field(s, "The Dalek Emperor")
    act(s, "p1", type="pass_priority")
    d = until_asked(s)
    assert d is not None and d.player == "p2"
    pick(s, "a")
    pick(s, "a")
    assert s.state.rules.decision is None or s.state.rules.decision.kind == "declare_attackers"
    assert names(s, "p1") == ["The Dalek Emperor"]
    roundtrip(s)


@pytest.mark.parametrize("option", ["a", "b"])
def test_damocles_base_the_damaged_player_faces_the_choice(cards, option):
    s = build3(cards, "Damocles Base, Sword of Kang")
    base = on_field(s, "Damocles Base, Sword of Kang")
    pilot = creature(s, "p1", "Pilot", "3/3")
    creature(s, "p2", "Keeper", "2/2")  # (a token: there is no nontoken creature for option a to sacrifice)
    s.state.rules.controlled_since[base.id].turn = 0
    s.state.rules.controlled_since[pilot.id].turn = 0
    act(s, "p1", type="activate_ability", card_id=base.id, ability=2, crew=[pilot.id])
    for _ in range(6):
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.kind == "declare_attackers"
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": base.id, "target": "p2"}])
    act(s, "p2", type="declare_blockers", blocks=[])
    d = until_asked(s)
    assert d is not None and d.player == "p2" and d.kind == "choose_one"  # Bob, not Carol, faces it
    pick(s, option)
    if option == "b":
        assert s.state.players["p2"].life == 40 - 5 - 2
    roundtrip(s)
