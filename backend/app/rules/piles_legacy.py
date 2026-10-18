"""-- review 53 -- Games saved before wave 53D paused inside a face-up pile split (Fact or Fiction, Steam Augury: CR 700.3) resume here.

Wave 53D moved pile separation to ``pile_groups.pile_deal``; this is the old ``looking.piles`` machinery kept only so an old save's
pending "piles" effect or "piles_opponent" / "piles_split" / "piles_pick" decision still resumes. New games never reach it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key

if TYPE_CHECKING:
    from app.rules.plan import Plan


def _cards(plan: Plan, ctx: dict[str, Any]) -> list[str]:
    owner = ctx.get("looked_owner") or ctx["controller"]
    library = plan.state.zones.get(zone_key(owner, "library"), [])
    return [c for c in ctx.get("looked") or [] if c in library]


def piles(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Start: which opponent takes part (the controller chooses, 608.2d), then the separation."""
    from app.rules.effects import decide

    pid = ctx["controller"]
    if not _cards(plan, ctx):
        return True
    opponents = [p for p in plan.live() if p != pid]
    if not opponents:
        return True
    if len(opponents) == 1:
        return _separate(plan, ctx, e, opponents[0])
    decide(plan, player=pid, kind="choose_one", prompt=f"{ctx.get('name') or 'Piles'}: choose an opponent to "
           + ("separate the cards into two piles" if e["separator"] == "opponent" else "choose one of the piles"),
           options=[DecisionOption(id=p, label=plan.name(p)) for p in opponents], resume={"step": "piles_opponent", "ctx": ctx, "e": e})
    return False


def _separate(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], opponent: str) -> bool:
    from app.rules.effects import decide

    cards = _cards(plan, ctx)
    separator = opponent if e["separator"] == "opponent" else ctx["controller"]
    decide(plan, player=separator, kind="choose_cards",
           prompt=f"{ctx.get('name') or 'Piles'}: separate the revealed cards into two piles — choose the cards of the "
                  "first pile (the others are the second; a pile may be empty)",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in cards],
           min_choices=0, max_choices=len(cards), resume={"step": "piles_split", "ctx": ctx, "e": e, "opponent": opponent})
    return False


def resume_opponent(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    plan.note(f"{plan.name(d.player)} chooses {plan.name(chosen[0])}")
    if _separate(plan, r["ctx"], r["e"], chosen[0]):
        effects.continue_effects(plan, r["ctx"])


def resume_split(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import decide

    r = d.resume
    ctx, e = r["ctx"], r["e"]
    cards = _cards(plan, ctx)
    first = [c for c in cards if c in chosen]
    second = [c for c in cards if c not in chosen]
    names = [", ".join(plan.state.cards[c].name or "a card" for c in pile) or "no cards" for pile in (first, second)]
    plan.note(f"{plan.name(d.player)} separates the cards: {names[0]} / {names[1]}")
    chooser = ctx["controller"] if e["chooser"] == "you" else r["opponent"]
    decide(plan, player=chooser, kind="choose_one",
           prompt=f"{ctx.get('name') or 'Piles'}: choose the pile {plan.name(ctx['controller'])} puts into their hand "
                  "(the other goes to their graveyard)",
           options=[DecisionOption(id="1", label=f"Pile 1: {names[0]}"), DecisionOption(id="2", label=f"Pile 2: {names[1]}")],
           resume={"step": "piles_pick", "ctx": ctx, "piles": [first, second]})


def resume_pick(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    ctx = r["ctx"]
    pid = ctx["controller"]
    first, second = r["piles"]
    keep, rest = (first, second) if chosen[0] == "1" else (second, first)
    plan.note(f"{plan.name(d.player)} chooses pile {chosen[0]}")
    library = set(_cards(plan, ctx))
    keep, rest = [c for c in keep if c in library], [c for c in rest if c in library]
    if keep:
        plan.do({"type": "move", "card_ids": keep, "to": {"player": pid, "zone": "hand"}}, actor=pid)
    if rest:
        plan.do({"type": "move", "card_ids": rest, "to": {"player": plan.state.cards[rest[0]].owner, "zone": "graveyard"}}, actor=pid)
    ctx["looked"] = []
    effects.continue_effects(plan, ctx)
