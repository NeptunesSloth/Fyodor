"""Native linked chosen-color pair entry receipts and cast intersections."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

if TYPE_CHECKING:
    from app.game.rules_state import Decision
    from app.rules.plan import Plan

TEXT = "Whenever you cast a spell, if it's at least one of the chosen colors, you gain 1 life for each of the chosen colors it is."
COLORS = {"White": "W", "Blue": "U", "Black": "B", "Red": "R", "Green": "G"}
CONDITION = {"chosen_color_pair_overlap": True, "object": "event"}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import events
    from app.rules.oracle import parse_abilities

    if ability.text != TEXT:
        return None
    cond = events.parse_condition("you cast a spell")
    assert cond is not None
    return {
        "kind": "triggered",
        "trigger": "event",
        "cond": cond,
        "if": dict(CONDITION),
        "color_pair_own": not ability.borrowed_origin
        and any(
            a.index == ability.index and a.text == ability.text
            for a in parse_abilities(ch.oracle_text, spell=ch.is_instant_or_sorcery)
        ),
        "effects": [{"do": "only_if", "cond": dict(CONDITION), "skip": 1}, {"do": "chosen_pair_gain"}],
    }


def acquisition(plan: Plan, oid: str) -> str | None:
    best = None
    for effect in plan.rules.effects:
        if (
            effect.layer == "1"
            and effect.copy_recipe is not None
            and oid in effect.affected
            and (best is None or effect.timestamp > best.timestamp)
        ):
            best = effect
    return best.id if best is not None else None


def record_entry(plan: Plan, card_id: str, choices: dict[str, str] | None) -> None:
    from app.game.rules_state import ChosenColorPairReceipt

    if choices is None or "color" not in choices or "second color" not in choices:
        return
    card = plan.state.cards.get(card_id)
    if card is None or not card.zone.endswith(":battlefield"):
        return
    colors = [COLORS.get(choices[k]) for k in ("color", "second color")]
    if any(c is None for c in colors) or len(set(colors)) != 2:
        return
    oid = plan.oid(card)
    alive = {
        plan.oid(c) for c in plan.state.cards.values() if c.zone.endswith((":battlefield", ":phased"))
    } | set(plan.rules.lki)
    plan.rules.chosen_color_pairs = {
        key: value for key, value in plan.rules.chosen_color_pairs.items() if key in alive
    }
    plan.rules.chosen_color_pairs[oid] = ChosenColorPairReceipt(
        card=card_id, colors=(str(colors[0]), str(colors[1])), acquisition=acquisition(plan, oid)
    )


def _capture(plan: Plan, oid: str, own: bool) -> dict[str, Any]:
    binding = {"source_object": oid, "status": "unknown", "colors": []}
    card = next(
        (c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.oid(c) == oid), None
    )
    if card is None:
        return binding
    if not own:
        return {**binding, "status": "known"}
    shown = [COLORS.get(card.choices.get(k, "")) for k in ("Chosen color", "Chosen second color")]
    if shown == [None, None]:
        return {**binding, "status": "known"}
    receipt = plan.rules.chosen_color_pairs.get(oid)
    if receipt is None or receipt.card != card.id:
        return binding
    if acquisition(plan, oid) != receipt.acquisition:
        return {**binding, "status": "known"}
    if tuple(shown) != receipt.colors:
        return binding
    return {**binding, "status": "known", "colors": list(receipt.colors)}


def _unbound(cond: Any) -> bool:
    return (
        isinstance(cond, dict)
        and set(cond) == set(CONDITION)
        and cond["chosen_color_pair_overlap"] is True
        and cond["object"] == "event"
    )


def freeze_trigger(plan: Plan, d: dict[str, Any], source_object: str) -> dict[str, Any]:
    if not _unbound(d.get("if")):
        return d
    effects = d.get("effects") or []
    if (
        len(effects) != 2
        or effects[0] != {"do": "only_if", "cond": CONDITION, "skip": 1}
        or effects[1] != {"do": "chosen_pair_gain"}
    ):
        return d
    binding = _capture(plan, source_object, d.get("color_pair_own") is True)
    condition = {**CONDITION, "binding": binding}
    return {
        **d,
        "if": condition,
        "effects": [
            {"do": "only_if", "cond": condition, "skip": 1},
            {"do": "chosen_pair_gain", "binding": binding},
        ],
    }


def _valid_binding(ctx: dict[str, Any], binding: Any) -> bool:
    if not isinstance(binding, dict) or set(binding) != {"source_object", "status", "colors"}:
        return False
    if not isinstance(binding["source_object"], str) or binding["source_object"] != ctx.get("source_object"):
        return False
    colors = binding["colors"]
    if not isinstance(colors, list) or not all(isinstance(c, str) and c in COLORS.values() for c in colors):
        return False
    if binding["status"] == "unknown":
        return colors == []
    return binding["status"] == "known" and (colors == [] or len(colors) == 2 and len(set(colors)) == 2)


def overlap(plan: Plan, ctx: dict[str, Any], binding: dict[str, Any] | None = None) -> int | None:
    from app.game.rules_state import ObjectRef
    from app.rules import context

    if binding is None:
        # Legacy unbound abilities cannot prove which acquired pair made a choice.
        source = plan.state.cards.get(ctx.get("source_card") or "")
        if (
            source is not None
            and source.zone.endswith(":battlefield")
            and plan.oid(source) == ctx.get("source_object")
            and not source.choices
        ):
            return 0
        return None
    if not _valid_binding(ctx, binding) or binding["status"] == "unknown":
        return None
    pair = binding["colors"]
    if not pair:
        return 0
    event = ctx.get("event") or {}
    if (
        event.get("kind") != "cast"
        or not isinstance(event.get("objects"), list)
        or len(event["objects"]) != 1
    ):
        return None
    try:
        ref = ObjectRef.model_validate(event["objects"][0])
    except (ValidationError, TypeError):
        return None
    if ref.zone != "stack":
        return None
    spell = plan.state.cards.get(ref.card)
    current = spell is not None and spell.zone == "stack" and plan.oid(spell) == ref.object_id
    previous = context.snapshot(plan, ref)
    if not current and (
        previous is None
        or previous.object_id != ref.object_id
        or previous.card != ref.card
        or previous.zone != "stack"
    ):
        return None
    info = context.info(plan, ctx, "event")
    return len(set(pair) & set(info[1].colors)) if info is not None else None


def holds(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    if _unbound(cond):
        amount = overlap(plan, ctx)
    elif (
        set(cond) == {"chosen_color_pair_overlap", "object", "binding"}
        and cond["chosen_color_pair_overlap"] is True
        and cond["object"] == "event"
        and _valid_binding(ctx, cond["binding"])
    ):
        amount = overlap(plan, ctx, cond["binding"])
    else:
        return False
    return amount is None or amount > 0


def gain(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    amount = overlap(plan, ctx, effect.get("binding"))
    if amount is None:
        decide(
            plan,
            player=ctx["controller"],
            kind="manual_resolution",
            prompt="This older saved trigger lacks the original linked entry choice or spell color history. Resolve Tablet of the Guilds by hand, then press Done.",
            options=[DecisionOption(id="done", label="Done")],
            resume={"step": "chosen_pair_legacy", "ctx": ctx},
        )
        return False
    if amount:
        ctx["effects"][ctx["next"] : ctx["next"]] = [{"do": "gain_life", "who": "you", "n": amount}]
    return True


def legacy_done(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    if chosen != ["done"]:
        raise ActionError("Finish the manual resolution with Done")
    if d.resume is None or not isinstance(d.resume.get("ctx"), dict):
        raise ActionError("The saved manual continuation is missing")
    effects.continue_effects(plan, d.resume["ctx"])


PRIMITIVES = {"chosen_pair_gain": gain}
RESUME = {"chosen_pair_legacy": legacy_done}
