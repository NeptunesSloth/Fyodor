"""-- "this way" outcomes (wave 4A) -- the reveal-or-tapped lands: "As this land enters, you may reveal an
Island or Swamp card from your hand. If you don't, this land enters tapped." (the Snarls: Choked Estuary,
Shineshadow Snarl …; the tribal lands: Gilt-Leaf Palace, Murmuring Bosk, Secluded Glen, Flamekin Village).

CR 2026-09-25: an "As [this permanent] enters" ability is a replacement effect (614.1c); its choice is made
before the permanent enters (614.12a), here like a shock land's (app/rules/replacements.entry_plan), on every
path onto the battlefield. The choice is the controller's, in private: the decision lists the matching cards
in their hand (hidden information, 400.2). Revealing shows the chosen card to every player for a brief time
(701.20a; it doesn't leave the hand, 701.20b), then it stops being revealed. A player with no matching card
has nothing to reveal: it enters tapped without a question. A permanent that enters tapped anyway ("put it
onto the battlefield tapped") asks nothing either.

The answer is recorded like the other entering answers (``choices``: ``"reveal:<selector key>"`` → the card
revealed, or :data:`NONE`).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key
from app.rules import selectors

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

KIND = "reveal_or_tapped"
PREFIX = "reveal:"
NONE = "none"
_TEXT = re.compile(r"^As ~ enters, you may reveal an? (?P<what>.+?) card from your hand\. If you don't, (?:~|it) enters tapped\.$")


def definition(text: str) -> dict[str, Any] | None:
    """The replacement for the wording above (``what``: "Island or Swamp", "Elf", "Treefolk"), or None."""
    m = _TEXT.match(text)
    if m is None:
        return None
    sel = selectors.parse(f"{m['what']} card")
    if sel is None or not sel.card or sel.player is not None or sel.other or sel.controller or sel.owner:
        return None
    return {"kind": "replacement", "replacement": KIND, "sel": sel.key(), "effects": []}


def _matching(plan: Plan, card: CardInstance, controller: str, key: str) -> list[str]:
    sel = selectors.from_key(key)
    return [c for c in plan.state.zones.get(zone_key(controller, "hand"), [])
            if c != card.id and c in plan.state.cards
            and selectors.matches(plan, sel, plan.state.cards[c], plan.ch(plan.state.cards[c]), controller)]


def plan_entry(plan: Plan, card: CardInstance, controller: str, defs: list[dict[str, Any]], answers: dict[str, str],
               out: dict[str, Any]) -> None:
    """replacements.entry_plan's part for these lands: tapped unless a matching card is revealed; the
    question (``out["choice"]``) while it isn't answered."""
    for d in defs:
        if d.get("replacement") != KIND or out["tapped"]:
            continue
        what = PREFIX + d["sel"]
        cards = _matching(plan, card, controller, d["sel"])
        given = answers.get(what)
        # -- review (wave 4R) -- asked whenever their hand holds another card (its size is public): skipping the
        # question only when no card matches would tell the table they hold none (hidden information)
        others = any(c != card.id for c in plan.state.zones.get(zone_key(controller, "hand"), []))
        if not others or given == NONE:
            out["tapped"] = True
        elif given is None:
            if "choice" not in out:
                out["choice"] = {"what": what}
        elif given in cards:
            out.setdefault("choices", {})[what] = given
        else:  # (the card answered with left the hand meanwhile: nothing revealed)
            out["tapped"] = True


def is_choice(what: str) -> bool:
    return what.startswith(PREFIX)


def prompt(plan: Plan, card: CardInstance, controller: str, what: str) -> tuple[str, list[DecisionOption]]:
    """The private question: which matching card to reveal, or none (it enters tapped)."""
    cards = _matching(plan, card, controller, what[len(PREFIX):])
    options = [DecisionOption(id=c, label=f"Reveal {plan.state.cards[c].name or 'card'}", card_id=c) for c in cards]
    options.append(DecisionOption(id=NONE, label="Don't reveal (it enters tapped)"))
    return f"{card.name}: as it enters, reveal a card from your hand, or it enters tapped?", options


def after_entry(plan: Plan, controller: str, choices: dict[str, str] | None) -> None:
    """701.20a: the revealed card is shown to every player, then stops being revealed (it stays in the hand)."""
    for what, cid in (choices or {}).items():
        if not is_choice(what) or cid == NONE or cid not in plan.state.cards:
            continue
        if plan.state.cards[cid].zone != zone_key(controller, "hand"):
            continue
        plan.do({"type": "reveal", "card_ids": [cid]}, actor=controller)
        plan.do({"type": "hide", "card_ids": [cid]}, actor=controller)
