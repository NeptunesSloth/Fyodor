"""Typed opponent-delegated target announcement before native activation costs.

The exact definition opts into this announcement path after whole-card proof.
Target legality always belongs to the original ability controller; selecting a
target grants the opponent neither cancellation nor payment authority.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

OPPONENT = 'delegated_target_opponent'
CREATURE = 'delegated_target_creature'
TEXT = "{3}, {T}: The next time a source of your choice would deal damage to you this turn, that damage is dealt to target creature of an opponent's choice instead."


PREACHER = "{T}: For as long as this creature remains tapped, gain control of target creature of an opponent's choice they control."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.kind == 'activated' and ability.text == PREACHER:  # -- delegated (wave 110D) -- the chosen opponent picks among THEIR creatures
        from app.rules import scripts

        d = scripts.define(replace(ability, text="{T}: For as long as this creature remains tapped, gain control of target creature."), ch)
        return {**d, 'delegated_target': 'opponent', 'delegated_controls110d': True} if d else None
    if (own := _opp_definition(ability, ch)) is not None:  # -- delegated (wave 110D) -- spells, triggers and a mixed own + opponent pair
        return own
    if ability.kind != 'activated' or ability.text != TEXT:
        return None
    return {'kind': 'activated', 'cost': ability.cost, 'target': {'what': 'creature'},
            'delegated_target': 'opponent', 'effects': [
                {'do': 'source_shield', 'props': {}, 'to': 'you', 'once': True, 'redirect': 'target'}]}


EVANGELIZE = "Gain control of target creature of an opponent's choice they control."
ARENA = "{3}, {T}: Tap target creature you control and target creature of an opponent's choice they control. Those creatures fight each other."
TURNKEY = "When this creature enters, return target creature card of an opponent's choice from your graveyard to your hand."
OWN = 'own_opponent110d'
ECHO = ("{4}, {T}: An opponent chooses target creature they control. Create a token that's a copy of that creature. That token gains haste until end of turn. "
        "Exile the token at the beginning of the next end step. Activate only as a sorcery.")
PAIRS = {  # Cuombajj Witches, Diaochan Artful Beauty: "<effect> target X ... <effect> target X of an opponent's choice" (any legal object)
    "{T}: This creature deals 1 damage to any target and 1 damage to any target of an opponent's choice.":
        "{T}: This creature deals 1 damage to any target and 1 damage to any target.",
    "{T}: Destroy target creature of your choice, then destroy target creature of an opponent's choice. Activate only during your turn, before attackers are declared.":
        "{T}: Destroy target creature, then destroy target creature. Activate only during your turn, before attackers are declared.",
}


def _opp_definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    """Evangelize (spell), Arena (own target + opponent's pick, then they fight: 701.14a), Mausoleum Turnkey (trigger, 603.3d: its controller
    puts it on the stack, the chosen opponent picks the target). The ability's controller keeps legality, payment and cancellation."""
    from app.rules import scripts

    text = ability.text.split(' (')[0]
    if ability.kind == 'spell' and text == EVANGELIZE:
        d = scripts.define(replace(ability, text="Gain control of target creature."), ch)
        return {**d, 'delegated_target': 'opponent', 'delegated_controls110d': True} if d else None
    if ability.kind == 'activated' and text == ARENA:
        d = scripts.define(replace(ability, text="{3}, {T}: Tap target creature you control and target creature an opponent controls."), ch)
        if not d:
            return None
        return {**d, 'effects': [*d['effects'], {'do': 'fight', 'who': 'target:0', 'with': 'target:1'}],
                'delegated_target': OWN, 'delegated_controls110d': True}
    if ability.kind == 'activated' and text == ECHO:  # "An opponent chooses target creature they control": the same announcement (115.1)
        d = scripts.define(replace(ability, text=ECHO.replace("An opponent chooses target creature they control. Create a token that's a copy of that creature.",
                                                              "Create a token that's a copy of target creature.")), ch)
        return {**d, 'delegated_target': 'opponent', 'delegated_controls110d': True} if d else None
    if ability.kind == 'activated' and text in PAIRS:  # your own first target, then the chosen opponent's pick among all legal ones
        d = scripts.define(replace(ability, text=PAIRS[text]), ch)
        return {**d, 'delegated_target': OWN} if d else None
    if ability.kind == 'triggered' and text == TURNKEY:
        d = scripts.define(replace(ability, text="When this creature enters, return target creature card from your graveyard to your hand."), ch)
        return {**d, 'target_choice': 'opponent110d'} if d else None
    return None


