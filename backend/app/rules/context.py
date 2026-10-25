"""Resolution and trigger context: explicit references from one part of a resolving spell or
ability to what an earlier part (or the trigger event) established — never recovered later by
scanning the board (CR 608.2c, 608.2h, 608.2k, 603.2, 400.7).

The context is the resolving ability's ``ctx`` dict (app/rules/effects.py). It is JSON-native, so it
survives pauses for decisions (a decision's ``resume`` carries it), saves, undo/redo and replay
unchanged. Two parts:

* ``ctx["event"]`` — the TriggerEvent a triggered ability triggered on (app.game.rules_state),
  captured as it triggered. Exposed here as the binding named ``event`` (the objects the event
  happened to, as they were) and ``event.new`` (the objects they became after a zone change,
  400.7e).
* ``ctx["refs"]`` — named bindings recorded by earlier effects of this resolution. Each is a
  ``Binding`` dict:

  - ``{"kind": "objects", "objects": [ObjectRef, …], "was": [ObjectRef, …]}`` — objects an
    effect affected or moved ("destroy target creature …", "exile …", "cards exiled this way");
    for a move to a public zone the refs are the NEW objects there (400.7j), for a hidden zone
    the old ones with their last known information (608.2h). ``was`` (only after a move) keeps
    the objects as they were expected to be, for *information* about them — "its toughness",
    "its controller" — which 608.2h reads from the object in the zone it was expected in, or
    from its last known information once it left, never from the new object;
  - ``{"kind": "players", "players": [id, …]}`` — "that player";
  - ``{"kind": "amount", "n": int}`` — "that much" / "that many" of an earlier effect;
  - ``{"kind": "payment", "ok": bool, "objects": [ObjectRef, …]}`` — an optional payment's
    result ("If you do", 118.12): ``ok`` only if the whole cost was paid;
  - ``{"kind": "flag", "ok": bool}`` — the verdict of a condition, judged once as the resolution
    reached it, for the "instead" / "Otherwise" clause that belongs to it (608.2c).

Effects address bindings by string: ``who: "ref:<name>"`` (the objects, or the players),
``"ref:<name>.controller"`` / ``"ref:<name>.owner"`` (players, from last known information once the
object is gone: 608.2h; a card that isn't a permanent or spell has no controller — its owner is
used, 108.4a). Values: ``{"power" | "toughness" | "mana_value": "ref:<name>"}`` and
``{"ref_amount": "<name>"}`` (app/rules/values.py). Conditions: ``{"succeeded": "<name>"}``
(app/rules/conditions.py). Binding names are chosen by the grammar (e.g. ``e0``, ``pay0``): an
explicit identifier, so "if you do" names the payment it depends on, not "the last thing".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import ObjectRef, ObjectSnapshot

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

Context = dict[str, Any]
Binding = dict[str, Any]
PREFIX = "ref:"
EVENT = "event"
EVENT_NEW = "event.new"
EVENT_OTHER = "event_other"  # -- damage wordings (wave 6B) -- "Whenever ~ blocks a creature, … that creature"
HIDDEN_ZONES = ("hand", "library")


# -- recording -------------------------------------------------------------------------------------
def refs(ctx: Context) -> dict[str, Binding]:
    out: dict[str, Binding] = ctx.setdefault("refs", {})
    return out


def ref_of(plan: Plan, card_id: str) -> ObjectRef | None:
    """The object a card is right now, as a reference."""
    card = plan.state.cards.get(card_id)
    if card is None:
        return None
    return ObjectRef(card=card.id, object_id=plan.oid(card), zone=card.zone)


def bind_objects(plan: Plan, ctx: Context, name: str, card_ids: list[str]) -> None:
    """Record the objects these cards are now (before an effect changes them)."""
    found = [r.model_dump(mode="json") for r in (ref_of(plan, c) for c in card_ids) if r is not None]
    refs(ctx)[name] = {"kind": "objects", "objects": found}


def moved_objects(plan: Plan, before: list[ObjectRef]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """After an effect moved these objects: (the object each became, "was" = each as it was, with its last known
    information) — see ``bind_moved``."""
    out = []
    was = []
    for old in before:
        card = plan.state.cards.get(old.card)
        zone = card.zone.split(":")[-1] if card is not None else None
        snap = plan.rules.lki.get(old.object_id) or old.snapshot
        was.append(old.model_copy(update={"snapshot": snap}).model_dump(mode="json"))
        if card is not None and zone not in HIDDEN_ZONES and plan.oid(card) != old.object_id:
            out.append(ObjectRef(card=card.id, object_id=plan.oid(card), zone=card.zone).model_dump(mode="json"))
            from app.rules import (
                merged,  # (-- review (wave 18D) -- 730.3c / 712.21c: a merged permanent became all of its cards)
            )

            out += [ObjectRef(card=p, object_id=plan.oid(plan.state.cards[p]), zone=plan.state.cards[p].zone).model_dump(mode="json")
                    for p in merged.pieces(plan, [card.id])[1:] if plan.state.cards[p].zone.split(":")[-1] not in HIDDEN_ZONES]
        else:
            out.append(was[-1])
    return out, was


def bind_moved(plan: Plan, ctx: Context, name: str, before: list[ObjectRef]) -> None:
    """After an effect moved these objects: the object each became, if it went to a public zone
    (400.7j: other parts of the effect can find it there); if it went to a hidden zone or ceased
    to exist, only what it was (with its last known information, 608.2h)."""
    out, was = moved_objects(plan, before)
    refs(ctx)[name] = {"kind": "objects", "objects": out, "was": was}


def bind_players(ctx: Context, name: str, players: list[str]) -> None:
    refs(ctx)[name] = {"kind": "players", "players": list(players)}


def bind_amount(ctx: Context, name: str, n: int) -> None:
    refs(ctx)[name] = {"kind": "amount", "n": int(n)}


def bind_payment(ctx: Context, name: str, ok: bool, objects: list[ObjectRef] = (),  # type: ignore[assignment]
                 moved: tuple[list[dict[str, Any]], list[dict[str, Any]]] | None = None) -> None:
    b: Binding = {"kind": "payment", "ok": bool(ok), "objects": [o.model_dump(mode="json") for o in objects]}
    if moved is not None:  # -- if you do (wave 8C) -- what the payment moved: the new objects to act on, as they were to read
        b["moved"], b["was"] = moved
    refs(ctx)[name] = b


def bind_flag(ctx: Context, name: str, ok: bool) -> None:
    """Record a condition's verdict as this resolution reached it (608.2c): the "instead" /
    "Otherwise" text that belongs to it reads this, never asks the table again."""
    refs(ctx)[name] = {"kind": "flag", "ok": bool(ok)}


# -- lookup ----------------------------------------------------------------------------------------
def _object_refs(ctx: Context, name: str, *, was: bool = False) -> list[ObjectRef]:
    """A binding's objects: the ones to act on (400.7j: after a move, the new objects), or with
    ``was`` the ones to read information from (608.2h: as they were expected to be)."""
    event = ctx.get("event") or {}
    if name == EVENT:
        raw = event.get("objects") or []
    elif name == EVENT_NEW:
        raw = event.get("new_objects") or (event.get("objects") if event.get("kind") in ("discard", "to_graveyard") else None) or []  # (wave 51C: a discarded card is already the new object in the graveyard, 701.9a)
    elif name == EVENT_OTHER:  # -- damage wordings (wave 6B) -- the creature on the other side of a block
        raw = [event["other"]] if event.get("other") else []
    else:
        b = (ctx.get("refs") or {}).get(name) or {}
        raw = (b.get("was") if was and b.get("was") is not None else b.get("moved") or b.get("objects")) or []  # (moved: wave 8C)
    return [ObjectRef.model_validate(r) for r in raw]


def _zone_kind(zone: str) -> str:
    return zone.rsplit(":", 1)[-1]


def _same(plan: Plan, ref: ObjectRef) -> CardInstance | None:
    """The card, if it is still that object where it was (400.7). Only a zone change makes a new
    object: a change of controller moves a permanent between players' battlefield keys but it is
    still the same object (603.7c, 400.7) — so battlefield refs compare the zone's kind only."""
    card = plan.state.cards.get(ref.card)
    if card is None or plan.oid(card) != ref.object_id:
        return None
    moved = ref.zone is not None and card.zone != ref.zone
    if moved and not (_zone_kind(ref.zone or "") == "battlefield" and _zone_kind(card.zone) == "battlefield"):
        return None
    return card


