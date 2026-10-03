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
"""

from __future__ import annotations

import re
from typing import Any

_SELF = r"(?:this creature|~)"
_CANT = re.compile(rf"^(?P<o>target creature(?: [^,.]+?)?) can't block {_SELF} this turn$")
_MUST_SELF = re.compile(rf"^(?P<o>target creature(?: [^,.]+?)?) blocks {_SELF} this turn if able$")
_MUST = re.compile(r"^(?P<o>target creature(?: [^,.]+?)?) blocks this turn if able$")


def _build(rules: list[str]) -> Any:
    def build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
        from app.rules.combat_rules import _restrict
        from app.rules.scripts import _NoMatch

        found = _restrict(m["o"], rules)
        if found is None:
            raise _NoMatch
        return found

    return build


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [
    (_CANT, _build(["cant_block_obj:@src"])),
    (_MUST_SELF, _build(["must_block_obj:@src"])),
    (_MUST, _build(["must_block"])),
]
