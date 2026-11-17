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

import hashlib
import re
import secrets
from collections.abc import Callable
from typing import Any

from app.game import actions as A
from app.game.control import acting_as, controller_of, decider_of
from app.game.errors import ActionError
from app.game.rules_state import (
    Decision,
    DecisionOption,
    PaymentRecord,
    Permission,
    PlayerPrefs,
    TurnCount,
    Yield,
    cancelable,
)
from app.game.state import STACK, CardInstance, GameState, zone_key
from app.rules import (
    assist,  # -- casting extras (wave 18E) --
    attachments,
    battles,
    bestow,
    casting,
    combat,
    combat_rules,  # -- combat (wave 5C) --
    copying,
    cost_moves,
    cost_payment,
    counter_destinations,
    coverage,
    deferred_payment82,
    delayed,
    effects,
    enlist,  # -- casting extras (wave 18E) --
    exert,  # -- static wordings (wave 6E) --
    extra_turns,  # -- extra turns (wave 8A) --
    gift,  # -- gift (wave 23D) --
    graveyard_order,  # -- graveyard order (wave 40C) --
    hideaway,  # -- hideaway (wave 29D) --
    kinship,  # -- kinship (wave 9C) --
    layers,
    library_placements,
    licids,  # -- licids (wave 50A) --
    looking,
    merged,  # -- merged permanents (wave 18D) --
    miracle,  # -- casting extras (wave 18E) --
    modal_abilities,
    next_untap,  # -- next untap step (wave 6A) --
    nonmana_combat_costs,
    opening_hand,  # -- opening hand (wave 18C) --
    optional_payment,
    permissions,
    phasing,  # -- phasing (wave 13D) --
    piles_legacy,
    planar_die,  # -- planechase -- 901.9
    player_control,  # -- controlling another player (wave 18H) --
    reconcile,
    recursion,  # -- static_other sweep (wave 17C) --
    regeneration_choices,
    replacements,
    rooms,  # -- Rooms (wave 18G) --
    sba,
    scripts,
    spell_grants,  # -- spell grants (wave 28C) --
    tap_gesture,  # -- playtest fixes (nov 5) --
    triggers,
    untap_choice,  # -- untap choice (wave 7F) --
    wave110a_teferi,  # -- wave 110A --
    wave110e_opp,  # -- cast-time choice (wave 110E) --
    wave110f_camo,  # -- Camouflage (wave 110F) --
    wave110f_cards,  # -- combat damage division (wave 110F) --
    wave110f_cmd,  # -- pregame commander color (wave 110F) --
    wave110g_spires,  # -- wave 110G --
    wave110h_cards,  # -- untap hold (wave 110H) --
    wave111r3_enter,  # -- enters attacking (wave 111R3) --
    wave111r3_replicate,  # -- granted replicate (wave 111R3) --
)
from app.rules import morph_costs78 as _morph_costs78  # noqa: F401

# Saved payment decisions must resume in a fresh process before another special action runs.
from app.rules import special_payment_tails as _special_payment_tails  # noqa: F401
from app.rules.characteristics import CardInfo, Characteristics
from app.rules.leave import leave_game
from app.rules.plan import Plan, decide, require_no_decision, require_priority, scratch_copy
from app.rules.targets import as_spell, still_legal

MAIN_PHASES = ("main1", "main2")

NOT_YET: dict[str, str] = {}


# -- entry point -------------------------------------------------------------------------
RULES_ENGINE_VERSION = 2  # bump when the rules engine's behaviour changes (saved with scenarios/diagnostics)
PREF_INTENTS = frozenset({"set_stops", "set_prefs", "set_card_automation"})  # allowed any time
ACTION_INTENTS = frozenset({"play_land", "cast_spell", "activate_ability", "declare_attackers", "declare_blockers",
                            "repeat_sequence", "turn_face_up", "unlock_door", "end_effect", "pay_deferred",
                            "roll_planar_die"})


def automation_on(state: GameState) -> bool:
    return state.settings.automation != "off" and state.rules is not None


def compile_intent(state: GameState, intent: A.Action, *, actor: str, info: CardInfo, rng: Any) -> list[dict[str, Any]]:
    """-- engine token stacks -- A step that would treat a token stack as one token (``token_stacks.StackGate``) stops the action: it
    runs again with every stack spread into separate tokens, or, when a stack is too big to spread, is refused (docs/TOKEN_STACKS.md)."""
    from app.rules import token_stacks

    try:
        return _compile_intent(state, intent, actor=actor, info=info, rng=rng, force_spread=False)
    except token_stacks.StackGate as gate:
        big = [state.cards[cid] for cid in token_stacks.stacks(state) if state.cards[cid].quantity > token_stacks.INDIVIDUAL_LIMIT]
        if big:
            raise ActionError(token_stacks.refusal(big, [gate.message])) from None
    try:
        return _compile_intent(state, intent, actor=actor, info=info, rng=rng, force_spread=True)
    except token_stacks.StackGate as gate:
        raise ActionError(f"The rules engine can't do this exactly: {gate.message} Pause automation and do it by hand.") from None


def _compile_intent(state: GameState, intent: A.Action, *, actor: str, info: CardInfo, rng: Any, force_spread: bool) -> list[dict[str, Any]]:
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
    if state.rules.draw_reason is not None:
        raise ActionError("The game is over: draw")
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
    if intent.type != "concede":  # -- controlling another player (wave 18H) -- 723.5: the controller acts for the player (723.6: a
        try:  # player always concedes for themselves)
            actor = acting_as(state, actor)
        except ValueError as exc:
            raise ActionError(str(exc)) from None
    plan = Plan(state, actor, info, rng)
    from app.rules import text_global_word71

    if intent.type != 'concede' and text_global_word71.recover(plan, intent):
        plan.do({'type': 'rules_sync', 'rules': plan.rules.model_dump(mode='json')})
        return plan.steps
    # Restore unknown layer-3 source choices before any derived control sync.
    restoring_word71 = plan.rules.decision is not None and (plan.rules.decision.resume or {}).get('step') == 'restore_global_word71'
    if not restoring_word71:
        plan.force_spread = force_spread  # (-- engine token stacks -- read by begin)
        begin(plan)
        sync_step(plan)
        from app.rules import token_stacks

        token_stacks.single_out_intent(plan, intent)  # -- engine token stacks -- a card the intent names as one object is one member
    handler = INTENTS.get(intent.type)
    if handler is None:
        what = NOT_YET.get(intent.type, intent.type)
        raise ActionError(f"{what} through the rules engine arrives with the next milestone. "
                          "Use the table tools for now (e.g. drag the card to the stack).")
    if intent.type in ACTION_INTENTS or intent.type == "pass_priority":
        miracle.clear(plan)  # -- casting extras (wave 18E) -- 702.94a: the moment to reveal a just-drawn card has passed
    if intent.type in ACTION_INTENTS:
        plan.rules.actions += 1  # for "pass until next action"
        plan.rules.last_actor = actor
    said = intent_label(plan, intent)  # (before it happens: a choice's options are gone once it's answered)
    handler(plan, intent)
    if plan.rules.decision is not None and (plan.rules.decision.resume or {}).get('step') == 'restore_global_word71':
        # Another unknown layer-3 source is still awaiting manual restoration.
        # Do not derive controls, run SBAs, or refresh reveals against guessed text.
        remember_intent(plan, intent)
        plan.do({'type': 'rules_sync', 'rules': plan.rules.model_dump(mode='json')})
        return plan.steps
    settle(plan)
    if intent.type != "repeat_sequence":
        remember_intent(plan, intent, said)
    from app.rules import linked_exile_look

    linked_exile_look.refresh(plan)
    permissions.refresh_reveals(plan.state, plan.info)  # 401.5: which top library cards the table reveals now
    hideaway.refresh(plan.state)  # -- hideaway (wave 29D) -- 406.3, 702.75a: who may look at the cards the permanents hid
    plan.rules.engine_version = RULES_ENGINE_VERSION
    plan.do({"type": "rules_sync", "rules": plan.rules.model_dump(mode="json")})
    return plan.steps


def compile_opening(state: GameState, actor: str, info: CardInfo, rng: Any) -> list[dict[str, Any]]:
    """-- opening hand (wave 18C) -- 103.6: the steps that ask the first player about their opening-hand actions (the mulligan
    action that ended the pregame carries them; ``state`` is the table as it leaves that action)."""
    plan = Plan(state, actor, info, rng)
    opening_hand.start(plan)
    plan.do({"type": "rules_sync", "rules": plan.rules.model_dump(mode="json")})
    return plan.steps


def compile_first_turn(state: GameState, info: CardInfo, rng: Any) -> list[dict[str, Any]] | None:
    """-- first turn (S7) -- 502.4: no player gets priority in the untap step. A new game with no pregame (no mulligans) begins in its
    first untap step; the engine goes on at once to the first step that gives priority, as after the mulligans (opening_hand.finish:
    priority none, then settle). None when there is nothing to do (rules off, opening hands still to settle, not at an untap step)."""
    r = state.rules
    if not automation_on(state) or r is None or state.pregame is not None or r.decision is not None or r.draw_reason is not None:
        return None
    if state.turn.phase != "untap" or state.zones.get(STACK) or r.paused:
        return None
    plan = Plan(state, state.turn.active_player, info, rng)
    plan.rules.priority, plan.rules.passed = None, []
    settle(plan)
    permissions.refresh_reveals(plan.state, plan.info)
    plan.rules.engine_version = RULES_ENGINE_VERSION
    plan.do({"type": "rules_sync", "rules": plan.rules.model_dump(mode="json")})
    return plan.steps


def begin(plan: Plan) -> None:
    """Before an intent: take in what happened by hand since the engine last acted (a land put
    onto the battlefield by hand still counts as the land for the turn), then start a fresh
    event list (keeping events not yet collected for triggers). Expired remembered answers are dropped."""
    from app.rules import hand_size

    hand_size.bound_legacy(plan)
    from app.rules import life_game_history

    life_game_history.begin(plan)
    from app.rules import previous_own_turns
    previous_own_turns.begin(plan)
    absorb_manual_events(plan)
    from app.rules import planar_chaos

    # -- planechase chaos (wave B) -- a planeswalk made since (a table action): "until a player planeswalks" ends (611.2a)
    planar_chaos.on_events(plan, [e for e in plan.rules.events if e.batch > plan.rules.trigger_batch])
    from app.rules import (
        planar_more,  # -- planechase more (wave E1) -- Unyaro: a planeswalk by hand ends its phasing too
    )

    planar_more.on_walks(plan, [e for e in plan.rules.events if e.batch > plan.rules.trigger_batch])
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
    r.loyalty_second = {k: t for k, t in r.loyalty_second.items() if t == turn}
    r.once_per_turn = {k: t for k, t in r.once_per_turn.items() if t == turn}
    from app.rules import linked_exile_look

    linked_exile_look.refresh(plan)
    permissions.refresh_reveals(plan.state, plan.info)  # (a permanent put onto the table by hand since)
    hideaway.refresh(plan.state)  # (-- hideaway (wave 29D) -- a permanent whose control was taken by hand since)
    # -- token stacks (gap 2; engine token stacks) -- the engine reads tokens one object each (109.1, 111.6), except a big stack the audit
    # accepts (docs/TOKEN_STACKS.md)
    from app.rules import token_stacks

    token_stacks.gate(plan, force_spread=getattr(plan, "force_spread", False))


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
                r.payments[oid] = PaymentRecord(card=card.id, controller=card.controller, cast_from=from_zone, cast_from_player=owner,
                                                mana_known=False, alternative="manual",
                                                cast_main=plan.state.turn.active_player == card.controller
                                                and plan.state.turn.phase in MAIN_PHASES)
            from app.rules import history  # -- this-turn history (wave 4D) --

            history.note_cast(plan, card)
            from app.rules import prohibitions

            prohibitions.bind_next_uncounterable(plan, card, card.controller)  # -- most-played cards (wave 43B) -- also a spell cast by hand
            # -- review (wave 4R) -- "their first noncreature spell each turn" counts a spell cast by hand too (601.2i)
            from app.rules import unless_pays

            unless_pays.mark_cast(plan, card.controller, plan.ch(card).types)