@dataclass
class Announcement:
    actor: str
    source_card: str
    source_object: str
    ability: int
    text: str
    intent: dict[str, Any]
    name: str
    definition: dict[str, Any]
    mode: str = 'opponent'
    opponent: str | None = None
    first: dict[str, Any] | None = None


_FRAME = TypeAdapter(Announcement)


def _mode(definition_: dict[str, Any]) -> str | None:
    marker = definition_.get('delegated_target')
    if marker == 'opponent':
        return 'opponent'
    if marker == OWN:
        return OWN
    if marker == {'kind': 'target_controller', 'of': 0, 'group': 1}:
        from app.rules import scripts

        specs = scripts.target_groups(definition_)
        if len(specs) == 2 and all(s.get('min', 1) == s.get('max', 1) == 1
                                   and set(s) <= {'what', 'min', 'max'} and s.get('what') for s in specs):
            return 'target_controller'
    return None


def handles(definition_: dict[str, Any]) -> bool:
    return _mode(definition_) is not None


def _resume(step: str, frame: Announcement, *, invalid: bool = False) -> dict[str, Any]:
    return {'step': step, 'frame': _FRAME.dump_python(frame, mode='json'),
            'intent': frame.intent, **({'invalid': True} if invalid else {})}


def _source(plan: Plan, frame: Announcement) -> tuple[Any, Any, Any]:
    if frame.actor not in plan.live():
        raise ActionError('The original activator has left the game')
    card = plan.state.cards.get(frame.source_card)
    if card is None or plan.oid(card) != frame.source_object or card.controller != frame.actor:
        raise ActionError('The original activating object has changed')
    ch = plan.ch(card)
    if frame.text == '':  # a spell still in its announcement
        return card, ch, None
    ability = next((a for a in ch.abilities if a.index == frame.ability and a.text == frame.text), None)
    if ability is None or ability.kind != 'activated' or not handles(frame.definition):
        raise ActionError('The original activated ability has changed')
    return card, ch, ability


def cast_action(frame: Announcement) -> A.CastSpell:
    action = A.parse_action(frame.intent)
    assert isinstance(action, A.CastSpell)
    return action


def _legal(plan: Plan, frame: Announcement, *, first: bool = False) -> list[str]:
    from app.rules import casting, scripts, targets

    _source(plan, frame)
    spell = frame.text == ''
    source = (casting._target_source(plan, cast_action(frame)) if spell
              else targets.source_of(plan, frame.source_card, object_id=frame.source_object))
    selector = scripts.target_groups(frame.definition)[0 if first else 1]['what'] if frame.mode in ('target_controller', OWN) else 'creature'
    legal = targets.legal_targets(plan, selector, frame.actor, source, frame.source_card, **({} if spell else {'source_object': frame.source_object}))
    if frame.definition.get('delegated_controls110d') and frame.opponent and not first:
        legal = [c for c in legal if plan.state.cards[c].controller == frame.opponent]
    if first:
        from app.rules import flagbearer86

        legal = flagbearer86.single(plan, legal, actor=frame.actor)
    return legal


