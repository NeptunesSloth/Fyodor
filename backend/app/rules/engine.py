"""The rules engine: turns a player's *intent* into ordinary table actions.

``compile_intent`` validates the intent against the rules, then carries it out on a scratch copy
of the table, step by step, with the same primitive actions the sandbox uses (``move``,
``draw``, ``phase``…). It returns those steps. ``resolve`` records them on the intent, and
``apply`` replays them. That means:

* undo takes back a whole intent (a pass that ran through three steps and a draw is one entry);
* replaying history never re-runs rules code, so changing the rules can't break old saves;
* the table stays the single source of truth: everything the engine does is a visible, logged
  table action, and anything it doesn't do can still be done by hand.

Milestone 14 (this module's scope today): priority with Arena-style stops, the turn structure
with its turn-based actions (untap, draw, discard to hand size, damage wearing off), playing
lands, resolving the stack with a *manual resolution* step for effects the engine doesn't
automate, decisions, and conceding. Casting, abilities and combat arrive with milestone 15.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import Decision, DecisionOption, PaymentRecord, PlayerPrefs, TurnCount, Yield
from app.game.state import STACK, CardInstance, GameState, zone_key
from app.rules import (
    attachments,
    battles,
    casting,
    combat,
    copying,
    cost_payment,
    coverage,
    delayed,
    effects,
    layers,
    looking,
    modal_abilities,
    optional_payment,
    permissions,
    reconcile,
    replacements,
    sba,
    scripts,
    triggers,
)
from app.rules.characteristics import CardInfo, Characteristics
from app.rules.leave import leave_game
from app.rules.plan import Plan, decide, require_no_decision, require_priority
from app.rules.targets import still_legal

MAIN_PHASES = ("main1", "main2")
MAX_HAND_SIZE = 7

NOT_YET: dict[str, str] = {}


# -- entry point -------------------------------------------------------------------------
RULES_ENGINE_VERSION = 2  # bump when the rules engine's behaviour changes (saved with scenarios/diagnostics)
PREF_INTENTS = frozenset({"set_stops", "set_prefs", "set_card_automation"})  # allowed any time
ACTION_INTENTS = frozenset({"play_land", "cast_spell", "activate_ability", "declare_attackers", "declare_blockers",
                            "repeat_sequence", "turn_face_up"})


def automation_on(state: GameState) -> bool:
    return state.settings.automation != "off" and state.rules is not None


def compile_intent(state: GameState, intent: A.Action, *, actor: str, info: CardInfo, rng: Any) -> list[dict[str, Any]]:
    if not automation_on(state):
        raise ActionError("Rules automation is off at this table. Use the table tools, or ask the host to turn it on.")
    assert state.rules is not None
    if intent.type in PREF_INTENTS:
        # A preference: allowed any time, even while paused, waiting, or mid-animation. It is
        # registered at once; the engine applies it at the next priority.
        plan = Plan(state, actor, info, rng)
        PREFS[intent.type](plan, intent)
        plan.do({"type": "rules_sync", "rules": plan.rules.model_dump(mode="json")})
        return plan.steps
    if state.rules.paused and intent.type != "concede":  # (104.3a: conceding is possible at any time)
        raise ActionError("Automation is paused by the host. Use the table tools meanwhile.")
    if state.pregame is not None and not state.pregame.finished:
        raise ActionError("Finish opening hands first")
    if actor in state.rules.conceded or actor in state.rules.lost:
        raise ActionError("You have left this game")
    if state.rules.paused:  # a concede while the host has automation paused: they leave, nothing else runs
        plan = Plan(state, actor, info, rng)
        concede(plan, intent)
        plan.do({"type": "rules_sync", "rules": plan.rules.model_dump(mode="json")})
        return plan.steps
    plan = Plan(state, actor, info, rng)
    begin(plan)
    sync_step(plan)
    handler = INTENTS.get(intent.type)
    if handler is None:
        what = NOT_YET.get(intent.type, intent.type)
        raise ActionError(f"{what} through the rules engine arrives with the next milestone. "
                          "Use the table tools for now (e.g. drag the card to the stack).")
    if intent.type in ACTION_INTENTS:
        plan.rules.actions += 1  # for "pass until next action"
        plan.rules.last_actor = actor
    handler(plan, intent)
    settle(plan)
    if intent.type != "repeat_sequence":
        remember_intent(plan, intent)
    permissions.refresh_reveals(plan.state, plan.info)  # 401.5: which top library cards the table reveals now
    plan.rules.engine_version = RULES_ENGINE_VERSION
    plan.do({"type": "rules_sync", "rules": plan.rules.model_dump(mode="json")})
    return plan.steps


def begin(plan: Plan) -> None:
    """Before an intent: take in what happened by hand since the engine last acted (a land put
    onto the battlefield by hand still counts as the land for the turn), then start a fresh
    event list (keeping events not yet collected for triggers). Expired remembered answers are dropped."""
    absorb_manual_events(plan)
    layers.control_sync(plan)  # -- control (wave 3K) -- an Aura or effect source moved by hand: control follows (613.1b)
    # (keep what hasn't been looked at for triggers yet: a resolution that stopped for a
    # decision may have left events its triggers still have to see, 603.2)
    # -- this-turn history (wave 4D) -- what was done by hand still happened (608.2i)
    from app.rules import history

    history.note_events(plan, [e for e in plan.rules.events if e.batch > plan.rules.trigger_batch and e.manual])
    plan.rules.events = [e for e in plan.rules.events if e.batch > plan.rules.trigger_batch and not e.manual]
    turn = plan.state.turn.number
    for prefs in plan.rules.prefs.values():
        prefs.yields = [y for y in prefs.yields if y.kind == "always_yield" or y.turn == turn]
    r = plan.rules
    r.loyalty_used = {k: t for k, t in r.loyalty_used.items() if t == turn}
    r.once_per_turn = {k: t for k, t in r.once_per_turn.items() if t == turn}
    permissions.refresh_reveals(plan.state, plan.info)  # (a permanent put onto the table by hand since)


def absorb_manual_events(plan: Plan) -> None:
    r = plan.rules
    turn = plan.state.turn.number
    for e in r.events:
        if not e.manual or e.kind != "zone_change" or e.turn != turn or e.card is None or e.from_zone is None:
            continue
        card = plan.state.cards.get(e.card)
        if card is None or card.zone != e.to_zone:
            continue
        owner, from_zone = e.from_zone.split(":")[0], e.from_zone.rsplit(":", 1)[-1]
        to_zone = (e.to_zone or "").rsplit(":", 1)[-1]
        if from_zone == "hand" and to_zone == "battlefield" and plan.ch(card).is_land and owner == plan.active:
            r.lands_played[owner] = TurnCount(turn=turn, count=r.lands_this_turn(owner, turn) + 1)
        elif from_zone in ("hand", "command") and to_zone == STACK:
            r.spells_cast[card.controller] = TurnCount(turn=turn, count=r.spells_this_turn(card.controller, turn) + 1)
            # -- refused modal/conditional (wave 3R1) -- cast by hand: where from is known, what paid for it isn't
            oid = plan.oid(card)
            if oid not in r.payments:
                r.payments[oid] = PaymentRecord(card=card.id, controller=card.controller, cast_from=from_zone,
                                                mana_known=False, alternative="manual",
                                                cast_main=plan.state.turn.active_player == card.controller
                                                and plan.state.turn.phase in MAIN_PHASES)
            from app.rules import history  # -- this-turn history (wave 4D) --

            history.note_cast(plan, card)
            # -- review (wave 4R) -- "their first noncreature spell each turn" counts a spell cast by hand too (601.2i)
            from app.rules import unless_pays

            unless_pays.mark_cast(plan, card.controller, plan.ch(card).types)


def settle(plan: Plan) -> None:
    """After every intent: state-based actions, triggered abilities, and make sure someone can act."""
    permissions.free_cast_abandoned(plan)  # -- refused look/cast-free (wave 3R5) -- a cancelled mid-resolution cast (608.2g)
    layers.control_sync(plan)  # -- control (wave 3K) -- continuous effects first (613.1b), then state-based actions
    sba.check(plan)
    r = plan.rules
    if r.decision is None and len(plan.live()) > 1 and (r.priority is None or r.priority not in plan.live()):
        advance(plan)
    elif r.decision is None and len(plan.live()) > 1 and triggers.flush(plan) and r.decision is None:
        advance(plan)  # e.g. a land's "enters" trigger: on the stack now, then priority as usual


def sync_step(plan: Plan) -> None:
    """If the step was changed by hand (a sandbox phase / next-turn action), the engine picks up
    from there: the active player gets priority in the step the table is now in."""
    r = plan.rules
    marker = f"{plan.state.turn.number}:{plan.state.turn.phase}"
    if r.step != marker:
        r.step = marker
        r.passed = []
        r.priority = plan.active if plan.active in plan.live() else plan.after(plan.active)
    elif r.priority is None and r.decision is None:
        r.priority = plan.active


# -- repeating a sequence ------------------------------------------------------------------
MAX_REPEAT_STEPS = 50000
RECENT_LIMIT = 30
RANDOM_STEPS = frozenset({"shuffle", "roll", "coin", "mulligan", "reset_deck"})


def remember_intent(plan: Plan, intent: A.Action) -> None:
    r = plan.rules
    turn = plan.state.turn.number
    if r.recent_turn != turn:
        r.recent, r.recent_turn = {}, turn
    mine = r.recent.setdefault(plan.actor, [])
    mine.append(intent.model_dump(mode="json", exclude={"r", "actor", "ts"}))
    del mine[:-RECENT_LIMIT]


class _Stop(Exception):
    pass


def _until_met(plan: Plan, a: A.RepeatSequence) -> bool:
    u = a.until
    if u is None:
        return False
    state = plan.state
    pid = u.player or plan.actor
    player = state.players.get(pid)
    if player is None:
        raise ActionError("Unknown player")
    if u.kind == "mana":
        return sum(player.mana.values()) >= u.value
    if u.kind == "tokens":
        return sum(c.quantity for c in state.cards.values()
                   if c.is_token and c.controller == pid and c.zone.endswith(":battlefield")) >= u.value
    if u.kind == "life_at_most":
        return player.life <= u.value
    if u.kind == "life_at_least":
        return player.life >= u.value
    card = state.cards.get(u.card_id or "")
    if card is None or not u.counter:
        raise ActionError("Choose a permanent and a counter")
    return card.counters.get(u.counter, 0) >= u.value


def repeat_sequence(plan: Plan, a: A.RepeatSequence) -> None:
    """Replay the actor's last ``count`` intents, iteration by iteration, through the engine. An
    iteration that fails, needs a choice, or does anything random is rolled back and ends the
    repeat; the table stays as it was after the last complete iteration. Never guesses that a
    board state "is" an infinite loop: it only repeats what the player actually did."""
    r = plan.rules
    seq = r.recent.get(plan.actor, [])[-a.count:] if r.recent_turn == plan.state.turn.number else []
    if len(seq) < a.count:
        raise ActionError("Do the whole sequence once first (this turn), then repeat it")
    if any(p["type"] in ("choose", "concede", "repeat_sequence") or p["type"] in PREF_INTENTS for p in seq):
        raise ActionError("That sequence involves choices, so it can't be repeated automatically")
    plan.max_steps = MAX_REPEAT_STEPS
    log_start = len(plan.state.log)
    done, reason = 0, ""
    for _ in range(a.times):
        if _until_met(plan, a):
            reason = "the condition was reached"
            break
        snapshot, mark = plan.state.model_copy(deep=True), len(plan.steps)
        try:
            for payload in seq:
                intent = A.parse_action(payload)
                INTENTS[intent.type](plan, intent)
                settle(plan)
                if plan.rules.decision is not None:
                    raise _Stop("it needed a choice")
            if any(step["type"] in RANDOM_STEPS for step in plan.steps[mark:]):
                raise _Stop("it isn't deterministic")
        except (ActionError, _Stop) as exc:
            plan.state, plan.steps = snapshot, plan.steps[:mark]
            reason = str(exc).rstrip(".")
            break
        done += 1
    if done == 0 and not (a.until is not None and reason == "the condition was reached"):
        raise ActionError(f"The sequence can't be repeated: {reason or 'nothing to do'}")
    folded = len(plan.state.log) - log_start
    plan.do({"type": "rules_log", "text": f"{plan.name(plan.actor)} repeated the sequence ×{done}"
             + (f" (stopped: {reason})" if reason else ""), "fold": folded})


# -- priority ----------------------------------------------------------------------------
def stack_signature(plan: Plan) -> str:
    return ",".join(plan.oid(cid) for cid in plan.state.zones.get(STACK, []))


def pass_mark(plan: Plan, until: str) -> str:
    """The situation when a PASS UNTIL … was set; the condition is met once it changes."""
    r = plan.rules
    if until == "next_action":
        return str(r.actions)
    if until == "stack_changes":
        return stack_signature(plan)
    if until in ("next_step", "combat"):
        return r.step or f"{plan.state.turn.number}:{plan.state.turn.phase}"
    return str(plan.state.turn.number)


def pass_until_met(plan: Plan, player: str, prefs: PlayerPrefs) -> bool:
    r = plan.rules
    until, mark = prefs.pass_until, prefs.pass_mark
    state = plan.state
    if until == "next_action":
        return r.actions > int(mark or 0) and r.last_actor not in (None, player)
    if until == "stack_changes":
        return stack_signature(plan) != mark
    if until == "stack_empty":
        return not state.zones.get(STACK)
    if until == "next_step":
        return r.step != mark
    if until == "next_turn":
        return str(state.turn.number) != mark
    if until == "my_turn":
        return plan.active == player and str(state.turn.number) != mark
    if until == "combat":
        return r.step != mark and state.turn.phase in ("begin_combat", "declare_attackers")
    return True


def bluff_stop(state: GameState, player: str) -> bool:
    """A stop that depends only on public information (cards in hand, untapped permanents), so
    stopping never tells the table that you really have a response."""
    if not state.zones.get(zone_key(player, "hand")):
        return False
    return any(not state.cards[cid].tapped for cid in state.zones.get(zone_key(player, "battlefield"), []))


def is_stop(plan: Plan, player: str) -> bool:
    """Does ``player`` get to act at this priority, or does the engine pass for them?

    Forced stops always win; then a PASS UNTIL … passes until its condition is met; then
    RESPONSE decides (OFF: pass whenever possible; AUTO: your stops, and anything you could
    respond with; ON: every priority). Nothing here ever tells other players *why* someone
    passed: auto-passes look exactly like passes.
    """
    r = plan.rules
    stored = r.prefs.get(player)
    prefs = stored or PlayerPrefs()
    if plan.hold == player:
        return True  # they just kept priority (HOLD PRIORITY)
    if plan.state.turn.phase == "untap" and not plan.state.zones.get(STACK):
        return False  # no one gets priority in the untap step (502.4)
    if prefs.force_stop:
        prefs.force_stop = False  # consumed
        return True
    if prefs.stop_after is not None:
        on_stack = {plan.oid(cid) for cid in plan.state.zones.get(STACK, [])}
        if prefs.stop_after not in on_stack:
            prefs.stop_after = None
            return True
    if prefs.pass_until is not None:
        if not pass_until_met(plan, player, prefs):
            return False
        prefs.pass_until, prefs.pass_mark = None, ""
        return True
    if prefs.full_control or not plan.options.auto_priority_pass or prefs.response == "on":
        return True
    phase = plan.state.turn.phase
    mine = player == plan.active
    if plan.state.zones.get(STACK):
        if prefs.response == "off":
            return False
        return casting.has_responses(plan.state, player, plan.info) or (prefs.bluff_stops and bluff_stop(plan.state, player))
    if prefs.response == "off":
        # Only a turn's first main phase, and only if there is something at all to do there.
        return mine and phase == "main1" and casting.can_act(plan.state, player, plan.info)
    return (mine and phase == "main1") or phase in prefs.stops(mine)


def advance(plan: Plan) -> None:
    """Hand priority on until someone has a real decision to make: skip players without a stop
    in this step, resolve the stack when everyone passed, move to the next step when the stack
    is empty and everyone passed."""
    while True:
        r = plan.rules
        if r.decision is not None:
            return
        sba.check(plan)  # before anyone gets priority (rule 117.5)
        if r.decision is not None:
            return
        stack_now = set(plan.state.zones.get(STACK, []))
        r.stack = {k: v for k, v in r.stack.items() if k in stack_now}  # (objects removed by hand)
        if triggers.flush(plan):  # triggered abilities go on the stack now (603.3)
            if r.decision is not None:
                return
            continue
        players = plan.live()
        if len(players) <= 1:
            r.priority = players[0] if players else None  # game over: the table stays a sandbox
            return
        if all(p in r.passed for p in players):
            if plan.state.zones.get(STACK):
                resolve_top_of_stack(plan)
            else:
                next_step(plan)
            continue
        holder = r.priority
        if holder is None or holder not in players or holder in r.passed:
            start = r.passed[-1] if r.passed else plan.active
            holder = start if start not in r.passed and start in players else plan.after(start)
            while holder in r.passed:
                holder = plan.after(holder)
        r.priority = holder
        if is_stop(plan, holder):
            return
        r.passed.append(holder)  # no stop here: pass for them (Arena's auto-pass)


def pass_priority(plan: Plan, a: A.PassPriority) -> None:
    require_no_decision(plan)
    require_priority(plan)
    if a.until is not None:
        if a.until in ("stack_changes", "stack_empty") and not plan.state.zones.get(STACK):
            raise ActionError("The stack is empty")
        prefs = plan.prefs(plan.actor)
        prefs.pass_until, prefs.pass_mark = a.until, pass_mark(plan, a.until)
    if plan.actor not in plan.rules.passed:
        plan.rules.passed.append(plan.actor)
    plan.rules.priority = plan.after(plan.actor)
    advance(plan)


# -- turn structure ----------------------------------------------------------------------
def _mark_step(plan: Plan) -> None:
    r = plan.rules
    r.step = f"{plan.state.turn.number}:{plan.state.turn.phase}"
    r.passed = []
    r.priority = plan.active if plan.active in plan.live() else plan.after(plan.active)


def empty_pools(plan: Plan) -> None:
    """Mana empties from every pool at the end of each step and phase (rule 500.4)."""
    kept = effects.keyword_actions.combat_mana_kept(plan)  # -- wave 3F -- firebending: kept until end of combat
    from app.rules import kept_mana  # -- refused copy/mana (wave 3R3): 106.4 "you don't lose this mana" --

    before = {pid: p.mana.get("R", 0) for pid, p in plan.state.players.items()}
    if plan.rules.kept_mana and kept_mana.empty(plan):
        # (both kinds of kept mana: the firebending {R} on top of what the other effects kept, never more than was there)
        for pid, n in kept.items():
            add = min(n, before.get(pid, 0) - plan.state.players[pid].mana.get("R", 0))
            if add > 0:
                plan.do({"type": "rules_mana", "player": pid, "delta": {"R": add}}, actor=pid)
        return
    if any(p.mana for p in plan.state.players.values()):
        plan.do({"type": "rules_mana", "player": plan.active, "empty_all": True}, actor=plan.active)
        for pid, n in kept.items():
            plan.do({"type": "rules_mana", "player": pid, "delta": {"R": n}}, actor=pid)


def next_step(plan: Plan) -> None:
    empty_pools(plan)
    r = plan.rules
    phase = plan.state.turn.phase
    if phase == "cleanup":
        start_next_turn(plan)
        return
    if phase == "combat_damage" and r.combat_round == "first":
        _mark_step(plan)
        combat_damage(plan, "second", "done")  # the regular damage step after first strike
        return
    if phase == "end_combat":
        combat.end_combat(plan)
    if phase == "declare_attackers" and r.no_attackers:
        # Nobody attacked: skip declare blockers and combat damage (rule 508.8).
        plan.do({"type": "phase", "to": "end_combat", "force": True}, actor=plan.active)
    else:
        plan.do({"type": "phase", "to": "next", "force": True}, actor=plan.active)
    effects.skips.skip_steps(plan)  # -- refused grants/replacements (wave 3R2) -- 614.10: a skipped step or combat phase
    _mark_step(plan)
    on_step_start(plan)


def _keep_tapped(plan: Plan) -> list[str]:
    """Tapped permanents that don't untap during the untap step (502.3): the permanent's own
    "~ doesn't untap during your untap step.", an Aura's "Enchanted creature doesn't untap during
    its controller's untap step.", and a static over a selector ("Islands don't untap during their
    controllers' untap steps.", "Creatures with power 3 or greater don't untap …"), all of which
    app/rules/layers.py puts in ``Characteristics.imposed`` for whatever matches right now."""
    return [c.id for c in plan.state.cards.values() if c.tapped and c.zone.endswith(":battlefield")
            and not plan.manual(c) and "doesnt_untap" in scripts.statics(plan.ch(c))][:250]


def _exerted(plan: Plan, player: str) -> list[str]:
    """-- activation costs (wave 4H) -- 701.43a: tapped permanents ``player`` exerted (still the same objects, 400.7)
    that they control: they don't untap during ``player``'s next untap step."""
    out = []
    for oid, who in plan.rules.exerted.items():
        card = plan.state.cards.get(oid.rsplit(".", 1)[0])
        if who == player and card is not None and plan.oid(card) == oid and card.zone.endswith(":battlefield") \
                and card.tapped and card.controller == player:
            out.append(card.id)
    return out


def start_next_turn(plan: Plan) -> None:
    keep = _keep_tapped(plan)
    keep += [c for c in _exerted(plan, plan.after(plan.active)) if c not in keep]  # (wave 4H: an exerted one isn't stunned, 122.1d)
    # -- keyword actions & face-down (wave 3F) -- 122.1d: a stunned permanent stays tapped and loses a stun counter instead
    stunned = effects.keyword_actions.stunned(plan, [c.id for c in plan.state.cards.values() if c.tapped and c.id not in keep])
    keep = [*keep, *stunned]
    skipped: list[tuple[str, int]] = []  # 800.4k: a departed player's turn doesn't begin
    previous = (plan.active, plan.state.turn.number)
    # -- refused grants/replacements (wave 3R2) -- 614.10: skipped turns (they never begin: nothing ends with
    # them, 500.4) and a skipped untap step (nothing untaps, 502.2's day / night check doesn't happen)
    skip_to = effects.skips.next_active(plan)
    stay = effects.skips.untap_skipped(plan, skip_to or plan.after(plan.active))
    if stay is not None:
        keep = list(dict.fromkeys([*keep, *stay]))[:250]
    keep = list(dict.fromkeys([*keep, *_exerted(plan, skip_to or plan.after(plan.active))]))[:250]  # (wave 4H)
    if skip_to is not None:
        plan.do({"type": "next_turn", "force": True, "keep_tapped": keep, "player": skip_to}, actor=plan.active)
    # -- end refused grants/replacements (wave 3R2) --
    for _ in range(len(plan.state.seat_order) + 1):
        if skip_to is not None:
            break
        plan.do({"type": "next_turn", "force": True, "keep_tapped": keep}, actor=plan.active)
        if plan.active in plan.live():
            break
        skipped.append((plan.active, plan.state.turn.number))
    effects.keyword_actions.lose_stun(plan, [c for c in stunned if c in plan.state.cards and plan.state.cards[c].controller == plan.active],
                                      plan.active)
    delayed.turn_began(plan, skipped)  # 500.4, 800.4m: "until your next turn" effects end
    if stay is None:  # -- activation costs (wave 4H) -- 701.43a: that untap step happened; 614.10a: a skipped one doesn't count
        plan.rules.exerted = {k: p for k, p in plan.rules.exerted.items()
                              if p != plan.active and plan.rules.object_id(k.rsplit(".", 1)[0]) == k}
    if stay is None:  # (wave 3R2: not in a skipped untap step)
        effects.designations.untap_day_night(plan, *previous)  # -- (wave 3E) 502.2: day / night --
    if not plan.state.settings.auto_untap and stay is None:
        plan.do({"type": "untap_all", "player": plan.active, "keep_tapped": keep}, actor=plan.active)
    # The untap step has no priority: straight on to upkeep.
    plan.do({"type": "phase", "to": "next", "force": True}, actor=plan.active)
    effects.skips.skip_steps(plan)  # -- refused grants/replacements (wave 3R2) -- 614.10: a skipped upkeep / draw step
    _mark_step(plan)
    on_step_start(plan)


def on_step_start(plan: Plan) -> None:
    """Turn-based actions at the start of a step."""
    state = plan.state
    phase = state.turn.phase
    ap = plan.active
    if not plan.has_active_player() and phase in ("draw", "declare_attackers", "cleanup"):
        # 800.4j: the turn goes on without its active player — their turn-based actions (the draw,
        # 504.1; declaring attackers, 508.1; discarding to hand size, 514.1) don't happen; the
        # cleanup's 514.2 still does. "At the beginning of" triggers of the step still trigger.
        if phase == "declare_attackers":
            plan.rules.no_attackers = True
        elif phase == "cleanup":
            finish_cleanup(plan)
            return
        else:
            triggers.at_step_generic(plan)
        return
    if phase == "draw":
        first_turn_skip = state.turn.number == 1 and len(plan.live()) == 2
        if first_turn_skip:
            plan.note(f"{plan.name(ap)} skips the first draw (two-player game)")
        else:
            # -- replacement effects stage 2 (wave 2E): the turn-based draw (504.1) through the draw
            # choke point — replaced even from an empty library (121.6a, 614.11), else 704.5b --
            empty = not state.zones.get(zone_key(ap, "library"))
            if not effects.replace.draw_cards(plan, [ap], 1, then={"do": "draw_step"}):
                return  # the drawing player chooses an order first (616.1); the step goes on after
            if empty and ap in plan.rules.drew_from_empty:
                plan.note(f"{plan.name(ap)} can't draw: their library is empty")
    elif phase in ("upkeep", "end"):
        triggers.at_step(plan, "upkeep_you" if phase == "upkeep" else "end_step_you")
        if phase == "end":
            triggers.monarch_end_step(plan)
        else:  # -- counters & designations (wave 3E): 726.2 the initiative's holder ventures into Undercity --
            effects.designations.initiative_upkeep(plan)
    elif phase == "main1":
        # -- sagas & attached-object triggers (wave 3S): 505.4 / 714.3c lore counters (a turn-based action) --
        from app.rules import sagas

        sagas.precombat_main(plan)
        # -- counters & designations (wave 3E): 728.1 rad counters (precombat main phase) --
        effects.designations.rad_trigger(plan)
    elif phase == "end_combat":  # -- (wave 3E) delayed triggers "at end of combat" (511.2, 603.7: the Ring's sacrifice) --
        delayed.at_step(plan, "end_combat")
    elif phase == "declare_attackers":
        combat.start_declare_attackers(plan)
    elif phase == "declare_blockers":
        combat.start_declare_blockers(plan)
    elif phase == "combat_damage":
        if combat.has_first_strike_round(plan):
            combat_damage(plan, "first", "first")
        else:
            combat_damage(plan, "only", "done")
    elif phase == "cleanup":
        cleanup_step(plan)
    if phase in ("upkeep", "draw", "main1", "begin_combat", "main2", "end"):
        triggers.at_step_generic(plan)  # "At the beginning of [whose] [step]" (503, 504, 505, 507, 513)


def combat_damage(plan: Plan, rnd: str, then: str) -> None:
    """Deal a round of combat damage, or with AUTO COMBAT DAMAGE off (ASSISTED), ask first."""
    plan.rules.combat_round = then  # type: ignore[assignment]
    if plan.options.auto_combat_damage or not combat.attackers_on(plan.state) or not plan.has_active_player():
        combat.deal_combat_damage(plan, rnd)  # type: ignore[arg-type]
        return
    preview = combat.damage_preview(plan, rnd)  # type: ignore[arg-type]
    decide(plan, player=plan.active, kind="confirm", prompt=f"Combat damage: {preview}",
           options=[DecisionOption(id="yes", label="Deal damage"), DecisionOption(id="no", label="By hand")],
           resume={"step": "combat_damage", "round": rnd})


def _resume_combat_damage(plan: Plan, d: Decision, chosen: list[str]) -> None:
    assert d.resume is not None
    if chosen[0] == "yes":
        if combat.deal_combat_damage(plan, d.resume["round"]):  # (False: a 615.7 shield choice is open)
            _after_resolution(plan)
        return
    decide(plan, player=d.player, kind="manual_resolution", prompt="Deal combat damage by hand, then press Done",
           options=[DecisionOption(id="done", label="Done")], resume={"step": "manual_done"})


def cleanup_step(plan: Plan) -> None:
    ap = plan.active
    if not plan.options.auto_cleanup:
        decide(plan, player=ap, kind="manual_resolution",
               prompt="Cleanup: discard down to your maximum hand size and remove damage by hand, then press Done",
               options=[DecisionOption(id="done", label="Done")], resume={"step": "cleanup_manual"})
        return
    hand = plan.state.zones.get(zone_key(ap, "hand"), [])
    excess = len(hand) - MAX_HAND_SIZE
    from app.rules import hand_size  # -- hand size (wave 4J) -- "You have no maximum hand size." (402.2)

    if excess > 0 and hand_size.no_maximum(plan, ap):
        excess = 0
    if excess > 0:
        decide(
            plan, player=ap, kind="choose_cards",
            prompt=f"Discard {excess} card{'s' if excess != 1 else ''} down to your maximum hand size ({MAX_HAND_SIZE})",
            options=[DecisionOption(id=cid, label=plan.state.cards[cid].name or "Card", card_id=cid) for cid in hand],
            min_choices=excess, max_choices=excess, resume={"step": "cleanup_discard"},
        )
        return
    finish_cleanup(plan)


def finish_cleanup(plan: Plan) -> None:
    turn_cleanup(plan)
    # Cleanup normally grants no priority: the turn ends (triggers during cleanup arrive in M16).
    start_next_turn(plan)


def turn_cleanup(plan: Plan) -> None:
    """514.2: damage is removed and "until end of turn" effects end, simultaneously."""
    if any(c.damage for c in plan.state.cards.values()):
        plan.do({"type": "cleanup", "what": ["damage"]}, actor=plan.active)
    if plan.rules.effects:
        layers.end_of_turn(plan)
    plan.rules.regen_shields = {}  # regeneration shields last "this turn"
    plan.rules.prevention = {}  # and so do prevention shields
    permissions.expire(plan)  # "you may play that card this turn" and friends
    delayed.cleanup(plan)  # "when … this turn" delayed triggers stop watching (514.2)
    for card in list(plan.state.cards.values()):
        for marker in [m for m in card.effects if m.text == "until end of turn"]:
            plan.do({"type": "remove_effect", "card_ids": [card.id], "effect_id": marker.id}, actor=plan.active)


# -- the stack ---------------------------------------------------------------------------
def needs_manual_resolution(ch: Characteristics) -> bool:
    """Does resolving this object do something the engine can't do by itself?"""
    if ch.is_ability:
        return True  # ability objects: scripted abilities arrive in M16
    if "Aura" in ch.subtypes and attachments.enchant_selector(ch) is None:
        return True  # an enchant wording the engine doesn't map: attach it by hand
    if ch.is_instant_or_sorcery:
        return any(not coverage.ability_supported(ch, a.index) for a in ch.abilities if a.kind != "keywords")
    # A permanent spell just enters; only "as/when it enters" text needs someone to act.
    return any(
        "enters" in a.text and a.kind in ("triggered", "static") and not coverage.ability_supported(ch, a.index)
        for a in ch.abilities
    )


