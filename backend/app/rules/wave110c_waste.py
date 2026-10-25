"""Wave 110C: Eumidian Wastewaker (you and defending player each discard a card or sacrifice a permanent, you draw per land card put into a graveyard this way).
Each of the two players, in APNAP order, picks one card to discard or one permanent to sacrifice (101.4); the picks are then carried out together (701.9a, 701.21a)
and the controller draws for each land card that reached a graveyard (a token is not a card, 111.7).
Kain, Traitorous Dragoon: "If they do" is the control change having happened (608.2c), read as the grammar's "If you do" gate."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key
from app.rules.plan import decide

Context = dict[str, Any]
_TEXT = ("Whenever this creature attacks, you and defending player each discard a card or sacrifice a permanent. "
         "You draw a card for each land card put into a graveyard this way.")


_KAIN = ("Whenever Kain deals combat damage to a player, that player gains control of Kain. If they do, you draw that many cards, "
         "create that many tapped Treasure tokens, then lose that much life.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.text == _KAIN:  # Kain, Traitorous Dragoon: "If they do" = the control change happened (the grammar's "If you do" gate); the rest is gated alike (608.2c)
        native = scripts.define(replace(ability, text="Whenever Kain deals combat damage to a player, that player gains control of Kain. If you do, you draw that many cards."), ch)
        rest = scripts.parse_effects("Create that many tapped Treasure tokens. You lose that much life.", event_player=True)
        if native is None or rest is None or [e["do"] for e in native["effects"]] != ["gain_control", "only_if", "draw"]:
            return None
        native["effects"][1]["skip"] = 3
        return {**native, "effects": [*native["effects"], *rest[0]]}
    if ability.text != _TEXT:
        return None

    native = scripts.define(replace(ability, text="Whenever this creature attacks, defending player discards a card."), ch)
    return None if native is None else {**native, "effects": [{"do": "discard_or_sacrifice110c"}]}


def discard_or_sacrifice(plan: Any, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import defending

    who = {ctx["controller"], *defending.players(plan, ctx)}
    return _next(plan, ctx, [p for p in plan.apnap() if p in who], [])


def _options(plan: Any, ctx: Context, pid: str) -> list[DecisionOption]:
    from app.rules import prohibitions

    out: list[DecisionOption] = []
    if prohibitions.cant_cause_discard(plan, pid, ctx["controller"]) is None:
        out += [DecisionOption(id=c, label=f"Discard {plan.state.cards[c].name or 'a card'}", card_id=c) for c in plan.state.zones.get(zone_key(pid, "hand"), [])]
    if prohibitions.cant_cause_sacrifice(plan, pid, ctx["controller"]) is None:
        out += [DecisionOption(id=c, label=f"Sacrifice {plan.state.cards[c].name or 'a permanent'}", card_id=c) for c in plan.state.zones.get(zone_key(pid, "battlefield"), [])
                if plan.state.cards[c].controller == pid and not prohibitions.sacrifice_forbidden(plan, plan.state.cards[c])]
    return out


def _next(plan: Any, ctx: Context, todo: list[str], picked: list[str]) -> bool:
    from app.rules import effects

    for i, pid in enumerate(todo):
        if options := _options(plan, ctx, pid):
            decide(plan, player=pid, kind="choose_cards", prompt="Discard a card or sacrifice a permanent", options=options, min_choices=1, max_choices=1,
                   resume={"step": "discard_or_sacrifice110c", "ctx": ctx, "rest": todo[i + 1:], "picked": picked})
            return False
    cards = [c for c in picked if c in plan.state.cards]
    sacrificed = [c for c in cards if plan.state.cards[c].zone.endswith(":battlefield")]
    discarded = [c for c in cards if plan.state.cards[c].zone.endswith(":hand")]
    if sacrificed:
        effects._sacrifice_cards(plan, sacrificed, ctx["controller"], ctx)
    if discarded:
        plan.do({"type": "move", "card_ids": discarded, "to": {"zone": "graveyard"}}, actor=ctx["controller"])
    lands = sum(1 for c in cards if plan.state.cards.get(c) is not None and plan.state.cards[c].zone.endswith(":graveyard") and not plan.state.cards[c].token
                and "Land" in plan.ch(plan.state.cards[c]).types)
    if lands:
        effects.PRIMITIVES["draw"](plan, ctx, {"do": "draw", "who": "you", "n": lands})
    return True


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    r = d.resume
    if _next(plan, r["ctx"], list(r["rest"]), [*r["picked"], *chosen]):
        continue_effects(plan, r["ctx"])


PRIMITIVES = {"discard_or_sacrifice110c": discard_or_sacrifice}
RESUME = {"discard_or_sacrifice110c": resume}
