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
the older ``blocking_source`` extras), ``@host`` what that source is attached to ("equipped creature", "enchanted creature"), ``@pron`` an unresolved "it" that scripts.define turns into one of these by what the ability is. A bound reference
is ``@obj:<object id>[,…]`` (JSON-native: it survives a pause for a decision, a save, undo and replay). A reference with nothing to bind is
``@none``: it matches nothing.

State: ``ObjectSnapshot.blocked_by_ids`` (who blocked it when it left; default empty) and ``DelayedTrigger.until_combat`` ("whenever … this combat" watches stop as
the combat phase ends: combat.end_combat; default off); the relations themselves store nothing (they read ``CardInstance.blocking``/``attached_to``,
``TurnLog.blocks``, last known information). Decisions: the existing ones only (a choice among the creatures blocking or blocked by one, 608.2d; a player with the most life,
effects.MOST_LIFE). Hidden information: only battlefield facts, public by construction. Save/load: the two
defaulted fields above, so old saves load as before.
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
_REFS = {"it": "pron", "that creature": "that", "that permanent": "that", "~": "src", "this creature": "src", "those creatures": "targets",
         "one of those creatures": "targets", "equipped creature": "host", "enchanted creature": "host"}
_TARGET = r"target (?:creature|land|permanent(?: you (?:own|control))?|artifact|enchantment)"
_REF = "|".join([*sorted(map(re.escape, _REFS), key=len, reverse=True), _TARGET])


def _ref(phrase: str) -> str:
    """The reference of a phrase: a pronoun's, or ``target=<selector>`` (the target the instruction has, whose kind the selector says: ``targeted``)."""
    if phrase in _REFS:
        return _REFS[phrase]
    from app.rules import selectors

    sel = selectors.parse(phrase[len("target "):])
    if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.card:
        raise ValueError("not a permanent")
    return f"target={sel.key()}"


def _add(s: selectors.Selector, extra: str) -> selectors.Selector:
    return replace(s, extras=(*s.extras, extra))


# -- grammar (selectors suffixes) ---------------------------------------------------------------------------------------------------
_KINDS = {"blocking or blocked by": "pair", "blocking": "blocking", "blocked by": "blockedby"}


def _blocks(s: selectors.Selector, m: re.Match[str]) -> selectors.Selector:
    """"creatures blocking or blocked by it / that creature / target creature" (509.1a)."""
    return _add(s, f"rel:{_KINDS[m['k']]}@{_ref(m['r'])}")


_HIST = {"blocked or was blocked by": "hpair", "blocked or were blocked by": "hpair", "was blocked by": "hblockedby", "were blocked by": "hblockedby",
         "blocked": "hblocked"}


def _history(s: selectors.Selector, m: re.Match[str]) -> selectors.Selector:
    """"creature that blocked or was blocked by it / a Zombie this turn", "creatures that were blocked by that creature this combat" (509.1g)."""
    kind = _HIST[m["v"]]
    if m["r"] is not None:
        if m["t"] == "combat":  # (the turn log keeps no combat apart: this combat's blocks are read off the creatures still blocking)
            kind = {"hblockedby": "blockedby", "hblocked": "blocking", "hpair": "pair"}[kind]
        return _add(s, f"rel:{kind}@{_ref(m['r'])}")
    if m["t"] == "combat":
        raise ValueError("this combat with a kind of creature")
    from app.rules import selectors

    sel = selectors.parse(re.sub(r"^an? ", "", m["sel"]))
    if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.card:
        raise ValueError("not a creature")
    return _add(s, f"rel:hsel:{kind}:{sel.key()}")


def _attached(s: selectors.Selector, m: re.Match[str]) -> selectors.Selector:
    """"Auras attached to that creature" (303.4, 301.5)."""
    return _add(s, f"rel:att@{_ref(m['r'])}")


def _was_attached(s: selectors.Selector, m: re.Match[str]) -> selectors.Selector:
    """"Aura cards that were attached to it" (Cass): attached to the creature as it last existed (608.2h), wherever the card is now."""
    return _add(s, f"rel:wasatt@{_ref(m['r'])}")