def leave_stack(plan: Plan, card_id: str, controller: str, *, tapped: bool = False, countered: bool = False) -> None:
    """A resolved spell leaves the stack: to the battlefield or its owner's graveyard, or into exile
    if it was cast with flashback (702.34a), or back to its owner's hand with buyback (702.27a)."""
    # -- X sized by a count (wave 4K) -- it shuffled itself into its library (608.2n)
    from app.rules import x_spells

    oid = plan.oid(card_id)
    if not countered and x_spells.left_stack_itself(plan, card_id):
        return
    if oid in plan.rules.rebound_cast:  # 702.88a rebound: exiled as it resolves, cast again next upkeep
        plan.rules.rebound_cast = [o for o in plan.rules.rebound_cast if o != oid]
        if not countered:
            card = plan.state.cards[card_id]
            plan.do({"type": "move", "card_ids": [card_id], "to": {"player": card.owner, "zone": "exile"}}, actor=controller)
            plan.rules.rebounding.append(card_id)
            return
    if oid in plan.rules.buyback:
        plan.rules.buyback = [o for o in plan.rules.buyback if o != oid]
        if not countered and oid not in plan.rules.flashback:
            card = plan.state.cards[card_id]
            plan.do({"type": "move", "card_ids": [card_id], "to": {"player": card.owner, "zone": "hand"}}, actor=controller)
            return
    if oid in plan.rules.flashback:
        plan.rules.flashback = [o for o in plan.rules.flashback if o != oid]
        card = plan.state.cards[card_id]
        plan.do({"type": "move", "card_ids": [card_id], "to": {"player": card.owner, "zone": "exile"}}, actor=controller)
        return
    if oid in plan.rules.exile_if_graveyard:  # -- refused look/cast-free (wave 3R5) -- "If that spell would be put
        plan.rules.exile_if_graveyard = [o for o in plan.rules.exile_if_graveyard if o != oid]  # into your graveyard, exile it instead"
        card = plan.state.cards[card_id]
        if plan.ch(card).is_instant_or_sorcery:  # (a permanent spell enters instead: not replaced, 614.1a)
            plan.do({"type": "move", "card_ids": [card_id], "to": {"player": card.owner, "zone": "exile"}}, actor=controller)
            return
    stack = plan.state.zones.get(STACK, [])
    if card_id in stack:
        step: dict[str, Any] = {"type": "resolve_top", "force": True, "tapped": tapped}
        if stack[-1] != card_id:  # -- refused look/cast-free (wave 3R5) -- 608.2g: spells cast while it resolved are
            step["card_id"] = card_id  # above it now; it leaves the stack all the same (608.2n)
        plan.do(step, actor=controller)
        record = plan.rules.payments.pop(oid, None)
        if record is not None and card_id in plan.state.cards and plan.state.cards[card_id].zone.endswith(":battlefield"):
            plan.rules.payments[plan.oid(card_id)] = record  # the permanent remembers how its spell was paid
        if card_id in plan.state.cards and plan.state.cards[card_id].zone.endswith(":battlefield"):
            from app.rules import history  # -- this-turn history (wave 4D) --

            history.note_became(plan, oid, plan.oid(card_id))
        copying.resolved(plan, card_id, oid)  # -- copy system (wave 2F): a permanent spell's copy became a token (608.3f)
    else:  # (defensive: resolution never adds to the stack today)
        plan.do({"type": "move", "card_ids": [card_id], "to": {"zone": "graveyard"}}, actor=controller)


