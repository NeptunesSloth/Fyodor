"""Effect primitives and the resolver for declarative definitions (``app.rules.scripts``).

Each primitive carries out one kind of instruction with ordinary table actions (so undo, replay
and the log work as everywhere else). The resolver runs a definition's effects in order
(608.2c); a primitive that needs a player's choice (scry, surveil) opens a decision and the
resolver continues from there when it is answered.

Primitives today: draw, gain_life, lose_life, damage (noncombat, as damage events; lifelink and
deathtouch apply), pump / grant (continuous effects until end of turn, layer 7c / 6), destroy
(indestructible respected), exile, bounce, tap, untap, scry, surveil, player_counter.
"""

from __future__ import annotations

from typing import Any

from app.game.rules_state import DecisionOption, StackEntry
from app.game.state import zone_key
from app.rules import layers
from app.rules.plan import Plan, decide
from app.rules.targets import still_legal

Context = dict[str, Any]  # {"controller", "source_card", "source_object", "name", "targets": [...], "stack_id", "kind"}


def _players(plan: Plan, ctx: Context, who: str) -> list[str]:
    me = ctx["controller"]
    if who == "you":
        return [me]
    if who == "each_player":
        return list(plan.live())
    if who == "each_opponent":
        return [p for p in plan.live() if p != me]
    if who == "target":
        return [t["id"] for t in ctx["targets"] if t["id"] in plan.state.players and t["id"] in plan.live()]
    return []


def _cards(plan: Plan, ctx: Context, who: str) -> list[str]:
    if who == "target":
        return [t["id"] for t in ctx["targets"] if t["id"] in plan.state.cards
                and plan.oid(t["id"]) == t.get("object_id")]
    if who == "self":
        src = plan.state.cards.get(ctx.get("source_card") or "")
        if src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == ctx.get("source_object"):
            return [src.id]
        return []  # the source left: "it" is gone (a new object isn't affected)
    if who == "creatures_you_control":
        return [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == ctx["controller"]
                and plan.in_game(c) and plan.ch(c).is_creature]
    if who == "each_creature":
        return [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.in_game(c)
                and plan.ch(c).is_creature]
    return []


