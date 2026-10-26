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
import json
from collections.abc import Callable, Iterator
from typing import Any

from app.game.rules_state import DecisionOption, ObjectRef, StackEntry, remember_stack
from app.game.state import ALL, STACK, zone_key
from app.rules import (
    block_effects,  # -- block effects (wave 30P) -- the object arguments of a block rule (a leaf module)
    block_events,  # -- block events (wave 53C) -- combat and attachment relations to a named creature (a leaf module)
    card_names,  # -- card names (wave 22B) -- 201.4
    context,
    delayed,
    entry_forms,
    layers,
    optional_payment,
    permissions,
    player_relative,  # -- player-relative selectors (wave 53A) --
    player_zones,
    regeneration,
    replace,  # -- replacement effects stage 2 (wave 2E): the choke points --
    replacements,
    selectors,
    sized_damage,  # -- damage sized by a count (wave 4E) --
    values,
)
from app.rules import this_way as _this_way  # -- "this way" outcomes (wave 4A) --
from app.rules.plan import Plan, decide
from app.rules.targets import relation_ok, source_of, still_legal

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
    if who.startswith("others100c:"):  # -- static spells (wave 100C) -- "each player other than target player"
        named = set(_players(plan, ctx, who[len("others100c:"):]))
        return [p for p in plan.live() if p not in named]
    if who.startswith("owners100c:"):  # -- static spells (wave 100C) -- "the owners of those cards"
        return [p for p in dict.fromkeys(plan.state.cards[c].owner for c in _cards(plan, ctx, who[len("owners100c:"):])) if p in plan.live()]
    if who.startswith(selectors.PREFIX):  # "each opponent", "each player" … as a selector
        sel = selectors.from_key(who)
        return [p for p in plan.live() if selectors.matches_player(plan, sel, p, me)] if sel.player else []
    if who == "target_owner":
        original = values._object(plan, ctx, "target")
        return [original[0].owner] if original is not None and original[0].owner in plan.live() else []
    if who == "you":
        return [me]
    if who == "left110e":  # -- left opponent (wave 110E) -- "the opponent to your left"/"that player" of Barroom Brawl: the next live player in turn order
        return [plan.after(me)]
    if who.startswith(player_relative.TP):  # -- player-relative selectors (wave 53A) -- the player (or the permanent's controller) a target group names
        return player_relative.players_in(plan, ctx, int(who[len(player_relative.TP):]))
    if who.startswith("player:"):  # -- keywords (wave 15E) -- one named player (ward: the player whose spell or ability targeted)
        return [who[7:]] if who[7:] in plan.live() else []
    if who == "each_player":
        return list(plan.live())
    if who == "source_controller110a":  # -- wave 110A -- "~'s controller" in an ability anyone may activate (Xantcha); last known if it left (608.2h)
        src110a = plan.state.cards.get(ctx.get("source_card") or "")
        snap110a = plan.rules.lki.get(ctx.get("source_object") or "")
        ctl110a = src110a.controller if src110a is not None and plan.oid(src110a) == ctx.get("source_object") else snap110a.controller if snap110a is not None else ""
        return [ctl110a] if ctl110a in plan.live() else []
    if who == "host_controller":  # -- block events (wave 53C) -- "enchanted permanent's controller": the controller of what the source is attached to, fixed when first read
        # (608.2c: "then that player loses 1 life" is still that player when the permanent was just sacrificed); no host, nobody
        if "host_controller" not in ctx:
            hosts = _cards(plan, ctx, "host")
            ctx["host_controller"] = plan.state.cards[hosts[0]].controller if hosts else ""
        return [ctx["host_controller"]] if ctx["host_controller"] in plan.live() else []
    if who == "looked_owner":  # -- most-played cards III (wave 46C) -- the owner of the library the last look or reveal was at
        return [ctx["looked_owner"]] if ctx.get("looked_owner") in plan.live() else []
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
    if who == "each_other_than_event":  # -- trigger other (wave 51C) -- every player but the one(s) the trigger event was about
        named = set(context.players(plan, ctx, context.EVENT))
        return [p for p in plan.live() if p not in named]
    if who == "each_other_opponent":  # -- sized amounts (wave 3D) -- the opponents besides the player the trigger event was about
        named = set(context.players(plan, ctx, context.EVENT))
        return [p for p in plan.live() if p != me and p not in named]
    if who == "event_opponents":  # -- player groups (wave 51G) -- "each of that player's opponents" (102.2): the other players, the controller among them when it isn't that player
        named = set(context.players(plan, ctx, context.EVENT))
        return [p for p in plan.live() if p not in named] if len(named) == 1 else []
    if who == "event_player":  # "that player": the one the trigger event was about (who drew, was dealt damage …)
        return context.players(plan, ctx, context.EVENT)
    if who == "source_controller":
        source_controller_card = plan.state.cards.get(ctx.get("source_card") or "")
        if source_controller_card is not None and plan.oid(source_controller_card) == ctx.get("source_object") and (source_controller_card.zone == "stack" or source_controller_card.zone.endswith(":battlefield")):
            pid = source_controller_card.controller
        else:
            snap = plan.rules.lki.get(ctx.get("source_object") or "")
            pid = snap.controller if snap is not None else None
        return [pid] if pid is not None and pid in plan.live() else []
    if who == "each_other_than_source_owner110d":  # -- lines (wave 110D) -- "each other player" next to "its owner" (Oft-Nabbed Goat): everyone but the source card's owner (108.3)
        src = plan.state.cards.get(ctx.get("source_card") or "") or plan.rules.lki.get(ctx.get("source_object") or "")
        return [p for p in plan.live() if src is None or p != src.owner]
    if who == "source_owner":  # -- review 33 -- "~'s owner": the source card's owner, wherever it is now (108.3; a card shuffled into a
        src = plan.state.cards.get(ctx.get("source_card") or "") or plan.rules.lki.get(ctx.get("source_object") or "")  # library is known
        return [src.owner] if src is not None and src.owner in plan.live() else []  # there by no id: as it last existed, 608.2h)
    if who == "enchanted_player":
        from app.rules import attached_players

        return attached_players.enchanted_player(plan, ctx)
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
    if who.startswith(("owned100c:", "attached100c:", "partner100c:", "samemv100c:", "dust100c")):  # -- static spells (wave 100C) -- "all artifacts target player owns", "all Auras attached to it", ...
        from app.rules import static_spell100c

        return static_spell100c.cards(plan, ctx, who)
    if who == 'all_targets':
        return list(dict.fromkeys(cid for i in range(len(ctx.get('groups') or []))
                                  for cid in _cards(plan, ctx, f'target:{i}')))
    if who == "bandmates":
        from app.rules import banding

        return banding.companions(plan, ctx)
    if who.startswith(context.PREFIX) and "|" in who:  # -- resolution memory (wave 22D) -- "each creature card put into a graveyard this way"
        from app.rules import this_way

        base, _, key = who.partition("|")
        return this_way.filtered(plan, ctx, _cards(plan, ctx, base), key)
    if who.startswith("union:"):  # -- block events (wave 53C) -- several references at once: "destroy both creatures"
        return list(dict.fromkeys(c for w in who[len("union:"):].split("+") for c in _cards(plan, ctx, w)))
    if who.startswith("typed:"):  # -- player-relative selectors (wave 53A) -- "all creature cards of a type chosen this way" (Patriarch's Bidding)
        return _player_choices.cards_of_types(plan, ctx, who)
    if who.startswith(player_zones.PREFIX):  # -- player-relative selectors (wave 53A) -- "all cards from target player's hand and graveyard"
        return player_zones.cards(plan, ctx, who)
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
        if any(isinstance(c[2], str) and c[2].startswith(selectors.RESOLUTION_STAT) for c in sel.compare):
            bound_energy: list[tuple[str, str, int | float | str]] = []
            for w, op, n in sel.compare:
                if isinstance(n, str) and n.startswith(selectors.RESOLUTION_STAT):
                    binding = n[len(selectors.RESOLUTION_STAT):]
                    if binding not in context.refs(ctx):
                        return []
                    n = values.evaluate(plan, ctx, {"ref_amount": binding})
                bound_energy.append((w, op, n))
            sel = selectors.replace(sel, compare=tuple(bound_energy))
        if any(isinstance(c[2], str) and c[2].startswith(selectors.TARGET_STAT) for c in sel.compare):  # -- most-played cards II (wave 45A) -- "power greater than target creature's power"
            first = next(iter(target_refs(ctx, "target")), {})  # (its power as the spell resolves, 608.2b; none left: the spell didn't resolve)
            tc = plan.state.cards.get(first.get("id", ""))
            if tc is None or not tc.zone.endswith(":battlefield") or plan.oid(tc) != first.get("object_id"):
                return []
            bound: list[tuple[str, str, int | float | str]] = []
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
    if who == "ring_bearer":  # -- random choices (wave 47B) -- "your Ring-bearer" (701.54a): the creature the Ring chose for the controller, while it still is
        bearer = designations._bearer_card(plan, ctx["controller"])
        return [bearer.id] if bearer is not None else []
    if who == "self_stack":
        src = plan.state.cards.get(ctx.get("source_card") or "")
        return [src.id] if src is not None and src.zone == "stack" and plan.oid(src) == ctx.get("source_object") else []
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
    if who == "cost:exiled":
        sid = ctx.get("stack_id")
        record = plan.rules.payments.get(plan.rules.object_id(sid)) if sid else None
        return [cid for oid in (record.exiled_objects if record is not None else [])
                if (cid := oid.rsplit(".", 1)[0]) in plan.state.cards and plan.oid(cid) == oid
                and plan.state.cards[cid].zone.endswith(":exile")]
    if who == "cost_exiled_self":  # -- casting extras (wave 18E) -- craft 702.167a: the source itself, exiled as part of the cost
        sid = ctx.get("stack_id")
        record = plan.rules.payments.get(plan.rules.object_id(sid)) if sid else None
        src = ctx.get("source_card")
        return [src] if record is not None and src in record.exiled and src in plan.state.cards \
            and plan.state.cards[src].zone.endswith(":exile") \
            and (not record.exiled_objects or plan.oid(src) in record.exiled_objects) else []  # (-- as long as (wave 37A) -- 400.7j: that object, not a later one)
    if who == 'cost_discarded_self':
        sid = ctx.get('stack_id')
        record = plan.rules.payments.get(plan.rules.object_id(sid)) if sid else None
        src = plan.state.cards.get(ctx.get('source_card') or '')
        return [src.id] if src is not None and record is not None and src.id in record.discarded \
            and src.zone == zone_key(ctx['controller'], 'graveyard') and plan.oid(src) in record.discarded_objects else []
    if who in ("self_gy", "self_gy_exile"):  # -- reanimation (wave 3R) -- "return this card from your graveyard": the source, only
        # while it is still the same object in a graveyard (400.7); -- activated other (wave 42C) -- "… from your graveyard or from exile": in either
        src = plan.state.cards.get(ctx.get("source_card") or "")
        if src is not None and src.zone.endswith((":graveyard", ":exile") if who == "self_gy_exile" else ":graveyard") and plan.oid(src) == ctx.get("source_object"):
            return [src.id]
        return []
    if who in ("self_hand", "self_command", "self_exile"):  # -- activated from hand / command zone (wave 27D; wave 110B: exile, Senu) -- 113.6m: the source, only while it
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
            if host is not None and snap is not None and snap.attached_object is not None and plan.oid(host) != snap.attached_object:
                host = None  # a new incarnation is no longer the permanent the departed Aura enchanted
        return [host.id] if host is not None and host.zone.endswith(":battlefield") else []
    if who == "host:kin":  # -- attached events (wave 25D) -- "Enchanted creature and other creatures that share a creature type with it" (the Crowns)
        return _host_kin(plan, ctx)
    if who == "kin110e":  # -- wave 110E -- "target creature and each other creature that shares a creature type with it" (205.3m; Killer)
        from app.rules.creature_types import CREATURE_TYPES

        found = [c for c in _cards(plan, ctx, "target") if plan.state.cards[c].zone.endswith(":battlefield")]
        if not found:
            return []
        kinds = plan.ch(plan.state.cards[found[0]]).subtypes & CREATURE_TYPES
        return [*found[:1], *(c.id for c in plan.state.cards.values() if c.id != found[0] and c.zone.endswith(":battlefield") and plan.in_game(c)
                              and (ch := plan.ch(c)).is_creature and kinds & ch.subtypes)]
    if who == "exiled_with" or who.startswith("exiled_with:"):  # -- exiled with (wave 6D) -- 607.2a (app/rules/exiled_with.py)
        from app.rules import exiled_with

        return exiled_with.cards(plan, ctx, who)
    if who == "event":  # "it" / "that creature": the object(s) the trigger event happened to — only while
        # each is still that object where it was (400.7: after a zone change it's a new object)
        return context.objects(plan, ctx, context.EVENT)
    if who == "event_spell":  # -- spell copies (wave 31D) -- the spell a cast trigger is about, while it is still that object on the stack (400.7)
        return [c for c in context.objects(plan, ctx, context.EVENT) if plan.state.cards[c].zone == "stack"]
    if who == "event_gy":  # -- review 42 -- "return this card from your graveyard …" (Mangara's Blessing): the discarded card while it is still that object in a
        # graveyard; discarded into exile instead (an opponent's Leyline of the Void), it is not returned (the card's ruling 2004-10-04)
        return [c for c in context.objects(plan, ctx, context.EVENT) if plan.state.cards[c].zone.endswith(":graveyard")]
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
    if e.get("as"):  # -- if you do (wave 52A) -- "for each card drawn this way": what each player had drawn this turn before (this_way.drawn reads the difference)
        from app.rules import this_way

        this_way.mark_drawn(plan, ctx, e["as"])
    players = _players(plan, ctx, e["who"])
    if sized_damage.has_per_player(e["n"]):  # -- static spells (wave 100C) -- "each player draws a card for each creature card in their graveyard":
        # every player's number determined once, before the first draw (608.2h); the draws in APNAP order (121.2c)
        each = {p: max(0, _amount(plan, {**ctx, "recipient": p}, e["n"])) for p in players}
        players = [p for p in players if each[p] > 0]
        return not players or replace.draw_cards(plan, players, each, then=_then(ctx, e), ctx=ctx)
    if isinstance(e["n"], dict) and e["n"].get("each_hand_shortfall"):
        # 608.2h: determine every shortfall once, before the first draw. A draw
        # replacement may then enlarge one hand without increasing later draws.
        hands = {p: len(plan.state.zones.get(f"{p}:hand", [])) for p in plan.live()}
        maximum = max(hands.values(), default=0)
        each = {p: max(0, maximum - hands[p]) for p in players}
        players = [p for p in players if each[p] > 0]
        if players:
            _drawing(ctx, e)
        # The existing replacement runner retains these counts through choices
        # and performs one player's draws before the next in APNAP order (121.2c).
        return not players or replace.draw_cards(plan, players, each, then=_then(ctx, e), ctx=ctx)
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
    if e.get("upto") and players and ctx.get("may_ok") != ctx["next"]:  # -- delayed draws (wave 51B) -- "may draw up to two cards": that player picks 0..N (608.2d)
        n = _amount(plan, ctx, e["n"])
        decide(plan, player=players[0], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: draw how many cards?",
               options=[DecisionOption(id=str(i), label=f"Draw {i}") for i in range(n + 1)],
               resume={"step": "draw_upto", "ctx": ctx, "e": e})
        return False
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
    counts = e.get('counts')
    gains = [(pid, amount) for pid in _players(plan, ctx, e["who"])
             if (amount := max(0, int(counts.get(pid, 0))) if counts is not None else n) > 0]
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
    if e.get('counts') is not None:
        each = {p: max(0,int(e['counts'].get(p,0))) for p in _players(plan,ctx,e['who'])}
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
    receipt: list[int] = []
    # -- life modifiers (wave 28B) -- the life-loss choke point: "would lose life" replacements (Bloodletter of Aclazotz)
    if not replace.lose_life(plan, losses, actor=ctx["controller"], then=_then(ctx, e), ctx=ctx, receipt=receipt, bind=e.get("bind")):
        return False
    lost = sum(receipt)
    if e.get("bind"):  # -- refused zones/sized (wave 3R4) -- "the life lost this way": the total actually lost (119.3)
        context.bind_amount(ctx, e["bind"], lost)
    return True


def set_life(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import life_changes44

    return life_changes44.set_life(plan, ctx, e)

def exchange_life(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import life_changes44

    return life_changes44.exchange_life(plan, ctx, e)

def exchange_life_stat(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import life_changes44

    return life_changes44.exchange_life_stat(plan, ctx, e)

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
    from app.rules import source_qualities

    if src_ch is not None:
        from dataclasses import replace as dc_replace

        is_spell = bool((source is not None and plan.oid(source) == ctx.get("source_object")
                         and source.zone == "stack" and source.ability is None)
                        or (lki is not None and lki.zone == "stack"))
        src_ch = dc_replace(src_ch, is_spell=is_spell)
        x = 0
        if source is not None and plan.oid(source) == ctx.get('source_object') and source.zone == 'stack':
            x = (source.stack_info.x or 0) if source.stack_info else 0
        elif lki is not None and lki.zone == 'stack':
            x = lki.x or 0
        src_ch = source_qualities.source(src_ch, x)
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


def _named_source(plan: Plan, ctx: Context, who: str, *, public_card: bool = False) -> _Source | None:
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
        if card is not None and (card.zone.endswith(":battlefield") or (public_card and who.startswith('ref:') and card.zone.split(':')[-1] in ('graveyard', 'exile'))) and (oid is None or plan.oid(card) == oid):
            return _card_source(plan, card.id)
        snap = plan.rules.lki.get(oid or "")
        if snap is not None:
            from app.rules.triggers import _snapshot_card  # (triggers imports this module)

            _, ch = _snapshot_card(plan, snap)
            from dataclasses import replace as dc_replace

            from app.rules import source_qualities

            ch = dc_replace(source_qualities.source(ch, snap.x if snap.zone == 'stack' else 0), is_spell=snap.zone == 'stack')
            return _Source(snap.object_id, ch.keywords, ch, snap.controller,
                           snap.card if snap.card in plan.state.cards else None)
    return None


def _card_source(plan: Plan, cid: str) -> _Source:
    """A creature on the battlefield as a damage source (a fight, a bite)."""
    ch = plan.ch(plan.state.cards[cid])
    return _Source(plan.oid(cid), ch.keywords, ch, cid, cid)


_DAMAGE_KEYWORDS = frozenset({"lifelink", "deathtouch", "wither", "infect"})


def _deal(plan: Plan, ctx: Context, hits: list[tuple[_Source, str, int]], e: dict[str, Any] | None = None,
          *, before: tuple[tuple[str, list[str]], ...] = (), completed_next: int | None = None) -> bool:
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
        if e is not None and e.get("creature_firm110h") and key in plan.state.cards and "Creature" in plan.ch(plan.state.cards[key]).types:
            ev.update(unpreventable=True, unredirectable110h=True)  # -- Lava Burst (wave 110H) -- 615.12, 614.9
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
        excess_events = out.events
        if e.get("excess_on"):
            recipients = set(_cards(plan, ctx, e["excess_on"]))
            excess_events = [ev for ev in excess_events if ev["target"] in recipients]
        context.bind_amount(ctx, e["bind_excess"], _this_way.excess_of(plan, excess_events))
    if e is not None and e.get("bind_hit"):  # -- if you do (wave 10C) -- "If a Dragon is dealt damage this way" (this_way.hits)
        context.bind_amount(ctx, e["bind_hit"], _this_way.hits(plan, ctx, out.events, e["hit_is"]))
    if e is not None and e.get('bind_life_caps'):
        from app.rules import capped_damage_life

        capped_damage_life.capture(plan, ctx, e['bind_life_caps'], out.events)
    if e is not None and e.get('bind_damage_players'):
        context.bind_players(ctx, e['bind_damage_players'], list(dict.fromkeys(
            ev['target'] for ev in out.events if int(ev['amount']) > 0 and ev['target'] in plan.state.players)))
    if e is not None and e.get("bind_dealt"):  # -- if you do (wave 5G) -- "the damage dealt this way" (this_way.damage_dealt)
        context.bind_amount(ctx, e["bind_dealt"], sum(max(0, int(ev["amount"])) for ev in out.events))
    after_ctx = dict(ctx)
    if completed_next is not None:
        after_ctx["next"] = completed_next
    return replace.do_damage(plan, out, actor=ctx["controller"], combat=False,
                             then={"do": "continue", "ctx": after_ctx})


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
    joined: dict[tuple[str, str], tuple[_Source, str, int]] = {}
    for src, key, n in (h for x in chain for h in _damage_hits(plan, ctx, x)):  # (one source, one recipient: one amount, Kaervek's Hex)
        joined[src.oid, key] = (src, key, n + joined[src.oid, key][2]) if (src.oid, key) in joined else (src, key, n)
    hits = list(joined.values())
    done = _deal(plan, ctx, hits, e, completed_next=k + len(chain) - 1) if hits else True
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
                    [str(plan.state.cards[sid].attached_to)] if e.get("to") == "attached100c" else \
                    [sid] if e["who"] == "itself" else [*_other_than(plan, ctx, e, cards, sid), *players]  # (wave 24D: "to its controller"; wave 100C: "to the creature it's attached to")
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
        src = _named_source(plan, ctx, e["src"], public_card=bool(e.get('public_card_source')))
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
    sel = selectors.from_key(key)
    skip = {t["id"] for t in player_relative.other_than(ctx, players, sel)}  # (-- player-relative selectors (wave 53A) -- "each other creature that player controls")
    return [c for c in selectors.candidates(plan, sel, ctx["controller"], ctx.get("source_card"))
            if plan.state.cards[c].controller in owners and c not in skip]
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
    if e.get("bind_excess"):
        context.bind_amount(ctx, e["bind_excess"], 0)
    if e.get("twin110f"):  # -- wave 110F -- the two creatures of one chosen group fight each other (Rivals' Duel)
        both = _cards(plan, ctx, e["who"])
        a, b = (both[:1], both[1:]) if len(both) == 2 else ([], [])
    else:
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
    from app.rules import fight_receipts90

    fight_receipts90.record(plan, [ca, cb])
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
        duration = e.get("duration", "end_of_turn")
        when = {"end_of_combat": "this combat", "end_of_turn": "until end of turn"}.get(duration, "for the rest of the game")
        layers.add_effect(plan, affected=affected, layer="7c", source=ctx.get("source_object"), controller=ctx["controller"],
                          power=p, toughness=t, duration=duration,
                          label=f"{_stat_label(p)}/{_stat_label(t)} {when} ({ctx.get('name', '')})")
        _mark(plan, _cards(plan, ctx, e["who"]), f"{_stat_label(p)}/{_stat_label(t)}", text=when)
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
    from app.rules import player_protection_grants, source_quality_grants

    abilities = source_quality_grants.abilities(plan, ctx, player_protection_grants.abilities(plan, ctx, list(e.get("abilities") or [])))
    abilities = [a.replace("to the player who cast this spell", f"to player {ctx['controller']}") for a in abilities]  # -- wave 110A -- Hellish Rebuke (601.2: the caster)
    if abilities:
        receivers = [c for c in cards if plan.state.cards[c].zone.endswith(":battlefield") or (
            plan.state.cards[c].zone == "stack" and plan.state.cards[c].ability is None
            and ((entry := plan.rules.stack.get(c)) is None or entry.kind == "spell"))]
        if len(receivers) < len(cards):
            plan.note(f"{ctx.get('name') or 'The effect'}: only a permanent or a spell gains an ability", actor=ctx["controller"])
        cards = receivers
    if cards and (keywords or removed or abilities):
        words = [*keywords, *(f"loses {k}" for k in removed), *(f'"{a}"' for a in abilities)]
        duration = e.get("duration", "end_of_turn")
        when = {"end_of_turn": "until end of turn", "end_of_combat": "this combat"}.get(duration, "for the rest of the game")  # (wave 49C: end_of_combat)
        layers.add_effect(plan, affected=[plan.oid(c) for c in cards], layer="6", source=ctx.get("source_object"),
                          controller=ctx["controller"], add_keywords=tuple(keywords), remove_keywords=tuple(removed),
                          imposes=tuple("cant_have_keyword:" + k for k in e.get("deny", ())),
                          duration=duration, label=f"{', '.join(words)} {when}", add_abilities=abilities,
                          activation_player=ctx["controller"] if e.get("activation_player") == "you" else None)
        marker = ", ".join([*(k.capitalize() for k in keywords), *(f"No {k}" for k in removed),
                            *(f'Gains "{a}"' for a in abilities)])
        _mark(plan, cards, marker, value="Ability" if abilities and not (keywords or removed) else None,
              text={"end_of_turn": "until end of turn", "end_of_combat": "this combat"}.get(duration, "as long as it's on the battlefield"))
    return True


# (the table marker's value is at most 20 characters: app/game/actions.py AddEffect.value)
RESTRICTION_LABELS = {"assign_toughness_if_tougher": "Assigns combat damage using toughness when toughness exceeds power",
                      "cant_block": "Can't block", "cant_attack": "Can't attack", "cant_attack_or_block": "Can't attack/block",
                      "cant_be_blocked": "Can't be blocked", "must_attack": "Attacks if able",
                      "assign_none": "Assigns no combat damage"}


# -- attack restrictions (wave 32B) -- the marker of "can't attack you …" names the player (the rule's own text is "cant_attack_player:<id>")
ATTACK_LABELS = {"cant_attack_player": "Can't attack {}", "cant_attack_player_pw": "Can't attack {} or their planeswalkers",
                 "cant_attack_player_perm": "Can't attack {} or their permanents", "cant_attack_player_jace110b": "Can't attack {}'s Jaces", "attack_tax": "Attacking {} costs extra",
                 "attack_tax_pw": "Attacking {} costs extra", "attack_player": "Attacks {} if able"}  # (attack_player: wave 47B)


def _restriction_label(plan: Plan, rule: str) -> str:
    if rule.startswith('declaration_cost:'):
        parts = rule.split(':')
        return f"{'Attacking' if parts[1] == 'attack' else 'Blocking'} costs {{{parts[2]}}}"
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
    if e.get('dealt'):
        oids = list(dict.fromkeys((ctx.get(DEALT_KEY) or {}).get(e['dealt']) or []))
        if e.get('types'):  # -- if you do (wave 100B) -- "A creature dealt damage this way can't block this turn": only those that were creatures (not a planeswalker)
            oids = [o for o in oids if (c := plan.state.cards.get(o.rsplit('.', 1)[0])) is not None and plan.oid(c) == o
                    and set(e['types']) & set(plan.ch(c).types)]
        e = {**e, 'who': 'union:' + '+'.join('object:' + oid for oid in oids), 'locked': True}
    who = _GROUPS.get(e["who"], e["who"])
    cards = _cards(plan, ctx, who)
    _remember(plan, ctx, e, cards)
    if any("@owner" in r for r in e["rules"]):  # -- group choices (wave 53D) -- "can't attack its owner": one restriction for each creature, naming its own owner
        for cid in cards:
            restrict(plan, ctx, {**e, "who": f"object:{plan.oid(cid)}", "rules": [r.replace("@owner", plan.state.cards[cid].owner) for r in e["rules"]]})
        return True
    if any("@that" in r for r in e["rules"]):  # -- random choices (wave 47B) -- "attacks that player": the player picked before (none left: nothing is required)
        that = _players(plan, ctx, e["player"])
        if not that:
            return True
        e = {**e, "rules": [r.replace("@that", that[0]) for r in e["rules"]]}
    if any(r.startswith('declaration_cost:') for r in e['rules']):
        e = {**e, 'rules': [r.replace('{@x}', str(values.evaluate(plan, ctx, {'x': 1}))).replace('@cost_instance', f'e{plan.rules.timestamp + 1}') for r in e['rules']]}
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
            sel = selectors.from_key(key)
            mine = selectors.replace(sel, controller=f"player:{pid}", extras=(*sel.extras, *(f"not_oid:{t['object_id']}" for t in player_relative.other_than(ctx, players, sel)))).key()  # (-- player-relative selectors (wave 53A) -- "Other creatures that player controls can't block": other than the target)
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
                          label=", ".join(_restriction_label(plan, r) for r in e["rules"]), who=who if group else None, source_card=ctx.get("source_card"),
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
    from app.rules import regeneration_choices

    doomed = [c for c in cards if "indestructible" not in plan.ch(plan.state.cards[c]).keywords]
    if not regeneration_choices.prepare(plan, doomed, can_regenerate=_can_regenerate(ctx), ctx=ctx):
        return False
    before = _remember(plan, ctx, e, cards)
    doomed = regeneration.survivors(plan, doomed, can_regenerate=_can_regenerate(ctx), actor=ctx["controller"])
    if doomed:
        gone = {c: plan.oid(c) for c in doomed}
        plan.do({"type": "move", "card_ids": doomed, "to": {"zone": "graveyard"}}, actor=ctx["controller"])
        _destroyed(plan, gone, ctx["controller"])
    _moved(plan, ctx, e, before)
    regeneration_choices.finish(plan)
    return True


def _destroyed(plan: Plan, gone: dict[str, str], by: str | None = None) -> None:
    """-- destroy events (wave 45C) -- 701.8a-b: these permanents (card -> the object it was) were destroyed: an effect's "destroy" that put them into their
    owner's graveyard (a replacement that sent one elsewhere, or a regeneration or an indestructible permanent, didn't destroy it). The event joins the
    batch of the move, so a permanent that left with them sees it (603.10a). ponytail: the state-based destruction (704.5g-h) isn't recorded, so the
    trigger grammar only reads a subject that can't be a creature (events.py)."""
    from app.game.rules_state import Event

    r = plan.rules
    if by is not None:  # -- turn history (wave 110C) -- who destroyed them (Cobra Trap)
        from app.rules import wave110c_history

        wave110c_history.note_destroyed(plan, {c: o for c, o in gone.items() if (k := plan.state.cards.get(c)) is None or k.zone.endswith(":graveyard")}, by)
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
    cards = _prohibitions.trigger_token_shield(plan, ctx, cards)  # -- prohibitions (wave 110A) --
    before = _remember(plan, ctx, e, cards)
    if cards:
        on_bf = [c for c in cards if plan.state.cards[c].zone.endswith(":battlefield")]  # -- cards (wave 110I) --
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "exile"},
                 **({'face_down': True, 'blind': bool(e.get('blind'))} if e.get('face_down') else {})}, actor=ctx["controller"])
        _wave110i_cards.note_exiled(plan, ctx, on_bf)
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
    # (-- most-played modal spells (wave 50I) -- "Target player scries 3": that player looks; wave 110C: "an opponent … and they scry 2", the player an earlier instruction chose)
    if (e.get("who") == "target" or str(e.get("who")).startswith("ref:")) and (named := _players(plan, ctx, e["who"])):
        pid = named[0]
    n = _amount(plan, ctx, e["n"])
    if where == "graveyard" and n > 0:  # -- static permanents (wave 100D) -- Enhanced Surveillance
        from app.rules import static_perm100d

        n += 2 * static_perm100d.yours(plan, static_perm100d.MORE_SURVEIL, pid)
    if where == "bottom" and n > 0 and (replaced := replace.keyword_replace(plan, ctx, e, "scry", pid, n=n)) is not None:
        return replaced  # -- keyword actions (wave 35C) -- "If you would scry a number of cards, draw that many cards instead." (Eligeth)
    top = plan.state.zones.get(zone_key(pid, "library"), [])[:n]
    if n > 0:  # -- this-turn history (wave 4D) -- 701.22b/d, 701.25c/d: N > 0 scries / surveils, even an empty library
        from app.rules import history

        history.note_look(plan, pid, "scry" if where == "bottom" else "surveil", len(top))
    if not top:
        if e.get('as_kept'):
            ctx.setdefault('surveil_kept', {})[e['as_kept']] = 0
        return True
    options = [DecisionOption(id=cid, label=plan.state.cards[cid].name or "Card", card_id=cid) for cid in top]
    verb = "Scry" if where == "bottom" else "Surveil"
    dest = "the bottom of your library" if where == "bottom" else "your graveyard"
    decide(plan, player=pid, kind="choose_cards", prompt=f"{verb} {len(top)}: choose the cards to put into {dest} (the rest stay on top)",
           options=options, min_choices=0, max_choices=len(top),
           resume={"step": "look", "where": where, "cards": list(top), "ctx": ctx,
                   'looked_objects': {c: plan.oid(plan.state.cards[c]) for c in top}, **({'as_kept': e['as_kept']} if e.get('as_kept') else {})})
    return False


