"""Unimported untap replacement model; producer provenance is an explicit gate.

No layer, turn, spell, Q-cost or production registry hooks. Grant identities must
come from the actual native grant constructor, which currently lacks a capture
API. This model never reconstructs them from rendered index 100+k or names.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, ObjectRef

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'untap_attempt45'
QUOTE = ('If this creature would untap during your untap step, remove a +1/+1 counter from it instead. '
         'If you do, untap it.')


class NativeGrant(BaseModel):
    source: ObjectRef
    ability: int = Field(ge=0)
    ordinal: int = Field(ge=0)

    def key(self) -> str:
        return f'grant:{self.source.object_id}:{self.ability}:{self.ordinal}'


class Removal(BaseModel):
    effect: str
    kind: str
    actual: int = Field(ge=0, le=1)


class TurnFinish(BaseModel):
    previous: tuple[str, int]
    skipped: list[tuple[str, int]] = Field(default_factory=list)
    stunned: list[str] = Field(default_factory=list)
    plain: bool
    keep: list[str] = Field(default_factory=list)
    same_turn: bool = False


class UntapAttempt(BaseModel):
    recipient: ObjectRef
    actor: str
    step_player: str | None = None
    grants: list[NativeGrant] = Field(default_factory=list)
    ancestry: list[str] = Field(default_factory=list)
    removals: list[Removal] = Field(default_factory=list)
    status: Literal['pending', 'untapped', 'replaced', 'gone'] = 'pending'
    turn_finish: TurnFinish | None = None
    ctx: dict[str, Any] | None = None
    finished: bool = False


def quoted(text: str) -> bool:
    return text.replace('This creature', 'this creature').replace('This permanent', 'this creature').replace(
        'this permanent', 'this creature').replace('~', 'this creature') == QUOTE


def definition(text: str) -> dict[str, Any] | None:
    """Explicit staging descriptor, not a supported production reader."""
    return {'kind': 'replacement', 'replacement': STEP, 'effects': []} if quoted(text) else None


def _recipient(plan: Plan, frame: UntapAttempt) -> Any:
    from app.rules import context

    card = context._same(plan, frame.recipient)
    return card if card is not None and card.zone.endswith(':battlefield') and plan.in_game(card) else None


def _live_grant(plan: Plan, frame: UntapAttempt, grant: NativeGrant, card: Any) -> bool:
    from app.rules import context, scripts, statics

    source = context._same(plan, grant.source)
    if source is None or not source.zone.endswith(':battlefield') or not plan.in_game(source):
        return False
    # Check the explicit producer identity against native source definitions and
    # native subject/attachment rules. Final per-grant wipe provenance remains
    # the native producer's responsibility, not a positional-index guess here.
    native = scripts.definitions(plan.ch(source)).get(grant.ability)
    texts = (native or {}).get('grants') or []
    if native is None or grant.ordinal >= len(texts) or not quoted(texts[grant.ordinal]):
        return False
    ch = plan.ch(card)
    if not any(quoted(ability.text) for ability in ch.abilities):
        return False
    return bool(statics.applies(plan, native, source=source, controller=source.controller, card=card, ch=ch, conditions=True))


def available(plan: Plan, frame: UntapAttempt) -> list[tuple[str, str]]:
    card = _recipient(plan, frame)
    if card is None or not card.tapped:
        return []
    out = []
    stun = 'stun:' + frame.recipient.object_id
    if card.counters.get('stun', 0) and stun not in frame.ancestry:
        out.append((stun, 'Remove a stun counter instead'))
    if frame.step_player == card.controller:
        out.extend((g.key(), 'Apply the granted counter-removal untap replacement') for g in frame.grants
                   if g.key() not in frame.ancestry and _live_grant(plan, frame, g, card))
    return out


def apply(plan: Plan, frame: UntapAttempt, selected: str) -> None:
    from app.rules import counter_removal_results

    if frame.status != 'pending' or selected not in {key for key, _ in available(plan, frame)}:
        raise ActionError('Choose an applicable untap replacement')
    # Seal ancestry BEFORE running the chosen replacement's action/contained
    # event. Native literal counter removal is permission-checked centrally.
    frame.ancestry.append(selected)
    kind = 'stun' if selected.startswith('stun:') else '+1/+1'
    actual = counter_removal_results.remove(plan, frame.recipient.card, kind, 1, by=frame.actor)
    frame.removals.append(Removal(effect=selected, kind=kind, actual=actual))
    if kind == 'stun' or actual != 1:
        frame.status = 'replaced'
    # A successful Leech replacement has a contained untap, with SAME ancestry.


def run(plan: Plan, frame: UntapAttempt) -> bool:
    from app.rules.plan import decide

    while frame.status == 'pending':
        card = _recipient(plan, frame)
        if card is None:
            frame.status = 'gone'
            break
        if not card.tapped:
            frame.status = 'untapped'
            break
        choices = available(plan, frame)
        if len(choices) == 1:
            apply(plan, frame, choices[0][0])
            continue
        if choices:
            decide(plan, player=card.controller, kind='choose_one', prompt='Choose the replacement for this untap',
                   options=[DecisionOption(id=key, label=label, card_id=card.id) for key, label in choices],
                   resume={'step': STEP, 'frame': frame.model_dump(mode='json')})
            return False
        plan.do({'type': 'tap', 'card_ids': [card.id], 'tapped': False}, actor=frame.actor)
        frame.status = 'untapped'
    return True


def finish(plan: Plan, frame: UntapAttempt) -> None:
    from app.rules import effects, engine

    if frame.finished or frame.status == 'pending':
        raise ActionError('The untap attempt has no new terminal result')
    frame.finished = True
    if frame.turn_finish is not None:
        native = frame.turn_finish
        # This original attempt must not be retried by the ordinary finisher,
        # whether it untapped or was replaced by a successful/failed removal.
        handled = frame.recipient.card
        engine.finish_turn_start(plan, [cid for cid in native.stunned if cid != handled], native.previous,
                                 native.skipped, native.plain, [*native.keep, handled], same_turn=native.same_turn)
    elif frame.ctx is not None:
        frame.ctx['_untap_attempt45_result'] = frame.model_dump(mode='json', exclude={'ctx'})
        effects.continue_effects(plan, frame.ctx)


def begin(plan: Plan, frame: UntapAttempt) -> None:
    if run(plan, frame):
        finish(plan, frame)


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    frame = UntapAttempt.model_validate(d.resume['frame'])
    if len(chosen) != 1 or chosen[0] not in {option.id for option in d.options}:
        raise ActionError('Choose one offered untap replacement')
    # An administrative edit can invalidate a saved original object/effect.
    # Reevaluate that same attempt; never bind its ancestry to a new object.
    if chosen[0] in {key for key, _ in available(plan, frame)}:
        apply(plan, frame, chosen[0])
    if run(plan, frame):
        finish(plan, frame)


RESUME = {STEP: resume}
