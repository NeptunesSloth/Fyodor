"""-- attach on resolution (wave 110D) -- "{4}, {T}: Attach target Aura attached to a creature to another creature." (Crown of the Ages): only the Aura is
targeted (115.1); its new host is chosen as the ability resolves (701.3a), among the creatures other than the one it is attached to (701.3b) that the Aura
could enchant (303.4d)."""
from __future__ import annotations

from typing import Any

TEXT = "{4}, {T}: Attach target Aura attached to a creature to another creature."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    if ability.text != TEXT:
        return None
    d = scripts.define(replace(ability, text=TEXT.replace("to another creature", "to target creature")), ch)
    if d is None:
        return None
    d["target"], d["targets"] = d["targets"][0], None
    d["effects"] = [{"do": "attach_other110d", "src": "target"}]
    return d


def attach_other(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import attachments, effects
    from app.rules.targets import label

    auras = effects._cards(plan, ctx, e["src"])  # (still the targeted Aura, 608.2b: none left, nothing happens)
    if not auras:
        return True
    aura = auras[0]
    pool = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.ch(c).is_creature
            and c.id != plan.state.cards[aura].attached_to and attachments.host_problem(plan, plan.state.cards[aura], c.id) is None]
    if not pool:
        return True
    effects.decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'Attach'}: attach {label(plan, aura)} to which creature?",
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Creature", card_id=c) for c in pool], min_choices=1, max_choices=1,
                   resume={"step": "attach_other110d", "ctx": ctx, "aura": aura, "pool": pool})
    return False


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import attachments
    from app.rules.effects import continue_effects

    if len(chosen) != 1 or chosen[0] not in d.resume["pool"]:
        raise ActionError("Choose one of those creatures")
    attachments.attach(plan, d.resume["aura"], chosen[0], d.player)
    continue_effects(plan, d.resume["ctx"])

PRIMITIVES: dict[str, Any] = {"attach_other110d": attach_other}
RESUME: dict[str, Any] = {"attach_other110d": resume}
