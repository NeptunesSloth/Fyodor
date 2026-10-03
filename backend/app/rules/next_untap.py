"""-- next untap step (wave 6A) -- "[Object] doesn't untap during its controller's next untap step".

Frost Breath, Kefnet's Monument, Wall of Frost, Vorinclex, Voice of Hunger, Arbalest Elite: a one-shot
effect that keeps particular permanents from untapping during one untap step (502.3: effects can keep
permanents from untapping). It modifies the rules of the game, not the objects' characteristics, so
"its controller" is read when an untap step comes (611.2c): the permanent stays tapped during the next
untap step of whoever controls it then, and the effect ends with that untap step whether or not the
permanent was tapped. "Your next untap step" waits for the ability's controller's untap step (the same
bookkeeping as exert, 701.43a). A skipped untap step doesn't happen (614.10a): the effect waits for the
next one. A permanent that leaves the battlefield is a new object (400.7): the effect is gone with it.

Named objects: a target, a pronoun for what an earlier instruction named, or the source; "that player's"
next untap step (Sleep) is that player's own, whoever controls the creature then.

-- untap restrictions (wave 13E) -- A mass wording ("Lands you control don't untap during your next untap
step", "Creatures and lands target opponent controls …"): it doesn't modify characteristics, so it applies to
whatever matches when the untap step comes (611.2c) and is a ``sel`` record (a selector, no object). "Each
attacking creature …" and "next two untap steps" stay manual.
"""

from __future__ import annotations

import re
from typing import Any

from app.rules.plan import Plan

Context = dict[str, Any]

# (-- other side (wave 6D) -- the object has no " and " in it: "tap that creature and it doesn't untap …" is two clauses)
_PATTERN = re.compile(r"^(?P<o>(?:(?! and ).)+?) (?:doesn't|don't) untap during (?P<whose>its controller's|their controller's|"
                      r"their controllers'|your|that player's) next untap steps?$")
_MASS = re.compile(r"^(?P<k>Creatures and lands|Lands|Creatures) (?:(?P<you>you control)|(?P<t>target (?:player|opponent)) controls) "
                   r"(?:doesn't|don't) untap during (?:your|their) next untap step$", re.I)
_OBJECTS = ("it", "them", "target", "self")


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language
    from app.rules.scripts import _NoMatch

    whose = "you" if m["whose"] == "your" else "player" if m["whose"] == "that player's" else "controller"
    if m[0].endswith("steps") and m["whose"] != "their controllers'":
        raise _NoMatch
    try:
        kind, key, group = language.ref(m["o"])
    except language._Fail:
        raise _NoMatch from None
    if kind not in _OBJECTS:
        raise _NoMatch  # (a mass wording: see above)
    return [{"do": "stay_tapped", "who": language._who(kind, key), "during": whose,
             **({"player": "that_player"} if whose == "player" else {})}], language._one(group)


def _mass(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language, selectors

    keys = [k.key() for k in (selectors.parse(w) for w in ("creatures", "lands") if w in m["k"].lower()) if k is not None]
    group = language.ref(m["t"])[2] if m["t"] else None
    return [{"do": "stay_tapped", "sel": keys, "who": "target" if m["t"] else "you"}], language._one(group)


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_MASS, _mass), (_PATTERN, _build)]


def stay_tapped(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Record the effect for each named permanent still on the battlefield (as the object it is now)."""
    from app.rules.effects import _cards, _players, _remember

    me = ctx["controller"]
    if "sel" in e:  # (611.2c: the permanents that match when that player's untap step comes)
        for pid in _players(plan, ctx, e["who"])[:1]:
            plan.rules.stay_tapped.extend({"sel": k, "player": pid} for k in e["sel"])
            plan.note(f"Some of {plan.name(pid)}'s permanents don't untap during their next untap step", actor=me)
        return True
    cards = [c for c in _cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    _remember(plan, ctx, e, cards)
    named = _players(plan, ctx, e["player"])[:1] if e.get("during") == "player" else []
    for cid in cards if e.get("during") != "player" or named else []:  # ("that player's": nobody left → nothing)
        player = me if e.get("during") == "you" else named[0] if named else "controller"
        plan.rules.stay_tapped.append({"oid": plan.oid(cid), "player": player})
        whose = f"{plan.name(me)}'s" if player == me else "its controller's"
        plan.note(f"{plan.state.cards[cid].name or 'It'} doesn't untap during {whose} next untap step", [cid], actor=me)
    return True


def _live(plan: Plan, rec: dict[str, str]) -> Any:
    if "sel" in rec:
        return None
    card = plan.state.cards.get(rec["oid"].rsplit(".", 1)[0])
    if card is None or plan.oid(card) != rec["oid"] or not card.zone.endswith(":battlefield"):
        return None
    return card


def _applies(plan: Plan, rec: dict[str, str], card: Any, player: str) -> bool:
    return card.controller == player and rec["player"] in ("controller", player)


def kept(plan: Plan, player: str) -> list[str]:
    """The tapped permanents that stay tapped during ``player``'s untap step about to happen (502.3)."""
    from app.rules import selectors

    out = []
    for rec in plan.rules.stay_tapped:
        if "sel" in rec and rec["player"] == player:
            sel = selectors.from_key(rec["sel"])
            out += [c.id for c in plan.state.cards.values() if c.tapped and c.controller == player and c.zone.endswith(":battlefield")
                    and selectors.matches(plan, sel, c, plan.ch(c), player) and c.id not in out]
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
        if "sel" in rec:
            if rec["player"] != player:
                keep.append(rec)  # (wave 13E: it waits for that player's untap step)
            continue
        if card is None or _applies(plan, rec, card, player) or rec["player"] == player:
            continue
        keep.append(rec)
    plan.rules.stay_tapped = keep


PRIMITIVES = {"stay_tapped": stay_tapped}
