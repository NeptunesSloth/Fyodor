"""Attached objects and control (wave 100F), researched against CR 2026-09-25.

**Losing control.** "When you lose control of the creature, tap it." (Ray of Command; "the artifact": Magus of the Unseen), "When you lose
control of that Equipment, unattach it." (Ogre Geargrabber): a delayed triggered ability (603.7) the resolving ability creates on the object it
just took (603.7c: that object, bound now). It triggers once (603.7b) when its controller loses control of that object: another player gains
control of it — the "until end of turn" effect ending in cleanup (514.2, 613.1b) or another control-changing effect — or it leaves the
battlefield (603.10d looks back in time; the official rulings of Ray of Command / Magus of the Unseen, and of Khârn the Betrayer and Gustha's
Scepter: "You lose control of [it] when it leaves the battlefield or another player gains control of it"). If its controller doesn't control
the object as the ability resolves, there is nothing to lose: no delayed trigger. A trigger in the cleanup step gives priority and another
cleanup step follows (514.3a, engine).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.rules_state import DelayedTrigger, Event, ObjectRef
    from app.rules.plan import Plan

Context = dict[str, Any]

LOSE_CONTROL = {"kind": "event", "event": "lose_control", "open": True}
_LOSE = re.compile(r"^when you lose control of (?:the creature|the artifact|that equipment), (?P<clause>tap it|unattach it)$", re.I)


def _lose(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import delayed

    inner = [{"do": "tap", "who": "it"}] if m["clause"] == "tap it" else [{"do": "unattach_it100f", "who": "it"}]
    return delayed.wrap_when(inner, LOSE_CONTROL, who="it"), None


def watching(plan: Plan, ctx: Context, watched: list[str]) -> list[str]:
    """The watched objects the creating ability's controller controls now (one it doesn't control can't be lost)."""
    return [c for c in watched if plan.state.cards[c].controller == ctx["controller"]]


def lost(plan: Plan, t: DelayedTrigger, events: list[Event]) -> list[ObjectRef]:
    """The watched objects ``t``'s controller lost control of in ``events`` (as they were then)."""
    from app.game.rules_state import ObjectRef
    from app.rules.triggers import _zone

    oids = {o["object_id"] for o in (t.refs.get("watch") or {}).get("objects") or []}
    out: list[ObjectRef] = []
    for e in events:
        if e.manual or e.object_id is None or e.object_id not in oids or not e.card:
            continue
        if e.kind == "designation" and e.counter == "control" and e.from_zone == t.controller and e.player != t.controller:
            out.append(ObjectRef(card=e.card, object_id=e.object_id))
        elif e.kind == "zone_change" and _zone(e.from_zone) == "battlefield" and _zone(e.to_zone) != "battlefield":
            snap = plan.rules.lki.get(e.object_id or "")
            if snap is not None and snap.controller == t.controller:
                out.append(ObjectRef(card=e.card, object_id=e.object_id, snapshot=snap))
    return out