def register() -> None:
    from app.rules import selectors

    suffixes = [
        # (the older extras read ~ and "blocking it": selectors._blocking_source, _block_pair_source)
        (re.compile(r"(?:,)? (?P<k>blocking or blocked by|blocked by) (?P<r>it|that creature|target creature|those creatures|equipped creature|enchanted creature)$"), _blocks),
        (re.compile(r"(?:,)? (?P<k>blocking) (?P<r>that creature|target creature|those creatures|one of those creatures|equipped creature|enchanted creature)$"), _blocks),
        (re.compile(rf"(?:,)? that (?P<v>blocked or (?:was|were) blocked by|blocked|was blocked by|were blocked by) (?:(?P<r>{_REF})|(?P<sel>an? .+?)) "
                    r"this (?P<t>turn|combat)$"), _history),
        (re.compile(r"(?:,)? that (?:was|were) attached to (?P<r>that creature|it)$"), _was_attached),
        (re.compile(rf"(?<!with a legendary Equipment)(?<!with another Aura)(?<!with another Equipment)(?:,)? (?:that(?:'s| is| are) )?attached to (?P<r>that creature|it|{_TARGET})$"), _attached),  # ("with another Aura/Equipment" and Kassandra's legendary Equipment qualifier have their own suffixes)
    ]
    for pair in reversed(suffixes):
        selectors._SUFFIXES.insert(0, pair)


# -- matching (selectors.matches calls this for a ``rel:`` extra) -----------------------------------------------------------------
def _refs(ref: str, source: str | None, plan: Plan) -> list[str]:
    """The object ids a bound reference names; ``@src``: the source, as it is (or as it last existed, 608.2h)."""
    if ref.startswith("obj:"):
        return ref[4:].split(",")
    if ref == "host" and source:  # (the permanent the source Equipment / Aura is attached to now: "equipped creature", "enchanted creature"; if the source left, as it last existed:
        # "Sacrifice this Aura: Destroy all non-Wall creatures blocking enchanted creature", 608.2h)
        src = plan.state.cards.get(source)
        if src is not None and src.zone.endswith(":battlefield"):
            attached = src.attached_to
        else:
            last = plan.rules.last_known(source)
            attached = last.attached_to if last is not None else None
        host = plan.state.cards.get(attached or "")
        return [plan.oid(host)] if host is not None and host.zone.endswith(":battlefield") else []
    if ref == "src" and source:
        src = plan.state.cards.get(source)
        if src is not None and src.zone.endswith(":battlefield"):
            return [plan.oid(src)]
        last = plan.rules.last_known(source)
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
        elif kind == "wasatt":  # (the creature as it last existed, a card id in its attachments then)
            ok = snap is not None and card.id in snap.attached
        elif kind in ("blocking", "blocking_live", "blockedby", "pair"):
            if kind == "blocking_live" and not here:
                continue
            ok = card.zone.endswith(":battlefield") and kind != "blockedby" and (
                card.blocks(rid) if here else snap is not None and card.id in snap.blocked_by_ids)
            if not ok and kind not in ("blocking", "blocking_live"):
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
    return paired_with(plan, plan.oid(card), mode, key, card.controller)


def paired_with(plan: Plan, me: str, mode: str, key: str, you: str) -> bool:
    """Did this object (400.7) block / get blocked by a creature of the selector's kind this turn (509.1g)? The other creature is read as it is while
    it is still that object, else as it last existed (608.2h)."""
    from app.rules import selectors
    from app.rules.triggers import _snapshot_card

    log = plan.rules.turn_log
    if log.turn != plan.state.turn.number:
        return False
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
        if selectors.matches(plan, sel, pair[0], pair[1], you, None):
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
    """"Return all creatures blocking or blocked by target creature to their owner's hand", "destroy all Auras attached to target land": the "target
    [kind of permanent]" of the relation is the instruction's one target (115.1), chosen as it goes on the stack; its kind is in the extra
    (``@target=<selector>``), taken out here. Two different kinds of target in one ability are not read."""
    if found is None or "@target=" not in json.dumps(found[0], default=str):
        return found
    from dataclasses import replace

    from app.rules import selectors

    kinds: set[str] = set()

    def fix(v: Any) -> Any:
        if isinstance(v, list):
            return [fix(x) for x in v]
        if isinstance(v, dict):
            return {k: fix(x) for k, x in v.items()}
        if isinstance(v, str) and v.startswith(selectors.PREFIX) and "@target=" in v:
            sel = selectors.from_key(v)
            extras = []
            for x in sel.extras:
                base, _, kind = x.partition("@target=")
                kinds.add(kind) if kind else None
                extras.append(f"{base}@target" if kind else x)
            return replace(sel, extras=tuple(extras)).key()
        return v

    effects = fix(found[0])
    if found[1] is not None or len(kinds) != 1:  # (an instruction with a target of its own: the relation's target would be a second one)
        return None
    return effects, kinds.pop(), found[2]


