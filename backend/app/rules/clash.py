"""-- clash (wave 12A) -- "Clash with an opponent." (701.30b) and "If you win, …" (701.30d). Researched against CR 2026-09-25.

* 701.30b: the controller chooses an opponent (a decision only with several); both clash.
* 701.30c: each clashing player reveals their top card at the same time (public: ``reveal_top``); then, in APNAP order, each
  decides whether that card goes to the bottom of their library (a decision for that player); the cards move together.
* 701.30d: a player wins if the revealed card's mana value is higher than all other revealed cards'. An empty library
  reveals nothing, so a lone revealed card wins. "If you win" reads this resolution's own clash (``ctx["clash"]``).

Refused (manual): "whenever you clash" triggers, repeating a clash ("if you win, repeat this process").
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.game.state import zone_key
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
STEP = "clash"
CLASHED = "clashed"


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "clash"}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(re.compile(r"^clash with an opponent$"), _build)]


def clash(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    pid = ctx["controller"]
    opponents = [p for p in plan.live() if p != pid]
    if not opponents:
        return True
    if len(opponents) == 1:
        return _reveal(plan, ctx, opponents[0])
    decide(plan, player=pid, kind="choose_one", prompt=f"{ctx.get('name') or 'Clash'}: choose an opponent to clash with",
           options=[DecisionOption(id=p, label=plan.name(p)) for p in opponents], resume={"step": STEP, "ctx": ctx})
    return False


def _reveal(plan: Plan, ctx: Context, opponent: str) -> bool:
    from app.rules import context

    context.bind_players(ctx, CLASHED, [opponent])  # -- attached (wave 100F) -- "Otherwise, that player …" (Captivating Glance): the opponent clashed with
    players = [p for p in plan.apnap() if p in (ctx["controller"], opponent)]
    cards: dict[str, str] = {}
    for p in players:
        library = plan.state.zones.get(zone_key(p, "library"), [])
        if library:
            plan.do({"type": "reveal_top", "player": p, "count": 1}, actor=p)
            cards[p] = library[0]
    mv = {p: plan.ch(plan.state.cards[c]).mana_value for p, c in cards.items()}
    winners = [p for p in mv if all(mv[p] > v for q, v in mv.items() if q != p)]
    ctx["clash"] = ctx["controller"] in winners
    plan.note(f"Clash: {plan.name(winners[0])} wins" if winners else "Clash: no player wins", actor=ctx["controller"])
    return _ask(plan, ctx, players, cards, [])


def _ask(plan: Plan, ctx: Context, players: list[str], cards: dict[str, str], bottom: list[str]) -> bool:
    for i, p in enumerate(players):
        if p in cards:
            decide(plan, player=p, kind="choose_one",
                   prompt=f"{ctx.get('name') or 'Clash'}: put {plan.state.cards[cards[p]].name} on the bottom of your library?",
                   options=[DecisionOption(id="top", label="Keep it on top"), DecisionOption(id="bottom", label="Put it on the bottom")],
                   resume={"step": STEP, "ctx": ctx, "players": players[i + 1:], "cards": cards, "mine": cards[p], "bottom": bottom})
            return False
    for cid in bottom:  # 701.30c: the cards chosen move at the same time
        owner = plan.state.cards[cid].owner
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": owner, "zone": "library"}, "position": "bottom"}, actor=owner)
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    ctx = r["ctx"]
    if "mine" not in r:  # the opponent chosen
        if len(chosen) != 1 or chosen[0] not in plan.live() or chosen[0] == d.player:
            raise ActionError("Choose an opponent")
        plan.note(f"{plan.name(d.player)} chooses {plan.name(chosen[0])}")
        if _reveal(plan, ctx, chosen[0]):
            effects.continue_effects(plan, ctx)
        return
    if chosen not in (["top"], ["bottom"]):
        raise ActionError("Choose top or bottom")
    bottom = r["bottom"]
    if chosen == ["bottom"]:
        bottom = [*bottom, r["mine"]]
    else:
        plan.do({"type": "hide", "card_ids": [r["mine"]]}, actor=d.player)
    cards = {p: c for p, c in r["cards"].items() if p in r["players"]}
    if _ask(plan, ctx, r["players"], cards, bottom):
        effects.continue_effects(plan, ctx)


PRIMITIVES = {"clash": clash}
