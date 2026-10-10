"""-- drawn this turn (wave 18G) -- Sylvan Library: "At the beginning of your draw step, you may draw two additional cards. If
you do, choose two cards in your hand drawn this turn. For each of those cards, pay 4 life or put the card on top of your library."

Read against the Comprehensive Rules:
* 121.2 / 121.2a: every card a player draws is its own draw, so which cards in a hand were drawn this turn is a record kept per
  object (``TurnLog.drawn``, filled by ``rules_state._diff`` from the "drew" events: a card that left the hand and came back is
  a new object, 400.7, and wasn't drawn). "Additional" draws are plain draws.
* 608.2c / 608.2d: the instructions are followed in order; "each of those cards" are the chosen cards, taken in the order their
  controller chooses (a one-by-one decision: pay 4 life for this one, or put this one on top of your library — so the order
  the ones put back go on top is theirs).
* 119.4: a player can pay life only if their life total is at least that much; with less, the card goes on top.
* HIDDEN INFORMATION: nothing here is ever shown to another player. The pick and each per-card choice are decisions for their
  controller only (``view.decision_view`` gives everyone else "is making a choice" and nothing of its options, labels or
  prompt); the pick is asked even when no card qualifies (its timing says nothing); the log names no card — a card that goes on
  top of the library is moved from a hand to a hidden zone (``handlers.zones.move`` names it only to who may see it).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key

if TYPE_CHECKING:
    from app.rules.effects import Context
    from app.rules.plan import Plan

_TWO_SENTENCES = re.compile(r"\b(choose \w+ cards in your hand drawn this turn)\. For each of those cards, pay (\d+) life or put the "
                            r"card on top of your library\.")
PATTERN = (r"choose (?P<n>one|two|three|four) cards? in your hand drawn this turn and for each of those cards pay (?P<l>\d+) life "
           r"or put it on top of your library")


def rewrite(body: str) -> str:
    """The two sentences about one choice read as one: "each of those cards" are the cards just chosen."""
    return _TWO_SENTENCES.sub(r"\1 and for each of those cards pay \2 life or put it on top of your library.", body)


def build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language

    return [{"do": "drawn_toll", "n": language._amount(m["n"]), "life": int(m["l"])}], None


def _label(plan: Plan, cid: str) -> str:
    return plan.state.cards[cid].name or "Card"


def toll(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import selectors
    from app.rules.effects import decide

    me = ctx["controller"]
    held = [c for c in plan.state.zones.get(zone_key(me, "hand"), []) if selectors.drawn_now(plan, plan.state.cards[c])]
    n = min(int(e["n"]), len(held))
    decide(plan, player=me, kind="choose_cards", prompt=f"{ctx.get('name') or 'Choose'}: choose {n} of the cards in your hand drawn this turn",
           options=[DecisionOption(id=c, label=_label(plan, c), card_id=c) for c in held], min_choices=n, max_choices=n,
           resume={"step": "drawn_toll", "ctx": ctx, "e": e})  # (asked even with nothing to choose: the timing says nothing)
    return False


def resume_pick(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import selectors

    me = d.player
    ok = [c for c in chosen if c in plan.state.cards and selectors.drawn_now(plan, plan.state.cards[c])
          and plan.state.cards[c].owner == me]
    _next(plan, d.resume["ctx"], d.resume["e"], ok)


def _next(plan: Plan, ctx: Context, e: dict[str, Any], left: list[str]) -> None:
    """One chosen card at a time, in the order its controller picks: pay the life, or put it on top of the library."""
    from app.rules.effects import continue_effects, decide

    me, life = ctx["controller"], int(e["life"])
    if left:
        from app.rules import life_lock  # -- can't lose life (wave 29D) -- 119.8

        can_pay = plan.state.players[me].life >= life and life_lock.pay_problem(plan.state, plan.info, me, life) is None  # 119.4
        options = [o for c in left for o in ([DecisionOption(id=f"pay:{c}", label=f"Pay {life} life ({_label(plan, c)})", card_id=c)]
                                             if can_pay else []) + [DecisionOption(id=f"top:{c}", label=f"Put {_label(plan, c)} on top "
                                                                                    "of your library", card_id=c)]]
        if len(options) == 1:  # (forced: the choice would say nothing the life total doesn't)
            _apply(plan, me, options[0].id, life)
            return _next(plan, ctx, e, [c for c in left if c != options[0].id.split(":", 1)[1]])
        decide(plan, player=me, kind="choose_one", prompt=f"{ctx.get('name') or 'Choose'}: pay {life} life or put a chosen card on top "
               "of your library", options=options, resume={"step": "drawn_toll_each", "ctx": ctx, "e": e, "left": left})
        return None
    continue_effects(plan, ctx)
    return None


def _apply(plan: Plan, me: str, option: str, life: int) -> None:
    how, _, cid = option.partition(":")
    if how == "pay":
        from app.rules import replace as _replace_life  # (wave 28B: 119.4)
        _replace_life.lose_life(plan, [(me, life)], actor=me)
    else:
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "library"},
                 "position": "top"}, actor=me)


def resume_each(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e, left = d.resume["ctx"], d.resume["e"], list(d.resume["left"])
    how, _, cid = chosen[0].partition(":")
    from app.rules import life_lock  # -- can't lose life (wave 29D) --

    if cid in left and how in ("pay", "top") and (how == "top" or (plan.state.players[d.player].life >= int(e["life"])
                                                                   and life_lock.pay_problem(plan.state, plan.info, d.player, int(e["life"])) is None)):
        _apply(plan, d.player, chosen[0], int(e["life"]))
        left.remove(cid)
    _next(plan, ctx, e, left)
