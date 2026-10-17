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
    log = rules.turn_log if rules.turn_log.turn == n else TurnLog(turn=n)
    # -- review (wave 24A) -- 608.2h: a resolution that counts what it just did ("sacrifice any number of creatures, then draw a
    # card for each that died this turn") reads the facts of events no trigger collection has noted yet, in a scratch copy
    pending = [e for e in rules.events if e.batch > rules.trigger_batch]
    if not pending:
        return log
    scratch = TurnLog(turn=n)
    note_events(plan, pending, into=scratch)
    return log.model_copy(update={"facts": [*log.facts, *scratch.facts]}) if scratch.facts else log


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


# -- history (wave 22E) -- where a permanent entered from (Entry.from_zone, recorded as it entered: 603.2, 603.4)
def entered_from(zone: str | None, want: str, you: str) -> bool:
    """Did a permanent enter from this zone ("graveyard" | "your graveyard" | "exile" | "your hand" …)? ``zone`` is the zone key it left
    ("<owner>:graveyard", "stack"); "your" is the ability controller's zone."""
    if not zone:
        return False
    owner, _, name = zone.rpartition(":")
    if want == "not_hand":  # -- trigger from (wave 30F) -- "enters from anywhere other than your hand" (a token created enters from nowhere: ``zone`` None)
        return name != "hand"
    if want.startswith("your "):
        return name == want[5:] and owner == you
    return name == want


def entry_came_from(plan: Plan, object_id: str | None, want: str, you: str) -> bool:
    """"if it entered from your graveyard": the entry of the object this turn."""
    return any(e.object_id == object_id and entered_from(e.from_zone, want, you) for e in reversed(log_for(plan).entered))
# -- end history (wave 22E) --


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
    # (-- this-turn state (wave 33D) -- "other": "event": another than the object a trigger's event is about, "if that player had another
    # land enter the battlefield under their control this turn" (Tunnel Ignus: lands that entered together count, 603.2)
    from app.rules import context

    other = {r.object_id for r in context._object_refs(ctx, context.EVENT)} if cond.get("other") == "event" else {_source_object(plan, ctx)}
    for e in log.entered:
        if (e.controller != me) != (cond.get("who") == "opponent") \
                or (cond.get("other") and e.object_id in other):  # ("who": wave 4D)
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
    from app.rules import (
        spell_grants,  # -- spell grants (wave 28C) -- "the next spell you cast this turn": used up by this cast
    )

    spell_grants.consume(plan, card, plan.ch(card))
    log = turn_log_now(plan.state)
    if log is None:
        return
    ch = plan.ch(card)
    record = plan.rules.payments.get(plan.oid(card))
    log.casts.append(CastNote(player=card.controller, object_id=plan.oid(card), types=sorted(ch.types),
                              subtypes=sorted(ch.subtypes), supertypes=sorted(ch.supertypes), colors=sorted(ch.colors),
                              mv=float(_stack_mv(card, ch)), cast_from=record.cast_from if record is not None else None,
                              alt=record.alternative if record is not None else None, x_cost="{X}" in ch.mana_cost))


def _stack_mv(card: Any, ch: Any) -> int:
    """-- review (wave 5R) -- a spell's mana value on the stack counts its X (202.3e): "a spell with mana value 5 or
    greater" cast this turn."""
    from app.rules.stack_interaction import mana_value

    return mana_value(card, ch)


