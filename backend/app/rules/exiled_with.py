"""-- exiled with (wave 6D) -- "When ~ leaves the battlefield, return the exiled card to the battlefield under its owner's
control." (Oblivion Ring, Fiend Hunter, Journey to Nowhere, Tidehollow Sculler, Worldgorger Dragon …)

607.2a: an activated or triggered ability printed on an object that instructs a player to exile cards and an ability
printed on it that refers to "the exiled card(s)" or to cards "exiled with [this object]" are linked: the second refers
only to cards in exile that the first put there. Researched against CR 2026-09-25.

* The exiling ability's ``exile`` effects carry ``"link": True``; as one resolves, the objects it put into exile are
  recorded under the source object (``RulesState.exiled_with``, by object id). A source that already left the
  battlefield is still that object (its last known information, 608.2h): what it exiles then is recorded under the
  object that left, whose leaves-the-battlefield ability already resolved — the cards stay in exile for good (the
  well-known Oblivion Ring sequence, 607.2a + 603.10a). A copy of the object is a different object with its own record.
* The referring ability's ``who: "exiled_with"`` finds those cards while each is still the object that was exiled
  (400.7: one that left exile and came back is a new object).
* Read only when the object has exactly one other printed ability that exiles and both are understood: anything else
  (two exiling abilities, an exiling ability the grammar doesn't read, "the exiled card's owner …") stays manual.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from app.game.rules_state import ObjectRef
from app.rules import context

if TYPE_CHECKING:
    from app.rules.plan import Plan

WHO = "exiled_with"
# (-- resolution memory (wave 22D) -- "each creature card exiled with it", "all permanent cards exiled with ~": a kind of the linked cards)
_THE = r"(?:the exiled cards?|(?:all|each) (?:(?P<spec>[\w\-]+) )?cards? exiled with (?:it|~))"
_UNDER = (r"under (?:(?P<you>your) control|(?:its|their) owner(?:'s|s') control"
          r"|the control of (?:that card's|its|their) owners?(?:'s|s')?)")  # (Trove Warden: "under the control of that card's owner")
_BATTLEFIELD = re.compile(rf"^(?:return|put) {_THE} (?:to|onto) the battlefield(?P<tapped> tapped)? {_UNDER}$")
_HAND = re.compile(rf"^(?:return|put) {_THE} (?:to|into) (?:its|their) owner(?:'s|s') hands?$")  # (wave 20D: "Put all cards exiled with ~ into their owners' hands.")
_GRAVEYARD = re.compile(rf"^put {_THE} into (?:its|their) owner(?:'s|s') graveyards?$")  # (Currency Converter, Valakut Exploration)
_REFERS = re.compile(r"\bthe exiled cards?\b|\bcards? exiled with (?:it\b|~)")  # (wave 17D: "~" has no word boundary after it)


# -- review (wave 6R) -- "Exile target creature. Return the exiled card to the battlefield under its owner's control at the
# beginning of the next end step." (Voyager Staff, Hide on the Ceiling): "the exiled card" there is what the same
# ability's own instruction exiled (608.2c), not a linked ability's (607.2a). Such an ability is read again without
# these templates (the pronoun reading it had before wave 6): ``_off_now()`` while that happens (per thread, review 29A: one thread's re-reading
# changed what another thread read, and the parse cache kept it).
def _off_now() -> bool:
    return getattr(_STATE, "off", False)


def _off(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any] | None:
    if not _off_now():
        return None
    from app.rules import language
    from app.rules.scripts import _NoMatch

    found = language.parse_sentence(m.group(0))  # ("the exiled card": the generic grammar's pronoun, language.ref)
    if found is None:
        raise _NoMatch
    return found


def _who(m: re.Match[str]) -> str:
    """The linked cards, or only those of the named kind ("each creature card exiled with it": a selector, 607.2a)."""
    from app.rules import selectors
    from app.rules.scripts import _NoMatch

    if not m["spec"]:
        return WHO
    sel = selectors.parse(f"{m['spec']} card")
    if sel is None or sel.player is not None or sel.zones or sel.controller is not None:
        raise _NoMatch
    return f"{WHO}:{sel.key()}"


def _battlefield(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    if (own := _off(m)) is not None:
        return own
    return [{"do": "return_card", "who": _who(m), "to": "battlefield", "tapped": bool(m["tapped"]), "under": "you" if m["you"] else "owner"}], None


def _hand(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    if (own := _off(m)) is not None:
        return own
    return [{"do": "return_card", "who": _who(m), "to": "hand"}], None


def _graveyard(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    if (own := _off(m)) is not None:
        return own
    return [{"do": "return_card", "who": _who(m), "to": "graveyard"}], None


# -- copied abilities (wave 18F) -- imprint (607.2a): "you may exile an instant card with mana value 2 or less from your hand" (the cost of
# an optional payment, public once in exile: 406.3), and "you may copy the exiled card" (707.12: the copy is made in exile, may be cast
# while this resolves; one not cast ceases to exist, 707.10a - so a copy not taken and a copy not cast are the same)
_IMPRINT = re.compile(r"^you may exile (?P<what>(?:an?|one) (?:[\w\-]+ )*card(?: with mana value \d+ or less)?) from your hand$")
_COPY = re.compile(rf"^(?:you may )?copy {_THE}$")


def imprint(text: str) -> list[dict[str, Any]] | None:
    """The optional payment "you may exile an instant card … from your hand" as a whole sentence (its "you may" is the payer's choice
    here, not an optional trigger's), or None."""
    from app.rules import optional_payment

    m = _IMPRINT.match(text)
    cost = optional_payment.cost_text(f"exile {m['what']} from your hand") if m else None
    return [{"do": "optional_payment", "who": "you", "cost": cost, "bind": "pay0"}] if cost else None


def _copy(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "copy_cards", "who": _who(m)}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_BATTLEFIELD, _battlefield), (_HAND, _hand), (_GRAVEYARD, _graveyard), (_COPY, _copy)]


