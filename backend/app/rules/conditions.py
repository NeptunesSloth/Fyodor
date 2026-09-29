"""Conditions as data ("if you control a Forest", "if you have 5 or less life"): parsed from Oracle
wording, evaluated against the table. Used by intervening-if triggers (CR 603.4: checked when the
ability triggers and again as it resolves) and by "If …, [effect]" sentences (608.2c).

A condition is ``{"value": <value>, "op": ">=" | "<=" | "==", "n": int}``: a quantity (see
app/rules/values.py) compared with a number; or ``{"succeeded": <binding>}``: an optional payment
of this resolution was made in full ("If you do", app/rules/context.py). :func:`parse` returns None for wordings it doesn't
read (the ability then stays manual).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import selectors, values

if TYPE_CHECKING:
    from app.rules.plan import Plan

Condition = dict[str, Any]
_N = values.NUMBERS | {"no": 0}


def _num(word: str) -> int | None:
    w = word.lower()
    return int(w) if w.isdigit() else _N.get(w)


def _count(phrase: str, controller: str) -> str | None:
    sel = selectors.parse(f"{phrase} {controller}")
    return sel.key() if sel is not None and sel.player is None else None


def parse(text: str) -> Condition | None:
    t = text.strip().rstrip(",")
    # "you control a Forest", "you control two or more Islands", "you control another Elf",
    # "you control no creatures", "you don't control a …", "an opponent controls a …"
    m = re.fullmatch(r"(?P<who>you|an opponent) (?P<neg>don't |doesn't )?controls? "
                     r"(?P<q>a|an|another|no|\w+ or more|at least \w+) (?P<sel>.+)", t)
    if m:
        q = m["q"]
        other = q == "another"
        if q in ("a", "an", "another"):
            n, op = 1, ">="
        elif q == "no":
            n, op = 0, "=="
        else:
            word = q.split()[2] if q.startswith("at least") else q.split()[0]
            got = _num(word)
            if got is None:
                return None
            n, op = got, ">="
        if m["neg"]:
            if op != ">=" or n != 1:
                return None
            n, op = 0, "=="
        key = _count(("another " if other else "") + m["sel"], "you control" if m["who"] == "you" else "an opponent controls")
        if not key:
            return None
        out: Condition = {"value": {"count": key}, "op": op, "n": n}
        if m["who"] == "an opponent":
            out["per_opponent"] = True  # one opponent must have that many, not all of them together
        return out
    # "you have 5 or less life", "you have 30 or more life", "you have at least 10 life"
    m = re.fullmatch(r"you have (?:(?P<n>\w+) or (?P<cmp>less|more|fewer|greater)|at least (?P<least>\w+)) life", t)
    if m:
        life = _num(m["n"] or m["least"])
        if life is None:
            return None
        return {"value": {"life": "you"}, "op": "<=" if m["cmp"] in ("less", "fewer") else ">=", "n": life}
    # "you have no cards in hand", "you have N or more cards in hand"
    m = re.fullmatch(r"you have (?:(?P<no>no)|(?P<n>\w+) or (?P<cmp>more|fewer|less)) cards in (?:your )?hand", t)
    if m:
        if m["no"]:
            return {"value": {"hand": "you"}, "op": "==", "n": 0}
        cards = _num(m["n"])
        if cards is None:
            return None
        return {"value": {"hand": "you"}, "op": ">=" if m["cmp"] == "more" else "<=", "n": cards}
    return None


def holds(plan: Plan, ctx: dict[str, Any], cond: Condition) -> bool:
    if "succeeded" in cond:  # "If you do": that payment (by its binding) was made in full (118.12)
        from app.rules import context

        return context.succeeded(ctx, cond["succeeded"])
    v = cond["value"]
    n = cond["n"]
    if cond.get("per_opponent"):
        found = selectors.candidates(plan, selectors.from_key(v["count"]), ctx["controller"], ctx.get("source_card"))
        per = [sum(1 for c in found if plan.state.cards[c].controller == p) for p in plan.live() if p != ctx["controller"]]
        # "an opponent controls two or more …" / "… controls no …": some one opponent does
        return any({">=": x >= n, "<=": x <= n, "==": x == n}[cond["op"]] for x in per)
    got = plan.state.players[ctx["controller"]].life if "life" in v else values.evaluate(plan, ctx, v)
    return {">=": got >= n, "<=": got <= n, "==": got == n}[cond["op"]]
