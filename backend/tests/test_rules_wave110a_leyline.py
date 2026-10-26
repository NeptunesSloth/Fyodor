"""Wave 110A: Leyline of Transformation, begun on the battlefield from the opening hand (CR 103.6a): "As this enchantment enters, choose
a creature type" (614.12a) is asked at the start of the game and the opening-hand actions go on afterwards. Real Oracle text."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.mulligan import COMMANDER_LONDON
from app.game.rules_state import AUTOMATION_PRESETS, start_rules
from app.game.session import GameSession
from app.game.state import GameSettings, GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, engine_pays
from tests.test_rules_effects import replay_matches


def real(name, cost, cmc, types, text, pt=None, colors=()):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=f"18C-{name[:6]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), **extra)


EXTRA = [
    real("Leyline of Transformation", "{2}{U}{U}", 4, "Enchantment",
         "If this card is in your opening hand, you may begin the game with it on the battlefield.\nAs this enchantment enters, choose a creature type.\nCreatures you control are the chosen type in addition to their other types. The same is true for creature spells you control and creature cards you own that aren't on the battlefield.", colors="U"),
    real("Chancellor of the Dross", "{4}{B}{B}{B}", 7, "Creature — Phyrexian Vampire Praetor",
         "You may reveal this card from your opening hand. If you do, at the beginning of the first upkeep, each opponent loses 3 life, then you gain life equal to the life lost this way.\nFlying, lifelink", ("6", "6"), "B"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path

def table(cards, alice, bob, *, policy=COMMANDER_LONDON):
    a = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in alice), (20, "Forest")])
    b = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (20, "Island")])
    state = new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b)], settings=GameSettings(mulligan=policy), shuffle=False)
    state.settings.automation = "full"
    state.settings.automation_options = AUTOMATION_PRESETS["full"].model_copy()
    start_rules(state)
    engine_pays(state)
    return GameSession(state, cards=cards)


def keep_all(s):
    act(s, "p1", type="mulligan_keep")
    act(s, "p2", type="mulligan_keep")


def zone_names(s, key):
    return sorted(s.state.cards[c].name for c in s.state.zones[key])


def answer(s, pid, names=()):
    d = s.state.rules.decision
    assert d is not None and d.player == pid, d
    ids = [o.id for n in names for o in d.options if o.label == n]
    act(s, pid, type="choose", decision_id=d.id, option_ids=ids)


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")



def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Leyline of Transformation")).level == "FULL"


def test_choice_at_game_start_then_rest_of_opening_hand(cards):
    s = table(cards, ["Leyline of Transformation", "Chancellor of the Dross"], ["Island"])
    keep_all(s)
    answer(s, "p1", ["Leyline of Transformation", "Chancellor of the Dross"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and "type" in d.prompt.lower()  # 614.12a: asked as it enters
    assert zone_names(s, "p1:battlefield") == []
    pick = next(o for o in d.options if o.label == "Elf")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[pick.id])
    assert zone_names(s, "p1:battlefield") == ["Leyline of Transformation"]
    d = s.state.rules.decision  # p2 is asked next (nothing to use), the Chancellor was revealed after the Leyline entered
    assert d is not None and d.player == "p2"
    answer(s, "p2", [])
    assert s.state.players["p2"].life == 37 and s.state.players["p1"].life == 43  # Chancellor's first-upkeep trigger
    roundtrip(s)