def _exiles(d: dict[str, Any] | None) -> bool:
    # (-- champion (wave 12B) -- also a payment: "sacrifice it unless you exile another Merfolk you control", recorded by
    # optional_payment._pay)
    return d is not None and any(e.get("do") in ("exile", "exile_top", "exile_until") or e.get("exile") or _picks_to_exile(e)
                                 or (e.get("do") == "optional_payment" and str(e.get("cost")).startswith("Exile "))
                                 for e in d.get("effects") or [])


def _picks_to_exile(e: dict[str, Any]) -> bool:
    """-- resolution memory (wave 22D) -- "search your library for an artifact card, exile it" / "look at …, exile one of them" (Hoarding Dragon)"""
    return e.get("do") in ("search", "pick_looked") and e.get("to") == "exile"


def link(d: dict[str, Any] | None, ability: Any, ch: Any) -> dict[str, Any] | None:
    """The definition with its link (607.2a) checked and marked; None when a reference has no single linked ability."""
    if d is None:
        return None
    active = _STATE.__dict__.setdefault("active", set())
    key = (ch.name, ability.index)
    if key in active and not _off_now():  # (the _off_now() re-reading of the same ability is deliberate: _link)
        return None  # (two abilities that each refer to the other's exile: no single linked ability, 607.2a)
    active.add(key)
    try:
        return _link(d, ability, ch)
    finally:
        active.discard(key)


