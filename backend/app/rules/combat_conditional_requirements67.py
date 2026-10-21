"""Source-origin conditional attack requirements, frozen from the proposed declaration."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.plan import Plan

PREFIX = 'conditional_attack67:'


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts, selectors, statics

    text = scripts.self_text(ability.text, ch.name)
    if text == 'If a creature an opponent controls attacks, all creatures that opponent controls attack if able.':
        controller, condition = 'opponent', 'any'
    elif text in ('If this creature attacks, all creatures you control attack if able.',
                  'If ~ attacks, all creatures you control attack if able.'):
        controller, condition = 'you', 'source'
    else:
        return None
    return statics._definition(selectors.Selector(types=('Creature',), controller=controller).key(), None, [],
                               rules=[PREFIX + '@src:' + condition])


def score(plan: Plan, ch: Characteristics, declared: dict[str, str], target: str | None) -> int:
    if target is None:
        return 0
    from app.rules import attack_requirements

    value = 0
    for rule, count in attack_requirements.counts(ch).items():
        if not rule.startswith(PREFIX):
            continue
        source, _, condition = rule[len(PREFIX):].rpartition(':')
        if (condition == 'any' and declared) or (condition == 'source' and source in declared):
            value += count
    return value
