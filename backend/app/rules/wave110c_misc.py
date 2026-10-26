"""-- exact wordings (wave 110C) -- one-off cards: Volcano Hellion."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

ECHO_LIFE = "This creature has echo {X}, where X is your life total."  # 702.30a, the cost is {N}, N = the controller's life total when it is paid
HELLION = "When this creature enters, it deals an amount of damage of your choice to you and target creature. The damage can't be prevented."


RELENTLESS = ("When this creature dies, you may pay {X}. If you do, return another target Zombie creature card with mana value X from your graveyard to the "
              "battlefield.")


SHUTTLE = ("Midnight Entity — Whenever this Vehicle attacks, defending player faces a villainous choice — That player sacrifices a creature of their choice, or you gain "
           "control of a creature of your choice that player controls until end of turn. If you gain control of a creature this way, tap it, and it's attacking that player.")


GLYPH = ("When this artifact enters, if you cast it, for each player, choose a creature with power 2 or less that player controls. "
         "Then destroy all creatures except creatures chosen this way.")


SIEGE = ("When this Siege enters, reveal any number of Dragon cards from your hand. When you do, this Siege deals X plus 2 damage to any other target, where X is the "
         "number of cards revealed this way.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = ability.text.replace(ch.name or "~", "this creature")
    if text == ECHO_LIFE:
        return {"kind": "static", "static": "echo_life110c", "effects": []}
    if text == RELENTLESS:
        # 107.3f, 115.1: the target is chosen as the ability goes on the stack, X as it resolves; the card returns only if its mana value is that X
        native = scripts.define(replace(ability, text=RELENTLESS.replace("this creature", "~")), ch)  # (reads, with the selector's X unknown at targeting)
        if native is None:
            return None
        fx = native.get("effects") or []
        gone = '"compare":[["mv","==",-1]],'
        if len(fx) != 3 or fx[2].get("do") != "return_card" or not isinstance(native.get("target"), dict) or gone not in native["target"]["what"]:
            return None
        native["target"] = {**native["target"], "what": native["target"]["what"].replace(gone, "")}
        same = {"object": "target", "stat": "mana_value", "op": "==", "n": {"paid_x": fx[0]["bind"]}}
        fx[1] = {**fx[1], "cond": {"all": [fx[1]["cond"], same]}}
        return native
    if text == "Each opponent who attacked you or a planeswalker you control this turn can't cast spells.":  # 601.3, like Angelic Arbiter (wave110a_spells)
        d = scripts.define(replace(ability, text="Your opponents can't cast spells."), ch)
        return None if d is None else {**d, "when": "attacked_me110c"}
    if text == "Whenever an opponent casts a spell during their turn, they can't attack you or planeswalkers you control this turn.":  # 508.1c: their creatures
        return scripts.define(replace(ability, text=text.replace("they can't attack", "creatures that player controls can't attack")), ch)
    if text == SHUTTLE:
        native = scripts.define(replace(ability, text=SHUTTLE.split(" or you gain control")[0] + ", or you draw a card."), ch)
        if native is None or native["effects"][0].get("do") != "villain":
            return None
        v = native["effects"][0]
        v["b"] = [{"do": "shuttle110c", "player": "event_player"}]
        v["labels"] = [v["labels"][0], "You gain control of a creature of your choice that player controls until end of turn. If you gain control of a creature this way, tap it, and it's attacking that player."]
        return native
    if text == GLYPH:  # 608.2d: not targets; the intervening "if you cast it" (603.4) is read natively from the same trigger
        native = scripts.define(replace(ability, text="When this artifact enters, if you cast it, destroy all creatures."), ch)
        if native is None or [e.get("do") for e in native["effects"]] != ["only_if", "destroy_all"]:
            return None
        return {**native, "effects": [native["effects"][0], {"do": "glyph110c"}]}
    if text == SIEGE:
        # 701.20a, 603.12: reveal first; the reflexive ability then chooses its target (X can be 0, so it always triggers): the payment-X reflexive, fed by the count
        native = scripts.define(replace(ability, text="When this Siege enters, you may pay {X}. When you do, this Siege deals X plus 2 damage to any other target."), ch)
        reveal = scripts.parse_effects("Reveal any number of Dragon cards in your hand. Draw X cards, where X is the number of cards revealed this way.")
        fx = (native or {}).get("effects") or []
        if native is None or reveal is None or [e.get("do") for e in fx] != ["optional_payment", "reflexive"] or len(reveal[0]) != 2:
            return None
        count = {"do": "revealed_x110c", "bind": fx[0]["bind"], "n": reveal[0][1]["n"]}
        return {**native, "effects": [reveal[0][0], count, {**fx[1], "cond": {"succeeded": fx[0]["bind"]}}]}
    if text != HELLION:
        return None
    native = scripts.define(replace(ability, text="When this creature enters, ~ deals 3 damage to you and target creature. The damage can't be prevented."), ch)
    if native is None or [e.get("do") for e in native["effects"]] != ["damage", "damage"]:
        return None
    amount = {"ref_amount": "gc_hi"}  # 107.1: a number of the controller's choice, chosen as the ability resolves (one chooser: the highest is it)
    pick = {"do": "gc_choose", "who": "you", "what": "number", "min": 0, "secret": False, "as": "gc", "say": "an amount of damage"}
    native["effects"] = [pick, {"do": "gc_extremes", "as": "gc"}, *({**e, "n": amount} for e in native["effects"])]
    return native


def echo_cost(ch: Any) -> tuple[str, Any] | None:
    """triggers.echo_cost's part: a mana cost the payment prices at its time (effects.pay_or_sacrifice reads "life110c")."""
    ours = any(ab.text.replace(ch.name or "~", "this creature") == ECHO_LIFE for ab in ch.abilities)
    return ("mana", "life110c") if ours else None