def announce(plan: Plan, action: A.CastSpell | A.ActivateAbility, definition_: dict[str, Any], what: str) -> Any:
    from app.rules.plan import decide

    spell = isinstance(action, A.CastSpell)
    mode = _mode(definition_)
    if spell and mode != 'opponent':
        raise ActionError('Delegated target announcement is only available to this activated ability')
    if spell and getattr(plan, 'delegated110d', None):  # the chosen opponent's pick, checked when they made it (resume_creature)
        from app.rules import casting

        if list(action.targets) != [plan.delegated110d]:
            raise ActionError('The chosen opponent must select this spell’s target')
        return casting.ChosenTargets(flat=[casting.target_ref(plan, str(plan.delegated110d))])
    if mode is None:
        raise ActionError('Unsupported delegated target announcement')
    if action.targets and (mode == 'opponent' or len(action.targets) != 1):
        raise ActionError('The chosen opponent must select this ability’s target')
    card = plan.state.cards[action.card_id]
    ch = plan.ch(card)
    ability = None if isinstance(action, A.CastSpell) else next((a for a in ch.abilities if a.index == action.ability), None)
    if not spell and (ability is None or ability.kind != 'activated'):
        raise ActionError('This ability has no supported delegated target announcement')
    frame = Announcement(plan.actor, card.id, plan.oid(card), -1 if ability is None or isinstance(action, A.CastSpell) else action.ability, '' if ability is None else ability.text,
                         action.model_dump(mode='json', exclude={'r', 'actor', 'ts'}), what, definition_, mode)
    if not _legal(plan, frame, first=mode != 'opponent') or not _legal(plan, frame):
        raise ActionError(f'{what} has no legal target')
    if mode != 'opponent':
        if action.targets:
            _first_target(plan, frame, action.targets[0])
        else:
            from app.rules import casting

            decide(plan, player=frame.actor, kind='choose_one', prompt=f'Choose the first target for {what}',
                   options=[DecisionOption(id=cid, label=casting.target_label(plan, cid), card_id=cid if cid in plan.state.cards else None)
                            for cid in _legal(plan, frame, first=True)], resume=_resume(OPPONENT, frame))
        return None
    opponents = [pid for pid in plan.live() if pid != frame.actor]
    if not opponents:
        raise ActionError('There is no opponent to select the target')
    decide(plan, player=frame.actor, kind='choose_one', prompt=f'Choose an opponent to select the target for {what}',
           options=[DecisionOption(id=pid, label=plan.name(pid)) for pid in opponents], resume=_resume(OPPONENT, frame))
    return None


def _first_target(plan: Plan, frame: Announcement, cid: str) -> None:
    from app.rules import casting

    if cid not in _legal(plan, frame, first=True):
        raise ActionError('The first target is not legal for the original activator')
    first = casting.target_ref(plan, cid).model_dump(mode='json')
    if frame.mode == OWN:  # the opponent is chosen by the activator (one opponent: no question)
        opponents = [pid for pid in plan.live() if pid != frame.actor]
        frame = replace(frame, first=first)
        if len(opponents) == 1:
            _creature_choice(plan, replace(frame, opponent=opponents[0]))
        else:
            from app.rules.plan import decide

            decide(plan, player=frame.actor, kind='choose_one', prompt=f'Choose an opponent to select the target for {frame.name}',
                   options=[DecisionOption(id=pid, label=plan.name(pid)) for pid in opponents], resume=_resume(OPPONENT, frame))
        return
    frame = replace(frame, first=first, opponent=plan.state.cards[cid].controller)
    _creature_choice(plan, frame)


def _creature_choice(plan: Plan, frame: Announcement) -> None:
    from app.rules import casting
    from app.rules.plan import decide

    try:
        legal = _legal(plan, frame)
        if frame.first is not None:
            cid = frame.first['id']
            if (cid not in _legal(plan, frame, first=True)
                    or (frame.first.get('object_id') and plan.oid(cid) != frame.first.get('object_id'))):
                raise ActionError('The original first target is no longer legal')
    except ActionError as exc:
        _invalid(plan, frame, str(exc))
        return
    if not legal or frame.opponent not in plan.live():
        _invalid(plan, frame, 'The original ability has no legal target or choosing player')
        return
    assert frame.opponent is not None
    decide(plan, player=frame.opponent, kind='choose_one', prompt=f'Choose a creature target for {frame.name}',
           options=[DecisionOption(id=cid, label=casting.target_label(plan, cid), card_id=cid if cid in plan.state.cards else None) for cid in legal],
           resume=_resume(CREATURE, frame))


def _invalid(plan: Plan, frame: Announcement, message: str) -> None:
    from app.rules.plan import decide

    if frame.actor not in plan.live():
        plan.rules.priority = next(iter(plan.live()), None)
        return
    decide(plan, player=frame.actor, kind='choose_one', prompt=f'{message}. Cancel the original announcement.',
           options=[], resume=_resume(OPPONENT, frame, invalid=True))


