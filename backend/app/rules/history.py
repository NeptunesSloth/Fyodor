"""This turn's history, for the conditions that look back in time (CR 608.2i): "if you attacked this
turn" (Raid), "if a creature died this turn" (Morbid), "if a permanent left the battlefield under
your control this turn" (Revolt), "if an opponent lost life this turn", "if you gained 3 or more
life this turn", "if you've drawn two or more cards this turn", "if you lost life last turn", "if you
descended this turn" (700.11: a permanent card — never a token — was put into your graveyard from
anywhere, and needn't still be there).

The facts are recorded deterministically as the game happens (app/game/rules_state.py ``TurnLog``:
``track`` / ``emit`` for what the table shows — departures, life, draws — and the declaration of
attackers, 508.1), so they survive saves, undo / redo and replay. This module only reads them:

* an effect like this "is not taking any actions on those objects", so they needn't still be where
  they were, nor meet the criteria now, as long as they did then (608.2i): a creature that died is
  read as it last existed on the battlefield — its last known information, with the card types the
  layers gave it (an animated land or a crewed Vehicle was a creature) when the rules engine moved
  it, else its printed ones;
* a creature put onto the battlefield attacking was never declared as an attacker, so it never
  "attacked" (508.4) — only ``declare_attackers`` records an attack;
* "dies" is being put into a graveyard from the battlefield (700.4); "leaves the battlefield" is
  moving to any other zone — a token counts (it moves before it ceases to exist, 111.7).
"""

from __future__ import annotations

from typing import Any

from app.game.rules_state import Departure, TurnLog
from app.rules import characteristics as chars
from app.rules.characteristics import PERMANENT_TYPES
from app.rules.plan import Plan


def log_for(plan: Plan, last: bool = False) -> TurnLog:
    """This turn's log (or the turn before's); an empty one if nothing was recorded then."""
    rules = plan.rules
    n = plan.state.turn.number
    if last:
        for log in (rules.turn_log, rules.last_turn_log):
            if log is not None and log.turn == n - 1:
                return log
        return TurnLog()
    return rules.turn_log if rules.turn_log.turn == n else TurnLog()


def departed_types(plan: Plan, d: Departure) -> set[str]:
    """What a permanent was as it last existed on the battlefield (608.2i, 700.4)."""
    if d.types is not None:
        return set(d.types)
    snap = plan.rules.lki.get(d.object_id)
    if snap is None:
        return set()
    from app.rules.triggers import _snapshot_card  # (triggers imports the modules that import this one)

    return set(_snapshot_card(plan, snap)[1].types)


def creatures_died(plan: Plan, *, controller: str | None = None, last: bool = False) -> int:
    """How many creatures were put into a graveyard from the battlefield (this turn), optionally only
    those ``controller`` controlled as they died."""
    return sum(1 for d in log_for(plan, last).left
               if d.to == "graveyard" and (controller is None or d.controller == controller)
               and "Creature" in departed_types(plan, d))


def permanent_cards_entered(plan: Plan, player: str, *, last: bool = False) -> int:
    """700.11: how many permanent cards were put into ``player``'s graveyard from anywhere this turn
    ("descended") — counted whether or not they're still there. A token is no card (111.1)."""
    n = 0
    for arrival in log_for(plan, last).entered_graveyard:
        card = plan.state.cards.get(arrival.card)
        if arrival.owner == player and card is not None and chars.of(card, plan.info).types & PERMANENT_TYPES:
            n += 1
    return n