def create_token(plan: Plan, ctx: Context, e: dict[str, Any], *, then: dict[str, Any] | None = None) -> bool:
    """111: tokens are individual objects for the rules; identical ones may be *shown* as a pile.
    -- replacement effects stage 2 (wave 2E) -- Through the token choke point (app/rules/replace.py:
    614.16, 616.1 per creating player in APNAP order). ``then``: how a caller other than the
    resolver goes on after a paused choice (the resolver itself: its effects continue)."""
    if e.get('investigate78'):
        from app.rules import first_event_receipts78

        return first_event_receipts78.investigate(plan, ctx, e)
    t = e["token"]
    # -- static spells (wave 100C) -- "Each player creates a … token for each untapped Forest they control": each player's own count, all
    # determined before any token is created (608.2h), one creation batch (616.1 APNAP)
    per100c = {p: max(0, _amount(plan, {**ctx, "recipient": p}, e["n"])) for p in _players(plan, ctx, e["who"])} \
        if sized_damage.has_per_player(e["n"]) and not e.get("more") and not e.get("per_controller") else None
    count = _amount(plan, ctx, e["n"]) if per100c is None else max(per100c.values(), default=0)
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
    if e.get("per_player"):  # -- if you do (wave 100B) -- "each player creates a number of … equal to the amount of mana they paid this way" (Liege of the Hollows)
        each = {p: int(n) for p, n in e["per_player"].items()}
    # -- triggers (wave 5D) -- "create a 3/3 … token with deathtouch and a 3/3 … token with lifelink" (Wurmcoil Engine):
    # one instruction, so one batch of tokens entering together (701.7a, 603.2c)
    creation_atoms: list[str] | None = [] if each is not None else None
    kinds = [(t, count, e.get("tapped"))] + [(m["token"], _amount(plan, ctx, m["n"]), m.get("tapped"))
                                             for m in e.get("more") or []]
    for t, count, tapped_by_creator in kinds:
        if count <= 0:
            continue
        if t.get("chosen"):  # -- chosen filters (wave 53B) -- "of the chosen color and type": what its source chose as it entered
            from app.rules import chosen as _chosen

            if (t := _chosen.chosen_token(plan, source, t)) is None:
                plan.note(f"{ctx.get('name') or 'The source'} has no color and creature type chosen: no token is created")
                continue
        # -- X sized by a count (wave 4K) -- "an X/X … token": X as the token is created, its printed P/T from then on (111.3)
        pt = {k: str(values.evaluate(plan, ctx, t[k])) if isinstance(t.get(k), dict) else t.get(k) for k in ("power", "toughness")}
        for pid in (list(each) if each is not None else _players(plan, ctx, e["who"])):
            if each is not None and pid not in plan.live():
                continue
            spec = {"name": t["name"], "power": pt["power"], "toughness": pt["toughness"],
                    "colors": t.get("colors") or [], "type_line": t["type_line"], "text": t.get("text") or "",
                    **({"mana_cost": t["mana_cost"]} if t.get("mana_cost") else {})}  # (wave 49D: 111.3)
            # a token enters tapped when its creator says so ("create a tapped …") or its own text does
            # (614.1d), never otherwise; its "enters with" counters follow (app/rules/replacements.py)
            tapped = (bool(tapped_by_creator) or replacements.token_enters_tapped(plan, pid, spec)) and not replacements.token_enters_untapped(plan, pid, spec)  # (wave 45A)
            spec['_effect_tapped'] = bool(tapped_by_creator)
            if each is not None:
                # Explicit "for each [destroyed object], its controller creates":
                # separate actions, performed in the same simultaneous batch.
                # A generic "create N tokens" remains one creation instruction.
                for iteration in range(each[pid]):
                    requests.append((pid, spec, count, source, tapped))
                    assert creation_atoms is not None
                    creation_atoms.append("controller:" + pid + ":" + str(iteration))
            elif per100c is not None:  # -- static spells (wave 100C) --
                if per100c.get(pid, 0) > 0:
                    requests.append((pid, spec, per100c[pid], source, tapped))
            else:
                requests.append((pid, spec, count, source, tapped))
    # (the tokens are recorded as binding "as", the new objects they are: "they gain haste")
    if not requests:  # (every kind counted 0)
        _remember(plan, ctx, e, [])
        return True
    made = replace.create_token_batch(plan, requests, ctx=ctx, bind=e.get("as"), then=then or _then(ctx, e),
                                      creation_atoms=creation_atoms)
    return made is not None  # (None: the creating player chooses an order first, 616.1)