def resolve_top_of_stack(plan: Plan) -> None:
    top_id = plan.state.zones[STACK][-1]
    top = plan.state.cards[top_id]
    entry = plan.rules.stack.get(top_id)
    if entry is not None:
        effects.begin_resolution(plan, top_id, entry)  # an automated spell or ability
        return
    ch = plan.ch(top)
    controller = top.controller if top.controller in plan.live() else plan.active
    if ch.is_permanent_card and not plan.manual(top) and not needs_manual_resolution(ch) \
            and replacements.stack_entry_choice(plan, top, controller):
        return  # "As ~ enters, choose a color": chosen before it enters (614.12a); resolved again with the answer
    ch = plan.ch(top)  # -- copy system (wave 2F): as it will enter — entering as a copy, the copied text (707.5, 614.12)
    aura_target = plan.rules.aura_targets.pop(top_id, None)
    # An instant, sorcery or ability the engine didn't put on the stack (moved there by hand) has
    # no recorded targets or choices: its controller resolves it by hand. So has an Aura without one.
    manual = ch.is_instant_or_sorcery or ch.is_ability or needs_manual_resolution(ch) or plan.manual(top) \
        or ("Aura" in ch.subtypes and aura_target is None)
    if aura_target is not None and not manual:
        selector = attachments.enchant_selector(ch)
        if selector is None or not still_legal(plan, selector, controller, aura_target, ch):
            # 608.2b / 303.4g: its target is illegal: it doesn't resolve and goes to the graveyard
            plan.note(f"{ch.name or 'The Aura'} does nothing: its target is no longer legal")
            plan.do({"type": "move", "card_ids": [top_id], "to": {"player": top.owner, "zone": "graveyard"}}, actor=controller)
            _after_resolution(plan)
            return
    # A permanent spell becomes a permanent as it resolves (608.3a): its own "enters" replacement
    # effects — tapped, a shock land's life, counters, loyalty — apply as it enters (614.1c-d,
    # app/rules/replacements.py; the tapped status is part of the move itself). No permanent
    # spell asks a question as it enters today (the pay-life wording is printed on lands only).
    entering = ch.is_permanent_card and not manual
    answers = plan.rules.entry_choices.pop(top_id, None)
    ep: dict[str, Any] = replacements.entry_plan(plan, top, controller, answers=answers) if entering else {"tapped": False}
    x = top.stack_info.x if top.stack_info else None
    if ep.get("life"):
        plan.do({"type": "life", "player": controller, "delta": -int(ep["life"])}, actor=controller)
    leave_stack(plan, top_id, controller, tapped=bool(ep["tapped"]))
    if aura_target is not None and not manual and plan.state.cards[top_id].zone.endswith(":battlefield"):
        attachments.attach(plan, top_id, aura_target.id, controller)  # 303.4f: it enters attached to its target
    if entering:
        replacements.after_entry(plan, top_id, controller, x=x, choices=ep.get("choices"))
    if top_id in plan.rules.evoked:  # 702.74a: "When this permanent enters, if its evoke cost was paid, its controller sacrifices it."
        plan.rules.evoked = [c for c in plan.rules.evoked if c != top_id]
        entered_now = plan.state.cards.get(top_id)
        if entered_now is not None and entered_now.zone.endswith(":battlefield"):
            from app.rules import trigger_multipliers  # -- trigger multipliers (wave 5D) -- an enters trigger (603.2d)

            triggers._add(plan, controller=controller, source_card=top_id, source_object=plan.oid(top_id),
                          name=entered_now.name, index=7100,
                          definition={"kind": "triggered", "trigger": "evoke", "optional": False, "target": None,
                                      "effects": [{"do": "sacrifice", "who": "self", "by": "controller"}]},
                          cause=trigger_multipliers.entering(plan, top_id))
    if top_id in plan.rules.dashed:  # 702.109a: haste, and back to its owner's hand at the next end step
        plan.rules.dashed = [c for c in plan.rules.dashed if c != top_id]
        entered_now = plan.state.cards.get(top_id)
        if entered_now is not None and entered_now.zone.endswith(":battlefield"):
            oid = plan.oid(top_id)
            layers.add_effect(plan, affected=[oid], layer="6", source=None, controller=controller,
                              add_keywords=("haste",), duration="permanent", label="Haste (dash)")
            delayed.create_move(plan, controller, top_id, oid, "hand", entered_now.name)  # (a delayed trigger, 603.7)
    if top_id in plan.rules.suspend_haste:  # 702.62e: a suspended creature has haste
        plan.rules.suspend_haste = [c for c in plan.rules.suspend_haste if c != top_id]
        entered_now = plan.state.cards.get(top_id)
        if entered_now is not None and entered_now.zone.endswith(":battlefield"):
            layers.add_effect(plan, affected=[plan.oid(top_id)], layer="6", source=None, controller=controller,
                              add_keywords=("haste",), duration="permanent", label="Haste (suspend)")
    if manual and ch.is_permanent_card:
        replacements.after_entry(plan, top_id, controller, x=x)  # (306.5b loyalty still applies to a manual planeswalker)
    if manual:
        resolved = plan.state.cards.get(top_id)
        if ch.is_ability:
            text = ch.oracle_text if len(ch.oracle_text) <= 160 else ch.oracle_text[:157] + "…"
            prompt = f"Resolve {ch.name + '’s ability' if ch.name and ch.name != 'Ability' else 'the ability'} by hand: “{text}”. Then press Done"
        else:
            prompt = f"Resolve {ch.name or 'it'} by hand with the table tools, then press Done"
        decide(
            plan, player=controller, kind="manual_resolution",
            prompt=prompt,
            options=[DecisionOption(id="done", label="Done")], resume={"step": "manual_done"},
            source=resolved,
        )
        return
    _after_resolution(plan)


