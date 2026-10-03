"""-- trigger multipliers (wave 5D) -- "that ability triggers an additional time" (CR 603.2d). Researched against
CR 2026-09-25 and the Wizards rulings of the cards below.

* 603.2d: rather than simply determining that an ability has triggered, determine how many times it triggers, then
  it triggers that many times. Each such effect adds one (two Panharmonicons: three times, not four); an effect
  doesn't apply to itself or to other such effects. It refers only to triggered abilities the object has — never to
  the delayed (603.7) or reflexive (603.12) triggered abilities they create.
* Each instance is a separate triggered ability (rulings: "doesn't copy the triggered ability"): its own targets and
  modes as it's put on the stack (603.3c-d), its own choices on resolution, ordered with the controller's other
  triggers (603.3b).
* "a permanent you control": only triggered abilities of permanents (as they are, or as they last existed for an
  ability that looks back in time, 603.10a) controlled by the multiplier's controller. A spell's "when you cast"
  ability, a card in a graveyard and the designations' inherent abilities (monarch, initiative) are not permanents.
* Which multipliers count (603.10): the continuous effects that exist immediately after the event — a Panharmonicon
  entering together with a creature counts for that creature (ruling) — except for abilities that look back in time
  (603.10a: leaves-the-battlefield, dies, sacrifice, leaving a graveyard), which use the effects that existed
  immediately before it — Teysa dying together with other creatures still counts (ruling).
* Two forms:
  - by cause: "If [an artifact or creature entering / a land entering / a permanent entering / a Wizard you control
    entering / a creature dying / you casting or copying an instant or sorcery spell / a player drawing a card]
    causes a triggered ability of a permanent you control to trigger, …". The trigger event must be that event:
    an object entering (603.6a), an object dying (700.4; a "leaves the battlefield" ability triggers twice when it
    died, a "whenever you sacrifice" ability doesn't — Teysa rulings; by the same reading "whenever you create a
    token" isn't "entering"), a spell cast or copied by that player (707.10), a card drawn.
  - by source: "If a triggered ability of [a Shaman or another Wizard / a creature you control with power 2 or less
    / a legendary creature / an Ally / another Elemental / a Ninja creature / another Wolf or battle] you control
    triggers, …": the source as it is as the ability triggers (Delney rulings: a later change doesn't matter).

Refused (stay manual): "a colorless spell you control" (Echoes of Eternity: spells' abilities), "while you control six
or more Shrines" (Sanctum of All), "a creature attacking" (Isshin: whether "attacks and isn't blocked" is
"directly related to attacking" isn't settled by its rulings), and any other cause.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import ObjectRef, PendingTrigger, TriggerEvent

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

STATIC = "trigger_multiplier"
_TAIL = r", (?:that ability|it) triggers an additional time\.$"
_CAUSE = re.compile(r"^If (?P<cause>.+?) causes a triggered ability of a permanent you control to trigger" + _TAIL)
_SOURCE = re.compile(r"^If a triggered ability of (?P<src>.+?) triggers" + _TAIL)
# the trigger events each cause names (603.2d: "If [event] causes a triggered ability … to trigger")
_CAUSES = (
    (re.compile(r"^an? (?P<sel>.+?) entering$"), "enter"),
    (re.compile(r"^an? (?P<sel>.+?) dying$"), "die"),
    (re.compile(r"^you casting or copying an? (?P<sel>instant or sorcery spell)$"), "cast"),
    (re.compile(r"^a player drawing a card$"), "draw"),
)
# Not multiplied: the ids of the abilities _add creates that aren't "triggered abilities the object has" (603.2d)
DELAYED, REFLEXIVE, MADNESS = 7000, 7300, 8000
LOOK_BACK = ("die", "leave", "sacrifice", "leave_graveyard")  # 603.10a


def static_definition(text: str) -> dict[str, Any] | None:
    """The static line, or None (unread: the card stays manual)."""
    from app.rules import selectors

    m = _CAUSE.match(text.strip())
    if m is not None:
        for rx, cause in _CAUSES:
            c = rx.match(m["cause"])
            if c is None:
                continue
            sel = selectors.parse(c["sel"]) if "sel" in rx.groupindex else selectors.Selector()
            if sel is None or sel.player is not None:
                return None
            return {"kind": "static", "static": STATIC, "cause": cause, "sel": sel.key(), "effects": []}
        return None
    m = _SOURCE.match(text.strip())
    if m is None or re.search(r"\bspells?\b|\bwhile\b", m["src"]):
        return None
    keys = []
    # "a Shaman or another Wizard you control": either one ("another": not the multiplier itself)
    parts = re.split(r" or (?=another )", re.sub(r"^an? ", "", m["src"]))
    tail = re.search(r" you control(?: with .+)?$", parts[-1])
    for part in parts:
        phrase = part if part is parts[-1] or tail is None else part + tail.group(0)
        sel = selectors.parse(phrase)
        if sel is None or sel.controller != "you":
            return None
        keys.append(sel.key())
    return {"kind": "static", "static": STATIC, "source": keys, "effects": []}


def _source(plan: Plan, t: PendingTrigger) -> tuple[CardInstance, Characteristics] | None:
    """The permanent whose ability triggered, as it is, or as it last existed on the battlefield (603.10a)."""
    from app.rules.triggers import _snapshot_card

    card = plan.state.cards.get(t.source_card)
    if card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == t.source_object:
        return card, plan.ch(card)
    snap = plan.rules.lki.get(t.source_object)
    if snap is not None and snap.zone.endswith(":battlefield") and snap.card == t.source_card:
        return _snapshot_card(plan, snap)
    return None


def _definitions(plan: Plan, ch: Characteristics) -> list[dict[str, Any]]:
    from app.rules import scripts

    if "an additional time" not in (ch.oracle_text or ""):
        return []
    return [d for d in scripts.definitions(ch).values() if d.get("kind") == "static" and d.get("static") == STATIC]


def _multipliers(plan: Plan, controller: str, batch: int | None,
                 look_back: bool) -> list[tuple[CardInstance, dict[str, Any]]]:
    """The multipliers ``controller`` controlled when the event of ``batch`` happened (603.10): right after it, or
    right before it for an ability that looks back in time (603.10a). No batch: as they are now."""
    from app.rules.triggers import _snapshot_card, _zone

    r = plan.rules
    entered: dict[str, int] = {}
    if batch is not None:
        for e in r.events:
            if e.kind == "zone_change" and _zone(e.to_zone) == "battlefield" and _zone(e.from_zone) != "battlefield" \
                    and e.new_object_id:
                entered[e.new_object_id] = e.batch
    out: list[tuple[CardInstance, dict[str, Any]]] = []
    for card in plan.state.cards.values():
        if card.controller != controller or not card.zone.endswith(":battlefield") or plan.manual(card) \
                or not plan.in_game(card):
            continue
        came = entered.get(plan.oid(card))
        if batch is not None and came is not None and (came > batch or (look_back and came == batch)):
            continue  # it wasn't there yet
        out += [(card, d) for d in _definitions(plan, plan.ch(card))]
    if batch is None:
        return out
    for e in r.events:  # those that have left since (or with) the event
        if e.kind != "zone_change" or _zone(e.from_zone) != "battlefield" or _zone(e.to_zone) == "battlefield":
            continue
        if e.batch < batch or (e.batch == batch and not look_back):
            continue
        snap = r.lki.get(e.object_id or "")
        if snap is None or snap.controller != controller or plan.rules.card_mode(snap.card) == "manual":
            continue
        came = entered.get(snap.object_id)
        if came is not None and (came > batch or (look_back and came == batch)):
            continue
        card, ch = _snapshot_card(plan, snap)
        out += [(card, d) for d in _definitions(plan, ch)]
    return out


def _object(plan: Plan, ref: ObjectRef) -> tuple[CardInstance, Characteristics] | None:
    from app.rules.triggers import _object_then, _snapshot_card

    if ref.snapshot is not None:
        return _snapshot_card(plan, ref.snapshot)
    card = plan.state.cards.get(ref.card)
    if card is not None and plan.oid(card) == ref.object_id:  # (a spell on the stack, a permanent still there)
        return card, plan.ch(card)
    return _object_then(plan, ref.card, ref.object_id)


def _died(plan: Plan, ref: ObjectRef) -> bool:
    """700.4: did this object leave the battlefield for a graveyard (a token: it went there and ceased to exist)?"""
    from app.rules.triggers import _zone

    for e in plan.rules.events:
        if e.kind == "zone_change" and e.object_id == ref.object_id and _zone(e.from_zone) == "battlefield":
            snap = plan.rules.lki.get(ref.object_id)
            return _zone(e.to_zone) == "graveyard" or (e.to_zone is None and snap is not None and snap.is_token)
    return False


def _caused(plan: Plan, d: dict[str, Any], mult: CardInstance, event: TriggerEvent | None) -> bool:
    from app.rules import selectors

    if event is None:
        return False
    cause, sel = d["cause"], selectors.from_key(d["sel"])

    def any_object(extra: Any = None) -> bool:
        for ref in event.objects:
            got = _object(plan, ref)
            if got is not None and (extra is None or extra(ref)) and \
                    selectors.matches(plan, sel, got[0], got[1], mult.controller, mult.id):
                return True
        return False

    if cause == "enter":
        return event.kind == "enter" and any_object()
    if cause == "die":  # (a "leaves the battlefield" ability, when it died; never "whenever you sacrifice")
        return event.kind == "die" and any_object() or event.kind == "leave" and any_object(lambda ref: _died(plan, ref))
    if cause == "cast":  # "you casting or copying": the player who cast or copied it (601.2i, 707.10)
        return event.kind in ("cast", "copy") and event.players == [mult.controller] and any_object()
    if cause == "draw":
        return event.kind == "draw"
    return False


def count(plan: Plan, t: PendingTrigger, index: int, cause: TriggerEvent | None) -> int:
    """How many additional times this just-triggered ability triggers (603.2d)."""
    if index in (DELAYED, REFLEXIVE, MADNESS) or t.ability.get("trigger") in ("delayed", "inherent") or not t.source_object:
        return 0
    if t.ability.get("limit") == "once_each_turn":
        return 0  # ("This ability triggers only once each turn.": its additional instances would be more than once)
    source = _source(plan, t)
    if source is None:
        return 0
    from app.rules import selectors

    batch = cause.batch if cause is not None and cause.batch > 0 else None
    look_back = cause is not None and cause.kind in LOOK_BACK
    n = 0
    for mult, d in _multipliers(plan, t.controller, batch, look_back):
        if "cause" in d:
            n += _caused(plan, d, mult, cause)
        elif any(selectors.matches(plan, selectors.from_key(k), source[0], source[1], mult.controller, mult.id)
                 for k in d["source"]):
            n += 1
    return n


def _extras(plan: Plan) -> dict[str, tuple[list[PendingTrigger], int]]:
    found: dict[str, tuple[list[PendingTrigger], int]] | None = getattr(plan, "_trigger_extras", None)
    if found is None:
        found = {}
        plan._trigger_extras = found  # type: ignore[attr-defined]
    return found


def multiply(plan: Plan, t: PendingTrigger, index: int, cause: TriggerEvent | None) -> None:
    """Add this trigger's additional instances (603.2d) next to it, each a separate triggered ability."""
    extras, _ = _extras(plan).get(t.id, ([], index))
    n = count(plan, t, index, cause) - len(extras)
    for _ in range(max(n, 0)):
        import secrets

        extra = t.model_copy(update={"id": secrets.token_hex(4)}, deep=True)
        plan.rules.pending_triggers.append(extra)
        extras.append(extra)
    _extras(plan)[t.id] = (extras, index)


def joined(plan: Plan, t: PendingTrigger) -> None:
    """A "one or more" trigger's event gained another object of its batch (603.2c): its additional instances carry
    the same event, and the new object may be the one a multiplier's cause names."""
    extras, index = _extras(plan).get(t.id, ([], -1))
    for extra in extras:
        extra.event = t.event.model_copy(deep=True) if t.event is not None else None
    if index >= 0:
        multiply(plan, t, index, t.event)


def entering(plan: Plan, card_id: str) -> TriggerEvent | None:
    """The event of a permanent entering (its zone change), for an enters trigger added outside the event pass (the
    evoke sacrifice, 702.74a)."""
    from app.rules.triggers import _zone

    card = plan.state.cards.get(card_id)
    if card is None:
        return None
    oid = plan.oid(card)
    batch = next((e.batch for e in reversed(plan.rules.events) if e.kind == "zone_change" and e.new_object_id == oid
                  and _zone(e.to_zone) == "battlefield"), 0)
    return TriggerEvent(kind="enter", batch=batch, count=1, objects=[ObjectRef(card=card.id, object_id=oid, zone=card.zone)])
