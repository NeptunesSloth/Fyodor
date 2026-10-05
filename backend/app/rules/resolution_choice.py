"""-- trigger other (wave 25B) -- "Create a Food token or a Treasure token." (Tireless Provisioner, Ant-Man's Army): the controller
chooses one of the instructions as the spell or ability RESOLVES (608.2d: "a player is asked for a decision as the instruction is
carried out"; it is not a modal ability, whose mode is chosen as it is put on the stack, 700.2a), and only the chosen one is
carried out. A private choice of the controller (no one else sees the question).

``{"do": "pick_one", "options": [{"label": …, "effects": [...]}, …]}``: the chosen option's effects are spliced into the resolution
right after this instruction (so they see the same context), and the resolution goes on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
STEP = "pick_one"


def pick_one(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    options = e["options"]
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose one",
           options=[DecisionOption(id=str(i), label=str(o["label"])) for i, o in enumerate(options)],
           resume={"step": STEP, "ctx": ctx, "options": options})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx = d.resume["ctx"]
    picked = d.resume["options"][int(chosen[0])]["effects"]
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *picked, *ctx["effects"][at:]]
    continue_effects(plan, ctx)


PRIMITIVES = {"pick_one": pick_one}
