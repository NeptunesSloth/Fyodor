"""One original graveyard source plus exactly two named others, exiled together."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_TEXT = 'Exile this card and two other cards named Say Its Name from your graveyard'


def parse(text: str) -> Any:
    from app.rules import costs as C
    from app.rules import selectors

    if text.strip().casefold() not in (_TEXT.casefold(), _TEXT.replace('this card', '~').casefold()):
        return None
    sel = selectors.Selector(card=True, zone_owner='you', zones=('graveyard',), extras=('name:Say Its Name',)).key()
    return C.AbilityCost(components=(C.CostComponent(C.EXILE_FROM_GRAVEYARD, amount=2, selector=sel,
                                                   source_with_choices=True, text=text),))


def retain(plan: Plan, source: Any, options: list[str]) -> dict[str, Any]:
    from app.rules import context

    refs = [context.ref_of(plan, cid) for cid in [source.id, *options]]
    if any(ref is None for ref in refs):
        raise ValueError('A named source cost lost its original public object')
    return {'source_packet_required69': True, 'source_packet69': {
        'source': source.id, 'originals': {ref.card: ref.model_dump(mode='json') for ref in refs if ref is not None}}}


def requires_receipt(plan: Plan, resume: dict[str, Any]) -> bool:
    from app.rules import costs as C

    if resume.get('source_packet_required69') or 'source_packet69' in resume:
        return True
    intent = resume.get('intent') or {}
    source = plan.state.cards.get(intent.get('card_id') or '')
    if intent.get('type') != 'activate_ability' or source is None:
        return False
    ch = plan.ch(source)
    ability = next((ab for ab in ch.abilities if ab.index == intent.get('ability')), None)
    if ability is None:
        return False
    cost = C.parse_ability_cost(ability.cost or '', card_name=ch.name)
    component = resume.get('component')
    return any(i == component and comp.source_with_choices for i, comp in enumerate(cost.components))


def guard(plan: Plan, resume: dict[str, Any], chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.game.rules_state import ObjectRef

    packet = resume.get('source_packet69')
    if not isinstance(packet, dict) or not isinstance(packet.get('originals'), dict) or not isinstance(packet.get('source'), str) or not packet['source']:
        raise ActionError('The original source-cost packet is unavailable')
    if packet['source'] != (resume.get('intent') or {}).get('card_id'):
        raise ActionError('The original source-cost packet does not match this activation')
    for cid in [packet['source'], *chosen]:
        raw = packet['originals'].get(cid)
        ref = ObjectRef.model_validate(raw) if raw is not None else None
        card = plan.state.cards.get(cid)
        if ref is None or card is None or plan.oid(card) != ref.object_id or card.zone != ref.zone:
            raise ActionError('The named source cost no longer has its original graveyard objects')


def payment(plan: Plan, comp: Any, source: Any, chosen: list[str]) -> list[str]:
    from app.game.errors import ActionError
    from app.rules import costs as C

    if (comp.kind != C.EXILE_FROM_GRAVEYARD or source.zone != f'{plan.actor}:graveyard'
            or source.id in chosen or len(chosen) != 2 or len(set(chosen)) != 2):
        raise ActionError('Exile the original graveyard source and two other named cards')
    return [source.id, *chosen]
