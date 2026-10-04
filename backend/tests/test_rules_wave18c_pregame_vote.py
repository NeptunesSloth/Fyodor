"""Wave 18C: opening-hand actions (CR 103.6) and voting (CR 701.38).

Opening hand: after the mulligans every player, the starting player first and then in turn order, is asked which of the cards in
their hand to use: "begin the game with it on the battlefield" (the Leylines, Quicksilver, Gemstone Caverns for a player who is
not the starting player) or "reveal this card from your opening hand" (the Chancellors, Sphinx of Foresight), whose delayed
trigger is the revealer's (603.7a). A revealed card stays revealed until the first turn begins (103.6b).

Real Oracle text; each scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

import json

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.mulligan import COMMANDER_LONDON
from app.game.rules_state import AUTOMATION_PRESETS, start_rules
from app.game.session import GameSession
from app.game.state import GameSettings, GameState
from app.game.visibility import SPECTATOR
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, engine_pays
from tests.test_rules_effects import replay_matches


def real(name, cost, cmc, types, text, pt=None, colors=()):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=f"18C-{name[:6]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), **extra)


EXTRA = [
    real("Leyline of Sanctity", "{2}{W}{W}", 4, "Enchantment",
         "If this card is in your opening hand, you may begin the game with it on the battlefield.\nYou have hexproof. (You can't be the target of spells or abilities your opponents control.)", colors="W"),
    real("Chancellor of the Dross", "{4}{B}{B}{B}", 7, "Creature — Phyrexian Vampire",
         "You may reveal this card from your opening hand. If you do, at the beginning of the first upkeep, each opponent loses 3 life, then you gain life equal to the life lost this way.\nFlying, lifelink", ("6", "6"), "B"),
    real("Sphinx of Foresight", "{3}{U}{U}", 5, "Creature — Sphinx",
         "You may reveal this card from your opening hand. If you do, scry 3 at the beginning of your first upkeep.\nFlying\nAt the beginning of your upkeep, scry 1.", ("4", "4"), "U"),
    real("Gemstone Caverns", "", 0, "Legendary Land",
         "If this card is in your opening hand and you're not the starting player, you may begin the game with Gemstone Caverns on the battlefield with a luck counter on it. If you do, exile a card from your hand.\n{T}: Add {C}. If Gemstone Caverns has a luck counter on it, instead add one mana of any color."),
    real("Chancellor of the Tangle", "{4}{G}{G}{G}", 7, "Creature — Phyrexian Treefolk",
         "You may reveal this card from your opening hand. If you do, at the beginning of your first main phase of the game, add {G}.\nReach, vigilance", ("6", "7"), "G"),
]
NAMES = [c["name"] for c in EXTRA]


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


def test_leyline_and_chancellor_in_turn_order_with_private_hands(cards):
    s = table(cards, ["Leyline of Sanctity", "Chancellor of the Dross"], ["Gemstone Caverns", "Sphinx of Foresight"])
    keep_all(s)
    d = s.state.rules.decision
    assert d.player == "p1" and s.state.pregame.finished  # 103.6: the starting player first
    # nobody else learns anything from the pending decision (option labels, the prompt's wording, the hand)
    for viewer in ("p2", SPECTATOR):
        view = json.dumps(s.view(viewer))
        assert "Leyline of Sanctity" not in view and "Chancellor of the Dross" not in view
    mine = s.view("p1")["rules"]["decision"]
    assert sorted(o["label"] for o in mine["options"]) == ["Chancellor of the Dross", "Leyline of Sanctity"]
    answer(s, "p1", ["Chancellor of the Dross", "Leyline of Sanctity"])
    assert zone_names(s, "p1:battlefield") == ["Leyline of Sanctity"]  # 103.6a
    d = s.state.rules.decision
    assert d.player == "p2"
    # Chancellor stays in hand, revealed until the opponents' decisions are done (103.6b); the Leyline is on the table
    seen = json.dumps(s.view("p2")["log"])
    assert "revealed" in seen and "Chancellor of the Dross" in seen
    p2_view_cards = {c["name"] for c in s.view("p2")["cards"].values() if c.get("name")}
    assert "Chancellor of the Dross" in p2_view_cards
    # Bob (not the starting player) begins with Gemstone Caverns, exiling a card from hand, and reveals Sphinx of Foresight
    answer(s, "p2", ["Gemstone Caverns", "Sphinx of Foresight"])
    d = s.state.rules.decision
    assert d.player == "p2" and d.prompt == "Exile a card from your hand"
    hand_before = len(s.state.zones["p2:hand"])
    pick = next(o for o in d.options if o.label == "Island")
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[pick.id])
    assert len(s.state.zones["p2:hand"]) == hand_before - 1 and zone_names(s, "p2:exile") == ["Island"]
    assert s.state.cards[next(c for c in s.state.zones["p2:battlefield"])].counters == {"luck": 1}
    assert s.state.rules.decision is None and s.state.rules.priority == "p1"
    assert s.state.rules.opening_revealed == []
    p2_after = {c["name"] for c in s.view("p1")["cards"].values() if c.get("name")}
    assert "Sphinx of Foresight" not in p2_after  # hidden again once the first turn begins
    # the first upkeep: Alice's Chancellor triggered for the whole table (Bob's Sphinx waits for Bob's own first upkeep)
    assert s.state.players["p1"].life == 43 and s.state.players["p2"].life == 37
    assert [t.name for t in s.state.rules.delayed] == ["Sphinx of Foresight"]
    roundtrip(s)


def test_nothing_to_use_still_asks_everyone(cards):
    s = table(cards, [], [])
    keep_all(s)
    assert s.state.rules.decision.player == "p1"
    assert s.view("p1")["rules"]["decision"]["options"] == []
    answer(s, "p1")
    assert s.state.rules.decision.player == "p2"
    answer(s, "p2")
    assert s.state.rules.decision is None and s.state.rules.priority == "p1"
    roundtrip(s)


def test_gemstone_caverns_not_for_the_starting_player(cards):
    s = table(cards, ["Gemstone Caverns"], [])
    keep_all(s)
    assert s.view("p1")["rules"]["decision"]["options"] == []  # 103.6: only a player who is not the starting player


def test_gemstone_caverns_mana_is_any_color_with_a_luck_counter(cards):
    s = table(cards, [], ["Gemstone Caverns"])
    keep_all(s)
    answer(s, "p1")
    answer(s, "p2", ["Gemstone Caverns"])
    d = s.state.rules.decision
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    from app.rules import casting
    from app.rules import mana as M

    caverns = next(iter(s.state.zones["p2:battlefield"]))
    ab = M.parse_mana_ability("{T}: Add {C}. If Gemstone Caverns has a luck counter on it, instead add one mana of any color.")
    assert ab is not None and ab.instead == tuple((c,) for c in "WUBRG")
    assert casting._resolve_options(s.state, s.state.cards[caverns], ab, s.cards) == ab.instead
    s.state.cards[caverns].counters.clear()
    assert casting._resolve_options(s.state, s.state.cards[caverns], ab, s.cards) == ab.options


def test_chancellor_of_the_tangle_adds_mana_in_their_first_main_phase(cards):
    s = table(cards, ["Chancellor of the Tangle"], [])
    keep_all(s)
    answer(s, "p1", ["Chancellor of the Tangle"])
    answer(s, "p2")
    for _ in range(3):
        if s.state.turn.phase != "main1":
            act(s, s.state.rules.priority, type="pass_priority")
    for _ in range(3):
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.turn.phase == "main1" and s.state.players["p1"].mana.get("G") == 1
    assert s.state.rules.delayed == []
    roundtrip(s)
