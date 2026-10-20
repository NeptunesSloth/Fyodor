"""-- tap or untap (wave 6D) -- "You may tap or untap target permanent." (Pestermite, Merrow Reejerey, Tidal Force).

701.26a: to tap a permanent is to turn it sideways, to untap it is to return it upright. The ability's controller
chooses one of the two as it resolves (the choice is part of the instruction, 608.2c: it isn't made as the ability is
put on the stack). Tapping a tapped permanent, or untapping an untapped one, does nothing (701.26a), so both choices are
always offered. Untapping a permanent with a stun counter removes a counter instead (122.1d: effects.untap). The
permanent is the target (608.2b: an illegal target is skipped by the resolution, nothing to choose).
"""

from __future__ import annotations

import re
from typing import Any

from app.rules.plan import Plan

Context = dict[str, Any]

_PATTERN = re.compile(r"^(?P<may>you may )?tap or untap (?P<o>(?:another )?target .+|enchanted (?:creature|permanent|land)|equipped creature|it|that (?:creature|permanent|artifact|land))$")


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language
    from app.rules.scripts import _NoMatch

    try:
        kind, key, group = language.ref(m["o"])
    except language._Fail:
        raise _NoMatch from None
    optional = {"optional": True} if m["may"] else {}
    if kind in ("host", "it"):
        return [{"do": "tap_or_untap", "who": language._who(kind, key), **optional}], None
    if kind != "target" or group is None or group.get("max") != 1:
        raise _NoMatch
    return [{"do": "tap_or_untap", "who": language._who(kind, key), **optional}], language._one(group)


def sequence(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """608.2c–d: two separate optional instructions, with both targets chosen first.

    'Another target' explicitly excludes the first (115.1 / 601.2c), even if its
    optional action will be declined. Declining the first doesn't skip the second.
    """
    from app.rules import language

    if re.fullmatch(r"You may tap or untap target permanent, then you may tap or untap another target permanent\.?", body, re.IGNORECASE) is None:
        return None
    _, _, group = language.ref("target permanent")
    assert group is not None
    return ([{"do": "tap_or_untap", "who": f"target:{i}", "optional": True} for i in range(2)],
            [group, {**group, "distinct_from": [0]}], False)


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_PATTERN, _build)]


def tap_or_untap(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.effects import _cards
    from app.rules.plan import decide

    cards = [c for c in _cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    if not cards:
        return True
    name = plan.state.cards[cards[0]].name or "it"
    options = [DecisionOption(id="tap", label=f"Tap {name}"), DecisionOption(id="untap", label=f"Untap {name}")]
    if e.get("optional"):  # (wave 7E) an activated ability's "you may": choosing neither
        options.append(DecisionOption(id="none", label="Do nothing"))
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Tap or untap'}: tap or untap {name}?",
           options=options,
           resume={"step": "tap_or_untap", "ctx": ctx, "e": e}, source=plan.state.cards[cards[0]])
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    if chosen and chosen[0] in ("tap", "untap"):
        (effects.tap if chosen[0] == "tap" else effects.untap)(plan, ctx, {"do": chosen[0], "who": e["who"]})
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"tap_or_untap": tap_or_untap}
