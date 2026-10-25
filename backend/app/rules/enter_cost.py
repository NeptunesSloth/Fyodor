"""-- entering for a cost (wave 5G) -- "If this artifact would enter, you may discard a land card instead. If you do,
put this artifact onto the battlefield. If you don't, put it into its owner's graveyard." (Mox Diamond) and the
lands that sacrifice one land as they would enter (Lake of the Dead, Kjeldoran Outpost, Heart of Yavimaya,
Soldevi Excavations, Balduvian Trading Post).

CR 2026-09-25: the ability replaces the permanent's entering (614.1a) with a payment and then, if it was made, the
entering (118.12: "If you do" checks whether the player chose to pay; "you may" is optional, the plain wording is
paid when it can be, 118.3). Its choice is made before the permanent enters (614.12a), on every path onto the
battlefield (a resolving spell, a land play, an effect putting it there: app/rules/replacements.py); the objects
it chooses can't be the one entering or one entering at the same time (614.13a), nor one already chosen for
another permanent entering with it (614.13b). If no payment is made it never enters: it is put into its owner's
graveyard from where it was (614.6: the replaced event never happens). A land played this way is still the land
played this turn (305.1-305.2a: playing it was the special action; its entering is what's replaced).

The question is private (the land cards in the controller's hand are hidden, 400.2): it's asked whenever the hand
holds another card, even when none would do (skipping it would tell the table there is none — as the reveal lands
do, app/rules/reveal_lands.py); a sacrifice needs a permanent on the battlefield (public), so with none it isn't
asked. The answer is recorded like the other entering answers (``choices[WHAT]``: the object, or :data:`NONE`).

-- Several objects (wave 110C) -- "sacrifice two untapped lands instead" (Scorched Ruins, Lotus Vale): the answer is the picks so far,
comma-joined (as devour's are), asked again until there are as many as the cost needs; refusing any one of them is refusing the payment.
A token copy of such a permanent is left to the players (app/rules/copying.py).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption, PaymentRecord
from app.game.state import zone_key

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

KIND = "enter_cost"
WHAT = "enter_cost"
NONE = "none"
_TEXT = re.compile(r"^If ~ would enter, (?P<may>you may )?(?P<cost>discard a land card|sacrifice an? (?:untapped )?"
                   r"(?:Plains|Island|Swamp|Mountain|Forest)|sacrifice two untapped lands) instead\. If you do, put ~ onto the battlefield\. If you don't, "
                   r"put it into its owner's graveyard\.$")


def definition(text: str) -> dict[str, Any] | None:
    m = _TEXT.match(text)
    if m is None:
        return None
    from app.rules import optional_payment

    cost = m["cost"][0].upper() + m["cost"][1:]
    parsed = optional_payment.parse(cost)
    if parsed is None or len(parsed.components) != 1 or parsed.components[0].amount not in (1, 2):
        return None
    return {"kind": "replacement", "replacement": KIND, "cost": cost, "may": bool(m["may"]), "effects": []}


def _component(d: dict[str, Any]) -> Any:
    from app.rules import optional_payment

    cost = optional_payment.parse(d["cost"])
    assert cost is not None
    return cost.components[0]


def candidates(plan: Plan, card: CardInstance, controller: str, d: dict[str, Any], reserved: set[str]) -> list[str]:
    """What could pay it: never the permanent entering, one entering with it, or one another entering permanent
    already chose (614.13a-b)."""
    from app.rules import cost_payment

    probe = card.model_copy(update={"controller": controller})
    return [c for c in cost_payment.candidates(plan, _component(d), controller, probe) if c != card.id and c not in reserved]


def picks(value: str | None) -> list[str]:
    return [x for x in (value or "").split(",") if x]


def merge(previous: str | None, chosen: str) -> str:
    """-- several objects (wave 110C) -- the answer after one more pick (declining at any point declines the payment)."""
    return NONE if NONE in (previous, chosen) else ",".join([*picks(previous), chosen])


def _is_discard(d: dict[str, Any]) -> bool:
    return d["cost"].startswith("Discard")


def plan_entry(plan: Plan, card: CardInstance, controller: str, defs: list[dict[str, Any]], answers: dict[str, str],
               out: dict[str, Any], reserved: set[str]) -> None:
    """replacements.entry_plan's part: ``out["pay"]`` (the object to pay with), ``out["divert"]`` (it goes to its
    owner's graveyard instead), or the question (``out["choice"]``)."""
    for d in defs:
        if d.get("replacement") != KIND:
            continue
        found = candidates(plan, card, controller, d, reserved)
        given = answers.get(WHAT)
        chosen, need = picks(given), _component(d).amount
        if given is None or (chosen and NONE not in chosen and len(chosen) < need and set(chosen) <= set(found)):
            hidden = _is_discard(d) and any(c != card.id for c in plan.state.zones.get(zone_key(controller, "hand"), []))
            if len(found) < need - len(chosen) and not hidden:
                out["divert"] = True
            elif "choice" not in out:
                out["choice"] = {"what": WHAT, "picked": given}
        elif len(chosen) == need and set(chosen) <= set(found) and len(set(chosen)) == need:
            out.setdefault("choices", {})[WHAT] = given
            out["pay"] = {"cost": d["cost"], "object": given}
        else:  # declined, or what was chosen is gone meanwhile (nothing paid: 118.3)
            out["divert"] = True
        return


