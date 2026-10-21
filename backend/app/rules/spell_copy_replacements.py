"""CR 614.1a, 614.5, 707.10: additional copies per spell-copying event.

Each applicable permanent replaces an event once, adding one copy to the batch.
Copying a card or an activated/triggered ability is a different event.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_WORDING = re.compile(
    r'if you would copy a spell one or more times, instead copy it that many times plus an additional time\. '
    r'[Yy]ou may choose new targets for the additional copy')


def definition(text: str) -> dict[str, Any] | None:
    return {'kind': 'static', 'static': 'additional_spell_copy', 'n': 1, 'retarget': True, 'effects': []} \
        if _WORDING.fullmatch(text) else None


def additional(plan: Plan, controller: str) -> int:
    from app.rules.permissions import _table_statics

    return sum(int(d['n']) for source, _, d in _table_statics(plan.state, plan.info, {'additional_spell_copy'})
               if source.controller == controller)


def prepare(plan: Plan, job: dict[str, Any], batch: dict[str, Any], *, ability: bool) -> None:
    """Replace this nonempty copying event once, before any of its copies are made."""
    if batch.get('copy_replacement_prepared'):
        return
    batch['copy_replacement_prepared'] = True
    batch['additional'] = additional(plan, job['controller']) \
        if not ability and batch['left'] > 0 and not job.get('replacements_done') else 0


def next_kind(plan: Plan, job: dict[str, Any], batch: dict[str, Any]) -> str | None:
    """Choose where the replacement's freely targeted additional copies are inserted.

    A pending kind stays in the saved batch while a subsequent target/mode choice
    pauses. It is consumed only when that copy has actually been made.
    """
    if batch.get('next_kind'):
        return str(batch['next_kind'])
    if batch['left'] > 0 and batch.get('additional', 0) > 0:
        from app.game.rules_state import DecisionOption
        from app.rules.copying import plan_decide

        plan_decide(plan, player=job['controller'], kind='choose_one',
                    prompt='Put the next copy on the stack: original or additional copy?',
                    options=[DecisionOption(id='original', label='Original copy'),
                             DecisionOption(id='additional', label='Additional copy (may choose new targets)')],
                    resume={'step': 'copy_order', 'job': job})
        return None
    return 'original' if batch['left'] > 0 else 'additional'
