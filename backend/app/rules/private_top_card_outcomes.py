"""Private top-card looks with optional reveal and native conditional follow-up."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.rules import selectors

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan
    from app.rules.scripts import Definition


def definition(ability: AbilityText, ch: Characteristics) -> Definition | None:
    from dataclasses import replace

    from app.rules import scripts
    text=scripts.self_text(ability.text,ch.name)
    if ability.kind=='activated' and text == "{2}, {T}: Look at the top card of your library. If it's an instant or sorcery card, you may reveal it and put it into your hand. If you don't put the card into your hand, you may put it into your graveyard. Activate only if you have exactly zero or seven cards in hand.":
        proto='{2}, {T}: Look at the top card of your library. Activate only if you have no cards in hand.'
        base=scripts.define(replace(ability,text=proto),ch)
        assert base is not None
        base['restriction']=[{'kind':'if','cond':{'any':[{'value':{'hand':'you'},'op':'==','n':n} for n in [0,7]]},
                              'text':'you have exactly zero or seven cards in hand'}]
        base['effects']=[{'do':'private_top_card','mode':'hand_or_graveyard'}]
        return base
    if ability.kind=='triggered' and text == "At the beginning of your upkeep, look at the top card of your library. You may reveal that card. If an instant or sorcery card is revealed this way, transform ~.":
        base=scripts.define(replace(ability,text='At the beginning of your upkeep, look at the top card of your library.'),ch)
        assert base is not None
        base['effects']=[{'do':'private_top_card','mode':'reveal_transform'}]
        return base
    return None


def insert(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> bool:
    ctx['effects'][ctx['next']:ctx['next']]=steps
    return True


def start(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects
    if not effects.look_top(plan,ctx,{'do':'look_top','n':1,'player':'you','reveal':False,'exact_look':True}):
        return False
    key=f'private_top_card_{ctx["next"]}'
    ctx[key]={'cards':list(ctx.get('looked') or []),'objects':dict(ctx.get('looked_objects') or {})}
    spell=selectors.Selector(zones=(),card=True,types=('Instant','Sorcery')).key()
    steps: list[dict[str, Any]]
    if e['mode']=='reveal_transform':
        steps=[{'do':'pick_looked','n':1,'optional':True,'to':'choose','reveal':True,'as':'private_revealed_card'},
               {'do':'private_revealed_transform','ref':'ref:private_revealed_card'}]
    else:
        steps=[{'do':'pick_looked','n':1,'optional':True,'sel':spell,'to':'hand','reveal':True},
               {'do':'private_top_card_restore','key':key},
               {'do':'pick_looked','n':1,'optional':True,'to':'graveyard'}]
    return insert(ctx,steps)


def restore(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    original=ctx[e['key']]
    library=plan.state.zones.get(ctx['controller']+':library',[])
    ctx['looked']=[c for c in original['cards'] if c in library and plan.oid(c)==original['objects'].get(c)]
    return True


def transform(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context
    info=context.info(plan,ctx,e['ref'].removeprefix(context.PREFIX))
    if info is not None and {'Instant','Sorcery'} & info[1].types:
        return insert(ctx,[{'do':'transform','who':'self'}])
    return True


PRIMITIVES={'private_top_card':start,'private_top_card_restore':restore,'private_revealed_transform':transform}
