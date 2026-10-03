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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

WHO = "exiled_with"
_THE = r"(?:the exiled cards?|all cards exiled with (?:it|~))"
_BATTLEFIELD = re.compile(rf"^return {_THE} to the battlefield(?P<tapped> tapped)? under (?:its|their) owner(?:'s|s') control$")
_HAND = re.compile(rf"^return {_THE} to (?:its|their) owner(?:'s|s') hands?$")
_REFERS = re.compile(r"\bthe exiled cards?\b|\bcards? exiled with (?:it|~)\b")


def _battlefield(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "return_card", "who": WHO, "to": "battlefield", "tapped": bool(m["tapped"]), "under": "owner"}], None


def _hand(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "return_card", "who": WHO, "to": "hand"}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_BATTLEFIELD, _battlefield), (_HAND, _hand)]


def _exiles(d: dict[str, Any] | None) -> bool:
    return d is not None and any(e.get("do") == "exile" for e in d.get("effects") or [])


def link(d: dict[str, Any] | None, ability: Any, ch: Any) -> dict[str, Any] | None:
    """The definition with its link (607.2a) checked and marked; None when a reference has no single linked ability."""
    from app.rules import scripts

    if d is None:
        return None
    refers = WHO in json.dumps(d, default=str)
    others = [ab for ab in ch.abilities if ab.index != ability.index and ab.kind in ("triggered", "activated")]
    if refers:
        exiling = [ab for ab in others if re.search(r"\bexile\b", ab.text, re.IGNORECASE)]
        if len(exiling) != 1 or not _exiles(scripts.define(exiling[0], ch)):
            return None
        return d
    if ability.kind not in ("triggered", "activated") or not _exiles(d):
        return d
    referring = [ab for ab in ch.abilities if ab.index != ability.index and _REFERS.search(scripts.self_text(ab.text, ch.name))]
    if not referring:
        return d
    return {**d, "effects": [{**e, "link": True} if e.get("do") == "exile" else e for e in d["effects"]]}


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


def cards(plan: Plan, ctx: dict[str, Any]) -> list[str]:
    """The cards the linked ability exiled, while each is still that object in exile (400.7)."""
    return [oid.rsplit(".", 1)[0] for oid in plan.rules.exiled_with.get(ctx.get("source_object") or "", [])
            if _in_exile(plan, oid)]
