"""-- block effects (wave 7E) -- "{R}: Target creature can't block this creature this turn." (Spin Engine, Duct Crawler),
"{G}: Target creature blocks this creature this turn if able." (Tangle Angler, Matsu-Tribe Decoy), "{T}: Target creature blocks
this turn if able." (Courtly Provocateur). Researched against CR 2026-09-25.

* 509.1b: a block restriction. "Can't block this creature" restricts one blocker against one attacker: the rule
  ``cant_block_obj:<object id>`` on the target names the attacker as the object it was when the ability resolved
  (400.7: a creature that left and came back is a new object, so the effect doesn't reach it).
* 509.1c: a block requirement. "Blocks this creature this turn if able" is ``must_block_obj:<object id>``, and "blocks
  this turn if able" the plain ``must_block`` (the same requirement as "blocks each combat if able", for this turn).
  The requirement is obeyed whenever the creature could block as declared (the restrictions are judged first, 509.1b),
  checked by ``combat.block_requirements`` like the other requirements.
* Both are rule-modifying effects of the resolution ending at cleanup (514.2); the target is the creature that must / may
  not block (115.1: a hexproof or protected target is refused when it is chosen).
* -- block effects (wave 30P) -- "It": in an attacking creature's trigger the creature that attacked, as that object (``@it``: Avalanche Tusker, Fighter
  Class, Grappling Hook), in an enters trigger the source; "up to one target creature", "you may have target creature block it"; "Target creature blocks
  target creature this turn if able" (``@t1``: the second target, Hunt Down). A creature that can't block - tapped, or a player's who isn't defending
  (506.2, 508.5a: one specific defending player) - has nothing to obey: 509.1c asks only for what is possible.
"""

from __future__ import annotations

import json
import re
from typing import Any

_SELF = r"(?:this creature|~)"
_CANT = re.compile(rf"^(?P<o>target creature(?: [^,.]+?)?) can't block {_SELF} this turn$")
# -- review (wave 18E) -- provoke (702.39a): "… block this creature this combat if able" ends with the combat (a turn may have several, 500.8)
# -- block effects (wave 30P) -- "blocks it / that creature / that Wolf this combat if able" (Avalanche Tusker, Fighter Class, Tolsimir): the
# attacker of the attack trigger it is in (``@it``), or the source of an enters trigger (Giant Ambush Beetle); "up to one target creature"
# (Impetuous Devils); "you may have target creature block it" is the optional form of the same instruction (scripts._may_have)
_MUST_SELF = re.compile(rf"^(?P<o>(?:up to one )?target creature(?: [^,.]+?)?) blocks (?P<i>{_SELF}|it|that creature|that [A-Z][a-z]+) "
                        r"this (?P<d>turn|combat) if able$")
_MUST_PAIR = re.compile(r"^(?P<o>target creature(?: [^,.]+?)?) blocks (?P<b>target creature(?: [^,.]+?)?) this turn if able$")  # (Hunt Down)
_MUST = re.compile(r"^(?P<o>target creature(?: [^,.]+?)?) blocks this turn if able$")


def _build(rules: list[str], duration: str | None = None) -> Any:
    def build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
        from app.rules.combat_rules import _restrict
        from app.rules.scripts import _NoMatch

        found = _restrict(m["o"], rules)
        if found is None:
            raise _NoMatch
        return ([{**e, "duration": duration} for e in found[0]], found[1]) if duration else found

    return build


def _must_it(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return _build([f"must_block_obj:{'@src' if re.fullmatch(_SELF, m['i']) else '@it'}"], "end_of_combat" if m["d"] == "combat" else None)(m)


def _must_pair(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    """"Target creature blocks target creature this turn if able." (Hunt Down, Rimehorn Aurochs): the second target is the one it must block."""
    from app.rules import language
    from app.rules.scripts import _NoMatch

    try:
        whos, groups = language._objects(f"{m['o']} and {m['b']}")
    except language._Fail:
        raise _NoMatch from None
    if len(groups) != 2:
        raise _NoMatch
    return [{"do": "restrict", "who": whos[0], "rules": ["must_block_obj:@t1"]}], language._out(groups)


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [
    (_CANT, _build(["cant_block_obj:@src"])),
    (_MUST_SELF, _must_it),
    (_MUST_PAIR, _must_pair),
    (_MUST, _build(["must_block"])),
]


def args(ctx: dict[str, Any], rule: str) -> str:
    """The object arguments of a rule (effects.restrict): ``@it``, in a trigger about an attack, is the attacking creature as that object (400.7:
    the event's), else the source (an enters trigger); ``@t1`` is the second target (Hunt Down). An object that is gone leaves "": nothing is it."""
    if "@it" in rule:
        ev = ctx.get("event") or {}
        attacker = (ev.get("objects") or [None])[0] if ev.get("kind") == "attack" else None
        rule = rule.replace("@it", str(attacker["object_id"]) if attacker else ctx.get("source_object") or "")
    if "@t1" in rule:
        from app.rules.effects import target_refs

        rule = rule.replace("@t1", next((str(t.get("object_id")) for t in target_refs(ctx, "target:1")), ""))
    return rule


def allowed(d: dict[str, Any]) -> bool:
    """``@it`` is read only where it is certain what "it" is: an attacking creature's trigger (Avalanche Tusker, Fighter Class) or an enters trigger."""
    if "@it" not in json.dumps(d, default=str):
        return True
    cond = d.get("cond") or {}
    return d.get("kind") == "triggered" and (d.get("trigger") in ("attacks_self", "enters_self")
                                              or (d.get("trigger") == "event" and cond.get("event") == "attack" and not cond.get("aggregate")))
