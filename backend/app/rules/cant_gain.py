"""-- refused grants/replacements (wave 3R2) -- "Can't gain life" (614.17, 119.7). Researched against
the Comprehensive Rules of 2026-09-25 (data/rules/comprehensive_rules/).

* 614.17: an effect saying something can't happen isn't a replacement effect but follows similar
  rules; 614.17a: it must exist before the event; 614.17c: an event that can't happen can only be
  replaced by a self-replacement effect (614.15) — "If an opponent would gain life, that player
  loses that much life instead." (Tainted Remedy) doesn't turn a life gain that can't happen into a
  loss. The engine's life-gain replacement effects are all statics and records (none is a
  self-replacement), so a gain that can't happen is simply not an event: nothing replaces it,
  nothing triggers on it (603.2g), lifelink damage is still dealt (only its gain is lost).
* 119.7: such a player can't exchange life totals with a player who has a lower life total, and a
  cost that has them gain life can't be paid — the engine automates neither (no exchange, no
  life-gain cost), so nothing more is needed here.

Wordings: statics "Players can't gain life." (Leyline of Punishment, Rampaging Ferocidon) and "Your
opponents can't gain life." (Erebos, God of the Dead); effects "Players can't gain life this turn."
(Skullcrack), "Your opponents can't gain life this turn." (Atarka's Command), "Target player can't
gain life this turn.", and "… that player can't gain life for the rest of the game." (Stigma
Lasher). Refused: "Enchanted player can't gain life." (an Aura on a player), conditional statics.
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
Definition = dict[str, Any]

_STATIC = {"Players can't gain life.": "each", "Your opponents can't gain life.": "opponents",
           "Enchanted player can't gain life.": "enchanted"}  # (wave 25D: Grievous Wound, an Aura on a player: the player it is attached to)
_EFFECT = re.compile(r"(?P<who>players|your opponents|target player|target opponent|that player) can't gain life "
                     r"(?P<when>this turn|for the rest of the game)")


def static_definition(text: str) -> Definition | None:
    who = _STATIC.get(text.strip())
    return {"kind": "static", "static": "cant_gain_life", "who": who, "effects": []} if who else None


def _effect(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    who = {"players": "each_player", "your opponents": "each_opponent", "target player": "target", "target opponent": "target",
           "that player": "event_player"}[m["who"]]
    sel = {"target player": "player", "target opponent": "opponent"}.get(m["who"])
    return [{"do": "cant_gain_life", "who": who, "until": "turn" if m["when"] == "this turn" else "game"}], sel


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(re.compile("^" + _EFFECT.pattern + "$"), _effect)]


def cant_gain_life(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.effects import _players

    r = plan.rules
    for pid in _players(plan, ctx, e["who"]):
        r.cant_gain.append({"id": secrets.token_hex(4), "player": pid, "controller": ctx["controller"],
                            "turn": plan.state.turn.number if e.get("until") == "turn" else None,
                            "label": ctx.get("name") or "an effect"})
        when = "this turn" if e.get("until") == "turn" else "for the rest of the game"
        plan.note(f"{plan.name(pid)} can't gain life {when}", actor=ctx["controller"])
    return True


def why_not(plan: Plan, player: str) -> str | None:
    """The effect that keeps ``player`` from gaining life now (614.17), or None."""
    turn = plan.state.turn.number
    for rec in plan.rules.cant_gain:
        if rec.get("player") == player and rec.get("turn") in (None, turn) and rec.get("controller") in plan.live():
            return str(rec.get("label") or "an effect")
    from app.rules import scripts
    from app.rules.replace import conditional_lines

    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        ch = plan.ch(c)
        if "Room" in ch.subtypes:
            continue  # (a Room door is unlocked or not: not modelled)
        skip = conditional_lines(ch)  # (a leveler's / Class's level lines: the level isn't tracked)
        for i, d in scripts.definitions(ch).items():
            if i in skip or d.get("kind") != "static" or d.get("static") != "cant_gain_life":
                continue
            if d.get("who") == "each" or (d.get("who") == "opponents" and player != c.controller) \
                    or (d.get("who") == "enchanted" and c.attached_player == player):
                return ch.name or c.name or "a permanent"
    return None


PRIMITIVES = {"cant_gain_life": cant_gain_life}