def shuttle(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Midnight Crusader Shuttle, option B: the controller chooses (608.2d, not a target) a creature the facing player controls, gains control of it until end of turn,
    taps it and it attacks that player (508.4: put onto the battlefield attacking only; it never "attacked", so no attack triggers)."""
    from app.rules import selectors

    pid = e["player"].removeprefix("player:")
    sel = selectors.parse("creature")
    assert sel is not None
    key = selectors.replace(sel, controller=f"player:{pid}").key()
    added = [{"do": "player_chooses", "who": "you", "sel": key, "n": 1, "label": "creature", "any": True, "as": "shuttle110c"},
             {"do": "gain_control", "who": "ref:shuttle110c", "duration": "end_of_turn"}, {"do": "tap", "who": "ref:shuttle110c"},
             {"do": "shuttle_attack110c", "at": pid}]
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *added, *ctx["effects"][at:]]
    return True


def shuttle_attack(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, token_grammar

    for cid in effects._cards(plan, ctx, "ref:shuttle110c"):
        card = plan.state.cards[cid]
        if card.controller == ctx["controller"] and card.zone.endswith(":battlefield"):
            token_grammar._attack_with(plan, [cid], e["at"], ctx["controller"])
    return True


def glyph(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Unstable Glyphbridge: you choose one creature with power 2 or less for each player, in turn order (101.4), then every other creature is destroyed (701.8)."""
    from app.rules import selectors

    small, every = selectors.parse("creature with power 2 or less"), selectors.parse("creature")
    assert small is not None and every is not None
    added: list[dict[str, Any]] = [
        {"do": "player_chooses", "who": "you", "sel": selectors.replace(small, controller=f"player:{p}").key(), "n": 1, "label": "creature", "any": True,
         "add": True, "as": "gco"} for p in plan.apnap() if p in plan.live()]
    added.append({"do": "destroy", "who": f"except:gco|{every.key()}"})
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *added, *ctx["effects"][at:]]
    return True


def revealed_x(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The number of cards the reveal before it showed, as the X of the reflexive ability that follows (608.2h: counted once, now)."""
    from app.rules import paid_x, this_way

    paid_x._record(ctx, e["bind"], True, this_way.count(plan, ctx, e["n"]))
    return True


PRIMITIVES = {"revealed_x110c": revealed_x, "glyph110c": glyph, "shuttle110c": shuttle, "shuttle_attack110c": shuttle_attack}
