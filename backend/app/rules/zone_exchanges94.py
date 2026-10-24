"""Whole original hidden/public zone cohorts move in one prepared replacement event."""

from __future__ import annotations

from typing import Any

from app.game.rules_state import DecisionOption
from app.rules.plan import Plan, decide


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == "Exchange your hand and graveyard.":
        return {
            "kind": "spell",
            "target": None,
            "effects": [{"do": "exchange_zones94", "zones": ["hand", "graveyard"]}],
        }
    if text == "Exchange your graveyard and library. Then shuffle your library.":
        return {
            "kind": "spell",
            "target": None,
            "effects": [
                {"do": "exchange_zones94", "zones": ["graveyard", "library"]},
                {"do": "shuffle_library", "who": "you"},
            ],
        }
    return None


def exchange(plan: Plan, ctx: Any, e: Any) -> bool:
    from app.rules import replacements

    pid = ctx["controller"]
    frame = ctx.get("zone_exchange94")
    if frame is None:
        first, second = e["zones"]
        frame = {
            "cards": [
                {"card": cid, "oid": plan.oid(plan.state.cards[cid]), "from": f"{pid}:{zone}", "to": dest}
                for zone, dest in ((first, second), (second, first))
                for cid in plan.state.zones.get(f"{pid}:{zone}", [])
            ],
            "routes": {},
            "next": 0,
            "candidates": {},
            "prepared": {},
        }
        ctx["zone_exchange94"] = frame
    if any(
        (c := plan.state.cards.get(row["card"])) is None or c.zone != row["from"] or plan.oid(c) != row["oid"]
        for row in frame["cards"]
    ):
        ctx.pop("zone_exchange94", None)
        plan.note("The original zone exchange cannot be completed")
        return True
    while frame["next"] < len(frame["cards"]):
        row = frame["cards"][frame["next"]]
        card = plan.state.cards[row["card"]]
        if row["to"] in ("hand", "library"):
            command = replacements._commander_instead(plan, card, row["to"])
            if command is None:
                decide(
                    plan,
                    player=card.owner,
                    kind="confirm",
                    prompt=f"Your commander would enter your {row['to']}: put it into the command zone instead? (903.9b)",
                    options=[
                        DecisionOption(id="yes", label="Command zone"),
                        DecisionOption(id="no", label=f"Into your {row['to']}"),
                    ],
                    resume={
                        "step": "exchange_zones94",
                        "ctx": ctx,
                        "e": e,
                        "commander": f"{row['oid']}>{row['to']}",
                    },
                    memory_key=f"commander_zone:{card.commander_key}",
                    memory_context=row["to"],
                )
                return False
            frame["routes"][card.id] = {"player": card.owner, "zone": "command" if command else row["to"]}
        else:
            # Moving a hand card into a graveyard is not necessarily discarding it.
            # Prepare only actual zone-change replacements, never madness/discard replacements.
            candidates = frame["candidates"].setdefault(
                card.id,
                [
                    c._asdict()
                    for c in {c.sig: c for c in replacements.zone_candidates(plan, card, row["to"])}.values()
                ],
            )
            if len(candidates) > 1 and card.id not in frame["prepared"]:
                decide(
                    plan,
                    player=card.owner,
                    kind="choose_one",
                    prompt=f"{card.name}: which graveyard replacement applies first? (616.1)",
                    options=[DecisionOption(id=str(i), label=c["label"]) for i, c in enumerate(candidates)],
                    resume={"step": "exchange_zones94", "ctx": ctx, "e": e, "candidate": card.id},
                )
                return False
            selected = frame["prepared"].get(card.id, candidates[0] if candidates else None)
            frame["prepared"][card.id] = selected
            outcome = selected["outcome"] if selected else row["to"]
            frame["routes"][card.id] = {"player": card.owner, "zone": outcome.split(":")[0]}
        frame["next"] += 1
    routes = frame["routes"]
    positions = {
        cid: ("bottom" if raw["outcome"].endswith(":bottom") else "top")
        for cid, raw in frame["prepared"].items()
        if raw and raw["outcome"].startswith("library:")
    }
    ordered = frame.setdefault("ordered", {})
    # Morality Shift shuffles the resulting library; other replacement piles retain
    # their owners' private order, chosen before this original cohort moves.
    if e["zones"] != ["graveyard", "library"]:
        for owner in plan.apnap():
            for place in ("top", "bottom"):
                key = f"{owner}:{place}"
                pile = [
                    cid
                    for cid, pos in positions.items()
                    if pos == place and plan.state.cards[cid].owner == owner
                ]
                if key in ordered:
                    continue
                if len(pile) < 2:
                    ordered[key] = pile
                    continue
                decide(
                    plan,
                    player=owner,
                    kind="order",
                    prompt=f"Order the cards for the {place} of your library",
                    options=[
                        DecisionOption(id=cid, label=plan.state.cards[cid].name or "Card", card_id=cid)
                        for cid in pile
                    ],
                    min_choices=len(pile),
                    max_choices=len(pile),
                    resume={"step": "exchange_zones94", "ctx": ctx, "e": e, "order": key},
                )
                return False
    order = []
    for owner in plan.apnap():
        order += ordered.get(f"{owner}:top", [])
        order += list(reversed(ordered.get(f"{owner}:bottom", [])))
    if routes:
        from app.rules import graveyard_order, replace

        # Table move actions have a 250-card transport bound. Prepare every route
        # first, then commit transport chunks as one native instruction/event.
        payload = {
            "type": "move",
            "non_discard": True,
            "card_ids": list(routes),
            "to": {"player": pid, "zone": "graveyard"},
            "routes": routes,
        }
        before = graveyard_order.before(plan, payload)
        order_start = len(plan.rules.pending_gy_order)
        batch = plan.rules.batch
        ids = list(routes)
        for offset in range(0, len(ids), 250):
            chunk = ids[offset : offset + 250]
            plan.do(
                {
                    **payload,
                    "card_ids": chunk,
                    "routes": {cid: routes[cid] for cid in chunk},
                    "library_positions": {cid: positions[cid] for cid in chunk if cid in positions},
                    "library_order": [cid for cid in order if cid in chunk],
                },
                actor=pid,
            )
        if len(ids) > 250:
            replace._one_batch(plan, batch)
            del plan.rules.pending_gy_order[order_start:]
            if before is not None:
                graveyard_order.after(plan, before)
    shuffles = set()
    riders = []
    for row in frame["cards"]:
        raw = frame["prepared"].get(row["card"])
        if raw is None:
            continue
        candidate = replacements.Cand(**raw)
        replacements._record_link(plan, row["card"], candidate)
        if candidate.counter:
            replacements.mark_exiled_counters(plan, [row["card"]], candidate.counter, actor=pid)
        if candidate.rider:
            riders.append(candidate.rider)
        if candidate.outcome == "library:shuffle":
            shuffles.add(routes[row["card"]]["player"])
    for owner in sorted(shuffles):
        plan.do({"type": "shuffle", "player": owner, "zone": "library"}, actor=owner)
    for rider in riders:
        replacements.run_rider(plan, rider)
    ctx.pop("zone_exchange94", None)
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    r = d.resume
    if r.get("commander"):
        plan.rules.answers_903_9b[r["commander"]] = chosen[0]
    elif r.get("order"):
        r["ctx"]["zone_exchange94"]["ordered"][r["order"]] = chosen
    else:
        frame = r["ctx"]["zone_exchange94"]
        frame["prepared"][r["candidate"]] = frame["candidates"][r["candidate"]][int(chosen[0])]
    if exchange(plan, r["ctx"], r["e"]):
        continue_effects(plan, r["ctx"])


PRIMITIVES = {"exchange_zones94": exchange}
RESUME = {"exchange_zones94": resume}
