"""Attach on entry (wave 5J), researched against CR 2026-09-25.

"When this Equipment enters, attach it to target creature you control." (Embercleave, Maul of the
Skyclaves, Celestial Armor …), "Whenever an Equipment you control enters, you may attach it to target
creature you control." (Sigarda's Aid) and "… you may attach that Equipment to target creature you
control." (Hammer of Nazahn).

* 301.5b: an Equipment enters unattached; a spell or ability may attach it. The ability targets the
  creature (115.1), so hexproof / shroud / protection apply, and a target that is illegal on
  resolution (608.2b: no longer a creature you control, gone) means the ability does nothing to it.
* 701.3a-b: to attach is to move the Equipment onto that creature — only if it could equip it
  (``attachments.host_problem``: an Equipment that's also a creature can't, 301.5c; protection,
  702.16c); otherwise it doesn't move. Attaching it to the creature it already equips does nothing.
* 701.3c: attaching gives the Equipment a new timestamp (the ``attach`` table action).
* 400.7: "it" is the object that entered: if it left the battlefield (or left and came back) before
  the ability resolves, there is nothing to attach (``effects._cards`` "self" / "event").

The rest of the ability ("That creature gains hexproof and indestructible until end of turn",
"Untap that creature", "Destroy up to one other target creature") is the ordinary grammar: "that
creature" is the target (scripts.resolve_it).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]


def parse(target: str) -> tuple[list[dict[str, Any]], Any] | None:
    """"[up to one ]target <creature …>" → the effect and its target group, or None (manual)."""
    from app.rules import selectors
    from app.rules.copying import _target_group

    group = _target_group(target)
    if group is None or group["max"] != 1 or "another" in group or not group["what"].startswith(selectors.PREFIX):
        return None
    sel = selectors.from_key(group["what"])
    if sel.player is not None or sel.zones != ("battlefield",) or sel.card or sel.ability is not None:
        return None  # ("target Dwarf you control": a permanent; one it can't be attached to, it doesn't move, 701.3b)
    return [{"do": "attach_to", "src": "it", "who": "target"}], group


def attach_to(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.3a-b: attach the object "it" names to the target, if it still is that object on the
    battlefield and could be attached there; otherwise nothing moves."""
    from app.rules import attachments, context, effects

    src = effects._cards(plan, ctx, str(e.get("src") or "self"))
    hosts = effects._cards(plan, ctx, str(e.get("who") or "target"))
    if (name := e.get("did")) and name not in context.refs(ctx):  # -- block events (wave 53C) -- "attach it to target creature you control. When you do / If you do, …": it was done if it is attached there
        context.refs(ctx)[name] = {"kind": "probe", "attached": {c: hosts[0] for c in src} if hosts else {}}
    if hosts:
        for cid in src:  # (-- attach all (wave 30S) -- "any number of target Equipment": each one, 701.3a)
            attachments.attach(plan, cid, hosts[0], ctx["controller"])
    return True


def choose(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """-- attach choice (wave 25A) -- "You may attach an Equipment you control to it." / "Attach any number of Equipment you control to it."
    (Nahiri, Heir of the Ancients; Armed and Armored): not targeted — as it resolves its controller chooses which Equipment they control
    (701.3a; one that can't be attached there, 701.3b, or is attached to it already isn't offered), at once and in no order (``n`` 1: one)."""
    from app.game.rules_state import DecisionOption
    from app.rules import attachments, effects
    from app.rules.targets import label

    who = str(e.get("who") or "self")
    # (-- wave 30S -- "target permanent or player": a player is the host of an Aura, 303.4c)
    hosts = effects._cards(plan, ctx, who) or [t["id"] for t in effects.target_refs(ctx, who) if t["id"] in plan.state.players]
    me = ctx["controller"]
    if not hosts:
        return True
    host = hosts[0]
    # -- attach all (wave 30S) -- Auras too ("kinds"), "all" of them with no choice, and any player's ("anyone": "on the battlefield")
    kinds = set(e.get("kinds") or ("Equipment",))
    pool = [c.id for c in plan.state.cards.values()
            if c.zone.endswith(":battlefield") and (e.get("anyone") or c.controller == me) and kinds & set(plan.ch(c).subtypes)
            and host not in (c.attached_to, c.attached_player) and attachments.host_problem(plan, c, host) is None]
    if not pool:
        return True
    if e.get("n") == "all":
        for cid in pool:
            attachments.attach(plan, cid, host, me)  # (613.7m: the order they receive their timestamps is the table's)
        return True
    effects.decide(plan, player=me, kind="choose_cards", prompt=f"{ctx.get('name') or 'Attach'}: attach which to {label(plan, host)}?",
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Equipment", card_id=c) for c in pool],
                   min_choices=1 if e.get("n") == 1 and not e.get("optional") else 0, max_choices=1 if e.get("n") == 1 else len(pool), resume={"step": "attach_choose", "ctx": ctx, "host": host})
    return False


def resume_choose(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import attachments
    from app.rules.effects import continue_effects

    for cid in chosen:
        attachments.attach(plan, cid, d.resume["host"], d.player)
    continue_effects(plan, d.resume["ctx"])


def unattach_all(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """-- attach all (wave 30S) -- "Unattach all Equipment from target creature." (Disarm): 701.3d — each Equipment attached to it stays on the
    battlefield, equipping nothing (the engine's ``detach``; the target is read while it is still that object, 608.2b)."""
    from app.rules import effects

    hosts = set(effects._cards(plan, ctx, str(e.get("who") or "target")))
    loose = [c.id for c in plan.state.cards.values() if c.attached_to in hosts and "Equipment" in plan.ch(c).subtypes]
    if loose:
        plan.do({"type": "detach", "card_ids": loose}, actor=ctx["controller"])
    return True


PRIMITIVES = {"attach_to": attach_to, "attach_choose": choose, "unattach_all": unattach_all}
RESUME = {"attach_choose": resume_choose}
