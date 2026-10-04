"""Mana that remembers where it came from (wave 18B), researched against CR 2026-09-25.

106.3: the source of mana is the permanent, spell or ability that produced it. 106.6: an ability that produces mana may restrict how it
can be spent, give the spell or ability it is spent on an additional effect, or create a delayed trigger for when it is spent; none of
that changes the mana's type. 106.6a: a replacement that adds mana applies the restriction to all of it. 107.4h: {S} is paid with one
mana of any type produced by a snow source. 106.12: "tap for mana" means a mana ability with {T} in its cost.

The plain pool (``PlayerState.mana``) stays one count per type: mana with no restriction, no rider and no source a rule asks about
(old saves load as it is). Every other mana is a :class:`~app.game.state.ManaUnit` in ``PlayerState.mana_units``: its type, the source
object, the source's types / subtypes / supertypes when it produced it (``tags``), its spending restriction (``only``, read by
``casting.spend_allowed``) and its riders. A unit pays like a source that is already tapped: ``unit_sources`` turns the units that may
pay for a purpose into pseudo-sources the mana solver uses (``unit:<id>``), so snow units pay {S}, restricted units are used first, and the
manual payer needs no new decision. ``settle`` turns a solved payment into the pool changes and the provenance recorded on the spell's
``PaymentRecord`` ("if mana from a Treasure was spent to cast it", "for each {S} spent to cast it", "when that mana is spent …").

Mana produced by a tapped source and not spent (a restricted source paying less than it makes) stays in the pool as a unit that keeps
the restriction (106.6: it is still restricted). Not tracked: the source of mana from a plain land tapped by hand (a basic land
isn't one of the ``INTERESTING`` tags), so "mana produced by basic lands" restrictions stay manual.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.rules import mana as M

if TYPE_CHECKING:
    from app.game.state import GameState, ManaUnit
    from app.rules.casting import Purpose
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

PREFIX = "unit:"
# Sources whose mana a rule asks about later: snow ({S}, 107.4h), Treasures, "mana from an artifact / a creature / a Desert / a Cave".
INTERESTING = frozenset({"Snow", "Treasure", "Artifact", "Creature", "Desert", "Cave"})
# A game remembers the source of plain mana only if one of its cards asks (so a table without such cards keeps its one plain pool).
ASKS = re.compile(r"\{S\}|\bmana (?:from|produced by|of a snow)\b|\bsnow (?:mana|source)", re.IGNORECASE)


def tracking(plan: Plan) -> bool:
    """Does any card of this game ask where mana came from ("mana from a Treasure was spent", {S}, "mana produced by creatures")?"""
    from app.rules import characteristics as chars

    r = plan.rules
    if r.provenance is None:
        r.provenance = any(ASKS.search(chars.of(c, plan.info).oracle_text) for c in plan.state.cards.values())
    return r.provenance


def tags_of(ch: Characteristics) -> list[str]:
    """What a source was when it produced mana: its supertypes, types and subtypes (last known information, 608.2h)."""
    return sorted(ch.supertypes | ch.types | ch.subtypes)


def needs_unit(plan: Plan, only: str | None, riders: list[dict[str, Any]] | tuple[Any, ...], tags: list[str]) -> bool:
    """Does mana with this restriction, these riders and this source have to be remembered?"""
    return bool(only or riders or (INTERESTING & set(tags) and tracking(plan)))


def unit_sources(state: GameState, player: str, purpose: Purpose | None) -> list[M.Source]:
    """The player's pool units that may pay for ``purpose`` (a spending restriction is checked as for a source), as pseudo-sources
    that are already 'tapped': used first (rank -1), each producing its one mana; a snow unit pays {S}."""
    from app.rules.casting import spend_allowed

    return [M.Source(f"{PREFIX}{u.id}", ((u.sym,),), rank=-1, snow="Snow" in u.tags)
            for u in state.players[player].mana_units if spend_allowed(u.only, purpose)]


@dataclass
class Slot:
    """One mana of a payment: a unit of the pool, or one a tapped source produced."""

    sym: str
    tags: list[str]
    only: str | None
    riders: list[dict[str, Any]]
    src: str
    unit: int | None = None


def settle(plan: Plan, player: str, payment: M.Payment) -> dict[str, Any]:
    """The ``rules_mana`` fields (net plain ``delta``, units spent and added) for a solved payment, and on ``payment`` the provenance of
    the mana spent (``tags``: one tag list per mana with a known source; ``riders``: the riders of the mana spent). Units are spent
    first, then what the tapped sources produced; the rest of the cost comes from the plain pool; what a source produced and wasn't
    needed stays (restricted / remembered mana as a unit, plain mana as a plain count)."""
    from app.rules.casting import mana_abilities

    state = plan.state
    units = {u.id: u for u in state.players[player].mana_units}
    used = dict(payment.used)
    slots: list[Slot] = []
    for cid, opt in payment.slots:
        if cid.startswith(PREFIX):
            u = units[int(cid[len(PREFIX):])]
            slots.append(Slot(u.sym, list(u.tags), u.only, list(u.riders), u.src, unit=u.id))
            continue
        card = state.cards[cid]
        ab = dict(mana_abilities(state, card, plan.info)).get(used.get(cid, -1))
        only = ab.spend_only if ab else None
        riders = rider_specs(ab)
        tags = tags_of(plan.ch(card))
        slots += [Slot(m, tags, only, riders, plan.oid(card)) for m in opt]
    delta: dict[str, int] = {}
    spend: list[int] = []
    add: list[dict[str, Any]] = []
    for sym in {*payment.spent, *(s.sym for s in slots)}:
        n = payment.spent.get(sym, 0)
        mine = sorted((s for s in slots if s.sym == sym), key=lambda s: s.unit is None)  # (units first)
        taken, left = mine[:n], mine[n:]
        payment.tags += [s.tags for s in taken if s.tags]
        payment.riders += [(s.src, r) for s in taken for r in s.riders]
        spend += [s.unit for s in taken if s.unit is not None]
        if n > len(taken):
            delta[sym] = delta.get(sym, 0) - (n - len(taken))  # the rest came from the plain pool
        for s in left:
            if s.unit is not None:
                continue
            if needs_unit(plan, s.only, s.riders, s.tags):
                add.append({"sym": s.sym, "src": s.src, "tags": s.tags, "only": s.only, "riders": s.riders})
            else:
                delta[sym] = delta.get(sym, 0) + 1
    return {"delta": {k: v for k, v in delta.items() if v}, "spend_units": spend, "add_units": add}


def rider_specs(ability: Any) -> list[dict[str, Any]]:
    """The riders of a mana ability ("when that mana is spent …"), as the dicts units keep."""
    import json

    return [json.loads(r) for r in getattr(ability, "on_spend", ())]


def restrict(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Spend this mana only to cast …" / "This mana can't be spent to …" after an instruction that added mana (106.6, 106.6a: all
    of it): the mana it just added (``ctx["_mana_added"]``, a plain count in the pool) becomes units that carry the restriction.
    ``ctx["_mana_unit_ids"]`` names them for "you don't lose this mana" (kept_mana)."""
    added_: dict[str, int] = ctx.pop("_mana_added", None) or {}
    pid = ctx["controller"]
    if not added_:
        return True
    card = plan.state.cards.get(ctx.get("source_card") or "")
    tags = tags_of(plan.ch(card)) if card is not None else []
    src = plan.oid(card) if card is not None else ""
    before = {u.id for u in plan.state.players[pid].mana_units}
    plan.do({"type": "rules_mana", "player": pid, "tap": [], "sacrifice": [], "life": 0, "label": "",
             "delta": {s: -n for s, n in added_.items()},
             "add_units": [{"sym": s, "src": src, "tags": tags, "only": e["only"], "riders": list(e.get("riders") or [])}
                           for s, n in added_.items() for _ in range(n)]}, actor=pid)
    ctx["_mana_unit_ids"] = [u.id for u in plan.state.players[pid].mana_units if u.id not in before]
    return True


def added(plan: Plan, card: Any, ability: Any, mana: dict[str, int]) -> dict[str, Any]:
    """The ``rules_mana`` fields that add the mana a source's mana ability produced (106.3): a plain count, or units when it is
    restricted, carries riders or comes from a source later rules ask about (see the module docstring)."""
    tags = tags_of(plan.ch(card))
    riders = rider_specs(ability)
    only = getattr(ability, "spend_only", None)
    if not needs_unit(plan, only, riders, tags):
        return {"delta": mana}
    src = plan.oid(card)
    return {"add_units": [{"sym": m, "src": src, "tags": tags, "only": only, "riders": riders}
                          for m, n in mana.items() for _ in range(n)]}
