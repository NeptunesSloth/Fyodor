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

Not read (stay manual): an X in a target's definition, except Relentless Dead's exact wording (the target
is chosen before X, 603.3d; read since wave 110C), an X in an ability that also has an X of
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
_MANA_X = re.compile(r"^pay \{X\}(?P<xx>\{X\})?(?P<extra>(?:\{[^}X]+\})*)(?:, where X is less than or equal to (?P<cap>.+))?$")  # (wave 26C: "{X}{W}{U}{B}", 118.12)
_LIFE_X = re.compile(r"^pay X life, where X is (?P<v>.+)$")
_ENERGY_X = re.compile(r"^pay X \{E\}$")  # -- energy X (wave 50J) -- see ``energy_text``
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
    from app.rules import tap_x_payments

    if (tapped := tap_x_payments.payment(phrase.strip())) is not None:
        return tapped
    p = phrase.strip()
    if colored := re.fullmatch(r"pay any amount of \{([WUBRGC])\}", p):
        return {"cost": "", "choose_x": {"color": colored[1]}, "that_many": True}
    m = _MANA_X.match(p)
    if m is not None:
        if m["xx"] and (m["extra"] or m["cap"]):  # ("{X}{X}" only bare, as Numa pays it: the other combinations are untested)
            return None
        cap = _value(m["cap"]) if m["cap"] else None
        if m["cap"] and cap is None:
            return None
        return {"cost": "", "cost_has_x": True,
                "choose_x": {"max": cap, **({"extra": m["extra"]} if m["extra"] else {}), **({"mult": 2} if m["xx"] else {})}}  # (-- wave 110O -- "{X}{X}": 2X mana, 107.3a: X is its half)
    m = _LIFE_X.match(p) or _LIFE_EQUAL.match(p)
    if m is not None:
        v = _value(m["v"])
        if v is None:
            return None
        # ("pay life equal to its power. If you do, put that many +1/+1 counters on it": "that many" is the life paid)
        return {"cost": "", "life_x": v, **({"that_many": True} if _LIFE_EQUAL.match(p) else {})}
    if m := _TIMES.match(p):  # -- pay N times (wave 51A) -- "that many" is the number of times
        return {"cost": "", "choose_x": {"max": int(m["n"]) if m["n"] else None, "times": m["c"]}, "that_many": True}
    if m := re.fullmatch(r"pay an amount of \{E\} equal to (?P<v>.+)", p):
        v = _value(m["v"])
        return {"cost": "", "energy_n": v} if v is not None else None
    if _ENERGY_X.match(p):
        return {"cost": "", "choose_x": {"max": None, "energy": True}, "energy_as": "energy_paid"}
    if p == "pay that much life":
        return {"cost": "", "life_x": {"event_amount": 1}}
    if p == "pay any amount of life":  # -- if you do (wave 21C) -- Necrodominance: the payer chooses 0 up to their life total (119.4), "that many" is it
        return {"cost": "", "choose_x": {"max": {"life": "you"}, "life": True}, "that_many": True}
    return None


_TIMES = re.compile(r"^pay (?P<c>(?:\{[^}]+\})+) X times(?:, at most (?P<n>\d+))?$")
_TIMES_TEXT = re.compile(r"\bpay (?P<c>(?:\{[^}]+\})+) (?:any number of times|up to (?P<n>one|two|three|four|five) times)\. When you (?:pay this cost one or more times|do), (?P<rest>[^.\n]+)")
_ENERGY_PAID = re.compile(r"(?P<pay>\bpay) one or more \{E\}\. (?P<if>If you do|When you do), (?P<rest>[^.]+)\.")


def times_text(body: str) -> str:
    """-- pay N times (wave 51A) -- 118.8, 107.1b: "you may pay {1}{W} any number of times. When you pay this cost one or more times, put that many valor counters on
    this creature." (Intrepid Adversary), "you may pay {G} up to three times" (Tranquil Frillback): the payer chooses how many times (one or more, at most the
    limit and what they can pay in full: 118.3) and pays that many copies of the cost together; the number is the X after it, like "you may pay one or more {E}"."""
    from app.rules import values

    def one(m: re.Match[str]) -> str:
        rest = re.sub(r"\bthat many\b", "X", m["rest"])
        return f"pay {m['c']} X times" + (f", at most {values.NUMBERS[m['n']]}" if m["n"] else "") + f". When you do, {rest}"
    return _TIMES_TEXT.sub(one, body)


