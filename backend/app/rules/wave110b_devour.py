"""-- wave 110B -- devour on a token (702.82a): "create a 1/1 ... Dragon creature token with flying and devour 2" (Dragon Broodmother).

The token's controller picks the creatures to sacrifice before the token is created (the questions of replacements.token_choices, 614.12a);
they are sacrificed as it enters and it gets the counters (devour.counters, replacements.after_entry). Each token of one creation picks
from what the earlier ones left.
"""
from __future__ import annotations

from typing import Any

from app.rules import devour
from app.rules.plan import Plan


def question(plan: Plan, pid: str, spec: dict[str, Any], key: str, answers: dict[str, str], reserved: set[str]) -> tuple[dict[str, str], dict[str, Any] | None]:
    """(the token's devour choice, or the open question {key, player, prompt, options}). Empty when the token has no devour."""
    from app.rules.replacements import _token_probe

    if "devour" not in (spec.get("text") or "").lower():
        return {}, None
    probe = _token_probe(pid, spec)
    value: str | None = None
    for pick in range(99):  # one question per pick, answered as "<key>#<pick>" (702.82a: any number of creatures, asked again until "done")
        out: dict[str, Any] = {}
        devour.plan_entry(plan, probe, pid, {devour.WHAT: value} if value else {}, out, reserved)
        if (choice := out.get("choice")) is None:
            return out.get("choices") or {}, None
        if f"{key}#{pick}" not in answers:
            prompt, options = devour.prompt(plan, probe, pid, choice)
            return {}, {"key": f"{key}#{pick}", "player": pid, "prompt": prompt, "options": options}
        value = devour.merge(value, answers[f"{key}#{pick}"])
    return {}, None


def sacrifice(plan: Plan, tid: str, pid: str, choices: dict[str, str] | None) -> dict[str, str] | None:
    """The picked creatures are sacrificed as the token enters; the choices then name the ones that went."""
    ids = [c for c in devour.picked((choices or {}).get(devour.WHAT)) if c in plan.state.cards]
    if not ids:
        return choices
    ep: dict[str, Any] = {"devour": ids}
    devour.sacrifice(plan, ep, pid)
    return {**(choices or {}), **ep["choices"]}
