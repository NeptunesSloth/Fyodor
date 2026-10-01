"""Optional costs paid as a spell or ability resolves: "You may pay {2}. If you do, draw a card.",
"You may sacrifice another creature. If you do, …", "… unless that player pays {1}".

CR 118.12: "[A player] may [do something]. If [that player] [does, doesn't, or can't], [effect]."
— the action is a cost, paid when the spell or ability resolves; the "if" clause checks whether the
player chose to pay it (not what events actually occurred). 118.12a: "[Do something] unless [a
player does something else]" means "[A player may do something else]. If [that player doesn't],
[do something]". 118.3: a player can't pay a cost without the resources to pay it fully; 601.2h:
partial payments are not allowed, unpayable costs can't be paid; 608.2d: a player can't choose an
option that's impossible ("A player who controls no creatures can't choose the sacrifice
option"). 608.2c: the instructions are followed in order — so the payment is an effect
(``optional_payment``) that records its result in the resolution context (app/rules/context.py,
``bind_payment``), and the dependent effects follow it behind an ``only_if`` on that binding
(``{"succeeded": "pay0"}``, negated for "unless"). The binding is named by the grammar, so a
second "if you do" in the same ability refers to its own payment.

The decision (PAY / DECLINE) goes to the payer only — the controller, or "that player" / "its
controller" — and PAY is offered only while the whole cost is payable (118.3). Paying is
transactional: the complete cost is validated again when the payer answers (mana abilities can
change the table while the prompt is open); if it can't be paid in full any more, nothing is
paid and the dependent effects don't happen. Non-mana parts go through the generic cost engine
(app/rules/costs.py components, app/rules/cost_payment.py): life, energy, discard, sacrifice,
tapping other permanents, removing counters, exiling (this card or cards from your graveyard),
returning permanents to hand. Mana goes through the mana payment (app/rules/casting.py).

Reflexive triggers ("When you do", 603.12): a "you may [cost]" followed by "When you do, …" is the same
payment; the reflexive ability triggers if it was made (wave 3R1: scripts._reflexive, effects.reflexive).
"""

from __future__ import annotations

import re
from typing import Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, PaymentRecord
from app.game.state import CardInstance
from app.rules import context, cost_payment
from app.rules import costs as C
from app.rules import mana as M
from app.rules.costs import AbilityCost
from app.rules.plan import Plan, decide

Context = dict[str, Any]

# The resume step shares its name with the pay-or-sacrifice prompt so that casting.paying_now lets
# the payer tap their mana while it is open (the mana-while-paying path); the resume payload tells
# the two apart (``opt`` is only ours).
STEP = "pay_or_sacrifice"
PAY, DECLINE = "pay", "decline"
SUPPORTED = frozenset({C.MANA, C.PAY_LIFE, C.PAY_ENERGY, C.SACRIFICE, C.DISCARD, C.EXILE, C.EXILE_FROM_GRAVEYARD,
                       C.REMOVE_COUNTER, C.RETURN_PERMANENT, C.TAP_OTHER})
_MANA_ONLY = re.compile(r"^(\{[^}]+\})+$")


# -- grammar helpers (app/rules/scripts.py) --------------------------------------------------------
def cost_text(phrase: str) -> str | None:
    """The cost an Oracle "you may …" / "unless … pays …" phrase names ("pay {2}", "sacrifice
    another creature", "pay 2 life", "pay {1} and discard a card"), as the comma-separated cost
    text the cost parser reads — or None when the engine couldn't pay every part by itself."""
    parts = []
    for raw in re.split(r", | and ", phrase.strip()):
        part = raw.strip()
        if part.startswith("pay ") and _MANA_ONLY.match(part[4:]) and not re.fullmatch(r"(?:\{E\})+", part[4:]):  # ({E}: wave 3E)
            part = part[4:]
        elif re.fullmatch(r"\d+ life", part):  # "… unless that player pays 3 life"
            part = "pay " + part
        if not part:
            return None
        parts.append(part[0].upper() + part[1:])
    text = ", ".join(parts)
    return text if parse(text) is not None else None


def parse(text: str) -> AbilityCost | None:
    """The cost text as components, or None if any part isn't one the engine pays here."""
    cost = C.parse_ability_cost(text)
    if cost.unsupported or not cost.components or "{X}" in cost.mana.upper() or cost.energy_x:
        return None
    if any(c.kind not in SUPPORTED for c in cost.components):
        return None
    return cost


# -- the payer -------------------------------------------------------------------------------------
def payer_of(plan: Plan, ctx: Context, who: str) -> str | None:
    """Who is offered the payment: "you" (the controller), "target" / "target:<g>" (a target
    player, or the controller of a target object: "its controller"), or a binding / the trigger
    event's player ("that player", app/rules/effects._players)."""
    from app.rules import effects  # (effects registers this module's primitive)

    if who == "you":
        return str(ctx["controller"])
    if who == "target" or who.startswith("target:"):
        for t in effects.target_refs(ctx, who):
            if t["id"] in plan.state.players:
                return str(t["id"]) if t["id"] in plan.live() else None
            card = plan.state.cards.get(t["id"])
            if card is not None and plan.oid(card) == t.get("object_id"):
                on_stack_or_field = card.zone == "stack" or card.zone.endswith(":battlefield")
                pid = card.controller if on_stack_or_field else card.owner  # 108.4a
                return pid if pid in plan.live() else None
        return None
    found = effects._players(plan, ctx, who)
    return found[0] if found else None