def _after_resolution(plan: Plan) -> None:
    r = plan.rules
    r.passed = []
    r.priority = plan.active if plan.active in plan.live() else plan.after(plan.active)


# -- intents -----------------------------------------------------------------------------
def land_play_grant(state: GameState, player: str, card: CardInstance, ch: Characteristics,
                    info: CardInfo | None) -> permissions.Grant | None:
    """How ``player`` may play this land from where it is: from their hand (305.1), or a
    permission ("you may play lands from your graveyard", "you may play that card this turn")."""
    if card.zone == zone_key(player, "hand"):
        return permissions.Grant("hand")
    found = [g for g in permissions.grants(state, player, card, ch, info, verb="play") if g.zone_ok] if info else []
    return found[0] if found else None


def land_play_problem(state: GameState, player: str, card: CardInstance, ch: Characteristics, *,
                      check_priority: bool = True, info: CardInfo | None = None) -> str | None:
    """Why ``player`` can't play ``card`` as a land right now (None if they can)."""
    r = state.rules
    if r is None:
        return "Rules automation is off"
    if not ch.is_land:
        return f"{ch.name or 'That card'} isn't a land"
    if land_play_grant(state, player, card, ch, info) is None:
        return "You can only play lands from your hand"
    if state.turn.active_player != player:
        return "You can only play a land during your own turn"
    if state.turn.phase not in MAIN_PHASES:
        return "Lands are played in a main phase"
    if state.zones.get(STACK):
        return "You can only play a land while the stack is empty"
    if check_priority and (r.priority != player or r.decision is not None):
        return "You don't have priority"
    from app.rules import land_plays  # -- additional land plays (wave 4J) -- 305.2a

    played = r.lands_this_turn(player, state.turn.number)
    if played >= 1 and played >= (allowed := land_plays.allowed(state, player, info)):  # (counted only when it matters)
        return "You've already played a land this turn" if allowed == 1 else "You've already played all the lands you can this turn"
    return None