def holds(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    """Is this ``{"history": …}`` condition true for the ability's controller right now?"""
    kind = cond["history"]
    me: str = ctx["controller"]
    n = int(cond.get("n", 1))
    log = log_for(plan, bool(cond.get("last")))
    if kind == "attacked":
        return bool(log.attacked) if cond.get("who") == "any" else me in log.attacked
    if kind in _WAVE_4D:  # -- this-turn history (wave 4D) --
        return _WAVE_4D[kind](plan, ctx, cond, log)
    if kind == "gained":
        return log.gained.get(me, 0) >= n
    if kind == "drew":
        return log.drew.get(me, 0) >= n
    if kind == "spells":
        return plan.rules.spells_this_turn(me, plan.state.turn.number) >= n
    if kind == "lost":
        who = cond.get("who", "you")
        players = [me] if who == "you" else [p for p in plan.live() if p != me] if who == "opponent" else list(plan.live())
        return any(log.lost.get(p, 0) >= n for p in players)
    if kind == "left_graveyard":
        return me in log.left_graveyard
    if kind == "descended":
        return permanent_cards_entered(plan, me, last=bool(cond.get("last"))) >= n
    if kind == "died":
        return creatures_died(plan, controller=me if cond.get("who") == "you" else None, last=bool(cond.get("last"))) >= n
    if kind == "left":
        return sum(1 for d in log.left if cond.get("who") != "you" or d.controller == me) >= n
    if kind == "warped":  # -- void (wave 19E) -- "a spell was warped this turn": cast for its warp cost (702.185a), by anyone
        return any(c.alt == "warp" for c in log.casts)
    if kind == "entered":  # -- refused modal/conditional (wave 3R1) --
        return entered(plan, ctx, cond, log) >= n
    if kind == "entered_self":
        return any(e.object_id == _source_object(plan, ctx) for e in log.entered)
    raise ValueError(f"unknown history condition {cond!r}")


# -- refused modal/conditional (wave 3R1) --
def entered(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any], log: TurnLog) -> int:
    """How many permanents matching ``cond["sel"]`` entered the battlefield under the ability controller's control
    this turn ("another": not the source object itself). 608.2i: read as each was when it entered — its card types
    and subtypes then — and otherwise as it is, or as it last existed if it has left since."""
    from dataclasses import replace

    from app.rules import selectors
    from app.rules.triggers import _snapshot_card  # (triggers imports the modules that import this one)

    sel = selectors.from_key(cond["sel"])
    me = ctx["controller"]
    n = 0
    for e in log.entered:
        if (e.controller != me) != (cond.get("who") == "opponent") \
                or (cond.get("other") and e.object_id == _source_object(plan, ctx)):  # ("who": wave 4D)
            continue
        card = plan.state.cards.get(e.card)
        if card is not None and plan.oid(card) == e.object_id:
            ch = plan.ch(card)
        else:
            snap = plan.rules.lki.get(e.object_id)
            if snap is None:
                continue  # (gone with no last known information: a token that left, long ago)
            card, ch = _snapshot_card(plan, snap)
        if e.types is not None:
            ch = replace(ch, types=frozenset(e.types), subtypes=frozenset(e.subtypes or ()))
        probe = card.model_copy(update={"zone": f"{me}:battlefield", "controller": me}) \
            if not card.zone.endswith(":battlefield") else card
        if selectors.matches(plan, replace(sel, zones=("battlefield",), controller=None, other=False), probe, ch, me, None):
            n += 1
    return n


def _source_object(plan: Plan, ctx: dict[str, Any]) -> str | None:
    """The source object: given, or — for a static or an activation restriction, which name only the source
    card — the object that card is now."""
    if ctx.get("source_object"):
        return str(ctx["source_object"])
    card = ctx.get("source_card")
    return plan.oid(card) if card and card in plan.state.cards else None
# -- end refused modal/conditional (wave 3R1) --


# -- this-turn history (wave 4D) ----------------------------------------------------------------------------
# What a player did this turn, recorded as it happens (TurnLog.casts / facts / attackers / resolved) so the
# conditions that look back at it (608.2i) read the objects as they were then, whether or not they're still there:
# spells cast (601.2i), tokens created (111.2), discards (701.9a), sacrifices (701.21a), damage dealt to players
# (120.3), scry / surveil (701.22, 701.25), counters put on permanents (122.6), attackers declared (508.1), how many
# times an ability of one object resolved. Saved with the table; a new turn starts a new log (turn_log_now).
def note_cast(plan: Plan, card: Any) -> None:
    """A spell became cast (601.2i): its characteristics on the stack — face-down ones for a face-down spell (708.2)."""
    from app.game.rules_state import CastNote, turn_log_now

    log = turn_log_now(plan.state)
    if log is None:
        return
    ch = plan.ch(card)
    record = plan.rules.payments.get(plan.oid(card))
    log.casts.append(CastNote(player=card.controller, object_id=plan.oid(card), types=sorted(ch.types),
                              subtypes=sorted(ch.subtypes), supertypes=sorted(ch.supertypes), colors=sorted(ch.colors),
                              mv=float(_stack_mv(card, ch)), cast_from=record.cast_from if record is not None else None,
                              alt=record.alternative if record is not None else None))


