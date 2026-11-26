"""CR 611.2, 614: trigger-bound damage replacements lasting until the controller's next turn."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    m = re.fullmatch(r"until your next turn, (?P<body>if .+)", body.strip().rstrip('.'), re.I)
    if m is None:
        return None
    text = m['body']
    recipient = 'that player or a permanent that player controls'
    if text.count(recipient) != 1:
        return None
    from app.rules import replace_grammar

    text = text.replace(recipient, 'a permanent or player')
    definition = replace_grammar.parse(text[0].upper() + text[1:] + '.')
    if definition is None or definition.get('event') != 'damage' or definition['op'].get('do') != 'mul':
        return None
    return ([{'do': 'replace_record', 'event': 'damage', 'match': definition['match'], 'op': definition['op'],
              'who': 'event_player', 'include_controlled_permanents': True, 'duration': 'next_turn'}], None, False)


def active(plan: Plan, record: dict[str, Any]) -> bool:
    """Shared modern/legacy record liveness; a next-turn record survives intervening turns."""
    if record.get('until') == 'source_on_battlefield':
        from app.rules import delayed

        return delayed._source_ok(plan, 'source_on_battlefield', record.get('source_card'), record.get('source'), record.get('controller'))
    if record.get('until') == 'game':  # -- planechase deck (wave D) -- "prevent all damage … this game" (Mount Keralia's chaos ability)
        return True
    turn = plan.state.turn.number
    if record.get('until') == 'next_turn':
        return not (record.get('until_player') == plan.active and turn > int(record.get('turn') or 0))
    return record.get('turn') == turn


def turn_began(plan: Plan, skipped: list[tuple[str, int]] | None = None) -> None:
    ended = {(plan.active, plan.state.turn.number), *(skipped or ())}
    plan.rules.replacements = [rec for rec in plan.rules.replacements if not (
        rec.get('until') == 'next_turn' and any(rec.get('until_player') == player and turn > int(rec.get('turn') or 0)
                                              for player, turn in ended))]


def expire_source_records(plan: Plan) -> None:
    """611.2b, 702.26f: source tracking durations end irreversibly."""
    plan.rules.replacements = [record for record in plan.rules.replacements
                               if record.get('until') != 'source_on_battlefield' or active(plan, record)]
