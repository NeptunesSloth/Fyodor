"""Wave 23A: "For each opponent, … target … that player controls" on spells and activated abilities (CR 115.1, 601.2c, 603.3d).

The ability has one group of targets for each opponent in the game as it is put on the stack, chosen as it is cast (601.2c); the one
instruction is carried out once for each group (Blatant Thievery, Mass Mutiny, The Theorist). A required group no opponent's
permanents offer drops that opponent. Real Oracle text; each scenario replays and survives a save."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import creature, pick, settle, to_hand, until_asked
from tests.test_rules_effects import mana, replay_matches


def real(name, cost, cmc, types, text, colors=(), loyalty=None):
    extra = {"loyalty": str(loyalty)} if loyalty is not None else {}
    return card(name, set_code="tst", number=f"23A-{name[:7]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), **extra)


EXTRA = [
    real("Blatant Thievery", "{4}{U}{U}{U}", 7, "Sorcery", "For each opponent, gain control of target permanent that player controls.", "U"),
    real("Mass Mutiny", "{4}{R}{R}", 6, "Sorcery",
         "For each opponent, gain control of up to one target creature that player controls until end of turn. Untap those creatures. They gain haste until end of turn.", "R"),
    real("The Theorist, Jace Beleren", "{2}{U}{U}", 4, "Legendary Planeswalker — Jace",
         "+1: Each player draws a card.\n−2: For each opponent, return up to one target artifact or creature that player controls to its owner's hand.\n−8: Exile all cards from all graveyards.",
         "U", 5),
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


def cast(s, name, **pool):
    c = to_hand(s, name)
    mana(s, "p1", **pool)
    act(s, "p1", type="cast_spell", card_id=c.id)
    return c


def controller(s, c):
    return s.state.cards[c.id].controller


@pytest.mark.parametrize("name", [e["name"] for e in EXTRA])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_blatant_thievery_one_target_for_each_opponent(cards):
    s = build3(cards, "Blatant Thievery")
    bear = creature(s, "p2", "Bear")
    wolf = creature(s, "p3", "Wolf")
    creature(s, "p3", "Fox")  # (Carol has two to choose from)
    cast(s, "Blatant Thievery", U=3, C=4)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and {o.id for o in d.options} == {bear.id}  # Bob's group first (turn order)
    roundtrip(s)  # (a save with the choice pending)
    pick(s, bear.id)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and len(d.options) == 2 and wolf.id in {o.id for o in d.options}
    pick(s, wolf.id)
    settle(s)
    assert controller(s, bear) == "p1" and controller(s, wolf) == "p1"
    roundtrip(s)


def test_blatant_thievery_an_opponent_with_nothing_to_take_has_no_group(cards):
    s = build3(cards, "Blatant Thievery")
    wolf = creature(s, "p3", "Wolf")  # Bob controls no permanent at all
    cast(s, "Blatant Thievery", U=3, C=4)
    d = until_asked(s)
    assert d is not None and {o.id for o in d.options} == {wolf.id}  # only Carol's group is asked
    pick(s, wolf.id)
    settle(s)
    assert controller(s, wolf) == "p1"
    roundtrip(s)


def test_mass_mutiny_up_to_one_creature_for_each_opponent_until_end_of_turn(cards):
    s = build3(cards, "Mass Mutiny")
    bear = creature(s, "p2", "Bear")
    wolf = creature(s, "p3", "Wolf")
    cast(s, "Mass Mutiny", R=2, C=4)
    d = until_asked(s)
    assert d is not None and d.min_choices == 0 and d.max_choices == 1  # "up to one"
    pick(s, bear.id)
    pick(s, wolf.id)
    settle(s)
    assert controller(s, bear) == "p1" and controller(s, wolf) == "p1"
    roundtrip(s)


def test_the_theorist_returns_one_of_each_opponents_permanents(cards):
    s = build3(cards, "The Theorist, Jace Beleren")
    bear = creature(s, "p2", "Bear")
    wolf = creature(s, "p3", "Wolf")
    walker = cast(s, "The Theorist, Jace Beleren", U=2, C=2)
    settle(s)
    assert s.state.cards[walker.id].zone == "p1:battlefield"
    act(s, "p1", type="activate_ability", card_id=walker.id, ability=1)
    d = until_asked(s)
    assert d is not None and {o.id for o in d.options} == {bear.id}
    pick(s, bear.id)
    pick(s, wolf.id)
    settle(s)
    # (tokens that return to a hand cease to exist: neither is on the battlefield any more)
    assert bear.id not in s.state.cards or s.state.cards[bear.id].zone != "p2:battlefield"
    assert wolf.id not in s.state.cards or s.state.cards[wolf.id].zone != "p3:battlefield"
    roundtrip(s)
