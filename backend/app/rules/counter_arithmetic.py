"""Counter arithmetic composes native removal, token, life, and turn effects."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def _replace_x(value: Any, amount: Any) -> Any:
    if value == {'x':1}:
        return amount
    if isinstance(value,list):
        return [_replace_x(x,amount) for x in value]
    if isinstance(value,dict):
        return {k:_replace_x(x,amount) for k,x in value.items()}
    return value


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts, selectors

    text=body.strip()
    text=(text[:1].upper()+text[1:]).rstrip('.')
    bind='actual_removed'
    amount={'ref_amount':bind}
    if text=='For each five counters paid, take an extra turn after this one':
        return ([{'do':'turns_per_counters_paid','per':5}],None,False)
    if text=='Each creature gets twice -X/-X until end of turn. Each player gets X rad counters':
        native=scripts.parse_effects('Each creature gets -X/-X until end of turn. Each player gets X rad counters.')
        assert native is not None
        out=[{**native[0][0],'p':{'neg':{'times':[2,{'x':1}]}},'t':{'neg':{'times':[2,{'x':1}]}}},*native[0][1:]]
        return out,native[1],native[2]
    if text=='You may remove all of them. If you do, exile each other nonland permanent with mana value less than or equal to the number of counters removed this way':
        sel=selectors.Selector(not_types=('Land',),other=True,compare=(('mana_value','<=',selectors.RESOLUTION_STAT+bind),))
        return ([{'do':'only_if','cond':{'object':'self','test':'on_battlefield'},'skip':4},
                 {'do':'may_rest'},
                 {'do':'remove_counters','who':'self','kind':'+1/+1','n':{'counters':'+1/+1','on':'self'},'bind':bind},
                 {'do':'only_if','cond':{'value':amount,'op':'>','n':0},'skip':1},
                 {'do':'exile','who':sel.key()}],None,False)
    coils=re.fullmatch(r'Remove all of them from it and create that many (?P<token>3/1 red Elemental creature tokens with haste)\. Exile them at the beginning of the next end step',text)
    if coils is not None:
        tail=scripts.parse_effects(f"Create X {coils['token']}. Exile them at the beginning of the next end step.")
        assert tail is not None
        return ([{'do':'remove_counters','who':'self','kind':'charge','n':{'counters':'charge','on':'self'},'bind':bind},
                 *_replace_x(tail[0],amount)],tail[1],tail[2])
    lily=re.fullmatch(r'Double the number of \+1/\+1 counters on ~ if its power is 16 or less\. Otherwise, remove all but one \+1/\+1 counter from it, then you gain 1 life for each \+1/\+1 counter removed this way',text)
    if lily is not None:
        return ([{'do':'only_if','cond':{'value':{'power':'self'},'op':'<=','n':16},'skip':1,'bind':'small_power'},
                 {'do':'double_counters','who':'self','kind':'+1/+1'},
                 {'do':'only_if','cond':{'flag':'small_power','negate':True},'skip':2},
                 {'do':'remove_counters','who':'self','kind':'+1/+1','n':{'minus':[{'counters':'+1/+1','on':'self'},1]},'bind':bind},
                 {'do':'gain_life','who':'you','n':amount}],None,False)
    return None


def turns_per_paid(plan: Plan,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import effects, extra_turns

    count=max(0,effects._amount(plan,ctx,{'x':1}))//e['per']
    # extra_turn's legacy default treats zero as one; zero complete groups create no turns.
    return not count or extra_turns.extra_turn(plan,ctx,{'do':'extra_turn','who':'you','n':count})


PRIMITIVES={'turns_per_counters_paid':turns_per_paid}
