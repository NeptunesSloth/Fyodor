"""-- as long as (wave 100K) -- small restriction wordings of the "as long as" package.

* "{R/G}: Target spell can't be countered." (Vexing Shusher): 101.2, 701.6 — that spell (one object, 400.7) can't be countered for as long as it
  stays on the stack; a spell never outlasts its turn on the stack (500.2: a step ends only on an empty stack), so a record of this turn holds it
  (permissions.spell_uncounterable reads it).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def _target_uncounterable(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "uncounterable_target100k", "who": "target"}], "spell"


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(re.compile(r"^target spell can't be countered$"), _target_uncounterable)]


def uncounterable_target(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    for cid in effects._cards(plan, ctx, e["who"]):
        card = plan.state.cards[cid]
        if card.zone == "stack":
            plan.rules.results.append({"player": card.controller, "what": "uncounterable", "turn": plan.state.turn.number,
                                       "oid": plan.rules.object_id(cid)})
    return True


PRIMITIVES = {"uncounterable_target100k": uncounterable_target}

# Imaginary Threats: "that player" / "they" is the target opponent; no creature of theirs untaps in their next untap step, those that come
# later included (its 2017-07-14 ruling: next_untap's selector record, read as that step comes)
THREATS = ("Creatures target opponent controls attack this turn if able. During that player's next untap step, creatures they control don't untap.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts, selectors

    if ability.kind != "spell" or ability.text != THREATS:
        return None
    native = scripts.define(replace(ability, text=THREATS.split(". ")[0] + "."), ch)
    if native is None or len(native.get("effects") or []) != 1:
        return None
    return {**native, "effects": [*native["effects"], {"do": "stay_tapped", "sel": [selectors.Selector(types=("Creature",)).key()], "who": "target"}]}
