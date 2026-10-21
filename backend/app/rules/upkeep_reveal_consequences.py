"""Revealed top cards feed native host effects and immutable permanent-copy recipes."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.game.rules_state import CopyRecipe
from app.rules.plan import Plan


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts
    if ability.kind!='triggered':
        return None
    text=scripts.self_text(ability.text,ch.name)
    cases={
        "At the beginning of the upkeep of enchanted creature's controller, that player reveals the top card of their library. If that card is a land card, destroy that creature. Otherwise, it gets +3/+3 until end of turn.":
            ("At the beginning of the upkeep of enchanted creature's controller, you gain 1 life.",'host'),
        "At the beginning of each opponent's upkeep, that player reveals the top card of their library. If it's a creature card, the player puts the card into their graveyard and ~ becomes a copy of that card.":
            ("At the beginning of each opponent's upkeep, you gain 1 life.",'copy'),
    }
    if text not in cases:
        return None
    prototype,mode=cases[text]
    parsed=scripts.define(replace(ability,text=prototype),ch)
    if parsed is None:
        return None
    return {**parsed,'effects':[{'do':'upkeep_reveal_consequence','mode':mode}]}


def reveal(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import copying, reveal_outcomes
    if not reveal_outcomes.reveal_outcome_top(plan,ctx,{'do':'reveal_outcome_top','n':1,'player':'event_player','reveal':True,'exact_look':True}):
        return False
    ids=list(ctx.get('looked') or [])
    steps:list[dict[str,Any]]=[]
    if e['mode']=='host':
        land=bool(ids) and plan.ch(plan.state.cards[ids[0]]).is_land
        steps=[{'do':'destroy','who':'ref:event'}] if land else [{'do':'pump','who':'ref:event','p':3,'t':3}]
    elif ids and plan.ch(plan.state.cards[ids[0]]).is_creature:
        recipe=copying.recipe_of(plan,plan.state.cards[ids[0]])
        steps=[{'do':'rest_looked','to':'graveyard','viewer':'event_player'},
               {'do':'upkeep_revealed_copy','recipe':recipe.model_dump(mode='json')}]
    at=int(ctx.get('next') or 0)
    ctx['effects'][at:at]=steps
    return True


def become(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import copying
    source=plan.state.cards.get(ctx.get('source_card') or '')
    if source is not None and source.zone.endswith(':battlefield') and plan.oid(source)==ctx.get('source_object'):
        recipe=CopyRecipe.model_validate(e['recipe'])
        copying.add_copy_effect(plan,[plan.oid(source)],recipe,ctx['controller'],duration='permanent')
        plan.note(f"{source.name} becomes a copy of {recipe.source or 'the revealed card'}",[source.id],actor=ctx['controller'])
    return True


PRIMITIVES={'upkeep_reveal_consequence':reveal,'upkeep_revealed_copy':become}
