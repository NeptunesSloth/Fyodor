"""Wave 110E session 12: Emissary of Grudges (entry secret choice, 614.12a; retargeting, 115.7d)."""
from __future__ import annotations

import json

import pytest

import tests.test_rules_wave110e_cards as base
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import card_db  # noqa: F401  (the fixture)
from tests.test_rules_wave110e_cards import cast as cast_card
from tests.test_rules_wave110e_s11 import _three
from tests.wave9c_kit import build, card_named, check, mana, to_hand  # noqa: F401

EMISSARY = real("Emissary of Grudges", "{5}{R}", 6, "Creature — Efreet",
                "Flying, haste\nAs this creature enters, secretly choose an opponent.\nReveal the player you chose: Choose new targets for target spell or ability if it's controlled by the "
                "chosen player and if it targets you or a permanent you control. Activate only once.", ("6", "5"), "R")
base.EXTRA.append(EMISSARY)


def test_emissary_full(cards):
    assert coverage.of_card_data(cards.resolve("Emissary of Grudges")).level == "FULL"


def _table(cards, choose):
    """Alice casts Emissary of Grudges and secretly chooses ``choose``; nobody else is told."""
    s = _three(cards, ["Emissary of Grudges"])
    mana(s, R=1, C=5)
    cast_card(s, "Emissary of Grudges")
    for _ in range(3):
        d = s.state.rules.decision
        if d is not None and d.player == "p1" and "secretly" in d.prompt:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label.startswith(choose))])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    return s


def test_emissary_choice_is_secret(cards):
    s = _table(cards, "Bob")
    emissary = card_named(s, "Emissary of Grudges")
    assert emissary.zone == "p1:battlefield" and s.state.rules.secret_choices
    for viewer in ("p2", "p3"):
        seen = json.dumps(s.view(viewer))
        assert "secret_choices" not in seen and "secretly" not in json.dumps(s.view(viewer)["log"])
    check(s)


def _bolt(s, target):
    """Alice passes in her main phase; Bob (stops on) casts Test Bolt at ``target``; the others pass until Alice holds priority with it on the stack."""
    act(s, "p2", type="set_stops", own=[], others=["main1"], smart_pass=False)
    act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Test Bolt", "p2").id, targets=[target])
    for _ in range(4):
        if s.state.rules.priority == "p1":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.priority == "p1" and s.state.zones["stack"]
    return s.state.zones["stack"][-1]


def _reveal(s, bolt):
    emissary = card_named(s, "Emissary of Grudges")
    act(s, "p1", type="activate_ability", card_id=emissary.id, ability=2, targets=[bolt])
    return emissary


def _finish(s, new=None):
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[new if new in ids else ids[0]])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def _lost(s):
    return {p: 40 - s.state.players[p].life for p in ("p1", "p2", "p3")}


@pytest.mark.parametrize(("chose", "target", "new", "lost"), [
    ("Bob", "p1", "p3", {"p1": 0, "p2": 0, "p3": 3}),      # chosen player's spell targets you: new target Carol
    ("Bob", "p1", None, {"p1": 3, "p2": 0, "p3": 0}),      # ... and you may keep the target
    ("Carol", "p1", "p3", {"p1": 3, "p2": 0, "p3": 0}),    # not the chosen player's spell: no new targets
    ("Bob", "p3", "p1", {"p1": 0, "p2": 0, "p3": 3}),      # chosen player's spell, but it targets neither you nor your permanent: no new targets
])
def test_emissary_retargets_only_a_chosen_players_spell_aimed_at_you(cards, chose, target, new, lost):
    """115.7d: its controller chooses new targets; the conditions are read on resolution (608.2c); a wrong player or a spell not aimed at Alice does nothing."""
    s = _table(cards, chose)
    bolt = _bolt(s, target)
    _reveal(s, bolt)
    _finish(s, new)
    assert _lost(s) == lost
    check(s)