def is_choice(what: str) -> bool:
    return what == WHAT


def prompt(plan: Plan, card: CardInstance, controller: str, reserved: set[str] | None = None, picked: str | None = None) -> tuple[str, list[DecisionOption]]:
    """The private question: what to pay with, or nothing (it goes to the graveyard)."""
    from app.rules import scripts

    d = next(x for x in scripts.definitions(plan.ch(card)).values() if x.get("replacement") == KIND)
    found = candidates(plan, card, controller, d, {*(reserved or ()), *picks(picked)})
    verb = "Discard" if _is_discard(d) else "Sacrifice"
    options = [DecisionOption(id=c, label=f"{verb} {plan.state.cards[c].name or 'card'}", card_id=c) for c in found]
    if d["may"] or not found:
        options.append(DecisionOption(id=NONE, label=f"Don't ({card.name or 'it'} goes to the graveyard)"))
    return f"{card.name}: as it would enter, {d['cost'][0].lower() + d['cost'][1:]} instead?", options


def pay(plan: Plan, card: CardInstance, controller: str, pay: dict[str, Any], actor: str) -> bool:
    """Make the payment before it enters (118.12); False if it can't be made any more (then it doesn't enter)."""
    from app.rules import cost_payment, optional_payment

    cost = optional_payment.parse(pay["cost"])
    assert cost is not None
    comp = cost.components[0]
    probe = card.model_copy(update={"controller": controller})
    objects = picks(pay["object"])
    if not objects or any(o not in cost_payment.candidates(plan, comp, controller, probe) for o in objects):
        return False
    record = PaymentRecord(card=card.id, controller=controller, total_cost=pay["cost"])
    saved = plan.actor
    plan.actor = controller  # (cost_payment acts as the payer: the discard / sacrifice is theirs)
    try:
        cost_payment.pay(plan, cost, probe, {0: objects}, record)
    finally:
        plan.actor = saved
    plan.note(f"{plan.name(controller)} paid “{pay['cost']}” for {card.name or 'it'} to enter", objects)
    return True


def divert(plan: Plan, card_id: str, actor: str) -> None:
    """It never enters: put into its owner's graveyard instead (614.6)."""
    card = plan.state.cards[card_id]
    plan.note(f"{card.name or 'It'} doesn't enter: it is put into its owner's graveyard", [card_id])
    if card.zone != zone_key(card.owner, "graveyard"):
        plan.do({"type": "move", "card_ids": [card_id], "to": {"player": card.owner, "zone": "graveyard"}}, actor=actor)


def chosen_objects(entries: list[dict[str, Any]], skip: int) -> set[str]:
    """The objects other entries entering together already chose (614.13b)."""
    from app.rules import devour  # -- keyword mechanics (wave 9D) -- what another entering devourer picked

    return {c for i, e in enumerate(entries)
            if i != skip and (e.get("choices") or {}).get(WHAT) not in (None, NONE) for c in picks(e["choices"][WHAT])} | {
        c for i, e in enumerate(entries) if i != skip for c in devour.picked((e.get("choices") or {}).get(devour.WHAT))}
