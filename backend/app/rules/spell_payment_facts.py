"""Snapshot a spell's actual payment before an instruction moves it off the stack."""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from app.rules.plan import Plan


class SpellPaymentFacts(BaseModel):
    kind: str = 'spell_payment'
    object_id: str
    mana: dict[str,int] | None = None
    mana_value: float


def capture(plan: Plan,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules.effects import _stack_targets
    from app.rules.stack_interaction import mana_value

    ids=_stack_targets(plan,ctx,e)
    if len(ids)!=1:
        return True
    card=plan.state.cards[ids[0]]
    oid=plan.oid(card)
    paid=plan.rules.payments.get(oid)
    fact=SpellPaymentFacts(object_id=oid,mana=dict(paid.mana_spent) if paid is not None and paid.mana_known else None,
                           mana_value=mana_value(card,plan.ch(card)))
    ctx.setdefault('refs',{})[e['as']]=fact.model_dump(mode='json')
    return True


def fact(ctx: dict[str,Any],ref: str) -> SpellPaymentFacts | None:
    raw=(ctx.get('refs') or {}).get(ref.removeprefix('ref:'))
    return SpellPaymentFacts.model_validate(raw) if isinstance(raw,dict) and raw.get('kind')=='spell_payment' else None


def amount(plan: Plan,ctx: dict[str,Any],ref: str) -> int | None:
    saved=fact(ctx,ref)
    if saved is None or saved.mana is None:
        plan.note('The mana spent on that spell was not recorded; apply its payment-dependent effect by hand')
        return None
    return sum(saved.mana.values())


def holds(plan: Plan,ctx: dict[str,Any],spec: dict[str,Any]) -> bool:
    n=amount(plan,ctx,spec['ref'])
    if n is None:
        return False
    if spec['test']=='zero':
        return n==0
    saved=fact(ctx,spec['ref'])
    return saved is not None and spec['test']=='under_mv' and n<saved.mana_value


def parse(body: str) -> tuple[list[dict[str,Any]],Any,bool] | None:
    from app.rules import conditions, delayed, scripts

    t=body.strip().rstrip('.')
    before={'do':'capture_spell_payment','who':'target','as':'spell_payment'}
    counter={'do':'counter','who':'target'}
    if t=='Counter target spell if no mana was spent to cast it':
        return [before,{'do':'only_if','cond':{'spell_payment':{'ref':'ref:spell_payment','test':'zero'}},'skip':1},counter],scripts.SELECTORS['target spell'],False
    if t=='Counter target spell. If the amount of mana spent to cast that spell was less than its mana value, you draw a card':
        return [before,counter,{'do':'only_if','cond':{'spell_payment':{'ref':'ref:spell_payment','test':'under_mv'}},'skip':1},
                {'do':'draw','who':'you','n':1}],scripts.SELECTORS['target spell'],False
    m=re.fullmatch(r'Counter target spell\. If (?P<cond>you control an? [A-Z][a-z]+), add an amount of \{(?P<sym>[WUBRGC])\} equal to the amount of mana spent to cast that spell at the beginning of your next main phase',t)
    if m is not None and (cond:=conditions.parse(m['cond'])) is not None:
        tail=delayed.wrap_when([{'do':'add_mana','sym':m['sym'],'n':{'spell_payment':'ref:spell_payment'}}],
                               {'kind':'step','step':'main','whose':'you'})
        return [before,counter,{'do':'only_if','cond':cond,'skip':len(tail)},*tail],scripts.SELECTORS['target spell'],False
    return None


def normalize(body: str) -> str | None:
    m=re.match(r'[Pp]ut a number of (?P<kind>[a-z]+) counters on (?P<source>~|this creature|this permanent) equal to the amount of mana spent to cast that spell\.',body)
    if m is None:
        return None
    first=f"Put X {m['kind']} counters on ~, where X is the amount of mana spent to cast that spell."
    tail=body[m.end():].replace(m['source'],'~')
    tail=re.sub(r'(Then if ~ has \w+ or more '+re.escape(m['kind'])+r' counters on )it,',r'\1~,',tail)
    return scripts_threshold(first+tail)


def scripts_threshold(body: str) -> str:
    from app.rules.scripts import _counter_threshold

    return _counter_threshold(body)
