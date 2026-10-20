"""Saved joint prevention choices feeding the existing native damage commit sites."""
from __future__ import annotations

import copy
import json
import secrets
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules import group_choice, replace
from app.rules import prevention_frontier_joint_draft as joint
from app.rules import prevention_frontier_journal as journal
from app.rules import prevention_frontier_planner_adapter as adapter
from app.rules.prevention_frontier_eligibility import eligible as eligible

if TYPE_CHECKING:
    from app.rules.plan import Plan

PREFIX = 'joint_prevention_frame'
STEP = 'joint_prevention_question'


class JointAsk(replace.ShieldAsk):
    def __init__(self, frame: journal.Frame, question: journal.Question):
        target = json.loads(question.key)[2]
        super().__init__(target, question.actor, json.loads(frame.events), question.maximum)
        self.frame = frame
        self.question = question


def _reject_legacy_finite(plan: Plan, ids: set[str]) -> None:
    for candidate in replace.damage_candidates(plan):
        if (candidate.id in ids and candidate.op.get('do') in ('finite_prevention', 'redirect')
                and candidate.op.get('allocate') and candidate.op.get('joint_prevention') is not True):
            raise ValueError('This existing finite effect requires its original single-recipient chooser')


def _question(plan: Plan, frame: journal.Frame) -> journal.Question | joint.Completed:
    result = journal.question(plan, frame)
    ids = set(result.candidates) if isinstance(result, journal.Question) else {pool.id for pool in result.frontier.pools}
    _reject_legacy_finite(plan, ids)
    return result


def plan_damage(plan: Plan, events: list[dict[str, Any]], *, answers: dict[str, str], order: list[str] | None,
                ask: bool, cands: list[replace.Candidate] | None = None) -> replace.DamagePlan | JointAsk:
    # Only trusted marked native batches or validated saved frames route here.
    if cands is not None:
        from app.rules import prevention_frontier_grounding as native

        if native._canonical(cands) != native._canonical(replace.damage_candidates(plan)):
            raise ActionError('The joint damage candidate manifest differs from the native batch')
    try:
        frame = (journal.Frame.loads(answers[PREFIX]) if PREFIX in answers else
                 journal.start(plan, events, batch=secrets.token_hex(8)))
        current = journal.start(plan, events, batch=frame.batch)
        if current.events != frame.events or current.candidates != frame.candidates or current.subjects != frame.subjects:
            raise ValueError('The original joint damage batch changed')
        planner = replace.Planner(plan, replace.damage_candidates(plan), ask=False)
        sim = {'shields': dict(plan.rules.prevention)}
        reachable = {candidate.id for event in json.loads(current.events) for candidate in planner.cands
                     if planner.applies(candidate, event, sim)}
        _reject_legacy_finite(plan, reachable)
        question = _question(plan, frame)
        if isinstance(question, joint.Completed):
            return adapter.damage_plan(plan, question, events)
        # An unresolved preview reports its question without deciding or consuming.
        # Actual sites must supply a saved continuation before asking/committing.
        return JointAsk(frame, question)
    except ValueError as error:
        raise ActionError(str(error)) from error


def ask(plan: Plan, request: JointAsk, site_resume: dict[str, Any], order: list[str]) -> None:
    from app.rules.plan import decide

    q = request.question
    if q.kind == 'order':
        candidates = {c.id: c for c in replace.damage_candidates(plan)}
        options = [DecisionOption(id=cid, label=candidates[cid].label, card_id=candidates[cid].source_card) for cid in q.candidates]
        prompt = 'Which replacement or prevention effect applies first? (616.1)'
    else:
        options = [DecisionOption(id=group_choice.NUMBER, label='Type a number ≥ 0', group='number')]
        prompt = f'Allocate how much damage to this effect? (at most {q.maximum})'
    decide(plan, player=q.actor, kind='choose_one', prompt=prompt, options=options,
           resume={'step': STEP, 'frame': request.frame.dumps(), 'site_resume': copy.deepcopy(site_resume), 'order': list(order)})


def resume(plan: Plan, decision: Any, chosen: list[str]) -> None:
    try:
        frame = journal.Frame.loads(decision.resume['frame'])
        question = _question(plan, frame)
        if not isinstance(question, journal.Question) or decision.player != question.actor:
            raise ValueError('The pending native joint chooser changed')
        if question.kind == 'order':
            frame = journal.choose_order(plan, frame, chosen[0], decision.player)
        else:
            frame = journal.choose_amount(plan, frame, int(chosen[0]), decision.player)
        next_question = _question(plan, frame)
        site = decision.resume['site_resume']
        order = list(decision.resume.get('order') or [])
        if isinstance(next_question, journal.Question):
            ask(plan, JointAsk(frame, next_question), site, order)
            return
        answers = dict(site.get('answers') or {})
        answers[PREFIX] = frame.dumps()
        replace.resume_site(plan, site, answers, order)
    except ValueError as error:
        raise ActionError(str(error)) from error


RESUME = {STEP: resume}