def _stack_mv(card: Any, ch: Any) -> int:
    """-- review (wave 5R) -- a spell's mana value on the stack counts its X (202.3e): "a spell with mana value 5 or
    greater" cast this turn."""
    from app.rules.stack_interaction import mana_value

    return mana_value(card, ch)


def note_events(plan: Plan, events: list[Any]) -> None:
    """The facts of a batch of events (app/rules/triggers.py reads the same events for triggers), kept for the turn."""
    from app.game.rules_state import TurnFact, turn_log_now
    from app.rules.triggers import _facts

    log = turn_log_now(plan.state)
    if log is None:
        return
    for e in events:
        if e.kind not in ("zone_change", "sacrificed", "damage", "counters") or e.turn != plan.state.turn.number:
            continue
        for kind, obj, ch, player, info in _facts(plan, e, {"cast_from": {}}):
            what: dict[str, Any] = {"types": sorted(ch.types), "subtypes": sorted(ch.subtypes),
                                    "supertypes": sorted(ch.supertypes)} if ch is not None else {}
            if kind == "create_token" and obj is not None:  # 111.2: the player who creates a token is its owner
                log.facts.append(TurnFact(kind="token", player=obj.owner, object_id=info.get("oid"), token=True, **what))
            elif kind in ("discard", "sacrifice") and player is not None and obj is not None:
                log.facts.append(TurnFact(kind=kind, player=player, object_id=info.get("oid"), token=obj.is_token, **what))
            elif kind == "dealt_damage" and obj is None and info.get("recipient"):  # a player was dealt damage (120.3)
                log.facts.append(TurnFact(kind="damage", player=info["recipient"], amount=int(info.get("amount") or 0),
                                          combat=bool(info.get("combat")), object_id=info.get("source_oid")))
            elif kind == "dealt_damage" and obj is not None and info.get("oid") and int(info.get("amount") or 0) > 0:
                # -- damage history (wave 6B) -- a permanent was dealt damage (120.3): "creature that was dealt damage
                # this turn", "creature that dealt damage this turn" (app/rules/damage_history.py)
                log.facts.append(TurnFact(kind="damaged", player=player or obj.controller, object_id=info["oid"],
                                          amount=int(info["amount"]), combat=bool(info.get("combat")),
                                          source=info.get("source_oid"), **what))
            elif kind == "deal_damage" and info.get("recipient") and log.facts and log.facts[-1].kind == "damage":
                # its source, as it was as it dealt that damage (608.2i)
                log.facts[-1].source_types, log.facts[-1].source_supertypes = what["types"], what["supertypes"]
                log.facts[-1].source_subtypes = what["subtypes"]  # (wave 17C: prowl, 702.76a)
                log.facts[-1].source_controller = obj.controller if obj is not None else None
            elif kind == "counters_put" and player is not None:
                log.facts.append(TurnFact(kind="counters", player=player, object_id=info.get("oid"),
                                          amount=int(info.get("amount") or 0), counter=info.get("counter"),
                                          actor=info.get("actor"), **what))


def note_discards(plan: Plan, card_ids: list[str]) -> None:
    """Cards discarded from their owners' hands that a replacement put somewhere other than the graveyard (702.35a
    madness, "exile it instead"): discarded all the same (701.9a; the card is revealed as it goes to exile)."""
    from app.game.rules_state import TurnFact, turn_log_now

    log = turn_log_now(plan.state)
    for cid in card_ids:
        card = plan.state.cards.get(cid)
        if log is None or card is None:
            continue
        ch = chars.of(card, plan.info)
        log.facts.append(TurnFact(kind="discard", player=card.owner, object_id=plan.oid(card), types=sorted(ch.types),
                                  subtypes=sorted(ch.subtypes), supertypes=sorted(ch.supertypes)))