def energy_text(body: str) -> str:
    """-- energy X (wave 50J) -- 107.14, 107.3f: "you may pay one or more {E}. If you do, create an X/X … token, where X is the amount of {E} paid this way." (Pia Nalaar,
    Aether Refinery), "… put that many +1/+1 counters on this creature." (Rampaging Aetherhood), "When you do, this creature deals that much damage to each other creature."
    (Territorial Aetherkite): the payer chooses how many {E} to pay as they pay (one or more), and that number is the X after it, like "you may pay {X}"."""
    def one(m: re.Match[str]) -> str:
        rest = re.sub(r"\bthat (?:much|many)\b", "X", re.sub(r", where X is the amount of \{E\} paid this way$", "", m["rest"]))
        return f"{m['pay']} X {{E}}. {m['if']}, {rest}."
    body = _ENERGY_PAID.sub(one, body)
    # CR 608.2c, 118.12: gaining energy precedes the optional payment; the payment is
    # its own instruction even when Oracle joins them with ", then" (Aether Refinery).
    energy_cost = r"pay (?:X \{E\}|an amount of \{E\} equal to [^.]+|(?:one|two|three|four|five|six|seven|eight|nine|ten|fifty|\d+) \{E\}|(?:\{E\})+)"
    body = re.sub(r", then you may (" + energy_cost + r")\.", r". You may \1.", body)
    body = re.sub(r"\. Then you may (" + energy_cost + r")\.", r". You may \1.", body)
    # CR 118.12: this immediately adjacent condition reads the optional payment,
    # not a later energy loss or a payment elsewhere in the ability.
    return re.sub(r"(You may " + energy_cost + r"\.) If you pay, ", r"\1 If you do, ", body)


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
    pays[0]["choose_x"] = {**pays[0]["choose_x"], "max": v}
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
    if (color := e.get("choose_x", {}).get("color")) is not None:
        from app.rules import colored_amount_payments

        return colored_amount_payments.start(plan, ctx, payer, bind, color)
    if e.get("choose_x", {}).get("tap_cost"):
        from app.rules import tap_x_payments

        return tap_x_payments.start(plan, ctx, e, payer, bind)
    if e.get("choose_x", {}).get("counters"):  # -- cards (wave 110H) -- Tetravus: "remove any number of +1/+1 counters from this creature"
        from app.rules import wave110h_cards

        return wave110h_cards.counters_start(plan, ctx, e, payer, bind)
    if "life_x" in e:
        n = values.evaluate(plan, ctx, e["life_x"])  # (608.2h: once, now)
        ctx.setdefault("paid_x", {})[bind] = n
        if n == 0:  # (nothing to pay: paying 0 life is paying it — 107.1b's 0 — but nothing to ask)
            _record(ctx, bind, True, 0)
            return True
        return f"Pay {n} life"
    if e["choose_x"].get("energy"):  # -- energy X (wave 50J) -- one or more of the {E} the payer has (118.3: no partial payment)
        from app.rules import context

        context.bind_amount(ctx, e.get("energy_as", "energy_paid"), 0)
        have = max(0, plan.state.players[payer].resources.get("energy", 0))
        if have == 0:
            plan.note(f"{plan.name(payer)} has no {{E}} to pay for {ctx.get('name') or 'it'}")
            _record(ctx, bind, False, 0)
            return True
        options = [DecisionOption(id=f"{CHOOSE}{n}", label=f"Pay {n} {{E}} (X = {n})") for n in range(1, min(have, 250) + 1)]
        options.append(DecisionOption(id=O.DECLINE, label="Don't pay"))
        decide(plan, player=payer, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: pay {{E}}? Choose X (you have {have})", options=options,
               source=plan.state.cards.get(ctx.get("source_card") or ""),
               resume={"step": O.STEP, "ctx": ctx, "choose_x": {"bind": bind, "payer": payer, "energy": True,
                       "energy_as": e.get("energy_as", "energy_paid")}, "cost": ""})
        return False
    cap = e["choose_x"].get("max")
    if (each := e["choose_x"].get("times")) is not None:  # -- pay N times (wave 51A) -- one or more copies of the cost, as many as the payer can pay in full (118.3)
        most = 0
        while most < min(_MAX, cap if cap is not None else _MAX) and casting.can_pay(plan.state, payer, M.parse_cost(each * (most + 1)), plan.info):
            most += 1
        if most == 0:
            plan.note(f"{plan.name(payer)} can't pay {each} for {ctx.get('name') or 'it'}")
            _record(ctx, bind, False, 0)
            return True
        options = [DecisionOption(id=f"{CHOOSE}{n}", label=f"Pay {each} {n} time{'s' if n > 1 else ''} (X = {n})") for n in range(1, most + 1)]
        options.append(DecisionOption(id=O.DECLINE, label="Don't pay"))
        hint = " (tap your mana first)" if O._self_pays(plan, payer) else ""
        decide(plan, player=payer, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: pay {each} how many times?{hint}", options=options,
               source=plan.state.cards.get(ctx.get("source_card") or ""),
               resume={"step": O.STEP, "ctx": ctx, "choose_x": {"bind": bind, "payer": payer, "times": each}, "cost": ""})
        return False
    limit = min(_MAX, values.evaluate(plan, ctx, cap)) if cap is not None else _MAX
    extra = e["choose_x"].get("extra", "")  # (wave 26C: the rest of "{X}{W}{U}{B}", paid with the X: 118.3, no partial payment)
    mult = int(e["choose_x"].get("mult", 1))  # (wave 110O: "{X}{X}" costs two generic mana for each X)
    purpose = casting.Purpose(selected_cost_has_x=e.get('cost_has_x'))
    most = 0 if not extra or casting.can_pay(plan.state, payer, M.parse_cost(extra), plan.info, purpose=purpose) else -1
    while most >= 0 and most < limit and casting.can_pay(plan.state, payer, M.parse_cost(f"{{{(most + 1) * mult}}}{extra}"), plan.info, purpose=purpose):
        most += 1
    if most < 0:  # (118.3: the part beside X can't be paid, so nothing can: not offered)
        plan.note(f"{plan.name(payer)} can't pay {extra} for {ctx.get('name') or 'it'}")
        _record(ctx, bind, False, 0)
        return True
    life = bool(e["choose_x"].get("life"))
    if life:  # (the cap is the life total, 119.4: life can be paid only from a total at least that large)
        from app.rules import (
            life_lock,  # -- can't lose life (wave 29D) -- 119.8, 119.4b: only 0 life can be paid by a player who can't lose life
        )

        most = 0 if life_lock.why_not(plan, payer, "lose") else max(0, limit)
    options = [DecisionOption(id=f"{CHOOSE}{n}", label=f"Pay {n} life (X = {n})" if life else f"Pay {{{n * mult}}}{extra} (X = {n})")
               for n in range(most + 1)]
    options.append(DecisionOption(id=O.DECLINE, label="Don't pay"))
    hint = " (tap your mana first)" if O._self_pays(plan, payer) else ""
    source = plan.state.cards.get(ctx.get("source_card") or "")
    decide(plan, player=payer, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: pay {{X}}? Choose X{hint}",
           options=options, source=source,
           resume={"step": O.STEP, "ctx": ctx, "choose_x": {"bind": bind, "payer": payer, "life": life, "extra": extra, "mult": mult,
                   "cost_has_x": e.get('cost_has_x')}, "cost": f"{{0}}{extra}"})
    return False