# -- validation (118.3: the whole cost, before anything moves) ------------------------------------
def _source(plan: Plan, ctx: Context) -> CardInstance:
    """The source, for the parts of a cost about it (and selectors' "another"). If the card is
    gone, a stand-in that is nowhere: costs about ~ then can't be paid."""
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is not None:
        return card
    return CardInstance(id=str(ctx.get("source_card") or "?"), owner=ctx["controller"], controller=ctx["controller"], zone="none")


def _self_parts(cost: AbilityCost) -> list[C.CostComponent]:
    return [c for c in cost.components if c.selector is None
            and c.kind in (C.SACRIFICE, C.EXILE, C.EXILE_FROM_GRAVEYARD, C.RETURN_PERMANENT, C.REMOVE_COUNTER)]


def problem(plan: Plan, ctx: Context, cost: AbilityCost, payer: str, chosen: dict[int, list[str]] | None = None) -> str | None:
    """Why ``payer`` can't pay ``cost`` in full right now, or None. With ``chosen`` (objects
    picked for the parts that need a choice) those picks are validated too."""
    from app.rules import casting  # casting imports cost_payment → (not this module)

    source = _source(plan, ctx)
    same = plan.oid(source) == ctx.get("source_object") if source.zone != "none" else False
    for comp in _self_parts(cost):
        if comp.kind == C.EXILE_FROM_GRAVEYARD:
            if not same or not source.zone.endswith(":graveyard"):
                return f"{source.name or 'it'} isn't in the graveyard"
        elif not same or not source.zone.endswith(":battlefield"):
            return f"{source.name or 'it'} isn't on the battlefield"  # (118.12: Standstill exiled in response)
        elif comp.kind == C.REMOVE_COUNTER and source.counters.get(comp.counter or "", 0) < comp.amount:
            return f"{source.name or 'It'} doesn't have {comp.amount} {comp.counter} counters"
    if cost.life and plan.state.players[payer].life < cost.life:  # 119.4
        return f"{plan.name(payer)} can't pay {cost.life} life"
    found = cost_payment.problem(plan, cost, source, payer)
    if found is not None:
        return found
    if chosen is not None:
        used: set[str] = set()
        for i, comp in cost.choices:
            usable = [c for c in cost_payment.candidates(plan, comp, payer, source)
                      if c not in cost_payment._reserved(cost, comp, source) and c not in used]
            picks = chosen.get(i, [])
            if len(picks) != comp.amount or len(set(picks)) != len(picks) or any(c not in usable for c in picks):
                return f"Those can't pay “{comp.text}”"
            used |= set(picks)
    if cost.mana:
        exclude = cost_payment.excluded(cost, source, chosen or {})
        if not casting.can_pay(plan.state, payer, M.parse_cost(cost.mana), plan.info, exclude=exclude):
            return f"{plan.name(payer)} can't pay {cost.mana}"
    return None


