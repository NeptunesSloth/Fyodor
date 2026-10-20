"""Life doubling follows its original creature; Unlife changes player damage results."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


UNLIFE = 'As long as you have 0 or less life, all damage is dealt to you as though its source had infect.'
MANTLE = "Whenever enchanted creature deals combat damage to a player, double its controller's life total."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.text == UNLIFE:
        return {'kind': 'static', 'static': 'player_damage_as_infect', 'effects': []}
    if ability.text == MANTLE:
        return {'kind': 'triggered', 'trigger': 'event',
                'cond': {'event': 'deal_damage', 'subject': 'host', 'combat': True, 'to': 'player'},
                'effects': [{'do': 'double_event_creature_controller_life'}]}
    return None


def infect_players(plan: Plan) -> frozenset[str]:
    """Freeze eligibility before converting any of one batch's damage results."""
    from app.rules import scripts
    from app.rules.replace import conditional_lines

    eligible = {p for p in plan.live() if plan.state.players[p].life <= 0}
    if not eligible:
        return frozenset()
    out = set()
    for card in plan.state.cards.values():
        if (card.controller not in eligible or not card.zone.endswith(':battlefield') or card.face_down or
                not plan.in_game(card) or plan.manual(card)):
            continue
        ch = plan.ch(card)
        skipped = conditional_lines(ch)
        if any(i not in skipped and d.get('kind') == 'static' and d.get('static') == 'player_damage_as_infect'
               for i, d in scripts.definitions(ch).items()):
            out.add(card.controller)
    return frozenset(out)


def double_life(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption, ObjectRef
    from app.rules import context
    from app.rules.plan import decide

    refs = (ctx.get('event') or {}).get('objects') or []
    ref = ObjectRef.model_validate(refs[0]) if len(refs) == 1 else None
    card = plan.state.cards.get(ref.card) if ref is not None else None
    current = ref is not None and card is not None and card.zone.endswith(':battlefield') and plan.oid(card) == ref.object_id
    snap = context.snapshot(plan, ref) if ref is not None else None
    if not current and snap is None:
        decide(plan, player=ctx['controller'], kind='manual_resolution',
               prompt="This older save did not preserve the original enchanted creature's controller. Double that player's life total by hand, then press Done.",
               options=[DecisionOption(id='done', label='Done')],
               resume={'step': 'double_event_creature_legacy', 'ctx': ctx})
        return False
    players = context.players(plan, ctx, 'event.controller')
    if not players:
        return True
    player = players[0]
    amount = plan.state.players[player].life
    if amount:
        # Literal positive gain/loss preserves the signed life-total rule while
        # retaining ordinary replacement and life-event handling (119.5).
        ctx['effects'][ctx['next']:ctx['next']] = [
            {'do': 'gain_life' if amount > 0 else 'lose_life', 'who': 'player:' + player, 'n': abs(amount)}]
    return True


def legacy_done(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects

    effects.continue_effects(plan, decision.resume['ctx'])


PRIMITIVES = {'double_event_creature_controller_life': double_life}
RESUME = {'double_event_creature_legacy': legacy_done}