def note_look(plan: Plan, player: str, kind: str, looked: int = 0) -> None:
    """701.22b / 701.25c: ``player`` scried / surveilled N (N > 0), even with too few cards to look at (701.22d)."""
    from app.game.rules_state import TurnFact, emit, turn_log_now

    log = turn_log_now(plan.state)
    if log is not None:
        log.facts.append(TurnFact(kind=kind, player=player))
        # -- looks (wave 8B) -- "Whenever you scry / surveil": the event (603.2), numbered among this turn's of that kind
        emit(plan.state, "designation", counter=kind, player=player,
             amount=sum(1 for f in log.facts if f.kind == kind and f.player == player), looked=looked)


def note_crime(plan: Plan, stack_id: str, controller: str, targets: list[Any]) -> None:
    """700.13: a player commits a crime as they cast a spell, activate an ability or put a triggered ability on the
    stack that targets an opponent, a permanent / spell / ability an opponent controls, or a card in an opponent's
    graveyard. A copy (707.10: put on the stack, not cast or activated) commits none."""
    from app.game.rules_state import TurnFact, turn_log_now

    entry = plan.rules.stack.get(stack_id)
    log = turn_log_now(plan.state)
    if log is None or entry is None or entry.copy_of:
        return
    for t in targets:
        tid = t.id if hasattr(t, "id") else str(t)
        if tid in plan.state.players:
            crime = tid != controller
        elif (card := plan.state.cards.get(tid)) is not None:
            zone = card.zone.rsplit(":", 1)[-1]
            if zone == "battlefield":
                crime = card.controller != controller
            elif zone == "stack":
                other = plan.rules.stack.get(card.id)
                crime = (other.controller if other is not None else card.controller) != controller
            else:
                crime = zone == "graveyard" and card.owner != controller
        else:
            crime = False
        if crime:
            log.facts.append(TurnFact(kind="crime", player=controller))
            # -- crimes (wave 6D) -- "Whenever you commit a crime" (700.13: one crime per spell or ability)
            from app.game.rules_state import emit

            emit(plan.state, "designation", counter="crime", player=controller)
            return


def note_resolution(plan: Plan, key: str) -> int:
    """The ability ``key`` ("<source object>:<index>") is resolving: how many times it has now resolved this turn,
    this time included (a copy of it counts; one that was countered never resolved)."""
    from app.game.rules_state import turn_log_now

    log = turn_log_now(plan.state)
    if log is None:
        return 0
    log.resolved[key] = log.resolved.get(key, 0) + 1
    return log.resolved[key]


