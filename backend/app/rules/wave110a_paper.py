"""-- wave 110A -- Psychic Paper: "As this Equipment becomes attached to a creature, choose a creature card name and a creature type." and
"Equipped creature has ward {1}, it can't be blocked, and its name and creature type are the last chosen name and creature type."

701.3a, 201.4: like Sanctuary Blade (wave110e_blade) the Equipment is queued as it becomes attached and engine.settle asks before anyone gets priority (it is no
trigger, nothing can respond): the creature card name (typed, 201.4a) and then the creature type, kept on the Equipment ("Chosen card name", "Chosen creature
type"). The static is the ward and unblockable grant plus a layer-3 name (613.1c) and a layer-4
creature type (205.1a, 613.1d) read from the Equipment's last choices at derive time (attached_types.layer45); the creature keeps its other types."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

ASK = "As this Equipment becomes attached to a creature, choose a creature card name and a creature type."
GRANT = "Equipped creature has ward {1}, it can't be blocked, and its name and creature type are the last chosen name and creature type."
NAME, TYPE = "Chosen card name", "Chosen creature type"


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    text = ability.text.strip()
    if text == ASK:
        return {"kind": "static", "static": "attach_choice110a", "effects": []}
    if text == GRANT:
        from app.rules import scripts

        native = scripts.define(replace(ability, text="Equipped creature has ward {1} and can't be blocked."), ch)
        return None if native is None else {**native, "paper110a": True, "layer4": {"add_subtypes": []}}  # the placeholder makes it a layer-4 static; layer45_definition fills in the real one
    return None


def ask(plan: Plan, src: Any) -> None:
    from app.rules import card_names
    from app.rules.plan import decide

    decide(plan, player=src.controller, kind="choose_one", prompt=f"{src.name}: choose a creature card name", source=src,
           options=[card_names.option("creature card name")], resume={"step": "paper_name110a", "card": src.id})


def resume_name(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.rules_state import DecisionOption
    from app.rules.creature_types import CREATURE_TYPES
    from app.rules.plan import decide

    r = d.resume
    src = plan.state.cards[r["card"]]
    plan.do({"type": "set_choice", "card_id": r["card"], "key": NAME, "value": chosen[0]}, actor=d.player)
    decide(plan, player=d.player, kind="choose_one", prompt=f"{src.name}: choose a creature type", source=src,
           options=[DecisionOption(id=t, label=t) for t in sorted(CREATURE_TYPES)], resume={**r, "step": "paper_type110a"})


def resume_type(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.creature_types import CREATURE_TYPES

    r = d.resume
    if chosen[0] not in CREATURE_TYPES:
        from app.game.errors import ActionError

        raise ActionError("Choose a creature type")
    plan.note(f"{plan.name(d.player)} chooses {plan.state.cards[r['card']].choices.get(NAME)} and {chosen[0]}", actor=d.player)
    plan.do({"type": "set_choice", "card_id": r["card"], "key": TYPE, "value": chosen[0]}, actor=d.player)
    if r["card"] in plan.rules.attach_asks110e:
        plan.rules.attach_asks110e.remove(r["card"])


def layer45_definition(state: Any, source: str, definition: dict[str, Any]) -> dict[str, Any]:
    """The name and creature type the Equipment last chose (nothing chosen yet: nothing to set)."""
    choices = state.cards[source].choices
    name, kind = choices.get(NAME), choices.get(TYPE)
    return {"who": "attached", **({"set_name": name} if name else {}), **({"layer4": {"set_creature_types": [kind]}} if kind else {})}


RESUME: dict[str, Any] = {"paper_name110a": resume_name, "paper_type110a": resume_type}