def add_counters(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    # -- replacement effects stage 2 (wave 2E): through the counter choke point (122.6, 614.16) --
    stat = e["n"].get("recipient_stat") if isinstance(e["n"], dict) else None
    recipient_ctx = ctx
    if stat and (source := ctx.get("source_card")) and plan.oid(source) != ctx.get("source_object"):
        # "Other" excludes the original object, not a new incarnation after a blink.
        recipient_ctx = {**ctx, "source_card": None}
    cards = _cards(plan, recipient_ctx, e["who"])
    if e.get("exclude"):
        cards = [cid for cid in cards if cid not in context.objects(plan, ctx, e["exclude"])]
    _remember(plan, ctx, e, cards)
    shares = divided(ctx, e)
    if shares is not None:  # "distribute N counters among …" (601.2d): each target its share
        puts = [(cid, e["kind"], shares[cid]) for cid in cards if shares.get(cid)]
    else:
        # -- triggers (wave 30J) -- "put a +1/+1 counter on it for each other Zombie that entered the battlefield under your control this turn"
        # (Geralf): "other" is than IT, the object the counters go on, not than the ability's source
        counted = e["who"] == "event" and len(cards) == 1 and isinstance(e["n"], dict) and "count" in e["n"]
        n = 0 if stat else _amount(plan, {**ctx, "other_than": cards[0]} if counted else ctx, e["n"])
        if stat == "power_above_base":
            puts = [(cid, e["kind"], pt[0] - ch.base_pt[0]) for cid in cards
                    if (ch := plan.ch(plan.state.cards[cid])).base_pt is not None
                    and (pt := ch.pt) is not None and pt[0] > ch.base_pt[0]]
        elif stat in ("power", "toughness"):
            # Determine every amount before putting any counters: one simultaneous instruction.
            index = 0 if stat == "power" else 1
            puts = [(cid, e["kind"], max(0, pt[index])) for cid in cards
                    if (pt := plan.ch(plan.state.cards[cid]).pt) is not None and pt[index] > 0]
        elif isinstance(e["n"], dict) and e["n"].get("colors") == e["who"] and len(cards) > 1:  # (wave 45D) "equal to the number of colors it is": each one's own
            puts = [(cid, e["kind"], k) for cid in cards if (k := len(plan.ch(plan.state.cards[cid]).colors))]
        else:
            puts = [(cid, e["kind"], n) for cid in cards] if n else []
        for more in e.get("also") or ():  # -- counters (wave 5H) -- several kinds at once (one event, 122.6)
            k = _amount(plan, ctx, more["n"])
            more_cards = _cards(plan, ctx, more["who"]) if more.get("who") else cards
            puts += [(cid, more["kind"], k) for cid in more_cards] if k else []
    if not puts:
        if e.get('receipt'):
            from app.rules import counter_receipts

            counter_receipts.store(ctx, e['receipt'], [])
        return True
    putters = _players(plan, ctx, e["by"]) if e.get("by") else [ctx["controller"]]
    return replace.put_counters(plan, puts, by=putters[0], then=_then(ctx, e), ctx=ctx,
                                receipt_bind=e.get('receipt')) if len(putters) == 1 else True


def remove_counters(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Remove N … counters from …" (as many as there are, 122.8)."""
    from app.rules import counter_removal_results

    n = _amount(plan, ctx, e["n"])
    cards = _cards(plan, ctx, e["who"])
    _remember(plan, ctx, e, cards)
    removed = 0
    for cid in cards:
        if e["kind"] == "*":  # -- attached events (wave 25D) -- "remove all counters from it": every kind it has
            for kind, have in sorted(plan.state.cards[cid].counters.items()):
                if have > 0 and n:
                    removed += counter_removal_results.remove(plan, cid, kind, min(have, n), by=ctx['controller'])
            continue
        have = plan.state.cards[cid].counters.get(e["kind"], 0)
        if have and n:
            removed += counter_removal_results.remove(plan, cid, e['kind'], min(have, n), by=ctx['controller'])
    if e.get("bind"):  # -- if you do (wave 52A) -- "Add {C} for each charge counter removed this way": the counters it actually removed (counters_removed.py)
        context.bind_amount(ctx, e["bind"], removed)
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
    if (replaced := replace.keyword_replace(plan, ctx, e, "proliferate", ctx["controller"])) is not None:
        return replaced  # -- keyword actions (wave 50F) -- 614.1a: "If you would proliferate, proliferate twice instead." (Tekuthal, Inquiry Dominus)
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
    from app.rules import proliferate_followup

    then = proliferate_followup.continuation(ctx, plan.rules.batch)
    if puts and not replace.put_counters(plan, puts, by=d.player, then=then):
        return  # an order to choose first (616.1)
    replace.run_then(plan, then)


def regenerate(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.19: "Regenerate ~" / "Regenerate target creature": a shield for this turn."""
    cards = _cards(plan, ctx, e["who"])
    _remember(plan, ctx, e, cards)
    for cid in cards:
        regeneration.add_shield(plan, cid)
        if e.get("regeneration_rider"):
            from app.rules import regeneration_riders

            regeneration_riders.capture(plan, ctx, e, cid)
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
                emit(plan.state, "crewed", object_id=plan.oid(c), card=c, player=plan.state.cards[c].controller, crew_count80=e.get("crew_count80"))
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
        _return_yours_to_hands(plan, ctx, e, pool, pid)
        return True
    decide(plan, player=pid, kind="choose_cards", prompt=f"Return {n} {e['what']}{'s' if n != 1 else ''} you control to hand",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in pool],
           min_choices=n, max_choices=n, resume={"step": "return_yours", "ctx": ctx, "e": e})
    return False


def _return_yours_to_hands(plan: Plan, ctx: Context, e: dict[str, Any], ids: list[str], actor: str) -> None:
    """-- if you do (wave 52A) -- what it returned is bound ("If another Desert was returned this way", Arid Archway): the permanents as they were (608.2h)."""
    before = _remember(plan, ctx, e, ids)
    _return_to_hands(plan, ids, actor)
    _moved(plan, ctx, e, before)


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
    _return_yours_to_hands(plan, d.resume["ctx"], d.resume.get("e") or {}, chosen, d.player)
    continue_effects(plan, d.resume["ctx"])


def suspend_tick(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.62b-d: remove a time counter; when the last is removed, its owner may cast it without
    paying its mana cost."""
    cid = e["card"]
    card = plan.state.cards.get(cid)
    from app.rules import suspend_grants

    if card is None or not suspend_grants.is_suspended(plan, card) or plan.oid(card) != ctx.get("source_object"):
        return True
    if card.counters.get("time", 0) > 0:
        plan.do({"type": "counter", "card_ids": [cid], "kind": "time", "delta": -1}, actor=card.owner)
    # Counter events from the native diff create the independent last-counter trigger (702.62c),
    # including removals by other effects. Do not emit a second event or cast within this trigger.
    return True


def suspend_cast(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.62a: "When the last time counter is removed from this card, if it's exiled, you may play it without paying its mana cost if able."""
    card = plan.state.cards.get(e["card"])
    if card is None or not card.zone.endswith(":exile") or (e.get("object") and plan.oid(card) != e["object"]):
        return True  # (the intervening "if it's exiled": it isn't any more)
    # -- granted casts (wave 29B) -- any half / face (709.3, 712.11b, 715.3)
    from app.rules import granted_casts

    return granted_casts.ask(plan, ctx, player=card.owner, cid=card.id, head="The last time counter was removed", no="Leave it exiled", play=True)


def leave_uncast(plan: Plan, player: str, cid: str, how: str | None, group: Any = ()) -> None:
    """The card the engine offered to cast isn't cast (declined, or nothing can be cast: granted_casts.ask): the grant ends and ``how`` says where it
    goes -- "bottom" (cascade), "ripple" (stays with the revealed cards, which the ability puts on the bottom in one order), "hand" (discover, 701.57a), "graveyard" (madness), "miracle" (stays in the hand), else it stays exiled.
    ``group``: the cards put on the bottom before the question (cascade)."""
    r = plan.rules
    r.free_casts = [c for c in r.free_casts if c != cid]
    r.free_cast_faces.pop(cid, None)
    r.alt_costs.pop(cid, None)
    if how == "ripple":  # -- free-cast cleanup (wave 30A) -- 702.60a: it stays on top with the revealed cards, which the ability goes on to put on the bottom
        return
    if how == "miracle":  # -- casting extras (wave 18E) -- 702.94a: it stays in the hand (and is hidden again)
        from app.rules import miracle

        miracle.done(plan, cid)
        plan.note(f"{plan.name(player)} keeps it in their hand")
        return
    if how == "graveyard" and cid in plan.state.cards:  # madness
        from app.rules import discarded_references

        old_object = discarded_references.begin(plan, cid)
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "graveyard"}}, actor=player)
        discarded_references.finish_attempt(plan, old_object)
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
    if d.resume.get("object") is not None and (card is None or plan.oid(card) != d.resume["object"] or not card.zone.endswith(":exile")):
        r.free_casts = [c for c in r.free_casts if c != cid]
        r.free_cast_faces.pop(cid, None)
        finish(plan, d.resume["ctx"])
        return
    if answer == "yes" and card is not None and chars.as_cast(card, plan.info, face).is_land:
        # 702.62a: a suspended card is *played* ("you may play it without paying its mana cost"): a land face (712.12) is played as the ability resolves
        r.free_casts = [c for c in r.free_casts if c != cid]
        if land_plays.open_for_effect(plan.state, d.player, plan.info):  # (review 29B: 305.2b / 305.3, an older save's plain "yes" wasn't checked)
            permissions.play_land_now(plan, d.resume["ctx"], {"n": 1}, cid, face)
            return
        plan.note(f"{plan.name(d.player)} can't play a land now (305.2b, 305.3)", actor=d.player)
        answer = "no"
    ripple = d.resume.get("decline") == "ripple"  # -- free-cast cleanup (wave 30A) -- 702.60a: the ability isn't over, it puts the rest on the bottom
    continuing = ripple or bool(d.resume.get("continue_resolution"))
    if not continuing:
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
        if continuing:
            continue_effects(plan, d.resume["ctx"])
        return
    if face:
        r.free_cast_faces[cid] = face  # casting.cast_free takes only this one
    if r.decision is not None:
        plan.note("Cast it without paying its mana cost when the pending choice is done")
        return
    if r.free_cast_then is None:  # (review 29B) a cast abandoned on the way (its payment cancelled: 601.2, nothing was paid) is a card not cast:
        # it goes where the declined card goes (permissions.free_cast_abandoned), never left in exile with its grant
        r.free_cast_then = {"card": cid, "ctx": None, "e": {},
                            "suspend_object": d.resume["ctx"].get("source_object") if any(
                                part.get("do") == "suspend_cast" and part.get("card") == cid
                                for part in d.resume["ctx"].get("effects", [])) else None, **({"object": d.resume["object"]} if d.resume.get("object") else {}), **({"face": face} if face else {}),
                            "granted": {"player": d.player, "decline": d.resume.get("decline"), "group": list(d.resume.get("group") or ()),
                                **({"ctx": d.resume["ctx"]} if continuing else {})}}  # (ctx: permissions.free_cast_done goes on with the ability)
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
        # Same-library moves retain reveals; randomized positions must become private.
        plan.do({"type": "hide", "card_ids": order[at:at + 250]}, actor=actor or pid)
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
    from app.rules import wave110a_averna

    if wave110a_averna.ask(plan, ctx, e, missed, hit):  # -- Averna (wave 110A) -- "As you cascade, you may put a land card from among the exiled cards onto the battlefield tapped"
        return False
    return cascade_end(plan, ctx, e["mv"], missed, hit)


def cascade_end(plan: Plan, ctx: Context, mv: int, missed: list[str], hit: str | None) -> bool:
    pid = ctx["controller"]
    order = bottom_at_random(plan, pid, missed)
    if hit is None:
        plan.note("Cascade found nothing")
        return True
    # -- granted casts (wave 29B) -- "if the resulting spell's mana value is less" (702.85a): each half / face
    from app.rules import granted_casts

    return granted_casts.ask(plan, ctx, player=pid, cid=hit, head="Cascade", no="Put it on the bottom", decline="bottom", below=mv,
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
        if e.get("by_now"):  # -- flash auras (wave 46B) -- whoever controls the permanent then sacrifices it
            _sacrifice_cards(plan, [card.id], card.controller)
        elif card.controller == ctx["controller"]:
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
    if card is None or not card.zone.endswith(":exile") or (e.get("object") is not None and plan.oid(card) != e["object"]):
        return True
    from app.rules import granted_casts  # -- granted casts (wave 29B) --

    return granted_casts.ask(plan, ctx, player=ctx["controller"], cid=cid, head="Rebound", no="Leave it exiled", object_id=e.get("object"))


def madness_offer(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.35a: "When this card is exiled this way, its owner may cast it by paying [cost] rather
    than its mana cost. If that player doesn't, they put this card into their graveyard." """
    cid = e["card"]
    card = plan.state.cards.get(cid)
    if card is None or not card.zone.endswith(":exile") or cid not in plan.rules.free_casts:
        return True
    from app.rules import madness_costs

    options = [DecisionOption(id="no", label="Put it into your graveyard")]
    if madness_costs.problem(plan, card, e["cost"]) is None:
        options.insert(0, DecisionOption(id="yes", label=f"Cast it for {e['cost']}"))
    decide(plan, player=card.owner, kind="choose_one", prompt=f"Madness: cast {card.name} for {e['cost']}?",
           options=options,
           resume={"step": "suspend_cast", "ctx": ctx, "card": cid, "decline": "graveyard"}, source=card)
    return False


def counterable(plan: Plan, stack_id: str) -> bool:
    """The same native legality predicate for announcement and committed countering."""
    card = plan.state.cards.get(stack_id)
    if card is None or card.zone != "stack":
        return False
    from app.rules import permissions, scripts

    return not (permissions.abilities_uncounterable(plan.state, plan.info) if card.ability is not None
                else scripts.uncounterable(plan.ch(card)) or _mana_units.uncounterable(plan, card)
                or permissions.spell_uncounterable(plan.state, plan.info, card, plan.ch(card)))


def counter_object(plan: Plan, stack_id: str, actor: str, to: str | None = None, *, exile: bool = False,
                   by: str | None = None, types: list[str] | None = None, source: str | None = None) -> None:
    """701.6: a countered spell goes to its owner's graveyard (a flashback spell into exile); a
    countered ability simply stops existing. ``exile``: "If that spell is countered this way, exile
    it instead of putting it into its owner's graveyard" (608.2c; wave 4C).
    -- "this way" outcomes (wave 4A) -- ``to``: "exile it / put it on top of / on the bottom of its owner's
    library instead of into that player's graveyard" (608.2c: the counter's own destination; a flashback spell
    is still exiled, 702.34a: that replacement applies to the spell leaving the stack whatever its destination)."""
    card = plan.state.cards.get(stack_id)
    if card is None or card.zone != "stack":
        return
    from app.rules import wave110b_cards

    if not counterable(plan, stack_id) or source and wave110b_cards.shielded(plan, card, source):  # (-- Autumn's Veil (wave 110B) --)
        plan.note(f"{card.name} can't be countered", [stack_id])
        return
    r = plan.rules
    remember_stack(plan.state, stack_id)  # -- spell copies (wave 31D) -- a copy of it can still be made (608.2h, 707.10)
    entry = r.stack.pop(stack_id, None)
    oid = plan.oid(stack_id)
    if card.ability is None and (entry is None or entry.copy_of is None):  # -- spell countered (wave 110B) -- 701.6a, 707.10: a cast spell (not a copy) was countered; its caster is told
        from app.game.rules_state import emit

        emit(plan.state, "designation", counter="spell_countered110b", player=card.controller)
    r.buyback = [o for o in r.buyback if o != oid]
    r.rebound_cast = [o for o in r.rebound_cast if o != oid]
    r.exile_resolves.pop(oid, None)  # -- cast riders (wave 38C) -- a countered spell doesn't resolve (701.6a): "as it resolves" never applies to it
    plan.note(f"{card.name or 'It'} is countered", [stack_id])
    if card.ability is None and by is not None:  # -- counter events (wave 19C) -- "Whenever a spell or ability you control counters a spell":
        from app.game.rules_state import (
            emit,  # ``by`` is the controller of the spell or ability that countered it (701.6a)
        )

        emit(plan.state, "designation", counter="counters_spell", player=by)
        from app.rules import wave110c_history  # -- turn history (wave 110C) -- Summoning Trap

        wave110c_history.note_countered(plan, card, by)
    if oid in r.flashback or exile:
        r.flashback = [o for o in r.flashback if o != oid]
        plan.do({"type": "move", "card_ids": [stack_id], "to": {"player": card.owner, "zone": "exile"}}, actor=actor)
    elif to == "exile" and (not types or any(t in plan.ch(card).types for t in types)):  # (wave 4A; 110I: "if a permanent spell is countered this way")
        plan.do({"type": "move", "card_ids": [stack_id], "to": {"player": card.owner, "zone": "exile"}}, actor=actor)
    elif to == "battlefield_you" and by is not None and types and any(t in plan.ch(card).types for t in types):
        # -- counter outcomes (wave 110C) -- Desertion: an artifact or creature spell is put onto the battlefield under the counterer's control (608.2c, 701.6a)
        plan.do({"type": "move", "card_ids": [stack_id], "to": {"player": by, "zone": "battlefield"}}, actor=actor)
    elif to == "hand":  # -- zone replacements (wave 37B) -- "put it into its owner's hand instead of into that player's graveyard" (Remand)
        plan.do({"type": "move", "card_ids": [stack_id], "to": {"player": card.owner, "zone": "hand"}}, actor=actor)
    elif to in ("top", "bottom"):  # (wave 4A)
        plan.do({"type": "move", "card_ids": [stack_id], "to": {"player": card.owner, "zone": "library"}, "position": to},
                actor=actor)
    else:
        plan.do({"type": "move", "card_ids": [stack_id], "to": {"player": card.owner, "zone": "graveyard"}}, actor=actor)


def _stack_targets(plan: Plan, ctx: Context, e: dict[str, Any]) -> list[str]:
    if e.get("object"):
        return [e["object"]] if e["object"] in plan.state.cards and plan.state.cards[e["object"]].zone == "stack" and (e.get("object_oid") is None or plan.oid(e["object"]) == e["object_oid"]) else []
    if e.get("who") == "event_spell":  # -- unless pays (wave 4C) -- a cast trigger's spell, while it's still that object (400.7)
        return [c for c in context.objects(plan, ctx, context.EVENT) if plan.state.cards[c].zone == "stack"]
    if e.get("who") == "each_opponent_spell":  # -- cast keywords (wave 43D) -- "Counter each spell you don't control." (an overloaded Counterflux): spells only (not abilities)
        return [c for c in plan.state.zones.get("stack", []) if c != ctx.get("stack_id") and plan.state.cards[c].ability is None
                and plan.state.cards[c].controller != ctx["controller"]]
    if e.get("who") == "opponent_abilities110b":  # -- face-down X (wave 110B) -- "counter all abilities your opponents control" (701.6a): every activated or triggered ability on the stack they control
        return [c for c in plan.state.zones.get("stack", []) if plan.state.cards[c].ability is not None and plan.state.cards[c].controller != ctx["controller"]]
    if e.get("who") in ("all_other_spells100c", "all_abilities100c"):  # -- static spells (wave 100C) -- "Counter all other spells." / "counter all abilities"
        spells = e["who"] == "all_other_spells100c"
        return [c for c in plan.state.zones.get("stack", []) if c != ctx.get("stack_id") and (plan.state.cards[c].ability is None) == spells]
    if e.get("who") == "event_source":  # -- unless pays (wave 20E) -- the spell or ability a "becomes the target" event names, while still that object
        ref = (ctx.get("event") or {}).get("source")
        card = context._same(plan, ObjectRef.model_validate(ref)) if ref else None
        return [card.id] if card is not None and card.zone == "stack" else []
    return [t["id"] for t in target_refs(ctx, e.get("who") or "target") if t["id"] in plan.state.cards
            and plan.state.cards[t["id"]].zone == "stack" and plan.oid(t["id"]) == t.get("object_id")]


def paid_sacrifice_effect(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import paid_sacrifice_effects

    return paid_sacrifice_effects.run(plan, ctx, e)


def conditional_counter(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import conditional_counters

    return conditional_counters.run(plan, ctx, e)


def capture_spell_payment(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import spell_payment_facts

    return spell_payment_facts.capture(plan,ctx,e)


def counter(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    sids = _stack_targets(plan, ctx, e)
    if e.get("to") == "choice_you":
        from app.rules import counter_destinations

        if not counter_destinations.offer(plan, ctx, e, sids):
            return False
    before = _remember(plan, ctx, e, sids)  # -- stack interaction (wave 5B) -- "its controller": 608.2h
    perms = _ability_sources(plan, sids, e) if e.get("perm_as") else {}
    for sid in sids:
        counter_object(plan, sid, ctx["controller"], e.get("to"), exile=bool(e.get("exile")), by=ctx["controller"], types=e.get("types"), source=ctx.get("source_card"))  # (exile: 4C; to: 4A)
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
    from app.rules import casting, reveal_mana  # casting imports this module

    if not cost.is_free and not casting.can_pay(plan.state, payer, cost, plan.info) and not reveal_mana.available(plan, payer):
        plan.note(f"{plan.name(payer)} can't pay {cost.text()}")
        counter_object(plan, sid, payer, by=ctx["controller"], source=ctx.get("source_card"))
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


def explore_each(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """-- trigger other (wave 50G) -- 701.44a: "each Merfolk creature you control explores" (Hakbal of the Surging Soul): each explores in turn, in the order its controller
    chooses (the 2023-11-10 ruling), nothing in between. ``rest``: the object ids still to explore; their controller (the effect's) is asked while two or more are left."""
    ids = e.get("rest")
    if ids is None:
        ids = [plan.oid(plan.state.cards[c]) for c in _cards(plan, ctx, e["who"])]
    if len(ids) > 1:
        decide(plan, player=ctx["controller"], kind="choose_one", prompt="Choose the creature that explores next",
               options=[DecisionOption(id=o, label=plan.state.cards[o.rsplit(".", 1)[0]].name or "Creature", card_id=o.rsplit(".", 1)[0]) for o in ids],
               resume={"step": "explore_each", "ctx": ctx, "rest": ids}, source=plan.state.cards.get(ctx.get("source_card") or ""))
        return False
    _explore_order(ctx, ids, [])
    return True


def _explore_order(ctx: Context, first: list[str], rest: list[str]) -> None:
    i = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:i], *({"do": "explore", "who": f"obj:{o}"} for o in first),
                      *([{"do": "explore_each", "rest": rest}] if rest else []), *ctx["effects"][i:]]


def resume_explore_each(plan: Plan, d: Any, chosen: list[str]) -> None:
    _explore_order(d.resume["ctx"], chosen, [o for o in d.resume["rest"] if o != chosen[0]])
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
    from app.rules import prepared_mill61

    return prepared_mill61.run(plan, ctx, e)


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
    cards = _prohibitions.trigger_token_shield(plan, ctx, cards)  # -- prohibitions (wave 110A) --
    before = _remember(plan, ctx, e, cards)
    if cards:
        on_bf = [c for c in cards if plan.state.cards[c].zone.endswith(":battlefield")]
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "exile"}}, actor=ctx["controller"])
        _wave110i_cards.note_exiled(plan, ctx, on_bf)  # -- cards (wave 110I) --
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
            entries.append({"card": cid, "player": card.owner, "actor": card.owner, **({"to": back} if back in ("hand", "graveyard") else {})})  # (back: wave 110G, Idol of Endurance, the graveyard)
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
    from app.rules import regeneration_choices

    if not regeneration_choices.prepare(plan, doomed, can_regenerate=_can_regenerate(ctx), ctx=ctx):
        return False
    doomed = regeneration.survivors(plan, doomed, can_regenerate=_can_regenerate(ctx), actor=ctx["controller"])
    before = _remember(plan, ctx, e, doomed)  # "creatures destroyed this way": the ones it destroys
    if doomed:
        gone = {c: plan.oid(c) for c in doomed}
        plan.do({"type": "move", "card_ids": doomed, "to": {"zone": "graveyard"}}, actor=ctx["controller"])
        _destroyed(plan, gone, ctx["controller"])
    _moved(plan, ctx, e, before)
    regeneration_choices.finish(plan)
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
    keys = e.get("alts") or [key]
    sels = [selectors.from_key(k) for k in keys]
    current = {c: plan.ch(plan.state.cards[c]) for c in among}
    matching = [c for c in among if any(selectors.matches(plan, sel, plan.state.cards[c], current[c], pid,
                                                          ctx.get("source_card") if sel.extras else None)  # (wave 47D: "not named ~", the searching ability's source)
                                        for sel in sels)]
    if keywords := e.get('controller_tutor_keyword_any'):
        matching = [c for c in matching if set(keywords) & current[c].keywords]
    # -- tutors (wave 3T) -- "a card named …" and "with mana value X or less" (the X chosen for this
    # spell or ability; a card in a library has its X as 0, 202.3e)
    if e.get("name"):
        src = plan.state.cards.get(ctx.get("source_card") or "")
        name = (src.name if src is not None else "") if e["name"] == "~" else e["name"]
        from app.rules import card_names

        matching = [c for c in matching if card_names.has_name(current[c], name)]
    if 'name_in' in e:
        from app.rules import card_names

        matching = [c for c in matching if any(card_names.has_name(current[c], n) for n in e['name_in'])]
    if e.get("name_as") is not None:  # -- tutor (wave 26D) -- "a card with the same name as that creature" (app/rules/same_name.py)
        from app.rules import same_name

        wanted = same_name.names(plan, ctx, e["name_as"])
        from app.rules import card_names

        matching = [c for c in matching if any(card_names.has_name(current[c], n) for n in wanted)]
    if e.get("mv"):
        op, value = e["mv"][0], (e["mv"][1] if e["mv"][0] == "in" else _amount(plan, ctx, e["mv"][1]))
        mvs = {c: current[c].mana_value for c in matching}
        matching = [c for c in matching if (mvs[c] <= value if op == "<=" else mvs[c] < value if op == "<"  # ("<": wave 4M)
                                            else mvs[c] in e["mv"][1] if op == "in" else mvs[c] == value)]  # ("in": wave 20D, "4 or 5")
    if e.get("relative_tutor"):
        from app.rules import qualified_attached_tutors

        matching = [c for c in matching if qualified_attached_tutors.matches(plan, ctx, e, c)]
    return matching


def search(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """A tutor. The server filters the library; only the searching player gets the matching cards
    in their private decision (nobody else learns the library's contents)."""
    pid = ctx["controller"]
    if e.get("who") in ("each_opponent", "each_player") or e.get("each_target"):  # -- other players' choices (wave 12D) -- "Each opponent may search their
        # library for …": one search per player, the active player first (101.4). A library is hidden, so each search is its
        # player's private choice; the cards they put onto the battlefield enter as each search ends (a corner of 101.4's
        # "actions happen simultaneously" that only an entering permanent watching the others entering could notice)
        order = [p for p in plan.apnap() if p in _players(plan, ctx, e["who"])]
        at = ctx["next"]
        ctx["effects"] = [*ctx["effects"][:at], *({**e, "who": f"player:{p}", "each_target": False} for p in order), *ctx["effects"][at:]]
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
    from app.rules import qualified_search_packets

    slot = qualified_search_packets.slot(e, part)
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
    if zones:
        ctx["search_performed"] = True
    depth = prohibitions.search_depth(plan, pid)  # (wave 43B: Aven Mindcensor: only the top four cards of any library are searched)
    library = [c for c in plan.state.zones.get(zone_key(owner, "library"), [])[:depth] if c not in picked] if "library" in zones else []
    search_group = qualified_search_packets.group_frame(plan, ctx, e, pid, owner, library) if "library" in zones else None
    if search_group is not None:
        library = qualified_search_packets.group_library(plan, search_group, picked)
    if part == 0 and not picked and "library" in zones and (search_group is None or not search_group['noted']):
        prohibitions.note_search(plan, pid, owner)  # -- most-played cards (wave 43B) -- "Whenever an opponent searches their library"
        if search_group is not None:
            search_group['noted'] = True
    if e.get("sel"):  # a structured card selector (app/rules/selectors.py)
        matching = _search_matches(plan, ctx, slot, owner, slot["sel"], library)
        if "graveyard" in zones:  # (wave 3R4) the graveyard's cards are public (404.2): the same test, read there
            graveyard = [c for c in plan.state.zones.get(zone_key(pid, "graveyard"), []) if c not in picked]
            keys = [selectors.replace(selectors.from_key(k), zones=("graveyard",)).key() for k in (slot.get("alts") or [slot["sel"]])]
            matching += _search_matches(plan, ctx, {**slot, "alts": keys}, pid, None, graveyard)
        if "hand" in zones:  # -- if you do (wave 15C) -- the searcher's own hand: private to them, as is this decision
            hand = [c for c in plan.state.zones.get(zone_key(pid, "hand"), []) if c not in picked]
            keys = [selectors.replace(selectors.from_key(k), zones=("hand",)).key() for k in (slot.get("alts") or [slot["sel"]])]
            matching += _search_matches(plan, ctx, {**slot, "alts": keys}, pid, None, hand)
        what =e.get("label") or "cards"
    else:
        matching = [c for c in library if _matches(plan, c, e["filter"])]
        what = e["filter"].replace("_", " ")
    most = 1 if e.get("parts") else _amount(plan, ctx, e.get("max", 1))
    options = [DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in matching]
    # 701.23b: a search for cards with a stated quality may find fewer (or none); 701.23d: a search
    # simply for a quantity of cards ("a card") must find that many, or as many as there are.
    # ("Up to N cards" may find fewer: only a single "a card" or an explicit ``upto: False`` forces.)
    quantity_only = (e.get("filter") == "any" or (e.get("sel") is not None and e.get("label") in ("card", "cards"))) and "name_in" not in slot
    forced = quantity_only and not e.get("upto", e.get("label") == "cards")
    if e.get('qualified_packet') and not {'library', 'hand'}.intersection(zones) and not e.get('upto'):
        forced = True  # A search entirely in public zones must find the specified quantity if available.
    whose = f"{plan.name(owner)}'s" if owner != pid else "your"
    decide(plan, player=pid, kind="choose_cards", prompt=f"Search {whose} {' and '.join(zones)} ({what})",
           options=options, min_choices=min(most, len(options)) if forced else 0, max_choices=min(most, len(options)),
           decider=search_group["decider"] if search_group is not None else _player_control.search_controller(plan, pid) if "library" in zones and owner == pid else None,  # (-- wave 18H -- 723.2: Opposition Agent; review 26A: only while they search their own library)
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
    to_if = e.get("to_if")  # -- most-played modal spells (wave 50I) -- "Put it onto the battlefield tapped if it's a land card. Otherwise, put it into your hand." (Archdruid's Charm)
    from app.rules import characteristics as chars

    _finish_search(plan, ctx, e, d.player, list(chosen),
                   {c: to_if["to"] if to_if is not None and selectors.matches(plan, selectors.from_key(to_if["sel"]), plan.state.cards[c],
                                                                              chars.of(plan.state.cards[c], plan.info), d.player, None) else e["to"]
                    for c in chosen})


def resume_search_split(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e, found = d.resume["ctx"], d.resume["e"], d.resume["found"]
    _finish_search(plan, ctx, e, d.player, found, {c: e["to"] if c in chosen else e["to2"] for c in found})


def _exile_search_finds(plan: Plan, pid: str, owner: str, cards: list[str], agents: list[Any]) -> None:
    """Apply Opposition Agent's found-card replacement before later instructions."""
    for cid in cards:
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": owner, "zone": "exile"}}, actor=pid)
    _player_control.permit_exiled(plan, agents, cards)


def _finish_search(plan: Plan, ctx: Context, e: dict[str, Any], pid: str, chosen: list[str], dest: dict[str, str]) -> None:
    from app.rules import attachments  # attachments → effects (resume)

    entering = []
    owner = e.get("lib_pid", pid)  # (wave 26A: a target player's library: the cards found are theirs; they enter under the searcher's control)
    found = _remember(plan, ctx, e, chosen)  # (library objects: a hidden zone, so nothing is read from them)
    # -- controlling another player (wave 18H) -- Opposition Agent: "they exile each card they find" (701.23): a card found in the
    # library is exiled and nothing else the instruction says about it happens (it is a new object, 400.7); the Agent's
    # controller may play it for as long as it remains exiled, spending mana as though it were any color
    grouped_library = any(f.get("group") == e.get("search_event_group") and f.get("owner") == owner for f in ctx.get("search_event_groups", [])) if e.get("search_event_group") else False
    agents = _player_control.search_exile(plan, pid) if ("library" in (e.get("zones") or ["library"]) or grouped_library) and owner == pid else []  # (review 26A: "their library")
    exiled = list(chosen) if agents else []
    dest = {**dest, **{c: "exile" for c in exiled}}
    if e.get("reveal"):
        for cid in chosen:
            if cid not in exiled:
                plan.do({"type": "reveal", "card_ids": [cid]}, actor=pid)  # to everyone
    _exile_search_finds(plan, pid, owner, exiled, agents)
    if e.get('outcome') or e.get('destination_choice'):
        from app.rules import conditional_tutor_outcomes

        conditional_tutor_outcomes.note_result(plan, ctx, e, chosen, exiled)
        if conditional_tutor_outcomes.offer_destination(plan, ctx, e, pid, chosen, dest):
            return
    if e.get('source_to_if'):
        from app.rules import conditional_search_destination

        dest = conditional_search_destination.destination_map(plan, ctx, e, dest)
    if e.get('partition'):
        from app.rules import search_partition

        remaining = [c for c in chosen if c not in exiled]
        if search_partition.offer(plan, ctx, e, pid, remaining, {c: dest[c] for c in remaining}):
            return
    if e.get("optional_to_if"):
        from app.rules import conditional_search_destination

        if conditional_search_destination.offer(plan, ctx, e, pid, chosen, dest):
            return
    for cid in ([] if e.get("capture_only") else chosen):
        if cid in exiled:
            continue  # the replacement already moved this exact found object
        to = dest[cid]
        if to in ("hand", "graveyard", "exile"):
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": owner, "zone": to},
                     **({"face_down": True} if e.get("face_down") and cid not in exiled else {})}, actor=pid)
        elif to in ("battlefield", "battlefield_tapped"):
            entering.append({"card": cid, "player": e.get("entry_player", e.get("entry_players", {}).get(cid, pid)), "actor": pid, "tapped": to == "battlefield_tapped",
                             **({"counter": e["counter"], "counter_n": e.get("counter_n", 1)} if e.get("counter") else {})})
    if e.get("defer_entries"):
        from app.rules import exile_land_compensation

        exile_land_compensation.collect(plan, ctx, e["defer_entries"], pid, entering)
        entering = []
    if entering and e.get("host"):  # -- if you do (wave 25C) -- "…, put it onto the battlefield attached to this creature"
        entering = _attached_entries(plan, ctx, e["host"], entering)
    if e.get("link"):  # -- resolution memory (wave 22D) -- 607.2a: "search your library for an artifact card, exile it" (Hoarding Dragon)
        from app.rules import exiled_with

        exiled_with.record(plan, ctx, [c for c in chosen if dest[c] == "exile" and c not in exiled])
    shuffle = owner if e.get("shuffle", True) else None  # 701.24: a library is shuffled only when the text says so
    if "library" not in (e.get("zones") or ["library"]):
        shuffle = None  # -- refused zones/sized (wave 3R4) -- "If you search your library this way, shuffle"
    if entering and not attachments.enter(plan, entering, ctx, shuffle=shuffle):  # an Aura chooses what it enchants (303.4f)
        return
    _moved(plan, ctx, e, found)  # the cards found, where they went (400.7j; a hand is hidden: nothing)
    if shuffle is not None:
        before = list(plan.state.zones.get(zone_key(shuffle, "library"), []))
        shuffled = plan.do({"type": "shuffle", "player": shuffle, "zone": "library"}, actor=shuffle)
        if e["to"] == "top":  # "then shuffle and put that card on top": follow it through the shuffle's new ids
            r = getattr(shuffled, "r", None)
            tops = []
            for cid in chosen:
                if dest[cid] != "top" or r is None or cid not in before:
                    continue
                new_id = r.new_ids[r.perm.index(before.index(cid))]
                tops.append(new_id)
                if not e.get("top_order"):
                    plan.do({"type": "move", "card_ids": [new_id], "to": {"player": shuffle, "zone": "library"},
                             "index": e.get("depth", 1) - 1}, actor=shuffle)  # (wave 20D: "third from the top")
            if e.get("top_order") and len(tops) > 1:  # -- refused zones/sized (wave 3R4) -- 401.4: in the order the
                _ask_order(plan, ctx, pid, shuffle, tops, "top")  # searcher chooses (private); the resolution goes on after
                return
            if e.get("top_order") and tops:
                plan.do({"type": "move", "card_ids": tops, "to": {"player": shuffle, "zone": "library"}, "index": 0}, actor=shuffle)
    continue_effects(plan, ctx)


def can_become_monarch(plan: Plan, pid: str) -> bool:
    """-- cant restrictions (wave 46A) -- 725.4: "You can't become the monarch this turn." (Jared Carthalion, True Heir) — the turn's records."""
    return not any(x.get("what") == "cant_monarch" and x["player"] == pid and x["turn"] == plan.state.turn.number for x in plan.rules.results)


def monarch(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    for pid in _players(plan, ctx, e["who"]):
        if plan.state.table.monarch != pid and can_become_monarch(plan, pid):
            plan.do({"type": "set_monarch", "player": pid}, actor=pid)
    return True


def cant_monarch(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    for pid in _players(plan, ctx, e["who"]):
        plan.rules.results.append({"what": "cant_monarch", "player": pid, "turn": plan.state.turn.number})
        plan.note(f"{plan.name(pid)} can't become the monarch this turn", actor=ctx["controller"])
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
        return _discard_next(plan, ctx, want, [], picked, e.get("as"), e.get('to', 'graveyard'), link=bool(e.get('link')), face_down=bool(e.get('face_down')), blind=bool(e.get('blind')))
    if e.get("all"):  # -- "this way" outcomes (wave 4A) -- "discard your hand": every card, no choice (701.9a)
        picked = [c for pid in order for c in plan.state.zones.get(zone_key(pid, "hand"), [])]
        return _discard_next(plan, ctx, 0, [], picked, e.get("as"), e.get('to', 'graveyard'), link=bool(e.get('link')), face_down=bool(e.get('face_down')), blind=bool(e.get('blind')))
    return _discard_next(plan, ctx, 0 if e.get("fewest") else _amount(plan, ctx, e["n"]), order, [], e.get("as"), e.get("to", "graveyard"),
                         e.get("zone", "hand"), bool(e.get("upto")), e.get("sel"), e.get("half"), bool(e.get("fewest")), bool(e.get('link')), bool(e.get('face_down')), bool(e.get('blind')),e.get('counts'))


def _discard_next(plan: Plan, ctx: Context, want: int, players: list[str], picked: list[str],
                  binding: str | None = None, dest: str = "graveyard", src: str = "hand", upto: bool = False,
                  sel: str | None = None, half: str | None = None, fewest: bool = False, link: bool = False, face_down: bool = False, blind: bool = False,
                  counts: dict[str,int] | None = None) -> bool:
    from app.rules import (
        prohibitions,  # -- prohibitions (wave 22B) -- 614.17: "… can't cause you to discard cards" (exiling isn't discarding)
    )

    for i, pid in enumerate(players):
        if counts is not None:
            want=max(0,int(counts.get(pid,0)))
        hand = plan.state.zones.get(zone_key(pid, src), [])  # (wave 15D: "exiles a card from their graveyard", public, 404.1)
        if sel:  # -- if you do (wave 21C) -- "discard a creature card": only cards of that kind can be chosen (701.9a)
            from app.rules import characteristics as chars

            kind = selectors.from_key(sel)
            hand = [c for c in hand if selectors.matches(plan, kind, plan.state.cards[c], chars.of(plan.state.cards[c], plan.info), pid)]
        if hand and dest != "exile" and (why := prohibitions.cant_cause_discard(plan, pid, str(ctx.get("replacement_controller") or ctx["controller"]))) is not None:
            plan.note(f"{why}: {plan.name(pid)} can't be made to discard cards")
            hand = []
        if half:  # -- trigger other (wave 39A) -- "discards half the cards in their hand, rounded down" (Lord Xander): 107.1a, of the hand as it is as they discard
            want = (len(hand) + (half == "up")) // 2
        if fewest:  # -- group choices (wave 53D) -- "each player discards cards the same way": down to as many as the player with the fewest cards in hand has (public: 402.3)
            want = len(hand) - min((len(plan.state.zones.get(zone_key(p, src), [])) for p in plan.live()), default=0)
        n = min(want, len(hand)) if counts is not None or want or not upto else len(hand)  # (upto, 0: "any number of cards")
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
                       "as": binding, "to": dest, "zone": src, "upto": upto, "sel": sel, "half": half, "fewest": fewest, 'link': link, 'face_down': face_down, 'blind': blind,'counts':counts})
        return False
    cards = [c for c in picked if c in plan.state.cards and plan.state.cards[c].zone.endswith(f":{src}")]
    if dest != "exile":  # (-- prohibitions (wave 22B) -- "discard your hand" / at random: the cards were picked without asking)
        cards = [c for c in cards if prohibitions.cant_cause_discard(plan, plan.state.cards[c].owner, str(ctx.get("replacement_controller") or ctx["controller"])) is None]
    e = {"as": binding}
    before = _remember(plan, ctx, e, cards)
    if cards:  # each to its owner's graveyard (701.9a); -- hand disruption (wave 11D) -- or exiled, which is no discard (701.9a)
        plan.discarding = dest == "graveyard"  # -- optional replacements (wave 110C) -- an effect's discard (Library of Leng)
        try:
            plan.do({"type": "move", "card_ids": cards, "to": {"zone": dest}, **({"face_down": True, "blind": blind} if dest == "exile" and face_down else {})}, actor=ctx["controller"])
        finally:
            plan.discarding = False
    if dest == 'exile' and link:
        from app.rules import exiled_with

        exiled_with.record(plan, ctx, cards)
    _moved(plan, ctx, e, before)  # "cards discarded this way": found in the graveyards (400.7j)
    return True


def resume_discard(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx = d.resume["ctx"]
    picked = [*(d.resume.get("picked") or []), *chosen]
    if _discard_next(plan, ctx, d.resume.get("want", 0), d.resume.get("rest") or [], picked, d.resume.get("as"),
                     d.resume.get("to", "graveyard"), d.resume.get("zone", "hand"), bool(d.resume.get("upto")),
                     d.resume.get("sel"), d.resume.get("half"), bool(d.resume.get("fewest")), bool(d.resume.get('link')), bool(d.resume.get('face_down')), bool(d.resume.get('blind')),d.resume.get('counts')):
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
        mine = [c for c in selectors.candidates(plan, sel, pid, ctx.get("source_card"), selectors.attacker_of(ctx.get("event")))  # (wave 110C: "other than that creature", Saw)
                if plan.state.cards[c].controller == pid and plan.state.cards[c].zone.endswith(":battlefield")]
        if not exile:
            from app.rules import prohibitions

            mine = [c for c in mine if not prohibitions.sacrifice_forbidden(plan, plan.state.cards[c])]
        if mine and not exile and _sacrifice_barred(plan, ctx, pid):
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
            return _exile_until_cards(plan, ctx, {"as": binding, "link": link}, picked)
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
    from app.rules import prohibitions

    cards = [c for c in cards if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")
             and not prohibitions.sacrifice_forbidden(plan, plan.state.cards[c])]
    if ctx is not None:
        cards = prohibitions.trigger_token_shield(plan, ctx, cards)  # -- prohibitions (wave 110A) --
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
    cards = [c for w in (e["who"], e.get("also")) if w for c in _cards(plan, ctx, w)
             if e["to"] == "command" or not plan.state.cards[c].zone.endswith(":battlefield")]
    if e.get("from"):  # -- if you do (wave 100B) -- "put it from your graveyard onto the battlefield" (Silvan Reveler): only while it is in that graveyard
        cards = [c for c in cards if plan.state.cards[c].zone == f"{ctx['controller']}:{e['from']}"]
    return _return_cards(plan, ctx, e, list(dict.fromkeys(cards)))


def _return_cards(plan: Plan, ctx: Context, e: dict[str, Any], cards: list[str]) -> bool:
    from app.rules import attachments  # attachments → effects (resume)

    before = _remember(plan, ctx, e, cards)
    if e.get("did"):  # -- group choices (wave 53D) -- "Put a card exiled with it into its owner's graveyard. If you do, investigate." (Foreboding Steamboat): a card was put
        context.bind_payment(ctx, e["did"], bool(cards))
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
        if e.get('link'):
            from app.rules import exiled_with

            exiled_with.record(plan, ctx, cards)
        _moved(plan, ctx, e, before)
        return True
    if e["to"] in ("graveyard", "command"):  # Explicit owner-zone destinations, including a delayed commander return.
        for cid in cards:
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": e["to"]}}, actor=ctx["controller"])
        _moved(plan, ctx, e, before)
        return True
    if e["to"] == "hand":
        for cid in cards:  # (400.3: a card goes to its OWNER's hand, whoever's graveyard it was in)
            card = plan.state.cards[cid]
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": card.owner, "zone": "hand"}}, actor=ctx["controller"])
        _moved(plan, ctx, e, before)
        return True
    if e.get("face_down"):
        from app.rules import face_down_entries64

        entries = face_down_entries64.prepare(plan, cards, ctx["controller"], under_you=e.get("under") == "you",
                                              spec=e.get("spec"), tapped=bool(e.get("tapped")))
        done = attachments.enter(plan, entries, ctx)
        if done:
            _moved(plan, ctx, e, before)
        return done
    from app.rules import conditions as entry_conditions

    entry_counter_applies = not e.get('counter_condition') or entry_conditions.holds(plan, ctx, e['counter_condition'])
    from app.rules import entry_characteristics

    form = entry_characteristics.prepare_return(plan, ctx, e)
    # -- commanders (wave 50C) -- "return it to the battlefield under an opponent's control" (Zuko, Sol'Kanar): under = "ref:<the opponent chosen before>"
    entries = [{"card": cid, "player": ctx["controller"] if e.get("under") == "you" else (_players(plan, ctx, e["under"]) or [plan.state.cards[cid].owner])[0]
                if str(e.get("under")).startswith("ref:") else plan.state.cards[cid].owner,
                "actor": ctx["controller"], "tapped": bool(e.get("tapped")),
                **({"tapped_if_land": True} if e.get("tapped_if_land") else {}),
                **({"host_choice": e["host_choice"]} if e.get("host_choice") else {}),
                **({"transformed": True} if e.get("transformed") else {}),  # (-- transform, wave 11A -- 712.14a)
                **({"counter": e["counter"], **({"counter_if": e["counter_if"]} if e.get("counter_if") else {})} if e.get("counter") and entry_counter_applies else {}),
                **({"conditional_counters": e["conditional_counters"]} if e.get("conditional_counters") else {}),
                **({"counter_n": e["counter_n"]} if e.get("counter_n") else {})} for cid in cards]  # (counters it enters with, 122.6; n: wave 4M; counter_if: wave 44A)
    if form is not None:
        entries = [{**entry, "entry_characteristics": form} for entry in entries]
    if "counter_n" in e:
        resolved_counter_n = _amount(plan, ctx, e["counter_n"])
        if resolved_counter_n <= 0:
            entries = [{k: v for k, v in entry.items() if k not in ("counter", "counter_n")} for entry in entries]
        else:
            entries = [{**entry, "counter_n": resolved_counter_n} for entry in entries]
    nxt = ctx["effects"][ctx["next"]] if e.get("as") and 0 <= ctx.get("next", -1) < len(ctx.get("effects") or ()) else {}
    if nxt.get("do") == "become" and nxt.get("lose_abilities") and nxt.get("who") == f"ref:{e['as']}" and nxt.get("duration") == "permanent":
        # -- review 35 -- "Return target creature card … to the battlefield. It's a Skeleton … and has no abilities." (Xu-Ifit, ruling 2025-07-25): it has
        # none as it enters — no "enters tapped" or "enters with" counters of its own apply (614.12), no "when it enters" triggers
        entries = [{**x, "bare": True} for x in entries]
    if e.get("host"):  # -- refused zones/sized (wave 3R4) -- "attached to this creature / that creature"
        entries = _attached_entries(plan, ctx, e["host"], entries)
        cards = [x["card"] for x in entries]
    if e.get("entry_receipt56"):
        from app.rules import entry_receipt56

        entry_receipt56.begin(plan, ctx, e["entry_receipt56"], cards)
        entries = [{**entry, "via": ctx.get("source_object")} for entry in entries]
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
    if not hosts and host_ref == "target":  # -- block events (wave 53C) -- a Curse is put onto the battlefield attached to a player (303.4c)
        hosts = [t["id"] for t in target_refs(ctx, "target") if t["id"] in plan.live()]
    if host_ref.startswith("player:") and host_ref[7:] in plan.live():
        hosts = [host_ref[7:]]
    host = hosts[0] if len(hosts) == 1 else None
    out = []
    for entry in entries:
        card = plan.state.cards[entry["card"]]
        face = attachments.entering_face(plan, card, entry)  # -- block events (wave 53C) -- 712.14a: transformed, it is the back face that attaches
        kind = attachments.attach_kind(face or plan.ch(card))
        legal = host is not None and attachments.host_problem(plan, card, host, entry["player"], face=face) is None
        if kind == "aura" and not legal:
            plan.note("The Aura can't be attached to that: it stays where it is (303.4i)", [card.id])
            continue
        out.append({**entry, "host": host} if legal and kind is not None else entry)
    return out


def pay_or_sacrifice(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Sacrifice ~ unless you pay {cost}" (and echo, 702.30): the original ability controller chooses."""
    from app.rules import mana  # casting imports this module

    pid = ctx["controller"]
    src = _cards(plan, ctx, "self")
    if not src and not e.get('echo_paid76'):
        # Non-echo source-presence checks still apply; a control change does not change the original payer.
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
    if e["cost"] == "life110c":  # -- echo {X}, X your life total (wave 110C) -- worked out as it is paid
        e = {**e, "cost": f"{{{max(0, plan.state.players[pid].life)}}}"}
    cost = mana.parse_cost(e["cost"])
    if e.get("per"):  # cumulative upkeep: the cost once for each age counter
        n = plan.state.cards[src[0]].counters.get(e["per"], 0)
        cost = mana.parse_cost(e["cost"] * n) if n else mana.parse_cost("{0}")
    e = {**e, "cost": cost.text() if not cost.is_free else "{0}"}
    options = [DecisionOption(id="pay", label=f"Pay {cost.text()}"),  # (tap your mana first, then Pay)
               DecisionOption(id="sacrifice", label=f"Sacrifice {plan.state.cards[src[0]].name}" if src and plan.state.cards[src[0]].controller == pid else "Don't pay")]
    question = " or sacrifice it" if src and plan.state.cards[src[0]].controller == pid else ""
    decide(plan, player=pid, kind="choose_one", prompt=f"{ctx.get('name', '')}: pay {cost.text()}{question}?",
           options=options, resume={"step": "pay_or_sacrifice", "ctx": ctx, "cost": e["cost"],
                   **({'echo_paid76': True} if e.get('echo_paid76') else {}),
                   **({"purpose_special": "cumulative_upkeep"} if e.get("per") == "age" else {})}, source=plan.state.cards[src[0]] if src else None)
    return False


def resume_pay_or_sacrifice(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import casting, mana  # casting imports this module

    ctx = d.resume["ctx"]
    if d.resume.get("counter"):  # "… unless its controller pays" / ward
        sid = d.resume["counter"]
        if chosen[0] == "pay":
            cost = mana.parse_cost(d.resume["cost"])
            casting.pay_from_pool_then(plan, d.player, cost, f"paid {cost.text()} so it isn't countered",
                                       then={"do": "continue", "ctx": ctx})
            return
        else:
            counter_object(plan, sid, d.player, by=ctx["controller"], source=ctx.get("source_card"))
        continue_effects(plan, ctx)
        return
    src = _cards(plan, ctx, "self")
    if chosen[0] == "pay":  # The original offer survives a mana ability sacrificing its source.
        if d.resume.get('echo_paid76'):
            from app.rules import echo_alternatives76

            echo_alternatives76.insert(ctx, [{'do': 'note_echo_paid76'}])
        cost = mana.parse_cost(d.resume["cost"])
        casting.pay_from_pool_then(plan, d.player, cost, f"paid {cost.text()} for {ctx.get('name', '')}",
                                   then={"do": "cu_paid110i" if d.resume.get("purpose_special") == "cumulative_upkeep" else "continue", "ctx": ctx},  # (wave 110I)
                                   purpose=casting.Purpose(special=d.resume.get("purpose_special")))
        return
    elif src:
        if d.resume.get("purpose_special") == "cumulative_upkeep":  # -- cumulative upkeep not paid (wave 110I) --
            from app.rules import wave110i_cards

            wave110i_cards.cu_unpaid(plan, ctx, src[0])
        _sacrifice_cards(plan, [c for c in src if plan.state.cards[c].controller == d.player], d.player, ctx)
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


PRIMITIVES: dict[str, Callable[[Plan, Context, dict[str, Any]], bool]] = {
    "use_targets": use_targets,
    "remove_counters": remove_counters, "restrict": restrict,
    "sacrifice_choice": sacrifice_choice, "return_card": return_card,
    "attach_self": attach_self, "unattach_self": unattach_self,
    "draw": draw, "gain_life": gain_life, "lose_life": lose_life, "damage": damage, "pump": pump, "grant": grant,
    "destroy": destroy, "exile": exile, "bounce": bounce, "tap": tap, "untap": untap, "scry": scry, "surveil": surveil,
    "player_counter": player_counter, "create_token": create_token, "add_counters": add_counters,
    "proliferate": proliferate, "destroy_all": destroy_all, "blink": blink, "search": search, "monarch": monarch, "cant_monarch": cant_monarch,
    "discard": discard, "regenerate": regenerate, "no_regen": no_regen, "no_regen_turn": no_regen_turn,
    "animate": animate, "pay_or_sacrifice": pay_or_sacrifice, "renown": renown, "return_yours": return_yours, "return_any": return_any, "suspend_tick": suspend_tick, "suspend_cast": suspend_cast, "cascade": cascade, "unearth": unearth, "delayed_move": delayed_move,
    "madness_offer": madness_offer, "free_cast_offer": free_cast_offer, "counter": counter, "capture_spell_payment": capture_spell_payment, "conditional_counter": conditional_counter, "paid_sacrifice_effect": paid_sacrifice_effect, "counter_unless": counter_unless,
    "sacrifice": sacrifice, "ascend": ascend, "explore": explore, "explore_each": explore_each, "prevent": prevent, "prevent_all": replacements.prevent_all, "mill": mill,
    "return_with_counter": return_with_counter, "exile_until": exile_until, "return_linked": return_linked,
    "fabricate": fabricate, "storm": storm,
    "fight": fight, "choose_targets": choose_targets,
    "double_counters": double_counters, "lki_counters": lki_counters,  # (wave 5H; move_counters: wave 12A, app/rules/counter_moves.py)
}
# -- copy system (wave 2F): copying spells, abilities and permanents (CR 707; app/rules/copying.py,
# which imports this module lazily) --
from app.rules import copying, graveyard_cost_grants57  # noqa: E402

PRIMITIVES.update(graveyard_cost_grants57.PRIMITIVES)
PRIMITIVES.update(copying.PRIMITIVES)
from app.rules import kicked_target_outcomes60  # noqa: E402

PRIMITIVES.update(kicked_target_outcomes60.PRIMITIVES)
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
    saved_after = plan.shuffle_after
    plan.shuffle_after = r.setdefault("shuffle_after", [])
    saved_retained = plan.shuffle_retained
    plan.shuffle_retained = tuple(ObjectRef(card=cid, object_id=plan.oid(plan.state.cards[cid]), zone=zone_key(pid, 'library'))
                                 for cid in r['cards'] if cid not in chosen and cid in library
                                 and (r.get('looked_objects') is None or r['looked_objects'].get(cid) == plan.oid(plan.state.cards[cid])))
    try:
        if chosen:
            if r["where"] == "graveyard":
                plan.do({"type": "move", "card_ids": chosen, "to": {"player": pid, "zone": "graveyard"}}, actor=pid)
                _wave110l.note_surveilled(plan, pid, chosen)  # -- (wave 110L) -- 701.25a: the cards a surveil put into the graveyard (Eye of Duskmantle)
            else:
                plan.do({"type": "move", "card_ids": chosen, "to": {"player": pid, "zone": "library"}, "position": "bottom"}, actor=pid)
    finally:
        plan.shuffle_retained = saved_retained
        plan.shuffle_after = saved_after
    r['chosen'] = chosen
    _finish_look45(plan, r, pid)


def resume_order_library(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The chooser's order for cards going to the top / bottom of a library (401.4: a private
    choice; ``owner``: whose library, the chooser's unless given)."""
    r = d.resume
    pid = d.player
    owner = r.get("owner") or pid
    if r.get("looked_objects") is not None:
        chosen = [c for c in chosen if c in plan.state.cards
                  and plan.state.cards[c].zone == zone_key(owner, "library")
                  and plan.oid(plan.state.cards[c]) == r["looked_objects"].get(c)]
    # Same-library moves retain reveal rights. End them before committing a
    # private order, just as bottom_at_random does for randomized placement.
    hidden = [c for c in chosen if c in plan.state.cards and plan.state.cards[c].revealed_to]
    for at in range(0, len(hidden), 250):
        plan.do({"type": "hide", "card_ids": hidden[at:at + 250]}, actor=pid)
    # -- review 30 -- one move (401.4: the cards go in at the same time and their order isn't revealed; one move per card logged it)
    if r["place"] == "top":  # the first chosen card goes on top (a move to the top puts its cards in their order)
        plan.do({"type": "move", "card_ids": list(chosen), "to": {"player": owner, "zone": "library"}, "position": "top"}, actor=pid)
    elif chosen:  # the first chosen ends at the very bottom
        plan.do({"type": "move", "card_ids": list(reversed(chosen)), "to": {"player": owner, "zone": "library"}, "position": "bottom"},
                actor=pid)
    if r.get('as_kept') and r['place'] == 'top':
        r['ctx'].setdefault('surveil_kept', {})[r['as_kept']] = sum(
            c in plan.state.cards and plan.state.cards[c].zone == zone_key(owner, 'library')
            and plan.oid(plan.state.cards[c]) == r['looked_objects'].get(c) for c in chosen)
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
        _ask_order(plan, ctx, nxt.get("chooser", nxt["owner"]), nxt["owner"], nxt["cards"], nxt["place"])
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
    sel = selectors.from_key(key)
    for i, cid in enumerate(cards):
        card = plan.state.cards[cid]
        if selectors.matches(plan, sel, card, plan.ch(card), pid, ctx.get("source_card")):
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
    viewer = _players(plan, ctx, e.get("viewer", "you"))
    if not viewer:
        return True
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
            need = _amount(plan, ctx, e["need"]) if e.get("need") is not None else 1  # (wave 51C: X, the announced value)
            at = _first_match(plan, ctx, library, e["until"], ctx["controller"]) if need > 0 else None
            for _ in range(need - 1):  # -- trigger other (wave 44B) -- "until they reveal four land cards": down to the Nth match (all of it if fewer)
                if at is None:
                    break
                nxt = _first_match(plan, ctx, library[at + 1:], e["until"], ctx["controller"])
                at = None if nxt is None else at + 1 + nxt
            top = (library if need > 0 else []) if at is None else library[: at + 1]
            if at is not None and len(owners) == 1 and not e.get("need"):
                ctx["found"] = library[at]
        else:
            top = library[: _amount(plan, ctx, e["n"])]
        if top and e.get("reveal"):
            if len(top) <= 100:
                plan.do({"type": "reveal_top", "player": pid, "count": len(top)}, actor=ctx["controller"])
            else:
                # The table top-N action is bounded, but a rules instruction may reveal an entire large library.
                for offset in range(0, len(top), 250):
                    plan.do({"type": "reveal", "card_ids": top[offset:offset + 250]}, actor=ctx["controller"])
        elif top and len(owners) == 1:  # shown to the looking player alone (a private view of those cards)
            plan.do({"type": "look_top", "player": pid, "count": len(top)}, actor=viewer[0])
        cards += top
    if len(owners) == 1:
        ctx["looked"] = cards
    ctx["looked_objects"] = {c: plan.oid(plan.state.cards[c]) for c in cards} if e.get("exact_look") else None
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


def resume_draw_upto(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx = d.resume["ctx"]
    ctx["may_ok"] = ctx["next"]
    if draw(plan, ctx, {**d.resume["e"], "n": int(chosen[0])}):
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
    if ctx.get("looked_zone") == "public_milled59":
        from app.rules import public_mill_attachment59

        return public_mill_attachment59.looked(plan, ctx)
    library = plan.state.zones.get(zone_key(pid, ctx.get("looked_zone") or "library"), [])  # (wave 10C: milled cards, in the graveyard)
    return pid, [c for c in ctx.get("looked") or [] if c in library and (not ctx.get("looked_objects")
                 or ctx["looked_objects"].get(c) == plan.oid(plan.state.cards[c]))]


def pick_looked(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Put N of them into your hand", "you may reveal a creature card from among them and put it
    into your hand", "put a land card from among them onto the battlefield tapped", "put that
    card into your hand" (``which``: "that" — the card a reveal-until found, or the one card
    looked at), "put those cards into your hand" (``which``: "all"), "put all land cards revealed
    this way into your hand" (a selector with no choice: every match)."""
    pid = ctx["controller"]
    if isinstance(e.get("total_mv"), dict):  # -- total mana value from a value (wave 110I) -- Smelting Vat: read once, when the choice opens (608.2d)
        e = {**e, "total_mv": values.evaluate(plan, ctx, e["total_mv"])}
    if e.get("public_mill59"):
        from app.rules import public_mill_attachment59

        public_mill_attachment59.prepare_public_mill(plan, ctx, e)
    owner, looked = _looked(plan, ctx)
    if e.get("by_owner"):  # -- most-played cards (wave 43B) -- "they put it onto the battlefield" / "that player puts it into their hand": the library's owner is the one who puts it
        pid = owner
    ctx["looked"] = looked
    sel = selectors.from_key(e["sel"]) if e.get("sel") else None
    options = [c for c in looked if sel is None  # (the source: "of the chosen type", wave 5I)
               or selectors.matches(plan, sel, plan.state.cards[c], plan.ch(plan.state.cards[c]), pid,
                                    ctx.get("source_card"))]
    if e.get("sels"):  # -- refused look/cast-free (wave 3R5) -- "a creature card and/or a land card": any listed kind
        from app.rules import looking

        options = [c for c in options if looking.kinds_of(plan, pid, c, e["sels"])]
    if e.get("types_cast110m"):  # -- (wave 110M) -- Hurkyl: one card for each card type among the noncreature spells cast this turn
        from app.rules import wave110m_cards

        kinds = wave110m_cards.noncreature_types_cast(plan, pid)
        options = [c for c in options if kinds & set(plan.ch(plan.state.cards[c]).types)]
        e = {**e, "n": len(kinds)}
    which = e.get("which")
    if which == "that":
        found = ctx.get("found")
        options = [found] if found and found in looked else looked if len(looked) == 1 and not e.get("require_found") else []
    most = len(options) if which in ("that", "all") else min(_amount(plan, ctx, e["n"]), len(options))
    least = 0 if e.get("optional") else most
    if not e.get("optional") and (which in ("that", "all") or (sel is not None and most == len(options))):
        return _picked(plan, ctx, e, list(options))  # nothing to choose: every card it names
    if most == 0 and (sel is None or not looked):
        return True
    # (with a filter, ask even when nothing matched, as search does: whether a decision appears
    # mustn't tell the other players what the hidden cards were)
    choosers = _players(plan, ctx, e["chooser"]) if e.get("chooser") else [pid]
    if not choosers:
        return True
    decide(plan, player=choosers[0], kind="choose_cards", prompt=e.get("prompt") or "Choose from among them" + (f" (total mana value {e['total_mv']} or less)" if e.get("total_mv") is not None else ""),
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in options],
           min_choices=least, max_choices=most, resume={"step": "pick_looked", "ctx": ctx, "e": e})
    return False


def resume_pick_looked(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    _within_total(plan, e, list(chosen))  # (wave 51A)
    if e.get("sels"):  # -- refused look/cast-free (wave 3R5) -- one card of each kind, each a different card
        from app.rules import looking

        if not looking.distinct_kinds(plan, ctx["controller"], list(chosen), e["sels"]):
            from app.game.errors import ActionError

            raise ActionError("Choose at most one card of each kind")
    if e.get("types_cast110m"):
        from app.rules import wave110m_cards

        if not wave110m_cards.one_per_type(plan, ctx["controller"], list(chosen)):
            from app.game.errors import ActionError

            raise ActionError("Choose at most one card for each card type among the noncreature spells you cast this turn")
    if e.get("different110m") == "power":  # -- (wave 110M) -- "cards with different powers" (Rip, Spawn Hunter): no two chosen share a power (a card with none shares nothing)
        powers = [pt[0] for c in chosen if (pt := plan.ch(plan.state.cards[c]).pt) is not None]
        if len(set(powers)) != len(powers):
            from app.game.errors import ActionError

            raise ActionError("Choose cards with different powers")
    if _picked(plan, ctx, e, list(chosen)):
        continue_effects(plan, ctx)


def _picked(plan: Plan, ctx: Context, e: dict[str, Any], chosen: list[str]) -> bool:
    """Move the picked cards where the instruction says; False while an Aura entering chooses."""
    from app.rules import attachments  # attachments → effects (resume)

    if ctx.get("looked_objects") is not None:
        valid = set(_looked(plan, ctx)[1])
        chosen = [c for c in chosen if c in valid]
    pid = _looked(plan, ctx)[0] if e.get("by_owner") else ctx["controller"]  # (wave 43B: the library's owner puts the card)
    if chosen and e.get("reveal"):
        plan.do({"type": "reveal", "card_ids": chosen}, actor=pid)  # to everyone
    ctx["looked"] = [c for c in ctx.get("looked") or [] if c not in chosen]
    if ctx.get("found") in chosen:
        ctx["found"] = None
    before = _remember(plan, ctx, e, chosen)
    if e["to"] == "choose":
        return True  # Publicly selected/revealed, without moving the exact looked-at object.
    # -- look and distribute (wave 3L) -- "If you don't [put the card …]" reads what this pick did
    # (a probe like draw's: the picked objects, as they were, and the zone they should reach)
    if e.get("did"):
        zone = {"battlefield_tapped": "battlefield", "battlefield_attacking": "battlefield", "top": "library",
                "bottom": "library"}.get(e["to"], e["to"])
        if e.get("choice_payment59"):
            context.bind_payment(ctx, e["did"], bool(chosen))
        else:
            context.refs(ctx)[e["did"]] = {"kind": "probe", "to": zone, "cards": {c: plan.oid(plan.state.cards[c]) for c in chosen}}
    if e["to"] in ("top_any", "bottom_any"):
        if len(chosen) > 1:
            _ask_order(plan, ctx, pid, _looked(plan, ctx)[0], chosen, "top" if e["to"] == "top_any" else "bottom")
            return False
        if chosen:
            if e["to"] == "top_any":
                plan.do({"type": "move", "card_ids": chosen, "to": {"player": _looked(plan, ctx)[0], "zone": "library"},
                         "position": "top"}, actor=pid)
            else:
                bottom_at_random(plan, _looked(plan, ctx)[0], chosen, actor=pid)
    elif e["to"] in ("top", "bottom"):  # "put it on top of / on the bottom of your library": the owner's (private order)
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
                    **({"counter": e["counter"], "counter_n": e.get("counter_n", 1)} if e.get("counter") and (not e.get("counter_if") or selectors.matches(
                        plan, selectors.from_key(e["counter_if"]), plan.state.cards[c], plan.ch(plan.state.cards[c]), pid)) else {})}  # CR 122.6
                   for c in chosen]
        from app.rules import entry_characteristics

        form = entry_characteristics.prepare_return(plan, ctx, e)
        if form is not None:
            for entry in entries:
                entry['entry_characteristics'] = form
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
    viewers = _players(plan, ctx, e.get("viewer", "you"))
    if not viewers:
        return True
    pid = viewers[0]
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
           resume={"step": "order_library", "place": place, "then_bottom": [], "owner": owner, "ctx": ctx,
                   **({"looked_objects": {c: plan.oid(plan.state.cards[c]) for c in cards}}
                      if ctx.get("looked_objects") is not None else {})})


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
        elif e.get("half"):  # -- commander sweep (wave 49B) -- 107.1a: "the top half of their library, rounded up" (Ulamog, the Defiler): half the cards in it now
            n = (len(library) + 1) // 2 if e["half"] == "up" else len(library) // 2
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
    cards = ([t["id"] for group in ctx.get("groups", []) for t in group if t] if e["who"] == "all_targets" else _cards(plan, ctx, e["who"]))
    before = _remember(plan, ctx, e, cards)
    compound81 = e.get('owner_root_choice81') and any(plan.state.cards[cid].merged for cid in cards)
    if (len(cards) > 1 or compound81) and (e["place"] == "choice" or (e["place"] in ("top", "bottom") and not e.get("chooser"))):
        from app.rules import library_placements

        return library_placements.start(plan, ctx, e, cards, before)
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
               resume={"step": "library_place", "card": card.id, "object": plan.oid(card), "ctx": ctx, "e": e, "before": [r.model_dump(mode="json") for r in before]},
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
    ctx["library_queue"] = [{"owner": pid, "cards": mine, "place": place,
                             "chooser": ctx["controller"] if e.get("chooser") == "controller" else pid} for pid, mine in multiple[1:]]
    ctx["library_before"] = [r.model_dump(mode="json") for r in before]
    ctx["library_e"] = e
    pid, mine = multiple[0]
    _ask_order(plan, ctx, ctx["controller"] if e.get("chooser") == "controller" else pid, pid, mine, place)
    return False


def resume_library_place(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    ctx, e = r["ctx"], r["e"]
    card = plan.state.cards.get(r["card"])
    if card is not None and (r.get("object") is None or plan.oid(card) == r["object"]):
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
        named = [p for p in _players(plan, ctx, e["who"]) if p != pid]  # -- player-relative selectors (wave 53A) -- "You may have that player shuffle": the choice is the controller's
        decide(plan, player=pid, kind="confirm", prompt=f"Have {plan.name(named[0])} shuffle their library?" if named else "Shuffle your library?",
               options=[DecisionOption(id="yes", label="Shuffle"), DecisionOption(id="no", label="Don't shuffle")],
               resume={"step": "shuffle_library", "ctx": ctx, "e": {**e, "optional": False}})
        return False
    players = _players(plan, ctx, e["who"])
    # (-- static_other sweep (wave 16B) -- "then draws that many cards": the cards shuffled in are the binding "as", each its owner's)
    chosen = _cards(plan, ctx, e["cards"]) if e.get("cards") else []  # -- shuffle target cards (wave 46B) -- the target cards still the same objects (608.2b)
    before = _remember(plan, ctx, e, [c for pid in players for zone in e.get("zones") or [] for c in plan.state.zones.get(zone_key(pid, zone), [])] + chosen)
    moved_count = 0
    for pid in players:
        if mine := [c for c in chosen if c in plan.state.cards and plan.state.cards[c].zone == zone_key(pid, "graveyard")]:  # (their graveyard: 701.24a puts them in before the shuffle; wave 100C: an earlier owner's shuffle re-keyed theirs)
            originals = {cid: plan.oid(cid) for cid in mine}
            plan.do({"type": "move", "card_ids": mine, "to": {"player": pid, "zone": "library"}}, actor=pid)
            moved_count += sum(cid in plan.state.cards and plan.state.cards[cid].zone == zone_key(pid, "library")
                               and plan.oid(cid) != oid for cid, oid in originals.items())
        for zone in e.get("zones") or []:
            cards = list(plan.state.zones.get(zone_key(pid, zone), []))
            if e.get("sel"):  # (wave 16C: "all creature cards from your graveyard")
                keep = set(_cards(plan, ctx, e["sel"]))
                cards = [c for c in cards if c in keep]
            if cards:
                originals = {cid: plan.oid(cid) for cid in cards}
                plan.do({"type": "move", "card_ids": cards, "to": {"player": pid, "zone": "library"}}, actor=pid)
                moved_count += sum(cid in plan.state.cards and plan.state.cards[cid].zone == zone_key(pid, "library")
                                   and plan.oid(cid) != oid for cid, oid in originals.items())
        plan.do({"type": "shuffle", "player": pid, "zone": "library"}, actor=pid)
    _moved(plan, ctx, e, before)
    if e.get("bind"):
        context.bind_amount(ctx, e["bind"], moved_count)
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
from app.rules import multiplayer_look as _multiplayer_look  # noqa: E402, I001

PRIMITIVES["multiplayer_look"] = _multiplayer_look.start

from app.rules import spell_control as _spell_control  # noqa: E402, I001

PRIMITIVES["gain_control_spell"] = _spell_control.gain_control

from app.rules import looking as _looking  # noqa: E402, I001  -- refused look/cast-free (wave 3R5) -- (a leaf module)

from app.rules import piles_legacy as _piles_legacy  # noqa: E402, I001  -- review 53 -- old saves (wave 53D replaced it with pile_groups)

PRIMITIVES["piles"] = _piles_legacy.piles
PRIMITIVES["piles_down"] = _looking.piles_down  # -- hidden exile (wave 18A) -- a face-down pile and a face-up pile
PRIMITIVES["win_if_library"] = _looking.win_if_library  # -- refused look/cast-free (wave 3R5) --
from app.rules import reveal_hand as _reveal_hand  # noqa: E402, I001  -- if you do (wave 10C) -- (a leaf module)

PRIMITIVES["reveal_hand_cards"] = _reveal_hand.reveal_hand_cards
PRIMITIVES["reveal_some"] = _reveal_hand.reveal_some  # -- hand disruption (wave 52C) --


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
from app.rules import group_choice as _group_choice  # noqa: E402, I001  -- group choices (wave 53D) --

PRIMITIVES.update(_group_choice.PRIMITIVES)
from app.rules import pile_groups as _pile_groups  # noqa: E402, I001  -- piles (wave 53D) --

PRIMITIVES.update(_pile_groups.PRIMITIVES)
from app.rules import reanimate_auras as _reanimate_auras  # noqa: E402, I001  -- reanimation Auras (wave 51F) --

PRIMITIVES.update(_reanimate_auras.PRIMITIVES)
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
                    c: plan.oid(plan.state.cards[c]) for c in cards if prohibitions.cant_counters(plan, c, None, e["kind"]) is None}}
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
            elif kind == "control":  # -- commanders (wave 50C) -- "Target opponent gains control of target Horse you control. If they do, …": a permanent now has another controller
                refs[name] = {"kind": "probe", "control": {c: [plan.oid(plan.state.cards[c]), plan.state.cards[c].controller] for c in _cards(plan, ctx, e["who"])}}
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
    from app.rules import conditions, optional_continuations58
    from app.rules.triggers import _add  # (triggers imports this module)

    if e.get("entry_receipt56"):
        from app.rules import entry_receipt56

        entry_receipt56.finish(plan, ctx, e["entry_receipt56"])
        if entry_receipt56.suppressed(plan, ctx, e):
            return True
    if bool(ctx.get("dice")) if e.get("roll_result") else conditions.holds(plan, ctx, e["cond"]):
        # (-- resolution memory (wave 22D) -- "cond_ref": the objects the counted "… this way" instruction acted on: "When you discard a card
        # this way, … that card's mana value")
        name = e["cond"]["value"]["ref_count"] if e.get("lki") == "cond_ref" else e.get("lki")
        event = _reflexive_event(plan, ctx, name) if name else None  # -- reflexive LKI (wave 4J) --
        if e.get("roll_result"):
            from app.game.rules_state import TriggerEvent

            event = TriggerEvent(kind="reflexive", amount=int(ctx["die"]))
        if event is not None and e.get("lki") == "cond_ref":  # -- reflexive this way (wave 30G) -- "that many" / "that much": how many it did this to (608.2c, 608.2h)
            event = event.model_copy(update={"amount": _this_way.count(plan, ctx, e["cond"]["value"])})
        if e.get("keep_event") and event is None and ctx.get("event"):  # -- reflexive this way (wave 30G) -- "that player" is still the trigger's
            from app.game.rules_state import TriggerEvent

            event = TriggerEvent.model_validate(ctx["event"])
        if e.get("players_from"):  # -- random choices (wave 47B) -- "Choose a player at random. When you do, … target creature that player controls" (Strax): the pick is the event's player
            from app.game.rules_state import TriggerEvent

            event = TriggerEvent(kind="reflexive", players=context.players(plan, ctx, e["players_from"]))
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
                 name=str(ctx.get("name") or ""), index=7300, definition=optional_continuations58.reflexive_ability(plan, ctx, e), event=ev)
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
    elif b.get("kind") == "probe" and b.get("attached"):  # -- block events (wave 53C) -- what an Aura / Equipment / Role was attached to (attach_entry.attach_to, roles.create_role)
        before = [ObjectRef(card=h, object_id=plan.oid(h)) for h in dict.fromkeys(b["attached"].values()) if h in plan.state.cards]
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
    from app.rules import conditions

    held = conditions.holds(plan, ctx, {"object": "self", "cast": {"optional": "teamwork"}}) if e.get("teamwork") else conditions.holds(
        plan, ctx, {"object": "self", "cast": {"optional": e["optional"]}}) if e.get("optional") else values.kicked_holds(plan, ctx, e.get("with"))
    if held != bool(e["kicked"]):  # (-- keywords (wave 50H) -- "kicked with its {R} kicker": ``with``; wave 100K: ``teamwork``, 702.194b, its announcement)
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
    from app.rules import text_spell_refresh71

    refreshed71 = text_spell_refresh71.refresh(plan, stack_id, entry)
    if refreshed71 is None:
        return
    entry = refreshed71
    if entry.x_from_event_spell:
        from app.rules.triggers import event_spell_x

        if (value := event_spell_x(plan, entry.event)) is not None:
            entry.x = value
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
        src = source_of(plan, entry.source_card, entry.kind == "spell", object_id=entry.source_object)
        slots, targeted, legal_any = [], False, False
        for refs, sspec in zip(entry.slots, entry.slot_specs, strict=False):
            ok = [t for t in refs if sspec and still_legal(plan, sspec["what"], entry.controller, t, src, entry.source_card, attacker, source_object=entry.source_object)]
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
        src = source_of(plan, entry.source_card, entry.kind == "spell", object_id=entry.source_object)
        groups: list[list[dict[str, Any] | None]] = []
        for refs, gspec in zip(entry.groups, entry.group_specs, strict=False):
            # an illegal target keeps its place (None), so the division stays as announced (115.7f)
            together = relation_ok(plan, gspec, refs)  # (wave 51A) "that share a creature type": no longer so, all of the group's targets are illegal (608.2b; Shifting Loyalties ruling)
            what = player_relative.bind_what(plan, gspec, entry.groups)  # (-- player-relative selectors (wave 53A) -- "that player controls": the player group ``of`` names, as it last was)
            dependency = gspec.get('requires_legal_group')
            if dependency is not None:
                together = together and 0 <= dependency < len(groups) and any(groups[dependency])
            groups.append([t.model_dump() if together and still_legal(plan, what, entry.controller, t, src, entry.source_card, attacker, source_object=entry.source_object)
                           else None for t in refs])
        chosen = sum(len(refs) for refs in entry.groups)
        from app.rules import exchange_conditions91

        if chosen and not any(t for g in groups for t in g) and not exchange_conditions91.resolves_illegal(entry):
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
        src = source_of(plan, entry.source_card, entry.kind == "spell", object_id=entry.source_object)  # (wave 49C: 115.2)
        legal = [t for t in entry.targets if still_legal(plan, spec["what"], entry.controller, t, src, entry.source_card, attacker, source_object=entry.source_object)]
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


def run_body(plan: Plan, ctx: Context) -> bool:
    """Run an immediate effect body without finishing its caller on synchronous completion."""
    with reading_x(plan, ctx.get("x")):
        return _run_body(plan, ctx)


def _run_body(plan: Plan, ctx: Context) -> bool:
    before110g, plan.cause110g = plan.cause110g, ctx.get("controller")  # -- wave 110G -- stamps the zone changes this body causes
    try:
        return _run_effects(plan, ctx)
    finally:
        plan.cause110g = before110g


def _run_effects(plan: Plan, ctx: Context) -> bool:
    while ctx["next"] < len(ctx["effects"]):  # (wave 19F: re-read each time: effects.repeat replaces the list)
        e = ctx["effects"][ctx["next"]]
        from app.rules import stickers101

        if stickers101.ask_first(plan, ctx, e):
            return False
        if replacements.ask_903_9b_first(plan, ctx, e):
            return False  # 903.9b: a commander's owner chooses before it would be put into a hand or library
        ctx["next"] += 1
        if e.get("that"):  # -- player-relative selectors (wave 53A) -- "cards that player owns in exile": that player, as the instruction before left it
            e = player_relative.bind_effect(plan, ctx, e)
        if e.get("note_group"):  # -- counters (wave 5H) -- the permanents a count reads, for a later "those creatures"
            context.bind_objects(plan, ctx, e["note_group"]["as"], _cards(plan, ctx, e["note_group"]["who"]))
        e = block_events.bind(plan, ctx, e)  # -- block events (wave 53C) -- "creatures blocking it", "Auras attached to that creature": the object bound now
        if not PRIMITIVES[e["do"]](plan, ctx, e):
            return False  # waiting for a choice; the decision's resume continues from ctx["next"]
    return True


def _continue_effects(plan: Plan, ctx: Context) -> None:
    if not _run_body(plan, ctx):
        return
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


def _did_transform(fn: Any) -> Any:
    """-- commanders (wave 50C) -- "Whenever you gain life, you may convert Ratchet. When you do, …": 701.28a / 118.12 — it is done when the permanent turned over (a
    permanent that already turned since the ability went on the stack doesn't, 701.27f / 701.28e). Bound after the run, once."""
    def run(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
        name = e.get("did")
        before = {c: plan.state.cards[c].face for c in _cards(plan, ctx, e["who"])} if name and name not in context.refs(ctx) else {}
        done = bool(fn(plan, ctx, e))
        if name and before and name not in context.refs(ctx):
            context.bind_payment(ctx, name, any(plan.state.cards[c].face != f for c, f in before.items()))
        return done
    return run


PRIMITIVES["transform"] = _did_transform(PRIMITIVES["transform"])


def describe(effects: list[dict[str, Any]]) -> str:
    if said := next((e["say110n"] for e in effects if e.get("say110n")), None):  # -- (wave 110N) -- an effect that words its own question (Vislor Turlough)
        return str(said).capitalize()
    words = {"draw": "draw {n} card(s)", "gain_life": "gain {n} life", "lose_life": "lose {n} life", "scry": "scry {n}",
             "surveil": "surveil {n}", "damage": "deal {n} damage", "player_counter": "get {n} {counter}",
             "create_token": "create {n} token(s)", "add_counters": "put {n} {kind} counter(s)", "proliferate": "proliferate",
             "monarch": "become the monarch", "discard": "discard {n}", "search": "search your library",
             "demonstrate_copy": "copy it, and an opponent copies it too (demonstrate)", "return_card": "return it", "attach_to": "attach it",
             "aura_sharing110d": "return this Aura to a creature that shares a creature type", "aura_back110d": "return this Aura to the battlefield"}  # (wave 110D; wave 100B: Auriok Survivors)
    # (an amount that is worked out as it resolves — "equal to its mana value", X — reads as X, not as its data)
    parts = [("discard any number" if e["do"] == "discard" else f"sacrifice up to {e['n']}" if isinstance(e.get("n"), int) and e["n"] < 10**6  # (wave 100B: "up to three")
              else "sacrifice any number") if e["do"] in ("discard", "sacrifice_choice") and e.get("upto")
             else words.get(e["do"], e["do"]).format(**{k: "X" if isinstance(v, (dict, list)) else v for k, v in e.items()}) for e in effects
             if e["do"] not in ("kicked_gate", "record_action", "action_gate", "only_if", "note_resolution", "reflexive", "demonstrate_opponent", "may_rest", "vislor110n", "rinoa_pick110o")]  # (wave 30G: "any number"; wave 110N: Vislor's goad follows the control change)
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


def _controlled(plan: Plan, key: str, pid: str, source: str | None, you: str | None = None, zone: str | None = None) -> list[str]:
    """The permanents ``pid`` controls that match a selector, evaluated for that player (``you``: -- trigger other (wave 39A) -- or for the ability's
    controller, whose "you" a qualifier like "that dealt combat damage to you this turn" is). ``zone``: -- player-relative selectors (wave 53A) -- the cards
    ``pid`` owns in that public zone instead ("choose a creature card in that player's graveyard", 404.1)."""
    sel = selectors.from_key(key)
    if zone is not None:
        return [c for c in selectors.candidates(plan, sel, you or pid, source) if plan.state.cards[c].owner == pid and plan.state.cards[c].zone == f"{pid}:{zone}"]
    if sel.zones == ("graveyard",):  # -- group choices (wave 53D) -- "a creature card in their graveyard": the cards in the graveyard of ``pid`` (404.1)
        return [c for c in selectors.candidates(plan, sel, you or pid, source) if plan.state.cards[c].zone == f"{pid}:graveyard"]
    return [c for c in selectors.candidates(plan, sel, you or pid, source)
            if plan.state.cards[c].controller == pid and plan.state.cards[c].zone.endswith(":battlefield")]


def _choose_next(plan: Plan, ctx: Context, e: dict[str, Any], players: list[Any], picked: list[str], step: str) -> bool:
    """Each player in ``players`` (APNAP order) chooses ``n`` of the matching permanents they
    control. A player with at most that many has no choice to make (they're all chosen); one
    with none is skipped. Choices already made are announced, so the next chooser knows them
    (101.4b). False while waiting for a choice."""
    from app.rules import conditions

    half = e["n"].get("half_own") if isinstance(e["n"], dict) else None  # -- trigger other (wave 39A) -- "sacrifices half the creatures they control, rounded down": each player's own count
    div = int(e["n"].get("div", 2)) if half else 2  # -- static permanents (wave 100D) -- "a tenth of the creatures they control" (Legate Lanius)
    fewest = e["n"].get("fewest") if isinstance(e["n"], dict) else None  # -- group choices (wave 53D) -- "a number of lands they control equal to the number of lands controlled by the player who controls the fewest"
    want = min((len(_controlled(plan, fewest, p, ctx.get("source_card"))) for p in plan.live()), default=0) if fewest else 0 if half else _amount(plan, ctx, e["n"])
    exiling = e.get("action") == "exile"  # -- modal spells (wave 24D) -- "Target opponent exiles a creature they control."
    verb = ("exiles" if exiling else "sacrifices") if step == "edict" else "chooses"
    for i, turn in enumerate(players):
        # -- per-player choices (wave 30K) -- a turn is a player and the kind of permanent chosen (an old save: just the player); "you choose …
        # for each player" (Tragic Arrogance): the ability's controller decides what each player's permanents are
        pid, key = (turn, e["sel"]) if isinstance(turn, str) else turn
        mine = _controlled(plan, key, plan.after(pid) if e.get("left") else pid, ctx.get("source_card"),  # (wave 53D: "the player to their left", Grenzo's Rebuttal)
                           ctx["controller"] if "dealt_combat_damage_you" in key else None, e.get("zone"))  # (wave 53A: a zone of that player)
        if e.get("any"):  # -- per-player choices (wave 31B) -- any permanent the ability's words allow ("a creature you don't control"), whoever controls it
            mine = [c for c in selectors.candidates(plan, selectors.from_key(key), pid if e.get("any_by_chooser") else ctx["controller"], ctx.get("source_card"))
                    if plan.state.cards[c].zone.endswith(":battlefield") or selectors.from_key(key).zones != ("battlefield",)]  # (wave 53D: or cards of another zone)
        if e.get("looked"):  # -- group choices (wave 53D) -- from the cards just revealed (Manifold Insights)
            from app.rules import characteristics as chars

            kind = selectors.from_key(key)
            mine = [c for c in _looked(plan, ctx)[1] if selectors.matches(plan, kind, plan.state.cards[c], chars.of(plan.state.cards[c], plan.info), ctx["controller"],
                                                                         ctx.get("source_card"))]
        if e.get("party"):  # -- group choices (wave 53D) -- 700.8: a party is up to one each of Cleric, Rogue, Warrior and Wizard (Stick Together)
            from app.rules import looking

            mine = [c for c in mine if looking.kinds_of(plan, pid, c, e["party"])]
        if e.get("shares_type_with") == "cost":  # -- group choices (wave 53D) -- "shares a card type with the sacrificed permanent" (Fatal Grudge): as it last existed (608.2h)
            from app.rules import this_way

            context.refs(ctx)["gcost"] = {"kind": "objects", **this_way.cost_objects(plan, ctx, this_way.COST, "sacrificed")}
            shared = {t for _, ch in context.infos(plan, ctx, "gcost") for t in ch.types}
            mine = [c for c in mine if plan.ch(plan.state.cards[c]).types & shared]
        if e.get("shares_type_with") == "event":  # -- group choices (wave 110B) -- Martyr's Bond: the card types of the permanent that left, as it last existed (603.10a, 608.2h)
            shared = {t for _, ch in context.infos(plan, ctx, context.EVENT) for t in ch.types}
            mine = [c for c in mine if plan.ch(plan.state.cards[c]).types & shared]
        if e.get("matching110f"):  # -- (wave 110F) -- Release: only choices that let the player fill as many kinds as they can
            from app.rules import wave110f_cards

            mine = wave110f_cards.matching(plan, ctx, e, pid, mine, picked, [k for t, k in (x for x in players[i + 1:] if not isinstance(x, str)) if t == pid])
        if e.get("distinct"):  # -- group choices (wave 53D) -- "a creature card in your graveyard that hasn't been chosen" (Rejoin the Fight): no object twice
            mine = [c for c in mine if c not in picked]
        if e.get("cap_power"):  # -- group choices (wave 53D) -- "with equal or lesser power" than the creature chosen first (Sculpted Sunburst)
            capped = context.objects(plan, ctx, e["cap_power"][len(context.PREFIX):])
            mine = [c for c in mine if capped and _power_of(plan, c) <= _power_of(plan, capped[0])]
        from app.rules import nontarget_creature_choices

        mine = nontarget_creature_choices.candidates(plan, ctx, e, mine)
        if step == "edict" and not exiling:
            from app.rules import prohibitions

            mine = [c for c in mine if not prohibitions.sacrifice_forbidden(plan, plan.state.cards[c])]
        if step == "edict" and not exiling and mine and _sacrifice_barred(plan, ctx, pid):
            mine = []  # -- prohibitions (wave 22B) -- nothing for them to sacrifice
        cap = e.get("power_cap")  # "any number of creatures they control with total power 4 or less" (Slaughter the Strong): always a choice
        n = len(mine) if cap is not None else (len(mine) + (div - 1) * (half == "up")) // div if half else min(len(e["party"]), len(mine)) if e.get("party") else min(want, len(mine))  # (107.1a: half rounded as written)
        if n == 0:
            continue
        by = ctx["controller"] if e.get("by") == "you" or (e.get("by_if") and conditions.holds(plan, ctx, e["by_if"])) else pid
        label = dict(zip(e.get("sels") or [], e.get("labels") or [], strict=False)).get(key, e.get("label", "permanent"))
        if n == len(mine) and cap is None and not e.get("party") and not (e.get("upto") and (e.get("any") or e.get("optional"))):  # (an "up to one" / "may choose" always asks; wave 32A: "optional")
            picked = [*picked, *mine]
            plan.note(f"{plan.name(by)} {verb} {_labels(plan, mine)} (no choice: all of them)", mine, actor=by)
            continue
        prompt = f"{ctx.get('name', '') or 'Choose'}: {verb[:-1] if step == 'edict' else 'choose'} {n} ({label})"
        if cap is not None:
            prompt = f"{ctx.get('name', '') or 'Choose'}: choose any number of {label} with total power {cap} or less"
        if by != pid:
            prompt += f" for {plan.name(pid)}"
        if e.get("left"):
            prompt += f" among {plan.name(plan.after(pid))}'s permanents"  # (wave 53D: the player to their left)
        if picked:
            prompt += f" — already chosen: {_labels(plan, picked)}"  # 101.4b: the earlier choices are known
        decide(plan, player=by, kind="choose_cards", prompt=prompt,
               options=[DecisionOption(id=c, label=(plan.state.cards[c].name or "Permanent") + (f" ({_power_of(plan, c)})" if cap is not None else "")
                        + (f" — {plan.name(plan.state.cards[c].controller)}" if e.get("any") else ""), card_id=c) for c in mine],
               min_choices=0 if e.get("upto") or cap is not None or e.get("party") else n, max_choices=n,  # (wave 11D: "chooses up to two creatures they control")
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
        if e.get("any"):
            rest = [cid for cid in selectors.candidates(plan, selectors.from_key(e.get('rest_sel', e['sel'])), ctx['controller'], ctx.get('source_card')) if cid not in picked]
        from app.rules import nontarget_creature_choices

        rest = nontarget_creature_choices.rest(plan, e, rest, picked)
        if e["rest"] == "sacrifice":
            _sacrifice_cards(plan, rest, ctx["controller"], ctx, e.get("as"))
        elif e["rest"] == "exile":  # -- group choices (wave 53D) -- "chooses two cards in their graveyard and exiles the rest" (Watchers of the Dead)
            exile_cards(plan, ctx, {}, rest)
        else:  # "Destroy the rest" (701.8): indestructible ones stay, regeneration may save the others
            _destroy_cards(plan, ctx, e, rest)
    else:
        if e.get("add") and e.get("as"):  # -- group choices (wave 53D) -- the objects of this choice join those an earlier choice of the same name bound
            picked = [*context.objects(plan, ctx, e["as"]), *picked]
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
    if isinstance(e, dict):
        from app.rules import nontarget_creature_choices

        nontarget_creature_choices.validate(plan, e, chosen)
    if isinstance(e, dict) and e.get("party"):  # -- group choices (wave 53D) -- 700.8, 700.8b: each creature of a party is the member for one type, no two for the same
        from app.rules import looking

        if not looking.distinct_kinds(plan, d.player, chosen, e["party"]):
            raise ActionError("A party has at most one Cleric, one Rogue, one Warrior and one Wizard, each a different creature (700.8)")


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
    if e.get("as") and not e.get("private"):  # -- chosen filters (wave 53B) -- "for each card of the chosen type revealed this way": the cards shown to everyone (701.20a)
        context.bind_objects(plan, ctx, e["as"], revealed)
    if e.get("private"):
        ctx["looked_hand"] = list(revealed)  # -- player-relative selectors (wave 53A) -- "look at that player's hand. You may cast a spell from among those cards": the cards seen (permissions._free_pool "revealed")
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
    def awaiting_move(cid: str) -> bool:
        # 701.16a: a held discard still needs its revealed object while 616.1 is
        # answered. The terminal native zone change clears that object's reveal.
        pending = plan.rules.pending_616.get(cid)
        return pending is not None and pending.get("oid") == plan.oid(plan.state.cards[cid])

    if e.get("refs"):
        # Explicit bindings can finish a library reveal without touching unrelated
        # cards or a new incarnation. Keep the established hand cleanup as default.
        left = [c for c in context.objects(plan, ctx, e["refs"])
                if plan.state.cards[c].zone.endswith(":" + e.get("zone", "hand")) and plan.state.cards[c].revealed_to and not awaiting_move(c)]
        if left:
            plan.do({"type": "hide", "card_ids": left}, actor=ctx["controller"])
        return True
    left = [c for c in ctx.get("revealed") or [] if c in plan.state.cards and plan.state.cards[c].zone.endswith(":hand")
            and plan.state.cards[c].revealed_to and not awaiting_move(c)]
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
    if e.get("extra110g"):  # -- wave 110G -- Cloak and Dagger: "… a nonland card from their hand or the chosen creature": a battlefield object joins the options
        options += [c for c in _cards(plan, ctx, e["extra110g"]) if plan.state.cards[c].zone.endswith(":battlefield")]
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
    chosen = [c for c in chosen if c in plan.state.cards and plan.state.cards[c].zone.endswith((":hand", ":graveyard", ":battlefield" if e.get("extra110g") else ":hand"))]
    if chosen:
        plan.note(f"{plan.name(d.player)} chooses {_labels(plan, chosen)}", chosen, actor=d.player)
    _remember(plan, ctx, e, chosen)  # "that card" / "those cards": the chosen cards, in that hand
    if e.get("did"):  # -- if you do (wave 15C) -- "You may choose a card from it. If you do, …": a card was chosen (608.2c)
        context.bind_payment(ctx, e["did"], bool(chosen))
    if e.get("keep110g"):  # -- wave 110G -- a second choice from the same revealed hand follows (Distended Mindbender): the rest stays revealed
        ctx["revealed"] = [c for c in ctx.get("revealed") or [] if c not in chosen]
    else:
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
    if e.get("n"):  # -- chosen filters (wave 53B) -- "discards a card with that name": one of them (701.9a)
        cards = cards[: e["n"]]
    before = _remember(plan, ctx, e, cards)
    if cards:
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "graveyard"}}, actor=ctx["controller"])
    _moved(plan, ctx, e, before)
    if e.get("else_draw") and not cards:  # "If they can't, you draw a card." (Brain Pry)
        from app.rules import replace

        return replace.draw_cards(plan, [ctx["controller"]], 1, then={"do": "continue", "ctx": ctx}, ctx=ctx)
    return True


# Named choices (105.1 colors, 205.3m creature types, 205.3i basic land types, players).
MOST_LIFE = "player with the most life or tied for most life"  # -- player-relative selectors (wave 53A), block events (wave 53C) -- The Black Gate
PLAYER_CHOICES = ("opponent", "player", MOST_LIFE)
CHOICE_OPTIONS: dict[str, list[str]] = {
    "color": ["White", "Blue", "Black", "Red", "Green"],
    "odd or even": ["Odd", "Even"],  # -- chosen quality (wave 50J) -- 107.1: zero is even
    "basic land type": ["Plains", "Island", "Swamp", "Mountain", "Forest"],
    "land type": sorted(t for t in layers.LAND_TYPES if t != "Urza’s"),
    "second color": ["White", "Blue", "Black", "Red", "Green"],
    "second basic land type": ["Plains", "Island", "Swamp", "Mountain", "Forest"],  # (wave 53B: "choose two basic land types", Illusionary Terrain)
    # -- commanders (wave 47A) -- 205.2a: "As Umori enters, choose a card type." / "… other than creature or land." (Stenn): the card types a spell or a permanent can have
    "card type": ["Artifact", "Battle", "Creature", "Enchantment", "Instant", "Kindred", "Land", "Planeswalker", "Sorcery"],
    "card type other than creature or land": ["Artifact", "Battle", "Enchantment", "Instant", "Kindred", "Planeswalker", "Sorcery"],
    "card type other than creature": ["Artifact", "Battle", "Enchantment", "Instant", "Kindred", "Land", "Planeswalker", "Sorcery"],  # (wave 53B: Arachne, Psionic Weaver)
    "artifact, creature, enchantment, instant, or sorcery": ["Artifact", "Creature", "Enchantment", "Instant", "Sorcery"],  # (Cloud Key)
}
CHOICE_LABELS = {"second color": "Chosen second color", "second basic land type": "Chosen second basic land type", "number": "Chosen number", "color": "Chosen color",  # (wave 53B: "Choose a number between 0 and 10": the options in the instruction)
                 "creature type": "Chosen creature type", "basic land type": "Chosen basic land type", "land type": "Chosen land type",
                 "opponent": "Chosen opponent", "player": "Chosen player", "card type": "Chosen card type",
                 "card type other than creature or land": "Chosen card type", "card type other than creature": "Chosen card type", "artifact, creature, enchantment, instant, or sorcery": "Chosen card type",
                 "number between 1 and 10": "Chosen number", "odd or even": "Chosen quality",  # (wave 49B: Talion, the Kindly Lord; wave 50J: Gollum, Riddle Master)
                 "two abilities from among first strike, vigilance, and lifelink": "Chosen abilities"}  # (wave 49B: Greymond, Avacyn's Stalwart)
CHOICE_OPTIONS["direction"] = ["left", "right"]
CHOICE_LABELS["direction"] = "Chosen direction"
CHOICE_LABELS.update(entry_forms.CHOICE_LABELS)  # -- entry forms (wave 5F) -- "a color other than blue"
CHOICE_LABELS.update({w: card_names.LABEL for w in (*card_names.ALL_WHATS, card_names.SECOND)})  # -- card names (wave 22B) -- 201.4


def _choice_options(plan: Plan, ctx: Context, what: str) -> list[DecisionOption]:
    from app.rules.creature_types import CREATURE_TYPES

    if card_names.is_choice(what):  # -- card names (wave 22B) -- typed, not listed (201.4)
        return [card_names.option(what)]
    from app.rules import static_perm100d  # -- static permanents (wave 100D) -- life paid

    if what == static_perm100d.LIFE_KEY:
        return [DecisionOption(id=str(n), label=str(n)) for n in range(static_perm100d.life_cap(plan, ctx) + 1)]
    if what.endswith(copying.TO_COPY):  # -- copy system (wave 2F): "enter as a copy of …" (707.5, 614.12a) --
        return copying.entry_options(plan, ctx["controller"], what, ctx.get("source_card"))  # (wave 5F: the entering card)
    if what == "creature type":
        return [DecisionOption(id=t, label=t) for t in sorted(CREATURE_TYPES)]
    if what == "number":  # -- chosen filters (wave 53B) -- 107.1b-c: any number, offered up to NUMBER_TOP; the instruction's own range narrows it (``options``)
        from app.rules import chosen as _chosen

        return [DecisionOption(id=str(n), label=str(n)) for n in range(_chosen.NUMBER_TOP + 1)]
    if what == "number between 1 and 10":  # (wave 49B) a number chosen as the permanent enters (614.12a)
        return [DecisionOption(id=str(n), label=str(n)) for n in range(1, 11)]
    if what.startswith("two abilities from among "):  # (wave 49B) every pair of the three (Greymond)
        from itertools import combinations

        return [DecisionOption(id=f"{a} and {b}", label=f"{a} and {b}") for a, b in combinations(("first strike", "vigilance", "lifelink"), 2)]
    from app.rules import chosen as _picked

    if (named := _picked.words(what)) is not None:  # -- linked words (wave 33B) -- 607.2f: "choose Khans or Dragons"
        return [DecisionOption(id=w, label=w) for w in named]
    if (others := entry_forms.color_options(what)) is not None:  # -- entry forms (wave 5F) --
        return [DecisionOption(id=v, label=v) for v in others]
    if what in ("opponent", "player"):
        pids = [p for p in plan.live() if what == "player" or p != ctx["controller"]]
        return [DecisionOption(id=p, label=plan.name(p)) for p in pids]
    if what == MOST_LIFE:  # -- block events (wave 53C) -- "Choose a player with the most life or tied for most life" (The Black Gate): life totals are public; with a tie, the choice is real
        top = max(plan.state.players[p].life for p in plan.live())
        return [DecisionOption(id=p, label=plan.name(p)) for p in plan.live() if plan.state.players[p].life == top]
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



def _bind_chosen_player(ctx: Context, pid: str) -> None:
    """-- block events (wave 53C) -- "Choose a player with the most life or tied for most life. Target creature can't be blocked by creatures that player controls": "that player" of the
    instructions after the choice is the player chosen (as bind_that_player does for a trigger's player)."""
    rest = json.dumps(ctx["effects"][ctx["next"]:]).replace('\\"controller\\":\\"that_player\\"', f'\\"controller\\":\\"player:{pid}\\"').replace('"event_player"', f'"player:{pid}"')
    ctx["effects"] = ctx["effects"][: ctx["next"]] + json.loads(rest)


def choose_value(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Choose a color / a creature type / a basic land type / an opponent / a player": the
    controller's public choice, bound under ``as`` as {"kind": "choice"}; with ``remember`` it is
    also written on the source object as its public ``choices`` entry ("Chosen color: Blue"):
    the record a permanent keeps of what was chosen as it entered (614.12a), gone with the object
    when it changes zones (400.7)."""
    if e.get("typed_min") is not None:
        from app.rules.group_choice import NUMBER

        options = [DecisionOption(id=NUMBER, label=f"Type a number ≥ {e['typed_min']}", group="number")]
    else:
        options = _choice_options(plan, ctx, e["what"])
    if e.get("options"):  # -- chosen type (wave 51C) -- "choose Elemental, Elf, …": only the creature types it lists
        options = [o for o in options if o.id in e["options"]]
    if e.get("noted110g"):  # -- (wave 110G) -- Long List of the Ents: 607.2e, only types not yet noted for this Saga (the record goes with the object, 400.7)
        from app.rules import wave110g_cards

        kept = plan.state.cards.get(ctx.get("source_card") or "")
        taken = set((kept.choices.get(wave110g_cards.NOTED) or "").split("|")) if kept is not None else set()
        options = [o for o in options if o.id not in taken]
    from app.rules import player_counter_instructions75

    options = player_counter_instructions75.remaining_players(plan, ctx, e, options)
    if not options:
        return True  # (no opponent left to choose: 800.4)
    if e["what"] == MOST_LIFE and len(options) == 1:  # (one player has the most life: nothing to choose)
        _bind_chosen_player(ctx, options[0].id)
        return True
    src = plan.state.cards.get(ctx.get("source_card") or "")
    article = "an" if e["what"][0] in "aeiou" else "a"
    chooser = _players(plan, ctx, e["who"])  # -- card names (wave 49C) -- "Target player chooses a card name": the target player (a target who left the game chooses nothing, 800.4)
    if not chooser:
        return True
    decide(plan, player=chooser[0], kind="choose_one", prompt=f"{ctx.get('name', '') or 'Choose'}: choose {article} {e['what']}",
           options=options, resume={"step": "choose_value", "ctx": ctx, "e": e}, source=src)
    return False


def resume_choose_value(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    value = chosen[0]
    shown = plan.name(value) if e["what"] in PLAYER_CHOICES else value
    if e["what"] == MOST_LIFE:
        _bind_chosen_player(ctx, value)
    plan.note(f"{plan.name(d.player)} chooses {shown} ({e['what']})", actor=d.player)
    if e.get("as"):
        context.refs(ctx)[e["as"]] = {"kind": "choice", "what": e["what"], "value": value,
                                      **({"players": [value]} if e["what"] in PLAYER_CHOICES else {})}  # (-- player-relative selectors (wave 53A) -- "Choose an opponent. That player …")
    if not e.get("remember") and (e["what"] in ("creature type", "color", "odd or even", "card type", "number") or card_names.is_choice(e["what"])):  # -- chosen type (wave 4J) -- (wave 53B: a card type)
        from app.rules import chosen as picked

        what = "card name" if card_names.is_choice(e["what"]) else e["what"]  # (wave 22B)
        rest = ctx["effects"][ctx["next"]:]
        cut = next((i for i, x in enumerate(rest) if x.get("do") == "choose_value" and x.get("what") == e["what"] and not x.get("remember")), len(rest))  # (wave 53B: down to the next choice of the same kind: a mode chosen twice, "Choose artifact or enchantment" in Season of Gathering, chooses twice)
        ctx["effects"] = ctx["effects"][: ctx["next"]] + picked.bind_effects(rest[:cut], what, value) + rest[cut:]
    src = plan.state.cards.get(ctx.get("source_card") or "")
    if e.get("noted110g") and src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == ctx.get("source_object"):
        from app.rules import wave110g_cards

        old = src.choices.get(wave110g_cards.NOTED)
        plan.do({"type": "set_choice", "card_id": src.id, "key": wave110g_cards.NOTED, "value": f"{old}|{value}" if old else value}, actor=d.player)
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
from app.rules import keyword_soup as _keyword_soup  # noqa: E402, I001  # -- keyword soups (wave 50J) --

PRIMITIVES["keyword_soup"] = _keyword_soup.soup
RESUME["keyword_soup"] = _keyword_soup.resume
RESUME["pick_counter"] = _counter_pick.resume
RESUME.update(_voting.RESUME)  # -- voting (wave 18C) --
RESUME.update(_tempting.RESUME)
RESUME.update(_friend_foe.RESUME)
RESUME.update(_group_choice.RESUME)  # -- group choices (wave 53D) --
RESUME.update(_pile_groups.RESUME)  # -- piles (wave 53D) --
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

    if e.get("action") == "search" and not ctx.get("search_performed"):
        return True
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

    if e.get("action") == "search":
        ctx.pop("search_performed", None)
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
    from app.rules import player_protection_grants

    e = {**e, "abilities": player_protection_grants.abilities(plan, ctx, list(e.get("abilities") or []))}
    from app.rules import derived_protection

    e = {**e, "abilities": derived_protection.bind_animation(plan, ctx, e["abilities"])}
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
        label = e.get("label") or _become_label(e, p, t)  # (-- reanimation Auras (wave 51F) -- ``label``: its own words)
        common: dict[str, Any] = {"affected": affected, "source": ctx.get("source_object"), "controller": ctx["controller"],
                                  "duration": duration, "label": f"{label} ({name})" if name else label}
        made: list[str] = []
        types = list(e.get("types") or [])
        lands = list(e.get("land_types") or ())  # -- land types set (wave 12D) -- 305.7: set, or added ("in addition", 205.1b)
        if types or e.get("creature_types") is not None or e.get("add_creature_types") or e.get("all_creature_types") \
                or e.get("legendary") or lands or e.get("remove_types") or e.get("remove_subtypes") or e.get("no_land_types110d"):
            made.append(layers.add_effect(plan, layer="4", **common,
                                          add_types=tuple(types) if e.get("retain") else (),
                                          set_types=None if e.get("retain") or not types else types,
                                          set_creature_types=e.get("creature_types"),
                                          set_artifact_types=e.get("artifact_types"),
                                          set_land_types=[] if e.get("no_land_types110d") else lands if lands and not e.get("retain") else None,  # (wave 110D: "loses all land types", 305.7)
                                          add_subtypes=(*(e.get("add_creature_types") or ()), *(lands if e.get("retain") else ())),
                                          remove_types=list(e.get("remove_types") or []),
                                          remove_subtypes=list(e.get("remove_subtypes") or []),
                                          all_creature_types=bool(e.get("all_creature_types")),
                                          add_supertypes=["Legendary"] if e.get("legendary") else []).id)
        if e.get("colors") is not None or e.get("add_colors"):
            made.append(layers.add_effect(plan, layer="5", **common, set_colors=e.get("colors"),
                                          add_colors=list(e.get("add_colors") or [])).id)
        if e.get("keywords") or e.get("abilities") or e.get("lose_abilities") or e.get("lose_index"):  # (-- licids (wave 50A) -- lose_index: "loses this ability", 613.1f)
            made.append(layers.add_effect(plan, layer="6", **common, add_keywords=tuple(e.get("keywords") or ()),
                                          add_abilities=list(e.get("abilities") or []), lose_index=list(e.get("lose_index") or ()),
                                          remove_abilities=bool(e.get("lose_abilities"))).id)
        if p is not None or t is not None:
            made.append(layers.add_effect(plan, layer="7b", **common, power=p, toughness=t).id)
        if duration in ("next_turn", "end_of_next_upkeep110g"):  # "until your next turn": whose, and from which turn (app/rules/delayed.py)
            for effect in plan.rules.effects:
                if effect.id in made:
                    effect.until_player, effect.turn = ctx["controller"], plan.state.turn.number
        elif duration.startswith("source_"):  # -- stack interaction (wave 23B) -- 611.2b: "for as long as ~ remains on the battlefield"
            for effect in plan.rules.effects:
                if effect.id in made:
                    effect.source_card, effect.until_player = ctx.get("source_card"), ctx["controller"]
        ctx["animated"] = [*ctx.get("animated", []), *made]  # (for a following "It's still a land.")
        markers: list[str] = []
        for cid in group:  # the table marker (cleared at cleanup for "until end of turn", 514.2; by a zone change, 400.7); (-- licids (wave 50A) -- ``marker``: its own words)
            markers += delayed.marker_ids(plan.do({"type": "add_effect", "card_ids": [cid], "name": label[:60],
                                                   "value": f"{p}/{t}" if p is not None and t is not None else None,
                                                   "text": e.get("marker") or _MARKER_TEXT.get(duration) or (delayed.LABELS[duration].replace("~", name or "its source")  # (review 23B: whose)
                                                           if duration.startswith("source_") else "as long as it's on the battlefield")}))
        for effect in plan.rules.effects:  # ending the effects removes these markers (app/rules/delayed.py)
            if effect.id in made:
                effect.markers = [*(effect.markers or []), *markers]
        for cid in group:
            plan.note(f"{plan.state.cards[cid].name or 'It'} becomes {label}"
                      + (f" {_MARKER_TEXT[duration]}" if duration in _MARKER_TEXT else ""), [cid], actor=ctx["controller"])
    return True


_MARKER_TEXT = {"end_of_turn": "until end of turn", "next_turn": delayed.LABELS["next_turn"], "end_of_combat": "this combat",
                "creature_cast110m": delayed.LABELS["creature_cast110m"], "roll1_110f": delayed.LABELS["roll1_110f"]}  # (wave 110M)  # (wave 49C: end_of_combat)
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
    if e.get("pick_added") and e["pick"] == "creature type":  # -- static permanents (wave 100D) -- "… in addition to its other types" (205.1b)
        more = {"add_creature_types": [chosen[0]]}
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
    if e.get("return110b"):  # -- one-card wordings (wave 110B) -- Cosmic Intervention: the exiled card comes back at the next end step (the spell is the rider's source)
        rec["return110b"] = ctx.get("source_card") or ""
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
    match = e["match"]
    if e.get("who") is not None:
        players = _players(plan, ctx, e["who"])
        if len(players) != 1:
            return True
        recipient: dict[str, Any] = {"pids": players}
        if e.get("include_controlled_permanents"):
            recipient["objects"] = {"sel": selectors.Selector(controller=f"player:{players[0]}").key()}
        match = {**match, "to": recipient}
    extra = {"until": "next_turn", "until_player": ctx["controller"]} if e.get("duration") == "next_turn" else {}
    op = {**e["op"], "n": int(e["op"]["n"]) + int(ctx.get("x") or 0)} if e["op"].get("x110b") else e["op"]  # -- one-card wordings (wave 110B) -- "plus X" (X paid)
    replace.add_record(plan, event=e["event"], match=match, op=op, controller=ctx["controller"],
                       source=ctx.get("source_object"), source_card=ctx.get("source_card"),
                       label=ctx.get("name") or "an effect", **extra)
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

    mana = _wave110i_cards.dawn_mana(plan, ctx["controller"], mana)  # -- cards (wave 110I) -- False Dawn

    ctx["_mana_added"] = {c: mana.count(c) for c in dict.fromkeys(mana)}  # (wave 3R3: "this mana", app/rules/kept_mana.py)
    ctx["_mana_added_player"] = pid  # (-- trigger other (wave 44B) -- whose pool: "that player adds {G}{G}{G}. … they don't lose this mana", Shizuko)
    ctx['_mana_pool_added'] = {}
    ctx['_mana_unit_ids'] = []
    if mana:
        delta: dict[str, int] = {}
        for c in mana:
            delta[c] = delta.get(c, 0) + 1
        from app.rules import mana_units

        before = {u.id for u in plan.state.players[pid].mana_units}
        plain_before = dict(plan.state.players[pid].mana)
        plan.do({"type": "rules_mana", "player": pid, "tap": [], "sacrifice": [], "life": 0,
                 **mana_units.from_context(plan, ctx, delta), "label": f"added {M.symbols(delta)}"[:200]}, actor=pid)
        ctx["_mana_unit_ids"] = [u.id for u in plan.state.players[pid].mana_units if u.id not in before]
        ctx['_mana_pool_added'] = {sym: n - plain_before.get(sym, 0)
                                  for sym, n in plan.state.players[pid].mana.items() if n > plain_before.get(sym, 0)}
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
    if e.get("chooser"):
        named = _players(plan, ctx, e["chooser"])
        if not named:
            return _return_cards(plan, ctx, e, [])
        pid = named[0]
    found = (_cards(plan, ctx, e["who"]) if e.get("who") else  # (-- wave 22D -- "a creature card put into a graveyard this way")
             selectors.candidates(plan, selectors.from_key(e["sel"]), pid, ctx.get("source_card")))
    # -- reanimation (wave 37B) -- "the top creature card of your graveyard": the last matching card of the graveyard's order (index -1 is the top), nothing chosen
    if e.get("exclude"):  # -- if you do (wave 52A) -- "return another permanent card" after "sacrificed a creature this way": not the card just sacrificed (Rise of the Witch-king)
        found = [c for c in found if c not in context.objects(plan, ctx, e["exclude"])]
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
    if want <= 0:
        # Announced X=0 is public: the hidden hand cannot make a land selectable.
        return _return_cards(plan, ctx, e, [])
    # -- reanimation (wave 37B) -- "from your hand or graveyard": the hand is hidden, so a hand that holds cards is asked whether or not one of them
    # matches (put_from_hand's rule, review 25C): the other players must not learn from the question that a matching card is there
    hidden = not e.get("who") and "hand" in selectors.from_key(e["sel"]).zones and bool(plan.state.zones.get(f"{pid}:hand"))
    if not hidden and (most == 0 or (least == most == len(pool))):
        return _return_cards(plan, ctx, e, pool[:most])
    decide(plan, player=pid, kind="choose_cards",
           prompt=f"Choose {'up to ' if e.get('upto') else ''}{max(most, 1) if hidden else most} ({e.get('label', 'card')})" + {"exile": " to exile", "choose": ""}.get(e["to"], " to return")
           + (f" with total mana value {e['total_mv']} or less" if e.get("total_mv") is not None else ""),
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in pool],
           min_choices=least, max_choices=max(most, 1) if hidden else most, resume={"step": "return_choice", "ctx": ctx, "e": e})
    return False


def _within_total(plan: Plan, e: dict[str, Any], cards: list[str]) -> None:
    """-- total mana value (wave 51A) -- "up to two creature cards with total mana value 6 or less": checked as the cards are chosen (608.2d)."""
    from app.game.errors import ActionError
    from app.rules.targets import _total

    if e.get("total_mv") is not None and _total(plan, cards, "mana_value") > e["total_mv"]:
        raise ActionError(f"Those cards must have total mana value {e['total_mv']} or less")


def resume_return_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    pool = set(_cards(plan, ctx, e["who"]) if e.get("who") else
               selectors.candidates(plan, selectors.from_key(e["sel"]), d.player if e.get("chooser") else ctx["controller"], ctx.get("source_card")))
    if e.get("exclude"):
        pool -= set(context.objects(plan, ctx, e["exclude"]))
    cards = [c for c in chosen if c in pool]  # (still there and still matching)
    _within_total(plan, e, cards)
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


PRIMITIVES.update({"gain_control": _did_r1(gain_control, "control"), "exchange_control": exchange_control})  # (wave 50C: "If they do")
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
RESUME["draw_upto"] = resume_draw_upto  # (wave 51B)
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
# -- random choices (wave 47B): app/rules/random_choice.py (a leaf module over this one) --
from app.rules import random_choice  # noqa: E402, I001

PRIMITIVES.update(random_choice.PRIMITIVES)
RESUME.update(random_choice.RESUME)
# -- end counters & designations (wave 3E) --
from app.rules import graveyard_bottom as _graveyard_bottom  # noqa: E402, I001  -- trigger other (wave 52B) --

from app.rules import reveal_until_gy as _reveal_until_gy  # noqa: E402, I001
from app.rules import top_trade as _top_trade  # noqa: E402, I001

PRIMITIVES.update(_reveal_until_gy.PRIMITIVES)  # Consuming Aberration (app/rules/reveal_until_gy.py)

PRIMITIVES.update(_top_trade.PRIMITIVES)  # Keen Duelist, Parker Luck, Duskmantle Seer (app/rules/top_trade.py)
PRIMITIVES.update(_graveyard_bottom.PRIMITIVES)  # "puts all the cards from their graveyard on the bottom of their library in a random order" (app/rules/graveyard_bottom.py)

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
RESUME.update(_end_turn.RESUME)
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
from app.rules import hand_library_exchange as _hand_library_exchange  # noqa: E402

PRIMITIVES.update(_hand_library_exchange.PRIMITIVES)

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
PRIMITIVES.update(block_events.PRIMITIVES)  # -- block events (wave 53C) -- an effect making an attacker become blocked
from app.rules import decayed as _decayed  # noqa: E402, I001  (702.147: decayed's sacrifice at end of combat)

PRIMITIVES.update(_decayed.PRIMITIVES)
# -- end token & pump wordings (wave 6C) --
from app.rules import player_choices as _player_choices  # noqa: E402, I001  -- player-relative selectors (wave 53A) --

PRIMITIVES.update(_player_choices.PRIMITIVES)
RESUME.update(_player_choices.RESUME)

# -- token copies & attach on entry (wave 5J) -- "attach it to target creature you control" (app/rules/attach_entry.py),
# populate and "for each …, create a token that's a copy of that …" (app/rules/populate.py)
from app.rules import attach_entry as _attach_entry  # noqa: E402, I001

PRIMITIVES.update(_attach_entry.PRIMITIVES)
RESUME.update(_attach_entry.RESUME)  # (wave 25A: attach_choose)
from app.rules import haunt as _haunt  # noqa: E402, I001  -- haunt (wave 50H) --
from app.rules import paradigm as _paradigm  # noqa: E402, I001  -- paradigm (wave 50H) --

PRIMITIVES.update(_haunt.PRIMITIVES)
PRIMITIVES.update(_paradigm.PRIMITIVES)
from app.rules import licids as _licids  # noqa: E402, I001  -- licids (wave 50A) --

PRIMITIVES["licid"] = _licids.licid
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
RESUME.update(_coin_flips.RESUME)
from app.rules import coin_outcomes as _coin_outcomes  # noqa: E402, I001

RESUME.update(_coin_outcomes.RESUME)
from app.rules import coin_recipes as _coin_recipes  # noqa: E402, I001

PRIMITIVES.update(_coin_recipes.PRIMITIVES)
RESUME.update(_coin_recipes.RESUME)
from app.rules import clash as _clash  # noqa: E402, I001  -- clash (wave 12A)

PRIMITIVES.update(_clash.PRIMITIVES)
RESUME[_clash.STEP] = _clash.resume
from app.rules import dice as _dice  # noqa: E402, I001  -- rolling dice (wave 12A)

PRIMITIVES.update(_dice.PRIMITIVES)
RESUME[_dice.STEP] = _dice.resume
RESUME["roll_group_continue"] = _dice.resume_group
RESUME["roll_ignore110g"] = _dice.resume_ignore
from app.rules import counter_moves as _counter_moves  # noqa: E402, I001  -- moving counters (wave 12A)

PRIMITIVES.update(_counter_moves.PRIMITIVES)
RESUME[_counter_moves.STEP] = _counter_moves.resume

from app.rules import counter_move_distribution as _counter_distribution  # noqa: E402, I001

PRIMITIVES.update(_counter_distribution.PRIMITIVES)
RESUME[_counter_distribution.STEP] = _counter_distribution.resume

from app.rules import proliferate_followup as _proliferate_followup  # noqa: E402, I001

PRIMITIVES.update(_proliferate_followup.PRIMITIVES)
RESUME[_proliferate_followup.STEP] = _proliferate_followup.resume
replace.THEN["record_proliferate_counters"] = _proliferate_followup.record

from app.rules import name_exile_loop as _name_exile_loop  # noqa: E402, I001

PRIMITIVES.update(_name_exile_loop.PRIMITIVES)
RESUME[_name_exile_loop.STEP] = _name_exile_loop.resume

from app.rules import named_recast as _named_recast  # noqa: E402, I001

PRIMITIVES.update(_named_recast.PRIMITIVES)

from app.rules import loyalty_survivors as _loyalty_survivors  # noqa: E402, I001

PRIMITIVES.update(_loyalty_survivors.PRIMITIVES)
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
RESUME.update(_hand_wheel.RESUME)  # (wave 51B)
# -- trigger other (wave 25B) -- join forces (app/rules/join_forces.py)
from app.rules import join_forces as _join_forces  # noqa: E402, I001

PRIMITIVES.update(_join_forces.PRIMITIVES)
# -- cast riders (wave 25C) -- "When you next cast a creature spell this turn, that creature enters with an additional +1/+1 counter on it."
from app.rules import cast_riders as _cast_riders  # noqa: E402, I001

PRIMITIVES.update(_cast_riders.PRIMITIVES)
# -- cast riders (wave 38C) -- "exile it instead of putting it into your graveyard as it resolves", "it becomes plotted" (app/rules/resolve_exile.py)
from app.rules import resolve_exile as _resolve_exile  # noqa: E402, I001

PRIMITIVES.update(_resolve_exile.PRIMITIVES)
RESUME.update(_resolve_exile.RESUME)
# -- pay to untap (wave 25C) -- Dream Tides, Mudslide (app/rules/pay_untap.py)
from app.rules import pay_untap as _pay_untap  # noqa: E402, I001

PRIMITIVES.update(_pay_untap.PRIMITIVES)
RESUME[_pay_untap.STEP] = _pay_untap.resume
# -- spell grants (wave 28C) -- "The next spell you cast this turn has improvise." (app/rules/spell_grants.py)
from app.rules import spell_grants as _spell_grants  # noqa: E402, I001

PRIMITIVES.update(_spell_grants.PRIMITIVES)
# -- activated other (wave 52D) -- the edge of a graveyard or library, and more (app/rules/activated52d.py)
from app.rules import activated52d as _activated52d  # noqa: E402, I001

PRIMITIVES.update(_activated52d.PRIMITIVES)

# CR 903.11: ordinary outside-game permissions, with an explicit fallback in other formats.
from app.rules import outside_game as _outside_game  # noqa: E402, I001

PRIMITIVES["outside_permission"] = _outside_game.permission

from app.rules import shared_damage as _shared_damage  # noqa: E402, I001

PRIMITIVES.update(_shared_damage.PRIMITIVES)
RESUME.update(_shared_damage.RESUME)


from app.rules import hexproof_targeting as _hexproof_targeting  # noqa: E402, I001

PRIMITIVES.update(_hexproof_targeting.PRIMITIVES)

from app.rules import optional_event_tap as _optional_event_tap  # noqa: E402

PRIMITIVES.update(_optional_event_tap.PRIMITIVES)
RESUME[_optional_event_tap.STEP] = _optional_event_tap.resume

from app.rules import shared_permanent_return as _shared_permanent_return  # noqa: E402

PRIMITIVES.update(_shared_permanent_return.PRIMITIVES)
RESUME[_shared_permanent_return.STEP] = _shared_permanent_return.resume


from app.rules import damage_controller_destruction as _damage_controller_destruction  # noqa: E402, I001

PRIMITIVES.update(_damage_controller_destruction.PRIMITIVES)


from app.rules import ability_mana_history as _ability_mana_history  # noqa: E402, I001

PRIMITIVES.update(_ability_mana_history.PRIMITIVES)


from app.rules import token_fight_pairs as _token_fight_pairs  # noqa: E402, I001

PRIMITIVES.update(_token_fight_pairs.PRIMITIVES)
RESUME[_token_fight_pairs.STEP] = _token_fight_pairs.resume

from app.rules import simultaneous_moves as _simultaneous_moves  # noqa: E402, I001

PRIMITIVES.update(_simultaneous_moves.PRIMITIVES)
RESUME.update(_simultaneous_moves.RESUME)


# CR 608.2c/g/h: counter, random mill, differently named free cast, then cleanup.
from app.rules import counter_random_recast as _counter_random_recast  # noqa: E402, I001

PRIMITIVES.update(_counter_random_recast.PRIMITIVES)

from app.rules import optional_repeat_roll as _optional_repeat_roll  # noqa: E402, I001

PRIMITIVES.update(_optional_repeat_roll.PRIMITIVES)
RESUME.update(_optional_repeat_roll.RESUME)


from app.rules import discover_followup as _discover_followup  # noqa: E402, I001

PRIMITIVES.update(_discover_followup.PRIMITIVES)


from app.rules import player_counter_top_up as _player_counter_top_up  # noqa: E402, I001

PRIMITIVES.update(_player_counter_top_up.PRIMITIVES)

from app.rules import mill_pair_repeat as _mill_pair_repeat  # noqa: E402, I001

PRIMITIVES.update(_mill_pair_repeat.PRIMITIVES)
RESUME.update(_mill_pair_repeat.RESUME)


from app.rules import attached_copy_fallback as _attached_copy_fallback  # noqa: E402, I001

PRIMITIVES.update(_attached_copy_fallback.PRIMITIVES)


from app.rules import harness as _harness  # noqa: E402, I001

PRIMITIVES.update(_harness.PRIMITIVES)

from app.rules import paid_effect_costs as _paid_effect_costs  # noqa: E402, I001

RESUME.update(_paid_effect_costs.RESUME)


from app.rules import linked_attachment_return as _linked_attachment_return  # noqa: E402

PRIMITIVES.update(_linked_attachment_return.PRIMITIVES)
RESUME.update(_linked_attachment_return.RESUME)


from app.rules import conditional_repeat_search as _conditional_repeat_search  # noqa: E402, I001

PRIMITIVES.update(_conditional_repeat_search.PRIMITIVES)
RESUME.update(_conditional_repeat_search.RESUME)


from app.rules import conditional_return_destination as _conditional_return_destination  # noqa: E402, I001

PRIMITIVES.update(_conditional_return_destination.PRIMITIVES)
RESUME.update(_conditional_return_destination.RESUME)


from app.rules import exile_land_compensation as _exile_land_compensation  # noqa: E402, I001

PRIMITIVES.update(_exile_land_compensation.PRIMITIVES)


from app.rules import chosen_library_kind as _chosen_library_kind  # noqa: E402, I001

PRIMITIVES.update(_chosen_library_kind.PRIMITIVES)
RESUME.update(_chosen_library_kind.RESUME)


from app.rules import delayed_fewer_counters as _delayed_fewer_counters  # noqa: E402, I001

PRIMITIVES.update(_delayed_fewer_counters.PRIMITIVES)


from app.rules import destroy_type_reveal as _destroy_type_reveal  # noqa: E402, I001

PRIMITIVES.update(_destroy_type_reveal.PRIMITIVES)


from app.rules import reveal_hand_or_top as _reveal_hand_or_top  # noqa: E402, I001

PRIMITIVES.update(_reveal_hand_or_top.PRIMITIVES)
RESUME.update(_reveal_hand_or_top.RESUME)


from app.rules import exile_delayed_damage as _exile_delayed_damage  # noqa: E402, I001

PRIMITIVES.update(_exile_delayed_damage.PRIMITIVES)


from app.rules import descendants_path as _descendants_path  # noqa: E402, I001

PRIMITIVES.update(_descendants_path.PRIMITIVES)

from app.rules import received_counter_doubling as _received_counter_doubling  # noqa: E402, I001

PRIMITIVES.update(_received_counter_doubling.PRIMITIVES)

from app.rules import player_counter_doubling as _player_counter_doubling  # noqa: E402, I001

PRIMITIVES.update(_player_counter_doubling.PRIMITIVES)


from app.rules import exchange_energy as _exchange_energy  # noqa: E402, I001

PRIMITIVES.update(_exchange_energy.PRIMITIVES)


from app.rules import armored_skyhunter as _armored_skyhunter  # noqa: E402, I001

PRIMITIVES.update(_armored_skyhunter.PRIMITIVES)
RESUME.update(_armored_skyhunter.RESUME)


from app.rules import capped_counters as _capped_counters  # noqa: E402, I001

PRIMITIVES["capped_counters"] = _capped_counters.run
RESUME["capped_counters"] = _capped_counters.resume


from app.rules import exert_equipment as _exert_equipment  # noqa: E402, I001

PRIMITIVES.update(_exert_equipment.PRIMITIVES)

from app.rules import conditional_search_destination as _conditional_search_destination  # noqa: E402, I001

RESUME.update(_conditional_search_destination.RESUME)


from app.rules import plargg_nassari as _plargg_nassari  # noqa: E402, I001

PRIMITIVES.update(_plargg_nassari.PRIMITIVES)
RESUME.update(_plargg_nassari.RESUME)


from app.rules import grouped_discard as _grouped_discard  # noqa: E402, I001

RESUME.update(_grouped_discard.RESUME)

from app.rules import equipment_unattach_choice as _equipment_unattach_choice  # noqa: E402, I001

PRIMITIVES.update(_equipment_unattach_choice.PRIMITIVES)
RESUME.update(_equipment_unattach_choice.RESUME)

from app.rules import exile_mv_threshold as _exile_mv_threshold  # noqa: E402, I001

PRIMITIVES.update(_exile_mv_threshold.PRIMITIVES)


from app.rules import counter_offers as _counter_offers  # noqa: E402, I001

PRIMITIVES.update(_counter_offers.PRIMITIVES)
RESUME.update(_counter_offers.RESUME)


from app.rules import counter_choice_effects as _counter_choice_effects  # noqa: E402, I001

PRIMITIVES.update(_counter_choice_effects.PRIMITIVES)
RESUME.update(_counter_choice_effects.RESUME)


from app.rules import capped_damage_life as _capped_damage_life  # noqa: E402, I001

PRIMITIVES.update(_capped_damage_life.PRIMITIVES)
RESUME.update(_capped_damage_life.RESUME)

from app.rules import player_protection_grants as _player_protection_grants  # noqa: E402

PRIMITIVES.update(_player_protection_grants.PRIMITIVES)

from app.rules import derived_protection as _derived_protection  # noqa: E402

PRIMITIVES.update(_derived_protection.PRIMITIVES)


from app.rules import counter_group_choices as _counter_group_choices  # noqa: E402, I001

PRIMITIVES.update(_counter_group_choices.PRIMITIVES)
RESUME.update(_counter_group_choices.RESUME)

from app.rules import library_look as _library_look  # noqa: E402

PRIMITIVES.update(_library_look.PRIMITIVES)


from app.rules import counter_distribution as _untargeted_counter_distribution  # noqa: E402, I001

PRIMITIVES.update(_untargeted_counter_distribution.PRIMITIVES)
RESUME.update(_untargeted_counter_distribution.RESUME)

from app.rules import opponent_looked_choice as _opponent_looked_choice  # noqa: E402

PRIMITIVES.update(_opponent_looked_choice.PRIMITIVES)


from app.rules import source_quality_grants as _source_quality_grants  # noqa: E402

PRIMITIVES.update(_source_quality_grants.PRIMITIVES)


from app.rules import counter_arithmetic as _counter_arithmetic  # noqa: E402, I001

PRIMITIVES.update(_counter_arithmetic.PRIMITIVES)

from app.rules import land_or_cast as _land_or_cast  # noqa: E402

PRIMITIVES.update(_land_or_cast.PRIMITIVES)

from app.rules import temporary_hand_exile as _temporary_hand_exile  # noqa: E402

PRIMITIVES.update(_temporary_hand_exile.PRIMITIVES)

from app.rules import group_counter_values as _group_counter_values  # noqa: E402, I001

PRIMITIVES.update(_group_counter_values.PRIMITIVES)

from app.rules import search_partition as _search_partition  # noqa: E402

PRIMITIVES.update(_search_partition.PRIMITIVES)
RESUME.update(_search_partition.RESUME)

from app.rules import counter_upkeep_payments as _counter_upkeep_payments  # noqa: E402, I001

PRIMITIVES.update(_counter_upkeep_payments.PRIMITIVES)
RESUME.update(_counter_upkeep_payments.RESUME)

from app.rules import optional_library_look as _optional_library_look  # noqa: E402

PRIMITIVES.update(_optional_library_look.PRIMITIVES)

from app.rules import activated_copy_effects as _activated_copy_effects  # noqa: E402

PRIMITIVES.update(_activated_copy_effects.PRIMITIVES)

from app.rules import linked_exile_look as _linked_exile_look  # noqa: E402

PRIMITIVES.update(_linked_exile_look.PRIMITIVES)

from app.rules import linked_play_grants as _linked_play_grants  # noqa: E402

PRIMITIVES.update(_linked_play_grants.PRIMITIVES)

from app.rules import foreign_zone_sequences as _foreign_zone_sequences  # noqa: E402

PRIMITIVES.update(_foreign_zone_sequences.PRIMITIVES)
RESUME.update(_foreign_zone_sequences.RESUME)

from app.rules import qualified_search_packets as _qualified_search_packets  # noqa: E402

PRIMITIVES.update(_qualified_search_packets.PRIMITIVES)
RESUME.update(_qualified_search_packets.RESUME)

from app.rules import linked_returns as _linked_returns  # noqa: E402

PRIMITIVES.update(_linked_returns.PRIMITIVES)

from app.rules import resolved_library_guesses as _resolved_library_guesses  # noqa: E402

PRIMITIVES.update(_resolved_library_guesses.PRIMITIVES)

from app.rules import reveal_outcomes as _reveal_outcomes  # noqa: E402

PRIMITIVES.update(_reveal_outcomes.PRIMITIVES)

from app.rules import conditional_tutor_outcomes as _conditional_tutor_outcomes  # noqa: E402

PRIMITIVES.update(_conditional_tutor_outcomes.PRIMITIVES)
RESUME.update(_conditional_tutor_outcomes.RESUME)

from app.rules import exile_permission_sequences as _exile_permission_sequences  # noqa: E402

PRIMITIVES.update(_exile_permission_sequences.PRIMITIVES)
RESUME.update(_exile_permission_sequences.RESUME)

from app.rules import suspended_counter_choices as _suspended_counter_choices  # noqa: E402

PRIMITIVES.update(_suspended_counter_choices.PRIMITIVES)
RESUME.update(_suspended_counter_choices.RESUME)


from app.rules import paid_sacrifice_effects as _paid_sacrifice_effects  # noqa: E402, I001

PRIMITIVES["source_emerge_tokens"] = _paid_sacrifice_effects.source_emerge_tokens
RESUME.update(_paid_sacrifice_effects.RESUME)

from app.rules import linked_aggregates as _linked_aggregates  # noqa: E402

PRIMITIVES.update(_linked_aggregates.PRIMITIVES)
RESUME.update(_linked_aggregates.RESUME)

from app.rules import name_equivalence_sequences as _name_equivalence_sequences  # noqa: E402

PRIMITIVES.update(_name_equivalence_sequences.PRIMITIVES)

from app.rules import qualified_attached_tutors as _qualified_attached_tutors  # noqa: E402

PRIMITIVES.update(_qualified_attached_tutors.PRIMITIVES)
RESUME.update(_qualified_attached_tutors.RESUME)

from app.rules import reveal_snapshots as _reveal_snapshots  # noqa: E402

PRIMITIVES.update(_reveal_snapshots.PRIMITIVES)

from app.rules import conditional_copy_sources as _conditional_copy_sources  # noqa: E402
from app.rules import token_copy_sources as _token_copy_sources  # noqa: E402
from app.rules import token_source_groups as _token_source_groups  # noqa: E402

PRIMITIVES.update(_token_copy_sources.PRIMITIVES)
PRIMITIVES.update(_token_source_groups.PRIMITIVES)
PRIMITIVES.update(_conditional_copy_sources.PRIMITIVES)

from app.rules import suspend_grant_followthrough as _suspend_grant_followthrough  # noqa: E402

PRIMITIVES.update(_suspend_grant_followthrough.PRIMITIVES)
RESUME.update(_suspend_grant_followthrough.RESUME)


from app.rules import attack_destinations as _attack_destinations  # noqa: E402

PRIMITIVES.update(_attack_destinations.PRIMITIVES)


from app.rules import hidden_card_facts as _hidden_card_facts  # noqa: E402, I001

PRIMITIVES.update(_hidden_card_facts.PRIMITIVES)
RESUME.update(_hidden_card_facts.RESUME)

RESUME.update(_token_copy_sources.RESUME)

from app.rules import reveal_consequences as _reveal_consequences  # noqa: E402

PRIMITIVES.update(_reveal_consequences.PRIMITIVES)

from app.rules import name_relation_continuations as _name_relation_continuations  # noqa: E402

PRIMITIVES.update(_name_relation_continuations.PRIMITIVES)
RESUME.update(_name_relation_continuations.RESUME)

from app.rules import nontarget_creature_choices as _nontarget_creature_choices  # noqa: E402

PRIMITIVES.update(_nontarget_creature_choices.PRIMITIVES)


from app.rules import card_copy_sources as _card_copy_sources  # noqa: E402

PRIMITIVES.update(_card_copy_sources.PRIMITIVES)
RESUME.update(_card_copy_sources.RESUME)

from app.rules import ordered_tutor_continuations as _ordered_tutor_continuations  # noqa: E402

PRIMITIVES.update(_ordered_tutor_continuations.PRIMITIVES)
RESUME.update(_ordered_tutor_continuations.RESUME)


from app.rules import discard_outcomes as _discard_outcomes  # noqa: E402, I001

PRIMITIVES.update(_discard_outcomes.PRIMITIVES)

from app.rules import upkeep_reveal_consequences as _upkeep_reveal_consequences  # noqa: E402

PRIMITIVES.update(_upkeep_reveal_consequences.PRIMITIVES)

from app.rules import reveal_target_sequences as _reveal_target_sequences  # noqa: E402

PRIMITIVES.update(_reveal_target_sequences.PRIMITIVES)
RESUME.update(_reveal_target_sequences.RESUME)


from app.rules import attack_reveal_fight as _attack_reveal_fight  # noqa: E402

PRIMITIVES.update(_attack_reveal_fight.PRIMITIVES)

from app.rules import spent_mana_outcomes as _spent_mana_outcomes  # noqa: E402, I001

PRIMITIVES.update(_spent_mana_outcomes.PRIMITIVES)

from app.rules import name_event_receipts as _name_event_receipts  # noqa: E402

PRIMITIVES.update(_name_event_receipts.PRIMITIVES)
RESUME.update(_name_event_receipts.RESUME)

from app.rules import controller_tutors as _controller_tutors  # noqa: E402

PRIMITIVES.update(_controller_tutors.PRIMITIVES)
RESUME.update(_controller_tutors.RESUME)

from app.rules import bound_subset_choices as _bound_subset_choices  # noqa: E402

PRIMITIVES.update(_bound_subset_choices.PRIMITIVES)

from app.rules import revealed_two_stage_picks as _revealed_two_stage_picks  # noqa: E402, I001

PRIMITIVES.update(_revealed_two_stage_picks.PRIMITIVES)
RESUME.update(_revealed_two_stage_picks.RESUME)

from app.rules import qualified_look_outcomes as _qualified_look_outcomes  # noqa: E402

PRIMITIVES.update(_qualified_look_outcomes.PRIMITIVES)

from app.rules import look_optional_placement as _look_optional_placement  # noqa: E402

PRIMITIVES.update(_look_optional_placement.PRIMITIVES)

from app.rules import private_top_card_outcomes as _private_top_card_outcomes  # noqa: E402, I001

PRIMITIVES.update(_private_top_card_outcomes.PRIMITIVES)

from app.rules import attached_kindred_look as _attached_kindred_look  # noqa: E402

PRIMITIVES.update(_attached_kindred_look.PRIMITIVES)

from app.rules import scoped_prevention_effects as _scoped_prevention_effects  # noqa: E402

PRIMITIVES.update(_scoped_prevention_effects.PRIMITIVES)

from app.rules import activated_card_outcomes as _activated_card_outcomes  # noqa: E402

PRIMITIVES.update(_activated_card_outcomes.PRIMITIVES)
RESUME.update(_activated_card_outcomes.RESUME)

from app.rules import immediate_mana_resolutions as _immediate_mana_resolutions  # noqa: E402, I001

PRIMITIVES.update(_immediate_mana_resolutions.PRIMITIVES)
RESUME.update(_immediate_mana_resolutions.RESUME)

from app.rules import casting_timing_permissions as _casting_timing_permissions  # noqa: E402

PRIMITIVES.update(_casting_timing_permissions.PRIMITIVES)

from app.rules import qualified_selection_packets as _qualified_selection_packets  # noqa: E402

PRIMITIVES.update(_qualified_selection_packets.PRIMITIVES)
RESUME.update(_qualified_selection_packets.RESUME)

from app.rules import conditional_prevention_effects as _conditional_prevention_effects  # noqa: E402

PRIMITIVES.update(_conditional_prevention_effects.PRIMITIVES)

from app.rules import reveal_cast_packets as _reveal_cast_packets  # noqa: E402

PRIMITIVES.update(_reveal_cast_packets.PRIMITIVES)

from app.rules import contextual_mana_outcomes as _contextual_mana_outcomes  # noqa: E402, I001

PRIMITIVES.update(_contextual_mana_outcomes.PRIMITIVES)
RESUME.update(_contextual_mana_outcomes.RESUME)

from app.rules import token_copy_outcomes as _token_copy_outcomes  # noqa: E402

PRIMITIVES.update(_token_copy_outcomes.PRIMITIVES)

from app.rules import damage_snapshot_outcomes as _damage_snapshot_outcomes  # noqa: E402

PRIMITIVES.update(_damage_snapshot_outcomes.PRIMITIVES)

from app.rules import damage_redirection_effects as _damage_redirection_effects  # noqa: E402

PRIMITIVES.update(_damage_redirection_effects.PRIMITIVES)

from app.rules import token_copy_continuations as _token_copy_continuations  # noqa: E402

PRIMITIVES.update(_token_copy_continuations.PRIMITIVES)

from app.rules import single_recipient_redirection as _single_recipient_redirection  # noqa: E402

RESUME.update(_single_recipient_redirection.RESUME)

from app.rules import damage_history_outcomes as _damage_history_outcomes  # noqa: E402

PRIMITIVES.update(_damage_history_outcomes.PRIMITIVES)

from app.rules import life_history_outcomes as _life_history_outcomes  # noqa: E402

PRIMITIVES.update(_life_history_outcomes.PRIMITIVES)

from app.rules import draw_replacement_sequences as _draw_replacement_sequences  # noqa: E402

PRIMITIVES.update(_draw_replacement_sequences.PRIMITIVES)
RESUME.update(_draw_replacement_sequences.RESUME)


from app.rules import random_consequences as _random_consequences  # noqa: E402

PRIMITIVES.update(_random_consequences.PRIMITIVES)
RESUME.update(_random_consequences.RESUME)

from app.rules import contextual_mana_triggers as _contextual_mana_triggers  # noqa: E402

PRIMITIVES.update(_contextual_mana_triggers.PRIMITIVES)
RESUME.update(_contextual_mana_triggers.RESUME)

# Immediate prevention bodies can suspend without completing the original damage caller.
from app.rules import damage_rider_continuations as _damage_rider_continuations  # noqa: E402, F401
from app.rules import life_game_history as _life_game_history  # noqa: E402

PRIMITIVES.update(_life_game_history.PRIMITIVES)

from app.rules import exile_packet_continuations as _exile_packet_continuations  # noqa: E402

PRIMITIVES.update(_exile_packet_continuations.PRIMITIVES)

from app.rules import random_receipt_consumers as _random_receipt_consumers  # noqa: E402

PRIMITIVES.update(_random_receipt_consumers.PRIMITIVES)
RESUME.update(_random_receipt_consumers.RESUME)

from app.rules import prevention_outcomes as _prevention_outcomes  # noqa: E402

PRIMITIVES.update(_prevention_outcomes.PRIMITIVES)

from app.rules import mana_resolution_profiles as _mana_resolution_profiles  # noqa: E402
from app.rules import mana_symbol_production as _mana_symbol_production  # noqa: E402

PRIMITIVES.update(_mana_resolution_profiles.PRIMITIVES)
RESUME.update(_mana_resolution_profiles.RESUME)

from app.rules import mana_codie_profiles as _mana_codie_profiles  # noqa: E402

PRIMITIVES.update(_mana_codie_profiles.PRIMITIVES)
RESUME.update(_mana_codie_profiles.RESUME)
PRIMITIVES.update(_mana_symbol_production.PRIMITIVES)
RESUME.update(_mana_symbol_production.RESUME)

from app.rules import mana_named_land_profiles as _mana_named_land_profiles  # noqa: E402

PRIMITIVES.update(_mana_named_land_profiles.PRIMITIVES)

from app.rules import mana_class_profiles as _mana_class_profiles  # noqa: E402

PRIMITIVES.update(_mana_class_profiles.PRIMITIVES)

from app.rules import mana_linked_profiles as _mana_linked_profiles  # noqa: E402

PRIMITIVES.update(_mana_linked_profiles.PRIMITIVES)

from app.rules import mana_crafted_profiles as _mana_crafted_profiles  # noqa: E402

PRIMITIVES.update(_mana_crafted_profiles.PRIMITIVES)
RESUME.update(_mana_crafted_profiles.RESUME)

from app.rules import multiplayer_roll_consumers as _multiplayer_roll_consumers  # noqa: E402

PRIMITIVES.update(_multiplayer_roll_consumers.PRIMITIVES)

from app.rules import life_card_outcomes41 as _life_card_outcomes41  # noqa: E402

PRIMITIVES.update(_life_card_outcomes41.PRIMITIVES)

# Interpreter/resumes are generic prerequisites; canonical recipe admission is separate.
from app.rules import random_choice_receipts as _random_choice_receipts  # noqa: E402

PRIMITIVES.update(_random_choice_receipts.PRIMITIVES)
from app.rules import random_native_outcomes42 as _random_native_outcomes42  # noqa: E402, I001

PRIMITIVES.update(_random_native_outcomes42.PRIMITIVES)
RESUME.update(_random_choice_receipts.RESUME)

from app.rules import random_characteristic_choices as _random_characteristic_choices  # noqa: E402

PRIMITIVES.update(_random_characteristic_choices.PRIMITIVES)

from app.rules import counter_outcomes42 as _counter_outcomes42  # noqa: E402

PRIMITIVES.update(_counter_outcomes42.PRIMITIVES)

from app.rules import copiable_coin_entry as _copiable_coin_entry  # noqa: E402

PRIMITIVES.update(_copiable_coin_entry.PRIMITIVES)

from app.rules import immortal_coil_outcomes as _immortal_coil_outcomes  # noqa: E402

PRIMITIVES.update(_immortal_coil_outcomes.PRIMITIVES)

from app.rules import counter_payments42 as _counter_payments42  # noqa: E402

PRIMITIVES.update(_counter_payments42.PRIMITIVES)
RESUME.update(_counter_payments42.RESUME)

from app.rules import mana_foundry_profiles as _mana_foundry_profiles  # noqa: E402

PRIMITIVES.update(_mana_foundry_profiles.PRIMITIVES)

from app.rules import mana_temporary_profiles as _mana_temporary_profiles  # noqa: E402

PRIMITIVES.update(_mana_temporary_profiles.PRIMITIVES)

from app.rules import mana_esper_profiles as _mana_esper_profiles  # noqa: E402

PRIMITIVES.update(_mana_esper_profiles.PRIMITIVES)
RESUME.update(_mana_esper_profiles.RESUME)

from app.rules import mana_combat_packet_profiles as _mana_combat_packet_profiles  # noqa: E402

PRIMITIVES.update(_mana_combat_packet_profiles.PRIMITIVES)

from app.rules import returned_counter_choices42 as _returned_counter_choices42  # noqa: E402

PRIMITIVES.update(_returned_counter_choices42.PRIMITIVES)
RESUME.update(_returned_counter_choices42.RESUME)

from app.rules import exile_authority_continuations as _exile_authority_continuations  # noqa: E402

PRIMITIVES.update(_exile_authority_continuations.PRIMITIVES)
RESUME.update(_exile_authority_continuations.RESUME)

from app.rules import sacrificed_equipment42 as _sacrificed_equipment42  # noqa: E402

PRIMITIVES.update(_sacrificed_equipment42.PRIMITIVES)
RESUME.update(_sacrificed_equipment42.RESUME)

from app.rules import life_prevention_outcomes42 as _life_prevention_outcomes42  # noqa: E402

PRIMITIVES.update(_life_prevention_outcomes42.PRIMITIVES)

from app.rules import mandatory_return_payments43 as _mandatory_return_payments43  # noqa: E402

PRIMITIVES.update(_mandatory_return_payments43.PRIMITIVES)
RESUME.update(_mandatory_return_payments43.RESUME)

from app.rules import life_receipt_sequences42 as _life_receipt_sequences42  # noqa: E402

PRIMITIVES.update(_life_receipt_sequences42.PRIMITIVES)
RESUME.update(_life_receipt_sequences42.RESUME)

from app.rules import tap_energy_outcomes43 as _tap_energy_outcomes43  # noqa: E402

PRIMITIVES.update(_tap_energy_outcomes43.PRIMITIVES)
RESUME.update(_tap_energy_outcomes43.RESUME)

from app.rules import numeric_roll_finalization42 as _numeric_roll_finalization42  # noqa: E402, I001

PRIMITIVES.update(_numeric_roll_finalization42.PRIMITIVES)
RESUME.update(_numeric_roll_finalization42.RESUME)

from app.rules import exiled_counter_payments43 as _exiled_counter_payments43  # noqa: E402

PRIMITIVES.update(_exiled_counter_payments43.PRIMITIVES)
RESUME.update(_exiled_counter_payments43.RESUME)

from app.rules import combat_damage_life_receipts as _combat_damage_life_receipts  # noqa: E402

PRIMITIVES.update(_combat_damage_life_receipts.PRIMITIVES)
RESUME.update(_combat_damage_life_receipts.RESUME)

from app.rules import life_total_damage_results43 as _life_total_damage_results43  # noqa: E402

PRIMITIVES.update(_life_total_damage_results43.PRIMITIVES)
RESUME.update(_life_total_damage_results43.RESUME)

from app.rules import linked_exile_life42 as _linked_exile_life42  # noqa: E402

PRIMITIVES.update(_linked_exile_life42.PRIMITIVES)

from app.rules import exiled_return_payments43 as _exiled_return_payments43  # noqa: E402

PRIMITIVES.update(_exiled_return_payments43.PRIMITIVES)

from app.rules import life_sequences43 as _life_sequences43  # noqa: E402

PRIMITIVES.update(_life_sequences43.PRIMITIVES)
RESUME.update(_life_sequences43.RESUME)

from app.rules import numeric_entry_roll42 as _numeric_entry_roll42  # noqa: E402, I001

PRIMITIVES.update(_numeric_entry_roll42.PRIMITIVES)

from app.rules import exile_outcomes42 as _exile_outcomes42  # noqa: E402

PRIMITIVES.update({"exile_outcomes42_dance": _exile_outcomes42.PRIMITIVES["exile_outcomes42_dance"]})
RESUME["exile_outcomes42_dance"] = _exile_outcomes42.resume_dance

PRIMITIVES.update({"exile_outcomes42_discard": _exile_outcomes42.PRIMITIVES["exile_outcomes42_discard"]})
RESUME["exile_outcomes42_discard"] = _exile_outcomes42.resume_discard

PRIMITIVES.update({"exile_outcomes42_monk": _exile_outcomes42.PRIMITIVES["exile_outcomes42_monk"]})

from app.rules import random_artifact_tables42 as _random_artifact_tables42  # noqa: E402, I001

PRIMITIVES.update(_random_artifact_tables42.PRIMITIVES)

PRIMITIVES.update({"exile_outcomes42_intellect": _exile_outcomes42.PRIMITIVES["exile_outcomes42_intellect"]})
RESUME["exile_outcomes42_intellect"] = _exile_outcomes42.resume_intellect

PRIMITIVES.update({"exile_outcomes42_kingpin": _exile_outcomes42.PRIMITIVES["exile_outcomes42_kingpin"]})

from app.rules import phase_lifetimes43 as _phase_lifetimes43  # noqa: E402

PRIMITIVES.update(_phase_lifetimes43.PRIMITIVES)

from app.rules import sacrifice_entry_outcomes43 as _sacrifice_entry_outcomes43  # noqa: E402

PRIMITIVES.update(_sacrifice_entry_outcomes43.PRIMITIVES)
RESUME.update(_sacrifice_entry_outcomes43.RESUME)

from app.rules import combat_player_scope43 as _combat_player_scope43  # noqa: E402, I001

RESUME.update(_combat_player_scope43.RESUME)

from app.rules import random_transform_outcomes43 as _random_transform_outcomes43  # noqa: E402

PRIMITIVES['random_transform43'] = _random_transform_outcomes43.consume

from app.rules import random_draw_reflexives43 as _random_draw_reflexives43  # noqa: E402

PRIMITIVES['random_draw_reflexives43'] = _random_draw_reflexives43.consume

from app.rules import random_walker_faces44 as _random_walker_faces44  # noqa: E402

PRIMITIVES['ral_other_blue44'] = _random_walker_faces44.draw_if_other_blue

from app.rules import prevention_frontier_cards as _joint_prevention_cards  # noqa: E402, I001

PRIMITIVES.update(_joint_prevention_cards.PRIMITIVES)
RESUME.update(_joint_prevention_cards.RESUME)

PRIMITIVES.update({"exile_outcomes42_wand": _exile_outcomes42.PRIMITIVES["exile_outcomes42_wand"]})

PRIMITIVES.update({"exile_outcomes42_stash": _exile_outcomes42.PRIMITIVES["exile_outcomes42_stash"]})

from app.rules import life_sequences44 as _life_sequences44  # noqa: E402
from app.rules import opponent_gain_costs44 as _opponent_gain_costs44  # noqa: E402, F401

PRIMITIVES.update(_life_sequences44.PRIMITIVES)
RESUME.update(_life_sequences44.RESUME)

PRIMITIVES.update({key: _exile_outcomes42.PRIMITIVES[key] for key in ("exile_outcomes42_lobelia_enter", "exile_outcomes42_lobelia", "exile_outcomes42_narfi", "exile_outcomes42_linked_grant")})
RESUME["exile_outcomes42_narfi"] = _exile_outcomes42.resume_narfi

from app.rules import prevention_unpreventable_outcomes44 as _prevention_unpreventable44  # noqa: E402

PRIMITIVES.update(_prevention_unpreventable44.PRIMITIVES)

PRIMITIVES["exile_outcomes44_mara"] = _exile_outcomes42.mara_next
RESUME["exile_outcomes44_mara"] = _exile_outcomes42.resume_mara

from app.rules import life_sets44 as _life_sets44  # noqa: E402

PRIMITIVES.update(_life_sets44.PRIMITIVES)

from app.rules import goldberry_outcomes44 as _goldberry_outcomes44  # noqa: E402

PRIMITIVES[_goldberry_outcomes44.STEP] = _goldberry_outcomes44.run

PRIMITIVES["exile_outcomes44_quintorius"] = _exile_outcomes42.quintorius_packet

from app.rules import bloatfly_outcomes44 as _bloatfly_outcomes44  # noqa: E402

PRIMITIVES[_bloatfly_outcomes44.STEP] = _bloatfly_outcomes44.run

from app.rules import source_duration_prevention45 as _source_duration_prevention45  # noqa: E402

PRIMITIVES.update(_source_duration_prevention45.PRIMITIVES)

from app.rules import random_previous_combat44 as _random_previous_combat44  # noqa: E402

PRIMITIVES['random_previous_combat44'] = _random_previous_combat44.consume
RESUME['last_combat44_legacy'] = _random_previous_combat44.legacy_done


def _finish_look45(plan: Plan, r: dict[str, Any], pid: str) -> None:
    from app.rules import replacements

    then = {'do': 'look_finish45', 'look': r, 'player': pid}
    for cid in r['chosen']:
        if cid not in plan.state.cards:
            continue
        pending = plan.rules.pending_616.get(cid)
        if pending is not None and pending.get('oid') == plan.oid(plan.state.cards[cid]) and replacements.offer_616(plan):
            assert plan.rules.decision is not None and plan.rules.decision.resume is not None
            plan.rules.decision.resume['then'] = then
            return
        if cid in plan.rules.pending_903_9b and replacements.offer_903_9b(plan, only=cid):
            assert plan.rules.decision is not None and plan.rules.decision.resume is not None
            plan.rules.decision.resume['then'] = then
            plan.rules.decision.resume['then_object'] = plan.oid(plan.state.cards[cid])
            return
    # Complete every selected move/replacement before a replacement shuffle can
    # conceal another selected object. Only the unchosen top cards are excluded.
    owners = r.pop('shuffle_after', [])
    if owners:
        saved_retained = plan.shuffle_retained
        plan.shuffle_retained = tuple(
            ObjectRef(card=cid, object_id=plan.oid(plan.state.cards[cid]), zone=zone_key(pid, 'library'))
            for cid in r['cards'] if cid not in r['chosen'] and cid in plan.state.cards
            and plan.state.cards[cid].zone == zone_key(pid, 'library')
            and (r.get('looked_objects') is None or r['looked_objects'].get(cid) == plan.oid(plan.state.cards[cid])))
        try:
            for owner in owners:
                plan.do({'type': 'shuffle', 'player': owner, 'zone': 'library'}, actor=owner)
        finally:
            plan.shuffle_retained = saved_retained
    from app.rules import graveyard_order

    if graveyard_order.offer(plan):
        assert plan.rules.decision is not None and plan.rules.decision.resume is not None
        plan.rules.decision.resume['look'] = r
        plan.rules.decision.resume['look_player'] = pid
        plan.rules.decision.resume['step'] = 'look_gy_order45'
        return
    chosen = r['chosen']
    rest = [c for c in r["cards"] if c not in chosen and c in plan.state.zones.get(zone_key(pid, "library"), [])]
    if r.get('looked_objects') is not None:
        rest = [c for c in rest if plan.oid(plan.state.cards[c]) == r.get('looked_objects', {}).get(c)]
    if len(rest) == 1:
        # Even a single remaining card must be returned to top: a graveyard
        # replacement may have shuffled the library while the chosen cards moved.
        hidden = [c for c in rest if plan.state.cards[c].revealed_to]
        if hidden:
            plan.do({'type': 'hide', 'card_ids': hidden}, actor=pid)
        plan.do({'type': 'move', 'card_ids': rest, 'to': {'player': pid, 'zone': 'library'}, 'position': 'top'}, actor=pid)
    if r.get('as_kept') and len(rest) <= 1:
        r['ctx'].setdefault('surveil_kept', {})[r['as_kept']] = len(rest)
    if len(rest) > 1 or len(chosen) > 1 and r["where"] == "bottom":
        ordering = rest if len(rest) > 1 else chosen
        place = "top" if len(rest) > 1 else "bottom"
        decide(plan, player=pid, kind="order",
               prompt=f"Order the cards for the {place} of your library (first chosen ends up on {'top' if place == 'top' else 'the bottom'})",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in ordering],
               min_choices=len(ordering), max_choices=len(ordering),
               resume={"step": "order_library", "place": place, "then_bottom": chosen if place == "top" and len(chosen) > 1 else [],
                       "ctx": r["ctx"],
                       **({'as_kept': r['as_kept'], 'looked_objects': r['looked_objects']} if r.get('as_kept') and place == 'top' else {})})
        return
    continue_effects(plan, r["ctx"])


def _then_look45(plan: Plan, then: dict[str, Any]) -> None:
    then['look'].setdefault('shuffle_after', []).extend(then.get('shuffle_after', []))
    _finish_look45(plan, then['look'], then['player'])


def _resume_look_gy_order45(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import graveyard_order

    graveyard_order.resume(plan, d, chosen)
    _finish_look45(plan, d.resume['look'], d.resume['look_player'])

replace.THEN['look_finish45'] = _then_look45
RESUME['look_gy_order45'] = _resume_look_gy_order45

from app.rules import random_cost_roll44 as _random_cost_roll44  # noqa: E402

PRIMITIVES.update(_random_cost_roll44.PRIMITIVES)

from app.rules import chosen_color_pairs45 as _chosen_color_pairs45  # noqa: E402

PRIMITIVES.update(_chosen_color_pairs45.PRIMITIVES)


def _register_counter_consumers45() -> None:
    from app.rules import counter_consumers45

    PRIMITIVES.update(counter_consumers45.PRIMITIVES)
    RESUME.update(counter_consumers45.RESUME)


_register_counter_consumers45()

from app.rules import surveil_outcomes45 as _surveil_outcomes45  # noqa: E402

PRIMITIVES.update(_surveil_outcomes45.PRIMITIVES)
RESUME.update(_surveil_outcomes45.RESUME)

# Only admitted exact45 text emits this continuation; other recipes stay held.
from app.rules import exile_cast_outcomes45 as _exile_cast_outcomes45  # noqa: E402

PRIMITIVES['exile_cast_outcome45'] = _exile_cast_outcomes45.run
RESUME['exile_cast_outcome45'] = _exile_cast_outcomes45.resume
RESUME['exile_cast_extract45'] = _exile_cast_outcomes45.resume_extract

from app.rules import exile_spell_choices49 as _exile_spell_choices49  # noqa: E402
from app.rules import exile_sphinx49 as _exile_sphinx49  # noqa: E402

PRIMITIVES.update(_exile_spell_choices49.PRIMITIVES)
RESUME.update(_exile_spell_choices49.RESUME)
PRIMITIVES.update(_exile_sphinx49.PRIMITIVES)

from app.rules import delayed_blinks50 as _delayed_blinks50  # noqa: E402
from app.rules import delayed_combat_blinks50 as _delayed_combat_blinks50  # noqa: E402
from app.rules import delayed_entry_blinks50 as _delayed_entry_blinks50  # noqa: E402
from app.rules import delayed_loyalty_blinks50 as _delayed_loyalty_blinks50  # noqa: E402
from app.rules import delayed_self_blinks50 as _delayed_self_blinks50  # noqa: E402

PRIMITIVES.update(_delayed_blinks50.PRIMITIVES)
PRIMITIVES.update(_delayed_combat_blinks50.PRIMITIVES)
PRIMITIVES.update(_delayed_entry_blinks50.PRIMITIVES)
PRIMITIVES.update(_delayed_loyalty_blinks50.PRIMITIVES)
PRIMITIVES.update(_delayed_self_blinks50.PRIMITIVES)
RESUME.update(_delayed_loyalty_blinks50.RESUME)


from app.rules import outside_research50 as _outside_research50  # noqa: E402

PRIMITIVES.update(_outside_research50.PRIMITIVES)
RESUME.update(_outside_research50.RESUME)


def _register_adjacent_counter_consumers45() -> None:
    from app.rules import graveyard_payments45, reprieve_payment45, urge_payment45

    for consumer in (graveyard_payments45, reprieve_payment45, urge_payment45):
        PRIMITIVES.update(consumer.PRIMITIVES)
        RESUME.update(consumer.RESUME)


_register_adjacent_counter_consumers45()

from app.rules import life_dynamic45 as _life_dynamic45  # noqa: E402

PRIMITIVES.update(_life_dynamic45.PRIMITIVES)


from app.rules import life_sequences45 as _life_sequences45  # noqa: E402

PRIMITIVES.update(_life_sequences45.PRIMITIVES)
RESUME.update(_life_sequences45.RESUME)


from app.rules import death_outcomes46 as _death_outcomes46  # noqa: E402

PRIMITIVES.update(_death_outcomes46.PRIMITIVES)
RESUME.update(_death_outcomes46.RESUME)

from app.rules import random_vehicle_crash45 as _random_vehicle_crash45  # noqa: E402

PRIMITIVES.update(_random_vehicle_crash45.PRIMITIVES)
RESUME.update(_random_vehicle_crash45.RESUME)


from app.rules import quoted_prevention_loss47 as _quoted_prevention_loss47  # noqa: E402

PRIMITIVES.update(_quoted_prevention_loss47.PRIMITIVES)

from app.rules import mana_persistent_replacements48 as _mana_persistent_replacements48  # noqa: E402

PRIMITIVES.update(_mana_persistent_replacements48.PRIMITIVES)


from app.rules import counter_alternatives50 as _counter_alternatives50  # noqa: E402

PRIMITIVES.update(_counter_alternatives50.PRIMITIVES)

from app.rules import trigger_leaf54_staged as _trigger_leaf54  # noqa: E402

PRIMITIVES["arbiter_highest54"] = _trigger_leaf54.arbiter_highest

from app.rules import trigger_leaf57_staged as _trigger_leaf57  # noqa: E402

PRIMITIVES["lammasu_unsuspect57"] = _trigger_leaf57.unsuspect


from app.rules import counter_event_packets50 as _counter_event_packets50  # noqa: E402

PRIMITIVES.update(_counter_event_packets50.PRIMITIVES)


from app.rules import trigger_attached_artifact67 as _trigger_attached_artifact67  # noqa: E402

PRIMITIVES.update(_trigger_attached_artifact67.PRIMITIVES)


from app.rules import ring_counter_packets67 as _ring_counter_packets67  # noqa: E402

PRIMITIVES.update(_ring_counter_packets67.PRIMITIVES)

from app.rules import combat_teyo66 as _combat_teyo66  # noqa: E402

PRIMITIVES.update(_combat_teyo66.PRIMITIVES)


from app.rules import entry_counter_kind_choices68 as _entry_counter_kind_choices68  # noqa: E402

PRIMITIVES.update(_entry_counter_kind_choices68.PRIMITIVES)

from app.rules import attacker_reselection73 as _attacker_reselection73  # noqa: E402

PRIMITIVES['attacker_reselect73'] = _attacker_reselection73.effect

from app.rules import manifest_aura74 as _manifest_aura74  # noqa: E402

PRIMITIVES['manifest_aura74'] = _manifest_aura74.become_aura


from app.rules import saddled_receipts76 as _saddled_receipts76  # noqa: E402

PRIMITIVES.update({"mount_vehicle76": _saddled_receipts76.mount_vehicle,
                   "saddle_contributors76": _saddled_receipts76.contributors,
                   "mount_cohort76": _saddled_receipts76.cohort})


from app.rules import targeting_sources77 as _targeting_sources77  # noqa: E402

PRIMITIVES['targeting_actor_damage77'] = _targeting_sources77.damage_actor


from app.rules import conditional_free_casts68 as _conditional_free_casts68  # noqa: E402

PRIMITIVES["next_free_cast68"] = _conditional_free_casts68.next_free


from app.rules import first_event_receipts78 as _first_event78  # noqa: E402

PRIMITIVES['investigate_complete78'] = _first_event78.complete


from app.rules import text_change_instructions71 as _text_change_instructions71  # noqa: E402

PRIMITIVES.update(_text_change_instructions71.PRIMITIVES)
CHOICE_OPTIONS['word to replace'] = [*_text_change_instructions71.COLORS, *_text_change_instructions71.LANDS,
                               *sorted(_text_change_instructions71.CREATURE_TYPES)]

RESUME['text71_legacy_done'] = _text_change_instructions71.legacy_done

CHOICE_OPTIONS['replacement word'] = CHOICE_OPTIONS['word to replace']

from app.rules import top_library_authorities69  # noqa: E402

PRIMITIVES.update(top_library_authorities69.PRIMITIVES)

from app.rules import conditional_counter_riders77  # noqa: E402

PRIMITIVES.update(conditional_counter_riders77.PRIMITIVES)

from app.rules import unblocked_choices79 as _unblocked79  # noqa: E402

PRIMITIVES.update({'bone_entry79': _unblocked79.bone_entry, 'bone_finish79': _unblocked79.bone_finish, 'spy_reveal79': _unblocked79.spy_reveal})

from app.rules import first_crew_saddle80 as _first_crew80  # noqa: E402

PRIMITIVES['mindlink_copy80'] = _first_crew80.mindlink_copy

from app.rules import public_mill_attachment59 as _public_mill_attachment59  # noqa: E402

PRIMITIVES.update(_public_mill_attachment59.PRIMITIVES)
RESUME.update(_public_mill_attachment59.RESUME)

from app.rules import object_mana_offers78  # noqa: E402

PRIMITIVES.update(object_mana_offers78.PRIMITIVES)
RESUME.update(object_mana_offers78.RESUME)

from app.rules import upkeep_tax79  # noqa: E402

PRIMITIVES.update(upkeep_tax79.PRIMITIVES)
RESUME.update(upkeep_tax79.RESUME)

from app.rules import prepared_mill61 as _prepared_mill61  # noqa: E402, I001

RESUME.update(_prepared_mill61.RESUME)


CHOICE_OPTIONS['color word'] = list(_text_change_instructions71.COLORS)
CHOICE_LABELS['color word'] = 'Chosen color word'
CHOICE_LABELS["amount of life to pay"] = "Life paid"  # -- static permanents (wave 100D) -- static_perm100d.LIFE_KEY

from app.rules import text_global_word71 as _global_word71  # noqa: E402

RESUME['restore_global_word71'] = _global_word71.resume_restore

RESUME['restore_global_continue71'] = _global_word71.resume_continue

from app.rules import post_mill_continuations60 as _post_mill_continuations60  # noqa: E402, I001

PRIMITIVES.update(_post_mill_continuations60.PRIMITIVES)
RESUME.update(_post_mill_continuations60.RESUME)

from app.rules import crew_saddle_readers81 as _crew_saddle_readers81  # noqa: E402, I001

PRIMITIVES.update(_crew_saddle_readers81.PRIMITIVES)

from app.rules import pooled_casting_authorities71 as _pooled_casting_authorities71  # noqa: E402, I001

PRIMITIVES.update(_pooled_casting_authorities71.PRIMITIVES)

from app.rules import demonic_covenant62 as _demonic_covenant62  # noqa: E402, I001

PRIMITIVES.update(_demonic_covenant62.PRIMITIVES)

from app.rules import deferred_payment82 as _deferred82  # noqa: E402

PRIMITIVES.update(_deferred82.PRIMITIVES)
RESUME.update(_deferred82.RESUME)

from app.rules import fortune83 as _fortune83  # noqa: E402, I001

PRIMITIVES.update(_fortune83.PRIMITIVES)

from app.rules import grave_adventure74 as _grave_adventure74  # noqa: E402, I001

PRIMITIVES.update(_grave_adventure74.PRIMITIVES)
RESUME.update(_grave_adventure74.RESUME)

from app.rules import target_duration_costs69 as _target_duration69  # noqa: E402

PRIMITIVES.update(_target_duration69.PRIMITIVES)

from app.rules import attack_subjects86 as _attack_subjects86  # noqa: E402, I001

PRIMITIVES.update(_attack_subjects86.PRIMITIVES)

from app.rules import teferi_realm84 as _teferi_realm84  # noqa: E402, I001

PRIMITIVES.update(_teferi_realm84.PRIMITIVES)

from app.rules import source_cohort87 as _source_cohort87  # noqa: E402, I001

PRIMITIVES.update(_source_cohort87.PRIMITIVES)

from app.rules import cyber_controller63 as _cyber_controller63  # noqa: E402, I001

PRIMITIVES.update(_cyber_controller63.PRIMITIVES)
CHOICE_OPTIONS[_teferi_realm84.WHAT] = list(_teferi_realm84.CHOICES)

from app.rules import permanent_payments83 as _permanent83  # noqa: E402, I001

PRIMITIVES.update(_permanent83.PRIMITIVES)
RESUME.update(_permanent83.RESUME)

from app.rules import greatest_creature_cost84 as _greatest_creature_cost84  # noqa: E402, I001

PRIMITIVES.update(_greatest_creature_cost84.PRIMITIVES)
RESUME.update(_greatest_creature_cost84.RESUME)

from app.rules import creature_obligations85 as _creature_obligations85  # noqa: E402, I001

PRIMITIVES.update(_creature_obligations85.PRIMITIVES)
RESUME.update(_creature_obligations85.RESUME)

from app.rules import public_mill_picks65 as _public_mill_picks65  # noqa: E402, I001

PRIMITIVES.update(_public_mill_picks65.PRIMITIVES)
RESUME.update(_public_mill_picks65.RESUME)

from app.rules import hall_gemstone86 as _hall_gemstone86  # noqa: E402, I001

PRIMITIVES.update(_hall_gemstone86.PRIMITIVES)

from app.rules import phase_skips88 as _phase_skips88  # noqa: E402, I001

PRIMITIVES.update(_phase_skips88.PRIMITIVES)
RESUME.update(_phase_skips88.RESUME)

from app.rules import linked_owner_cast77 as _linked_owner_cast77  # noqa: E402, I001

PRIMITIVES.update(_linked_owner_cast77.PRIMITIVES)

from app.rules import nonbattlefield_life_offers86 as _life86  # noqa: E402, I001

PRIMITIVES.update(_life86.PRIMITIVES)
RESUME.update(_life86.RESUME)

from app.rules import public_mill_costs64 as _public_mill_costs64  # noqa: E402, I001

PRIMITIVES.update(_public_mill_costs64.PRIMITIVES)
RESUME.update(_public_mill_costs64.RESUME)

from app.rules import knowledge_pool78 as _knowledge_pool78  # noqa: E402, I001

PRIMITIVES.update(_knowledge_pool78.PRIMITIVES)


from app.rules import echo_alternatives76 as _echo76  # noqa: E402

PRIMITIVES['echo_payment76'] = _echo76.payment

PRIMITIVES['note_echo_paid76'] = _echo76.note_paid

PRIMITIVES['echo_draws76'] = _echo76.draws


from app.rules import nightshade_reveal88 as _nightshade88  # noqa: E402, I001

PRIMITIVES.update(_nightshade88.PRIMITIVES)
RESUME.update(_nightshade88.RESUME)

from app.rules import repeated_graveyard_offer89 as _lore89  # noqa: E402, I001

PRIMITIVES.update(_lore89.PRIMITIVES)
RESUME.update(_lore89.RESUME)


from app.rules import exchange_conditions91 as _exchange91  # noqa: E402

PRIMITIVES.update({"exchange_drake91": _exchange91.drake, "exchange_neither91": _exchange91.neither, "exchange_auras91": _exchange91.auras})

from app.rules import graveyard_windows80 as _graveyard_windows80  # noqa: E402

PRIMITIVES.update(_graveyard_windows80.PRIMITIVES)

from app.rules import post_mill_graveyard68  # noqa: E402

PRIMITIVES.update(post_mill_graveyard68.PRIMITIVES)

from app.rules import attached_destruction82 as _attached_destruction82  # noqa: E402

PRIMITIVES.update(_attached_destruction82.PRIMITIVES)

from app.rules import exchange_choices92 as _exchange92  # noqa: E402

PRIMITIVES.update(_exchange92.PRIMITIVES)

from app.rules import exchange_spells93 as _exchange93  # noqa: E402

PRIMITIVES.update(_exchange93.PRIMITIVES)

from app.rules import vault_loop71 as _vault71  # noqa: E402, I001

PRIMITIVES.update(_vault71.PRIMITIVES)

from app.rules import conditional_upkeep_grants91 as _upkeep91  # noqa: E402, I001

PRIMITIVES.update(_upkeep91.PRIMITIVES)

from app.rules import zone_exchanges94 as _zone_exchanges94  # noqa: E402

PRIMITIVES.update(_zone_exchanges94.PRIMITIVES)

# -- trigger lines (wave 100A) --
from app.rules import triggers100a as _triggers100a  # noqa: E402

PRIMITIVES.update(_triggers100a.PRIMITIVES)
from app.rules import xdamage100e as _xdamage100e  # noqa: E402  -- xdamage (wave 100E) --

PRIMITIVES.update(_xdamage100e.PRIMITIVES)
RESUME.update(_xdamage100e.RESUME)
from app.rules import ifyoudo100b as _ifyoudo100b  # noqa: E402, I001  -- if you do (wave 100B) --

PRIMITIVES.update(_ifyoudo100b.PRIMITIVES)
RESUME.update(_ifyoudo100b.RESUME)
# -- attached (wave 100F) -- (app/rules/attached100f.py)
from app.rules import attached100f as _attached100f  # noqa: E402, I001

PRIMITIVES.update(_attached100f.PRIMITIVES)
RESUME.update(_attached100f.RESUME)
# -- static spells (wave 100C) --
from app.rules import static_spell100c as _static_spell100c  # noqa: E402

PRIMITIVES.update(_static_spell100c.PRIMITIVES)
from app.rules import zones100g as _zones100g  # noqa: E402  -- zones (wave 100G) --

PRIMITIVES.update(_zones100g.PRIMITIVES)
RESUME.update(_zones100g.RESUME)
RESUME.update(_triggers100a.RESUME)
# -- activated (wave 100I) -- (app/rules/activated100i.py)
from app.rules import activated100i as _activated100i  # noqa: E402, I001

PRIMITIVES.update(_activated100i.PRIMITIVES)
# -- counters (wave 100J) -- (app/rules/counters100j.py)
from app.rules import counters100j as _counters100j  # noqa: E402

PRIMITIVES.update(_counters100j.PRIMITIVES)
RESUME.update(_counters100j.RESUME)
# -- turn state (wave 100H) -- (app/rules/turnstate100h.py)
from app.rules import turnstate100h as _turnstate100h  # noqa: E402

PRIMITIVES.update(_turnstate100h.PRIMITIVES)
from app.rules import instead100k as _instead100k  # noqa: E402, I001  -- instead (wave 100K) --

PRIMITIVES.update(_instead100k.PRIMITIVES)
RESUME.update(_instead100k.RESUME)
from app.rules import aslongas100k as _aslongas100k  # noqa: E402, I001  -- as long as (wave 100K) --

PRIMITIVES.update(_aslongas100k.PRIMITIVES)
from app.rules import attractions100l as _attractions100l  # noqa: E402  -- Attractions (wave 100L) --

PRIMITIVES.update(_attractions100l.PRIMITIVES)
from app.rules import otherchooser100p as _otherchooser100p  # noqa: E402  -- other choosers (wave 100P) --

PRIMITIVES.update(_otherchooser100p.PRIMITIVES)

from app.rules import multi100n as _multi100n  # noqa: E402, I001  -- multi (wave 100N) --

PRIMITIVES.update(_multi100n.PRIMITIVES)
from app.rules import retarget100o as _retarget100o  # noqa: E402  -- retarget (wave 100O) --

PRIMITIVES.update(_retarget100o.PRIMITIVES)
RESUME.update(_retarget100o.RESUME)
from app.rules import modal_clauses101 as _modal101  # noqa: E402

PRIMITIVES.update(_modal101.PRIMITIVES)

from app.rules import upkeep_sacrifice101 as _upkeep101  # noqa: E402

PRIMITIVES.update(_upkeep101.PRIMITIVES)

from app.rules import library_packets101 as _library_packets101  # noqa: E402

PRIMITIVES.update(_library_packets101.PRIMITIVES)
RESUME.update(_library_packets101.RESUME)

from app.rules import damage_values102 as _damage_values102  # noqa: E402

PRIMITIVES.update(_damage_values102.PRIMITIVES)

from app.rules import stack_events102 as _stack102  # noqa: E402

PRIMITIVES.update(_stack102.PRIMITIVES)

from app.rules import library_polymorph102 as _library_polymorph102  # noqa: E402

PRIMITIVES.update(_library_polymorph102.PRIMITIVES)

from app.rules import combat_damage95 as _combat_damage95  # noqa: E402

PRIMITIVES.update(_combat_damage95.PRIMITIVES)

from app.rules import stack_extension103 as _stack103  # noqa: E402

PRIMITIVES.update(_stack103.PRIMITIVES)

from app.rules import next_copy104 as _next104  # noqa: E402

PRIMITIVES.update(_next104.PRIMITIVES)

from app.rules import sticker_effects101 as _sticker_effects101  # noqa: E402

PRIMITIVES.update(_sticker_effects101.PRIMITIVES)
from app.rules import epic103 as _epic103  # noqa: E402

PRIMITIVES.update(_epic103.PRIMITIVES)


from app.rules import vampire_returns105 as _vampire_returns105  # noqa: E402, I001
PRIMITIVES.update(_vampire_returns105.PRIMITIVES)

from app.rules import copy_controllers105 as _copy105  # noqa: E402

PRIMITIVES.update(_copy105.PRIMITIVES)

from app.rules import wave110a as _wave110a  # noqa: E402  -- wave 110A --

PRIMITIVES.update(_wave110a.primitives())
# -- wave 110B --
from app.rules import wave110b_cards as _wave110b_cards  # noqa: E402

PRIMITIVES.update(_wave110b_cards.PRIMITIVES)
from app.rules import wave110c_core as _wave110c_core  # noqa: E402, I001  -- core (wave 110C) --
PRIMITIVES.update(_wave110c_core.PRIMITIVES)
RESUME.update(_wave110c_core.RESUME)
from app.rules import wave110d as _wave110d  # noqa: E402, I001  -- wave 110D --

PRIMITIVES.update(_wave110d.PRIMITIVES)
RESUME.update(_wave110d.RESUME)
RESUME.update(_wave110b_cards.RESUME)

from app.rules import wave110c_kusari as _wave110c_kusari  # noqa: E402, I001
PRIMITIVES.update(_wave110c_kusari.PRIMITIVES)  # -- Kusari-Gama (wave 110C) --

from app.rules import wave110e_cards as _wave110e  # noqa: E402, I001  -- wave 110E --

PRIMITIVES.update(_wave110e.PRIMITIVES)
from app.rules import wave110f_cards as _wave110f_cards  # noqa: E402, I001  -- cards (wave 110F) --
PRIMITIVES.update(_wave110f_cards.PRIMITIVES)
# -- wave 110G --
from app.rules import wave110g_cards as _wave110g_cards  # noqa: E402

PRIMITIVES.update(_wave110g_cards.PRIMITIVES)
from app.rules import wave110h_cards as _wave110h  # noqa: E402, I001  -- wave 110H --

PRIMITIVES.update(_wave110h.PRIMITIVES)
RESUME.update(_wave110h.RESUME)
from app.rules import wave110i_cards as _wave110i_cards  # noqa: E402, I001  -- cards (wave 110I) --

PRIMITIVES.update(_wave110i_cards.PRIMITIVES)
RESUME.update(_wave110i_cards.RESUME)
replace.THEN["cu_paid110i"] = _wave110i_cards.cu_paid_then  # -- cumulative upkeep paid (wave 110I) --
from app.rules import wave110c_any as _wave110c_any  # noqa: E402, I001
PRIMITIVES.update(_wave110c_any.PRIMITIVES)  # -- any opponent may (wave 110C) --
from app.rules import wave110e_opp as _wave110e_opp  # noqa: E402, I001  -- wave 110E --
PRIMITIVES.update(_wave110e_opp.PRIMITIVES)

from app.rules import wave110e_imps as _wave110e_imps  # noqa: E402  -- Nettling Imp (wave 110E)

PRIMITIVES.update(_wave110e_imps.PRIMITIVES)
RESUME.update(_wave110f_cards.RESUME)
RESUME.update(_wave110g_cards.RESUME)
from app.rules import wave110j_cards as _wave110j  # noqa: E402, I001  -- wave 110J --

PRIMITIVES.update(_wave110j.PRIMITIVES)
RESUME.update(_wave110j.RESUME)
from app.rules import wave110k_cards as _wave110k  # noqa: E402, I001  -- wave 110K --

PRIMITIVES.update(_wave110k.PRIMITIVES)
RESUME.update(_wave110k.RESUME)
from app.rules import wave110l_cards as _wave110l  # noqa: E402, I001  -- wave 110L --

PRIMITIVES.update(_wave110l.PRIMITIVES)
RESUME.update(_wave110l.RESUME)
from app.rules import wave110m_cards as _wave110m  # noqa: E402, I001  -- wave 110M --

PRIMITIVES.update(_wave110m.PRIMITIVES)
RESUME.update(_wave110m.RESUME)
from app.rules import wave110n_cards as _wave110n  # noqa: E402, I001  -- wave 110N --

PRIMITIVES.update(_wave110n.PRIMITIVES)
RESUME.update(_wave110n.RESUME)
from app.rules import wave110o_cards as _wave110o  # noqa: E402, I001  -- (wave 110O) --

PRIMITIVES.update(_wave110o.PRIMITIVES)
RESUME.update(_wave110o.RESUME)
RESUME.update(_wave110a.resume())  # -- wave 110A --
from app.rules import wave110c_misc as _wave110c_misc  # noqa: E402, I001  -- (wave 110C) --

PRIMITIVES.update(_wave110c_misc.PRIMITIVES)
RESUME.update(_wave110c_misc.RESUME)
from app.rules import wave110e_pets as _wave110e_pets  # noqa: E402, I001  -- Exotic Pets (wave 110E) --

PRIMITIVES.update(_wave110e_pets.PRIMITIVES)
RESUME.update(_wave110e_pets.RESUME)
from app.rules import wave110b_mirror as _wave110b_mirror  # noqa: E402, I001  -- (wave 110B) --

PRIMITIVES.update(_wave110b_mirror.PRIMITIVES)
from app.rules import wave110e_once as _wave110e_once  # noqa: E402, I001  -- Storyweave (wave 110E) --

PRIMITIVES.update(_wave110e_once.PRIMITIVES)
from app.rules import wave110e_blade as _wave110e_blade  # noqa: E402, I001  -- Sanctuary Blade (wave 110E) --

RESUME.update(_wave110e_blade.RESUME)
