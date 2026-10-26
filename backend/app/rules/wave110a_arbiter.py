"""-- wave 110A -- Leonin Arbiter: "Players can't search libraries. Any player may pay {2} for that player to ignore this effect until end of turn."

614.17 (can't search) as prohibitions' "cant_search" static. Scryfall ruling 2011-01-01: paying {2} is a special action (116.2) that its player may take any time they
have priority, it doesn't use the stack, it is per player, lasts the turn and covers any library; each Arbiter needs its own {2}. Taken with ``end_effect`` on the
Arbiter (licids.end_effect), recorded as a turn result for (player, Arbiter object)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

TEXT = "Players can't search libraries. Any player may pay {2} for that player to ignore this effect until end of turn."
COST = "{2}"
WHAT = "ignore_search110a"


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.text.strip() != TEXT:
        return None
    return {"kind": "static", "static": "cant_search", "who": "each", "ignore110a": True, "effects": []}


def has(ch: Any) -> bool:
    from app.rules import scripts

    return any(d.get("ignore110a") for d in scripts.definitions(ch).values())


def is_arbiter(plan: Plan, card: CardInstance) -> bool:
    return card.zone.endswith(":battlefield") and has(plan.ch(card))


def ignoring(plan: Plan, player: str, source: CardInstance) -> bool:
    turn = plan.state.turn.number
    oid = plan.oid(source)
    return any(x["what"] == WHAT and x["player"] == player and x["src"] == oid and x["turn"] == turn for x in plan.rules.results)


def record(plan: Plan, player: str, source: CardInstance) -> None:
    turn = plan.state.turn.number
    plan.rules.results = [x for x in plan.rules.results if x["turn"] == turn]
    plan.rules.results.append({"player": player, "what": WHAT, "src": plan.oid(source), "turn": turn})
    plan.note(f"{plan.name(player)} pays {COST} to ignore {source.name} until end of turn", [source.id], actor=player)
