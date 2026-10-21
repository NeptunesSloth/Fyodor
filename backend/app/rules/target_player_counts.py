"""CR 608.2b, 608.2h: sum a count across a spell's still-legal player targets."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts, values

    m = re.fullmatch(r'Choose any number of target (?P<who>opponents|players)\. '
                     r'(?P<create>Create X .+? creature tokens), where X is the number of '
                     r'(?P<what>creatures|artifacts|enchantments|lands) those (?P=who) control\.', body)
    if m is None:
        return None
    chosen = scripts._parse_effects_plain(f"Choose any number of target {m['who']}.")
    created = scripts._parse_effects_plain(m['create'] + '.')
    count = values.parse_count(f"the number of {m['what']} you control")
    if chosen is None or created is None or count is None or created[1] is not None:
        return None
    if len(created[0]) != 1 or created[0][0]['do'] != 'create_token' or created[0][0]['n'] != {'x': 1}:
        return None
    return ([*chosen[0], {**created[0][0], 'n': {'sum_for_players': 'target:0', 'of': count}}], chosen[1], False)


def evaluate(plan: Plan, ctx: dict[str, Any], value: dict[str, Any]) -> int:
    from app.rules import values
    from app.rules.effects import target_refs

    # Resolution has already removed illegal targets from these groups (608.2b).
    players = {t['id'] for t in target_refs(ctx, value['sum_for_players']) if t['id'] in plan.live()}
    return sum(values.evaluate(plan, {**ctx, 'controller': pid}, value['of']) for pid in players)
