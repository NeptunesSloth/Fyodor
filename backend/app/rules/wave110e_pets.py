"""Exotic Pets (wave 110E): two Fish tokens, then one counter of each kind among your creatures goes on either token, chosen per kind (122.1, 701.34)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ('Create two 1/1 blue Fish creature tokens with "This token can\'t be blocked." Then for each kind of counter among creatures you control, '
        "put a counter of that kind on either of those tokens.")
_MAKE = 'Create two 1/1 blue Fish creature tokens with "This token can\'t be blocked."'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.text.strip() != TEXT:
        return None
    native = scripts.define(replace(ability, text=_MAKE), ch)
    if native is None or len(native["effects"]) != 1 or native["effects"][0].get("do") != "create_token":
        return None
    return {**native, "effects": [{**native["effects"][0], "as": "pets110e"}, {"do": "pets110e"}]}


def _kinds(plan: Any, me: str) -> list[str]:
    seen: dict[str, None] = {}
    for c in plan.state.cards.values():
        if c.controller == me and c.zone.endswith(":battlefield") and "Creature" in plan.ch(c).types:
            seen.update((k, None) for k, n in sorted(c.counters.items()) if n > 0)
    return list(seen)


def _next(plan: Any, ctx: dict[str, Any], kinds: list[str], toks: list[str]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context, effects

    while kinds:
        if len(toks) == 1:  # (nothing to choose)
            context.bind_objects(plan, ctx, "pet110e", toks)
            effects.PRIMITIVES["add_counters"](plan, ctx, {"do": "add_counters", "who": "ref:pet110e", "kind": kinds.pop(0), "n": 1})
            continue
        opts = [DecisionOption(id=t, label=f"Fish token {i + 1}", card_id=t) for i, t in enumerate(toks)]
        effects.decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'Exotic Pets'}: put a {kinds[0]} counter on which token?",
                       options=opts, min_choices=1, max_choices=1, resume={"step": "pets110e", "ctx": ctx, "kinds": kinds, "toks": toks})
        return False
    return True


def pets(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context

    name = next((k for k in context.refs(ctx) if k.endswith("pets110e")), "pets110e")  # (a spell line's bindings are renamed l0_*)
    toks = [t for t in context.objects(plan, ctx, name) if t in plan.state.cards and plan.state.cards[t].zone.endswith(":battlefield")]
    return _next(plan, ctx, _kinds(plan, ctx["controller"]), toks) if toks else True


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects

    r = d.resume
    if len(chosen) != 1 or chosen[0] not in r["toks"]:
        raise ActionError("Choose one of the tokens")
    context.bind_objects(plan, r["ctx"], "pet110e", chosen)
    effects.PRIMITIVES["add_counters"](plan, r["ctx"], {"do": "add_counters", "who": "ref:pet110e", "kind": r["kinds"][0], "n": 1})
    if _next(plan, r["ctx"], r["kinds"][1:], r["toks"]):
        effects.continue_effects(plan, r["ctx"])


PRIMITIVES: dict[str, Any] = {"pets110e": pets}
RESUME: dict[str, Any] = {"pets110e": resume}