def play_land(plan: Plan, a: A.PlayLand) -> None:
    require_no_decision(plan)
    card = plan.state.cards.get(a.card_id)
    if card is None:
        raise ActionError("That card isn't here any more")
    probe = card.model_copy(update={"face": a.face}) if a.face is not None else card
    problem = land_play_problem(plan.state, plan.actor, card, plan.ch(probe), info=plan.info)
    if problem:
        raise ActionError(problem)
    grant = land_play_grant(plan.state, plan.actor, card, plan.ch(probe), plan.info)
    # The land's own "enters" replacement effects (614.1c-d, app/rules/replacements.py): "enters
    # tapped [unless …]", a shock land's pay-life-or-tapped choice (made before it enters: 614.12a),
    # "enters [tapped] with … counters" as it enters (122.6).
    ep = replacements.entry_plan(plan, probe, plan.actor, pay_life=a.pay_life, answers=plan.rules.entry_choices.get(card.id))
    if ep.get("choice") is not None and "what" in ep["choice"]:  # "As ~ enters, choose …": before it enters
        prompt, options = replacements.choice_prompt(plan, card, plan.actor, ep["choice"])
        decide(plan, player=plan.actor, kind="choose_one", prompt=prompt, options=options, source=card,
               resume={"step": "land_enter_choice", "card": card.id, "what": ep["choice"]["what"],
                       "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})})
        return
    if ep.get("choice") is not None:
        n = ep["choice"]["life"]
        decide(plan, player=plan.actor, kind="choose_one", prompt=f"{plan.ch(probe).name}: pay {n} life, or it enters tapped?",
               options=[DecisionOption(id="pay", label=f"Pay {n} life (untapped)"), DecisionOption(id="tapped", label="Enters tapped")],
               resume={"step": "shock", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})}, source=card)
        return
    if a.face is not None and a.face != card.face:
        plan.do({"type": "set_face", "card_id": card.id, "face": a.face})
    if ep.get("life"):
        plan.do({"type": "life", "player": plan.actor, "delta": -int(ep["life"])})
    payload: dict[str, Any] = {"type": "move", "card_ids": [card.id], "to": {"zone": "battlefield"}, "tapped": bool(ep["tapped"])}
    if a.x is not None and a.y is not None:
        payload.update(x=a.x, y=a.y)
    from_where = card.zone.rsplit(":", 1)[-1]
    plan.do(payload)
    plan.rules.entry_choices.pop(card.id, None)
    if grant is not None and grant.how == "permission":
        permissions.consume(plan, grant)  # ("once during each of your turns")
        plan.note(f"{plan.name(plan.actor)} plays {card.name} from their {from_where} ({grant.label})", [card.id])
    replacements.after_entry(plan, card.id, plan.actor, choices=ep.get("choices"))
    r = plan.rules
    turn = plan.state.turn.number
    r.lands_played[plan.actor] = TurnCount(turn=turn, count=r.lands_this_turn(plan.actor, turn) + 1)
    r.passed = []  # an action was taken: everyone must pass again
    r.priority = plan.actor  # playing a land doesn't use the stack; you keep priority