def settle(plan: Plan) -> None:
    """After every intent: state-based actions, triggered abilities, and make sure someone can act."""
    if plan.rules.draw_reason is not None:
        return
    permissions.free_cast_abandoned(plan)  # -- refused look/cast-free (wave 3R5) -- a cancelled mid-resolution cast (608.2g)
    if r0 := plan.rules.attach_asks110e:  # -- becomes attached, choose (wave 110E) --
        from app.rules import wave110e_blade

        if plan.rules.decision is None:
            wave110e_blade.ask(plan, r0)
    layers.control_sync(plan)  # -- control (wave 3K) -- continuous effects first (613.1b), then state-based actions
    combat.sync_attacking(plan)
    checked = sba.check(plan)
    r = plan.rules
    if r.decision is None and len(plan.live()) > 1 and (r.priority is None or r.priority not in plan.live()):
        advance(plan, checked=checked)
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


def remember_intent(plan: Plan, intent: A.Action, label: str | None = None) -> None:
    r = plan.rules
    turn = plan.state.turn.number
    if r.recent_turn != turn:
        r.recent, r.recent_labels, r.recent_turn = {}, {}, turn
    mine = r.recent.setdefault(plan.actor, [])
    mine.append(intent.model_dump(mode="json", exclude={"r", "actor", "ts"}))
    del mine[:-RECENT_LIMIT]
    said = r.recent_labels.setdefault(plan.actor, [])
    said.append(label or intent.type.replace("_", " ").capitalize())
    del said[:-RECENT_LIMIT]
    if len(said) != len(mine):  # (an older save kept payloads without words)
        r.recent_labels[plan.actor] = [p["type"].replace("_", " ").capitalize() for p in mine[:len(mine) - len(said)]] + said


def intent_label(plan: Plan, intent: A.Action) -> str:
    """An intent in words for its own player's Repeat panel: "Cast Dramatic Reversal", "Activate Isochron Scepter",
    "Choose: Yes". Only ever shown to the player who did it (their own cards and their own choices)."""
    def name(cid: str | None) -> str:
        card = plan.state.cards.get(cid or "")
        return card.name if card is not None and card.name else "a card"

    kind = intent.type
    if kind == "cast_spell":
        return f"Cast {name(getattr(intent, 'card_id', None))}"
    if kind == "play_land":
        return f"Play {name(getattr(intent, 'card_id', None))}"
    if kind == "activate_ability":
        return f"Activate {name(getattr(intent, 'card_id', None))}"
    if kind == "pass_priority":
        return "Pass priority"
    if kind == "choose":
        d = plan.rules.decision
        picked = set(getattr(intent, "option_ids", []) or [])
        labels = [o.label for o in d.options if o.id in picked] if d is not None and d.id == getattr(intent, "decision_id", None) else []
        return "Choose: " + (", ".join(labels)[:60] or "done")
    return kind.replace("_", " ").capitalize()


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
        return sum(player.mana.values()) + len(player.mana_units) >= u.value  # (remembered mana is in the pool too)
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
    if seq and seq[0]["type"] == "choose":
        raise ActionError("Start the sequence with an action, not with a choice")
    if any(p["type"] in ("concede", "repeat_sequence") or p["type"] in PREF_INTENTS for p in seq):
        raise ActionError("That sequence can't be repeated automatically")
    plan.max_steps = MAX_REPEAT_STEPS
    log_start = len(plan.state.log)
    done, reason = 0, ""
    for _ in range(a.times):
        if _until_met(plan, a):
            reason = "the condition was reached"
            break
        snapshot, mark = scratch_copy(plan.state), len(plan.steps)
        try:
            for i, payload in enumerate(seq):
                if payload["type"] == "choose":  # the same answer to the same question, as the player gave it the first time
                    d = plan.rules.decision
                    if d is None:
                        raise _Stop("a choice from the first time didn't come up")
                    wanted = set(payload.get("option_ids") or [])
                    if d.player != plan.actor or not wanted <= {o.id for o in d.options}:
                        raise _Stop("it needed a different choice")
                    payload = {**payload, "decision_id": d.id}
                elif plan.rules.decision is not None:
                    raise _Stop("it needed a choice")
                intent = A.parse_action(payload)
                plan.chain = None  # (-- runaway chains -- each repeated intent counts its own resolutions, as it would played by hand)
                INTENTS[intent.type](plan, intent)
                settle(plan)
                if plan.rules.decision is not None and (i + 1 == len(seq) or seq[i + 1]["type"] != "choose"):
                    raise _Stop("it needed a choice")
            if any(step["type"] in RANDOM_STEPS for step in plan.steps[mark:]):
                raise _Stop("it isn't deterministic")
        except (ActionError, _Stop) as exc:
            plan.state, plan.steps = snapshot, plan.steps[:mark]
            from app.rules import read_pass

            read_pass.own(plan.state, plan)  # (the table is the snapshot now: its readers use this plan's passes)
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
    """The stack as it is, as a fixed-size digest of its objects in order (PlayerPrefs.pass_mark holds 400 characters, and a stack of
    landfall triggers is far longer than that written out; soak: Omnath and Scapeshift)."""
    objects = ",".join(plan.oid(cid) for cid in plan.state.zones.get(STACK, []))
    return hashlib.sha256(objects.encode()).hexdigest()[:32]


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
    stored = r.prefs.get(controller_of(plan.state, player))  # (-- controlling another player (wave 18H) -- 723.5: their controller's stops)
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
        if not pass_until_met(plan, player, prefs) and not new_response(plan, player, prefs):
            return False
        until = prefs.pass_until
        prefs.pass_until, prefs.pass_mark, prefs.pass_hand = None, "", []
        if until != "stack_changes" or plan.state.zones.get(STACK):
            return True
        # RESOLVE (the top object) emptied the stack: the usual stops decide, as after any pass (a lone spell resolves and play
        # goes on with one press). With something still on the stack the player gets priority back (117.3b): one object a press.
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


def new_response(plan: Plan, player: str, prefs: PlayerPrefs) -> bool:
    """-- runaway chains -- while a PASS UNTIL … passes for ``player``: did a card arrive in their hand since (drawn while a chain of
    triggers resolved) that they could cast right now at instant speed? Then the passing stops and they get priority (117.3b): they
    chose to pass over what they had, not over what they hadn't seen yet. Only the player's own hand is read (nothing is revealed:
    the stop looks like any other)."""
    hand = plan.state.zones.get(zone_key(player, "hand"), [])
    if not hand:
        return False
    before = set(prefs.pass_hand)
    fresh = [cid for cid in hand if cid not in before]
    if not fresh:
        return False
    state, info = plan.state, plan.info
    for cid in fresh:
        card = state.cards.get(cid)
        if card is None:
            continue
        ch = plan.ch(card)
        if ch.is_land:
            continue
        instant = "Instant" in ch.types or ch.has_flash or casting._flash_granted(state, player, card, ch, info) \
            or casting.flash_if(ch) is not None
        if instant and (casting.castable(state, player, card, info, check_priority=False)
                        or casting.free_castable(state, player, card, info, check_priority=False)
                        or casting.alt_castable(state, player, card, info, check_priority=False)):
            return True
    return False


def advance(plan: Plan, *, checked: bool = False) -> None:
    """Hand priority on until someone has a real decision to make: skip players without a stop
    in this step, resolve the stack when everyone passed, move to the next step when the stack
    is empty and everyone passed. ``checked``: the state-based actions were just checked and nothing has happened since."""
    while True:
        from app.rules import mana_named_land_profiles

        mana_named_land_profiles.refresh_reveals(plan)
        r = plan.rules
        if r.decision is not None or r.draw_reason is not None or (plan.state.pregame is not None and not plan.state.pregame.finished):  # (wave 110A: a restarted game's mulligans first)
            return
        # -- repeat speed -- after a check that left nothing to do, an automatic pass changes nothing it reads
        clean = checked or sba.check(plan)  # before anyone gets priority (rule 117.5)
        clean_at, checked = len(plan.steps), False
        if r.decision is not None:
            return
        stack_now = set(plan.state.zones.get(STACK, []))
        r.stack = {k: v for k, v in r.stack.items() if k in stack_now}  # (objects removed by hand)
        if triggers.flush(plan):  # triggered abilities go on the stack now (603.3)
            if r.decision is not None:
                return
            continue
        players = plan.live()
        # game over (one player left of several, or nobody): the table stays a sandbox. A table seated for one from the start is
        # solo testing (goldfishing a deck), not a won game: its turns go on.
        if not players or (len(players) == 1 and len(plan.state.seat_order) > 1):
            r.priority = players[0] if players else None
            return
        if all(p in r.passed for p in players):
            if plan.state.zones.get(STACK) and loop_pause(plan, players):
                return
            if plan.state.zones.get(STACK):
                _count_resolution(plan)
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
        if r.auto_pass is not None:  # -- core review -- the Arena-style pass after their own cast / activation (casting.py)
            auto, r.auto_pass = r.auto_pass, None
            if auto == holder:
                r.passed.append(holder)
                checked = clean and clean_at == len(plan.steps)
                continue
        if is_stop(plan, holder):
            return
        r.passed.append(holder)  # no stop here: pass for them (Arena's auto-pass)
        checked = clean and clean_at == len(plan.steps)



# -- loops -- 104.4b / 732.4: a loop of mandatory actions is a draw, but only when no player can stop it, which the
# engine can't know (an instant in a hand). So it never calls the draw: once one action has run this long, the
# automatic passing stops between two resolutions and every player gets their choices back; each pass after that
# carries on, and the pod can agree to a draw (End game → Propose).
LOOP_PAUSE_SHARE = 0.6  # of plan.max_steps: past this, no further automatic resolution in this action
# -- runaway chains -- a chain of mandatory triggers that keeps refilling the stack (Shabraz, the Skyshark and Marina Vendrell's Grimoire:
# each draw gains life, each life gain draws) resolved dozens of objects in one action, passing for a player who had nothing to cast
# yet, and showed nothing in between. At most this many objects resolve on automatic passes in one action once the stack has been
# refilled (more resolved than were on it when the first one resolved: a tall stack of landfall triggers that only empties isn't a loop).
LOOP_RESOLUTIONS = 20


class _Chain:
    """The objects resolved in this action (``Plan.chain``): how many, how tall the stack was before the first, and the cards each
    player had drawn this turn by then (a public count)."""

    __slots__ = ("base", "drew", "last", "n", "refills")

    def __init__(self, base: int, drew: dict[str, int]) -> None:
        self.base, self.drew, self.n = base, drew, 0
        # -- playtest B4 -- the stack's height at the last resolution, and how many resolutions found it no lower than the one before
        # (something was put on it in between): a loop refills it nearly every time, a big batch (a wipe's 150 death triggers, 200
        # end-step sacrifices) only drains it
        self.last, self.refills = base, 0


def _count_resolution(plan: Plan) -> None:
    chain = getattr(plan, "chain", None)
    if chain is None:
        from app.rules import history

        chain = plan.chain = _Chain(len(plan.state.zones.get(STACK, [])), dict(history.log_for(plan).drew))
    else:
        height = len(plan.state.zones.get(STACK, []))
        if height >= chain.last:
            chain.refills += 1
        chain.last = height
    chain.n += 1


def _repeating(chain: _Chain | None) -> bool:
    """Does this action's chain keep refilling the stack (most resolutions put something new on it), as a loop does?"""
    return chain is not None and chain.n > chain.base and chain.refills * 2 >= chain.n


def runaway(plan: Plan) -> int:
    """How many objects this action resolved, once that is a runaway chain (else 0)."""
    chain = getattr(plan, "chain", None)
    if chain is None or chain.n < LOOP_RESOLUTIONS or not _repeating(chain):
        return 0
    return chain.n


def loop_pause(plan: Plan, players: list[str]) -> bool:
    looping = runaway(plan)
    if not looping and (not plan.max_steps or len(plan.steps) < plan.max_steps * LOOP_PAUSE_SHARE):
        return False
    r = plan.rules
    r.passed, r.auto_pass = [], None
    r.priority = plan.active if plan.active in players else plan.after(plan.active)
    for pid in players:
        prefs = plan.rules.prefs.get(pid)
        if prefs is not None:
            prefs.pass_until, prefs.pass_mark, prefs.pass_hand = None, "", []
    if looping:
        from app.rules import history

        chain, drew = plan.chain, history.log_for(plan).drew
        told = ", ".join(f"{plan.state.players[pid].name} drew {n}" for pid in plan.state.seat_order
                         if (n := drew.get(pid, 0) - chain.drew.get(pid, 0)) > 0)
        plan.chain = None  # (a pass after this one starts a new count)
        plan.note(f"This keeps repeating: {looping} objects resolved in a row{f' ({told})' if told else ''}. Automatic passing stopped so "
                  "you can respond. Resolve to go on one object at a time, or Resolve all for another round; if it can never end, "
                  "the game is a draw (104.4b): propose one from End game.")
        return True
    if _repeating(getattr(plan, "chain", None)):  # (the stack keeps being refilled while it resolves: it may be repeating)
        plan.note("This keeps repeating, so automatic passing stopped. Pass to keep going; if nobody can stop it, "
                  "the game is a draw (104.4b): propose one from End game.")
        return True
    # -- playtest B4 -- a big finite batch (200 "sacrifice it at the beginning of the next end step" triggers) only drains the stack: it
    # used up this action's step budget without repeating anything, so it is no loop and says nothing about a draw
    left = len(plan.state.zones.get(STACK, [])) + len(r.pending_triggers)
    plan.note(f"Many objects to resolve: {left:,} left on the stack. Automatic passing stopped here so you can respond; "
              "Resolve all carries on with the rest." if left else "Automatic passing stopped here so you can respond; pass to carry on.")
    return True


