"""Ordered instructions following native searches; all bindings are exact rules objects."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption, ObjectRef
from app.rules import context
from app.rules import qualified_search_packets as queries

if TYPE_CHECKING:
    from app.rules.plan import Plan

BIND = "ref:ordered_find"


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = " ".join(body.lower().split()).rstrip(".")
    kinds = {
        "search your library for any number of artifact cards, exile them, then create that many 1/1 colorless myr artifact creature tokens. then shuffle": "myr",
        "search your library for a basic land card, put that card onto the battlefield tapped, then shuffle. return this land to its owner's hand at the beginning of the next cleanup step": "glaciers",
        "search your library for a basic land card, put that card onto the battlefield tapped, then shuffle. return ~ to its owner's hand at the beginning of the next cleanup step": "glaciers",
        "you may search your library for a basic land card, reveal that card, put it into your hand, then shuffle. if you do, you skip your draw step this turn": "sanctuary",
        "search your library for a card, exile it, then shuffle. any opponent may have you put that card into your hand. if no player does, you draw three cards": "memories",
        "search your library for a basic land card, put it onto the battlefield tapped, then shuffle. the player to your right gains control of this artifact": "rope_search",
        "search your library for a basic land card, put it onto the battlefield tapped, then shuffle. the player to your right gains control of ~": "rope_search",
        "draw a card. the player to your right gains control of this artifact": "rope_draw",
        "draw a card. the player to your right gains control of ~": "rope_draw",
        "if the {2}{r}{r} cost was paid, an opponent discards any number of cards, then draws that many cards": "mastery",
        "search your library for up to five land cards that have different names, exile them, then shuffle": "journey",
        "search your library and graveyard for five cards and exile the rest. put the chosen cards on top of your library in any order. you lose half your life, rounded up": "doomsday",
        "search your library for a basic land card or town card, put it onto the battlefield tapped, then shuffle. when you search your library this way, put a +1/+1 counter on target creature you control": "prishe",
        "if you've cast a spell named peer through depths and a spell named reach through mists this turn, you may search your library for a card named the unspeakable, put it onto the battlefield, then shuffle": "sift",
        "search your library for a nonland card and reveal it. each opponent who cast a spell this turn with the same name as that card loses 6 life. then shuffle": "grim",
        "return it to its owner's hand. if you do, you may search your library for a plains card, put it onto the battlefield tapped, then shuffle": "hawk",
        "you may search your library for a forest card, put it onto the battlefield tapped under target player's control, then shuffle": "dryad",
        "choose a card at random exiled with this enchantment and put it onto the battlefield tapped": "journey_return",
        "choose a card at random exiled with ~ and put it onto the battlefield tapped": "journey_return",
    }
    if (k := kinds.get(text)) is None:
        return None
    if k == "journey":
        return (
            [queries.search("land card", to="exile", max=5, upto=True, distinct_names=True, link=True)],
            None,
            False,
        )
    if k == "journey_return":
        from app.rules import exiled_with

        return (
            [
                {
                    "do": "return_choice",
                    "who": exiled_with.WHO,
                    "n": 1,
                    "upto": False,
                    "random": True,
                    "label": "card",
                    "to": "battlefield",
                    "tapped": True,
                    "under": "you",
                }
            ],
            None,
            False,
        )
    return [{"do": "ordered_tutor", "kind": k, "binding": BIND}], "player" if k == "dryad" else None, False


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import events, scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if text.startswith("When ~ deals combat damage to a player who controls more lands than you, "):
        body = text.split(", ", 1)[1]
        got = parse(body)
        if got is not None:
            cond = events.parse_condition("~ deals combat damage to a player")
            assert cond is not None
            return {
                "kind": "triggered",
                "trigger": "event",
                "cond": {**cond, "recipient_more_lands": True},
                "effects": got[0],
                "optional": False,
                "target": None,
            }
    if text.startswith(
        "For each opponent, choose up to one target artifact or enchantment that player controls. For each permanent chosen this way, its controller may exile it. Then if one or more of the chosen permanents are still on the battlefield, you search your library for up to that many land cards, put them onto the battlefield tapped, then shuffle."
    ):
        from app.rules.per_opponent import FLAG

        sel = selectors.parse("artifact or enchantment an opponent controls")
        assert sel is not None
        return {
            "kind": "spell",
            "targets": [{"what": sel.key(), "min": 0, "max": 1, FLAG: True}],
            "effects": [
                {"do": "ordered_tutor", "kind": "disorient", "binding": BIND, "opponent_aggregate": True}
            ],
        }
    # Qualifier commas must not be mistaken for the trigger/body boundary.
    if ", " in text:
        head, body = text.split(", ", 1)
        if (got := parse(body)) is not None and (
            got[0][0].get("kind") in ("dryad", "sanctuary") or got[0][0]["do"] in ("search", "return_choice")
        ):
            stub = scripts._define(replace(ability, text=head + ", scry 1."), ch)
            if stub is not None:
                return {**stub, "effects": got[0], **scripts.target_fields(got[1])}
    return None


def insert(ctx: dict[str, Any], es: list[dict[str, Any]]) -> bool:
    ctx["effects"][ctx["next"] : ctx["next"]] = es
    return True


def prepare(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, exiled_with, history

    k = e["kind"]
    bind = e["binding"]
    if k == "journey_return":
        return insert(
            ctx,
            [
                {
                    "do": "return_choice",
                    "who": exiled_with.WHO,
                    "n": 1,
                    "upto": False,
                    "random": True,
                    "label": "card",
                    "to": "battlefield",
                    "tapped": True,
                    "under": "you",
                }
            ],
        )
    if k == "rope_draw":
        return insert(
            ctx, [{"do": "draw", "who": "you", "n": 1}, {"do": "ordered_after", "kind": k, "binding": bind}]
        )
    if k == "mastery":
        record = plan.rules.payments.get(ctx.get("source_object") or "")
        if record is None or record.alternative != "alternative":
            return True
        return choose_player(plan, ctx, e, "Choose an opponent to discard and draw")
    if k == "sift":
        names, unknown = history.cast_names_this_turn(plan, ctx["controller"])
        from app.cards.names import normalize_name

        if not all(normalize_name(n) in names for n in ("Peer Through Depths", "Reach Through Mists")):
            return insert(ctx, [{"do": "ensure_cast_names", "who": "you"}, e]) if unknown else True
        return insert(ctx, [queries.search("card named The Unspeakable", to="battlefield", may=True)])
    if k == "disorient":
        ids = list(
            dict.fromkeys(
                t["id"]
                for group in ctx.get("groups", [])
                for t in group
                if t
                and t["id"] in plan.state.cards
                and plan.oid(t["id"]) == t.get("object_id")
                and plan.state.cards[t["id"]].zone.endswith(":battlefield")
            )
        )
        context.bind_objects(plan, ctx, bind[4:], ids)
        order = [p for p in plan.apnap() if p != ctx["controller"]]
        # CR101.4: choices in turn order starting after the spell's controller.
        seats = [p for p in plan.state.turn_order() if p in plan.live()]
        i = seats.index(ctx["controller"])
        order = [seats[(i + j) % len(seats)] for j in range(1, len(seats))]
        ctx.setdefault("ordered_choice", {})[bind] = {"order": order, "i": 0, "chosen": []}
        return disorient_choice(plan, ctx, e)
    if k == "hawk":
        # The native move result records whether this exact permanent returned.
        return insert(
            ctx,
            [
                {"do": "bounce", "who": "self", "as": bind[4:]},
                {"do": "ordered_after", "kind": k, "binding": bind},
            ],
        )
    config: dict[str, tuple[str, str, dict[str, Any]]] = {
        "myr": ("artifact card", "exile", {"max": 999, "upto": True, "shuffle": False}),
        "glaciers": ("basic land card", "battlefield_tapped", {}),
        "sanctuary": ("basic land card", "hand", {"may": True}),
        "memories": ("card", "exile", {"upto": False}),
        "rope_search": ("basic land card", "battlefield_tapped", {}),
        "journey": ("land card", "exile", {"max": 5, "upto": True, "distinct_names": True, "link": True}),
        "doomsday": (
            "card",
            "capture",
            {
                "max": 5,
                "upto": False,
                "zones": ["library", "graveyard"],
                "capture_only": True,
                "shuffle": False,
                "reveal": False,
            },
        ),
        "prishe": (
            "basic land card",
            "battlefield_tapped",
            {"alts": [queries.key("basic land card"), queries.key("Town card")]},
        ),
        "grim": (
            "nonland card",
            "capture",
            {"capture_only": True, "shuffle": False, "reveal": True, "upto": False},
        ),
        "dryad": ("Forest card", "battlefield_tapped", {"may": True}),
    }
    kind, to, extra = config[k]
    search = queries.search(kind, to=to, outcome=bind, **extra)
    if k == "dryad":
        ps = effects._players(plan, ctx, "target")
        if not ps:
            return True
        search["entry_player"] = ps[0]
    ctx["search_performed"] = False
    return insert(ctx, [search, {"do": "ordered_after", "kind": k, "binding": bind}])


def choose_player(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], prompt: str) -> bool:
    from app.rules import effects
    from app.rules.plan import decide

    players = effects._players(plan, ctx, "each_opponent")
    if not players:
        return True
    decide(
        plan,
        player=ctx["controller"],
        kind="choose_one",
        prompt=prompt,
        options=[DecisionOption(id=p, label=plan.name(p)) for p in players],
        resume={"step": "ordered_player", "ctx": ctx, "e": e},
    )
    return False


def current(plan: Plan, ctx: dict[str, Any], binding: str, moved: bool = True) -> list[str]:
    name = binding.removeprefix(context.PREFIX)
    if moved:
        before = [ObjectRef.model_validate(r) for r in context.refs(ctx).get(name, {}).get("objects", [])]
        context.bind_moved(plan, ctx, name, before)
    return context.objects(plan, ctx, name)


def after(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import card_names, delayed, effects, history, scripts, this_way

    k = e["kind"]
    bind = e["binding"]
    ids = current(plan, ctx, bind, moved=k not in ("doomsday", "grim", "hawk", "mastery"))
    if k == "myr":
        n = sum(plan.state.cards[c].zone.endswith(":exile") for c in ids)
        native = scripts.parse_effects(f"Create {n} 1/1 colorless Myr artifact creature tokens.")
        assert native is not None
        return insert(ctx, [*native[0], {"do": "shuffle_library", "who": "you"}])
    if k == "glaciers":
        src = effects._cards(plan, ctx, "self")
        if src:
            delayed.create_move(
                plan,
                ctx["controller"],
                src[0],
                plan.oid(src[0]),
                "hand",
                ctx.get("name") or "Return the land",
                step="cleanup",
            )
        return True
    if k == "sanctuary":
        if ctx.get("search_performed"):
            return insert(ctx, [{"do": "skip_next", "who": "you", "what": "draw", "this_turn": True}])
        return True
    if k in ("rope_search", "rope_draw"):
        from app.rules.group_choice import _neighbor

        src = effects._cards(plan, ctx, "self")
        if src:
            return effects.gain_control(
                plan,
                ctx,
                {
                    "who": "self",
                    "to": "player:" + _neighbor(plan, ctx["controller"], True),
                    "duration": "permanent",
                },
            )
        return True
    if k == "memories":
        if not ids:
            return insert(ctx, [{"do": "draw", "who": "you", "n": 3}])
        seats = [p for p in plan.state.turn_order() if p in plan.live()]
        i = seats.index(ctx["controller"])
        order = [seats[(i + j) % len(seats)] for j in range(1, len(seats))]
        ctx.setdefault("ordered_choice", {})[bind] = {"order": order, "i": 0, "cards": ids}
        return memories_choice(plan, ctx, e)
    if k == "doomsday":
        rest = [
            c
            for z in ("library", "graveyard")
            for c in plan.state.zones.get(f"{ctx['controller']}:{z}", [])
            if c not in ids
        ]
        if rest:
            plan.do(
                {"type": "move", "card_ids": rest, "to": {"player": ctx["controller"], "zone": "exile"}},
                actor=ctx["controller"],
            )
        es = [{"do": "to_library", "who": bind, "place": "top"}] if ids else []
        es.append({"do": "lose_life", "who": "you", "n": 0, "half": "up"})
        return insert(ctx, es)
    if k == "prishe":
        if not ctx.get("search_performed"):
            return True
        target = scripts.parse_effects("Put a +1/+1 counter on target creature you control.")
        assert target is not None
        return insert(
            ctx,
            [
                {
                    "do": "reflexive",
                    "cond": {"all": []},
                    "ability": {
                        "kind": "triggered",
                        "trigger": "reflexive",
                        "effects": target[0],
                        "optional": False,
                        **scripts.target_fields(target[1]),
                    },
                }
            ],
        )
    if k == "grim":
        names = {n for c in ids for n in card_names.names_of(plan.ch(plan.state.cards[c]))}
        from app.cards.names import normalize_name

        wanted = {normalize_name(n) for n in names}
        opponents = effects._players(plan, ctx, "each_opponent")
        uncertain = [
            p
            for p in opponents
            if wanted
            and not wanted.intersection(history.cast_names_this_turn(plan, p)[0])
            and history.cast_names_this_turn(plan, p)[1]
        ]
        if uncertain:
            return insert(ctx, [*({"do": "ensure_cast_names", "who": "player:" + p} for p in uncertain), e])
        es = [
            {"do": "lose_life", "who": "player:" + p, "n": 6}
            for p in opponents
            if wanted.intersection(history.cast_names_this_turn(plan, p)[0])
        ]
        es.append({"do": "shuffle_library", "who": "you"})
        return insert(ctx, es)
    if k == "hawk":
        if this_way.count(plan, ctx, {"ref_count": bind[4:], "this_way": "returned"}):
            return insert(ctx, [queries.search("Plains card", to="battlefield_tapped", may=True)])
        return True
    if k == "mastery":
        n = this_way.count(plan, ctx, {"ref_count": bind[4:], "this_way": "discarded", "of": None})
        return insert(ctx, [{"do": "draw", "who": "player:" + e["player"], "n": n}])
    return True


def memories_choice(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    state = ctx["ordered_choice"][e["binding"]]
    if state["i"] >= len(state["order"]):
        return insert(ctx, [{"do": "draw", "who": "you", "n": 3}])
    player = state["order"][state["i"]]
    decide(
        plan,
        player=player,
        kind="confirm",
        prompt="Put the exiled card into its owner's hand instead of letting the caster draw three?",
        options=[
            DecisionOption(id="yes", label="Put it into hand"),
            DecisionOption(id="no", label="Leave it exiled"),
        ],
        resume={"step": "ordered_memories", "ctx": ctx, "e": e},
    )
    return False


def disorient_choice(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    state = ctx["ordered_choice"][e["binding"]]
    ids = current(plan, ctx, e["binding"], moved=False)
    while state["i"] < len(state["order"]):
        p = state["order"][state["i"]]
        own = [c for c in ids if plan.state.cards[c].controller == p]
        if own:
            decide(
                plan,
                player=p,
                kind="confirm",
                prompt="Exile your chosen permanent?",
                options=[
                    DecisionOption(id="yes", label="Exile it"),
                    DecisionOption(id="no", label="Keep it"),
                ],
                resume={"step": "ordered_disorient", "ctx": ctx, "e": e, "card": own[0]},
            )
            return False
        state["i"] += 1
    chosen = [c for c in state["chosen"] if c in ids]
    if chosen:
        plan.do({"type": "move", "card_ids": chosen, "to": {"zone": "exile"}}, actor=ctx["controller"])
    left = current(plan, ctx, e["binding"], moved=False)
    if left:
        return insert(ctx, [queries.search("land card", to="battlefield_tapped", max=len(left), upto=True)])
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    e = d.resume["e"]
    k = d.resume["step"]
    bind = e["binding"]
    done = True
    if k == "ordered_player":
        who = chosen[0]
        insert(
            ctx,
            [
                {"do": "discard", "who": "player:" + who, "n": 0, "upto": True, "as": bind[4:]},
                {"do": "ordered_after", "kind": "mastery", "binding": bind, "player": who},
            ],
        )
    elif k == "ordered_memories":
        state = ctx["ordered_choice"][bind]
        if chosen[0] == "yes":
            insert(ctx, [{"do": "return_card", "who": bind, "to": "hand"}])
        else:
            state["i"] += 1
            done = memories_choice(plan, ctx, e)
    elif k == "ordered_disorient":
        state = ctx["ordered_choice"][bind]
        card = plan.state.cards.get(d.resume["card"])
        verb = "chose to exile" if chosen[0] == "yes" else "chose to keep"
        plan.note(
            f"{plan.name(d.player)} {verb} {(plan.ch(card).name or 'the chosen permanent') if card is not None else 'the chosen permanent'}",
            [card.id] if card is not None else [],
            actor=d.player,
        )
        if chosen[0] == "yes":
            state["chosen"].append(d.resume["card"])
        state["i"] += 1
        done = disorient_choice(plan, ctx, e)
    if done:
        effects.continue_effects(plan, ctx)


PRIMITIVES = {"ordered_tutor": prepare, "ordered_after": after}
RESUME = {k: resume for k in ("ordered_player", "ordered_memories", "ordered_disorient")}
