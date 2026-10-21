"""Counter-sized upkeep payments compose native costs and resumable instructions."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

QUANTITY='counter_upkeep_quantity'
PAID='counter_upkeep_paid'


def parse(body: str) -> tuple[list[dict[str,Any]],Any,bool] | None:
    from app.rules import scripts

    text=body.strip().rstrip('.')
    text=text[:1].upper()+text[1:]
    put={'do':'add_counters','who':'self','kind':'+1/+1','n':1}
    remember={'do':'remember_counter_quantity','kind':'+1/+1','bind':QUANTITY}
    amount={'ref_amount':QUANTITY}
    payment={'do':'optional_payment','who':'you','cost':'{0}','per':'{1}','n':amount,'bind':PAID}
    unpaid={'do':'only_if','cond':{'succeeded':PAID,'negate':True},'skip':1}
    if text=="Put a +1/+1 counter on ~. Then you may pay {X}, where X is the number of +1/+1 counters on it. If you don't, tap ~ and it deals X damage to you":
        return ([put,remember,payment,{**unpaid,'skip':2},{'do':'tap','who':'self'},
                 {'do':'damage','who':'you','n':amount}],None,False)
    if text=='Put a +1/+1 counter on ~, then sacrifice ~ unless you pay {1} for each +1/+1 counter on it':
        return ([put,remember,payment,unpaid,{'do':'sacrifice','who':'self'}],None,False)
    if text=="Put a wage counter on ~. You may pay {2} for each wage counter on it. If you don't, remove all wage counters from ~ and an opponent gains control of it":
        return ([{**put,'kind':'wage'},{**remember,'kind':'wage'},{**payment,'per':'{2}'},
                 {**unpaid,'skip':2},{'do':'remove_counters','who':'self','kind':'wage','n':{'counters':'wage','on':'self'},'as':'upkeep_source'},
                 {'do':'gain_control','who':'ref:upkeep_source','to':'choose_opponent'}],None,False)
    if text=='Put a wind counter on ~, then sacrifice ~ unless you pay {G} for each wind counter on it. If you pay, ~ deals damage equal to the number of wind counters on it to each creature and each player':
        damage=scripts.parse_effects('~ deals damage equal to the number of wind counters on it to each creature and each player.')
        assert damage is not None
        return ([{**put,'kind':'wind'},{**remember,'kind':'wind'},{**payment,'per':'{G}'},unpaid,
                 {'do':'sacrifice','who':'self'},{'do':'only_if','cond':{'succeeded':PAID},'skip':len(damage[0])},*damage[0]],None,False)
    if text=='Remove all delay counters from ~. For each delay counter removed this way, you lose 1 life unless you pay {1}{W}':
        return ([{'do':'remove_counters','who':'self','kind':'delay','n':{'counters':'delay','on':'self'},'bind':QUANTITY},
                 {'do':'counter_payment_loop','n':amount}],None,False)
    return None


def remember_quantity(plan: Plan,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import context, effects

    context.bind_amount(ctx,e['bind'],effects._amount(plan,ctx,{'counters':e['kind'],'on':'self'}))
    return True


def payment_loop(plan: Plan,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    n=effects._amount(plan,ctx,e['n'])
    if not n:
        return True
    if len(plan.steps)>=plan.max_steps-24:
        ctx['next']-=1
        decide(plan,player=ctx['controller'],kind='confirm',
               prompt=f"Continue resolving {ctx.get('name') or 'the ability'} (no priority is available).",
               options=[DecisionOption(id='continue',label='Continue resolving')],
               resume={'step':'counter_upkeep_continue','ctx':ctx})
        return False
    # One independent 118.12a payment per removed counter. Keep only the pending
    # iteration and original tail, rather than expanding an unbounded effect list.
    tail=ctx['effects'][ctx['next']:]
    ctx['effects']=[{'do':'optional_payment','who':'you','cost':'{1}{W}','bind':PAID},
                    {'do':'only_if','cond':{'succeeded':PAID,'negate':True},'skip':1},
                    {'do':'lose_life','who':'you','n':1},
                    {'do':'counter_payment_loop','n':n-1},*tail]
    ctx['next']=0
    return True


def resume_continue(plan: Plan,d: Any,chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    continue_effects(plan,d.resume['ctx'])


PRIMITIVES={'remember_counter_quantity':remember_quantity,'counter_payment_loop':payment_loop}
RESUME={'counter_upkeep_continue':resume_continue}