def pass_priority(plan: Plan, a: A.PassPriority) -> None:
    require_no_decision(plan)
    require_priority(plan)
    if a.until is not None:
        if a.until in ("stack_changes", "stack_empty") and not plan.state.zones.get(STACK):
            raise ActionError("The stack is empty")
        prefs = plan.prefs(plan.actor)
        prefs.pass_until, prefs.pass_mark = a.until, pass_mark(plan, a.until)
        prefs.pass_hand = list(plan.state.zones.get(zone_key(plan.actor, "hand"), []))  # (-- runaway chains -- new_response)
    if plan.actor not in plan.rules.passed:
        plan.rules.passed.append(plan.actor)
    plan.rules.priority = plan.after(plan.actor)
    advance(plan)


# -- turn structure ----------------------------------------------------------------------
def _mark_step(plan: Plan) -> None:
    r = plan.rules
    for pending in r.delayed:
        if pending.created_step is None:
            pending.created_step = r.step_serial
    r.step_serial += 1
    if r.step_count_turn != plan.state.turn.number:
        r.step_counts = {}
        r.step_count_turn = plan.state.turn.number
    phase = plan.state.turn.phase
    r.step_counts[phase] = r.step_counts.get(phase, 0) + 1
    r.step = f"{plan.state.turn.number}:{phase}"
    r.passed = []
    r.priority = plan.active if plan.active in plan.live() else plan.after(plan.active)


def empty_pools(plan: Plan) -> None:
    """Mana empties from every pool at the end of each step and phase (rule 500.4)."""
    from app.rules import wave110j_cards  # -- Yurlok (wave 110J) --

    before = wave110j_cards.pools(plan)
    _empty_pools(plan)
    wave110j_cards.mana_lost(plan, before)


def _empty_pools(plan: Plan) -> None:
    kept = effects.keyword_actions.combat_mana_kept(plan)  # -- wave 3F -- firebending: kept until end of combat
    from app.rules import kept_mana  # -- refused copy/mana (wave 3R3): 106.4 "you don't lose this mana" --

    before = {pid: p.mana.get("R", 0) for pid, p in plan.state.players.items()}
    if kept_mana.empty(plan):
        # (both kinds of kept mana: the firebending {R} on top of what the other effects kept, never more than was there)
        for pid, n in kept.items():
            add = min(n, before.get(pid, 0) - plan.state.players[pid].mana.get("R", 0))
            if add > 0:
                plan.do({"type": "rules_mana", "player": pid, "delta": {"R": add}}, actor=pid)
        return
    if any(p.mana or p.mana_units for p in plan.state.players.values()):  # (wave 18B: units too)
        plan.do({"type": "rules_mana", "player": plan.active, "empty_all": True}, actor=plan.active)
        for pid, n in kept.items():
            plan.do({"type": "rules_mana", "player": pid, "delta": {"R": n}}, actor=pid)


def next_step(plan: Plan) -> None:
    miracle.clear(plan)  # -- casting extras (wave 18E) -- 702.94a: a draw is over once the game moves on
    empty_pools(plan)
    r = plan.rules
    phase = plan.state.turn.phase
    if phase == "cleanup":
        if r.cleanup_again:  # -- review 34 -- 514.3a: a new cleanup step (discard to hand size, 514.2 again)
            r.cleanup_again = False
            _mark_step(plan)
            on_step_start(plan)
            return
        start_next_turn(plan)
        return
    if phase == "combat_damage" and r.combat_round == "first":
        _mark_step(plan)
        combat_damage(plan, "second", "done")  # the regular damage step after first strike
        return
    if phase == "end_combat":
        player_control.combat_ended(plan)  # -- wave 110A -- Secret of Bloodbending: control of their combat phase ends with it
        combat.end_combat(plan)
    inserted = r.extra_steps.pop(0) if r.extra_steps else None
    finish_phase = inserted == "phase"
    if finish_phase:
        inserted = None
    boundary = phase in ("main1", "main2", "end_combat", "end") or (phase == "draw" and r.extra_beginning) or (phase == "upkeep" and r.upkeep_only) or finish_phase
    extra = inserted if inserted is not None else combat_rules.next_phase(plan) if boundary else None
    if inserted is None and (finish_phase or phase == "draw"):
        r.extra_beginning = False
    if inserted is None:
        r.upkeep_only = extra == "upkeep" and r.combat_tag == "upkeep_only"
    if extra is not None:
        plan.do({"type": "phase", "to": extra, "force": True}, actor=plan.active)
        if extra == "untap":
            r.extra_beginning = True
            _mark_step(plan)
            extra_untap_step(plan)
            return
    elif phase == "declare_attackers" and r.no_attackers and not combat.attackers_on(plan.state):  # (wave 110I: 508.8 creatures put onto the battlefield attacking count)
        # Nobody attacked: skip declare blockers and combat damage (rule 508.8).
        plan.do({"type": "phase", "to": "end_combat", "force": True}, actor=plan.active)
    else:
        plan.do({"type": "phase", "to": "next", "force": True}, actor=plan.active)
    if effects.skips.skip_steps(plan):  # -- refused grants/replacements (wave 3R2) -- 614.10: a skipped step or combat phase (wave 110I: waits for Fasting's choice)
        return
    if plan.state.turn.phase == "untap" and r.extra_beginning:
        _mark_step(plan)
        extra_untap_step(plan)
        return
    _mark_step(plan)
    on_step_start(plan)


def _keep_tapped(plan: Plan) -> list[str]:
    """Tapped permanents that don't untap during the untap step (502.3): the permanent's own
    "~ doesn't untap during your untap step.", an Aura's "Enchanted creature doesn't untap during
    its controller's untap step.", and a static over a selector ("Islands don't untap during their
    controllers' untap steps.", "Creatures with power 3 or greater don't untap …"), all of which
    app/rules/layers.py puts in ``Characteristics.imposed`` for whatever matches right now."""
    return [c.id for c in plan.state.cards.values() if c.tapped and c.zone.endswith(":battlefield")
            and not plan.manual(c) and _untap_restricted(plan, c)]  # (wave 29C: all of them — a cut list untapped the rest)


def _untap_restricted(plan: Plan, card: CardInstance) -> bool:
    from app.rules import previous_own_turns
    rules = scripts.statics(plan.ch(card))
    # (wave 110D: "can't become untapped" stays tapped too, 701.26)
    if any(r.startswith("doesnt_untap_counter:") and card.counters.get(r.split(":", 1)[1], 0) > 0 for r in rules):  # -- wave 110J -- Mindbender Spores, 502.3
        return True
    return "doesnt_untap" in rules or "cant_untap" in rules or (previous_own_turns.UNTAP in rules and previous_own_turns.attacked(plan.state, card) is not False)


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
    from app.game.rules_state import complete_own_turn
    complete_own_turn(plan.state)
    plan.rules.turn_end_objects[plan.active] = plan.rules.next_object  # (wave 110A: selectors "entered since your last turn ended")
    from app.rules import wave110b_cards  # -- combat damage since your last turn (wave 110B) --

    wave110b_cards.note_hits(plan)
    combat_rules.new_turn(plan)  # -- combat (wave 5C) -- added phases belong to the turn that ends
    keep = _keep_tapped(plan)
    # -- extra turns (wave 8A) -- 500.7: an extra turn comes first (the latest created first); otherwise the turn order goes
    # on after the player whose regular turn it was
    extra = extra_turns.take(plan)
    base = plan.rules.turn_base or plan.active
    upcoming = extra or plan.after(base)
    keep += [c for c in _exerted(plan, upcoming) if c not in keep]  # (wave 4H: an exerted one isn't stunned, 122.1d)
    # -- next untap step (wave 6A) -- 502.3: kept tapped by "doesn't untap during … next untap step" (not stunned either)
    keep += [c for c in next_untap.kept(plan, upcoming) if c not in keep]
    skipped: list[tuple[str, int]] = []  # 800.4k: a departed player's turn doesn't begin
    previous = (plan.active, plan.state.turn.number)
    plan.rules.previous_turn = previous
    plan.rules.monarch_began110b = plan.state.table.monarch  # -- wave 110B -- 725: "if you were the monarch as the turn began"
    # -- refused grants/replacements (wave 3R2) -- 614.10: skipped turns (they never begin: nothing ends with
    # them, 500.4) and a skipped untap step (nothing untaps, 502.2's day / night check doesn't happen)
    skip_to = extra or effects.skips.next_active(plan, base)
    if skip_to is None and upcoming != plan.after(plan.active):  # (leaving an extra turn)
        skip_to = upcoming
    # -- (wave 110C) -- 500.1: as the turn begins, before anything untaps: "untapped lands they controlled at the beginning of this turn" (Power Surge)
    with plan.reading():  # -- big boards (step scans) -- read-only: each permanent derived once
        began = sum(1 for c in plan.state.cards.values()
                    if c.zone.endswith(":battlefield") and c.controller == (skip_to or upcoming) and not c.tapped and "Land" in plan.ch(c).types)
    plan.rules.began_lands110c = {skip_to or upcoming: began}
    plan.rules.began_untapped110j = [plan.oid(c) for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and not c.tapped]  # -- (wave 110J) -- "started the turn untapped"
    stay = effects.skips.untap_skipped(plan, skip_to or upcoming)
    if stay is None:  # -- phasing (wave 13D) -- 702.26a/m: before the untap step, unless it is skipped
        phasing.untap_step(plan, skip_to or upcoming)
        keep += [c for c in _keep_tapped(plan) if c not in keep]  # (the ones that just phased in)
    if stay is not None:
        keep = list(dict.fromkeys([*keep, *stay]))
    keep = list(dict.fromkeys([*keep, *_exerted(plan, skip_to or upcoming)]))  # (wave 4H)
    keep = list(dict.fromkeys([*keep, *next_untap.kept(plan, skip_to or upcoming)]))  # (wave 6A)
    # -- untap choice (wave 7F) -- 502.3: "You may choose not to untap ~": asked below, after the turn changes
    asked = untap_choice.candidates(plan, skip_to or upcoming, keep) if stay is None else []
    # -- untap restrictions (wave 13E) -- 502.3: "Players can't untap more than one creature": held back until chosen below
    limited = untap_choice.limited(plan, skip_to or upcoming, keep) if stay is None else []
    keep = [*keep, *asked, *dict.fromkeys(c for g in limited for c in g[0])]
    # -- keyword actions & face-down (wave 3F) -- 122.1d: a stunned permanent stays tapped and loses a stun counter instead
    # (wave 7F: after every other reason to stay tapped, so a permanent that isn't untapping keeps its counter)
    stunned = effects.keyword_actions.stunned(plan, [c.id for c in plan.state.cards.values() if c.tapped and c.id not in keep])
    keep = [*keep, *stunned]
    keep += wave110h_cards.untap_hold(plan, skip_to or upcoming, keep) if stay is None else []  # -- untap hold (wave 110H) --
    from app.rules import (
        planar_more,  # -- planechase more (wave E1) -- Edge of Malacol: counters instead of untapping (614.1a)
    )

    keep += planar_more.untap_instead(plan, skip_to or upcoming, keep) if stay is None else []
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
    plan.rules.turn_base = base if extra else plan.active  # -- extra turns (wave 8A) -- 500.7
    plan.rules.extra_turn = bool(extra)  # -- static_other (wave 42A) -- 500.7: this turn is one an effect added
    from app.rules import wave111c_statics  # -- Star Trek statics (wave 111C) --

    wave111c_statics.turn_began(plan, bool(extra))  # ("haven't begun an extra turn this game")
    tt = plan.rules.turns_taken  # -- most-played cards (wave 43B) -- the game's first turn was never begun here: counted when it ends
    # ponytail: a state loaded mid-game starts the count at its next turn, so "first, second, or third turn" reads low there
    if not tt:
        tt[previous[0]] = 1
    tt[plan.active] = tt.get(plan.active, 0) + 1
    from app.rules import attack_destinations

    attack_destinations.begin_window(plan, "next_turn")
    player_control.turn_began(plan)  # -- controlling another player (wave 18H) -- 723.1: the whole turn, its untap choices too
    if untap_choice.ask(plan, asked, {"stunned": stunned, "previous": list(previous), "skipped": [list(s) for s in skipped],
                                      "plain": stay is None, "keep": keep}, limited):  # (wave 7F) the untap step waits for the choice
        return
    finish_turn_start(plan, stunned, previous, skipped, stay is None, keep)


