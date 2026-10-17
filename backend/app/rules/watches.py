"""-- turn watches (wave 7D) -- "Whenever [event] this turn, [effect]" and "When you next cast [spell] this turn,
[effect]": a delayed triggered ability whose trigger event is an ordinary one (CR 603.7, 603.7c). Researched against the
Comprehensive Rules of 2026-09-25.

* 603.7: a resolving spell or ability creates the delayed triggered ability; "whenever" ones trigger every time the event
  happens until the turn ends (cleanup, 514.2; "this turn" is the duration, 611.2a), "when you next cast" ones trigger
  once, for the first matching spell cast after it was created (603.7b).
* The event is a generic trigger condition (app/rules/events.py): what happened after the watch was created, matched
  with the same code the permanents' triggers use (app/rules/triggers.py), against the objects as they were then
  (603.10a). Events of the creating resolution that happened before the watch existed never trigger it (603.7a).
* The watch is the creating ability's: its controller and source are fixed as it was created (603.7d-e). "You" is its
  controller; "another" is relative to its source.
* "that spell" / "that creature" / "that much" / "that player" read what the watch triggered on (603.7c, 608.2k).
* A watch on one object (wave 33A): "Whenever that creature / target creature you control / ~ deals combat damage to a player
  this turn" is bound as it is created to the rules object it names (603.7c: the target as chosen, or the source); a new object
  (it left and came back, 400.7) is not it, so the watch no longer matches. Only damage-to-player, attack and block events.
  "Until end of turn, whenever …" / "This turn, whenever …" lead with the same duration (611.2a).
* Dies / leaves-the-battlefield watches (wave 35B, below ``bound_sentence``): "When the creature an opponent controls dies this turn, …" and
  "Whenever a creature dealt damage this way dies this turn, …" are delayed triggers of app/rules/delayed.py (kind "event"), read as they
  are created from the spell's targets or from the objects its one damage instruction was actually dealt to (603.7c, 603.10a, 700.4).
* Refused (the sentence stays manual): a watch on what its source is attached to, "one or more …" and damage events that join
  several recipients, a target of the deferred ability (chosen as it triggers: not modelled), a watch with its own delayed
  trigger or duration inside.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from app.rules import delayed

if TYPE_CHECKING:
    from app.rules.plan import Plan

_OBJECT_SUBJECTS = {"player", "sel"}  # (not "self", "host": a watch has no object of its own to look at)
_NEXT_CAST_KEYS = {"event", "subject", "player", "spell"}
_BOUND_EVENTS = {"deal_damage", "deal_combat_damage_player", "attack", "block", "blocked"}
_ONE_OR_MORE = {"deal_damage", "deal_combat_damage_player"}  # (wave 33A: "one or more creatures you control deal combat damage to a player")


def cond_ok(cond: dict[str, Any] | None, bound: str | None = None) -> bool:
    """Is this condition one a turn watch can read: an event about players or objects matching a selector, one fact at a
    time (a "one or more" / several-recipients damage event joins facts: not modelled). ``bound``: the watch is on one
    object (its source or a target, wave 33A), whose events are the damage, attack and block ones only."""
    if cond is None or cond.get("subject") not in _OBJECT_SUBJECTS | ({"self"} if bound == "self" else set()) \
            or (cond.get("aggregate") and (bound or cond["event"] not in _ONE_OR_MORE)) or cond.get("while") \
            or (bound and cond["event"] not in _BOUND_EVENTS):
        return False
    if cond["event"] in ("multi", "either", "dealt_damage", "you_attack", "unblocked") or cond.get("copy"):
        return False
    return not (cond["event"] == "deal_damage" and cond.get("to", "any") == "any")


def refs_ok(cond: dict[str, Any], effects: list[dict[str, Any]]) -> bool:
    """What the deferred effects name of the event (a spell, a player, an amount, an object) must be there."""
    from app.rules import scripts

    text = json.dumps(effects)
    if any(e.get("who") == "event_spell" for e in effects) and not (cond["event"] == "cast" and cond["subject"] == "player"):
        return False
    wants_player = any(e.get("who") in ("event_player", "each_other_opponent") for e in effects)
    wants_amount = any(scripts._wants_amount(e.get(k)) for e in effects for k in ("n", "p", "t", "mv"))
    if wants_player and not scripts._has_player(cond):
        return False
    if wants_amount and (cond["event"] not in scripts._AMOUNT_EVENTS or cond["event"] == "attack"):
        return False
    # -- turn-long triggers (wave 33A) -- "one or more …" is one trigger for the whole batch (603.2c): no one amount, object or (of
    # several players) player of it; "it" that moved (destroy / return / exile it) needs an event that moved it
    if cond.get("aggregate") and (wants_amount or re.search(r'"(?:ref:)?event(?:\.\w+)?"', text) or (wants_player and cond.get("to") == "players")):
        return False
    if re.search(r'"(?:ref:)?event\.new', text) and cond["event"] not in ("die", "leave", "enter"):
        return False
    # (the object the event happened to: only an event about objects has one)
    return not (re.search(r'"(?:ref:)?event(?:\.\w+)?"', text) and cond["subject"] != "sel")


def build(cond: dict[str, Any] | None, clause: str, *, once: bool, text: str, bound: str | None = None, next_turn: bool = False,
          ) -> tuple[list[dict[str, Any]], Any] | None:
    """The ``delayed`` effect and its deferred effects for "[whenever / when you next …] this turn, <clause>"."""
    from app.rules import scripts

    if not cond_ok(cond, bound) or cond is None:
        return None
    from app.rules import (
        cast_riders,  # -- cast riders (wave 25C) -- "…, that creature enters with an additional +1/+1 counter on it"
    )

    inner = cast_riders.parse(cond, clause) or scripts._clause(clause)
    if inner is None:
        return None
    own_target = None
    if inner[1] is not None:  # -- if you do (wave 25C) -- the deferred ability's own target: chosen each time it triggers (603.3d)
        own_target = scripts.target_fields(inner[1]).get("target")
        if not (isinstance(own_target, dict) and set(own_target) == {"what"}):
            return None
    # (-- turn-long triggers (wave 33A) -- "that player" is the player the event was about: who was dealt the damage, 603.7c)
    effects = delayed.inner_for_event([{**e, "who": "event_player"} if e.get("who") == "that_player" else e for e in inner[0]])
    if effects is None or any(e.get("do") in delayed.UNDEFERRABLE for e in effects) \
            or not refs_ok(cond, effects):
        return None
    if own_target is not None:
        effects = delayed.mark_target(effects)  # ("target" is the deferred ability's own, not one of the creating ability's groups)
    head = {"kind": "watch", "cond": cond, "text": text, **({"bound": True} if bound else {})}
    wrapped = delayed.wrap_when(effects, head, who=bound, this_turn=not next_turn, next_turn=next_turn)  # (wave 50G: "Until your next turn, whenever …", 500.4)
    wrapped[0]["once"] = once
    if own_target is not None:
        wrapped[0]["target"] = own_target
    return wrapped, None


# -- turn-long triggers (wave 33A) -- the wording of a watch on one object, and of a leading duration (603.7, 611.2a)
_BOUND_VERB = re.compile(r"(?:deals?|attacks?|blocks?|becomes blocked)\b")


def bound_cond(text: str) -> tuple[dict[str, Any], str, Any] | None:
    """"~ deals combat damage to a player" / "that creature attacks one of your opponents" / "target creature you control deals
    …": the condition, who the watch is bound to ("self": its source; "it": the antecedent's object; "target": the creating
    ability's target, with that target's selector) and that selector, 603.7c."""
    from app.rules import events, language

    if text.startswith("~ "):
        cond = events.parse_condition(text)
        return (cond, "self", None) if cond is not None else None
    pronoun = re.fullmatch(r"(?:that creature|it) (?P<rest>.+)", text)
    if pronoun is not None:
        cond = events.parse_condition(f"a creature {pronoun['rest']}")
        return (cond, "it", None) if cond is not None and _BOUND_VERB.match(pronoun["rest"]) else None
    words = text.split()
    for k in range(2, min(7, len(words))):  # ("target creature you control" | "target Giant you control" …, then the verb)
        rest = " ".join(words[k:])
        if words[0] == "target" and _BOUND_VERB.match(rest) and (group := language.target_group(" ".join(words[:k]))) is not None:
            cond = events.parse_condition(f"a creature {rest}")
            return (cond, "target", group["what"]) if cond is not None else None
    return None


def parse(cond_text: str, clause: str, *, next_turn: bool = False) -> tuple[list[dict[str, Any]], Any] | None:
    """"Whenever <cond> this turn, <clause>": a watch on players or objects, or on the one object the condition names."""
    from app.rules import events

    if (bound := bound_cond(cond_text)) is not None:
        found = build(bound[0], clause, once=False, text=cond_text, bound=bound[1], next_turn=next_turn)
        return (found[0], bound[2]) if found is not None else None
    return build(events.parse_condition(cond_text), clause, once=False, text=cond_text, next_turn=next_turn)


def parse_leading(rest: str, *, next_turn: bool = False) -> tuple[list[dict[str, Any]], Any] | None:
    """"Until end of turn, whenever <cond>, <clause>" (611.2a): the condition is the shortest comma-separated start that reads."""
    from app.rules import events

    for at in [m.start() for m in re.finditer(", ", rest)]:
        if bound_cond(rest[:at]) is not None or events.parse_condition(rest[:at]) is not None:
            return parse(rest[:at], rest[at + 2:], next_turn=next_turn)
    return None


# "Choose target creature you control. Whenever that creature deals combat damage to a player this turn, …" (Hunter's Insight): the
# chosen target is the watch's object, as "Whenever target creature … this turn" names it
_CHOOSE_WATCH = re.compile(r"(?<![^ ])[Cc]hoose (?P<t>target [^.,]+)\. [Ww]henever (?:that creature|it) (?P<rest>[^.]*? this turn, [^.]+\.)")


def join_choose(body: str) -> str:
    return _CHOOSE_WATCH.sub(lambda m: f"Whenever {m['t']} {m['rest']}", body)


# -- turn-long triggers (wave 35B) -- "When that creature dies / leaves the battlefield this turn, …" on the objects the spell itself named (603.7c)
# "When the creature an opponent controls dies this turn, if you control your commander, you become the monarch." (Fight for the Throne;
# Devouring Tendrils): the target of an earlier part, described again rather than "that creature" (which of two targets would that be?);
# "Whenever a creature [you control] dealt damage this way dies this turn, …" (Ghired's Belligerence, Reckless Blaze, Skeletonize): each
# permanent the one damage instruction before it actually dealt damage to (after prevention), a trigger for each of them (603.7b: "this
# turn" is a stated duration). 603.10a / 700.4: a dies trigger looks back in time; the object is the one bound, not a new one (400.7).
_DIES_WATCH = re.compile(r"^(?:when|whenever) (?P<subj>.+?) (?P<verb>dies|leaves the battlefield) this turn, (?P<clause>.+)$")
_DEALT_SUBJ = re.compile(r"^an? (?P<what>creature|permanent|creature or planeswalker)(?P<ctl> you control)? dealt damage this way$")
_LATER_SUBJ = re.compile(r"^the (?P<noun>(?:creature|permanent|planeswalker|creature or planeswalker) (?:an opponent controls|you don't control|you control))$")


def deferred(clause: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, Any] | None] | None:
    """The deferred part of "When <object> dies / leaves the battlefield this turn, [if <cond>,] <clause>": its effects as they read the
    event (delayed.inner_for_event: "it" is the object, its new object where it went), its own target (chosen as it triggers, 603.3d; not
    one of the creating ability's groups) and an intervening "if" (603.4: checked as it triggers, and again as it resolves). None: manual."""
    from app.rules import conditions, scripts

    cond = None
    if (iff := re.match(r"if (?P<c>[^,]+), (?P<rest>.+)$", clause)) is not None:
        if (cond := conditions.parse(iff["c"])) is None:
            return None
        clause = iff["rest"]
    inner = scripts._clause(clause)
    if inner is None:
        return None
    own = None
    if inner[1] is not None:
        own = scripts.target_fields(inner[1]).get("target")
        if not (isinstance(own, dict) and set(own) == {"what"}):
            return None
    effects = delayed.inner_for_event(inner[0])
    if effects is None or any(e.get("do") in delayed.UNDEFERRABLE for e in effects):
        return None
    if own is not None:
        effects = delayed.mark_target(effects)
    if cond is not None:
        effects = [{"do": "only_if", "cond": cond, "skip": len(effects)}, *effects]
    return effects, own, cond


def _names_group(group: dict[str, Any], noun: str) -> bool:
    """Does the described object ("creature an opponent controls", "permanent you don't control") cover everything the target group allows?"""
    from dataclasses import replace

    from app.rules import selectors

    legacy = {"creature": "creature", "creature_you_control": "creature you control", "creature_opponent_controls": "creature an opponent controls"}
    what = str(group.get("what"))
    ours = selectors.from_key(what) if what.startswith(selectors.PREFIX) else selectors.parse(legacy[what]) if what in legacy else None
    said = selectors.parse(noun)
    if ours is None or said is None or ours.player is not None:
        return False
    return set(ours.types) <= set(said.types or ours.types) and replace(said, types=ours.types) == ours  # (all else the same: whose, what kind)


def bound_sentence(text: str, effects: list[dict[str, Any]], groups: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """The sentence as a delayed trigger bound to a target of the spell named again, or to the objects the damage before it was dealt to."""
    from app.rules import scripts

    m = _DIES_WATCH.match(text)
    if m is None or (got := deferred(m["clause"])) is None:
        return None
    deferred_effects, own, cond = got
    when: dict[str, Any] = {"kind": "event", "event": "die" if m["verb"] == "dies" else "leave", **({"if": cond} if cond is not None else {})}
    extra: dict[str, Any] = {}
    who = None
    if (dealt := _DEALT_SUBJ.match(m["subj"])) is not None:
        hits = [(i, e) for i, e in enumerate(effects) if e.get("do") in ("damage", "fight")]
        if len(hits) != 1 or hits[0][1].get("do") != "damage":  # ("this way": the one damage instruction; two would not say which)
            return None
        i, e = hits[0]
        e["dealt_as"] = e.get("dealt_as") or f"ref:d{i}"
        extra = {"dealt": e["dealt_as"], "types": scripts._DIES_THAT[dealt["what"]], "once": False}
        if dealt["ctl"]:
            when["ctl"] = "you"  # (603.10a: who controlled it as it died)
    elif (later := _LATER_SUBJ.match(m["subj"])) is not None:
        found = [g for g, group in enumerate(groups) if group.get("max") == 1 and _names_group(group, later["noun"])]
        if len(found) != 1:
            return None  # (none, or which of two?)
        who = f"target:{found[0]}"
    else:
        return None
    wrapped = delayed.wrap_when(deferred_effects, when, who=who, this_turn=True)
    wrapped[0].update(extra)
    if own is not None:
        wrapped[0]["target"] = own
    return wrapped


def deferred_event_effects(effects: list[dict[str, Any]]) -> set[int]:
    """The indices of the effects a watch defers: what they name of "the event" is the watch's own, not the creating
    ability's (scripts._event_refs_ok / _event_spell_ok skip them)."""
    out: set[int] = set()
    for i, e in enumerate(effects):
        if e.get("do") == "delayed" and e.get("when", {}).get("kind") == "watch":
            out.update(range(i + 1, i + 1 + int(e.get("n", 0))))
    return out


def on_facts(plan: Plan, facts: list[Any], batch: int, fired_once: dict[Any, Any] | None = None) -> None:
    """One event's facts: the watches created before it that it matches trigger (603.7). ``fired_once``: what already triggered in
    these events ("one or more" triggers once per batch, and per player dealt the damage, 603.2c)."""
    r = plan.rules
    mine = [t for t in r.delayed if t.when.get("kind") == "watch" and (batch < 0 or batch > int(t.when.get("since", 0)))]  # (batch -1: as it happens)
    if not mine:
        return
    from app.rules import triggers

    fired = []
    for t in mine:
        source = plan.state.cards.get(t.source_card or "")
        if source is None or t.controller not in plan.live():
            continue
        watcher = source.model_copy(update={"controller": t.controller})
        bound = {o["object_id"] for o in (t.refs.get("watch") or {}).get("objects") or []} if t.when.get("bound") else None
        for fact in facts:
            if bound is not None and fact[4].get("oid") not in bound:
                continue  # -- turn-long triggers (wave 33A) -- 603.7c, 400.7: the object it was bound to, not a new one
            if triggers._cond_matches(plan, t.when["cond"], watcher, fact):
                cond = t.when["cond"]
                key = (t.id, -7, batch, "" if cond.get("to") in ("players", "opponents") else fact[4].get("recipient") or "")
                if cond.get("aggregate") and fired_once is not None:
                    if key in fired_once:
                        continue
                    fired_once[key] = delayed._fire(plan, t, triggers._event(plan, fact, batch))
                else:
                    delayed._fire(plan, t, triggers._event(plan, fact, batch))
                if t.once:
                    fired.append(t)
                    break
    if fired:
        r.delayed = [t for t in r.delayed if t not in fired]


# "When you next cast …, copy that spell. You may choose new targets for the copy." — the second sentence belongs to the
# deferred ability (it follows the copy it is about: 707.10c), so the two are read as one clause
_COPY_RETARGET = re.compile(r"(?P<head>\b[Ww]hen you next cast [^.]*? this turn, copy (?:that spell|it)"
                            r"(?: (?:twice|three times|[xX] times|an additional time)| for each [^.]+?)?)"  # (review 32: Howl of the Horde's raid, Thunderclap Drake)
                            r"\. [Yy]ou may choose new targets for the cop(?:y|ies)\.")


_COPY_RETARGET_LEAD = re.compile(r"(?P<head>\b(?:[Uu]ntil end of turn|[Tt]his turn), whenever you cast [^.]*?, copy (?:that spell|it))"
                                 r"\. [Yy]ou may choose new targets for the copy\.")  # (wave 33A: The Mirari Conjecture)


def join_retarget(body: str) -> str:
    body = _COPY_RETARGET_LEAD.sub(lambda m: f"{m['head']} and you may choose new targets for the copy.", body)
    return _COPY_RETARGET.sub(lambda m: f"{m['head']} and you may choose new targets for the copy.", body)


def bind_x(value: Any, x: int) -> Any:
    """The creating spell's X (107.3) as a plain number in the deferred effects ("copy that spell X times")."""
    if value == {"x": 1}:
        return x
    if isinstance(value, list):
        return [bind_x(v, x) for v in value]
    if isinstance(value, dict):
        return {k: bind_x(v, x) for k, v in value.items()}
    return value
