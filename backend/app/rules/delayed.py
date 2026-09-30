"""Delayed triggered abilities (CR 603.7) and effect durations (611.2), researched against CR 2026-09-25.

**Delayed triggers.** A resolving spell or ability may say "at the beginning of the next end step,
exile it" or "when that creature dies this turn, return it to the battlefield". The grammar turns
that into a ``delayed`` effect followed by the ``n`` effects it defers (app/rules/scripts.py, the
appended block; the wording helpers are at the bottom of this module). As the creating spell or
ability resolves (603.7a), the ``delayed`` primitive captures everything the deferred effects
will need into a ``DelayedTrigger`` (app/game/rules_state.py): the objects they name as
ObjectRefs — the target as chosen, "it" of an earlier instruction, the source — bound now
(603.7c: it still affects them whatever their characteristics become, but not if they have left
the zone they're expected in; an object that left and came back is a new object, 400.7), the
controller and source as they were (603.7d-e), the resolution bindings so far and the creating
trigger's event. It is JSON in ``RulesState.delayed``, so it survives saves, undo/redo and replay.

When its event happens — a step begins (500.6), or a watched object dies / leaves the battlefield
(603.6c, 603.10a) — it triggers like any other triggered ability: a PendingTrigger that the
trigger collector puts on the stack in APNAP order with the others (603.3b), resolved with its
own context (``bind_refs`` restores the bindings; "it" is read through app/rules/context.py,
never by rescanning the table). It triggers once (603.7b): "when that creature dies this turn"
triggers only for the object it was bound to, not for the new object it becomes if it returns
(603.7c / 400.7); "this turn" ones stop watching at cleanup (514.2). A watched object that has
already left when the trigger would be created never triggers it (603.7a).

**Durations.** "Until end of turn" effects end at cleanup (514.2, app/rules/layers.py). "Until
your next turn" ends as that player's next turn begins (500.4; ``turn_began``). "For as long as ~
remains on the battlefield / you control ~ / ~ remains tapped" (611.2b) ends the moment that stops
being true (``expire``, checked after every table change); if it isn't true as the effect would
begin, the effect does nothing at all. "For as long as that creature has a bounty counter on it"
(``while_counter``, quoted grants: app/rules/granted.py) is the same for each object it affects:
one that has no such counter any more drops out, and the effect ends with the last. A duration
doesn't change what an effect applies to: a characteristic-changing effect stays locked to the
objects it began on (611.2c), so a "this turn" pump keeps going when the creature changes controllers.

Not modelled here (the wording stays manual, never guessed): "whenever … this turn" (an "each"
duration), "when you next cast … this turn, copy that spell", conditions on the deferred effect
("… if it didn't attack this turn"), several watched objects ("when a creature dealt damage this
way dies"), and linked leaves-the-battlefield abilities of a *second* ability line (607).
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DelayedTrigger, ObjectRef, TriggerEvent
from app.game.state import PHASES

if TYPE_CHECKING:
    from app.game.rules_state import ContinuousEffect, Event
    from app.rules.plan import Plan

Context = dict[str, Any]

# -- the wording of when a delayed trigger triggers ---------------------------------------------
WHEN = {
    "the next end step": {"kind": "step", "step": "end", "whose": "next"},
    "your next end step": {"kind": "step", "step": "end", "whose": "you"},
    "the next turn's upkeep": {"kind": "step", "step": "upkeep", "whose": "next_turn"},
    "the next upkeep": {"kind": "step", "step": "upkeep", "whose": "next_turn"},
    "your next upkeep": {"kind": "step", "step": "upkeep", "whose": "you"},
}
WHEN_RE = "|".join(re.escape(k) for k in sorted(WHEN, key=len, reverse=True))
# "when that creature dies / leaves the battlefield this turn": the object an earlier part named
EVENT_SUBJECTS = ("it", "that creature", "that permanent", "that token", "that card", "~", "this creature",
                  "target creature", "target permanent")
EVENT_VERBS = {"dies": "die", "leaves the battlefield": "leave", "is put into a graveyard": "die"}
EVENT_RE = "|".join(re.escape(k) for k in sorted(EVENT_VERBS, key=len, reverse=True))

# -- the wording of durations --------------------------------------------------------------------
# text → (duration, what replaces it so the ordinary "until end of turn" grammar reads the clause)
DURATIONS: dict[str, str] = {
    "until your next turn": "next_turn",
    "for as long as ~ remains on the battlefield": "source_on_battlefield",
    "for as long as you control ~": "source_controlled",
    "for as long as ~ remains tapped": "source_tapped",
}
# -- quoted grants (wave 2D) -- "for as long as that creature has a bounty counter on it" (Mathas): the
# duration names a kind of counter ("while_counter:<kind>"): the effect lasts while the object it affects
# has one (611.2b), and does nothing if it has none as the effect would begin
COUNTER_DURATION = r"for as long as (?:that \w+|it|~) has an? (?P<kind>[\w+/-]+) counters? on it"
DURATION_RE = "|".join([*(re.escape(k) for k in sorted(DURATIONS, key=len, reverse=True)), COUNTER_DURATION])
LABELS = {"next_turn": "until your next turn", "source_on_battlefield": "for as long as ~ remains on the battlefield",
          "source_controlled": "for as long as you control ~", "source_tapped": "for as long as ~ remains tapped",
          "while_counter": "for as long as it has a counter on it"}
MARKER = "until end of turn"  # the table marker text app/rules/effects._mark writes


def wrap_when(effects: list[dict[str, Any]], when: dict[str, Any], *, who: str | None = None,
              this_turn: bool = False) -> list[dict[str, Any]]:
    """The ``delayed`` effect and the ``n`` effects it defers, as one flat list (so the pronoun
    resolver and the target-group bookkeeping see the deferred effects like any others)."""
    head: dict[str, Any] = {"do": "delayed", "when": dict(when), "n": len(effects)}
    if who is not None:
        head["who"] = who
    if this_turn:
        head["this_turn"] = True
    # (marked as deferred: a later sentence's "that creature" must not bind to what the deferred
    # exile will record — it hasn't happened when the creating ability resolves)
    return [head, *({**e, "do": DEFERRED + e["do"]} for e in effects)]


DEFERRED = "deferred:"


_MOVES = {"bounce", "return_card", "exile", "destroy", "sacrifice"}


def inner_for_event(effects: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """The deferred effects of "when that creature dies this turn, …": "it" / "that card" there is
    the object the event happened to — the new object where it went for a move ("return it to the
    battlefield": 400.7e, 603.6c), the object as it last existed otherwise (603.10a) — never an
    earlier target. Anything that still needs an antecedent stays manual (None)."""
    out = []
    for e in effects:
        e = dict(e)
        who = e.get("who")
        if who in ("it", "them"):
            e["who"] = "event.new" if e.get("do") in _MOVES else "event"
        elif who in ("it.controller", "it.owner"):
            e["who"] = f"ref:event.{who[3:]}"
        elif who == "that_player" or (isinstance(who, str) and who.startswith(("it:", "them:"))):
            return None
        n = e.get("n")
        if isinstance(n, dict) and any(n.get(k) == "it" for k in ("power", "toughness", "mana_value")):
            e["n"] = {k: ("event" if v == "it" else v) for k, v in n.items()}
        if e.get("src") == "it":
            return None
        out.append(e)
    return out


# -- creating one (as the spell or ability resolves, 603.7a) --------------------------------------
_BIND_NOW = ("target", "self", "host")  # who-values that mean "this object, as it is now" (603.7c)


def _bind_now(plan: Plan, ctx: Context, effects: list[dict[str, Any]], refs: dict[str, Any]) -> list[dict[str, Any]]:
    """The deferred effects with every reference to a particular object turned into a binding of
    the object as it is now: the target as chosen, the source, what the source is attached to.
    Selectors ("each creature you control") stay: they're read when the ability resolves."""
    from app.rules import context
    from app.rules.effects import _cards

    out = []
    for k, e in enumerate(effects):
        e = dict(e)
        who = e.get("who")
        if isinstance(who, str) and (who in _BIND_NOW or who.startswith("target:")):
            name = f"d{len(refs)}_{k}"
            context.bind_objects(plan, {"refs": refs}, name, _cards(plan, ctx, who))
            e["who"] = f"ref:{name}"
        out.append(e)
    return out


def create(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The ``delayed`` primitive: capture the next ``n`` effects of this resolution as a delayed
    triggered ability (603.7a) and skip them now."""
    n = int(e.get("n", 0))
    start = ctx["next"]
    deferred = [{**x, "do": x["do"].removeprefix(DEFERRED)} for x in ctx["effects"][start:start + n]]
    ctx["next"] = start + n
    refs = {k: v for k, v in (ctx.get("refs") or {}).items()}
    when = dict(e["when"])
    if when["kind"] == "event":
        from app.rules import context
        from app.rules.effects import _cards

        watched = _cards(plan, ctx, e["who"])
        watched = [c for c in watched if plan.state.cards[c].zone.endswith(":battlefield")]
        if not watched:  # 603.7a: it already left — the event can't happen to that object
            plan.note(f"{ctx.get('name') or 'The ability'}: nothing to watch (it already left)")
            return True
        context.bind_objects(plan, {"refs": refs}, "watch", watched)
    turn = plan.state.turn.number
    trigger = DelayedTrigger(
        id=secrets.token_hex(4), controller=ctx["controller"], source_card=ctx.get("source_card"),
        source_object=ctx.get("source_object"), name=ctx.get("name") or "", when=when,
        effects=_bind_now(plan, ctx, deferred, refs), refs=refs, event=ctx.get("event"), turn=turn,
        step=plan.state.turn.phase, until_turn=turn if e.get("this_turn") else None)
    plan.rules.delayed.append(trigger)
    plan.note(f"{trigger.name or 'A delayed ability'} will trigger {describe_when(when)}")
    return True


def create_move(plan: Plan, controller: str, card_id: str, oid: str, to: str, name: str) -> None:
    """Unearth (702.84a) / dash (702.109a): "at the beginning of the next end step, exile it /
    return it to its owner's hand" — the object as it is now (603.7c)."""
    plan.rules.delayed.append(DelayedTrigger(
        id=secrets.token_hex(4), controller=controller, source_card=card_id, source_object=oid, name=name,
        when={"kind": "step", "step": "end", "whose": "next"},
        effects=[{"do": "delayed_move", "card": card_id, "object": oid, "to": to}],
        turn=plan.state.turn.number, step=plan.state.turn.phase))


def describe_when(when: dict[str, Any]) -> str:
    if when["kind"] == "event":
        return "when it " + ("dies" if when["event"] == "die" else "leaves the battlefield") + " this turn"
    whose = {"next": "the next", "you": "your next", "next_turn": "the next turn's"}[when["whose"]]
    return f"at the beginning of {whose} {'end step' if when['step'] == 'end' else 'upkeep'}"


# -- triggering (603.2) and going on the stack with the other triggers (603.3b) --------------------
def _fire(plan: Plan, t: DelayedTrigger, event: TriggerEvent | None) -> None:
    from app.rules.triggers import _add

    if t.controller not in plan.live():
        return
    definition = {"kind": "triggered", "trigger": "delayed", "optional": False, "target": None,
                  "effects": [{"do": "bind_refs", "refs": t.refs}, *t.effects]}
    _add(plan, controller=t.controller, source_card=t.source_card or "", source_object=t.source_object or "",
         name=t.name, index=7000, definition=definition, event=event)


def _step_due(plan: Plan, t: DelayedTrigger, phase: str) -> bool:
    w = t.when
    if w.get("kind") != "step" or w.get("step") != phase:
        return False
    turn = plan.state.turn.number
    later_turn = turn > t.turn
    created_at = PHASES.index(t.step) if t.step in PHASES else -1
    same_turn_before = turn == t.turn and created_at < PHASES.index(phase)
    whose = w.get("whose")
    if whose == "next":  # the next such step to begin, this turn's if it hasn't yet (500.6)
        return later_turn or same_turn_before
    if whose == "you":
        return plan.active == t.controller and (later_turn or same_turn_before)
    return later_turn  # "the next turn's upkeep"


def at_step(plan: Plan, phase: str) -> None:
    """A step began: delayed triggers waiting for it trigger (500.6, 603.7). They join the
    other step triggers in ``pending_triggers`` and go on the stack in APNAP order (603.3b)."""
    r = plan.rules
    due = [t for t in r.delayed if _step_due(plan, t, phase)]
    if not due:
        return
    r.delayed = [t for t in r.delayed if t not in due or not t.once]
    for t in due:
        event = TriggerEvent.model_validate(t.event) if t.event else None
        _fire(plan, t, event)


def on_events(plan: Plan, events: list[Event]) -> None:
    """The watched object died / left the battlefield (603.6c; 603.10a: the object as it last
    existed, and what it became where it went, 400.7e)."""
    from app.rules.triggers import _new_ref, _zone

    r = plan.rules
    watching = [t for t in r.delayed if t.when.get("kind") == "event"]
    if not watching:
        return
    fired: list[DelayedTrigger] = []
    for e in events:
        if e.kind != "zone_change" or e.manual or _zone(e.from_zone) != "battlefield" or _zone(e.to_zone) == "battlefield":
            continue
        snap = r.lki.get(e.object_id or "")
        if snap is None:
            continue
        died = _zone(e.to_zone) == "graveyard" or (e.to_zone is None and snap.is_token)
        for t in watching:
            if t in fired:
                continue
            oids = {o["object_id"] for o in (t.refs.get("watch") or {}).get("objects") or []}
            if e.object_id not in oids or (t.when["event"] == "die" and not died):
                continue
            kind = "die" if t.when["event"] == "die" else "leave"
            event = TriggerEvent(kind=kind, batch=e.batch, count=1,
                                 objects=[ObjectRef(card=snap.card, object_id=snap.object_id, zone=snap.zone, snapshot=snap)],
                                 new_objects=_new_ref(snap.card, e.new_object_id, e.to_zone))
            fired.append(t)
            _fire(plan, t, event)
    if fired:
        r.delayed = [t for t in r.delayed if t not in fired or not t.once]


def cleanup(plan: Plan) -> None:
    """514.2: "this turn" delayed triggers stop watching."""
    turn = plan.state.turn.number
    plan.rules.delayed = [t for t in plan.rules.delayed if t.until_turn is None or t.until_turn > turn]


# -- durations (611.2) -------------------------------------------------------------------------------
def apply_duration(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The ``until`` primitive: carry out the next ``n`` effects, then give the continuous effects
    they created this duration instead of "until end of turn". If a "for as long as" duration
    isn't true as the effects would begin, they do nothing (611.2b)."""
    from app.rules.effects import PRIMITIVES

    n = int(e.get("n", 0))
    start = ctx["next"]
    inner = list(ctx["effects"][start:start + n])
    ctx["next"] = start + n
    duration = e["duration"]
    counter = None
    if duration.startswith("while_counter:"):  # (quoted grants, wave 2D)
        duration, counter = "while_counter", duration.split(":", 1)[1]
    if duration.startswith("source_") and not _source_ok(plan, duration, ctx.get("source_card"), ctx.get("source_object"),
                                                          ctx["controller"]):
        plan.note(f"{ctx.get('name') or 'The effect'} does nothing: its duration has already ended")
        return True
    r = plan.rules
    mark = r.timestamp
    before = {cid: {m.id for m in c.effects} for cid, c in plan.state.cards.items()}
    for x in inner:
        if not PRIMITIVES[x["do"]](plan, ctx, x):
            raise AssertionError("a duration wraps only effects that never pause")  # (the grammar only wraps pumps and grants)
    label = LABELS[duration].replace("~", ctx.get("name") or "it")
    if counter:
        label = f"for as long as it has a {counter} counter on it"
    written = _relabel(plan, before, label)
    for effect in r.effects:
        if effect.timestamp > mark:
            effect.duration = duration
            effect.until_player = ctx["controller"]
            effect.turn = plan.state.turn.number
            if counter:
                effect.counter = counter
            if duration.startswith("source_"):
                effect.source = ctx.get("source_object")
                effect.source_card = ctx.get("source_card")
            # each effect of the clause ("gets +2/+2 and gains flying") owns the markers on the
            # objects it affects; ``_end`` keeps a marker another effect still owns
            effect.markers = [m for cid, ids in written.items() if plan.oid(cid) in effect.affected for m in ids]
    if counter:
        expire(plan)  # 611.2b: a counter the objects don't have as the effect begins — it does nothing
    return True


def _relabel(plan: Plan, before: dict[str, set[str]], label: str) -> dict[str, list[str]]:
    """The table markers the clause's effects just wrote say "until end of turn": say the real
    duration. Returns the new markers' ids by card (the effects remember them: ``_end``)."""
    written: dict[str, list[str]] = {}
    for cid, card in plan.state.cards.items():
        for m in [m for m in card.effects if m.id not in before.get(cid, set()) and m.text == MARKER]:
            plan.do({"type": "remove_effect", "card_ids": [cid], "effect_id": m.id})
            added = plan.do({"type": "add_effect", "card_ids": [cid], "name": m.name, "value": m.value, "text": label[:200]})
            written.setdefault(cid, []).extend(marker_ids(added))
    return written


def _source_ok(plan: Plan, duration: str, source_card: str | None, source_object: str | None, controller: str | None) -> bool:
    card = plan.state.cards.get(source_card or "")
    if card is None or not card.zone.endswith(":battlefield") or plan.oid(card) != source_object:
        return False
    if not plan.in_game(card):
        return False  # 800.4a: its owner (or controller) left the game, and it left with them
    if duration == "source_controlled":
        return card.controller == controller
    if duration == "source_tapped":
        return card.tapped
    return True


def marker_ids(action: Any) -> list[str]:
    """The ids of the table markers an ``add_effect`` action just wrote."""
    return list(getattr(getattr(action, "r", None), "ids", None) or [])


def _end(plan: Plan, ended: list[ContinuousEffect]) -> None:
    """The effects end, and with them the table markers they wrote (keyed by the effect: another
    effect's marker with the same wording on the same creature stays)."""
    r = plan.rules
    ids = {e.id for e in ended}
    r.effects = [e for e in r.effects if e.id not in ids]
    still = {m for e in r.effects for m in e.markers or ()}  # (one marker can stand for several effects)
    for effect in ended:
        label = LABELS.get(effect.duration, "")
        if effect.markers is None and not label:
            continue
        for cid, card in plan.state.cards.items():
            if effect.markers is not None:
                gone = [m for m in card.effects if m.id in effect.markers and m.id not in still]
            elif plan.oid(card) in effect.affected:  # (an effect saved before effects remembered their markers)
                gone = [m for m in card.effects if m.text and m.text.startswith(label.split("~")[0].strip())
                        and m.text != MARKER and m.id not in still]
            else:
                continue
            for m in gone:
                plan.do({"type": "remove_effect", "card_ids": [cid], "effect_id": m.id})


def turn_began(plan: Plan, skipped: list[tuple[str, int]] | None = None) -> None:
    """500.4: as a player's turn begins, effects lasting "until [their] next turn" end. 800.4m:
    for a player who left the game, they end when that turn would have begun (``skipped``: the
    seats of departed players passed on the way here, with the turn number each would have had)."""
    r = plan.rules
    turn, active = plan.state.turn.number, plan.active
    ended = [e for e in r.effects if e.duration == "next_turn" and (
        (e.until_player == active and turn > e.turn)
        or any(e.until_player == p and n > e.turn for p, n in skipped or ()))]
    if ended:
        _end(plan, ended)


def expire(plan: Plan) -> None:
    """611.2b: "for as long as …" effects end as soon as it stops being true (checked after every
    table change: the source left, changed controller or untapped)."""
    r = plan.rules
    ended = [e for e in r.effects if e.duration.startswith("source_")
             and not _source_ok(plan, e.duration, e.source_card, e.source, e.until_player)]
    for e in r.effects:  # -- quoted grants (wave 2D) -- "for as long as it has a … counter on it": per object
        if e.duration == "while_counter":
            kept = [oid for oid in e.affected if _has_counter(plan, oid, e.counter or "")]
            if not kept:
                ended.append(e)
            elif len(kept) < len(e.affected):
                _drop(plan, e, kept)
    if ended:
        _end(plan, ended)


def _has_counter(plan: Plan, oid: str, kind: str) -> bool:
    card = next((c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.oid(c) == oid), None)
    return card is not None and card.counters.get(kind, 0) > 0


def _drop(plan: Plan, effect: ContinuousEffect, kept: list[str]) -> None:
    """Objects that no longer have the counter leave the effect (and its table markers)."""
    gone = set(effect.affected) - set(kept)
    effect.affected = kept
    for card in plan.state.cards.values():
        if plan.oid(card) in gone:
            for m in [m for m in card.effects if m.id in (effect.markers or ())]:
                plan.do({"type": "remove_effect", "card_ids": [card.id], "effect_id": m.id})


def bind_refs(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The first effect of a delayed trigger's resolution: its bindings, as captured (603.7c)."""
    ctx["refs"] = {k: v for k, v in (e.get("refs") or {}).items()}
    return True


# -- wording -----------------------------------------------------------------------------------------
LEADING = re.compile(rf"^at the beginning of (?P<when>{WHEN_RE}), (?P<clause>.+)$")
TRAILING = re.compile(rf"^(?P<clause>.+?) at the beginning of (?P<when>{WHEN_RE})$")
EVENT = re.compile(rf"^when (?P<subject>{'|'.join(re.escape(s) for s in EVENT_SUBJECTS)}) (?P<verb>{EVENT_RE}) this turn, "
                   r"(?P<clause>.+)$")
UNTIL_LEADING = re.compile(rf"^(?P<duration>{DURATION_RE}), (?P<clause>.+)$")
UNTIL_TRAILING = re.compile(rf"^(?P<clause>.+?) (?P<duration>{DURATION_RE})$")
_EOT = re.compile(r"^(?P<clause>.+?)(?: until end of turn)$")
_RESTRICT = re.compile(r"^(?P<o>.+?) can't (?P<r>attack or block|block|attack|be blocked)$")


def duration_clause(m: re.Match[str]) -> tuple[str, str]:
    """(the clause as the ordinary grammar reads it — with "until end of turn" / "this turn"
    — the duration): "it gains haste until your next turn" → "it gains haste until end of turn"."""
    kind = m.groupdict().get("kind")
    clause, duration = m["clause"].strip(), (f"while_counter:{kind}" if kind else DURATIONS[m["duration"]])
    if _RESTRICT.fullmatch(clause):
        return clause + " this turn", duration
    return clause + " until end of turn", duration


def wrap_duration(effects: list[dict[str, Any]], duration: str) -> list[dict[str, Any]] | None:
    """The ``until`` effect over the continuous effects of a clause; only pumps, grants and
    restrictions (they never pause, and their effects carry a duration)."""
    if not effects or any(e.get("do") not in ("pump", "grant", "restrict") for e in effects):
        return None
    return [{"do": "until", "duration": duration, "n": len(effects)}, *effects]


def event_when(m: re.Match[str]) -> tuple[dict[str, Any], str]:
    """("when that creature dies this turn" → its trigger, the subject as a who-placeholder for
    scripts.resolve_it: "it" for a pronoun, "self" for ~, "target" for a target)."""
    subject = m["subject"]
    when = {"kind": "event", "event": EVENT_VERBS[m["verb"]]}
    if subject in ("~", "this creature"):
        return when, "self"
    if subject.startswith("target "):
        return when, "target"
    return when, "it"