def extra_untap_step(plan: Plan) -> None:
    from app.rules import next_untap, phasing, untap_choice

    pid = plan.active
    keep = _keep_tapped(plan)
    stay = effects.skips.untap_skipped(plan, pid)
    if stay is None:
        phasing.untap_step(plan, pid)
    keep = list(dict.fromkeys([*keep, *(stay or []), *_keep_tapped(plan), *_exerted(plan, pid), *next_untap.kept(plan, pid)]))
    asked = untap_choice.candidates(plan, pid, keep) if stay is None else []
    limited = untap_choice.limited(plan, pid, keep) if stay is None else []
    keep = list(dict.fromkeys([*keep, *asked, *(c for g in limited for c in g[0])]))
    stunned = effects.keyword_actions.stunned(plan, [c.id for c in plan.state.cards.values() if c.tapped and c.id not in keep]) if stay is None else []
    keep = list(dict.fromkeys([*keep, *stunned]))
    keep += wave110h_cards.untap_hold(plan, pid, keep) if stay is None else []  # -- untap hold (wave 110H) --
    from app.rules import planar_more  # -- planechase more (wave E1) -- Edge of Malacol

    keep += planar_more.untap_instead(plan, pid, keep) if stay is None else []
    previous = plan.rules.previous_turn or (plan.state.turn_order()[(plan.state.turn_order().index(pid) - 1) % len(plan.state.seat_order)], max(0, plan.state.turn.number - 1))
    finish = {"stunned": stunned, "previous": list(previous), "skipped": [], "plain": stay is None, "keep": keep, "same_turn": True}
    if untap_choice.ask(plan, asked, finish, limited):
        return
    finish_turn_start(plan, stunned, previous, [], stay is None, keep, same_turn=True)


def finish_turn_start(plan: Plan, stunned: list[str], previous: tuple[str, int], skipped: list[tuple[str, int]], plain: bool,
                      keep: list[str], same_turn: bool = False) -> None:
    """The rest of the turn's beginning after the untap step's permanents were chosen (``plain``: the untap step happened)."""
    stay: list[str] | None = None if plain else []
    effects.keyword_actions.lose_stun(plan, [c for c in stunned if c in plan.state.cards and plan.state.cards[c].controller == plan.active],
                                      plan.active)
    if not same_turn:
        delayed.turn_began(plan, skipped)  # 500.4, 800.4m: "until your next turn" effects end
    if stay is None:  # -- activation costs (wave 4H) -- 701.43a: that untap step happened; 614.10a: a skipped one doesn't count
        plan.rules.exerted = {k: p for k, p in plan.rules.exerted.items()
                              if p != plan.active and plan.rules.object_id(k.rsplit(".", 1)[0]) == k}
    if stay is None:  # -- next untap step (wave 6A) -- that untap step happened (614.10a: a skipped one doesn't count)
        next_untap.untap_step_done(plan, plan.active)
        from app.rules import contextual_mana_outcomes
        contextual_mana_outcomes.untap_operations(plan, plan.active)
    if stay is None:  # (wave 3R2: not in a skipped untap step)
        effects.designations.untap_day_night(plan, *previous)  # -- (wave 3E) 502.2: day / night --
    if (same_turn or not plan.state.settings.auto_untap) and stay is None:
        plan.do({"type": "untap_all", "player": plan.active, "keep_tapped": keep}, actor=plan.active)
    if stay is None:  # -- mana riders (wave 5A) -- 502.3: Seedborn Muse untaps the others' permanents in this untap step
        effects._untap_riders.other_untap_step(plan)
        wave110a_teferi.untap_step(plan)  # -- wave 110A -- Teferi's emblem
        from app.rules import (
            planar_more,  # -- planechase more (wave E1) -- Edge of Malacol's counters, Horizon Boughs
        )

        planar_more.untap_step(plan)
    # The untap step has no priority: straight on to upkeep.
    plan.do({"type": "phase", "to": "next", "force": True}, actor=plan.active)
    if effects.skips.skip_steps(plan):  # -- refused grants/replacements (wave 3R2) -- 614.10: a skipped upkeep / draw step
        return
    _mark_step(plan)
    on_step_start(plan)


def on_step_start(plan: Plan) -> None:
    """Turn-based actions at the start of a step."""
    state = plan.state
    phase = state.turn.phase
    ap = plan.active
    if phase == "draw":
        delayed.at_step(plan, "draw")  # The early-payment deadline closes as the step begins, before any draw choice.
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
        first_turn_skip = state.turn.number == 1 and len(plan.live()) == 2 and plan.rules.step_counts.get("draw", 1) == 1
        also = wave110a_teferi.extra_drawers(plan)  # -- wave 110A -- 504.1: Teferi's emblem, the holders draw in the same step
        if first_turn_skip:
            plan.note(f"{plan.name(ap)} skips the first draw (two-player game)")
        if also and first_turn_skip:
            effects.replace.draw_cards(plan, also, 1, then={"do": "draw_step"})
        elif not first_turn_skip:
            # -- replacement effects stage 2 (wave 2E): the turn-based draw (504.1) through the draw
            # choke point — replaced even from an empty library (121.6a, 614.11), else 704.5b --
            empty = not state.zones.get(zone_key(ap, "library"))
            if not effects.replace.draw_cards(plan, [ap, *also], 1, then={"do": "draw_step"}):
                return  # the drawing player chooses an order first (616.1); the step goes on after
            if empty and ap in plan.rules.drew_from_empty:
                plan.note(f"{plan.name(ap)} can't draw: their library is empty")
    elif phase in ("upkeep", "end"):
        if phase == "end":
            permissions.expire_end_step(plan)  # -- trigger tail (wave 15B) -- "until your next end step" ends as it begins
        triggers.at_step(plan, "upkeep_you" if phase == "upkeep" else "end_step_you")
        if phase == "end":
            triggers.monarch_end_step(plan)
        else:  # -- counters & designations (wave 3E): 726.2 the initiative's holder ventures into Undercity --
            effects.designations.initiative_upkeep(plan)
    elif phase == "main1":
        # -- sagas & attached-object triggers (wave 3S): 505.4 / 714.3c lore counters (a turn-based action) --
        from app.rules import sagas

        sagas.precombat_main(plan)
        # -- Attractions (wave 100L) -- 505.5: then the roll to visit (a turn-based action)
        from app.rules import attractions100l

        attractions100l.precombat_main(plan)
        from app.rules import (
            paradigm,  # -- keywords (wave 50H) -- 702.192a: the copies of the exiled paradigm cards
        )

        paradigm.main_phase(plan)
        # -- counters & designations (wave 3E): 728.1 rad counters (precombat main phase) --
        effects.designations.rad_trigger(plan)
    elif phase == "begin_combat":  # -- combat (wave 5C) -- "if it's the first combat phase of the turn"
        combat_rules.combat_began(plan)
        from app.rules import attack_destinations

        attack_destinations.begin_window(plan, "next_combat")
        delayed.at_step(plan, "begin_combat")  # -- commander sweep (wave 49B) -- 603.7: "At the beginning of that combat" (Moraug), the one combat phase a tagged trigger waits for
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
        delayed.at_step(plan, "cleanup")  # -- flash auras (wave 46B) -- 514.3a: "at the beginning of the next cleanup step" waits to go on the stack after 514.1-2
        cleanup_step(plan)
    if phase in ("main1", "main2"):  # -- stack interaction (wave 5B) -- "at the beginning of your next main phase" (603.7)
        delayed.at_step(plan, phase)
    if phase in ("upkeep", "draw", "main1", "begin_combat", "end_combat", "main2", "end"):  # (wave 31D: 511.2 "At end of combat")
        triggers.at_step_generic(plan)  # "At the beginning of [whose] [step]" (503, 504, 505, 507, 513)


def combat_damage(plan: Plan, rnd: str, then: str) -> None:
    """Deal a round of combat damage, or with AUTO COMBAT DAMAGE off (ASSISTED), ask first."""
    plan.rules.combat_round = then  # type: ignore[assignment]
    if combat.attackers_on(plan.state) and combat.ask_split(plan, rnd, then):  # type: ignore[arg-type]
        return  # (-- multiple blocks (wave 13B) -- 510.1d: a blocker's damage is divided first)
    if plan.options.auto_combat_damage or not combat.attackers_on(plan.state) or not plan.has_active_player():
        combat.deal_combat_damage(plan, rnd)  # type: ignore[arg-type]
        return
    preview = combat.damage_preview(plan, rnd)  # type: ignore[arg-type]
    decide(plan, player=plan.active, kind="confirm", prompt=f"Combat damage: {preview}",
           options=[DecisionOption(id="yes", label="Deal damage"), DecisionOption(id="no", label="By hand")],
           resume={"step": "combat_damage", "round": rnd})


def _resume_block_split(plan: Plan, d: Decision, chosen: list[str]) -> None:
    assert d.resume is not None
    creature = d.resume.get("creature") or d.resume["blocker"]  # ("blocker": a save from before wave 14A)
    plan.rules.block_split[creature] = {o.id: int(n) for o, n in zip(d.options, chosen, strict=True)}
    combat_damage(plan, d.resume["round"], d.resume["then"])
    if plan.rules.decision is None:
        _after_resolution(plan)


def _resume_assign_unblocked(plan: Plan, d: Decision, chosen: list[str]) -> None:
    assert d.resume is not None
    plan.rules.assign_unblocked[d.resume["creature"]] = chosen[0] == "yes"
    combat_damage(plan, d.resume["round"], d.resume["then"])
    if plan.rules.decision is None:
        _after_resolution(plan)


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
    from app.rules import hand_size  # -- hand size (wave 4J) -- "You have no maximum hand size." (402.2)

    limit = hand_size.maximum(plan, ap, warn_legacy=True)  # -- static statics (wave 10B) -- (changed by statics; None: no maximum)
    excess = 0 if limit is None else len(hand) - limit
    if excess > 0:
        decide(
            plan, player=ap, kind="choose_cards",
            prompt=f"Discard {excess} card{'s' if excess != 1 else ''} down to your maximum hand size ({limit})",
            options=[DecisionOption(id=cid, label=plan.state.cards[cid].name or "Card", card_id=cid) for cid in hand],
            min_choices=excess, max_choices=excess, resume={"step": "cleanup_discard"},
        )
        return
    finish_cleanup(plan)


def finish_cleanup(plan: Plan) -> None:
    turn_cleanup(plan)
    # Cleanup normally grants no priority: the turn ends. -- review 34 -- 514.3a: unless a state-based action is performed or a triggered
    # ability waits to be put on the stack (a discard to hand size: Rielle's ruling, "you'll draw that many cards … and a new cleanup step
    # will happen after that one"): then the players get priority in this step, and once the stack is empty and all pass another cleanup
    # step begins (next_step)
    seq = plan.state.seq
    sba.check(plan)
    performed = plan.state.seq != seq
    triggers.collect(plan)
    r = plan.rules
    if r.decision is not None or performed or any(t.controller in plan.live() for t in r.pending_triggers):
        r.cleanup_again = True
        _mark_step(plan)
        return
    # 500.4: cleanup normally ends without priority, so next_step is not called.
    # End-of-turn retention has expired; permanent retention still applies.
    empty_pools(plan)
    start_next_turn(plan)


