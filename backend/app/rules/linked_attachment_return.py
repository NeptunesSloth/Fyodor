"""CR 400.7e, 603.7c: return a dead host, then its Aura next end step."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption, ObjectRef

if TYPE_CHECKING:
    from app.rules.plan import Plan

BODY = ("Return that card to the battlefield under its owner's control. "
        "Return this card to the battlefield attached to that creature at the beginning of the next end step.")


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    text = body[:1].upper() + body[1:]
    if text.replace("Return ~ to", "Return this card to") != BODY:
        return None
    return ([{'do': 'return_card', 'who': 'event.new', 'to': 'battlefield', 'under': 'owner', 'as': 'returned_host'},
             {'do': 'delay_attachment_return', 'host': 'ref:returned_host'}], None, False)


def capture(plan: Plan, definition: dict[str, Any], source_object: str) -> dict[str, Any]:
    """Freeze the source's first graveyard incarnation before zone events expire."""
    if not any(e.get('do') == 'delay_attachment_return' for e in definition.get('effects') or []):
        return definition
    moved = next((e for e in plan.rules.events if e.kind == 'zone_change' and e.object_id == source_object
                  and e.to_zone and e.to_zone.endswith(':graveyard') and e.new_object_id and e.card), None)
    ref = ObjectRef(card=moved.card or '', object_id=moved.new_object_id or '', zone=moved.to_zone or '').model_dump(mode='json') if moved else None
    return {**definition, 'effects': [{**e, 'aura': ref} if e.get('do') == 'delay_attachment_return' else e
                                     for e in definition.get('effects') or []]}


def schedule(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, delayed, effects

    hosts = effects._cards(plan, ctx, e['host'])
    hosts = [c for c in hosts if plan.state.cards[c].zone.endswith(':battlefield')]
    if not hosts or not e.get('aura'):
        return True
    refs = [r.model_dump(mode='json') for c in hosts if (r := context.ref_of(plan, c)) is not None]
    delayed.create_plain(plan, ctx['controller'], ctx['source_card'], ctx['source_object'], ctx.get('name') or 'An Aura',
                         {'kind': 'step', 'step': 'end', 'whose': 'next'},
                         [{'do': 'return_linked_attachment', 'aura': e['aura'], 'hosts': refs}])
    return True


def return_attached(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import attachments, context, effects
    from app.rules.plan import decide

    aura = ObjectRef.model_validate(e['aura'])
    card = context._same(plan, aura)
    if card is None or not card.zone.endswith(':graveyard'):
        return True
    hosts = [creature for r in e['hosts'] if (creature := context._same(plan, ObjectRef.model_validate(r))) is not None
             and creature.zone.endswith(':battlefield')
             and attachments.host_problem(plan, card, creature.id, card.owner) is None]
    if not hosts:
        return True
    if len(hosts) > 1:
        decide(plan, player=card.owner, kind='choose_one', prompt='Choose which returned creature the Aura enchants (303.4d)',
               options=[DecisionOption(id=c.id, label=plan.ch(c).name or 'A creature', card_id=c.id) for c in hosts],
               resume={'step': 'linked_attachment_host', 'ctx': ctx, 'effect': e}, source=card)
        return False
    context.bind_objects(plan, ctx, 'linked_aura', [card.id])
    context.bind_objects(plan, ctx, 'linked_host', [hosts[0].id])
    return effects.return_card(plan, ctx, {'do': 'return_card', 'who': 'ref:linked_aura', 'to': 'battlefield',
                                           'under': 'owner', 'host': 'ref:linked_host'})


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    e = d.resume['effect']
    e = {**e, 'hosts': [r for r in e['hosts'] if r['card'] == chosen[0]]}
    if return_attached(plan, d.resume['ctx'], e):
        effects.continue_effects(plan, d.resume['ctx'])


PRIMITIVES = {'delay_attachment_return': schedule, 'return_linked_attachment': return_attached}

RESUME = {'linked_attachment_host': resume}