def objects(plan: Plan, ctx: Context, name: str) -> list[str]:
    """The cards a binding names that can still be acted on: each only while it is still that
    object in that zone (a new object after another zone change is not it, 400.7)."""
    return [c.id for c in (_same(plan, r) for r in _object_refs(ctx, name)) if c is not None]


def snapshot(plan: Plan, ref: ObjectRef) -> ObjectSnapshot | None:
    return plan.rules.lki.get(ref.object_id) or ref.snapshot


def infos(plan: Plan, ctx: Context, name: str) -> list[tuple[CardInstance, Characteristics]]:
    """Every object a binding names, for reading its characteristics: each as it is while it's still that object where it was, else as it
    last existed (608.2h). -- event batches (wave 34C) -- "the greatest power among them": a "one or more" trigger's whole batch."""
    from app.rules.triggers import _snapshot_card  # (triggers imports effects, which imports this)

    out: list[tuple[CardInstance, Characteristics]] = []
    for ref in _object_refs(ctx, name, was=True):
        card = _same(plan, ref)
        if card is not None:
            out.append((card, plan.ch(card)))
            continue
        snap = snapshot(plan, ref)
        if snap is not None:
            out.append(_snapshot_card(plan, snap))
            continue
        card = plan.state.cards.get(ref.card)
        if card is not None:  # no last known information is kept for a card that was in a graveyard
            out.append((card, plan.ch(card)))  # or exile: it had its printed characteristics there, as now
    return out


