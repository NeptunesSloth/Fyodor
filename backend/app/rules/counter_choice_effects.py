"""Printed counter-kind choices, captured by recipient object before a simultaneous placement."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, TypedDict

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan


class ChoiceFrame(TypedDict):
    objects: list[dict[str, Any]]
    chosen: list[str]


def parse_sentence(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    from app.rules import counter_choice, language

    each = text.startswith('for each of them, ')
    if each:
        text = text[len('for each of them, '):]
    m = re.fullmatch(r'put (?P<fixed>a \+1/\+1 counter and a counter from among )?(?:your choice of )?(?P<kinds>.+) on (?P<who>.+)', text)
    if m is None or (kinds := counter_choice.kinds_of(m['kinds'])) is None:
        return None
    if each and m['who'] != 'it':
        return None
    kind, key, group = language.ref('them' if each else m['who'])
    if kind not in ('self', 'host', 'it', 'them', 'target', 'each'):
        return None
    return [{'do': 'counter_kind_choice', 'who': language._who(kind, key), 'kinds': kinds,
             **({'fixed': '+1/+1'} if m['fixed'] else {})}], language._one(group)


_KEY = '_counter_kind_choices'


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, replace
    from app.rules.plan import decide

    key = str(int(ctx.get('next') or 0) - 1)
    frames = ctx.setdefault(_KEY, {})
    if key not in frames:
        frame: ChoiceFrame = {'objects': [captured_ref.model_dump(mode='json') for cid in effects._cards(plan, ctx, e['who'])
                                         if (captured_ref := context.ref_of(plan, cid)) is not None], 'chosen': []}
        frames[key] = frame
    frame = frames[key]
    while len(frame['chosen']) < len(frame['objects']):
        ref = frame['objects'][len(frame['chosen'])]
        current = plan.state.cards.get(ref['card'])
        if current is None or plan.oid(current) != ref['object_id'] or not current.zone.endswith(':battlefield'):
            frame['chosen'].append('')
            continue
        decide(plan, player=ctx['controller'], kind='choose_one',
               prompt=f"{ctx.get('name') or 'The effect'}: choose a counter for {current.name}",
               options=[DecisionOption(id=k, label=k) for k in e['kinds']], source=current,
               resume={'step': 'counter_kind_choice', 'ctx': ctx, 'e': e})
        return False
    puts = []
    for ref, chosen in zip(frame['objects'], frame['chosen'], strict=True):
        card = plan.state.cards.get(ref['card'])
        if not chosen or card is None or plan.oid(card) != ref['object_id'] or not card.zone.endswith(':battlefield'):
            continue
        if e.get('fixed'):
            puts.append((card.id, e['fixed'], 1))
        puts.append((card.id, chosen, 1))
    if puts:
        answers = replace._ctx_answers(ctx)
        planned = replace.plan_counters(plan, puts, by=ctx['controller'], effect=True, entering=None, answers=answers, ask=True)
        if isinstance(planned, replace.Ask):
            then = replace.rerun_then(ctx, e)
            assert then is not None
            replace.ask(plan, planned, answers, then)
            return False
        replace.do_counters(plan, planned, by=ctx['controller'])
    frames.pop(key, None)
    return True


def resume(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = decision.resume['ctx'], decision.resume['e']
    key = str(int(ctx.get('next') or 0) - 1)
    ctx[_KEY][key]['chosen'].append(chosen[0])
    if run(plan, ctx, e):
        effects.continue_effects(plan, ctx)


PRIMITIVES = {'counter_kind_choice': run}
RESUME = {'counter_kind_choice': resume}
