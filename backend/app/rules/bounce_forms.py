"""-- bounce forms (wave 6A) -- more "return … to its owner's hand" wordings.

* "Return a permanent you control to its owner's hand." (Kor Skyfisher), "you may return another creature you
  control …" (Loyal Gryff, as the whole ability's "may"), "Return a red or green creature you control …": not a
  target — the player chooses as the effect resolves (608.2d), among what they control then: the existing
  "chooses N … they control" choice (effects.player_chooses) followed by a return of what was chosen.
* "Each player returns a creature they control to its owner's hand." (Curfew), "that player returns a land they
  control …" (Mana Breach): each of those players chooses their own (APNAP, 101.4), then they return together.
* "Return target creature you control and target creature you don't control to their owners' hands." (Peel from
  Reality, Aether Tradewinds, Churning Eddy): one target group per word "target" (115.3); one instruction, so one
  move (all at once).
* "Return this creature and target creature you control to their owner's hand." (Wizard Mentor, Coastal Wizard).
* "Return all artifacts and enchantments to their owners' hands." (Reduce to Dreams): every permanent that is either.

A card goes to its owner's hand whoever controlled it (400.3).
"""

from __future__ import annotations

import re
from typing import Any

from app.rules.plan import Plan

Context = dict[str, Any]

_N = r"a|an|one|two|three"
_HAND = r"to (?:its owner's hand|their owners' hands|their owner's hand)"
_YOURS = re.compile(rf"^return (?:(?P<n>{_N})|(?P<another>another)) (?P<sel>.+?) you control {_HAND}$")
_THEIRS = re.compile(rf"^(?P<s>each player|each opponent|that player|target player|target opponent) returns? (?P<n>{_N}) "
                     rf"(?P<sel>.+?) they control {_HAND}$")
_TWO_TARGETS = re.compile(rf"^return (?P<o>target .+? and (?:another )?target .+?) {_HAND}$")
_SELF_AND = re.compile(r"^return (?:this creature|~) and (?P<t>(?:another )?target .+?) to their (?:owners' hands|owner's hand)$")
_ALL_AND = re.compile(rf"^return all (?P<a>[a-z]+s) and (?P<b>[a-z]+s) {_HAND}$")


def _fail() -> Exception:
    from app.rules.scripts import _NoMatch

    return _NoMatch()


def _choose(who: str, n: Any, sel: str, label: str) -> list[dict[str, Any]]:
    pronoun = "it" if n == 1 else "them"  # (resolve_it counts the choice as one per chooser)
    return [{"do": "player_chooses", "who": who, "sel": sel, "n": n, "label": label}, {"do": "bounce", "who": pronoun}]


def _yours(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language

    try:
        phrase = f"another {m['sel']}" if m["another"] else m["sel"]  # (other than the source)
        sel = language._permanent_sel(phrase)
        n = language._amount(m["n"] or "a")
    except language._Fail:
        raise _fail() from None
    return _choose("you", n, sel, phrase), None


def _theirs(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language

    try:
        sel = language._permanent_sel(m["sel"])
        n = language._amount(m["n"])
        who, group = language._chooser(m["s"])
    except language._Fail:
        raise _fail() from None
    return _choose(who, n, sel, m["sel"]), language._one(group)


def _two_targets(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language

    try:
        whos, groups = language._objects(m["o"])
    except language._Fail:
        raise _fail() from None
    if len(whos) < 2 or len(groups) != len(whos) or any(g.get("what", "").endswith("spell") for g in groups):
        raise _fail()
    return [{"do": "bounce_together", "who": whos[0], "also": whos[1:]}], language._out(groups)


def _self_and(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    """"Return this creature and target creature you control to their owner's hand." (Wizard Mentor): the source and
    the target, together (the source only while it is still that permanent, 400.7)."""
    from app.rules import language

    try:
        kind, _key, group = language.ref(m["t"])
    except language._Fail:
        raise _fail() from None
    if kind != "target" or group is None or group.get("what", "").endswith("spell"):
        raise _fail()
    return [{"do": "bounce_together", "who": "self", "also": ["target"]}], language._one(group)


def _all_and(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import selectors

    sel = selectors.parse(f"{m['a']} or {m['b']}")
    if sel is None or sel.player is not None or sel.card or sel.zones not in ((), ("battlefield",)) or sel.controller:
        raise _fail()
    return [{"do": "bounce", "who": sel.key()}], None


def _deferring(build: Any) -> Any:
    """What the generic grammar already reads stays its reading (these templates run before it)."""
    def template(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
        from app.rules import language

        found = language.parse_sentence(m.group(0))
        return found if found is not None else build(m)
    return template


# -- counters sweep (wave 19D) -- "Put a +1/+1 counter on a creature you control." / "Put two +1/+1 counters on a creature you
# control." / "… on up to one creature you control.": no target (115.1), the player chooses as the effect resolves (608.2d), among what
# they control then — the same choice (effects.player_chooses), then the counters on what was chosen (122.1; "up to one": none
# is a choice too)
_COUNTERS_ON_YOURS = re.compile(r"^put (?P<n>a|an|one|two|three|four|five) (?P<k>\+1/\+1|-1/-1|[a-z]+) counters? on "
                                r"(?:(?P<up>up to one)|(?P<a>a|another)) (?P<sel>.+?) you control$", re.I)


def _counters_on_yours(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language, values

    if m["k"] in values.UNMODELED_COUNTERS:
        raise _fail()
    try:
        phrase = f"another {m['sel']}" if m["a"] == "another" else m["sel"]
        sel = language._permanent_sel(phrase)
        n = language._amount(m["n"])
    except language._Fail:
        raise _fail() from None
    choose = _choose("you", 1, sel, phrase)[0]
    if m["up"]:
        choose["upto"] = True
    return [choose, {"do": "add_counters", "who": "it", "kind": m["k"], "n": n}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_YOURS, _deferring(_yours)), (_THEIRS, _deferring(_theirs)),
                                                (_COUNTERS_ON_YOURS, _deferring(_counters_on_yours)),
                                                (_TWO_TARGETS, _deferring(_two_targets)), (_ALL_AND, _deferring(_all_and)),
                                                (_SELF_AND, _deferring(_self_and))]


def bounce_together(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Each still-legal target of the groups named, to its owner's hand in one move (608.2b: an illegal one isn't)."""
    from app.rules.effects import _cards, _moved, _remember

    cards = list(dict.fromkeys(c for who in [e["who"], *e.get("also", [])] for c in _cards(plan, ctx, who)
                               if plan.state.cards[c].zone.endswith(":battlefield")))
    before = _remember(plan, ctx, e, cards)
    if cards:
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "hand"}}, actor=ctx["controller"])
    _moved(plan, ctx, e, before)
    return True


PRIMITIVES = {"bounce_together": bounce_together}
