"""CR 614.8/616.1: prepare automatic regeneration before a destruction batch commits."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import TypeAdapter

from app.game.rules_state import DecisionOption
from app.rules.plan import Plan, decide


@dataclass
class Candidate:
    key: str
    label: str
    aura: str | None = None
    aura_object: str | None = None


@dataclass
class Preparation:
    objects: dict[str, str]
    candidates: dict[str, list[Candidate]]
    can_regenerate: bool
    sba: bool
    ctx: dict[str, Any] | None = None
    chosen: dict[str, str] = field(default_factory=dict)


_FRAME = TypeAdapter(Preparation)


def automatic(plan: Plan, cid: str) -> bool:
    from app.rules import scripts

    card = plan.state.cards.get(cid)
    return bool(card is not None and card.zone.endswith(':battlefield') and not plan.manual(card)
                and any(d.get('static') == 'regenerate_instead' for d in scripts.definitions(plan.ch(card)).values()))


def options(plan: Plan, cid: str, *, can_regenerate: bool, effect: bool) -> list[Candidate]:
    from app.rules import regeneration, regeneration_riders

    card = plan.state.cards[cid]
    oid = plan.oid(card)
    out = []
    if can_regenerate and oid not in plan.rules.no_regen:
        if automatic(plan, cid):
            out.append(Candidate('automatic', f'{card.name}: regenerate'))
        if regeneration.shielded(plan, card):
            riders = regeneration_riders.shields(plan, oid)
            if plan.rules.regen_shields.get(oid, 0) > len(riders):
                out.append(Candidate('shield', 'Use a regeneration shield'))
            out.extend(Candidate('rider:' + shield.id, f'{shield.name}: use its regeneration shield') for shield in riders)
    if effect and card.counters.get('shield', 0) > 0:
        out.append(Candidate('counter', 'Remove a shield counter'))
    for aura in plan.state.cards.values():
        if aura.zone.endswith(':battlefield') and aura.attached_to == cid and not plan.manual(aura) and any(
                'umbra armor' in a.keywords for a in plan.ch(aura).abilities if a.kind == 'keywords'):
            out.append(Candidate(f'aura:{plan.oid(aura)}', f"{aura.name}: use umbra armor", aura.id, plan.oid(aura)))
    return out


def _save(plan: Plan, frame: Preparation) -> None:
    plan.rules.destruction_replacements = _FRAME.dump_python(frame, mode='json')


def _offer(plan: Plan, frame: Preparation) -> bool:
    order = {player: i for i, player in enumerate(plan.apnap())}
    for cid in sorted(frame.candidates, key=lambda c: order.get(plan.state.cards[c].controller, len(order))):
        candidates = frame.candidates[cid]
        oid = frame.objects[cid]
        if oid in frame.chosen or not candidates:
            continue
        if len(candidates) == 1:
            frame.chosen[oid] = candidates[0].key
            continue
        _save(plan, frame)
        decide(plan, player=plan.state.cards[cid].controller, kind='choose_one',
               prompt=f'{plan.state.cards[cid].name}: choose a destruction replacement',
               options=[DecisionOption(id=str(i), label=c.label) for i, c in enumerate(candidates)],
               resume={'step': 'regeneration_replacement', 'card': cid, 'object': oid})
        return True
    _save(plan, frame)
    return False


def prepare(plan: Plan, cards: list[str], *, can_regenerate: bool, sba: bool = False,
            ctx: dict[str, Any] | None = None) -> bool:
    objects = {cid: plan.oid(cid) for cid in cards}
    raw = plan.rules.destruction_replacements
    frame = _FRAME.validate_python(raw) if raw is not None else None
    if frame is not None and (frame.objects != objects or frame.sba != sba or frame.can_regenerate != can_regenerate):
        plan.rules.destruction_replacements = None
        frame = None
    if frame is None:
        from app.rules import regeneration_riders

        auto = [cid for cid in cards if automatic(plan, cid) or regeneration_riders.shields(plan, plan.oid(cid))]
        if not auto:
            return True
        candidates = {cid: options(plan, cid, can_regenerate=can_regenerate, effect=not sba) for cid in auto}
        saved = dict(ctx) if ctx is not None else None
        if saved is not None:
            saved['next'] = max(0, saved['next'] - 1)
        frame = Preparation(objects, candidates, can_regenerate, sba, saved)
    return not _offer(plan, frame)


def resume(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError

    raw = plan.rules.destruction_replacements
    if raw is None or len(chosen) != 1 or chosen[0] not in {o.id for o in decision.options}:
        raise ActionError('Choose one of the destruction replacements')
    frame = _FRAME.validate_python(raw)
    cid, oid = decision.resume['card'], decision.resume['object']
    frame.chosen[oid] = frame.candidates[cid][int(chosen[0])].key
    if _offer(plan, frame):
        return
    if frame.ctx is not None:
        from app.rules.effects import continue_effects

        continue_effects(plan, frame.ctx)


def protect(plan: Plan, cards: list[str], actor: str | None) -> list[str]:
    from app.rules import regeneration, shield_counters

    raw = plan.rules.destruction_replacements
    if raw is None:
        return cards
    frame = _FRAME.validate_python(raw)
    kept = []
    for cid in cards:
        oid = frame.objects.get(cid)
        key = frame.chosen.get(oid or '')
        candidate = next((c for c in frame.candidates.get(cid, []) if c.key == key), None)
        if candidate is None:
            kept.append(cid)
        elif key in ('automatic', 'shield') or (key or '').startswith('rider:'):
            regeneration.regenerate(plan, plan.state.cards[cid], consume=key != 'automatic',
                                    shield_id=key.removeprefix('rider:') if key and key.startswith('rider:') else None)
        elif key == 'counter':
            shield_counters.remove(plan, [cid], actor)
        elif candidate.aura:
            aura = plan.state.cards.get(candidate.aura)
            if aura is not None and plan.oid(aura) == candidate.aura_object and aura.zone.endswith(':battlefield'):
                regeneration.use_umbra_armor(plan, plan.state.cards[cid], aura, actor)
            else:
                # The replacement was applicable before this simultaneous batch.
                card = plan.state.cards[cid]
                if card.damage:
                    plan.do({'type': 'set_damage', 'card_ids': [cid], 'value': 0}, actor=actor)
                plan.rules.deathtouched = [c for c in plan.rules.deathtouched if c != cid]
    return [c for c in kept if c in plan.state.cards and plan.state.cards[c].zone.endswith(':battlefield')]


def finish(plan: Plan) -> None:
    plan.rules.destruction_replacements = None
