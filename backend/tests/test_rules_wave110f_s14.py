"""Wave 110F session 14, on real Oracle text. Every scenario checks the replay and a save and a load.

* 607.2p, 604.3, 113.6a: "If ~ is your commander, choose a color before the game begins. ~ is the chosen color." (Faceless One, The Prismatic Piper): the
  choice is asked after the mulligans, the card is that color in every zone and keeps it when it changes zones; 903.4: the color joins the commander identity.
"""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.mulligan import COMMANDER_LONDON
from app.game.rules_state import AUTOMATION_PRESETS, start_rules
from app.game.session import GameSession
from app.game.state import GameSettings
from app.rules import casting, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act, deck, engine_pays
from tests.test_rules_wave12a_counters_keywords import real as _real
from tests.test_rules_wave18c_pregame_vote import keep_all, roundtrip


def real(name, cost, cmc, types, text, pt=None, colors=()):
    return _real(name, cost, cmc, types, text, pt, colors)


EXTRA = [
    real("Faceless One", "{5}", 5, "Legendary Enchantment Creature — Background",
         "If Faceless One is your commander, choose a color before the game begins. Faceless One is the chosen color.\nChoose a Background (You can have a Background as a second commander.)",
         ("3", "3")),
    real("The Prismatic Piper", "{5}", 5, "Legendary Creature — Shapeshifter",
         "If The Prismatic Piper is your commander, choose a color before the game begins. The Prismatic Piper is the chosen color.\nPartner (You can have two commanders if both have partner.)",
         ("3", "3")),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def table(cards, alice, bob):
    a = deck(cards, alice, [(20, "Forest")])
    b = deck(cards, bob, [(20, "Island")])
    state = new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b)], settings=GameSettings(mulligan=COMMANDER_LONDON), shuffle=False)
    state.settings.automation = "full"
    state.settings.automation_options = AUTOMATION_PRESETS["full"].model_copy()
    start_rules(state)
    engine_pays(state)
    return GameSession(state, cards=cards)


def pick(s, pid, letter):
    d = s.state.rules.decision
    assert d is not None and d.player == pid and d.resume["step"] == "cmd_color110f", d
    act(s, pid, type="choose", decision_id=d.id, option_ids=[letter])


def colors(s, pid):
    c = next(c for c in s.state.cards.values() if c.owner == pid and c.commander_key)
    return set(Plan(s.state, pid, s.cards, None).ch(c).colors), c


def test_each_commander_gets_its_chosen_color_in_every_zone(cards):
    s = table(cards, "Faceless One", "The Prismatic Piper")
    keep_all(s)
    pick(s, "p1", "U")  # the starting player's, then the other's, then the opening-hand questions (103.6)
    assert colors(s, "p1")[0] == {"U"}
    pick(s, "p2", "R")
    assert colors(s, "p2")[0] == {"R"}
    d = s.state.rules.decision
    assert d.player == "p1" and d.resume["step"] == "opening_hand"
    info = Plan(s.state, "p1", s.cards, None).info
    assert casting.commander_identity(s.state, "p1", info) == ("U",) and casting.commander_identity(s.state, "p2", info) == ("R",)
    roundtrip(s)


def test_the_color_stays_when_the_commander_changes_zones(cards):
    s = table(cards, "Faceless One", "The Prismatic Piper")
    keep_all(s)
    pick(s, "p1", "G")
    pick(s, "p2", "W")
    c = colors(s, "p1")[1]
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    assert colors(s, "p1")[0] == {"G"}  # 607.2p: still the choice, 604.3: in the hand too
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    assert colors(s, "p1")[0] == {"G"}
    roundtrip(s)
