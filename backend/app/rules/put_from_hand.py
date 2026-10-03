"""Putting a permanent card from your hand onto the battlefield (wave 5J), researched against CR 2026-09-25.

"{1}{W}, {T}: You may put an Equipment card from your hand onto the battlefield." (Stoneforge Mystic), "{G}, {T}: You
may put a creature card from your hand onto the battlefield." (Elvish Piper, Quicksilver Amulet), "{T}: You may put a
land card from your hand onto the battlefield." (Sakura-Tribe Scout), Sneak Attack, Dragon Arch …

* The card isn't cast (601.1: no cast triggers, no costs) and a land put onto the battlefield this way isn't played
  (305.4: it doesn't use a land play). It enters as any permanent does (entry replacements 614.12, "As ~ enters"
  choices, enters triggers): ``attachments.enter``; an Aura chooses what it enchants without targeting (303.4f), and
  with nothing to enchant it stays in the hand (303.4g). An Equipment enters unattached (301.5b).
* The choice is made from a hidden zone: only the player choosing sees the options (the decision is private,
  app/rules/view.py), and "you may" lets them put nothing (no one learns whether a matching card was there).
* What it put is recorded for a later "That creature gains haste. Sacrifice the creature at the beginning of the next
  end step." (Sneak Attack): the permanent it became (400.7).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]

_PERMANENT_TYPES = frozenset({"Artifact", "Creature", "Enchantment", "Land", "Planeswalker", "Battle"})
PATTERN = r"put (?:a|an) (?P<what>[^.]+?) card from your hand onto the battlefield(?P<tapped> tapped)?"


def parse(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any] | None:
    """The effect, or None (manual) when the card it names could be something that can't enter the battlefield."""
    from app.rules import selectors

    sel = selectors.parse(f"{m['what']} card from your hand")
    if sel is None or sel.zones != ("hand",) or sel.zone_owner != "you" or sel.player is not None or sel.extras:
        return None
    if not sel.types and not sel.subtypes:
        return None  # ("a card": an instant or sorcery can't be put onto the battlefield)
    if sel.types and not set(sel.types) <= _PERMANENT_TYPES:
        return None
    effect: dict[str, Any] = {"do": "put_from_hand", "sel": sel.key(), "label": m["what"]}
    if m["tapped"]:
        effect["tapped"] = True
    return [effect], None


def put_from_hand(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Its controller chooses up to one matching card in their hand (privately), then it enters."""
    from app.rules import effects, selectors
    from app.rules.plan import decide

    pid = ctx["controller"]
    options = [c for c in selectors.candidates(plan, selectors.from_key(e["sel"]), pid, ctx.get("source_card"))
               if plan.state.cards[c].zone == f"{pid}:hand" and _permanent_card(plan, c)]
    if not options:
        effects._remember(plan, ctx, e, [])
        return True  # (nothing is announced: the hand is hidden)
    may = bool(e.get("optional"))  # ("you may": none is a choice; a trigger's "you may" was asked already, 603.5)
    decide(plan, player=pid, kind="choose_cards",
           prompt=f"{ctx.get('name') or 'It'}: {'you may ' if may else ''}put a {e.get('label') or 'permanent'} card from "
                  "your hand onto the battlefield",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in options],
           min_choices=0 if may else 1, max_choices=1, resume={"step": "put_from_hand", "ctx": ctx, "e": e})
    return False


def _permanent_card(plan: Plan, cid: str) -> bool:
    from app.rules import characteristics as chars

    ch = chars.of(plan.state.cards[cid], plan.info)
    return bool(ch.types & _PERMANENT_TYPES) and not ch.is_instant_or_sorcery


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import attachments, effects, selectors
    from app.rules import characteristics as chars

    ctx, e = d.resume["ctx"], d.resume["e"]
    pid = ctx["controller"]
    sel = selectors.from_key(e["sel"])
    cards = []
    for cid in chosen[:1]:
        card = plan.state.cards.get(cid)
        if card is None or card.zone != f"{pid}:hand" or not _permanent_card(plan, cid) \
                or not selectors.matches(plan, sel, card, chars.of(card, plan.info), pid, ctx.get("source_card")):
            raise ActionError("Choose a matching card from your hand")
        cards.append(cid)
    before = effects._remember(plan, ctx, e, cards)
    entries = [{"card": c, "player": pid, "actor": pid, "tapped": bool(e.get("tapped"))} for c in cards]
    if entries and not attachments.enter(plan, entries, ctx):
        return  # (an Aura chooses what it enchants; the resolution goes on from there)
    effects._moved(plan, ctx, e, before)
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"put_from_hand": put_from_hand}
RESUME = {"put_from_hand": resume}