# -- the primitive ---------------------------------------------------------------------------------
def optional_payment(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """``{"do": "optional_payment", "who": <payer>, "cost": <cost text>, "bind": "pay0"}``: offer
    the payer the cost (PAY / DECLINE, privately) if they can pay it now; record the result as the
    binding ``bind`` (``{"succeeded": bind}`` in a following ``only_if``)."""
    cost = parse(e["cost"])
    name = str(e.get("bind") or "pay0")
    payer = payer_of(plan, ctx, e.get("who", "you"))
    if cost is None or payer is None:
        context.bind_payment(ctx, name, False)
        return True
    why = problem(plan, ctx, cost, payer)
    if why is not None:  # 118.3 / 608.2d: the option isn't offered
        plan.note(f"{plan.name(payer)} can't pay {_label(cost)} for {ctx.get('name') or 'it'}: {why}")
        context.bind_payment(ctx, name, False)
        return True
    source = plan.state.cards.get(ctx.get("source_card") or "")
    opt = {"cost": e["cost"], "bind": name, "payer": payer, "chosen": {}}
    hint = " (tap your mana first)" if cost.mana and _self_pays(plan, payer) else ""
    decide(plan, player=payer, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: pay {_label(cost)}?{hint}",
           options=[DecisionOption(id=PAY, label=f"Pay {_label(cost)}"), DecisionOption(id=DECLINE, label="Don't pay")],
           resume=_resume(ctx, opt, cost), source=source,
           display={"kind": "optional_cost", "cost": _label(cost), "pool": dict(plan.state.players[payer].mana)} if cost.mana else None)
    return False


def _label(cost: AbilityCost) -> str:
    return ", ".join(c.text for c in cost.components)


def _self_pays(plan: Plan, payer: str) -> bool:
    from app.rules import casting

    return casting.payment_mode(plan, payer) == "self"


def _resume(ctx: Context, opt: dict[str, Any], cost: AbilityCost, **more: Any) -> dict[str, Any]:
    # "cost" (the mana part) is what casting._best_option reads to pick a color while tapping
    return {"step": STEP, "ctx": ctx, "opt": opt, "cost": cost.mana or "{0}", **more}


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    """PAY / DECLINE, or the objects chosen for one part of the cost."""
    from app.rules import effects

    r = d.resume
    assert r is not None
    if "opt" not in r:  # a pay-or-sacrifice / counter-unless prompt (app/rules/effects.py)
        effects.resume_pay_or_sacrifice(plan, d, chosen)
        return
    ctx, opt = r["ctx"], r["opt"]
    cost = parse(opt["cost"])
    assert cost is not None
    if "component" in r:
        if len(chosen) != r["amount"]:
            raise ActionError(f"Choose {r['amount']}")
        opt = {**opt, "chosen": {**opt["chosen"], str(r["component"]): list(chosen)}}
    elif chosen[0] != PAY:
        plan.note(f"{plan.name(d.player)} didn't pay {_label(cost)} for {ctx.get('name') or 'it'}")
        context.bind_payment(ctx, opt["bind"], False)
        effects.continue_effects(plan, ctx)
        return
    if _choose_next(plan, ctx, opt, cost):
        _pay(plan, ctx, opt, cost)
        effects.continue_effects(plan, ctx)


def _choose_next(plan: Plan, ctx: Context, opt: dict[str, Any], cost: AbilityCost) -> bool:
    """Ask the payer for the objects of the next part that needs a choice (privately: a discard's
    options are their hand); True when every part has its objects."""
    payer = opt["payer"]
    source = _source(plan, ctx)
    picked = {int(k): list(v) for k, v in opt["chosen"].items()}
    used = {c for ids in picked.values() for c in ids}
    for i, comp in cost.choices:
        if i in picked:
            continue
        usable = [c for c in cost_payment.candidates(plan, comp, payer, source)
                  if c not in cost_payment._reserved(cost, comp, source) and c not in used]
        if len(usable) < comp.amount:
            return True  # (validated again in _pay: it can't be paid any more)
        if len(usable) == comp.amount:
            picked[i] = usable
            used |= set(usable)
            opt["chosen"][str(i)] = usable
            continue
        verb = cost_payment._VERBS.get(comp.kind, "use")
        decide(plan, player=payer, kind="choose_cards",
               prompt=f"{ctx.get('name') or 'It'}: choose {comp.amount} to {verb} (“{comp.text}”)",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in usable],
               min_choices=comp.amount, max_choices=comp.amount,
               resume=_resume(ctx, opt, cost, component=i, amount=comp.amount), source=plan.state.cards.get(ctx.get("source_card") or ""))
        return False
    return True


def _pay(plan: Plan, ctx: Context, opt: dict[str, Any], cost: AbilityCost) -> None:
    """Pay the whole cost at once (601.2h), or nothing: the payer chose to pay, but the table may
    have changed while they were asked (mana abilities), so everything is checked first."""
    from app.rules import casting

    payer: str = opt["payer"]
    name: str = opt["bind"]
    label = ctx.get("name") or "it"
    chosen = {int(k): list(v) for k, v in opt["chosen"].items()}
    why = problem(plan, ctx, cost, payer, chosen)
    if why is not None:
        plan.note(f"{plan.name(payer)} couldn't pay {_label(cost)} for {label}: {why}")
        context.bind_payment(ctx, name, False)
        return
    source = _source(plan, ctx)
    mana_cost = M.parse_cost(cost.mana) if cost.mana else None
    if mana_cost is not None and _self_pays(plan, payer) and not casting.pool_covers(plan.state, payer, mana_cost):
        raise ActionError(f"Tap your mana first: {mana_cost.text()} isn't in your mana pool")
    paid = ([source.id] if _self_parts(cost) else []) + [c for ids in chosen.values() for c in ids]
    refs = [r for r in (context.ref_of(plan, c) for c in dict.fromkeys(paid)) if r is not None]
    if mana_cost is not None:
        if _self_pays(plan, payer):
            casting.pay(plan, payer, mana_cost, f"paid {mana_cost.text()} for {label}", sources=[])
        else:
            casting.pay(plan, payer, mana_cost, f"paid {mana_cost.text()} for {label}",
                        exclude=cost_payment.excluded(cost, source, chosen))
    if cost.life:
        plan.do({"type": "life", "player": payer, "delta": -cost.life}, actor=payer)
    for kind, n in cost.remove_counters:
        plan.do({"type": "counter", "card_ids": [source.id], "kind": kind, "delta": -n}, actor=payer)
    record = PaymentRecord(card=source.id, controller=payer, total_cost=_label(cost))
    cost_payment.pay(plan, cost, source, chosen, record)
    plan.note(f"{plan.name(payer)} paid {_label(cost)} for {label}", [c for c in paid if c in plan.state.cards])
    context.bind_payment(ctx, name, True, refs)
