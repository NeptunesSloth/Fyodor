"""Original equipped/enchanted damage source as each death event happened."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.game.rules_state import ObjectRef


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import context, scripts

    text = scripts.self_text(ability.text, ch.name)
    scythe = "Whenever a creature dealt damage by equipped creature this turn dies, return that card to the battlefield under your control. Attach ~ to that creature."
    embrace = "Whenever a creature dealt damage by enchanted creature this turn dies, put a +1/+1 counter on that creature."
    if text not in (scythe, embrace):
        return None
    native = scripts.define(
        replace(ability, text="Whenever a creature dealt damage by ~ this turn dies, draw a card."), ch
    )
    assert native is not None
    cond = {**native["cond"], "damaged_by_host104": True}
    cond.pop("damaged_by_self")
    effects = (
        [
            {
                "do": "return_card",
                "who": context.EVENT_NEW,
                "to": "battlefield",
                "under": "you",
                "as": "reborn104",
            },
            {"do": "attach_to", "src": "self", "who": "ref:reborn104"},
        ]
        if text == scythe
        else [{"do": "add_counters", "who": context.PREFIX + context.EVENT_OTHER, "kind": "+1/+1", "n": 1}]
    )
    return {**native, "cond": cond, "effects": effects}


def host_then(plan: Any, watcher: Any, source_object: str, batch: int) -> ObjectRef | None:
    current = plan.state.cards.get(watcher.id)
    host = None
    if current is not None and plan.oid(current) == source_object and current.zone.endswith(":battlefield"):
        attached = plan.state.cards.get(current.attached_to or "")
        if attached is not None:
            host = ObjectRef(card=attached.id, object_id=plan.oid(attached), zone=attached.zone)
    # Reverse the exact pending native attachment events through the event's batch:
    # death looks back to immediately before that event (603.10a).
    for event in reversed(plan.rules.events):
        if event.object_id != source_object or event.batch < batch:
            continue
        if event.kind == "attached":
            host = None
        elif event.kind == "unattached" and event.by_card and event.source:
            host = ObjectRef(
                card=event.by_card, object_id=event.source, zone=f"{watcher.controller}:battlefield"
            )
    return host


def matches(
    plan: Any, watcher: Any, victim: str | None, info: dict[str, Any], source_object: str | None
) -> bool:
    from app.rules import history

    oid = source_object or plan.oid(watcher)
    host = host_then(plan, watcher, oid, int(info["batch"]))
    if host is None or victim is None:
        return False
    if not any(
        f.kind == "damaged" and f.object_id == victim and f.source == host.object_id and f.amount > 0
        for f in history.log_for(plan).facts
    ):
        return False
    info["damage_host104"] = host
    return True