def counting_activations(effects: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """-- activations (wave 19E) -- "If this ability has been activated four or more times this turn": the ability's own count
    (``RulesState.ability_uses``, recorded as each activation is made, 602.2) is named in the condition, as the object and ability
    index it is; a copy of the ability is no activation."""
    import json

    text = json.dumps(effects)
    if '"history": "activations"' not in text:
        return effects
    return json.loads(text.replace('"history": "activations"', f'"history": "activations", "key": "{key}"'))


def counting_resolutions(effects: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """An ability that asks how many times it has resolved this turn counts its resolution first: the effect that
    does it goes ahead of the others (copied with them, 707.10: a copy of the ability counts too; an ability that
    doesn't resolve — countered, or every target gone, 608.2b — never gets to it)."""
    import json

    if '"history": "resolution"' not in json.dumps(effects):
        return effects
    return [{"do": "note_resolution", "key": key}, *effects]


def note_became(plan: Plan, spell_object: str, permanent_object: str) -> None:
    """A permanent spell resolved into a permanent (608.3): "another spell" asked by that permanent's abilities isn't
    the spell it was."""
    log = log_for(plan)
    for note in log.casts:
        if note.object_id == spell_object:
            note.became = permanent_object


# The fields of a selector the recorded characteristics answer (anything else — keywords, tapped, control now —
# isn't recorded, so a condition naming it isn't read)
_NOTE_FIELDS = {"types", "not_types", "subtypes", "not_subtypes", "supertypes", "not_supertypes", "colors", "not_colors",
                "colorless", "multicolored", "token", "compare", "extras", "union", "zones"}


def note_selector_ok(sel: Any) -> bool:
    from dataclasses import fields

    from app.rules.selectors import Selector

    blank = Selector()
    for f in fields(sel):
        if f.name not in _NOTE_FIELDS and getattr(sel, f.name) != getattr(blank, f.name):
            return False
    return set(sel.extras) <= {"all_types"} and all(c[0] == "mv" and isinstance(c[2], int) for c in sel.compare)


def note_matches(sel: Any, types: Any, subtypes: Any = (), supertypes: Any = (), colors: Any = (), mv: float = 0,
                 token: bool | None = None) -> bool:
    """Does an object, as recorded then, match a selector ``note_selector_ok`` accepts?"""
    types, subtypes, supertypes, colors = set(types), set(subtypes), set(supertypes), set(colors)
    if sel.union:
        if not (set(sel.types) & types or set(sel.subtypes) & subtypes):
            return False
    else:
        if sel.types and not (set(sel.types) <= types if "all_types" in sel.extras else set(sel.types) & types):
            return False
        if sel.subtypes and not set(sel.subtypes) & subtypes:
            return False
    if sel.zones == ("battlefield",) and not sel.types and not sel.union and not types & PERMANENT_TYPES:
        return False  # ("a permanent": what was on the battlefield always was one; a spell has a type, 300.1)
    if set(sel.not_types) & types or set(sel.not_subtypes) & subtypes or set(sel.not_supertypes) & supertypes:
        return False
    if sel.supertypes and not set(sel.supertypes) & supertypes:
        return False
    if sel.colors and not set(sel.colors) & colors or set(sel.not_colors) & colors:
        return False
    if sel.colorless is not None and sel.colorless != (not colors):
        return False
    if sel.multicolored is not None and sel.multicolored != (len(colors) > 1):
        return False
    if sel.token is not None and token is not None and sel.token != token:
        return False
    ops = {">=": float.__ge__, "<=": float.__le__, "==": float.__eq__}
    return all(ops[op](float(mv), float(n)) for _, op, n in sel.compare)


def _players(plan: Plan, me: str, who: str | None) -> set[str]:
    """Whose actions count: "you", "opponent" (any one of them), "any" — departed players' too (800.4a doesn't erase
    what happened)."""
    return {me} if who in (None, "you") else set(plan.state.players) - {me} if who == "opponent" else set(plan.state.players)


def _cmp(got: int, cond: dict[str, Any]) -> bool:
    n = int(cond.get("n", 1))
    return got == n if cond.get("op") == "==" else got >= n


def _cast(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any], log: TurnLog) -> bool:
    """Spells cast this turn (601.2i), as they were cast — resolved, countered or still on the stack (608.2i)."""
    from app.rules import selectors

    sel = selectors.from_key(cond["sel"])
    me_src = _source_object(plan, ctx) if cond.get("other") else None
    per: dict[str, int] = {}
    for note in log.casts:
        if cond.get("from") and note.cast_from != cond["from"]:
            continue
        if me_src is not None and me_src in (note.object_id, note.became):
            continue
        if note_matches(sel, note.types, note.subtypes, note.supertypes, note.colors, note.mv):
            per[note.player] = per.get(note.player, 0) + 1
    return _per_player(plan, ctx, cond, per)


def _per_player(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any], per: dict[str, int]) -> bool:
    """You did it that many times / one opponent did / the players together did."""
    who = _players(plan, ctx["controller"], cond.get("who"))
    if cond.get("who") == "any":
        return _cmp(sum(per.get(p, 0) for p in who), cond)
    if cond.get("op") == "==":  # ("no …": none of them did)
        return all(_cmp(per.get(p, 0), cond) for p in who)
    return any(_cmp(per.get(p, 0), cond) for p in who)


def _facts_holds(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any], log: TurnLog) -> bool:
    from app.rules import selectors

    sel = selectors.from_key(cond["sel"]) if cond.get("sel") else None
    per: dict[str, int] = {}
    for f in log.facts:
        if f.kind != cond["kind"] or (cond.get("counter") and f.counter != cond["counter"]):
            continue
        if sel is not None and not note_matches(sel, f.types, f.subtypes, f.supertypes, (), 0, f.token):
            continue
        if cond.get("self") and f.object_id != _source_object(plan, ctx):  # (wave 16D) "a counter was put on ~ this turn"
            continue
        if cond.get("by") == "you" and f.actor != ctx["controller"]:  # (wave 16D) "you put a counter on a creature this turn"
            continue
        per[f.player] = per.get(f.player, 0) + 1
    return _per_player(plan, ctx, cond, per)


