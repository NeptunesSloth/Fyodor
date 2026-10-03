"""-- sized payments (wave 5G) -- optional payments whose size is chosen or worked out as the ability
resolves, and the "X" the rest of the ability reads from them:

* "You may pay {X}. If you do, draw X cards." (Stark's Ingenuity, Vigil for the Lost, Hero of Leina Tower,
  Squealing Devil): X appears in the text but in no cost of the ability, so its controller chooses it at the
  appropriate time (107.3f) — here as the payment is made (118.12: the cost is paid as it resolves). The choice
  is bounded by what the payer can pay (118.3, 601.2h: no partial payment) and by any limit the text gives:
  "where X is less than or equal to the amount of life you gained" (Well of Lost Dreams: the trigger event's
  amount, 603.2c / 608.2k), or a later "X can't be greater than the amount of life you gained this turn."
  (Shanna, Purifying Blade; Mortarion, Daemon Primarch: the turn's history).
* "You may pay X life, where X is its power. If you do, draw X cards." (Mask of Griselbrand, Tymna the Weaver):
  X is defined by the text (107.3c), worked out as the payment is made (608.2h: once); "you may pay that much
  life. If you do, draw that many cards." (Niv-Mizzet, Ghost Counsel: the event's amount, 608.2k).

The payment is the optional_payment effect (app/rules/optional_payment.py: the payer alone decides; PAY is
offered only while the whole cost is payable, 118.3; 119.4: life is paid only from a total at least that
large). Its binding records the X paid (``amount``); "X" in the instructions after it is ``{"paid_x": <bind>}``
(values.evaluate), so the number is the one paid even when the table changes afterwards.

Not read (stay manual): an X in a target's definition ("return another target Zombie creature card with mana
value X": the target is chosen before X, 603.3d — Relentless Dead), an X in an ability that also has an X of
its own (a cost's or a spell's X, 107.3a/107.3m), "pay any amount of mana" (Chorus of the Conclave), energy X.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
CHOOSE = "x:"  # a decision option "x:<n>": pay {n}
_MAX = 40  # (the most X offered: far beyond any real table's mana; the payer is never offered more than they can pay)
_MANA_X = re.compile(r"^pay \{X\}(?:, where X is less than or equal to (?P<cap>.+))?$")
_LIFE_X = re.compile(r"^pay X life, where X is (?P<v>.+)$")
_LIFE_EQUAL = re.compile(r"^pay life equal to (?P<v>.+)$")
_CAP = re.compile(r"^x can't be greater than (?P<v>.+)$")


def _value(phrase: str) -> Any:
    from app.rules import language

    p = phrase.strip()
    if p in ("the amount of life you gained", "that much"):  # (only in a "whenever you gain life" trigger: see scripts)
        return {"event_amount": 1}
    v = language.x_definition(p)
    if v is None or "x" in json.dumps(v):
        return None
    return v


def payment(phrase: str) -> dict[str, Any] | None:
    """The optional payment "you may <phrase>" names, when it is a sized one (else None): ``{"choose_x": {"max":
    value | None}}`` (mana {X}: the payer chooses), ``{"life_x": value}`` (life, X defined by the text)."""
    p = phrase.strip()
    m = _MANA_X.match(p)
    if m is not None:
        cap = _value(m["cap"]) if m["cap"] else None
        if m["cap"] and cap is None:
            return None
        return {"cost": "", "choose_x": {"max": cap}}
    m = _LIFE_X.match(p) or _LIFE_EQUAL.match(p)
    if m is not None:
        v = _value(m["v"])
        if v is None:
            return None
        # ("pay life equal to its power. If you do, put that many +1/+1 counters on it": "that many" is the life paid)
        return {"cost": "", "life_x": v, **({"that_many": True} if _LIFE_EQUAL.match(p) else {})}
    if p == "pay that much life":
        return {"cost": "", "life_x": {"event_amount": 1}}
    return None


def cap_sentence(text: str, effects: list[dict[str, Any]]) -> bool:
    """"X can't be greater than the amount of life you gained this turn." after the payment it limits (the
    sentence modifies the choice, 608.2c): True when read (the limit is set on that payment)."""
    m = _CAP.match(text)
    if m is None:
        return False
    pays = [e for e in effects if e["do"] == "optional_payment" and "choose_x" in e]
    if len(pays) != 1 or pays[0]["choose_x"].get("max") is not None:
        return False
    v = _value(m["v"])
    if v is None or v == {"event_amount": 1}:
        return False
    pays[0]["choose_x"] = {"max": v}
    return True


def bind_x(effects: list[dict[str, Any]], bind: str) -> list[dict[str, Any]]:
    """The instructions after a sized payment, their X the payment's (``{"paid_x": bind}``)."""
    def sub(v: Any) -> Any:
        if v == {"x": 1}:
            return {"paid_x": bind}
        if isinstance(v, list):
            return [sub(x) for x in v]
        if isinstance(v, dict):
            return {k: sub(x) for k, x in v.items()}
        return v
    return [sub(e) for e in effects]


