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
from app.game.rules_state import Decision, DecisionOption, Stops, TurnCount
from app.game.state import STACK, CardInstance, GameState, zone_key
from app.rules import casting, combat, coverage, sba
from app.rules.characteristics import CardInfo, Characteristics
from app.rules.plan import Plan, decide, require_no_decision, require_priority

MAIN_PHASES = ("main1", "main2")
MAX_HAND_SIZE = 7

NOT_YET: dict[str, str] = {}


# -- entry point -------------------------------------------------------------------------
def compile_intent(state: GameState, intent: A.Action, *, actor: str, info: CardInfo, rng: Any) -> list[dict[str, Any]]:
    if state.settings.automation != "rules" or state.rules is None:
        raise ActionError("Rules automation is off at this table. Use the table tools, or ask the host to turn it on.")
    if intent.type == "set_stops":
        plan = Plan(state, actor, info, rng)
        set_stops(plan, intent)  # a preference: allowed any time, even while paused or waiting
        plan.do({"type": "rules_sync", "rules": plan.rules.model_dump(mode="json")})
        return plan.steps
    if state.rules.paused:
        raise ActionError("Automation is paused by the host. Use the table tools meanwhile.")
    if state.pregame is not None and not state.pregame.finished:
        raise ActionError("Finish opening hands first")
    if actor in state.rules.conceded:
        raise ActionError("You have conceded this game")
    plan = Plan(state, actor, info, rng)
    sync_step(plan)
    handler = INTENTS.get(intent.type)
    if handler is None:
        what = NOT_YET.get(intent.type, intent.type)
        raise ActionError(f"{what} through the rules engine arrives with the next milestone. "
                          "Use the table tools for now (e.g. drag the card to the stack).")
    handler(plan, intent)
    settle(plan)
    plan.do({"type": "rules_sync", "rules": plan.rules.model_dump(mode="json")})
    return plan.steps


def settle(plan: Plan) -> None:
    """After every intent: state-based actions, and make sure someone can act."""
    sba.check(plan)
    r = plan.rules
    if r.decision is None and len(plan.live()) > 1 and (r.priority is None or r.priority not in plan.live()):
        advance(plan)


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


# -- priority ----------------------------------------------------------------------------
def is_stop(plan: Plan, player: str) -> bool:
    phase = plan.state.turn.phase
    stops: Stops = plan.rules.stops_for(player)
    if plan.state.zones.get(STACK):
        # Something to respond to. With smart passing (the default) the engine passes for players
        # who have nothing they could respond with, like Arena does.
        return not stops.smart_pass or casting.has_responses(plan.state, player, plan.info)
    if player == plan.active:
        return phase == "main1" or phase in stops.own
    return phase in stops.others


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
        players = plan.live()
        if len(players) <= 1:
            r.priority = players[0] if players else None  # game over: the table stays a sandbox
            return
        if plan.active not in players:
            start_next_turn(plan)  # the active player has left the game: on to the next turn
            continue
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


def pass_priority(plan: Plan, _: A.Action) -> None:
    require_no_decision(plan)
    require_priority(plan)
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
    if any(p.mana for p in plan.state.players.values()):
        plan.do({"type": "rules_mana", "player": plan.active, "empty_all": True}, actor=plan.active)


def next_step(plan: Plan) -> None:
    empty_pools(plan)
    r = plan.rules
    phase = plan.state.turn.phase
    if phase == "cleanup":
        start_next_turn(plan)
        return
    if phase == "combat_damage" and r.combat_round == "first":
        combat.deal_combat_damage(plan, "second")  # the regular damage step after first strike
        r.combat_round = "done"
        _mark_step(plan)
        return
    if phase == "end_combat":
        combat.end_combat(plan)
    if phase == "declare_attackers" and r.no_attackers:
        # Nobody attacked: skip declare blockers and combat damage (rule 508.8).
        plan.do({"type": "phase", "to": "end_combat", "force": True}, actor=plan.active)
    else:
        plan.do({"type": "phase", "to": "next", "force": True}, actor=plan.active)
    _mark_step(plan)
    on_step_start(plan)