def unattach_it(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.3d: "unattach it": the Equipment stays on the battlefield attached to nothing (nothing if it isn't attached or is gone)."""
    from app.rules import effects

    loose = [c for c in effects._cards(plan, ctx, str(e.get("who") or "it"))
             if plan.state.cards[c].zone.endswith(":battlefield") and plan.state.cards[c].attached_to]
    if loose:
        plan.do({"type": "detach", "card_ids": loose}, actor=ctx["controller"])
    return True


def _clause(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    from app.rules import scripts

    return scripts._clause(text)


# -- one grant, two subjects -- "it and Zombies you control gain deathtouch until end of turn" (Wand of Orcus): the one object and the group, each
# granted the keywords until end of turn (611.2a; the group is read as the ability resolves, 611.2c); a creature that is both is simply granted them
_AND_GROUP = re.compile(r"^(?P<a>it|~|equipped creature|enchanted creature) and (?P<b>(?!target\b)[^,.\"]+? you control) gain (?P<kw>[a-z ,]+?) until end of turn$")


def _and_group(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    left, right = _clause(f"{m['a']} gains {m['kw']} until end of turn"), _clause(f"{m['b']} gain {m['kw']} until end of turn")
    if left is None or right is None or left[1] is not None or right[1] is not None or len(left[0]) != 1 or len(right[0]) != 1 \
            or {e["do"] for e in (*left[0], *right[0])} != {"grant"}:
        raise _NoMatch
    return left[0] + right[0], None


# "Each equipped creature and Equipment you control gains deathtouch until end of turn." (Hemlock Vial): one group, either kind (the ruling: the set is
# fixed as the ability resolves, 611.2c — a creature equipped later doesn't gain it)
_EQUIPPED_AND_EQUIPMENT = re.compile(r"^each equipped creature and equipment you control gains (?P<kw>[a-z ,]+?) until end of turn$", re.I)


def _equipped_and_equipment(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import selectors
    from app.rules.scripts import _NoMatch

    halves = [selectors.parse(p) for p in ("equipped creatures you control", "Equipment you control")]
    found = _clause(f"creatures you control gain {m['kw']} until end of turn")
    if any(h is None for h in halves) or found is None or found[1] is not None or [e["do"] for e in found[0]] != ["grant"]:
        raise _NoMatch
    return [{**found[0][0], "who": selectors.Selector(either=tuple(h.key() for h in halves if h is not None)).key()}], None


# -- the host deals damage -- "enchanted creature deals 1 damage to its owner" (Enslave), "Enchanted creature deals 1 damage to target creature with flying."
# (Dizzying Gaze): the creature the source is attached to is the source of the damage (120.3; its lifelink / deathtouch count, 702.15b, 702.2b). 608.2h: the
# creature is read as the effect happens — what the Aura enchants now, or what it enchanted as it last existed if the Aura has left — and if that creature has
# left the battlefield too, as it last existed (it still deals the damage). "Its owner" is that creature's owner (108.3).
HOST = "host100f"
_HOST_DAMAGE = re.compile(r"^(?:enchanted|equipped) creature deals (?P<n>\d+) damage to (?P<o>its owner|its controller|target [^,.\"]+|any target)$")


def _host_damage(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language
    from app.rules.scripts import _NoMatch

    n, o = int(m["n"]), m["o"]
    if o in ("its owner", "its controller"):
        who, group = f"ref:{HOST}.{o.split()[1]}", None
    else:
        try:
            group = language.target_group(o)
        except language._Fail:
            raise _NoMatch from None
        if group is None or group.get("min") != 1 or group.get("max") != 1 or "another" in group:
            raise _NoMatch
        who = "target"
    return [{"do": "bind_host100f", "as": HOST}, {"do": "damage", "who": who, "n": n, "src": f"ref:{HOST}"}], group


def bind_host(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """608.2h: bind (``as``) the object the source is attached to — now, or as the source last existed — as it is, or as it last existed."""
    from app.game.rules_state import ObjectRef
    from app.rules import context

    r = plan.rules
    src = plan.state.cards.get(ctx.get("source_card") or "")
    if src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == ctx.get("source_object"):
        host_id = src.attached_to
        host_oid = plan.oid(host_id) if host_id in plan.state.cards else None
    else:
        snap = r.lki.get(ctx.get("source_object") or "")
        host_id, host_oid = (snap.attached_to, snap.attached_object) if snap is not None else (None, None)
    found: list[dict[str, Any]] = []
    card = plan.state.cards.get(host_id or "")
    if host_id and host_oid:
        if card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == host_oid:
            found.append(ObjectRef(card=host_id, object_id=host_oid, zone=card.zone).model_dump(mode="json"))
        elif (was := r.lki.get(host_oid)) is not None:
            found.append(ObjectRef(card=host_id, object_id=host_oid, zone=was.zone, snapshot=was).model_dump(mode="json"))
    context.refs(ctx)[str(e["as"])] = {"kind": "objects", "objects": found}
    return True


# -- bounces -- "Return enchanted creature and this Aura to their owners' hands." (Disappear), "When enchanted creature attacks, return it and this Aura to their owners'
# hands at end of combat." (Contempt: a delayed trigger, 603.7, 511.2; "it" is the attacking creature the trigger is about, the Aura the source — each only while still
# that object, 400.7): both in one move (one event, 603.2c); "Return enchanted creature and all Auras attached to that creature to their owners' hands." (Mark of
# Eviction): the creature and every Aura on it as the ability resolves, at once
_BOUNCE_BOTH = re.compile(r"^return (?:(?P<host>enchanted creature) and ~ to their owners' hands|(?P<it>it) and ~ to their owners' hands at end of combat"
                          r"|(?P<all>enchanted creature and all auras attached to that creature) to their owners' hands)$", re.I)


def _bounce_both(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import delayed

    if m["host"]:
        return [{"do": "bounce", "who": "union:host+self"}], None
    if m["all"]:
        return [{"do": "bounce_host_auras100f"}], None
    return delayed.wrap_when([{"do": "bounce", "who": "union:event+self"}], delayed.END_OF_COMBAT), None


def bounce_host_auras(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    hosts = effects._cards(plan, ctx, "host")
    auras = [c.id for c in plan.state.cards.values() if hosts and c.attached_to == hosts[0] and c.zone.endswith(":battlefield")
             and "Aura" in plan.ch(c).subtypes]
    if hosts:
        plan.do({"type": "move", "card_ids": [*hosts, *auras], "to": {"zone": "hand"}}, actor=ctx["controller"])
    return True


# "unattach it" (Tamiyo's Compleation: "If it's an Equipment, unattach it." — 701.3d)
_UNATTACH = re.compile(r"^unattach it$")


def _unattach(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "unattach_it100f", "who": "it"}], None


# "target player sacrifices a creature of their choice other than enchanted creature" (Sporogenic Infection): 701.21a, the player chooses among their own; the
# enchanted creature (as the ability resolves, or as the Aura last existed: 608.2h) isn't among the choices
_EDICT_NOT_HOST = re.compile(r"^(?P<who>target player|target opponent|each opponent|each player) sacrifices an? (?P<sel>[a-z ]+?) of their choice other than enchanted creature$")


def _edict_not_host(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    found = _clause(f"{m['who']} sacrifices a {m['sel']} of their choice")
    if found is None or len(found[0]) != 1 or found[0][0]["do"] != "edict":
        raise _NoMatch
    return [{"do": "bind_host100f", "as": HOST}, {**found[0][0], "except_ref": HOST}], found[1]


# "you may have enchanted creature fight target creature an opponent controls" (Cartouche of Strength): the optional instruction "enchanted creature fights …"
# (701.14; the rulings: with the target gone or the creature gone, no one fights; with the Aura gone, the creature it last enchanted still fights, 608.2h)
_HAVE_FIGHT = re.compile(r"^have (?P<s>enchanted creature|equipped creature) fight (?P<o>target [^,.\"]+)$")


def _have_fight(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    found = _clause(f"{m['s']} fights {m['o']}")
    if found is None or [e["do"] for e in found[0]] != ["fight"]:
        raise _NoMatch
    return found


TEMPLATES = [(_LOSE, _lose), (_AND_GROUP, _and_group), (_EQUIPPED_AND_EQUIPMENT, _equipped_and_equipment), (_HOST_DAMAGE, _host_damage),
             (_BOUNCE_BOTH, _bounce_both), (_UNATTACH, _unattach), (_EDICT_NOT_HOST, _edict_not_host), (_HAVE_FIGHT, _have_fight)]
PRIMITIVES = {"unattach_it100f": unattach_it, "bind_host100f": bind_host, "bounce_host_auras100f": bounce_host_auras}
RESUME: dict[str, Any] = {}
