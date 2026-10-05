"""-- soulbond (wave 24B) -- paired creatures (CR 2026-09-25, 702.95).

702.95a: soulbond is two triggered abilities (``keyword_triggers.MEANINGS``): "When this creature enters, if you control both this
creature and another creature and both are unpaired, you may pair this creature with another unpaired creature you control" and
"Whenever another creature you control enters, if you control both that creature and this one and both are unpaired, you may pair
that creature with this creature". The intervening "if" is the condition ``{"paired": "self" | "other"}``; the pairing is the
``pair`` effect.

* 702.95b / 702.95d: a pair is two objects, each in one pair only: ``RulesState.pairs`` (object id → [partner's object id, the
  controller who paired them]), both directions. A new object (400.7) is unpaired.
* 702.95c: as the ability resolves, if either object is no longer a creature, no longer on the battlefield or no longer under the
  control of the player who controls the soulbond ability, neither becomes paired.
* 702.95e: a pair ends when another player gains control of either creature, either stops being a creature or either leaves the
  battlefield (:func:`sync`, any time: ``triggers.collect`` runs it before the triggers are looked at).
* "As long as this creature is paired with another creature, both creatures have …" is a static whose subject is the pair
  (``statics`` ``who: "paired"``, condition ``{"static": "paired"}``, ``static_conditions``): :func:`partner_of`.

Refused (manual): pairing with a battle (Battlebond), "if that creature is a Dwarf" riders, abilities that ask about the paired creature
by name (Donna Noble).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

Context = dict[str, Any]
STEP = "pair_choose"
SELF = ("you control both this creature and another creature and both are unpaired",
        "you control both ~ and another creature and both are unpaired")
OTHER = ("you control both that creature and this one and both are unpaired",)
MEANING = ("When this creature enters, if you control both this creature and another creature and both are unpaired, you may pair this "
           "creature with another unpaired creature you control.\n"
           "Whenever another creature you control enters, if you control both that creature and this one and both are unpaired, you may "
           "pair that creature with this creature.")


def condition(text: str) -> dict[str, Any] | None:
    return {"paired": "self"} if text in SELF else {"paired": "other"} if text in OTHER else None


def partner_oid(plan: Plan, card: CardInstance) -> str | None:
    """The object ``card`` is paired with (none: unpaired)."""
    found = plan.rules.pairs.get(plan.oid(card))
    return found[0] if found else None


def is_paired(plan: Plan, card: CardInstance) -> bool:
    return plan.oid(card) in plan.rules.pairs


def _creature(plan: Plan, card: CardInstance | None, controller: str) -> bool:
    return card is not None and card.zone.endswith(":battlefield") and card.controller == controller and plan.in_game(card) \
        and not plan.manual(card) and plan.ch(card).is_creature


def sync(plan: Plan) -> None:
    """702.95e: end the pairs whose creatures changed controller, stopped being creatures or left the battlefield."""
    pairs = plan.rules.pairs
    if not pairs:
        return
    here = {plan.oid(c): c for c in plan.state.cards.values() if c.zone.endswith(":battlefield")}
    for oid in list(pairs):
        if oid not in pairs:
            continue
        other, controller = pairs[oid]
        if not (_creature(plan, here.get(oid), controller) and _creature(plan, here.get(other), controller)):
            pairs.pop(oid, None)
            pairs.pop(other, None)


def _unpaired(plan: Plan, controller: str, *, but: str | None = None) -> list[CardInstance]:
    return [c for c in plan.state.cards.values() if c.id != but and _creature(plan, c, controller) and not is_paired(plan, c)]


def holds(plan: Plan, ctx: Context, cond: dict[str, Any]) -> bool:
    """The intervening "if" of soulbond (603.4: as it triggers and as it resolves)."""
    me = plan.state.cards.get(ctx.get("source_card") or "")
    you = ctx["controller"]
    if not _creature(plan, me, you) or is_paired(plan, me):  # type: ignore[arg-type]
        return False
    if cond["paired"] == "self":
        return bool(_unpaired(plan, you, but=me.id))  # type: ignore[union-attr]
    other = _entered(plan, ctx)
    return _creature(plan, other, you) and not is_paired(plan, other)  # type: ignore[arg-type]


def _entered(plan: Plan, ctx: Context) -> CardInstance | None:
    """The creature a "another creature enters" soulbond trigger is about (as the same object it entered as)."""
    for o in (ctx.get("event") or {}).get("objects") or []:
        card = plan.state.cards.get(o.get("card") or "")
        if card is not None and plan.oid(card) == o.get("object_id"):
            return card
    return None


def _make(plan: Plan, a: CardInstance, b: CardInstance, controller: str) -> None:
    plan.rules.pairs[plan.oid(a)] = (plan.oid(b), controller)
    plan.rules.pairs[plan.oid(b)] = (plan.oid(a), controller)
    plan.note(f"{a.name} and {b.name} become paired")


def pair(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.95a / 702.95c: pair the source with the creature that entered, or with another unpaired creature the controller chooses."""
    you = ctx["controller"]
    me = plan.state.cards.get(ctx.get("source_card") or "")
    if not _creature(plan, me, you) or is_paired(plan, me):  # type: ignore[arg-type]
        return True
    if e["with"] == "event":
        other = _entered(plan, ctx)
        if _creature(plan, other, you) and not is_paired(plan, other):  # type: ignore[arg-type]
            _make(plan, me, other, you)  # type: ignore[arg-type]
        return True
    pool = _unpaired(plan, you, but=me.id)  # type: ignore[union-attr]
    if len(pool) == 1:
        _make(plan, me, pool[0], you)  # type: ignore[arg-type]
    elif pool:
        decide(plan, player=you, kind="choose_cards", prompt=f"{me.name}: choose the creature to pair it with",  # type: ignore[union-attr]
               options=[DecisionOption(id=c.id, label=c.name or "Creature", card_id=c.id) for c in pool],
               resume={"step": STEP, "ctx": ctx}, source=me)
        return False
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    you = ctx["controller"]
    me = plan.state.cards.get(ctx.get("source_card") or "")
    other = plan.state.cards.get(chosen[0]) if len(chosen) == 1 else None
    if other is None or other not in _unpaired(plan, you, but=getattr(me, "id", None)):
        raise ActionError("Choose one of the creatures")
    if _creature(plan, me, you) and not is_paired(plan, me):  # type: ignore[arg-type]
        _make(plan, me, other, you)  # type: ignore[arg-type]
    effects.continue_effects(plan, ctx)


_PAIR = re.compile(r"^pair (?:this creature|~) with another unpaired creature you control$")
_PAIR_THAT = re.compile(r"^pair that creature with (?:this creature|~)$")


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "pair", "with": "event" if m.re is _PAIR_THAT else "choose"}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_PAIR, _build), (_PAIR_THAT, _build)]
PRIMITIVES = {"pair": pair}
