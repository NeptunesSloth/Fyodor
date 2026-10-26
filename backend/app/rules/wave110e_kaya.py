"""-- wave 110E -- Kaya, Spirits' Justice: "Whenever one or more creatures you control and/or creature cards in your graveyard are put into exile, you may choose a
creature card from among them. Until end of turn, target token you control becomes a copy of it, except it has flying."

603.2c: one trigger for the batch (the two halves are a counter union: they share one fired key). The token target is chosen as the trigger is put on the
stack (603.3d); the card is chosen as it resolves (608.2d) from the creature cards among the exiled objects (a token ceases to exist: 111.7, 704.5d).
707.2 / 707.4: the copy takes the chosen card's copiable values; 707.9a: the exception adds flying.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

TEXT = ("Whenever one or more creatures you control and/or creature cards in your graveyard are put into exile, you may choose a creature card from among them. "
        "Until end of turn, target token you control becomes a copy of it, except it has flying.")
_BATTLEFIELD = {"event": "leave", "subject": "sel", "sel": 'sel:{"controller":"you","types":["Creature"]}', "aggregate": True, "dest": "exile"}
_GRAVEYARD = {"event": "to_exile", "subject": "sel", "aggregate": True, "sel": 'sel:{"card":true,"types":["Creature"],"zones":[]}', "froms": ["graveyard"], "from_owner": "you"}


_BUSY = False


def join(body: str) -> Any:
    """608.2c / 603.2c: "Exile target X and target Y." is ONE instruction: both exiles happen at the same time (one event batch), so a "one or more ... are put
    into exile" trigger fires once. The second exile is marked ``join110e``; the effect runner closes the batch after it (effects._run_effects)."""
    global _BUSY
    if _BUSY or not re.fullmatch(r"Exile target [^.,;]+ and target [^.,;]+\.?", body):
        return None
    from app.rules import scripts

    _BUSY = True
    try:
        parsed = scripts.parse_effects(body)
    finally:
        _BUSY = False
    if parsed is None or [e["do"] for e in parsed[0]] != ["exile", "exile"]:
        return parsed
    return [parsed[0][0], {**parsed[0][1], "join110e": True}], parsed[1], parsed[2]


def definition(text: str) -> dict[str, Any] | None:
    if text != TEXT:
        return None
    return {"kind": "triggered", "trigger": "event", "optional": False, "target": {"what": 'sel:{"controller":"you","token":true}'},
            "cond": {"event": "either", "subject": "sel", "counter_union": True, "conds": [_BATTLEFIELD, _GRAVEYARD]},
            "effects": [{"do": "kaya110e"}]}


def _pool(plan: Plan, ctx: dict[str, Any]) -> list[str]:
    from app.rules import context

    seen = [*context.objects(plan, ctx, context.EVENT_NEW), *context.objects(plan, ctx, context.EVENT)]
    return [c for c in dict.fromkeys(seen) if (card := plan.state.cards.get(c)) is not None and card.zone.endswith(":exile") and not card.is_token
            and "Creature" in plan.ch(card).types]


def choose(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    pool = _pool(plan, ctx)
    if not pool:
        return True
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'Kaya'}: choose a creature card from among the exiled cards?",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "a card", card_id=c) for c in pool], min_choices=0, max_choices=1,
           resume={"step": "kaya110e", "ctx": ctx})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, copying, effects

    ctx = d.resume["ctx"]
    if len(chosen) > 1 or any(c not in _pool(plan, ctx) for c in chosen):
        raise ActionError("Choose at most one of the exiled creature cards")
    if chosen:
        context.bind_objects(plan, ctx, "kaya110e", chosen)
        if not copying.become_copy(plan, ctx, {"who": "target", "with": "ref:kaya110e", "excepts": [{"add_text": ["Flying"]}], "duration": "end_of_turn"}):
            return  # (a manual copy decision is waiting)
    effects.continue_effects(plan, ctx)


PRIMITIVES: dict[str, Any] = {"kaya110e": choose}
RESUME: dict[str, Any] = {"kaya110e": resume}
