"""-- merged permanents (wave 18D) -- mutate (CR 702.140, 730) and meld (CR 701.42, 712.4, 712.21), researched against the stored
Comprehensive Rules (2026-09-25). (In this text 721 is Station cards: "merging with permanents" is rule 730.)

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

import re
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


def note_cast(plan: Plan, card: CardInstance) -> None:
    """The spell on the stack is a mutating creature spell (702.140a); the ones that left the stack are forgotten."""
    r = plan.rules
    r.mutating = [o for o in r.mutating if (c := plan.state.cards.get(o.rsplit(".", 1)[0])) is not None and c.zone == STACK
                  and plan.oid(c) == o]
    r.mutating.append(plan.oid(card))


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


def parts_left(plan: Plan, e: Any) -> list[Any]:
    """-- review (wave 18D) -- the zone-change events of the other cards of the merged / melded permanent that left in ``e``
    (each put into the zone from the battlefield, 730.3 / 712.21; app/game/rules_state._diff)."""
    snap = plan.rules.lki.get(e.object_id or "")
    if snap is None or not snap.merged:
        return []
    ids = {p["id"] for p in snap.merged} - {e.card}
    return [x for x in plan.rules.events if x.kind == "zone_change" and x.batch == e.batch and x.object_id is None and x.card in ids
            and x.from_zone == snap.zone]


def pieces(plan: Plan, card_ids: list[str]) -> list[str]:
    """730.3c / 712.21c: an effect that finds the new object a merged permanent became as it left the battlefield finds all of them:
    each card id, followed by the other cards of the pile it just left the battlefield as (still the objects they became)."""
    out: list[str] = []
    for cid in card_ids:
        out.append(cid)
        card = plan.state.cards.get(cid)
        oid = plan.oid(card) if card is not None else None
        e = next((x for x in reversed(plan.rules.events) if x.kind == "zone_change" and x.card == cid and x.new_object_id == oid), None) \
            if oid is not None else None
        out += [x.card for x in (parts_left(plan, e) if e is not None else [])
                if x.card in plan.state.cards and plan.oid(plan.state.cards[x.card]) == x.new_object_id and x.card not in out]
    return out


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


# -- meld (wave 18D) -- 701.42, 712.4, 712.21 ----------------------------------------------------------------------------------
# "If you both own and control ~ and a creature named Bruna, the Fading Light, exile them, then meld them into Brisela, Voice of
# Nightmares." The names hold commas and the other card's name is a card name (the card's own name is read as ~): they are carried as
# one hex word through the grammar (scripts.define) and read back here.
_MELD_NAMES = re.compile(r"(?<=\bnamed )(?P<n>[^.]+?)(?=, exile them, then meld|, you may pay)|(?<=meld them into )(?P<r>[^.]+?)(?=\.|$)")
_PAIR = re.compile(r"you both own and control (?:~|this (?:creature|land|artifact|permanent)) and (?:a|an) (?P<k>creature|land|artifact|permanent) "
                   r"named meldname:(?P<n>[0-9a-f]+)")
MELD_EFFECT = re.compile(r"exile them, then meld them into meldname:(?P<r>[0-9a-f]+)")


def protect(text: str) -> str:
    """The ability text with the partner's name and the meld result's name each as one word ``meldname:<hex>``."""
    if "meld them into" not in text:
        return text
    return _MELD_NAMES.sub(lambda m: "meldname:" + (m["n"] or m["r"]).encode().hex(), text)


def name_of(word: str) -> str:
    return bytes.fromhex(word).decode()


def condition(t: str) -> dict[str, Any] | None:
    m = _PAIR.fullmatch(t)
    return {"pair": {"name": name_of(m["n"]), "kind": m["k"]}} if m else None


def _pair_of(plan: Plan, card: CardInstance) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """(the meld result's, the other half's) card data for a card that is half of a meld pair."""
    data = plan.info.get(card.card_id) if card.card_id and not card.is_token else None
    if data is None or data.get("layout") != "meld":
        return None
    related = data.get("related_cards") or []
    result = next((plan.info.get(r["id"]) for r in related if r.get("component") == "meld_result"), None)
    other = next((plan.info.get(r["id"]) for r in related if r.get("component") == "meld_part" and r.get("name") != card.name), None)
    return (result, other) if result is not None and other is not None else None


def partner_of(plan: Plan, ctx: dict[str, Any], kind: str | None = None, name: str | None = None) -> CardInstance | None:
    """The permanent its controller both owns and controls that this ability's source melds with, if it is on the battlefield."""
    src = plan.state.cards.get(ctx.get("source_card") or "")
    if src is None or not src.zone.endswith(":battlefield") or plan.oid(src) != ctx.get("source_object") or src.merged \
            or src.owner != ctx["controller"] or src.controller != ctx["controller"]:
        return None
    pair = _pair_of(plan, src)
    if pair is None or (name is not None and pair[1]["name"] != name):
        return None
    return next((c for c in plan.state.cards.values() if c.id != src.id and c.zone == f"{ctx['controller']}:battlefield" and not c.merged
                 and not c.is_token and c.owner == ctx["controller"] and c.name == pair[1]["name"]
                 and (kind in (None, "permanent") or kind.capitalize() in plan.ch(c).types)), None)


def pair_holds(plan: Plan, ctx: dict[str, Any], spec: dict[str, Any]) -> bool:
    """"You both own and control ~ and a creature named X": ~ and a permanent named X (a card, the other half of its meld pair) both
    belong to and are controlled by the ability's controller (701.42a)."""
    return partner_of(plan, ctx, spec["kind"], spec["name"]) is not None


def meld(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """701.42a: "Exile them, then meld them into [name]": both cards are exiled, then put onto the battlefield with their back faces up
    and combined, one permanent (712.4a, 712.14c). If they can't be melded (not the pair, not both exiled: 701.42c) nothing more
    happens. Returns False while the entering permanent waits for a choice (attachments.enter)."""
    from app.rules import attachments
    from app.rules import characteristics as chars

    src = plan.state.cards.get(ctx.get("source_card") or "")
    partner = partner_of(plan, ctx) if src is not None else None
    pair = _pair_of(plan, src) if src is not None and partner is not None else None
    if src is None or partner is None or pair is None or pair[0]["name"] != e["result"]:
        return True
    owner = src.owner
    plan.do({"type": "move", "card_ids": [src.id, partner.id], "to": {"player": owner, "zone": "exile"}}, actor=ctx["controller"])
    cards = [plan.state.cards.get(src.id), plan.state.cards.get(partner.id)]
    if any(c is None or c.zone != f"{owner}:exile" for c in cards):
        return True  # (701.42c: replaced, or gone)
    ch = chars.printed_from_data(pair[0])
    plan.do({"type": "meld", "card_id": src.id, "other_id": partner.id, "result_id": pair[0]["id"], "result_name": pair[0]["name"],
             "row": "land" if ch.is_land and not ch.is_creature else "creature" if ch.is_creature else "other"}, actor=ctx["controller"])
    return attachments.enter(plan, [{"card": src.id, "player": owner, "actor": ctx["controller"]}], ctx)


PRIMITIVES = {"meld": meld}
