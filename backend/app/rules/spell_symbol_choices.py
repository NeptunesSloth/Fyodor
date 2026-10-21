"""Private, replayable CR 601.2b announcements for a concrete spell mana cost."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.actions import CastSpell
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan
    from app.rules.spell_cost_stages import PreparedCost

PAGE = 100


def announce(plan: Plan, a: CastSpell, card: CardInstance, ch: Characteristics, prepared: PreparedCost, *, start: int = 0) -> bool:
    from app.game.errors import ActionError
    from app.game.rules_state import DecisionOption
    from app.rules import casting, spell_cost_stages
    from app.rules.plan import decide

    if a.mana_symbols is not None:
        life = spell_cost_stages.life_symbols(prepared.raw, a.mana_symbols)
        if a.life_symbols is not None and sorted(a.life_symbols) != sorted(life):
            raise ActionError('The announced life payment must match the Phyrexian mana choices')
        if 2 * len(life) > casting.spendable_life(plan.state, plan.actor, plan.info) - plan.reserved_life:
            raise ActionError('The announced Phyrexian life payment cannot be paid')
        a.life_symbols = life
        plan.reserved_life += 2 * len(life)
        return False
    ways = spell_cost_stages.variants(prepared.raw)
    if a.life_symbols is not None:
        ways = [w for w in ways if sorted(spell_cost_stages.life_symbols(prepared.raw, w)) == sorted(a.life_symbols)]
    available_life = casting.spendable_life(plan.state, plan.actor, plan.info) - plan.reserved_life
    ways = [w for w in ways if 2 * len(spell_cost_stages.life_symbols(prepared.raw, w)) <= available_life]
    if not ways:
        raise ActionError('No legal mana-symbol announcement can be paid with the available life')
    if len(ways) == 1:
        a.mana_symbols = ways[0]
        a.life_symbols = spell_cost_stages.life_symbols(prepared.raw, ways[0])
        plan.reserved_life += 2 * len(a.life_symbols)
        return False
    options = []
    for i in range(start, min(start + PAGE, len(ways))):
        due = spell_cost_stages.concrete(prepared.raw, ways[i])
        life_due = 2 * len(spell_cost_stages.life_symbols(prepared.raw, ways[i]))
        options.append(DecisionOption(id=str(i), label=f'Mana symbols: {due.text()}' + (f' and {life_due} life' if life_due else '')))
    if start:
        options.append(DecisionOption(id=f'page:{max(0, start-PAGE)}', label='Previous announcements'))
    if start + PAGE < len(ways):
        options.append(DecisionOption(id=f'page:{start+PAGE}', label='More announcements'))
    decide(plan, player=plan.actor, kind='choose_one', prompt=f'{ch.name}: choose how to pay its mana symbols',
           options=options, resume=casting._announcing(plan, 'spell_symbols', a, options=ways), source=card)
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game import actions as A
    from app.rules import casting
    from app.rules.engine import INTENTS

    if casting.cancelled(plan, d, chosen):
        return
    intent = A.parse_action(d.resume['intent'])
    assert isinstance(intent, A.CastSpell)
    plan.rules.priority = d.player
    plan.rules.passed = []
    if chosen[0].startswith('page:'):
        # Page the already computed announcements without recomputing costs or changing resources.
        from app.game.rules_state import DecisionOption
        from app.rules.plan import decide

        start = int(chosen[0][5:])
        ways = d.resume['options']
        options = [DecisionOption(id=str(i), label=', '.join(ways[i])) for i in range(start, min(start+PAGE, len(ways)))]
        if start:
            options.append(DecisionOption(id=f'page:{max(0, start-PAGE)}', label='Previous announcements'))
        if start + PAGE < len(ways):
            options.append(DecisionOption(id=f'page:{start+PAGE}', label='More announcements'))
        decide(plan, player=d.player, kind='choose_one', prompt=d.prompt, options=options, resume=d.resume)
        return
    intent.mana_symbols = d.resume['options'][int(chosen[0])]
    INTENTS[intent.type](plan, intent)
