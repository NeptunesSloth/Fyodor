"""Kicked target cardinality uses native groups and actual move receipts."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    if body == "Exile up to two target cards from a single graveyard. If this spell was kicked, instead exile target player's graveyard. Create a 2/2 black Rogue creature token for each creature card exiled this way.":
        base = scripts.parse_effects("Exile up to two target cards from a single graveyard. Create a 2/2 black Rogue creature token for each creature card exiled this way.")
        alternate = scripts.parse_effects("Exile target player's graveyard.")
        if base is None or alternate is None:
            return None
        groups = [{**base[1][0], "kicked": False}, {"what": alternate[1], "kicked": True}]
        alt = scripts._renumber(alternate[0], [1])[0]
        effects = [{"do": "kicked_gate", "kicked": False, "n": 1}, base[0][0],
                   {"do": "kicked_gate", "kicked": True, "n": 1}, {**alt, "as": base[0][0]["as"]}, base[0][1]]
        return effects, groups, False
    if body == "Choose target creature you own. If this spell was kicked, instead choose any number of target creatures you own. Return each chosen creature to your hand. At the beginning of the next upkeep, create a 4/4 white Bird Soldier creature token with flying for each creature returned to your hand this way.":
        targets = scripts.parse_effects("Return any number of target creatures you own to your hand.")
        delayed = scripts.parse_effects("At the beginning of the next upkeep, create a 4/4 white Bird Soldier creature token with flying.")
        if targets is None or delayed is None:
            return None
        group = targets[1][0]
        groups = [{**group, "min": 1, "max": 1, "kicked": False}, {**group, "kicked": True}]
        return ([{"do": "bounce", "who": "all_targets", "as": "returned60"},
                 {"do": "freeze_returned_count60", "ref": "ref:returned60", "bind": "returned60_amount"},
                 delayed[0][0], {**delayed[0][1], "n": {"ref_amount": "returned60_amount"}}], groups, False)
    return None


def freeze_returned(plan: Any, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import context, history

    binding = (ctx.get("refs") or {}).get(effect["ref"].removeprefix("ref:")) or {}
    original = {row["object_id"] for row in binding.get("was") or [] if str(row.get("zone") or "").endswith(":battlefield")}
    arrived = {departure.object_id for departure in history.log_for(plan).left if departure.to == "hand"}
    context.bind_amount(ctx, effect["bind"], len(original & arrived))
    return True


PRIMITIVES = {"freeze_returned_count60": freeze_returned}
