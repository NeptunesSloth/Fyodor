"""-- wave 110L -- exact Oracle wordings of single cards, built from parts the grammar already reads, plus a few small primitives.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

Def = dict[str, Any]
Context = dict[str, Any]

# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)


def _swap_hands(d: Def) -> Def:
    """Rakdos Augermage: each hand is revealed in turn and the *other* player picks the discard (701.9a, 701.20a: a revealed hand is public)."""
    return {**d, "effects": [{"do": "pick_discard110l", "owner": "you", "chooser": "target"},
                             {"do": "pick_discard110l", "owner": "target", "chooser": "you"}]}


_BUILD["{T}: Reveal your hand and discard a card of target opponent's choice. Then that player reveals their hand and discards a card of your choice. Activate only as a sorcery."] = (
    "{T}: Target opponent loses 1 life. Activate only as a sorcery.", _swap_hands)


def _chime(d: Def) -> Def:
    """Apocalypse Chime: only the permanents with a name first printed in Homelands (wave110l_homelands) are destroyed."""
    from dataclasses import replace as rep

    from app.rules import selectors

    out = []
    for e in d["effects"]:
        if e.get("do") == "destroy":
            sel = selectors.from_key(e["who"])
            e = {**e, "who": rep(sel, extras=(*sel.extras, "first_hml110l")).key()}
        out.append(e)
    return {**d, "effects": out}


_BUILD["{2}, {T}, Sacrifice this artifact: Destroy all nontoken permanents with a name originally printed in the Homelands expansion. They can't be regenerated."] = (
    "{2}, {T}, Sacrifice this artifact: Destroy all nontoken permanents. They can't be regenerated.", _chime)


def pick_discard(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The owner reveals their hand; the chooser picks one card of it, which is discarded (an empty hand reveals nothing and discards nothing)."""
    from app.rules.effects import _players, decide, zone_key

    owner, chooser = _players(plan, ctx, e["owner"])[:1], _players(plan, ctx, e["chooser"])[:1]
    if not owner or not chooser:
        return True
    hand = list(plan.state.zones.get(zone_key(owner[0], "hand"), []))
    if not hand:
        plan.note(f"{plan.name(owner[0])} reveals an empty hand", actor=owner[0])
        return True
    plan.do({"type": "reveal", "card_ids": hand}, actor=owner[0])
    if len(hand) > 1:
        decide(plan, player=chooser[0], kind="choose_cards", prompt=f"Choose a card from {plan.name(owner[0])}'s hand to be discarded",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in hand],
               min_choices=1, max_choices=1, resume={"step": "pick_discard110l", "ctx": ctx, "hand": hand, "owner": owner[0]})
        return False
    _finish(plan, ctx, owner[0], hand, hand)
    return True


def _finish(plan: Plan, ctx: Context, owner: str, hand: list[str], chosen: list[str]) -> None:
    from app.rules import prohibitions

    take = [c for c in chosen if c in plan.state.cards and plan.state.cards[c].zone == f"{owner}:hand"]
    if take and (why := prohibitions.cant_cause_discard(plan, owner, ctx["controller"])) is not None:
        plan.note(f"{why}: {plan.name(owner)} can't be made to discard cards")
        take = []
    rest = [c for c in hand if c not in take and c in plan.state.cards and plan.state.cards[c].zone == f"{owner}:hand"]
    if take:
        plan.do({"type": "move", "card_ids": take, "to": {"zone": "graveyard"}}, actor=ctx["controller"])
    if rest:  # 701.20a: the rest is no longer revealed
        plan.do({"type": "hide", "card_ids": rest}, actor=ctx["controller"])


def resume_pick_discard(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    _finish(plan, d.resume["ctx"], d.resume["owner"], d.resume["hand"], chosen)
    continue_effects(plan, d.resume["ctx"])


PRIMITIVES = {"pick_discard110l": pick_discard}
RESUME = {"pick_discard110l": resume_pick_discard}
