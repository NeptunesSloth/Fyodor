"""Cemetery Desecrator (wave 110F): "When this creature enters or dies, exile another card from a graveyard. When you do, choose one — • Remove X counters from
target permanent, where X is the mana value of the exiled card. • Target creature an opponent controls gets -X/-X until end of turn, where X is the mana value of
the exiled card."

Nothing is targeted by the exile (it is chosen as the ability resolves, 608.2d, so "another" only leaves out the Desecrator itself); 603.12: "When you do" is a
reflexive triggered ability that triggers only if a card really was exiled; its modes and targets are chosen as it goes on the stack (700.2, 603.3c-d). X is the
exiled card's mana value as it was in the graveyard (608.2h), carried as the reflexive event's amount (``x_event``)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.game.rules_state import DecisionOption, TriggerEvent

HEADER = "When ~ enters or dies, exile another card from a graveyard. When you do, choose one —"
B1 = "• Remove X counters from target permanent, where X is the mana value of the exiled card."
B2 = "• Target creature an opponent controls gets -X/-X until end of turn, where X is the mana value of the exiled card."
_WHERE = ", where X is the mana value of the exiled card."


def definitions(ab: Any, ch: Any) -> dict[int, Any] | None:
    from app.rules import modal_abilities, scripts

    if ab.kind != "triggered" or scripts.self_text(ab.text, ch.name) != HEADER:
        return None
    bullets = modal_abilities._bullets(ch, ab.index)
    if [scripts.self_text(b.text, ch.name) for b in bullets] != [B1, B2]:
        return {}
    probe = scripts.define(replace(ab, text="When ~ enters or dies, draw a card."), ch)
    if probe is None or probe["kind"] != "triggered":
        return {}
    modes = []
    for k, b in enumerate(bullets):
        found = scripts.parse_effects(b.text[2:].replace(_WHERE, "."))  # (X reads the reflexive event's amount: x_event)
        if found is None or found[2]:
            return {}
        modes.append({"text": b.text[2:].strip(), "effects": scripts.rename_bindings(found[0], f"m{k}_"), "target": scripts.target_fields(found[1])["target"]})
    reflexive = {"kind": "triggered", "trigger": "reflexive", "effects": [], "target": None, "optional": False, "modes": modes, "x_event": True,
                 "modal": {"min": 1, "max": 1, "repeat": False, "condition": None, "memory": None, "index": ab.index, "form": "triggered"}}
    out: dict[int, Any] = {ab.index: {**probe, "effects": [{"do": "desecrate110f", "ability": reflexive}]}}
    for b in bullets:
        out[b.index] = {"kind": "mode", "of": ab.index, "form": "triggered", "memory": None, "effects": []}
    return out


def desecrate(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Choose and exile the card (the controller picks among all graveyards, 608.2d), then the reflexive trigger with its mana value."""
    from app.rules.plan import decide

    here = [c.id for c in plan.state.cards.values() if c.zone.endswith(":graveyard") and c.id != ctx.get("source_card")]
    if len(here) > 1:
        decide(plan, player=ctx["controller"], kind="choose_cards", prompt="Exile another card from a graveyard",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in here],
               resume={"step": "desecrate110f", "ctx": ctx, "e": e})
        return False
    return _exile(plan, ctx, e, here)


def _exile(plan: Any, ctx: dict[str, Any], e: dict[str, Any], picked: list[str]) -> bool:
    from app.rules import triggers
    from app.rules.trigger_multipliers import REFLEXIVE

    if not picked:
        return True
    card = plan.state.cards[picked[0]]
    value = plan.ch(card).mana_value  # 608.2h: as it was in the graveyard
    plan.do({"type": "move", "card_ids": [card.id], "to": {"zone": "exile"}}, actor=ctx["controller"])
    if plan.state.cards[card.id].zone.endswith(":exile"):  # 603.12: "when you do" only if it was exiled
        triggers._add(plan, controller=ctx["controller"], source_card=ctx.get("source_card") or "", source_object=ctx.get("source_object") or "",
                      name=str(ctx.get("name") or ""), index=REFLEXIVE, definition=e["ability"], event=TriggerEvent(kind="reflexive", amount=int(value)))
    return True


def resume_desecrate(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    if _exile(plan, ctx, d.resume["e"], chosen[:1]):
        effects.continue_effects(plan, ctx)


PRIMITIVES = {"desecrate110f": desecrate}
RESUME = {"desecrate110f": resume_desecrate}