def _resume_shock(plan: Plan, d: Decision, chosen: list[str]) -> None:
    intent = A.parse_action((d.resume or {})["intent"])
    intent.pay_life = chosen[0] == "pay"  # type: ignore[union-attr]
    plan.rules.priority = d.player
    play_land(plan, intent)  # type: ignore[arg-type]


def choose(plan: Plan, a: A.Choose) -> None:
    d = plan.rules.decision
    if d is None or d.id != a.decision_id:
        raise ActionError("That decision is no longer pending")
    if d.kind in ("declare_attackers", "declare_blockers"):
        raise ActionError(f"Answer this with {d.kind}")
    if d.player != plan.actor:
        raise ActionError(f"It's {plan.name(d.player)}'s decision")
    chosen = list(a.option_ids)
    valid = {o.id for o in d.options}
    if d.kind == "divide":  # 601.2d: an amount per option (target), at least 1 each, adding up to the total
        total = int((d.resume or {}).get("total", 0))
        if chosen or len(a.amounts) != len(d.options) or any(n < 1 for n in a.amounts) or sum(a.amounts) != total:
            raise ActionError(f"Divide {total} among the {len(d.options)} targets: at least 1 each, {total} in all")
        chosen = [str(n) for n in a.amounts]
    elif a.amounts:
        raise ActionError("Amounts only answer a division")
    elif len(set(chosen)) != len(chosen) or not set(chosen) <= valid:
        raise ActionError("Choose from the options offered")
    if d.kind == "reconcile":
        groups = {o.id: o.group for o in d.options}
        answered = [groups[c] for c in chosen]
        if len(set(answered)) != len(answered) or set(answered) != set(groups.values()):
            raise ActionError("Answer each question once")
    if not d.min_choices <= len(chosen) <= d.max_choices:
        n = d.min_choices if d.min_choices == d.max_choices else f"{d.min_choices}–{d.max_choices}"
        raise ActionError(f"Choose {n}")
    if a.remember is not None:
        if d.memory_key is None:
            raise ActionError("This answer can't be remembered")
        prefs = plan.prefs(plan.actor)
        prefs.yields = [y for y in prefs.yields if y.key != d.memory_key][-49:]
        prefs.yields.append(Yield(kind=a.remember, key=d.memory_key, context=d.memory_context,
                                  turn=plan.state.turn.number))
    plan.rules.decision = None
    step = (d.resume or {}).get("step")
    RESUME[str(step)](plan, d, chosen)
    if step != "reconcile":  # after reconciling, play picks up where the table is (like without questions)
        advance(plan)