def note_events(plan: Plan, events: list[Any], into: TurnLog | None = None) -> None:
    """The facts of a batch of events (app/rules/triggers.py reads the same events for triggers), kept for the turn
    (``into``: a scratch log instead, for events not yet looked at — review 23C)."""
    from app.game.rules_state import TurnFact, turn_log_now
    from app.rules.triggers import _facts

    log = into if into is not None else turn_log_now(plan.state)
    if log is None:
        return
    for e in events:
        if e.kind not in ("zone_change", "sacrificed", "damage", "counters", "milled") or e.turn != plan.state.turn.number:
            continue
        for kind, obj, ch, player, info in _facts(plan, e, {"cast_from": {}}):
            what: dict[str, Any] = {"types": sorted(ch.types), "subtypes": sorted(ch.subtypes),
                                    "supertypes": sorted(ch.supertypes)} if ch is not None else {}
            if kind == "create_token" and obj is not None:  # 111.2: the player who creates a token is its owner
                log.facts.append(TurnFact(kind="token", player=obj.owner, object_id=info.get("oid"), token=True, **what))
            elif kind == "discard" and not (info.get("to") or "").endswith(":graveyard"):
                continue  # (review 23D: a discard put elsewhere instead was noted as it was replaced, note_discards)
            elif kind in ("discard", "sacrifice") and player is not None and obj is not None:
                log.facts.append(TurnFact(kind=kind, player=player, object_id=info.get("oid"), token=obj.is_token, batch=e.batch if kind == "discard" else 0,
                                          **what))  # (-- trigger other (wave 36A) -- the batch of a discard: "for the first time each turn")
            elif kind == "dealt_damage" and obj is None and info.get("recipient"):  # a player was dealt damage (120.3)
                log.facts.append(TurnFact(kind="damage", player=info["recipient"], amount=int(info.get("amount") or 0),
                                          combat=bool(info.get("combat")), object_id=info.get("source_oid"), batch=e.batch))  # (wave 39B: batch)
            elif kind == "dealt_damage" and obj is not None and info.get("oid") and int(info.get("amount") or 0) > 0:
                # -- damage history (wave 6B) -- a permanent was dealt damage (120.3): "creature that was dealt damage
                # this turn", "creature that dealt damage this turn" (app/rules/damage_history.py)
                log.facts.append(TurnFact(kind="damaged", player=player or obj.controller, object_id=info["oid"],
                                          amount=int(info["amount"]), combat=bool(info.get("combat")),
                                          source=info.get("source_oid"), batch=e.batch, excess=int(info.get("excess") or 0),
                                          **what))  # (wave 39B: batch, excess — 120.10)
            elif kind == "deal_damage" and info.get("recipient") and log.facts and log.facts[-1].kind == "damage":
                # its source, as it was as it dealt that damage (608.2i)
                log.facts[-1].source_types, log.facts[-1].source_supertypes = what["types"], what["supertypes"]
                log.facts[-1].source_subtypes = what["subtypes"]  # (wave 17C: prowl, 702.76a)
                log.facts[-1].source_controller = obj.controller if obj is not None else None
                log.facts[-1].source_commander = obj is not None and obj.commander_key is not None  # (wave 43D: freerunning, 702.173a; 903.3)
            elif kind == "deal_damage" and info.get("other_oid") and log.facts and log.facts[-1].kind == "damaged" \
                    and log.facts[-1].object_id == info["other_oid"] and log.facts[-1].source == info.get("oid"):
                # -- trigger damage (wave 39B) -- its source, as it was as it dealt that damage to a permanent (608.2i): "a Giant, Wizard, or spell you
                # controlled dealt damage to it this turn" (Aegar) — a spell is a source on the stack that isn't an ability (120.1)
                last = log.facts[-1]
                last.source_subtypes, last.source_controller = what["subtypes"], obj.controller if obj is not None else None
                last.source_types, last.source_supertypes = what["types"], what["supertypes"]
                last.source_spell = obj is not None and obj.zone == "stack" and obj.ability is None
            elif kind == "mill" and obj is not None:  # -- free cast (wave 40D) -- 701.17a: this object was milled ("cards in your graveyard that were milled this turn", Raul)
                log.facts.append(TurnFact(kind="mill", player=player or obj.owner, object_id=info.get("oid"), **what))
            elif kind == "to_exile" and player is not None:  # -- this-turn state (wave 33D) -- 400.1: a card put into exile from another zone (a token is no card)
                log.facts.append(TurnFact(kind="exile", player=player, object_id=info.get("oid"), **what))
            elif kind == "counters_put" and player is not None:
                log.facts.append(TurnFact(kind="counters", player=player, object_id=info.get("oid"),
                                          amount=int(info.get("amount") or 0), counter=info.get("counter"),
                                          actor=info.get("actor"), batch=e.batch, **what))  # (wave 39B: batch)


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


