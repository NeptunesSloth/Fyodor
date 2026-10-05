"""-- speed (wave 24B) -- "Start your engines!" and "Max speed — …" (CR 2026-09-25, 702.178, 702.179, 704.5aa).

* 702.179b: a player has no speed until a rule or effect sets it: the player resource ``speed`` is absent then (the table's
  free-form player counters: ``PlayerState.resources``, old saves have none); 702.179f: no speed reads as 0 for an effect that
  refers to it, and ``values`` reads "your speed" as the player counter ``speed`` (``{"player_counters": "speed"}``).
* 702.179a / 704.5aa: a player who controls a permanent with start your engines! and has no speed gets speed 1 (a state-based
  action: ``sba._round`` calls :func:`start_engines`).
* 702.179d: the inherent triggered ability of a player with 1 or more speed (no source): "Whenever one or more opponents lose life
  during your turn, if your speed is less than 4, your speed increases by 1. This ability triggers only once each turn." The life
  loss is the table's ``life_loss`` event; the intervening "if" is checked as it triggers and as it resolves (603.4); the once-a-turn
  limit is the same ``once_each_turn`` limit abilities use (only the active player's ability can trigger in a turn).
* 702.179c: increasing the speed of a player with none makes it that value; 702.179e / 702.178a: max speed is speed 4
  (``{"value": {"player_counters": "speed"}, "op": ">=", "n": 4}``: Gomif lets it grow further and is still at max speed).
* 702.178a: "Max speed — [Ability]" is a static ability: "As long as your speed is 4, this object has '[Ability]'": the wording
  is rewritten that way (:func:`rewrite`) and read by the grant / "as long as" grammar the engine has.

Refused (manual): speed changes other than the inherent increase ("reduce that opponent's speed", Gomif's "can increase beyond 4",
"Pay X speed"), a max speed ability of a card in a zone other than the battlefield (702.178b).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.rules_state import Event
    from app.rules.plan import Plan

Context = dict[str, Any]
MAX = 4  # 702.179e
KEY = "speed"
INDEX = 90  # (the inherent ability's index in the once-each-turn record: no source object)
_HAS = {"all": [{"value": {"player_counters": KEY}, "op": ">=", "n": 1}, {"value": {"player_counters": KEY}, "op": "<=", "n": MAX - 1}]}


def of(plan: Plan, pid: str) -> int:
    """702.179f: a player with no speed has speed 0 for an effect that refers to it."""
    return max(0, int(plan.state.players[pid].resources.get(KEY, 0)))


def has(plan: Plan, pid: str) -> bool:
    return KEY in plan.state.players[pid].resources


def start_engines(plan: Plan) -> bool:
    """704.5aa: a player who controls a permanent with start your engines! and has no speed gets speed 1."""
    happened = False
    for pid in plan.live():
        if has(plan, pid) or not any(
                c.controller == pid and c.zone.endswith(":battlefield") and not plan.manual(c) and plan.in_game(c)
                and "start your engines!" in plan.ch(c).keywords for c in plan.state.cards.values()):
            continue
        plan.do({"type": "set_resource", "player": pid, "key": KEY, "value": 1}, actor=pid)
        happened = True
    return happened


def on_events(plan: Plan, events: list[Event]) -> None:
    """702.179d: one or more opponents lost life during the active player's turn."""
    from app.rules import designations

    ap = plan.active
    if ap not in plan.live() or not has(plan, ap):
        return
    for e in events:
        if e.kind == "life_loss" and not e.manual and e.player and e.player != ap and e.player in plan.live() and e.amount > 0:
            designations._add_trigger(plan, ap, "Speed", [{"do": "speed", "n": 1}], index=INDEX,
                                      extra={"if": _HAS, "limit": "once_each_turn"})
            return  # (one trigger a turn: the limit also stops a later event's)


def increase(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.179c: "your speed increases by N": a player with no speed gets speed N."""
    pid = ctx["controller"]
    if pid in plan.live():
        plan.do({"type": "set_resource", "player": pid, "key": KEY, "value": of(plan, pid) + int(e["n"])}, actor=pid)
    return True


# 702.178a: "Max speed — [Ability]" → "As long as you have max speed, ~ has "[Ability]"" (a triggered or activated ability) / "As long as you
# have max speed, [static ability]". 702.178b: an ability that works from another zone (a graveyard) is one the grant would never give
# from the battlefield: refused, the line stays as printed (unsupported).
_WORD = re.compile(r"^max speed — (?P<rest>.+)$", re.IGNORECASE | re.DOTALL)
_ABILITY = re.compile(r"^(?:whenever |when |at the beginning of |[^.:\"]{1,80}: )", re.IGNORECASE)
_OTHER_ZONE = re.compile(r"\bfrom (?:your|a|their) (?:graveyard|hand|library|exile)\b|\bthis card\b", re.IGNORECASE)


def rewrite(text: str) -> str:
    m = _WORD.match(text)
    if m is None:
        return text
    rest = m["rest"].strip()
    if _OTHER_ZONE.search(rest):
        # 702.178b: the granted ability works from the zone it states: an activated ability of a card in a graveyard is "[cost]: [effect]. Activate only
        # if you have max speed." (the ability exists exactly while the speed is 4: the same moments it can be activated)
        return f"{rest} Activate only if you have max speed." if re.match(r"^[^.:\"]{1,80}: ", rest) and rest.endswith(".") and not rest.startswith(("When", "At ")) else text
    if _ABILITY.match(rest):
        return f'As long as you have max speed, ~ has "{rest}"'
    return f"As long as you have max speed, {rest[:1].lower()}{rest[1:]}"


PRIMITIVES = {"speed": increase}
