"""-- Mishra, Claimed by Gix (wave 110D) -- "Whenever you attack, each opponent loses X life and you gain X life, where X is the number of attacking creatures. If Mishra, Claimed by
Gix and a creature named Phyrexian Dragon Engine are attacking, and you both own and control them, exile them, then meld them into Mishra, Lost to Phyrexia. It enters tapped and attacking."

603.2/608.2c: the drain happens first (X counts the attackers then); the "if" is checked as the ability resolves. 701.42a the meld (merged.meld); 508.4 the melded permanent enters tapped
and attacking, its controller choosing whom it attacks (token_grammar.enter_attacking). ponytail: it is tapped right after it enters, not "as it enters" (no replacement sees the difference).
"""

from __future__ import annotations

from typing import Any

from app.rules.plan import Plan

LINE = ("Whenever you attack, each opponent loses X life and you gain X life, where X is the number of attacking creatures. If ~ and a creature named Phyrexian Dragon Engine are attacking, "
        "and you both own and control them, exile them, then meld them into ~, Lost to Phyrexia. It enters tapped and attacking.")  # (self_text turns the short name "Mishra" into ~)
RESULT = "Mishra, Lost to Phyrexia"


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    d = scripts.define(replace(ability, text=LINE.split(" If ~")[0]), ch)
    if d is None:
        return None
    return {**d, "effects": [*d["effects"], {"do": "mishra_meld110d"}]}


def meld(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import merged, token_grammar

    src = plan.state.cards.get(ctx.get("source_card") or "")
    partner = merged.partner_of(plan, ctx, "creature", "Phyrexian Dragon Engine")
    if src is None or partner is None or not (src.is_attacking and partner.is_attacking):
        return True
    if not merged.meld(plan, ctx, {"result": RESULT}) or not src.melded:
        return False
    plan.do({"type": "tap", "card_ids": [src.id], "tapped": True}, actor=ctx["controller"])
    return token_grammar.enter_attacking(plan, ctx, [src.id])


PRIMITIVES = {"mishra_meld110d": meld}