def note_selector_ok(sel: Any, spell: bool = False) -> bool:
    from dataclasses import fields

    from app.rules.selectors import Selector

    blank = Selector()
    for f in fields(sel):
        if f.name not in _NOTE_FIELDS and getattr(sel, f.name) != getattr(blank, f.name):
            return False
    # (-- history (wave 22E) -- a spell's note also records whether its cost has {X}, and "outlaw"-style subtype lists answer from the subtypes)
    extras_ok = {"all_types", "historic", *(("x_cost",) if spell else ())}  # (wave 30T: 700.6 historic is answered from the recorded types)
    return all(e in extras_ok or e.startswith("subtype_any:") for e in sel.extras) \
        and all(c[0] == "mv" and isinstance(c[2], int) for c in sel.compare)


def note_matches(sel: Any, types: Any, subtypes: Any = (), supertypes: Any = (), colors: Any = (), mv: float = 0,
                 token: bool | None = None, x_cost: bool | None = None) -> bool:
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
    if "x_cost" in sel.extras and not x_cost:
        return False
    for extra in sel.extras:  # (wave 22E) "outlaw": any of these subtypes
        if extra.startswith("subtype_any:") and not set(extra[12:].split("|")) & subtypes:
            return False
    if "historic" in sel.extras and not ("Artifact" in types or "Legendary" in supertypes or "Saga" in subtypes):
        return False  # -- spell grants (wave 30T) -- 700.6: "the first historic spell you cast each turn" (Peri Brown)
    ops = {">=": float.__ge__, "<=": float.__le__, "==": float.__eq__}
    return all(ops[op](float(mv), float(n)) for _, op, n in sel.compare)


def _players(plan: Plan, me: str, who: str | None) -> set[str]:
    """Whose actions count: "you", "opponent" (any one of them), "any" — departed players' too (800.4a doesn't erase
    what happened)."""
    return {me} if who in (None, "you") else set(plan.state.players) - {me} if who == "opponent" else set(plan.state.players)


def _cmp(got: int, cond: dict[str, Any]) -> bool:
    n = int(cond.get("n", 1))
    return got == n if cond.get("op") == "==" else got >= n


def _cast_counts(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any], log: TurnLog) -> dict[str, int]:
    """Spells cast this turn (601.2i) of a kind, per caster, as they were cast — resolved, countered or still on the stack (608.2i)."""
    from app.rules import selectors

    sel = selectors.from_key(cond["sel"])
    me_src = _source_object(plan, ctx) if cond.get("other") else None
    # -- spell copies (wave 31D) -- "for each other instant and sorcery spell you've cast before it this turn" (Thousand-Year Storm): the
    # spells cast before the one a cast trigger is about (601.2i, in the order they were cast), not those cast after it
    from app.rules import context

    stop = {r.object_id for r in context._object_refs(ctx, context.EVENT)} if cond.get("before") else set()
    per: dict[str, int] = {}
    for note in log.casts:
        if note.object_id in stop:
            break
        if cond.get("from") and note.cast_from != cond["from"]:
            continue
        if me_src is not None and me_src in (note.object_id, note.became):
            continue
        if note_matches(sel, note.types, note.subtypes, note.supertypes, note.colors, note.mv, x_cost=note.x_cost):
            per[note.player] = per.get(note.player, 0) + 1
    return per


def _cast(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any], log: TurnLog) -> bool:
    return _per_player(plan, ctx, cond, _cast_counts(plan, ctx, cond, log))