def _link(d: dict[str, Any], ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    refers = WHO in json.dumps(d, default=str) or "linked_cards" in json.dumps(d, default=str)
    others = [ab for ab in ch.abilities if ab.index != ability.index and ab.kind in ("triggered", "activated")]
    if refers and _exiles(d):  # -- review (wave 6R) -- its own exiled card (see _off_now)
        if _off_now():
            return None  # (-- wave 22D -- read again without the templates and it still refers to a linked card: not read)
        _STATE.off = True
        try:
            return scripts.define(ability, ch)
        finally:
            _STATE.off = False
    if refers:
        exiling = [ab for ab in others if re.search(r"\bexile\b", ab.text, re.IGNORECASE)]
        from app.rules import hideaway

        if hideaway.exiles(ch):  # -- hideaway (wave 29D) -- 702.75a: the keyword is the exiling ability (and the only one: 607.2a)
            return None if exiling else hideaway.each(d)
        if len(exiling) != 1 or not _exiles(scripts.define(exiling[0], ch)):
            return None
        return d
    if ability.kind not in ("triggered", "activated") or not _exiles(d):
        return d
    referring = [ab for ab in ch.abilities if ab.index != ability.index and _REFERS.search(scripts.self_text(ab.text, ch.name))]
    if not referring:
        return d
    return {**d, "effects": [{**e, "link": True} if e.get("do") in ("exile", "exile_top", "exile_until") or e.get("exile") or _picks_to_exile(e) else e
                                     for e in d["effects"]]}


# -- resolution memory (wave 22D) -- 607.2a: a referring ability that does more than return / put the cards ("the exiled card's owner
# creates an X/X token, where X is the mana value of the exiled card": Skyclave Apparition, Hoarding Dragon, Unidentified Hovership)
# reads the linked cards through a leading pseudo-instruction ``linked_cards`` that binds them (as the objects they were put into
# exile as: their owner and mana value are the same wherever they have gone since, 608.2h), so the ordinary pronoun grammar
# ("the exiled card", "its owner", "that card's mana value") finds them. ``linked()`` is true while such an ability is read.
_STATE = threading.local()  # (per thread: games may parse cards concurrently)
_EXILES = re.compile(r"\bexiles?\b|\bexiling\b", re.IGNORECASE)


def linked() -> bool:
    return getattr(_STATE, "on", False)


@contextmanager
def reading(ability: Any, text: str) -> Iterator[None]:
    """While the ability (its text, ~ for itself) is read: does it only refer to what another ability exiled?"""
    _STATE.on = ability.kind in ("triggered", "activated") and _REFERS.search(text) is not None and _EXILES.search(text) is None
    try:
        yield
    finally:
        _STATE.on = False


def linked_cards(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Bind the cards the linked ability exiled (a token that was exiled has ceased to exist, 111.8: not found)."""
    if e.get("as"):
        found = [ObjectRef(card=cid, object_id=oid, zone=f"{plan.state.cards[cid].owner}:exile")
                 for oid in plan.rules.exiled_with.get(ctx.get("source_object") or "", []) if (cid := oid.rsplit(".", 1)[0]) in plan.state.cards]
        context.refs(ctx)[e["as"]] = {"kind": "objects", "objects": [r.model_dump(mode="json") for r in found]}
    return True


PRIMITIVES = {"linked_cards": linked_cards}


def record(plan: Plan, ctx: dict[str, Any], cards: list[str]) -> None:
    """The objects these cards became in exile, under the source object (as it is, or was: 608.2h)."""
    key = ctx.get("source_object")
    if not key:
        return
    kept = [oid for oid in plan.rules.exiled_with.get(key, []) if _in_exile(plan, oid)]
    now = [plan.oid(c) for c in cards if c in plan.state.cards and plan.state.cards[c].zone.endswith(":exile")]
    plan.rules.exiled_with[key] = [*kept, *(o for o in now if o not in kept)]


def _in_exile(plan: Plan, oid: str) -> bool:
    cid = oid.rsplit(".", 1)[0]
    card = plan.state.cards.get(cid)
    return card is not None and card.zone.endswith(":exile") and plan.oid(cid) == oid


def cards(plan: Plan, ctx: dict[str, Any], who: str = WHO) -> list[str]:
    """The cards the linked ability exiled, while each is still that object in exile (400.7); only those of the kind
    "exiled_with:<selector>" names ("each creature card exiled with it")."""
    found = [oid.rsplit(".", 1)[0] for oid in plan.rules.exiled_with.get(ctx.get("source_object") or "", []) if _in_exile(plan, oid)]
    if ":" not in who:
        return found
    from app.rules import selectors

    sel = selectors.from_key(who.split(":", 1)[1])
    return [c for c in found if selectors.matches(plan, sel, plan.state.cards[c], plan.ch(plan.state.cards[c]), ctx["controller"],
                                                  ctx.get("source_card"))]
