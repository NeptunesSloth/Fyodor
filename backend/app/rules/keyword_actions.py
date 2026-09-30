"""Keyword actions (CR 701) as effect primitives, on top of the building blocks in
``app.rules.effects`` (create_token, add_counters, draw, discard, decisions).

Each primitive carries out one keyword action exactly as the Comprehensive Rules define it (the
rule number is in its docstring); the Oracle wording that calls for it is a template at the end
of ``app.rules.scripts``. A primitive that needs a choice opens a decision for the player who
makes it (703/701: "choose a creature you control …" is that player's choice, nobody else's) and
the resolver continues from ``RESUME`` when it is answered.

Implemented: amass (701.47), connive (701.50), monstrosity (701.37), bolster (701.39); support
(701.41) needs no primitive (it is "put a +1/+1 counter on each of up to N other target
creatures", a template over add_counters). Not implemented, on purpose: goad (701.15: "attacks a
player other than you if able" is a combat requirement app/rules/combat.py doesn't model, and its
"until your next turn" duration has no continuous-effect duration yet), earthbend (701.66: the
"when that land dies or is exiled, return it" delayed trigger isn't modeled), incubate (701.53:
the Incubator's "{2}: Transform this token." needs transforming, which the engine doesn't do).
"""

from __future__ import annotations

from typing import Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key
from app.rules import effects, selectors, token_grammar
from app.rules.plan import Plan, decide

Context = dict[str, Any]

ARMY_KEY = 'sel:{"controller":"you","subtypes":["Army"],"types":["Creature"]}'  # "Army creature you control"


# -- amass (701.47) ---------------------------------------------------------------------------
def army_token(subtype: str) -> dict[str, Any]:
    """701.47a: "a 0/0 black [subtype] Army creature token"."""
    return {"name": f"{subtype} Army", "power": "0", "toughness": "0", "colors": ["B"],
            "type_line": f"Token Creature — {subtype} Army", "text": ""}


def _armies(plan: Plan, ctx: Context) -> list[str]:
    return selectors.candidates(plan, selectors.from_key(ARMY_KEY), ctx["controller"], ctx.get("source_card"))


def amass(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.47a: "To amass [subtype] N means 'If you don't control an Army creature, create a 0/0
    black [subtype] Army creature token. Choose an Army creature you control. Put N +1/+1
    counters on that creature. If it isn't a [subtype], it becomes a [subtype] in addition to its
    other types.'" The choice is the controller's when they control several Armies."""
    sub, n = e["sub"], effects._amount(plan, ctx, e["n"])
    armies = _armies(plan, ctx)
    if not armies:
        effects.create_token(plan, ctx, {"who": "you", "n": 1, "token": army_token(sub)})
        armies = _armies(plan, ctx)
        if not armies:
            return True  # 701.47b: amassed, even though the token couldn't be created
    if len(armies) == 1:
        _amass_on(plan, ctx, armies[0], sub, n)
        return True
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"Amass {sub}s {n}: choose an Army you control",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Army", card_id=c) for c in armies],
           resume={"step": "amass_choose", "ctx": ctx, "sub": sub, "n": n})
    return False


def _amass_on(plan: Plan, ctx: Context, cid: str, sub: str, n: int) -> None:
    if n > 0:
        plan.do({"type": "counter", "card_ids": [cid], "kind": "+1/+1", "delta": n}, actor=ctx["controller"])
    card = plan.state.cards.get(cid)
    if card is None or not card.zone.endswith(":battlefield"):
        return
    ch = plan.ch(card)
    if sub not in ch.subtypes:
        # 701.47a, last sentence: "it becomes a [subtype] in addition to its other types" — a
        # type-changing effect (layer 4, 613.1d) on that object; no duration is stated, so it
        # lasts until the end of the game (611.2a) — for the object, which ends when it leaves
        # the battlefield (611.2c, 400.7)
        from app.rules import layers

        layers.add_effect(plan, affected=[plan.oid(cid)], layer="4", source=ctx.get("source_object"),
                          controller=ctx["controller"], add_subtypes=(sub,), duration="permanent",
                          label=f"{ch.name} is also a {sub}")
        plan.note(f"{ch.name} becomes a {sub} in addition to its other types", [cid], actor=ctx["controller"])


def resume_amass(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    if chosen and chosen[0] in plan.state.cards and plan.state.cards[chosen[0]].zone.endswith(":battlefield"):
        _amass_on(plan, r["ctx"], chosen[0], r["sub"], r["n"])
    effects.continue_effects(plan, r["ctx"])


# -- connive (701.50) -------------------------------------------------------------------------
def connive(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.50a: "that permanent's controller draws a card, then discards a card. If a nonland card
    is discarded this way, that player puts a +1/+1 counter on the conniving permanent."
    701.50d (connive N): draw N, discard N, one counter per nonland card discarded. 701.50b: a
    permanent that already left connives by its last known information (its last controller
    draws and discards; there is no permanent to put a counter on). 701.50c: several conniving
    permanents connive one at a time, their controllers in APNAP order. 701.50e: connive 0 is
    nothing. The discard is that player's private choice from their hand."""
    n = effects._amount(plan, ctx, e.get("n", 1))
    if n <= 0:
        return True
    who = e.get("who", "self")
    queue: list[Conniver] = [(cid, plan.oid(cid), plan.state.cards[cid].controller) for cid in effects._cards(plan, ctx, who)]
    if not queue and who == "self":
        lki = plan.rules.lki.get(ctx.get("source_object") or "")
        if lki is not None:
            queue = [(None, None, lki.controller)]
    order = plan.apnap()
    queue.sort(key=lambda x: order.index(x[2]) if x[2] in order else len(order))
    return _connive_next(plan, ctx, queue, n)


Conniver = tuple[str | None, str | None, str]  # (the card, its rules object, its controller)


def _connive_next(plan: Plan, ctx: Context, queue: list[Conniver], n: int) -> bool:
    """Each conniver in turn: its controller draws, then chooses the discard (a decision when
    there is a choice). True when every one is done."""
    while queue:
        cid, oid, pid = queue.pop(0)
        if pid not in plan.live():
            continue
        effects.draw(plan, ctx, {"who": f"player:{pid}", "n": n})
        hand = list(plan.state.zones.get(zone_key(pid, "hand"), []))
        if n >= len(hand):  # no choice: the whole hand (or nothing) is discarded
            _connive_discard(plan, cid, oid, pid, hand)
            continue
        decide(plan, player=pid, kind="choose_cards", prompt=f"Connive: discard {n} card{'s' if n != 1 else ''}",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in hand],
               min_choices=n, max_choices=n,
               resume={"step": "connive_discard", "ctx": ctx, "card": cid, "object": oid, "player": pid, "n": n,
                       "queue": [list(q) for q in queue]})
        return False
    return True


