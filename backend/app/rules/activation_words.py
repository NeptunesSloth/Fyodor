"""-- activation wordings (wave 7B) -- what an activated ability's own text may say beyond its cost and effect.

* "Any player may activate this ability." (Flailing Soldier, Lethal Vapors, Excavation): 602.2 lets an object say that
  someone other than its controller may activate its ability; 602.2a makes the player who activated it the ability's
  controller, so "you" in the effect (and the cost's payments) are that player's. The activation costs read here are
  mana, a sacrifice or discard the activator pays from their own permanents — never {T} or "sacrifice this", which only
  the permanent's controller can pay (302.6, 118.3).
* "Activate only if …" conditions about the source ("~ is attacking / is blocked / is a creature / doesn't have
  defender", "~'s power is 4 or greater" — read from the source as it is now, 608.2h), about the player ("you have at
  least 10 life more than your starting life total", 103.4; "you have more cards in hand than each opponent"; "you
  control three or more lands with the same name", 201.2) and "… entered this turn or if you control a basic land".
* Steps: "before the combat damage step", "during combat after blockers are declared", "before the end of combat step"
  (500.1, 506.1).

A wording not read here stays manual (restrictions.parse returns None).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

ANY_PLAYER = "Any player may activate this ability."

_COMBAT_STATES = ("attacking", "blocked", "blocking")
_SELF_COMBAT = re.compile(r"~ is (?P<a>attacking|blocked|blocking)(?: or (?P<b>attacking|blocked|blocking))?")
_LIFE_ABOVE = re.compile(r"you have at least (?P<n>\w+) life more than your starting life total")
_SAME_NAME = re.compile(r"you control (?P<n>\w+) or more (?P<what>lands|creatures|artifacts|permanents) with the same name")
_NO_DEFENDER = re.compile(r"~ doesn't have (?P<kw>defender)")


def any_player(ability: Any, cost: Any) -> bool:
    """Does this activated ability say any player may activate it (and cost nothing only its controller can pay)?"""
    return ability.kind == "activated" and ability.text.rstrip().endswith(ANY_PLAYER) and not cost.tap \
        and not cost.sacrifice_self and not cost.untap


def condition(text: str) -> dict[str, Any] | None:
    """An "Activate only if …" condition this module reads (None: not one of them)."""
    from app.rules import conditions

    if " or if " in text:  # "~ entered this turn or if you control a basic land"
        parts = [condition(p) or _base(p) for p in text.split(" or if ")]
        return {"any": parts} if all(p is not None for p in parts) else None
    m = _SELF_COMBAT.fullmatch(text)
    if m:
        return {"act7b": "self_combat", "any": [x for x in (m["a"], m["b"]) if x]}
    m = _LIFE_ABOVE.fullmatch(text)
    if m and (n := conditions._num(m["n"])) is not None:
        return {"act7b": "life_above_start", "n": n}
    if text == "you have more cards in hand than each opponent":
        return {"act7b": "hand_most"}
    m = _SAME_NAME.fullmatch(text)
    if m and (n := conditions._num(m["n"])) is not None:
        key = conditions._count(m["what"], "you control")
        return {"act7b": "same_name", "sel": key, "n": n} if key else None
    m = _NO_DEFENDER.fullmatch(text)
    if m:
        return {"not": {"object": "self", "has": m["kw"]}}
    m = re.fullmatch(r"you have exactly (?P<n>\w+) cards in hand", text)
    if m and (n := conditions._num(m["n"])) is not None:
        return {"value": {"hand": "you"}, "op": "==", "n": n}
    return _base(text)


def _base(text: str) -> dict[str, Any] | None:
    """The generic grammar, plus what it says of the source itself ("~ is a creature", "~'s power is 4 or greater")."""
    from app.rules import conditions

    found = conditions.parse(text)
    if found is None:
        found = conditions.parse(text, objects=True)
        if found is not None and set(conditions.objects_in(found)) - {"self"}:
            return None
    return found


def holds(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    from app.rules import selectors

    me = ctx["controller"]
    kind = cond["act7b"]
    if kind == "life_above_start":
        return plan.state.players[me].life - plan.state.settings.starting_life >= cond["n"]
    if kind == "hand_most":
        mine = len(plan.state.zones.get(f"{me}:hand", []))
        return all(mine > len(plan.state.zones.get(f"{p}:hand", [])) for p in plan.live() if p != me)
    if kind == "same_name":
        found = selectors.candidates(plan, selectors.from_key(cond["sel"]), me, ctx.get("source_card"))
        names: dict[str, int] = {}
        for c in found:
            card = plan.state.cards[c]
            if not card.face_down:  # (a face-down permanent has no name, 708.2a)
                names[plan.ch(card).name] = names.get(plan.ch(card).name, 0) + 1
        return max(names.values(), default=0) >= cond["n"]
    if kind == "self_combat":
        src = plan.state.cards.get(ctx.get("source_card") or "")
        if src is None or not src.zone.endswith(":battlefield"):
            return False
        states = {"attacking": src.attacking is not None, "blocking": bool(src.blocking),
                  "blocked": src.attacking is not None and src.id in plan.rules.blocked}  # (509.1h: stays blocked)
        return any(states[s] for s in cond["any"])
    raise ValueError(f"unknown activation condition {cond!r}")


_BEFORE_DAMAGE = ("begin_combat", "declare_attackers", "declare_blockers")


def step_clause(clause: str) -> dict[str, Any] | None:
    """The steps of combat as a restriction ("before the combat damage step", …); None: not one of these."""
    if clause == "before the combat damage step":
        return {"kind": "step", "phases": ["untap", "upkeep", "draw", "main1", *_BEFORE_DAMAGE], "whose": None,
                "text": "before the combat damage step"}
    if clause == "during combat after blockers are declared":
        return {"kind": "step", "phases": ["declare_blockers", "combat_damage", "end_combat"], "whose": None,
                "text": "during combat after blockers are declared"}
    if clause == "before the end of combat step":
        return {"kind": "step", "phases": ["untap", "upkeep", "draw", "main1", *_BEFORE_DAMAGE, "combat_damage"],
                "whose": None, "text": "before the end of combat step"}
    return None


# -- Adapt (701.46) --
# "Adapt N." means "If this permanent has no +1/+1 counters on it, put N +1/+1 counters on it."
_ADAPT = re.compile(r"^adapt (?P<n>\w+)$")


def _adapt(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import conditions
    from app.rules.scripts import _NoMatch

    n = conditions._num(m["n"])
    if n is None:
        raise _NoMatch()
    return [{"do": "only_if", "cond": {"not": {"object": "self", "counters": "+1/+1"}}, "skip": 1},
            {"do": "add_counters", "who": "self", "kind": "+1/+1", "n": n}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_ADAPT, _adapt)]