def resume_opponent(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import casting

    frame = _FRAME.validate_python(decision.resume['frame'])
    if decision.player != frame.actor:
        raise ActionError('Only the original activator may choose the opponent or cancel')
    if casting.cancelled(plan, decision, chosen):
        return
    if decision.resume.get('invalid'):
        raise ActionError('Only the original activator may cancel this invalid announcement')
    if frame.mode == 'target_controller' or (frame.mode == OWN and frame.first is None):
        if len(chosen) != 1:
            raise ActionError('Choose one first target')
        try:
            _first_target(plan, frame, chosen[0])
        except ActionError as exc:
            _invalid(plan, frame, str(exc))
        return
    if len(chosen) != 1 or chosen[0] == frame.actor or chosen[0] not in plan.live():
        raise ActionError('Choose an opponent still in the game')
    frame = replace(frame, opponent=chosen[0])
    _creature_choice(plan, frame)


def resume_creature(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import casting

    frame = _FRAME.validate_python(decision.resume['frame'])
    if decision.player != frame.opponent or plan.actor != frame.opponent:
        raise ActionError('Only the chosen opponent may select the target')
    try:
        card, ch, ability = _source(plan, frame)
        legal = _legal(plan, frame)
        if frame.first is not None and (frame.first['id'] not in _legal(plan, frame, first=True)
                                       or (frame.first.get('object_id') and plan.oid(frame.first['id']) != frame.first.get('object_id'))):
            raise ActionError('The original first target is no longer legal')
    except ActionError as exc:
        _invalid(plan, frame, str(exc))
        return
    if len(chosen) != 1 or chosen[0] not in legal:
        _invalid(plan, frame, 'The selected target is no longer legal')
        return
    if frame.text == '':  # a spell: cast again with the chosen target, as the original caster (601.2c)
        from app.rules.engine import INTENTS

        intent = A.parse_action({**frame.intent, 'targets': list(chosen), 'actor': frame.actor})
        actor = plan.actor
        plan.actor, plan.delegated110d = frame.actor, chosen[0]
        plan.rules.priority, plan.rules.passed = frame.actor, []
        try:
            INTENTS[intent.type](plan, intent)
        finally:
            plan.actor, plan.delegated110d = actor, None
        return
    definition_ = {k: v for k, v in frame.definition.items() if k != 'delegated_target'}
    combined = ([frame.first['id']] if frame.first else []) + list(chosen)
    intent = A.ActivateAbility.model_validate({**frame.intent, 'targets': combined, 'actor': frame.actor,
                                             **({'target_counts': [1, 1]} if frame.first else {})})
    actor, reserved = plan.actor, plan.reserved_life
    plan.actor = frame.actor
    plan.rules.priority, plan.rules.passed = frame.actor, []
    try:
        from app.rules import cost_payment

        cost = casting.ability_cost(ch, ability, state=plan.state, card=card, info=plan.info, target=combined[0])
        problem = casting.ability_problem(plan.state, frame.actor, card, ch, ability, cost, plan=plan)
        problem = problem or cost_payment.problem(plan, cost, card, frame.actor, intent.x_value)
        if problem:
            _invalid(plan, frame, problem)
            return
        # An unaffordable automatic/explicit payment must not strand the
        # opponent at a payer-owned announcement. This is the ordinary pure
        # payment finder; self-payment remains free to open its native prompt.
        if intent.sources is not None or casting.payment_mode(plan, frame.actor) != 'self':
            from app.rules import mana

            try:
                casting.find_payment(plan.state, frame.actor, mana.parse_cost(cost.mana), plan.info,
                                     sources=intent.sources, exclude=cost_payment.excluded(cost, card, {}),
                                     purpose=casting.Purpose(ability_of=ch), reserve=plan.reserved_life)
            except ActionError as exc:
                _invalid(plan, frame, str(exc))
                return
        casting.activate_to_stack(plan, card, ch, ability, intent, definition=definition_)
    finally:
        plan.actor, plan.reserved_life = actor, reserved


RESUME = {OPPONENT: resume_opponent, CREATURE: resume_creature}