def _damage(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any], log: TurnLog) -> bool:
    """A player was dealt damage this turn (120.3): "an opponent was dealt 4 or more damage" — one opponent, in all."""
    src = cond.get("source")
    per: dict[str, int] = {}
    for f in log.facts:
        if f.kind != "damage" or f.amount <= 0 or ("combat" in cond and f.combat != cond["combat"]):
            continue
        if src and not (set(src["types"]) <= set(f.source_types) and set(src["supertypes"]) <= set(f.source_supertypes)):
            continue
        if cond.get("by_self") and f.object_id != _source_object(plan, ctx):  # ("~ dealt damage to an opponent")
            continue
        per[f.player] = per.get(f.player, 0) + f.amount
    return any(per.get(p, 0) >= int(cond.get("n", 1)) for p in _players(plan, ctx["controller"], cond.get("who")))


def _prowl(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any], log: TurnLog) -> bool:
    """-- static_other sweep (wave 17C) -- 702.76a: a player was dealt combat damage this turn by a source that, at the time it dealt that
    damage, was under your control and had any of this spell's creature types (the spell being the condition's source)."""
    from app.rules.creature_types import CREATURE_TYPES

    spell = plan.state.cards.get(ctx.get("source_card") or "")
    if spell is None:
        return False
    types = set(plan.ch(spell).subtypes) & CREATURE_TYPES
    return any(f.kind == "damage" and f.combat and f.amount > 0 and f.source_controller == ctx["controller"]
               and types & set(f.source_subtypes) for f in log.facts)


def _departed(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any], log: TurnLog) -> bool:
    """Permanents that left the battlefield (or died, 700.4) this turn, as they last existed there (608.2i, 603.10a)."""
    from app.rules import selectors
    from app.rules.triggers import _snapshot_card

    sel = selectors.from_key(cond["sel"])
    me = ctx["controller"]
    src = _source_object(plan, ctx) if cond.get("other") else None
    n = 0
    for d in log.left:
        if (cond.get("died") and d.to != "graveyard") or d.object_id == src:
            continue
        if cond.get("who") and (d.controller == me) != (cond["who"] == "you"):
            continue
        snap = plan.rules.lki.get(d.object_id)
        if snap is None or (cond.get("owner") == "you" and snap.owner != me):
            continue
        _, ch = _snapshot_card(plan, snap)
        types = d.types if d.types is not None else ch.types
        if note_matches(sel, types, ch.subtypes, ch.supertypes, ch.colors, float(ch.mana_value), snap.is_token):
            n += 1
    return _cmp(n, cond)


_WAVE_4D: dict[str, Any] = {
    "tokens": lambda plan, ctx, cond, log: _facts_holds(plan, ctx, {**cond, "kind": "token"}, log),
    "attackers": lambda plan, ctx, cond, log: len(log.attackers.get(ctx["controller"], [])) >= int(cond.get("n", 1)),
    "cast": _cast,
    "facts": _facts_holds,
    "damage": _damage,
    "prowl": _prowl,
    "departed": _departed,
    "lands": lambda plan, ctx, cond, log: plan.rules.lands_this_turn(ctx["controller"], plan.state.turn.number) >= int(cond.get("n", 1)),
    "resolution": lambda plan, ctx, cond, log: resolution_holds(ctx, cond),
    "activations": lambda plan, ctx, cond, log: bool(cond.get("key")) and plan.rules.ability_uses.get(
        f"{cond['key']}:t{plan.state.turn.number}", 0) >= int(cond["n"]),
    "self_attacked": lambda plan, ctx, cond, log: _source_object(plan, ctx) in {a for v in log.attackers.values() for a in v},
    "graveyard_cards": lambda plan, ctx, cond, log: _graveyard_cards(plan, ctx, cond, log),
}


