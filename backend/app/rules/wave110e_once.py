"""-- wave 110E -- "The next time one or more enchantment creatures you control enter this turn, each enters with two additional +1/+1 counters on it." (Storyweave).

614.1c: a one-shot replacement of the entering event; 614.12: it applies to every matching permanent of that one event (``replacements.move_together``), then it is
used up. The counters ride the ``entry_counters`` layer-6 effect the Cavern-style riders use (casting_timing_permissions.entering_counters); the effect is removed
after the first entry event that had a matching permanent, or at end of turn.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def arm(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import layers

    layers.add_effect(plan, affected=[], layer="6", source=ctx.get("source_object"), controller=ctx["controller"], duration="end_of_turn",
                      who=e["sel"], source_card=ctx.get("source_card"), entry_counters={e["kind"]: e["n"]}, entry_once110e=True, label=ctx.get("name") or "Next entry")
    return True


def spend(plan: Plan, entered: list[str]) -> None:
    """After one entry event: the armed one-shots with a matching permanent among ``entered`` are used up."""
    from app.rules import selectors

    for fx in [f for f in plan.rules.effects if f.entry_once110e]:
        for cid in entered:
            card = plan.state.cards.get(cid)
            if card is not None and card.zone.endswith(":battlefield") and fx.who and selectors.matches(
                    plan, selectors.from_key(fx.who), card, plan.ch(card), fx.controller, fx.source_card):
                plan.rules.effects = [f for f in plan.rules.effects if f.id != fx.id]
                break


PRIMITIVES: dict[str, Any] = {"next_entry_counters110e": arm}


def radiate(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Radiate: 707.10d, a copy of the targeted spell for each other permanent or player it could target (every "target" legal), each copy targeting that one (the stack_extension103 spread)."""
    from app.rules import copying, spell_copy_replacements, targets

    found = next(iter(copying._copy_sources(plan, ctx, "target")), None)
    if found is None:
        return True  # the target spell is gone: Radiate does nothing (608.2b)
    source, oid = found
    card = plan.state.cards.get(source)
    entry = copying.source_entry102(plan, card, oid) if card is not None else None
    if card is None or entry is None or not copying.positions(entry):
        return True
    reason = copying.uncopyable(plan, card, object_id=oid)
    if reason is not None:
        return True if not reason else copying._manual_each(plan, ctx, ctx["controller"], card)
    pos = copying.positions(entry)
    old = {t.id for t in entry.targets}
    caster = entry.controller
    source_ch = targets.source_of(plan, source, True, object_id=oid)
    victims = []
    for cid in [*plan.live(), *(c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield"))]:
        if cid in old or any(cid not in targets.legal_targets(plan, copying._spec(entry, p).get("what", "any"), caster, source_ch, source, source_object=oid) for p in pos):
            continue
        probe = copying._retargeted(entry, pos, [targets.ref(plan, cid)] * len(pos))
        probe.controller = caster
        if copying._problem(plan, probe) is None:
            victims.append(cid)
    if not victims:
        return True
    return copying._each_run(plan, {"ctx": ctx, "spell": source, "oid": oid, "controller": ctx["controller"], "victims": victims,
                                    "additional": spell_copy_replacements.additional(plan, ctx["controller"])})


PRIMITIVES["radiate110e"] = radiate


def chill(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Winter's Chill: "For each of those creatures, its controller may pay {1} or {2}. If that player doesn't, destroy that creature at end of combat. If that
    player pays only {1}, prevent all combat damage that would be dealt to and dealt by that creature this combat." (118.12 / 608.2c: its controller decides, creature by
    creature.) Each creature becomes its own target group, then the instructions run for it: pay {2} (nothing more), else pay {1} (prevention), else destroy."""
    groups = ctx.setdefault("groups", [[]])
    block: list[dict[str, Any]] = []
    for t in [t for t in (groups[0] if groups else []) if t]:
        g = len(groups)
        groups.append([t])
        who, a, b = f"target:{g}", f"chill{g}a", f"chill{g}b"
        block += [{"do": "optional_payment", "who": who, "cost": "{2}", "bind": a},
                  {"do": "only_if", "cond": {"succeeded": a, "negate": True}, "skip": 6},
                  {"do": "optional_payment", "who": who, "cost": "{1}", "bind": b},
                  {"do": "only_if", "cond": {"succeeded": b}, "skip": 1},
                  {"do": "prevent_all", "scope": {"combat": True, "to_or_by": True}, "who": who, "role": "both", "duration": "end_of_combat"},
                  {"do": "only_if", "cond": {"succeeded": b, "negate": True}, "skip": 2},
                  {"do": "delayed", "when": {"kind": "step", "step": "end_combat", "whose": "next"}, "n": 1},
                  {"do": "deferred:destroy", "who": who}]
    ctx["effects"][ctx["next"]:ctx["next"]] = block
    return True


PRIMITIVES["chill110e"] = chill
