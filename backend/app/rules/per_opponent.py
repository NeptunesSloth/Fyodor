"""-- per-opponent targets (wave 12C) -- "When this creature enters, for each opponent, exile up to one target creature that
player controls." (Haytham Kenway, Grasp of Fate, Enigma Thief). The ability has one target group per opponent in the game as
it is put on the stack (115.1, 603.3d, 601.2c: each "target" word is its own group; "that player controls" names the opponent
the group belongs to) and the one instruction is carried out once per group.

Parsed once as the single-opponent clause ("… up to one target creature an opponent controls": one flagged group); expanded
when the trigger is put (``expand``): every live opponent gets its own copy of the group, narrowed to that player's
permanents, and of the effects, aimed at that group. Only a triggered ability's own clause is read (scripts.define refuses
the flag anywhere else: a reflexive or delayed ability puts its targets elsewhere), and nothing else may name "that player"."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.rules import selectors

if TYPE_CHECKING:
    from app.game.rules_state import PendingTrigger
    from app.rules.plan import Plan

FLAG = "opponent_group"
_FOR_EACH = re.compile(r"^(?P<pre>.*?\. )?[Ff]or each (?P<who>opponent|player), (?P<rest>.+?)\.?$", re.S)  # (-- per-player targets (wave 50F) -- "For each player" (Nils, Battle at the Helvault); a sentence before it (Tasha: "Draw a card.") happens once)
_THOSE = re.compile(r"\b(?:[Ee]ach of )?[Tt]hose (?:creatures|permanents)\b")  # (the one chosen for this opponent: the copy's "it")
_THAT_PLAYER = re.compile(r"\bthat (?:player|opponent) controls\b")
_THAT_YARD = re.compile(r"\bthat (?:player|opponent)'s graveyard\b")  # (-- per-opponent targets (wave 50F) -- Tasha, Sepulchral Primordial: a card from that opponent's graveyard)
Parsed = tuple[list[dict[str, Any]], Any, bool]


def parse(body: str, read: Callable[[str], Parsed | None]) -> Parsed | None:
    m = _FOR_EACH.match(body.strip())
    if m is None:
        return None
    rest = _THOSE.sub("it", _THAT_YARD.sub("an opponent's graveyard", _THAT_PLAYER.sub("an opponent controls", m["rest"])).replace(". They gain ", ". It gains "))
    if re.search(r"\b(?:that (?:player|opponent)|they|them|their)\b", rest.replace("its controller cloaks the top card of their library", "")):  # (-- if you do (wave 52A) -- Unexplained Absence: "their" is that controller's, not the opponent of the group)
        return None  # (another reference to the opponent: not read)
    found = read(rest + ".")
    if found is None:
        return None
    groups = [{"what": found[1], "min": 1, "max": 1}] if isinstance(found[1], str) else found[1]  # (one plain "target …")
    if not isinstance(groups, list) or len(groups) != 1:
        return None
    group = groups[0]
    sel = selectors.from_key(group["what"]) if str(group.get("what", "")).startswith(selectors.PREFIX) else None
    if sel is None or (sel.controller != "opponent" and not (sel.zone_owner == "opponent" and sel.controller is None)) or group["max"] != 1 or group["min"] > 1 or set(group) - {"what", "min", "max"}:
        return None
    before: list[dict[str, Any]] = []
    if m["pre"]:  # (once, not per opponent: an untargeted sentence of no choice and no payment of its own)
        pre = read(m["pre"].strip())
        if pre is None or pre[1] is not None or pre[2] or re.search(r'"(?:target|optional|bind|skip)', json.dumps(pre[0], default=str)):
            return None
        before = pre[0]
    return before + found[0], [{**group, FLAG: True if m["who"] == "opponent" else m["who"], **({"from": len(before)} if before else {})}], found[2]


def flagged(definition: dict[str, Any]) -> bool:
    return any(g.get(FLAG) for g in definition.get("targets") or [])


def allowed(definition: dict[str, Any]) -> bool:
    """The flag only on a triggered ability's, an activated ability's or a spell's own single target group (see the module
    docstring; a spell or ability is expanded as it is put on the stack, 601.2c)."""
    raw = json.dumps(definition, default=str)
    # (-- if you do (wave 50F) -- "you may exile it. When you do, for each opponent, …" (The Balrog of Moria): 603.12 the reflexive ability is put on the stack, and
    # expanded, like any trigger — the flag is its own single group)
    return FLAG not in raw or (definition.get("kind") in ("triggered", "activated", "spell") and flagged(definition)
                               and raw.count(f'"{FLAG}"') == len(definition["targets"]) == 1) \
        or (raw.count(f'"{FLAG}"') == 1 and any(e.get("do") == "reflexive" and allowed(e["ability"]) for e in definition.get("effects") or []))


def expand(plan: Plan, t: PendingTrigger) -> None:
    """A pending trigger with a flagged group gets one group (and one copy of the effects) per live opponent of its
    controller, in turn order from the controller; a required target no opponent's permanents offer drops that opponent."""
    t.ability = expanded(plan, t.controller, t.source_card, t.ability)


def for_cast(plan: Plan, source_card: str | None, definition: dict[str, Any] | None) -> dict[str, Any] | None:
    """-- per-opponent targets (wave 23A) -- the same for a spell or activated ability about to be put on the stack by the
    acting player (601.2c: a group of targets for each opponent, chosen as it is cast)."""
    return definition if definition is None else expanded(plan, plan.actor, source_card, definition)


def expanded(plan: Plan, controller: str, source_card: str | None, ab: dict[str, Any]) -> dict[str, Any]:
    from app.rules.scripts import _renumber
    from app.rules.targets import legal_targets
    from app.rules.triggers import source_of

    if not flagged(ab):
        return ab
    group = ab["targets"][0]
    order = plan.state.seat_order
    start = order.index(controller) if controller in order else 0
    opponents = [p for i in range(len(order)) if (p := order[(start + i) % len(order)]) in plan.live() and (p != controller or group[FLAG] == "player")]
    sel = selectors.from_key(group["what"])
    first = group.get("from", 0)  # (-- per-player targets (wave 50F) -- the sentences before the "For each …" one are carried out once)
    groups: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []
    for p in opponents:
        key = (replace(sel, zone_owner=f"player:{p}") if sel.zone_owner == "opponent" else replace(sel, controller=f"player:{p}")).key()
        if group["min"] and not legal_targets(plan, key, controller, source_of(plan, source_card, ab.get("kind") == "spell"), source_card):
            continue
        effects += _renumber([e for e in ab["effects"][first:] if not e.get("opponent_aggregate")], [len(groups)])
        groups.append({k: v for k, v in group.items() if k not in (FLAG, "from")} | {"what": key})
    aggregate = [{k: v for k, v in e.items() if k != "opponent_aggregate"} for e in ab["effects"][first:] if e.get("opponent_aggregate")]
    return {**ab, "effects": [*ab["effects"][:first], *effects, *aggregate], "targets": groups}
