"""Grouped counter instructions freeze recipients and derived quantities at resolution."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts, selectors

    text=body.strip().rstrip('.')
    text=text[:1].upper()+text[1:]
    if text=="For each creature you control with power greater than that creature's base power, put a number of +1/+1 counters on that creature equal to the difference":
        who=selectors.Selector(controller='you',types=('Creature',),extras=('power_gt_base',)).key()
        return ([{'do':'add_counters','who':who,'kind':'+1/+1','n':{'recipient_stat':'power_above_base'}}],None,False)
    if text=='Each opponent gets a poison counter. Then each creature your opponents control gets -1/-1 until end of turn for each poison counter its controller has':
        first=scripts.parse_effects('Each opponent gets a poison counter.')
        assert first is not None
        return ([*first[0],{'do':'pump_by_controller_counters','who':selectors.Selector(controller='opponents',types=('Creature',)).key(),'kind':'poison'}],None,False)
    if text=='For each creature card in your graveyard, put a +1/+1 counter on each creature you control':
        return scripts.parse_effects('Put a +1/+1 counter on each creature you control for each creature card in your graveyard.')
    if text=='Put a +1/+1 counter on each creature each opponent controls':
        return scripts.parse_effects('Put a +1/+1 counter on each creature your opponents control.')
    if text=='Put a fade counter on each permanent with fading you control':
        who=selectors.Selector(controller='you',with_keywords=('fading',)).key()
        return ([{'do':'add_counters','who':who,'kind':'fade','n':1}],None,False)
    if text=='Put a +1/+1 counter on each creature you control with toughness less than the number of basic land types among lands you control':
        return ([{'do':'counters_below_domain','who':selectors.Selector(controller='you',types=('Creature',)).key()}],None,False)
    return None


def pump_by_controller(plan: Plan,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import context, effects

    # Both membership and amounts are fixed now; subsequent controller/counter changes
    # cannot resize an already-created continuous effect (611.2c).
    groups: dict[int,list[str]]={}
    for cid in effects._cards(plan,ctx,e['who']):
        player=plan.state.players[plan.state.cards[cid].controller]
        n=max(0,int(player.resources.get(e['kind'],0)))
        groups.setdefault(n,[]).append(cid)
    for n,cards in groups.items():
        local={**ctx,'refs':dict(ctx.get('refs') or {})}
        context.bind_objects(plan,local,'group_counter_recipients',cards)
        effects.pump(plan,local,{'do':'pump','who':'ref:group_counter_recipients','p':-n,'t':-n})
    return True


def below_domain(plan: Plan,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import context, effects, selectors, values

    lands=selectors.Selector(controller='you',types=('Land',)).key()
    domain=values.evaluate(plan,ctx,{'distinct':'basic_land_types','among':lands})
    cards=[cid for cid in effects._cards(plan,ctx,e['who'])
           if (pt:=plan.ch(plan.state.cards[cid]).pt) is not None and pt[1]<domain]
    context.bind_objects(plan,ctx,'domain_counter_recipients',cards)
    return effects.add_counters(plan,ctx,{'do':'add_counters','who':'ref:domain_counter_recipients','kind':'+1/+1','n':1})


PRIMITIVES={'pump_by_controller_counters':pump_by_controller,'counters_below_domain':below_domain}