def turn_cleanup(plan: Plan) -> None:
    """514.2: damage is removed and "until end of turn" effects end, simultaneously."""
    from app.rules import damage_retention83

    damage_retention83.cleanup(plan)
    if plan.rules.effects:
        layers.end_of_turn(plan)
    from app.rules import (
        wave110k_cards,  # -- (wave 110K) -- Teferi, Timeless Voyager's "can't phase in" ends in the cleanup of the holder's next turn
    )

    wave110k_cards.end_of_turn(plan)
    plan.rules.no_regen_sources110k = []  # (wave 110K) Runesword's rule ends with the turn
    plan.rules.regen_shields = {}  # regeneration shields last "this turn"
    plan.rules.wipe_shields110o = {}  # -- (wave 110O) -- and so do Pyramids' damage-removal shields
    plan.rules.regeneration_riders = []
    plan.rules.no_regen = []  # (wave 19E) and so does "can't be regenerated this turn"
    plan.rules.prevention = {}  # and so do prevention shields
    plan.rules.prevention_riders = {}
    permissions.expire(plan)  # "you may play that card this turn" and friends
    spell_grants.expire(plan)  # -- spell grants (wave 28C) -- "the next spell you cast this turn" ends (514.2)
    delayed.cleanup(plan)  # "when … this turn" delayed triggers stop watching (514.2)
    for card in list(plan.state.cards.values()):
        for marker in [m for m in card.effects if m.text in ("until end of turn", "this combat")]:
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
        "enters" in a.text and a.kind in ("triggered", "static") and not coverage.ability_supported(ch, a.index) and not a.linked  # (-- trigger other (wave 52B) -- 607.2f: a linked word's ability isn't there until the word is chosen as it enters: Frontier Siege's Dragons line)
        for a in ch.abilities
    )


def leave_stack(plan: Plan, card_id: str, controller: str, *, tapped: bool = False, countered: bool = False) -> None:
    """A resolved spell leaves the stack: to the battlefield or its owner's graveyard, or into exile
    if it was cast with flashback (702.34a), or back to its owner's hand with buyback (702.27a)."""
    # -- X sized by a count (wave 4K) -- it shuffled itself into its library (608.2n)
    from app.rules import x_spells

    oid = plan.oid(card_id)
    printed_delve = plan.state.cards[card_id].zone == STACK and any(
        ab.index < 100 and ab.kind == 'keywords' and 'delve' in ab.keywords
        for ab in plan.ch(plan.state.cards[card_id]).abilities)
    if not countered and x_spells.left_stack_itself(plan, card_id):
        return
    from app.rules import (
        resolve_exile,  # -- cast riders (wave 38C) -- 614.1a, 608.2n: "exile it instead of putting it into your graveyard as it resolves"
    )

    if oid in plan.rules.exile_resolves and resolve_exile.resolved(plan, card_id, controller, countered):  # (first: the controller picks, 616.1; this one has "If you do")
        return
    was_rebound = oid in plan.rules.rebound_cast
    plan.rules.rebound_cast = [o for o in plan.rules.rebound_cast if o != oid]
    card = plan.state.cards[card_id]
    record = plan.rules.payments.get(oid)
    # 109.5, 702.88a: a static ability's "your hand" is the CURRENT
    # controller's hand. A control change can enable or disable rebound.
    hand_player = (record.cast_from_player or record.controller) if record is not None else card.owner if was_rebound else None
    from_hand = record.cast_from == "hand" if record is not None else was_rebound
    from app.rules import (  # -- static permanents (wave 100D) -- Cast Through Time; (wave F1) Trail of the Mage-Rings
        planar_more2,
        static_perm100d,
    )

    if not countered and from_hand and hand_player == controller and ("rebound" in plan.ch(card).keywords or (
            plan.ch(card).is_instant_or_sorcery and (static_perm100d.yours(plan, static_perm100d.REBOUND, controller)
                                                     or planar_more2.rebound_all(plan)))):  # (wave F1: Trail of the Mage-Rings)
        from app.rules import (
            wave110b_cards,  # -- rebound vs hand (wave 110B) -- 616.1: its controller picks between the two replacements
        )

        if wave110b_cards.rebound_or_hand(plan, card_id, controller):
            return
        plan.do({"type": "move", "card_ids": [card_id], "to": {"player": card.owner, "zone": "exile"}}, actor=controller)
        plan.rules.rebounding.append(card_id)
        plan.rules.rebound_objects[card_id] = plan.oid(card_id)
        plan.rules.rebound_controllers[card_id] = controller
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
    # -- instead (wave 20B) -- 614.1a: a resolved instant or sorcery card that "would be put into a graveyard" from the stack is exiled by
    # a Rest in Peace-style effect ("an instant or sorcery card … from anywhere", "a card …"), like the one cast from a graveyard above
    card = plan.state.cards[card_id]
    if card_id in plan.state.zones.get(STACK, []) and not card.is_token and card.card_id is not None and plan.ch(card).is_instant_or_sorcery \
            and replacements.leave_stack_instead(plan, card, controller):  # -- zone replacements (wave 22C) -- exile / shuffle / 616.1 choice
        return
    # -- review 25B -- 720.3d: an Omen spell is shuffled into its owner's library as it resolves; 715.3d: an Adventure is exiled (resolve_top)
    # and its controller may play it for as long as it remains exiled, not as an Adventure
    spell_types = plan.ch(card).subtypes & {"Adventure", "Omen"} if not countered and not card.is_token and card.card_id else set()
    if "Omen" in spell_types and card_id in plan.state.zones.get(STACK, []):
        plan.do({"type": "move", "card_ids": [card_id], "to": {"player": card.owner, "zone": "library"}}, actor=controller)
        plan.do({"type": "shuffle", "player": card.owner}, actor=controller)
        return
    stack = plan.state.zones.get(STACK, [])
    if "Adventure" in spell_types and card_id in stack:
        plan.do({"type": "resolve_top", "force": True, "tapped": tapped, **({"card_id": card_id} if stack[-1] != card_id else {})},
                actor=controller)
        plan.rules.payments.pop(oid, None)
        gone = plan.state.cards.get(card_id)
        if gone is not None and gone.zone.endswith(":exile"):
            from app.rules import selectors

            plan.rules.permissions.append(Permission(
                id=secrets.token_hex(4), player=controller, play=True, cast=True, zone="exile", object_id=plan.oid(gone), card=card_id,
                until="permanent", turn=plan.state.turn.number, filter=selectors.Selector(zones=(STACK,), not_subtypes=("Adventure",)).key(),
                label=f"{gone.name}: cast it from exile (it went on an adventure)"))
        return
    if card_id in stack:
        step: dict[str, Any] = {"type": "resolve_top", "force": True, "tapped": tapped}
        spot = plan.rules.cast_spots.pop(oid, None)  # -- drag to cast -- the caster's drop spot, only on the caster's own battlefield
        if spot is not None and not countered and card.controller == spot.player:
            step.update(x=spot.x, y=spot.y)
        if stack[-1] != card_id:  # -- refused look/cast-free (wave 3R5) -- 608.2g: spells cast while it resolved are
            step["card_id"] = card_id  # above it now; it leaves the stack all the same (608.2n)
        plan.do(step, actor=controller)
        if not countered:  # -- keywords (wave 50H) -- 702.55a haunt on an instant or sorcery: put into a graveyard during its resolution
            from app.rules import haunt

            haunt.spell_resolved(plan, card_id, controller)
        record = plan.rules.payments.pop(oid, None)
        if (sacrificed := plan.rules.sacrificed110j.pop(oid, None)) is not None and card_id in plan.state.cards and plan.state.cards[card_id].zone.endswith(":battlefield"):
            plan.rules.sacrificed110j[plan.oid(card_id)] = sacrificed  # -- Gluttonous Hellkite (wave 110J) -- its cast trigger's count follows the permanent
        if record is not None and card_id in plan.state.cards and plan.state.cards[card_id].zone.endswith(":battlefield"):
            plan.rules.payments[plan.oid(card_id)] = record  # the permanent remembers how its spell was paid
            if record.pick110e and "|" not in record.pick110e:  # -- cast-time choice (wave 110E) -- public, read as the permanent's "Chosen creature type"
                plan.do({"type": "set_choice", "card_id": card_id, "key": "Chosen creature type", "value": record.pick110e}, actor=controller)
            if (paid := [c for c in record.exiled if c != card_id and c in plan.state.cards and plan.state.cards[c].zone.endswith(":exile")
                        and (not record.exiled_objects or plan.oid(c) in record.exiled_objects)]) \
                    and any(ab.index < 100 and ab.kind not in ("triggered", "activated") and re.search(r"\bexile\b", ab.text, re.IGNORECASE)
                            and re.search(r"\bcost\b|^escape", ab.text, re.IGNORECASE) for ab in plan.ch(plan.state.cards[card_id]).abilities):
                # -- resolution memory (wave 22D) -- 607.2q: the cards exiled to pay the permanent spell's cost are "exiled with" the permanent
                # (review 22D: only through a cost an ability printed on it allows — not an escape cost Underworld Breach grants)
                plan.rules.exiled_with[plan.oid(card_id)] = [*plan.rules.exiled_with.get(plan.oid(card_id), []), *(plan.oid(c) for c in paid)]
            if printed_delve:
                delved_objects = [c.exiled_object_id for c in record.contributions if c.kind == 'delve' and c.exiled_object_id
                                  and c.card in plan.state.cards and plan.state.cards[c.card].zone.endswith(':exile')
                                  and plan.oid(c.card) == c.exiled_object_id]
                key = plan.oid(card_id)
                plan.rules.exiled_with[key] = list(dict.fromkeys([*plan.rules.exiled_with.get(key, []), *delved_objects]))
        if oid in plan.rules.bestowed:  # -- keywords (wave 15E) -- the bestowed Aura permanent is the spell it was (702.103b)
            plan.rules.bestowed = [o for o in plan.rules.bestowed if o != oid]
            if card_id in plan.state.cards and plan.state.cards[card_id].zone.endswith(":battlefield"):
                plan.rules.bestowed.append(plan.oid(card_id))
        if card_id in plan.state.cards and plan.state.cards[card_id].zone.endswith(":battlefield"):
            from app.rules import history  # -- this-turn history (wave 4D) --

            history.note_became(plan, oid, plan.oid(card_id))
        copying.resolved(plan, card_id, oid)  # -- copy system (wave 2F): a permanent spell's copy became a token (608.3f)
    else:  # (defensive: resolution never adds to the stack today)
        plan.do({"type": "move", "card_ids": [card_id], "to": {"zone": "graveyard"}}, actor=controller)


