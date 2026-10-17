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

import contextlib
import itertools
from collections.abc import Iterator
from typing import Any

from app.game.rules_state import DecisionOption, ObjectRef, StackEntry, remember_stack
from app.game.state import ALL, STACK, zone_key
from app.rules import (
    block_effects,  # -- block effects (wave 30P) -- the object arguments of a block rule (a leaf module)
    card_names,  # -- card names (wave 22B) -- 201.4
    context,
    delayed,
    entry_forms,
    layers,
    optional_payment,
    permissions,
    protection,
    regeneration,
    replace,  # -- replacement effects stage 2 (wave 2E): the choke points --
    replacements,
    selectors,
    sized_damage,  # -- damage sized by a count (wave 4E) --
    values,
)
from app.rules import this_way as _this_way  # -- "this way" outcomes (wave 4A) --
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
    if who.startswith("player:"):  # -- keywords (wave 15E) -- one named player (ward: the player whose spell or ability targeted)
        return [who[7:]] if who[7:] in plan.live() else []
    if who == "each_player":
        return list(plan.live())
    if who == "each_opponent":
        return [p for p in plan.live() if p != me]
    if who == "put_none_opponents":  # -- trigger other (wave 44B) -- 101.4: the opponents who chose no card in the "each player may put" just before (put_from_hand.each_put)
        return [p for p in plan.live() if p != me and p in ctx.get("_put_none", ())]
    if who == "gifted":  # -- gift (wave 23D) -- 702.174d-i: the opponent the gift was promised to
        from app.rules import gift

        return gift.recipient(plan, ctx)
    if who == "target" or who.startswith("target:"):
        return [t["id"] for t in target_refs(ctx, who) if t["id"] in plan.state.players and t["id"] in plan.live()]
    if who == "target_player_or_controller":  # -- damage wordings (wave 6B) -- "that player or that planeswalker's
        # controller": the target player, or the target permanent's controller (as it last existed: 608.2h)
        out: list[str] = []
        for t in target_refs(ctx, "target"):
            pid: str | None = t["id"] if t["id"] in plan.state.players else None
            if pid is None:
                card = plan.state.cards.get(t["id"])
                if card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == t.get("object_id"):
                    pid = card.controller
                elif (snap := plan.rules.lki.get(t.get("object_id") or "")) is not None:
                    pid = snap.controller
            if pid is not None and pid in plan.live() and pid not in out:
                out.append(pid)
        return out
    if who == "each_other_opponent":  # -- sized amounts (wave 3D) -- the opponents besides the player the trigger event was about
        named = set(context.players(plan, ctx, context.EVENT))
        return [p for p in plan.live() if p != me and p not in named]
    if who == "event_player":  # "that player": the one the trigger event was about (who drew, was dealt damage …)
        return context.players(plan, ctx, context.EVENT)
    if who == "source_owner":  # -- review 33 -- "~'s owner": the source card's owner, wherever it is now (108.3; a card shuffled into a
        src = plan.state.cards.get(ctx.get("source_card") or "") or plan.rules.lki.get(ctx.get("source_object") or "")  # library is known
        return [src.owner] if src is not None and src.owner in plan.live() else []  # there by no id: as it last existed, 608.2h)
    if who == "attacking_opponents":  # -- attached events (wave 4L) -- "Each opponent attacking that player"
        from app.rules import attached_players

        return attached_players.attacking_opponents(plan, ctx)
    if who.startswith(context.PREFIX):  # a binding: "that player", "its controller", "its owner" (app/rules/context.py)
        return context.players(plan, ctx, who[len(context.PREFIX):])
    if who == "defending_player":  # -- defending player (wave 6D) -- 508.5 (app/rules/defending.py)
        from app.rules import defending

        return defending.players(plan, ctx)
    if who == "attacked":  # -- attacked object (wave 45A) -- "the player or planeswalker it's attacking" (508.5; app/rules/defending.py)
        from app.rules import defending

        return defending.attacked(plan, ctx)[0]
    if who == "chosen_player":  # -- chosen player (wave 4J) -- the player the source chose as it entered (614.12a)
        from app.rules import chosen

        pid = chosen.player_of(plan, ctx.get("source_card") or "", ctx.get("source_object"))
        return [pid] if pid is not None and pid in plan.live() else []
    if who.startswith("player:"):  # (older saves: a player bound into the effect when it triggered)
        return [who[7:]] if who[7:] in plan.live() else []
    return []


def _cards(plan: Plan, ctx: Context, who: str) -> list[str]:
    if who.startswith(context.PREFIX) and "|" in who:  # -- resolution memory (wave 22D) -- "each creature card put into a graveyard this way"
        from app.rules import this_way

        base, _, key = who.partition("|")
        return this_way.filtered(plan, ctx, _cards(plan, ctx, base), key)
    if who.startswith("controlled:"):  # -- damage sized by a count (wave 4E) -- "each creature that player controls"
        return _controlled_by(plan, ctx, who)
    if who.startswith("graveyard_of:"):  # -- graveyard exile (wave 4J) -- "target player's graveyard": every card in it
        ref, _, key = who[len("graveyard_of:"):].partition("|")  # (wave 15C: "|<selector>" — only the cards of that kind)
        sel = selectors.from_key(key) if key else None
        return [c for p in _players(plan, ctx, ref) for c in plan.state.zones.get(f"{p}:graveyard", [])
                if sel is None or selectors.matches(plan, sel, plan.state.cards[c], plan.ch(plan.state.cards[c]), ctx["controller"],
                                                    ctx.get("source_card"))]
    if who.startswith("except:"):  # -- refused modal/conditional (wave 3R1) -- "all other creatures" after "Create X
        name, _, key = who[len("except:"):].partition("|")  # … tokens" (Martial Coup): other than what it made
        made = set(context.objects(plan, ctx, name))
        return [c for c in _cards(plan, ctx, key) if c not in made]
    if who.startswith(("radiance:", "samename:")):  # -- radiance (wave 9C) -- the target and each other object sharing a color with it
        from app.rules import radiance

        return radiance.cards(plan, ctx, who)
    if who.startswith(selectors.PREFIX):  # "each creature you control", "all other Goblins" …
        sel = selectors.from_key(who)
        if any(isinstance(c[2], str) and c[2].startswith(selectors.TARGET_STAT) for c in sel.compare):  # -- most-played cards II (wave 45A) -- "power greater than target creature's power"
            first = next(iter(target_refs(ctx, "target")), {})  # (its power as the spell resolves, 608.2b; none left: the spell didn't resolve)
            tc = plan.state.cards.get(first.get("id", ""))
            if tc is None or not tc.zone.endswith(":battlefield") or plan.oid(tc) != first.get("object_id"):
                return []
            bound: list[tuple[str, str, int | str]] = []
            for w, o, n in sel.compare:
                v = selectors._stat(plan.ch(tc), n[len(selectors.TARGET_STAT):]) if isinstance(n, str) and n.startswith(selectors.TARGET_STAT) else n
                if v is None:
                    return []
                bound.append((w, o, v))
            sel = selectors.replace(sel, compare=tuple(bound))
        return [] if sel.player else selectors.candidates(plan, sel, ctx["controller"], ctx.get("source_card"))
    if who == "target" or who.startswith("target:"):
        return [t["id"] for t in target_refs(ctx, who) if t["id"] in plan.state.cards
                and plan.oid(t["id"]) == t.get("object_id")]
    if who == "attacked":  # -- attacked object (wave 45A) --
        from app.rules import defending

        return defending.attacked(plan, ctx)[1]
    if who == "self":
        src = plan.state.cards.get(ctx.get("source_card") or "")
        if src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == ctx.get("source_object"):
            return [src.id]
        return []  # the source left: "it" is gone (a new object isn't affected)
    if who.startswith("obj:"):  # -- granted from object (wave 18F) -- the granting object, while it is still that object here
        obj = plan.state.cards.get(who[4:].rsplit(".", 1)[0])
        return [obj.id] if obj is not None and obj.zone.endswith(":battlefield") and plan.oid(obj) == who[4:] else []
    if who == "cost_exiled":  # -- keywords (wave 15E) -- the card an activation cost exiled from the graveyard (embalm: "this card")
        sid = ctx.get("stack_id")
        record = plan.rules.payments.get(plan.rules.object_id(sid)) if sid else None
        return [c for c in (record.exiled if record is not None else []) if c in plan.state.cards
                and plan.state.cards[c].zone.endswith(":exile")]
    if who == "cost_exiled_self":  # -- casting extras (wave 18E) -- craft 702.167a: the source itself, exiled as part of the cost
        sid = ctx.get("stack_id")
        record = plan.rules.payments.get(plan.rules.object_id(sid)) if sid else None
        src = ctx.get("source_card")
        return [src] if record is not None and src in record.exiled and src in plan.state.cards \
            and plan.state.cards[src].zone.endswith(":exile") \
            and (not record.exiled_objects or plan.oid(src) in record.exiled_objects) else []  # (-- as long as (wave 37A) -- 400.7j: that object, not a later one)
    if who in ("self_gy", "self_gy_exile"):  # -- reanimation (wave 3R) -- "return this card from your graveyard": the source, only
        # while it is still the same object in a graveyard (400.7); -- activated other (wave 42C) -- "… from your graveyard or from exile": in either
        src = plan.state.cards.get(ctx.get("source_card") or "")
        if src is not None and src.zone.endswith((":graveyard", ":exile") if who == "self_gy_exile" else ":graveyard") and plan.oid(src) == ctx.get("source_object"):
            return [src.id]
        return []
    if who in ("self_hand", "self_command"):  # -- activated from hand / command zone (wave 27D) -- 113.6m: the source, only while it
        src = plan.state.cards.get(ctx.get("source_card") or "")  # is still the same object in that zone (400.7)
        if src is not None and src.zone.endswith(":" + who[5:]) and plan.oid(src) == ctx.get("source_object"):
            return [src.id]
        return []
    if who.startswith("self_aura_gy"):  # -- sagas & attached-object triggers (wave 3S) --
        return _aura_card(plan, ctx, who)
    if who == "host":  # "enchanted creature" / "equipped creature": what the source is attached to now
        src = plan.state.cards.get(ctx.get("source_card") or "")
        if src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == ctx.get("source_object"):
            host = plan.state.cards.get(src.attached_to or "")
        else:  # the Aura / Equipment left (sacrificed as a cost: "Sacrifice ~: Equipped creature can't be
            # blocked this turn"): what it was attached to as it last existed (608.2h, its LKI snapshot)
            snap = plan.rules.lki.get(ctx.get("source_object") or "")
            host = plan.state.cards.get(snap.attached_to or "") if snap is not None else None
        return [host.id] if host is not None and host.zone.endswith(":battlefield") else []
    if who == "host:kin":  # -- attached events (wave 25D) -- "Enchanted creature and other creatures that share a creature type with it" (the Crowns)
        return _host_kin(plan, ctx)
    if who == "exiled_with" or who.startswith("exiled_with:"):  # -- exiled with (wave 6D) -- 607.2a (app/rules/exiled_with.py)
        from app.rules import exiled_with

        return exiled_with.cards(plan, ctx, who)
    if who == "event":  # "it" / "that creature": the object(s) the trigger event happened to — only while
        # each is still that object where it was (400.7: after a zone change it's a new object)
        return context.objects(plan, ctx, context.EVENT)
    if who == "event_spell":  # -- spell copies (wave 31D) -- the spell a cast trigger is about, while it is still that object on the stack (400.7)
        return [c for c in context.objects(plan, ctx, context.EVENT) if plan.state.cards[c].zone == "stack"]
    if who == context.EVENT_NEW:  # after "dies" / "leaves": the new object where it went — only while
        # it's still there (400.7e, 603.6c)
        return context.objects(plan, ctx, context.EVENT_NEW)
    if who.startswith(context.PREFIX):  # an earlier effect's objects ("it", "cards exiled this way")
        return context.objects(plan, ctx, who[len(context.PREFIX):])
    if who.startswith("exiled_card:"):  # -- static_other sweep (wave 17C) -- one card in exile, while it is still that object (cipher)
        oid = who[len("exiled_card:"):]
        card = plan.state.cards.get(oid.rsplit(".", 1)[0])
        return [card.id] if card is not None and card.zone.endswith(":exile") and plan.oid(card) == oid else []
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


# -- sagas & attached-object triggers (wave 3S) --
def _aura_card(plan: Plan, ctx: Context, who: str) -> list[str]:
    """400.7f: an ability that triggered on the enchanted permanent leaving the battlefield finds the
    new object its Aura became in its owner's graveyard — put there at the same time, or afterwards
    by the state-based action for not being attached (704.5m) — while it is still that object (bound
    as it triggered: "self_aura_gy:<object id>", app/rules/triggers.py)."""
    src = plan.state.cards.get(ctx.get("source_card") or "")
    oid = who.split(":", 1)[1] if ":" in who else None
    if src is None or not oid or src.zone != f"{src.owner}:graveyard" or plan.oid(src) != oid:
        return []
    return [src.id]
# -- end sagas & attached-object triggers (wave 3S) --


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
    # -- replacement effects stage 2 (wave 2E): the draw choke point (app/rules/replace.py: 121.2,
    # 121.2c APNAP, 121.6a / 614.11 with an empty library, 704.5b) --
    players = _players(plan, ctx, e["who"])
    if e.get("may") and players and ctx.get("may_ok") != ctx["next"]:  # -- activated sweep (wave 17B) -- "Target opponent may draw a card": their choice (608.2d)
        decide(plan, player=players[0], kind="confirm", prompt=f"{ctx.get('name') or 'It'}: draw a card?",
               options=[DecisionOption(id="yes", label="Draw"), DecisionOption(id="no", label="Don't draw")],
               resume={"step": "draw_may", "ctx": ctx, "e": e})
        return False
    if isinstance(e["n"], dict) and e["n"].get("each_owner"):  # -- static_other sweep (wave 16B) -- "each player discards …, then draws that
        # many cards [plus / minus one]": each draws as many as they discarded (this_way.by_controller: a card's owner, 108.4a)
        from app.rules import this_way

        counts = this_way.by_controller(plan, ctx, e["n"])
        each = {p: max(0, counts.get(p, 0) + int(e["n"].get("delta", 0))) for p in players}
        players = [p for p in players if each[p] > 0]
        if players:
            _drawing(ctx, e)
        return not players or replace.draw_cards(plan, players, each, then=_then(ctx, e), ctx=ctx)
    want = _amount(plan, ctx, e["n"])
    if e.get("also"):  # -- triggers (wave 5D) -- "You and target opponent each draw a card": one instruction (121.2c)
        players = list(dict.fromkeys([*_players(plan, ctx, e["also"]), *players]))
    if players and (want > 0 or isinstance(e["n"], dict)):
        _drawing(ctx, e, want)  # (-- reflexive this way (wave 30G) -- "You may draw cards equal to X. If you do, …": chosen even when X is 0, 118.12)
    if want <= 0 or not players:
        return True
    return replace.draw_cards(plan, players, want, then=_then(ctx, e), ctx=ctx)


def _drawing(ctx: Context, e: dict[str, Any], want: int = 0) -> None:
    """-- if you do (review 29C) -- "You may draw a card. If you do, …": 118.12 — the draw is a cost paid as it resolves, and "if you do"
    checks that the player chose to draw (or started a mandatory draw), "regardless of what events actually occurred": a draw a
    replacement effect changed (118.11: Underrealm Lich, Notion Thief, dredge) or one from an empty library was still done."""
    if e.get("did"):
        context.bind_payment(ctx, e["did"], True)
        context.refs(ctx)[e["did"]]["n"] = want  # (the number it came to: "discard that many cards", context.amount)


