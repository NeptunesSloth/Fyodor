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


def next_kind(plan: Plan, job: dict[str, Any], batch: dict[str, Any], *, name: str = 'the spell', targets: bool = True) -> str | None:
    """Choose where the replacement's freely targeted additional copies are inserted.

    A pending kind stays in the saved batch while a subsequent target/mode choice
    pauses. It is consumed only when that copy has actually been made.
    -- pod audit -- asked only when the copied spell has targets (``targets``): the additional copy differs from the others only in that
    its targets may be changed (707.10c), so for a spell without targets (Raise the Alarm) the order means nothing.
    """
    if batch.get('next_kind'):
        return str(batch['next_kind'])
    if batch['left'] > 0 and batch.get('additional', 0) > 0 and targets:
        from app.game.rules_state import DecisionOption
        from app.rules.copying import plan_decide

        plan_decide(plan, player=job['controller'], kind='choose_one',
                    prompt=f'{name}: which copy goes on the stack next? (the last one there resolves first)',
                    options=[DecisionOption(id='original', label=f"A copy ({'may choose new targets' if job.get('retarget') else 'same targets'})"),
                             DecisionOption(id='additional', label=f'{_source(plan, job["controller"])} (may choose new targets)')],
                    resume={'step': 'copy_order', 'job': job})
        return None
    return 'original' if batch['left'] > 0 else 'additional'


def _source(plan: Plan, controller: str) -> str:
    """"Twinning Staff's additional copy" (the permanent on the battlefield that adds it), or "The additional copy" when several do."""
    from app.rules.permissions import _table_statics

    names = {name for source, _, d in _table_statics(plan.state, plan.info, {'additional_spell_copy'})
             if source.controller == controller and (name := plan.ch(source).name)}  # (a copy of Twinning Staff by its copied name, 707.2)
    return f"{next(iter(names))}'s additional copy" if len(names) == 1 else 'The additional copy'