def _resume_manual_done(plan: Plan, d: Decision, _: list[str]) -> None:
    plan.note(f"{plan.name(d.player)} finished resolving by hand")
    _after_resolution(plan)


def _resume_cleanup_discard(plan: Plan, d: Decision, chosen: list[str]) -> None:
    plan.do({"type": "move", "card_ids": chosen, "to": {"zone": "graveyard"}}, actor=d.player)
    finish_cleanup(plan)


def concede(plan: Plan, _: A.Action) -> None:
    """104.3a: a player can concede at any time — with or without priority, during anyone's
    decision, mid-combat — and leaves the game at once (800.4a, app/rules/leave.py). A decision
    left pending is settled so the others go on: their own is dropped (800.4f-h: a player who left
    makes no choices; the resolution it was part of goes on without it), and one that was part of
    a spell or ability that left the game with them ends with it. Their turn goes on without an
    active player (800.4j)."""
    r = plan.rules
    if r.winner is not None:
        raise ActionError(f"The game is over: {plan.name(r.winner)} won")
    _require_seated(plan)
    r.conceded.append(plan.actor)
    plan.note(f"{plan.name(plan.actor)} conceded")
    pending = r.decision
    leave_game(plan, plan.actor)
    left = plan.live()
    if len(left) == 1:
        plan.note(f"{plan.name(left[0])} is the last player standing")
        r.decision = None
        r.winner = left[0]
        r.priority = left[0]
        return
    if r.paused:  # (automation paused by the host: the table goes on by hand; nothing is resolved now)
        if r.priority is None or r.priority not in left:
            r.priority = plan.after(plan.actor)
        return
    if pending is not None:
        _settle_decision(plan, pending, plan.actor)
    if r.decision is None and (r.priority is None or r.priority not in left):
        # 800.4a: priority passes to the next player in turn order who's still in the game
        r.priority = plan.after(plan.actor)
    advance(plan)


def _settle_decision(plan: Plan, d: Decision, leaver: str) -> None:
    """The decision pending as ``leaver`` left the game: keep it, re-ask it as things now are, or
    end it (and with it the resolution it belonged to) — never leave the others stuck."""
    r = plan.rules
    resume = d.resume or {}
    found = resume.get("ctx")
    ctx: dict[str, Any] = found if isinstance(found, dict) else {}
    resolving = "stack_id" in ctx and "effects" in ctx
    if resolving and ctx["stack_id"] not in plan.state.zones.get(STACK, []):
        # the spell or ability being resolved left the game with its controller (800.4a): the rest
        # of it doesn't happen
        r.decision = None
        plan.rules.stack.pop(ctx["stack_id"], None)
        _after_resolution(plan)
        return
    if d.player != leaver:
        if d.kind == "declare_attackers" and r.decision is not None:
            r.decision = None
            combat.start_declare_attackers(plan)  # (the attack targets changed)
        elif d.kind == "declare_blockers" and r.decision is not None:
            r.decision = None
            combat.ask_next_blocker(plan)  # (the attackers changed: maybe none attack them now)
            if r.decision is None:
                combat.blocks_declared(plan)
        return
    r.decision = None  # (leave_game dropped it already)
    if resolving:
        # 800.4f-g: the choice isn't made; the resolution goes on — with the other players still to
        # choose in APNAP order ("each opponent discards a card"), then its next instruction
        plan.note(f"{plan.name(leaver)} left the game: their choice isn't made")
        if "rest" in resume and "picked" in resume and str(resume.get("step")) in RESUME:
            RESUME[str(resume["step"])](plan, d, [])
        else:
            effects.continue_effects(plan, ctx)
        return
    step = resume.get("step")
    if d.kind == "declare_blockers":
        combat.ask_next_blocker(plan)  # (leave_game took them off the defenders still to declare)
        if r.decision is None:
            combat.blocks_declared(plan)
        return
    if d.kind == "declare_attackers":
        r.no_attackers = True  # (they declared none: 800.4j, the turn goes on)
    if step in ("cleanup_discard", "cleanup_manual"):
        finish_cleanup(plan)  # 514.2 still happens; then the next player's turn
        return
    _after_resolution(plan)


def set_stops(plan: Plan, a: A.SetStops) -> None:
    """The M14 stops intent, kept for old saves' histories and simple clients."""
    _require_seated(plan)
    prefs = plan.prefs(plan.actor)
    prefs.stops_my_turn, prefs.stops_their_turn = list(a.own), list(a.others)
    prefs.hold_priority = a.hold_priority
    prefs.response = "auto" if a.smart_pass else "on"


def _require_seated(plan: Plan) -> None:
    if plan.actor not in plan.state.players:
        raise ActionError("Only seated players have automation preferences")


SIMPLE_PREFS = ("response", "stops_my_turn", "stops_their_turn", "bluff_stops", "payment", "auto_resolve_own_triggers",
                "auto_order_identical_triggers", "hold_priority", "full_control", "force_stop")


