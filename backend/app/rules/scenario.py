"""EXPORT RULES SCENARIO: a compact, reproducible fixture of an automation problem.

A scenario holds the table just *before* the intent(s) in question, the intents themselves as
they were recorded (with their compiled steps and any shuffle/dice results), the decisions made
since, the failure if there was one, and the versions and Oracle fingerprints of every card
involved. ``replay`` turns it back into a regression check: it re-compiles the intents with the
*current* engine and reports where the outcome differs from what was recorded.

Private information that has nothing to do with the problem is redacted: cards in hidden zones
(libraries, hands …) keep their place but lose their identity unless the scenario refers to them;
the log, chat, private searches and deck-builder categories are dropped.
"""

from __future__ import annotations

import json
import time
from typing import Any

from app.game import actions as A
from app.game.state import HIDDEN_ZONES, GameState
from app.rules import cards as scripts
from app.rules.characteristics import CardInfo

SCENARIO_FORMAT = "fyodor-rules-scenario"
SCENARIO_VERSION = 1
NOT_A_TRIGGER = frozenset({"choose", "set_prefs", "set_stops", "set_card_automation"})


def _trigger_start(actions: list[A.Action], intents: int) -> int:
    """Index of the ``intents``-th last rules intent that isn't just an answer or a preference."""
    found = 0
    for i in range(len(actions) - 1, -1, -1):
        a = actions[i]
        if a.type in A.INTENT_TYPES and a.type not in NOT_A_TRIGGER or a.type == "configure" and getattr(a, "r", None):
            found += 1
            if found == intents:
                return i
    return max(0, len(actions) - 1) if actions else 0


def redact(state: GameState, keep: set[str]) -> dict[str, Any]:
    out = state.model_copy(deep=True)
    for cid, card in out.cards.items():
        card.categories = []
        zone = card.zone.rsplit(":", 1)[-1]
        if zone in HIDDEN_ZONES and cid not in keep:
            card.card_id = None
            card.name = ""
            card.note = ""
            card.token = None
            card.commander_key = card.commander_key  # (commanders are public)
    out.log = []
    out.views = []
    # (the salt stays: the ids of cards turned face down are derived from it, ops.renumber, and a replay must reproduce them; it
    # tells nothing the scenario doesn't show: its hidden cards are redacted, its face-down ones are not)
    return out.model_dump(mode="json")


def export(session: Any, info: CardInfo, *, intents: int = 1, failure: dict[str, Any] | None = None) -> dict[str, Any]:
    from app.buildinfo import build_info  # (imports the engine, which imports this package)

    history = session.history
    applied = history.actions[: history.cursor]
    start = _trigger_start(applied, max(1, intents))
    before = history.state_at(start)
    replay = [a.model_dump(mode="json") for a in applied[start:]]
    blob = json.dumps(replay) + json.dumps(failure or {})
    if before.rules is not None:
        blob += before.rules.model_dump_json()
    keep = {cid for cid in before.cards if cid in blob}
    cards: dict[str, Any] = {}
    for cid, card in before.cards.items():
        if not card.card_id or (card.zone.rsplit(":", 1)[-1] in HIDDEN_ZONES and cid not in keep):
            continue
        data = info.get(card.card_id) or {}
        oracle_id = data.get("oracle_id")
        script = scripts.get(oracle_id)
        cards[card.card_id] = {
            "name": data.get("name") or card.name, "oracle_id": oracle_id,
            "oracle_hash": scripts.oracle_hash(data.get("oracle_text")),
            "script_version": script.version if script else None,
            "script_trusted": bool(script and script.matches(data.get("oracle_text"))) if script else None,
        }
    return {
        "format": SCENARIO_FORMAT, "version": SCENARIO_VERSION, "exported_at": time.time(),
        "build": build_info(),
        "state": redact(before, keep), "actions": replay, "failure": failure, "cards": cards,
    }


def replay(scenario: dict[str, Any], info: CardInfo) -> list[str]:
    """Re-run a scenario's intents with the current engine. Returns the differences from what
    was recorded (empty: the engine still behaves the same)."""
    import random

    from app.game import engine
    from app.game.resolve import resolve

    if scenario.get("format") != SCENARIO_FORMAT:
        raise ValueError("Not a rules scenario")
    state = GameState.model_validate(scenario["state"])
    problems: list[str] = []
    for i, payload in enumerate(scenario["actions"]):
        recorded = A.parse_action(payload)
        expected = state.model_copy(deep=True)
        engine.apply(expected, recorded)
        if recorded.type in A.INTENT_TYPES or recorded.type == "configure":
            fresh = recorded.model_copy(update={"r": None})
            try:
                resolved = resolve(state, fresh, actor=recorded.actor, cards=info, rng=random.Random(i))
                engine.apply(state, resolved)
            except Exception as exc:  # noqa: BLE001 - a failure *is* the finding
                problems.append(f"action {i} ({recorded.type}): {exc}")
                state = expected
                continue
            for key in ("zones", "players", "turn"):
                if getattr(state, key) != getattr(expected, key):
                    problems.append(f"action {i} ({recorded.type}): {key} differ from the recording")
            state = expected
        else:
            state = expected
    return problems
