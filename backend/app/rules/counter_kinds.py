"""-- counter kinds (wave 24C) -- instructions that read WHICH kinds of counters an object has.

"For each kind of counter on target permanent or player, give that permanent or player another counter of that kind." (Powerful
Broker, Skyship Plunderer, Maulfist Revolutionary), "For each kind of counter on target permanent, put another counter of that kind
on it or remove one from it." (Dramatist's Puppet, Quarry Hauler), "Choose a counter on target permanent or player. Give that
permanent or player another counter of that kind." (Animation Module), "Choose a counter on a permanent you control. Put a counter
of that kind on target permanent you control if it doesn't have a counter of that kind on it." (Aven Courier), "Remove any number
of counters from target creature you control." (Rhys, the Evermore).

* 122.1: a counter's kind is its name; the kinds an object has are read as the instruction is carried out (608.2h, 608.2b: a
  target that is gone isn't affected — nothing is read from it).
* 608.2d: "choose" / "you may" are choices made as it resolves — the controller's: the kind (offered among the kinds the objects
  have right now, a single one is taken without asking), "put … or remove one" per kind, the number of each kind removed.
* "Give … another counter" / "put another counter" is putting a counter (122.6): through the counter choke point, so Doubling
  Season and Vorinclex apply, all the kinds of one instruction at once (one event batch); removing isn't a put (122.8) and passes
  straight through.
* A player is a legal object for "give": a player's counters (poison, energy, experience …) are kinds too (122.1b-d, 122.5 doesn't
  apply — giving is a put, not a move).

Effect: ``{"do": "counter_kinds", "of": <who> | [<who>, …], "to": <who> | absent (= the objects it read), "pick": "each" | "one",
"then": "give" | "give_or_remove", "unless_has": bool}``; ``{"do": "remove_any_counters", "who": <who>}``.
Refused (manual): "give … another counter" of a kind that has a rule the engine doesn't carry (none are listed: a kind on the
object is data, put and removed the same way), a stun/finality counter read off an object that isn't on the table, and every wording
this module doesn't read."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules import replace
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
STEP = "counter_kinds"
AMOUNTS = "counter_amounts"


def _objects(plan: Plan, ctx: Context, who: str | list[str]) -> list[str]:
    """The cards (still the object that was chosen: 608.2b) and live players ``who`` names."""
    from app.rules import effects

    out: list[str] = []
    for w in [who] if isinstance(who, str) else who:
        for x in [*effects._cards(plan, ctx, w), *effects._players(plan, ctx, w)]:
            if x not in out:
                out.append(x)
    return out


def _counters(plan: Plan, obj: str) -> dict[str, int]:
    have = plan.state.cards[obj].counters if obj in plan.state.cards else plan.state.players[obj].resources
    return {k: v for k, v in sorted(have.items()) if v > 0}


def _label(plan: Plan, obj: str) -> str:
    return plan.state.cards[obj].name or "it" if obj in plan.state.cards else plan.name(obj)


def _put(plan: Plan, ctx: Context, e: dict[str, Any], puts: list[tuple[str, str, int]]) -> bool:
    from app.rules import effects

    return not puts or replace.put_counters(plan, puts, by=ctx["controller"], then=effects._then(ctx, e), ctx=ctx)


def kinds(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:

    objs = _objects(plan, ctx, e["of"])
    found = sorted({k for o in objs for k in _counters(plan, o)})
    to = _objects(plan, ctx, e["to"]) if e.get("to") else objs
    if not found or not to:
        return True
    if e["pick"] == "each":
        if e["then"] == "give":  # all the kinds at once (122.6: one batch through the choke point)
            return _put(plan, ctx, e, [(t, k, 1) for t in to for k in found if not e.get("unless_has") or not _counters(plan, t).get(k)])
        return _ask_each(plan, ctx, e, found, to, {})
    if len(found) == 1:  # (a choice of one: nothing to ask)
        return _give_kind(plan, ctx, e, found[0], to)
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Choose'}: choose a kind of counter",
           options=[DecisionOption(id=k, label=f"{k} counter") for k in found],
           resume={"step": STEP, "ctx": ctx, "e": e, "to": to, "found": found, "picks": None},
           source=plan.state.cards.get(ctx.get("source_card") or ""))
    return False


def _give_kind(plan: Plan, ctx: Context, e: dict[str, Any], kind: str, to: list[str]) -> bool:
    plan.note(f"{plan.name(ctx['controller'])} chooses a {kind} counter", actor=ctx["controller"])
    return _put(plan, ctx, e, [(t, kind, 1) for t in to if not e.get("unless_has") or not _counters(plan, t).get(kind)])


def _ask_each(plan: Plan, ctx: Context, e: dict[str, Any], found: list[str], to: list[str], picks: dict[str, str]) -> bool:
    """"… put another counter of that kind on it or remove one from it": the controller says which for each kind, in turn; then
    the puts go through at once and the removals pass straight through."""
    left = [k for k in found if k not in picks]
    if left:
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Choose'}: {left[0]} counter",
               options=[DecisionOption(id="put", label=f"Put another {left[0]} counter on it"),
                        DecisionOption(id="remove", label=f"Remove a {left[0]} counter from it")],
               resume={"step": STEP, "ctx": ctx, "e": e, "to": to, "found": found, "picks": picks, "kind": left[0]},
               source=plan.state.cards.get(ctx.get("source_card") or ""))
        return False
    puts = [(t, k, 1) for k, how in picks.items() if how == "put" for t in to]
    for k, how in picks.items():
        if how == "remove":
            for t in to:
                if t in plan.state.cards and plan.state.cards[t].counters.get(k, 0) > 0:
                    plan.do({"type": "counter", "card_ids": [t], "kind": k, "delta": -1}, actor=ctx["controller"])
    return _put(plan, ctx, e, puts)


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    ctx, e = r["ctx"], r["e"]
    if len(chosen) != 1:
        raise ActionError("Choose one")
    if r["picks"] is None:  # the kind
        if chosen[0] not in r["found"]:
            raise ActionError("Choose one of the kinds offered")
        done = _give_kind(plan, ctx, e, chosen[0], r["to"])
    else:
        if chosen[0] not in ("put", "remove"):
            raise ActionError("Choose to put or to remove")
        plan.note(f"{plan.name(d.player)} chooses to {chosen[0]} a {r['kind']} counter", actor=d.player)
        done = _ask_each(plan, ctx, e, r["found"], r["to"], {**r["picks"], r["kind"]: chosen[0]})
    if done:
        effects.continue_effects(plan, ctx)


# -- "any number of counters" (Rhys, the Evermore; counter_moves.py for the move wordings) -----------------------------------------
def ask_amounts(plan: Plan, ctx: Context, e: dict[str, Any], have: dict[str, int], then: dict[str, Any]) -> None:
    """How many of each kind (0 to all of them), kind by kind in order (608.2d); ``then`` says what happens with the totals."""
    _ask_amount(plan, ctx, e, have, {}, then)


def _ask_amount(plan: Plan, ctx: Context, e: dict[str, Any], have: dict[str, int], got: dict[str, int], then: dict[str, Any]) -> None:
    kind = next(k for k in have if k not in got)
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Choose'}: how many {kind} counters?",
           options=[DecisionOption(id=str(i), label=str(i)) for i in range(have[kind] + 1)],
           resume={"step": AMOUNTS, "ctx": ctx, "e": e, "have": have, "got": got, "kind": kind, "then": then},
           source=plan.state.cards.get(ctx.get("source_card") or ""))


def resume_amount(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import counter_moves, effects

    r = d.resume
    ctx, e, have = r["ctx"], r["e"], r["have"]
    if len(chosen) != 1 or not chosen[0].isdigit() or int(chosen[0]) > have[r["kind"]]:
        raise ActionError("Choose a number")
    got = {**r["got"], r["kind"]: int(chosen[0])}
    if len(got) < len(have):
        _ask_amount(plan, ctx, e, have, got, r["then"])
        return
    amounts = {k: n for k, n in got.items() if n > 0}
    plan.note(f"{plan.name(d.player)} chooses " + (", ".join(f"{n} {k}" for k, n in amounts.items()) or "none"), actor=d.player)
    if r["then"]["do"] == "move":
        done = counter_moves.finish(plan, ctx, e, r["then"]["from"], r["then"]["to"], amounts)
    else:
        for obj in r["then"]["from"]:
            for k, n in amounts.items():
                if obj in plan.state.cards and plan.state.cards[obj].counters.get(k, 0) > 0:
                    plan.do({"type": "counter", "card_ids": [obj], "kind": k, "delta": -min(n, plan.state.cards[obj].counters[k])},
                            actor=d.player)
        done = True
    if done:
        effects.continue_effects(plan, ctx)


def remove_any(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Remove any number of counters from target creature you control." (122.8: as many as it has; the controller chooses how many of
    each kind)."""
    from app.rules import effects

    cards = effects._cards(plan, ctx, e["who"])
    effects._remember(plan, ctx, e, cards)
    have: dict[str, int] = {}
    for c in cards:
        for k, v in _counters(plan, c).items():
            have[k] = have.get(k, 0) + v
    if not have:
        return True
    ask_amounts(plan, ctx, e, have, {"do": "remove", "from": cards})
    return False


PRIMITIVES = {"counter_kinds": kinds, "remove_any_counters": remove_any}
RESUME = {STEP: resume, AMOUNTS: resume_amount}


_JOIN = re.compile(r"(?P<c>[Cc])hoose a counter on (?P<of>target permanent or player|a permanent you control)\. "
                   r"(?P<then>Give that permanent or player another counter of that kind|Put a counter of that kind on target permanent you control "
                   r"if it doesn't have a counter of that kind on it)\.")


def join(body: str) -> str:
    """"Choose a counter on …. Give … another counter of that kind." — one instruction printed as two sentences (the kind chosen in the
    first is the one the second names, 608.2c), read as "Choose a counter on …, then give …"."""
    return _JOIN.sub(lambda m: f"{m['c']}hoose a counter on {m['of']}, then {m['then'][0].lower()}{m['then'][1:]}.", body)
