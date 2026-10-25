"""Nettling Imp / Norritt (wave 110E): "{T}: Choose target non-Wall creature the active player has controlled continuously since the beginning of the turn.
That creature attacks this turn if able. Destroy it at the beginning of the next end step if it didn't attack this turn. Activate only [during an opponent's
turn, ]before attackers are declared."

508.1d / 508.1a: the requirement is the existing must_attack restriction; 603.7 the end-step destroy is a delayed trigger of the same target and its "if" is
checked as it resolves (history "attacked": declared as an attacker this turn, 508.1). The target is a non-Wall creature the active player (not necessarily the
controller) has controlled since the turn began (302.6 style continuous control: selectors controlled_since_turn_start69)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

_HEAD = ("{T}: Choose target non-Wall creature the active player has controlled continuously since the beginning of the turn. That creature attacks this turn if able. "
         "Destroy it at the beginning of the next end step if it didn't attack this turn. Activate only ")
_TAILS = {"during an opponent's turn, before attackers are declared.": True, "before attackers are declared.": False}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors
    from app.rules.controller_turn_history69 import EXTRA

    text = ability.text.strip()
    if not text.startswith(_HEAD) or text[len(_HEAD):] not in _TAILS:
        return None
    opponents_only = _TAILS[text[len(_HEAD):]]
    base = scripts.define(replace(ability, text="{T}: Target non-Wall creature attacks this turn if able. Activate only before attackers are declared."), ch)
    kill = scripts.parse_effects("Target creature attacks this turn if able. At the beginning of the next end step, destroy it.")
    if base is None or kill is None or len(kill[0]) != 3:
        return None
    sel = selectors.from_key(base["target"]["what"])
    sel = replace(sel, controller="active", extras=(*sel.extras, EXTRA))
    delayed = {**kill[0][1], "n": 2}  # 603.4: the "if" is checked again as the delayed trigger resolves
    effects = [*base["effects"], delayed, {"do": "deferred:didnt_attack110e", "who": "target"}, kill[0][2]]
    restriction = [*base["restriction"], *([{"kind": "opponents_turn"}] if opponents_only else [])]
    return {**base, "effects": effects, "restriction": restriction, "target": {**base["target"], "what": sel.key()}}


def didnt_attack(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The delayed trigger's intervening "if it didn't attack this turn" (603.4): the next effect happens only then. ``who`` is the target, bound as the trigger was
    created (delayed._bind_now), so it is the very object that was chosen (400.7: a creature that left and came back is not it)."""
    from app.rules import conditions

    if not conditions.holds(plan, ctx, {"history": "object", "object": e["who"], "what": "attacked", "negate": True}):
        ctx["next"] += 1
    return True


PRIMITIVES = {"didnt_attack110e": didnt_attack}
