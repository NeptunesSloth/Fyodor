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

from app.game.rules_state import DecisionOption, copy_recipe_of
from app.game.state import CardInstance, GameState, zone_key
from app.rules import effects, facedown, replace, selectors, token_grammar
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
        # -- replacement effects stage 2 (wave 2E): the token choke point; after a 616.1 choice
        # amass runs again from here (nothing was done yet) --
        if not effects.create_token(plan, ctx, {"who": "you", "n": 1, "token": army_token(sub)}, then=replace.rerun_then(ctx, e)):
            return False
        armies = _armies(plan, ctx)
        if not armies:
            return True  # 701.47b: amassed, even though the token couldn't be created
    if len(armies) == 1:
        return _amass_on(plan, ctx, armies[0], sub, n)
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"Amass {sub}s {n}: choose an Army you control",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Army", card_id=c) for c in armies],
           resume={"step": "amass_choose", "ctx": ctx, "sub": sub, "n": n})
    return False


def _amass_on(plan: Plan, ctx: Context, cid: str, sub: str, n: int) -> bool:
    """The counters (through the counter choke point) and the subtype; False while the Army's
    controller chooses an order (616.1): the rest follows the answer ("amass_rest")."""
    if n > 0 and not replace.put_counters(plan, [(cid, "+1/+1", n)], by=ctx["controller"],
                                          then={"do": "amass_rest", "ctx": ctx, "card": cid, "sub": sub}):
        return False
    _amass_subtype(plan, ctx, cid, sub)
    return True


def _amass_rest(plan: Plan, then: dict[str, Any]) -> None:
    _amass_subtype(plan, then["ctx"], then["card"], then["sub"])
    effects.continue_effects(plan, then["ctx"])


def _amass_subtype(plan: Plan, ctx: Context, cid: str, sub: str) -> None:
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
    if chosen and chosen[0] in plan.state.cards and plan.state.cards[chosen[0]].zone.endswith(":battlefield") \
            and not _amass_on(plan, r["ctx"], chosen[0], r["sub"], r["n"]):
        return  # (a 616.1 choice first)
    effects.continue_effects(plan, r["ctx"])


# -- empower Jace (wave 48A) ------------------------------------------------------------------
# 701.71a: "To empower Jace N means 'If you don't control a Jace planeswalker token, create a blue Jace planeswalker token with 0
# loyalty, "[−1]: Surveil 1," and "[−3]: Draw a card." Choose a Jace planeswalker token you control. Put N loyalty counters on it.'"
JACE: dict[str, Any] = {"name": "Jace", "power": None, "toughness": None, "colors": ["U"], "type_line": "Token Planeswalker — Jace",
                        "text": "−1: Surveil 1\n−3: Draw a card."}
JACE_KEY = selectors.Selector(controller="you", types=("Planeswalker",), subtypes=("Jace",), token=True).key()


def _jaces(plan: Plan, ctx: Context) -> list[str]:
    return selectors.candidates(plan, selectors.from_key(JACE_KEY), ctx["controller"], ctx.get("source_card"))


def empower_jace(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.71a. The token enters with 0 loyalty (state-based actions are not checked mid-resolution, 704.3); the choice among several
    Jace tokens (a token-doubling effect) is the controller's. After a 616.1 choice the instruction runs again from the start."""
    n = effects._amount(plan, ctx, e["n"])
    jaces = _jaces(plan, ctx)
    if not jaces:
        if not effects.create_token(plan, ctx, {"who": "you", "n": 1, "token": dict(JACE)}, then=replace.rerun_then(ctx, e)):
            return False
        if not (jaces := _jaces(plan, ctx)):
            return True  # (the token could not be created: nothing to put counters on)
    if len(jaces) > 1:
        decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"Empower Jace {n}: choose a Jace planeswalker token you control",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Jace", card_id=c) for c in jaces],
               resume={"step": "empower_choose", "ctx": ctx, "n": n})
        return False
    return n <= 0 or replace.put_counters(plan, [(jaces[0], "loyalty", n)], by=ctx["controller"], then={"do": "continue", "ctx": ctx})