def rewrite(body: str) -> str:
    """Wordings that say "When you do" another way: "attach any number of target Equipment you control to target creature you control. When one or more Equipment become attached
    to that creature this way, that creature deals damage equal to its power to up to one target creature." (Thorin, Mountain-king): a reflexive ability (603.12) that triggers
    if any Equipment was attached to it."""
    body = re.sub(r"\bWhen one or more Equipment become attached to that creature this way, ", "When you do, ", body)
    # "Choose target creature. At this turn's next end of combat, destroy all creatures that blocked or were blocked by it this turn." (Venomous Breath): the target the first sentence only names,
    # named in the relation (115.1: chosen as the spell is cast, read when the end of combat comes)
    body = re.sub(r"^Choose (target [^.,]+)\. (At this turn's next end of combat, [^.]*?) it( this turn\.)$", r"\2 \1\3", body)
    # "create a white Aura enchantment token named Contract attached to target creature an opponent controls. The token has enchant creature and "Whenever enchanted creature attacks, …"" (Scriv,
    # the Obligator): the token roles.NAMED knows, with exactly those abilities
    from app.rules import roles

    contract = roles.NAMED["Contract"][1]
    return body.replace('create a white Aura enchantment token named Contract attached to target creature an opponent controls. The token has enchant creature and "' + contract + '"',
                        "create a Contract Aura token attached to target creature an opponent controls.")


def host_wording(body: str) -> str:
    """A trigger of the creature an Aura / Equipment is attached to, about the creature on the other side of a block: "it gains deathtouch" (Hedron Blade) and
    "the first creature assigns no combat damage" (Laccolith Rig) name the host, which "that creature" (the other side) would hide."""
    body = re.sub(r"\bthe first creature\b", "equipped creature", body)
    return re.sub(r"^it (?=gains? |gets? |has |assigns )", "equipped creature ", body)