def set_prefs(plan: Plan, a: A.SetPrefs) -> None:
    _require_seated(plan)
    prefs = plan.prefs(plan.actor)
    for key in SIMPLE_PREFS:
        value = getattr(a, key)
        if value is not None:
            setattr(prefs, key, list(value) if isinstance(value, list) else value)
    if a.cancel_pass:
        prefs.pass_until, prefs.pass_mark, prefs.stop_after = None, "", None
    if a.stop_after is not None:
        card = plan.state.cards.get(a.stop_after)
        if card is None or card.zone != STACK:
            raise ActionError("That isn't on the stack")
        prefs.stop_after = plan.oid(card)
    if a.mana_source is not None:
        card = plan.state.cards.get(a.mana_source)
        if card is None or plan.actor not in (card.controller, card.owner):
            raise ActionError("Only your own mana sources")
        protection = a.mana_source_protection
        if protection is None or protection == "normal":
            prefs.mana_sources.pop(card.id, None)
        else:
            prefs.mana_sources[card.id] = protection
    if a.add_yield is not None:
        prefs.yields = [y for y in prefs.yields if y.key != a.add_yield.key][-49:]
        prefs.yields.append(Yield(kind=a.add_yield.kind, key=a.add_yield.key, turn=plan.state.turn.number))
    if a.cancel_yield is not None:
        prefs.yields = [y for y in prefs.yields if y.key != a.cancel_yield]
    if a.cancel_all_yields:
        prefs.yields = []


def set_card_automation(plan: Plan, a: A.SetCardAutomation) -> None:
    card = plan.state.cards.get(a.card_id)
    if card is None:
        raise ActionError("That card isn't here any more")
    if plan.actor not in (card.controller, card.owner):
        raise ActionError("Only its controller can change a card's automation")
    if a.mode == "auto":
        plan.rules.card_modes.pop(card.id, None)
    else:
        plan.rules.card_modes[card.id] = a.mode
    plan.note(f"{plan.name(plan.actor)} set automation to {a.mode.upper()} for", [card.id])


def remembered(plan: Plan, player: str, key: str, context: str) -> str | None:
    """A remembered answer for this prompt: "yes", "no" or "yield" (None: ask). Answers given in a
    different context don't apply."""
    for y in plan.rules.prefs_for(player).yields:
        if y.key != key or (y.context and y.context != context):
            continue
        if y.kind == "always_yield":
            return "yield"
        if y.turn == plan.state.turn.number:
            return "yes" if y.kind == "yes_this_turn" else "no"
    return None


PREFS: dict[str, Callable[[Plan, Any], None]] = {
    "set_stops": set_stops,
    "set_prefs": set_prefs,
    "set_card_automation": set_card_automation,
}
INTENTS: dict[str, Callable[[Plan, Any], None]] = {
    "pass_priority": pass_priority,
    "play_land": play_land,
    "cast_spell": casting.cast_spell,
    "turn_face_up": casting.turn_face_up,
    "activate_ability": casting.activate_ability,
    "declare_attackers": combat.declare_attackers,
    "declare_blockers": combat.declare_blockers,
    "choose": choose,
    "concede": concede,
    "repeat_sequence": repeat_sequence,
}
RESUME: dict[str, Callable[[Plan, Decision, list[str]], None]] = {
    "manual_done": _resume_manual_done,
    "combat_damage": _resume_combat_damage,
    "cleanup_manual": lambda plan, d, chosen: start_next_turn(plan),
    "sba_confirm": sba.resume_confirm,
    "reconcile": reconcile.resume_reconcile,
    "payment": casting.resume_payment,
    "pay_mana": casting.resume_pay_mana,
    "look": effects.resume_look,
    "order_library": effects.resume_order_library,
    "may": effects.resume_may,
    "proliferate": effects.resume_proliferate,
    "search": effects.resume_search,
    "search_split": effects.resume_search_split,
    "discard": effects.resume_discard,
    # optional payments as an effect (PAY / DECLINE, the objects for a part of the cost); the same
    # step name also continues the older pay-or-sacrifice / counter-unless prompts
    "pay_or_sacrifice": optional_payment.resume,
    "return_yours": effects.resume_return_yours,
    "explore": effects.resume_explore,
    "aura_enters": attachments.resume_aura_enters,
    "battle_protector": battles.resume_protector,  # 310.11
    "siege_cast": battles.resume_siege_cast,  # 310.12b
    "sacrifice_choice": effects.resume_sacrifice_choice,
    "tap_choice": effects._this_way.resume_tap_choice,  # -- "this way" outcomes (wave 4A) --
    "pick_looked": effects.resume_pick_looked,
    "library_place": effects.resume_library_place,
    "shuffle_library": effects.resume_shuffle_library,
    "cast_modes": casting.resume_cast_modes,
    "cast_slot_target": casting.resume_cast_slot_target,
    "cast_group": casting.resume_cast_group,
    "cast_divide": casting.resume_cast_divide,
    "trigger_group": triggers.resume_group,
    "trigger_divide": triggers.resume_divide,
    # -- modal triggered abilities (wave 1A): the modes, then each chosen mode's target (603.3c) --
    "trigger_modes": modal_abilities.resume_trigger_modes,
    "trigger_slot_target": modal_abilities.resume_trigger_slot,
    "fabricate": effects.resume_fabricate,
    "storm": effects.resume_storm,
    "add_mana": effects.resume_add_mana,  # (mana effects, wave 3M)
    "shock": lambda plan, d, chosen: _resume_shock(plan, d, chosen),
    "suspend_cast": effects.resume_suspend_cast,
    "free_cast_pick": permissions.resume_free_cast,  # (wave 3C)
    # -- refused look/cast-free (wave 3R5) -- piles (700.3)
    "piles_opponent": looking.resume_opponent,
    "piles_split": looking.resume_split,
    "piles_pick": looking.resume_pick,
    "order_triggers": triggers.resume_order,
    "trigger_target": triggers.resume_target,
    "trigger_confirm": triggers.resume_confirm,
    "cast_target": casting.resume_target,
    "payment_sources": casting.resume_payment_sources,
    "cleanup_discard": _resume_cleanup_discard,
    "mana_ability": casting.resume_mana_ability,
    "crew": casting.resume_crew,
    "ability_cost": cost_payment.resume_choice,
    "legend_rule": sba.resume_legend_rule,
    "commander_zone": sba.resume_commander_zone,
    **effects.keyword_actions.RESUME,  # amass / bolster choices, tokens entering attacking (app/rules/keyword_actions.py)
    **effects.RESUME,  # player choices: edicts, "chooses a", a revealed hand, "choose a color" (app/rules/effects.py)
    # replacement / prevention effects (app/rules/replacements.py): a shock land put onto the
    # battlefield by an effect, 903.9b before a commander is returned to a hand, 615.7 shields
    "enter_choice": replacements.resume_entry_choice,
    "stack_enter_choice": replacements.resume_stack_enter_choice,
    "land_enter_choice": replacements.resume_land_enter_choice,
    "commander_instead": replacements.resume_commander_instead,
    "commander_first": replacements.resume_commander_first,  # 903.9b asked before the move
    "shield_order": replacements.resume_shield_order,
    # -- replacement effects stage 2 (wave 2E): which of several replacement / prevention effects
    # applies first (616.1), then the paused site runs again (app/rules/replace.py) --
    "replace_order": effects.replace.resume_order,
    # -- copy system (wave 2F): copies of spells and abilities — same or new targets for several
    # copies, one copy's targets (707.10c), a copy made by hand (app/rules/copying.py) --
    **copying.RESUME,
}
# (the draw step, once its draw is done after a 616.1 choice: its "at the beginning of" triggers)
effects.replace.THEN["draw_step"] = lambda plan, then: triggers.at_step_generic(plan)
