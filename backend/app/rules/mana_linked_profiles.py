"""Mana production tied to an exact source's native linked exile scope."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules import mana as M
    from app.rules.plan import Plan


def parse_mana(text: str, identity: tuple[str, ...], name: str) -> M.ManaAbility | None:
    from app.rules import mana as M
    from app.rules import scripts

    if scripts.self_text(text, name) == '{T}: Add {C}. If a card is exiled with ~, add {C}{C} instead.':
        return M.ManaAbility(tap=True, sacrifice_self=False, options=(('C',),), native_body=True, chooses=True,
            immediate_effects=({'do': 'linked_colorless_production'},))
    return None


def linked_colorless(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import exiled_with, immediate_mana_resolutions

    n = 2 if exiled_with.cards(plan, ctx) else 1
    immediate_mana_resolutions.produce_chosen(plan, ctx, ctx['controller'], ['C'] * n)
    return False


PRIMITIVES = {'linked_colorless_production': linked_colorless}
