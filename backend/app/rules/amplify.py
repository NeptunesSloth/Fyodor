"""-- casting extras (wave 18E) -- amplify N (CR 702.38), researched against the stored Comprehensive Rules (2026-09-25).

* 702.38a — "As this object enters, reveal any number of cards from your hand that share a creature type with it. This permanent enters
  with N +1/+1 counters on it for each card revealed this way. You can't reveal this card or any other cards that are entering the
  battlefield at the same time as this card." Chosen before it enters (614.12a) like devour's picks (``app/rules/devour.py``, the same
  one-answer-at-a-time list: ``choices[WHAT]`` is the comma-separated cards, ending ``done``) and revealed to everyone as it enters
  (701.20a: :func:`reveal`); the counters follow the cards actually revealed.

Privacy: which cards in a hand share a type with the entering creature is the owner's private information, so the question is asked every
time a creature with amplify enters — whether or not the hand has a card to offer (then "none" is the only answer) — so that asking, or
not asking, tells the table nothing. Only the chooser sees the options (the decision view shows the others who is choosing); a card is
public from the moment it is revealed.
Only a single amplify instance on an object is read (702.38b: several would each need their own list).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

WHAT = "amplify"
DONE = "done"
_PIECE = re.compile(r"amplify (?P<n>\d+)")


def pieces(line: str) -> list[int]:
    out = []
    for p in re.split(r"[,;]\s*", re.sub(r"\s*\(.*?\)", "", line).strip().rstrip(".")):
        m = _PIECE.fullmatch(p.strip().lower())
        if m:
            out.append(int(m["n"]))
    return out


def supported(line: str) -> bool:
    return len(pieces(line)) == 1


def spec(ch: Any) -> int | None:
    found = [n for ab in ch.abilities if ab.kind == "keywords" and "amplify" in ab.keywords for n in pieces(ab.text)]
    return found[0] if len(found) == 1 else None


def picked(value: str | None) -> list[str]:
    return [x for x in (value or "").split(",") if x and x != DONE]


def finished(value: str | None) -> bool:
    return bool(value) and value.endswith(DONE)  # type: ignore[union-attr]


def merge(previous: str | None, chosen: str) -> str:
    return ",".join([*picked(previous), chosen])


def candidates(plan: Plan, card: CardInstance, controller: str, taken: set[str]) -> list[str]:
    """Cards in its controller's hand that share a creature type with it (702.38a); never itself."""
    from app.rules import characteristics as chars
    from app.rules.creature_types import CREATURE_TYPES

    mine = plan.ch(card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller})).subtypes & CREATURE_TYPES
    out = []
    for cid in plan.state.zones.get(zone_key(controller, "hand"), []):
        if cid == card.id or cid in taken:
            continue
        theirs = chars.of(plan.state.cards[cid], plan.info).subtypes & CREATURE_TYPES
        if mine & theirs:
            out.append(cid)
    return out


def plan_entry(plan: Plan, card: CardInstance, controller: str, answers: dict[str, str], out: dict[str, Any]) -> None:
    """replacements.entry_plan's part: the next question (``out["choice"]``), or ``out["amplify"]`` (what to reveal)."""
    if plan.manual(card):
        return
    ch = plan.ch(card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller}))
    if spec(ch) is None:
        return
    value = answers.get(WHAT)
    left = candidates(plan, card, controller, set(picked(value)))
    if not finished(value) and (left or not value):  # (always asked once: the question itself is no information)
        if "choice" not in out:
            out["choice"] = {"what": WHAT, "picked": value}
        return
    hand = plan.state.zones.get(zone_key(controller, "hand"), [])
    ids = [c for c in picked(value) if c in hand]
    if ids:
        out["amplify"] = ids
    out.setdefault("choices", {})[WHAT] = ",".join(ids) + ("," if ids else "") + DONE


def is_choice(what: str) -> bool:
    return what == WHAT


def prompt(plan: Plan, card: CardInstance, controller: str, choice: dict[str, Any]) -> tuple[str, list[DecisionOption]]:
    already = picked(choice.get("picked"))
    options = [DecisionOption(id=c, label=f"Reveal {plan.state.cards[c].name or 'a card'}", card_id=c)
               for c in candidates(plan, card, controller, set(already))]
    options.append(DecisionOption(id=DONE, label=f"Done: reveal {len(already)}" if already else "Don't reveal any"))
    return (f"{card.name}: amplify — as it enters, reveal cards from your hand that share a creature type with it ({len(already)} chosen)",
            options)


def reveal(plan: Plan, ep: dict[str, Any], controller: str) -> None:
    """702.38a: the chosen cards are revealed as it enters (701.20a); the counters follow the ones that still were in the hand."""
    ids = ep.get("amplify")
    if not ids:
        return
    hand = plan.state.zones.get(zone_key(controller, "hand"), [])
    live = [c for c in ids if c in hand]
    if live:
        plan.do({"type": "reveal", "card_ids": live}, actor=controller)  # (everyone sees them, then they stop being revealed)
        plan.do({"type": "hide", "card_ids": live}, actor=controller)
        plan.note(f"{plan.name(controller)} reveals {len(live)} card{'s' if len(live) != 1 else ''} to amplify", live)
    ep.setdefault("choices", {})[WHAT] = ",".join(live) + ("," if live else "") + DONE


def counters(ch: Any, choices: dict[str, str] | None) -> int:
    n = spec(ch)
    return n * len(picked((choices or {}).get(WHAT))) if n is not None else 0
