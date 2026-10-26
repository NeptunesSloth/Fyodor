"""-- trigger other (wave 25B) -- join forces: "Starting with you, each player may pay any amount of mana. Each player draws X cards, where X
is the total amount of mana paid this way." (Minds Aglow, Shared Trauma, Alliance of Arms, Collective Voyage, Mana-Charged Dragon).
Researched against CR 2026-09-25.

* 207.2c: "join forces" is an ability word with no rules meaning; the rules are in the text. 101.4 / 608.2d: each player, starting with the
  spell's or ability's controller and then in turn order, is asked in turn whether to pay mana and how much (an optional cost paid as the
  instruction is carried out, 118.12; the payer can't pay more than they can pay, 118.3). Each payment is that player's own and private
  until made; the payments are made one after another so every later player knows what the earlier ones paid (it is open information).
* X is the total of what every player paid (608.2c: the instructions after it read it). It is recorded like a sized payment's X
  (app/rules/paid_x.py ``{"paid_x": "jf"}``), so "where X is the total amount of mana paid this way" is that value.
* The instruction splices one optional payment per player (the players still in the game when it is reached) into the resolution, then the
  total, behind it (as app/rules/each_may.py does for "each opponent may …").
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
BIND = "jf"  # the binding the total is recorded under ("the total amount of mana paid this way": language._rider_value)


def join_forces(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    live = set(plan.live())
    seats = plan.state.turn_order()
    start = seats.index(ctx["controller"]) if ctx["controller"] in seats else 0
    order = [p for i in range(len(seats)) if (p := seats[(start + i) % len(seats)]) in live]
    bind = e["bind"]
    pays = [{"do": "optional_payment", "who": f"player:{p}", "cost": "", "bind": f"{bind}{i}", "choose_x": {"max": None}}
            for i, p in enumerate(order)]
    total = {"do": "join_total", "binds": [p["bind"] for p in pays], "bind": bind}
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *pays, total, *ctx["effects"][at:]]
    return True


def join_total(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import paid_x

    n = sum(paid_x.amount(ctx, b) for b in e["binds"])
    paid_x._record(ctx, e["bind"], True, n)
    plan.note(f"{n} mana was paid this way for {ctx.get('name') or 'it'}")
    return True


PRIMITIVES = {"join_forces": join_forces, "join_total": join_total}