def draw(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    for pid in _players(plan, ctx, e["who"]):
        library = plan.state.zones.get(zone_key(pid, "library"), [])
        n = min(e["n"], len(library))
        if n:
            plan.do({"type": "draw", "player": pid, "count": n}, actor=pid)
        if n < e["n"] and pid not in plan.rules.drew_from_empty:
            plan.rules.drew_from_empty.append(pid)  # 704.5b at the next check
    return True


def gain_life(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    for pid in _players(plan, ctx, e["who"]):
        plan.do({"type": "life", "player": pid, "delta": e["n"]}, actor=ctx["controller"])
    return True


def lose_life(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    for pid in _players(plan, ctx, e["who"]):
        plan.do({"type": "life", "player": pid, "delta": -e["n"]}, actor=ctx["controller"])
    return True


def damage(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Noncombat damage from the source (120.3): life loss for players, marked damage for
    creatures, loyalty loss for planeswalkers; lifelink and deathtouch of the source apply."""
    n = e["n"]
    players = _players(plan, ctx, e["who"])
    cards = _cards(plan, ctx, e["who"])
    source = plan.state.cards.get(ctx.get("source_card") or "")
    lki = plan.rules.lki.get(ctx.get("source_object") or "")
    keywords: frozenset[str] = frozenset()
    if source is not None and source.zone.endswith(":battlefield") and plan.oid(source) == ctx.get("source_object"):
        keywords = plan.ch(source).keywords
    elif lki is not None and source is not None:
        keywords = plan.ch(source).keywords  # (printed keywords of the card; LKI of granted ones is M16 later)
    creatures, walkers, dealt = {}, {}, []
    deathtouched = []
    for cid in cards:
        card = plan.state.cards[cid]
        ch = plan.ch(card)
        if "Planeswalker" in ch.types and not ch.is_creature:
            walkers[cid] = n
        else:
            creatures[cid] = n
            if "deathtouch" in keywords:
                deathtouched.append(cid)
        dealt.append({"source": ctx.get("source_object") or "", "target": cid, "target_object": plan.oid(cid), "amount": n})
    for pid in players:
        dealt.append({"source": ctx.get("source_object") or "", "target": pid, "amount": n})
    if not dealt or n <= 0:
        return True
    total = n * (len(cards) + len(players))
    plan.do({"type": "rules_damage", "creatures": creatures, "players": {p: n for p in players}, "planeswalkers": walkers,
             "lifelink": {ctx["controller"]: total} if "lifelink" in keywords else {}, "combat": False,
             "dealt": dealt}, actor=ctx["controller"])
    plan.rules.deathtouched = list(dict.fromkeys([*plan.rules.deathtouched, *deathtouched]))
    return True


def pump(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    affected = [plan.oid(c) for c in _cards(plan, ctx, e["who"])]  # locked in now (611.2c)
    if affected:
        layers.add_effect(plan, affected=affected, layer="7c", source=ctx.get("source_object"), controller=ctx["controller"],
                          power=e["p"], toughness=e["t"], label=f"{e['p']:+d}/{e['t']:+d} until end of turn ({ctx.get('name', '')})")
        _mark(plan, _cards(plan, ctx, e["who"]), f"{e['p']:+d}/{e['t']:+d}")
    return True


def grant(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    cards = _cards(plan, ctx, e["who"])
    if cards:
        layers.add_effect(plan, affected=[plan.oid(c) for c in cards], layer="6", source=ctx.get("source_object"),
                          controller=ctx["controller"], add_keywords=tuple(e["keywords"]),
                          label=f"{', '.join(e['keywords'])} until end of turn")
        _mark(plan, cards, ", ".join(k.capitalize() for k in e["keywords"]))
    return True


def _mark(plan: Plan, cards: list[str], label: str) -> None:
    """The visible table marker for an engine effect (it goes away at cleanup with the effect)."""
    for cid in cards:
        plan.do({"type": "add_effect", "card_ids": [cid], "name": label, "value": label, "text": "until end of turn"})


def destroy(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    doomed = [c for c in _cards(plan, ctx, e["who"]) if "indestructible" not in plan.ch(plan.state.cards[c]).keywords]
    if doomed:
        plan.do({"type": "move", "card_ids": doomed, "to": {"zone": "graveyard"}}, actor=ctx["controller"])
    return True


def exile(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    cards = _cards(plan, ctx, e["who"])
    if cards:
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "exile"}}, actor=ctx["controller"])
    return True


def bounce(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    for cid in _cards(plan, ctx, e["who"]):
        owner = plan.state.cards[cid].owner
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": owner, "zone": "hand"}}, actor=ctx["controller"])
    return True


def tap(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    cards = [c for c in _cards(plan, ctx, e["who"]) if not plan.state.cards[c].tapped]
    if cards:
        plan.do({"type": "tap", "card_ids": cards, "tapped": True}, actor=ctx["controller"])
    return True


def untap(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    cards = [c for c in _cards(plan, ctx, e["who"]) if plan.state.cards[c].tapped]
    if cards:
        plan.do({"type": "tap", "card_ids": cards, "tapped": False}, actor=ctx["controller"])
    return True


def player_counter(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    for pid in _players(plan, ctx, e["who"]):
        plan.do({"type": "resource", "player": pid, "key": e["counter"], "delta": e["n"]}, actor=ctx["controller"])
    return True


def scry(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.22a: look at the top N, put any number on the bottom in any order, the rest on top in
    any order. Asked as two private choices (which go to the bottom, then the order on top)."""
    return _look(plan, ctx, e, "bottom")


def surveil(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.25a: look at the top N, put any number into the graveyard, the rest on top in any order."""
    return _look(plan, ctx, e, "graveyard")


def _look(plan: Plan, ctx: Context, e: dict[str, Any], where: str) -> bool:
    pid = ctx["controller"]
    top = plan.state.zones.get(zone_key(pid, "library"), [])[: e["n"]]
    if not top:
        return True
    options = [DecisionOption(id=cid, label=plan.state.cards[cid].name or "Card", card_id=cid) for cid in top]
    verb = "Scry" if where == "bottom" else "Surveil"
    dest = "the bottom of your library" if where == "bottom" else "your graveyard"
    decide(plan, player=pid, kind="choose_cards", prompt=f"{verb} {e['n']}: choose the cards to put into {dest} (the rest stay on top)",
           options=options, min_choices=0, max_choices=len(top),
           resume={"step": "look", "where": where, "cards": list(top), "ctx": ctx})
    return False


PRIMITIVES = {
    "draw": draw, "gain_life": gain_life, "lose_life": lose_life, "damage": damage, "pump": pump, "grant": grant,
    "destroy": destroy, "exile": exile, "bounce": bounce, "tap": tap, "untap": untap, "scry": scry, "surveil": surveil,
    "player_counter": player_counter,
}


def resume_look(plan: Plan, d: Any, chosen: list[str]) -> None:
    """After a scry/surveil choice: move the chosen cards, then (if needed) ask the order on top."""
    r = d.resume
    pid = d.player
    library = plan.state.zones.get(zone_key(pid, "library"), [])
    chosen = [c for c in chosen if c in library]
    if chosen:
        if r["where"] == "graveyard":
            plan.do({"type": "move", "card_ids": chosen, "to": {"player": pid, "zone": "graveyard"}}, actor=pid)
        else:
            plan.do({"type": "move", "card_ids": chosen, "to": {"player": pid, "zone": "library"}, "position": "bottom"}, actor=pid)
    rest = [c for c in r["cards"] if c not in chosen and c in plan.state.zones.get(zone_key(pid, "library"), [])]
    if len(rest) > 1 or len(chosen) > 1 and r["where"] == "bottom":
        ordering = rest if len(rest) > 1 else chosen
        place = "top" if len(rest) > 1 else "bottom"
        decide(plan, player=pid, kind="order",
               prompt=f"Order the cards for the {place} of your library (first chosen ends up on {'top' if place == 'top' else 'the bottom'})",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in ordering],
               min_choices=len(ordering), max_choices=len(ordering),
               resume={"step": "order_library", "place": place, "then_bottom": chosen if place == "top" and len(chosen) > 1 else [],
                       "ctx": r["ctx"]})
        return
    continue_effects(plan, r["ctx"])


def resume_order_library(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    pid = d.player
    if r["place"] == "top":
        # The first chosen card goes on top: put them on top in reverse.
        for cid in reversed(chosen):
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": pid, "zone": "library"}, "position": "top"}, actor=pid)
    else:
        for cid in reversed(chosen):  # the first chosen ends at the very bottom
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": pid, "zone": "library"}, "position": "bottom"}, actor=pid)
    if r.get("then_bottom"):
        bottom = r["then_bottom"]
        decide(plan, player=pid, kind="order", prompt="Order the cards for the bottom of your library (first chosen ends up at the very bottom)",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in bottom],
               min_choices=len(bottom), max_choices=len(bottom),
               resume={"step": "order_library", "place": "bottom", "then_bottom": [], "ctx": r["ctx"]})
        return
    continue_effects(plan, r["ctx"])


# -- resolving a definition -----------------------------------------------------------------
def begin_resolution(plan: Plan, stack_id: str, entry: StackEntry) -> None:
    """608.2: check targets, ask "you may", then carry out the effects in order."""
    ctx: Context = {"controller": entry.controller, "source_card": entry.source_card, "source_object": entry.source_object,
                    "name": entry.name, "targets": [t.model_dump() for t in entry.targets], "stack_id": stack_id,
                    "kind": entry.kind, "effects": entry.effects, "next": 0}
    spec = entry.target_spec
    if spec and entry.targets:
        legal = [t for t in entry.targets if still_legal(plan, spec["what"], entry.controller, t)]
        if not legal:
            plan.note(f"{entry.name or 'It'} does nothing: its target is no longer legal")
            finish(plan, ctx, countered=True)
            return
        ctx["targets"] = [t.model_dump() for t in legal]
    if entry.optional:
        from app.rules.engine import remembered  # engine imports this module

        key = f"may:{entry.name}:{entry.effects[0]['do'] if entry.effects else ''}"
        answer = remembered(plan, entry.controller, key, "")
        if answer in ("yes", "no"):
            if answer == "no":
                finish(plan, ctx)
                return
        else:
            summary = describe(entry.effects)
            decide(plan, player=entry.controller, kind="confirm", prompt=f"{entry.name}: {summary}?",
                   options=[DecisionOption(id="yes", label="Yes"), DecisionOption(id="no", label="No")],
                   resume={"step": "may", "ctx": ctx}, memory_key=key)
            return
    continue_effects(plan, ctx)


def resume_may(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx = d.resume["ctx"]
    if chosen[0] == "yes":
        continue_effects(plan, ctx)
    else:
        plan.note(f"{plan.name(d.player)} chose not to")
        finish(plan, ctx)


def continue_effects(plan: Plan, ctx: Context) -> None:
    effects = ctx["effects"]
    while ctx["next"] < len(effects):
        e = effects[ctx["next"]]
        ctx["next"] += 1
        if not PRIMITIVES[e["do"]](plan, ctx, e):
            return  # waiting for a choice; the decision's resume continues from ctx["next"]
    finish(plan, ctx)


def finish(plan: Plan, ctx: Context, *, countered: bool = False) -> None:
    from app.rules.engine import _after_resolution  # engine imports this module

    stack_id = ctx["stack_id"]
    stack = plan.state.zones.get("stack", [])
    plan.rules.stack.pop(stack_id, None)
    if stack_id in stack:
        if stack[-1] != stack_id:  # (defensive: resolution never adds to the stack today)
            plan.do({"type": "move", "card_ids": [stack_id], "to": {"zone": "graveyard"}}, actor=ctx["controller"])
        else:
            plan.do({"type": "resolve_top", "force": True}, actor=ctx["controller"])
    _after_resolution(plan)


def describe(effects: list[dict[str, Any]]) -> str:
    words = {"draw": "draw {n} card(s)", "gain_life": "gain {n} life", "lose_life": "lose {n} life", "scry": "scry {n}",
             "surveil": "surveil {n}", "damage": "deal {n} damage", "player_counter": "get {n} {counter}"}
    parts = [words.get(e["do"], e["do"]).format(**{k: v for k, v in e.items()}) for e in effects]
    return (", ".join(parts) or "do it").capitalize()
