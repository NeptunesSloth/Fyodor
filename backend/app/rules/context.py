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
    result ("If you do", 118.12): ``ok`` only if the whole cost was paid.

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


def bind_moved(plan: Plan, ctx: Context, name: str, before: list[ObjectRef]) -> None:
    """After an effect moved these objects: the object each became, if it went to a public zone
    (400.7j: other parts of the effect can find it there); if it went to a hidden zone or ceased
    to exist, only what it was (with its last known information, 608.2h)."""
    out = []
    was = []
    for old in before:
        card = plan.state.cards.get(old.card)
        zone = card.zone.split(":")[-1] if card is not None else None
        snap = plan.rules.lki.get(old.object_id) or old.snapshot
        was.append(old.model_copy(update={"snapshot": snap}).model_dump(mode="json"))
        if card is not None and zone not in HIDDEN_ZONES and plan.oid(card) != old.object_id:
            out.append(ObjectRef(card=card.id, object_id=plan.oid(card), zone=card.zone).model_dump(mode="json"))
        else:
            out.append(was[-1])
    refs(ctx)[name] = {"kind": "objects", "objects": out, "was": was}


def bind_players(ctx: Context, name: str, players: list[str]) -> None:
    refs(ctx)[name] = {"kind": "players", "players": list(players)}


def bind_amount(ctx: Context, name: str, n: int) -> None:
    refs(ctx)[name] = {"kind": "amount", "n": int(n)}


def bind_payment(ctx: Context, name: str, ok: bool, objects: list[ObjectRef] = ()) -> None:  # type: ignore[assignment]
    refs(ctx)[name] = {"kind": "payment", "ok": bool(ok), "objects": [o.model_dump(mode="json") for o in objects]}


# -- lookup ----------------------------------------------------------------------------------------
def _object_refs(ctx: Context, name: str, *, was: bool = False) -> list[ObjectRef]:
    """A binding's objects: the ones to act on (400.7j: after a move, the new objects), or with
    ``was`` the ones to read information from (608.2h: as they were expected to be)."""
    event = ctx.get("event") or {}
    if name == EVENT:
        raw = event.get("objects") or []
    elif name == EVENT_NEW:
        raw = event.get("new_objects") or []
    else:
        b = (ctx.get("refs") or {}).get(name) or {}
        raw = (b.get("was") if was and b.get("was") is not None else b.get("objects")) or []
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


def info(plan: Plan, ctx: Context, name: str) -> tuple[CardInstance, Characteristics] | None:
    """The first object a binding names, for reading its characteristics: as it is while it's
    still that object where it was, else as it last existed (608.2h)."""
    from app.rules.triggers import _snapshot_card  # (triggers imports effects, which imports this)

    for ref in _object_refs(ctx, name, was=True):
        card = _same(plan, ref)
        if card is not None:
            return card, plan.ch(card)
        snap = snapshot(plan, ref)
        if snap is not None:
            return _snapshot_card(plan, snap)
        card = plan.state.cards.get(ref.card)
        if card is not None:  # no last known information is kept for a card that was in a graveyard
            return card, plan.ch(card)  # or exile: it had its printed characteristics there, as now
    return None


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