def sized(e: dict[str, Any]) -> bool:
    return "choose_x" in e or "life_x" in e


def amount(ctx: Context, bind: str) -> int:
    """The X a payment paid (values.evaluate ``{"paid_x": bind}``): 0 when it wasn't paid."""
    b = (ctx.get("refs") or {}).get(bind) or {}
    return int((ctx.get("paid_x") or {}).get(bind) or 0) if b.get("ok") else 0


def _record(ctx: Context, bind: str, ok: bool, n: int) -> None:
    from app.rules import context

    context.bind_payment(ctx, bind, ok)
    ctx.setdefault("paid_x", {})[bind] = n if ok else 0


# -- resolution (optional_payment.optional_payment) ---------------------------------------------------------------
def start(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool | str:
    """A sized payment as the resolution reaches it: the concrete cost text to offer ("{3}", "Pay 4 life"), True when
    done here (nothing to ask), False while the payer chooses X."""
    from app.rules import casting, values
    from app.rules import mana as M
    from app.rules import optional_payment as O
    from app.rules.plan import decide

    bind = str(e.get("bind") or "pay0")
    payer = O.payer_of(plan, ctx, e.get("who", "you"))
    if payer is None:
        _record(ctx, bind, False, 0)
        return True
    if "life_x" in e:
        n = values.evaluate(plan, ctx, e["life_x"])  # (608.2h: once, now)
        ctx.setdefault("paid_x", {})[bind] = n
        if n == 0:  # (nothing to pay: paying 0 life is paying it — 107.1b's 0 — but nothing to ask)
            _record(ctx, bind, True, 0)
            return True
        return f"Pay {n} life"
    cap = e["choose_x"].get("max")
    limit = min(_MAX, values.evaluate(plan, ctx, cap)) if cap is not None else _MAX
    most = 0
    while most < limit and casting.can_pay(plan.state, payer, M.parse_cost(f"{{{most + 1}}}"), plan.info):
        most += 1
    options = [DecisionOption(id=f"{CHOOSE}{n}", label=f"Pay {{{n}}} (X = {n})") for n in range(most + 1)]
    options.append(DecisionOption(id=O.DECLINE, label="Don't pay"))
    hint = " (tap your mana first)" if O._self_pays(plan, payer) else ""
    source = plan.state.cards.get(ctx.get("source_card") or "")
    decide(plan, player=payer, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: pay {{X}}? Choose X{hint}",
           options=options, source=source,
           resume={"step": O.STEP, "ctx": ctx, "choose_x": {"bind": bind, "payer": payer}, "cost": "{0}"})
    return False


def resume_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The X chosen (or declined): pay {X} through the ordinary payment, X recorded on the binding."""
    from app.rules import effects
    from app.rules import optional_payment as O

    ctx, info = d.resume["ctx"], d.resume["choose_x"]
    bind, payer = info["bind"], info["payer"]
    if chosen[0] == O.DECLINE:
        plan.note(f"{plan.name(payer)} didn't pay for {ctx.get('name') or 'it'}")
        _record(ctx, bind, False, 0)
        effects.continue_effects(plan, ctx)
        return
    n = int(chosen[0][len(CHOOSE):])
    if n == 0:
        plan.note(f"{plan.name(payer)} paid {{0}} (X = 0) for {ctx.get('name') or 'it'}")
        _record(ctx, bind, True, 0)
        effects.continue_effects(plan, ctx)
        return
    text = f"{{{n}}}"
    cost = O.parse(text)
    assert cost is not None
    ctx.setdefault("paid_x", {})[bind] = n
    opt = {"cost": text, "bind": bind, "payer": payer, "chosen": {}}
    why = O.problem(plan, ctx, cost, payer)
    if why is not None:
        from app.game.errors import ActionError

        raise ActionError(f"Can't pay {text}: {why}")
    O._pay(plan, ctx, opt, cost)
    effects.continue_effects(plan, ctx)

