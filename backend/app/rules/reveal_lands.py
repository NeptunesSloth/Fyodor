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
CONTROLS = "controls"  # (wave 100K: no question, the counter because you control one)
_TEXT = re.compile(r"^As ~ enters, you may reveal an? (?P<what>.+?) card from your hand\. (?:If you don't, (?:~|it) enters tapped\.|"
                   r"(?:~|This land) enters tapped unless you revealed an? (?P<w2>.+?) card this way or you control an? (?P<w3>.+?)\.|"
                   r"If you do or if you control an? (?P<w4>.+?), (?:~|this creature) enters with a \+1/\+1 counter on it\.)$")  # (wave 100K: Dragon's Disciple)


# -- if you do (wave 100B) -- "As this land enters, you may behold a Jace. If you don't, this land enters tapped." (Theorist's Sanctum): 701.4a, reveal a
# Jace card from your hand or choose a Jace permanent you control (``behold``: those are options too; a chosen permanent isn't revealed)
_BEHOLD = re.compile(r"^As ~ enters, you may behold an? (?P<what>[A-Z][a-z]+)\. If you don't, (?:~|it) enters tapped\.$")


def definition(text: str) -> dict[str, Any] | None:
    """The replacement for the wording above (``what``: "Island or Swamp", "Elf", "Treefolk"), or None."""
    if (b := _BEHOLD.match(text)) is not None:
        card, mine = selectors.parse(f"{b['what']} card"), selectors.parse(f"{b['what']} you control")
        return None if card is None or mine is None else {"kind": "replacement", "replacement": KIND, "sel": card.key(), "behold": mine.key(), "effects": []}
    m = _TEXT.match(text)
    if m is None:
        return None
    sel = selectors.parse(f"{m['what']} card")
    if sel is None or not sel.card or sel.player is not None or sel.other or sel.controller or sel.owner:
        return None
    if m["w4"]:  # -- as long as (wave 100K) -- Dragon's Disciple: the counter (once, its ruling) if it was revealed or you control one
        ctl = selectors.parse(f"{m['w4']} you control")
        if m["w4"] != m["what"] or ctl is None or ctl.card:
            return None
        return {"kind": "replacement", "replacement": KIND, "sel": sel.key(), "ctl": ctl.key(), "counter": "+1/+1", "effects": []}
    if m["w2"]:  # -- if you do (wave 25C) -- "… tapped unless you revealed a Dragon card this way or you control a Dragon" (Temple of the Dragon Queen)
        ctl = selectors.parse(f"{m['w3']} you control")
        if m["w2"] != m["what"] or m["w3"] != m["what"] or ctl is None or ctl.card:
            return None
        return {"kind": "replacement", "replacement": KIND, "sel": sel.key(), "ctl": ctl.key(), "effects": []}
    return {"kind": "replacement", "replacement": KIND, "sel": sel.key(), "effects": []}


def _matching(plan: Plan, card: CardInstance, controller: str, key: str) -> list[str]:
    key, _, beheld = key.partition("|")  # (behold: "<card key>|<permanent key>")
    sel = selectors.from_key(key)
    out = [c for c in plan.state.zones.get(zone_key(controller, "hand"), [])
           if c != card.id and c in plan.state.cards
           and selectors.matches(plan, sel, plan.state.cards[c], plan.ch(plan.state.cards[c]), controller)]
    return out + ([c for c in selectors.candidates(plan, selectors.from_key(beheld), controller) if c != card.id] if beheld else [])


def plan_entry(plan: Plan, card: CardInstance, controller: str, defs: list[dict[str, Any]], answers: dict[str, str],
               out: dict[str, Any]) -> None:
    """replacements.entry_plan's part for these lands: tapped unless a matching card is revealed; the
    question (``out["choice"]``) while it isn't answered."""
    for d in defs:
        if d.get("replacement") != KIND or out["tapped"] and not d.get("counter"):
            continue
        if d.get("ctl") and selectors.candidates(plan, selectors.from_key(d["ctl"]), controller):
            if d.get("counter"):
                out.setdefault("choices", {})[PREFIX + d["sel"]] = CONTROLS
            continue  # (you control one: it enters untapped without revealing anything; public, so no question to leak)
        what = PREFIX + d["sel"] + ("|" + d["behold"] if d.get("behold") else "")
        cards = _matching(plan, card, controller, what[len(PREFIX):])
        given = answers.get(what)
        # -- review (wave 4R) -- asked whenever their hand holds another card (its size is public): skipping the
        # question only when no card matches would tell the table they hold none (hidden information)
        others = any(c != card.id for c in plan.state.zones.get(zone_key(controller, "hand"), [])) or (bool(d.get("behold")) and bool(cards))
        if not others or given == NONE:
            out["tapped"] = out["tapped"] or not d.get("counter")
        elif given is None:
            if "choice" not in out:
                out["choice"] = {"what": what}
        elif given in cards:
            out.setdefault("choices", {})[what] = given
        else:  # (the card answered with left the hand meanwhile: nothing revealed)
            out["tapped"] = out["tapped"] or not d.get("counter")


def is_choice(what: str) -> bool:
    return what.startswith(PREFIX)


def prompt(plan: Plan, card: CardInstance, controller: str, what: str) -> tuple[str, list[DecisionOption]]:
    """The private question: which matching card to reveal, or none (it enters tapped)."""
    cards = _matching(plan, card, controller, what[len(PREFIX):])
    options = [DecisionOption(id=c, label=f"{'Choose' if plan.state.cards[c].zone.endswith(':battlefield') else 'Reveal'} {plan.state.cards[c].name or 'card'}",
                              card_id=c) for c in cards]
    from app.rules import scripts

    if any(d.get("counter") for d in scripts.definitions(plan.ch(card)).values()):  # (wave 100K)
        options.append(DecisionOption(id=NONE, label="Don't reveal (no +1/+1 counter)"))
        return f"{card.name}: as it enters, reveal a card from your hand for a +1/+1 counter?", options
    options.append(DecisionOption(id=NONE, label="Don't reveal (it enters tapped)"))
    if "|" in what:  # (behold, 701.4a)
        return f"{card.name}: as it enters, behold (reveal a card from your hand or choose a permanent you control), or it enters tapped?", options
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


def counters(ch: Any, choices: dict[str, str] | None) -> int:
    """-- as long as (wave 100K) -- Dragon's Disciple's +1/+1 counter: a card revealed, or one you control."""
    from app.rules import scripts

    return sum(1 for d in scripts.definitions(ch).values() if d.get("replacement") == KIND and d.get("counter")
               and (choices or {}).get(PREFIX + d["sel"], NONE) != NONE)
