"""-- cast riders (wave 38C) -- "Whenever you cast an instant or sorcery spell that targets a creature you control, exile that card instead of putting it into your
graveyard as it resolves. If you do, return it to your hand at the beginning of the next end step." (Feather), "… If you do, it becomes plotted." (Lilah), "…
exile that card with a dream counter on it instead of …" (Goliath Daydreamer), "… with three time counters on it instead of …. Then if the exiled card doesn't have
suspend, it gains suspend." (Gandalf of the Secret Fire). Researched against the Comprehensive Rules of 2026-09-25.

* 614.1a / 608.2n: a replacement effect of the spell the cast trigger is about: as the instant or sorcery spell would be put into its owner's graveyard as the final
  part of its resolution, it is exiled instead. Only a spell that resolves: a spell that is countered (701.6a) or has no legal target (608.2b) doesn't resolve, so it
  goes to the graveyard as usual and nothing follows ("If you do").
* 400.7: the effect is of that object (``RulesState.exile_resolves``, keyed by object id): a copy of the spell is another object (707.10) and is never exiled; it
  ceases to exist when it leaves the stack (704.5e).
* "your graveyard": a spell its controller doesn't own would go to another player's graveyard, which the effect doesn't replace.
* "If you do, …" / "Then …" follow the exile, so they are carried out when it happens, "it" being the card in exile (a new object, 400.7j): the sentences are read
  as the ones of an exile of a target card (the grammar that binds "it" to what an exile moved) and kept as ``then``, run with that card bound. Only the riders listed in
  ``RIDERS`` are accepted (counters, a delayed return, plotted, suspend); anything else leaves the ability manual.
"""

from __future__ import annotations

import copy
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_EXILE = re.compile(r"^exile (?:it|that card|that spell)(?: with (?P<n>an?|one|two|three|four|five|six|seven|eight|nine|ten) (?P<kind>[a-z]+) counters? on it)?"
                    r" instead of putting it into (?P<g>your|its owner's|a) graveyard as it resolves(?:\.(?: (?P<rest>.+))?)?$", re.IGNORECASE | re.DOTALL)
RIDERS = ("add_counters", "suspend_found", "suspend_mark", "plotted", "delayed", "deferred:bounce")


def bind(body: str, it: str | None, parse: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """The effect of "Exile that card [with N counters on it] instead of putting it into your graveyard as it resolves. [If you do, …]" in a cast trigger
    (``it`` "event_spell": the spell the trigger is about), or None. ``parse``: scripts.parse_effects."""
    m = _EXILE.match(body.strip())
    if m is None or it != "event_spell":
        return None
    rest = re.sub(r"^(?:if you do, |then )", "", m["rest"] or "", flags=re.IGNORECASE)
    gains = re.match(r"(?:if the exiled card doesn't have suspend, )?it gains suspend\.?$", rest, re.IGNORECASE)
    if m["kind"] and m["kind"].lower() == "time" and gains:  # Gandalf: the counters and the suspend it gains are one instruction (702.62b: app/rules/suspend_grants.py)
        rest = f"Suspend it with {m['n']} time counters."
    elif m["kind"] and gains is None:
        rest = f"Put {m['n']} {m['kind']} counter{'' if m['n'].lower() in ('a', 'an', 'one') else 's'} on it. {rest}".strip()
    elif m["kind"] or gains:
        return None  # (suspend gained without time counters, counters and something else: not one of the cards)
    own = m["g"].lower() == "your"
    if not rest:
        return [{"do": "exile_on_resolve", "who": "event_spell", "own": own, "bind": None, "then": []}], None, False
    found = parse("Exile target card from a graveyard. " + rest[:1].upper() + rest[1:])
    if found is None or not isinstance(found[1], str) or found[2] or len(found[0]) < 2 or found[0][0].get("do") != "exile" or not found[0][0].get("as"):
        return None
    then = found[0][1:]
    if any(e.get("do") not in RIDERS or str(e.get("who", "")).startswith("target") for e in then):
        return None
    return [{"do": "exile_on_resolve", "who": "event_spell", "own": own, "bind": found[0][0]["as"], "then": then}], None, False


def exile_on_resolve(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The cast trigger's effect: the spell it is about (while it is still that object on the stack) is exiled instead of going to the graveyard as it resolves."""
    from app.rules import copying

    for sid in copying._stack_objects(plan, ctx, e["who"]):
        card = plan.state.cards[sid]
        if card.copy_of is not None or card.is_token or not plan.ch(card).is_instant_or_sorcery or (e.get("own") and card.owner != ctx["controller"]):
            continue
        plan.rules.exile_resolves.setdefault(plan.oid(sid), {
            "bind": e.get("bind"), "then": copy.deepcopy(e["then"]), "controller": ctx["controller"], "source_card": ctx.get("source_card"),
            "source_object": ctx.get("source_object"), "name": ctx.get("name") or ""})
    return True


def resolved(plan: Plan, card_id: str, controller: str, countered: bool) -> bool:
    """A spell leaves the stack (engine.leave_stack). True if it was exiled instead of going to the graveyard as it resolved (and its riders have run)."""
    from app.rules import context, effects

    record = plan.rules.exile_resolves.pop(plan.oid(card_id), None)
    card = plan.state.cards[card_id]
    if record is None or countered or not plan.ch(card).is_instant_or_sorcery:
        return False
    plan.do({"type": "move", "card_ids": [card_id], "to": {"player": card.owner, "zone": "exile"}}, actor=controller)
    if record["then"] and plan.state.cards[card_id].zone.endswith(":exile"):  # ("If you do": a commander that went to the command zone instead (903.9a) was not exiled)
        ctx: Context = {"controller": record["controller"], "source_card": record["source_card"], "source_object": record["source_object"], "name": record["name"],
                        "targets": [], "stack_id": None, "kind": "replacement", "effects": copy.deepcopy(record["then"]), "next": 0, "x": 0, "event": None,
                        "body_done": {"do": "noop"}}
        context.bind_objects(plan, ctx, record["bind"], [card_id])
        effects.continue_effects(plan, ctx)
    return True


def plotted(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"It becomes plotted." (702.170c): each card the instruction names that is in exile."""
    from app.rules import casting, effects

    for cid in effects._cards(plan, ctx, e["who"]):
        casting.become_plotted(plan, cid)
    return True


PRIMITIVES = {"exile_on_resolve": exile_on_resolve, "plotted": plotted}
