"""-- block events (wave 53C) -- creatures related to a named creature by combat (blocking it, blocked by it, blocked or was blocked by it this turn,
attached to it): "each creature blocking it", "all creatures blocking or blocked by target creature", "destroy target creature that blocked or was
blocked by a legendary creature this turn", "destroy all Auras attached to that creature". Researched against CR 2026-09-25.

* 509.1a, 509.1g: a creature blocks an attacking creature; a blocker stays blocking an attacker that left combat (506.4), so "creatures blocking it"
  is read off the blockers' own marker (``CardInstance.blocking``), and "creatures it blocked" off the attacker's last known information once it left
  (608.2h: ``ObjectSnapshot.blocking_ids``). 509.3c-d: a creature that "becomes blocked" stays blocked (``RulesState.blocked``).
* 509.1g: "blocked or was blocked by X this turn" is the turn log's block record (``TurnLog.blocks``: blocker object -> attacker objects), by object
  (400.7: a creature that left and came back is a new object). The other creature is read as it is while it is still that object, else as it last existed
  (608.2h, 603.10a).
* 301.5, 303.4: "attached to X" is ``CardInstance.attached_to``; X must still be that object (400.7).

The reference ("it", "that creature", "target creature") is a placeholder in the selector (extra ``rel:<kind>@<ref>``) bound when an instruction
runs (``bind``): ``@that`` the object the trigger event is about (else the first target), ``@target`` the first target, ``@targets`` every target,
``@src`` the ability's source (an activated ability, a trigger about the source itself, a static: the ``source`` the selector is matched with, as
the older ``blocking_source`` extras), ``@pron`` an unresolved "it" that scripts.define turns into one of these by what the ability is. A bound reference
is ``@obj:<object id>[,…]`` (JSON-native: it survives a pause for a decision, a save, undo and replay). A reference with nothing to bind is
``@none``: it matches nothing.

State: none of its own (reads ``CardInstance.blocking``/``attached_to``, ``TurnLog.blocks``, last known information). Decisions: none. Hidden
information: only battlefield facts, public by construction. Save/load: nothing stored, so old saves load as before.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules import selectors
    from app.rules.plan import Plan

PLACEHOLDER = re.compile(r"rel:(\w+)@(that|target|targets)\b")
_REFS = {"it": "pron", "that creature": "that", "that permanent": "that", "target creature": "target", "target permanent": "target",
         "~": "src", "this creature": "src", "those creatures": "targets", "one of those creatures": "targets"}
_REF = "|".join(sorted(map(re.escape, _REFS), key=len, reverse=True))


def _add(s: selectors.Selector, extra: str) -> selectors.Selector:
    return replace(s, extras=(*s.extras, extra))


# -- grammar (selectors suffixes) ---------------------------------------------------------------------------------------------------
_KINDS = {"blocking or blocked by": "pair", "blocking": "blocking", "blocked by": "blockedby"}


def _blocks(s: selectors.Selector, m: re.Match[str]) -> selectors.Selector:
    """"creatures blocking or blocked by it / that creature / target creature" (509.1a)."""
    return _add(s, f"rel:{_KINDS[m['k']]}@{_REFS[m['r']]}")


_HIST = {"blocked or was blocked by": "hpair", "blocked or were blocked by": "hpair", "was blocked by": "hblockedby", "were blocked by": "hblockedby",
         "blocked": "hblocked"}


def _history(s: selectors.Selector, m: re.Match[str]) -> selectors.Selector:
    """"creature that blocked or was blocked by it / a Zombie this turn", "creatures that were blocked by that creature this combat" (509.1g)."""
    kind = _HIST[m["v"]]
    if m["r"] is not None:
        if m["t"] == "combat":  # (the turn log keeps no combat apart: this combat's blocks are read off the creatures still blocking)
            kind = {"hblockedby": "blockedby", "hblocked": "blocking", "hpair": "pair"}[kind]
        return _add(s, f"rel:{kind}@{_REFS[m['r']]}")
    if m["t"] == "combat":
        raise ValueError("this combat with a kind of creature")
    from app.rules import selectors

    sel = selectors.parse(re.sub(r"^an? ", "", m["sel"]))
    if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.card:
        raise ValueError("not a creature")
    return _add(s, f"rel:hsel:{kind}:{sel.key()}")


def _attached(s: selectors.Selector, m: re.Match[str]) -> selectors.Selector:
    """"Auras attached to that creature" (303.4, 301.5)."""
    return _add(s, f"rel:att@{_REFS[m['r']]}")


def register() -> None:
    from app.rules import selectors

    suffixes = [
        # (the older extras read ~ and "blocking it": selectors._blocking_source, _block_pair_source)
        (re.compile(r"(?:,)? (?P<k>blocking or blocked by|blocked by) (?P<r>it|that creature|target creature|those creatures)$"), _blocks),
        (re.compile(r"(?:,)? (?P<k>blocking) (?P<r>that creature|target creature|those creatures|one of those creatures)$"), _blocks),
        (re.compile(rf"(?:,)? that (?P<v>blocked or (?:was|were) blocked by|blocked|was blocked by|were blocked by) (?:(?P<r>{_REF})|(?P<sel>an? .+?)) "
                    r"this (?P<t>turn|combat)$"), _history),
        (re.compile(r"(?:,)? (?:that(?:'s| is| are) )?attached to (?P<r>that creature|target creature|it)$"), _attached),
    ]
    for pair in reversed(suffixes):
        selectors._SUFFIXES.insert(0, pair)


# -- matching (selectors.matches calls this for a ``rel:`` extra) -----------------------------------------------------------------
def _refs(ref: str, source: str | None, plan: Plan) -> list[str]:
    """The object ids a bound reference names; ``@src``: the source, as it is (or as it last existed, 608.2h)."""
    if ref.startswith("obj:"):
        return ref[4:].split(",")
    if ref == "src" and source:
        src = plan.state.cards.get(source)
        if src is not None and src.zone.endswith(":battlefield"):
            return [plan.oid(src)]
        last = max((x for x in plan.rules.lki.values() if x.card == source), key=lambda x: x.turn, default=None)
        return [last.object_id] if last is not None else []
    return []


def rel_matches(plan: Plan, card: CardInstance, extra: str, source: str | None) -> bool:
    body = extra[len("rel:"):]
    if body.startswith("hsel:"):
        mode, _, key = body[len("hsel:"):].partition(":")
        return _hist_sel(plan, card, mode, key)
    kind, _, ref = body.partition("@")
    me = plan.oid(card)
    for oid in _refs(ref, source, plan):
        rid = oid.rsplit(".", 1)[0]
        rcard = plan.state.cards.get(rid)
        snap = plan.rules.lki.get(oid)  # (R left, a token ceased to exist: as it last existed, 608.2h; what it blocked or was blocked by is unblocked, ops.move_card)
        here = rcard is not None and rcard.zone.endswith(":battlefield") and plan.oid(rcard) == oid
        if kind == "att":
            ok = here and card.attached_to == rid
        elif kind in ("blocking", "blockedby", "pair"):
            ok = card.zone.endswith(":battlefield") and kind != "blockedby" and (
                card.blocks(rid) if here else snap is not None and card.id in snap.blocked_by_ids)
            if not ok and kind != "blocking":
                ok = rcard.blocks(card.id) if here and rcard is not None else snap is not None and card.id in snap.blocking_ids
        else:  # the turn's blocks (509.1g)
            log = plan.rules.turn_log
            ok = log.turn == plan.state.turn.number and (
                (kind in ("hblockedby", "hpair") and me in log.blocks.get(oid, ()))
                or (kind in ("hblocked", "hpair") and oid in log.blocks.get(me, ())))
        if ok:
            return True
    return False


def _hist_sel(plan: Plan, card: CardInstance, mode: str, key: str) -> bool:
    """"blocked or was blocked by a [kind of creature] this turn": the other creature as it is, else as it last existed (608.2h)."""
    from app.rules import selectors
    from app.rules.triggers import _snapshot_card

    log = plan.rules.turn_log
    if log.turn != plan.state.turn.number:
        return False
    me = plan.oid(card)
    others: list[str] = []
    if mode in ("hblocked", "hpair"):
        others += log.blocks.get(me, [])
    if mode in ("hblockedby", "hpair"):
        others += [b for b, attackers in log.blocks.items() if me in attackers]
    sel = selectors.from_key(key)
    for oid in others:
        other = plan.state.cards.get(oid.rsplit(".", 1)[0])
        if other is not None and other.zone.endswith(":battlefield") and plan.oid(other) == oid:
            pair = (other, plan.ch(other))
        elif (snap := plan.rules.lki.get(oid)) is not None:
            pair = _snapshot_card(plan, snap)
        else:
            continue
        if selectors.matches(plan, sel, pair[0], pair[1], card.controller, None):
            return True
    return False


# -- binding (effects._continue_effects, delayed._bind_now) --------------------------------------------------------------------
def bind(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> dict[str, Any]:
    """The instruction with the placeholders of its selectors bound to the objects they name now (603.7c: a delayed trigger's too)."""
    text = json.dumps(e, default=str)
    if "rel:" not in text or not PLACEHOLDER.search(text):
        return e
    event = (ctx.get("event") or {}).get("objects") or []
    targets = [t.get("object_id") for t in ctx.get("targets") or [] if t.get("object_id")]
    every = [t.get("object_id") for g in ctx.get("groups") or [] for t in g if t and t.get("object_id")] or targets

    def pick(m: re.Match[str]) -> str:
        found = {"that": [event[0]["object_id"]] if event else targets[:1], "target": targets[:1], "targets": every}[m[2]]
        return f"rel:{m[1]}@" + (f"obj:{','.join(found)}" if found else "none")

    return json.loads(PLACEHOLDER.sub(pick, text))


# -- definitions (scripts.define) ------------------------------------------------------------------------------------------------
def targeted(found: tuple[list[dict[str, Any]], Any, bool] | None) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """"Return all creatures blocking or blocked by target creature to their owner's hand": the "target creature" of the relation is the
    instruction's one target (115.1), chosen as the spell is cast."""
    if found is None or found[1] is not None or "@target" not in json.dumps(found[0], default=str):
        return found
    from app.rules import selectors

    return found[0], selectors.Selector(types=("Creature",)).key(), found[2]


def settle_it(d: dict[str, Any] | None, ante: str | None) -> dict[str, Any] | None:
    """"…blocked by it": "it" is the source in an activated ability and in a trigger about the source (``self``, ``self_gone``), the object the
    event is about in any other trigger, the target in a spell."""
    if d is None or "@pron" not in json.dumps(d, default=str):
        return d
    kind = d.get("kind")
    ref = "src" if kind == "activated" or (kind == "triggered" and ante in ("self", "self_gone")) else \
        "that" if (kind == "triggered" and ante in ("event", "event_gone") or kind == "spell") else None
    if ref is None:
        return None
    return json.loads(json.dumps(d, default=str).replace("@pron", f"@{ref}"))


def refs_ok(d: dict[str, Any]) -> bool:
    """Every reference of the definition can be bound where it runs: ``@that`` by a trigger event's object or a target, ``@target`` by one
    target group, ``@src`` where the older ``blocking_source`` extras are read (the ability's source)."""
    text = json.dumps(d, default=str)
    kinds = set(PLACEHOLDER.findall(text)) | {("", r) for r in re.findall(r"rel:\w+@(src)\b", text)}
    for _, ref in kinds:
        if ref == "that" and not (d.get("kind") == "triggered" and d.get("trigger") == "event" and (d.get("cond") or {}).get("event") != "multi"
                                  or d.get("kind") in ("spell",) and (d.get("target") or d.get("targets"))
                                  or d.get("kind") == "triggered" and (d.get("cond") or {}).get("other")):
            return False
        if ref in ("target", "targets") and not (d.get("target") or d.get("targets")):
            return False
        if ref == "src" and d.get("kind") not in ("activated", "triggered", "static", "spell"):
            return False
    return True
