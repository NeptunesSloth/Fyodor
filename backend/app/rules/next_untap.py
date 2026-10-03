"""-- next untap step (wave 6A) -- "[Object] doesn't untap during its controller's next untap step".

Frost Breath, Kefnet's Monument, Wall of Frost, Vorinclex, Voice of Hunger, Arbalest Elite: a one-shot
effect that keeps particular permanents from untapping during one untap step (502.3: effects can keep
permanents from untapping). It modifies the rules of the game, not the objects' characteristics, so
"its controller" is read when an untap step comes (611.2c): the permanent stays tapped during the next
untap step of whoever controls it then, and the effect ends with that untap step whether or not the
permanent was tapped. "Your next untap step" waits for the ability's controller's untap step (the same
bookkeeping as exert, 701.43a). A skipped untap step doesn't happen (614.10a): the effect waits for the
next one. A permanent that leaves the battlefield is a new object (400.7): the effect is gone with it.

Only named objects: a target, a pronoun for what an earlier instruction named, or the source. A mass
wording ("Lands you control don't untap during your next untap step", "Each attacking creature …")
would apply to whatever matches when the untap step comes (611.2c: a rules-modifying effect isn't
locked to a set), so it stays manual; so do "that player's next untap step" and "next two untap steps".
"""

from __future__ import annotations

import re
from typing import Any

from app.rules.plan import Plan

Context = dict[str, Any]

_PATTERN = re.compile(r"^(?P<o>.+?) (?:doesn't|don't) untap during (?P<whose>its controller's|their controller's|"
                      r"their controllers'|your) next untap steps?$")
_OBJECTS = ("it", "them", "target", "self")


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language
    from app.rules.scripts import _NoMatch

    whose = "you" if m["whose"] == "your" else "controller"
    if m[0].endswith("steps") and m["whose"] != "their controllers'":
        raise _NoMatch
    try:
        kind, key, group = language.ref(m["o"])
    except language._Fail:
        raise _NoMatch from None
    if kind not in _OBJECTS:
        raise _NoMatch  # (a mass wording: see above)
    return [{"do": "stay_tapped", "who": language._who(kind, key), "during": whose}], language._one(group)


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_PATTERN, _build)]


def stay_tapped(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Record the effect for each named permanent still on the battlefield (as the object it is now)."""
    from app.rules.effects import _cards, _remember

    cards = [c for c in _cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    _remember(plan, ctx, e, cards)
    me = ctx["controller"]
    for cid in cards:
        player = me if e.get("during") == "you" else "controller"
        plan.rules.stay_tapped.append({"oid": plan.oid(cid), "player": player})
        whose = f"{plan.name(me)}'s" if player == me else "its controller's"
        plan.note(f"{plan.state.cards[cid].name or 'It'} doesn't untap during {whose} next untap step", [cid], actor=me)
    return True


def _live(plan: Plan, rec: dict[str, str]) -> Any:
    card = plan.state.cards.get(rec["oid"].rsplit(".", 1)[0])
    if card is None or plan.oid(card) != rec["oid"] or not card.zone.endswith(":battlefield"):
        return None
    return card


def _applies(plan: Plan, rec: dict[str, str], card: Any, player: str) -> bool:
    return card.controller == player and rec["player"] in ("controller", player)


def kept(plan: Plan, player: str) -> list[str]:
    """The tapped permanents that stay tapped during ``player``'s untap step about to happen (502.3)."""
    out = []
    for rec in plan.rules.stay_tapped:
        card = _live(plan, rec)
        if card is not None and card.tapped and _applies(plan, rec, card, player) and card.id not in out:
            out.append(card.id)
    return out


def untap_step_done(plan: Plan, player: str) -> None:
    """``player``'s untap step happened: the effects waiting for it end (whether or not the permanent was
    tapped); the effects of objects that are gone end too."""
    keep = []
    for rec in plan.rules.stay_tapped:
        card = _live(plan, rec)
        if card is None or _applies(plan, rec, card, player) or rec["player"] == player:
            continue
        keep.append(rec)
    plan.rules.stay_tapped = keep


PRIMITIVES = {"stay_tapped": stay_tapped}
