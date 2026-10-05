"""-- suspend granted (wave 24C) -- "Exile target creature and put two time counters on it. If it doesn't have suspend, it gains suspend."
(Suspend), "… exile target nonland card from your graveyard with two time counters on it. If it doesn't have suspend, it gains suspend."
(Doom's Time Platform), "When this creature dies, exile it with three time counters on it and it gains suspend." (Epochrasite).

* 702.62b: a card is suspended while it has suspend, is in exile and has a time counter on it; at the beginning of its owner's upkeep a
  time counter comes off, and when the last is removed its owner may cast it without paying its mana cost (702.62c-d; a creature
  spell cast this way has haste, 702.62e). The engine tracks that with ``RulesState.suspended`` (casting.suspend, triggers._suspend,
  effects.suspend_tick): a card in the list is one that has suspend now. Gaining suspend is joining the list; a card that already
  has suspend printed is exiled with its counters by the same instruction and joins it too — "if it doesn't have suspend, it gains
  suspend" ends with the card suspended either way, so one instruction does both.
* "Exile X with N time counters on it" is read as the exile followed by the counters put on the card it became in exile (400.7j,
  the pronoun's binding: effects._moved): nothing can tell the two apart in between.
* A card that leaves exile without being cast and comes back is a new object (400.7); its old entry is dropped when it is next
  looked at (triggers._suspend: not in exile, or no time counter left).

Effect: ``{"do": "suspend_mark", "who": <the exiled card>}``. Refused (manual): "gains vanishing" and the other granted keywords (their
tick isn't a suspend), counters equal to a mana value chosen from a hand, a spell exiling itself as it is cast."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_COUNTED = re.compile(r"\b(?P<e>[Ee])xile (?P<what>it|that card|target [^.,]+?) (?:with|and put) (?P<n>an?|one|two|three|four|five|six|seven|eight|nine|ten) "
                      r"time counters? (?:on it)?(?P<gain> and it gains suspend)?(?=[.,]|$)")


_FOUND = re.compile(r"(exile cards from the top of your library until you exile an? [^.,]+?)\. Put (?P<n>an?|one|two|three|four|five|six|seven|eight|nine|ten) "
                    r"time counters on that card\. It gains suspend\.")


def rewrite(body: str) -> str:
    """"Exile X with N time counters on it [and it gains suspend]" / "Exile X and put N time counters on it" → "Exile X. Put N time
    counters on it. [It gains suspend.]" (separate sentences: the pronoun binds to what the first moved); "If it doesn't have suspend,
    it gains suspend." → "It gains suspend." (see the module docstring)."""
    body = body.replace("If it doesn't have suspend, it gains suspend.", "It gains suspend.")
    body = _FOUND.sub(lambda m: f"{m[1]}. Suspend that card with {m['n']} time counters.", body)
    return _COUNTED.sub(lambda m: f"{m['e']}xile {m['what']}. Put {m['n']} time counters on it" + (". It gains suspend" if m["gain"] else ""), body)


def mark(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    cards = effects._cards(plan, ctx, e["who"])
    effects._remember(plan, ctx, e, cards)
    for cid in cards:
        card = plan.state.cards[cid]
        if card.zone.endswith(":exile") and card.counters.get("time", 0) > 0 and cid not in plan.rules.suspended:
            plan.rules.suspended.append(cid)
            plan.note(f"{card.name} is suspended with {card.counters['time']} time counters", [cid])
    return True


def suspend_found(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"… until you exile a nonland card. Put two time counters on that card. It gains suspend.": the card the exile stopped at
    (ctx["found"], effects.exile_top), in exile now (400.7j). It has suspend first, the counters follow (a counter replacement can
    pause the resolution; 702.62b is read at the next upkeep)."""
    from app.rules import effects, replace

    cid = str(ctx.get("found") or "")
    card = plan.state.cards.get(cid)
    if card is None or not card.zone.endswith(":exile"):
        return True
    n = effects._amount(plan, ctx, e["n"])
    if n <= 0:
        return True
    if cid not in plan.rules.suspended:
        plan.rules.suspended.append(cid)
        plan.note(f"{card.name} is suspended with {n} time counters", [cid])
    return replace.put_counters(plan, [(cid, "time", n)], by=ctx["controller"], then=effects._then(ctx, e), ctx=ctx)


PRIMITIVES = {"suspend_mark": mark, "suspend_found": suspend_found}