def start_next_turn(plan: Plan) -> None:
    for _ in range(len(plan.state.seat_order) + 1):
        plan.do({"type": "next_turn", "force": True}, actor=plan.active)
        if plan.active in plan.live():
            break
    if not plan.state.settings.auto_untap:
        plan.do({"type": "untap_all", "player": plan.active}, actor=plan.active)
    # The untap step has no priority: straight on to upkeep.
    plan.do({"type": "phase", "to": "next", "force": True}, actor=plan.active)
    _mark_step(plan)
    on_step_start(plan)


def on_step_start(plan: Plan) -> None:
    """Turn-based actions at the start of a step."""
    state = plan.state
    phase = state.turn.phase
    ap = plan.active
    if phase == "draw":
        first_turn_skip = state.turn.number == 1 and len(plan.live()) == 2
        if first_turn_skip:
            plan.note(f"{plan.name(ap)} skips the first draw (two-player game)")
        elif not state.zones.get(zone_key(ap, "library")):
            if ap not in plan.rules.drew_from_empty:
                plan.rules.drew_from_empty.append(ap)
            plan.note(f"{plan.name(ap)} can't draw: their library is empty")
        else:
            plan.do({"type": "draw", "player": ap, "count": 1}, actor=ap)
    elif phase == "declare_attackers":
        combat.start_declare_attackers(plan)
    elif phase == "declare_blockers":
        combat.start_declare_blockers(plan)
    elif phase == "combat_damage":
        if combat.has_first_strike_round(plan):
            combat.deal_combat_damage(plan, "first")
            plan.rules.combat_round = "first"
        else:
            combat.deal_combat_damage(plan, "only")
            plan.rules.combat_round = "done"
    elif phase == "cleanup":
        cleanup_step(plan)


def cleanup_step(plan: Plan) -> None:
    ap = plan.active
    hand = plan.state.zones.get(zone_key(ap, "hand"), [])
    excess = len(hand) - MAX_HAND_SIZE
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
    if any(c.damage for c in plan.state.cards.values()):
        plan.do({"type": "cleanup", "what": ["damage"]}, actor=plan.active)
    # Cleanup normally grants no priority: the turn ends (triggers during cleanup arrive in M16).
    start_next_turn(plan)


# -- the stack ---------------------------------------------------------------------------
def needs_manual_resolution(ch: Characteristics) -> bool:
    """Does resolving this object do something the engine can't do by itself?"""
    if ch.is_ability:
        return True  # ability objects: scripted abilities arrive in M16
    if "Aura" in ch.subtypes:
        return True  # attaching an Aura as it resolves is done by hand until M16
    if ch.is_instant_or_sorcery:
        return any(not coverage.ability_supported(ch, a.index) for a in ch.abilities if a.kind != "keywords")
    # A permanent spell just enters; only "as/when it enters" text needs someone to act.
    return any(
        "enters" in a.text and a.kind in ("triggered", "static") and not coverage.ability_supported(ch, a.index)
        for a in ch.abilities
    )


def resolve_top_of_stack(plan: Plan) -> None:
    top_id = plan.state.zones[STACK][-1]
    top = plan.state.cards[top_id]
    ch = plan.ch(top)
    controller = top.controller if top.controller in plan.live() else plan.active
    manual = needs_manual_resolution(ch)
    plan.do({"type": "resolve_top", "force": True}, actor=controller)
    entered = plan.state.cards.get(top_id)
    if entered is not None and entered.zone.endswith(":battlefield") and "Planeswalker" in ch.types:
        loyalty = int(ch.loyalty) if ch.loyalty and ch.loyalty.isdigit() else 0
        if loyalty:
            plan.do({"type": "counter", "card_ids": [top_id], "kind": "loyalty", "delta": loyalty}, actor=controller)
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
def land_play_problem(state: GameState, player: str, card: CardInstance, ch: Characteristics) -> str | None:
    """Why ``player`` can't play ``card`` as a land right now (None if they can)."""
    r = state.rules
    if r is None:
        return "Rules automation is off"
    if card.zone != zone_key(player, "hand"):
        return "You can only play lands from your hand"
    if not ch.is_land:
        return f"{ch.name or 'That card'} isn't a land"
    if state.turn.active_player != player:
        return "You can only play a land during your own turn"
    if state.turn.phase not in MAIN_PHASES:
        return "Lands are played in a main phase"
    if state.zones.get(STACK):
        return "You can only play a land while the stack is empty"
    if r.priority != player or r.decision is not None:
        return "You don't have priority"
    if r.lands_this_turn(player, state.turn.number) >= 1:
        return "You've already played a land this turn"
    return None