def resume_empower(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    if chosen and chosen[0] in plan.state.cards and plan.state.cards[chosen[0]].zone.endswith(":battlefield") and r["n"] > 0 \
            and not replace.put_counters(plan, [(chosen[0], "loyalty", r["n"])], by=r["ctx"]["controller"], then={"do": "continue", "ctx": r["ctx"]}):
        return  # (a 616.1 choice first)
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
    if queue and replace.candidates(plan, "connive"):  # -- keyword actions (wave 35C) -- "If a creature you control would connive, …" (Leader, Super-Genius)
        if len(queue) > 1:  # (each of several conniving permanents is its own event, 701.50c: no card of Commander makes several connive at once)
            plan.note("A replacement effect of connive may apply to these creatures here, and the engine can't ask: apply it by hand (614.1a)")
        elif queue[0][0] is not None and (replaced := replace.keyword_replace(plan, ctx, e, "connive", queue[0][2], card=queue[0][0], n=n)) is not None:
            return replaced
    return _connive_next(plan, ctx, queue, n)


Conniver = tuple[str | None, str | None, str]  # (the card, its rules object, its controller)


def _connive_next(plan: Plan, ctx: Context, queue: list[Conniver], n: int) -> bool:
    """Each conniver in turn: its controller draws, then chooses the discard (a decision when
    there is a choice). True when every one is done."""
    while queue:
        cid, oid, pid = queue.pop(0)
        if pid not in plan.live():
            continue
        if cid is not None:  # -- trigger tail (wave 15B) -- "Whenever a creature you control connives" (701.50a)
            from app.game.rules_state import emit

            emit(plan.state, "designation", counter="connive", card=cid, object_id=oid, player=pid)
        # -- replacement effects stage 2 (wave 2E): the draw through the draw choke point; after a
        # 616.1 choice the conniving goes on from the discard ("connive_after_draw") --
        rest = {"do": "connive_after_draw", "ctx": ctx, "card": cid, "object": oid, "player": pid, "n": n,
                "queue": [list(q) for q in queue]}
        if not replace.draw_cards(plan, [pid], n, then=rest):
            return False
        if not _connive_after_draw(plan, ctx, cid, oid, pid, n, queue):
            return False
    return True


def _connive_after_draw(plan: Plan, ctx: Context, cid: str | None, oid: str | None, pid: str, n: int,
                        queue: list[Conniver]) -> bool:
    """The discard of one conniver (True when done without a decision)."""
    hand = list(plan.state.zones.get(zone_key(pid, "hand"), []))
    if n >= len(hand):  # no choice: the whole hand (or nothing) is discarded
        return _connive_discard(plan, ctx, cid, oid, pid, hand, n, queue)
    decide(plan, player=pid, kind="choose_cards", prompt=f"Connive: discard {n} card{'s' if n != 1 else ''}",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in hand],
           min_choices=n, max_choices=n,
           resume={"step": "connive_discard", "ctx": ctx, "card": cid, "object": oid, "player": pid, "n": n,
                   "queue": [list(q) for q in queue]})
    return False


def _connive_discard(plan: Plan, ctx: Context, cid: str | None, oid: str | None, pid: str, chosen: list[str], n: int,
                     queue: list[Conniver]) -> bool:
    """701.9a: the chosen cards go to the graveyard, all at once; then one +1/+1 counter per nonland
    card among them — on the conniving permanent, if it is still that object on the battlefield
    (through the counter choke point: False while its controller chooses an order, 616.1)."""
    cards = [c for c in chosen if c in plan.state.cards and plan.state.cards[c].zone == zone_key(pid, "hand")]
    if not cards:
        return True
    nonland = sum(1 for c in cards if not plan.ch(plan.state.cards[c]).is_land)
    plan.do({"type": "move", "card_ids": cards, "to": {"zone": "graveyard"}}, actor=pid)
    card = plan.state.cards.get(cid or "")
    if nonland and card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == oid:
        rest = {"do": "connive_next", "ctx": ctx, "n": n, "queue": [list(q) for q in queue]}
        return replace.put_counters(plan, [(card.id, "+1/+1", nonland)], by=pid, then=rest)
    return True


def _queue(raw: list[list[Any]]) -> list[Conniver]:
    return [(q[0], q[1], q[2]) for q in raw]


