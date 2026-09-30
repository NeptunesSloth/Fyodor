"""Effect primitives and the resolver for declarative definitions (``app.rules.scripts``).

Each primitive carries out one kind of instruction with ordinary table actions (so undo, replay
and the log work as everywhere else). The resolver runs a definition's effects in order
(608.2c); a primitive that needs a player's choice (scry, surveil) opens a decision and the
resolver continues from there when it is answered.

Primitives today: draw, gain_life, lose_life, damage (noncombat, as damage events; lifelink and
deathtouch apply), pump / grant (continuous effects until end of turn, layer 7c / 6), destroy
(indestructible respected), exile, bounce, tap, untap, scry, surveil, player_counter.

A primitive given a binding name by the grammar (``"as": "e0"``) records the objects it acted on
in the resolution context (``_remember`` before it changes them, ``_moved`` after it moved them:
app/rules/context.py), so a later instruction of the same resolution can name them — "its
controller", "its toughness" (608.2h: as they were), "return it" (400.7j: where it went).
"""

from __future__ import annotations

from typing import Any

from app.game.rules_state import DecisionOption, ObjectRef, StackEntry
from app.game.state import zone_key
from app.rules import (
    context,
    delayed,
    layers,
    optional_payment,
    permissions,
    protection,
    regeneration,
    replacements,
    selectors,
    values,
)
from app.rules.plan import Plan, decide
from app.rules.targets import source_of, still_legal

Context = dict[str, Any]  # {"controller", "source_card", "source_object", "name", "targets": [...], "stack_id", "kind"}


def _amount(plan: Plan, ctx: Context, n: Any) -> int:
    """An effect's number: a literal or a value expression (app/rules/values.py)."""
    return values.evaluate(plan, ctx, n)


def target_refs(ctx: Context, who: str) -> list[dict[str, Any]]:
    """The still-legal targets an effect names: "target" (the spell's or ability's target, or its
    first target group) or "target:<g>" (group g). Illegal ones were dropped on resolution
    (608.2b: they aren't affected)."""
    if who == "target":
        return list(ctx.get("targets") or [])
    if not who.startswith("target:"):
        return []
    g = int(who[7:])
    groups = ctx.get("groups") or []
    return [t for t in groups[g] if t] if g < len(groups) else []


def divided(ctx: Context, e: dict[str, Any]) -> dict[str, int] | None:
    """601.2d / 115.7f: "divided as you choose": each legal target's share of a divided group (by
    player or card id), as announced when it was put on the stack; an illegal target's share
    isn't dealt to anyone else. None if the effect's amount isn't divided."""
    n = e.get("n")
    if not isinstance(n, dict) or "divided" not in n:
        return None
    g = n["divided"]
    groups, division = ctx.get("groups") or [], ctx.get("division") or []
    if g >= len(groups) or g >= len(division):
        return {}
    return {t["id"]: amount for t, amount in zip(groups[g], division[g], strict=False) if t}


def _players(plan: Plan, ctx: Context, who: str) -> list[str]:
    me = ctx["controller"]
    if who.startswith(selectors.PREFIX):  # "each opponent", "each player" … as a selector
        sel = selectors.from_key(who)
        return [p for p in plan.live() if selectors.matches_player(plan, sel, p, me)] if sel.player else []
    if who == "you":
        return [me]
    if who == "each_player":
        return list(plan.live())
    if who == "each_opponent":
        return [p for p in plan.live() if p != me]
    if who == "target" or who.startswith("target:"):
        return [t["id"] for t in target_refs(ctx, who) if t["id"] in plan.state.players and t["id"] in plan.live()]
    if who == "event_player":  # "that player": the one the trigger event was about (who drew, was dealt damage …)
        return context.players(plan, ctx, context.EVENT)
    if who.startswith(context.PREFIX):  # a binding: "that player", "its controller", "its owner" (app/rules/context.py)
        return context.players(plan, ctx, who[len(context.PREFIX):])
    if who.startswith("player:"):  # (older saves: a player bound into the effect when it triggered)
        return [who[7:]] if who[7:] in plan.live() else []
    return []


def _cards(plan: Plan, ctx: Context, who: str) -> list[str]:
    if who.startswith(selectors.PREFIX):  # "each creature you control", "all other Goblins" …
        sel = selectors.from_key(who)
        return [] if sel.player else selectors.candidates(plan, sel, ctx["controller"], ctx.get("source_card"))
    if who == "target" or who.startswith("target:"):
        return [t["id"] for t in target_refs(ctx, who) if t["id"] in plan.state.cards
                and plan.oid(t["id"]) == t.get("object_id")]
    if who == "self":
        src = plan.state.cards.get(ctx.get("source_card") or "")
        if src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == ctx.get("source_object"):
            return [src.id]
        return []  # the source left: "it" is gone (a new object isn't affected)
    if who == "host":  # "enchanted creature" / "equipped creature": what the source is attached to now
        src = plan.state.cards.get(ctx.get("source_card") or "")
        host = plan.state.cards.get(src.attached_to or "") if src is not None and src.zone.endswith(":battlefield") else None
        return [host.id] if host is not None and host.zone.endswith(":battlefield") else []
    if who == "event":  # "it" / "that creature": the object(s) the trigger event happened to — only while
        # each is still that object where it was (400.7: after a zone change it's a new object)
        return context.objects(plan, ctx, context.EVENT)
    if who == context.EVENT_NEW:  # after "dies" / "leaves": the new object where it went — only while
        # it's still there (400.7e, 603.6c)
        return context.objects(plan, ctx, context.EVENT_NEW)
    if who.startswith(context.PREFIX):  # an earlier effect's objects ("it", "cards exiled this way")
        return context.objects(plan, ctx, who[len(context.PREFIX):])
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


# -- within-resolution references (app/rules/context.py) ---------------------------------------
def _remember(plan: Plan, ctx: Context, e: dict[str, Any], cards: list[str]) -> list[ObjectRef]:
    """Record the objects an effect is about to act on as its binding ("as": given by the grammar
    when a later instruction refers back to them: "its controller", "it", "cards exiled this
    way"). Recorded BEFORE the effect changes them, so the binding knows the objects as they were
    (608.2h: last known information once they leave). Returns the refs for ``_moved``."""
    name = e.get("as")
    if not name:
        return []
    context.bind_objects(plan, ctx, name, cards)
    return [r for r in (context.ref_of(plan, c) for c in cards) if r is not None]


def _moved(plan: Plan, ctx: Context, e: dict[str, Any], before: list[ObjectRef]) -> None:
    """AFTER an effect moved its objects: rebind to what each became where it went (400.7j: a
    later instruction can find it in a public zone; 111.8 / 111.7: a token that left has ceased to
    exist and is found nowhere), keeping what it was for information about it (608.2h)."""
    if e.get("as"):
        context.bind_moved(plan, ctx, e["as"], before)