def gain_life(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    # -- replacement effects stage 2 (wave 2E): the life-gain choke point (119.10; each player's
    # gain its own event) --
    n = _amount(plan, ctx, e["n"])
    gains = [(pid, n) for pid in _players(plan, ctx, e["who"]) if n > 0]
    if not gains:
        return True
    return replace.gain_life(plan, gains, actor=ctx["controller"], then=_then(ctx, e), ctx=ctx)


def _then(ctx: Context, e: dict[str, Any]) -> dict[str, Any] | None:
    """-- replacement effects stage 2 (wave 2E) -- How a primitive's choke point goes on after the
    affected player chose an order (616.1): the resolution continues — only when this primitive
    is the effect being resolved (called from another primitive, it can't pause: None)."""
    return {"do": "continue", "ctx": ctx} if replace.rerun_then(ctx, e) is not None else None


def lose_life(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    # -- life lost (wave 8B) -- "Each opponent loses life equal to the life they lost this turn": each one's own amount,
    # worked out before any of them loses life (608.2h; they lose it at once)
    each = {p: _amount(plan, {**ctx, "recipient": p}, e["n"]) for p in _players(plan, ctx, e["who"])} \
        if sized_damage.has_per_player(e["n"]) else None
    n = 0 if each is not None else _amount(plan, ctx, e["n"])
    losses: list[tuple[str, int]] = []
    for pid in _players(plan, ctx, e["who"]):
        if each is not None:
            n = each[pid]
        if e.get("half"):  # -- attached events (wave 8D) -- "loses half their life, rounded up": of the life total now (a
            half_of = max(0, plan.state.players[pid].life)  # negative total is 0, 107.1b)
            div = e.get("of", 2)  # (wave 16C: "a third of their life")
            n = half_of // div + (1 if half_of % div and e["half"] == "up" else 0)
        if n:
            losses.append((pid, n))
    before = {pid: plan.state.players[pid].life for pid, _ in losses}
    # -- life modifiers (wave 28B) -- the life-loss choke point: "would lose life" replacements (Bloodletter of Aclazotz)
    if not replace.lose_life(plan, losses, actor=ctx["controller"], then=_then(ctx, e), ctx=ctx):
        return False
    lost = sum(max(0, before[pid] - plan.state.players[pid].life) for pid, _ in losses)
    if e.get("bind"):  # -- refused zones/sized (wave 3R4) -- "the life lost this way": the total actually lost (119.3)
        context.bind_amount(ctx, e["bind"], lost)
    return True


def set_life(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """-- trigger tail (wave 16C) -- 119.5: "[Player]'s life total becomes N": the player gains or loses what it takes (each its own
    event, with replacement effects); 119.7: a player who can't gain life stays where they are when the new total is higher."""
    from app.rules import cant_gain

    for pid in _players(plan, ctx, e["who"]):
        start = plan.state.settings.starting_life
        want = -(-start // 2) if e["n"] == "half_start" else _amount(plan, ctx, e["n"])  # (107.1a: rounded up)
        diff = want - plan.state.players[pid].life
        if diff < 0:
            replace.lose_life(plan, [(pid, abs(diff))], actor=ctx["controller"])  # -- life modifiers (wave 28B) -- 119.5: a loss event
        elif diff > 0:
            if (why := cant_gain.why_not(plan, pid)) is not None:
                plan.note(f"{why}: the life total doesn't change", actor=ctx["controller"])
            elif not replace.gain_life(plan, [(pid, diff)], actor=ctx["controller"], then=_then(ctx, e), ctx=ctx):
                return False
    return True


def exchange_life(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """-- activated wordings (wave 15D) -- 701.12c: the player with the lower life total gains, the other loses, what it takes to
    equal the other's previous total (replacement effects and triggers apply to the gain and the loss). 701.12a: if the whole
    exchange can't be done (a target gone, 119.7: a player who can't gain life can't be given a higher total), none of it is."""
    ps = list(dict.fromkeys([ctx["controller"], *_players(plan, ctx, e["with"])] if e.get("with") else _players(plan, ctx, e["who"])))
    if len(ps) != 2:
        return True
    low, high = sorted(ps, key=lambda p: plan.state.players[p].life)
    diff = plan.state.players[high].life - plan.state.players[low].life
    if diff == 0:
        return True
    from app.rules import cant_gain

    if (why := cant_gain.why_not(plan, low)) is not None:
        plan.note(f"{why}: the life totals aren't exchanged", actor=ctx["controller"])
        return True
    from app.rules import (
        life_lock,  # -- can't lose life (wave 29D) -- 119.8: a player who can't lose life can't be given a lower total either
    )

    if (why := life_lock.why_not(plan, high, "lose")) is not None:
        plan.note(f"{why}: the life totals aren't exchanged", actor=ctx["controller"])
        return True
    replace.lose_life(plan, [(high, diff)], actor=ctx["controller"])  # -- life modifiers (wave 28B) -- 701.12c
    return replace.gain_life(plan, [(low, diff)], actor=ctx["controller"], then=_then(ctx, e), ctx=ctx)


def exchange_life_stat(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """-- exchange (wave 19E) -- 701.12g: "Exchange your life total with this creature's toughness." (Tree of Redemption, Evra): the
    player gains or loses what it takes to equal the stat (replacements and triggers apply, as in set_life) and a continuous effect
    (613.4b, layer 7b) with no duration sets the creature's stat to the life total it had. 701.12a: if the whole exchange can't be done
    (the creature is gone, 119.7: a player who can't gain life can't be given a higher total) none of it is."""
    from app.rules import cant_gain

    players = _players(plan, ctx, e["who"])
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if len(players) != 1 or card is None or not card.zone.endswith(":battlefield") or plan.oid(card) != ctx.get("source_object"):
        return True
    pt = plan.ch(card).pt
    if pt is None:
        return True
    power = e["stat"] == "power"
    value, life = pt[0 if power else 1], plan.state.players[players[0]].life
    if value > life and (why := cant_gain.why_not(plan, players[0])) is not None:
        plan.note(f"{why}: nothing is exchanged", actor=ctx["controller"])
        return True
    from app.rules import life_lock  # -- can't lose life (wave 29D) -- 119.8

    if value < life and (why := life_lock.why_not(plan, players[0], "lose")) is not None:
        plan.note(f"{why}: nothing is exchanged", actor=ctx["controller"])
        return True
    layers.add_effect(plan, affected=[plan.oid(card)], layer="7b", source=ctx.get("source_object"), controller=ctx["controller"],
                      power=life if power else None, toughness=None if power else life, duration="permanent",
                      label=f"{e['stat'].capitalize()} {life}")
    return set_life(plan, ctx, {"who": e["who"], "n": value})


class _Source:
    """What deals damage: the spell or ability's source, or a creature the text names ("target
    creature you control deals damage equal to its power to …", a fight). ``keywords`` and ``ch``
    are the object's as it is, or as it last existed if it left (702.15c, 702.2e: last known
    information decides whether it had lifelink / deathtouch); ``key`` is what a lifelink gain is
    recorded under (the card while it's there — each source is its own gain event, 702.15e — else
    its controller as it last existed, 702.15b)."""

    __slots__ = ("oid", "keywords", "ch", "key", "card")

    def __init__(self, oid: str, keywords: frozenset[str], ch: Any, key: str, card: str | None) -> None:
        self.oid, self.keywords, self.ch, self.key, self.card = oid, keywords, ch, key, card


def _ability_source(plan: Plan, ctx: Context) -> _Source:
    """The damage source of "~ deals N damage": the ability's source object (608.2h)."""
    source = plan.state.cards.get(ctx.get("source_card") or "")
    lki = plan.rules.lki.get(ctx.get("source_object") or "")
    keywords: frozenset[str] = frozenset()
    src_ch = plan.ch(source) if source is not None else None
    if source is not None and (source.zone.endswith(":battlefield") or (source.zone == STACK and source.ability is None)) \
            and plan.oid(source) == ctx.get("source_object"):  # (wave 28C: a spell on the stack deals its damage with the abilities it was granted)
        keywords = plan.ch(source).keywords
    elif lki is not None:
        # as it last existed (603.10a, 702.15c, 702.2e): keywords granted by an effect or a static count, and a
        # token that ceased to exist still has them (quoted grants, wave 2D: ObjectSnapshot.abilities/keywords)
        from app.rules.triggers import _snapshot_card  # (triggers imports this module)

        _, src_ch = _snapshot_card(plan, lki)
        keywords = src_ch.keywords
    return _Source(ctx.get("source_object") or "", keywords, src_ch, ctx["controller"], source.id if source is not None else None)


def _host_kin(plan: Plan, ctx: Context) -> list[str]:
    """The creature the source Aura / Equipment is attached to (as it is, or — if it left since — as it last existed, 608.2h) and every other
    creature on the battlefield that shares a creature type with it (205.3m; a changeling shares with every creature type). The host leaves
    nothing to affect itself once gone; the others are still found by what it was."""
    from app.rules.creature_types import CREATURE_TYPES
    from app.rules.triggers import _snapshot_card  # (triggers imports this module)

    src = plan.state.cards.get(ctx.get("source_card") or "")
    if src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == ctx.get("source_object"):
        host_id = src.attached_to
    else:
        snap = plan.rules.lki.get(ctx.get("source_object") or "")
        host_id = snap.attached_to if snap is not None else None
    host = plan.state.cards.get(host_id or "")
    if host is None:
        return []
    if host.zone.endswith(":battlefield"):
        kinds = plan.ch(host).subtypes & CREATURE_TYPES
    else:  # it left: its last known types (the newest snapshot of that card)
        snaps = [x for x in plan.rules.lki.values() if x.card == host.id and x.zone.endswith(":battlefield")]
        if not snaps:
            return []
        kinds = _snapshot_card(plan, snaps[-1])[1].subtypes & CREATURE_TYPES
    out = [host.id] if host.zone.endswith(":battlefield") else []
    for c in plan.state.cards.values():
        if c.id != host.id and c.zone.endswith(":battlefield") and plan.in_game(c) and (ch := plan.ch(c)).is_creature and kinds & ch.subtypes:
            out.append(c.id)
    return out


def _named_source(plan: Plan, ctx: Context, who: str) -> _Source | None:
    """The damage source an instruction names — "target creature you control deals damage …"
    (``who``: "target", "target:<g>", "self", "host", "event", "ref:<b>"): the object as it is
    while it's still that object on the battlefield, else as it last existed (608.2h; 702.15c /
    702.2e for lifelink and deathtouch). None if nothing (or no longer anything) is named."""
    refs: list[tuple[str, str | None]] = []
    if who == "self":
        refs = [(ctx.get("source_card") or "", ctx.get("source_object"))]
    elif who == "target" or who.startswith("target:"):
        refs = [(t["id"], t.get("object_id")) for t in target_refs(ctx, who) if t["id"] in plan.state.cards]
    elif who == "host":
        refs = [(c, plan.oid(c)) for c in _cards(plan, ctx, "host")]
    elif who.startswith("obj:"):  # -- granted from object (wave 18F) -- "Blazing Torch deals 2 damage": the granter, as it last existed if it left
        refs = [(who[4:].rsplit(".", 1)[0], who[4:])]
    elif who == "event" or who.startswith("ref:"):
        name = context.EVENT if who == "event" else who[4:]
        refs = [(r.card, r.object_id) for r in context._object_refs(ctx, name, was=True)]
    for card_id, oid in refs[:1]:
        card = plan.state.cards.get(card_id)
        if card is not None and card.zone.endswith(":battlefield") and (oid is None or plan.oid(card) == oid):
            return _card_source(plan, card.id)
        snap = plan.rules.lki.get(oid or "")
        if snap is not None:
            from app.rules.triggers import _snapshot_card  # (triggers imports this module)

            _, ch = _snapshot_card(plan, snap)
            return _Source(snap.object_id, ch.keywords, ch, snap.controller,
                           snap.card if snap.card in plan.state.cards else None)
    return None


def _card_source(plan: Plan, cid: str) -> _Source:
    """A creature on the battlefield as a damage source (a fight, a bite)."""
    ch = plan.ch(plan.state.cards[cid])
    return _Source(plan.oid(cid), ch.keywords, ch, cid, cid)


_DAMAGE_KEYWORDS = frozenset({"lifelink", "deathtouch", "wither", "infect"})


def _deal(plan: Plan, ctx: Context, hits: list[tuple[_Source, str, int]], e: dict[str, Any] | None = None,
          *, before: tuple[tuple[str, list[str]], ...] = ()) -> bool:
    """Deal the damage of ``hits`` (source, a player or permanent, amount) all at once: one damage
    event batch (a fight's two creatures deal their damage simultaneously, 701.14a). Protection
    from the source prevents it (702.16e); then — replacement effects stage 2 (wave 2E),
    app/rules/replace.py — the replacement and prevention effects on each event (614, 615: "deals
    double that damage", "prevent 1 of that damage", "prevent all …", 615.7 shields), in the order
    the affected player chooses when it matters (616.1); wither / infect give -1/-1 counters
    (120.3d), infect poison to players (120.3b), deathtouch marks the creature for the next
    state-based check (702.2b), lifelink gains the source's controller that much (120.3f / 702.15b)
    — each result through its own replacement effects (120.4c). False while the affected player
    chooses: the primitive ``e`` runs again with the answers (nothing was done yet); ``before``:
    log lines for once the damage is dealt."""
    notes: list[tuple[str, list[str]]] = list(before)
    kept: list[dict[str, Any]] = []
    for src, key, want in hits:
        if want <= 0:
            continue
        ev = {"source_card": src.card, "source_oid": src.oid, "target": key, "amount": want, "combat": False,
              "src": replace.source_info(plan, src.card, src.oid, src.ch, ctx["controller"]),
              "kw": sorted(src.keywords & _DAMAGE_KEYWORDS), "lkey": src.key,
              # -- refused grants/replacements (wave 3R2) -- "The damage can't be prevented." (615.12)
              **({"unpreventable": True} if e is not None and e.get("unpreventable") else {})}
        if key not in plan.state.players and protection.protected_from(plan.ch(plan.state.cards[key]), src.ch) \
                and source_shields.protection_applies(plan, ev):  # (615.12: protection's prevention, 702.16e, too)
            notes.append((f"Protection prevents the damage to {plan.ch(plan.state.cards[key]).name}", [key]))
            continue
        # -- player shields (wave 5E) -- a player's protection (702.16e, 702.16j)
        from app.rules import player_shields

        if key in plan.state.players and player_shields.protected_from(plan, key, src.ch) is not None \
                and source_shields.protection_applies(plan, ev):
            notes.append((f"Protection prevents the damage to {plan.name(key)}", []))
            continue
        kept.append(ev)
    rerun = replace.rerun_then(ctx, e)
    answers = dict(ctx.get(replace.ANSWERS) or {})
    order = list(ctx.get(replace.SHIELDS) or [])
    out = replace.damage_outcome(plan, kept, answers=answers, order=order, ask=rerun is not None)
    if isinstance(out, replace.ShieldAsk):
        replace.ask_shield(plan, out, {**(rerun or {}), "answers": answers}, order)
        return False
    if not isinstance(out, replace.DamageOutcome):
        replace.ask(plan, out, answers, {**(rerun or {}), "order": order})
        return False
    for text, ids in notes:
        plan.note(text, ids, actor=ctx["controller"])
    if kept and ctx.get(DEALT_KEY) is not None and e is not None and e.get("dealt_as"):
        # "a creature dealt damage this way" (the objects actually dealt damage: after prevention)
        ctx[DEALT_KEY][e["dealt_as"]] = [ev["target_oid"] for ev in out.events if ev.get("target_oid")]
    if e is not None and e.get("bind_excess"):  # -- as long as (wave 9B) -- 120.10 (read before the damage is recorded)
        context.bind_amount(ctx, e["bind_excess"], _this_way.excess_of(plan, out.events))
    if e is not None and e.get("bind_hit"):  # -- if you do (wave 10C) -- "If a Dragon is dealt damage this way" (this_way.hits)
        context.bind_amount(ctx, e["bind_hit"], _this_way.hits(plan, ctx, out.events, e["hit_is"]))
    replace.do_damage(plan, out, actor=ctx["controller"], combat=False)
    if e is not None and e.get("bind_dealt"):  # -- if you do (wave 5G) -- "the damage dealt this way" (this_way.damage_dealt)
        context.bind_amount(ctx, e["bind_dealt"], sum(max(0, int(ev["amount"])) for ev in out.events))
    return True


DEALT_KEY = "dealt"  # -- replacement effects stage 2 (wave 2E) -- ctx: binding -> objects a damage effect dealt damage to


def damage(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """One damage instruction — or, with ``with_next``, one sentence naming several recipients
    ("~ deals 1 damage to each creature and each player"): all of it is dealt at once, one
    simultaneous damage event (120, 608.2: one instruction), not one batch per recipient group."""
    effects = ctx.get("effects") or []
    k = int(ctx.get("next") or 0)
    chain = [e]
    if replace.rerun_then(ctx, e) is not None:
        while chain[-1].get("with_next") and k + len(chain) - 1 < len(effects) \
                and effects[k + len(chain) - 1].get("do") == "damage":
            chain.append(effects[k + len(chain) - 1])
    if len(chain) == 1 or any(x.get("dealt_as") for x in chain):
        hits = _damage_hits(plan, ctx, e)
        return _deal(plan, ctx, hits, e) if hits else True
    hits = [h for x in chain for h in _damage_hits(plan, ctx, x)]
    done = _deal(plan, ctx, hits, e) if hits else True
    if done:
        ctx["next"] = k + len(chain) - 1  # (the joined instructions are done too)
    return done


def _damage_hits(plan: Plan, ctx: Context, e: dict[str, Any]) -> list[tuple[_Source, str, int]]:
    """Noncombat damage from the source (120.3): life loss for players, marked damage for
    creatures, loyalty loss for planeswalkers; lifelink and deathtouch of the source apply. With
    ``src`` ("target", "target:<g>", "host", "self", "ref:…"), the named creature is the source
    ("target creature you control deals damage equal to its power to target creature you don't
    control": the biting creature's lifelink and deathtouch count, 120.3f, 702.2b; nothing is
    dealt if it's gone and has no last known information)."""
    shares = divided(ctx, e)  # 601.2d: each target's share, as divided when it was put on the stack
    # -- damage sized by a count (wave 4E) -- an amount read for each player dealt damage (app/rules/sized_damage.py):
    # every player's number determined at once, as the effect is applied (608.2h)
    per_player = shares is None and sized_damage.has_per_player(e["n"])
    n = 0 if shares is not None or per_player else _amount(plan, ctx, e["n"])
    players = _players(plan, ctx, e["who"])
    each_player = {p: _amount(plan, {**ctx, "recipient": p}, e["n"]) for p in players} if per_player else {}

    def amount(key: str) -> int:
        if per_player:
            return each_player.get(key, 0)
        return shares.get(key, 0) if shares is not None else n
    cards = _cards(plan, ctx, e["who"])
    _remember(plan, ctx, e, cards)
    if str(e.get("src") or "").startswith("each:"):
        # -- sized amounts (wave 3D) -- "Each creature you control deals damage equal to its power to target creature":
        # every one is a damage source (its own lifelink and deathtouch count), all dealt at once (120.3, 608.2h)
        hits: list[tuple[_Source, str, int]] = []
        for sid in selectors.candidates(plan, selectors.from_key(e["src"][5:]), ctx["controller"], ctx.get("source_card")):
            each = _amount(plan, {**ctx, "each_source": sid}, e["n"])
            if each > 0:
                # (wave 4E: "Each creature deals damage to itself equal to its power": its own damage, to itself;
                # "… to each other creature": other than the creature dealing it)
                keys = [plan.state.cards[sid].controller] if e.get("to") == "controller" else \
                    [sid] if e["who"] == "itself" else [*_other_than(plan, ctx, e, cards, sid), *players]  # (wave 24D: "to its controller")
                hits += [(_card_source(plan, sid), key, each) for key in keys]
        return hits
    if e.get("src_many"):
        # -- as long as (wave 9B) -- "Up to two target creatures you control each deal damage equal to their power to …": every
        # creature of the group that is still a legal target is a source, dealing its own power (120.3, 608.2h), all at once
        many: list[tuple[_Source, str, int]] = []
        for sid in dict.fromkeys([*_cards(plan, ctx, e["src"]), *(_cards(plan, ctx, e["src2"]) if e.get("src2") else [])]):
            each = _amount(plan, {**ctx, "each_source": sid}, e["n"])
            if each > 0:
                many += [(_card_source(plan, sid), key, each) for key in [*cards, *players]]
        return many
    if e.get("src"):
        src = _named_source(plan, ctx, e["src"])
        if src is None:
            plan.note(f"{ctx.get('name') or 'It'}: the creature that would deal the damage is gone", actor=ctx["controller"])
            return []
        if src.card is not None:  # (wave 4E: "target creature deals damage … to each other creature": other than it)
            cards = _other_than(plan, ctx, e, cards, src.card)
    else:
        src = _ability_source(plan, ctx)
    if shares is None and not per_player and n <= 0:
        return []
    if e.get("dealt_as"):  # -- replacement effects stage 2 (wave 2E): "dealt damage this way" --
        ctx.setdefault(DEALT_KEY, {})[e["dealt_as"]] = []
    if e.get("excess"):  # -- refused zones/sized (wave 3R4) -- "excess damage is dealt to that creature's controller instead"
        return _excess_hits(plan, src, [(src, key, amount(key)) for key in [*cards, *players]], e["excess"])
    return [(src, key, amount(key)) for key in [*cards, *players]]


# -- damage sized by a count (wave 4E) --
def _other_than(plan: Plan, ctx: Context, e: dict[str, Any], cards: list[str], source_card: str) -> list[str]:
    """"Each other creature" when a named object deals the damage (a bite, "each creature … deals damage equal
    to its power to each other creature"): the creatures other than the one dealing it, not other than the
    spell or ability's own source."""
    who = str(e.get("who") or "")
    if not who.startswith(selectors.PREFIX) or not selectors.from_key(who).other:
        return cards
    return selectors.candidates(plan, selectors.from_key(who), ctx["controller"], source_card)


def _controlled_by(plan: Plan, ctx: Context, who: str) -> list[str]:
    """"each creature that player controls": "controlled:<player reference>|<selector key>"."""
    players, _, key = who[len("controlled:"):].partition("|")
    if players == "target:0" and not ctx.get("groups"):
        players = "target"  # (one target group: the spell's plain target)
    owners = set(_players(plan, ctx, players))
    return [c for c in selectors.candidates(plan, selectors.from_key(key), ctx["controller"], ctx.get("source_card"))
            if plan.state.cards[c].controller in owners]
# -- end damage sized by a count (wave 4E) --


def _excess_hits(plan: Plan, src: _Source, hits: list[tuple[_Source, str, int]], when: str) -> list[tuple[_Source, str, int]]:
    """-- refused zones/sized (wave 3R4) -- 120.4a: the damage event is modified first: what is in excess of lethal
    damage to the creature (its toughness less the damage already marked on it; with a deathtouch source any
    damage beyond 1 is excess, 702.2c) goes to its controller instead. ``when`` "trample": only if the creature
    dealing it has trample (as it is, or as it last existed: 608.2h). A planeswalker's is what exceeds its loyalty, a
    battle's its defense; a permanent of several of those types: the greatest (120.4a)."""
    if when == "trample" and "trample" not in src.keywords:
        return hits
    out: list[tuple[_Source, str, int]] = []
    for s_, key, n in hits:
        card = plan.state.cards.get(key)
        ch = plan.ch(card) if card is not None else None
        if card is None or ch is None or not card.zone.endswith(":battlefield"):
            out.append((s_, key, n))
            continue
        amounts = []
        if ch.is_creature and ch.pt is not None:
            left = max(0, ch.pt[1] - card.damage)
            amounts.append(n - (min(left, 1) if "deathtouch" in s_.keywords else left))
        if "Planeswalker" in ch.types:
            amounts.append(n - card.counters.get("loyalty", 0))
        if "Battle" in ch.types:
            amounts.append(n - card.counters.get("defense", 0))
        excess = max(0, max(amounts, default=0))
        if excess and card.controller in plan.live():
            out += [(s_, key, n - excess), (s_, card.controller, excess)]
        else:
            out.append((s_, key, n))
    return [h for h in out if h[2] > 0]


def fight(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.14: ``who`` fights ``with``: each deals damage equal to its power to the other, at
    once (701.14a, one damage batch; not combat damage, 701.14d). Nothing happens if either isn't
    on the battlefield or isn't a creature any more, or was an illegal target (701.14b: illegal
    targets were dropped on resolution; "up to one target" with none chosen: nothing to fight).
    A creature fighting itself deals damage equal to twice its power to itself (701.14c)."""
    a = _cards(plan, ctx, e["who"].replace("pair:", "target:"))  # (wave 26D: "pair:N" = the ability's Nth chosen group, app/rules/fight_pair.py)
    b = _cards(plan, ctx, e["with"].replace("pair:", "target:"))
    _remember(plan, ctx, e, a)
    if len(a) != 1 or len(b) != 1:
        plan.note(f"{ctx.get('name') or 'It'}: no fight (one of the creatures is gone or wasn't chosen)", actor=ctx["controller"])
        return True
    pair = []
    for cid in (a[0], b[0]):
        card = plan.state.cards[cid]
        ch = plan.ch(card)
        if not card.zone.endswith(":battlefield") or not ch.is_creature:
            plan.note(f"{ctx.get('name') or 'It'}: no fight ({ch.name or 'it'} isn't a creature on the battlefield)",
                      actor=ctx["controller"])
            return True
        pair.append((cid, max(0, ch.pt[0]) if ch.pt is not None else 0))
    (ca, pa), (cb, pb) = pair
    fights = (f"{plan.ch(plan.state.cards[ca]).name} fights {plan.ch(plan.state.cards[cb]).name}", [ca, cb])
    if e.get("dealt_as"):  # -- replacement effects stage 2 (wave 2E): "dealt damage this way" --
        ctx.setdefault(DEALT_KEY, {})[e["dealt_as"]] = []
    return _deal(plan, ctx, [(_card_source(plan, ca), cb, pa), (_card_source(plan, cb), ca, pb)], e, before=(fights,))


def choose_targets(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Choose up to one target creature." — only names its targets (chosen on casting, 601.2c)
    for the sentences that follow ("That creature can't block this turn"): nothing to do here."""
    return True


def _stat_label(v: int) -> str:
    return f"{v:+d}"


def pump(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"… gets +N/+N until end of turn" (layer 7c). ``p`` / ``t`` are ints or value expressions
    ("+X/+0", "+1/+1 for each creature you control", "-X/-X where X is …": app/rules/values.py),
    read once as the effect begins (611.2d, 608.2h) — unlike a static's "for each", never again."""
    cards = _cards(plan, ctx, e["who"])
    _remember(plan, ctx, e, cards)
    affected = [plan.oid(c) for c in cards]  # locked in now (611.2c)
    if affected:
        # (a literal keeps its sign: values.evaluate reads a *count*, never negative, 107.1b)
        p = e["p"] if isinstance(e["p"], int) else values.evaluate_signed(plan, ctx, e["p"])
        t = e["t"] if isinstance(e["t"], int) else values.evaluate_signed(plan, ctx, e["t"])
        layers.add_effect(plan, affected=affected, layer="7c", source=ctx.get("source_object"), controller=ctx["controller"],
                          power=p, toughness=t, label=f"{_stat_label(p)}/{_stat_label(t)} until end of turn ({ctx.get('name', '')})")
        _mark(plan, _cards(plan, ctx, e["who"]), f"{_stat_label(p)}/{_stat_label(t)}")
    return True


def grant(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"… gains flying [and lifelink] until end of turn" (layer 6, 613.1f), and "… loses flying
    until end of turn" (``remove``: keywords taken away, later than any static that grants
    them — 613.7: this effect's timestamp is now).

    -- quoted grants (wave 2D, app/rules/granted.py) -- ``abilities``: quoted abilities the objects
    gain too ("gains trample and "{G}: Regenerate this creature."", "It gains "If this creature would
    die, exile it instead.""), in the same layer-6 effect: one timestamp (613.7b), the set of objects
    fixed now (611.2c), and only permanents on the battlefield gain one (611.2e). ``duration``: the
    game when the text states none (611.2a); an ``until`` wrapper (app/rules/delayed.py) sets any other."""
    cards = _cards(plan, ctx, e["who"])
    _remember(plan, ctx, e, cards)
    keywords = list(e.get("keywords") or [])
    removed = list(e.get("remove") or [])
    abilities = list(e.get("abilities") or [])
    if abilities:
        permanents = [c for c in cards if plan.state.cards[c].zone.endswith(":battlefield")]
        if len(permanents) < len(cards):
            plan.note(f"{ctx.get('name') or 'The effect'}: only a permanent on the battlefield gains an ability", actor=ctx["controller"])
        cards = permanents
    if cards and (keywords or removed or abilities):
        words = [*keywords, *(f"loses {k}" for k in removed), *(f'"{a}"' for a in abilities)]
        duration = e.get("duration", "end_of_turn")
        when = "until end of turn" if duration == "end_of_turn" else "for the rest of the game"
        layers.add_effect(plan, affected=[plan.oid(c) for c in cards], layer="6", source=ctx.get("source_object"),
                          controller=ctx["controller"], add_keywords=tuple(keywords), remove_keywords=tuple(removed),
                          duration=duration, label=f"{', '.join(words)} {when}", add_abilities=abilities)
        marker = ", ".join([*(k.capitalize() for k in keywords), *(f"No {k}" for k in removed),
                            *(f'Gains "{a}"' for a in abilities)])
        _mark(plan, cards, marker, value="Ability" if abilities and not (keywords or removed) else None,
              text="until end of turn" if duration == "end_of_turn" else "as long as it's on the battlefield")
    return True


# (the table marker's value is at most 20 characters: app/game/actions.py AddEffect.value)
RESTRICTION_LABELS = {"cant_block": "Can't block", "cant_attack": "Can't attack", "cant_attack_or_block": "Can't attack/block",
                      "cant_be_blocked": "Can't be blocked", "must_attack": "Attacks if able",
                      "assign_none": "Assigns no combat damage"}


# -- attack restrictions (wave 32B) -- the marker of "can't attack you …" names the player (the rule's own text is "cant_attack_player:<id>")
ATTACK_LABELS = {"cant_attack_player": "Can't attack {}", "cant_attack_player_pw": "Can't attack {} or their planeswalkers",
                 "cant_attack_player_perm": "Can't attack {} or their permanents", "attack_tax": "Attacking {} costs extra",
                 "attack_tax_pw": "Attacking {} costs extra"}


def _restriction_label(plan: Plan, rule: str) -> str:
    name, _, rest = rule.partition(":")
    who = rest.split(":")[0]
    return ATTACK_LABELS[name].format(plan.name(who)) if name in ATTACK_LABELS and who in plan.state.players else RESTRICTION_LABELS.get(rule, rule)


_GROUPS = {"each_creature": selectors.Selector(types=("Creature",)).key(),
           "creatures_you_control": selectors.Selector(types=("Creature",), controller="you").key()}


def restrict(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"… can't block this turn", "… can't be blocked this turn": a rule-modifying effect, ending
    at cleanup (514.2). It doesn't change characteristics or control, so its set of objects isn't
    locked in (611.2c): "Creatures can't block this turn" also stops a creature that enters later.
    A named object (target, "it", self, host) stays that one object (a new object isn't it, 400.7).

    -- quoted grants (wave 2D) -- ``locked``: the restriction a granted ability states ("gains "This
    creature can't be blocked."", app/rules/granted.py ``rules_of``) is an ability: the objects it
    affects are the ones there as it begins, even for a group (611.2c). ``duration``: the game when
    the text states none (611.2a)."""
    who = _GROUPS.get(e["who"], e["who"])
    cards = _cards(plan, ctx, who)
    _remember(plan, ctx, e, cards)
    e = {**e, "rules": [block_effects.args(ctx, r.replace("@you", ctx["controller"])
                        .replace("@src", f"e{plan.rules.timestamp + 1}" if r.startswith("block_extra:") else ctx.get("source_object") or ""))
                        for r in e["rules"]]}  # (@src: wave 7E; wave 13B: each "can block an additional creature" adds up, 509.1a; @it, @t1: wave 30P)  # -- combat (wave 5C) -- (Kardur)
    group = who.startswith(selectors.PREFIX) and not e.get("locked")
    duration = e.get("duration", "end_of_turn")
    if who.startswith("controlled:") and not e.get("locked"):  # -- review (wave 26A) -- "Creatures target player controls attack this
        # turn if able" / "can't block this turn": the player is fixed as it resolves, the creatures are not (611.2c): one group per player,
        # read through the selector's "player:<id>" controller, so a creature that comes under their control later this turn is affected too
        players, _, key = who[len("controlled:"):].partition("|")
        for pid in _players(plan, ctx, "target" if players == "target:0" and not ctx.get("groups") else players):
            mine = selectors.replace(selectors.from_key(key), controller=f"player:{pid}").key()
            made = layers.add_effect(plan, affected=[], layer="6", source=ctx.get("source_object"), controller=ctx["controller"],
                                     imposes=tuple(e["rules"]), label=", ".join(e["rules"]), who=mine, source_card=ctx.get("source_card"),
                                     duration="end_of_next_turn" if duration == "their_turn" else duration)
            if duration == "their_turn":  # -- attack restrictions (wave 32B) -- "that player can't attack you … during their next turn" (611.2a):
                # wave 32C's "end of next turn" with that player's turn (it ends in the cleanup of their next turn, 514.2; a departed player's with them, 800.4m)
                made.until_player, made.turn = pid, plan.state.turn.number
                plan.note(f"{plan.name(pid)}: {', '.join(_restriction_label(plan, r) for r in e['rules'])} during their next turn", actor=ctx["controller"])
    elif cards or group:
        layers.add_effect(plan, affected=[] if group else [plan.oid(c) for c in cards], layer="6",
                          source=ctx.get("source_object"), controller=ctx["controller"], imposes=tuple(e["rules"]),
                          label=", ".join(e["rules"]), who=who if group else None, source_card=ctx.get("source_card"),
                          duration=duration)
    if cards and duration != "their_turn":  # (-- attack restrictions (wave 32B) -- a player's next turn: no marker on the creatures there now, the group is the player's)
        _mark(plan, cards, ", ".join(_restriction_label(plan, r) for r in e["rules"]),
              text={"end_of_turn": "until end of turn", "end_of_combat": "this combat"}.get(duration, "as long as it's on the battlefield"))
    return True


def _mark(plan: Plan, cards: list[str], label: str, *, value: str | None = None, text: str = "until end of turn") -> None:
    """The visible table marker for an engine effect (it goes away at cleanup with the effect)."""
    # (AddEffect: the name is at most 60 characters, the short value 20 — "Deathtouch, Indestructible")
    value = value if value is not None else label if len(label) <= 20 else label[:19] + "…"
    for cid in cards:
        plan.do({"type": "add_effect", "card_ids": [cid], "name": label[:60], "value": value, "text": text})


def _can_regenerate(ctx: Context) -> bool:
    """False when the spell or ability says "It/They can't be regenerated"."""
    return not any(x.get("do") == "no_regen" for x in ctx.get("effects") or [])


def destroy(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    # The binding is every object the instruction was about ("Destroy target creature. Its
    # controller …" means the target's controller even if it was indestructible or regenerated)
    return _destroy_cards(plan, ctx, e, _cards(plan, ctx, e["who"]))


def _destroy_cards(plan: Plan, ctx: Context, e: dict[str, Any], cards: list[str]) -> bool:
    before = _remember(plan, ctx, e, cards)
    doomed = [c for c in cards if "indestructible" not in plan.ch(plan.state.cards[c]).keywords]
    doomed = regeneration.survivors(plan, doomed, can_regenerate=_can_regenerate(ctx), actor=ctx["controller"])
    if doomed:
        gone = {c: plan.oid(c) for c in doomed}
        plan.do({"type": "move", "card_ids": doomed, "to": {"zone": "graveyard"}}, actor=ctx["controller"])
        _destroyed(plan, gone)
    _moved(plan, ctx, e, before)
    return True


def _destroyed(plan: Plan, gone: dict[str, str]) -> None:
    """-- destroy events (wave 45C) -- 701.8a-b: these permanents (card -> the object it was) were destroyed: an effect's "destroy" that put them into their
    owner's graveyard (a replacement that sent one elsewhere, or a regeneration or an indestructible permanent, didn't destroy it). The event joins the
    batch of the move, so a permanent that left with them sees it (603.10a). ponytail: the state-based destruction (704.5g-h) isn't recorded, so the
    trigger grammar only reads a subject that can't be a creature (events.py)."""
    from app.game.rules_state import Event

    r = plan.rules
    for cid, oid in gone.items():
        card = plan.state.cards.get(cid)
        if card is None or card.zone.endswith(":graveyard"):  # (a token is gone from the graveyard once there: 111.7)
            r.events.append(Event(batch=r.batch, kind="designation", turn=plan.state.turn.number, counter="destroyed", card=cid, object_id=oid,
                                  player=plan.actor))


def exile(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    return exile_cards(plan, ctx, e, _from_zone(plan, e, _cards(plan, ctx, e["who"])))


def _from_zone(plan: Plan, e: dict[str, Any], cards: list[str]) -> list[str]:
    """-- review 32 -- "exile that card from your graveyard": only the cards still in that zone (language: "from_zone")."""
    z = e.get("from_zone")
    return [c for c in cards if plan.state.cards[c].zone.endswith(":" + z)] if z else cards


def exile_cards(plan: Plan, ctx: Context, e: dict[str, Any], cards: list[str]) -> bool:
    before = _remember(plan, ctx, e, cards)
    if cards:
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "exile"}}, actor=ctx["controller"])
    if e.get("link"):  # -- exiled with (wave 6D) -- 607.2a: what the linked ability will refer to
        from app.rules import exiled_with

        exiled_with.record(plan, ctx, _merged.pieces(plan, cards))  # (review (wave 18D): every card of a merged permanent, 730.3c)
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
    cards = keyword_actions.untap_stunned(plan, cards, ctx["controller"])  # -- wave 3F -- 122.1d stun counters
    if cards:
        plan.do({"type": "tap", "card_ids": cards, "tapped": False}, actor=ctx["controller"])
    return True


def player_counter(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    # -- replacement effects stage 2 (wave 2E): a player getting counters, through the counter
    # choke point ("If you would get one or more counters": Winding Constrictor) --
    n = max(0, _amount(plan, ctx, e["n"]))  # -- counters & designations (wave 3E): "that many {E}", "X rad counters" --
    puts = [(pid, e["counter"], n) for pid in _players(plan, ctx, e["who"]) if n]
    if not puts:
        return True
    return replace.put_counters(plan, puts, by=ctx["controller"], then=_then(ctx, e), ctx=ctx)


def scry(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.22a: look at the top N, put any number on the bottom in any order, the rest on top in
    any order. Asked as two private choices (which go to the bottom, then the order on top)."""
    return _look(plan, ctx, e, "bottom")


def surveil(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.25a: look at the top N, put any number into the graveyard, the rest on top in any order."""
    return _look(plan, ctx, e, "graveyard")


def _look(plan: Plan, ctx: Context, e: dict[str, Any], where: str) -> bool:
    pid = ctx["controller"]
    n = _amount(plan, ctx, e["n"])
    if where == "bottom" and n > 0 and (replaced := replace.keyword_replace(plan, ctx, e, "scry", pid, n=n)) is not None:
        return replaced  # -- keyword actions (wave 35C) -- "If you would scry a number of cards, draw that many cards instead." (Eligeth)
    top = plan.state.zones.get(zone_key(pid, "library"), [])[:n]
    if n > 0:  # -- this-turn history (wave 4D) -- 701.22b/d, 701.25c/d: N > 0 scries / surveils, even an empty library
        from app.rules import history

        history.note_look(plan, pid, "scry" if where == "bottom" else "surveil", len(top))
    if not top:
        return True
    options = [DecisionOption(id=cid, label=plan.state.cards[cid].name or "Card", card_id=cid) for cid in top]
    verb = "Scry" if where == "bottom" else "Surveil"
    dest = "the bottom of your library" if where == "bottom" else "your graveyard"
    decide(plan, player=pid, kind="choose_cards", prompt=f"{verb} {len(top)}: choose the cards to put into {dest} (the rest stay on top)",
           options=options, min_choices=0, max_choices=len(top),
           resume={"step": "look", "where": where, "cards": list(top), "ctx": ctx})
    return False


def create_token(plan: Plan, ctx: Context, e: dict[str, Any], *, then: dict[str, Any] | None = None) -> bool:
    """111: tokens are individual objects for the rules; identical ones may be *shown* as a pile.
    -- replacement effects stage 2 (wave 2E) -- Through the token choke point (app/rules/replace.py:
    614.16, 616.1 per creating player in APNAP order). ``then``: how a caller other than the
    resolver goes on after a paused choice (the resolver itself: its effects continue)."""
    t = e["token"]
    count = _amount(plan, ctx, e["n"])
    if count <= 0 and not e.get("more"):  # (wave 34C: a list of kinds is judged kind by kind below: "create X A tokens and two B tokens", X = 0)
        _remember(plan, ctx, e, [])
        return True
    requests: list[tuple[str, dict[str, Any], int, str | None, bool]] = []
    source = ctx.get("source_card") if ctx.get("source_card") in plan.state.cards else None
    # -- "this way" outcomes (wave 4A) -- "For each permanent destroyed this way, its controller creates …": each
    # player creates as many as they controlled, all in one batch (one simultaneous instruction, 101.4 / 616.1 APNAP)
    each: dict[str, int] | None = None
    if e.get("per_controller"):
        from app.rules import this_way

        each = this_way.by_controller(plan, ctx, e["per_controller"])
    # -- triggers (wave 5D) -- "create a 3/3 … token with deathtouch and a 3/3 … token with lifelink" (Wurmcoil Engine):
    # one instruction, so one batch of tokens entering together (701.7a, 603.2c)
    kinds = [(t, count, e.get("tapped"))] + [(m["token"], _amount(plan, ctx, m["n"]), m.get("tapped"))
                                             for m in e.get("more") or []]
    for t, count, tapped_by_creator in kinds:
        if count <= 0:
            continue
        # -- X sized by a count (wave 4K) -- "an X/X … token": X as the token is created, its printed P/T from then on (111.3)
        pt = {k: str(values.evaluate(plan, ctx, t[k])) if isinstance(t.get(k), dict) else t.get(k) for k in ("power", "toughness")}
        for pid in (list(each) if each is not None else _players(plan, ctx, e["who"])):
            if each is not None and pid not in plan.live():
                continue
            spec = {"name": t["name"], "power": pt["power"], "toughness": pt["toughness"],
                    "colors": t.get("colors") or [], "type_line": t["type_line"], "text": t.get("text") or ""}
            # a token enters tapped when its creator says so ("create a tapped …") or its own text does
            # (614.1d), never otherwise; its "enters with" counters follow (app/rules/replacements.py)
            tapped = (bool(tapped_by_creator) or replacements.token_enters_tapped(plan, pid, spec)) and not replacements.token_enters_untapped(plan, pid, spec)  # (wave 45A)
            requests.append((pid, spec, count * each[pid] if each is not None else count, source, tapped))
    # (the tokens are recorded as binding "as", the new objects they are: "they gain haste")
    if not requests:  # (every kind counted 0)
        _remember(plan, ctx, e, [])
        return True
    made = replace.create_token_batch(plan, requests, ctx=ctx, bind=e.get("as"), then=then or _then(ctx, e))
    return made is not None  # (None: the creating player chooses an order first, 616.1)


def add_counters(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    # -- replacement effects stage 2 (wave 2E): through the counter choke point (122.6, 614.16) --
    cards = _cards(plan, ctx, e["who"])
    _remember(plan, ctx, e, cards)
    shares = divided(ctx, e)
    if shares is not None:  # "distribute N counters among …" (601.2d): each target its share
        puts = [(cid, e["kind"], shares[cid]) for cid in cards if shares.get(cid)]
    else:
        # -- triggers (wave 30J) -- "put a +1/+1 counter on it for each other Zombie that entered the battlefield under your control this turn"
        # (Geralf): "other" is than IT, the object the counters go on, not than the ability's source
        counted = e["who"] == "event" and len(cards) == 1 and isinstance(e["n"], dict) and "count" in e["n"]
        n = _amount(plan, {**ctx, "other_than": cards[0]} if counted else ctx, e["n"])
        puts = [(cid, e["kind"], n) for cid in cards] if n else []
        for more in e.get("also") or ():  # -- counters (wave 5H) -- several kinds at once (one event, 122.6)
            k = _amount(plan, ctx, more["n"])
            more_cards = _cards(plan, ctx, more["who"]) if more.get("who") else cards
            puts += [(cid, more["kind"], k) for cid in more_cards] if k else []
    if not puts:
        return True
    return replace.put_counters(plan, puts, by=ctx["controller"], then=_then(ctx, e), ctx=ctx)


def remove_counters(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Remove N … counters from …" (as many as there are, 122.8)."""
    n = _amount(plan, ctx, e["n"])
    cards = _cards(plan, ctx, e["who"])
    _remember(plan, ctx, e, cards)
    for cid in cards:
        if e["kind"] == "*":  # -- attached events (wave 25D) -- "remove all counters from it": every kind it has
            for kind, have in sorted(plan.state.cards[cid].counters.items()):
                if have > 0 and n:
                    plan.do({"type": "counter", "card_ids": [cid], "kind": kind, "delta": -min(have, n)}, actor=ctx["controller"])
            continue
        have = plan.state.cards[cid].counters.get(e["kind"], 0)
        if have and n:
            plan.do({"type": "counter", "card_ids": [cid], "kind": e["kind"], "delta": -min(have, n)}, actor=ctx["controller"])
    return True


# -- counters (wave 5H) --
def double_counters(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.10e: "double the number of [kind] counters on …" gives each object as many more of that kind as it has
    ("each kind of counter": every kind it has) — counters put, all at once, through the choke point (122.6, 614.16:
    Hardened Scales and Doubling Season apply)."""
    cards = _cards(plan, ctx, e["who"])
    _remember(plan, ctx, e, cards)
    puts = []
    for cid in cards:
        have = plan.state.cards[cid].counters
        kinds = [k for k, v in have.items() if v > 0] if e["kind"] == "*" else [e["kind"]]
        puts += [(cid, k, have.get(k, 0)) for k in kinds if have.get(k, 0) > 0]
    if not puts:
        return True
    return replace.put_counters(plan, puts, by=ctx["controller"], then=_then(ctx, e), ctx=ctx)


def lki_counters(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """122.8: "put its counters on …" after the object left: the same number of each kind it had as it last
    existed (603.10a) are put — not moved — through the choke point (614.16 applies). Nothing to read: nothing put."""
    got = values._object(plan, ctx, e["from"])
    cards = _cards(plan, ctx, e["who"])
    _remember(plan, ctx, e, cards)
    had = {k: n for k, n in sorted(got[0].counters.items()) if n > 0} if got is not None else {}
    puts = [(cid, k, n) for cid in cards for k, n in had.items()]
    if not puts:
        return True
    return replace.put_counters(plan, puts, by=ctx["controller"], then=_then(ctx, e), ctx=ctx)


# -- end counters (wave 5H) --


def proliferate(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.34a: choose any number of permanents and/or players that have a counter; each gets one
    more of each kind it already has."""
    options = [DecisionOption(id=c.id, label=f"{c.name} ({', '.join(f'{v} {k}' for k, v in c.counters.items() if v)})", card_id=c.id)
               for c in plan.state.cards.values()
               if c.zone.endswith(":battlefield") and plan.in_game(c) and any(v > 0 for v in c.counters.values())]
    # (review 24B: speed is a player resource but not a counter, 702.179: proliferate never touches it)
    options += [DecisionOption(id=pid, label=f"{plan.name(pid)} ({', '.join(f'{v} {k}' for k, v in p.resources.items() if v > 0 and k != 'speed')})")
                for pid, p in plan.state.players.items() if pid in plan.live() and any(v > 0 and k != "speed" for k, v in p.resources.items())]
    from app.game.rules_state import emit

    if not options:
        emit(plan.state, "designation", counter="proliferate", player=ctx["controller"])  # -- trigger tail (wave 15B) --
        return True
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt="Proliferate: choose permanents and players",
           options=options, min_choices=0, max_choices=len(options), resume={"step": "proliferate", "ctx": ctx})
    return False


def resume_proliferate(plan: Plan, d: Any, chosen: list[str]) -> None:
    # -- replacement effects stage 2 (wave 2E): all at once, through the counter choke point
    # (701.34a: "give each one additional counter of each kind"; 614.16) --
    ctx = d.resume["ctx"]
    puts: list[tuple[str, str, int]] = []
    for x in chosen:
        if x in plan.state.cards:
            puts += [(x, kind, 1) for kind, v in plan.state.cards[x].counters.items() if v > 0]
        elif x in plan.state.players:
            puts += [(x, kind, 1) for kind, v in plan.state.players[x].resources.items() if v > 0 and kind != "speed"]
    from app.game.rules_state import emit

    emit(plan.state, "designation", counter="proliferate", player=d.player)  # -- trigger tail (wave 15B) -- 701.34a: "you proliferate"
    if puts and not replace.put_counters(plan, puts, by=d.player, then={"do": "continue", "ctx": ctx}):
        return  # an order to choose first (616.1)
    continue_effects(plan, ctx)


def regenerate(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.19: "Regenerate ~" / "Regenerate target creature": a shield for this turn."""
    cards = _cards(plan, ctx, e["who"])
    _remember(plan, ctx, e, cards)
    for cid in cards:
        regeneration.add_shield(plan, cid)
        _mark(plan, [cid], "Regeneration shield")
    return True


def no_regen_turn(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """-- can't regenerate (wave 19E) -- "Target creature can't be regenerated this turn." (701.19c: shields aren't applied to it)."""
    if e.get("dealt"):  # -- regeneration (wave 22C) -- "A creature dealt damage this way": the objects damage was actually dealt to
        plan.rules.no_regen.extend(list((ctx.get(DEALT_KEY) or {}).get(e["dealt"]) or []))
        return True
    for cid in _cards(plan, ctx, e["who"]):
        if not e.get("types") or set(e["types"]) & plan.ch(plan.state.cards[cid]).types:
            plan.rules.no_regen.append(plan.oid(cid))
    return True


def animate(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Layer 4: "~ becomes an artifact creature until end of turn" (a crewed Vehicle, 702.122)."""
    cards = _cards(plan, ctx, e["who"])
    if cards:
        layers.add_effect(plan, affected=[plan.oid(c) for c in cards], layer="4", source=ctx.get("source_object"),
                          controller=ctx["controller"], add_types=tuple(e["types"]),
                          label=f"{' '.join(e['types'])} until end of turn ({ctx.get('name', '')})")
        _mark(plan, cards, "Crewed" if e.get("crewed") else " ".join(e["types"]))
        if e.get("crewed"):  # -- crew & saddle (wave 23D) -- 702.122e: "becomes crewed" is its crew ability resolving
            from app.game.rules_state import emit

            for c in cards:
                emit(plan.state, "crewed", object_id=plan.oid(c), card=c, player=plan.state.cards[c].controller)
    return True


def renown(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.112: if it isn't renowned, N +1/+1 counters and it becomes renowned."""
    for cid in _cards(plan, ctx, "self"):
        oid = plan.oid(cid)
        if oid in plan.rules.renowned:
            continue
        # -- replacement effects stage 2 (wave 2E): the counter choke point; after a choice the
        # primitive runs again (nothing was done yet) --
        if not replace.put_counters(plan, [(cid, "+1/+1", int(e["n"]))], by=ctx["controller"],
                                    then=replace.rerun_then(ctx, e), ctx=ctx):
            return False
        plan.rules.renowned.append(oid)
        _mark(plan, [cid], "Renowned")
        # -- becomes monstrous (wave 6D) -- "Whenever a creature you control becomes renowned" (702.112b)
        from app.game.rules_state import emit

        emit(plan.state, "designation", counter="renowned", card=cid, object_id=oid, player=plan.state.cards[cid].controller)
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


def return_any(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """-- activated sweep (wave 26C) -- "Sweep — Return any number of Plains you control to their owner's hand." (107.1c: any number
    includes none; the controller chooses as it resolves, 608.2d). The number returned is the X the rest of the spell reads
    ("for each Plains returned this way", 608.2c: what the instruction actually did)."""
    pid = ctx["controller"]
    pool = [c.id for c in plan.state.cards.values() if c.zone == zone_key(pid, "battlefield") and c.controller == pid
            and plan.in_game(c) and e["land"] in plan.ch(c).subtypes]
    ctx["x"] = 0
    if not pool:
        return True
    decide(plan, player=pid, kind="choose_cards", prompt=f"Return any number of {e['land']}s you control to your hand",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in pool],
           min_choices=0, max_choices=len(pool), resume={"step": "return_any", "ctx": ctx})
    return False


def resume_return_any(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx = d.resume["ctx"]
    ctx["x"] = len(chosen)
    if chosen:
        _return_to_hands(plan, chosen, d.player)
    continue_effects(plan, ctx)


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
    # -- granted casts (wave 29B) -- any half / face (709.3, 712.11b, 715.3)
    from app.rules import granted_casts

    return granted_casts.ask(plan, ctx, player=card.owner, cid=cid, head="The last time counter was removed", no="Leave it exiled", play=True)


def leave_uncast(plan: Plan, player: str, cid: str, how: str | None, group: Any = ()) -> None:
    """The card the engine offered to cast isn't cast (declined, or nothing can be cast: granted_casts.ask): the grant ends and ``how`` says where it
    goes -- "bottom" (cascade), "ripple" (stays with the revealed cards, which the ability puts on the bottom in one order), "hand" (discover, 701.57a), "graveyard" (madness), "miracle" (stays in the hand), else it stays exiled.
    ``group``: the cards put on the bottom before the question (cascade)."""
    r = plan.rules
    r.free_casts = [c for c in r.free_casts if c != cid]
    r.free_cast_faces.pop(cid, None)
    r.suspended = [c for c in r.suspended if c != cid]
    r.alt_costs.pop(cid, None)
    if how == "ripple":  # -- free-cast cleanup (wave 30A) -- 702.60a: it stays on top with the revealed cards, which the ability goes on to put on the bottom
        return
    if how == "miracle":  # -- casting extras (wave 18E) -- 702.94a: it stays in the hand (and is hidden again)
        from app.rules import miracle

        miracle.done(plan, cid)
        plan.note(f"{plan.name(player)} keeps it in their hand")
        return
    if how == "graveyard" and cid in plan.state.cards:  # madness
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "graveyard"}}, actor=player)
        return
    if how == "hand" and cid in plan.state.cards:  # -- discover (wave 9A) -- 701.57a
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "hand"}}, actor=player)
        plan.note(f"{plan.name(player)} puts it into their hand")
        return
    if how == "bottom" and cid in plan.state.cards:  # cascade: it joins the others
        import secrets

        owner = plan.state.cards[cid].owner
        library = plan.state.zones.get(zone_key(owner, "library"), [])
        k = len(group)
        # -- granted casts (wave 29B) -- 702.85a: "put all cards exiled this way that weren't cast on the bottom of your library in a random order":
        # the others were put there before the question, in a random order; this one lands anywhere among them (so all are in a random order)
        at = len(library) - k + (plan.rng or secrets.SystemRandom()).randint(0, k) if k and set(library[-k:]) == set(group) else None
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": owner, "zone": "library"}, "position": "bottom",
                 **({"index": at} if at is not None else {})}, actor=player)
        plan.note(f"{plan.name(player)} puts it on the bottom of their library")
    else:
        plan.note(f"{plan.name(player)} leaves it exiled")


def resume_suspend_cast(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game import actions as A
    from app.rules.casting import cast_spell

    cid = d.resume["card"]
    r = plan.rules
    # -- granted casts (wave 29B) -- "yes" casts the card as it is, "yes@1" its second half / back face (granted_casts.ask)
    answer, _, at = chosen[0].partition("@")
    face = int(at) if at else None
    from app.rules import cast_limits, land_plays, permissions
    from app.rules import characteristics as chars

    card = plan.state.cards.get(cid)
    if answer == "yes" and card is not None and chars.as_cast(card, plan.info, face).is_land:
        # 702.62a: a suspended card is *played* ("you may play it without paying its mana cost"): a land face (712.12) is played as the ability resolves
        r.free_casts = [c for c in r.free_casts if c != cid]
        r.suspended = [c for c in r.suspended if c != cid]
        if land_plays.open_for_effect(plan.state, d.player, plan.info):  # (review 29B: 305.2b / 305.3, an older save's plain "yes" wasn't checked)
            permissions.play_land_now(plan, d.resume["ctx"], {"n": 1}, cid, face)
            return
        plan.note(f"{plan.name(d.player)} can't play a land now (305.2b, 305.3)", actor=d.player)
        answer = "no"
    ripple = d.resume.get("decline") == "ripple"  # -- free-cast cleanup (wave 30A) -- 702.60a: the ability isn't over, it puts the rest on the bottom
    if not ripple:
        finish(plan, d.resume["ctx"])
    # -- cast limits (wave 5E) -- a prohibited cast (601.3) can't begin: as if declined (a pending choice of an older save wasn't checked)
    # (review 29B: a plain "yes" casts a split card's / an adventurer's first half too, chars.as_cast)
    one = face if face is not None else 0 if card is not None and (chars.is_two_spell_card(card, plan.info)
                                                                  or len(permissions.play_faces(plan, card)) > 1) else None
    if answer == "yes" and (limited := cast_limits.free_cast_blocked(plan, d.player, cid, one)) is not None:
        plan.note(limited, actor=d.player)
        answer = "no"
    if answer != "yes":
        leave_uncast(plan, d.player, cid, d.resume.get("decline"), d.resume.get("group") or ())
        if ripple:
            continue_effects(plan, d.resume["ctx"])
        return
    if face:
        r.free_cast_faces[cid] = face  # casting.cast_free takes only this one
    if r.decision is not None:
        plan.note("Cast it without paying its mana cost when the pending choice is done")
        return
    if r.free_cast_then is None:  # (review 29B) a cast abandoned on the way (its payment cancelled: 601.2, nothing was paid) is a card not cast:
        # it goes where the declined card goes (permissions.free_cast_abandoned), never left in exile with its grant
        r.free_cast_then = {"card": cid, "ctx": None, "e": {}, **({"face": face} if face else {}),
                            "granted": {"player": d.player, "decline": d.resume.get("decline"), "group": list(d.resume.get("group") or ()),
                                **({"ctx": d.resume["ctx"]} if ripple else {})}}  # (ctx: permissions.free_cast_done goes on with the ability)
    r.priority = d.player
    prev = plan.actor
    plan.actor = d.player
    try:
        cast_spell(plan, A.CastSpell(card_id=cid, free=True, face=face))
    finally:
        plan.actor = prev


def bottom_at_random(plan: Plan, pid: str, cards: list[str], actor: str | None = None) -> list[str]:
    """-- review (wave 29B) -- "put … on the bottom of your library in a random order" (702.85a, 701.57a): the table's randomness, recorded in
    the move (replay is deterministic); one move, whose log line lists the cards by name, so the order isn't readable (401.4: a face-down spell's
    cascade puts the whole library back). Returns the order they went in (top to bottom). ``pid``: whose library; ``actor``: who puts them
    there (the library's owner unless given). (-- review 30 -- every "in a random order" goes through here: `rest_looked`, `rest_exiled`.)"""
    import secrets

    order = list(cards)
    (plan.rng or secrets.SystemRandom()).shuffle(order)
    for at in range(0, len(order), 250):  # (a move names at most 250 cards)
        plan.do({"type": "move", "card_ids": order[at:at + 250], "to": {"player": pid, "zone": "library"}, "position": "bottom"},
                actor=actor or pid)
    return order


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
    order = bottom_at_random(plan, pid, missed)
    if hit is None:
        plan.note("Cascade found nothing")
        return True
    # -- granted casts (wave 29B) -- "if the resulting spell's mana value is less" (702.85a): each half / face
    from app.rules import granted_casts

    return granted_casts.ask(plan, ctx, player=pid, cid=hit, head="Cascade", no="Put it on the bottom", decline="bottom", below=e["mv"],
                             group=order)


def ripple_split(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """-- static_other sweep (wave 17C) -- 702.60a: of the revealed cards, those with the spell's name may be cast; the others go on the
    bottom. Two or more copies revealed (a game with several of one card) is a choice this does not carry out: all stay on top."""
    from app.rules import characteristics as chars

    looked = ctx.get("looked") or []
    # -- granted casts (wave 29B) -- 201.2a: the same name is one name in common (a split card has two, 709.4a; a nameless face-down spell has none)
    spell_names = {n for n in e["name"].split(" // ") if n}
    same = [c for c in looked if spell_names & set(chars.of(plan.state.cards[c], plan.info).name.split(" // "))]
    if len(same) > 1:
        plan.note(f"Ripple: several cards named {e['name']} were revealed; cast them by hand and put the others on the bottom")
        ctx["looked"] = []
        return True
    ctx["ripple_same"] = same  # (-- free-cast cleanup (wave 30A) -- it stays among the looked cards: "all revealed cards not cast this way")
    return True


def ripple_cast(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.60a: the revealed card with the spell's name may be cast without paying its mana cost. -- free-cast cleanup (wave 30A) -- A card not cast
    (declined, can't be cast, cast cancelled) stays among the revealed cards, which ``rest_looked`` then puts on the bottom in the player's order."""
    same = ctx.pop("ripple_same", None) or []
    if not same:
        return True
    from app.rules import granted_casts  # -- granted casts (wave 29B) --

    return granted_casts.ask(plan, ctx, player=ctx["controller"], cid=same[0], head="Ripple", no="Put it on the bottom", decline="ripple")


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
    if e.get("sacrifice"):  # -- keywords (wave 15E) -- blitz 702.152a: "Sacrifice it at the beginning of the next end step" (701.21a)
        if card.controller == ctx["controller"]:
            _sacrifice_cards(plan, [card.id], ctx["controller"])
        return True
    plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": e["to"]}}, actor=ctx["controller"])
    if e.get("warp"):  # -- keywords (wave 15E) -- 702.185a: its owner may cast it from exile after the current turn has ended
        import secrets

        from app.game.rules_state import Permission

        moved = plan.state.cards.get(card.id)
        if moved is not None and moved.zone.endswith(":exile"):
            plan.rules.permissions.append(Permission(
                id=secrets.token_hex(4), player=moved.owner, cast=True, zone="any", object_id=plan.oid(moved), card=moved.id,
                until="permanent", turn=plan.state.turn.number, after_turn=plan.state.turn.number,
                label=f"{moved.name}: cast it from exile (warped)"))
            plan.note(f"{moved.name} is exiled: {plan.name(moved.owner)} may cast it on a later turn", [moved.id])
    return True


def free_cast_offer(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Rebound: you may cast it from exile without paying its mana cost (it stays exiled if not)."""
    cid = e["card"]
    card = plan.state.cards.get(cid)
    if card is None or not card.zone.endswith(":exile"):
        return True
    from app.rules import granted_casts  # -- granted casts (wave 29B) --

    return granted_casts.ask(plan, ctx, player=card.owner, cid=cid, head="Rebound", no="Leave it exiled")


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


def counter_object(plan: Plan, stack_id: str, actor: str, to: str | None = None, *, exile: bool = False,
                   by: str | None = None) -> None:
    """701.6: a countered spell goes to its owner's graveyard (a flashback spell into exile); a
    countered ability simply stops existing. ``exile``: "If that spell is countered this way, exile
    it instead of putting it into its owner's graveyard" (608.2c; wave 4C).
    -- "this way" outcomes (wave 4A) -- ``to``: "exile it / put it on top of / on the bottom of its owner's
    library instead of into that player's graveyard" (608.2c: the counter's own destination; a flashback spell
    is still exiled, 702.34a: that replacement applies to the spell leaving the stack whatever its destination)."""
    card = plan.state.cards.get(stack_id)
    if card is None or card.zone != "stack":
        return
    from app.rules import permissions, scripts

    if card.ability is None and (scripts.uncounterable(plan.ch(card)) or _mana_units.uncounterable(plan, card)  # (wave 18B: 106.6)
                                 or permissions.spell_uncounterable(plan.state, plan.info, card, plan.ch(card))):
        plan.note(f"{card.name} can't be countered", [stack_id])
        return
    r = plan.rules
    remember_stack(plan.state, stack_id)  # -- spell copies (wave 31D) -- a copy of it can still be made (608.2h, 707.10)
    r.stack.pop(stack_id, None)
    oid = plan.oid(stack_id)
    r.buyback = [o for o in r.buyback if o != oid]
    r.exile_resolves.pop(oid, None)  # -- cast riders (wave 38C) -- a countered spell doesn't resolve (701.6a): "as it resolves" never applies to it
    plan.note(f"{card.name or 'It'} is countered", [stack_id])
    if card.ability is None and by is not None:  # -- counter events (wave 19C) -- "Whenever a spell or ability you control counters a spell":
        from app.game.rules_state import (
            emit,  # ``by`` is the controller of the spell or ability that countered it (701.6a)
        )

        emit(plan.state, "designation", counter="counters_spell", player=by)
    if oid in r.flashback or exile:
        r.flashback = [o for o in r.flashback if o != oid]
        plan.do({"type": "move", "card_ids": [stack_id], "to": {"player": card.owner, "zone": "exile"}}, actor=actor)
    elif to == "exile":  # (wave 4A)
        plan.do({"type": "move", "card_ids": [stack_id], "to": {"player": card.owner, "zone": "exile"}}, actor=actor)
    elif to == "hand":  # -- zone replacements (wave 37B) -- "put it into its owner's hand instead of into that player's graveyard" (Remand)
        plan.do({"type": "move", "card_ids": [stack_id], "to": {"player": card.owner, "zone": "hand"}}, actor=actor)
    elif to in ("top", "bottom"):  # (wave 4A)
        plan.do({"type": "move", "card_ids": [stack_id], "to": {"player": card.owner, "zone": "library"}, "position": to},
                actor=actor)
    else:
        plan.do({"type": "move", "card_ids": [stack_id], "to": {"player": card.owner, "zone": "graveyard"}}, actor=actor)


def _stack_targets(plan: Plan, ctx: Context, e: dict[str, Any]) -> list[str]:
    if e.get("object"):
        return [e["object"]] if e["object"] in plan.state.cards and plan.state.cards[e["object"]].zone == "stack" else []
    if e.get("who") == "event_spell":  # -- unless pays (wave 4C) -- a cast trigger's spell, while it's still that object (400.7)
        return [c for c in context.objects(plan, ctx, context.EVENT) if plan.state.cards[c].zone == "stack"]
    if e.get("who") == "each_opponent_spell":  # -- cast keywords (wave 43D) -- "Counter each spell you don't control." (an overloaded Counterflux): spells only (not abilities)
        return [c for c in plan.state.zones.get("stack", []) if c != ctx.get("stack_id") and plan.state.cards[c].ability is None
                and plan.state.cards[c].controller != ctx["controller"]]
    if e.get("who") == "event_source":  # -- unless pays (wave 20E) -- the spell or ability a "becomes the target" event names, while still that object
        ref = (ctx.get("event") or {}).get("source")
        card = context._same(plan, ObjectRef.model_validate(ref)) if ref else None
        return [card.id] if card is not None and card.zone == "stack" else []
    return [t["id"] for t in target_refs(ctx, e.get("who") or "target") if t["id"] in plan.state.cards
            and plan.state.cards[t["id"]].zone == "stack" and plan.oid(t["id"]) == t.get("object_id")]


def counter(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    sids = _stack_targets(plan, ctx, e)
    before = _remember(plan, ctx, e, sids)  # -- stack interaction (wave 5B) -- "its controller": 608.2h
    perms = _ability_sources(plan, sids, e) if e.get("perm_as") else {}
    for sid in sids:
        counter_object(plan, sid, ctx["controller"], e.get("to"), exile=bool(e.get("exile")), by=ctx["controller"])  # (exile: 4C; to: 4A)
    if e.get("perm_as"):  # -- stack interaction (wave 23B) -- "If a permanent's ability is countered this way, … that permanent": the sources
        context.bind_objects(plan, ctx, e["perm_as"], [c for sid, c in perms.items() if sid not in plan.rules.stack])  # of the abilities that were
    _moved(plan, ctx, e, before)  # (wave 5B)
    return True


def _ability_sources(plan: Plan, sids: list[str], e: dict[str, Any]) -> dict[str, str]:
    """-- stack interaction (wave 23B) -- the permanent each ability on the stack came from, while it is still that object on the battlefield
    (400.7: one that left is no permanent to name; "that permanent" of Trickbind / Tishana's Tidebinder), of the kinds ``perm_types`` lists."""
    out: dict[str, str] = {}
    for sid in sids:
        entry = plan.rules.stack.get(sid)
        card = plan.state.cards.get(entry.source_card or "") if entry is not None and plan.state.cards[sid].ability is not None else None
        if card is not None and entry is not None and card.zone.endswith(":battlefield") and plan.oid(card) == entry.source_object \
                and (not e.get("perm_types") or plan.ch(card).types & set(e["perm_types"])):
            out[sid] = card.id
    return out


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
    # -- review (wave 4R) -- 118.3: PAY is offered only while the payer can pay all of it (as optional_payment)
    from app.rules import casting  # casting imports this module

    if not cost.is_free and not casting.can_pay(plan.state, payer, cost, plan.info):
        plan.note(f"{plan.name(payer)} can't pay {cost.text()}")
        counter_object(plan, sid, payer, by=ctx["controller"])
        return True
    # -- end review (wave 4R) --
    options = [DecisionOption(id="pay", label=f"Pay {cost.text()}"),  # (tap your mana first)
               DecisionOption(id="decline", label="Don't pay (it's countered)")]
    decide(plan, player=payer, kind="choose_one",
           prompt=f"{ctx.get('name', '')}: pay {cost.text()} or {plan.state.cards[sid].name or 'your spell'} is countered",
           options=options, resume={"step": "pay_or_sacrifice", "counter": sid, "ctx": ctx, "cost": e["cost"]},
           source=plan.state.cards[sid])
    return False


def ascend(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """-- keywords (wave 15E) -- 702.131a: Ascend on an instant or sorcery: if you control ten or more permanents and you
    don't have the city's blessing, you get it for the rest of the game."""
    from app.rules import designations

    if designations.city_blessing_due(plan, ctx["controller"]):
        designations.get_city_blessing(plan, ctx["controller"])
    return True


def sacrifice(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.21a: a player can't sacrifice a permanent they don't control ("sacrifice it" after the
    creature changed control does nothing to it). ``by`` "controller": "its controller sacrifices
    it" (evoke, 702.74a) — whoever controls it as the effect happens."""
    you = ctx["controller"]
    cards = _cards(plan, ctx, e["who"])
    if e.get("by") == "event_player":  # -- attached events (wave 25D) -- "that player sacrifices that creature": only if that player still controls it
        mine = _players(plan, ctx, "event_player")
        cards = [c for c in cards if plan.state.cards[c].controller in mine]
    elif e.get("by") != "controller":
        cards = [c for c in cards if plan.state.cards[c].controller == you]
    actor = plan.state.cards[cards[0]].controller if cards else you
    _sacrifice_cards(plan, cards, actor, ctx, e.get("as"))
    return True


def explore(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.44a: reveal the top card of your library. A land goes into your hand; otherwise put a
    +1/+1 counter on this creature, then you may put the revealed card into your graveyard."""
    from app.game.rules_state import emit
    from app.rules import characteristics as chars

    me = _cards(plan, ctx, e.get("who", "self"))  # (wave 16C: "target creature you control explores"; 17D: "it" the event's creature)
    pid = plan.state.cards[me[0]].controller if me else ctx["controller"]  # 701.44a: that permanent's controller reveals and decides
    if me and (replaced := replace.keyword_replace(plan, ctx, e, "explore", pid, card=me[0])) is not None:
        return replaced  # -- keyword actions (wave 35C) -- "If a creature you control would explore, …" (Topography Tracker, Twists and Turns)
    library = plan.state.zones.get(zone_key(pid, "library"), [])

    def explored(kind: int) -> None:  # -- trigger tail (wave 15B) -- "Whenever a creature you control explores" (701.44a): 1 a land
        if me:  # card was revealed, 2 a nonland card, 0 none
            emit(plan.state, "designation", counter="explore", card=me[0], object_id=plan.oid(me[0]), player=pid, amount=kind)
    # -- replacement effects stage 2 (wave 2E): the +1/+1 counter through the counter choke point --
    if not library:  # (False: an order to choose first; then the resolution continues)
        explored(0)
        return not me or replace.put_counters(plan, [(c, "+1/+1", 1) for c in me], by=pid, then={"do": "continue", "ctx": ctx})
    top = library[0]
    plan.do({"type": "reveal_top", "player": pid, "count": 1}, actor=pid)
    card = plan.state.cards[top]
    explored(1 if chars.of(card, plan.info).is_land else 2)
    if chars.of(card, plan.info).is_land:
        plan.do({"type": "move", "card_ids": [top], "to": {"player": pid, "zone": "hand"}}, actor=pid)
        return True
    if me and not replace.put_counters(plan, [(c, "+1/+1", 1) for c in me], by=pid,
                                       then={"do": "explore_ask", "ctx": ctx, "card": top, "player": pid}):
        return False
    _explore_ask(plan, ctx, top, pid)
    return False


def _explore_ask(plan: Plan, ctx: Context, top: str, pid: str) -> None:
    card = plan.state.cards[top]
    decide(plan, player=pid, kind="choose_one", prompt=f"Explore revealed {card.name}: put it into your graveyard?",
           options=[DecisionOption(id="keep", label="Keep it on top"), DecisionOption(id="graveyard", label="Put it into your graveyard")],
           resume={"step": "explore", "ctx": ctx, "card": top}, source=card)


replace.THEN["explore_ask"] = lambda plan, t: _explore_ask(plan, t["ctx"], t["card"], t["player"])


def resume_explore(plan: Plan, d: Any, chosen: list[str]) -> None:
    cid = d.resume["card"]
    if chosen[0] == "graveyard" and cid in plan.state.cards and plan.state.cards[cid].zone.endswith(":library"):
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": d.player, "zone": "graveyard"}}, actor=d.player)
    continue_effects(plan, d.resume["ctx"])


def prevent(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """615.7: "Prevent the next N damage that would be dealt to … this turn" — a shield."""
    r = plan.rules
    if (shares := divided(ctx, e)) is not None:  # -- prevention riders (wave 17A) -- 601.2d: each target's share, an illegal target's lost
        legal = {*_cards(plan, ctx, e["who"]), *_players(plan, ctx, e["who"])}
        for t, share in shares.items():
            if t in legal and share > 0:
                key = plan.oid(t) if t in plan.state.cards else t
                r.prevention[key] = r.prevention.get(key, 0) + share
        return True
    keys = [plan.oid(c) for c in _cards(plan, ctx, e["who"])] + _players(plan, ctx, e["who"])
    n = _amount(plan, ctx, e["n"])  # (wave 12C: "prevent the next X damage, where X is …": the amount as it resolves, 608.2h)
    for key in keys:
        if e.get("rider"):  # -- prevention riders (wave 17A) -- its own shield: the additional effect is this one's (615.5)
            import secrets

            key = f"{key}#{secrets.token_hex(4)}"
            r.prevention_riders[key] = {"rider": e["rider"], "by": ctx["controller"], "card": ctx.get("source_card"),
                                        "oid": ctx.get("source_object"), "name": ctx.get("name") or "a prevention effect"}
        r.prevention[key] = r.prevention.get(key, 0) + n
    return True


def mill(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    want = _amount(plan, ctx, e["n"])
    before: list[ObjectRef] = []
    wants: list[tuple[str, int]] = []
    for pid in _players(plan, ctx, e["who"]):
        if e.get("half"):  # -- if you do (wave 15C) -- 107.1a: half the library as it is now, rounded as the text says
            size = len(plan.state.zones.get(zone_key(pid, "library"), []))
            want = (size + 1) // 2 if e["half"] == "up" else size // 2
        wants.append((pid, want))
    # -- mill counts (wave 28B) -- "would mill" replacements change the number the instruction says (the library may hold fewer)
    counts = replace.mill_counts(plan, wants, then=replace.rerun_then(ctx, e), ctx=ctx)  # (run again with the answers, not continued)
    if counts is None:
        return False
    start = plan.rules.batch
    for pid, count in counts:
        library = plan.state.zones.get(zone_key(pid, "library"), [])
        n = min(count, len(library))
        before += [r for r in (context.ref_of(plan, c) for c in library[:n]) if r is not None]
        if n:
            plan.do({"type": "mill", "player": pid, "count": n}, actor=pid)
    # -- review 28D -- "each player mills …" is one event: a "whenever one or more cards are milled" ability triggers once for all
    # of them (603.2c; The Wise Mothman ruling 2024-03-08)
    from app.rules.replace import _one_batch

    _one_batch(plan, start)
    _moved(plan, ctx, e, before)  # "cards milled this way": the new objects in the graveyards (400.7j)
    if e.get("look"):  # -- if you do (wave 10C) -- "Mill three cards. You may put a land card from among them into your hand."
        # (701.17a: the cards are put into the graveyard; "them" are the ones this mill put there — a card a replacement sent
        # elsewhere isn't "milled" — and they are public, so the pick that follows works on them like a look's)
        pid = _players(plan, ctx, e["who"])[0]
        gone = {r.card for r in before}
        grave = plan.state.zones.get(zone_key(pid, "graveyard"), [])
        ctx["looked"] = [c for c in grave if c in gone]
        ctx["looked_zone"], ctx["looked_owner"], ctx["found"] = "graveyard", pid, None
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
    return _exile_until_cards(plan, ctx, e, [c for c in _cards(plan, ctx, e["who"])
                                             if e.get("hand_origin") or plan.state.cards[c].zone.endswith(":battlefield")])  # (610.3: returns to the battlefield)


def _exile_until_cards(plan: Plan, ctx: Context, e: dict[str, Any], cards: list[str]) -> bool:
    before = _remember(plan, ctx, e, cards)
    if cards:
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "exile"}}, actor=ctx["controller"])
        key = ctx["source_object"]
        exiled = [plan.oid(c) for c in _merged.pieces(plan, cards)  # (review (wave 18D): each card of a merged permanent, 730.3c)
                  if c in plan.state.cards and plan.state.cards[c].zone.endswith(":exile")]
        plan.rules.linked_exile[key] = [*plan.rules.linked_exile.get(key, []), *exiled]  # the objects in exile (400.7)
        if e.get("hand_origin"):  # -- resolution memory (wave 22D) -- 610.3: returns to its previous zone, the hand
            plan.rules.linked_exile_from.update({oid: "hand" for oid in exiled})
        if e.get("link"):  # -- resolution memory (wave 22D) -- 607.2a: also "the exiled card" of another ability (Phantom Steed)
            from app.rules import exiled_with

            exiled_with.record(plan, ctx, _merged.pieces(plan, cards))
    _moved(plan, ctx, e, before)
    return True


def return_linked(plan: Plan, ctx: Context | None, e: dict[str, Any]) -> bool:
    """The exiled cards return to the battlefield under their owners' control (610.3c). ``ctx``:
    the resolving effects to go on with after an Aura's choice of what to enchant (303.4f); None
    when the return isn't part of a resolution (the source just left the battlefield)."""
    from app.rules import attachments  # attachments → effects (resume)

    return attachments.enter(plan, linked_entries(plan, e["source"]), ctx)


def linked_entries(plan: Plan, source: str) -> list[dict[str, Any]]:
    """The link ends: the entries for the cards "exiled until ``source`` leaves the battlefield"
    that return — each only while it's still the object that was exiled (a card that left exile
    and came back is a new object, 400.7). A card whose owner left the game stays where it is
    (800.4a-b)."""
    entries = []
    live = plan.live()
    for ref in plan.rules.linked_exile.pop(source, []):
        if ref in plan.state.cards:  # (a game saved before this kept card ids)
            cid = ref
        else:
            cid = ref.rsplit(".", 1)[0]
            if cid not in plan.state.cards or plan.oid(cid) != ref:
                continue
        card = plan.state.cards[cid]
        back = plan.rules.linked_exile_from.pop(ref, None)  # -- resolution memory (wave 22D) -- 610.3: back to the hand it came from
        if card.zone.endswith(":exile") and card.owner in live:
            entries.append({"card": cid, "player": card.owner, "actor": card.owner, **({"to": "hand"} if back == "hand" else {})})
    return entries


SERVO = {"name": "Servo", "power": "1", "toughness": "1", "colors": [], "type_line": "Token Artifact Creature — Servo", "text": ""}


def fabricate(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    n = e["n"]
    me = _cards(plan, ctx, "self")
    if not me:  # it left: only the Servos are possible (702.123b)
        return create_token(plan, ctx, {"who": "you", "n": n, "token": SERVO}, then={"do": "continue", "ctx": ctx})
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"Fabricate {n}",
           options=[DecisionOption(id="counters", label=f"{n} +1/+1 counter{'s' if n != 1 else ''} on it"),
                    DecisionOption(id="servos", label=f"{n} 1/1 Servo{'s' if n != 1 else ''}")],
           resume={"step": "fabricate", "ctx": ctx, "n": n}, source=plan.state.cards[me[0]])
    return False


def resume_fabricate(plan: Plan, d: Any, chosen: list[str]) -> None:
    # -- replacement effects stage 2 (wave 2E): the counters / Servos through the choke points --
    ctx, n = d.resume["ctx"], d.resume["n"]
    me = _cards(plan, ctx, "self")
    then = {"do": "continue", "ctx": ctx}
    if chosen[0] == "counters" and me:
        done = replace.put_counters(plan, [(c, "+1/+1", int(n)) for c in me], by=d.player, then=then)
    else:
        done = create_token(plan, ctx, {"who": "you", "n": n, "token": SERVO}, then=then)
    if done:
        continue_effects(plan, ctx)


def storm(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.40a: put N copies of the spell on the stack (real spell copies, 707.10); its controller
    may choose new targets for any of them (707.10c) — app/rules/copying.py (copy system, wave 2F)."""
    from app.rules import copying

    return copying.storm(plan, ctx, e)


def resume_storm(plan: Plan, d: Any, chosen: list[str]) -> None:
    """(A storm decision saved by an older version: answered through the copy system.)"""
    from app.rules import copying

    copying.resume_storm(plan, d, chosen)


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
    doomed = regeneration.survivors(plan, doomed, can_regenerate=_can_regenerate(ctx), actor=ctx["controller"])
    before = _remember(plan, ctx, e, doomed)  # "creatures destroyed this way": the ones it destroys
    if doomed:
        gone = {c: plan.oid(c) for c in doomed}
        plan.do({"type": "move", "card_ids": doomed, "to": {"zone": "graveyard"}}, actor=ctx["controller"])
        _destroyed(plan, gone)
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
        for piece in _merged.pieces(plan, [cid]):  # (-- review (wave 18D) -- 730.3c: every card a merged permanent became returns)
            if piece in plan.state.cards:  # (a token ceases to exist in exile: 111.7, and can't come back, 111.8)
                entries.append({"card": piece, "player": back, "actor": ctx["controller"]})
    done = attachments.enter(plan, entries, ctx)
    if done:  # (an Aura choosing what it enchants pauses: the binding then keeps what they were)
        _moved(plan, ctx, e, before)  # the permanents they became: new objects (400.7)
    if done and e.get("attacking"):  # -- refused zones/sized (wave 3R4) -- "tapped and attacking" (508.4)
        return refused_zones.enter_attacking(plan, ctx, cards, e.get("at"))
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


def _search_matches(plan: Plan, ctx: Context, e: dict[str, Any], pid: str, key: str | None, among: list[str]) -> list[str]:
    """The cards of ``among`` (the searcher's library) that fit one phrase of the search: a selector
    key (or any of the alternatives), a name, a mana value."""
    from app.rules import characteristics as chars

    keys = e.get("alts") or [key]
    sels = [selectors.from_key(k) for k in keys]
    matching = [c for c in among if any(selectors.matches(plan, sel, plan.state.cards[c], chars.of(plan.state.cards[c], plan.info), pid)
                                        for sel in sels)]
    # -- tutors (wave 3T) -- "a card named …" and "with mana value X or less" (the X chosen for this
    # spell or ability; a card in a library has its X as 0, 202.3e)
    if e.get("name"):
        src = plan.state.cards.get(ctx.get("source_card") or "")
        name = (src.name if src is not None else "") if e["name"] == "~" else e["name"]
        matching = [c for c in matching if name and (plan.state.cards[c].name or "").lower() == name.lower()]
    if e.get("name_as") is not None:  # -- tutor (wave 26D) -- "a card with the same name as that creature" (app/rules/same_name.py)
        from app.rules import same_name

        wanted = same_name.names(plan, ctx, e["name_as"])
        matching = [c for c in matching if (plan.state.cards[c].name or "").lower() in wanted]
    if e.get("mv"):
        op, value = e["mv"][0], (e["mv"][1] if e["mv"][0] == "in" else _amount(plan, ctx, e["mv"][1]))
        mvs = {c: chars.of(plan.state.cards[c], plan.info).mana_value for c in matching}
        matching = [c for c in matching if (mvs[c] <= value if op == "<=" else mvs[c] < value if op == "<"  # ("<": wave 4M)
                                            else mvs[c] in e["mv"][1] if op == "in" else mvs[c] == value)]  # ("in": wave 20D, "4 or 5")
    return matching


def search(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """A tutor. The server filters the library; only the searching player gets the matching cards
    in their private decision (nobody else learns the library's contents)."""
    pid = ctx["controller"]
    if e.get("who") in ("each_opponent", "each_player"):  # -- other players' choices (wave 12D) -- "Each opponent may search their
        # library for …": one search per player, the active player first (101.4). A library is hidden, so each search is its
        # player's private choice; the cards they put onto the battlefield enter as each search ends (a corner of 101.4's
        # "actions happen simultaneously" that only an entering permanent watching the others entering could notice)
        order = [p for p in plan.apnap() if p in _players(plan, ctx, e["who"])]
        at = ctx["next"]
        ctx["effects"] = [*ctx["effects"][:at], *({**e, "who": f"player:{p}"} for p in order), *ctx["effects"][at:]]
        continue_effects(plan, ctx)
        return False
    if e.get("library"):  # -- static_other sweep (wave 26A) -- "Search target opponent's library for …": the controller searches it (701.23a)
        owners = _players(plan, ctx, e["library"])
        if not owners:
            return True
        e = {**e, "lib_pid": owners[0]}
    if e.get("who", "you") != "you":  # "Its controller may search their library …" (Path to Exile)
        who = _players(plan, ctx, e["who"])
        if not who:
            return True
        pid = who[0]
    if e.get("graveyard") and "zones" not in e:  # -- refused zones/sized (wave 3R4) -- "your library and/or graveyard"
        options = [DecisionOption(id="both", label="Search your library and graveyard"),
                   DecisionOption(id="graveyard", label="Search your graveyard only")]
        if e.get("search_zones"):  # -- if you do (wave 15C) -- "your graveyard, hand, and/or library": any of the zones named (701.23a)
            subsets = [c for n in range(len(e["search_zones"]), 0, -1) for c in itertools.combinations(e["search_zones"], n)]
            options = [DecisionOption(id="+".join(c), label="Search your " + " and ".join(c)) for c in subsets]
        if e.get("may"):
            options.append(DecisionOption(id="none", label="Don't search"))
        decide(plan, player=pid, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: search for a {e.get('label') or 'card'}",
               options=options, resume={"step": "search_zones", "ctx": ctx, "e": e})
        return False
    if e.get("may") and barred_search(plan, ctx, e):  # -- prohibitions (wave 24D) -- 608.2d: no choosing to search; so no shuffle
        return True
    if e.get("may"):
        # "Its controller may search …, then shuffle" (Path to Exile): searching is their choice,
        # asked first — a player who doesn't search doesn't shuffle either (the card's ruling;
        # 701.23b: one who searches may still find nothing, and then shuffles)
        decide(plan, player=pid, kind="confirm", prompt=f"{ctx.get('name') or 'It'}: search your library for a {e.get('label') or 'card'}?",
               options=[DecisionOption(id="yes", label="Search"), DecisionOption(id="no", label="Don't search")],
               resume={"step": "search_may", "ctx": ctx, "e": e})
        return False
    return _ask_search(plan, ctx, e, pid, 0, [])


def barred_search(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """-- prohibitions (wave 24D) -- 608.2d (the player can't choose an impossible option): "You may search your library …" can't be chosen while the searcher can't search it, so the
    instruction is skipped whole — no search and (the ruling) no shuffle, unlike a mandatory "search …, then shuffle"
    (a "may" over several zones, or a search of someone else's library, stays as it was)."""
    from app.rules import prohibitions

    if e.get("do") != "search" or e.get("graveyard") or e.get("zones") or e.get("who", "you") in ("each_opponent", "each_player"):
        return False
    who = _players(plan, ctx, e["who"]) if e.get("who", "you") != "you" else [ctx["controller"]]
    if not who or (why := prohibitions.cant_search(plan, who[0], ctx["controller"])) is None:
        return False
    plan.note(f"{why}: {plan.name(who[0])} can't search their library, so doesn't choose to", actor=who[0])
    return True


def resume_search_may(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    if chosen[0] == "yes":
        _ask_search(plan, ctx, e, d.player, 0, [])
        return
    plan.note(f"{plan.name(d.player)} chose not to search (no shuffle)", actor=d.player)
    continue_effects(plan, ctx)


def resume_search_zones(plan: Plan, d: Any, chosen: list[str]) -> None:
    """-- refused zones/sized (wave 3R4) -- which zones the searcher looks through (701.23a: all of each)."""
    ctx, e = d.resume["ctx"], d.resume["e"]
    if chosen[0] == "none":
        plan.note(f"{plan.name(d.player)} chose not to search (no shuffle)", actor=d.player)
        continue_effects(plan, ctx)
        return
    zones = {"both": ["library", "graveyard"], "graveyard": ["graveyard"]}.get(chosen[0]) or chosen[0].split("+")
    _ask_search(plan, ctx, {**e, "zones": zones}, d.player, 0, [])


def _ask_search(plan: Plan, ctx: Context, e: dict[str, Any], pid: str, part: int, picked: list[str]) -> bool:
    zones = e.get("zones") or ["library"]  # (-- refused zones/sized (wave 3R4) -- "and/or graveyard": the chosen zones)
    from app.rules import (
        prohibitions,  # -- prohibitions (wave 22B) -- 614.17: "Players can't search libraries."
    )

    owner = e.get("lib_pid", pid)  # (wave 26A: whose library is searched; the searcher's own unless a target's)
    if "library" in zones and (why := prohibitions.cant_search(plan, pid, ctx["controller"], owner)) is not None:
        whose = "their" if owner == pid else plan.name(owner) + "'s"
        plan.note(f"{why}: {plan.name(pid)} can't search {whose} library", actor=pid)
        zones = [z for z in zones if z != "library"]
        e = {**e, "zones": zones}
        if not zones:  # nothing is searched; "then shuffle" is its own instruction (701.24) and still happens
            _finish_search(plan, ctx, e, pid, [], {})
            return False
    if part == 0 and not picked and "library" in zones:
        prohibitions.note_search(plan, pid, owner)  # -- most-played cards (wave 43B) -- "Whenever an opponent searches their library"
    depth = prohibitions.search_depth(plan, pid)  # (wave 43B: Aven Mindcensor: only the top four cards of any library are searched)
    library = [c for c in plan.state.zones.get(zone_key(owner, "library"), [])[:depth] if c not in picked] if "library" in zones else []
    if e.get("sel"):  # a structured card selector (app/rules/selectors.py)
        parts = e.get("parts")  # "a Forest card and a Plains card": one card of each kind, asked in turn
        matching = _search_matches(plan, ctx, e, owner, parts[part] if parts else e["sel"], library)
        if "graveyard" in zones:  # (wave 3R4) the graveyard's cards are public (404.2): the same test, read there
            graveyard = [c for c in plan.state.zones.get(zone_key(pid, "graveyard"), []) if c not in picked]
            keys = [selectors.replace(selectors.from_key(k), zones=("graveyard",)).key() for k in (e.get("alts") or [e["sel"]])]
            matching += _search_matches(plan, ctx, {**e, "alts": keys}, pid, None, graveyard)
        if "hand" in zones:  # -- if you do (wave 15C) -- the searcher's own hand: private to them, as is this decision
            hand = [c for c in plan.state.zones.get(zone_key(pid, "hand"), []) if c not in picked]
            keys = [selectors.replace(selectors.from_key(k), zones=("hand",)).key() for k in (e.get("alts") or [e["sel"]])]
            matching += _search_matches(plan, ctx, {**e, "alts": keys}, pid, None, hand)
        what =e.get("label") or "cards"
    else:
        matching = [c for c in library if _matches(plan, c, e["filter"])]
        what = e["filter"].replace("_", " ")
    most = 1 if e.get("parts") else _amount(plan, ctx, e.get("max", 1))
    options = [DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in matching]
    # 701.23b: a search for cards with a stated quality may find fewer (or none); 701.23d: a search
    # simply for a quantity of cards ("a card") must find that many, or as many as there are.
    # ("Up to N cards" may find fewer: only a single "a card" or an explicit ``upto: False`` forces.)
    quantity_only = e.get("filter") == "any" or (e.get("sel") is not None and e.get("label") in ("card", "cards"))
    forced = quantity_only and not e.get("upto", e.get("label") == "cards")
    whose = f"{plan.name(owner)}'s" if owner != pid else "your"
    decide(plan, player=pid, kind="choose_cards", prompt=f"Search {whose} {' and '.join(zones)} ({what})",
           options=options, min_choices=min(most, len(options)) if forced else 0, max_choices=min(most, len(options)),
           decider=_player_control.search_controller(plan, pid) if "library" in zones and owner == pid else None,  # (-- wave 18H -- 723.2: Opposition Agent; review 26A: only while they search their own library)
           resume={"step": "search", "ctx": ctx, "e": e, "part": part, "picked": picked})
    return False


_PLACES = {"hand": "into your hand", "battlefield": "onto the battlefield", "battlefield_tapped": "onto the battlefield tapped",
           "graveyard": "into your graveyard"}


def resume_search(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    if e.get("distinct_names"):  # -- refused zones/sized (wave 3R4) -- "… cards with different names" (201.2)
        names = [(plan.state.cards[c].name or "").lower() for c in chosen if c in plan.state.cards]
        if len(set(names)) != len(names):
            from app.game.errors import ActionError

            raise ActionError("The cards you find must have different names")
    if e.get("total_mv") is not None:  # -- tutor (wave 20D) -- "creature cards with total mana value 6 or less" (Protean Hulk)
        from app.rules import characteristics as chars

        if sum(chars.of(plan.state.cards[c], plan.info).mana_value for c in chosen if c in plan.state.cards) > e["total_mv"]:
            from app.game.errors import ActionError

            raise ActionError(f"The cards you find must have total mana value {e['total_mv']} or less")
    _recursion.check_found(plan, e, chosen)  # -- recursion & tutors (wave 4M) -- "… that share a land type"
    if e.get("parts"):  # the next kind of card, or all the cards found
        chosen = [*d.resume.get("picked", []), *chosen]
        if d.resume.get("part", 0) + 1 < len(e["parts"]):
            _ask_search(plan, ctx, e, d.player, d.resume["part"] + 1, chosen)
            return
    if e.get("to2") and len(chosen) > 1:  # "put one onto the battlefield and the other into your hand": the
        # searcher says which (a private decision: nobody else sees which cards were found)
        decide(plan, player=d.player, kind="choose_cards", prompt=f"Choose the card that goes {_PLACES[e['to']]}",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in chosen],
               min_choices=1, max_choices=1, resume={"step": "search_split", "ctx": ctx, "e": e, "found": list(chosen)})
        return
    _finish_search(plan, ctx, e, d.player, list(chosen), {c: e["to"] for c in chosen})


def resume_search_split(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e, found = d.resume["ctx"], d.resume["e"], d.resume["found"]
    _finish_search(plan, ctx, e, d.player, found, {c: e["to"] if c in chosen else e["to2"] for c in found})


def _finish_search(plan: Plan, ctx: Context, e: dict[str, Any], pid: str, chosen: list[str], dest: dict[str, str]) -> None:
    from app.rules import attachments  # attachments → effects (resume)

    entering = []
    owner = e.get("lib_pid", pid)  # (wave 26A: a target player's library: the cards found are theirs; they enter under the searcher's control)
    found = _remember(plan, ctx, e, chosen)  # (library objects: a hidden zone, so nothing is read from them)
    # -- controlling another player (wave 18H) -- Opposition Agent: "they exile each card they find" (701.23): a card found in the
    # library is exiled and nothing else the instruction says about it happens (it is a new object, 400.7); the Agent's
    # controller may play it for as long as it remains exiled, spending mana as though it were any color
    agents = _player_control.search_exile(plan, pid) if "library" in (e.get("zones") or ["library"]) and owner == pid else []  # (review 26A: "their library")
    exiled = [c for c in chosen if agents and plan.state.cards[c].zone == zone_key(owner, "library")]
    dest = {**dest, **{c: "exile" for c in exiled}}
    if e.get("reveal"):
        for cid in chosen:
            if cid not in exiled:
                plan.do({"type": "reveal", "card_ids": [cid]}, actor=pid)  # to everyone
    for cid in chosen:
        to = dest[cid]
        if to in ("hand", "graveyard", "exile"):
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": owner, "zone": to},
                     **({"face_down": True} if e.get("face_down") and cid not in exiled else {})}, actor=pid)
        elif to in ("battlefield", "battlefield_tapped"):
            entering.append({"card": cid, "player": pid, "actor": pid, "tapped": to == "battlefield_tapped"})
    _player_control.permit_exiled(plan, agents, exiled)
    if entering and e.get("host"):  # -- if you do (wave 25C) -- "…, put it onto the battlefield attached to this creature"
        entering = _attached_entries(plan, ctx, e["host"], entering)
    if e.get("link"):  # -- resolution memory (wave 22D) -- 607.2a: "search your library for an artifact card, exile it" (Hoarding Dragon)
        from app.rules import exiled_with

        exiled_with.record(plan, ctx, [c for c in chosen if dest[c] == "exile"])
    shuffle = owner if e.get("shuffle", True) else None  # 701.24: a library is shuffled only when the text says so
    if "library" not in (e.get("zones") or ["library"]):
        shuffle = None  # -- refused zones/sized (wave 3R4) -- "If you search your library this way, shuffle"
    if entering and not attachments.enter(plan, entering, ctx, shuffle=shuffle):  # an Aura chooses what it enchants (303.4f)
        return
    _moved(plan, ctx, e, found)  # the cards found, where they went (400.7j; a hand is hidden: nothing)
    if shuffle is not None:
        before = list(plan.state.zones.get(zone_key(pid, "library"), []))
        shuffled = plan.do({"type": "shuffle", "player": pid, "zone": "library"}, actor=pid)
        if e["to"] == "top":  # "then shuffle and put that card on top": follow it through the shuffle's new ids
            r = getattr(shuffled, "r", None)
            tops = []
            for cid in chosen:
                if r is None or cid not in before:
                    continue
                new_id = r.new_ids[r.perm.index(before.index(cid))]
                tops.append(new_id)
                if not e.get("top_order"):
                    plan.do({"type": "move", "card_ids": [new_id], "to": {"player": pid, "zone": "library"},
                             "index": e.get("depth", 1) - 1}, actor=pid)  # (wave 20D: "third from the top")
            if e.get("top_order") and len(tops) > 1:  # -- refused zones/sized (wave 3R4) -- 401.4: in the order the
                _ask_order(plan, ctx, pid, pid, tops, "top")  # searcher chooses (private); the resolution goes on after
                return
            if e.get("top_order") and tops:
                plan.do({"type": "move", "card_ids": tops, "to": {"player": pid, "zone": "library"}, "index": 0}, actor=pid)
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
    if e.get("random"):  # -- refused zones/sized (wave 3R4) -- 701.9b "discards N cards at random": nobody chooses; the
        # table picks (the recorded move says which, so replay is the same) and they are discarded at once (101.4)
        import secrets

        rng = plan.rng or secrets.SystemRandom()
        want = _amount(plan, ctx, e["n"])
        picked = [c for pid in order for c in rng.sample(sorted(plan.state.zones.get(zone_key(pid, "hand"), [])),
                                                           min(want, len(plan.state.zones.get(zone_key(pid, "hand"), []))))]
        return _discard_next(plan, ctx, want, [], picked, e.get("as"))
    if e.get("all"):  # -- "this way" outcomes (wave 4A) -- "discard your hand": every card, no choice (701.9a)
        picked = [c for pid in order for c in plan.state.zones.get(zone_key(pid, "hand"), [])]
        return _discard_next(plan, ctx, 0, [], picked, e.get("as"))
    return _discard_next(plan, ctx, _amount(plan, ctx, e["n"]), order, [], e.get("as"), e.get("to", "graveyard"),
                         e.get("zone", "hand"), bool(e.get("upto")), e.get("sel"), e.get("half"))


def _discard_next(plan: Plan, ctx: Context, want: int, players: list[str], picked: list[str],
                  binding: str | None = None, dest: str = "graveyard", src: str = "hand", upto: bool = False,
                  sel: str | None = None, half: str | None = None) -> bool:
    from app.rules import (
        prohibitions,  # -- prohibitions (wave 22B) -- 614.17: "… can't cause you to discard cards" (exiling isn't discarding)
    )

    for i, pid in enumerate(players):
        hand = plan.state.zones.get(zone_key(pid, src), [])  # (wave 15D: "exiles a card from their graveyard", public, 404.1)
        if sel:  # -- if you do (wave 21C) -- "discard a creature card": only cards of that kind can be chosen (701.9a)
            from app.rules import characteristics as chars

            kind = selectors.from_key(sel)
            hand = [c for c in hand if selectors.matches(plan, kind, plan.state.cards[c], chars.of(plan.state.cards[c], plan.info), pid)]
        if hand and dest != "exile" and (why := prohibitions.cant_cause_discard(plan, pid, ctx["controller"])) is not None:
            plan.note(f"{why}: {plan.name(pid)} can't be made to discard cards")
            hand = []
        if half:  # -- trigger other (wave 39A) -- "discards half the cards in their hand, rounded down" (Lord Xander): 107.1a, of the hand as it is as they discard
            want = (len(hand) + (half == "up")) // 2
        n = min(want, len(hand)) if want or not upto else len(hand)  # (upto, 0: "any number of cards")
        if n == 0:
            continue
        if n == len(hand) and not upto:
            picked = [*picked, *hand]
            continue
        decide(plan, player=pid, kind="choose_cards",
               prompt=(f"Discard up to {n} cards" if upto else
                       f"{'Exile' if dest == 'exile' else 'Discard'} {n} card{'s' if n != 1 else ''}")  # (wave 11D: "exiles two cards from their hand")
               + (f" from your {src}" if dest == "exile" else ""),
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in hand],
               min_choices=0 if upto else n, max_choices=n,  # (-- trigger tail (wave 15B) -- "up to N" / "any number": 701.9a)
               resume={"step": "discard", "ctx": ctx, "want": want, "rest": players[i + 1:], "picked": picked,
                       "as": binding, "to": dest, "zone": src, "upto": upto, "sel": sel, "half": half})
        return False
    cards = [c for c in picked if c in plan.state.cards and plan.state.cards[c].zone.endswith(f":{src}")]
    if dest != "exile":  # (-- prohibitions (wave 22B) -- "discard your hand" / at random: the cards were picked without asking)
        cards = [c for c in cards if prohibitions.cant_cause_discard(plan, plan.state.cards[c].owner, ctx["controller"]) is None]
    e = {"as": binding}
    before = _remember(plan, ctx, e, cards)
    if cards:  # each to its owner's graveyard (701.9a); -- hand disruption (wave 11D) -- or exiled, which is no discard (701.9a)
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": dest}}, actor=ctx["controller"])
    _moved(plan, ctx, e, before)  # "cards discarded this way": found in the graveyards (400.7j)
    return True


def resume_discard(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx = d.resume["ctx"]
    picked = [*(d.resume.get("picked") or []), *chosen]
    if _discard_next(plan, ctx, d.resume.get("want", 0), d.resume.get("rest") or [], picked, d.resume.get("as"),
                     d.resume.get("to", "graveyard"), d.resume.get("zone", "hand"), bool(d.resume.get("upto")),
                     d.resume.get("sel"), d.resume.get("half")):
        continue_effects(plan, ctx)


def sacrifice_choice(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.21a: "[Players] sacrifice N [selector]": each affected player chooses permanents they
    control that match, in APNAP order; then they're all sacrificed at once (101.4)."""
    who = _players(plan, ctx, e["who"])
    order = [p for p in plan.apnap() if p in who]
    if e.get("exile") == "until" and not _cards(plan, ctx, "self"):  # -- resolution memory (wave 22D) -- 610.3a-b: the source left: nothing happens
        _remember(plan, ctx, e, [])
        return True
    if e.get("exploit"):  # -- keyword triggers (wave 23D) -- 702.110b: the creature sacrificed as the exploit ability resolves is exploited
        ctx["exploiting"] = True
    return _sacrifice_next(plan, ctx, e["sel"], _amount(plan, ctx, e["n"]), order, [], e.get("as"), e.get("exile") or False,
                           bool(e.get("link")), bool(e.get("upto")))


def _sacrifice_next(plan: Plan, ctx: Context, key: str, want: int, players: list[str], picked: list[str],
                    binding: str | None = None, exile: bool | str = False, link: bool = False, upto: bool = False) -> bool:
    sel = selectors.from_key(key)
    for i, pid in enumerate(players):
        mine = [c for c in selectors.candidates(plan, sel, pid, ctx.get("source_card"))
                if plan.state.cards[c].controller == pid and plan.state.cards[c].zone.endswith(":battlefield")]
        if mine and _sacrifice_barred(plan, ctx, pid):
            mine = []  # -- prohibitions (wave 22B) --
        n = min(want, len(mine))
        if n == 0:
            continue
        if n == len(mine) and not upto:
            picked = [*picked, *mine]
            continue
        decide(plan, player=pid, kind="choose_cards", prompt=f"{'Exile' if exile else 'Sacrifice'} {'up to ' if upto else ''}{n}",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Permanent", card_id=c) for c in mine],
               min_choices=0 if upto else n, max_choices=n,  # (-- triggers (wave 19B) -- "any number of": none is allowed)
               resume={"step": "sacrifice_choice", "ctx": ctx, "sel": key, "want": want, "rest": players[i + 1:],
                       "picked": picked, "as": binding, "exile": exile, "link": link, "upto": upto})
        return False
    if exile:  # -- trigger tail (wave 16C) -- "Exile a land you control": chosen as it resolves, then exiled (not sacrificed)
        picked = [c for c in picked if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")]
        if exile == "until":  # -- resolution memory (wave 22D) -- "Exile any number of … you control until ~ leaves the battlefield" (610.3)
            return _exile_until_cards(plan, ctx, {"as": binding}, picked)
        return exile_cards(plan, ctx, {"as": binding, "link": link}, picked)
    _sacrifice_cards(plan, picked, ctx["controller"], ctx, binding)
    return True


def _sacrifice_barred(plan: Plan, ctx: Context, pid: str) -> bool:
    """-- prohibitions (wave 22B) -- 614.17: this resolution is an opponent's spell or ability and ``pid`` has "can't cause you to sacrifice"."""
    from app.rules import prohibitions

    why = prohibitions.cant_cause_sacrifice(plan, pid, ctx["controller"])
    if why is not None:
        plan.note(f"{why}: {plan.name(pid)} can't be made to sacrifice permanents")
    return why is not None


def _sacrifice_cards(plan: Plan, cards: list[str], actor: str, ctx: Context | None = None, binding: str | None = None) -> None:
    """701.21a: each to its owner's graveyard, all at once (one move, one event batch: a "one or
    more" trigger fires once, 603.2c). ``binding``: recorded for "its power" / "creatures
    sacrificed this way" — as they were (608.2h), and the cards they became (400.7j)."""
    cards = [c for c in cards if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")]
    if ctx is not None:  # -- prohibitions (wave 22B) -- 614.17: "Spells and abilities your opponents control can't cause you to sacrifice permanents."
        from app.rules import prohibitions

        cards = [c for c in cards if not prohibitions.cant_cause_sacrifice(plan, plan.state.cards[c].controller, ctx["controller"])]
    e = {"as": binding}
    before = _remember(plan, ctx, e, cards) if ctx is not None else []
    if cards:
        from app.rules.triggers import sacrificing  # (triggers imports this module)

        sacrificing(plan, cards)
        if ctx is not None and ctx.pop("exploiting", False):  # -- keyword triggers (wave 23D) -- 702.110b
            from app.rules.triggers import exploiting

            exploiting(plan, cards, ctx["source_card"], ctx["controller"])
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "graveyard"}}, actor=actor)
    if ctx is not None:
        _moved(plan, ctx, e, before)


def resume_sacrifice_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    picked = [*(r.get("picked") or []), *chosen]
    if _sacrifice_next(plan, r["ctx"], r["sel"], r["want"], r.get("rest") or [], picked, r.get("as"), r.get("exile", False),
                       r.get("link", False), r.get("upto", False)):
        continue_effects(plan, r["ctx"])


def return_card(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Return cards (the target, or those matching) from a graveyard / exile to a hand or the
    battlefield: "to your hand", "to its owner's hand", "to the battlefield [tapped] [under your
    control]". A card that left its zone isn't there to return (a new object, 400.7)."""
    # A pronoun ("return it …") names the card an earlier instruction of this effect put there
    # (400.7j); one that isn't there any more — or a token, which ceased to exist (111.7, 111.8)
    # — is nothing to return (603.7c's principle: not in the zone it's expected in).
    # -- reanimation (wave 37B) -- ``also``: "Return this card and target land card …" (Sandman): the source too, both in one move (608.2c)
    cards = [c for w in (e["who"], e.get("also")) if w for c in _cards(plan, ctx, w) if not plan.state.cards[c].zone.endswith(":battlefield")]
    return _return_cards(plan, ctx, e, list(dict.fromkeys(cards)))


def _return_cards(plan: Plan, ctx: Context, e: dict[str, Any], cards: list[str]) -> bool:
    from app.rules import attachments  # attachments → effects (resume)

    before = _remember(plan, ctx, e, cards)
    if e["to"] == "library_top":  # -- refused zones/sized (wave 3R4) -- "put a land card from your graveyard on top of
        for cid in cards[:1]:  # your library": one card, to its owner's library (400.3)
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "library"},
                     "position": "top"}, actor=ctx["controller"])
        _moved(plan, ctx, e, before)
        return True
    if e["to"] == "choose":  # -- if you do (wave 25C) -- "Choose an instant or sorcery card in your graveyard.": only the choice, bound for "it" after
        return True
    if e["to"] == "exile":  # -- if you do (wave 25C) -- "Exile an instant or sorcery card at random from your graveyard": face up, in its owner's exile (400.3)
        for cid in cards:
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "exile"}}, actor=ctx["controller"])
        _moved(plan, ctx, e, before)
        return True
    if e["to"] == "graveyard":  # -- resolution memory (wave 22D) -- "put the exiled card into its owner's graveyard"
        for cid in cards:
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "graveyard"}}, actor=ctx["controller"])
        _moved(plan, ctx, e, before)
        return True
    if e["to"] == "hand":
        for cid in cards:  # (400.3: a card goes to its OWNER's hand, whoever's graveyard it was in)
            card = plan.state.cards[cid]
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": card.owner, "zone": "hand"}}, actor=ctx["controller"])
        _moved(plan, ctx, e, before)
        return True
    if e.get("face_down"):  # -- hidden exile (wave 18A) -- 708.4: enters face down (a 2/2 creature; turned up with its morph cost)
        from app.rules import facedown

        for cid in cards:
            facedown.put_face_down(plan, cid, ctx["controller"] if e.get("under") == "you" else plan.state.cards[cid].owner,
                                   "generic", actor=ctx["controller"], spec=e.get("spec"))
        _moved(plan, ctx, e, before)
        return True
    entries = [{"card": cid, "player": ctx["controller"] if e.get("under") == "you" else plan.state.cards[cid].owner,
                "actor": ctx["controller"], "tapped": bool(e.get("tapped")),
                **({"transformed": True} if e.get("transformed") else {}),  # (-- transform, wave 11A -- 712.14a)
                **({"counter": e["counter"]} if e.get("counter") and (not e.get("counter_if") or selectors.matches(
                    plan, selectors.from_key(e["counter_if"]), plan.state.cards[cid], plan.ch(plan.state.cards[cid]), ctx["controller"])) else {}),
                **({"counter_n": e["counter_n"]} if e.get("counter_n") else {})} for cid in cards]  # (counters it enters with, 122.6; n: wave 4M; counter_if: wave 44A)
    nxt = ctx["effects"][ctx["next"]] if e.get("as") and 0 <= ctx.get("next", -1) < len(ctx.get("effects") or ()) else {}
    if nxt.get("do") == "become" and nxt.get("lose_abilities") and nxt.get("who") == f"ref:{e['as']}" and nxt.get("duration") == "permanent":
        # -- review 35 -- "Return target creature card … to the battlefield. It's a Skeleton … and has no abilities." (Xu-Ifit, ruling 2025-07-25): it has
        # none as it enters — no "enters tapped" or "enters with" counters of its own apply (614.12), no "when it enters" triggers
        entries = [{**x, "bare": True} for x in entries]
    if e.get("host"):  # -- refused zones/sized (wave 3R4) -- "attached to this creature / that creature"
        entries = _attached_entries(plan, ctx, e["host"], entries)
        cards = [x["card"] for x in entries]
    done = attachments.enter(plan, entries, ctx)
    if done:  # (an Aura choosing what it enchants pauses: the binding then keeps what they were)
        _moved(plan, ctx, e, before)  # the permanents they became: new objects (400.7)
    if done and e.get("attacking"):  # -- refused zones/sized (wave 3R4) -- "tapped and attacking" (508.4)
        return refused_zones.enter_attacking(plan, ctx, cards, e.get("at"))
    return done


def _attached_entries(plan: Plan, ctx: Context, host_ref: str, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """-- refused zones/sized (wave 3R4) -- An effect that puts a card onto the battlefield attached to an object
    (``self``: the source, ``event``: the trigger's object — each only while it is still that permanent). An Aura
    that can't legally enchant it (or with nothing there) stays where it is (303.4i); an Equipment enters
    unattached (301.5e); anything else enters unattached (303.4h)."""
    from app.rules import attachments

    hosts = [c for c in _cards(plan, ctx, host_ref) if plan.state.cards[c].zone.endswith(":battlefield")]
    host = hosts[0] if len(hosts) == 1 else None
    out = []
    for entry in entries:
        card = plan.state.cards[entry["card"]]
        kind = attachments.attach_kind(plan.ch(card))
        legal = host is not None and attachments.host_problem(plan, card, host, entry["player"]) is None
        if kind == "aura" and not legal:
            plan.note("The Aura can't be attached to that: it stays where it is (303.4i)", [card.id])
            continue
        out.append({**entry, "host": host} if legal and kind is not None else entry)
    return out


def pay_or_sacrifice(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Sacrifice ~ unless you pay {cost}" (and echo, 702.30): its controller chooses; paying is
    offered only when they can."""
    from app.rules import mana  # casting imports this module

    pid = ctx["controller"]
    src = [c for c in _cards(plan, ctx, "self") if plan.state.cards[c].controller == pid]
    if not src:
        # it already left — or 701.21a: another player controls it now (echo, "sacrifice ~ unless
        # you pay" after a control change): it can't be sacrificed, so there's nothing to choose
        return True
    if e["cost"] == "mana_cost":  # -- cost alt (wave 16F) -- "unless you pay its mana cost": what is printed on it (X is 0 off the stack,
        # 202.3e); an object with no mana cost has nothing to pay: it is sacrificed
        printed = (plan.ch(plan.state.cards[src[0]]).mana_cost or "").replace("{X}", "")
        if not printed:
            decide(plan, player=pid, kind="choose_one", prompt=f"{ctx.get('name', '')}: it has no mana cost to pay: sacrifice it",
                   options=[DecisionOption(id="sacrifice", label=f"Sacrifice {plan.state.cards[src[0]].name}")],
                   resume={"step": "pay_or_sacrifice", "ctx": ctx, "cost": "{0}"}, source=plan.state.cards[src[0]])
            return False
        e = {**e, "cost": printed}
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
            counter_object(plan, sid, d.player, by=ctx["controller"])
        continue_effects(plan, ctx)
        return
    src = [c for c in _cards(plan, ctx, "self") if plan.state.cards[c].controller == d.player]  # (701.21a)
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


def unattach_self(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """-- casting extras (wave 18E) -- 702.151a reconfigure: "Unattach this permanent." (701.3d: nothing if it isn't attached)."""
    src = _cards(plan, ctx, "self")
    if src and plan.state.cards[src[0]].attached_to:
        plan.do({"type": "detach", "card_ids": [src[0]]}, actor=ctx["controller"])
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
    "attach_self": attach_self, "unattach_self": unattach_self,
    "draw": draw, "gain_life": gain_life, "lose_life": lose_life, "damage": damage, "pump": pump, "grant": grant,
    "destroy": destroy, "exile": exile, "bounce": bounce, "tap": tap, "untap": untap, "scry": scry, "surveil": surveil,
    "player_counter": player_counter, "create_token": create_token, "add_counters": add_counters,
    "proliferate": proliferate, "destroy_all": destroy_all, "blink": blink, "search": search, "monarch": monarch,
    "discard": discard, "regenerate": regenerate, "no_regen": no_regen, "no_regen_turn": no_regen_turn,
    "animate": animate, "pay_or_sacrifice": pay_or_sacrifice, "renown": renown, "return_yours": return_yours, "return_any": return_any, "suspend_tick": suspend_tick, "cascade": cascade, "unearth": unearth, "delayed_move": delayed_move,
    "madness_offer": madness_offer, "free_cast_offer": free_cast_offer, "counter": counter, "counter_unless": counter_unless,
    "sacrifice": sacrifice, "ascend": ascend, "explore": explore, "prevent": prevent, "prevent_all": replacements.prevent_all, "mill": mill,
    "return_with_counter": return_with_counter, "exile_until": exile_until, "return_linked": return_linked,
    "fabricate": fabricate, "storm": storm,
    "fight": fight, "choose_targets": choose_targets,
    "double_counters": double_counters, "lki_counters": lki_counters,  # (wave 5H; move_counters: wave 12A, app/rules/counter_moves.py)
}
# -- copy system (wave 2F): copying spells, abilities and permanents (CR 707; app/rules/copying.py,
# which imports this module lazily) --
from app.rules import copying  # noqa: E402

PRIMITIVES.update(copying.PRIMITIVES)
from app.rules import crew_saddle, phasing  # noqa: E402

PRIMITIVES.update(phasing.PRIMITIVES)  # -- phasing (wave 13D) -- 702.26
PRIMITIVES.update(crew_saddle.PRIMITIVES)  # -- crew & saddle (wave 23D) -- 702.171
PRIMITIVES.update(entry_forms.PRIMITIVES)  # -- entry forms (wave 5F) -- "It's an enchantment." (611.2e)
from app.rules import merged as _merged  # noqa: E402

PRIMITIVES.update(_merged.PRIMITIVES)  # -- merged permanents (wave 18D) -- meld, 701.42
# -- resolution memory (wave 22D) --
from app.rules import exiled_with as _exiled_with  # noqa: E402

PRIMITIVES.update(_exiled_with.PRIMITIVES)


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
    # -- review 30 -- one move (401.4: the cards go in at the same time and their order isn't revealed; one move per card logged it)
    if r["place"] == "top":  # the first chosen card goes on top (a move to the top puts its cards in their order)
        plan.do({"type": "move", "card_ids": list(chosen), "to": {"player": owner, "zone": "library"}, "position": "top"}, actor=pid)
    elif chosen:  # the first chosen ends at the very bottom
        plan.do({"type": "move", "card_ids": list(reversed(chosen)), "to": {"player": owner, "zone": "library"}, "position": "bottom"},
                actor=pid)
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
    if e.get("optional") and not ctx.pop("reveal_asked", None):  # -- if you do (wave 15C) -- "you may reveal the top card": asked first
        decide(plan, player=ctx["controller"], kind="confirm", prompt=f"{ctx.get('name') or 'It'}: reveal the top " + (f"{e['n']} cards" if isinstance(e.get("n"), int) and e["n"] > 1 else "card")
               + " of your library?",  # (wave 17C: "Ripple 4")
               options=[DecisionOption(id="yes", label="Reveal it"), DecisionOption(id="no", label="Don't reveal")],
               resume={"step": "look_may", "ctx": ctx, "e": e})
        return False
    ctx["looked"], ctx["found"] = [], None
    ctx.pop("looked_zone", None)  # (wave 10C: a look is at a library; a mill's cards are in a graveyard)
    ctx["looked_owner"] = owners[0] if len(owners) == 1 else None
    cards: list[str] = []
    for pid in owners:
        library = _library(plan, pid)
        if e.get("until"):
            at = _first_match(plan, ctx, library, e["until"], ctx["controller"])
            for _ in range(int(e.get("need") or 1) - 1):  # -- trigger other (wave 44B) -- "until they reveal four land cards": down to the Nth match (all of it if fewer)
                if at is None:
                    break
                nxt = _first_match(plan, ctx, library[at + 1:], e["until"], ctx["controller"])
                at = None if nxt is None else at + 1 + nxt
            top = library if at is None else library[: at + 1]
            if at is not None and len(owners) == 1 and not e.get("need"):
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
    _remember(plan, ctx, e, [ctx["found"]] if ctx.get("found") else [] if e.get("until") else cards)  # (wave 20A: none found: no "that card")
    return True


def resume_draw_may(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    if chosen[0] == "yes":
        ctx["may_ok"] = ctx["next"]
        if not draw(plan, ctx, e):
            return
    else:
        plan.note(f"{plan.name(d.player)} chose not to draw", actor=d.player)
    continue_effects(plan, ctx)


def resume_look_may(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    if chosen[0] == "yes":
        ctx["reveal_asked"] = True
        look_top(plan, ctx, e)
    else:
        plan.note(f"{plan.name(d.player)} chose not to reveal", actor=d.player)
        ctx["looked"], ctx["found"] = [], None
        _remember(plan, ctx, e, [])
    continue_effects(plan, ctx)


def _looked(plan: Plan, ctx: Context) -> tuple[str, list[str]]:
    """(the library's owner, the set-aside cards still in that library)."""
    pid = ctx.get("looked_owner") or ctx["controller"]
    library = plan.state.zones.get(zone_key(pid, ctx.get("looked_zone") or "library"), [])  # (wave 10C: milled cards, in the graveyard)
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
    if e.get("by_owner"):  # -- most-played cards (wave 43B) -- "they put it onto the battlefield" / "that player puts it into their hand": the library's owner is the one who puts it
        pid = owner
    ctx["looked"] = looked
    sel = selectors.from_key(e["sel"]) if e.get("sel") else None
    options = [c for c in looked if sel is None  # (the source: "of the chosen type", wave 5I)
               or selectors.matches(plan, sel, plan.state.cards[c], chars.of(plan.state.cards[c], plan.info), pid,
                                    ctx.get("source_card"))]
    if e.get("sels"):  # -- refused look/cast-free (wave 3R5) -- "a creature card and/or a land card": any listed kind
        from app.rules import looking

        options = [c for c in options if looking.kinds_of(plan, pid, c, e["sels"])]
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
    if e.get("sels"):  # -- refused look/cast-free (wave 3R5) -- one card of each kind, each a different card
        from app.rules import looking

        if not looking.distinct_kinds(plan, ctx["controller"], list(chosen), e["sels"]):
            from app.game.errors import ActionError

            raise ActionError("Choose at most one card of each kind")
    if _picked(plan, ctx, e, list(chosen)):
        continue_effects(plan, ctx)


def _picked(plan: Plan, ctx: Context, e: dict[str, Any], chosen: list[str]) -> bool:
    """Move the picked cards where the instruction says; False while an Aura entering chooses."""
    from app.rules import attachments  # attachments → effects (resume)

    pid = _looked(plan, ctx)[0] if e.get("by_owner") else ctx["controller"]  # (wave 43B: the library's owner puts the card)
    if chosen and e.get("reveal"):
        plan.do({"type": "reveal", "card_ids": chosen}, actor=pid)  # to everyone
    ctx["looked"] = [c for c in ctx.get("looked") or [] if c not in chosen]
    if ctx.get("found") in chosen:
        ctx["found"] = None
    before = _remember(plan, ctx, e, chosen)
    # -- look and distribute (wave 3L) -- "If you don't [put the card …]" reads what this pick did
    # (a probe like draw's: the picked objects, as they were, and the zone they should reach)
    if e.get("did"):
        zone = {"battlefield_tapped": "battlefield", "battlefield_attacking": "battlefield", "top": "library",
                "bottom": "library"}.get(e["to"], e["to"])
        context.refs(ctx)[e["did"]] = {"kind": "probe", "to": zone, "cards": {c: plan.oid(plan.state.cards[c]) for c in chosen}}
    if e["to"] in ("top", "bottom"):  # "put it on top of / on the bottom of your library": the owner's (private order)
        for cid in chosen:
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "library"},
                     "position": e["to"]}, actor=pid)
    elif e["to"] in ("hand", "graveyard", "exile"):
        for cid in chosen:  # (a graveyard or exile is the owner's; "your hand" yours)
            to = pid if e["to"] == "hand" else plan.state.cards[cid].owner
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": to, "zone": e["to"]},
                     **({"face_down": True} if e.get("face_down") else {})}, actor=pid)
        if e["to"] == "exile" and e.get("link"):  # -- resolution memory (wave 22D) -- 607.2a: "exile one of them" linked to "the exiled card"
            from app.rules import exiled_with

            exiled_with.record(plan, ctx, chosen)
        if e.get("hideaway"):  # -- hideaway (wave 29D) -- 702.75a: whoever controls the permanent may look at the exiled card
            from app.rules import hideaway

            hideaway.record(plan, ctx, chosen)
    else:
        entries = [{"card": c, "player": pid, "actor": pid, "tapped": e["to"] in ("battlefield_tapped", "battlefield_attacking"),
                    **({"counter": e["counter"], "counter_n": e.get("counter_n", 1)} if e.get("counter") else {})}  # (wave 3E)
                   for c in chosen]
        if not attachments.enter(plan, entries, ctx):
            return False
    _moved(plan, ctx, e, before)
    if e["to"] == "battlefield_attacking":  # -- refused look/cast-free (wave 3R5) -- 508.4
        from app.rules import looking

        return looking.attack_with_entered(plan, ctx, chosen, e.get("at"))
    return True


def rest_looked(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"… and the rest into your graveyard / on the bottom of your library in any order / in a
    random order", "put them back in any order" (``to``: "top_any"), "exile the rest". "In any
    order" is the player's private choice (401.4: the order isn't revealed); "in a random order"
    is the table's randomness, recorded as moves (replay is deterministic)."""
    pid = ctx["controller"]
    owner, rest = _looked(plan, ctx)
    ctx["looked"] = []
    before = _remember(plan, ctx, e, rest)  # (wave 44A: "for each card put into your graveyard this way")
    if not rest:
        return True
    if e["to"] in ("graveyard", "exile"):
        plan.do({"type": "move", "card_ids": rest, "to": {"player": owner, "zone": e["to"]}}, actor=pid)
        _moved(plan, ctx, e, before)
        return True
    if e["to"] == "hand":
        plan.do({"type": "move", "card_ids": rest, "to": {"player": pid, "zone": "hand"}}, actor=pid)
        _moved(plan, ctx, e, before)
        return True
    if e["to"] == "top_any":
        if len(rest) == 1:
            return True  # (already there)
        place = "top"
    else:
        place = "bottom"
        if e["to"] == "bottom_random" or len(rest) == 1:
            bottom_at_random(plan, owner, rest, actor=pid)  # (-- review 30 -- one move: one move per card made the order readable, 401.4)
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
    taken: list[str] = []
    ctx["found"] = None
    for pid in owners:
        library = _library(plan, pid)
        if e.get("until"):
            at = _first_match(plan, ctx, library, e["until"], ctx["controller"])
            n = len(library) if at is None else at + 1
            if at is not None and len(owners) == 1:
                ctx["found"] = library[at]
        elif e.get("keep_bottom") is not None:  # -- hidden exile (wave 18A) -- "all but the bottom six cards of their library"
            n = max(0, len(library) - int(e["keep_bottom"]))
        else:
            n = min(_amount(plan, ctx, e["n"]), len(library))
        if not n:
            continue
        before += [r for r in (context.ref_of(plan, c) for c in library[:n]) if r is not None]
        taken += library[:n]
        plan.do({"type": "mill", "player": pid, "count": n, "to": "exile", "face_down": bool(e.get("face_down")),
                 "blind": bool(e.get("face_down"))}, actor=pid)
    if e.get("link"):  # -- tutor (wave 20D) -- 607.2a: "exile the top card of your library face down" linked to "Put all cards exiled with ~ into their owners' hands"
        from app.rules import exiled_with

        exiled_with.record(plan, ctx, taken)
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
    for cid in cards if e.get("reveal") else ():  # -- if you do (wave 44A) -- 701.20a: "that player reveals the chosen card, puts it on the bottom" (Vendilion Clique): shown to everyone first
        if plan.state.cards[cid].zone.endswith(":hand"):
            plan.do({"type": "reveal", "card_ids": [cid]}, actor=plan.state.cards[cid].owner)
    if e["place"] == "shuffle":
        for cid in cards:
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "library"}},
                    actor=ctx["controller"])
        for pid in sorted(owners):
            plan.do({"type": "shuffle", "player": pid, "zone": "library"}, actor=pid)
        _moved(plan, ctx, e, before)  # (new objects: a shuffled library is re-keyed, 701.20d)
        return True
    if isinstance(e["place"], int):  # -- trigger tail (wave 15B) -- "third from the top": one card, its owner's library (401.4)
        for cid in cards:
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "library"},
                     "index": e["place"] - 1}, actor=ctx["controller"])
        _moved(plan, ctx, e, before)
        return True
    if e["place"] in ("choice", "choice_second", "choice_you") and len(cards) == 1:
        card = plan.state.cards[cards[0]]
        second = e["place"] == "choice_second"  # -- static_other sweep (wave 17C) -- "second from the top or on the bottom" (Lost Days)
        # (-- ability words (wave 20C) -- "on your choice of the top or bottom of its owner's library": the controller chooses)
        decide(plan, player=ctx["controller"] if e["place"] == "choice_you" else card.owner, kind="choose_one",
               prompt=f"Put {card.name} " + ("second from the top or on the bottom of your library?" if second else "on the top or the bottom of its owner's library?" if e["place"] == "choice_you" else "on the top or the bottom of your library?"),
               options=[DecisionOption(id="second" if second else "top", label="Second from the top" if second else "On top"),
                        DecisionOption(id="bottom", label="On the bottom")],
               resume={"step": "library_place", "card": card.id, "ctx": ctx, "e": e, "before": [r.model_dump(mode="json") for r in before]},
               source=card)
        return False
    place = "bottom" if e["place"] == "bottom" else "top"
    pending = [(pid, [c for c in cards if plan.state.cards[c].owner == pid]) for pid in sorted(owners)]
    multiple = [(pid, mine) for pid, mine in pending if len(mine) > 1]
    for pid, mine in pending:
        if len(mine) == 1:
            plan.do({"type": "move", "card_ids": mine, "to": {"player": pid, "zone": "library"}, "position": place}, actor=ctx["controller"])
            pile = [c for c in _merged.pieces(plan, mine) if plan.state.cards[c].zone == zone_key(pid, "library")]
            if len(pile) > 1:  # -- review (wave 18D) -- 730.3a / 712.21a: a merged permanent's owner arranges its cards (unrevealed)
                multiple.append((pid, pile))
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
        where = {"index": 1} if chosen[0] == "second" else {"position": chosen[0]}  # (the index: 2nd from the top, 401.4)
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "library"}, **where}, actor=d.player)
        pile = [c for c in _merged.pieces(plan, [card.id]) if plan.state.cards[c].zone == zone_key(card.owner, "library")]
        if len(pile) > 1 and chosen[0] != "second":  # -- review (wave 18D) -- 730.3a: its owner arranges a merged permanent's cards
            ctx.update(library_before=r["before"], library_e=e, library_queue=[])
            _ask_order(plan, ctx, card.owner, card.owner, pile, chosen[0])
            return
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
    players = _players(plan, ctx, e["who"])
    # (-- static_other sweep (wave 16B) -- "then draws that many cards": the cards shuffled in are the binding "as", each its owner's)
    before = _remember(plan, ctx, e, [c for pid in players for zone in e.get("zones") or [] for c in plan.state.zones.get(zone_key(pid, zone), [])])
    for pid in players:
        for zone in e.get("zones") or []:
            cards = list(plan.state.zones.get(zone_key(pid, zone), []))
            if e.get("sel"):  # (wave 16C: "all creature cards from your graveyard")
                keep = set(_cards(plan, ctx, e["sel"]))
                cards = [c for c in cards if c in keep]
            if cards:
                plan.do({"type": "move", "card_ids": cards, "to": {"player": pid, "zone": "library"}}, actor=pid)
        plan.do({"type": "shuffle", "player": pid, "zone": "library"}, actor=pid)
    _moved(plan, ctx, e, before)
    return True


def resume_shuffle_library(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx = d.resume["ctx"]
    if chosen[0] == "yes":
        shuffle_library(plan, ctx, d.resume["e"])
    continue_effects(plan, ctx)


PRIMITIVES.update({"ripple_split": ripple_split, "ripple_cast": ripple_cast})  # (wave 17C)
PRIMITIVES.update({"look_top": look_top, "pick_looked": pick_looked, "rest_looked": rest_looked, "exile_top": exile_top,
                   "to_library": to_library, "shuffle_library": shuffle_library, "grant_play": permissions.grant_play,
                   "free_cast": permissions.free_cast,  # (free_cast: wave 3C)
                   "rest_exiled": permissions.rest_exiled, "found_to": permissions.found_to})
from app.rules import looking as _looking  # noqa: E402, I001  -- refused look/cast-free (wave 3R5) -- (a leaf module)

PRIMITIVES["piles"] = _looking.piles
PRIMITIVES["piles_down"] = _looking.piles_down  # -- hidden exile (wave 18A) -- a face-down pile and a face-up pile
PRIMITIVES["win_if_library"] = _looking.win_if_library  # -- refused look/cast-free (wave 3R5) --
from app.rules import reveal_hand as _reveal_hand  # noqa: E402, I001  -- if you do (wave 10C) -- (a leaf module)

PRIMITIVES["reveal_hand_cards"] = _reveal_hand.reveal_hand_cards


def only_if(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"If [condition], [the next ``skip`` effects]" (608.2c), and an intervening "if" checked
    again as the ability resolves (603.4): when it doesn't hold, those effects don't happen.
    With ``bind`` (an "instead" / "Otherwise" clause follows, conditional / instead clauses wave 1B) the
    verdict is recorded under that name as the resolution reaches it: the clause that belongs to it
    reads that verdict, it doesn't judge the table a second time (608.2c)."""
    from app.rules import conditions

    ok = conditions.holds(plan, ctx, e["cond"])
    if e.get("bind"):
        context.bind_flag(ctx, e["bind"], ok)
    if not ok:
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e.get("skip", len(ctx["effects"]))))
    return True


PRIMITIVES.update({"only_if": only_if})
# -- kinship (wave 9C) -- the look-and-reveal step of a kinship ability (app/rules/kinship.py)
from app.rules import kinship as _kinship  # noqa: E402

PRIMITIVES["kinship"] = _kinship.run
from app.rules import voting as _voting  # noqa: E402, I001  -- voting (wave 18C) --

PRIMITIVES.update(_voting.PRIMITIVES)
from app.rules import tempting as _tempting  # noqa: E402, I001  -- tempting offers (wave 18C) --

PRIMITIVES.update(_tempting.PRIMITIVES)
from app.rules import friend_foe as _friend_foe  # noqa: E402, I001  -- friend or foe (wave 18C) --

PRIMITIVES.update(_friend_foe.PRIMITIVES)
from app.rules import parley as _parley  # noqa: E402  -- parley (wave 9C) --

PRIMITIVES.update({"parley_reveal": _parley.reveal, "parley_repeat": _parley.repeat})
# "You may pay {2}. If you do, …" / "… unless that player pays {1}" (118.12): app/rules/optional_payment.py
PRIMITIVES["optional_payment"] = optional_payment.optional_payment


def _did(fn: Any, kind: str) -> Any:
    """An instruction whose "If you do" is judged by whether the player started it ("did": a binding name, ``{"succeeded": name}``
    in the gate after it, 118.12): an object was there to take, wherever it ends up (a token is gone as it arrives, a commander may go
    to the command zone instead, 903.9b); an object already gone can't be (400.7). Probed before the first run only: a paused
    primitive runs again (616.1). (A draw binds its own "did": ``draw``.)"""
    def run(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
        name = e.get("did")
        if name and name not in context.refs(ctx):
            context.refs(ctx)[name] = {"kind": "probe", "to": kind, "cards": {
                c: plan.oid(plan.state.cards[c]) for c in _from_zone(plan, e, _cards(plan, ctx, e["who"]))}}
        return bool(fn(plan, ctx, e))
    return run


for _name in ("exile", "bounce"):
    PRIMITIVES[_name] = _did(PRIMITIVES[_name], {"exile": "exile", "bounce": "hand"}[_name])


def _did_counters_up(fn: Any) -> Any:
    """-- if you do (wave 15C) -- "You may put three +1/+1 counters on target land you control. If you do, …": the put was allowed
    (118.12; Solemnity — "can't", 614.17b — makes it false, a reduction to none — Vizier of Remedies, Vorinclex — doesn't: the
    Devoted Druid ruling of 2018-12-07, 118.11). A reflexive "When you do" ("reflex", scripts._probe_previous, 603.12) reads the
    event instead: the counters really reached the object (the Auron ruling of 2025-06-06)."""
    def run(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
        from app.rules import prohibitions

        name = e.get("did")
        if name and name not in context.refs(ctx):
            cards = _cards(plan, ctx, e["who"])
            if e.get("reflex"):
                context.refs(ctx)[name] = {"kind": "probe", "counter": e["kind"], "counters_up": {
                    c: [plan.oid(plan.state.cards[c]), plan.state.cards[c].counters.get(e["kind"], 0)] for c in cards},
                    **({"per": e["n"]} if isinstance(e.get("n"), int) else {})}  # (review 33: _reflex_times)
            else:  # (the "cards" record of a move, context.probe_ok: the objects the put was allowed on)
                context.refs(ctx)[name] = {"kind": "probe", "to": "battlefield", "cards": {
                    c: plan.oid(plan.state.cards[c]) for c in cards if prohibitions.cant_counters(plan, c, None) is None}}
        return bool(fn(plan, ctx, e))
    return run


PRIMITIVES["add_counters"] = _did_counters_up(PRIMITIVES["add_counters"])


def _did_lose_life(fn: Any) -> Any:
    """-- if you do (wave 30G) -- "You may have target player lose 3 life. If you do, …" (Ob Nixilis, the Fallen): 118.12 — the player chose to
    pay it, "regardless of what events actually occurred" (a loss doubled, prevented or replaced was still done, 118.11) — unless that player's
    life total can't change: then the event can't happen and the cost can't be chosen (119.8, 614.17b; life_lock). Probed before the first run only."""
    def run(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
        from app.rules import life_lock

        name = e.get("did")
        if name and name not in context.refs(ctx):
            context.bind_payment(ctx, name, all(life_lock.why_not(plan, p, "lose") is None for p in _players(plan, ctx, e["who"])))
        return bool(fn(plan, ctx, e))
    return run


PRIMITIVES["lose_life"] = _did_lose_life(PRIMITIVES["lose_life"])


def _did_tap(fn: Any) -> Any:
    """-- if you do (wave 30G) -- "When this creature enters, you may tap it. When you do, …" (The Fire Nation Drill, Spider-Man, To the Rescue):
    118.12 — the player chose to pay it; only an untapped permanent can be tapped (701.26a), so one that is tapped already can't be paid (118.3).
    Probed before the first run only."""
    def run(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
        name = e.get("did")
        if name and name not in context.refs(ctx):
            cards = _cards(plan, ctx, e["who"])
            context.bind_payment(ctx, name, bool(cards) and not any(plan.state.cards[c].tapped for c in cards))
        return bool(fn(plan, ctx, e))
    return run


PRIMITIVES["tap"] = _did_tap(PRIMITIVES["tap"])


def _did_look(fn: Any) -> Any:
    """-- if you do (wave 31A) -- "You may reveal the top card of your library. If you do, each opponent loses life equal to that card's mana value." (Baneful
    Omen), "You may look at the top card of target opponent's library. If you do, …" (Precognition): 118.12 — the player chose to; a library with no card in it
    has none to reveal or look at (701.20a), so that can't be chosen. Probed before the first run only."""
    def run(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
        name = e.get("did")
        if name and name not in context.refs(ctx):
            context.bind_payment(ctx, name, all(_library(plan, p) for p in _library_owner(plan, ctx, e)))
        return bool(fn(plan, ctx, e))
    return run


PRIMITIVES["look_top"] = _did_look(PRIMITIVES["look_top"])


def _did_search(fn: Any) -> Any:
    """-- if you do (wave 31A) -- 118.12b: "Search your library for a Dragon permanent card and put it into your graveyard. If you do, …" (Scion of the Ur-Dragon)
    checks whether the player chose to search, not whether they found or took anything: true unless a prohibition stops the search (614.17: "Players can't
    search libraries"). Probed before the first run only."""
    def run(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
        name = e.get("did")
        if name and name not in context.refs(ctx):
            from app.rules import prohibitions

            context.bind_payment(ctx, name, prohibitions.cant_search(plan, ctx["controller"], ctx["controller"]) is None)
        return bool(fn(plan, ctx, e))
    return run


PRIMITIVES["search"] = _did_search(PRIMITIVES["search"])


# -- refused modal/conditional (wave 3R1) -- "Sacrifice this enchantment. If you do, …", "Remove a +1/+1 counter
# from it. If you do, …", "Discard a card. If you do, …": "If you do" after an instruction that isn't optional asks
# whether it was started (118.12; a permanent that is already gone can't be sacrificed, 701.21a; a counter
# that isn't there can't be removed, 122.8; an empty hand discards nothing, 701.9b). Probed like draw's above.
def _did_r1(fn: Any, kind: str) -> Any:
    def run(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
        name = e.get("did")
        if name and name not in context.refs(ctx):
            refs = context.refs(ctx)
            if kind == "leave":  # sacrificed: moved off the battlefield (to wherever a replacement sent it)
                if e["do"] in ("sacrifice_choice", "edict"):  # (wave 41C: an edict, "That player sacrifices a creature of their choice. If the player can't, …")
                    who = set(_players(plan, ctx, e["who"]))
                    cards = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller in who]
                else:
                    cards = [c for c in _cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
                refs[name] = {"kind": "probe", "left": {c: plan.oid(plan.state.cards[c]) for c in cards}}
            elif kind == "counters":
                refs[name] = {"kind": "probe", "counter": e["kind"], "counters": {
                    c: [plan.oid(plan.state.cards[c]), plan.state.cards[c].counters.get(e["kind"], 0)]
                    for c in _cards(plan, ctx, e["who"])}}
            else:  # discarded: a card left the hand
                players = _players(plan, ctx, e.get("who", "you")) if e.get("who") else [ctx["controller"]]
                refs[name] = {"kind": "probe", "hands_down": {p: len(plan.state.zones.get(f"{p}:hand", [])) for p in players}}
        return bool(fn(plan, ctx, e))
    return run


for _name, _kind in (("sacrifice", "leave"), ("sacrifice_choice", "leave"), ("remove_counters", "counters"),
                     ("discard", "discard")):
    PRIMITIVES[_name] = _did_r1(PRIMITIVES[_name], _kind)


def reflexive(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """603.12: "When you do, …" — a reflexive triggered ability: it triggers now, during the resolution, if the
    action it waits for was taken (a payment made, 118.12; an instruction carried out); like a delayed trigger
    (603.7) it is put on the stack the next time a player would receive priority (603.3), its controller choosing
    its modes and targets then (603.3c-d) — not while the ability that created it was announced. Its source is that
    ability's source; it has no trigger event of its own."""
    from app.rules import conditions
    from app.rules.triggers import _add  # (triggers imports this module)

    if conditions.holds(plan, ctx, e["cond"]):
        # (-- resolution memory (wave 22D) -- "cond_ref": the objects the counted "… this way" instruction acted on: "When you discard a card
        # this way, … that card's mana value")
        name = e["cond"]["value"]["ref_count"] if e.get("lki") == "cond_ref" else e.get("lki")
        event = _reflexive_event(plan, ctx, name) if name else None  # -- reflexive LKI (wave 4J) --
        if event is not None and e.get("lki") == "cond_ref":  # -- reflexive this way (wave 30G) -- "that many" / "that much": how many it did this to (608.2c, 608.2h)
            event = event.model_copy(update={"amount": _this_way.count(plan, ctx, e["cond"]["value"])})
        if e.get("keep_event") and event is None and ctx.get("event"):  # -- reflexive this way (wave 30G) -- "that player" is still the trigger's
            from app.game.rules_state import TriggerEvent

            event = TriggerEvent.model_validate(ctx["event"])
        if e.get("x_from"):  # -- if you do (wave 25C) -- "you may pay {X}. When you do, …": the X paid is the reflexive ability's amount
            from app.game.rules_state import TriggerEvent
            from app.rules import paid_x

            paid = paid_x.amount(ctx, e["x_from"])
            outer = TriggerEvent.model_validate(ctx["event"]) if ctx.get("event") else None
            event = outer.model_copy(update={"amount": paid}) if outer is not None else TriggerEvent(kind="reflexive", amount=paid)
        # (-- reflexive this way (wave 30G) -- "each": one reflexive ability for each object the event happened to, each about its own object:
        # the rulings of Ajani, Nacatl Avenger (a Doubling Season makes two Cat Warriors: two triggers), 603.12a)
        for ev in ([event.model_copy(update={"objects": [o], "count": 1, "amount": 1}) for o in event.objects
                    if any(new["card"] == o.card for new, _ in _this_way._matched(plan, ctx, e["cond"]["value"]))]
                   if e.get("each") and event is not None else [event] * _reflex_times(plan, ctx, e["cond"])):
            _add(plan, controller=ctx["controller"], source_card=ctx.get("source_card") or "", source_object=ctx.get("source_object") or "",
                 name=str(ctx.get("name") or ""), index=7300, definition=e["ability"], event=ev)
    return True


def _reflex_times(plan: Plan, ctx: Context, cond: Any) -> int:
    """-- review 33 -- 603.12a: "Put two quest counters on ~. When you do, …" triggers once each time that was done: once for every two
    counters the put really added to that one object (a Doubling Season's four: twice — the rulings of Craig Boone, Novac Guard and Etched
    Slith; a Hardened Scales' three: once). Anything else (several objects, an amount that isn't a number) triggers once."""
    b = context.refs(ctx).get(cond.get("succeeded") or "") if isinstance(cond, dict) and isinstance(cond.get("succeeded"), str) else None
    per = (b or {}).get("per")
    if not b or not isinstance(per, int) or per <= 0 or len(b.get("counters_up") or {}) != 1:
        return 1
    (cid, (oid, before)), = b["counters_up"].items()
    card = plan.state.cards.get(cid)
    if card is None or plan.oid(card) != oid:
        return 1
    return max(1, (card.counters.get(b["counter"], 0) - int(before)) // per)


# -- reflexive LKI (wave 4J) --
def _reflexive_event(plan: Plan, ctx: Context, name: str) -> Any:
    """The object the payment a reflexive trigger waited for sacrificed (its binding), with its last known
    information (608.2h, 113.7a): the trigger's event object, which "that creature's power" in its body reads
    (scripts._reflexive_lki)."""
    from app.game.rules_state import TriggerEvent

    b = context.refs(ctx).get(name) or {}
    before = [ObjectRef.model_validate(r) for r in b.get("objects") or []] if b.get("kind") in ("payment", "objects") else []
    if b.get("kind") == "probe" and b.get("to") == "exile":  # -- reflexive exile (wave 41B) -- the object an exile was about to take (_did): its last known information
        before = [ObjectRef(card=c, object_id=o) for c, o in (b.get("cards") or {}).items()]
    elif b.get("kind") == "probe" and b.get("left"):  # (… or the permanents that were there when "exile … until" chose and are not any more: a token ceased to exist, 111.7)
        before = [ObjectRef(card=c, object_id=o) for c, o in b["left"].items()
                  if (card := plan.state.cards.get(c)) is None or (card.zone.endswith(":exile") and plan.oid(card) != o)]
    if b.get("kind") == "objects" and b.get("was"):
        # -- reflexive this way (wave 30G) -- an instruction that moved its objects ("Sacrifice a creature. When you do, … that creature's
        # power"): an object that left the battlefield is read as it last existed there (608.2h), not as the new object it became (400.7)
        was = [ObjectRef.model_validate(r) for r in b["was"]]
        before = [w if context.snapshot(plan, w) is not None and w.object_id != n.object_id else n for n, w in zip(before, was, strict=False)]
    objects = [r.model_copy(update={"snapshot": context.snapshot(plan, r)}) for r in before]
    return TriggerEvent(kind="reflexive", objects=objects, count=len(objects))
# -- end reflexive LKI (wave 4J) --


PRIMITIVES["reflexive"] = reflexive
# -- "this way" outcomes (wave 4A) -- "Tap any number of untapped creatures you control." (app/rules/this_way.py)
PRIMITIVES["tap_choice"] = _this_way.tap_choice
# -- end refused modal/conditional (wave 3R1) --


def kicked_gate(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.33e: "If this spell was kicked, …" (``kicked`` True) — and, for "… instead", the
    unkicked text (``kicked`` False): the next ``n`` effects happen only if the spell was (or
    wasn't) kicked; otherwise they're skipped."""
    if (values.kicked_count(plan, ctx) > 0) != bool(e["kicked"]):
        ctx["next"] += int(e["n"])
    return True


PRIMITIVES["kicked_gate"] = kicked_gate


# -- resolving a definition -----------------------------------------------------------------
@contextlib.contextmanager
def reading_x(plan: Plan, x: int | None) -> Iterator[None]:
    """-- X from the triggering object (wave 34C) -- while an ability resolves, a selector comparing with X ("mana value X": selectors.X_VALUE)
    reads the X it was put on the stack with (107.3a, 107.3e), as it reads a spell's own (its stack_info) or the one announced while casting."""
    before = plan.x_choice
    if x is not None:
        plan.x_choice = x
    try:
        yield
    finally:
        plan.x_choice = before


def begin_resolution(plan: Plan, stack_id: str, entry: StackEntry) -> None:
    with reading_x(plan, entry.x):
        _begin_resolution(plan, stack_id, entry)


def _begin_resolution(plan: Plan, stack_id: str, entry: StackEntry) -> None:
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
    gate = entry.effects[0] if entry.optional and entry.effects else None
    if gate is not None and gate["do"] == "only_if" and not gate.get("bind") and int(gate.get("skip", 0)) >= len(entry.effects) - 1:
        # -- this-turn history (wave 4D) -- 603.4: an intervening "if" that no longer holds: the ability does
        # nothing — there's nothing to ask (603.5)
        from app.rules import conditions

        if not conditions.holds(plan, ctx, gate["cond"]):
            plan.note(f"{entry.name or 'It'} does nothing: its condition no longer holds")
            finish(plan, ctx)
            return
    if entry.optional and entry.effects and barred_search(plan, ctx, entry.effects[0]):
        finish(plan, ctx)  # (-- prohibitions (wave 24D) -- "you may search …" can't be chosen: nothing is asked, nothing shuffled)
        return
    if entry.optional:
        from app.rules.engine import remembered  # engine imports this module

        key = may_key(entry)
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


def may_key(entry: StackEntry) -> str:
    """The remembered-answer key of a "you may" (603.5): this card's own ability — its source card
    and what the ability does — so two cards with the same name (or two abilities of one card
    that start alike) never share an answer."""
    import hashlib
    import json

    what = hashlib.sha1(json.dumps(entry.effects, sort_keys=True, default=str).encode()).hexdigest()[:12]
    return f"may:{(entry.source_card or entry.name)[:90]}:{what}"  # (a Yield key is at most 120 characters)


def resume_may(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx = d.resume["ctx"]
    if chosen[0] == "yes":
        continue_effects(plan, ctx)
    else:
        plan.note(f"{plan.name(d.player)} chose not to")
        prev = ctx["effects"][ctx["next"] - 1] if ctx["next"] else {}  # (-- review (wave 24D) -- a whole-ability "may" asked at next 0)
        if prev.get("do") == "may_rest" and prev.get("skip"):
            ctx["next"] += prev["skip"]  # -- optional first sentence (wave 24D) -- only X is skipped, "Then Y" still happens
            continue_effects(plan, ctx)
        else:
            finish(plan, ctx)


def continue_effects(plan: Plan, ctx: Context) -> None:
    with reading_x(plan, ctx.get("x")):
        _continue_effects(plan, ctx)


def _continue_effects(plan: Plan, ctx: Context) -> None:
    while ctx["next"] < len(ctx["effects"]):  # (wave 19F: re-read each time: effects.repeat replaces the list)
        e = ctx["effects"][ctx["next"]]
        if replacements.ask_903_9b_first(plan, ctx, e):
            return  # 903.9b: a commander's owner chooses before it would be put into a hand or library
        ctx["next"] += 1
        if e.get("note_group"):  # -- counters (wave 5H) -- the permanents a count reads, for a later "those creatures"
            context.bind_objects(plan, ctx, e["note_group"]["as"], _cards(plan, ctx, e["note_group"]["who"]))
        if not PRIMITIVES[e["do"]](plan, ctx, e):
            return  # waiting for a choice; the decision's resume continues from ctx["next"]
    if ctx.get("body_done") is not None:  # -- draw bodies (wave 28B) -- a replacement effect's own resolution: no stack object (draw_bodies.py)
        replace.run_then(plan, ctx["body_done"])
        return
    finish(plan, ctx)


def repeat(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """-- X sized by a count (wave 19F) -- the next ``span`` instructions, as many times as ``n`` says ("Proliferate X times": each time
    is a whole proliferate, 701.34a; none when it is 0), one after the other."""
    effects, i = ctx["effects"], ctx["next"]
    ctx["effects"] = [*effects[:i], *effects[i: i + e["span"]] * _amount(plan, ctx, e["n"]), *effects[i + e["span"]:]]
    return True


PRIMITIVES["repeat"] = repeat


def finish(plan: Plan, ctx: Context, *, countered: bool = False) -> None:
    from app.rules.engine import _after_resolution  # engine imports this module

    stack_id = ctx["stack_id"]
    stack = plan.state.zones.get("stack", [])
    if countered:  # -- spell copies (wave 31D) -- a spell with no legal target leaves the stack: a copy of it can still be made (608.2h)
        remember_stack(plan.state, stack_id)
    entry = plan.rules.stack.pop(stack_id, None)
    plan.rules.answers_903_9b = {}  # (answers for moves that didn't happen after all)
    if stack_id in stack:
        from app.rules.engine import leave_stack  # engine imports this module

        leave_stack(plan, stack_id, ctx["controller"], countered=countered)
    if not countered and entry is not None and entry.event is not None and entry.event.kind == "chapter" and entry.copy_of is None:
        from app.rules import (
            sagas,  # -- saga events (wave 45C) -- 714.2d: a final chapter ability finished resolving (and left the stack)
        )

        sagas.chapter_event(plan, entry.event, "resolves")
    _after_resolution(plan)


from app.rules import keyword_actions  # noqa: E402, I001  (keyword actions, CR 701, and token wording: leaf modules over this one)

PRIMITIVES.update(keyword_actions.PRIMITIVES)


def describe(effects: list[dict[str, Any]]) -> str:
    words = {"draw": "draw {n} card(s)", "gain_life": "gain {n} life", "lose_life": "lose {n} life", "scry": "scry {n}",
             "surveil": "surveil {n}", "damage": "deal {n} damage", "player_counter": "get {n} {counter}",
             "create_token": "create {n} token(s)", "add_counters": "put {n} {kind} counter(s)", "proliferate": "proliferate",
             "monarch": "become the monarch", "discard": "discard {n}", "search": "search your library",
             "demonstrate_copy": "copy it, and an opponent copies it too (demonstrate)"}
    # (an amount that is worked out as it resolves — "equal to its mana value", X — reads as X, not as its data)
    parts = [("discard any number" if e["do"] == "discard" else "sacrifice any number") if e["do"] in ("discard", "sacrifice_choice") and e.get("upto")
             else words.get(e["do"], e["do"]).format(**{k: "X" if isinstance(v, (dict, list)) else v for k, v in e.items()}) for e in effects
             if e["do"] not in ("kicked_gate", "record_action", "action_gate", "only_if", "note_resolution", "reflexive", "demonstrate_opponent")]  # (wave 30G: "any number")
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


def _controlled(plan: Plan, key: str, pid: str, source: str | None, you: str | None = None) -> list[str]:
    """The permanents ``pid`` controls that match a selector, evaluated for that player (``you``: -- trigger other (wave 39A) -- or for the ability's
    controller, whose "you" a qualifier like "that dealt combat damage to you this turn" is)."""
    sel = selectors.from_key(key)
    return [c for c in selectors.candidates(plan, sel, you or pid, source)
            if plan.state.cards[c].controller == pid and plan.state.cards[c].zone.endswith(":battlefield")]


def _choose_next(plan: Plan, ctx: Context, e: dict[str, Any], players: list[Any], picked: list[str], step: str) -> bool:
    """Each player in ``players`` (APNAP order) chooses ``n`` of the matching permanents they
    control. A player with at most that many has no choice to make (they're all chosen); one
    with none is skipped. Choices already made are announced, so the next chooser knows them
    (101.4b). False while waiting for a choice."""
    from app.rules import conditions

    half = e["n"].get("half_own") if isinstance(e["n"], dict) else None  # -- trigger other (wave 39A) -- "sacrifices half the creatures they control, rounded down": each player's own count
    want = 0 if half else _amount(plan, ctx, e["n"])
    exiling = e.get("action") == "exile"  # -- modal spells (wave 24D) -- "Target opponent exiles a creature they control."
    verb = ("exiles" if exiling else "sacrifices") if step == "edict" else "chooses"
    for i, turn in enumerate(players):
        # -- per-player choices (wave 30K) -- a turn is a player and the kind of permanent chosen (an old save: just the player); "you choose …
        # for each player" (Tragic Arrogance): the ability's controller decides what each player's permanents are
        pid, key = (turn, e["sel"]) if isinstance(turn, str) else turn
        mine = _controlled(plan, key, pid, ctx.get("source_card"), ctx["controller"] if "dealt_combat_damage_you" in key else None)
        if e.get("any"):  # -- per-player choices (wave 31B) -- any permanent the ability's words allow ("a creature you don't control"), whoever controls it
            mine = [c for c in selectors.candidates(plan, selectors.from_key(key), ctx["controller"], ctx.get("source_card"))
                    if plan.state.cards[c].zone.endswith(":battlefield")]
        if step == "edict" and not exiling and mine and _sacrifice_barred(plan, ctx, pid):
            mine = []  # -- prohibitions (wave 22B) -- nothing for them to sacrifice
        cap = e.get("power_cap")  # "any number of creatures they control with total power 4 or less" (Slaughter the Strong): always a choice
        n = len(mine) if cap is not None else (len(mine) + (half == "up")) // 2 if half else min(want, len(mine))  # (107.1a: half rounded as written)
        if n == 0:
            continue
        by = ctx["controller"] if e.get("by") == "you" or (e.get("by_if") and conditions.holds(plan, ctx, e["by_if"])) else pid
        label = dict(zip(e.get("sels") or [], e.get("labels") or [], strict=False)).get(key, e.get("label", "permanent"))
        if n == len(mine) and cap is None and not (e.get("upto") and (e.get("any") or e.get("optional"))):  # (an "up to one" / "may choose" always asks; wave 32A: "optional")
            picked = [*picked, *mine]
            plan.note(f"{plan.name(by)} {verb} {_labels(plan, mine)} (no choice: all of them)", mine, actor=by)
            continue
        prompt = f"{ctx.get('name', '') or 'Choose'}: {verb[:-1] if step == 'edict' else 'choose'} {n} ({label})"
        if cap is not None:
            prompt = f"{ctx.get('name', '') or 'Choose'}: choose any number of {label} with total power {cap} or less"
        if by != pid:
            prompt += f" for {plan.name(pid)}"
        if picked:
            prompt += f" — already chosen: {_labels(plan, picked)}"  # 101.4b: the earlier choices are known
        decide(plan, player=by, kind="choose_cards", prompt=prompt,
               options=[DecisionOption(id=c, label=(plan.state.cards[c].name or "Permanent") + (f" ({_power_of(plan, c)})" if cap is not None else "")
                        + (f" — {plan.name(plan.state.cards[c].controller)}" if e.get("any") else ""), card_id=c) for c in mine],
               min_choices=0 if e.get("upto") or cap is not None else n, max_choices=n,  # (wave 11D: "chooses up to two creatures they control")
               resume={"step": step, "ctx": ctx, "e": e, "rest": players[i + 1:], "picked": picked})
        return False
    if step == "edict" and exiling:  # (-- modal spells (wave 24D) --) all exiled at once
        exile_cards(plan, ctx, e, [c for c in picked if plan.state.cards[c].zone.endswith(":battlefield")])
    elif step == "edict":  # 101.4: after every choice, all sacrificed at once (one move, one event batch)
        _sacrifice_cards(plan, picked, ctx["controller"], ctx, e.get("as"))
    elif e.get("rest"):  # -- choose the rest (wave 11D) -- "Each player chooses a creature they control, then sacrifices the rest."
        # Everything those players control that fits and wasn't chosen, all at once after every choice was made (101.4).
        rest = [c for pid in _players(plan, ctx, e["who"]) for c in _controlled(plan, e["sel"], pid, ctx.get("source_card"))
                if c not in picked]
        if e["rest"] == "sacrifice":
            _sacrifice_cards(plan, rest, ctx["controller"], ctx, e.get("as"))
        else:  # "Destroy the rest" (701.8): indestructible ones stay, regeneration may save the others
            _destroy_cards(plan, ctx, e, rest)
    else:
        _remember(plan, ctx, e, list(dict.fromkeys(picked)))  # "that creature", "it": the chosen objects (they stay where they are; one chosen twice is one object)
        if e.get("did"):  # -- choose own (wave 32A) -- "You may choose a token you control. If you do, …": something was chosen (608.2c)
            context.bind_payment(ctx, e["did"], bool(picked))
    return True


def _power_of(plan: Plan, card_id: str) -> int:
    from app.rules import sba  # (a leaf over this module)

    c = plan.state.cards[card_id]
    return sba.power(c, plan.ch(c)) or 0


def check_total_power(plan: Plan, d: Any, chosen: list[str]) -> None:
    """-- per-player choices (wave 30K) -- "any number of creatures they control with total power 4 or less" (Slaughter the Strong): the
    answer is checked as it is given (608.2d: an illegal choice can't be made); a power below 0 subtracts (107.1b, its rulings)."""
    from app.game.errors import ActionError

    e = (d.resume or {}).get("e")
    cap = e.get("power_cap") if isinstance(e, dict) else None
    if cap is not None and sum(_power_of(plan, c) for c in chosen) > cap:
        raise ActionError(f"Those creatures have more than {cap} total power")


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
    turns: list[Any] = [p for p in plan.apnap() if p in who]
    if e.get("start"):  # -- per-player choices (wave 31B) -- 101.4: "starting with you" / "with the next opponent in turn order", then turn order
        first = ctx["controller"] if e["start"] == "you" else plan.after(ctx["controller"])
        at = turns.index(first) if first in turns else 0
        turns = turns[at:] + turns[:at]
    if e.get("sels"):  # -- per-player choices (wave 30K) -- 101.4: one player makes all their choices (one per kind), then the next
        turns = [(p, k) for p in turns for k in e["sels"]]
    return _choose_next(plan, ctx, e, turns, [], "player_chooses")


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
    me = ctx["controller"]
    for pid in _players(plan, ctx, e["who"]):
        hand = list(plan.state.zones.get(zone_key(pid, "hand"), []))
        if e.get("private"):  # -- hand disruption (wave 11D) -- "Look at target player's hand": shown to the looker alone (701.20e)
            ctx["look"] = True
            hand = [c for c in hand if ALL not in plan.state.cards[c].revealed_to and me not in plan.state.cards[c].revealed_to]
            if hand:
                plan.do({"type": "reveal", "card_ids": hand, "to": [me]}, actor=me)
        elif hand:
            plan.do({"type": "reveal", "card_ids": hand}, actor=pid)
        else:
            plan.note(f"{plan.name(pid)} reveals an empty hand", actor=pid)
        revealed += hand
    ctx["revealed"] = revealed
    if not ctx.get("hide_queued"):  # (appended in place: the resolver walks the same list)
        ctx["hide_queued"] = True
        ctx["effects"].append({"do": "hide_revealed"})
    pick = next((x for x in ctx["effects"][ctx["next"]:] if x["do"] == "choose_from_hand"), None)
    if e.get("private") and revealed and (pick is None or not _hand_options(plan, ctx, pick)[1]):
        # a look with nothing (left) to choose from it: the looker sees the hand until they say they're done, then it is hidden again
        decide(plan, player=me, kind="confirm", prompt=f"{ctx.get('name') or 'Look'}: you look at the hand",
               options=[DecisionOption(id="ok", label="Done looking")], resume={"step": "look_hand", "ctx": ctx})
        return False
    return True


def resume_look_hand(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx = d.resume["ctx"]
    hide_revealed(plan, ctx, {})
    continue_effects(plan, ctx)


def hide_revealed(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """End the reveal of the cards still in a hand that the effect revealed (701.20a: no longer
    needed). A card that changed zones is a new object and was never revealed there (400.7)."""
    left = [c for c in ctx.get("revealed") or [] if c in plan.state.cards and plan.state.cards[c].zone.endswith(":hand")
            and plan.state.cards[c].revealed_to]
    if left:
        plan.do({"type": "hide", "card_ids": left}, actor=ctx["controller"])
    ctx["revealed"] = []
    return True


def _hand_options(plan: Plan, ctx: Context, e: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(the revealed cards still in a hand, those of them — and, for "or a card from their graveyard", of that player's
    graveyard — that the choice may name)."""
    from app.rules import characteristics as chars

    pid = ctx["controller"]
    sel = selectors.from_key(e["sel"])
    pool = [c for c in ctx.get("revealed") or [] if c in plan.state.cards and plan.state.cards[c].zone.endswith(":hand")]
    options = [c for c in pool if selectors.matches(plan, sel, plan.state.cards[c], chars.of(plan.state.cards[c], plan.info), pid)]
    if e.get("gy_sel"):  # -- hand disruption (wave 11D) -- and the graveyard of the player whose hand it is (public: 404.2)
        gsel = selectors.from_key(e["gy_sel"])
        owners = sorted({plan.state.cards[c].owner for c in pool})
        options += [c for o in owners for c in plan.state.zones.get(zone_key(o, "graveyard"), [])
                    if selectors.matches(plan, gsel, plan.state.cards[c], chars.of(plan.state.cards[c], plan.info), pid)]
    return pool, options


def choose_from_hand(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"You choose a [nonland] card from it" after a hand was revealed: the controller chooses
    among the revealed cards matching the selector, then the unchosen ones stop being revealed.
    "You may choose" / "up to N" may choose fewer (or none)."""
    pid = ctx["controller"]
    pool, options = _hand_options(plan, ctx, e)
    most = min(_amount(plan, ctx, e["n"]), len(options))
    least = 0 if e.get("optional") else most
    if most == 0:
        if not ctx.get("look"):  # (after a private look, that nothing fit would tell the table what the hand holds: review of 11D)
            plan.note(f"Nothing to choose ({e.get('label', 'card')})", actor=pid)
        _remember(plan, ctx, e, [])
        if e.get("did"):  # -- if you do (wave 15C) -- "You may choose a card from it. If you do, …": nothing was chosen
            context.bind_payment(ctx, e["did"], False)
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
    chosen = [c for c in chosen if c in plan.state.cards and plan.state.cards[c].zone.endswith((":hand", ":graveyard"))]
    if chosen:
        plan.note(f"{plan.name(d.player)} chooses {_labels(plan, chosen)}", chosen, actor=d.player)
    _remember(plan, ctx, e, chosen)  # "that card" / "those cards": the chosen cards, in that hand
    if e.get("did"):  # -- if you do (wave 15C) -- "You may choose a card from it. If you do, …": a card was chosen (608.2c)
        context.bind_payment(ctx, e["did"], bool(chosen))
    _after_hand_choice(plan, ctx, chosen)
    continue_effects(plan, ctx)


def discard_named(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"That player discards that card / those cards": 701.9a — the named cards, each from its
    owner's hand to that player's graveyard, all at once (only while each is still that object
    in that hand, 400.7)."""
    if e.get("sel"):  # -- hand disruption (wave 11D) -- "reveals their hand and discards all nonland cards": the revealed ones that fit
        from app.rules import characteristics as chars

        sel = selectors.from_key(e["sel"])
        named = [c for c in ctx.get("revealed") or [] if c in plan.state.cards and selectors.matches(
            plan, sel, plan.state.cards[c], chars.of(plan.state.cards[c], plan.info), ctx["controller"])]
    else:
        named = _cards(plan, ctx, e["who"])
    from app.rules import (
        prohibitions,  # -- prohibitions (wave 22B) -- 614.17: "… can't cause you to discard cards"
    )

    cards = [c for c in named if plan.state.cards[c].zone.endswith(":hand")
             and prohibitions.cant_cause_discard(plan, plan.state.cards[c].owner, ctx["controller"]) is None]
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
CHOICE_LABELS.update(entry_forms.CHOICE_LABELS)  # -- entry forms (wave 5F) -- "a color other than blue"
CHOICE_LABELS.update({w: card_names.LABEL for w in card_names.ALL_WHATS})  # -- card names (wave 22B) -- 201.4


def _choice_options(plan: Plan, ctx: Context, what: str) -> list[DecisionOption]:
    from app.rules.creature_types import CREATURE_TYPES

    if card_names.is_choice(what):  # -- card names (wave 22B) -- typed, not listed (201.4)
        return [card_names.option(what)]
    if what.endswith(copying.TO_COPY):  # -- copy system (wave 2F): "enter as a copy of …" (707.5, 614.12a) --
        return copying.entry_options(plan, ctx["controller"], what, ctx.get("source_card"))  # (wave 5F: the entering card)
    if what == "creature type":
        return [DecisionOption(id=t, label=t) for t in sorted(CREATURE_TYPES)]
    from app.rules import chosen as _picked

    if (named := _picked.words(what)) is not None:  # -- linked words (wave 33B) -- 607.2f: "choose Khans or Dragons"
        return [DecisionOption(id=w, label=w) for w in named]
    if (others := entry_forms.color_options(what)) is not None:  # -- entry forms (wave 5F) --
        return [DecisionOption(id=v, label=v) for v in others]
    if what in ("opponent", "player"):
        pids = [p for p in plan.live() if what == "player" or p != ctx["controller"]]
        return [DecisionOption(id=p, label=plan.name(p)) for p in pids]
    # -- counters (wave 7C) -- "enters with your choice of a flying or a hexproof counter"
    from app.rules import counter_choice

    if (kinds := counter_choice.options(what)) is not None:
        return [DecisionOption(id=k, label=k) for k in kinds]
    # -- sagas & attached-object triggers (wave 3S): read ahead's number (702.155b) --
    from app.rules import sagas

    chapters = sagas.choice_options(what)
    if chapters is not None:
        return [DecisionOption(id=v, label=label) for v, label in chapters]
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
    if not e.get("remember") and (e["what"] in ("creature type", "color") or card_names.is_choice(e["what"])):  # -- chosen type (wave 4J) --
        from app.rules import chosen as picked

        what = "card name" if card_names.is_choice(e["what"]) else e["what"]  # (wave 22B)
        ctx["effects"] = ctx["effects"][: ctx["next"]] + picked.bind_effects(ctx["effects"][ctx["next"]:], what, value)
    src = plan.state.cards.get(ctx.get("source_card") or "")
    if e.get("remember") and src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == ctx.get("source_object"):
        plan.do({"type": "set_choice", "card_id": src.id, "key": card_names.LABEL if card_names.is_choice(e["what"]) else CHOICE_LABELS[e["what"]], "value": shown}, actor=d.player)
        if e["what"] in ("opponent", "player"):  # -- chosen player (wave 4J) --
            from app.rules import chosen as picked

            picked.record(plan, src.id, value)
    continue_effects(plan, ctx)


PRIMITIVES.update({"edict": edict, "player_chooses": player_chooses, "reveal_hand": reveal_hand, "hide_revealed": hide_revealed,
                   "choose_from_hand": choose_from_hand, "discard_named": discard_named, "choose_value": choose_value})
PRIMITIVES["edict"] = _did_r1(PRIMITIVES["edict"], "leave")  # -- trigger other (wave 41C) -- "That player sacrifices a creature of their choice. If the player can't, …"
RESUME = {"edict": resume_edict, "player_chooses": resume_player_chooses, "choose_from_hand": resume_choose_from_hand,
          "choose_value": resume_choose_value, "look_hand": resume_look_hand}
# -- if you do (wave 8C) -- "put your choice of a +1/+1, first strike, or trample counter on it" (app/rules/counter_pick.py)
from app.rules import counter_pick as _counter_pick  # noqa: E402, I001

PRIMITIVES["pick_counter"] = _counter_pick.pick_counter
RESUME["pick_counter"] = _counter_pick.resume
RESUME.update(_voting.RESUME)  # -- voting (wave 18C) --
RESUME.update(_tempting.RESUME)
RESUME.update(_friend_foe.RESUME)
# -- name search (wave 11D) -- "Search its controller's graveyard, hand, and library for all cards with the same name …"
from app.rules import name_search as _name_search  # noqa: E402, I001

PRIMITIVES["name_search"] = _name_search.search
RESUME["name_search"] = _name_search.resume
# -- drawn this turn (wave 18G) -- Sylvan Library (app/rules/drawn_toll.py)
from app.rules import drawn_toll as _drawn_toll  # noqa: E402, I001

PRIMITIVES["drawn_toll"] = _drawn_toll.toll
RESUME["drawn_toll"] = _drawn_toll.resume_pick
RESUME["drawn_toll_each"] = _drawn_toll.resume_each
# -- Doctor Who keywords (wave 25A) -- time travel (app/rules/time_travel.py)
from app.rules import time_travel as _time_travel  # noqa: E402, I001

PRIMITIVES.update(_time_travel.PRIMITIVES)
RESUME.update(_time_travel.RESUME)
# -- end if you do (wave 8C) --


# -- temporary grants & riders (agent G) ------------------------------------------------------------
# ``pump`` reads value expressions ("+X/+0", "+1/+1 for each …", "-X/-X where X is …": 611.2d, once);
# ``damage`` takes its source from a named creature ("src": a bite); ``fight`` (701.14);
# ``choose_targets`` (a sentence that only names targets); ``grant`` also removes keywords
# ("loses flying until end of turn"). "Do this only once each turn." (603.2h: the ability triggers
# only if its controller hasn't taken the indicated action that turn) is enforced by triggers._add
# reading the uses it records here: ``record_action`` is appended to such an ability's effects,
# so the action counts as taken only when the resolution got that far — not when the ability was
# countered, its "you may" declined, or an optional payment it hinges on wasn't made.
def record_action(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import restrictions

    refs = ctx.get("refs") or {}
    if any(b.get("kind") == "payment" and not b.get("ok") for b in refs.values()):
        return True  # ("you may pay … If you do, …": declined — the action wasn't taken)
    if any(x.get("do") == "free_cast" for x in ctx.get("effects") or []) and not ctx.get("free_cast_done"):
        return True  # -- if you do (wave 25C) -- "you may cast …. Do this only once each turn.": no spell was cast, so the action wasn't taken
    restrictions.record_use(plan.rules, e["object"], int(e["index"]), plan.state.turn.number)
    return True


def action_gate(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The first effect of a "Do this only once each turn." ability: if another instance (one that
    triggered at the same time) already took the action as it resolved, this one does nothing —
    the action is taken only once each turn (603.2h)."""
    from app.rules import restrictions

    if restrictions.uses(plan.rules, e["object"], int(e["index"]), plan.state.turn.number):
        plan.note(f"{ctx.get('name') or 'It'}: already done this turn (only once each turn)", actor=ctx["controller"])
        ctx["next"] = len(ctx["effects"])
    return True


PRIMITIVES.update({"record_action": record_action, "action_gate": action_gate})


# -- animation (agent A2): "becomes a N/N [color] [creature type] [artifact] creature …" ----------
# One instruction, several layers (613.6): the types (4), colors (5), keywords / quoted abilities
# / "loses all abilities" (6) and base power and toughness (7b) it names each become their own
# continuous effect on the same objects, locked in now (611.2c), with the stated duration ("until
# end of turn" ends at cleanup, 514.2; none: the game, 611.2a). Types replace the object's (205.1a)
# unless it says "in addition to its other types", "that's still a land", or "artifact creature"
# (205.1b) — or a following sentence "It's still a land." (``still_a``) says so; creature types
# replace the object's creature types (205.1a: the land types of a land stay); a color named
# replaces its colors (105.3), none named leaves them; "all creature types" is every creature
# type. A permanent that became a creature this way attacks and taps under 302.6 like any other
# (summoning sickness reads how long it has been controlled, not how long it has been a creature).
# X and "its mana value" are read once, as the effect begins (611.2d, 608.2h).
def _animate_value(plan: Plan, ctx: Context, n: Any, cid: str) -> int | None:
    """A P/T value: a number, X, "its mana value" (the object's own, bound per object) …"""
    if n is None:
        return None
    if isinstance(n, int):
        return n
    context.bind_objects(plan, ctx, "_animated", [cid])
    return values.evaluate(plan, ctx, _its(n))


def _its(v: Any) -> Any:
    """"its power" / "its mana value" placeholders → the object being animated."""
    if isinstance(v, list):
        return [_its(x) for x in v]
    if isinstance(v, dict):
        return {k: ("ref:_animated" if k in ("power", "toughness", "mana_value") and x == "it" else _its(x))
                for k, x in v.items()}
    return v


def _reads_it(v: Any) -> bool:
    if isinstance(v, list):
        return any(_reads_it(x) for x in v)
    return isinstance(v, dict) and any((k in ("power", "toughness", "mana_value") and x == "it") or _reads_it(x)
                                       for k, x in v.items())


def become(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """See above. ``e``: who; types (card types named, [] for "becomes a blue Frog"); retain
    (types added, 205.1b); creature_types (None: unchanged); all_creature_types; legendary;
    colors (None: unchanged; []: colorless); add_colors; keywords; abilities (quoted texts);
    lose_abilities; p / t (None: unchanged); duration."""
    cards = _cards(plan, ctx, e["who"])
    _remember(plan, ctx, e, cards)
    if not cards:
        return True
    if e.get("land_pick"):  # -- land types set (wave 12D) -- "the basic land type of your choice": made as it resolves, by the controller
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose a basic land type",
               options=[DecisionOption(id=t, label=t) for t in e["land_pick"]],
               resume={"step": "become_land", "ctx": ctx, "e": e})
        return False
    if e.get("pick") == "color or colors":  # -- activated other (wave 21E) -- "becomes the color or colors of your choice": one or more
        decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: choose one or more colors",
               options=[DecisionOption(id=t, label=t) for t in CHOICE_OPTIONS["color"]], min_choices=1,
               max_choices=len(CHOICE_OPTIONS["color"]), resume={"step": "become_pick", "ctx": ctx, "e": e})
        return False
    if e.get("pick"):  # -- activated wordings (wave 15D) -- "becomes the creature type / color of your choice": chosen as it resolves
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose a {e['pick']}",
               options=[o for o in _choice_options(plan, ctx, e["pick"]) if o.id != e.get("not")],
               resume={"step": "become_pick", "ctx": ctx, "e": e})
        return False
    per_object = _reads_it(e.get("p")) or _reads_it(e.get("t"))
    groups = [[c] for c in cards] if per_object else [cards]
    duration = e.get("duration", "end_of_turn")
    name = ctx.get("name", "")
    if duration.startswith("source_") and not delayed._source_ok(plan, duration, ctx.get("source_card"), ctx.get("source_object"),
                                                               ctx["controller"]):
        plan.note(f"{name or 'The effect'} does nothing: its duration has already ended")  # -- stack interaction (wave 23B) -- 611.2b
        return True
    for group in groups:
        affected = [plan.oid(c) for c in group]  # locked in now (611.2c)
        p = _animate_value(plan, ctx, e.get("p"), group[0])
        t = _animate_value(plan, ctx, e.get("t"), group[0])
        label = _become_label(e, p, t)
        common: dict[str, Any] = {"affected": affected, "source": ctx.get("source_object"), "controller": ctx["controller"],
                                  "duration": duration, "label": f"{label} ({name})" if name else label}
        made: list[str] = []
        types = list(e.get("types") or [])
        lands = list(e.get("land_types") or ())  # -- land types set (wave 12D) -- 305.7: set, or added ("in addition", 205.1b)
        if types or e.get("creature_types") is not None or e.get("add_creature_types") or e.get("all_creature_types") \
                or e.get("legendary") or lands:
            made.append(layers.add_effect(plan, layer="4", **common,
                                          add_types=tuple(types) if e.get("retain") else (),
                                          set_types=None if e.get("retain") or not types else types,
                                          set_creature_types=e.get("creature_types"),
                                          set_land_types=lands if lands and not e.get("retain") else None,
                                          add_subtypes=(*(e.get("add_creature_types") or ()), *(lands if e.get("retain") else ())),
                                          all_creature_types=bool(e.get("all_creature_types")),
                                          add_supertypes=["Legendary"] if e.get("legendary") else []).id)
        if e.get("colors") is not None or e.get("add_colors"):
            made.append(layers.add_effect(plan, layer="5", **common, set_colors=e.get("colors"),
                                          add_colors=list(e.get("add_colors") or [])).id)
        if e.get("keywords") or e.get("abilities") or e.get("lose_abilities"):
            made.append(layers.add_effect(plan, layer="6", **common, add_keywords=tuple(e.get("keywords") or ()),
                                          add_abilities=list(e.get("abilities") or []),
                                          remove_abilities=bool(e.get("lose_abilities"))).id)
        if p is not None or t is not None:
            made.append(layers.add_effect(plan, layer="7b", **common, power=p, toughness=t).id)
        if duration == "next_turn":  # "until your next turn": whose, and from which turn (app/rules/delayed.py)
            for effect in plan.rules.effects:
                if effect.id in made:
                    effect.until_player, effect.turn = ctx["controller"], plan.state.turn.number
        elif duration.startswith("source_"):  # -- stack interaction (wave 23B) -- 611.2b: "for as long as ~ remains on the battlefield"
            for effect in plan.rules.effects:
                if effect.id in made:
                    effect.source_card, effect.until_player = ctx.get("source_card"), ctx["controller"]
        ctx["animated"] = [*ctx.get("animated", []), *made]  # (for a following "It's still a land.")
        markers: list[str] = []
        for cid in group:  # the table marker (cleared at cleanup for "until end of turn", 514.2; by a zone change, 400.7)
            markers += delayed.marker_ids(plan.do({"type": "add_effect", "card_ids": [cid], "name": label[:60],
                                                   "value": f"{p}/{t}" if p is not None and t is not None else None,
                                                   "text": _MARKER_TEXT.get(duration) or (delayed.LABELS[duration].replace("~", name or "its source")  # (review 23B: whose)
                                                           if duration.startswith("source_") else "as long as it's on the battlefield")}))
        for effect in plan.rules.effects:  # ending the effects removes these markers (app/rules/delayed.py)
            if effect.id in made:
                effect.markers = [*(effect.markers or []), *markers]
        for cid in group:
            plan.note(f"{plan.state.cards[cid].name or 'It'} becomes {label}"
                      + (f" {_MARKER_TEXT[duration]}" if duration in _MARKER_TEXT else ""), [cid], actor=ctx["controller"])
    return True


_MARKER_TEXT = {"end_of_turn": "until end of turn", "next_turn": delayed.LABELS["next_turn"]}
_COLOR_WORDS = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}


def _become_label(e: dict[str, Any], p: int | None, t: int | None) -> str:
    words: list[str] = []
    if e.get("lose_abilities"):
        words.append("(loses all abilities)")
    if e.get("legendary"):
        words.append("legendary")
    if p is not None and t is not None:
        words.append(f"{p}/{t}")
    if e.get("colors"):
        words.append(" and ".join(_COLOR_WORDS.get(c, c) for c in e["colors"]))
    elif e.get("colors") == []:
        words.append("colorless")
    words += list(e.get("creature_types") or e.get("add_creature_types") or e.get("land_types") or [])
    words += [w.lower() for w in e.get("types") or []]
    extras = list(e.get("keywords") or [])
    if e.get("all_creature_types"):
        extras.append("all creature types")
    if e.get("abilities"):
        extras += [f'"{a}"' for a in e["abilities"]]
    if extras:
        words.append("with " + ", ".join(extras))
    return " ".join(words) or "a creature"


def resume_become_land(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    if chosen[0] not in e["land_pick"]:
        raise ValueError("not an offered basic land type")
    if become(plan, ctx, {**e, "land_pick": None, "land_types": [chosen[0]]}):
        continue_effects(plan, ctx)


RESUME["become_land"] = resume_become_land


_COLOR_LETTER = {"White": "W", "Blue": "U", "Black": "B", "Red": "R", "Green": "G"}


def resume_become_pick(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    if e["pick"] == "color or colors":  # -- activated other (wave 21E) -- every color chosen, once each (105.2)
        if not chosen or len(set(chosen)) != len(chosen) or not set(chosen) <= set(CHOICE_OPTIONS["color"]):
            raise ValueError("not an offered choice")
        plan.note(f"{plan.name(d.player)} chooses {', '.join(chosen)} (colors)", actor=d.player)
        if become(plan, ctx, {**e, "pick": None, "colors": [_COLOR_LETTER[c] for c in chosen]}):
            continue_effects(plan, ctx)
        return
    if chosen[0] not in {o.id for o in _choice_options(plan, ctx, e["pick"])} - {e.get("not")}:
        raise ValueError("not an offered choice")
    plan.note(f"{plan.name(d.player)} chooses {chosen[0]} ({e['pick']})", actor=d.player)
    more = {"creature_types": [chosen[0]]} if e["pick"] == "creature type" else {"colors": [_COLOR_LETTER[chosen[0]]]}
    if become(plan, ctx, {**e, "pick": None, **more}):
        continue_effects(plan, ctx)


RESUME["become_pick"] = resume_become_pick


def still_a(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"It's still a land." (205.1b): the sentence before retains all the object's prior card
    types, supertypes and subtypes — the types it set are added instead, and so are the creature
    types it named (a land creature keeps its creature types too)."""
    ids = set(ctx.get("animated") or [])
    for effect in plan.rules.effects:
        if effect.id not in ids or effect.layer != "4":
            continue
        if effect.set_types is not None:
            effect.add_types = list(dict.fromkeys([*effect.add_types, *effect.set_types]))
            effect.set_types = None
        if effect.set_creature_types is not None:
            effect.add_subtypes = list(dict.fromkeys([*effect.add_subtypes, *effect.set_creature_types]))
            effect.set_creature_types = None
    return True


def prevent_self(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """(Kept for games saved while a Gideon ability was on the stack: the grammar now gives the
    plain ``prevent_all`` to "~", which locks to the source object itself.)"""
    return replacements.prevent_all(plan, ctx, {"scope": {"combat": None, "to_objects": "self"}})


PRIMITIVES.update({"become": become, "still_a": still_a, "prevent_self": prevent_self})


def _siege_defeated(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import battles  # (battles → plan; a leaf here)

    return battles.siege_defeated(plan, ctx, e)


PRIMITIVES["siege_defeated"] = _siege_defeated  # 310.12b (app/rules/battles.py)
PRIMITIVES["cost_modifier"] = permissions.cost_modifier  # "… spells you cast this turn cost {2} less to cast" (611.2a)


# -- replacement effects stage 2 (wave 2E) -----------------------------------------------------------
def exile_if_dies(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"If that creature would die this turn, exile it instead." / "If a creature dealt damage this
    way would die this turn, …" / "If a creature would die this turn, …": a replacement effect of
    this resolution lasting the turn (614.1a, 611.2a), applied by replacements.replace_move with the
    other "exile instead" effects. It is locked to the objects it names as they are now (400.7: a
    creature that leaves and comes back is a new object); "dealt damage this way" names only the
    objects that damage was actually dealt to (after prevention). A group ("a creature") is checked
    whenever something would die this turn (a rule-modifying effect isn't locked, 611.2c)."""
    import secrets

    rec: dict[str, Any] = {"id": secrets.token_hex(4), "kind": "exile_if_dies", "turn": plan.state.turn.number,
                           "controller": ctx["controller"], "source": ctx.get("source_object"), "label": ctx.get("name") or ""}
    if e.get("cards"):  # -- zone replacements (wave 37B) -- "If a card would be put into your graveyard from anywhere this turn, exile that card instead."
        plan.rules.replacements.append({**rec, "kind": "exile_cards", "whose": e["cards"]})
        return True
    if e.get("each"):
        rec["each"] = e["each"]
    else:
        if e.get("dealt"):
            oids = list((ctx.get(DEALT_KEY) or {}).get(e["dealt"]) or [])
        else:
            oids = [plan.oid(c) for c in _cards(plan, ctx, e.get("who") or "")]
        if not oids:
            return True  # (nothing to watch: gone, or dealt no damage)
        rec.update(oids=oids, types=list(e.get("types") or []))
    plan.rules.replacements.append(rec)
    return True


def replace_record(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Until end of turn, if one or more tokens would be created under your control, …" / "If a
    source you control would deal damage to an opponent this turn, …": the replacement effect of
    this resolution, for the rest of the turn (611.2a; its timestamp now, 613.7b), with "you" its
    controller — applied by app/rules/replace.py with the statics."""
    replace.add_record(plan, event=e["event"], match=e["match"], op=e["op"], controller=ctx["controller"],
                       source=ctx.get("source_object"), source_card=ctx.get("source_card"),
                       label=ctx.get("name") or "an effect")
    return True


PRIMITIVES.update({"exile_if_dies": exile_if_dies, "replace_record": replace_record})
# -- end replacement effects stage 2 (wave 2E) --


# -- mana (wave 3M): mana added by a spell, a triggered ability or a non-mana activated ability (CR 106.3, 605.1a/605.5) --
def add_mana(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """106.3: the mana an effect adds goes into its controller's pool (it empties as the step ends,
    106.4). Forms: ``mana`` (fixed symbols), ``sym`` + ``n`` (n of one type, n a value), ``of`` + ``n`` (n
    mana each chosen from ``of``; ``same`` = one choice for all of them: "any one color"), ``identity``
    (``of`` is the controller's commander color identity; none in it = nothing is added, 106.5).
    Choices are decisions of the controller (resume data kept). Nothing is tapped: the mana is
    simply added, carrying no restriction (a restricted wording isn't parsed, so never reaches here)."""
    from app.rules import mana as M

    pid = ctx["controller"]
    ctx.pop("_mana_added", None)  # (wave 3R3)
    if "who" in e:  # -- other players' choices (wave 12D) -- "That player adds {G}{G}": 106.3, into their pool; their colour choice
        # ("any color they choose"), the resumed decision being theirs
        who = _players(plan, ctx, e["who"])
        if not who:
            return True
        pid = who[0]
    if "mana" in e:
        return _put_mana(plan, ctx, pid, list(e["mana"]))
    if "sym" in e:
        return _put_mana(plan, ctx, pid, [e["sym"]] * _amount(plan, ctx, e["n"]))
    of = list(e["of"])
    if e.get("identity"):
        from app.rules.casting import commander_identity

        ident = commander_identity(plan.state, pid, plan.info)
        of = [c for c in M.COLORS if c in ident]
    n = _amount(plan, ctx, e["n"])
    if n <= 0 or not of:
        return True
    if len(of) == 1:
        return _put_mana(plan, ctx, pid, of * n)
    same = bool(e.get("same"))
    return _ask_mana(plan, ctx, pid, of, 1 if same else n, n if same else 1, [])


def _ask_mana(plan: Plan, ctx: Context, pid: str, of: list[str], asks: int, repeat: int, got: list[str]) -> bool:
    """Ask for the next of ``asks`` choices (each chosen mana is added ``repeat`` times)."""
    if len(got) >= asks:
        return _put_mana(plan, ctx, pid, got * repeat)
    decide(plan, player=pid, kind="choose_one",
           prompt=f"Choose the mana to add ({asks - len(got)} left)" if asks > 1 else "Choose the mana to add",
           options=[DecisionOption(id=c, label="{" + c + "}") for c in of],
           resume={"step": "add_mana", "ctx": ctx, "of": of, "asks": asks, "repeat": repeat, "got": got})
    return False


def resume_add_mana(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    if chosen[0] not in r["of"]:
        raise ValueError("not an offered mana type")
    if _ask_mana(plan, r["ctx"], d.player, r["of"], r["asks"], r["repeat"], [*r["got"], chosen[0]]):
        continue_effects(plan, r["ctx"])


def _put_mana(plan: Plan, ctx: Context, pid: str, mana: list[str]) -> bool:
    from app.rules import mana as M

    ctx["_mana_added"] = {c: mana.count(c) for c in dict.fromkeys(mana)}  # (wave 3R3: "this mana", app/rules/kept_mana.py)
    ctx["_mana_added_player"] = pid  # (-- trigger other (wave 44B) -- whose pool: "that player adds {G}{G}{G}. … they don't lose this mana", Shizuko)
    if mana:
        delta: dict[str, int] = {}
        for c in mana:
            delta[c] = delta.get(c, 0) + 1
        plan.do({"type": "rules_mana", "player": pid, "tap": [], "sacrifice": [], "delta": delta, "life": 0,
                 "label": f"added {M.symbols(delta)}"}, actor=pid)
    return True


PRIMITIVES["add_mana"] = add_mana
# -- end mana (wave 3M) --


# -- reanimation (wave 3R) ---------------------------------------------------------------------------
def return_choice(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Return a creature card from your graveyard to the battlefield" / "return up to two … cards" /
    "return a card at random …": nothing is targeted, so the controller chooses on resolution (608.2d)
    among the matching cards in the graveyard (public, 404.2), or the table picks at random
    (recorded as the move, so a replay is the same). Then the cards go as ``return_card`` does."""
    import secrets

    pid = ctx["controller"]
    found = (_cards(plan, ctx, e["who"]) if e.get("who") else  # (-- wave 22D -- "a creature card put into a graveyard this way")
             selectors.candidates(plan, selectors.from_key(e["sel"]), pid, ctx.get("source_card")))
    # -- reanimation (wave 37B) -- "the top creature card of your graveyard": the last matching card of the graveyard's order (index -1 is the top), nothing chosen
    pool = found[-1:] if e.get("top") else sorted(found)
    want = _amount(plan, ctx, e["n"])
    if e.get("random"):
        picked = (plan.rng or secrets.SystemRandom()).sample(pool, min(want, len(pool)))
        return _return_cards(plan, ctx, e, picked)
    most = min(want, len(pool))
    least = 0 if e.get("upto") else most
    if most == 0 and e.get("lose_if_none"):  # -- draw bodies (wave 28B) -- "If you can't, you lose the game." (104.3e; Forbidden Crypt)
        from app.rules import win_game

        return win_game.lose_game(plan, ctx, {"who": "you"})
    # -- reanimation (wave 37B) -- "from your hand or graveyard": the hand is hidden, so a hand that holds cards is asked whether or not one of them
    # matches (put_from_hand's rule, review 25C): the other players must not learn from the question that a matching card is there
    hidden = not e.get("who") and "hand" in selectors.from_key(e["sel"]).zones and bool(plan.state.zones.get(f"{pid}:hand"))
    if not hidden and (most == 0 or (least == most == len(pool))):
        return _return_cards(plan, ctx, e, pool[:most])
    decide(plan, player=pid, kind="choose_cards",
           prompt=f"Choose {'up to ' if e.get('upto') else ''}{max(most, 1) if hidden else most} ({e.get('label', 'card')})" + {"exile": " to exile", "choose": ""}.get(e["to"], " to return"),
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in pool],
           min_choices=least, max_choices=max(most, 1) if hidden else most, resume={"step": "return_choice", "ctx": ctx, "e": e})
    return False


def resume_return_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    pool = set(_cards(plan, ctx, e["who"]) if e.get("who") else
               selectors.candidates(plan, selectors.from_key(e["sel"]), ctx["controller"], ctx.get("source_card")))
    cards = [c for c in chosen if c in pool]  # (still there and still matching)
    if e.get("different"):  # -- refused zones/sized (wave 3R4) -- "… cards with different names / mana values"
        from app.rules.targets import _different

        if not _different(plan, cards, e["different"]):
            from app.game.errors import ActionError

            raise ActionError(f"Choose cards with different {'names' if e['different'] == 'name' else 'mana values'}")
    if _return_cards(plan, ctx, e, cards):
        continue_effects(plan, ctx)


PRIMITIVES["return_choice"] = return_choice
RESUME["return_choice"] = resume_return_choice


# -- control (wave 3K) -----------------------------------------------------------------------------------
# "Gain control of target creature [until end of turn | for as long as …]", "target opponent gains
# control of target permanent", "exchange control of two target creatures". A control-changing effect is a
# layer-2 continuous effect (613.1b) on the objects there as it begins (611.2c) with the duration it
# states (none: the game, 611.2a; "until end of turn" ends in cleanup, 514.2; "for as long as …" is the
# ``until`` wrapper's, app/rules/delayed.py). The table follows it (layers.control_sync): the same object
# changes sides (no zone change), a new controller restarts summoning sickness (302.6), and when it ends
# the permanent goes back to the owner (or to the player of the next-latest effect). Only permanents
# still on the battlefield as the same object are affected.
def _control_effect(plan: Plan, ctx: Context, cards: list[str], player: str, duration: str) -> None:
    if not cards:
        return
    name = ctx.get("name") or ""
    layers.add_effect(plan, affected=[plan.oid(c) for c in cards], layer="2", source=ctx.get("source_object"),
                      controller=ctx["controller"], duration=duration,  # type: ignore[arg-type]
                      label=f"Control: {plan.name(player)} ({name})" if name else f"Control: {plan.name(player)}",
                      new_controller=player)
    plan.note(f"{plan.name(player)} gains control of " + ", ".join(plan.state.cards[c].name or "a permanent" for c in cards)
              + (" until end of turn" if duration == "end_of_turn" else ""), cards, actor=ctx["controller"])


def gain_control(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """See above. ``e``: who (the permanents); to ("you", a target player "target:N", or -- wave 12D -- "choose_opponent":
    "An opponent gains control of it", not a target, so its controller chooses one as it resolves (608.2d); "owner":
    "Each player gains control of all creatures they own"); duration; untap."""
    cards = [c for c in _cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")
             and plan.in_game(plan.state.cards[c])]
    if e.get("to") == "choose_opponent":
        opponents = [p for p in plan.live() if p != ctx["controller"]]
        if len(opponents) > 1 and cards:
            decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose an opponent to gain control",
                   options=[DecisionOption(id=p, label=plan.name(p)) for p in opponents], resume={"step": "gain_control", "ctx": ctx, "e": e})
            return False
        e = {**e, "to": f"player:{opponents[0]}" if opponents else "you"}
        cards = cards if opponents else []
    if e.get("to") == "owner":  # 613.1b: a control effect of its own for each owner (it overrides the earlier ones, 613.7); a permanent
        # its owner already controls changes nothing unless an earlier control effect is on it
        r = plan.rules
        held = {o for x in r.effects if x.layer == "2" and x.new_controller for o in x.affected}
        for owner in dict.fromkeys(plan.state.cards[c].owner for c in cards):
            mine = [c for c in cards if plan.state.cards[c].owner == owner
                    and (plan.state.cards[c].controller != owner or plan.oid(c) in held)]
            if owner in plan.live():
                _control_effect(plan, ctx, mine, owner, "permanent")
        _remember(plan, ctx, e, cards)
        layers.control_sync(plan)
        return True
    _remember(plan, ctx, e, cards)
    if e.get("untap"):  # "Untap target creature and gain control of it": the same objects, untapped first
        tapped = [c for c in cards if plan.state.cards[c].tapped]
        tapped = keyword_actions.untap_stunned(plan, tapped, ctx["controller"])  # -- wave 3F -- 122.1d
        if tapped:
            plan.do({"type": "tap", "card_ids": tapped, "tapped": False}, actor=ctx["controller"])
    who = _players(plan, ctx, e.get("to", "you"))
    if cards and len(who) == 1:
        _control_effect(plan, ctx, cards, who[0], e.get("duration", "permanent"))
        layers.control_sync(plan)
    return True


def exchange_control(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.12: exchange control of two permanents. If the whole exchange can't be completed (one of them
    is no longer there, or no longer the object it was) nothing happens (701.12a); if one player controls
    both, nothing happens (701.12b); otherwise each player gains control of the other's permanent."""
    if "with" not in e:  # "exchange control of two target creatures": one group of two
        cards = _cards(plan, ctx, e["who"])
    else:
        a, b = _cards(plan, ctx, e["who"]), _cards(plan, ctx, e["with"])
        cards = [*a, *b] if len(a) == len(b) == 1 else []
    cards = [c for c in cards if plan.state.cards[c].zone.endswith(":battlefield")]
    if len(cards) != 2 or cards[0] == cards[1]:
        return True
    first, second = (plan.state.cards[c] for c in cards)
    if first.controller == second.controller or not (plan.in_game(first) and plan.in_game(second)):
        return True
    _remember(plan, ctx, e, cards)
    duration = e.get("duration", "permanent")
    _control_effect(plan, ctx, [first.id], second.controller, duration)
    _control_effect(plan, ctx, [second.id], first.controller, duration)
    layers.control_sync(plan)
    return True


def resume_gain_control(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    if chosen[0] not in plan.live() or chosen[0] == ctx["controller"]:
        raise ValueError("not an opponent")
    plan.note(f"{plan.name(d.player)} chooses {plan.name(chosen[0])}")
    if gain_control(plan, ctx, {**e, "to": f"player:{chosen[0]}"}):
        continue_effects(plan, ctx)


PRIMITIVES.update({"gain_control": gain_control, "exchange_control": exchange_control})
RESUME["gain_control"] = resume_gain_control
# -- end control (wave 3K) --


# -- keywords (wave 43C) -- "an opponent" in a cost that is an instruction ("Cumulative upkeep—An opponent gains 1 life.", Wall of Shards; "Have an
# opponent create a 1/1 red Survivor creature token.", Varchild's War-Riders): its payer chooses one as it is paid, each time (ruling 2006-07-15: a different
# opponent for each age counter); it isn't a target (115.1), and with a single opponent in the game there is nothing to choose. The instructions after
# it name the player as ``ref:<as>`` (context.players).
def choose_opponent(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    opponents = [p for p in plan.live() if p != ctx["controller"]]
    if len(opponents) > 1:
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose an opponent",
               options=[DecisionOption(id=p, label=plan.name(p)) for p in opponents], resume={"step": "choose_opponent", "ctx": ctx, "as": e["as"]})
        return False
    context.bind_players(ctx, e["as"], opponents)
    return True


def resume_choose_opponent(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx = d.resume["ctx"]
    if chosen[0] not in plan.live() or chosen[0] == ctx["controller"]:
        raise ValueError("not an opponent")
    plan.note(f"{plan.name(d.player)} chooses {plan.name(chosen[0])}")
    context.bind_players(ctx, d.resume["as"], [chosen[0]])
    continue_effects(plan, ctx)


PRIMITIVES["choose_opponent"] = choose_opponent
RESUME["choose_opponent"] = resume_choose_opponent

RESUME["search_may"] = resume_search_may
RESUME["draw_may"] = resume_draw_may  # (wave 17B)
RESUME["look_may"] = resume_look_may  # (wave 15C)
RESUME["search_zones"] = resume_search_zones  # -- refused zones/sized (wave 3R4) --
# -- counters & designations (wave 3E) --------------------------------------------------------------
# Rad counters (728), the monarch (725), the initiative (726), venture into the dungeon (701.49, 309),
# the Ring tempts you (701.54): app/rules/designations.py (a leaf module over this one).
from app.rules import designations  # noqa: E402, I001

PRIMITIVES.update(designations.PRIMITIVES)
RESUME.update(designations.RESUME)
# -- refused zones/sized (wave 3R4): app/rules/refused_zones.py (a leaf module over this one) --
from app.rules import refused_zones  # noqa: E402, I001

PRIMITIVES.update(refused_zones.PRIMITIVES)
RESUME.update(refused_zones.RESUME)
# -- end counters & designations (wave 3E) --

# -- refused grants/replacements (wave 3R2) -- source-of-your-choice shields (609.7a, 615.8) and "Damage can't be
# prevented this turn." (615.12): app/rules/source_shields.py (a leaf module over this one)
from app.rules import cant_gain, graveyard_grants, skips, source_shields  # noqa: E402, I001

PRIMITIVES.update(source_shields.PRIMITIVES)
PRIMITIVES.update(skips.PRIMITIVES)  # 614.10 "skips their next …" (app/rules/skips.py)
# -- next untap step (wave 6A) --
from app.rules import next_untap as _next_untap  # noqa: E402

PRIMITIVES.update(_next_untap.PRIMITIVES)  # 502.3 "doesn't untap during its controller's next untap step"
from app.rules import extra_turns as _extra_turns  # noqa: E402  -- extra turns (wave 8A) --
from app.rules import player_control as _player_control  # noqa: E402  (wave 18H)

PRIMITIVES.update(_player_control.PRIMITIVES)  # 723.1 "You control target player during that player's next turn."
PRIMITIVES.update(_extra_turns.PRIMITIVES)  # 500.7 "Take an extra turn after this one."
from app.rules import end_turn as _end_turn  # noqa: E402  -- end the turn (wave 46C) --

PRIMITIVES.update(_end_turn.PRIMITIVES)  # 724.1 "End the turn."
from app.rules import land_plays as _land_plays  # noqa: E402  -- one-shot extra land plays (wave 8A) --

PRIMITIVES.update(_land_plays.PRIMITIVES)  # 305.2 "You may play an additional land this turn."
from app.rules import bounce_forms as _bounce_forms  # noqa: E402

PRIMITIVES.update(_bounce_forms.PRIMITIVES)  # "return target A and target B to their owners' hands" (one move)
PRIMITIVES["exchange_life"] = exchange_life
PRIMITIVES["exchange_life_stat"] = exchange_life_stat
PRIMITIVES["set_life"] = set_life  # (wave 16C)  # -- activated wordings (wave 15D) --
PRIMITIVES.update(cant_gain.PRIMITIVES)  # 614.17 "can't gain life …" (app/rules/cant_gain.py)
from app.rules import game_result as _game_result  # noqa: E402, I001  -- prohibitions (wave 22B) --

PRIMITIVES.update(_game_result.PRIMITIVES)  # 104.2b / 104.3 "can't lose the game this turn" (app/rules/game_result.py)
from app.rules import prohibitions as _prohibitions  # noqa: E402, I001

PRIMITIVES.update(_prohibitions.PRIMITIVES)  # 614.17 "Players can't search libraries this turn." (app/rules/prohibitions.py)
from app.rules import hand_size as _hand_size  # noqa: E402  -- ability words (wave 20C) --

PRIMITIVES.update(_hand_size.PRIMITIVES)  # "You have no maximum hand size for the rest of the game." (app/rules/hand_size.py)
PRIMITIVES.update(graveyard_grants.PRIMITIVES)  # "gains flashback until end of turn" (app/rules/graveyard_grants.py)
RESUME.update(graveyard_grants.RESUME)  # ("Choose one of them.")
RESUME.update(source_shields.RESUME)
# -- end refused grants/replacements (wave 3R2) --
from app.rules import tap_mana as _tap_mana  # noqa: E402, I001  -- mana riders (wave 5A) --

PRIMITIVES["tap_mana_until_eot"] = _tap_mana.until_eot  # High Tide: a triggered mana ability for the rest of the turn
from app.rules import untap_riders as _untap_riders  # noqa: E402, I001

PRIMITIVES["untap_choice"] = _untap_riders.untap_choice  # "Untap up to three lands." (a choice, not a target)

# -- refused copy/mana (wave 3R3) -- "you don't lose this mana" (106.4, 500.4): app/rules/kept_mana.py
from app.rules import kept_mana as _kept_mana  # noqa: E402, I001

PRIMITIVES["keep_mana"] = _kept_mana.keep
from app.rules import mana_units as _mana_units  # noqa: E402, I001  -- mana provenance (wave 18B) --

PRIMITIVES["restrict_mana"] = _mana_units.restrict
# -- end refused copy/mana (wave 3R3) --

# -- unless pays (wave 4C) -- "you may [effect] unless that player pays …" (118.12a): app/rules/unless_pays.py
from app.rules import unless_pays as _unless_pays  # noqa: E402, I001

PRIMITIVES.update(_unless_pays.PRIMITIVES)
# -- end unless pays (wave 4C) --

# -- cast limits (wave 5E) -- "… can't cast spells this turn" / flash for a turn (app/rules/cast_limits.py)
from app.rules import cast_limits as _cast_limits  # noqa: E402, I001

PRIMITIVES.update(_cast_limits.PRIMITIVES)
RESUME.update(_cast_limits.RESUME)  # (and player hexproof / protection: app/rules/player_shields.py)
from app.rules import protection_grants as _protection_grants  # noqa: E402, I001

PRIMITIVES.update(_protection_grants.PRIMITIVES)  # "gains protection from the color of your choice" (608.2)
RESUME.update(_protection_grants.RESUME)
# -- end cast limits (wave 5E) --


# -- this-turn history (wave 4D) -- "If this is the second time this ability has resolved this turn": the resolution
# is counted as it begins (app/rules/history.py), the count kept for this resolution's condition
def _note_resolution(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import history

    context.refs(ctx)["resolution"] = {"kind": "amount", "n": history.note_resolution(plan, str(e["key"]))}
    return True


PRIMITIVES["note_resolution"] = _note_resolution
# -- end this-turn history (wave 4D) --

# -- X sized by a count (wave 4K) -- "Shuffle ~ into its owner's library." as a spell's last instruction (the Zenith
# cycle): app/rules/x_spells.py (a leaf module over this one)
from app.rules import x_spells as _x_spells  # noqa: E402, I001

PRIMITIVES.update(_x_spells.PRIMITIVES)
# -- end X sized by a count (wave 4K) --

# -- discover (wave 9A) -- 701.57: app/rules/discover.py
from app.rules import discover as _discover  # noqa: E402, I001

PRIMITIVES.update(_discover.PRIMITIVES)
# -- end discover (wave 9A) --

# -- recursion & tutors (wave 4M) -- a spell moving itself (608.2m/n) and the rest: app/rules/recursion.py
from app.rules import recursion as _recursion  # noqa: E402, I001

PRIMITIVES.update(_recursion.PRIMITIVES)
# -- end recursion & tutors (wave 4M) --


# -- combat (wave 5C) -- additional combat phases, tokens entering attacking each opponent (app/rules/combat_rules.py)
from app.rules import combat_rules as _combat_rules  # noqa: E402

PRIMITIVES.update(_combat_rules.PRIMITIVES)
from app.rules import ninjutsu as _ninjutsu  # noqa: E402  -- keywords (wave 15E) -- 702.49

PRIMITIVES["ninjutsu_enter"] = _ninjutsu.enter
from app.rules import miracle as _miracle  # noqa: E402, I001  -- casting extras (wave 18E) -- 702.94a

PRIMITIVES["miracle_offer"] = _miracle.offer
RESUME.update(_combat_rules.RESUME)

# -- triggers (wave 5D) -- "then put two cards from your hand on top of your library in any order" (app/rules/put_back.py)
from app.rules import put_back as _put_back  # noqa: E402, I001

PRIMITIVES.update(_put_back.PRIMITIVES)
RESUME.update(_put_back.RESUME)
# -- end triggers (wave 5D) --

# -- stack interaction (wave 5B) -- changing the target of a spell or ability (115.7): app/rules/stack_interaction.py
from app.rules import stack_interaction as _stack_interaction  # noqa: E402, I001

PRIMITIVES.update(_stack_interaction.PRIMITIVES)
RESUME.update(_stack_interaction.RESUME)
# -- end stack interaction (wave 5B) --

# -- token & pump wordings (wave 6C) -- Role tokens created attached to a creature (app/rules/roles.py)
from app.rules import roles as _roles  # noqa: E402, I001

PRIMITIVES.update(_roles.PRIMITIVES)
from app.rules import decayed as _decayed  # noqa: E402, I001  (702.147: decayed's sacrifice at end of combat)

PRIMITIVES.update(_decayed.PRIMITIVES)
# -- end token & pump wordings (wave 6C) --

# -- token copies & attach on entry (wave 5J) -- "attach it to target creature you control" (app/rules/attach_entry.py),
# populate and "for each …, create a token that's a copy of that …" (app/rules/populate.py)
from app.rules import attach_entry as _attach_entry  # noqa: E402, I001

PRIMITIVES.update(_attach_entry.PRIMITIVES)
RESUME.update(_attach_entry.RESUME)  # (wave 25A: attach_choose)
from app.rules import populate as _populate  # noqa: E402, I001

PRIMITIVES.update(_populate.PRIMITIVES)
RESUME.update(_populate.RESUME)
from app.rules import put_from_hand as _put_from_hand  # noqa: E402, I001

PRIMITIVES.update(_put_from_hand.PRIMITIVES)
RESUME.update(_put_from_hand.RESUME)
# -- end token copies & attach on entry (wave 5J) --
# -- tap or untap (wave 6D) -- "You may tap or untap target permanent." (app/rules/tap_or_untap.py)
from app.rules import tap_or_untap as _tap_or_untap  # noqa: E402

PRIMITIVES.update(_tap_or_untap.PRIMITIVES)
RESUME["tap_or_untap"] = _tap_or_untap.resume
# -- state triggers (wave 6D) -- the marker effect of a state trigger (603.8: app/rules/state_triggers.py)
from app.rules import state_triggers as _state_triggers  # noqa: E402

PRIMITIVES.update(_state_triggers.PRIMITIVES)
# -- endure (wave 6D) -- "it endures 2" (701.63: app/rules/endure.py)
from app.rules import endure as _endure  # noqa: E402

PRIMITIVES.update(_endure.PRIMITIVES)
RESUME["endure"] = _endure.resume
# -- win the game (wave 6D) -- "you win the game" (104.2b: app/rules/win_game.py)
from app.rules import win_game as _win_game  # noqa: E402

PRIMITIVES.update(_win_game.PRIMITIVES)

# -- if you do (wave 6F) -- "Each opponent may [cost]. Each opponent who doesn't …" (app/rules/each_may.py)
from app.rules import each_may as _each_may  # noqa: E402, I001

PRIMITIVES.update(_each_may.PRIMITIVES)
# -- end if you do (wave 6F) --
# -- choice grants and switches (wave 7E) -- app/rules/choice_grants.py
from app.rules import choice_grants as _choice_grants  # noqa: E402, I001

PRIMITIVES.update(_choice_grants.PRIMITIVES)
from app.rules import coin_flips as _coin_flips  # noqa: E402, I001  -- coin flips (wave 7E)

PRIMITIVES.update(_coin_flips.PRIMITIVES)
from app.rules import clash as _clash  # noqa: E402, I001  -- clash (wave 12A)

PRIMITIVES.update(_clash.PRIMITIVES)
RESUME[_clash.STEP] = _clash.resume
from app.rules import dice as _dice  # noqa: E402, I001  -- rolling dice (wave 12A)

PRIMITIVES.update(_dice.PRIMITIVES)
RESUME[_dice.STEP] = _dice.resume
from app.rules import counter_moves as _counter_moves  # noqa: E402, I001  -- moving counters (wave 12A)

PRIMITIVES.update(_counter_moves.PRIMITIVES)
RESUME[_counter_moves.STEP] = _counter_moves.resume
RESUME.update(_choice_grants.RESUME)
# -- zone replacements (wave 22C) -- "If it would leave the battlefield, exile it instead of putting it anywhere else." (app/rules/leave_exile.py)
from app.rules import leave_exile as _leave_exile  # noqa: E402, I001

PRIMITIVES.update(_leave_exile.PRIMITIVES)
# -- per-player filters (wave 23A) -- "Each opponent who can't …": the players a predicate holds for (app/rules/player_filter.py)
from app.rules import player_filter as _player_filter  # noqa: E402, I001

PRIMITIVES.update(_player_filter.PRIMITIVES)
# -- villainous choice (wave 23A) -- 701.55 (app/rules/villainous.py)
from app.rules import villainous as _villainous  # noqa: E402, I001

PRIMITIVES.update(_villainous.PRIMITIVES)
# -- speed (wave 24B) -- 702.179c (app/rules/speed.py)
from app.rules import speed as _speed  # noqa: E402, I001

PRIMITIVES.update(_speed.PRIMITIVES)
# -- soulbond (wave 24B) -- 702.95 (app/rules/pairing.py)
from app.rules import pairing as _pairing  # noqa: E402, I001

PRIMITIVES.update(_pairing.PRIMITIVES)
RESUME[_pairing.STEP] = _pairing.resume
# -- loops and repeats (wave 24B) -- "Repeat this process" (608.2c: app/rules/loops.py)
from app.rules import loops as _loops  # noqa: E402, I001

PRIMITIVES.update(_loops.PRIMITIVES)
RESUME[_loops.STEP] = _loops.resume
RESUME.update(_villainous.RESUME)
# -- counter kinds (wave 24C) -- "for each kind of counter on …", "choose a counter on …", "remove any number of counters" (app/rules/counter_kinds.py)
from app.rules import counter_kinds as _counter_kinds  # noqa: E402, I001

PRIMITIVES.update(_counter_kinds.PRIMITIVES)
RESUME.update(_counter_kinds.RESUME)
# -- suspend granted (wave 24C) -- "it gains suspend" (app/rules/suspend_grants.py)
from app.rules import suspend_grants as _suspend_grants  # noqa: E402, I001

PRIMITIVES.update(_suspend_grants.PRIMITIVES)
# -- trigger other (wave 25B) -- airbend 701.65 (app/rules/airbend.py)
from app.rules import airbend as _airbend  # noqa: E402, I001

PRIMITIVES.update(_airbend.PRIMITIVES)
# -- trigger other (wave 25B) -- "create a Food token or a Treasure token" (app/rules/resolution_choice.py)
from app.rules import resolution_choice as _resolution_choice  # noqa: E402, I001

PRIMITIVES.update(_resolution_choice.PRIMITIVES)
RESUME[_resolution_choice.STEP] = _resolution_choice.resume
# -- trigger other (wave 25B) -- "put the cards in your hand on the bottom of your library in any order, then draw that many cards" (app/rules/hand_wheel.py)
from app.rules import hand_wheel as _hand_wheel  # noqa: E402, I001

PRIMITIVES.update(_hand_wheel.PRIMITIVES)
# -- trigger other (wave 25B) -- join forces (app/rules/join_forces.py)
from app.rules import join_forces as _join_forces  # noqa: E402, I001

PRIMITIVES.update(_join_forces.PRIMITIVES)
# -- cast riders (wave 25C) -- "When you next cast a creature spell this turn, that creature enters with an additional +1/+1 counter on it."
from app.rules import cast_riders as _cast_riders  # noqa: E402, I001

PRIMITIVES.update(_cast_riders.PRIMITIVES)
# -- cast riders (wave 38C) -- "exile it instead of putting it into your graveyard as it resolves", "it becomes plotted" (app/rules/resolve_exile.py)
from app.rules import resolve_exile as _resolve_exile  # noqa: E402, I001

PRIMITIVES.update(_resolve_exile.PRIMITIVES)
# -- pay to untap (wave 25C) -- Dream Tides, Mudslide (app/rules/pay_untap.py)
from app.rules import pay_untap as _pay_untap  # noqa: E402, I001

PRIMITIVES.update(_pay_untap.PRIMITIVES)
RESUME[_pay_untap.STEP] = _pay_untap.resume
# -- spell grants (wave 28C) -- "The next spell you cast this turn has improvise." (app/rules/spell_grants.py)
from app.rules import spell_grants as _spell_grants  # noqa: E402, I001

PRIMITIVES.update(_spell_grants.PRIMITIVES)