def resume_connive(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    queue = _queue(r["queue"])
    if not _connive_discard(plan, r["ctx"], r["card"], r["object"], r["player"], chosen, r["n"], queue):
        return
    if _connive_next(plan, r["ctx"], queue, r["n"]):
        effects.continue_effects(plan, r["ctx"])


def _connive_after_draw_then(plan: Plan, t: dict[str, Any]) -> None:
    queue = _queue(t["queue"])
    if _connive_after_draw(plan, t["ctx"], t["card"], t["object"], t["player"], t["n"], queue) \
            and _connive_next(plan, t["ctx"], queue, t["n"]):
        effects.continue_effects(plan, t["ctx"])


def _connive_next_then(plan: Plan, t: dict[str, Any]) -> None:
    if _connive_next(plan, t["ctx"], _queue(t["queue"]), t["n"]):
        effects.continue_effects(plan, t["ctx"])


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
        # -- replacement effects stage 2 (wave 2E): the counter choke point; after a 616.1 choice the
        # primitive runs again (nothing was done yet) --
        if n > 0 and not replace.put_counters(plan, [(cid, "+1/+1", n)], by=ctx["controller"],
                                              then=replace.rerun_then(ctx, e), ctx=ctx):
            return False
        plan.rules.monstrous.append(oid)
        if isinstance(e["n"], dict):  # (wave 19F: other abilities of the permanent that refer to X read this one, 701.37c)
            plan.rules.monstrous_x[oid] = n
        plan.do({"type": "add_effect", "card_ids": [cid], "name": "Monstrous", "value": "Monstrous",
                 "text": "until it leaves the battlefield"})
        # -- becomes monstrous (wave 6D) -- "When ~ becomes monstrous, …" (701.37b: a trigger event)
        from app.game.rules_state import emit

        emit(plan.state, "designation", counter="monstrous", card=cid, object_id=oid, player=plan.state.cards[cid].controller)
    return True


# -- Class (wave 16A) -- 716.2a ---------------------------------------------------------------
def class_level(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"This Class's level becomes N": the level designation (716.2b) of the permanent; "becomes level N" triggers."""
    from app.game.rules_state import emit

    for cid in effects._cards(plan, ctx, "self"):
        card = plan.state.cards[cid]
        if card.zone.endswith(":battlefield"):
            oid = plan.oid(cid)
            plan.rules.levels[oid] = e["n"]
            emit(plan.state, "designation", counter="level", card=cid, object_id=oid, amount=e["n"], player=card.controller)
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
    if len(tied) == 1:  # -- replacement effects stage 2 (wave 2E): the counter choke point --
        return replace.put_counters(plan, [(tied[0].id, "+1/+1", n)], by=pid, then={"do": "continue", "ctx": ctx})
    decide(plan, player=pid, kind="choose_cards", prompt=f"Bolster {n}: choose a creature with the least toughness ({least})",
           options=[DecisionOption(id=c.id, label=c.name or "Creature", card_id=c.id) for c in tied],
           resume={"step": "bolster_choose", "ctx": ctx, "n": n})
    return False


def resume_bolster(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    if chosen and chosen[0] in plan.state.cards and plan.state.cards[chosen[0]].zone.endswith(":battlefield") \
            and not replace.put_counters(plan, [(chosen[0], "+1/+1", int(r["n"]))], by=d.player,
                                         then={"do": "continue", "ctx": r["ctx"]}):
        return  # (a 616.1 choice first; then the resolution continues)
    effects.continue_effects(plan, r["ctx"])


# -- keyword actions & face-down (wave 3F) ------------------------------------------------------
# goad (701.15). Goaded is a designation (701.15b), not an ability and not copiable: a rule-modifying
# effect on those objects ("goaded:<player>" in ``Characteristics.imposed``, read by
# app/rules/combat.py's attack requirements), locked to the objects goaded (a new object isn't, 400.7),
# lasting until the goading player's next turn (701.15a; ends as it begins, 500.4 / 800.4m:
# app/rules/delayed.turn_began).
GOADED = "goaded:"


def goaded_by(ch: Any) -> set[str]:
    """The players who goaded this object (701.15c: possibly several)."""
    return {r[len(GOADED):] for r in ch.imposed if r.startswith(GOADED)}


def goad(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.15a: "Until the next turn of the controller of that spell or ability, that creature is
    goaded." 701.15d: the same player goading it again has no effect (no second requirement).
    ``controlled``: "goad each creature target player / that player controls" (``who`` names the
    player(s))."""
    pid = ctx["controller"]
    if e.get("controlled"):
        players = set(effects._players(plan, ctx, e["who"]))
        cards = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller in players
                 and plan.in_game(c) and plan.ch(c).is_creature]
    else:
        cards = effects._cards(plan, ctx, e["who"])
    effects._remember(plan, ctx, e, cards)
    fresh = [c for c in cards if plan.state.cards[c].zone.endswith(":battlefield")
             and pid not in goaded_by(plan.ch(plan.state.cards[c]))]
    if fresh:
        _until_next_turn(plan, ctx, fresh, (GOADED + pid,), "Goaded", "goads")
        ctx.setdefault("goaded", []).extend(plan.oid(c) for c in fresh)  # -- goad (wave 50J) -- "goaded this way" (this_way.py)
    return True


def _until_next_turn(plan: Plan, ctx: Context, fresh: list[str], imposes: tuple[str, ...], word: str, verb: str) -> None:
    """A layer-6 effect on these objects lasting until the controller's next turn (701.15a goad, 701.35a detain)."""
    from app.rules import delayed, layers

    pid = ctx["controller"]
    effect = layers.add_effect(plan, affected=[plan.oid(c) for c in fresh], layer="6", source=ctx.get("source_object"),
                               controller=pid, imposes=imposes, label=f"{word.lower()} by {plan.name(pid)}")
    effect.duration, effect.until_player, effect.turn = "next_turn", pid, plan.state.turn.number
    markers: list[str] = []
    for cid in fresh:
        markers += delayed.marker_ids(plan.do({"type": "add_effect", "card_ids": [cid], "name": f"{word} by {plan.name(pid)}"[:60],
                                               "value": word, "text": delayed.LABELS["next_turn"]}))
    effect.markers = markers
    plan.note(f"{plan.name(pid)} {verb} {effects._labels(plan, fresh)}", fresh, actor=pid)


def suspect(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.60a: the creature becomes suspected until it leaves the battlefield (the designation is kept by rules object, as
    monstrous is); 701.60c: it has menace and can't block while it is (app/rules/layers.py); 701.60d: it can't become
    suspected again."""
    cards = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")
             and plan.ch(plan.state.cards[c]).is_creature]
    effects._remember(plan, ctx, e, cards)
    for cid in cards:
        oid = plan.oid(cid)
        if oid not in plan.rules.suspected:
            plan.rules.suspected.append(oid)
            plan.do({"type": "add_effect", "card_ids": [cid], "name": "Suspected", "value": "Suspected",
                     "text": "until it leaves the battlefield"})
            plan.note(f"{plan.name(ctx['controller'])} suspects {plan.state.cards[cid].name}", [cid], actor=ctx["controller"])
    return True


# -- prepared (wave 13C) -- 722.3: the designation is kept by rules object (``rules.prepared``: object -> its copy)
def prepared_permanent(state: GameState, copy_id: str) -> CardInstance | None:
    """The permanent this exiled copy belongs to while it is still that prepared object on the battlefield (722.3c)."""
    r = state.rules
    if r is None:
        return None
    for oid, cid in r.prepared.items():
        perm = state.cards.get(oid.rsplit(".", 1)[0])
        if cid == copy_id and perm is not None and perm.zone.endswith(":battlefield") and r.object_id(perm.id) == oid:
            return perm
    return None


def become_prepared(plan: Plan, card: CardInstance) -> None:
    """722.3a / 722.3c: a permanent with a prepare spell gains the designation (once), and its controller creates a copy
    of it in exile with only the prepare spell's characteristics (the card's second face, 722.2), which stays there while
    it remains prepared on the battlefield (an exception to 704.5e: sba.py) and may be cast (casting.cast_grant)."""
    oid = plan.oid(card)
    if not card.zone.endswith(":battlefield") or (oid in plan.rules.prepared and plan.rules.prepared[oid] in plan.state.cards):
        return  # (722.3a: it can't gain the designation again; a prepared permanent that phased out and in gets its copy anew, 722.3c)
    # 722.2b: a copy of a preparation card (a Clone, a token copy) has that card's prepare spell among its copiable values;
    # 722.3c: the exiled copy has only that prepare spell's characteristics, ignoring the copy's other exceptions
    recipe = copy_recipe_of(plan.rules, oid)
    printing = recipe.printing if recipe is not None else card.card_id
    data = plan.info.get(printing) if printing else None
    if (data or {}).get("layout") != "prepare" or card.face_down:
        return  # (no prepare spell, 722.3a)
    created = plan.do({"type": "copy_card", "card_id": card.id, "player": card.controller, "count": 1, "zone": "exile", "face": 1,
                       **({"printing": printing} if printing != card.card_id else {})}, actor=card.controller)
    made = getattr(getattr(created, "r", None), "ids", [])
    if made:
        plan.rules.prepared[oid] = made[0]
    plan.note(f"{card.name} becomes prepared", [card.id], actor=card.controller)


def prepare(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"~ becomes prepared" (722.3a)."""
    cards = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    effects._remember(plan, ctx, e, cards)
    for cid in cards:
        become_prepared(plan, plan.state.cards[cid])
    return True


def detain(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.35a: "Until the next turn of the controller of that spell or ability, that permanent can't attack or block and
    its activated abilities can't be activated." (Mana abilities too: ``cant_activate``.) Detaining it again just extends
    the same restrictions, so one effect per resolution is enough."""
    cards = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    effects._remember(plan, ctx, e, cards)
    if cards:
        _until_next_turn(plan, ctx, cards, ("cant_attack_or_block", "cant_activate"), "Detained", "detains")
    return True


# earthbend (701.66a): "Target land you control becomes a 0/0 land creature with haste in addition to its
# other types. Put N +1/+1 counters on it. When that land dies or is put into exile, return it to the
# battlefield tapped under your control." No duration is stated: the effects last for that object (611.2a;
# a new object isn't it, 400.7). The return is a delayed trigger (603.7) watching that object.
def earthbend(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    import secrets

    from app.game.rules_state import DelayedTrigger
    from app.rules import context, layers

    pid = ctx["controller"]
    n = effects._amount(plan, ctx, e.get("n", 0))
    lands = [c for c in effects._cards(plan, ctx, e.get("who", "target")) if plan.state.cards[c].zone.endswith(":battlefield")]
    effects._remember(plan, ctx, e, lands)
    if not lands:
        return True
    oids = [plan.oid(c) for c in lands]
    name = ctx.get("name") or "Earthbend"
    layers.add_effect(plan, affected=oids, layer="4", source=ctx.get("source_object"), controller=pid, add_types=("Creature",),
                      duration="permanent", label=f"0/0 land creature with haste (earthbend, {name})")
    layers.add_effect(plan, affected=oids, layer="6", source=ctx.get("source_object"), controller=pid, add_keywords=("haste",),
                      duration="permanent", label=f"haste (earthbend, {name})")
    layers.add_effect(plan, affected=oids, layer="7b", source=ctx.get("source_object"), controller=pid, power=0, toughness=0,
                      duration="permanent", label=f"base 0/0 (earthbend, {name})")
    for cid in lands:
        plan.do({"type": "add_effect", "card_ids": [cid], "name": "Earthbent: 0/0 creature, haste", "value": "Earthbent",
                 "text": "as long as it's on the battlefield"})
    refs: dict[str, Any] = {}
    context.bind_objects(plan, {"refs": refs}, "watch", lands)
    plan.rules.delayed.append(DelayedTrigger(
        id=secrets.token_hex(4), controller=pid, source_card=ctx.get("source_card"), source_object=ctx.get("source_object"),
        name=name, when={"kind": "event", "event": "die_or_exile"}, refs=refs, turn=plan.state.turn.number,
        step=plan.state.turn.phase,
        effects=[{"do": "return_card", "who": "event.new", "to": "battlefield", "tapped": True, "under": "you"}]))
    plan.note(f"{plan.name(pid)} earthbends {n}: {effects._labels(plan, lands)} becomes a 0/0 creature with haste", lands,
              actor=pid)
    if n <= 0:
        return True
    return replace.put_counters(plan, [(c, "+1/+1", n) for c in lands], by=pid, then={"do": "continue", "ctx": ctx})


# firebending (702.189a): "Whenever this creature attacks, add N {R}. Until end of combat, you don't lose this
# mana as steps and phases end." The red mana added is remembered (RulesState.combat_mana); at each step's
# end during combat (500.4) as much of it as is still in the pool stays — the player is free to have spent
# their other red mana first (any red mana pays the same) — and at the end of the combat phase it empties.
COMBAT_STEPS = ("begin_combat", "declare_attackers", "declare_blockers", "combat_damage")


def firebend(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    pid = ctx["controller"]
    n = effects._amount(plan, ctx, e.get("n", 0))
    if n <= 0 or plan.state.turn.phase not in (*COMBAT_STEPS, "end_combat"):
        return True  # (an attack trigger resolves during combat; outside it there is nothing to keep)
    plan.do({"type": "rules_mana", "player": pid, "delta": {"R": n}, "label": f"added {'{R}' * n} (firebending {n})"}, actor=pid)
    plan.rules.combat_mana[pid] = plan.rules.combat_mana.get(pid, 0) + n
    return True


def combat_mana_kept(plan: Plan) -> dict[str, int]:
    """As a step ends: the firebending mana each player keeps (none once the combat phase ends)."""
    r = plan.rules
    if not r.combat_mana:
        return {}
    if plan.state.turn.phase not in COMBAT_STEPS:
        r.combat_mana = {}
        return {}
    kept = {pid: min(n, plan.state.players[pid].mana.get("R", 0)) for pid, n in r.combat_mana.items() if pid in plan.state.players}
    r.combat_mana = {pid: n for pid, n in kept.items() if n > 0}
    return dict(r.combat_mana)


# incubate (701.53): "create an Incubator token that enters the battlefield with N +1/+1 counters on it";
# 111.10i: a double-faced token — front "Incubator", a colorless artifact with "{2}: Transform this token.",
# back a 0/0 colorless Phyrexian artifact creature named "Phyrexian Token". Transforming (701.27) turns the
# token over (``set_face``; its new timestamp, 613.7g, is app/game/rules_state.py's): it's the same object.
INCUBATOR: dict[str, Any] = {
    "name": "Incubator", "power": None, "toughness": None, "colors": [], "type_line": "Token Artifact — Incubator",
    "text": "{2}: Transform this token.",
    "back": {"name": "Phyrexian Token", "power": "0", "toughness": "0", "colors": [],
             "type_line": "Token Artifact Creature — Phyrexian", "text": ""}}


def incubate(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    pid = ctx["controller"]
    n = effects._amount(plan, ctx, e.get("n", 0))
    source = ctx.get("source_card") if ctx.get("source_card") in plan.state.cards else None
    made = replace.create_tokens(plan, pid, dict(INCUBATOR), 1, source=source, ctx=ctx, bind=e.get("as"),
                                 then=replace.rerun_then(ctx, e))
    if made is None:
        return False  # (616.1: the creating player orders replacement effects first; incubate runs again)
    puts = [(t, "+1/+1", n) for t in made if t in plan.state.cards and n > 0]
    if not puts:
        return True
    # 122.6: the counters it enters with, through the counter choke point
    return replace.put_counters(plan, puts, by=pid, entering={t: pid for t, _, _ in puts}, then={"do": "continue", "ctx": ctx})


def transform(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.27a, "Transform this token / ~.": a double-faced token or nonmodal double-faced card turns over (712.18: the
    same object); 701.27c / 712.10: anything else, or one whose other face is an instant or sorcery, doesn't (nothing
    happens); 701.27f: not if it transformed since this ability was put onto the stack (-- transform, wave 11A --)."""
    from app.rules import attachments
    from app.rules import characteristics as chars

    r = plan.rules
    named = effects._cards(plan, ctx, e.get("who", "self"))
    effects._remember(plan, ctx, e, named)  # -- most-played cards II (wave 45A) -- "Transform this land, then untap it." (Westvale Abbey): "it" is the permanent named, transformed or not
    for cid in named:
        card = plan.state.cards[cid]
        if not card.zone.endswith(":battlefield") or card.face_down:
            continue
        if (card.token is None or card.token.back is None) and not chars.transformable(card, plan.info):
            continue
        if r.transformed.get(cid, 0) > r.objects.get(ctx.get("stack_id") or "", 1 << 60):
            continue  # (an ability not on the stack has no number: never ignored)
        if e.get("since") is not None and r.transformed.get(cid, 0) > e["since"]:
            continue  # (wave 47D) 701.27f: a delayed triggered ability counts from when it was created
        plan.do({"type": "set_face", "card_id": cid, "face": 1 - min(card.face, 1)}, actor=ctx["controller"])
        now = plan.state.cards[cid]
        # -- transform (wave 16F) -- 701.28: "When this creature transforms into …" (the same object, 712.18; designations.facts)
        from app.game.rules_state import emit

        emit(plan.state, "designation", counter="transformed", card=cid, object_id=plan.oid(cid), player=now.controller)
        if (now.attached_to or now.attached_player) and attachments.attach_kind(plan.ch(now)) is None:
            plan.do({"type": "detach", "card_ids": [cid]}, actor=ctx["controller"])  # 704.5n: no longer an Equipment (or Aura …)
    return True


def flip(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """-- flip (wave 24C) -- 710: "flip ~" turns a flip card's permanent upside down (``CardInstance.flipped``, 110.5: the same object; its name,
    text, type line and power and toughness are the alternative ones, 710.2; its color and mana cost stay, 710.1c). One-way (710.4): a flipped
    permanent, a card that isn't a flip card and anything not on the battlefield does nothing."""
    from app.rules import characteristics as chars
    from app.rules import copying

    for cid in effects._cards(plan, ctx, e.get("who", "self")):
        card = plan.state.cards[cid]
        if card.zone.endswith(":battlefield") and not card.face_down and chars.flippable(card, plan.info, copying.room_printing(plan.rules, card, plan.oid(card))):
            plan.do({"type": "flip", "card_id": cid}, actor=ctx["controller"])
    return True


# stun counters (122.1d): "If a permanent with a stun counter on it would become untapped, instead remove a
# stun counter from it." — a replacement effect of the counters themselves, applied wherever the engine untaps
# a permanent (the untap step, "untap target creature", "untap … and gain control of it").
def stunned(plan: Plan, card_ids: list[str]) -> list[str]:
    """The permanents among these that would become untapped but have a stun counter."""
    return [c for c in card_ids if (card := plan.state.cards.get(c)) is not None and card.tapped
            and card.zone.endswith(":battlefield") and card.counters.get("stun", 0) > 0 and not plan.manual(card)]


def lose_stun(plan: Plan, card_ids: list[str], actor: str | None) -> None:
    """Instead of untapping: one stun counter comes off each (removing counters isn't replaceable)."""
    for cid in card_ids:
        plan.do({"type": "counter", "card_ids": [cid], "kind": "stun", "delta": -1}, actor=actor)


def untap_stunned(plan: Plan, card_ids: list[str], actor: str | None) -> list[str]:
    """The cards to untap after 122.1d replaced the untapping of the stunned ones."""
    stuck = stunned(plan, card_ids)
    lose_stun(plan, stuck, actor)
    return [c for c in card_ids if c not in stuck]


PRIMITIVES = {"class_level": class_level, "amass": amass, "connive": connive, "monstrosity": monstrosity, "bolster": bolster,
              "goad": goad, "detain": detain, "suspect": suspect, "prepare": prepare, "earthbend": earthbend, "firebend": firebend, "incubate": incubate, "empower_jace": empower_jace, "transform": transform, "flip": flip,
              **facedown.PRIMITIVES,  # -- keyword actions & face-down (wave 3F) --
              **token_grammar.PRIMITIVES}
RESUME = {"amass_choose": resume_amass, "empower_choose": resume_empower, "bolster_choose": resume_bolster, "connive_discard": resume_connive,
          **facedown.RESUME,  # -- keyword actions & face-down (wave 3F) --
          **token_grammar.RESUME}
# -- replacement effects stage 2 (wave 2E): where a keyword action goes on after a 616.1 choice --
replace.THEN.update({"amass_rest": _amass_rest, "connive_after_draw": _connive_after_draw_then,
                     "connive_next": _connive_next_then})
replace.THEN["face_up_done"] = lambda plan, then: None  # -- wave 3F -- (megamorph's counter: the special action is done)
