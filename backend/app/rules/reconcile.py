"""Reconciliation: bringing the rules bookkeeping back in line with the table.

While automation is OFF or paused, players manipulate the table by hand, so the old rules state
may no longer describe it. When automation is turned back on (or resumed), this runs *before*
the engine acts again:

* what can be derived from the table is derived (the step, priority, combat bookkeeping, which
  permanents are where, whether a pending decision still makes sense);
* what the recorded manual events show is taken in (a land moved from hand to the battlefield is
  the land for the turn);
* what can't be known is **asked**, never invented: one concise list, answered by the player who
  knows ("Did Llanowar Elves come under your control this turn?" [This turn] [Earlier] [Leave it
  manual]). "Leave it manual" takes that card out of automation.

It is compiled like an intent (steps recorded on the ``configure`` action), so replay never
re-runs it.
"""

from __future__ import annotations

from typing import Any

from app.game import actions as A
from app.game.rules_state import ControlMark, Decision, DecisionOption, ReconcileItem, TurnCount
from app.game.state import COMBAT_PHASES, PHASES, GameState, zone_key
from app.rules.characteristics import CardInfo
from app.rules.plan import Plan, decide

MAIN1 = PHASES.index("main1")


def needs_reconcile(state: GameState, a: A.Configure) -> bool:
    turning_on = a.automation not in (None, "off") and state.settings.automation == "off"
    resuming = a.automation_paused is False and state.rules is not None and state.rules.paused
    return turning_on or resuming


def compile_reconcile(state: GameState, a: A.Configure, *, actor: str, info: CardInfo, rng: Any) -> list[dict[str, Any]]:
    from app.game.handlers.objects import configure  # handlers → rules; imported late

    fresh = state.rules is None
    scratch = state.model_copy(deep=True)
    configure(scratch, a.model_copy(update={"r": None}))  # the settings change itself, then reconcile
    plan = Plan(scratch, actor, info, rng)
    reconcile(plan, fresh=fresh)
    plan.do({"type": "rules_sync", "rules": plan.rules.model_dump(mode="json")})
    return plan.steps


def reconcile(plan: Plan, *, fresh: bool) -> None:
    from app.rules.engine import absorb_manual_events, sync_step  # engine imports rules modules

    r = plan.rules
    absorb_manual_events(plan)
    unknown_history = fresh or r.events_dropped
    r.events = []
    r.events_dropped = False
    r.unsynced = False
    sync_step(plan)
    _derive(plan)
    questions = _questions(plan, unknown_history=unknown_history)
    r.reconcile = [item for item, _ in questions]
    if questions:
        options = [o for _, opts in questions for o in opts]
        n = len(questions)
        decide(plan, player=plan.turn_player, kind="reconcile",
               prompt=f"Automation needs {n} answer{'s' if n != 1 else ''} it can't work out from the table",
               options=options, min_choices=n, max_choices=n, resume={"step": "reconcile"})
    elif r.decision is None and (r.priority is None or r.priority not in plan.live()):
        r.priority = plan.active
    plan.note("Automation reconciled with the table" + (f": {len(questions)} to confirm" if questions else ""))


def _derive(plan: Plan) -> None:
    """Everything that follows from the table alone."""
    r = plan.rules
    state = plan.state
    cards = state.cards
    live = set(plan.live())
    on_battlefield = {cid for cid, c in cards.items() if c.zone.endswith(":battlefield")}
    r.blocked = [cid for cid in r.blocked if cid in cards and cards[cid].attacking is not None]
    r.deathtouched = [cid for cid in r.deathtouched if cid in on_battlefield]
    r.commander_offered = {cid: z for cid, z in r.commander_offered.items() if cid in cards}
    r.card_modes = {cid: m for cid, m in r.card_modes.items() if cid in cards}
    r.blockers_pending = [p for p in r.blockers_pending if p in live]
    r.passed = [p for p in r.passed if p in live]
    for prefs in r.prefs.values():
        prefs.mana_sources = {cid: v for cid, v in prefs.mana_sources.items() if cid in cards}
        prefs.stop_after = None  # stack objects may have changed by hand
        prefs.pass_until, prefs.pass_mark = None, ""
    if state.turn.phase not in COMBAT_PHASES:
        r.blocked, r.blockers_pending, r.no_attackers, r.combat_round = [], [], False, ""
    d = r.decision
    if d is not None and r.payment_outer is not None and _stale(plan, d):  # -- review 28D -- a stale nested choice: back to its payment,
        from app.rules import casting  # which is checked in turn

        casting.unnest(plan)
        d = r.decision
    if d is not None and _stale(plan, d):
        r.decision = None
        r.payment_outer = None
        r.priority = plan.active
        plan.note("A pending decision no longer matched the table and was cancelled")


