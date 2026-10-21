"""Double all positive counters a player has through native counter replacements."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    if body.strip().rstrip('.').casefold() == 'double the number of each kind of counter you have':
        return [{'do': 'double_player_counters', 'who': 'you'}], None, False
    return None


def double(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, replace

    # Speed is a player resource, but not a counter (702.179).
    puts = [(pid, kind, n) for pid in effects._players(plan, ctx, e['who'])
            for kind, n in plan.state.players[pid].resources.items() if n > 0 and kind != 'speed']
    return not puts or replace.put_counters(plan, puts, by=ctx['controller'], then=effects._then(ctx, e), ctx=ctx)


PRIMITIVES = {'double_player_counters': double}
