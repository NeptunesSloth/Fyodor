"""Offer copy outcomes, original-controller copies, and countered-spell memory."""
from __future__ import annotations

from dataclasses import replace
from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import conditions, scripts
    from app.rules.oracle import strip_reminders

    text = strip_reminders(scripts.self_text(ability.text, ch.name)).strip()
    text = text.split(' — ', 1)[-1]
    if text == '{2}{U}, {T}: The controller of target instant or sorcery spell copies it. That player may choose new targets for the copy.':
        d = scripts.define(replace(ability, text='{2}{U}, {T}: Copy target instant or sorcery spell. You may choose new targets for the copy.'), ch)
        assert d is not None
        return {**d, 'effects': [{'do': 'controller_copy105'}, {'do': 'copy_new_targets', 'optional': True}]}
    if text == 'Choose target instant or sorcery spell. Each opponent may copy that spell and may choose new targets for the copy they control. You copy that spell once plus an additional time for each opponent who copied the spell this way. You may choose new targets for the copies you control.':
        d = scripts.define(replace(ability, text='Copy target instant or sorcery spell. You may choose new targets for the copy.'), ch)
        assert d is not None
        return {**d, 'effects': [{'do': 'tempt_copy105'}]}
    if text == 'If there are two or more instant and/or sorcery cards in your graveyard, you may copy the spell countered this way. You may choose new targets for the copy.':
        cond = conditions.parse('there are two or more instant and/or sorcery cards in your graveyard')
        assert cond is not None
        d = scripts.define(replace(ability, text='Draw a card.'), ch)
        assert d is not None
        return {**d, 'effects': [{'do': 'only_if', 'cond': cond, 'skip': 2}, {'do': 'may_rest', 'skip': 1, 'label': 'Copy the countered spell'}, {'do': 'rebuttal_copy105'}]}
    if ch.name == 'Psychic Rebuttal' and text == 'Counter target instant or sorcery spell that targets you.':
        d = scripts.define(replace(ability, text=text), replace(ch, name='Rebuttal native proxy'))
        assert d is not None
        return {**d, 'effects': [{'do': 'rebuttal_counter105'}]}
    return None


def controller_copy(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import copying

    found = copying._stack_objects(plan, ctx, 'target')
    if not found:
        return True
    return copying.copy_stack_object(plan, ctx, {'do': 'copy_spell', 'who': 'target', 'by': 'player:' + plan.state.cards[found[0]].controller})


def tempt_copy(plan: Any, ctx: Any, effect: Any) -> bool:
    opponents = [p for p in plan.apnap() if p != ctx['controller']]
    tag = f"tempt105_{ctx['next']}_"
    out = []
    for i,p in enumerate(opponents):
        out.extend([{'do': 'tempt_ask', 'player': p, 'bind': tag+'yes'+str(i), 'text': 'copy the chosen spell'},
                    {'do': 'only_if', 'cond': {'flag': tag+'yes'+str(i)}, 'skip': 2},
                    {'do': 'copy_spell', 'who': 'target', 'by': 'player:'+p, 'bind': tag+'did'+str(i)},
                    {'do': 'copy_new_targets', 'optional': True}])
    out.append({'do': 'tempt_final105', 'flags': [tag+'did'+str(i) for i in range(len(opponents))]})
    ctx['effects'][ctx['next']:ctx['next']] = out
    return True


def tempt_final(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import conditions

    n = 1 + sum(conditions.holds(plan, ctx, {'succeeded': f}) for f in effect['flags'])
    ctx['effects'][ctx['next']:ctx['next']] = [{'do': 'copy_spell', 'who': 'target', 'n': n}, {'do': 'copy_new_targets', 'optional': True}]
    return True


def rebuttal_counter(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import effects

    found = effects._stack_targets(plan, ctx, {'who': 'target'})
    before = [(cid, plan.oid(cid)) for cid in found]
    effects.counter(plan, ctx, {'do': 'counter', 'who': 'target'})
    ctx['rebuttal_spell105'] = [{'card': cid, 'oid': oid} for cid,oid in before
                               if plan.state.cards[cid].zone != 'stack' or plan.oid(cid) != oid]
    return True


def rebuttal_copy(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import copying

    objects = [(x['card'], x['oid'], 1) for x in ctx.get('rebuttal_spell105', [])]
    job = copying.new_job(ctx, controller=ctx['controller'], objects=objects, retarget=True, label=ctx.get('name') or 'Psychic Rebuttal')
    return copying.run(plan, job)


PRIMITIVES = {'controller_copy105': controller_copy, 'tempt_copy105': tempt_copy,
              'tempt_final105': tempt_final, 'rebuttal_counter105': rebuttal_counter, 'rebuttal_copy105': rebuttal_copy}