def draw(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    want = _amount(plan, ctx, e["n"])
    for pid in _players(plan, ctx, e["who"]):
        library = plan.state.zones.get(zone_key(pid, "library"), [])
        n = min(want, len(library))
        if n:
            plan.do({"type": "draw", "player": pid, "count": n}, actor=pid)
        if n < want and pid not in plan.rules.drew_from_empty:
            plan.rules.drew_from_empty.append(pid)  # 704.5b at the next check
    return True


def gain_life(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    n = _amount(plan, ctx, e["n"])
    for pid in _players(plan, ctx, e["who"]):
        if n:
            plan.do({"type": "life", "player": pid, "delta": n}, actor=ctx["controller"])
    return True


def lose_life(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    n = _amount(plan, ctx, e["n"])
    for pid in _players(plan, ctx, e["who"]):
        if n:
            plan.do({"type": "life", "player": pid, "delta": -n}, actor=ctx["controller"])
    return True


def damage(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Noncombat damage from the source (120.3): life loss for players, marked damage for
    creatures, loyalty loss for planeswalkers; lifelink and deathtouch of the source apply."""
    shares = divided(ctx, e)  # 601.2d: each target's share, as divided when it was put on the stack
    n = 0 if shares is not None else _amount(plan, ctx, e["n"])

    def amount(key: str) -> int:
        return shares.get(key, 0) if shares is not None else n
    players = _players(plan, ctx, e["who"])
    cards = _cards(plan, ctx, e["who"])
    _remember(plan, ctx, e, cards)
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
    # prevention effects (615: "prevent all …" in force, then "prevent the next N" shields) on this
    # one simultaneous damage event — app/rules/replacements.py
    source_oid = ctx.get("source_object") or ""
    events = [{"source_card": source.id if source is not None else None, "source_oid": source_oid, "target": cid,
               "amount": amount(cid), "combat": False}
              for cid in cards if not protection.protected_from(plan.ch(plan.state.cards[cid]), src_ch)]
    events += [{"source_card": source.id if source is not None else None, "source_oid": source_oid, "target": pid,
                "amount": amount(pid), "combat": False} for pid in players]
    after = replacements.apply_prevention(plan, events) or []
    left = {ev["target"]: ev["amount"] - ev["prevented"] for ev in after}
    for cid in cards:
        card = plan.state.cards[cid]
        ch = plan.ch(card)
        if protection.protected_from(ch, src_ch):  # 702.16e: the damage is prevented
            plan.note(f"Protection prevents the damage to {ch.name}", [cid], actor=ctx["controller"])
            continue
        per[cid] = left.get(cid, 0)
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
    to_players = {pid: left.get(pid, 0) for pid in players}
    players = [pid for pid, m in to_players.items() if m > 0]
    for pid in players:
        dealt.append({"source": ctx.get("source_object") or "", "target": pid, "amount": to_players[pid]})
    if not dealt or (shares is None and n <= 0):
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
    cards = _cards(plan, ctx, e["who"])
    _remember(plan, ctx, e, cards)
    affected = [plan.oid(c) for c in cards]  # locked in now (611.2c)
    if affected:
        layers.add_effect(plan, affected=affected, layer="7c", source=ctx.get("source_object"), controller=ctx["controller"],
                          power=e["p"], toughness=e["t"], label=f"{e['p']:+d}/{e['t']:+d} until end of turn ({ctx.get('name', '')})")
        _mark(plan, _cards(plan, ctx, e["who"]), f"{e['p']:+d}/{e['t']:+d}")
    return True


def grant(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    cards = _cards(plan, ctx, e["who"])
    _remember(plan, ctx, e, cards)
    if cards:
        layers.add_effect(plan, affected=[plan.oid(c) for c in cards], layer="6", source=ctx.get("source_object"),
                          controller=ctx["controller"], add_keywords=tuple(e["keywords"]),
                          label=f"{', '.join(e['keywords'])} until end of turn")
        _mark(plan, cards, ", ".join(k.capitalize() for k in e["keywords"]))
    return True


RESTRICTION_LABELS = {"cant_block": "Can't block", "cant_attack": "Can't attack", "cant_attack_or_block": "Can't attack or block",
                      "cant_be_blocked": "Can't be blocked", "must_attack": "Attacks if able"}


_GROUPS = {"each_creature": selectors.Selector(types=("Creature",)).key(),
           "creatures_you_control": selectors.Selector(types=("Creature",), controller="you").key()}


def restrict(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"… can't block this turn", "… can't be blocked this turn": a rule-modifying effect, ending
    at cleanup (514.2). It doesn't change characteristics or control, so its set of objects isn't
    locked in (611.2c): "Creatures can't block this turn" also stops a creature that enters later.
    A named object (target, "it", self, host) stays that one object (a new object isn't it, 400.7)."""
    who = _GROUPS.get(e["who"], e["who"])
    cards = _cards(plan, ctx, who)
    _remember(plan, ctx, e, cards)
    group = who.startswith(selectors.PREFIX)
    if cards or group:
        layers.add_effect(plan, affected=[] if group else [plan.oid(c) for c in cards], layer="6",
                          source=ctx.get("source_object"), controller=ctx["controller"], imposes=tuple(e["rules"]),
                          label=", ".join(e["rules"]), who=who if group else None, source_card=ctx.get("source_card"))
    if cards:
        _mark(plan, cards, ", ".join(RESTRICTION_LABELS.get(r, r) for r in e["rules"]))
    return True


def _mark(plan: Plan, cards: list[str], label: str) -> None:
    """The visible table marker for an engine effect (it goes away at cleanup with the effect)."""
    for cid in cards:
        plan.do({"type": "add_effect", "card_ids": [cid], "name": label, "value": label, "text": "until end of turn"})


def _can_regenerate(ctx: Context) -> bool:
    """False when the spell or ability says "It/They can't be regenerated"."""
    return not any(x.get("do") == "no_regen" for x in ctx.get("effects") or [])


def destroy(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    # The binding is every object the instruction was about ("Destroy target creature. Its
    # controller …" means the target's controller even if it was indestructible or regenerated)
    before = _remember(plan, ctx, e, _cards(plan, ctx, e["who"]))
    doomed = [c for c in _cards(plan, ctx, e["who"]) if "indestructible" not in plan.ch(plan.state.cards[c]).keywords]
    doomed = regeneration.survivors(plan, doomed, can_regenerate=_can_regenerate(ctx))
    if doomed:
        plan.do({"type": "move", "card_ids": doomed, "to": {"zone": "graveyard"}}, actor=ctx["controller"])
    _moved(plan, ctx, e, before)
    return True


def exile(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    cards = _cards(plan, ctx, e["who"])
    before = _remember(plan, ctx, e, cards)
    if cards:
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "exile"}}, actor=ctx["controller"])
    _moved(plan, ctx, e, before)
    return True


def bounce(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Return to the owner's hand: all of them at once, one move and one event batch (a "one or
    more" trigger fires once, 603.2c). The zone "hand" goes to each card's owner."""
    cards = _cards(plan, ctx, e["who"])
    before = _remember(plan, ctx, e, cards)
    if cards:
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "hand"}}, actor=ctx["controller"])
    _moved(plan, ctx, e, before)  # (a hidden zone: only what they were is kept, 608.2h)
    return True


def tap(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    _remember(plan, ctx, e, _cards(plan, ctx, e["who"]))
    cards = [c for c in _cards(plan, ctx, e["who"]) if not plan.state.cards[c].tapped]
    if cards:
        plan.do({"type": "tap", "card_ids": cards, "tapped": True}, actor=ctx["controller"])
    return True


def untap(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    _remember(plan, ctx, e, _cards(plan, ctx, e["who"]))
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
    top = plan.state.zones.get(zone_key(pid, "library"), [])[: _amount(plan, ctx, e["n"])]
    if not top:
        return True
    options = [DecisionOption(id=cid, label=plan.state.cards[cid].name or "Card", card_id=cid) for cid in top]
    verb = "Scry" if where == "bottom" else "Surveil"
    dest = "the bottom of your library" if where == "bottom" else "your graveyard"
    decide(plan, player=pid, kind="choose_cards", prompt=f"{verb} {len(top)}: choose the cards to put into {dest} (the rest stay on top)",
           options=options, min_choices=0, max_choices=len(top),
           resume={"step": "look", "where": where, "cards": list(top), "ctx": ctx})
    return False


def create_token(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """111: tokens are individual objects for the rules; identical ones may be *shown* as a pile."""
    t = e["token"]
    count = _amount(plan, ctx, e["n"])
    if count <= 0:
        _remember(plan, ctx, e, [])
        return True
    made: list[str] = []
    for pid in _players(plan, ctx, e["who"]):
        spec = {"name": t["name"], "power": t.get("power"), "toughness": t.get("toughness"),
                "colors": t.get("colors") or [], "type_line": t["type_line"], "text": t.get("text") or ""}
        # a token enters tapped when its creator says so ("create a tapped …") or its own text does
        # (614.1d), never otherwise; its "enters with" counters follow (app/rules/replacements.py)
        tapped = bool(e.get("tapped")) or replacements.token_enters_tapped(plan, pid, spec)
        created = plan.do({"type": "create_token", "player": pid, "count": count, "stacked": False, "tapped": tapped,
                           "source_id": ctx.get("source_card") if ctx.get("source_card") in plan.state.cards else None,
                           "token": spec}, actor=pid)
        new_ids = getattr(created, "r", None)
        fresh = list(new_ids.ids) if new_ids is not None else []
        for tid in fresh:
            replacements.after_entry(plan, tid, pid)
        made += fresh
    _remember(plan, ctx, e, made)  # the tokens, as the new objects they are ("they gain haste")
    return True


def add_counters(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    cards = _cards(plan, ctx, e["who"])
    _remember(plan, ctx, e, cards)
    shares = divided(ctx, e)
    if shares is not None:  # "distribute N counters among …" (601.2d): each target its share
        for cid in cards:
            if shares.get(cid):
                plan.do({"type": "counter", "card_ids": [cid], "kind": e["kind"], "delta": shares[cid]}, actor=ctx["controller"])
        return True
    n = _amount(plan, ctx, e["n"])
    if cards and n:
        plan.do({"type": "counter", "card_ids": cards, "kind": e["kind"], "delta": n}, actor=ctx["controller"])
    return True


def remove_counters(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Remove N … counters from …" (as many as there are, 122.8)."""
    n = _amount(plan, ctx, e["n"])
    cards = _cards(plan, ctx, e["who"])
    _remember(plan, ctx, e, cards)
    for cid in cards:
        have = plan.state.cards[cid].counters.get(e["kind"], 0)
        if have and n:
            plan.do({"type": "counter", "card_ids": [cid], "kind": e["kind"], "delta": -min(have, n)}, actor=ctx["controller"])
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
    cards = _cards(plan, ctx, e["who"])
    _remember(plan, ctx, e, cards)
    for cid in cards:
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
    from app.rules import attachments  # attachments → effects (resume)

    # It enters through the one entry path (its "enters" replacements apply: 614.1c-d); haste,
    # "exile it at the next end step" and "if it would leave, exile it instead" (702.84a) follow.
    return attachments.enter(plan, [{"card": cid, "player": card.owner, "actor": ctx["controller"], "gain_haste": "unearth",
                                     "exile_if_leaves": True, "delayed": "exile"}], ctx)


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
    return [t["id"] for t in target_refs(ctx, e.get("who") or "target") if t["id"] in plan.state.cards
            and plan.state.cards[t["id"]].zone == "stack" and plan.oid(t["id"]) == t.get("object_id")]


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
    _sacrifice_cards(plan, _cards(plan, ctx, e["who"]), ctx["controller"], ctx, e.get("as"))
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


def mill(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    want = _amount(plan, ctx, e["n"])
    before: list[ObjectRef] = []
    for pid in _players(plan, ctx, e["who"]):
        library = plan.state.zones.get(zone_key(pid, "library"), [])
        n = min(want, len(library))
        before += [r for r in (context.ref_of(plan, c) for c in library[:n]) if r is not None]
        if n:
            plan.do({"type": "mill", "player": pid, "count": n}, actor=pid)
    _moved(plan, ctx, e, before)  # "cards milled this way": the new objects in the graveyards (400.7j)
    return True


def return_with_counter(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Persist / undying: "return it to the battlefield under its owner's control with a … counter on it"."""
    cid = ctx.get("source_card") or ""
    card = plan.state.cards.get(cid)
    if card is None or not card.zone.endswith(":graveyard"):
        return True  # it's gone (a token ceased to exist, or it left the graveyard)
    from app.rules import attachments  # attachments → effects (resume)

    # the one entry path: it enters with the counter (122.6) and its own "enters" replacements
    return attachments.enter(plan, [{"card": cid, "player": card.owner, "actor": card.owner, "counter": e["counter"]}], ctx)


def exile_until(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """610.3c: "exile … until ~ leaves the battlefield" — if the source already left, nothing happens."""
    src = _cards(plan, ctx, "self")
    if not src:
        _remember(plan, ctx, e, [])
        return True
    cards = _cards(plan, ctx, e["who"])
    before = _remember(plan, ctx, e, cards)
    if cards:
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "exile"}}, actor=ctx["controller"])
        key = ctx["source_object"]
        plan.rules.linked_exile[key] = [*plan.rules.linked_exile.get(key, []), *cards]
    _moved(plan, ctx, e, before)
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
                                               slot_specs=list(entry.slot_specs),
                                               # a copy has the original's targets and division (707.10)
                                               groups=[list(g) for g in entry.groups], group_specs=list(entry.group_specs),
                                               division=[list(d) for d in entry.division],
                                               kicked=entry.kicked)  # 707.10: and whether it was kicked


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
    before = _remember(plan, ctx, e, doomed)  # "creatures destroyed this way": the ones it destroys
    if doomed:
        plan.do({"type": "move", "card_ids": doomed, "to": {"zone": "graveyard"}}, actor=ctx["controller"])
    _moved(plan, ctx, e, before)
    return True


def blink(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Exile, then return under its owner's control: a new object (400.7), so it enters again."""
    from app.rules import attachments  # attachments → effects (resume)

    entries = []
    cards = _cards(plan, ctx, e["who"])
    before = _remember(plan, ctx, e, cards)
    for cid in cards:
        owner = plan.state.cards[cid].owner
        back = ctx["controller"] if e.get("under") == "you" else owner
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": owner, "zone": "exile"}}, actor=ctx["controller"])
        if cid in plan.state.cards:  # (a token ceases to exist in exile: 111.7, and can't come back, 111.8)
            entries.append({"card": cid, "player": back, "actor": ctx["controller"]})
    done = attachments.enter(plan, entries, ctx)
    if done:  # (an Aura choosing what it enchants pauses: the binding then keeps what they were)
        _moved(plan, ctx, e, before)  # the permanents they became: new objects (400.7)
    return done


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
    if e.get("sel"):  # a structured card selector (app/rules/selectors.py)
        from app.rules import characteristics as chars

        sel = selectors.from_key(e["sel"])
        matching = [c for c in library if selectors.matches(plan, sel, plan.state.cards[c],
                                                             chars.of(plan.state.cards[c], plan.info), pid)]
        what = e.get("label") or "cards"
    else:
        matching = [c for c in library if _matches(plan, c, e["filter"])]
        what = e["filter"].replace("_", " ")
    most = _amount(plan, ctx, e.get("max", 1))
    options = [DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in matching]
    # 701.23b: a search for cards with a stated quality may find fewer (or none); 701.23d: a search
    # simply for a quantity of cards ("a card") must find that many, or as many as there are.
    # ("Up to N cards" may find fewer: only a single "a card" or an explicit ``upto: False`` forces.)
    quantity_only = e.get("filter") == "any" or (e.get("sel") is not None and e.get("label") in ("card", "cards"))
    forced = quantity_only and not e.get("upto", e.get("label") == "cards")
    decide(plan, player=pid, kind="choose_cards", prompt=f"Search your library ({what})",
           options=options, min_choices=min(most, len(options)) if forced else 0, max_choices=min(most, len(options)),
           resume={"step": "search", "ctx": ctx, "e": e})
    return False


def resume_search(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    from app.rules import attachments  # attachments → effects (resume)

    pid = d.player
    entering = []
    found = _remember(plan, ctx, e, list(chosen))  # (library objects: a hidden zone, so nothing is read from them)
    for cid in chosen:
        if e.get("reveal"):
            plan.do({"type": "reveal", "card_ids": [cid]}, actor=pid)  # to everyone
        if e["to"] in ("hand", "graveyard", "exile"):
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": pid, "zone": e["to"]},
                     **({"face_down": True} if e.get("face_down") else {})}, actor=pid)
        elif e["to"] in ("battlefield", "battlefield_tapped"):
            entering.append({"card": cid, "player": pid, "actor": pid, "tapped": e["to"] == "battlefield_tapped"})
    if entering and not attachments.enter(plan, entering, ctx, shuffle=pid):  # an Aura chooses what it enchants (303.4f)
        return
    _moved(plan, ctx, e, found)  # the cards found, where they went (400.7j; a hand is hidden: nothing)
    before = list(plan.state.zones.get(zone_key(pid, "library"), []))
    shuffled = plan.do({"type": "shuffle", "player": pid, "zone": "library"}, actor=pid)
    if e["to"] == "top":  # "then shuffle and put that card on top": follow it through the shuffle's new ids
        r = getattr(shuffled, "r", None)
        for cid in chosen:
            if r is None or cid not in before:
                continue
            new_id = r.new_ids[r.perm.index(before.index(cid))]
            plan.do({"type": "move", "card_ids": [new_id], "to": {"player": pid, "zone": "library"}, "index": 0}, actor=pid)
    continue_effects(plan, ctx)


def monarch(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    for pid in _players(plan, ctx, e["who"]):
        if plan.state.table.monarch != pid:
            plan.do({"type": "set_monarch", "player": pid}, actor=pid)
    return True


def discard(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.9: each affected player discards N cards of their choice; each chooses privately from
    their own hand, in APNAP order, then all the cards are discarded at once (101.4): one move,
    one event batch."""
    who = _players(plan, ctx, e.get("who", "you")) if e.get("who") else [ctx["controller"]]
    order = [p for p in plan.apnap() if p in who]
    return _discard_next(plan, ctx, _amount(plan, ctx, e["n"]), order, [], e.get("as"))


def _discard_next(plan: Plan, ctx: Context, want: int, players: list[str], picked: list[str],
                  binding: str | None = None) -> bool:
    for i, pid in enumerate(players):
        hand = plan.state.zones.get(zone_key(pid, "hand"), [])
        n = min(want, len(hand))
        if n == 0:
            continue
        if n == len(hand):
            picked = [*picked, *hand]
            continue
        decide(plan, player=pid, kind="choose_cards", prompt=f"Discard {n} card{'s' if n != 1 else ''}",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in hand],
               min_choices=n, max_choices=n,
               resume={"step": "discard", "ctx": ctx, "want": want, "rest": players[i + 1:], "picked": picked,
                       "as": binding})
        return False
    cards = [c for c in picked if c in plan.state.cards and plan.state.cards[c].zone.endswith(":hand")]
    e = {"as": binding}
    before = _remember(plan, ctx, e, cards)
    if cards:  # each to its owner's graveyard (701.9a)
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "graveyard"}}, actor=ctx["controller"])
    _moved(plan, ctx, e, before)  # "cards discarded this way": found in the graveyards (400.7j)
    return True


def resume_discard(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx = d.resume["ctx"]
    picked = [*(d.resume.get("picked") or []), *chosen]
    if _discard_next(plan, ctx, d.resume.get("want", 0), d.resume.get("rest") or [], picked, d.resume.get("as")):
        continue_effects(plan, ctx)


def sacrifice_choice(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.21a: "[Players] sacrifice N [selector]": each affected player chooses permanents they
    control that match, in APNAP order; then they're all sacrificed at once (101.4)."""
    who = _players(plan, ctx, e["who"])
    order = [p for p in plan.apnap() if p in who]
    return _sacrifice_next(plan, ctx, e["sel"], _amount(plan, ctx, e["n"]), order, [], e.get("as"))


def _sacrifice_next(plan: Plan, ctx: Context, key: str, want: int, players: list[str], picked: list[str],
                    binding: str | None = None) -> bool:
    sel = selectors.from_key(key)
    for i, pid in enumerate(players):
        mine = [c for c in selectors.candidates(plan, sel, pid, ctx.get("source_card"))
                if plan.state.cards[c].controller == pid and plan.state.cards[c].zone.endswith(":battlefield")]
        n = min(want, len(mine))
        if n == 0:
            continue
        if n == len(mine):
            picked = [*picked, *mine]
            continue
        decide(plan, player=pid, kind="choose_cards", prompt=f"Sacrifice {n}",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Permanent", card_id=c) for c in mine],
               min_choices=n, max_choices=n,
               resume={"step": "sacrifice_choice", "ctx": ctx, "sel": key, "want": want, "rest": players[i + 1:],
                       "picked": picked, "as": binding})
        return False
    _sacrifice_cards(plan, picked, ctx["controller"], ctx, binding)
    return True


def _sacrifice_cards(plan: Plan, cards: list[str], actor: str, ctx: Context | None = None, binding: str | None = None) -> None:
    """701.21a: each to its owner's graveyard, all at once (one move, one event batch: a "one or
    more" trigger fires once, 603.2c). ``binding``: recorded for "its power" / "creatures
    sacrificed this way" — as they were (608.2h), and the cards they became (400.7j)."""
    cards = [c for c in cards if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")]
    e = {"as": binding}
    before = _remember(plan, ctx, e, cards) if ctx is not None else []
    if cards:
        from app.rules.triggers import sacrificing  # (triggers imports this module)

        sacrificing(plan, cards)
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "graveyard"}}, actor=actor)
    if ctx is not None:
        _moved(plan, ctx, e, before)


def resume_sacrifice_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    picked = [*(r.get("picked") or []), *chosen]
    if _sacrifice_next(plan, r["ctx"], r["sel"], r["want"], r.get("rest") or [], picked, r.get("as")):
        continue_effects(plan, r["ctx"])


def return_card(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Return cards (the target, or those matching) from a graveyard / exile to a hand or the
    battlefield: "to your hand", "to its owner's hand", "to the battlefield [tapped] [under your
    control]". A card that left its zone isn't there to return (a new object, 400.7)."""
    from app.rules import attachments  # attachments → effects (resume)

    # A pronoun ("return it …") names the card an earlier instruction of this effect put there
    # (400.7j); one that isn't there any more — or a token, which ceased to exist (111.7, 111.8)
    # — is nothing to return (603.7c's principle: not in the zone it's expected in).
    cards = [c for c in _cards(plan, ctx, e["who"]) if not plan.state.cards[c].zone.endswith(":battlefield")]
    before = _remember(plan, ctx, e, cards)
    if e["to"] == "hand":
        for cid in cards:
            card = plan.state.cards[cid]
            dest = ctx["controller"] if e.get("under") == "you" else card.owner
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": dest, "zone": "hand"}}, actor=ctx["controller"])
        _moved(plan, ctx, e, before)
        return True
    entries = [{"card": cid, "player": ctx["controller"] if e.get("under") == "you" else plan.state.cards[cid].owner,
                "actor": ctx["controller"], "tapped": bool(e.get("tapped"))} for cid in cards]
    done = attachments.enter(plan, entries, ctx)
    if done:  # (an Aura choosing what it enchants pauses: the binding then keeps what they were)
        _moved(plan, ctx, e, before)  # the permanents they became: new objects (400.7)
    return done


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
        from app.rules.triggers import sacrificing  # (triggers imports this module)

        card = plan.state.cards[src[0]]
        sacrificing(plan, src)
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
    "remove_counters": remove_counters, "restrict": restrict,
    "sacrifice_choice": sacrifice_choice, "return_card": return_card,
    "attach_self": attach_self,
    "draw": draw, "gain_life": gain_life, "lose_life": lose_life, "damage": damage, "pump": pump, "grant": grant,
    "destroy": destroy, "exile": exile, "bounce": bounce, "tap": tap, "untap": untap, "scry": scry, "surveil": surveil,
    "player_counter": player_counter, "create_token": create_token, "add_counters": add_counters,
    "proliferate": proliferate, "destroy_all": destroy_all, "blink": blink, "search": search, "monarch": monarch,
    "discard": discard, "regenerate": regenerate, "no_regen": no_regen,
    "animate": animate, "pay_or_sacrifice": pay_or_sacrifice, "renown": renown, "return_yours": return_yours, "suspend_tick": suspend_tick, "cascade": cascade, "unearth": unearth, "delayed_move": delayed_move,
    "madness_offer": madness_offer, "free_cast_offer": free_cast_offer, "counter": counter, "counter_unless": counter_unless,
    "sacrifice": sacrifice, "explore": explore, "prevent": prevent, "prevent_all": replacements.prevent_all, "mill": mill,
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
    """The chooser's order for cards going to the top / bottom of a library (401.4: a private
    choice; ``owner``: whose library, the chooser's unless given)."""
    r = d.resume
    pid = d.player
    owner = r.get("owner") or pid
    if r["place"] == "top":
        # The first chosen card goes on top: put them on top in reverse.
        for cid in reversed(chosen):
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": owner, "zone": "library"}, "position": "top"}, actor=pid)
    else:
        for cid in reversed(chosen):  # the first chosen ends at the very bottom
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": owner, "zone": "library"}, "position": "bottom"}, actor=pid)
    if r.get("then_bottom"):
        bottom = r["then_bottom"]
        decide(plan, player=pid, kind="order", prompt="Order the cards for the bottom of your library (first chosen ends up at the very bottom)",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in bottom],
               min_choices=len(bottom), max_choices=len(bottom),
               resume={"step": "order_library", "place": "bottom", "then_bottom": [], "ctx": r["ctx"]})
        return
    ctx = r["ctx"]
    queue = ctx.get("library_queue") or []
    if queue:  # to_library: the next owner orders their cards (401.4)
        nxt = queue.pop(0)
        _ask_order(plan, ctx, nxt["owner"], nxt["owner"], nxt["cards"], nxt["place"])
        return
    if ctx.get("library_e") is not None:
        _moved(plan, ctx, ctx.pop("library_e"), [ObjectRef.model_validate(x) for x in ctx.pop("library_before", [])])
        ctx.pop("library_queue", None)
    continue_effects(plan, ctx)


# -- looking at, revealing and moving the top of a library ----------------------------------
# The cards an instruction set aside from the top of a library live in the resolution context:
# ctx["looked"] (their ids, still in that library), ctx["looked_owner"] (whose library) and
# ctx["found"] (the card a "… until you reveal a …" instruction stopped at). "Look at" is private:
# only the looking player's decisions carry the cards (701.20e); "reveal" shows them to everyone
# (701.20a) until they move or the library is reordered (701.20d, ops.move_card clears reveals).
def _library_owner(plan: Plan, ctx: Context, e: dict[str, Any]) -> list[str]:
    """Whose library an instruction reads: "your library" (default), "target player's",
    "each player's" …"""
    return _players(plan, ctx, e.get("player") or "you")


def _library(plan: Plan, pid: str) -> list[str]:
    return plan.state.zones.get(zone_key(pid, "library"), [])


def _first_match(plan: Plan, ctx: Context, cards: list[str], key: str, pid: str) -> int | None:
    """The index of the first card matching a selector, or None."""
    from app.rules import characteristics as chars

    sel = selectors.from_key(key)
    for i, cid in enumerate(cards):
        card = plan.state.cards[cid]
        if selectors.matches(plan, sel, card, chars.of(card, plan.info), pid):
            return i
    return None


def look_top(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Look at the top N cards of your library": only you see them (the choices that follow are
    your private decisions); they stay where they are until an instruction moves them. With
    ``reveal``: "reveal the top N cards" — shown to everyone (701.20a). With ``until`` (a selector
    key): "reveal cards from the top of your library until you reveal a creature card" — the
    cards down to and including the first match are revealed; that match is "that card"
    (ctx["found"]), the others "the rest". With ``player``: another player's library."""
    owners = _library_owner(plan, ctx, e)
    ctx["looked"], ctx["found"] = [], None
    ctx["looked_owner"] = owners[0] if len(owners) == 1 else None
    cards: list[str] = []
    for pid in owners:
        library = _library(plan, pid)
        if e.get("until"):
            at = _first_match(plan, ctx, library, e["until"], ctx["controller"])
            top = library if at is None else library[: at + 1]
            if at is not None and len(owners) == 1:
                ctx["found"] = library[at]
        else:
            top = library[: _amount(plan, ctx, e["n"])]
        if top and e.get("reveal"):
            plan.do({"type": "reveal_top", "player": pid, "count": len(top)}, actor=ctx["controller"])
        elif top and len(owners) == 1:  # shown to the looking player alone (a private view of those cards)
            plan.do({"type": "look_top", "player": pid, "count": len(top)}, actor=ctx["controller"])
        cards += top
    if len(owners) == 1:
        ctx["looked"] = cards
    # (the objects looked at, for "that card's mana value" and the like: still in the library)
    _remember(plan, ctx, e, [ctx["found"]] if ctx.get("found") else cards)
    return True


def _looked(plan: Plan, ctx: Context) -> tuple[str, list[str]]:
    """(the library's owner, the set-aside cards still in that library)."""
    pid = ctx.get("looked_owner") or ctx["controller"]
    library = _library(plan, pid)
    return pid, [c for c in ctx.get("looked") or [] if c in library]


def pick_looked(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Put N of them into your hand", "you may reveal a creature card from among them and put it
    into your hand", "put a land card from among them onto the battlefield tapped", "put that
    card into your hand" (``which``: "that" — the card a reveal-until found, or the one card
    looked at), "put those cards into your hand" (``which``: "all"), "put all land cards revealed
    this way into your hand" (a selector with no choice: every match)."""
    from app.rules import characteristics as chars

    pid = ctx["controller"]
    owner, looked = _looked(plan, ctx)
    ctx["looked"] = looked
    sel = selectors.from_key(e["sel"]) if e.get("sel") else None
    options = [c for c in looked if sel is None
               or selectors.matches(plan, sel, plan.state.cards[c], chars.of(plan.state.cards[c], plan.info), pid)]
    which = e.get("which")
    if which == "that":
        found = ctx.get("found")
        options = [found] if found and found in looked else looked if len(looked) == 1 else []
    most = len(options) if which in ("that", "all") else min(_amount(plan, ctx, e["n"]), len(options))
    least = 0 if e.get("optional") else most
    if not e.get("optional") and (which in ("that", "all") or (sel is not None and most == len(options))):
        return _picked(plan, ctx, e, list(options))  # nothing to choose: every card it names
    if most == 0 and (sel is None or not looked):
        return True
    # (with a filter, ask even when nothing matched, as search does: whether a decision appears
    # mustn't tell the other players what the hidden cards were)
    decide(plan, player=pid, kind="choose_cards", prompt=e.get("prompt") or "Choose from among them",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in options],
           min_choices=least, max_choices=most, resume={"step": "pick_looked", "ctx": ctx, "e": e})
    return False


def resume_pick_looked(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    if _picked(plan, ctx, e, list(chosen)):
        continue_effects(plan, ctx)


def _picked(plan: Plan, ctx: Context, e: dict[str, Any], chosen: list[str]) -> bool:
    """Move the picked cards where the instruction says; False while an Aura entering chooses."""
    from app.rules import attachments  # attachments → effects (resume)

    pid = ctx["controller"]
    if chosen and e.get("reveal"):
        plan.do({"type": "reveal", "card_ids": chosen}, actor=pid)  # to everyone
    ctx["looked"] = [c for c in ctx.get("looked") or [] if c not in chosen]
    if ctx.get("found") in chosen:
        ctx["found"] = None
    before = _remember(plan, ctx, e, chosen)
    if e["to"] in ("hand", "graveyard", "exile"):
        for cid in chosen:  # (a graveyard or exile is the owner's; "your hand" yours)
            to = pid if e["to"] == "hand" else plan.state.cards[cid].owner
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": to, "zone": e["to"]}}, actor=pid)
    else:
        entries = [{"card": c, "player": pid, "actor": pid, "tapped": e["to"] == "battlefield_tapped"} for c in chosen]
        if not attachments.enter(plan, entries, ctx):
            return False
    _moved(plan, ctx, e, before)
    return True


def rest_looked(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"… and the rest into your graveyard / on the bottom of your library in any order / in a
    random order", "put them back in any order" (``to``: "top_any"), "exile the rest". "In any
    order" is the player's private choice (401.4: the order isn't revealed); "in a random order"
    is the table's randomness, recorded as moves (replay is deterministic)."""
    import secrets

    pid = ctx["controller"]
    owner, rest = _looked(plan, ctx)
    ctx["looked"] = []
    if not rest:
        return True
    if e["to"] in ("graveyard", "exile"):
        plan.do({"type": "move", "card_ids": rest, "to": {"player": owner, "zone": e["to"]}}, actor=pid)
        return True
    if e["to"] == "hand":
        plan.do({"type": "move", "card_ids": rest, "to": {"player": pid, "zone": "hand"}}, actor=pid)
        return True
    if e["to"] == "top_any":
        if len(rest) == 1:
            return True  # (already there)
        place = "top"
    else:
        place = "bottom"
        if e["to"] == "bottom_random" or len(rest) == 1:
            order = list(rest)
            (plan.rng or secrets.SystemRandom()).shuffle(order)  # (recorded as moves: replay is deterministic)
            for cid in order:
                plan.do({"type": "move", "card_ids": [cid], "to": {"player": owner, "zone": "library"}, "position": "bottom"},
                        actor=pid)
            return True
    _ask_order(plan, ctx, pid, owner, rest, place)
    return False


def _ask_order(plan: Plan, ctx: Context, chooser: str, owner: str, cards: list[str], place: str) -> None:
    whose = "your library" if owner == chooser else f"{plan.name(owner)}'s library"
    end = "on top" if place == "top" else "at the very bottom"
    decide(plan, player=chooser, kind="order", prompt=f"Order the cards for the {place} of {whose} (first chosen ends up {end})",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in cards],
           min_choices=len(cards), max_choices=len(cards),
           resume={"step": "order_library", "place": place, "then_bottom": [], "owner": owner, "ctx": ctx})


def exile_top(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Exile the top N cards of your library" (face up unless it says "face down"; then hidden
    from everyone but its controller); "exile cards from the top of your library until you exile
    a nonland card" (``until``: the match is "that card", ctx["found"]). Records the exiled cards
    ("cards exiled this way", 400.7j)."""
    owners = _library_owner(plan, ctx, e)
    before: list[ObjectRef] = []
    ctx["found"] = None
    for pid in owners:
        library = _library(plan, pid)
        if e.get("until"):
            at = _first_match(plan, ctx, library, e["until"], ctx["controller"])
            n = len(library) if at is None else at + 1
            if at is not None and len(owners) == 1:
                ctx["found"] = library[at]
        else:
            n = min(_amount(plan, ctx, e["n"]), len(library))
        if not n:
            continue
        before += [r for r in (context.ref_of(plan, c) for c in library[:n]) if r is not None]
        plan.do({"type": "mill", "player": pid, "count": n, "to": "exile", "face_down": bool(e.get("face_down"))}, actor=pid)
    _moved(plan, ctx, e, before)  # the new objects in exile (400.7j)
    if e.get("bind") and not e.get("as"):  # (a permission's "You may play that card": app/rules/permissions.py)
        context.bind_moved(plan, ctx, e["bind"], before)
    return True


def to_library(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Put target creature on top of its owner's library" / "on the bottom of its owner's
    library", "shuffle ~ into its owner's library" (701.24c: the library is shuffled even when
    the object is gone), "its owner puts it on their choice of the top or bottom of their library"
    (``place``: "choice"). Several cards to one position: their owner orders them privately
    (401.4)."""
    cards = _cards(plan, ctx, e["who"])
    before = _remember(plan, ctx, e, cards)
    owners = {plan.state.cards[c].owner for c in cards}
    if e["place"] == "shuffle":
        for cid in cards:
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "library"}},
                    actor=ctx["controller"])
        for pid in sorted(owners):
            plan.do({"type": "shuffle", "player": pid, "zone": "library"}, actor=pid)
        _moved(plan, ctx, e, before)  # (new objects: a shuffled library is re-keyed, 701.20d)
        return True
    if e["place"] == "choice" and len(cards) == 1:
        card = plan.state.cards[cards[0]]
        decide(plan, player=card.owner, kind="choose_one", prompt=f"Put {card.name} on the top or the bottom of your library?",
               options=[DecisionOption(id="top", label="On top"), DecisionOption(id="bottom", label="On the bottom")],
               resume={"step": "library_place", "card": card.id, "ctx": ctx, "e": e, "before": [r.model_dump(mode="json") for r in before]},
               source=card)
        return False
    place = "bottom" if e["place"] == "bottom" else "top"
    pending = [(pid, [c for c in cards if plan.state.cards[c].owner == pid]) for pid in sorted(owners)]
    multiple = [(pid, mine) for pid, mine in pending if len(mine) > 1]
    for pid, mine in pending:
        if len(mine) == 1:
            plan.do({"type": "move", "card_ids": mine, "to": {"player": pid, "zone": "library"}, "position": place}, actor=ctx["controller"])
    if not multiple:
        _moved(plan, ctx, e, before)
        return True
    ctx["library_queue"] = [{"owner": pid, "cards": mine, "place": place} for pid, mine in multiple[1:]]
    ctx["library_before"] = [r.model_dump(mode="json") for r in before]
    ctx["library_e"] = e
    pid, mine = multiple[0]
    _ask_order(plan, ctx, pid, pid, mine, place)
    return False


def resume_library_place(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    ctx, e = r["ctx"], r["e"]
    card = plan.state.cards.get(r["card"])
    if card is not None:
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "library"}, "position": chosen[0]},
                actor=d.player)
    _moved(plan, ctx, e, [ObjectRef.model_validate(x) for x in r["before"]])
    continue_effects(plan, ctx)


def shuffle_library(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Shuffle" / "shuffle your library" (701.24a), "shuffle your graveyard into your library",
    "each player shuffles their hand and graveyard into their library" (``zones``: what goes in
    first). Every card in the library becomes a new object (the shuffle re-keys them). "You may
    shuffle": asked."""
    if e.get("optional"):
        pid = ctx["controller"]
        decide(plan, player=pid, kind="confirm", prompt="Shuffle your library?",
               options=[DecisionOption(id="yes", label="Shuffle"), DecisionOption(id="no", label="Don't shuffle")],
               resume={"step": "shuffle_library", "ctx": ctx, "e": {**e, "optional": False}})
        return False
    for pid in _players(plan, ctx, e["who"]):
        for zone in e.get("zones") or []:
            cards = list(plan.state.zones.get(zone_key(pid, zone), []))
            if cards:
                plan.do({"type": "move", "card_ids": cards, "to": {"player": pid, "zone": "library"}}, actor=pid)
        plan.do({"type": "shuffle", "player": pid, "zone": "library"}, actor=pid)
    return True


def resume_shuffle_library(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx = d.resume["ctx"]
    if chosen[0] == "yes":
        shuffle_library(plan, ctx, d.resume["e"])
    continue_effects(plan, ctx)


PRIMITIVES.update({"look_top": look_top, "pick_looked": pick_looked, "rest_looked": rest_looked, "exile_top": exile_top,
                   "to_library": to_library, "shuffle_library": shuffle_library, "grant_play": permissions.grant_play})


def only_if(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"If [condition], [the next ``skip`` effects]" (608.2c), and an intervening "if" checked
    again as the ability resolves (603.4): when it doesn't hold, those effects don't happen."""
    from app.rules import conditions

    if not conditions.holds(plan, ctx, e["cond"]):
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e.get("skip", len(ctx["effects"]))))
    return True


PRIMITIVES.update({"only_if": only_if})
# "You may pay {2}. If you do, …" / "… unless that player pays {1}" (118.12): app/rules/optional_payment.py
PRIMITIVES["optional_payment"] = optional_payment.optional_payment


def kicked_gate(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.33e: "If this spell was kicked, …" (``kicked`` True) — and, for "… instead", the
    unkicked text (``kicked`` False): the next ``n`` effects happen only if the spell was (or
    wasn't) kicked; otherwise they're skipped."""
    if (values.kicked_count(plan, ctx) > 0) != bool(e["kicked"]):
        ctx["next"] += int(e["n"])
    return True


PRIMITIVES["kicked_gate"] = kicked_gate


# -- resolving a definition -----------------------------------------------------------------
def begin_resolution(plan: Plan, stack_id: str, entry: StackEntry) -> None:
    """608.2: check targets, ask "you may", then carry out the effects in order."""
    ctx: Context = {"controller": entry.controller, "source_card": entry.source_card, "source_object": entry.source_object,
                    "name": entry.name, "targets": [t.model_dump() for t in entry.targets], "stack_id": stack_id,
                    "kind": entry.kind, "effects": entry.effects, "next": 0, "x": entry.x,
                    # what a triggered ability triggered on (603.2, 608.2k): JSON, so it survives
                    # pauses for decisions, saves and replay with the rest of the context
                    "event": entry.event.model_dump(mode="json") if entry.event is not None else None}
    attacker = selectors.attacker_of(entry.event)  # (508.5: "defending player" of an attack trigger)
    if entry.slot_specs:  # a modal spell: each mode's target is checked on its own (608.2b)
        src = source_of(plan, entry.source_card)
        slots, targeted, legal_any = [], False, False
        for refs, sspec in zip(entry.slots, entry.slot_specs, strict=False):
            ok = [t for t in refs if sspec and still_legal(plan, sspec["what"], entry.controller, t, src, entry.source_card, attacker)]
            targeted = targeted or bool(sspec and refs)
            legal_any = legal_any or bool(ok)
            slots.append([t.model_dump() for t in ok])
        if targeted and not legal_any:
            plan.note(f"{entry.name or 'It'} does nothing: its targets are no longer legal")
            finish(plan, ctx, countered=True)
            return
        ctx["slots"] = slots
        ctx["targets"] = []
    if entry.group_specs:  # target groups: every target is checked on its own (608.2b)
        src = source_of(plan, entry.source_card)
        groups: list[list[dict[str, Any] | None]] = []
        for refs, gspec in zip(entry.groups, entry.group_specs, strict=False):
            # an illegal target keeps its place (None), so the division stays as announced (115.7f)
            groups.append([t.model_dump() if still_legal(plan, gspec["what"], entry.controller, t, src, entry.source_card, attacker)
                           else None for t in refs])
        chosen = sum(len(refs) for refs in entry.groups)
        if chosen and not any(t for g in groups for t in g):
            # 608.2b: every target, for every word "target", is illegal: it doesn't resolve.
            # (With zero targets chosen — "up to …" — it resolves normally: 115.6.)
            plan.note(f"{entry.name or 'It'} does nothing: its targets are no longer legal")
            finish(plan, ctx, countered=True)
            return
        ctx["groups"] = groups
        ctx["division"] = [list(d) for d in entry.division]
        ctx["targets"] = [t for t in groups[0] if t] if groups else []
    spec = entry.target_spec
    if spec and entry.targets:
        src = source_of(plan, entry.source_card)
        legal = [t for t in entry.targets if still_legal(plan, spec["what"], entry.controller, t, src, entry.source_card, attacker)]
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


from app.rules import keyword_actions  # noqa: E402, I001  (keyword actions, CR 701, and token wording: leaf modules over this one)

PRIMITIVES.update(keyword_actions.PRIMITIVES)


def describe(effects: list[dict[str, Any]]) -> str:
    words = {"draw": "draw {n} card(s)", "gain_life": "gain {n} life", "lose_life": "lose {n} life", "scry": "scry {n}",
             "surveil": "surveil {n}", "damage": "deal {n} damage", "player_counter": "get {n} {counter}",
             "create_token": "create {n} token(s)", "add_counters": "put {n} {kind} counter(s)", "proliferate": "proliferate",
             "monarch": "become the monarch", "discard": "discard {n}", "search": "search your library"}
    parts = [words.get(e["do"], e["do"]).format(**{k: v for k, v in e.items()}) for e in effects if e["do"] != "kicked_gate"]
    return (", ".join(parts) or "do it").capitalize()


# -- delayed triggered abilities (603.7) and durations (611.2): app/rules/delayed.py (agent J) ------
# "delayed": capture the next n effects as a delayed triggered ability with the objects they name
# bound now; "until": run the next n effects and give their continuous effects a stated duration;
# "bind_refs": a delayed trigger's own resolution context, restored as it resolves.
PRIMITIVES.update({"delayed": delayed.create, "until": delayed.apply_duration, "bind_refs": delayed.bind_refs})


# -- player choices (agent I) ----------------------------------------------------------------------
# Choices that belong to a player other than (or as well as) the ability's controller: edicts
# ("each opponent sacrifices a creature of their choice", 701.21a: the sacrificing player chooses),
# "target opponent chooses a creature they control", a revealed hand the controller chooses from
# ("target player reveals their hand. You choose a nonland card from it. That player discards that
# card", 701.20a), and a named choice ("choose a color / a creature type / an opponent", recorded
# as a public ``choices`` entry on the object when it is made as a permanent enters, 614.12a).
# Several players choosing: APNAP order (101.4), each later chooser knowing the earlier choices
# (101.4b: they are announced in the log and in the prompt), then the action happens to all of
# them at once (101.4).
def _labels(plan: Plan, cards: list[str]) -> str:
    return ", ".join(plan.state.cards[c].name or "a card" for c in cards if c in plan.state.cards)


def _controlled(plan: Plan, key: str, pid: str, source: str | None) -> list[str]:
    """The permanents ``pid`` controls that match a selector, evaluated for that player."""
    sel = selectors.from_key(key)
    return [c for c in selectors.candidates(plan, sel, pid, source)
            if plan.state.cards[c].controller == pid and plan.state.cards[c].zone.endswith(":battlefield")]


def _choose_next(plan: Plan, ctx: Context, e: dict[str, Any], players: list[str], picked: list[str], step: str) -> bool:
    """Each player in ``players`` (APNAP order) chooses ``n`` of the matching permanents they
    control. A player with at most that many has no choice to make (they're all chosen); one
    with none is skipped. Choices already made are announced, so the next chooser knows them
    (101.4b). False while waiting for a choice."""
    want = _amount(plan, ctx, e["n"])
    verb = "sacrifices" if step == "edict" else "chooses"
    for i, pid in enumerate(players):
        mine = _controlled(plan, e["sel"], pid, ctx.get("source_card"))
        n = min(want, len(mine))
        if n == 0:
            continue
        if n == len(mine):
            picked = [*picked, *mine]
            plan.note(f"{plan.name(pid)} {verb} {_labels(plan, mine)} (no choice: all of them)", mine, actor=pid)
            continue
        prompt = f"{ctx.get('name', '') or 'Choose'}: {'sacrifice' if step == 'edict' else 'choose'} {n} ({e.get('label', 'permanent')})"
        if picked:
            prompt += f" — already chosen: {_labels(plan, picked)}"  # 101.4b: the earlier choices are known
        decide(plan, player=pid, kind="choose_cards", prompt=prompt,
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Permanent", card_id=c) for c in mine],
               min_choices=n, max_choices=n,
               resume={"step": step, "ctx": ctx, "e": e, "rest": players[i + 1:], "picked": picked})
        return False
    if step == "edict":  # 101.4: after every choice, all sacrificed at once (one move, one event batch)
        _sacrifice_cards(plan, picked, ctx["controller"], ctx, e.get("as"))
    else:
        _remember(plan, ctx, e, picked)  # "that creature", "it": the chosen objects (they stay where they are)
    return True


def edict(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"[Each opponent / target player / that player] sacrifices N [selector] (of their choice)":
    701.21a — each affected player chooses among the permanents *they* control; the ability's
    controller never chooses for them. Several players: APNAP (101.4), then simultaneously."""
    who = _players(plan, ctx, e["who"])
    return _choose_next(plan, ctx, e, [p for p in plan.apnap() if p in who], [], "edict")


def resume_edict(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    plan.note(f"{plan.name(d.player)} chooses {_labels(plan, chosen)}", chosen, actor=d.player)  # 101.4b
    if _choose_next(plan, r["ctx"], r["e"], r.get("rest") or [], [*(r.get("picked") or []), *chosen], "edict"):
        continue_effects(plan, r["ctx"])


def player_chooses(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"[Target opponent / each player] chooses N [selector] they control": that player's choice,
    bound as the sentence's objects for what follows ("that creature", "it")."""
    who = _players(plan, ctx, e["who"])
    return _choose_next(plan, ctx, e, [p for p in plan.apnap() if p in who], [], "player_chooses")


def resume_player_chooses(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    plan.note(f"{plan.name(d.player)} chooses {_labels(plan, chosen)}", chosen, actor=d.player)
    if _choose_next(plan, r["ctx"], r["e"], r.get("rest") or [], [*(r.get("picked") or []), *chosen], "player_chooses"):
        continue_effects(plan, r["ctx"])


def reveal_hand(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Target player reveals their hand" (701.20a: shown to everyone, and it stays revealed as long
    as the effect needs it: a following choice hides what it didn't pick; the end of this
    resolution hides the rest — a ``hide_revealed`` step is queued after the last instruction)."""
    revealed: list[str] = []
    for pid in _players(plan, ctx, e["who"]):
        hand = list(plan.state.zones.get(zone_key(pid, "hand"), []))
        if hand:
            plan.do({"type": "reveal", "card_ids": hand}, actor=pid)
        else:
            plan.note(f"{plan.name(pid)} reveals an empty hand", actor=pid)
        revealed += hand
    ctx["revealed"] = revealed
    if not ctx.get("hide_queued"):  # (appended in place: the resolver walks the same list)
        ctx["hide_queued"] = True
        ctx["effects"].append({"do": "hide_revealed"})
    return True


def hide_revealed(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """End the reveal of the cards still in a hand that the effect revealed (701.20a: no longer
    needed). A card that changed zones is a new object and was never revealed there (400.7)."""
    left = [c for c in ctx.get("revealed") or [] if c in plan.state.cards and plan.state.cards[c].zone.endswith(":hand")
            and plan.state.cards[c].revealed_to]
    if left:
        plan.do({"type": "hide", "card_ids": left}, actor=ctx["controller"])
    ctx["revealed"] = []
    return True


def choose_from_hand(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"You choose a [nonland] card from it" after a hand was revealed: the controller chooses
    among the revealed cards matching the selector, then the unchosen ones stop being revealed.
    "You may choose" / "up to N" may choose fewer (or none)."""
    from app.rules import characteristics as chars

    pid = ctx["controller"]
    sel = selectors.from_key(e["sel"])
    pool = [c for c in ctx.get("revealed") or [] if c in plan.state.cards and plan.state.cards[c].zone.endswith(":hand")]
    options = [c for c in pool if selectors.matches(plan, sel, plan.state.cards[c], chars.of(plan.state.cards[c], plan.info), pid)]
    most = min(_amount(plan, ctx, e["n"]), len(options))
    least = 0 if e.get("optional") else most
    if most == 0:
        plan.note(f"Nothing to choose ({e.get('label', 'card')})", actor=pid)
        _remember(plan, ctx, e, [])
        return _after_hand_choice(plan, ctx, [])
    owners = sorted({plan.state.cards[c].owner for c in pool})
    whose = ", ".join(f"{plan.name(o)}'s hand" for o in owners) or "the revealed hand"
    decide(plan, player=pid, kind="choose_cards", prompt=f"Choose {most} ({e.get('label', 'card')}) from {whose}",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in options],
           min_choices=least, max_choices=most, resume={"step": "choose_from_hand", "ctx": ctx, "e": e})
    return False


def _after_hand_choice(plan: Plan, ctx: Context, chosen: list[str]) -> bool:
    rest = [c for c in ctx.get("revealed") or [] if c not in chosen and c in plan.state.cards
            and plan.state.cards[c].zone.endswith(":hand") and plan.state.cards[c].revealed_to]
    if rest:  # 701.20a: the cards the effect is done with stop being revealed
        plan.do({"type": "hide", "card_ids": rest}, actor=ctx["controller"])
    ctx["revealed"] = list(chosen)
    return True


def resume_choose_from_hand(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    chosen = [c for c in chosen if c in plan.state.cards and plan.state.cards[c].zone.endswith(":hand")]
    if chosen:
        plan.note(f"{plan.name(d.player)} chooses {_labels(plan, chosen)}", chosen, actor=d.player)
    _remember(plan, ctx, e, chosen)  # "that card" / "those cards": the chosen cards, in that hand
    _after_hand_choice(plan, ctx, chosen)
    continue_effects(plan, ctx)


def discard_named(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"That player discards that card / those cards": 701.9a — the named cards, each from its
    owner's hand to that player's graveyard, all at once (only while each is still that object
    in that hand, 400.7)."""
    cards = [c for c in _cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":hand")]
    before = _remember(plan, ctx, e, cards)
    if cards:
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "graveyard"}}, actor=ctx["controller"])
    _moved(plan, ctx, e, before)
    return True


# Named choices (105.1 colors, 205.3m creature types, 205.3i basic land types, players).
CHOICE_OPTIONS: dict[str, list[str]] = {
    "color": ["White", "Blue", "Black", "Red", "Green"],
    "basic land type": ["Plains", "Island", "Swamp", "Mountain", "Forest"],
}
CHOICE_LABELS = {"color": "Chosen color", "creature type": "Chosen creature type", "basic land type": "Chosen basic land type",
                 "opponent": "Chosen opponent", "player": "Chosen player"}


def _choice_options(plan: Plan, ctx: Context, what: str) -> list[DecisionOption]:
    from app.rules.creature_types import CREATURE_TYPES

    if what == "creature type":
        return [DecisionOption(id=t, label=t) for t in sorted(CREATURE_TYPES)]
    if what in ("opponent", "player"):
        pids = [p for p in plan.live() if what == "player" or p != ctx["controller"]]
        return [DecisionOption(id=p, label=plan.name(p)) for p in pids]
    return [DecisionOption(id=v, label=v) for v in CHOICE_OPTIONS[what]]


def choose_value(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Choose a color / a creature type / a basic land type / an opponent / a player": the
    controller's public choice, bound under ``as`` as {"kind": "choice"}; with ``remember`` it is
    also written on the source object as its public ``choices`` entry ("Chosen color: Blue"):
    the record a permanent keeps of what was chosen as it entered (614.12a), gone with the object
    when it changes zones (400.7)."""
    options = _choice_options(plan, ctx, e["what"])
    if not options:
        return True  # (no opponent left to choose: 800.4)
    src = plan.state.cards.get(ctx.get("source_card") or "")
    article = "an" if e["what"][0] in "aeiou" else "a"
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name', '') or 'Choose'}: choose {article} {e['what']}",
           options=options, resume={"step": "choose_value", "ctx": ctx, "e": e}, source=src)
    return False


def resume_choose_value(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    value = chosen[0]
    shown = plan.name(value) if e["what"] in ("opponent", "player") else value
    plan.note(f"{plan.name(d.player)} chooses {shown} ({e['what']})", actor=d.player)
    if e.get("as"):
        context.refs(ctx)[e["as"]] = {"kind": "choice", "what": e["what"], "value": value}
    src = plan.state.cards.get(ctx.get("source_card") or "")
    if e.get("remember") and src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == ctx.get("source_object"):
        plan.do({"type": "set_choice", "card_id": src.id, "key": CHOICE_LABELS[e["what"]], "value": shown}, actor=d.player)
    continue_effects(plan, ctx)


PRIMITIVES.update({"edict": edict, "player_chooses": player_chooses, "reveal_hand": reveal_hand, "hide_revealed": hide_revealed,
                   "choose_from_hand": choose_from_hand, "discard_named": discard_named, "choose_value": choose_value})
RESUME = {"edict": resume_edict, "player_chooses": resume_player_chooses, "choose_from_hand": resume_choose_from_hand,
          "choose_value": resume_choose_value}
