"""Wave 110A: Comet, Stellar Pup - "0: Roll a six-sided die." and its four result rows (706.3, the rows are the following lines of the card).

* 107.7: "[+N]" is "put N loyalty counters on this permanent", "[-N]" is "remove N loyalty counters from it".
* "deals damage equal to the number of loyalty counters on him to a creature or player" chooses no target: its controller picks the recipient as it resolves
  (608.2d), the damage is read before the "[-2]" (the counters are still on Comet).
* 606.3 with "you may activate Comet's loyalty ability two more times this turn": the rows' last line gives two activations beyond the first (``loyalty_extra110a``,
  read by casting.ability_problem and used up in casting where the use is recorded).
The rows themselves are no abilities of their own: each is a marker static (the die's table is part of the loyalty ability above them)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.game.rules_state import DecisionOption
from app.rules.plan import decide

Context = dict[str, Any]
HEAD = "0: Roll a six-sided die."
ROWS = ('[+2], then create two 1/1 green Squirrel creature tokens. They gain haste until end of turn.',
        '[−1], then return a card with mana value 2 or less from your graveyard to your hand.',
        "~ deals damage equal to the number of loyalty counters on ~ to a creature or player, then [−2].",
        "[+1], and you may activate ~'s loyalty ability two more times this turn.")
BASE = (HEAD + " If the result is 1 to 2, put two loyalty counters on ~. If the result is 1 to 2, create two 1/1 green Squirrel creature tokens. "
        "If the result is 1 to 2, those tokens gain haste until end of turn. If the result is 3, remove a loyalty counter from ~. "
        "If the result is 3, return a card with mana value 2 or less from your graveyard to your hand.")


def _gate(lo: int, hi: int) -> dict[str, Any]:
    return {"do": "only_if", "cond": {"all": [{"value": {"die": "result"}, "op": ">=", "n": lo}, {"value": {"die": "result"}, "op": "<=", "n": hi}]}, "skip": 1}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == "static" and text in ROWS and [scripts.self_text(a.text, ch.name) for a in ch.abilities if a.kind == "static"][-4:] == list(ROWS):
        return {"kind": "static", "static": "comet_row110a", "effects": []}
    if text != HEAD or ability.kind != "loyalty":
        return None
    rows = [scripts.self_text(a.text, ch.name) for a in ch.abilities if a.index > ability.index]
    if rows != list(ROWS):
        return None
    d = scripts.define(replace(ability, text=BASE), ch)
    if d is None:
        return None
    return {**d, "effects": [*d["effects"], _gate(4, 5), {"do": "comet_damage110a"}, _gate(4, 5), {"do": "remove_counters", "who": "self", "kind": "loyalty", "n": 2},
                             _gate(6, 6), {"do": "add_counters", "who": "self", "kind": "loyalty", "n": 1}, _gate(6, 6), {"do": "loyalty_more110a", "n": 2}]}


def damage(plan: Any, ctx: Context, e: dict[str, Any]) -> bool:
    src = plan.state.cards.get(ctx.get("source_card") or "")
    n = src.counters.get("loyalty", 0) if src is not None and plan.oid(src) == ctx.get("source_object") else 0
    options = [DecisionOption(id=p, label=plan.name(p)) for p in plan.live()]
    options += [DecisionOption(id=c.id, label=c.name or "Creature", card_id=c.id) for c in plan.state.cards.values()
                if c.zone.endswith(":battlefield") and plan.in_game(c) and plan.ch(c).is_creature]
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Comet'}: choose a creature or player to be dealt {n} damage", options=options,
           resume={"step": "comet_damage110a", "ctx": ctx, "n": n}, source=src)
    return False


def resume_damage(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    who = f"player:{chosen[0]}" if chosen[0] in plan.state.players else f"obj:{plan.oid(plan.state.cards[chosen[0]])}"
    if d.resume["n"] > 0 and effects.PRIMITIVES["damage"](plan, ctx, {"do": "damage", "who": who, "n": d.resume["n"]}) or d.resume["n"] <= 0:
        effects.continue_effects(plan, ctx)


def more(plan: Any, ctx: Context, e: dict[str, Any]) -> bool:
    turn, left = plan.rules.loyalty_extra110a.get(ctx.get("source_object") or "", [0, 0])
    plan.rules.loyalty_extra110a[ctx["source_object"]] = [plan.state.turn.number, e["n"] + (left if turn == plan.state.turn.number else 0)]
    plan.note(f"{ctx.get('name') or 'It'}'s loyalty ability can be activated {e['n']} more times this turn (606.3)", actor=ctx["controller"])
    return True


def extra_left(r: Any, oid: str, turn: int) -> int:
    t, n = r.loyalty_extra110a.get(oid, [0, 0])
    return n if t == turn else 0


def use_extra(r: Any, oid: str, turn: int) -> None:
    r.loyalty_extra110a[oid] = [turn, extra_left(r, oid, turn) - 1]


PRIMITIVES = {"comet_damage110a": damage, "loyalty_more110a": more}
RESUME = {"comet_damage110a": resume_damage}