def resume_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The X chosen (or declined): pay {X} through the ordinary payment, X recorded on the binding."""
    from app.rules import effects
    from app.rules import optional_payment as O

    ctx, info = d.resume["ctx"], d.resume["choose_x"]
    bind, payer = info["bind"], info["payer"]
    if info.get("color") is not None:
        from app.rules import colored_amount_payments

        colored_amount_payments.resume(plan, d, chosen)
        return
    if info.get("tap_cost"):
        from app.rules import tap_x_payments

        tap_x_payments.resume(plan, d, chosen)
        return

    if chosen[0] == O.DECLINE:
        plan.note(f"{plan.name(payer)} didn't pay for {ctx.get('name') or 'it'}")
        _record(ctx, bind, False, 0)
        effects.continue_effects(plan, ctx)
        return
    n = int(chosen[0][len(CHOOSE):])
    if info.get("counters"):  # -- cards (wave 110H) -- 118.12: the counters are removed as the cost (122.1)
        from app.rules import counter_removal_results

        counter_removal_results.remove(plan, info["source"], info["counters"], n, by=payer)
        _record(ctx, bind, True, n)
        effects.continue_effects(plan, ctx)
        return
    if info.get("energy"):
        from app.rules import context

        context.bind_amount(ctx, info.get("energy_as", "energy_paid"), n)
    extra = info.get("extra", "")
    if n == 0 and not extra:
        plan.note(f"{plan.name(payer)} paid {{0}} (X = 0) for {ctx.get('name') or 'it'}")
        _record(ctx, bind, True, 0)
        effects.continue_effects(plan, ctx)
        return
    if info.get("times"):  # (wave 51A) the copies of the cost, together (601.2h)
        extra = info["times"] * n
    text = f"Pay {n} life" if info.get("life") else "Pay " + "{E}" * n if info.get("energy") else (extra if info.get("times") else f"{{{n * int(info.get('mult', 1))}}}{extra}" if n else extra)
    cost = O.parse(text)
    assert cost is not None
    ctx.setdefault("paid_x", {})[bind] = n
    opt = {"cost": text, "bind": bind, "payer": payer, "chosen": {}, "cost_has_x": info.get('cost_has_x')}
    why = O.problem(plan, ctx, cost, payer, cost_has_x=info.get('cost_has_x'))
    if why is not None:
        from app.game.errors import ActionError

        raise ActionError(f"Can't pay {text}: {why}")
    O._pay(plan, ctx, opt, cost)