def _stale(plan: Plan, d: Decision) -> bool:
    state = plan.state
    if d.player not in plan.live():
        return True
    if d.kind == "declare_attackers" and state.turn.phase != "declare_attackers":
        return True
    if d.kind == "declare_blockers" and state.turn.phase != "declare_blockers":
        return True
    referenced = [o.card_id for o in d.options if o.card_id]
    resume = d.resume or {}
    referenced += [c for c in resume.get("cards", []) if isinstance(c, str)]
    if isinstance(resume.get("card"), str):
        referenced.append(resume["card"])
    return any(cid not in state.cards for cid in referenced)


def _questions(plan: Plan, *, unknown_history: bool) -> list[tuple[ReconcileItem, list[DecisionOption]]]:
    """Facts the engine needs but the table can't show. Only asked when they matter now."""
    state = plan.state
    r = plan.rules
    ap = plan.active
    out: list[tuple[ReconcileItem, list[DecisionOption]]] = []
    if not unknown_history:
        return out
    turn = state.turn.number
    # Summoning sickness of the active player's creatures (the only ones it matters for this turn).
    if state.seq > 0:
        for cid in state.zones.get(zone_key(ap, "battlefield"), []):
            card = state.cards[cid]
            if card.controller != ap or r.card_mode(cid) == "manual" or not plan.ch(card).is_creature:
                continue
            item = ReconcileItem(id=f"sick:{cid}", card=cid, player=ap,
                                 question=f"Did {card.name or 'this creature'} come under your control this turn?")
            out.append((item, [
                DecisionOption(id=f"{cid}:new", label="This turn", card_id=cid, group=item.id),
                DecisionOption(id=f"{cid}:old", label="Before this turn", card_id=cid, group=item.id),
                DecisionOption(id=f"{cid}:manual", label="Leave it manual", card_id=cid, group=item.id),
            ]))
    # The land for the turn (only matters in the active player's main phases and later).
    phase = state.turn.phase
    if phase in PHASES and PHASES.index(phase) >= MAIN1 and r.lands_this_turn(ap, turn) == 0:
        item = ReconcileItem(id="land", player=ap, question=f"Has {plan.name(ap)} played a land this turn?")
        out.append((item, [
            DecisionOption(id="land:yes", label="Yes", group=item.id),
            DecisionOption(id="land:no", label="Not yet", group=item.id),
        ]))
    return out


def resume_reconcile(plan: Plan, d: Decision, chosen: list[str]) -> None:
    r = plan.rules
    turn = plan.state.turn.number
    for answer in chosen:
        subject, _, value = answer.rpartition(":")
        if subject == "land":
            if value == "yes":
                r.lands_played[d.player] = TurnCount(turn=turn, count=1)
            continue
        card = plan.state.cards.get(subject)
        if card is None:
            continue
        if value == "manual":
            r.card_modes[subject] = "manual"
        else:
            r.controlled_since[subject] = ControlMark(controller=card.controller, turn=turn if value == "new" else 0)
    r.reconcile = []
    plan.note(f"{plan.name(d.player)} answered the reconciliation questions")
    r.passed = []
    r.priority = plan.active