def info(plan: Plan, ctx: Context, name: str) -> tuple[CardInstance, Characteristics] | None:
    """The first object a binding names, for reading its characteristics: as it is while it's
    still that object where it was, else as it last existed (608.2h)."""
    found = infos(plan, ctx, name)
    return found[0] if found else None


def players(plan: Plan, ctx: Context, name: str) -> list[str]:
    """Players a binding names, still in the game (800.4a). ``name`` may be ``<binding>.controller``
    or ``<binding>.owner`` for an object binding."""
    base, _, attr = name.partition(".")
    if base == EVENT and attr in ("", "players"):
        return [p for p in (ctx.get("event") or {}).get("players") or [] if p in plan.live()]
    if attr in ("controller", "owner"):
        out: list[str] = []
        for ref in _object_refs(ctx, EVENT if base == EVENT else base, was=True):
            card = _same(plan, ref)
            snap = snapshot(plan, ref)
            if card is not None:
                on_stack_or_field = card.zone == "stack" or card.zone.endswith(":battlefield")
                pid = card.controller if attr == "controller" and on_stack_or_field else card.owner  # 108.4a
            elif snap is not None:
                pid = snap.controller if attr == "controller" else snap.owner
            elif ref.card in plan.state.cards:  # (it was in a graveyard or exile: no controller, 108.4a)
                pid = plan.state.cards[ref.card].owner
            else:
                continue
            if pid in plan.live() and pid not in out:
                out.append(pid)
        return out
    b = (ctx.get("refs") or {}).get(base) or {}
    return [p for p in b.get("players") or [] if p in plan.live()]


def amount(ctx: Context, name: str) -> int:
    if name == EVENT:
        return max(0, int((ctx.get("event") or {}).get("amount") or 0))
    b = (ctx.get("refs") or {}).get(name) or {}
    return max(0, int(b.get("n") or 0))


def succeeded(ctx: Context, name: str) -> bool:
    """"If you do": whether that payment (by its binding) was made in full (118.12)."""
    b = (ctx.get("refs") or {}).get(name) or {}
    return b.get("kind") == "payment" and bool(b.get("ok"))


def probe_ok(plan: Any, ctx: Context, name: str) -> bool:
    """Did the player do the probed instruction ("did": name, app/rules/effects.py)? 118.12: "If you do" checks that they chose to pay
    or started to pay it, "regardless of what events actually occurred", so a move counts when it took an object (one still there,
    400.7), wherever it ended up: a token that is gone, a commander sent to the command zone (903.9b, 118.11). (A draw binds "did" as a
    payment when it is done, 118.12: effects._drawing.)"""
    b = (ctx.get("refs") or {}).get(name) or {}
    if b.get("kind") != "probe":
        return False
    if "hands" in b:  # (a draw probe of a save from before review 29C, paused mid-resolution: a card reached the hand)
        return any(len(plan.state.zones.get(f"{p}:hand", [])) > n for p, n in b["hands"].items())
    # -- refused modal/conditional (wave 3R1) -- sacrificed / a counter removed / a card discarded (effects._did_r1)
    if "left" in b:
        return any((card := plan.state.cards.get(cid)) is None or plan.oid(card) != oid or not card.zone.endswith(":battlefield")
                   for cid, oid in b["left"].items())
    if "control" in b:  # -- commanders (wave 50C) -- a permanent that is still that object has another controller than before (effects.gain_control)
        return any((card := plan.state.cards.get(cid)) is not None and plan.oid(card) == oid and card.controller != was
                   for cid, (oid, was) in b["control"].items())
    if "counters" in b:
        return any((card := plan.state.cards.get(cid)) is not None and plan.oid(card) == oid
                   and card.counters.get(b["counter"], 0) < n for cid, (oid, n) in b["counters"].items())
    if "counters_up" in b:  # -- if you do (wave 15C) -- a reflexive "When you do" (603.12): counters were put on it (effects._did_counters_up)
        return any((card := plan.state.cards.get(cid)) is not None and plan.oid(card) == oid
                   and card.counters.get(b["counter"], 0) > n for cid, (oid, n) in b["counters_up"].items())
    if "attached" in b:  # -- block events (wave 53C) -- 701.3a: "attach it to … If you do": what was to be attached is attached to the object it was to go to (attach_entry.attach_to)
        return any((card := plan.state.cards.get(cid)) is not None and host in (card.attached_to, card.attached_player)  # (one or more: "When one or more Equipment become attached")
                   for cid, host in b["attached"].items())
    if "hands_down" in b:
        return any(len(plan.state.zones.get(f"{p}:hand", [])) < n for p, n in b["hands_down"].items())
    return bool(b["cards"])  # (the objects taken before the move, effects._did / _picked: "to", the zone asked for, is not read)


def flag(ctx: Context, name: str) -> bool:
    """A condition's recorded verdict (an "instead" / "Otherwise" clause); False if none was recorded."""
    b = (ctx.get("refs") or {}).get(name) or {}
    return b.get("kind") == "flag" and bool(b.get("ok"))