def cast_amount(plan: Plan, ctx: dict[str, Any], v: dict[str, Any]) -> int:
    """-- this-turn history (wave 30R) -- "the number of instant and sorcery spells you've cast this turn" / "noncreature spells they've cast"
    (the trigger's player) / "spells cast this turn" (anyone's) / "other" than the spell or permanent counting them: the same notes the
    conditions read (601.2i), counted as the effect is carried out (608.2h)."""
    from app.rules import context

    if v.get("greatest"):  # -- this-turn state (wave 33D) -- Rootha: "the greatest mana value among instant and sorcery spells you've cast this turn"
        from app.rules import selectors

        sel = selectors.from_key(v["sel"])
        return max((int(n.mv) for n in log_for(plan).casts if n.player == ctx["controller"] and note_matches(
            sel, n.types, n.subtypes, n.supertypes, n.colors, n.mv, x_cost=n.x_cost)), default=0)
    per = _cast_counts(plan, ctx, v, log_for(plan))
    who = v["spells_cast"]
    return sum(per.values()) if who == "all" else sum(per.get(p, 0) for p in ([ctx["controller"]] if who == "you" else context.players(plan, ctx, context.EVENT)))


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
        if f.kind != cond["kind"] or (cond.get("counter") and f.counter != cond["counter"]) or (cond.get("excess") and f.excess <= 0):  # (wave 39B: 120.10)
            continue
        if sel is not None and not note_matches(sel, f.types, f.subtypes, f.supertypes, (), 0, f.token):
            continue
        if cond.get("self") and f.object_id != _source_object(plan, ctx):  # (wave 16D) "a counter was put on ~ this turn"
            continue
        if cond.get("by") == "you" and f.actor != ctx["controller"]:  # (wave 16D) "you put a counter on a creature this turn"
            continue
        if cond.get("of_self") and f.source != _source_object(plan, ctx):  # (wave 33D) "an Assassin crewed it this turn": the Vehicle is the source
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
        if src and not (set(src["types"]) <= set(f.source_types) and set(src["supertypes"]) <= set(f.source_supertypes)
                        and set(src.get("subtypes", ())) <= set(f.source_subtypes)):  # (wave 33D: "dealt combat damage by a Zombie")
            continue
        if cond.get("by_self") and f.object_id != _source_object(plan, ctx):  # ("~ dealt damage to an opponent")
            continue
        per[f.player] = per.get(f.player, 0) + f.amount
    return any(per.get(p, 0) >= int(cond.get("n", 1)) for p in _players(plan, ctx["controller"], cond.get("who")))


# -- this-turn state (wave 33D) -- a fact about ONE object this turn ("it was dealt damage", "it was blocked", "that creature entered"): found by
# its rules object id, so a creature that has died since is still read as it was (603.10a, 608.2h; 400.7: a new object is not it)
def object_ids(plan: Plan, ctx: dict[str, Any], who: str) -> set[str]:
    """The object ids a condition's object word names: the source, the trigger event's object, an earlier instruction's or a target."""
    from app.rules import context

    if who == "self":
        oid = _source_object(plan, ctx)
        return {oid} if oid else set()
    if who == "event" or who.startswith("ref:"):
        return {r.object_id for r in context._object_refs(ctx, context.EVENT if who == "event" else who[4:], was=True)}
    if who == "target" or who.startswith("target:"):
        from app.rules.effects import target_refs  # (effects imports this module)

        return {t["object_id"] for t in target_refs(ctx, who) if t.get("object_id")}
    return set()