def resolve_top_of_stack(plan: Plan) -> None:
    miracle.clear(plan)  # -- casting extras (wave 18E) --
    top_id = plan.state.zones[STACK][-1]
    top = plan.state.cards[top_id]
    entry = plan.rules.stack.get(top_id)
    if entry is not None:
        from app.rules import token_stacks

        token_stacks.check_targets(plan, entry)  # -- engine token stacks -- a target is one member, split off as it was chosen
        effects.begin_resolution(plan, top_id, entry)  # an automated spell or ability
        return
    ch = plan.ch(top)
    controller = top.controller if top.controller in plan.live() else plan.active
    if plan.oid(top) in plan.rules.mutating and not plan.manual(top):  # -- merged permanents (wave 18D) -- 702.140b-c, 608.3b/d
        from app.rules import merged

        if merged.resolve(plan, top, controller):
            if plan.rules.decision is None:
                _after_resolution(plan)
            return
        ch = plan.ch(top)
    if ch.is_permanent_card and plan.rules.specimens110f and not plan.manual(top):  # -- wave 110F -- Gather Specimens: a creature enters under the controller it names (614.1a)
        from app.rules import wave110f_fin

        if (taken110f := wave110f_fin.entering_player(plan, controller)) != controller and wave110f_fin.creature_entering(plan, top, taken110f):
            plan.do({"type": "set_controller", "card_ids": [top_id], "player": taken110f}, actor=controller)  # (as wave110a_control.give: the resolution below reads the card's controller)
            controller = taken110f
    if ch.is_permanent_card and not plan.manual(top) and not needs_manual_resolution(ch) \
            and replacements.stack_entry_choice(plan, top, controller):
        return  # "As ~ enters, choose a color": chosen before it enters (614.12a); resolved again with the answer
    ch = plan.ch(top)  # -- copy system (wave 2F): as it will enter — entering as a copy, the copied text (707.5, 614.12)
    if top_id in plan.rules.aura_targets:
        from app.game.rules_state import remember_stack

        remember_stack(plan.state, top_id)  # Retain Aura targets before normal resolution consumes its map.
    aura_target = plan.rules.aura_targets.pop(top_id, None)
    # An instant, sorcery or ability the engine didn't put on the stack (moved there by hand) has
    # no recorded targets or choices: its controller resolves it by hand. So has an Aura without one.
    manual = ch.is_instant_or_sorcery or ch.is_ability or needs_manual_resolution(ch) or plan.manual(top) \
        or ("Aura" in ch.subtypes and aura_target is None)
    if aura_target is not None and not manual:
        selector = attachments.enchant_selector(ch)
        if (selector is None or not still_legal(plan, selector, controller, aura_target, as_spell(ch, top.stack_info.x if top.stack_info else 0))) and bestow.is_bestowed(plan.state, top):
            bestow.cease(plan, top, "its target is illegal")  # -- keywords (wave 15E) -- 702.103e: it resolves as a creature spell
            aura_target = None
            ch = plan.ch(top)
            manual = ch.is_instant_or_sorcery or ch.is_ability or needs_manual_resolution(ch) or plan.manual(top)
        elif selector is None or not still_legal(plan, selector, controller, aura_target, as_spell(ch, top.stack_info.x if top.stack_info else 0)):
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
    # -- cast permissions (wave 30Q) -- "If you cast a spell this way, that artifact enters tapped / with a finality counter on it" (122.6, 614.1c)
    rider = plan.rules.cast_enters.pop(plan.oid(top_id), None) or {}
    ep: dict[str, Any] = replacements.entry_plan(plan, top, controller, answers=answers, extra=rider.get("counters")) if entering else {"tapped": False}
    paid_for = plan.rules.payments.get(plan.oid(top_id))
    sneaked = entering and paid_for is not None and paid_for.alternative == "sneak"
    if sneaked or (entering and rider.get("tapped")):
        ep["tapped"] = True  # -- keywords (wave 30I) -- 702.190b: a permanent spell whose sneak cost was paid enters tapped (and attacking, below)
    x = top.stack_info.x if top.stack_info else None
    if ep.get('divert_zone') == 'exile':
        from app.rules import entry_payment_diversion

        plan.rules.payments.pop(plan.oid(top_id), None)
        entry_payment_diversion.divert(plan, top_id, controller)
        _after_resolution(plan)
        return
    if ep.get("life"):
        from app.rules import replace as _replace_life  # (wave 28B: 119.4)
        _replace_life.lose_life(plan, [(controller, int(ep["life"]))], actor=controller, paid=True)
    # -- entering for a cost (wave 5G) -- paid as it would enter, or it goes to its owner's graveyard instead (614.6)
    from app.rules import enter_cost

    if ep.get("pay") and not enter_cost.pay(plan, top, controller, ep["pay"], controller):
        ep["divert"] = True
    if ep.get("divert"):
        plan.rules.payments.pop(plan.oid(top_id), None)
        enter_cost.divert(plan, top_id, controller)
        _after_resolution(plan)
        return
    # -- end entering for a cost (wave 5G) --
    from app.rules import devour  # -- keyword mechanics (wave 9D) -- 702.82a

    devour.sacrifice(plan, ep, controller)
    from app.rules import (
        copying as _copying,  # -- (wave 110C) -- The Mimeoplasm: the two graveyard cards are exiled as it enters
    )

    _copying.exile_pair(plan, ep, controller)
    from app.rules import static_perm100d  # -- static permanents (wave 100D) -- 614.12: done as it enters

    static_perm100d.as_enters(plan, top_id, ep, controller)
    from app.rules import amplify  # -- casting extras (wave 18E) -- 702.38a

    amplify.reveal(plan, ep, controller)
    replacements.turn_down(plan, ep, controller)  # -- hidden exile (wave 18A) --
    from app.rules import creature_entry_redirect

    if entering and creature_entry_redirect.conflict(plan, top, controller):  # -- cards (wave 110H) -- Don't Blink + an exile replacement: 616.1 choice (sba.offer_616)
        creature_entry_redirect.hold(plan, top)
        _after_resolution(plan)
        return
    if entering and creature_entry_redirect.shuffles(plan, top, controller):  # -- cards (wave 110H) -- Don't Blink
        creature_entry_redirect.shuffle_in(plan, top_id)
        plan.rules.payments.pop(plan.oid(top_id), None)
        _after_resolution(plan)
        return
    if entering and creature_entry_redirect.exiles(plan, top, controller):
        plan.do({"type": "move", "card_ids": [top_id], "to": {"player": top.owner, "zone": "exile"}}, actor=controller)
        plan.rules.payments.pop(plan.oid(top_id), None)
        _after_resolution(plan)
        return
    if entering:  # -- entry control (wave 110A) -- 110.2, 614.12: it enters under the opponent chosen
        from app.rules import wave110a_control

        wave110a_control.give(plan, top_id, ep.get("choices"))
        controller = plan.state.cards[top_id].controller
    leave_stack(plan, top_id, controller, tapped=bool(ep["tapped"]))
    if entering:
        rooms.entered(plan, top_id)  # -- Rooms (wave 18G) -- 709.5d: the cast half's door is unlocked as it enters
    if aura_target is not None and not manual and plan.state.cards[top_id].zone.endswith(":battlefield"):
        attachments.attach(plan, top_id, aura_target.id, controller)  # 303.4f: it enters attached to its target
    if entering:
        counters = rider.get("counters")
        paid = plan.rules.payments.get(plan.oid(top_id))
        if paid is not None and paid.alternative == "impending" and not manual:  # -- cast keywords (wave 43D) -- 702.176a: "it enters with N time counters on it"
            from app.rules import alt_costs

            if (n_time := alt_costs.impending_n(ch)) is not None:
                counters = {**(counters or {}), "time": (counters or {}).get("time", 0) + n_time}
        replacements.after_entry(plan, top_id, controller, x=x, choices=ep.get("choices"), extra_counters=counters)
        permissions.gain_on_entry(plan, top_id, controller, rider)
    if top_id in plan.rules.evoked:  # 702.74a: "When this permanent enters, if its evoke cost was paid, its controller sacrifices it."
        plan.rules.evoked = [c for c in plan.rules.evoked if c != top_id]
        entered_now = plan.state.cards.get(top_id)
        if entered_now is not None and entered_now.zone.endswith(":battlefield"):
            # -- trigger multipliers (wave 5D) -- an enters trigger (603.2d)
            from app.rules import trigger_multipliers

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
    rec = plan.rules.payments.get(plan.oid(top_id))
    if rec is not None and rec.alternative == "warp" and entering and not manual:  # -- keywords (wave 15E) -- 702.185a
        entered_now = plan.state.cards.get(top_id)
        if entered_now is not None and entered_now.zone.endswith(":battlefield"):
            delayed.create_move(plan, controller, top_id, plan.oid(top_id), "exile", entered_now.name, warp=True)
    if rec is not None and rec.flash_sac and entering and not manual:  # -- flash auras (wave 46B) -- the controller of the permanent sacrifices it at the next cleanup step
        entered_now = plan.state.cards.get(top_id)
        if entered_now is not None and entered_now.zone.endswith(":battlefield"):
            delayed.create_move(plan, controller, top_id, plan.oid(top_id), "graveyard", entered_now.name, sacrifice=True, step="cleanup")
    if rec is not None and rec.alternative == "blitz" and entering and not manual:  # -- keywords (wave 15E) -- 702.152a
        entered_now = plan.state.cards.get(top_id)
        if entered_now is not None and entered_now.zone.endswith(":battlefield"):
            oid = plan.oid(top_id)
            layers.add_effect(plan, affected=[oid], layer="6", source=None, controller=controller, add_keywords=("haste",),
                              duration="permanent", label="Haste (blitz)",
                              add_abilities=["When this permanent is put into a graveyard from the battlefield, draw a card."])
            delayed.create_move(plan, controller, top_id, oid, "graveyard", entered_now.name, sacrifice=True)
    if sneaked and not manual:  # -- keywords (wave 30I) -- 702.190b, 506.3d: attacking what the returned creature attacked, unblocked
        from app.rules import ninjutsu

        ninjutsu.attack_returned(plan, top_id, rec, controller)
    if top_id in plan.rules.eot_haste110m:  # (wave 110M) Alaundo the Seer: "it gains haste until end of turn"
        plan.rules.eot_haste110m = [c for c in plan.rules.eot_haste110m if c != top_id]
        entered_now = plan.state.cards.get(top_id)
        if entered_now is not None and entered_now.zone.endswith(":battlefield"):
            layers.add_effect(plan, affected=[plan.oid(top_id)], layer="6", source=None, controller=controller,
                              add_keywords=("haste",), duration="end_of_turn", label="Haste (Alaundo the Seer)")
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
                    info: CardInfo | None, via: str | None = None) -> permissions.Grant | None:
    """How ``player`` may play this land from where it is: from their hand (305.1), or a
    permission ("you may play lands from your graveyard", "you may play that card this turn").
    (-- cast permissions (wave 32D) -- ``via``: the limited permission the player named, 601.2)"""
    if card.zone == zone_key(player, "hand"):
        return permissions.Grant("hand")
    found = [g for g in permissions.grants(state, player, card, ch, info, verb="play") if g.zone_ok and (via is None or g.use == via)] if info else []
    return permissions.with_choices(found[0], found) if found else None


def _exiled_land_probe(state: GameState, player: str, card: CardInstance, info: CardInfo | None,
                       via: str | None = None) -> tuple[CardInstance, Characteristics] | None:
    """A face-down exile object is played face up only under current authority (406.3). Never turn the real card over to probe it."""
    from app.game.visibility import can_see
    from app.rules import characteristics as chars
    from app.rules.layers import derive

    if info is None or not can_see(state, card, player):
        return None
    probe = card.model_copy(update={'face_down': False, 'face_down_kind': None, 'face_down_as': None})
    ch = derive(state, probe, chars.of(probe, info), info)
    if land_play_grant(state, player, card, ch, info, via) is None:
        return None
    return probe, ch


