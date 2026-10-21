"""Copiable as-entry coin forms (208.2b, 613.2a); previews never flip a coin."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

WHAT = "copiable coin form"
_TEXT = "As ~ enters, flip a coin. If the coin comes up heads, ~ enters as a 5/2 creature with haste. If it comes up tails, ~ enters as a 2/5 creature with defender."


def definition(text: str) -> dict[str, Any] | None:
    if text != _TEXT:
        return None
    return {
        "kind": "replacement",
        "replacement": "enters_choice",
        "effects": [{"do": "choose_value", "who": "you", "what": WHAT, "options": ["heads", "tails"]}],
    }


def form_recipe(plan: Plan, recipe: Any, answer: str) -> Any:
    from app.game.rules_state import CopyExcept
    from app.rules import copying

    heads = answer == "heads"
    return copying.with_excepts(
        recipe,
        [
            CopyExcept(
                power="5" if heads else "2",
                toughness="2" if heads else "5",
                add_text=["Haste" if heads else "Defender"],
            )
        ],
    )


def ensure_form(plan: Plan, card: Any, controller: str, answer: str) -> None:
    from app.rules import copying, layers

    if answer not in ("heads", "tails"):
        return
    oid = plan.oid(card)
    label = "Molten Sentry entry form: " + answer
    if any(e.layer == "1" and e.label == label and oid in e.affected for e in plan.rules.effects):
        return
    recipe = form_recipe(plan, copying.recipe_of(plan, card), answer)
    layers.add_effect(
        plan,
        affected=[oid],
        layer="1",
        controller=controller,
        source=copying.ENTERING + card.id,
        duration="permanent",
        copy_recipe=recipe,
        label=label,
    )


def run_coin(plan: Plan, player: str, data: dict[str, Any]) -> bool:
    from app.rules import effects

    data["do"] = "copiable_entry_coin"
    ctx = {
        "controller": player,
        "name": "Molten Sentry entering coin",
        "effects": [{"do": "coin_flip", "n": 1, "face": True}, {"do": "copiable_entry_coin_record"}],
        "next": 0,
        "body_done": data,
    }
    return effects.run_body(plan, ctx)


def record(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    data = ctx["body_done"]
    answer = "heads" if ctx["coin"] else "tails"
    if data["caller"] == "stack":
        card = plan.state.cards.get(data["card"])
        if card is not None and plan.oid(card) == data["object"]:
            plan.rules.entry_choices.setdefault(card.id, {})[WHAT] = answer
    elif data["caller"] == "entry":
        entry = data["entries"][data["index"]]
        entry["choices"] = {**(entry.get("choices") or {}), WHAT: answer}
    else:
        data["answers"][data["key"]] = answer
    return True


def resume(plan: Plan, data: dict[str, Any]) -> None:
    from app.rules import engine, replacements

    if data["caller"] == "stack":
        card = plan.state.cards.get(data["card"])
        if (
            card is not None
            and card.zone == "stack"
            and plan.oid(card) == data["object"]
            and plan.state.zones.get("stack", [])[-1:] == [card.id]
        ):
            engine.resolve_top_of_stack(plan)
        else:
            engine._after_resolution(plan)
    elif data["caller"] == "entry":
        entries = data["entries"]
        index = data["index"]
        entry = entries[index]
        card = plan.state.cards.get(entry["card"])
        if card is None or plan.oid(card) != data["object"]:
            from app.rules import attachments

            if attachments.enter(
                plan,
                [e for i, e in enumerate(entries) if i != index],
                data.get("ctx"),
                shuffle=data.get("shuffle"),
            ):
                replacements._finish_entries(plan, data.get("ctx"), data.get("shuffle"))
        else:
            replacements._enter_again(plan, entries, index, entry, data.get("ctx"), data.get("shuffle"))
    else:
        from app.rules import replace

        replace.resume_site(plan, data["resume"], data["answers"], data["resume"].get("order"))


PRIMITIVES = {"copiable_entry_coin_record": record}
THEN = {"copiable_entry_coin": resume}
