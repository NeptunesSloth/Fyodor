"""Exact revealed-library choices with native entry and shared destinations."""
from __future__ import annotations

from typing import Any

from app.game.rules_state import Decision, DecisionOption
from app.rules import selectors
from app.rules.plan import Plan, decide


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text=body.strip().rstrip('.')
    text=text[:1].upper()+text[1:]
    cases={
        'Reveal the top six cards of your library. You may put up to one land card from among them onto the battlefield tapped and up to one Elf card from among them into your hand. Put the rest on the bottom of your library in a random order':'land_elf',
        'Reveal the top X plus one cards of your library. Choose a creature card and/or a land card from among them. Put those cards into your hand and the rest on the bottom of your library in a random order. If X is 5 or more, instead put the chosen cards onto the battlefield or into your hand and the rest on the bottom of your library in a random order':'creature_land',
        'Reveal the top six cards of your library. You may put a permanent card from among them onto the battlefield with an indestructible counter on it. You may put a permanent card from among them into your hand. Put the rest into your graveyard':'permanent_counter',
    }
    mode=cases.get(text)
    return ([{'do':'revealed_two_stage','mode':mode}],None,False) if mode else None


def _insert(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> bool:
    ctx['effects'][ctx['next']:ctx['next']]=steps
    return True


def start(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, values
    mode=e['mode']
    n=values.evaluate(plan,ctx,{'x':1})+1 if mode=='creature_land' else 6
    if not effects.look_top(plan,ctx,{'do':'look_top','n':n,'player':'you','reveal':True,'exact_look':True}):
        return False
    key=f'revealed_two_stage_{ctx["next"]}'
    original=list(ctx.get('looked') or [])
    ctx[key]={'cards':original,'objects':dict(ctx.get('looked_objects') or {})}
    steps: list[dict[str, Any]]
    if mode=='creature_land':
        steps=[{'do':'revealed_choose_kinds','key':key}]
    else:
        first=selectors.Selector(zones=(),card=True,types=('Land',)) if mode=='land_elf' else selectors.Selector(zones=(),card=True,types=tuple(sorted(selectors.PERMANENT_TYPES)))
        second=selectors.Selector(zones=(),card=True,subtypes=('Elf',)) if mode=='land_elf' else first
        steps=[{'do':'pick_looked','n':1,'optional':True,'sel':first.key(),'to':'battlefield_tapped' if mode=='land_elf' else 'battlefield',
                **({'counter':'indestructible','counter_n':1} if mode=='permanent_counter' else {})},
               {'do':'restore_revealed_choices','key':key},
               {'do':'pick_looked','n':1,'optional':True,'sel':second.key(),'to':'hand'}]
    steps += [{'do':'rest_looked','to':'graveyard' if mode=='permanent_counter' else 'bottom_random'},
              {'do':'hide_two_stage_reveal','key':key}]
    return _insert(ctx,steps)


def restore(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    state=ctx[e['key']]
    owner=ctx.get('looked_owner') or ctx['controller']
    library=plan.state.zones.get(owner+':library',[])
    ctx['looked']=[c for c in state['cards'] if c in library and c in plan.state.cards and plan.oid(c)==state['objects'].get(c)]
    return True


def hide(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    state=ctx[e['key']]
    ids=[c for c in state['cards'] if c in plan.state.cards and plan.state.cards[c].zone.endswith(':library') and plan.oid(c)==state['objects'].get(c)]
    if ids:
        plan.do({'type':'hide','card_ids':ids},actor=ctx['controller'])
    return True


def _kinds() -> list[str]:
    return [selectors.Selector(zones=(),card=True,types=(t,)).key() for t in ['Creature','Land']]


def choose_kinds(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, looking
    ids=[c for c in effects._looked(plan,ctx)[1] if looking.kinds_of(plan,ctx['controller'],c,_kinds())]
    if not ids:
        return True
    decide(plan,player=ctx['controller'],kind='choose_cards',prompt='Choose a creature card and/or a land card',
           options=[DecisionOption(id=c,label=plan.state.cards[c].name or 'Card',card_id=c) for c in ids],
           min_choices=1,max_choices=min(2,len(ids)),resume={'step':'revealed_choose_kinds','ctx':ctx,'e':e})
    return False


def resume_kinds(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects, looking, values
    assert d.resume is not None
    ctx=d.resume['ctx']
    if not looking.distinct_kinds(plan,ctx['controller'],chosen,_kinds()):
        raise ActionError('Choose at most one creature and one land, as different cards')
    # Native choose-only staging binds exact originals without moving them.
    effects._picked(plan,ctx,{'do':'pick_looked','to':'choose','as':'two_stage_chosen'},chosen)
    if values.evaluate(plan,ctx,{'x':1})>=5:
        decide(plan,player=ctx['controller'],kind='choose_one',prompt='Put all chosen cards onto the battlefield or into your hand',
               options=[DecisionOption(id='battlefield',label='Onto the battlefield'),DecisionOption(id='hand',label='Into your hand')],
               resume={'step':'revealed_shared_destination','ctx':ctx,'chosen':chosen})
    else:
        _insert(ctx,[{'do':'return_card','who':'ref:two_stage_chosen','to':'hand'}])
        effects.continue_effects(plan,ctx)


def resume_destination(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.rules import effects
    assert d.resume is not None
    ctx=d.resume['ctx']
    _insert(ctx,[{'do':'return_card','who':'ref:two_stage_chosen','to':chosen[0],'under':'you'}])
    effects.continue_effects(plan,ctx)


PRIMITIVES={'revealed_two_stage':start,'restore_revealed_choices':restore,'hide_two_stage_reveal':hide,'revealed_choose_kinds':choose_kinds}
RESUME={'revealed_choose_kinds':resume_kinds,'revealed_shared_destination':resume_destination}
