"""Mana bodies whose separate reflexive triggers wait for priority."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules import mana as M
    from app.rules.plan import Plan


def parse_mana(text: str, identity: tuple[str, ...], name: str) -> M.ManaAbility | None:
    from app.rules import mana as M
    from app.rules import scripts

    own = scripts.self_text(text, name)
    if own == '{X}, {T}, Sacrifice ~: Add X mana in any combination of colors.':
        return M.ManaAbility(tap=True, sacrifice_self=True, options=((),), extra_cost='{X}',
            chooses=True, native_body=True, immediate_effects=({'do': 'mana_composition', 'of': list(M.COLORS)},))
    first, sep, tail = own.partition(' When you do, ')
    if sep and tail in ('~ deals 1 damage to each opponent.', 'mill two cards.'):
        base = M.parse_mana_ability(first, identity, card_name=name)
        parsed = scripts.parse_effects(tail)
        if base is not None and parsed is not None and parsed[1] is None and not parsed[2]:
            return replace(base, immediate_effects=(*base.immediate_effects,
                {'do': 'mana_reflexive', 'effects': parsed[0]}))
    if own == '{T}: Add one mana of any color. Roll a d20.':
        base = M.parse_mana_ability('{T}: Add one mana of any color.', identity, card_name=name)
        return replace(base, immediate_effects=({'do': 'roll', 'sides': 20, 'count': 1},)) if base else None
    return None


def reflexive(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import triggers

    # Reaching this body means the entire activation cost was paid. Unlike an
    # immediate mill instruction, this creates a separate normal stack ability.
    triggers._add(plan, controller=ctx['controller'], source_card=ctx['source_card'],
        source_object=ctx['source_object'], name=ctx['name'], index=7300,
        definition={'effects': e['effects']}, event=None)
    return True


PRIMITIVES = {'mana_reflexive': reflexive}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == 'spell' and text == "Counter target spell. Clash with an opponent. If you win, at the beginning of your next main phase, you may add an amount of {C} equal to that spell's mana value.":
        base = scripts.define(replace(ability, text="Counter target spell. At the beginning of your next main phase, add an amount of {C} equal to that spell's mana value."), ch)
        if base is not None:
            counter, delayed, mana = base['effects']
            return {**base, 'effects': [counter, {'do': 'clash'},
                {'do': 'only_if', 'cond': {'coin': 'win', 'of': 'clash'}, 'skip': 2},
                delayed, {'do': 'deferred:optional_mana_output', 'effect': {**mana, 'do': 'add_mana'}}]}
    if ability.kind == 'activated' and text == '{T}: Target player adds two mana of any one color. The next spell they cast this turn has cascade.':
        base = scripts.define(replace(ability, text='{T}: Target player adds two mana of any one color.'), ch)
        if base is not None:
            return {**base, 'effects': [*base['effects'], {'do': 'target_next_spell_grant', 'keyword': 'cascade'}]}
    if ability.kind == 'triggered' and text == 'Whenever you roll one or more dice, put a number of charge counters on ~ equal to the result.':
        base = scripts.define(replace(ability, text='Whenever you roll one or more dice, draw a card.'), ch)
        if base is not None:
            return {**base, 'effects': [{'do': 'dice_result_counters', 'kind': 'charge'}]}
    attack = ('Whenever ~ or equipped creature attacks, add an amount of {G} equal to its power. '
              "Until end of turn, you don't lose this mana as steps and phases end.")
    if ability.kind == 'triggered' and text == attack:
        base = scripts.define(replace(ability, text=text.replace('its power', "~'s power")), ch)
        if base is not None:
            # The event creature can be the Equipment or its equipped host. Keep
            # the Equipment as mana producer, and read the attacker via event LKI.
            base['effects'][0]['n'] = {'power': 'event'}
            return base
    return None


def composition(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    return _composition(plan, ctx, e['of'], max(0, int(ctx.get('x') or 0)), [])


def _composition(plan: Plan, ctx: dict[str, Any], colors: list[str], left: int, got: list[str]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import immediate_mana_resolutions
    from app.rules.plan import decide

    if left == 0:
        immediate_mana_resolutions.produce_chosen(plan, ctx, ctx['controller'], got)
        return False
    decide(plan, player=ctx['controller'], kind='choose_one', prompt=f'Choose a color ({left} mana remaining)',
        options=[DecisionOption(id=c, label='{'+c+'}') for c in colors],
        resume={'step': 'mana_composition', 'ctx': ctx, 'colors': colors, 'left': left, 'got': got})
    return False


def resume_composition(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    _composition(plan, r['ctx'], r['colors'], r['left'] - 1, [*r['got'], chosen[0]])


PRIMITIVES['mana_composition'] = composition
RESUME = {'mana_composition': resume_composition}


def target_next_spell_grant(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, spell_grants

    for player in effects._players(plan, ctx, 'target'):
        spell_grants.next_spell_grant(plan, {**ctx, 'controller': player},
            {'grants': [{'keyword': e['keyword'], 'what': '', 'filter': None}]})
    return True


PRIMITIVES['target_next_spell_grant'] = target_next_spell_grant


def optional_output(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    decide(plan, player=ctx['controller'], kind='choose_one', prompt='Add the mana?',
        options=[DecisionOption(id='yes', label='Add the mana'), DecisionOption(id='no', label='Decline')],
        resume={'step': 'optional_mana_output', 'ctx': ctx, 'effect': e['effect']})
    return False


def resume_optional_output(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume['ctx']
    if chosen[0] == 'yes':
        ctx['effects'][ctx['next']:ctx['next']] = [d.resume['effect']]
    effects.continue_effects(plan, ctx)


PRIMITIVES['optional_mana_output'] = optional_output
RESUME['optional_mana_output'] = resume_optional_output


def dice_result_counters(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    total = (ctx.get('event') or {}).get('dice_total')
    if total is None:
        from app.game.rules_state import DecisionOption
        from app.rules.plan import decide

        decide(plan, player=ctx['controller'], kind='manual_resolution',
            prompt='This older roll did not record its numerical result total. Put the appropriate counters on the source by hand, then press Done.',
            options=[DecisionOption(id='done', label='Done')],
            resume={'step': 'mana_legacy_roll_done', 'ctx': ctx})
        return False
    if total > 0:
        ctx['effects'][ctx['next']:ctx['next']] = [{'do': 'add_counters', 'who': 'self', 'kind': e['kind'], 'n': total}]
    return True


def legacy_roll_done(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    effects.continue_effects(plan, d.resume['ctx'])


PRIMITIVES['dice_result_counters'] = dice_result_counters
RESUME['mana_legacy_roll_done'] = legacy_roll_done
