"""Wave 110A: Averna, the Chaos Bloom - "As you cascade, you may put a land card from among the exiled cards onto the battlefield tapped." (702.85a, reminder:
after the last card is exiled but before deciding whether to cast the nonland card). The exiled lands are all in ``missed`` (the hit is a nonland card)."""

from __future__ import annotations

from typing import Any

from app.game.rules_state import DecisionOption
from app.rules.plan import decide

Context = dict[str, Any]
TEXT = "As you cascade, you may put a land card from among the exiled cards onto the battlefield tapped."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    return {"kind": "static", "static": "cascade_land110a", "effects": []} if scripts.self_text(ability.text, ch.name) == TEXT else None


def ask(plan: Any, ctx: Context, e: dict[str, Any], missed: list[str], hit: str | None) -> bool:
    """True while the controller is choosing (the cascade goes on in :func:`resume`)."""
    from app.rules import characteristics as chars
    from app.rules import permissions

    pid = ctx["controller"]
    lands = [c for c in missed if chars.of(plan.state.cards[c], plan.info).is_land]
    if not lands or not any(src.controller == pid for src, _, _ in permissions._table_statics(plan.state, plan.info, {"cascade_land110a"})):
        return False
    decide(plan, player=pid, kind="choose_cards", prompt="Cascade: you may put a land card from among the exiled cards onto the battlefield tapped",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Land", card_id=c) for c in lands], min_choices=0, max_choices=1,
           resume={"step": "cascade_land110a", "ctx": ctx, "mv": e["mv"], "missed": missed, "hit": hit})
    return True


def tail(plan: Any, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    return effects.cascade_end(plan, ctx, e["mv"], e["missed"], e["hit"])


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import attachments
    from app.rules.effects import continue_effects

    r = d.resume
    ctx, missed = r["ctx"], [c for c in r["missed"] if c not in chosen]
    ctx["effects"].insert(ctx["next"], {"do": "cascade_end110a", "mv": r["mv"], "missed": missed, "hit": r["hit"]})  # the rest of the cascade runs after any entry choice
    if not chosen or attachments.enter(plan, [{"card": chosen[0], "player": ctx["controller"], "actor": ctx["controller"], "tapped": True}], ctx):
        continue_effects(plan, ctx)


PRIMITIVES = {"cascade_end110a": tail}
RESUME = {"cascade_land110a": resume}