def land_play_problem(state: GameState, player: str, card: CardInstance, ch: Characteristics, *,
                      check_priority: bool = True, info: CardInfo | None = None) -> str | None:
    """Why ``player`` can't play ``card`` as a land right now (None if they can)."""
    r = state.rules
    if r is None:
        return "Rules automation is off"
    if card.face_down and card.zone.endswith(':exile') and ch.face_down:
        visible = _exiled_land_probe(state, player, card, info)
        if visible is None:
            return "You aren't authorized to play that face-down exiled card"
        _, ch = visible
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
    from app.rules import cast_limits, wave110a_spells  # (-- wave 110A -- Ward of Bones)

    if info is not None and (barred := next((src for src, d in cast_limits._statics(state, info, "cant_play_lands") if (wave110a_spells.more_of(state, info, src, d, player) if d.get("more110a") else d.get("players") or src.controller == player)), None)) is not None:
        return f"{barred.name or 'A permanent'}: you can't play lands"  # -- most-played cards III (wave 46C) -- 305.1
    from app.rules import wave110a_final  # -- wave 110A -- Damping Engine

    if info is not None and (barred := wave110a_final.land_barred(state, info, player)) is not None:
        return f"{barred.name or 'A permanent'}: you can't play lands"  # (305.1: it controls the most permanents)
    if info is not None and card.zone == zone_key(player, "hand") and (barred := next(
            (src for src, d in cast_limits._statics(state, info, "cast_limit") if d.get("lands_from_hand") and src.controller == player), None)) is not None:
        return f"{barred.name or 'A permanent'}: you can't play lands from your hand"  # -- static permanents (wave 100D) -- Experimental Frenzy (305.1)
    if info is not None and card.zone.endswith(":graveyard") and (barred := next(
            (src for src, _ in cast_limits._statics(state, info, "cant_play_gy_lands") if src.controller != player), None)) is not None:
        return f"{barred.name or 'A permanent'}: you can't play land cards from graveyards"  # -- cant restrictions (wave 50G) -- Tomik, Distinguished Advokist
    from app.rules import card_names

    if info is not None and (barred := next((src for src, d in cast_limits._statics(state, info, "cast_limit") if d.get("named_lands110f") and card_names.matches(Plan.view(state, src.controller, info), src.id, ch)), None)) is not None:
        return f"{barred.name or 'A permanent'}: you can't play {ch.name}"  # -- two names (wave 110F) -- Null Chamber: 305.1
    from app.rules import wave110n_cards  # -- (wave 110N) -- Rock Jockey: 305.1

    if (why := wave110n_cards.land_problem(state, player, info)) is not None:
        return why
    if (why := cast_limits.land_problem(state, player, ch, info, card.zone)) is not None:
        return why  # -- chosen filters (wave 53B) -- Conjurer's Ban: a land with the chosen name can't be played until a turn
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
    if probe.face and (plan.info.get(card.card_id or "") or {}).get("layout") != "modal_dfc":
        raise ActionError("Only a modal double-faced card can be played with its back face up (712.12)")
    if probe.face_down and card.zone.endswith(':exile'):
        visible = _exiled_land_probe(plan.state, plan.actor, probe, plan.info, a.via)
        if visible is None:
            raise ActionError("You aren't authorized to play that face-down exiled card")
        probe, _ = visible
    problem = land_play_problem(plan.state, plan.actor, card, plan.ch(probe), info=plan.info)
    if problem:
        raise ActionError(problem)
    grant = land_play_grant(plan.state, plan.actor, card, plan.ch(probe), plan.info, a.via)
    if a.via is not None and (grant is None or grant.use != a.via):  # -- cast permissions (wave 32D) -- 601.2: a permission that doesn't cover this play
        raise ActionError(f"{plan.ch(probe).name or 'That card'} can't be played using that permission now")
    if grant is not None and len(grant.among) > 1:  # … or several limited ones fit: which does the player use up? (asked before anything else is)
        permissions.ask_use(plan, a, card, plan.ch(probe), grant.among, "play")
        return
    # The land's own "enters" replacement effects (614.1c-d, app/rules/replacements.py): "enters
    # tapped [unless …]", a shock land's pay-life-or-tapped choice (made before it enters: 614.12a),
    # "enters [tapped] with … counters" as it enters (122.6).
    if plan.rules.specimens110f:  # -- wave 110F -- Gather Specimens: a land creature (Dryad Arbor) played by an opponent would enter under another player's control: by hand
        from app.rules import wave110f_fin

        if wave110f_fin.entering_player(plan, plan.actor) != plan.actor and wave110f_fin.creature_entering(plan, probe, plan.actor):
            raise ActionError("Gather Specimens: this creature land would enter under another player's control. Put it onto the battlefield with the table tools")
    ep = replacements.entry_plan(plan, probe, plan.actor, pay_life=a.pay_life, answers=plan.rules.entry_choices.get(card.id))
    if ep.get("choice") is not None and "what" in ep["choice"]:  # "As ~ enters, choose …": before it enters
        prompt, options = replacements.choice_prompt(plan, card, plan.actor, ep["choice"])
        decide(plan, player=plan.actor, kind="choose_one", prompt=prompt, options=options, source=card,
               resume={"step": "land_enter_choice", "card": card.id, "what": ep["choice"]["what"],
                       "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})})
        return
    if ep.get("choice") is not None:
        prompt, options = replacements.choice_prompt(plan, probe, plan.actor, ep['choice'])
        decide(plan, player=plan.actor, kind="choose_one", prompt=prompt, options=options,
               resume={"step": "shock", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})}, source=card)
        return
    if a.face is not None and a.face != card.face:
        plan.do({"type": "set_face", "card_id": card.id, "face": a.face})
    from app.game.rules_state import snapshot

    played_snapshot = snapshot(plan.state, card.id)
    from app.rules import characteristics as played_chars
    from app.rules import granted

    played_snapshot.abilities, played_snapshot.keywords, played_snapshot.traits = granted.last_existed(
        played_chars.of(plan.state.cards[card.id], plan.info), plan.ch(plan.state.cards[card.id]))
    if ep.get("life"):
        from app.rules import replace as _replace_life  # (wave 28B: 119.4)
        _replace_life.lose_life(plan, [(plan.actor, int(ep["life"]))], paid=True)
    # -- entering for a cost (wave 5G) -- the land was played (305.1); its entering is what the payment replaces
    from app.rules import enter_cost

    if ep.get("pay") and not enter_cost.pay(plan, card, plan.actor, ep["pay"], plan.actor):
        ep["divert"] = True
    if ep.get("divert"):
        enter_cost.divert(plan, card.id, plan.actor)
        from app.game.rules_state import emit

        emit(plan.state, "land_played", object_id=played_snapshot.object_id, card=card.id, player=plan.actor,
             from_zone=played_snapshot.zone, played_snapshot=played_snapshot)
        plan.rules.entry_choices.pop(card.id, None)
        if grant is not None and grant.how == "permission":
            permissions.consume(plan, grant, card_id=card.id, verb="play")
        r = plan.rules
        r.lands_played[plan.actor] = TurnCount(turn=plan.state.turn.number, count=r.lands_this_turn(plan.actor, plan.state.turn.number) + 1)
        r.passed = []
        r.priority = plan.actor
        return
    # -- end entering for a cost (wave 5G) --
    from app.rules import (
        devour,  # -- sacrificed as it enters (wave 110I) -- Sheltered Valley (614.1a), a land entering by being played
    )

    devour.sacrifice(plan, ep, plan.actor)
    payload: dict[str, Any] = {"type": "move", "card_ids": [card.id], "to": {"zone": "battlefield"},
                               "tapped": bool(ep["tapped"]) or bool(grant is not None and grant.enters and grant.enters.get("tapped"))}  # (wave 51D: "If you do, it enters tapped", 614.1d)
    if a.x is not None and a.y is not None:
        payload.update(x=a.x, y=a.y)
    if probe.face:  # (review 25B) 712.12: a modal double-faced land played back face up enters that way (leaving the hand resets the face)
        payload["back_ids"] = [card.id]
    from_where = card.zone.rsplit(":", 1)[-1]
    plan.do(payload)
    plan.rules.entry_choices.pop(card.id, None)
    if grant is not None and grant.how == "permission":
        permissions.consume(plan, grant, card_id=card.id, verb="play")  # ("once during each of your turns")
        plan.note(f"{plan.name(plan.actor)} plays {card.name} from their {from_where} ({grant.label})", [card.id])
    replacements.after_entry(plan, card.id, plan.actor, choices=ep.get("choices"))
    permissions.gain_on_entry(plan, card.id, plan.actor, grant.enters if grant is not None else None)  # (-- cast permissions (wave 30Q) -- "If you do, it gains …")
    # -- entry forms (wave 5F) -- 305.1: the land was played ("When you play another land", City of Traitors)
    from app.game.rules_state import emit

    if plan.state.cards[card.id].zone.endswith(":battlefield"):
        emit(plan.state, "land_played", object_id=plan.oid(card.id), card=card.id, player=plan.actor,
             from_zone=played_snapshot.zone)
    else:
        emit(plan.state, "land_played", object_id=played_snapshot.object_id, card=card.id, player=plan.actor,
             from_zone=played_snapshot.zone, played_snapshot=played_snapshot)
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
    valid = {o.id for o in d.options if o.group != "seen"}  # (wave 53B: the cards a player looked at, shown beside the options, are not answers)
    if cancelable(d):
        valid.add("cancel")  # (-- cancelling a cast (wave 24D) --)
    from app.rules import card_names  # -- card names (wave 22B) -- 201.4: a typed name answers it

    if card_names.is_free_text(d) and not (chosen == ["cancel"] and cancelable(d)):
        if chosen or a.amounts:
            raise ActionError("Type a card name")
        chosen, valid = [card_names.answer(plan, d, a.name)], set()
    elif a.name is not None:
        raise ActionError("A name only answers a card-name choice")
    if d.kind == "divide":  # 601.2d: an amount per option (target), at least 1 each, adding up to the total
        total = int((d.resume or {}).get("total", 0))
        least = int((d.resume or {}).get("least", 1))  # (-- multiple blocks (wave 13B) -- 510.1d: a share may be 0)
        if chosen or len(a.amounts) != len(d.options) or any(n < least for n in a.amounts) or (sum(a.amounts) != total and not ((d.resume or {}).get("upto") and sum(a.amounts) < total)):
            raise ActionError(f"Divide {total} among the {len(d.options)} targets: at least {least} each, {total} in all")
        need, free = (d.resume or {}).get("lethal") or [], (d.resume or {}).get("free")
        if free is not None and a.amounts[free] > 0 and any(a.amounts[i] < k for i, k in enumerate(need)):
            raise ActionError("Assign lethal damage to every blocker before assigning any to what it attacks (702.19b)")
        chosen = [str(n) for n in a.amounts]
    elif a.amounts:
        raise ActionError("Amounts only answer a division")
    elif card_names.is_free_text(d):
        pass
    elif len(set(chosen)) != len(chosen) or not set(chosen) <= valid:
        raise ActionError("Choose from the options offered")
    if d.kind == "reconcile":
        groups = {o.id: o.group for o in d.options}
        answered = [groups[c] for c in chosen]
        if len(set(answered)) != len(answered) or set(answered) != set(groups.values()):
            raise ActionError("Answer each question once")
    cancelling = chosen == ["cancel"] and cancelable(d)  # (-- cancelling a cast (wave 24D) --)
    if not cancelling and not d.min_choices <= len(chosen) <= d.max_choices:
        n = d.min_choices if d.min_choices == d.max_choices else f"{d.min_choices}–{d.max_choices}"
        raise ActionError(f"Choose {n}")
    if a.remember == "always_order":  # -- trigger order memory -- (an order prompt has no memory key: no yield answers it)
        triggers.remember_order(plan, d, chosen)
    elif a.remember is not None:
        if d.memory_key is None:
            raise ActionError("This answer can't be remembered")
        prefs = plan.prefs(decider_of(plan.state, d))  # (-- controlling another player (wave 18H) -- the decider's own preference)
        prefs.yields = [y for y in prefs.yields if y.key != d.memory_key][-49:]
        # A yes-or-no question remembers the answer given: "Same answer this turn" after a No is a No this turn, and "Always" keeps
        # whichever answer it was (603.5: each later "you may" of that ability is answered alike)
        answer = chosen[0] if len(chosen) == 1 and chosen[0] in ("yes", "no") else ""
        kind = ("no_this_turn" if answer == "no" else "yes_this_turn") if answer and a.remember in ("yes_this_turn", "no_this_turn") else a.remember
        prefs.yields.append(Yield(kind=kind, key=d.memory_key, context=d.memory_context,
                                  turn=plan.state.turn.number, answer=answer))
    effects.check_total_power(plan, d, chosen)  # -- per-player choices (wave 30K) -- "total power 4 or less" (Slaughter the Strong)
    plan.rules.decision = None
    step = (d.resume or {}).get("step")
    zero_modes = (d.resume or {}).get("zero_modes_object")
    plan.locked_zero_modes = zero_modes if isinstance(zero_modes, str) else None
    plan.cause110g = ((d.resume or {}).get("ctx") or {}).get("controller")  # -- wave 110G -- the answered effect's controller stamps its moves
    try:
        RESUME[str(step)](plan, d, chosen)
    finally:
        plan.cause110g = None
    if plan.rules.payment_outer is not None:  # -- nested payment choices (wave 28D) -- back to the payment the choice was nested in
        casting.resume_outer(plan)
    permissions.free_cast_abandoned(plan)  # -- free-cast cleanup (wave 30A) -- a cancelled free cast ends before play goes on: advance would resolve the
    # ability it belongs to (still on the stack, ripple) again from its start (-- review 30 -- after the payment a nested choice set aside is back)
    if step not in ("reconcile", "restore_global_word71"):  # Unknown layer-3 source restoration must complete before deriving reveals/SBAs.
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
    from app.rules import life_game_history

    watchers = life_game_history.loss_watchers(plan)  # 603.10f: looked back to before the concession's 800.4a departure
    r.conceded.append(plan.actor)
    if r.declaration_cost_reserved and r.declaration_cost_reserved.payer == plan.actor:
        r.declaration_cost_reserved = None
    plan.note(f"{plan.name(plan.actor)} conceded")
    casting.unnest(plan)  # (review 28D: a payment prompt a nested choice set aside is the decision settled)
    pending = r.decision
    leave_game(plan, plan.actor)
    life_game_history.loss_events(plan, [plan.actor], prior_leave=True, cohort=watchers)
    left = plan.live()
    if len(left) == 1:  # 104.2a: at once, overriding "can't win the game" (review of wave 10B)
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
    from app.rules import sticker_effects101

    if sticker_effects101.replaced_choice(plan, d):
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
        from app.rules import repeated_graveyard_offer89

        if repeated_graveyard_offer89.replaced_choice(plan, d):
            return
        # 800.4f-g: the choice isn't made; the resolution goes on — with the other players still to
        # choose in APNAP order ("each opponent discards a card"), then its next instruction
        plan.note(f"{plan.name(leaver)} left the game: their choice isn't made")
        if ("rest" in resume and "picked" in resume or resume.get("step") == "vote") and str(resume.get("step")) in RESUME:
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
    if step == "cmd_color110f":  # -- wave 110F -- a player left during the commander color question: the next question, or the opening hands
        opening_hand.start(plan)
        return
    if step in ("opening_hand", "opening_exile"):  # -- opening hand (wave 18C) -- the rest of the table still acts (103.6)
        opening_hand.ask(plan, list(resume.get("order") or resume.get("rest") or [])[1 if step == "opening_hand" else 0:])
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
                "auto_order_identical_triggers", "auto_target", "ask_graveyard_order", "hold_priority", "full_control", "force_stop")


