"""CR 101.4, 118.12: shared optional damage costs (Browbeat, Vexing Devil).

Every eligible player chooses in APNAP order; choices precede the damage. The official
Vexing Devil ruling explicitly gives every opponent a choice, even after another accepts.
No priority or mana-payment window exists during these choices. Ordinary damage primitives
then handle the simultaneous damage, replacements, prevention, and last known source.
"""
from __future__ import annotations

import re
from typing import Any

from app.game.rules_state import DecisionOption
from app.rules import context
from app.rules.plan import Plan, decide

_TEXT = re.compile(
    r"^any (?P<who>player|opponent) may have (?P<src>~|it|this creature|this permanent|this spell) "
    r"deal (?P<n>\d+) damage to them\. If (?P<gate>no one does|a player does), (?P<rest>.+)$", re.I | re.S)
STEP = "shared_damage_choice"


def parse(body: str, it: str | None, event_player: bool) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    m = _TEXT.fullmatch(body.strip())
    if m is None or (m["src"].lower() == "it" and it not in ("self", "self_gone")):
        return None
    rest = scripts.parse_effects(m["rest"], it=it, event_player=event_player)
    if rest is None or rest[2] or not rest[0] or any(e["do"] == "shared_damage" for e in rest[0]):
        return None
    bind = "shared_damage_paid"
    return [
        {"do": "shared_damage", "who": m["who"].lower(), "n": int(m["n"]), "bind": bind},
        {"do": "only_if", "cond": {"succeeded": bind, **({"negate": True} if m["gate"].lower() == "no one does" else {})},
         "skip": len(rest[0])}, *rest[0]], rest[1], False


def start(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    if e["who"] == "target":  # -- multi (wave 100M) -- "Target opponent may have ~ deal 4 damage to them." (Risk Factor): that player alone
        from app.rules import effects

        return _ask(plan, ctx, e, effects._players(plan, ctx, "target")[:1], [])
    players = [p for p in plan.apnap() if e["who"] == "player" or p != ctx["controller"]]
    return _ask(plan, ctx, e, players, [])


def _ask(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], remaining: list[str], accepted: list[str]) -> bool:
    remaining = [p for p in remaining if p in plan.live()]
    if not remaining:
        accepted = [p for p in accepted if p in plan.live()]
        context.bind_payment(ctx, e["bind"], bool(accepted))
        hurt = [{"do": "damage", "who": f"player:{p}", "n": e["n"],
                 **({"with_next": True} if i < len(accepted) - 1 else {})} for i, p in enumerate(accepted)]
        at = ctx["next"]
        ctx["effects"] = [*ctx["effects"][:at], *hurt, *ctx["effects"][at:]]
        return True
    payer = remaining[0]
    decide(plan, player=payer, kind="choose_one",
           prompt=f"{ctx.get('name') or 'The source'}: have it deal {e['n']} damage to you?",
           options=[DecisionOption(id="pay", label=f"Take {e['n']} damage"), DecisionOption(id="decline", label="Decline")],
           resume={"step": STEP, "ctx": ctx, "e": e, "remaining": remaining[1:], "accepted": accepted},
           source=plan.state.cards.get(ctx.get("source_card") or ""))
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    accepted = [*r["accepted"], *([d.player] if chosen == ["pay"] else [])]
    plan.note(f"{plan.name(d.player)} {'chooses' if chosen == ['pay'] else 'declines'} to have "
              f"{r['ctx'].get('name') or 'the source'} deal {r['e']['n']} damage to them")
    if _ask(plan, r["ctx"], r["e"], r["remaining"], accepted):
        effects.continue_effects(plan, r["ctx"])


PRIMITIVES = {"shared_damage": start}
RESUME = {STEP: resume}
