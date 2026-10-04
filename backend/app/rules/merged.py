"""-- merged permanents (wave 18D) -- mutate (CR 702.140, 730) and meld (CR 701.42, 712.4, 712.21), researched against the stored
Comprehensive Rules (2026-09-25). (The numbers 721 / 730 of older rules texts: "merging with permanents" is 730 here.)

Representation (app/game/merging.py): one permanent is one ``CardInstance`` whose card fields are its topmost component's (730.2a)
and whose ``merged`` lists every card or token that represents it; the object (its rules id, counters, attachments, status) is the
target's, unchanged (730.2b-c). :func:`app.rules.characteristics.merged_of` gives it every component's abilities (702.140e); a melded
permanent is its combined back face (712.8g). ``ops.move_card`` breaks the pile up when the permanent leaves the battlefield (730.3,
712.21) — one object leaves, each card arrives.

* 702.140a — "Mutate [cost]": an alternative cost (118.9, app/rules/alt_costs.py, tag "mutate") and the spell targets a non-Human
  creature with the same owner as the spell; the offer exists only when such a creature can be targeted.
* 702.140b — as it resolves with an illegal target it stays a creature spell and enters the battlefield (608.3b).
* 702.140c — with a legal target it merges: its controller chooses on top or underneath (a decision).
* 702.140d — "Whenever this creature mutates" triggers as it merges (designation event "mutated").
* 903.3c, 903.9c — a pile with a commander is that commander; to the hand or library its owner may put it into the command zone
  and the rest goes there (the commander is the card that stays the instance, ``merging.break_up``).

Refused (the spell can't be cast mutating, the engine never guesses): a target that is face down (708.2: the merged status, 730.2e-g),
double-faced or a flip card (730.2h-j), a copy or a token spell, a permanent under a copy effect (730.2a: the merge is a copiable
effect with its own timestamp, 613.2), a melded permanent, or a second commander in the pile (903.3c: one is that player's commander).
A permanent that copies a merged permanent is refused too (copying.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.state import STACK, CardInstance
from app.rules import selectors
from app.rules import targets as T

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

MUTATE_TARGET = selectors.Selector(types=("Creature",), not_subtypes=("Human",), owner="you", extras=("mergeable",)).key()
_UNMERGEABLE_LAYOUTS = ("transform", "modal_dfc", "double_faced_token", "reversible_card", "meld", "flip", "prepare", "battle")


def _plain(plan: Plan, card: CardInstance) -> bool:
    """A card the pile logic models: face up, one printed face, not a copy."""
    if card.face_down or card.copy_of is not None or card.ability is not None:
        return False
    data = plan.info.get(card.card_id) if card.card_id else None
    return not (data and data.get("layout") in _UNMERGEABLE_LAYOUTS) and not (card.token and card.token.back is not None)


def mergeable(plan: Plan, card: CardInstance) -> bool:
    """Can a mutating creature spell merge with this permanent (see the refusals above)?"""
    if not card.zone.endswith(":battlefield") or card.melded:
        return False
    if not all(_plain(plan, CardInstance(id=p.id, card_id=p.card_id, owner=p.owner, controller=card.controller, zone=card.zone,
                                         token=p.token, is_token=p.is_token, copy_of=p.copy_of)) for p in card.merged) \
            or (not card.merged and not _plain(plan, card)):
        return False
    oid = plan.oid(card)
    return not any(e.layer == "1" and oid in e.affected for e in plan.rules.effects)  # (a copy effect: 613.2, 730.2a)


def can_mutate(plan: Plan, player: str, card: CardInstance, ch: Characteristics) -> bool:
    """702.140a: is there a creature this card could be cast mutating onto, as ``player`` casts it now?"""
    return card.owner == player and card.copy_of is None and not card.is_token and _plain(plan, card) \
        and bool(T.legal_targets(plan, MUTATE_TARGET, player, ch, card.id))


def times_mutated(card: CardInstance) -> int:
    """The number of times this permanent has mutated: each component beyond the first merged in once (702.140)."""
    return 0 if card.melded else max(0, len(card.merged) - 1)


def times_mutated_in(plan: Plan, ctx: dict[str, Any]) -> int:
    """"The number of times this creature has mutated" for the ability's source: as it is now, or as it last existed (608.2h)."""
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == ctx.get("source_object"):
        return times_mutated(card)
    snap = plan.rules.lki.get(ctx.get("source_object") or "")
    return 0 if snap is None or snap.melded else max(0, len(snap.merged) - 1)


def resolve(plan: Plan, top: CardInstance, controller: str) -> bool:
    """A mutating creature spell begins resolving. True when it is done (merged) or waiting for the over / under answer; False when
    its target is illegal and it carries on as a creature spell (702.140b, 608.3b)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    r = plan.rules
    target = r.aura_targets.get(top.id)
    ch = plan.ch(top)
    host = plan.state.cards.get(target.id) if target is not None else None
    if target is None or host is None or not T.still_legal(plan, MUTATE_TARGET, controller, target, ch, top.id):
        r.mutating = [o for o in r.mutating if o != plan.oid(top)]
        r.aura_targets.pop(top.id, None)
        plan.note(f"{ch.name} ceases to be a mutating creature spell: its target is illegal", [top.id])
        return False
    over = r.entry_choices.get(top.id, {}).get("mutate")
    if over is None:
        decide(plan, player=controller, kind="choose_one", prompt=f"Put {ch.name} on top of or underneath {host.name}? (702.140c)",
               options=[DecisionOption(id="over", label=f"On top: it's {ch.name}, with every ability"),
                        DecisionOption(id="under", label=f"Underneath: it stays {host.name}, with every ability")],
               resume={"step": "mutate_choice", "card": top.id}, source=top)
        return True
    from app.game.rules_state import emit

    r.mutating = [o for o in r.mutating if o != plan.oid(top)]
    r.aura_targets.pop(top.id, None)
    r.entry_choices.pop(top.id, None)
    r.payments.pop(plan.oid(top), None)
    plan.do({"type": "merge", "card_id": host.id, "spell_id": top.id, "over": over == "over"}, actor=controller)
    emit(plan.state, "designation", counter="mutated", card=host.id, object_id=plan.oid(host), player=host.controller)
    return True


def resume_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.engine import resolve_top_of_stack

    plan.rules.entry_choices.setdefault(d.resume["card"], {})["mutate"] = chosen[0]
    resolve_top_of_stack(plan)
