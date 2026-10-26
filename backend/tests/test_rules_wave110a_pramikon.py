"""Wave 110A: Pramikon, Sky Rampart: as it enters its controller chooses left or right (614.12a); each player may attack only the nearest opponent in that
direction and planeswalkers that opponent controls (508.1d, restriction from combat_teyo66; it ends when Pramikon leaves, 611.2b)."""

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.game_helpers import act, deck, enable
from tests.test_rules_wave30p_combat import to_phase
from tests.wave110c_kit import answer, cast, check, make_db, mana, put, real

EXTRA = [real("Pramikon, Sky Rampart", "{U}{R}{W}", 3, "Legendary Creature — Wall",
              "Flying, defender\nAs Pramikon enters, choose left or right.\nEach player may attack only the nearest opponent in the chosen direction and "
              "planeswalkers controlled by that opponent.", ("1", "5"), "URW")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Pramikon, Sky Rampart")).level == "FULL"


def _three(cards):
    mine = [(1, "Pramikon, Sky Rampart"), (1, "Grizzly Bears"), (9, "Forest")]
    setups = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", mine)), PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])),
              PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(10, "Forest")]))]
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def _attack(cards, direction, target):
    s = _three(cards)
    bears = put(s, "Grizzly Bears")
    mana(s, "p1", U=1, R=1, W=1)
    cast(s, "Pramikon, Sky Rampart")
    answer(s, direction)
    to_phase(s, "declare_attackers", 4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": target}])
    return s


@pytest.mark.parametrize(("direction", "ok", "bad"), [("left", "p2", "p3"), ("right", "p3", "p2")])
def test_only_the_nearest_opponent_that_way(cards, direction, ok, bad):
    with pytest.raises(ActionError):
        _attack(cards, direction, bad)
    s = _attack(cards, direction, ok)
    check(s)