def amount(plan: Plan, ctx: dict[str, Any], v: dict[str, Any]) -> int:
    """A quantity of this turn's history (app/rules/values.py ``{"turn_history": …}``), as the effect is carried out."""
    from app.rules import selectors

    log = log_for(plan)
    me = ctx["controller"]
    kind = v["turn_history"]
    if kind == "gained":
        return log.gained.get(me, 0)
    if kind == "lost":
        return log.lost.get(me, 0)
    if kind == "drew":
        return log.drew.get(me, 0)
    if kind == "died":
        return sum(1 for d in log.left if d.to == "graveyard" and (snap := plan.rules.lki.get(d.object_id)) is not None
                   and (v.get("who") != "you" or d.controller == me)  # (-- X actions (wave 9A) -- "under your control")
                   and _departed_matches(plan, selectors.from_key(v["sel"]), d, snap))
    if kind == "attackers":  # -- cost self reduction (wave 16F) -- each creature declared as an attacker this turn, once (508.1)
        return len({a for p, ids in log.attackers.items() if v.get("who") != "you" or p == me for a in ids})
    if kind in ("tokens", "sacrificed", "discarded"):  # -- X sized by a count (wave 19F) -- one fact per token / permanent (111.2, 701.21a)
        return sum(1 for f in log.facts if f.kind == {"tokens": "token", "sacrificed": "sacrifice", "discarded": "discard"}[kind]
                   and (f.player == me or v.get("who") == "any"))  # (wave 21F: "who": "any" — each permanent sacrificed, whoever did it)
    if kind in ("opp_lost", "opp_damage"):  # (the opponents still in the game: 800.4a)
        opps = {p for p in plan.live() if p != me}
        if kind == "opp_lost":
            return sum(n for p, n in log.lost.items() if p in opps)
        return sum(f.amount for f in log.facts if f.kind == "damage" and f.player in opps)
    if kind == "opponents_who":
        n = int(v.get("n", 1))
        opponents = [p for p in plan.state.players if p != me]  # (800.4a: a player who left still did it — but isn't counted)
        opponents = [p for p in opponents if p in plan.live()]
        if v["what"] == "drew":
            return sum(1 for p in opponents if log.drew.get(p, 0) >= n)
        if v["what"] == "lost":
            return sum(1 for p in opponents if log.lost.get(p, 0) >= n)
        if v["what"] == "damaged":  # (wave 21F: Gnoll War Band — damage dealt to the player, 120.3)
            return sum(1 for p in opponents if any(f.kind == "damage" and f.player == p and f.amount > 0 for f in log.facts))
        land = selectors.parse("land")
        assert land is not None
        return sum(1 for p in opponents if entered(plan, {**ctx, "controller": p}, {"sel": land.key()}, log) >= n)
    raise ValueError(f"unknown history amount {v!r}")


def _departed_matches(plan: Plan, sel: Any, d: Any, snap: Any) -> bool:
    from app.rules.triggers import _snapshot_card

    _, ch = _snapshot_card(plan, snap)
    types = d.types if d.types is not None else ch.types
    return note_matches(sel, types, ch.subtypes, ch.supertypes, ch.colors, float(ch.mana_value), snap.is_token)


def _graveyard_cards(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any], log: TurnLog) -> bool:
    """Cards put into your graveyard from anywhere this turn (whether or not they're still there, 608.2i): a card's
    characteristics are the same in any zone but the battlefield and the stack, so they're read from the card."""
    from dataclasses import replace

    from app.rules import selectors

    sel = replace(selectors.from_key(cond["sel"]), zone_owner=None, card=False)
    n = 0
    for arrival in log.entered_graveyard:
        card = plan.state.cards.get(arrival.card)
        if arrival.owner != ctx["controller"] or card is None:
            continue
        ch = chars.of(card, plan.info)
        if note_matches(sel, ch.types, ch.subtypes, ch.supertypes, ch.colors, float(ch.mana_value)):
            n += 1
    return _cmp(n, cond)


def resolution_holds(ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    """"If this is the second time this ability has resolved this turn": exactly that many (the third time isn't)."""
    got = ((ctx.get("refs") or {}).get("resolution") or {}).get("n")
    return got is not None and int(got) == int(cond["n"])
# -- end this-turn history (wave 4D) --
