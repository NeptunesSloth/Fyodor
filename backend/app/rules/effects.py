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
from app.rules import layers, protection, regeneration
from app.rules.plan import Plan, decide
from app.rules.targets import source_of, still_legal

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
    if who.startswith("object:"):  # one specific rules object (e.g. the creature that attacked alone)
        oid = who[7:]
        return [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.oid(c) == oid]
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
    src_ch = plan.ch(source) if source is not None else None
    if source is not None and source.zone.endswith(":battlefield") and plan.oid(source) == ctx.get("source_object"):
        keywords = plan.ch(source).keywords
    elif lki is not None and source is not None:
        keywords = plan.ch(source).keywords  # (printed keywords of the card; LKI of granted ones is M16 later)
    creatures, walkers, withered, dealt = {}, {}, {}, []
    deathtouched = []
    per: dict[str, int] = {}
    for cid in cards:
        card = plan.state.cards[cid]
        ch = plan.ch(card)
        if protection.protected_from(ch, src_ch):  # 702.16e: the damage is prevented
            plan.note(f"Protection prevents the damage to {ch.name}", [cid], actor=ctx["controller"])
            continue
        per[cid] = shield(plan, plan.oid(cid), n)
        if per[cid] <= 0:
            continue
        if "Planeswalker" in ch.types and not ch.is_creature:
            walkers[cid] = per[cid]
        elif {"wither", "infect"} & keywords:
            withered[cid] = per[cid]
        else:
            creatures[cid] = per[cid]
        if cid not in walkers and "deathtouch" in keywords:
            deathtouched.append(cid)
        dealt.append({"source": ctx.get("source_object") or "", "target": cid, "target_object": plan.oid(cid), "amount": per[cid]})
    to_players = {pid: shield(plan, pid, n) for pid in players}
    players = [pid for pid, m in to_players.items() if m > 0]
    for pid in players:
        dealt.append({"source": ctx.get("source_object") or "", "target": pid, "amount": to_players[pid]})
    if not dealt or n <= 0:
        return True
    total = sum(int(d["amount"]) for d in dealt)
    infect = "infect" in keywords
    for pid in players:
        plan.rules.damaged[pid] = plan.state.turn.number
    plan.do({"type": "rules_damage", "creatures": creatures, "players": {} if infect else {p: to_players[p] for p in players},
             "poison": {p: to_players[p] for p in players} if infect else {}, "wither": withered, "planeswalkers": walkers,
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


def _can_regenerate(ctx: Context) -> bool:
    """False when the spell or ability says "It/They can't be regenerated"."""
    return not any(x.get("do") == "no_regen" for x in ctx.get("effects") or [])


def destroy(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    doomed = [c for c in _cards(plan, ctx, e["who"]) if "indestructible" not in plan.ch(plan.state.cards[c]).keywords]
    doomed = regeneration.survivors(plan, doomed, can_regenerate=_can_regenerate(ctx))
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


def create_token(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """111: tokens are individual objects for the rules; identical ones may be *shown* as a pile."""
    t = e["token"]
    for pid in _players(plan, ctx, e["who"]):
        plan.do({"type": "create_token", "player": pid, "count": e["n"], "stacked": False,
                 "source_id": ctx.get("source_card") if ctx.get("source_card") in plan.state.cards else None,
                 "token": {"name": t["name"], "power": t.get("power"), "toughness": t.get("toughness"),
                           "colors": t.get("colors") or [], "type_line": t["type_line"], "text": t.get("text") or ""}},
                actor=pid)
    return True


def add_counters(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    cards = _cards(plan, ctx, e["who"])
    if cards:
        plan.do({"type": "counter", "card_ids": cards, "kind": e["kind"], "delta": e["n"]}, actor=ctx["controller"])
    return True


def proliferate(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.34a: choose any number of permanents and/or players that have a counter; each gets one
    more of each kind it already has."""
    options = [DecisionOption(id=c.id, label=f"{c.name} ({', '.join(f'{v} {k}' for k, v in c.counters.items() if v)})", card_id=c.id)
               for c in plan.state.cards.values()
               if c.zone.endswith(":battlefield") and plan.in_game(c) and any(v > 0 for v in c.counters.values())]
    options += [DecisionOption(id=pid, label=f"{plan.name(pid)} ({', '.join(f'{v} {k}' for k, v in p.resources.items() if v > 0)})")
                for pid, p in plan.state.players.items() if pid in plan.live() and any(v > 0 for v in p.resources.values())]
    if not options:
        return True
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt="Proliferate: choose permanents and players",
           options=options, min_choices=0, max_choices=len(options), resume={"step": "proliferate", "ctx": ctx})
    return False


def resume_proliferate(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx = d.resume["ctx"]
    for x in chosen:
        if x in plan.state.cards:
            card = plan.state.cards[x]
            for kind, v in list(card.counters.items()):
                if v > 0:
                    plan.do({"type": "counter", "card_ids": [x], "kind": kind, "delta": 1}, actor=d.player)
        elif x in plan.state.players:
            for kind, v in list(plan.state.players[x].resources.items()):
                if v > 0:
                    plan.do({"type": "resource", "player": x, "key": kind, "delta": 1}, actor=d.player)
    continue_effects(plan, ctx)


def regenerate(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.19: "Regenerate ~" / "Regenerate target creature": a shield for this turn."""
    for cid in _cards(plan, ctx, e["who"]):
        regeneration.add_shield(plan, cid)
        _mark(plan, [cid], "Regeneration shield")
    return True


def animate(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Layer 4: "~ becomes an artifact creature until end of turn" (a crewed Vehicle, 702.122)."""
    cards = _cards(plan, ctx, e["who"])
    if cards:
        layers.add_effect(plan, affected=[plan.oid(c) for c in cards], layer="4", source=ctx.get("source_object"),
                          controller=ctx["controller"], add_types=tuple(e["types"]),
                          label=f"{' '.join(e['types'])} until end of turn ({ctx.get('name', '')})")
        _mark(plan, cards, "Crewed" if e.get("crewed") else " ".join(e["types"]))
    return True


def renown(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.112: if it isn't renowned, N +1/+1 counters and it becomes renowned."""
    for cid in _cards(plan, ctx, "self"):
        oid = plan.oid(cid)
        if oid in plan.rules.renowned:
            continue
        plan.do({"type": "counter", "card_ids": [cid], "kind": "+1/+1", "delta": e["n"]}, actor=ctx["controller"])
        plan.rules.renowned.append(oid)
        _mark(plan, [cid], "Renowned")
    return True


def return_yours(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Return a land you control to its owner's hand" (bounce lands): a choice, not a target."""
    pid = ctx["controller"]
    pool = [c.id for c in plan.state.cards.values() if c.zone == zone_key(pid, "battlefield") and c.controller == pid
            and plan.in_game(c) and (plan.ch(c).is_land if e["what"] == "land" else plan.ch(c).is_creature)]
    n = min(e["n"], len(pool))
    if n == 0:
        return True
    if n == len(pool):
        _return_to_hands(plan, pool, pid)
        return True
    decide(plan, player=pid, kind="choose_cards", prompt=f"Return {n} {e['what']}{'s' if n != 1 else ''} you control to hand",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in pool],
           min_choices=n, max_choices=n, resume={"step": "return_yours", "ctx": ctx})
    return False


def _return_to_hands(plan: Plan, ids: list[str], actor: str) -> None:
    for cid in ids:
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "hand"}}, actor=actor)


def resume_return_yours(plan: Plan, d: Any, chosen: list[str]) -> None:
    _return_to_hands(plan, chosen, d.player)
    continue_effects(plan, d.resume["ctx"])


def suspend_tick(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.62b-d: remove a time counter; when the last is removed, its owner may cast it without
    paying its mana cost."""
    cid = e["card"]
    card = plan.state.cards.get(cid)
    r = plan.rules
    if card is None or cid not in r.suspended or not card.zone.endswith(":exile"):
        return True
    if card.counters.get("time", 0) > 0:
        plan.do({"type": "counter", "card_ids": [cid], "kind": "time", "delta": -1}, actor=card.owner)
    if card.counters.get("time", 0) > 0:
        return True
    r.free_casts.append(cid)
    decide(plan, player=card.owner, kind="choose_one", prompt=f"The last time counter was removed: cast {card.name} without paying its mana cost?",
           options=[DecisionOption(id="yes", label="Cast it"), DecisionOption(id="no", label="Leave it exiled")],
           resume={"step": "suspend_cast", "ctx": ctx, "card": cid}, source=card)
    return False


def resume_suspend_cast(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game import actions as A
    from app.rules.casting import cast_spell

    cid = d.resume["card"]
    finish(plan, d.resume["ctx"])
    r = plan.rules
    if chosen[0] != "yes":
        r.free_casts = [c for c in r.free_casts if c != cid]
        r.suspended = [c for c in r.suspended if c != cid]
        r.alt_costs.pop(cid, None)
        if d.resume.get("decline") == "graveyard" and cid in plan.state.cards:  # madness
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "graveyard"}},
                    actor=d.player)
            return
        if d.resume.get("decline") == "bottom" and cid in plan.state.cards:  # cascade: it joins the others
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "library"},
                     "position": "bottom"}, actor=d.player)
            plan.note(f"{plan.name(d.player)} puts it on the bottom of their library")
        else:
            plan.note(f"{plan.name(d.player)} leaves it exiled")
        return
    if r.decision is not None:
        plan.note("Cast it without paying its mana cost when the pending choice is done")
        return
    r.priority = d.player
    prev = plan.actor
    plan.actor = d.player
    try:
        cast_spell(plan, A.CastSpell(card_id=cid, free=True))
    finally:
        plan.actor = prev


def cascade(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.85a: exile cards from the top of your library until a nonland card with lesser mana
    value; you may cast it without paying its mana cost; the rest go on the bottom in a random order."""
    from app.rules import characteristics as chars

    pid = ctx["controller"]
    missed: list[str] = []
    hit: str | None = None
    for _ in range(len(plan.state.zones.get(zone_key(pid, "library"), []))):
        library = plan.state.zones.get(zone_key(pid, "library"), [])
        if not library:
            break
        top = library[0]
        plan.do({"type": "move", "card_ids": [top], "to": {"player": pid, "zone": "exile"}}, actor=pid)
        ch = chars.of(plan.state.cards[top], plan.info)
        if not ch.is_land and ch.mana_value < e["mv"]:
            hit = top
            break
        missed.append(top)
    order = list(missed)
    plan.rng.shuffle(order)
    for cid in order:
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": pid, "zone": "library"}, "position": "bottom"}, actor=pid)
    if hit is None:
        plan.note("Cascade found nothing")
        return True
    plan.rules.free_casts.append(hit)
    name = plan.state.cards[hit].name
    decide(plan, player=pid, kind="choose_one", prompt=f"Cascade: cast {name} without paying its mana cost?",
           options=[DecisionOption(id="yes", label="Cast it"), DecisionOption(id="no", label="Put it on the bottom")],
           resume={"step": "suspend_cast", "ctx": ctx, "card": hit, "decline": "bottom"}, source=plan.state.cards[hit])
    return False


def unearth(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    cid = e["card"]
    card = plan.state.cards.get(cid)
    if card is None or not card.zone.endswith(":graveyard") or plan.oid(cid) != e["object"]:
        return True  # it left the graveyard: the ability does nothing
    plan.do({"type": "move", "card_ids": [cid], "to": {"player": card.owner, "zone": "battlefield"}}, actor=ctx["controller"])
    oid = plan.oid(cid)
    layers.add_effect(plan, affected=[oid], layer="6", source=None, controller=ctx["controller"], add_keywords=("haste",),
                      duration="permanent", label="Haste (unearth)")
    plan.rules.exile_if_leaves.append(oid)
    plan.rules.delayed.append({"card": cid, "object": oid, "to": "exile", "name": card.name})
    return True


def delayed_move(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """A delayed trigger's move ("exile it / return it to its owner's hand at the next end step")."""
    card = plan.state.cards.get(e["card"])
    if card is None or not card.zone.endswith(":battlefield") or plan.oid(card) != e["object"]:
        return True  # it's a different object now
    plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": e["to"]}}, actor=ctx["controller"])
    return True


def free_cast_offer(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Rebound: you may cast it from exile without paying its mana cost (it stays exiled if not)."""
    cid = e["card"]
    card = plan.state.cards.get(cid)
    if card is None or not card.zone.endswith(":exile"):
        return True
    plan.rules.free_casts.append(cid)
    decide(plan, player=card.owner, kind="choose_one", prompt=f"Rebound: cast {card.name} without paying its mana cost?",
           options=[DecisionOption(id="yes", label="Cast it"), DecisionOption(id="no", label="Leave it exiled")],
           resume={"step": "suspend_cast", "ctx": ctx, "card": cid}, source=card)
    return False


def madness_offer(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.35a: "When this card is exiled this way, its owner may cast it by paying [cost] rather
    than its mana cost. If that player doesn't, they put this card into their graveyard." """
    cid = e["card"]
    card = plan.state.cards.get(cid)
    if card is None or not card.zone.endswith(":exile") or cid not in plan.rules.free_casts:
        return True
    decide(plan, player=card.owner, kind="choose_one", prompt=f"Madness: cast {card.name} for {e['cost']}?",
           options=[DecisionOption(id="yes", label=f"Cast it for {e['cost']}"), DecisionOption(id="no", label="Put it into your graveyard")],
           resume={"step": "suspend_cast", "ctx": ctx, "card": cid, "decline": "graveyard"}, source=card)
    return False


def counter_object(plan: Plan, stack_id: str, actor: str) -> None:
    """701.6: a countered spell goes to its owner's graveyard (a flashback spell into exile); a
    countered ability simply stops existing."""
    card = plan.state.cards.get(stack_id)
    if card is None or card.zone != "stack":
        return
    from app.rules import scripts

    if card.ability is None and scripts.uncounterable(plan.ch(card)):
        plan.note(f"{card.name} can't be countered", [stack_id])
        return
    r = plan.rules
    r.stack.pop(stack_id, None)
    oid = plan.oid(stack_id)
    r.buyback = [o for o in r.buyback if o != oid]
    plan.note(f"{card.name or 'It'} is countered", [stack_id])
    if oid in r.flashback:
        r.flashback = [o for o in r.flashback if o != oid]
        plan.do({"type": "move", "card_ids": [stack_id], "to": {"player": card.owner, "zone": "exile"}}, actor=actor)
    else:
        plan.do({"type": "move", "card_ids": [stack_id], "to": {"player": card.owner, "zone": "graveyard"}}, actor=actor)


def _stack_targets(plan: Plan, ctx: Context, e: dict[str, Any]) -> list[str]:
    if e.get("object"):
        return [e["object"]] if e["object"] in plan.state.cards and plan.state.cards[e["object"]].zone == "stack" else []
    return [t["id"] for t in ctx["targets"] if t["id"] in plan.state.cards and plan.state.cards[t["id"]].zone == "stack"
            and plan.oid(t["id"]) == t.get("object_id")]


def counter(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    for sid in _stack_targets(plan, ctx, e):
        counter_object(plan, sid, ctx["controller"])
    return True


def counter_unless(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Counter target spell unless its controller pays {X}" (and ward): that player decides; they
    can tap their mana while the prompt is open."""
    from app.rules import mana  # casting imports this module

    targets = _stack_targets(plan, ctx, e)
    if not targets:
        return True
    sid = targets[0]
    payer = plan.state.cards[sid].controller
    cost = mana.parse_cost(e["cost"])
    options = [DecisionOption(id="pay", label=f"Pay {cost.text()}"),  # (tap your mana first)
               DecisionOption(id="decline", label="Don't pay (it's countered)")]
    decide(plan, player=payer, kind="choose_one",
           prompt=f"{ctx.get('name', '')}: pay {cost.text()} or {plan.state.cards[sid].name or 'your spell'} is countered",
           options=options, resume={"step": "pay_or_sacrifice", "counter": sid, "ctx": ctx, "cost": e["cost"]},
           source=plan.state.cards[sid])
    return False


def sacrifice(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    for cid in _cards(plan, ctx, e["who"]):
        card = plan.state.cards[cid]
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": card.owner, "zone": "graveyard"}}, actor=card.controller)
    return True


def explore(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.44a: reveal the top card of your library. A land goes into your hand; otherwise put a
    +1/+1 counter on this creature, then you may put the revealed card into your graveyard."""
    from app.rules import characteristics as chars

    pid = ctx["controller"]
    library = plan.state.zones.get(zone_key(pid, "library"), [])
    me = _cards(plan, ctx, "self")
    if not library:
        if me:
            plan.do({"type": "counter", "card_ids": me, "kind": "+1/+1", "delta": 1}, actor=pid)
        return True
    top = library[0]
    plan.do({"type": "reveal_top", "player": pid, "count": 1}, actor=pid)
    card = plan.state.cards[top]
    if chars.of(card, plan.info).is_land:
        plan.do({"type": "move", "card_ids": [top], "to": {"player": pid, "zone": "hand"}}, actor=pid)
        return True
    if me:
        plan.do({"type": "counter", "card_ids": me, "kind": "+1/+1", "delta": 1}, actor=pid)
    decide(plan, player=pid, kind="choose_one", prompt=f"Explore revealed {card.name}: put it into your graveyard?",
           options=[DecisionOption(id="keep", label="Keep it on top"), DecisionOption(id="graveyard", label="Put it into your graveyard")],
           resume={"step": "explore", "ctx": ctx, "card": top}, source=card)
    return False


def resume_explore(plan: Plan, d: Any, chosen: list[str]) -> None:
    cid = d.resume["card"]
    if chosen[0] == "graveyard" and cid in plan.state.cards and plan.state.cards[cid].zone.endswith(":library"):
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": d.player, "zone": "graveyard"}}, actor=d.player)
    continue_effects(plan, d.resume["ctx"])


def prevent(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """615.7: "Prevent the next N damage that would be dealt to … this turn" — a shield."""
    r = plan.rules
    keys = [plan.oid(c) for c in _cards(plan, ctx, e["who"])] + _players(plan, ctx, e["who"])
    for key in keys:
        r.prevention[key] = r.prevention.get(key, 0) + e["n"]
    return True


def shield(plan: Plan, key: str, n: int) -> int:
    """Use prevention shields on ``key`` (a player or object id): how much of ``n`` is still dealt."""
    r = plan.rules
    left = r.prevention.get(key, 0)
    if not left or n <= 0:
        return n
    used = min(left, n)
    if left - used:
        r.prevention[key] = left - used
    else:
        r.prevention.pop(key, None)
    plan.note(f"{used} damage prevented")
    return n - used


def mill(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    for pid in _players(plan, ctx, e["who"]):
        n = min(e["n"], len(plan.state.zones.get(zone_key(pid, "library"), [])))
        if n:
            plan.do({"type": "mill", "player": pid, "count": n}, actor=pid)
    return True


def return_with_counter(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Persist / undying: "return it to the battlefield under its owner's control with a … counter on it"."""
    cid = ctx.get("source_card") or ""
    card = plan.state.cards.get(cid)
    if card is None or not card.zone.endswith(":graveyard"):
        return True  # it's gone (a token ceased to exist, or it left the graveyard)
    plan.do({"type": "move", "card_ids": [cid], "to": {"player": card.owner, "zone": "battlefield"}}, actor=card.owner)
    plan.do({"type": "counter", "card_ids": [cid], "kind": e["counter"], "delta": 1}, actor=card.owner)
    return True


def exile_until(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """610.3c: "exile … until ~ leaves the battlefield" — if the source already left, nothing happens."""
    src = _cards(plan, ctx, "self")
    if not src:
        return True
    cards = _cards(plan, ctx, e["who"])
    if cards:
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "exile"}}, actor=ctx["controller"])
        key = ctx["source_object"]
        plan.rules.linked_exile[key] = [*plan.rules.linked_exile.get(key, []), *cards]
    return True


def return_linked(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The exiled cards return to the battlefield under their owners' control (610.3c)."""
    from app.rules import attachments  # attachments → effects (resume)

    entries = []
    for cid in plan.rules.linked_exile.pop(e["source"], []):
        card = plan.state.cards.get(cid)
        if card is not None and card.zone.endswith(":exile"):
            entries.append({"card": cid, "player": card.owner, "actor": card.owner})
    return attachments.enter(plan, entries, ctx)


SERVO = {"name": "Servo", "power": "1", "toughness": "1", "colors": [], "type_line": "Token Artifact Creature — Servo", "text": ""}


def fabricate(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    n = e["n"]
    me = _cards(plan, ctx, "self")
    if not me:  # it left: only the Servos are possible (702.123b)
        return create_token(plan, ctx, {"who": "you", "n": n, "token": SERVO})
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"Fabricate {n}",
           options=[DecisionOption(id="counters", label=f"{n} +1/+1 counter{'s' if n != 1 else ''} on it"),
                    DecisionOption(id="servos", label=f"{n} 1/1 Servo{'s' if n != 1 else ''}")],
           resume={"step": "fabricate", "ctx": ctx, "n": n}, source=plan.state.cards[me[0]])
    return False


def resume_fabricate(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, n = d.resume["ctx"], d.resume["n"]
    me = _cards(plan, ctx, "self")
    if chosen[0] == "counters" and me:
        plan.do({"type": "counter", "card_ids": me, "kind": "+1/+1", "delta": n}, actor=d.player)
    else:
        create_token(plan, ctx, {"who": "you", "n": n, "token": SERVO})
    continue_effects(plan, ctx)


def storm(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Put N copies of the spell on the stack; for a targeted spell its controller may choose
    new targets (asked once: keep the target for all, or choose for each copy)."""
    sid = e["spell"]
    entry = plan.rules.stack.get(sid)
    card = plan.state.cards.get(sid)
    if entry is None or card is None or card.zone != "stack" or plan.oid(sid) != e["object"]:
        plan.note("Storm: the spell is gone (or handled by hand), so there is nothing to copy")
        return True
    if entry.target_spec and entry.targets:
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"Storm: {e['n']} cop{'y' if e['n'] == 1 else 'ies'} of {entry.name}",
               options=[DecisionOption(id="same", label="Same target for every copy"),
                        DecisionOption(id="choose", label="Choose a target for each copy")],
               resume={"step": "storm", "ctx": ctx, "spell": sid, "left": e["n"], "mode": None})
        return False
    for _ in range(e["n"]):
        _copy_spell(plan, sid, entry, entry.targets, ctx["controller"])
    return True


def _copy_spell(plan: Plan, sid: str, entry: StackEntry, targets: list[Any], controller: str) -> None:
    created = plan.do({"type": "create_ability", "text": f"Copy of {entry.name}"[:500], "source_id": sid, "kind": "other"},
                      actor=controller)
    new_ids = getattr(created, "r", None)
    copy_id = new_ids.ids[0] if new_ids is not None else None
    if copy_id:
        slots = [list(s) for s in entry.slots]
        if entry.slot_specs and list(targets) != list(entry.targets):  # a new target for a modal copy's only targeted mode
            targeted = [k for k, spec in enumerate(entry.slot_specs) if spec]
            if len(targeted) == 1:
                slots[targeted[0]] = list(targets)
        plan.rules.stack[copy_id] = StackEntry(kind="spell", controller=controller, source_card=entry.source_card,
                                               source_object=entry.source_object, name=f"Copy of {entry.name}",
                                               effects=list(entry.effects), targets=list(targets),
                                               target_spec=entry.target_spec, x=entry.x,
                                               modes=list(entry.modes), slots=slots,  # 700.2g: the copy keeps its modes
                                               slot_specs=list(entry.slot_specs))


def resume_storm(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.targets import legal_targets, ref, source_of

    r = d.resume
    entry = plan.rules.stack.get(r["spell"])
    ctx = r["ctx"]
    if entry is None:
        continue_effects(plan, ctx)
        return
    left = r["left"]
    if r["mode"] is None and chosen[0] == "same":
        for _ in range(left):
            _copy_spell(plan, r["spell"], entry, entry.targets, d.player)
        continue_effects(plan, ctx)
        return
    if r["mode"] == "choose":  # a target for this copy was chosen
        _copy_spell(plan, r["spell"], entry, [ref(plan, chosen[0])], d.player)
        left -= 1
    if left <= 0:
        continue_effects(plan, ctx)
        return
    spec = entry.target_spec or next((sp for sp in entry.slot_specs if sp), None) or {}
    if len([sp for sp in entry.slot_specs if sp]) > 1:  # several targeted modes: the copies keep their targets
        for _ in range(left):
            _copy_spell(plan, r["spell"], entry, entry.targets, d.player)
        continue_effects(plan, ctx)
        return
    legal = legal_targets(plan, spec.get("what", "any"), d.player, source_of(plan, entry.source_card))
    if not legal:
        continue_effects(plan, ctx)
        return
    from app.rules.targets import label as target_label

    decide(plan, player=d.player, kind="choose_one", prompt=f"Target for a copy of {entry.name} ({left} left)",
           options=[DecisionOption(id=x, label=target_label(plan, x), card_id=x if x in plan.state.cards else None) for x in legal],
           resume={**r, "left": left, "mode": "choose"})


def no_regen(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    return True  # read by destroy / destroy_all of the same spell or ability


def destroy_all(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """All at once: one move, one event batch (their dies triggers see each other leave)."""
    doomed = []
    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or not plan.in_game(c):
            continue
        ch = plan.ch(c)
        wanted = e["types"]
        hit = (not ch.is_land) if wanted == ["*nonland"] else bool(ch.types & set(wanted))
        if hit and "indestructible" not in ch.keywords:
            doomed.append(c.id)
    doomed = regeneration.survivors(plan, doomed, can_regenerate=_can_regenerate(ctx))
    if doomed:
        plan.do({"type": "move", "card_ids": doomed, "to": {"zone": "graveyard"}}, actor=ctx["controller"])
    return True


def blink(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Exile, then return under its owner's control: a new object (400.7), so it enters again."""
    from app.rules import attachments  # attachments → effects (resume)

    entries = []
    for cid in _cards(plan, ctx, e["who"]):
        owner = plan.state.cards[cid].owner
        back = ctx["controller"] if e.get("under") == "you" else owner
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": owner, "zone": "exile"}}, actor=ctx["controller"])
        if cid in plan.state.cards:  # (a token ceases to exist in exile)
            entries.append({"card": cid, "player": back, "actor": ctx["controller"]})
    return attachments.enter(plan, entries, ctx)


def _matches(plan: Plan, card_id: str, what: str) -> bool:
    from app.rules import characteristics as chars

    ch = chars.of(plan.state.cards[card_id], plan.info)
    if what.startswith("type:"):  # typecycling: "Swampcycling" finds a Swamp card, "Wizardcycling" a Wizard
        t = what[5:]
        return t in ch.subtypes or t in ch.types or t in ch.supertypes
    return {"any": True, "basic_land": ch.is_land and "Basic" in ch.supertypes, "land": ch.is_land,
            "creature": ch.is_creature, "artifact": "Artifact" in ch.types, "enchantment": "Enchantment" in ch.types,
            "instant_or_sorcery": ch.is_instant_or_sorcery}[what]


def search(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """A tutor. The server filters the library; only the searching player gets the matching cards
    in their private decision (nobody else learns the library's contents)."""
    pid = ctx["controller"]
    library = plan.state.zones.get(zone_key(pid, "library"), [])
    matching = [c for c in library if _matches(plan, c, e["filter"])]
    options = [DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in matching]
    decide(plan, player=pid, kind="choose_cards", prompt=f"Search your library ({e['filter'].replace('_', ' ')})",
           options=options, min_choices=0, max_choices=min(1, len(options)), resume={"step": "search", "ctx": ctx, "e": e})
    return False


def resume_search(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    from app.rules import attachments  # attachments → effects (resume)

    pid = d.player
    entering = []
    for cid in chosen:
        if e.get("reveal"):
            plan.do({"type": "reveal", "card_ids": [cid]}, actor=pid)  # to everyone
        if e["to"] == "hand":
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": pid, "zone": "hand"}}, actor=pid)
        else:
            entering.append({"card": cid, "player": pid, "actor": pid, "tapped": e["to"] == "battlefield_tapped"})
    if entering and not attachments.enter(plan, entering, ctx, shuffle=pid):  # an Aura chooses what it enchants (303.4f)
        return
    plan.do({"type": "shuffle", "player": pid, "zone": "library"}, actor=pid)
    continue_effects(plan, ctx)


def monarch(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    for pid in _players(plan, ctx, e["who"]):
        if plan.state.table.monarch != pid:
            plan.do({"type": "set_monarch", "player": pid}, actor=pid)
    return True


def discard(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    pid = ctx["controller"]
    hand = plan.state.zones.get(zone_key(pid, "hand"), [])
    n = min(e["n"], len(hand))
    if n == 0:
        return True
    if n == len(hand):
        plan.do({"type": "move", "card_ids": list(hand), "to": {"player": pid, "zone": "graveyard"}}, actor=pid)
        return True
    decide(plan, player=pid, kind="choose_cards", prompt=f"Discard {n} card{'s' if n != 1 else ''}",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in hand],
           min_choices=n, max_choices=n, resume={"step": "discard", "ctx": ctx})
    return False


def resume_discard(plan: Plan, d: Any, chosen: list[str]) -> None:
    plan.do({"type": "move", "card_ids": chosen, "to": {"player": d.player, "zone": "graveyard"}}, actor=d.player)
    continue_effects(plan, d.resume["ctx"])


def pay_or_sacrifice(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Sacrifice ~ unless you pay {cost}" (and echo, 702.30): its controller chooses; paying is
    offered only when they can."""
    from app.rules import mana  # casting imports this module

    src = _cards(plan, ctx, "self")
    if not src:
        return True  # it already left: nothing to sacrifice
    pid = ctx["controller"]
    cost = mana.parse_cost(e["cost"])
    if e.get("per"):  # cumulative upkeep: the cost once for each age counter
        n = plan.state.cards[src[0]].counters.get(e["per"], 0)
        cost = mana.parse_cost(e["cost"] * n) if n else mana.parse_cost("{0}")
    e = {**e, "cost": cost.text() if not cost.is_free else "{0}"}
    options = [DecisionOption(id="pay", label=f"Pay {cost.text()}"),  # (tap your mana first, then Pay)
               DecisionOption(id="sacrifice", label=f"Sacrifice {plan.state.cards[src[0]].name}")]
    decide(plan, player=pid, kind="choose_one", prompt=f"{ctx.get('name', '')}: pay {cost.text()} or sacrifice it?",
           options=options, resume={"step": "pay_or_sacrifice", "ctx": ctx, "cost": e["cost"]}, source=plan.state.cards[src[0]])
    return False


def resume_pay_or_sacrifice(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import casting, mana  # casting imports this module

    ctx = d.resume["ctx"]
    if d.resume.get("counter"):  # "… unless its controller pays" / ward
        sid = d.resume["counter"]
        if chosen[0] == "pay":
            cost = mana.parse_cost(d.resume["cost"])
            casting.pay_from_pool(plan, d.player, cost, f"paid {cost.text()} so it isn't countered")
        else:
            counter_object(plan, sid, d.player)
        continue_effects(plan, ctx)
        return
    src = _cards(plan, ctx, "self")
    if chosen[0] == "pay" and src:
        cost = mana.parse_cost(d.resume["cost"])
        casting.pay_from_pool(plan, d.player, cost, f"paid {cost.text()} for {ctx.get('name', '')}")
    elif src:
        card = plan.state.cards[src[0]]
        plan.do({"type": "move", "card_ids": src, "to": {"player": card.owner, "zone": "graveyard"}}, actor=d.player)
    continue_effects(plan, ctx)


def attach_self(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Equip (702.6a): attach this Equipment to the target creature. Nothing happens if the
    Equipment left or stopped being an Equipment, is a creature (301.5c), or is already attached
    there (701.3b)."""
    from app.rules import attachments  # attachments → effects (resume)

    src = _cards(plan, ctx, "self")
    targets = _cards(plan, ctx, "target")
    if src and targets:
        attachments.attach(plan, src[0], targets[0], ctx["controller"])  # doesn't move if it can't (701.3b)
    return True


def use_targets(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """A modal spell's next mode: its own target slot (empty if that target became illegal: the
    mode's targeted parts then do nothing, 608.2b)."""
    slots = ctx.get("slots") or []
    ctx["targets"] = slots[e["slot"]] if e["slot"] < len(slots) else []
    return True


PRIMITIVES = {
    "use_targets": use_targets,
    "attach_self": attach_self,
    "draw": draw, "gain_life": gain_life, "lose_life": lose_life, "damage": damage, "pump": pump, "grant": grant,
    "destroy": destroy, "exile": exile, "bounce": bounce, "tap": tap, "untap": untap, "scry": scry, "surveil": surveil,
    "player_counter": player_counter, "create_token": create_token, "add_counters": add_counters,
    "proliferate": proliferate, "destroy_all": destroy_all, "blink": blink, "search": search, "monarch": monarch,
    "discard": discard, "regenerate": regenerate, "no_regen": no_regen,
    "animate": animate, "pay_or_sacrifice": pay_or_sacrifice, "renown": renown, "return_yours": return_yours, "suspend_tick": suspend_tick, "cascade": cascade, "unearth": unearth, "delayed_move": delayed_move,
    "madness_offer": madness_offer, "free_cast_offer": free_cast_offer, "counter": counter, "counter_unless": counter_unless,
    "sacrifice": sacrifice, "explore": explore, "prevent": prevent, "mill": mill,
    "return_with_counter": return_with_counter, "exile_until": exile_until, "return_linked": return_linked,
    "fabricate": fabricate, "storm": storm,
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
    if entry.slot_specs:  # a modal spell: each mode's target is checked on its own (608.2b)
        src = source_of(plan, entry.source_card)
        slots, targeted, legal_any = [], False, False
        for refs, sspec in zip(entry.slots, entry.slot_specs, strict=False):
            ok = [t for t in refs if sspec and still_legal(plan, sspec["what"], entry.controller, t, src)]
            targeted = targeted or bool(sspec and refs)
            legal_any = legal_any or bool(ok)
            slots.append([t.model_dump() for t in ok])
        if targeted and not legal_any:
            plan.note(f"{entry.name or 'It'} does nothing: its targets are no longer legal")
            finish(plan, ctx, countered=True)
            return
        ctx["slots"] = slots
        ctx["targets"] = []
    spec = entry.target_spec
    if spec and entry.targets:
        src = source_of(plan, entry.source_card)
        legal = [t for t in entry.targets if still_legal(plan, spec["what"], entry.controller, t, src)]
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
        from app.rules.engine import leave_stack  # engine imports this module

        leave_stack(plan, stack_id, ctx["controller"], countered=countered)
    _after_resolution(plan)


def describe(effects: list[dict[str, Any]]) -> str:
    words = {"draw": "draw {n} card(s)", "gain_life": "gain {n} life", "lose_life": "lose {n} life", "scry": "scry {n}",
             "surveil": "surveil {n}", "damage": "deal {n} damage", "player_counter": "get {n} {counter}",
             "create_token": "create {n} token(s)", "add_counters": "put {n} {kind} counter(s)", "proliferate": "proliferate",
             "monarch": "become the monarch", "discard": "discard {n}", "search": "search your library"}
    parts = [words.get(e["do"], e["do"]).format(**{k: v for k, v in e.items()}) for e in effects]
    return (", ".join(parts) or "do it").capitalize()
