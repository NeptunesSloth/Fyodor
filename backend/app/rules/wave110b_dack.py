"""-- (wave 110B) -- Dack Fayden, Helping Hand: "When Dack Fayden enters, reveal cards from the top of your library until you reveal X creature cards, where X is
the number of opponents you have. Put those creature cards onto the battlefield, then shuffle. They're goaded for the rest of the game. For each of those
permanents, choose a different opponent. Each opponent gains control of the permanent for which they were chosen."

* 701.15a goad with no end (keyword_actions.goad "forever"): the goader is Dack's controller, who stays so after control changes (ruling 2026-08-21: it still
  must attack another player if the goader left); a goad effect is locked to the object (400.7).
* 613.1b control effects (effects._control_effect), 608.2d: the choices are made as the ability resolves, each opponent is chosen for one permanent at most.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_REF = "dack110b"
_TEXT = ("Reveal cards from the top of your library until you reveal X creature cards, where X is the number of opponents you have. Put those creature "
         "cards onto the battlefield, then shuffle. They're goaded for the rest of the game. For each of those permanents, choose a different opponent. "
         "Each opponent gains control of the permanent for which they were chosen.")


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    if body[:1].upper() + body[1:] != _TEXT:
        return None
    got = scripts.parse_effects(_TEXT.split(" They're goaded")[0])
    if got is None or got[1] is not None or [e["do"] for e in got[0]] != ["look_top", "pick_looked", "shuffle_library"]:
        return None
    effects = [{**e, "as": _REF} if e["do"] == "pick_looked" else e for e in got[0]]
    return [*effects, {"do": "dack_give110b"}], None, False


def give(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import context, keyword_actions

    cards = [c for c in context.objects(plan, ctx, _REF) if plan.state.cards[c].zone.endswith(":battlefield")]
    if cards:
        keyword_actions.goad(plan, ctx, {"do": "goad", "who": f"ref:{_REF}", "forever": True})
    return _assign(plan, ctx, cards, [p for p in plan.live() if p != ctx["controller"]], [])


def _assign(plan: Plan, ctx: Context, cards: list[str], free: list[str], pairs: list[list[str]]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects, layers
    from app.rules.plan import decide

    cards = list(cards)
    while cards and free:
        if len(free) > 1:
            decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Dack'}: choose a different opponent for {plan.state.cards[cards[0]].name}",
                   options=[DecisionOption(id=p, label=plan.name(p)) for p in free],
                   resume={"step": "dack110b", "ctx": ctx, "cards": cards, "free": free, "pairs": pairs})
            return False
        pairs.append([cards.pop(0), free.pop(0)])
    for cid, opp in pairs:
        if plan.state.cards[cid].zone.endswith(":battlefield"):
            effects._control_effect(plan, ctx, [cid], opp, "permanent")
    layers.control_sync(plan)
    return True


def resume_give(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    r = d.resume
    if len(chosen) != 1 or chosen[0] not in r["free"]:
        raise ActionError("Choose one of the opponents offered")
    pair = [r["cards"][0], chosen[0]]
    plan.note(f"{plan.name(d.player)} chooses {plan.name(chosen[0])} for {plan.state.cards[pair[0]].name}", actor=d.player)
    if _assign(plan, r["ctx"], r["cards"][1:], [p for p in r["free"] if p != chosen[0]], [*r["pairs"], pair]):
        effects.continue_effects(plan, r["ctx"])


PRIMITIVES = {"dack_give110b": give}
RESUME = {"dack110b": resume_give}