def _connive_discard(plan: Plan, cid: str | None, oid: str | None, pid: str, chosen: list[str]) -> None:
    """701.9a: the chosen cards go to the graveyard, all at once; then one +1/+1 counter per nonland
    card among them — on the conniving permanent, if it is still that object on the battlefield."""
    cards = [c for c in chosen if c in plan.state.cards and plan.state.cards[c].zone == zone_key(pid, "hand")]
    if not cards:
        return
    nonland = sum(1 for c in cards if not plan.ch(plan.state.cards[c]).is_land)
    plan.do({"type": "move", "card_ids": cards, "to": {"zone": "graveyard"}}, actor=pid)
    card = plan.state.cards.get(cid or "")
    if nonland and card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == oid:
        plan.do({"type": "counter", "card_ids": [card.id], "kind": "+1/+1", "delta": nonland}, actor=pid)


def resume_connive(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    _connive_discard(plan, r["card"], r["object"], r["player"], chosen)
    if _connive_next(plan, r["ctx"], [(q[0], q[1], q[2]) for q in r["queue"]], r["n"]):
        effects.continue_effects(plan, r["ctx"])


# -- monstrosity (701.37) ---------------------------------------------------------------------
def monstrosity(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.37a: "If this permanent isn't monstrous, put N +1/+1 counters on it and it becomes
    monstrous." 701.37b: monstrous is a designation of the permanent, kept until it leaves the
    battlefield (a new object then, 400.7: the marker is by rules object)."""
    n = effects._amount(plan, ctx, e["n"])
    for cid in effects._cards(plan, ctx, "self"):
        oid = plan.oid(cid)
        name = plan.state.cards[cid].name or "It"
        if oid in plan.rules.monstrous:
            plan.note(f"{name} is already monstrous", [cid], actor=ctx["controller"])
            continue
        if n > 0:
            plan.do({"type": "counter", "card_ids": [cid], "kind": "+1/+1", "delta": n}, actor=ctx["controller"])
        plan.rules.monstrous.append(oid)
        plan.do({"type": "add_effect", "card_ids": [cid], "name": "Monstrous", "value": "Monstrous",
                 "text": "until it leaves the battlefield"})
    return True


# -- bolster (701.39) -------------------------------------------------------------------------
def _toughness(ch: Any) -> int:
    if ch.pt is not None:
        return int(ch.pt[1])
    raw = ch.toughness
    return int(raw) if raw and raw.lstrip("-").isdigit() else 0


def bolster(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.39a: "Choose a creature you control with the least toughness or tied for least
    toughness among creatures you control. Put N +1/+1 counters on that creature." With a tie,
    the choice is the controller's (their decision alone)."""
    pid = ctx["controller"]
    n = effects._amount(plan, ctx, e["n"])
    mine = [c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == pid
            and plan.in_game(c) and plan.ch(c).is_creature]
    if not mine or n <= 0:
        return True
    least = min(_toughness(plan.ch(c)) for c in mine)
    tied = [c for c in mine if _toughness(plan.ch(c)) == least]
    if len(tied) == 1:
        plan.do({"type": "counter", "card_ids": [tied[0].id], "kind": "+1/+1", "delta": n}, actor=pid)
        return True
    decide(plan, player=pid, kind="choose_cards", prompt=f"Bolster {n}: choose a creature with the least toughness ({least})",
           options=[DecisionOption(id=c.id, label=c.name or "Creature", card_id=c.id) for c in tied],
           resume={"step": "bolster_choose", "ctx": ctx, "n": n})
    return False


def resume_bolster(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    if chosen and chosen[0] in plan.state.cards and plan.state.cards[chosen[0]].zone.endswith(":battlefield"):
        plan.do({"type": "counter", "card_ids": [chosen[0]], "kind": "+1/+1", "delta": r["n"]}, actor=d.player)
    effects.continue_effects(plan, r["ctx"])


PRIMITIVES = {"amass": amass, "connive": connive, "monstrosity": monstrosity, "bolster": bolster,
              **token_grammar.PRIMITIVES}
RESUME = {"amass_choose": resume_amass, "bolster_choose": resume_bolster, "connive_discard": resume_connive,
          **token_grammar.RESUME}