def set_prefs(plan: Plan, a: A.SetPrefs) -> None:
    _require_seated(plan)
    prefs = plan.prefs(plan.actor)
    for key in SIMPLE_PREFS:
        value = getattr(a, key)
        if value is not None:
            setattr(prefs, key, list(value) if isinstance(value, list) else value)
    if a.cancel_pass:
        prefs.pass_until, prefs.pass_mark, prefs.stop_after, prefs.pass_hand = None, "", None, []
    if a.forget_trigger_orders:  # -- trigger order memory --
        prefs.trigger_orders = []
    elif a.forget_trigger_order is not None and a.forget_trigger_order < len(prefs.trigger_orders):
        del prefs.trigger_orders[a.forget_trigger_order]
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
    for y in plan.rules.prefs_for(controller_of(plan.state, player)).yields:  # (-- wave 18H -- 723.5)
        if y.key != key or (y.context and y.context != context):
            continue
        if y.kind == "always_yield":
            return y.answer or "yield"  # (the answer to a yes-or-no question; a yield to a priority stop has none)
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
    "unlock_door": rooms.unlock_action,
    "pay_deferred": deferred_payment82.pay,
    "end_effect": licids.end_effect,  # -- licids (wave 50A) -- 116.2c
    "roll_planar_die": planar_die.roll,  # -- planechase -- 901.9: the planar die, its {N} paid from the pool
    "miracle_reveal": miracle.reveal,  # -- casting extras (wave 18E) --
    "activate_ability": casting.activate_ability,
    "declare_attackers": combat.declare_attackers,
    "declare_blockers": combat.declare_blockers,
    "choose": choose,
    "concede": concede,
    "repeat_sequence": repeat_sequence,
}
from app.rules import reveal_mana as _reveal_mana  # noqa: E402, I001


RESUME: dict[str, Callable[[Plan, Decision, list[str]], None]] = {
    "manual_done": _resume_manual_done,
    "combat_damage": _resume_combat_damage,
    "block_split": _resume_block_split,
    "assign_unblocked": _resume_assign_unblocked,
    "cipher": recursion.resume_cipher,  # (wave 17C)
    "cleanup_manual": lambda plan, d, chosen: start_next_turn(plan),
    "untap_keep": untap_choice.resume,  # -- untap choice (wave 7F) --
    "untap_category89": untap_choice.resume_category89,
    "untap_limit": untap_choice.resume_limit,  # -- untap restrictions (wave 13E) --
    "sba_confirm": sba.resume_confirm,
    "regeneration_replacement": regeneration_choices.resume,
    "reconcile": reconcile.resume_reconcile,
    "payment": casting.resume_payment,
    "pay_mana": casting.resume_pay_mana,
    "x_allocation": casting.resume_x_allocation,
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
    "return_any": effects.resume_return_any,  # (wave 26C)
    "explore": effects.resume_explore,
    "explore_each": effects.resume_explore_each,  # (wave 50G)
    "aura_enters": attachments.resume_aura_enters,
    "battle_protector": battles.resume_protector,  # 310.11
    "siege_cast": battles.resume_siege_cast,  # 310.12b
    "sacrifice_choice": effects.resume_sacrifice_choice,
    "tap_choice": effects._this_way.resume_tap_choice,  # -- "this way" outcomes (wave 4A) --
    "untap_choice": effects._untap_riders.resume_untap_choice,  # -- mana riders (wave 5A) -- "Untap up to three lands."
    "pick_looked": effects.resume_pick_looked,
    "multiplayer_look": effects._multiplayer_look.resume,
    "kinship_look": kinship.resume_look,  # -- kinship (wave 9C) --
    "kinship_reveal": kinship.resume_reveal,
    "reveal_mana": _reveal_mana.resume,
    "reveal_mana_replace": _reveal_mana.resume_replace,
    "reveal_mana_type": _reveal_mana.resume_type,
    "reveal_mana_extra": _reveal_mana.resume_extra,
    "reveal_hand_cards": effects._reveal_hand.resume,  # -- if you do (wave 10C) --
    "reveal_some": effects._reveal_hand.resume_some,  # -- hand disruption (wave 52C) --
    "library_place": effects.resume_library_place,
    "counter_destination": counter_destinations.resume,
    "library_placements": library_placements.resume,
    "shuffle_library": effects.resume_shuffle_library,
    "cast_modes": casting.resume_cast_modes,
    "cast_slot_target": casting.resume_cast_slot_target,
    "phyrexian": casting.resume_phyrexian,  # -- phyrexian mana (wave 50B) --
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
    "piles_opponent": piles_legacy.resume_opponent,  # -- review 53 -- games saved before wave 53D
    "piles_split": piles_legacy.resume_split,
    "piles_pick": piles_legacy.resume_pick,
    "piles_down_opponent": looking.resume_down_opponent,  # -- hidden exile (wave 18A) --
    "piles_down_split": looking.resume_down_split,
    "piles_down_pick": looking.resume_down_pick,
    "order_triggers": triggers.resume_order,
    "trigger_target": triggers.resume_target,
    "trigger_opp110d": triggers.resume_opponent,
    "trigger_confirm": triggers.resume_confirm,
    "cast_target": casting.resume_target,
    "payment_sources": casting.resume_payment_sources,
    "cleanup_discard": _resume_cleanup_discard,
    "mana_ability": casting.resume_mana_ability,
    "tap_for_mana": tap_gesture.resume,  # -- playtest fixes (nov 5) --
    "crew": casting.resume_crew,
    "ability_cost": cost_payment.resume_choice,
    "declaration_cost_order": nonmana_combat_costs.resume_order,
    "cost_moves": cost_moves.resume,
    "opening_hand": opening_hand.resume,  # -- opening hand (wave 18C) -- 103.6
    "opening_exile": opening_hand.resume_exile,
    "clara110e": wave110f_cmd.resume_old,  # -- pregame color (wave 110E): saved Clara Oswald questions
    "spires110g": wave110g_spires.resume,  # -- wave 110G --
    "exert_attackers": exert.resume,  # -- static wordings (wave 6E) -- 508.1g
    "enlist": enlist.resume,  # -- casting extras (wave 18E) -- 702.154a
    "assist": assist.resume,  # -- casting extras (wave 18E) -- 702.132a
    "pick110e": wave110e_opp.resume,  # -- cast-time choice (wave 110E)
    "camo110f": wave110f_camo.resume,  # -- Camouflage (wave 110F)
    "giant110f": wave110f_cards.resume_giant,  # -- combat damage division (wave 110F)
    "gift": gift.resume,  # -- gift (wave 23D) -- 702.174a
    "free_multikicker": casting.resume_free_multikicker,
    "free_chorus": casting.resume_free_chorus,  # -- Chorus of the Conclave (wave 110C) --
    "free_replicate111r3": wave111r3_replicate.resume_free_count,  # -- granted replicate (wave 111R3) -- a typed count, on a free cast
    "attack111r3": wave111r3_enter.resume,  # -- enters attacking (wave 111R3) -- 508.4, asked right after it entered
    "free_optional": casting.resume_free_optional,  # -- free-cast optional costs (wave 41D) -- 118.9d, 601.2b
    "casualty_x": casting.resume_casualty_x,
    "flashback_choice": casting.resume_flashback_choice,
    "spell_symbols": casting.resume_spell_symbols,
    "free_x": casting.resume_free_x,
    "paid_x_number": casting.resume_paid_x_number,  # -- cast keywords (wave 43D) -- 107.3a: the X of a kicker or miracle cost paid on a free cast
    "slot": permissions.resume_slot,  # -- cast permissions (wave 30Q) -- Muldrotha: which permanent type a cast uses up
    "legend_rule": sba.resume_legend_rule,
    "graveyard_order": graveyard_order.resume,  # -- graveyard order (wave 40C) -- 404.3
    "commander_zone": sba.resume_commander_zone,
    **effects.keyword_actions.RESUME,  # amass / bolster choices, tokens entering attacking (app/rules/keyword_actions.py)
    **effects.RESUME,  # player choices: edicts, "chooses a", a revealed hand, "choose a color" (app/rules/effects.py)
    # replacement / prevention effects (app/rules/replacements.py): a shock land put onto the
    # battlefield by an effect, 903.9b before a commander is returned to a hand, 615.7 shields
    "enter_choice": replacements.resume_entry_choice,
    "stack_enter_choice": replacements.resume_stack_enter_choice,
    "land_enter_choice": replacements.resume_land_enter_choice,
    "commander_instead": replacements.resume_commander_instead,
    "mutate_choice": merged.resume_choice,  # -- merged permanents (wave 18D) --
    "commander_first": replacements.resume_commander_first,  # 903.9b asked before the move
    "shield_order": replacements.resume_shield_order,
    "zone_replace_order": replacements.resume_616,  # -- zone replacements (wave 22C) --
    # -- replacement effects stage 2 (wave 2E): which of several replacement / prevention effects
    # applies first (616.1), then the paused site runs again (app/rules/replace.py) --
    "replace_order": effects.replace.resume_order,
    # -- copy system (wave 2F): copies of spells and abilities — same or new targets for several
    # copies, one copy's targets (707.10c), a copy made by hand (app/rules/copying.py) --
    **copying.RESUME,
    **effects._hand_library_exchange.RESUME,
}
# (the draw step, once its draw is done after a 616.1 choice: its "at the beginning of" triggers)
effects.replace.THEN["draw_step"] = lambda plan, then: triggers.at_step_generic(plan)

from app.rules import delegated_target_announcements as _delegated_target_announcements  # noqa: E402

RESUME.update(_delegated_target_announcements.RESUME)
from app.rules import wave110d_volc as _wave110d_volc  # noqa: E402

RESUME.update(_wave110d_volc.RESUME)

from app.rules import numeric_roll_finalization42 as _numeric_roll_finalization42  # noqa: E402, I001

RESUME.update(_numeric_roll_finalization42.RESUME)

from app.rules import prevention_frontier_bridge as _joint_prevention  # noqa: E402, I001

RESUME.update(_joint_prevention.RESUME)

from app.rules import combat_player_scope43 as _combat_player_scope43  # noqa: E402, I001

RESUME.update(_combat_player_scope43.RESUME)

from app.rules import prevention_frontier_cards as _joint_prevention_cards  # noqa: E402, I001

RESUME.update(_joint_prevention_cards.RESUME)

from app.rules import fixed_top_graveyard_cost46 as _fixed_top_graveyard_cost46  # noqa: E402

RESUME["fixed_top_cost_order46"] = _fixed_top_graveyard_cost46.resume_order

from app.rules import chosen_color_pairs45 as _chosen_color_pairs45  # noqa: E402

RESUME.update(_chosen_color_pairs45.RESUME)


from app.rules import first_event_receipts78 as _first_event78  # noqa: E402

RESUME['first_event_legacy_done78'] = _first_event78.legacy_done

from app.rules import echo_alternatives76 as _echo76  # noqa: E402

RESUME['echo_alternative76'] = _echo76.resume

RESUME['echo_draw_count76'] = _echo76.resume_draw

from app.rules import chosen_forms95 as _chosen_forms95  # noqa: E402

RESUME.update(_chosen_forms95.RESUME)

from app.rules import zone_exchanges94 as _zone_exchanges94  # noqa: E402

RESUME.update(_zone_exchanges94.RESUME)

RESUME['graveyard_order_page94'] = graveyard_order.resume_page

from app.rules import modal_clauses101 as _modal101  # noqa: E402

RESUME.update(_modal101.RESUME)

from app.rules import combat_damage95 as _combat_damage95  # noqa: E402

RESUME.update(_combat_damage95.RESUME)

from app.rules import stickers101 as _stickers101  # noqa: E402

RESUME.update(_stickers101.RESUME)

from app.rules import sticker_effects101 as _sticker_effects101  # noqa: E402

RESUME.update(_sticker_effects101.RESUME)

from app.rules import vampire_returns105 as _vampire_returns105  # noqa: E402, I001
RESUME.update(_vampire_returns105.RESUME)

from app.rules import wave110c_lose as _wave110c_lose  # noqa: E402, I001
RESUME.update(_wave110c_lose.RESUME)  # -- lose replacements (wave 110C) --