def both_creatures(cond: dict[str, Any], body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """"Whenever equipped creature blocks or becomes blocked by a creature, destroy both creatures." (Dead-Iron Sledge): the host and the creature on the other side,
    destroyed together (one instruction, so one event: 603.10a, and regeneration shields are used up together); "this creature and that creature phase out."
    (Dream Fighter)."""
    if not cond.get("other") or not (cond["event"] in ("block", "blocked") or set(cond.get("events", ())) <= {"block", "blocked"}):
        return None
    if cond.get("subject") == "host" and body == "destroy both creatures.":
        return [{"do": "destroy", "who": "union:ref:event_other+host"}], None, False
    if cond.get("subject") == "host" and cond.get("aggregate") and body == "you may exile one of those creatures.":
        # (Godsend: one of the creatures blocking or blocked by the equipped creature as this resolves, chosen by its controller, not targeted: 608.2d, 115.1; the exile is the linked ability's, 607.2a)
        from app.rules import selectors

        sel = selectors.parse("creature blocking or blocked by equipped creature")
        if sel is None:
            return None
        pick = {"do": "player_chooses", "who": "you", "sel": sel.key(), "n": 1, "label": "creature", "any": True, "upto": True, "optional": True, "as": "e0"}
        return [pick, {"do": "exile", "who": "ref:e0", "link": True}], None, False
    if cond.get("subject", "self") == "self" and body == "~ and that creature phase out.":  # (Dream Fighter: both phase out, 702.26a)
        return [{"do": "phase_out", "who": "union:self+ref:event_other"}], None, False
    if cond.get("subject", "self") == "self" and cond["event"] == "blocked" and body == "that creature gets -X/-0 until end of turn, where X is half the creature's power, rounded down.":
        # (Catacomb Dragon: X is half the blocker's power as this resolves, rounded down; it gets -X/-0 for the turn, 107.1a, 611.2a)
        return [{"do": "pump", "who": "ref:event_other", "p": {"neg": {"half": {"power": "ref:event_other"}, "round": "down"}}, "t": 0}], None, False
    if cond.get("subject", "self") == "self" and cond["event"] == "blocked" and body == (
            "that creature's controller sacrifices it at end of combat. If the player does, they create a 0/2 colorless Wall artifact creature token with defender."):
        # (Basalt Golem: at end of combat its controller sacrifices it; they create the Wall only if they did, 701.21a, 118.12 — a creature that is gone by then is not sacrificed)
        from app.rules import delayed

        wall = {"name": "Wall", "power": "0", "toughness": "2", "colors": [], "type_line": "Token Artifact Creature — Wall", "text": "Defender"}
        return delayed.wrap_when([
            {"do": "sacrifice", "who": "ref:event_other", "by": "controller", "did": "mdid0", "as": "e0"},
            {"do": "only_if", "cond": {"succeeded": "mdid0"}, "skip": 1},
            {"do": "create_token", "who": "ref:e0.controller", "n": 1, "token": wall}], delayed.END_OF_COMBAT), None, False
    return None


def lki_attachments(cond: dict[str, Any], body: str, ante: str | None) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """"Whenever Cass or another creature you control dies, if it was enchanted or equipped, return any number of Aura cards that were attached to it from your graveyard to the
    battlefield attached to target creature, then attach any number of Equipment that were attached to it to that creature." (Cass, Hand of Vengeance): what was attached to the
    creature as it last existed (608.2h, 603.10a), each Aura entering attached to the target only if it could enchant it (303.4i), then the Equipment chosen as it resolves (701.3a)."""
    head = "if it was enchanted or equipped, "
    if cond.get("event") != "die" or body != head + ("return any number of Aura cards that were attached to it from your graveyard to the battlefield attached to target creature, "
                                                      "then attach any number of Equipment that were attached to it to that creature."):
        return None
    from app.rules import scripts, selectors

    lead = scripts.parse_effects(head + "draw a card.", it=ante)  # (the intervening "if", read as the grammar reads it: 603.4, checked as it triggers and as it resolves)

    auras = selectors.parse("Aura card that was attached to that creature from your graveyard")
    target = selectors.parse("creature")
    if auras is None or target is None or lead is None or lead[0][0].get("do") != "only_if":
        return None
    back = {"do": "return_choice", "to": "battlefield", "tapped": False, "under": "you", "host": "target", "sel": auras.key(), "n": 999, "upto": True, "random": False, "label": "Aura card"}
    attach = {"do": "attach_choose", "n": 0, "kinds": ["Equipment"], "who": "target", "anyone": True, "was_attached": True}
    return [{**lead[0][0], "skip": 2}, back, attach], target.key(), False


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


# -- becoming blocked by an effect (509.1h, 509.3c) ----------------------------------------------------------------------------------
def become_blocked(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Target unblocked attacking creature becomes blocked." (Curtain of Light, Dazzling Beauty, Trap Runner): 509.1h — it is a blocked creature from now on, though no
    creature blocks it (it deals no combat damage unless it has trample, 702.19e). 509.3c: its "becomes blocked" abilities trigger (not "becomes blocked by a creature",
    509.3d — nothing blocks it), only if it was unblocked at that time. A target that is no longer an unblocked attacking creature as this resolves does nothing (608.2b)."""
    from app.rules import banding, effects, triggers

    selected = effects._cards(plan, ctx, e["who"])
    for cid in dict.fromkeys(member for selected_id in selected for member in banding.members(plan.state, selected_id)):
        card = plan.state.cards[cid]
        if not card.is_attacking or not card.zone.endswith(":battlefield") or cid in plan.rules.blocked or not blockers_declared(plan):
            continue
        plan.rules.blocked = [*plan.rules.blocked, cid]
        plan.note(f"{card.name} becomes blocked", [cid])
        triggers.blocked(plan, [], [card])
    return True


def blockers_declared(plan: Plan) -> bool:
    """509.1h: a creature is blocked or unblocked once blockers have been declared (the declare blockers step, its decisions made, or later in combat)."""
    d = plan.rules.decision
    return plan.state.turn.phase in ("declare_blockers", "combat_damage", "end_combat") and not (d is not None and d.kind == "declare_blockers") \
        and not plan.rules.blockers_pending


PRIMITIVES = {"become_blocked": become_blocked}