def _object_history(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any], log: TurnLog) -> bool:
    """damaged: it was dealt ``n`` or more damage (120.3: dealt, so not prevented; ``combat``: only combat / noncombat), blocked: it became
    blocked when blockers were declared (509.1g), attacked_or_blocked (508.1, 509.1g), entered: it entered the battlefield, dealt_player: it
    dealt ``n`` or more damage to a player (``to`` "event": to the player the trigger's event is about). No such object: the test fails (608.2b)."""
    from app.rules import context

    ids = object_ids(plan, ctx, cond["object"])
    if not ids:
        return False
    what, n = cond["what"], int(cond.get("n", 1))

    def total(kind: str, key: Any) -> int:
        return sum(f.excess if cond.get("excess") else f.amount for f in log.facts
                   if f.kind == kind and key(f) and ("combat" not in cond or f.combat == cond["combat"]))  # (wave 39B: excess, 120.10)

    if what == "entered":
        got = any(e.object_id in ids for e in log.entered)
    elif what == "blocked":
        got = any(a in ids for attacked in log.blocks.values() for a in attacked)
    elif what == "died":  # -- counters (wave 41A) -- 700.4: it was put into a graveyard from the battlefield (Departure.to)
        got = any(d.object_id in ids and d.to == "graveyard" for d in log.left)
    elif what == "enlisted":  # -- trailing & intervening ifs (wave 38A) -- 702.154a: in this combat phase (500.8), fixed once it was (603.4: still so as it resolves)
        got = any(log.enlisted.get(i) == plan.rules.combats for i in ids)
    elif what == "attacked_or_blocked":
        got = bool(ids & set(log.blockers)) or any(a in ids for attacking in log.attackers.values() for a in attacking)
    elif what == "damaged":
        got = total("damaged", lambda f: f.object_id in ids) >= n
    elif what == "damaged_by":  # -- trigger damage (wave 39B) -- a Giant, Wizard or spell you controlled dealt it damage (the source as it was, 608.2i)
        got = any(f.kind == "damaged" and f.object_id in ids and f.amount > 0 and f.source_controller == ctx["controller"]
                  and ((cond.get("spell") and f.source_spell) or set(cond.get("subtypes", ())) & set(f.source_subtypes)) for f in log.facts)
    elif what == "dealt_player":
        to = set(context.players(plan, ctx, context.EVENT)) if cond.get("to") == "event" else None
        got = total("damage", lambda f: f.object_id in ids and (to is None or f.player in to)) >= n
    else:
        raise ValueError(f"unknown object history {cond!r}")
    return got != bool(cond.get("negate"))


def _cast_nth(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any], log: TurnLog) -> bool:
    """"It's the second creature spell you cast this turn" (Vengevine: the spell a cast trigger is about), "if it was the second spell you cast
    this turn" (Codespell Cleric: the spell this permanent was, 608.3): the nth spell of its kind its caster cast, counted in the order they
    were cast (601.2i) — fixed once it was cast, so later casts don't change it as the ability resolves (603.4)."""
    from app.rules import selectors

    sel = selectors.from_key(cond["sel"])
    ids, n = object_ids(plan, ctx, cond["object"]), 0
    for note in log.casts:
        subject = note.object_id in ids or (note.became is not None and note.became in ids)
        if note.player != ctx["controller"] or not note_matches(sel, note.types, note.subtypes, note.supertypes, note.colors, note.mv,
                                                                x_cost=note.x_cost):
            if subject:
                return False  # (the spell isn't of that kind)
            continue
        n += 1
        if subject:
            return n == int(cond["n"])
    return False
# -- end this-turn state (wave 33D) --


def _source_damage(ctx: dict[str, Any], cond: dict[str, Any], log: TurnLog) -> bool:
    """-- this-turn state (wave 42B) -- "if a source you controlled dealt 5 or more damage this turn" (Dragon Cultist): one source's total, whoever or
    whatever it hurt and in however many events (a double striker's two steps, damage to a player and to a blocker: 120.3), counting only damage that was
    dealt (a prevented point never was). The source need only have been under your control as it dealt it (608.2i: the ruling for Dragon Cultist); the log
    keeps the source of damage to a player (``damage`` facts) and to a permanent (``damaged`` facts) by its object, so a source that has left still counts."""
    per: dict[str, int] = {}
    for f in log.facts:
        src = f.object_id if f.kind == "damage" else f.source if f.kind == "damaged" else None
        if src is not None and f.amount > 0 and f.source_controller == ctx["controller"]:
            per[src] = per.get(src, 0) + f.amount
    return any(n >= int(cond["n"]) for n in per.values())


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


