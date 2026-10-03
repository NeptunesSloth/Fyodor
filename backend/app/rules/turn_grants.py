"""-- turn grants (wave 6A) -- "can't be blocked" with a filter, and one subject for two grants.

* "Target creature can't be blocked by Walls this turn." (Tower of Coireall), "This creature can't be blocked this
  turn except by creatures with haste." (Gingerbrute), "Until end of turn, target creature can't be blocked by
  creatures with power 2 or less and/or Walls." (Doorman): the same blocking restrictions a static ability states
  (app/rules/statics.py ``cant_be_blocked_by`` / ``cant_be_blocked_except_by``, 509.1b), as a rule-modifying effect
  until the turn ends (effects.restrict; 611.2c, 514.2).
* "Target creature gains vigilance until end of turn and can't be blocked this turn." (Pym Particles), "Until end of
  turn, target creature you control has base power and toughness 4/4 and gains flying and hexproof." (Water Wings),
  "This creature has base power and toughness 4/2 until end of turn and gains first strike until end of turn."
  (Battlegate Mimic): one subject, two instructions — each half is read with the subject repeated (and the leading
  "until end of turn" for both); a target subject is one target (115.3), so both halves name the same group. Base
  power and toughness is layer 7b (613.4b), a keyword layer 6 (613.1f).

Not read: "this combat" (a turn may have several combats, 500.8), a filter the selector grammar doesn't read.
"""

from __future__ import annotations

import re
from typing import Any

_UNBLOCKED = re.compile(r"^(?P<o>.+?) can't be blocked (?P<by>by .+?) this turn$")
_UNBLOCKED_EXCEPT = re.compile(r"^(?P<o>.+?) can't be blocked this turn except by (?P<ex>.+)$")
_UNBLOCKED_LEAD = re.compile(r"^until end of turn, (?P<o>.+?) can't be blocked (?P<by>by .+)$")
_SHARED = re.compile(r"^(?P<lead>until end of turn, )?(?P<o>(?:target|another target|this|that|~|it\b)[^,]*?) "
                     r"(?P<a>(?:gains?|gets|has|have) .+?) and (?P<b>(?:gains?|can't be blocked) .+)$")
_EOT = " until end of turn"


def _fail() -> Exception:
    from app.rules.scripts import _NoMatch

    return _NoMatch()


def _unblocked(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language, statics

    by, ex = m.groupdict().get("by"), m.groupdict().get("ex")
    rules = statics._rule(f"can't be blocked except by {ex}" if ex else f"can't be blocked {by}")
    if not rules:
        raise _fail()
    try:
        kind, key, group = language.ref(m["o"])
    except language._Fail:
        raise _fail() from None
    if kind not in ("target", "it", "them", "self", "each"):
        raise _fail()
    return [{"do": "restrict", "who": language._who(kind, key), "rules": rules}], language._one(group)


def _shared(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language, permissions, scripts

    # (registered last: what the cast permissions or the generic grammar read stays theirs, as before)
    whole = permissions.parse_clause(m.group(0)) or language.parse_sentence(m.group(0))
    if whole is not None:
        return whole
    a, b = m["a"], m["b"]
    if m["lead"]:
        if _EOT in a or _EOT in b or "this turn" in b:
            raise _fail()
        a, b = a + _EOT, (b + _EOT if not b.startswith("can't") else b)
    if not (a.endswith(_EOT) and (b.endswith(_EOT) or b.endswith("this turn"))):
        raise _fail()  # (each half with its own duration: a permanent grant isn't read here)
    left, right = scripts._clause(f"{m['o']} {a}"), scripts._clause(f"{m['o']} {b}")
    if left is None or right is None:
        raise _fail()
    lgroups, rgroups = scripts._as_groups(left[1]), scripts._as_groups(right[1])
    if len(lgroups) > 1 or len(rgroups) != len(lgroups):
        raise _fail()
    if lgroups and lgroups != rgroups:  # (a literal template's key and the grammar's selector for the same phrase)
        group = language.target_group(m["o"])
        same = {scripts.SELECTORS.get(m["o"]), group["what"] if group else None} - {None}
        if not (language.simple(lgroups[0]) and language.simple(rgroups[0]) and
                {lgroups[0]["what"], rgroups[0]["what"]} <= same):
            raise _fail()
    return left[0] + right[0], left[1]


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_UNBLOCKED, _unblocked), (_UNBLOCKED_EXCEPT, _unblocked),
                                                (_UNBLOCKED_LEAD, _unblocked)]
LAST: list[tuple[re.Pattern[str], Any]] = [(_SHARED, _shared)]  # (after every other template)