def play_land(plan: Plan, a: A.PlayLand) -> None:
    require_no_decision(plan)
    card = plan.state.cards.get(a.card_id)
    if card is None:
        raise ActionError("That card isn't here any more")
    probe = card.model_copy(update={"face": a.face}) if a.face is not None else card
    problem = land_play_problem(plan.state, plan.actor, card, plan.ch(probe))
    if problem:
        raise ActionError(problem)
    if a.face is not None and a.face != card.face:
        plan.do({"type": "set_face", "card_id": card.id, "face": a.face})
    payload: dict[str, Any] = {"type": "move", "card_ids": [card.id], "to": {"zone": "battlefield"}}
    if a.x is not None and a.y is not None:
        payload.update(x=a.x, y=a.y)
    plan.do(payload)
    r = plan.rules
    turn = plan.state.turn.number
    r.lands_played[plan.actor] = TurnCount(turn=turn, count=r.lands_this_turn(plan.actor, turn) + 1)
    r.passed = []  # an action was taken: everyone must pass again
    r.priority = plan.actor  # playing a land doesn't use the stack; you keep priority


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
    if len(set(chosen)) != len(chosen) or not set(chosen) <= valid:
        raise ActionError("Choose from the options offered")
    if not d.min_choices <= len(chosen) <= d.max_choices:
        n = d.min_choices if d.min_choices == d.max_choices else f"{d.min_choices}–{d.max_choices}"
        raise ActionError(f"Choose {n}")
    plan.rules.decision = None
    step = (d.resume or {}).get("step")
    RESUME[str(step)](plan, d, chosen)
    advance(plan)


def _resume_manual_done(plan: Plan, d: Decision, _: list[str]) -> None:
    plan.note(f"{plan.name(d.player)} finished resolving by hand")
    _after_resolution(plan)


def _resume_cleanup_discard(plan: Plan, d: Decision, chosen: list[str]) -> None:
    plan.do({"type": "move", "card_ids": chosen, "to": {"zone": "graveyard"}}, actor=d.player)
    finish_cleanup(plan)


def concede(plan: Plan, _: A.Action) -> None:
    r = plan.rules
    r.conceded.append(plan.actor)
    plan.note(f"{plan.name(plan.actor)} conceded")
    if plan.actor in r.passed:
        r.passed.remove(plan.actor)
    if r.decision is not None and r.decision.player == plan.actor:
        r.decision = None
        _after_resolution(plan)
    left = plan.live()
    if len(left) == 1:
        plan.note(f"{plan.name(left[0])} is the last player standing")
        r.winner = left[0]
        r.priority = left[0]
        return
    if r.priority == plan.actor or r.priority is None:
        r.priority = plan.after(plan.actor)
    if plan.active == plan.actor and r.decision is None:
        start_next_turn(plan)  # the conceding player's turn ends
        return
    advance(plan)


def set_stops(plan: Plan, a: A.SetStops) -> None:
    if plan.actor not in plan.state.players:
        raise ActionError("Only seated players have stops")
    plan.rules.stops[plan.actor] = Stops(own=list(a.own), others=list(a.others), hold_priority=a.hold_priority,
                                         smart_pass=a.smart_pass)


INTENTS: dict[str, Callable[[Plan, Any], None]] = {
    "pass_priority": pass_priority,
    "play_land": play_land,
    "cast_spell": casting.cast_spell,
    "activate_ability": casting.activate_ability,
    "declare_attackers": combat.declare_attackers,
    "declare_blockers": combat.declare_blockers,
    "choose": choose,
    "concede": concede,
}
RESUME: dict[str, Callable[[Plan, Decision, list[str]], None]] = {
    "manual_done": _resume_manual_done,
    "cleanup_discard": _resume_cleanup_discard,
    "mana_ability": casting.resume_mana_ability,
    "legend_rule": sba.resume_legend_rule,
    "commander_zone": sba.resume_commander_zone,
}