def _freerunning(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any], log: TurnLog) -> bool:
    """-- cast keywords (wave 43D) -- 702.173a: a player was dealt combat damage this turn by a creature that, at the time it dealt that damage, was
    an Assassin creature or a commander under your control (the source as it was then, 608.2i: it may be gone now — Eagle Vision's ruling)."""
    return any(f.kind == "damage" and f.combat and f.amount > 0 and f.source_controller == ctx["controller"]
               and (f.source_commander or ("Creature" in f.source_types and "Assassin" in f.source_subtypes)) for f in log.facts)


def _departed(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any], log: TurnLog) -> bool:
    """Permanents that left the battlefield (or died, 700.4) this turn, as they last existed there (608.2i, 603.10a)."""
    from app.rules import selectors
    from app.rules.triggers import _snapshot_card

    sel = selectors.from_key(cond["sel"])
    me = ctx["controller"]
    src = _source_object(plan, ctx) if cond.get("other") else None
    skip = {src}
    spell = plan.state.cards.get(ctx.get("source_card") or "")
    if src is not None and spell is not None and spell.zone == "stack" and spell.ability is None:
        # (-- review 38 -- a spell's "another creature": one other than its target, "Destroy target creature. If another creature died this turn, draw a card."
        # (Chain Assassination ruling 2024-07-05: the target's own death doesn't count))
        skip |= {t.get("object_id") if isinstance(t, dict) else getattr(t, "object_id", None) for t in ctx.get("targets") or []}
    n = 0
    for d in log.left:
        if (cond.get("died") and d.to != "graveyard") or (cond.get("to") and d.to != cond["to"]) or d.object_id in skip:
            continue  # (-- this-turn history (wave 30R) -- "to": a permanent put into a hand from the battlefield)
        if cond.get("who") and (d.controller == me) != (cond["who"] == "you"):
            continue
        snap = plan.rules.lki.get(d.object_id)
        if snap is None or (cond.get("owner") == "you" and snap.owner != me):
            continue
        _, ch = _snapshot_card(plan, snap)
        types = d.types if d.types is not None else ch.types
        if cond.get("not_named") and named_like(plan, ctx, ch):
            continue
        if note_matches(sel, types, ch.subtypes, ch.supertypes, ch.colors, float(ch.mana_value), snap.is_token):
            n += 1
    return _cmp(n, cond)


def named_like(plan: Plan, ctx: dict[str, Any], ch: Any) -> bool:
    """-- this-turn state (wave 42B) -- 201.2a: does this object (as it last existed) share a name with the condition's source? "A creature not named
    Ebondeath, Dracolich died this turn" reads the name it had on the battlefield — a copy of Ebondeath that died is named so, a face-down creature
    (708.2a) and a token with another name are not — whether or not the source was in the graveyard yet (the ruling for Ebondeath)."""
    from app.rules import card_names

    src = plan.state.cards.get(ctx.get("source_card") or "")
    return src is not None and card_names.share(ch, plan.ch(src))


_WAVE_4D: dict[str, Any] = {
    "tokens": lambda plan, ctx, cond, log: _facts_holds(plan, ctx, {**cond, "kind": "token"}, log),
    "attackers": lambda plan, ctx, cond, log: len(log.attackers.get(ctx["controller"], [])) >= int(cond.get("n", 1)),
    "cast": _cast,
    "facts": _facts_holds,
    "damage": _damage,
    "prowl": _prowl,
    "freerunning": _freerunning,  # (wave 43D)
    "source_damage": lambda plan, ctx, cond, log: _source_damage(ctx, cond, log),  # (wave 42B)
    "object": _object_history,  # (wave 33D)
    "cast_nth": _cast_nth,  # (wave 33D)
    "departed": _departed,
    "lands": lambda plan, ctx, cond, log: plan.rules.lands_this_turn(ctx["controller"], plan.state.turn.number) >= int(cond.get("n", 1)),
    "resolution": lambda plan, ctx, cond, log: resolution_holds(ctx, cond),
    "activations": lambda plan, ctx, cond, log: bool(cond.get("key")) and plan.rules.ability_uses.get(
        f"{cond['key']}:t{plan.state.turn.number}", 0) >= int(cond["n"]),
    "attackers_power": lambda plan, ctx, cond, log: plan.rules.attack_power.get(ctx["controller"], 0) >= int(cond["n"]),
    "self_attacked": lambda plan, ctx, cond, log: _self_attacked(plan, ctx, cond, log),
    "graveyard_cards": lambda plan, ctx, cond, log: _graveyard_cards(plan, ctx, cond, log),
    "rolled": lambda plan, ctx, cond, log: log.rolled.get(ctx["controller"], 0) >= int(cond["n"]),  # -- dice (wave 24B) --
}


