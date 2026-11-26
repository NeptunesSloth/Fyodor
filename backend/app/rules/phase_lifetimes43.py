"""Exact direct phasing packets with an original-source departure duration.

Native phasing, untap and source-departure expiry preserve the same objects.
"""
from __future__ import annotations

from typing import Any

from app.game.rules_state import ObjectRef, PhaseLifetime
from app.rules.plan import Plan

STEP = 'phase_until_source43'
FINISH = 'phase_until_source_finish43'
STEP_TARGET = 'phase_until_target110c'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip()
    text = text[:1].upper() + text[1:]
    text = text.replace('~', 'this enchantment')
    if text == ('Target creature phases out until this enchantment leaves the battlefield. '
                'Tap that creature as it phases in this way.'):
        # Oubliette (wave 110C): 702.26a/610.3; the tap rides on the packet and happens as it phases in (702.26d).
        from app.rules import scripts

        parsed = scripts.parse_effects('Target creature phases out.')
        assert parsed is not None
        _, target, optional = parsed
        return ([{'do': STEP_TARGET}], target, optional)
    if text != ('Untap all creatures, then those creatures phase out until this enchantment leaves the battlefield. '
                'Put a time counter on this enchantment for each creature that phased out this way.'):
        return None
    return ([{'do': STEP}], None, False)


def resolve(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context

    ids = [c.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and plan.ch(c).is_creature]
    context.bind_objects(plan, ctx, '_phase_until43', ids)
    # "Those creatures" means the original packet, including stunned ones for
    # which the attempted untap removed a stun counter instead.
    ctx['effects'][ctx['next']:ctx['next']] = [
        {'do': 'untap', 'who': 'ref:_phase_until43'}, {'do': FINISH}]
    return True


def resolve_target(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    source = ObjectRef(card=ctx['source_card'], object_id=ctx['source_object'])
    for r in phase_out(plan, source, effects._cards(plan, ctx, 'target'), ctx['controller'], while_tapped=bool(e.get('tapped110i'))):
        for p in plan.rules.phase_lifetimes:
            if p.source == source and r in p.recipients and not e.get('untapped110i'):  # (110I The Moment: no tap, 702.26a)
                p.tap_on_return = True
    return True


def finish(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    ids = effects._cards(plan, ctx, 'ref:_phase_until43')
    source = ObjectRef(card=ctx['source_card'], object_id=ctx['source_object'])
    actual = phase_out(plan, source, ids, ctx['controller'])
    if actual:
        ctx['effects'][ctx['next']:ctx['next']] = [
            {'do': 'add_counters', 'who': 'self', 'kind': 'time', 'n': len(actual)}]
    return True


def source_present(plan: Plan, ref: ObjectRef, control: str | None = None, while_tapped: bool = False) -> bool:
    card = plan.state.cards.get(ref.card)
    # A departing controller's control effect may end without this permanent
    # leaving (800.4a). Ownership departure, unlike that transient controller
    # state, means the object left the game even if its table record remains.
    return (card is not None and card.owner in plan.live() and plan.oid(card) == ref.object_id and (control is None or card.controller == control)
            and (not while_tapped or card.tapped)  # -- wave 110I -- The Pandorica: "for as long as ~ remains tapped" (611.2b)
            and card.zone.rsplit(':', 1)[-1] in ('battlefield', 'phased'))


def _alive(plan: Plan, p: PhaseLifetime) -> bool:
    return p.roll_max110f is not None or p.until_walk_e1 or source_present(plan, p.source, p.control, p.while_tapped)  # (wave 110F: a roll packet outlasts its source)


def held(plan: Plan, card_id: str) -> bool:
    card = plan.state.cards.get(card_id)
    if card is None:
        return False
    oid = plan.oid(card)
    return any(_alive(plan, packet) and any(r.card == card_id and r.object_id == oid for r in packet.recipients)
               for packet in plan.rules.phase_lifetimes)


def phase_out(plan: Plan, source: ObjectRef, card_ids: list[str], actor: str, control: str | None = None, while_tapped: bool = False,
              roll_max: int | None = None) -> list[ObjectRef]:
    """610.3b: a duration already over never starts; preserve native indirect phasing."""
    if roll_max is None and not source_present(plan, source, control, while_tapped):
        return []
    refs = [ObjectRef(card=cid, object_id=plan.oid(card), zone=card.zone)
            for cid in card_ids if (card := plan.state.cards.get(cid)) is not None and plan.in_game(card)
            and card.zone.endswith(':battlefield')]
    if not refs:
        return []
    # Install before the native action: a source that is itself among the
    # creatures stays present as a phased object, with precisely the same OID.
    packet = PhaseLifetime(source=source, recipients=refs, control=control, while_tapped=while_tapped,
                           roll_max110f=roll_max, roller110f=actor if roll_max is not None else None)
    plan.rules.phase_lifetimes.append(packet)
    plan.do({'type': 'phase_shift', 'card_ids': [r.card for r in refs], 'out': True}, actor=actor)
    packet.recipients = [r for r in refs if (c := plan.state.cards.get(r.card)) is not None
                         and plan.oid(c) == r.object_id and c.zone.endswith(':phased') and not c.phased_indirect]
    return packet.recipients


def expire(plan: Plan) -> None:
    _release(plan, [p for p in plan.rules.phase_lifetimes if not _alive(plan, p)])


def roll_visit(plan: Plan, pid: str, result: int) -> None:
    """-- wave 110F -- Ferris Wheel: "phases out until you roll a 3 or less while rolling to visit your Attractions": ``pid`` rolled ``result`` to visit."""
    _release(plan, [p for p in plan.rules.phase_lifetimes if p.roll_max110f is not None and p.roller110f == pid and result <= p.roll_max110f])


def _release(plan: Plan, ended: list[PhaseLifetime]) -> None:
    if not ended:
        return
    # Remove before actions or characteristic queries can recursively expire.
    plan.rules.phase_lifetimes = [p for p in plan.rules.phase_lifetimes if p not in ended]
    back = list(dict.fromkeys(r.card for p in ended for r in p.recipients
                             if (c := plan.state.cards.get(r.card)) is not None
                             and c.owner in plan.live() and plan.oid(c) == r.object_id and c.zone.endswith(':phased')
                             and not c.phased_indirect and not held(plan, c.id)))
    if back:
        from app.game.rules_state import emit

        for cid in back:
            emit(plan.state, 'designation', counter='phase_in', card=cid,
                 object_id=plan.oid(cid), player=plan.state.cards[cid].controller)
        plan.do({'type': 'phase_shift', 'card_ids': back, 'out': False})
        tap = [r.card for p in ended if p.tap_on_return for r in p.recipients if r.card in back]
        if tap:
            plan.do({'type': 'tap', 'card_ids': tap, 'tapped': True})
        from app.rules import keyword_actions

        for cid in back:
            card = plan.state.cards[cid]
            if plan.oid(card) in plan.rules.prepared:
                keyword_actions.become_prepared(plan, card)


PRIMITIVES = {STEP: resolve, FINISH: finish, STEP_TARGET: resolve_target}