def _self_attacked(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any], log: TurnLog) -> bool:
    """508.1: the source was declared as an attacker this turn, or (``combat``, wave 38A) in the combat phase this is — "Tolsimir attacked this
    combat" is still so if it left combat since (603.4), but not in another combat of the turn (500.8)."""
    oid = _source_object(plan, ctx)
    if cond.get("combat"):
        from app.game.state import COMBAT_PHASES

        return oid is not None and plan.state.turn.phase in COMBAT_PHASES and log.declared.get(oid) == plan.rules.combats
    return oid in {a for v in log.attackers.values() for a in v}


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
    if kind == "life_greater":  # -- this-turn state (wave 42B) -- 119.3: the larger of the life you gained and the life you lost this turn (Willowdusk)
        return max(log.gained.get(me, 0), log.lost.get(me, 0))
    if kind == "drew":
        return log.drew.get(me, 0)
    if kind == "died":
        return sum(1 for d in log.left if (v.get("left") or d.to == v.get("to", "graveyard")) and (snap := plan.rules.lki.get(d.object_id)) is not None
                   and (v.get("who") != "you" or d.controller == me)  # (-- X actions (wave 9A) -- "under your control")
                   and (v.get("who") != "opponent" or d.controller != me)  # (wave 41B: "exiled under your opponents' control", ``to``: the zone it went to)
                   and (v.get("owner") != "you" or snap.owner == me)  # (-- this-turn history (wave 30R) -- "your graveyard": 400.3)
                   and _departed_matches(plan, selectors.from_key(v["sel"]), d, snap))
    if kind == "entered":  # -- tokens (wave 38B) -- "creatures you had enter the battlefield under your control this turn": those that left too (608.2i)
        return entered(plan, ctx, {"sel": v["sel"]}, log)
    if kind == "attackers":  # -- cost self reduction (wave 16F) -- each creature declared as an attacker this turn, once (508.1)
        return len({a for p, ids in log.attackers.items() if v.get("who") != "you" or p == me for a in ids})
    if kind in ("tokens", "sacrificed", "discarded"):  # -- X sized by a count (wave 19F) -- one fact per token / permanent (111.2, 701.21a)
        return sum(1 for f in log.facts if f.kind == {"tokens": "token", "sacrificed": "sacrifice", "discarded": "discard"}[kind]
                   and (f.player == me or v.get("who") == "any"))  # (wave 21F: "who": "any" — each permanent sacrificed, whoever did it)
    if kind == "opponents_attacked":  # -- this-turn state (wave 33D) -- 508.6: the opponents (still in the game, 800.4a) you declared attackers against
        return len({p for a in log.attackers.get(me, []) for p in log.attacked_who.get(a, []) if p != me and p in plan.live()})
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
            return sum(1 for p in opponents if any(f.kind == "damage" and f.player == p and f.amount > 0 and (f.combat or not v.get("combat"))
                                                   and (not v.get("by") or f.object_id == ctx.get("source_object") or v["by"] in f.source_subtypes)  # (wave 41B: ~ or a <type>)
                                                   for f in log.facts))
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
